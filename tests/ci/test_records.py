import pytest

from afya.records.service import RecordsService
from afya.records.views import GrowthRecord, ImmunisationRecord, MedReminder, WalletMember


async def test_minor_requires_guardian() -> None:
	svc = RecordsService()
	with pytest.raises(AssertionError):
		await svc.add_member(WalletMember(member_ref='KID1', dob_iso='2015-01-01'))
	await svc.add_member(WalletMember(member_ref='KID1', dob_iso='2015-01-01', guardian_ref='GUARD1'))
	assert svc._members['KID1'].is_minor  # noqa: SLF001 — contract check


async def test_epi_gap_detection() -> None:
	svc = RecordsService()
	await svc.add_member(WalletMember(member_ref='CH1', dob_iso='2025-10-01', guardian_ref='GUARD1'))  # ~12 months
	gaps = svc.immunisation_gaps('CH1')
	assert 'BCG dose 1' in gaps or 'PCV10 dose 1' in gaps
	await svc.record_immunisation(ImmunisationRecord(member_ref='CH1', vaccine='BCG', dose_no=1, given_iso='2025-10-02'))
	assert 'BCG dose 1' not in svc.immunisation_gaps('CH1')


def test_growth_underweight_flag() -> None:
	svc = RecordsService()
	flag = svc.growth_flag(GrowthRecord(member_ref='CH1', age_months=12, weight_kg=4.5, height_cm=74.5))
	assert flag.flag == 'underweight'
	normal = svc.growth_flag(GrowthRecord(member_ref='CH1', age_months=12, weight_kg=9.5, height_cm=74.5))
	assert normal.flag == 'normal'


def test_growth_stunted_flag() -> None:
	svc = RecordsService()
	flag = svc.growth_flag(GrowthRecord(member_ref='CH1', age_months=24, weight_kg=11.0, height_cm=70.0))
	assert flag.flag == 'stunted'


async def test_reminders() -> None:
	svc = RecordsService()
	rem = MedReminder(member_ref='CH1', drug='amoxicillin', times_per_day=3, started_iso='2026-10-01', channel='sms')
	await svc.add_reminder(rem)
	assert svc.reminders_for('CH1') == [rem]
	assert svc.reminders_for('OTHER') == []