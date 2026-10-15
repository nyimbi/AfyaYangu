"""Canaries for §21.1's Channels column and the tier ceiling it sits beside.

§21.1 is a table with two columns that constrain each other — Channels and Tiers — and the phase
sections §21.2–§21.7 schedule features under both. Three defects lived in the gap, and each is
invisible to a check on one column alone:

* the Channels column carried as-is served the literal string `'all'` on `/rollout/phases`, an
  anonymous partner-facing route, where it read as a channel id beside `CHAN-006`;
* the `+` in `+ CHAN-6` is cumulative, so reading the cell as exclusive made Phase 2's channel set
  **shrink** from six to one as the rollout advanced;
* `CHAN-005` (Tier 2) is scheduled in §21.2 and §21.3 under a ceiling of Tier 1, a contradiction
  between two columns of one row that no existing check crossed.

* **#1 restores the quantifier** as a served channel, aimed at the front-door test — the route is
  where it was wrong, so a model-level canary would prove less.
* **#2 reverts Phase 2 to the exclusive reading**, which the accumulation assertion catches and a
  check on `channels_cell` cannot: the cell is unchanged and correct, only the expansion is wrong.
* **#3 removes the ceiling crossing** from the readiness report, aimed at the finding test.
* **#4 raises the ceiling instead of reporting the crossing** — the "resolve it by picking a column"
  failure the code deliberately refuses. `CHAN-005` stays Tier 2 and Phase 1's ceiling becomes 2, so
  the crossing disappears while §21.1's `Tier 1` cell is contradicted; the Channels-column test is
  what catches it, since the ceiling assertions alone would read the new number as consistent.
* **#5 drops the en-dash from a Timeline cell**, restoring the ASCII form the code carried against
  §21.1's own text. Aimed at the cell comparison, which is what makes the whole table verbatim.

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
S = ROOT / 'src/afya/rollout/service.py'

_ALL_CHANNELS = "'CHAN-000', 'CHAN-001', 'CHAN-002', 'CHAN-003', 'CHAN-004', 'CHAN-005', 'CHAN-006'"

CANARIES = [
	# 1. The quantifier served as a channel again — the defect as it shipped, on the wire.
	('the All cell is served as a channel id again', S,
	 [("		channels=list(ALL_CHANNELS), channels_cell='All', max_tier=2, tiers_cell='Tier 1–2', weeks_start=8, weeks_end=26),",
	   "		channels=['all'], channels_cell='All', max_tier=2, tiers_cell='Tier 1–2', weeks_start=8, weeks_end=26),")],
	 'test_the_routes_are_scoped_and_the_plan_is_public', False),

	# 2. Phase 2 read as exclusive: the cell is still `+ CHAN-6` and still correct, only the
	#    expansion is wrong — which is why the assertion has to be on the accumulation.
	('the cumulative row is read as exclusive again', S,
	 [(f"""		channels=[{_ALL_CHANNELS}],
		channels_cell='+ CHAN-6', max_tier=1, tiers_cell='Tier 1', weeks_start=2, weeks_end=8),""",
	   """		channels=['CHAN-006'],
		channels_cell='+ CHAN-6', max_tier=1, tiers_cell='Tier 1', weeks_start=2, weeks_end=8),""")],
	 'test_the_channels_column_is_expanded_and_accumulated', False),

	# 3. The crossing stops being reported.
	('the tier-ceiling crossing stops being reported', S,
	 [("""		over_ceiling = self._tier_over_ceiling(phase)""",
	   """		over_ceiling: list[str] = []""")],
	 'test_a_deliverable_above_its_own_phases_ceiling_is_reported', False),

	# 4. The crossing "resolved" by raising the ceiling — the failure the docstring refuses. The
	#    ceiling is pinned as a literal by `test_the_phase_table_matches_the_spec`, so that test
	#    alone would read the new number as self-consistent; what catches it is the cell comparison
	#    against §21.1's own Tiers column.
	('the crossing is resolved by raising the ceiling', S,
	 [("		channels_cell='CHAN-0,1,2,3,4,5', max_tier=1, tiers_cell='Info only', weeks_start=0, weeks_end=4),",
	   "		channels_cell='CHAN-0,1,2,3,4,5', max_tier=2, tiers_cell='Tier 1–2', weeks_start=0, weeks_end=4),")],
	 'test_the_channels_column_is_expanded_and_accumulated', False),

	# 5. The Timeline cell back to ASCII, against §21.1's en-dash.
	('the timeline cell drifts back to an ASCII hyphen', S,
	 [("timeline='Weeks 0–4'", "timeline='Weeks 0-4'")],
	 'test_the_channels_column_is_expanded_and_accumulated', False),
]

# A canary whose test does not exist would "pass" for the wrong reason, so collection is asserted
# before anything is mutated.
_F = 'tests/ci/test_rollout.py'
_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only', _F],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_KNOWN = {line.strip().split('::')[-1] for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({c[3] for c in CANARIES if c[3] not in _KNOWN})
assert not _missing, f'canaries name tests that do not exist: {_missing}'


failures = []
for name, path, patches, node, inverted in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_rollout_channels.{path.name}.bak')
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
		# at all — so the `aimed` check could not tell the right test ran from a collection that
		# silently picked up nothing.
		proc = subprocess.run(['uv', 'run', 'pytest', '-v', '-p', 'no:randomly', f'{_F}::{node}'],
			cwd=ROOT, capture_output=True, text=True)
		passed = proc.returncode == 0
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
