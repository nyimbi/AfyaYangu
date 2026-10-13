"""§MON-004 — medication reminders, and the two Features that were a count and a route.

The section prints seven Features and five had carriers. The two that did not failed in the two ways
this codebase keeps failing:

- **"Multiple daily reminders"** — `times_per_day` was a count, and a count cannot be notified at.
  A twice-daily course had no morning and no evening anywhere in the system, so the client that
  wanted to wake somebody had to invent both, and two clients inventing them would invent two
  different days. The schedule now carries the instants, derived once, server-side.
- **"Works with no data connection"** — a dose was recordable only through an HTTP route. The dose
  is the highest-frequency health action anyone takes and the one most likely to be logged with no
  bars, and `SyncService` already had a `medication` conflict rule with nothing queueing a dose
  through it. A rule with no producer is a rule for a dataset nothing writes.

The two are the same shape as §MON-001's defect and are tested the same way: the fact must exist
*and* something must act on it, so the tests below read the served payload and the queue rather than
the field.
"""
import httpx
import pytest

from afya.monitoring.service import MonitoringService
from afya.monitoring.views import (
	REMINDER_CLOCK, AdherenceAction, AdherenceEvent, MedSchedule, reminder_times,
)
from afya.service import build_services, create_app
from afya.sync.service import SyncService
from afya.sync.views import ConflictStrategy, ConnectionClass, SyncOp

def _schedule(times_per_day: int = 2, schedule_id: str = 'MED-ABC123') -> MedSchedule:
	return MedSchedule(schedule_id=schedule_id, member_ref='m1', drug='Amlodipine', dose='5mg',
	                   times_per_day=times_per_day, start_iso='2026-01-01', duration_days=10)


def _event(schedule_id: str = 'MED-ABC123', action: AdherenceAction = AdherenceAction.taken) -> AdherenceEvent:
	return AdherenceEvent(schedule_id=schedule_id, at_iso='2026-01-01T08:00:00Z', action=action)


async def _token(c: httpx.AsyncClient, subject: str = 'U1') -> dict[str, str]:
	tok = (await c.post('/auth/anonymous', json={'subject_ref': subject})).json()['token']
	return {'Authorization': f'Bearer {tok}'}


# --- "Multiple daily reminders": instants, not a count --------------------------------------------

def test_every_supported_frequency_has_instants_and_they_are_times_of_day() -> None:
	"""The bullet asks for reminders, and a reminder is an instant.

	`times_per_day` is `ge=1, le=6`, so the table has to cover six frequencies — and the instants
	have to be *times*: a four-character `HH:MM` on a 24-hour clock. The load-bearing property is
	that they are **distinct**, because two reminders at one instant are one reminder.

	Clock order is asserted only up to the midnight wrap, which the six-a-day course deliberately
	crosses: 06/10/14/18/22/02 is a four-hourly schedule, and a table sorted into 02:00-first would
	put the dose after midnight *before* the morning one, which is the wrong day.
	"""
	for per_day in range(1, 7):
		times = reminder_times(per_day)
		assert len(times) == per_day, f'{per_day}/day produced {len(times)} instants'
		assert len(set(times)) == per_day, f'{per_day}/day repeats an instant: {times}'
		assert all(len(t) == 5 and t[2] == ':' and t[:2].isdigit() and t[3:].isdigit() for t in times), times
		assert all(0 <= int(t[:2]) <= 23 and 0 <= int(t[3:]) <= 59 for t in times), times
		minutes = [int(t[:2]) * 60 + int(t[3:]) for t in times]
		descents = [i for i in range(1, len(minutes)) if minutes[i] < minutes[i - 1]]
		assert len(descents) <= 1, f'{per_day}/day crosses midnight more than once: {times}'
		if descents:
			assert descents == [len(minutes) - 1], f'{per_day}/day wraps before its last dose: {times}'


def test_the_table_is_a_choice_of_times_and_not_an_even_division_of_the_day() -> None:
	"""The property the table exists for, and the one arithmetic cannot satisfy.

	`REMINDER_CLOCK`'s own comment gives the reason: the instants are chosen "so that a twice-daily
	course lands on morning and evening rather than on two arbitrary hours". Dividing 24 hours by the
	frequency is the obvious implementation and it passes every structural check above — the strings
	are still well-formed, still distinct, still ordered — while giving a twice-daily course midnight
	and noon, which is one dose in the middle of the night and one in the middle of the day.

	So the check is on the *choice*: a twice-daily course is a morning and an evening, and no
	frequency's first dose is at midnight, which is the boundary of a day and not a time to be woken.
	"""
	per_day_2 = reminder_times(2)
	assert len(per_day_2) == 2
	first, second = (int(t[:2]) for t in per_day_2)
	assert 5 <= first <= 11, f'a twice-daily course starts at {per_day_2[0]}, not in the morning'
	assert 17 <= second <= 23, f'a twice-daily course ends at {per_day_2[1]}, not in the evening'
	for per_day in range(1, 7):
		assert reminder_times(per_day)[0] != '00:00', (
			f'{per_day}/day starts at midnight, which is an even division of the day and not a time')


def test_a_frequency_outside_the_table_is_refused_rather_than_approximated() -> None:
	"""`MedSchedule.times_per_day` is bounded at 6, so 7 is not a schedule a client can file.

	The refusal matters because the alternative — dividing 24 hours evenly — produces 03:26 for a
	seven-times-a-day course, a time nobody chose, presented to a patient as the time to take a
	medicine.
	"""
	assert 6 in REMINDER_CLOCK, 'the model allows six and the table must cover it'
	for bad in (0, 7, -1):
		with pytest.raises(AssertionError):
			reminder_times(bad)


async def test_the_service_derives_the_instants_and_a_caller_cannot_supply_them() -> None:
	"""The schedule a client files carries no times; the service fills them.

	A client that *could* supply them would let a phone decide when a patient is woken, which is the
	divergence the bullet exists to prevent — so a supplied list is overwritten rather than honoured.
	"""
	svc = MonitoringService()
	claimed = MedSchedule(schedule_id='MED-XYZ789', member_ref='m1', drug='Metformin', dose='500mg',
	                      times_per_day=2, start_iso='2026-01-01', duration_days=5,
	                      reminder_times=['03:00', '03:00'])
	out = await svc.add_schedule(claimed)
	assert out.reminder_times == list(REMINDER_CLOCK[2]), 'the caller’s times survived the service'
	assert len(set(out.reminder_times)) == 2, 'two reminders at one instant is one reminder'


async def test_the_route_serves_the_instants_and_binds_the_member_to_the_wallet() -> None:
	"""The front door, which is where the feature is either present or not.

	A unit test over `add_schedule` says nothing about what the route returns, and the route used to
	answer with the schedule id alone — so a client had the count and no times. The second half is
	the existing guard: a schedule cannot be filed against a stranger's child.
	"""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		u1 = await _token(c, 'U1')
		u2 = await _token(c, 'U2')
		await c.post('/records/member', json={'member_ref': 'U1', 'dob_iso': '1990-01-01'}, headers=u1)
		await c.post('/records/member', json={'member_ref': 'KID-1', 'dob_iso': '2024-01-01',
		                                      'guardian_ref': 'U1'}, headers=u1)

		body = {'member_ref': 'KID-1', 'drug': 'Amoxicillin', 'dose': '5ml', 'times_per_day': 3,
		        'start_iso': '2026-10-13', 'duration_days': 5}
		ok = await c.post('/monitoring/medication', json=body, headers=u1)
		assert ok.status_code == 200, ok.text
		assert ok.json()['reminder_times'] == list(REMINDER_CLOCK[3]), ok.json()
		assert ok.json()['schedule_id'].startswith('MED-')

		cross = await c.post('/monitoring/medication', json=body, headers=u2)
		assert cross.status_code == 403, 'a schedule filed against another wallet’s child'


# --- "Works with no data connection": the dose reaches the queue ----------------------------------

async def test_a_dose_taken_with_no_signal_is_queued_under_the_specs_own_rule() -> None:
	"""The dose must reach the sync queue, and under the dataset §16.3 already names.

	`CONFLICT_RULES` carries `medication` as last-write-wins with the rationale "Personal", so the
	strategy applied on replay is the spec's own rather than one chosen at the call site. A dose
	recorded and never queued is a dose the server never learns about, which is the bullet failing
	while the screen says it was recorded.
	"""
	sync = SyncService()
	svc = MonitoringService(sync=sync)
	await svc.add_schedule(_schedule())
	assert sync.offline_state(ConnectionClass.offline).pending == 0, 'nothing queued before the dose'

	await svc.record_adherence(_event(action=AdherenceAction.taken))
	queued = [o for o in sync._queue.values() if not o.synced]  # noqa: SLF001 - the queue is the evidence
	assert len(queued) == 1, 'the dose did not reach the queue'
	op = queued[0]
	assert op.dataset == 'medication', op.dataset
	assert sync.strategy_for(op.dataset) is ConflictStrategy.lww, 'the spec’s own rule for this data'
	assert op.payload['schedule_id'] == 'MED-ABC123'
	assert op.payload['action'] == 'taken' and op.payload['at_iso'] == '2026-01-01T08:00:00Z'


async def test_a_queued_dose_survives_as_a_pending_change_the_indicator_counts() -> None:
	"""§16.1's promise is that an offline write is *kept*, and the indicator is where that shows.

	Two doses with no signal are two pending changes, and they are still there after a flush that
	cannot send them — which is the difference between a queue and a drop.
	"""
	sync = SyncService()
	svc = MonitoringService(sync=sync)
	await svc.add_schedule(_schedule())
	for action in (AdherenceAction.taken, AdherenceAction.snoozed):
		await svc.record_adherence(_event(action=action))
	assert sync.offline_state(ConnectionClass.offline).pending == 2

	await sync.flush(now_ms=1, connection=ConnectionClass.offline)
	assert sync.offline_state(ConnectionClass.offline).pending == 2, 'an offline flush dropped a dose'


async def test_a_schedule_with_no_queue_still_records_the_dose_locally() -> None:
	"""The service is constructible without a sync layer, and then the dose is kept and not queued.

	This is the honest reading of the dependency: the *tracker* owns the dose and the queue is how
	it travels. A service built with no queue must not raise, or every existing caller that builds
	one breaks — and the adherence history, which is the other five bullets, keeps working.
	"""
	svc = MonitoringService()
	await svc.add_schedule(_schedule())
	report = await svc.record_adherence(_event(action=AdherenceAction.taken))
	assert report.taken == 1 and report.expected_doses == 20


async def test_the_route_queues_a_dose_for_a_signed_in_caller() -> None:
	"""The composition root wires the queue in, so the *route* is what has to be checked.

	A dose posted to `/monitoring/medication/adherence` must appear in the app's own sync queue —
	the service taking a queue as an optional argument proves nothing about whether production
	passes one.
	"""
	svc = build_services()
	app = create_app(svc)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		u1 = await _token(c, 'U1')
		await c.post('/records/member', json={'member_ref': 'U1', 'dob_iso': '1990-01-01'}, headers=u1)
		made = await c.post('/monitoring/medication', json={
			'member_ref': 'U1', 'drug': 'Amlodipine', 'dose': '5mg', 'times_per_day': 2,
			'start_iso': '2026-10-13', 'duration_days': 30}, headers=u1)
		assert made.status_code == 200, made.text
		sid = made.json()['schedule_id']

		posted = await c.post('/monitoring/medication/adherence', json={
			'schedule_id': sid, 'at_iso': '2026-10-13T08:00:00Z', 'action': 'taken'}, headers=u1)
		assert posted.status_code == 200, posted.text
		assert posted.json()['taken'] == 1

		sync: SyncService = svc['sync']  # type: ignore[assignment]
		ops = [o for o in sync._queue.values() if o.dataset == 'medication']  # noqa: SLF001
		assert len(ops) == 1, 'the composition root did not hand the tracker a queue'
		assert ops[0].payload['schedule_id'] == sid


def test_the_dataset_the_dose_is_queued_under_is_the_one_the_rule_is_written_for() -> None:
	"""The join between the two halves of the bullet, asserted as a value rather than assumed.

	`SyncService.enqueue` refuses a dataset outside `STRATEGY_MATRIX`, so a typo here would raise at
	the first dose rather than silently queue. This is the cheap gate that says the string is right.
	"""
	from afya.sync.views import STRATEGY_MATRIX

	assert 'medication' in STRATEGY_MATRIX
	assert SyncOp(op_id='OP-ABCDEF12', dataset='medication', client_ts=0).dataset == 'medication'
