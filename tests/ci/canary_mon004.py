"""Canaries for tests/ci/test_mon004.py.

Both bullets of §MON-004 are the same shape — a fact that exists and nothing that acts on it — and
that shape is exactly what a canary has to reproduce, because code that *has* the field and never
serves it looks like working code from the service's own tests. Each canary below is a plausible
implementation of the same feature that answers the question incorrectly:

* **The instants are arithmetic instead of a table** (#1) — dividing 24 hours by the frequency is
  the obvious implementation and it produces 03:26 for a seven-dose day. This is the canary that
  catches a "simplification" of the table.
* **The caller's times are honoured** (#2) — the divergence the bullet exists to prevent: a phone
  that sends its own instants decides when a patient is woken.
* **The route answers with the id alone** (#3) — the feature present in the service and absent from
  the served payload, which every unit test over `add_schedule` passes through.
* **The dose is recorded and never queued** (#4) — the bullet failing while the screen says the dose
  was taken. This is the one whose failure mode is lost adherence data after an outage.
* **The dose is queued under a dataset the spec has no rule for** (#5) — `SyncService.enqueue`
  refuses it, so the dose is dropped at the one moment it must be kept.
* **The composition root builds a second tracker with no queue** (#6) — the wiring present in the
  unit test and absent from production, which is why the route test exists.
* **The op id is taken from the head of the uuid** (#7) — the defect this work actually found: a
  UUID7's prefix is its timestamp, so doses logged in one millisecond collide and the queue keeps
  the last.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script. The `__pycache__`
purge after each write is load-bearing for the reason `canary_inf001.py` documents: two canaries
mutating two files with same-length edits in the same second make CPython reuse the previous
canary's bytecode, and the gate then reports a mutation it never made.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
V = ROOT / 'src/afya/monitoring/views.py'
S = ROOT / 'src/afya/monitoring/service.py'
G = ROOT / 'src/afya/service.py'

CANARIES = [
	# 1. The instants become arithmetic. Every property the test checks about *format* still holds —
	#    they are still five-character HH:MM strings, still distinct, still in order — and the first
	#    dose of a six-a-day course moves to 04:00, a time nobody chose.
	('the instants are divided out of 24 hours instead of read from the table', V,
	 "	assert 1 <= times_per_day <= 6, f'{times_per_day} doses a day is outside the table'\n	return list(REMINDER_CLOCK[times_per_day])",
	 "	assert 1 <= times_per_day <= 6, f'{times_per_day} doses a day is outside the table'\n	return [f'{int(24 * i / times_per_day):02d}:00' for i in range(times_per_day)]",
	 'test_the_table_is_a_choice_of_times_and_not_an_even_division_of_the_day'),

	# 2. The service honours the caller's own times. A client can then decide when a patient is
	#    woken, which is the divergence the server-side derivation exists to prevent.
	('the caller’s own reminder times are honoured', S,
	 "		sched.reminder_times = reminder_times(sched.times_per_day)",
	 "		sched.reminder_times = sched.reminder_times or reminder_times(sched.times_per_day)",
	 'test_the_service_derives_the_instants_and_a_caller_cannot_supply_them'),

	# 3. The route answers with the schedule id alone — the shape it had before this change. The
	#    instants are stored, correct, and unreachable, and every test over the service stays green.
	('the route stops serving the instants', G,
	 "		return {'schedule_id': out.schedule_id, 'reminder_times': out.reminder_times}",
	 "		return {'schedule_id': out.schedule_id}",
	 'test_the_route_serves_the_instants_and_binds_the_member_to_the_wallet'),

	# 4. The dose is recorded and never queued. This is the bullet failing: the history on this phone
	#    is right, and the server never learns the dose was taken.
	('the dose is recorded and never queued', S,
	 "		if self._sync is not None:\n			await self._queue_adherence(event)",
	 "		if False:\n			await self._queue_adherence(event)",
	 'test_a_dose_taken_with_no_signal_is_queued_under_the_specs_own_rule'),

	# 5. The dose is queued under a dataset name the spec has no rule for. `enqueue` asserts against
	#    `STRATEGY_MATRIX`, so the dose raises at the one moment it must be kept — and a queue that
	#    silently accepted it would apply a conflict strategy nobody chose.
	('the dose is queued under a dataset with no conflict rule', S,
	 "			dataset='medication',",
	 "			dataset='medications',",
	 'test_a_dose_taken_with_no_signal_is_queued_under_the_specs_own_rule'),

	# 6. The composition root builds the tracker with no queue. The service takes the argument, the
	#    unit test passes one, and production passes none — so every dose is recorded and dropped.
	('the composition root hands the tracker no queue', G,
	 "		'monitoring': MonitoringService(records_svc, sync_svc),",
	 "		'monitoring': MonitoringService(records_svc),",
	 'test_the_route_queues_a_dose_for_a_signed_in_caller'),

	# 7. The op id is taken from the *head* of the uuid, which is its millisecond timestamp. Two
	#    doses logged in one millisecond then share an id, the queue is keyed on it, and the second
	#    overwrites the first — a week of doses replayed after an outage collapses to one.
	('the op id is taken from the timestamp end of the uuid', S,
	 "			op_id='OP-' + uuid7str().replace('-', '').upper()[-8:],",
	 "			op_id='OP-' + uuid7str().replace('-', '').upper()[:8],",
	 'test_a_queued_dose_survives_as_a_pending_change_the_indicator_counts'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_mon004.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	# See the module docstring: a same-second write of the same size reuses the previous canary's
	# bytecode, and the canary then tests code it never mutated. Purged for the file just written.
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly',
			f'tests/ci/test_mon004.py::{node}'], cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
	print(f'{"CAUGHT " if caught else "MISSED "} {name}')
	if not caught:
		failures.append(name)
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
