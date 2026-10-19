"""Canaries for tests/ci/test_client_queue.py — each gate pointed at a planted defect.

Every mutation is disjoint from what its predicate reads:

* #1 removes the Kotlin 429 branch (the blanket 4xx drop is left in place);
* #2 keeps the branch and makes it *drop* instead of deferring;
* #3 reverts iOS to `hashValue` while leaving the Android key alone;
* #4 makes Android's first attempt keyless again;
* #5 stops the server sending `Retry-After`, which the clients now honour.

Backups are read back before the mutation and the restore is verified, because the mutation and the
real fix live in one uncommitted tree and `git checkout --` would take the real work with it.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
KOTLIN = ROOT / 'android/app/src/main/java/ke/go/health/afyayangu/BackendClient.kt'
SWIFT = ROOT / 'ios/AfyaYangu/BackendClient.swift'
SVC = ROOT / 'src/afya/service.py'

GATE = 'tests/ci/test_client_queue.py'

CANARIES = [
	('Android drops a 429 again', KOTLIN,
	 '''				if (err.code == 429) {
					val attempt = op.attempt + 1
					val wait = err.retryAfterSeconds?.times(1000) ?: backoffDelayMs(attempt)
					store.defer(op.opId, attempt, now + wait)
					return sent
				}
''',
	 '',
	 'test_a_rate_limited_replay_waits_rather_than_deleting_the_write'),

	('Android defers the 429 but drops the op', KOTLIN,
	 '''					store.defer(op.opId, attempt, now + wait)
					return sent''',
	 '''					store.drop(op.opId)
					return sent''',
	 'test_a_rate_limited_replay_waits_rather_than_deleting_the_write'),

	('iOS goes back to a per-process hash key', SWIFT,
	 '''		let digest = SHA256.hash(data: Data(material.utf8))
		return "OP-" + digest.prefix(12).map { String(format: "%02X", $0) }.joined()''',
	 '''		return "OP-" + String(UInt(bitPattern: material.hashValue), radix: 16).uppercased()''',
	 'test_the_idempotency_key_is_a_digest_of_the_content_on_both_clients'),

	('Android first attempt carries no key', KOTLIN,
	 '			val key = opKey(method, path, pathValues, params)\n			perform(method, path, pathValues, params, key)',
	 '			perform(method, path, pathValues, params)',
	 'test_the_first_attempt_carries_the_key_the_replay_will'),

	('the server stops sending Retry-After', SVC,
	 "				headers={'Retry-After': str(decision.retry_after_seconds)},",
	 "				headers={},",
	 'test_the_server_answers_a_rate_limited_write_with_retry_after'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_queue.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	assert s == backup.read_text(), f'{name}: the backup is not this file'
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', f'{GATE}::{node}'],
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
