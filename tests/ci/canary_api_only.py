"""Canaries for the route-surface register, whose whole value is that it can fail.

The register's defect class is a route nobody reaches, and a register that is never seen to fail is
indistinguishable from a register that cannot. Each mutation here is *disjoint* from what its
predicate reads:

* **#1 removes an entry from `API_ONLY`** without touching any route. The served set is unchanged,
  so the "every route is reached or named" gate is the only one that can catch it — and it is the
  gate the register exists for. Aimed there.
* **#2 adds a register entry for a route the catalogue already reaches.** Disjoint from #1: this is
  the *stale* direction, which #1 cannot produce. Aimed at the drift gate.
* **#3 misspells a path in the register.** A route that is neither reached nor served — the case a
  comparison against `served` alone would pass if the two sets were only crossed one way. Aimed at
  the drift gate, and the reason that gate checks membership in `served` and not merely absence
  from `reached`.
* **#4 adds a catalogue action pointing at a path no route serves** — the reverse direction, a
  screen that 404s. Aimed at `test_every_catalogue_action_has_a_route`.
* **#5 gives a register entry an invented jurisdiction**, so the vocabulary check is exercised
  rather than restated.
* **#6 stops the iOS client naming the resumable-upload path.** This is the one jurisdiction that
  is *read* rather than declared, and the canary proves the reading is load-bearing: with the
  client silent, the register's `client_direct` entry becomes a route reached by nobody, and the
  client-direct test is what says so.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree).
`__pycache__` is purged after each write, for the reason `canary_inf001.py` documents. A canary that
passes is a bug in the canary, so a MISSED line fails this script.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
A = ROOT / 'src/afya/mobile/actions.py'
IOS = ROOT / 'ios/AfyaYangu/Evidence.swift'
TEST = 'tests/ci/test_api_only.py'

CANARIES = [
	# 1. An entry leaves the register and no route moves: the silent case the gate exists for.
	('a served route loses its jurisdiction', A,
	 "\t('GET', '/features/taxonomy'): 'public_read',\n", '',
	 'test_every_served_route_is_reachable_or_named_api_only'),

	# 2. The stale direction: a route the catalogue reaches is parked in the register anyway. The
	#    anchor is a route *not* already in the register — a second key for a route that is, would
	#    collapse silently in the dict literal and the canary would mutate nothing.
	('a reached route is parked in the register', A,
	 "\t('GET', '/health'): 'public_read',",
	 "\t('GET', '/health'): 'public_read',\n\t('GET', '/access/battery'): 'public_read',",
	 'test_the_register_does_not_drift'),

	# 3. A misspelled path: neither reached nor served, which a one-way comparison would let pass.
	('a register path is misspelled', A,
	 "\t('GET', '/features/taxonomy'): 'public_read',",
	 "\t('GET', '/features/taxonomies'): 'public_read',",
	 'test_the_register_does_not_drift'),

	# 4. The reverse direction: an action whose path is not served is a screen that 404s.
	('a catalogue action points at a route nobody serves', A,
	 "\t_a('sha_cover_check', 'Am I covered?', 'Insurance', 'POST', '/insurance/sha-check',",
	 "\t_a('sha_cover_check', 'Am I covered?', 'Insurance', 'POST', '/insurance/sha-check-zzz',",
	 'test_every_catalogue_action_has_a_route'),

	# 5. An invented jurisdiction, so the vocabulary check is exercised rather than restated.
	('a register entry carries an invented jurisdiction', A,
	 "\t('GET', '/features/taxonomy'): 'public_read',",
	 "\t('GET', '/features/taxonomy'): 'nonsense_party',",
	 'test_the_register_does_not_drift'),

	# 6. The client stops naming the resumable-upload path, so a `client_direct` entry names a route
	#    no handset calls. Aimed at the client-direct test, which is the only one that reads the
	#    clients; a server-side test cannot see this. The anchor is the *opener* call, which is the
	#    one literal that appears once — the two chunk calls carry the same substring, so a
	#    `str.replace` on the bare path would have rewritten all three and the canary would not have
	#    been the mutation it claims.
	('the iOS client stops calling the resumable upload', IOS,
	 '\t\tvar opened = try await json(client, "evidence/upload", [',
	 '\t\tvar opened = try await json(client, "evidence/zzz-upload", [',
	 'test_the_client_direct_entries_are_the_paths_the_clients_actually_name'),
]

_FILES = {name: TEST for name, *_ in CANARIES}  # noqa: F841 — kept so a canary may target another file later

# A canary whose test does not exist would "pass" for the wrong reason, so collection is asserted
# for the file, before anything is mutated.
_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only', TEST],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_api_only.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	# A same-second write of the same size reuses the previous canary's bytecode, and the canary then
	# tests code it never mutated. Purged for the file just written.
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		# `-v`, not `-q`: a passing run under `-q` prints no node name, so `aimed` could not tell
		# the right test ran from a collection that silently picked up nothing.
		proc = subprocess.run(['uv', 'run', 'pytest', '-v', '-p', 'no:randomly', f'{TEST}::{node}'],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
		aimed = node in proc.stdout
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
		for cache in path.parent.rglob('__pycache__'):
			shutil.rmtree(cache, ignore_errors=True)
	ok = caught and aimed
	print(f'{"CAUGHT " if ok else "MISSED "} {name}')
	if not ok:
		failures.append(name)
		print(f'  returncode={proc.returncode} aimed_at_node={aimed}')
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
