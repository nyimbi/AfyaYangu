"""Canaries for tests/ci/test_spec_register.py — each gate pointed at a planted defect.

Every mutation is **disjoint** from what its predicate reads:

* #1 makes a `carried` carrier unreachable *and* leaves its note silent, which is the defect the
  gate was built for (the shipped state of `record_donation` before this unit) — the predicate reads
  the note and `src/`, and the mutation changes the note only, so a gate that read the note alone
  would pass it;
* #2 makes a note claim a carrier is unreachable while the route still calls it, which is the other
  direction and the one that catches a stale note after a wire lands;
* #3 changes a docstring figure the gate parses and compares to the tables;
* #4 changes the `§CHAN-001` note's measured figure, which the gate crosses against the walker's own
  output rather than against a second constant;
* #5 removes a figure from the docstring entirely, so the parse fails instead of skipping — a gate
  that silently ignores a sentence it cannot match is the checker-that-enumerates-one-spelling
  defect wearing a test's clothes, and this canary is what proves the parse is load-bearing.

Each patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). The
`__pycache__` purge after each write is load-bearing for the reason `canary_inf001.py` documents: a
same-second write of the same size reuses the previous canary's bytecode and the canary then tests
code it never mutated.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
REG = ROOT / 'src/afya/content_audit/service.py'

GATE = 'tests/ci/test_spec_register.py'

CANARIES = [
	# 1. A carried row loses its caller and says nothing about it. `record_donation` is the shipped
	#    shape of this defect: the method exists, resolves, and no route and no caller reaches it.
	#    The note is rewritten to drop the marker, so the mutation is in the same field the gate reads
	#    without also changing the code the gate scans.
	('a carried carrier has no caller and the note stays silent', REG,
	 'Reachability stated rather than implied: `record_donation` has **no route and no caller in `src/`** — a donor date can only be set on `POST /blood/donors`, so the eligibility half is served (`/blood/match` and `/blood/alerts` both read `_eligible`) while the history half is reachable only from Python.',
	 '`record_donation` stamps the date, so the eligibility half is served by `/blood/match` and `/blood/alerts`.',
	 'test_every_reachable_carrier_is_used_somewhere_in_src'),

	# 2. The other direction: a note keeps claiming no caller after the code started reaching it. The
	#    mutation adds the marker to a reachable carrier's own sentence, so a gate that only checked
	#    "unreachable rows say so" would pass it.
	('a note claims no caller for a carrier the route uses', REG,
	 'the report intake is `report_stock`, reached by `POST /medicine/stock`',
	 'the report intake is `report_stock`, which has no route and no caller',
	 'test_every_reachable_carrier_is_used_somewhere_in_src'),

	# 3. A docstring figure drifts from the table it describes. 689 -> 690 is one row, which is the
	#    size of drift a revision actually produces, and it is invisible to every other gate in the
	#    repo because the docstring is not data.
	('the docstring row count drifts from the table', REG,
	 '689 rows over 122 (section, label) pairs',
	 '690 rows over 122 (section, label) pairs',
	 'test_the_register_docstring_counts_match_the_tables'),

	# 4. The one note that quotes another module's measurement. 191 -> 181 is the exact stale figure
	#    this unit corrected, and the gate crosses it against `plain_language_report()` rather than
	#    against a constant, so a mutation here can only be caught by running the walker.
	('the CHAN-001 note quotes a stale string count', REG,
	 'measures all 191 outbound strings across 30 tables',
	 'measures all 181 outbound strings across 30 tables',
	 'test_the_chan001_note_measures_what_the_walker_measures'),

	# 5. The figure leaves the sentence. A gate whose regex silently fails to match would pass this;
	#    the one here asserts the match and fails, which is the difference between a gate and a
	#    comment about one.
	('the docstring stops stating a figure the gate parses', REG,
	 '`_DUAL_LABELS` (2) is the two the',
	 '`_DUAL_LABELS` is the two the',
	 'test_the_register_docstring_counts_match_the_tables'),
]


def _node(canary_node: str) -> str:
	return canary_node if '/' in canary_node else f'{GATE}::{canary_node}'


_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only', GATE],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_specreg.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	assert s == backup.read_text(), f'{name}: the backup is not this file'
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	for cache in path.parent.rglob('__pycache__'):
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
