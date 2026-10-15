"""Canaries for tests/ci/test_com101.py.

§COM-101's offline bullet failed in the quietest way this codebase has: every part of it existed
except the join. `SyncService` carried a `case_reports` rule in §16.3's matrix, `CaseReport` carried
a `reported_offline` flag, the mobile catalogue carried the field on its form — and nothing put a
report in the queue. A screen rendering the form looked finished, which is why the audit row and not
the UI is where it was found.

So every canary here is a plausible way to keep failing while the form still works, and the two
directions are the two ways this bullet can be wrong: a report that never reaches the queue, and a
report that reaches it when it should not.

* **The report is recorded and never queued** (#1) — the bullet failing outright, with the screen
  saying the case was filed and the server never learning of it.
* **Every report is queued, not only the offline ones** (#2) — the queue as a duplicate factory, and
  §5.4's dedup cannot catch the copy: a CHW logging offline carries no MSISDN, so the key is `None`
  and two replays of one report are two cases in the count PHEOC reads.
* **The dataset is one the spec has no rule for** (#3) — `enqueue` asserts against `STRATEGY_MATRIX`,
  so this raises at the first offline report rather than queueing it, and the case is lost at the
  moment it was most likely to be filed.
* **The payload carries a reference instead of the report** (#4) — §COM-101's "stored locally" read
  as "a note that something happened". The officer then receives a case with no symptoms, no village
  and no temperature.
* **The nulls are dropped from the payload** (#5) — §16.4's delta is field by field, so an absent key
  means "unchanged" and a field that went from a value to nothing can never be sent.
* **The op id is taken from the timestamp end of the uuid** (#6) — a UUID7's leading bytes are its
  millisecond, so a CHW replaying a day of reports after an outage loses all but the last of each
  burst. The queue is keyed on `op_id`.
* **The composition root hands the service no queue** (#7) — the service *can* take one, and
  production does not pass it. Only the route test catches this.
* **The queue is written before the consent refusal** (#8) — §COM-101's geotag gate becomes
  advisory, and a report refused for want of consent reaches the server on the next flush anyway.
* **The duplicate is dropped instead of stored** (#9) — the dedup docstring's own promise, and the
  channel §5.4's cross-channel journeys are made of.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script. Every node is
collected first and asserted present, because a nonexistent node id makes pytest exit non-zero on a
*collection* error, which reads as CAUGHT.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
S = ROOT / 'src/afya/community/service.py'
G = ROOT / 'src/afya/service.py'

CANARIES = [
	# 1. The report is recorded and never queued. The bullet failing outright: the CHW's screen says
	#    the case was filed, the service holds it, and the queue — the only thing that outlives the
	#    process — has nothing in it.
	('the report is recorded and never queued', S,
	 "		if report.reported_offline and self._sync is not None:\n			await self._queue_case(report)",
	 "		if False:\n			await self._queue_case(report)",
	 'test_an_offline_report_reaches_the_queue'),

	# 2. Every report is queued rather than only the offline ones — the dangerous direction. A report
	#    that already reached the server is replayed, and §5.4's dedup cannot fire because the CHW
	#    logging offline carries no MSISDN for the key to be built on.
	('a report that arrived over the network is queued too', S,
	 "		if report.reported_offline and self._sync is not None:",
	 "		if self._sync is not None:",
	 'test_a_report_that_arrived_over_a_network_is_not_queued'),

	# 3. The dataset name is one §16.3 has no rule for. `enqueue` asserts against `STRATEGY_MATRIX`,
	#    so the raise happens at the first offline report — the case lost at the one moment the
	#    offline queue exists to keep it.
	('the report is queued under a dataset with no conflict rule', S,
	 "			dataset='case_reports',",
	 "			dataset='case_report',",
	 'test_the_dataset_is_the_one_the_spec_writes_the_rule_for'),

	# 4. The payload carries a pointer instead of the report. §COM-101's "reports stored locally" read
	#    as a note that something happened, so a handset that closed leaves the officer a case with no
	#    symptoms, no village and no temperature.
	('the payload carries a reference and not the report', S,
	 "			payload={name: json.dumps(value) for name, value in report.model_dump(mode='json').items()},",
	 "			payload={'report_id': report.report_id},",
	 'test_the_payload_carries_every_field_including_the_nulls'),

	# 5. The nulls are dropped. §16.4's delta is computed field by field, so an omitted key reads as
	#    "unchanged" and a field that went from a value to nothing can never travel.
	('the nulls are dropped from the payload', S,
	 "			payload={name: json.dumps(value) for name, value in report.model_dump(mode='json').items()},",
	 "			payload={name: json.dumps(value) for name, value in report.model_dump(mode='json').items() if value is not None},",
	 'test_the_payload_carries_every_field_including_the_nulls'),

	# 6. The op id is taken from the *head* of the uuid, which is its millisecond timestamp — so a
	#    burst of reports filed after an outage collides on `op_id` and the queue keeps only the last
	#    of each millisecond.
	('the op id is taken from the timestamp end of the uuid', S,
	 "			op_id='OP-' + uuid7str().replace('-', '').upper()[-8:],",
	 "			op_id='OP-' + uuid7str().replace('-', '').upper()[:8],",
	 'test_two_reports_filed_in_one_millisecond_are_two_ops'),

	# 7. The composition root hands the service no queue. The service takes one and production does
	#    not pass it, which is invisible to every test that constructs the service itself. The target
	#    is the *whole* wiring line: it grew four arguments since this canary was written and the old
	#    prefix silently stopped matching, so the canary had been reporting a pass without running.
	('the composition root hands the service no queue', G,
	 "		'community': CommunityService(identity_svc, sync_svc, crypto_svc, adam_svc, channels_svc, alerting_svc),",
	 "		'community': CommunityService(identity_svc, None, crypto_svc, adam_svc, channels_svc, alerting_svc),",
	 'test_the_route_queues_a_report_for_a_signed_in_chw'),

	# 8. The queue is written before the consent refusal, so §COM-101's geotag gate becomes advisory:
	#    a report refused for want of consent is queued anyway and reaches the server on the next
	#    flush. The order is the control.
	('the queue is written before the consent refusal', S,
	 "		assert report.symptoms, 'symptom checklist required'\n		if report.photo_sha256 is not None:\n			assert report.geotagged, 'a photo needs its location consent before it can be filed'",
	 "		assert report.symptoms, 'symptom checklist required'",
	 'test_a_photo_without_geotag_is_still_refused_before_anything_is_queued'),

	# 9. The duplicate is dropped rather than stored. The dedup docstring promises the opposite: the
	#    second report is a channel, and §5.4's cross-channel journeys are made of it.
	('the duplicate open case is dropped instead of stored', S,
	 "			self._cases[report.report_id] = report\n			self._case_status[report.report_id] = CaseStatus.reported\n			self._log_info('case report deduplicated onto an open case'",
	 "			self._log_info('case report deduplicated onto an open case'",
	 'test_a_duplicate_open_case_is_still_stored_and_still_queued_when_it_arrived_offline'),
]

failures = []


def _node(canary_node: str) -> str:
	return canary_node if '/' in canary_node else f'tests/ci/test_com101.py::{canary_node}'


_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only',
	'tests/ci/test_com101.py'],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_com101.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	# A same-second write of the same size reuses the previous canary's bytecode, and the canary then
	# tests code it never mutated.
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', _node(node)],
			cwd=ROOT, capture_output=True, text=True)
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
