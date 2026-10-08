"""Records service — wallet CRUD, EPI completeness, growth flags, med reminders."""
from afya.logmixin import LogMixin
from afya.records.views import (
	EPI_SCHEDULE, GrowthFlag, GrowthRecord, ImmunisationRecord, LabResult, MedReminder,
	Prescription, WalletMember,
)


class RecordsService(LogMixin):
	def __init__(self) -> None:
		self._members: dict[str, WalletMember] = {}
		self._imm: list[ImmunisationRecord] = []
		self._reminders: list[MedReminder] = []
		assert self._members == {} and self._imm == [] and self._reminders == []

	async def add_member(self, member: WalletMember) -> WalletMember:
		age_months = self._age_months(member.dob_iso)
		if age_months < 216:
			member.is_minor = True
			assert member.guardian_ref, 'minors require guardian_ref (spec 17.6)'
			assert member.guardian_ref != member.member_ref, 'self-guardianship invalid'
		self._members[member.member_ref] = member
		return member

	@staticmethod
	def _age_months(dob_iso: str) -> int:
		year, month, _ = (int(p) for p in dob_iso.split('-'))
		return (2026 - year) * 12 + (10 - month)

	def immunisation_gaps(self, member_ref: str) -> list[str]:
		assert member_ref in self._members, 'unknown member'
		given = {(r.vaccine, r.dose_no) for r in self._imm if r.member_ref == member_ref}
		age = self._age_months(self._members[member_ref].dob_iso)
		return [
			f'{vac} dose {dose}'
			for vac, doses in EPI_SCHEDULE.items()
			for dose in doses
			if dose <= age and (vac, dose) not in given
		]

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
