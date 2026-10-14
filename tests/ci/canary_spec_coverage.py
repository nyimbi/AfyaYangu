"""Canaries for tests/ci/test_spec_coverage.py — the spec↔registry gate.

This gate had no canary file. The two directions were each watched failing once by hand (recorded in
`docs/buildout.md`: `AI-005` deleted from the registry, and the range branch reverted to a literal
scan), and a hand-run canary is not a canary — it is a memory. What it leaves behind is a gate
nobody can re-point at a known-bad input without redoing the work.

The gate now walks both directions, so it has two ways to fail open and each gets a canary:

* **spec → registry** (`test_every_spec_id_resolves`) — a feature the spec names and nothing built.
  Its blind spot is the *reader*: `_spec_ids` sees ids written literally and inside `AI-004…005`
  ranges, and dropping the range branch hides `AI-005`, which the spec spells no other way. Canary
  #2 is that revert, and it is the canary the module's own docstring says was watched failing.
* **registry → spec** (the test added with this file) — a feature the registry carries that the spec
  never defines. Its blind spot is a *tenth* one joining the nine. Canary #1 renames a registry id
  out of the spec's namespace, and canary #3 gives a registered feature a name that collides with a
  spec section the alias table does not record.

Canary #1 must fail on the *pinned list*, not on a downstream consequence. Renaming `INF-013` to an
undefined id would also break other suites, so the canary asserts the failure output names the test
it was aimed at — a canary caught for the wrong reason is a canary that did not test its target.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
T = ROOT / 'tests/ci/test_spec_coverage.py'
R = ROOT / 'src/afya/registry/service.py'

CANARIES = [
	# 1. A registered feature leaves the spec's namespace — the tenth phantom id, which is the
	#    finding this test exists to make impossible to add quietly. The pinned list stops matching
	#    and the failure names the id that joined.
	('a tenth registry id the spec does not define', R,
	 "		FeatureSpec(id='INF-013', name='Flood and Weather Alerts',",
	 "		FeatureSpec(id='INF-017', name='Flood and Weather Alerts',",
	 'test_the_registry_ids_the_spec_does_not_define_are_the_nine_known_ones'),

	# 2. The range branch goes, so `_spec_ids` is a literal scan again and `AI-005` — spelled in the
	#    spec only as `AI-004…005` — is invisible. The gate then cannot see the id it was blind to,
	#    and deleting `AI-005` from the registry would leave every test in the file green.
	('the range expansion goes back to a literal scan', T,
	 "	for prefix, first, last in ID_RANGE.findall(text):\n		assert int(first) <= int(last), f'§7.3 writes a backwards range: {prefix}-{first}…{last}'\n		ids |= {f'{prefix}-{n:03d}' for n in range(int(first), int(last) + 1)}",
	 "	for prefix, first, last in []:\n		assert int(first) <= int(last), f'§7.3 writes a backwards range: {prefix}-{first}…{last}'\n		ids |= {f'{prefix}-{n:03d}' for n in range(int(first), int(last) + 1)}",
	 'test_the_extractor_sees_an_id_written_only_as_a_range'),

	# 3. The name-collision half of the registry→spec test goes, so `INF-011` may be renamed to
	#    anything and the registry can hold two ids for one feature with nothing recording it. The
	#    alias in `test_feature_coverage.ON_DEVICE` is what this protects: MON-005 maps to INF-011's
	#    service because the two are one feature, and that mapping rests on the names agreeing.
	('the duplicate-name check goes', T,
	 "	assert reg.get('INF-011').name == 'Water Quality Alerts'",
	 "	assert reg.get('INF-011').name == 'Anything At All'",
	 'test_the_registry_ids_the_spec_does_not_define_are_the_nine_known_ones'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_spec_coverage.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	target = f'tests/ci/test_spec_coverage.py::{node}'
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', target],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
		# Caught for the *right* reason: the failure must name the node the canary aimed at, not a
		# collection error or a sibling's breakage from the same rename.
		aimed = node in proc.stdout
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
	ok = caught and aimed
	print(f'{"CAUGHT " if ok else "MISSED "} {name}')
	if not ok:
		failures.append(name)
		print(f'  returncode={proc.returncode} aimed_at_node={aimed}')
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
