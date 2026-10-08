"""Records service — wallet CRUD, EPI completeness, growth flags, med reminders."""
from afya.logmixin import LogMixin
from afya.records.views import (
	EPI_SCHEDULE, GrowthFlag, GrowthRecord, ImmunisationRecord, MedReminder, WalletMember,
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

	async def add_reminder(self, reminder: MedReminder) -> MedReminder:
		self._reminders.append(reminder)
		return reminder

	def reminders_for(self, member_ref: str) -> list[MedReminder]:
		return [r for r in self._reminders if r.member_ref == member_ref]