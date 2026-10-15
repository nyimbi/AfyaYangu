"""Canaries for §LOC-004's check-in sync.

Each mutation is *disjoint* from what its predicate looks for — a canary that is a superstring of
the asserted text is a canary that did not run. Every one of these changes the implementation in a
way the observation must notice, and each is paired with the one node that should go red.

Run: `uv run python tests/ci/canary_loc004_sync.py`. Any MISSED exits non-zero.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVICE = REPO / 'src/afya/location/service.py'
VIEWS = REPO / 'src/afya/location/views.py'
ROUTES = REPO / 'src/afya/service.py'
AUDIT = REPO / 'src/afya/content_audit/service.py'
RECENCY = REPO / 'src/afya/info/recency.py'

# (name, path, old, new, node)
CANARIES: list[tuple[str, Path, str, str, str]] = [
	(
		'the sync outcome is read off the request again, which is the defect this unit closes',
		SERVICE,
		'		checkin.synced = synced',
		'		checkin.synced = checkin.share_with_authority',
		'tests/ci/test_loc004_sync.py::test_attendance_reports_the_send_rather_than_the_request',
	),
	(
		'the receipt reports the send off the request rather than off the queue',
		SERVICE,
		'			guidance=self.GUIDANCE[point.kind], logged_locally=True, synced=synced,',
		'			guidance=self.GUIDANCE[point.kind], logged_locally=True, synced=checkin.share_with_authority,',
		'tests/ci/test_loc004_sync.py::test_asking_to_share_without_the_permission_is_refused_in_those_words',
	),
	(
		'the sharing gate stops asking for the permission, so a refused Ministry still gets the check-in',
		SERVICE,
		"		if self._share_consent is None or not self._share_consent(\n"
		"				checkin.subject_ref, SHARE_AUTHORITY_CATEGORY):\n"
		"			self._log_info('check-in kept on the phone: no sharing permission',\n"
		"				point=point.point_id, subject=checkin.subject_ref)\n"
		"			return False\n",
		'',
		'tests/ci/test_loc004_sync.py::test_the_permission_is_checked_on_the_send_path_and_not_only_in_the_prose',
	),
	(
		'a missing consent ledger fails open instead of closed',
		SERVICE,
		'		if self._share_consent is None or not self._share_consent(\n				checkin.subject_ref, SHARE_AUTHORITY_CATEGORY):',
		'		if self._share_consent is not None and not self._share_consent(\n				checkin.subject_ref, SHARE_AUTHORITY_CATEGORY):',
		'tests/ci/test_loc004_sync.py::test_a_deployment_with_no_consent_ledger_refuses_to_send',
	),
	(
		'a caller can assert its own sync outcome, so `synced: true` in the body is believed',
		SERVICE,
		'		checkin.synced = synced\n		place = point.label',
		'		checkin.synced = checkin.synced or synced\n		place = point.label',
		'tests/ci/test_loc004_sync.py::test_a_caller_cannot_assert_its_own_sync_outcome',
	),
	(
		'the payload names the person, under a consent that says "with no names"',
		SERVICE,
		"				'checkin_id': checkin.checkin_id, 'point_id': point.point_id,",
		"				'checkin_id': checkin.checkin_id, 'subject_ref': checkin.subject_ref,\n"
		"				'point_id': point.point_id,",
		'tests/ci/test_loc004_sync.py::test_what_is_queued_names_the_place_and_not_the_person',
	),
	(
		'the dataset is one §16.3 has no rule for, so the check-in raises at the moment it must be kept',
		SERVICE,
		"CHECKIN_SYNC_DATASET = 'facility'",
		"CHECKIN_SYNC_DATASET = 'check_ins'",
		'tests/ci/test_loc004_sync.py::test_the_dataset_is_the_one_the_conflict_matrix_carries_a_rule_for',
	),
	(
		'the op id takes its head, so a burst of check-ins in one millisecond collapses to one op',
		SERVICE,
		"			op_id='OP-' + uuid7str().replace('-', '').upper()[-8:],",
		"			op_id='OP-' + uuid7str().replace('-', '').upper()[:8],",
		'tests/ci/test_loc004_sync.py::test_two_check_ins_in_one_millisecond_do_not_collide_in_the_queue',
	),
	(
		'the not-asked and no-permission states collapse into one sentence, which is the shipped defect',
		SERVICE,
		"		elif not checkin.share_with_authority:\n			key, sent_with = 'sync_local_only', None",
		"		elif not checkin.share_with_authority:\n			key, sent_with = 'sync_no_consent', None",
		'tests/ci/test_loc004_sync.py::test_a_check_in_nobody_asked_to_share_stays_local_and_says_so',
	),
	(
		'the local write is made conditional on the send, so a check-in with no consent is lost',
		SERVICE,
		'		self._checkins.append(checkin)\n		synced = await self._sync_checkin(checkin, point)',
		'		synced = await self._sync_checkin(checkin, point)\n		if synced or not checkin.share_with_authority:\n			self._checkins.append(checkin)',
		'tests/ci/test_loc004_sync.py::test_a_queue_that_raises_costs_the_send_and_not_the_record',
	),
	(
		'attendance reads the request flag back off the stored record again',
		SERVICE,
		'				visit_no=seen[point.point_id], method=c.method, synced=c.synced,',
		'				visit_no=seen[point.point_id], method=c.method, synced=c.share_with_authority,',
		'tests/ci/test_loc004_sync.py::test_attendance_reports_the_send_rather_than_the_request',
	),
	(
		'the receipt is built in English regardless of the language the person asked for',
		SERVICE,
		'			message=checkin_text(checkin.lang, key, place=place),',
		"			message=checkin_text('en', key, place=place),",
		'tests/ci/test_loc004_sync.py::test_the_receipt_is_served_in_the_language_the_person_asked_for',
	),
	(
		'the local write is announced without saying it is local, so a person is told nothing is unsent',
		SERVICE,
		"			key, sent_with = 'sync_local_only', None",
		"			key, sent_with = 'sync_sent', CHECKIN_SYNC_DATASET",
		'tests/ci/test_loc004_sync.py::test_a_check_in_nobody_asked_to_share_stays_local_and_says_so',
	),
	(
		'the audit row goes back to naming the method that only does the local half',
		AUDIT,
		"'afya.location.service:LocationService._sync_checkin'",
		"'afya.location.service:LocationService.check_in'",
		'tests/ci/test_loc004_sync.py::test_the_audit_row_names_the_sync_half',
	),
	(
		'the route stops serving the outcome, so the flag is all a client can read',
		ROUTES,
		"			return (await location.check_in(checkin)).model_dump(mode='json')",
		"			return (await location.check_in(checkin)).model_dump(mode='json', exclude={'synced'})",
		'tests/ci/test_loc004_sync.py::test_the_route_serves_the_sync_outcome_and_not_the_flag',
	),
	(
		'the `synced` field is dropped from the model, so the outcome has nowhere to be reported',
		VIEWS,
		'	logged_locally: bool\n	synced: bool',
		'	logged_locally: bool',
		'tests/ci/test_loc004_sync.py::test_a_check_in_that_was_sent_says_so_and_names_where_it_went',
	),
	(
		'the op carries the day its check-in falls on rather than the instant it happened',
		SERVICE,
		'			client_ts=instant_ms(checkin.at_iso),',
		'			client_ts=midnight_ms(checkin.at_iso),',
		'tests/ci/test_loc004_sync.py::test_the_op_carries_the_instant_and_not_the_day_it_falls_on',
	),
	(
		'the instant helper truncates like the date helper, so two stamps hours apart become one',
		RECENCY,
		'	return int(parsed.timestamp() * 1000)',
		'	return int(parsed.replace(hour=0, minute=0, second=0).timestamp() * 1000)',
		'tests/ci/test_content_recency.py::test_a_date_helper_and_an_instant_helper_are_two_different_answers',
	),
]


def main() -> int:
	missed: list[str] = []
	for name, path, old, new, node in CANARIES:
		source = path.read_text()
		count = source.count(old)
		if count != 1:
			print(f'MISSED (patch target occurs {count}x, not once): {name}')
			missed.append(name)
			continue
		backup = Path('/tmp') / f'{path.name}.canary.bak'
		shutil.copy2(path, backup)
		try:
			path.write_text(source.replace(old, new))
			# A same-second, same-size write can serve the *previous* canary's bytecode, so the
			# revert is only evidence once the cache is gone.
			subprocess.run(
				['find', str(REPO / 'src'), '-name', '__pycache__', '-type', 'd',
				 '-exec', 'rm', '-rf', '{}', '+'], check=False)
			run = subprocess.run(
				['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', node],
				cwd=REPO, capture_output=True, text=True)
			fired = run.returncode != 0
			print(('fired  ' if fired else 'MISSED ') + name)
			if not fired:
				missed.append(name)
		finally:
			shutil.copy2(backup, path)
			backup.unlink()
			if path.read_text() != source:
				print(f'REVERT FAILED: {path}')
				return 2
	if missed:
		print(f'\n{len(missed)} canary/canaries did not fire: {missed}')
		return 1
	print(f'\nall {len(CANARIES)} canaries fired')
	return 0


if __name__ == '__main__':
	sys.exit(main())
