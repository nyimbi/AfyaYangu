"""Canaries for §22.2–§22.4's Measurement column, the feature-id cells inside it, and the row §22
prints twice.

The column says *where a target's number comes from* — "Station surveys", "Comms log", "MON-009
data" — and the register carried none of it: `app_downloads` was a figure among forty-three with no
route to it, and the count-only test over `KPIS` could not see a source because there was no field
to hold one. That is the §23 shape again: a predicate that is a strict subset of the thing it tests.

Three of §22.4's cells are a **feature id**, and the standing constraint is that a spec code does not
reach a surface a person reads. Serving the cell verbatim put `MON-009`, `MON-001` and `MON-004` on
`/metrics/kpis`; the register now serves the registry's name for the feature and keeps the id in
`MEASURED_BY_FEATURE`, which is why two of these canaries are about that resolution rather than
about the column.

* **#1 drifts a measurement cell** — `app_downloads` back to a source §22.2 does not print. Aimed at
  the cell comparison, which is the only check that reads the value.
* **#2 re-serves the raw §22.4 cell** for one KPI, restoring the defect as it first shipped: the
  feature id on the wire. Aimed at the served-surface gate, because that is where it was wrong — a
  register-level check would prove less.
* **#3 breaks the resolution's link to the section** — the recorded cell no longer matches what
  §22.4 prints, so the substitution is being applied to text nobody checked. Aimed at the cell test.
* **#4 is inverted**: the *same* mutation as #1, aimed at the count-only test over `KPIS`, which must
  stay **green**. This records why the column test exists rather than asserting it — if the count
  test ever starts catching a drifted source, the two have collapsed into one and this file should
  say so. Inverted, so `-v` not `-q`: a passing run under `-q` prints no node name and the "aimed at
  the right node" check could not tell the right test ran from a collection that picked up nothing.
* **#5 drops the second printing**, so §22.3 reads as six rows against the seven it prints and the
  coverage assertion fails. Aimed at the cell test, which is what walks the section's own rows.

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
S = ROOT / 'src/afya/metrics/service.py'
_F = 'tests/ci/test_metrics.py'

CANARIES = [
	# 1. A measurement cell drifts off §22.2. Aimed at the cell comparison.
	('a measurement cell drifts off the section', S,
	 [("	'app_downloads': 'App stores',", "	'app_downloads': 'App store reports',")],
	 'test_the_measurement_column_is_the_sections_cell_for_cell', False),

	# 2. The defect as it first shipped: §22.4's cell served verbatim, feature id and all. Aimed at
	#    the front door, since the register being "clean" is not what the constraint is about.
	('the raw feature-id cell is served again', S,
	 [("	'contacts_monitored': '21-Day Contact Monitoring Diary data',",
	   "	'contacts_monitored': 'MON-009 data',")],
	 'test_no_spec_code_reaches_the_served_target_register', False),

	# 3. The resolution's link to the section breaks: the recorded cell is no longer the one §22.4
	#    prints, so the substitution is applied to text the test never saw.
	('the recorded cell stops matching the section', S,
	 [("	'medication_adherence': ('MON-004', 'MON-004'),",
	   "	'medication_adherence': ('MON-004', 'MON-004 adherence'),")],
	 'test_the_measurement_column_is_the_sections_cell_for_cell', False),

	# 4. The finding, inverted. Same mutation as #1, aimed at the count test, which must stay green.
	('the count check stays blind to the same drifted cell', S,
	 [("	'app_downloads': 'App stores',", "	'app_downloads': 'App store reports',")],
	 'test_every_spec_section_22_subsection_is_represented', True),

	# 5. The second printing is dropped, so §22.3's seven rows meet six in the register.
	('the row §22 prints twice loses its record', S,
	 [("ALSO_PRINTED_AT: dict[str, list[str]] = {'retention_dau_mau': ['§22.3']}",
	   "ALSO_PRINTED_AT: dict[str, list[str]] = {}")],
	 'test_the_measurement_column_is_the_sections_cell_for_cell', False),
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
	backup = pathlib.Path(f'/tmp/canary_metrics_measurement.{path.name}.bak')
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
		# `-v`, not `-q`: canary #4 is inverted and passes, and a passing run under `-q` prints no node
		# name at all — so the `aimed` check could not tell the right test ran from a collection that
		# silently picked up nothing.
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
