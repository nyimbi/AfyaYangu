"""Canaries for §17.4's "Access to personal data requires a documented purpose".

The unit added a purpose argument to `require_scope`, which is the same call `rbac.route_scopes()`
reads out of `service.py` with a regex. That coupling is the whole risk: a checker that stops
matching its subject does not fail, it reports the opposite of the truth, and `route_scopes()` feeds
`unreachable_scopes()` and the auditor's own report — so adding a purpose to 38 routes could have
announced `assigned` as a §17.4 row with no implementation.

The three worth reading as a set:

* **#1** is that hazard, reproduced exactly. The paren-adjacent form is what the regex was, and
  `assigned` genuinely becomes unfindable — the mutation makes the subject *absent*, not merely
  differently written, which is what a canary has to do to be a canary.
* **#2** is the fail-open shape the first version of `route_purposes` had: a mapping keyed by scope
  collapses 38 `assigned` sites to one, so three documented routes would make the gate pass while
  thirty-five declared nothing.
* **#4** removes the `access_audit` migration. The table is `CREATE TABLE IF NOT EXISTS`, so a
  deployed handset keeps four columns and the first insert naming `purpose` fails — silently, on the
  audit path, where the consequence is that §17.4's record stops being written.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary that
passes is a bug in the canary, so a MISSED line is a failure of this script. The `__pycache__` purge
after each write is load-bearing for the reason `canary_inf001.py` documents: two canaries mutating
two files with same-length edits in the same second make CPython reuse the previous canary's
bytecode, and the gate then reports a mutation it never made.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
R = ROOT / 'src/afya/privacy/rbac.py'
G = ROOT / 'src/afya/service.py'
S = ROOT / 'src/afya/privacy/service.py'
P = ROOT / 'src/afya/persistence/service.py'

CANARIES = [
	# 1. The hazard. The regex reverts to requiring the closing paren immediately, which is what it
	#    was before this unit — and every purpose-bearing `assigned` route stops matching. The
	#    mutation makes the scope genuinely unfindable rather than reworded.
	('the scope regex stops seeing a purpose-bearing call', R,
	 r"""_SCOPE_CALL = re.compile(r"require_scope\('([a-z_]+)'(?:\s*,[^)]*)?\)")""",
	 r"""_SCOPE_CALL = re.compile(r"require_scope\('([a-z_]+)'\)")""",
	 'test_the_regex_still_sees_every_scope_now_that_purposes_are_declared'),

	# 2. The fail-open gate: a mapping keyed by scope, so one documented `assigned` route satisfies
	#    the check for all 38. This is the shape `route_purposes` returned before it was a list.
	('one documented route satisfies the whole scope', R,
	 """	return sorted(
		f'{scope}:{purpose}' if purpose else scope
		for scope, purpose in route_purposes(source)
		if scope in PURPOSE_FOR_SCOPE and purpose is None
	)""",
	 """	seen = {}
	for scope, purpose in route_purposes(source):
		seen.setdefault(scope, purpose)
	return sorted(s for s, p in seen.items() if s in PURPOSE_FOR_SCOPE and p is None)""",
	 'test_every_route_reaching_another_person_declares_a_purpose'),

	# 3. A declared purpose is never checked against the vocabulary, so a typo is written into the
	#    ledger as a value nothing recognises and read back by an auditor as a purpose.
	('a misspelled purpose is accepted', R,
	 """	known = {p.value for p in AccessPurpose}
	return sorted({p for _, p in route_purposes(source) if p is not None and p not in known})""",
	 """	known = {p.value for p in AccessPurpose}
	return sorted({p for _, p in route_purposes(source) if p is not None and False})""",
	 'test_every_route_reaching_another_person_declares_a_purpose'),

	# 4. The `access_audit` migration is removed. A deployed handset keeps its four-column table and
	#    the first insert naming `purpose` fails — on the audit path, where the failure is silent.
	('an old audit table never gains the column', P,
	 """		audit_cols = {r[1] for r in await (await c.execute('PRAGMA table_info(access_audit)')).fetchall()}
		if audit_cols and 'purpose' not in audit_cols:
			await c.execute('ALTER TABLE access_audit ADD COLUMN purpose TEXT')
			self._log_info('access_audit migrated', added='purpose')""",
	 """		pass""",
	 'test_an_audit_table_from_an_older_build_gains_the_purpose_column'),

	# 5. The guard stops forwarding the purpose to the ledger. The route still declares it and the
	#    guard still reads it, so nothing else fails — the ledger simply records authorisation
	#    without accountability, which is the gap the unit exists to close.
	('the guard declares a purpose and the ledger never sees it', S,
	 """			await self._store.append_audit(req.role.value, req.dataset, allowed, now_ms(),
			                               req.purpose.value if req.purpose else None)""",
	 """			await self._store.append_audit(req.role.value, req.dataset, allowed, now_ms())""",
	 'test_a_declared_purpose_reaches_the_ledger'),

	# 6. The access-log route stops serving the purpose, so the auditor can see *whether* and not
	#    *why* — the one question the ledger was extended to answer.
	('the auditor cannot read the purpose back', G,
	 """			'entries': [{'role': r, 'dataset': d, 'allowed': a, 'at_ms': t, 'purpose': p}
			            for r, d, a, t, p in rows],""",
	 """			'entries': [{'role': r, 'dataset': d, 'allowed': a, 'at_ms': t, 'purpose': None}
			            for r, d, a, t, p in rows],""",
	 'test_access_log_endpoint_is_auditor_only_and_records_real_access'),
]

# Every canary node names a test in one of these two files; a canary whose test does not exist would
# "pass" for the wrong reason, so collection is asserted before anything is mutated.
_FILES = ['tests/ci/test_rbac.py', 'tests/ci/test_privacy.py']


def _node(canary_node: str) -> str:
	"""Resolve a bare test name to `file::name` by asking pytest, so a renamed test is caught."""
	for f, names in _KNOWN.items():
		if canary_node in names:
			return f'{f}::{canary_node}'
	raise AssertionError(f'no test file declares {canary_node}')


_KNOWN: dict[str, set[str]] = {}
for _f in _FILES:
	_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only', _f],
		cwd=ROOT, capture_output=True, text=True)
	assert _collected.returncode == 0, _collected.stdout[-2000:]
	_KNOWN[_f] = {line.strip().split('::')[-1] for line in _collected.stdout.splitlines() if '::' in line}

_missing = sorted({c[-1] for c in CANARIES if not any(c[-1] in v for v in _KNOWN.values())})
assert not _missing, f'canaries name tests that do not exist: {_missing}'

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_rbac_purpose.{path.name}.bak')
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
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', _node(node)],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
		for cache in path.parent.rglob('__pycache__'):
			shutil.rmtree(cache, ignore_errors=True)
	print(f'{"CAUGHT " if caught else "MISSED "} {name}')
	if not caught:
		failures.append(name)
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
