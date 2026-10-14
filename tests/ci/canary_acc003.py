"""Canaries for tests/ci/test_acc003.py.

§ACC-003's "local-first data storage" was `missing` because the clients kept their write queue in a
preferences cache and the audit row said so. The canaries are the ways this kind of unit goes wrong
once it exists, and the first two are the ways it usually does:

* **#1** is that the contract is a document nothing runs. Every vector is present, the audit row
  says `carried`, and no client reads the file — which is the `report_stock` failure at the level of
  the contract rather than of a route.
* **#2** is the one that matters most and is the easiest to miss: a client quietly reverts to the
  cache. The store still exists, the contract still passes, and the queue is a JSON array again.
* **#3** is the device table drifting from the server's. It is the failure the shared contract
  exists for, and it is invisible until the replay, which is the moment the queue was built for.
* **#4** is a client whose schema is a copy of the contract's rather than the contract's own DDL.
* **#5** is the backoff cap becoming this deployment's number instead of the server's.
* **#6** is the audit row reverting to `missing` while the code stays — a row that lies in the
  direction that hides work that was done.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script. The `__pycache__`
purge after each write is load-bearing for the reason `canary_inf001.py` documents.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
C = ROOT / 'proto/local_store/contract.json'
KS = ROOT / 'android/app/src/main/java/ke/go/health/afyayangu/LocalStoreSchema.kt'
SS = ROOT / 'ios/AfyaYangu/LocalStoreSchema.swift'
KC = ROOT / 'android/app/src/main/java/ke/go/health/afyayangu/BackendClient.kt'
SC = ROOT / 'ios/AfyaYangu/BackendClient.swift'
A = ROOT / 'src/afya/content_audit/service.py'

CANARIES = [
	# 1. The contract becomes a document nothing runs. The vectors are all there and the audit row
	#    cites them; the client tests read a file of their own instead.
	('no client runs the shared contract', ROOT / 'ios/Tests/LocalStoreTests.swift',
	 'appendingPathComponent("proto/local_store/contract.json")',
	 'appendingPathComponent("proto/local_store/contract-copy.json")',
	 'test_both_clients_run_the_shared_contract_rather_than_a_copy'),

	# 2. The queue goes back to the preferences cache. This is the row's actual finding returning,
	#    with every other assertion still green: the store exists and is simply not used for the one
	#    thing §16.1 promises survives a restart.
	('the Android queue is a preferences array again', KC,
	 '\tfun queuedCount(): Int = store.pendingCount()',
	 '\tfun queuedCount(): Int = JSONArray(prefs.getString("queue", "[]")).length()',
	 'test_the_queue_left_the_preferences_cache_on_both_clients'),

	# 3. The device table drifts from the server's. A queue whose row the server's `SyncOp` refuses
	#    fails at the replay — which is the moment the queue exists for, and the one moment nobody is
	#    watching.
	('the device queue drops a column the server expects', C,
	 'server_ts INTEGER NOT NULL DEFAULT 0, ',
	 '',
	 'test_the_contract_table_is_the_servers_table'),

	# 4. A client's schema becomes a copy of the contract's rather than the contract's own DDL. The
	#    vectors still pass and the artefact the contract describes is no longer the one that runs.
	('the Swift schema drops a column', SS,
	 '\t\t\t"retry_at_ms INTEGER)",',
	 '\t\t\t"attempt INTEGER NOT NULL DEFAULT 0)",',
	 'test_the_clients_run_the_contracts_ddl_not_a_schema_of_their_own'),

	# 5. The backoff cap becomes this deployment's figure instead of the server's. The client still
	#    backs off and no longer matches the function it cites.
	('the client backoff cap is not the server figure', SC,
	 'let seconds = min(Int64(1) << Int64(min(max(attempt, 0), 10)), 600)',
	 'let seconds = min(Int64(1) << Int64(min(max(attempt, 0), 10)), 300)',
	 'test_the_client_backoff_matches_the_servers_cap'),

	# 6. The audit row reverts to `missing` while the store stays. A row that under-reports is the
	#    one direction of drift nothing else here can see, because every other assertion is about the
	#    code and this one is about the claim.
	('the audit row says missing while the store exists', A,
	 "'Local-first data storage (SQLite / Room / Core Data)', 'carried', 'afya.persistence.local_store:SCENARIOS'",
	 "'Local-first data storage (SQLite / Room / Core Data)', 'missing', None",
	 'test_the_audit_row_resolves'),
]


def _node(canary_node: str) -> str:
	return canary_node if '/' in canary_node else f'tests/ci/test_acc003.py::{canary_node}'


_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only',
	'tests/ci/test_acc003.py'], cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_acc003.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	for cache in (ROOT / 'src/afya').rglob('__pycache__'):
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
