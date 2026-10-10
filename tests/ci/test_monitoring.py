"""Behavioural tests for afya.monitoring (§9.1, §10.2, §11.3).

Dates are injected as ISO strings so the schedule is exercised deterministically without a clock.
"""
import pytest

from afya.monitoring.service import MonitoringService
from afya.monitoring.views import (
	AdherenceAction, AdherenceEvent, ConditionProfile, MedSchedule, MonitoringDay, PeakFlowReading,
)


def _statuses(rows: list) -> dict[tuple[str, int], str]:
	return {(r.vaccine, r.dose_no): r.status for r in rows}


async def test_schedule_marks_due_and_upcoming_at_fourteen_days() -> None:
	svc = MonitoringService()
	await svc.register_child('c1', '2026-01-01')
	rows = svc.schedule('c1', '2026-01-15')  # age 14 days
	status = _statuses(rows)
	assert status[('BCG', 1)] == 'due'  # due_weeks 0
	assert status[('OPV', 0)] == 'due'  # due_weeks 0
	assert status[('OPV', 1)] == 'upcoming'  # due_weeks 6 -> day 42
	assert status[('PCV10', 1)] == 'upcoming'
	assert status[('Measles-Rubella', 1)] == 'upcoming'  # due_weeks 39


async def test_schedule_marks_overdue_after_grace_window() -> None:
	svc = MonitoringService()
	await svc.register_child('c1', '2026-01-01')
	rows = svc.schedule('c1', '2026-03-05')  # age 63 days
	status = _statuses(rows)
	assert status[('BCG', 1)] == 'overdue'  # due day 0, grace 28 days elapsed
	assert status[('OPV', 0)] == 'overdue'
	assert status[('OPV', 1)] == 'due'  # due day 42, grace runs to day 70


async def test_schedule_marks_given_and_ignores_age() -> None:
	svc = MonitoringService()
	await svc.register_child('c1', '2026-01-01')
	await svc.record_dose('c1', 'BCG', 1, '2026-01-02')
	rows = svc.schedule('c1', '2026-03-05')
	assert _statuses(rows)[('BCG', 1)] == 'given'


async def test_schedule_sets_reminder_lead_three_days_before() -> None:
	svc = MonitoringService()
	await svc.register_child('c1', '2026-01-01')
	rows = svc.schedule('c1', '2026-02-09')  # OPV dose 1 due day 42 = 2026-02-12; 3 days out
	opv1 = next(r for r in rows if (r.vaccine, r.dose_no) == ('OPV', 1))
	assert opv1.status == 'upcoming'
	assert opv1.remind_days_before == [3]
	assert opv1.due_age_weeks == 6


async def test_catch_up_names_defaulted_doses() -> None:
	svc = MonitoringService()
	await svc.register_child('c1', '2026-01-01')
	report = svc.catch_up('c1', '2026-03-05')  # age 63 days
	assert report.defaulted == ['BCG dose 1', 'OPV dose 0']
	assert report.advise.startswith('2 dose(s) behind schedule')


async def test_catch_up_reports_clean_when_nothing_missed() -> None:
	svc = MonitoringService()
	await svc.register_child('c1', '2026-01-01')
	report = svc.catch_up('c1', '2026-01-15')
	assert report.defaulted == []
	assert report.advise == 'No missed doses: the child is up to date.'


async def test_record_dose_refuses_unknown_vaccine() -> None:
	svc = MonitoringService()
	await svc.register_child('c1', '2026-01-01')
	with pytest.raises(AssertionError):
		await svc.record_dose('c1', 'Unobtainium', 1, '2026-01-02')


async def test_adherence_percentage_and_refill_detection() -> None:
	svc = MonitoringService()
	await svc.add_schedule(MedSchedule(
		schedule_id='MED-ABC123', member_ref='m1', drug='Amlodipine', dose='5mg', start_iso='2026-01-01',
		times_per_day=2, duration_days=10, refill_at_days_left=2,  # expected 20 doses, refill window 4
	))
	for i in range(17):
		await svc.record_adherence(AdherenceEvent(schedule_id='MED-ABC123', at_iso=f'2026-01-{i + 1:02d}', action=AdherenceAction.taken))
	await svc.record_adherence(AdherenceEvent(schedule_id='MED-ABC123', at_iso='2026-01-20', action=AdherenceAction.skipped))
	await svc.record_adherence(AdherenceEvent(schedule_id='MED-ABC123', at_iso='2026-01-21', action=AdherenceAction.snoozed))
	report = svc.adherence('MED-ABC123')
	assert report.expected_doses == 20
	assert report.taken == 17 and report.skipped == 1 and report.snoozed == 1
	assert report.adherence_pct == 85.0
	assert report.refill_due is True  # 3 doses left <= 2 days * 2/day


async def test_refill_not_due_when_window_is_tight() -> None:
	svc = MonitoringService()
	await svc.add_schedule(MedSchedule(
		schedule_id='MED-ABC123', member_ref='m1', drug='Metformin', dose='500mg', start_iso='2026-01-01',
		times_per_day=2, duration_days=10, refill_at_days_left=1,  # window 2 doses
	))
	for i in range(17):
		await svc.record_adherence(AdherenceEvent(schedule_id='MED-ABC123', at_iso=f'2026-01-{i + 1:02d}', action=AdherenceAction.taken))
	report = svc.adherence('MED-ABC123')
	assert report.adherence_pct == 85.0
	assert report.refill_due is False  # 3 left > 2-dose window


async def test_adherence_refuses_unknown_schedule() -> None:
	svc = MonitoringService()
	with pytest.raises(AssertionError):
		await svc.record_adherence(AdherenceEvent(schedule_id='MED-ZZZ999', at_iso='2026-01-01', action=AdherenceAction.taken))


async def test_peak_flow_zones_against_personal_best() -> None:
	svc = MonitoringService()
	green = await svc.log_peak_flow(PeakFlowReading(subject_ref='s1', litres_per_min=400, personal_best=500))
	assert green['zone'] == 'green' and green['pct_of_best'] == 80.0
	yellow = await svc.log_peak_flow(PeakFlowReading(subject_ref='s1', litres_per_min=399, personal_best=500))
	assert yellow['zone'] == 'yellow' and yellow['pct_of_best'] == 79.8
	yellow_floor = await svc.log_peak_flow(PeakFlowReading(subject_ref='s1', litres_per_min=250, personal_best=500))
	assert yellow_floor['zone'] == 'yellow' and yellow_floor['pct_of_best'] == 50.0
	red = await svc.log_peak_flow(PeakFlowReading(subject_ref='s1', litres_per_min=249, personal_best=500))
	assert red['zone'] == 'red' and red['pct_of_best'] == 49.8
	assert '719' in str(red['advise'])


async def test_peak_flow_first_reading_is_its_own_best() -> None:
	svc = MonitoringService()
	out = await svc.log_peak_flow(PeakFlowReading(subject_ref='s1', litres_per_min=430))
	assert out['zone'] == 'green' and out['pct_of_best'] == 100.0


async def test_shareable_report_withholds_hiv() -> None:
	svc = MonitoringService()
	await svc.set_conditions(ConditionProfile(subject_ref='s1', conditions=['asthma', 'HIV'], hiv_pin_set=True))
	report = svc.shareable_report('s1')
	assert report['conditions'] == ['asthma']
	assert report['withheld'] == ['HIV status (separate consent required)']


async def test_hiv_condition_requires_separate_pin() -> None:
	svc = MonitoringService()
	with pytest.raises(AssertionError):
		await svc.set_conditions(ConditionProfile(subject_ref='s1', conditions=['HIV'], hiv_pin_set=False))


async def test_log_day_escalates_on_fever_threshold() -> None:
	svc = MonitoringService()
	svc.enrol('s1', officer='chw-1')
	calm = await svc.log_day(MonitoringDay(entry_id='MON-ABCD1234', subject_ref='s1', day=1, temperature_c=37.9))
	assert calm.escalate is False and calm.notify_chw is False
	assert calm.days_remaining == 20
	fever = await svc.log_day(MonitoringDay(entry_id='MON-ABCD1235', subject_ref='s1', day=2, temperature_c=38.0))
	assert fever.escalate is True and fever.notify_chw is True
	assert 'fever' in fever.message


async def test_log_day_escalates_on_any_alert_symptom() -> None:
	svc = MonitoringService()
	svc.enrol('s1', officer='chw-1')
	out = await svc.log_day(MonitoringDay(entry_id='MON-ABCD1234', subject_ref='s1', day=3, temperature_c=36.6, symptoms=['headache']))
	assert out.escalate is True
	assert 'headache' in out.message


async def test_log_day_ignores_non_alert_symptom() -> None:
	svc = MonitoringService()
	svc.enrol('s1', officer='chw-1')
	out = await svc.log_day(MonitoringDay(entry_id='MON-ABCD1234', subject_ref='s1', day=1, temperature_c=36.6, symptoms=['cough']))
	assert out.escalate is False
	assert out.days_remaining == 20


async def test_log_day_without_officer_does_not_notify_chw() -> None:
	svc = MonitoringService()
	svc.enrol('s1')  # no monitoring officer
	out = await svc.log_day(MonitoringDay(entry_id='MON-ABCD1234', subject_ref='s1', day=21, temperature_c=39.1))
	assert out.escalate is True
	assert out.notify_chw is False
	assert out.days_remaining == 0


async def test_log_day_refuses_unenrolled_subject() -> None:
	svc = MonitoringService()
	with pytest.raises(AssertionError):
		await svc.log_day(MonitoringDay(entry_id='MON-ABCD1234', subject_ref='ghost', day=1, temperature_c=36.6))


async def test_diary_and_missing_day_window() -> None:
	svc = MonitoringService()
	svc.enrol('s1', officer='chw-1')
	await svc.log_day(MonitoringDay(entry_id='MON-ABCD1234', subject_ref='s1', day=3, temperature_c=36.6))
	await svc.log_day(MonitoringDay(entry_id='MON-ABCD1235', subject_ref='s1', day=1, temperature_c=36.6))
	assert [e.day for e in svc.diary('s1')] == [1, 3]
	missing = svc.adherence_reminder_days('s1')
	assert len(missing) == 19
	assert 1 not in missing and 3 not in missing


async def test_nutrition_guidance_is_age_appropriate() -> None:
	svc = MonitoringService()
	assert svc.nutrition_guidance(0).guidance.startswith('Exclusive breastfeeding')
	assert svc.nutrition_guidance(5).guidance.startswith('Exclusive breastfeeding')
	assert svc.nutrition_guidance(6).seasonal_foods == ['mashed pumpkin', 'avocado', 'well-cooked beans']
	assert svc.nutrition_guidance(11).guidance.startswith('Start soft mashed foods')
	assert svc.nutrition_guidance(12).seasonal_foods == ['ugali', 'sukuma wiki', 'eggs', 'small fish']
	assert svc.nutrition_guidance(23).age_months == 23
	assert svc.nutrition_guidance(24).guidance.startswith('Balanced plate')
	assert svc.nutrition_guidance(60).seasonal_foods == ['githeri', 'milk', 'fruit in season']


def test_nutrition_guidance_refuses_out_of_range_age() -> None:
	svc = MonitoringService()
	with pytest.raises(AssertionError):
		svc.nutrition_guidance(61)
