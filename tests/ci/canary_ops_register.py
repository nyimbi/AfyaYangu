"""Canaries for §23's register gate: a count that passed while five cells had drifted.

`test_the_register_has_every_spec_row` asserted 5 + 7 + 9 + 7 + 5 and `len(RISKS) == 33`, and it was
the *whole* of §23's coverage. A predicate that is a strict subset of the thing it claims to test
fails open, and it fails toward "clean" — a count is blind to content, so R-O7's likelihood could read
`medium` against §23.2's `High` for as long as anyone cared to look and the register stayed green.

* **#1 drifts a rating cell.** R-O7's likelihood goes back to `medium`. This is the one that changes
  behaviour rather than prose: `Risk.exposure()` is likelihood × impact, so the row sorted below its
  neighbours on a fix-first list. Aimed at the cell test.
* **#2 drifts a statement cell**, restoring the paraphrase `an Ebola app` where §23.2 quotes the brand
  `"Ebola app"`. A different column, so the cell test is proven to read all four rather than the one
  the first canary touched.
* **#3 is the finding itself, and it is inverted**: the *same* mutation as #1, aimed at the count test,
  which must stay **green**. This is the canary that records why the cell test was written — if the
  count test ever starts catching a drifted cell, the two tests have collapsed into one and the file
  should say so. Inverted, so `-v` rather than `-q`: a passing run under `-q` prints no node name and
  the "aimed at the right node" check could not tell the right test ran from a collection that picked
  up nothing.
* **#4 empties the divergence map**, so R-T2's recorded Flutter omission is no longer excused and the
  cell test names it. This proves the map is load-bearing rather than decorative — without it the
  entry could be deleted and every test would still pass.
* **#5 adds a *stale* excuse** — a row recorded as diverging that carries §23 verbatim. The cell test
  passes it by name, so only the second test can see it; without that test a stale entry silently
  widens the gate's blind spot by one row.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary that
passes is a bug in the canary, so a MISSED line fails this script. `__pycache__` is purged after each
write, for the reason `canary_inf001.py` documents.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
S = ROOT / 'src/afya/operations/service.py'
_F = 'tests/ci/test_operations.py'

# R-O7 as §23.2 writes it (`High`), which is what the register carries after this unit.
_R_O7_OLD = "		likelihood=Rating.high, impact=Rating.medium, mitigation='Granular preferences; critical-only defaults',"
_R_O7_NEW = "		likelihood=Rating.medium, impact=Rating.medium, mitigation='Granular preferences; critical-only defaults',"

CANARIES = [
	# 1. The rating cell drifts back. Aimed at the cell test, which is the one that must see it.
	('the likelihood cell drifts back to medium', S, [(_R_O7_OLD, _R_O7_NEW)],
	 'test_the_register_is_the_sections_table_cell_for_cell', False),

	# 2. A different column: the statement loses the section's quoting of the brand.
	('the statement cell drifts back to the paraphrase', S,
	 [("""statement='Branded as "Ebola app" and abandoned post-outbreak',""",
	   """statement='Branded as an Ebola app and abandoned post-outbreak',""")],
	 'test_the_register_is_the_sections_table_cell_for_cell', False),

	# 3. The finding. Same mutation as #1, aimed at the count test, which must stay green — the count
	#    check cannot see a drifted cell and this is what records that rather than asserting it.
	('the count check stays blind to the same drifted cell', S, [(_R_O7_OLD, _R_O7_NEW)],
	 'test_the_register_has_every_spec_row', True),

	# 4. The divergence map emptied. The assert below it holds for an empty dict, so this is a clean
	#    patch rather than a collection error — which matters, because a collection error would also
	#    exit non-zero and the `aimed` check is what refuses to read that as a catch.
	('the recorded divergence stops excusing R-T2', S,
	 [("""MITIGATION_DIVERGENCES: dict[str, str] = {
	'R-T2':""",
	   """MITIGATION_DIVERGENCES: dict[str, str] = {}
_UNUSED: dict[str, str] = {
	'R-T2':""")],
	 'test_the_register_is_the_sections_table_cell_for_cell', False),

	# 5. A stale excuse: R-S3 carries §23.1 verbatim, so the cell test passes it by name and only the
	#    divergence test can see it.
	('a stale divergence excuses a row that no longer diverges', S,
	 [("""MITIGATION_DIVERGENCES: dict[str, str] = {
	'R-T2':""",
	   """MITIGATION_DIVERGENCES: dict[str, str] = {
	'R-S3': '§23.1 — reconciled, so this entry is stale',
	'R-T2':""")],
	 'test_the_recorded_mitigation_divergences_are_still_divergences', False),
]

# A canary whose test does not exist would "pass" for the wrong reason, so collection is asserted
# before anything is mutated.
_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only', _F],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_KNOWN = {line.strip().split('::')[-1] for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({c[3] for c in CANARIES if c[3] not in _KNOWN})
assert not _missing, f'canaries name tests that do not exist: {_missing}'


failures = []
for name, path, patches, node, inverted in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_ops_register.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	mutated = s
	for old, new in patches:
		count = mutated.count(old)
		assert count == 1, f'{name}: patch target not unique/found ({count}) for {old!r}'
		mutated = mutated.replace(old, new)
	path.write_text(mutated)
	# A same-second write of the same size reuses the previous canary's bytecode, and the canary then
	# tests code it never mutated. Purged for the file just written.
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		# `-v`, not `-q`: canary #3 is inverted and passes, and a passing run under `-q` prints no node
		# name at all — so the `aimed` check could not tell the right test ran from a collection that
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
