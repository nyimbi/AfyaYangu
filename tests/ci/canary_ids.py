"""Canaries for tests/ci/test_ids.py's source scan.

`test_no_model_truncates_a_uuid7_into_a_reference` passes when its offender list is empty, and an
empty list is also what a scan that walks nothing returns. So the scan is canaried against a planted
instance of the exact class it was written for, and against the *documentation* of that class — the
second is the one worth reading, because `afya/ids.py` and the two modules that already carry the fix
describe this defect in prose, and a scan that reads its own explanation as an instance of the defect
fails forever on a clean tree.

* **#1 plants the defect** in a model that has been correct since the fix — the shape that was live in
  twenty-five fields across eleven modules while the hand-enumerated test above passed. If the scan
  cannot see a freshly planted `[:8]`, it never saw any of them.
* **#2 plants it in the form the scan must *not* match** — the same expression inside a comment, which
  is what the prose in `afya/ids.py` is. This canary is **inverted**: the test must still *pass*, so
  the script reads a green run here as the catch. The scan parses with `ast` for this reason, and this
  canary is what proves the parse is doing work rather than the scan happening to match nothing. The
  inversion is also why the harness runs `-v` rather than `-q`: a passing run under `-q` prints no
  node name, so the "aimed at the right node" check below could not tell the right test ran from a
  collection that silently picked up nothing.
* **#3 replaces the counter with the truncation in a live model** the burst test enumerates — the
  product-level defect, caught there rather than by the scan. It is here because the scan's fix and
  the burst test's fix are the same `ref8()`, and a change that reverted one would leave the other
  green.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). `__pycache__`
is purged after each write, for the reason `canary_inf001.py` documents: a same-second write of the
same size reuses the previous canary's bytecode and the canary then tests code it never mutated.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
C = ROOT / 'src/afya/channels/views.py'
M = ROOT / 'src/afya/monitoring/views.py'
E = ROOT / 'src/afya/emergency/views.py'

# `inverted=True` means the *test passing* is the catch: the mutation plants text the predicate must
# ignore, so a red run would mean the scan is reading its own documentation as a defect. Each canary
# carries a list of patches because the defect needs the name back as well as the expression: the
# migrated modules import `ref8` only, so a mutation naming `uuid7str` without restoring the import
# raises `NameError` — caught, but for the wrong reason, which is the failure this harness exists to
# refuse.
_IMPORT_OLD = 'from afya.ids import ref8'
_IMPORT_NEW = 'from afya.ids import ref8, uuid7str'

CANARIES = [
	# 1. The defect planted in a model that is correct today. `CB-` + a truncated UUID7 is exactly what
	#    `request_id` carried before this unit, and it is what the scan must name.
	('a model truncates a uuid7 into a reference again', C,
	 [(_IMPORT_OLD, _IMPORT_NEW),
	  ("""	request_id: str = Field(default_factory=lambda: 'CB-' + ref8())""",
	   """	request_id: str = Field(default_factory=lambda: 'CB-' + uuid7str().replace('-', '').upper()[:8])""")],
	 'test_no_model_truncates_a_uuid7_into_a_reference', False),

	# 2. The same text inside a *comment*, which is how the fix is documented in `afya/ids.py` and in
	#    the two modules that carry it. An `ast` scan ignores it; a text scan fails on the tree's own
	#    explanation of the bug it fixed. Inverted: the test must stay green.
	('the scan reads its own documentation as a defect', M,
	 [("""	campaign_id: str = Field(default_factory=lambda: 'CMP-' + ref8())""",
	   """	campaign_id: str = Field(default_factory=lambda: 'CMP-' + ref8())  # was uuid7str()[:8]""")],
	 'test_no_model_truncates_a_uuid7_into_a_reference', True),

	# 3. The counter replaced by the truncation on `SOSEvent.sos_id`, a model the burst test enumerates
	#    by hand — the product defect itself, on the field §18.4's sibling wire mints per event.
	('a live model reads the timestamp as a reference again', E,
	 [(_IMPORT_OLD, _IMPORT_NEW),
	  ("""	sos_id: str = Field(default_factory=lambda: 'SOS-' + ref8())""",
	   """	sos_id: str = Field(default_factory=lambda: 'SOS-' + uuid7str().replace('-', '').upper()[:8])""")],
	 'test_the_prefixed_references_are_distinct_within_a_burst', False),
]

# A canary whose test does not exist would "pass" for the wrong reason, so collection is asserted
# before anything is mutated.
_F = 'tests/ci/test_ids.py'
_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only', _F],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_KNOWN = {line.strip().split('::')[-1] for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({c[3] for c in CANARIES if c[3] not in _KNOWN})
assert not _missing, f'canaries name tests that do not exist: {_missing}'


failures = []
for name, path, patches, node, inverted in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_ids.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	mutated = s
	for old, new in patches:
		count = mutated.count(old)
		assert count == 1, f'{name}: patch target not unique/found ({count}) for {old!r}'
		mutated = mutated.replace(old, new)
	path.write_text(mutated)
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		# `-v`, not `-q`: an inverted canary passes, and a passing run under `-q` prints no node name
		# at all — so the `aimed` check below could not tell the right test ran from a collection that
		# silently picked up nothing. `-v` names the node in both directions.
		proc = subprocess.run(['uv', 'run', 'pytest', '-v', '-p', 'no:randomly', f'{_F}::{node}'],
			cwd=ROOT, capture_output=True, text=True)
		passed = proc.returncode == 0
		# Caught for the *right* reason: the run must name the node the canary aimed at, so a
		# collection error from a malformed patch cannot read as a gate that fired.
		aimed = node in proc.stdout
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
		for cache in path.parent.rglob('__pycache__'):
			shutil.rmtree(cache, ignore_errors=True)
	ok = (passed if inverted else not passed) and aimed
	print(f'{"CAUGHT " if ok else "MISSED "} {name}')
	if not ok:
		failures.append(name)
		print(f'  returncode={proc.returncode} aimed_at_node={aimed} inverted={inverted}')
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
