"""Canaries for §18's Frequency register, whose column nothing compared to the section.

Seven of the eight subsections carried their cadence only in a client docstring ("App → ADaM, daily,
consented only"), where no test reads it and no operator can query it; §18.3 carried it as slugs and
the only test over it asserted the *key set*. So a feed could move from hourly to weekly against a
section reading "Hourly" and every gate stayed green — the same defect class §SEC-005's retention
cells had, which is why the reader is the same shape.

Each mutation is *disjoint* from what its predicate reads:

* **#1** moves a cell in the **register** and leaves `docs/spec.md` alone. The register is a copy of
  the section, so this is "this build's reading drifted".
* **#2** moves a cell in **`docs/spec.md`** and leaves the register alone. The opposite direction,
  and the one that catches the "edit the constant until it agrees" move: a reconciliation invented
  in the code is exactly what a spec-reading gate exists to refuse. It is also the mutation the
  in-process canary in `test_integrations.py` cannot make — that one rewrites a dict, this one
  rewrites the file the gate actually reads.
* **#3** drops a row from `CARRIER`, so a frequency is declared with no route behind it — the wire
  nobody built, which is the defect §18 was fixed from. The frequency map is untouched, so only the
  carrier test can see it.
* **#4** moves a §18.3 cadence in `FEED_CADENCE` — the machine contract the PHEOC client actually
  posts under — and leaves the register alone. Different from #1 and #2, which are the
  register↔section crossing: this is register↔wire, and the module-level assert in `frequencies.py`
  is what fires. It is also the mutation `test_every_feed_declares_its_granularity_and_cadence`
  cannot see, because that test asserts the key *sets* and a value moved underneath it.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). `__pycache__`
is purged after each write, for the reason `canary_inf001.py` documents: two canaries mutating two
files with same-length edits in the same second make CPython reuse the previous canary's bytecode,
and the gate then reports a mutation it never made. A canary that passes is a bug in the canary, so a
MISSED line fails this script.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
F = ROOT / 'src/afya/integrations/frequencies.py'
SPEC = ROOT / 'docs/spec.md'
FEEDS = ROOT / 'src/afya/integrations/feeds.py'

CANARIES = [
	# 1. The register's own cell drifts from the section. Aimed at the spec-reading test, which is
	#    the only thing that compares the two.
	('a declared frequency drifts from the section', F,
	 "	('18.1', 'Contact monitoring summaries'): 'Daily',",
	 "	('18.1', 'Contact monitoring summaries'): 'Weekly',",
	 'tests/ci/test_integrations.py::test_every_spec_18_frequency_is_the_sections_own'),

	# 2. The *section* moves and the register does not — the reverse direction, and the one an
	#    in-process canary cannot make. A gate that reads only its own constant would pass this.
	('the sections own cell is reworded', SPEC,
	 "| Contact monitoring summaries | App → ADaM | Daily symptom summaries (consented) | Daily |",
	 "| Contact monitoring summaries | App → ADaM | Daily symptom summaries (consented) | Weekly |",
	 'tests/ci/test_integrations.py::test_every_spec_18_frequency_is_the_sections_own'),

	# 3. A row loses its carrier, so the register declares a cadence for a wire no route implements.
	#    The frequency map is untouched, so the spec comparison stays green and only the carrier test
	#    fails — which is what makes the two tests separately load-bearing.
	('a declared frequency loses its route', F,
	 "	('18.6', 'Facility acceptance list'): ('GET', '/insurance/sha/facilities'),\n",
	 "",
	 'tests/ci/test_integrations.py::test_every_spec_18_row_names_a_route_that_carries_it'),

	# 4. The *wire* moves and the register does not: `FEED_CADENCE` is what the PHEOC client posts
	#    under, so a cadence changed here is the section's obligation broken at the machine, while
	#    `docs/spec.md` and the register still agree. Aimed at the spec-reading test, which imports
	#    `frequencies.py` and therefore trips its module-level assert — the node that reads the
	#    crossing. The first cut of this canary moved the register's cell instead and named
	#    `test_every_feed_declares_its_granularity_and_cadence`, which never imports the module: it
	#    passed a file whose assert would have fired, because nothing on that path imports it. A
	#    canary pointed at a node that cannot see its mutation is a canary that did not run.
	('the PHEOC wire cadence drifts from the register', FEEDS,
	 "	'geofence_events': 'hourly',",
	 "	'geofence_events': 'daily',",
	 'tests/ci/test_integrations.py::test_every_spec_18_frequency_is_the_sections_own'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_freq.{path.name}.bak')
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
