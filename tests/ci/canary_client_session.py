"""Canaries for tests/ci/test_client_session.py.

* #1 drops the held token from the Kotlin reclaim;
* #2 drops the Kotlin fallback to a fresh identity;
* #3 drops the held token from the Swift reclaim;
* #4 drops the Swift fallback;
* #5 makes the *server* refuse a live service-minted subject, which the behavioural gate in
  `test_auth.py` must catch — a client honouring a route that refuses it is not a fix.

Backups are read back before the mutation and restored in the same invocation.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
KOTLIN = ROOT / 'android/app/src/main/java/ke/go/health/afyayangu/BackendClient.kt'
SWIFT = ROOT / 'ios/AfyaYangu/BackendClient.swift'
AUTH = ROOT / 'src/afya/auth/service.py'

GATE = 'tests/ci/test_client_session.py'

CANARIES = [
	('Android reclaims with no credential', KOTLIN,
	 '			JSONObject(request("auth/anonymous", body, authorize = false, bearer = held))',
	 '			JSONObject(request("auth/anonymous", body, authorize = false))',
	 'test_both_clients_present_the_held_token_when_reclaiming_a_subject'),

	('Android has no fallback identity', KOTLIN,
	 '''			if (e.code != 403 || known == null) throw e
			JSONObject(request("auth/anonymous", "{}", authorize = false))''',
	 '''			throw e''',
	 'test_a_refused_reclaim_asks_for_a_new_identity_rather_than_bricking_the_app'),

	('iOS reclaims with no credential', SWIFT,
	 '		var data = try await issueAnonymous(subject: known, bearer: held)',
	 '		var data = try await issueAnonymous(subject: known, bearer: nil)',
	 'test_both_clients_present_the_held_token_when_reclaiming_a_subject'),

	('iOS has no fallback identity', SWIFT,
	 '''			data = try await issueAnonymous(subject: nil, bearer: nil)''',
	 '''			throw ApiError.transport(-1)''',
	 'test_a_refused_reclaim_asks_for_a_new_identity_rather_than_bricking_the_app'),

	('the server honours a subject it never issued', AUTH,
	 '''		if subject_ref in self._subjects:
			return False''',
	 '''		if False:
			return False''',
	 'test_a_subject_is_claimed_once_and_a_lost_token_means_a_new_identity'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_session.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	assert s == backup.read_text(), f'{name}: the backup is not this file'
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	# The behavioural canary lives in test_auth.py, not in the client-source gate.
	target = f'tests/ci/test_auth.py::{node}' if path is AUTH else f'{GATE}::{node}'
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', target],
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
