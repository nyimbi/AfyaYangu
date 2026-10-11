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

# --- §17.6 children's data: the age at which control transfers -----------------------------------

def test_age_is_computed_from_the_dates_not_from_a_constant() -> None:
	"""The first version of this arithmetic was `(2026 - year) * 12 + (10 - month)` — the clock
	written into the expression. It read correctly in October 2026 and nowhere else, and wrong in
	the one direction that matters: a child born in 2008 read as 18 forever, so §17.6's transfer
	never fired, and nobody ever aged, so a 17-year-old enrolled in 2026 was still a minor in 2030."""
	from datetime import date
	from afya.records.service import age_years
	assert age_years('2008-05-01', date(2026, 10, 12)) == 18, 'a birthday already passed this year'
	assert age_years('2008-11-01', date(2026, 10, 12)) == 17, 'a birthday still to come this year'
	assert age_years('2008-10-12', date(2026, 10, 12)) == 18, 'the birthday itself counts'
	assert age_years('2008-10-13', date(2026, 10, 12)) == 17, 'the day before does not'
	assert age_years('2026-01-01', date(2026, 10, 12)) == 0


async def test_control_transfers_at_eighteen() -> None:
	"""§17.6 line 4: "At age 18, control transfers to the individual." Guardianship is a relation
	with an end date, and a rule that read only `guardian_ref == subject_ref` gave a guardian
	perpetual access to a child's record — a 30-year-old's health history readable by whoever
	enrolled them as a minor, which is the failure the line exists to prevent."""
	from datetime import date
	svc = RecordsService()
	await svc.add_member(WalletMember(member_ref='KID', dob_iso='2015-01-01', guardian_ref='GUARD1'),
		today=date(2026, 10, 12))
	assert svc.owns('GUARD1', 'KID') is True, 'a guardian reads their minor'
	assert svc.owns('STRANGER', 'KID') is False
	# The same wallet, read after the child's eighteenth birthday: the relation ended on its own,
	# without anything being re-enrolled — which is the part a stored `is_minor` flag gets wrong.
	after = date(2033, 1, 2)
	assert svc.owns('GUARD1', 'KID', after) is False, 'control transferred to the individual at 18'
	assert svc.owns('GUARD1', 'KID', date(2033, 1, 1)) is False, 'the eighteenth birthday is the transfer'
	assert svc.owns('GUARD1', 'KID', date(2032, 12, 31)) is True, 'the day before it is still a minor'
	assert svc.owns('KID', 'KID', after) is True, 'they still read their own records'


async def test_an_adult_cannot_be_enrolled_as_someone_elses_dependent() -> None:
	"""The assert that stops the transfer being undone by the next enrolment. A guardian_ref on an
	adult is a reference `owns` would have honoured before this rule existed, so the model refuses
	it rather than storing a relation nothing will ever apply."""
	from datetime import date
	svc = RecordsService()
	with pytest.raises(AssertionError, match='an adult controls their own records'):
		await svc.add_member(WalletMember(member_ref='ADULT', dob_iso='1990-01-01', guardian_ref='GUARD1'),
			today=date(2026, 10, 12))
	# Naming yourself is not a guardianship claim, so it is allowed.
	await svc.add_member(WalletMember(member_ref='ADULT', dob_iso='1990-01-01', guardian_ref='ADULT'),
		today=date(2026, 10, 12))
	assert svc.owns('ADULT', 'ADULT') is True
	assert svc.owns('GUARD1', 'ADULT') is False, "a self-named guardian_ref is not a claim by anyone else"


async def test_the_transfer_date_is_reported_not_only_the_boolean() -> None:
	"""A guardian told "no" without a date has no way to know whether the record moved or they
	mistyped a reference, so the route that serves them can answer both questions."""
	from datetime import date
	svc = RecordsService()
	await svc.add_member(WalletMember(member_ref='KID', dob_iso='2015-03-04', guardian_ref='GUARD1'),
		today=date(2026, 10, 12))
	assert svc.transfers_at('KID', date(2026, 10, 12)) == '2033-03-04'
	await svc.add_member(WalletMember(member_ref='ADULT', dob_iso='1990-01-01'),
		today=date(2026, 10, 12))
	assert svc.transfers_at('ADULT', date(2026, 10, 12)) is None, 'already their own controller'


def test_the_canary_watches_the_minor_check_fire() -> None:
	"""The ownership rule's new conjunct is the thing to canary, because dropping it is a silent
	change: `owns` still returns True for the self case and False for a stranger either way, and
	only a guardian-and-adult pair distinguishes the two versions."""
	from datetime import date
	svc = RecordsService()
	svc._members['KID'] = WalletMember(member_ref='KID', dob_iso='2008-01-01', guardian_ref='GUARD1')  # noqa: SLF001
	assert svc.owns('GUARD1', 'KID', date(2026, 10, 12)) is False, 'the age check did not fire'
	# The same stored row, read one day earlier, reads True — so what decided it was the date and
	# not the guardian_ref, which is the conjunct a future edit would be tempted to drop.
	assert svc.owns('GUARD1', 'KID', date(2008, 1, 1)) is True
	# And a member with no guardian at all is still nobody else's to read.
	svc._members['ORPHAN'] = WalletMember(member_ref='ORPHAN', dob_iso='2020-01-01')  # noqa: SLF001
	assert svc.owns('GUARD1', 'ORPHAN', date(2026, 10, 12)) is False
