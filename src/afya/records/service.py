"""Records service — wallet CRUD, EPI completeness, growth flags, med reminders."""
from datetime import date

from afya.logmixin import LogMixin
from afya.records.views import (
	EPI_SCHEDULE, GrowthFlag, GrowthRecord, ImmunisationRecord, LabResult, MedReminder,
	Prescription, WalletMember,
)

MAJORITY_YEARS = 18
"""§17.6's age of majority. Children under 18 require guardian consent for an identified profile
and a guardian controls their records; at 18 control transfers to the individual."""


def age_years(dob_iso: str, today: date) -> int:
	"""Whole years between a date of birth and today, from the dates rather than from a constant.

	The earlier version of this computed months as `(2026 - year) * 12 + (10 - month)`, which is
	the same arithmetic with the clock written into it: correct for an October 2026 run and wrong
	everywhere else, and wrong in the one direction that matters. It made a child born in 2008 read
	as 18 forever, so §17.6's transfer of control never fired; it also aged nobody, so a 17-year-old
	enrolled in 2026 was still a minor in 2030.
	"""
	year, month, day = (int(p) for p in dob_iso.split('-')[:3])
	born = date(year, month, day)
	return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


class RecordsService(LogMixin):
	def __init__(self) -> None:
		self._members: dict[str, WalletMember] = {}
		self._imm: list[ImmunisationRecord] = []
		self._reminders: list[MedReminder] = []
		assert self._members == {} and self._imm == [] and self._reminders == []

	async def add_member(self, member: WalletMember, today: date | None = None) -> WalletMember:
		"""Enrol a member, and set the flag §17.6 hangs ownership on.

		`today` is optional so a caller that has no clock (a test, a replay) can say what day it is;
		the default reads the real one, because a service that refuses to know the date cannot
		implement an age-dependent rule at all.
		"""
		today = today or date.today()
		if age_years(member.dob_iso, today) < MAJORITY_YEARS:
			member.is_minor = True
			assert member.guardian_ref, 'minors require guardian_ref (spec 17.6)'
			assert member.guardian_ref != member.member_ref, 'self-guardianship invalid'
		else:
			# §17.6 "At age 18, control transfers to the individual." A member who is already 18 is
			# their own controller, so a guardian recorded on them is not an owner — it is a
			# guardian_ref that `owns` would honour and must not.
			member.is_minor = False
			assert member.guardian_ref in (None, member.member_ref), \
				'an adult controls their own records (spec 17.6)'
		self._members[member.member_ref] = member
		return member

	def immunisation_gaps(self, member_ref: str, today: date | None = None) -> list[str]:
		assert member_ref in self._members, 'unknown member'
		given = {(r.vaccine, r.dose_no) for r in self._imm if r.member_ref == member_ref}
		age = age_years(self._members[member_ref].dob_iso, today or date.today()) * 12
		return [
			f'{vac} dose {dose}'
			for vac, doses in EPI_SCHEDULE.items()
			for dose in doses
			if dose <= age and (vac, dose) not in given
		]

	def owns(self, subject_ref: str, member_ref: str, today: date | None = None) -> bool:
		"""Whether `subject_ref` may read `member_ref`'s records: a person reads their own, and a
		guardian reads the *minors* in their wallet (§17.6). This is the single ownership rule every
		family-record route binds to, so a route cannot invent a looser one.

		The minor test is the load-bearing part and it used to be absent. §17.6's fourth line — "At
		age 18, control transfers to the individual" — makes guardianship a relation with an end
		date, and a rule that read only `guardian_ref == subject_ref` gave a guardian perpetual
		access to a child's record. A 30-year-old's health history was readable by whoever enrolled
		them as a minor, which is the failure the line exists to prevent.

		The age is computed from the date of birth on every call rather than read off `is_minor`.
		That flag records what was true when the member was enrolled, and a flag is the wrong place
		for a rule whose whole content is that it stops being true: a wallet enrolled in 2026 would
		carry a seventeen-year-old as a minor in 2030, and the transfer would happen only if someone
		re-enrolled them. `today` is optional for the same reason it is on `add_member`.

		The reverse is not granted: a member does not read their guardian's records, and no route
		here offers that, so nothing depends on it.
		"""
		if subject_ref == member_ref:
			return True
		member = self._members.get(member_ref)
		if member is None or member.guardian_ref != subject_ref:
			return False
		return age_years(member.dob_iso, today or date.today()) < MAJORITY_YEARS

	def transfers_at(self, member_ref: str, today: date | None = None) -> str | None:
		"""§17.6's transfer date, or None for a member who is already their own controller.

		A route serving a guardian needs to answer "when does this stop" as well as "may I read it",
		and the answer is a date rather than a boolean: a guardian told "no" without a date has no
		way to know whether the record moved or they mistyped a reference.
		"""
		assert member_ref in self._members, 'unknown member'
		member = self._members[member_ref]
		if age_years(member.dob_iso, today or date.today()) >= MAJORITY_YEARS:
			return None
		year, month, day = (int(p) for p in member.dob_iso.split('-')[:3])
		return date(year + MAJORITY_YEARS, month, day).isoformat()

	def assert_owns(self, subject_ref: str, member_ref: str) -> None:
		assert self.owns(subject_ref, member_ref), 'these records belong to someone else'

	async def record_immunisation(self, rec: ImmunisationRecord) -> None:
		self._imm.append(rec)
		self._log_info('immunisation recorded', member=rec.member_ref, vaccine=rec.vaccine)

	def growth_flag(self, rec: GrowthRecord) -> GrowthFlag:
		assert rec.weight_kg > 0 and rec.height_cm > 0, 'measurements positive'
		weight_band = {1: (4.0, 12.0), 12: (7.0, 12.0), 24: (9.0, 15.0), 36: (11.0, 18.0), 48: (13.0, 21.0), 60: (15.0, 24.0)}
		band = weight_band[min(weight_band, key=lambda k: abs(k - rec.age_months))]
		low, high = band
		flag = 'underweight' if rec.weight_kg < low * 0.75 else 'normal'
		height_band = {0: 49.9, 12: 74.8, 24: 87.1, 36: 96.1, 48: 103.3, 60: 110.0}
		median_h = height_band[min(height_band, key=lambda k: abs(k - rec.age_months))]
		if rec.height_cm < median_h * 0.9:
			flag = 'stunted'
		return GrowthFlag(member_ref=rec.member_ref, flag=flag)

	def wallet(self, guardian_ref: str) -> dict[str, object]:
		assert guardian_ref in self._members, 'unknown guardian'
		kids = [m for m in self._members.values() if m.guardian_ref == guardian_ref]
		return {
			'guardian': self._members[guardian_ref].model_dump(mode='json'),
			'members': [m.model_dump(mode='json') for m in kids],
			'gaps': {m.member_ref: self.immunisation_gaps(m.member_ref) for m in kids},
		}

	async def add_reminder(self, reminder: MedReminder) -> MedReminder:
		self._reminders.append(reminder)
		return reminder

	def reminders_for(self, member_ref: str) -> list[MedReminder]:
		return [r for r in self._reminders if r.member_ref == member_ref]

	def __init_labs(self) -> None:
		self._labs: list[LabResult] = []
		self._rx: list[Prescription] = []

	async def add_lab(self, res: LabResult) -> None:
		if not hasattr(self, '_labs'):
			self.__init_labs()
		self._labs.append(res)
		if res.flag == 'critical':
			self._log_warn('critical lab result', test=res.test)

	def labs(self, member_ref: str) -> list[LabResult]:
		if not hasattr(self, '_labs'):
			self.__init_labs()
		return [l for l in self._labs if l.member_ref == member_ref]

	async def add_prescription(self, rx: Prescription) -> None:
		if not hasattr(self, '_rx'):
			self.__init_labs()
		self._rx.append(rx)

	def prescriptions(self, member_ref: str) -> list[Prescription]:
		if not hasattr(self, '_rx'):
			self.__init_labs()
		return [r for r in self._rx if r.member_ref == member_ref]
