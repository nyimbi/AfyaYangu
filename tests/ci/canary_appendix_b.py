"""Canaries for the Appendix B crossing, whose reader opened one of the appendix's seven tables.

`test_the_sensor_ids_the_summary_flattens_are_recorded_not_reported` read
`_spec_table('### Records')` and then walked the five recorded sensor ids, looking each up. That
shape can only ever confirm a divergence somebody had already found: the ids in the other six tables
(`### Channel Features`, `### Information`, `### Triage`, `### Facility`, `### Medicine`,
`### Emergency`) were never read, so a divergence there had nothing to report it. `LOC-001` was
reachable only because its row happens to live in `### Records`.

The replacement walks the appendix and reports every disagreement, and the register it excludes is
split in two — `DIVERGENCES` for tiers and `NAME_DIVERGENCES` for names — because the first cut put
two name divergences into `TierDivergence` rows carrying the tier both sides already agreed on: a
name divergence wearing a tier's clothes, which is a row whose every tier field says "no divergence".

Each mutation is *disjoint* from what its predicate reads:

* **#1** moves a tier in the **registry** for an id in `### Emergency` — one of the six tables the old
  reader never opened, and an id no divergence row names. Aimed at the comparison test, which reads
  `docs/spec.md` and must report it.
* **#2** renames a feature in the **registry** so the appendix cell and the registry disagree by a
  word, on an id no name row names. Aimed at the same test's name half.
* **#3** narrows the reader back to `### Records` alone — the shipped defect — and confirms the
  coverage test fails, because a reader scoped narrower than its subject reports clean forever.
* **#4** records a name divergence whose two cells are identical, which is a register row claiming a
  difference that is not there. Aimed at the module-level assert in `taxonomy.py`, which fires at
  import — the node named below imports the module, so the assert is on its path.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). `__pycache__`
is purged after each write, for the reason `canary_inf001.py` documents. A canary that passes is a bug
in the canary, so a MISSED line fails this script.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
T = ROOT / 'src/afya/registry/taxonomy.py'
SVC = ROOT / 'src/afya/registry/service.py'
TEST = ROOT / 'tests/ci/test_registry.py'

COMPARE = 'tests/ci/test_registry.py::test_every_appendix_b_row_agrees_with_the_registry_or_is_a_recorded_divergence'
COVERAGE = 'tests/ci/test_registry.py::test_the_appendix_b_reader_sees_all_seven_domain_tables'

CANARIES = [
	# 1. A tier moves in the registry on an id from `### Emergency`, a table the old reader never
	#    opened and no divergence row names. The appendix still says `1`.
	('a tier moves on an unrecorded id in an unread table', SVC,
	 "		FeatureSpec(id='EMG-001', name='Emergency SOS', tier=Tier.tier1, channels=['native']),",
	 "		FeatureSpec(id='EMG-001', name='Emergency SOS', tier=Tier.tier4, channels=['native']),",
	 COMPARE),

	# 2. A name moves in the registry, so the appendix cell and the registry differ by a word on an id
	#    no name row records. Disjoint from #1, which moves a tier.
	('a name moves on an unrecorded id', SVC,
	 "		FeatureSpec(id='MED-003', name='Dosage Calculator', tier=Tier.tier1, channels=['native', 'chw']),",
	 "		FeatureSpec(id='MED-003', name='Dose Calculator', tier=Tier.tier1, channels=['native', 'chw']),",
	 COMPARE),

	# 3. The reader narrows back to `### Records` alone — the shipped defect exactly. The comparison
	#    test still passes (its two recorded rows are in that table), so only the coverage test sees
	#    it; that asymmetry is the finding, and it is why the coverage test has to exist separately.
	('the reader opens one table again', TEST,
	 "	appendix = text.split('## Appendix B', 1)[1]",
	 "	appendix = '### Records' + text.split('### Records', 1)[1]",
	 COVERAGE),

	# 4. A name row is recorded whose two cells are identical, so the register claims a divergence that
	#    is not there. Aimed at the import-time assert in `taxonomy.py`; the node named imports it.
	('a name divergence records a difference that is not there', T,
	 "		section_name='Acoustic Cough and Respiratory Monitoring',\n"
	 "		appendix_b_name='Acoustic Cough Detection'),",
	 "		section_name='Acoustic Cough and Respiratory Monitoring',\n"
	 "		appendix_b_name='Acoustic Cough and Respiratory Monitoring'),",
	 COMPARE),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_appb.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', node],
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
