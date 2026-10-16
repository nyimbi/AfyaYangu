"""Canaries for §20.5's launch sequence, its window headings, and the route that now serves them.

§20.5 was carried in code and reachable by no route, and its only test asserted
`{s.sequence for s in steps} == {'Phase 0', 'Launch week', 'Weeks 2-4'}` — a set literal the test
also wrote. The drift it was blind to is real: §20.5 writes `Weeks 2–4` with an **en-dash**, the
code carried an ASCII hyphen in all five of those rows and the test carried the same hyphen, so
both sides agreed and neither was compared to the section. The same drift §21.1's Timeline column
had, one subsection over.

* **#1 drifts a step's text** — a cell-for-cell comparison catches it; a count-only check cannot.
* **#2 moves a step between windows** without changing the total, which is what the per-window
  `counts` exists for: the sum stays 18 and only the split moves.
* **#3 reverts a window heading to the slug form** (`Phase 0` where §20.5 writes
  `Phase 0 — Pre-launch (2 weeks before)`), dropping the parenthetical that is the only place the
  section says the pre-launch window is two weeks.
* **#4 puts the ASCII hyphen back** in the heading — the exact defect as it shipped. The mutation is
  the en-dash swapped for a hyphen, which is *disjoint* from what the verbatim comparison reads
  (it compares whole strings, so any byte change is caught, but a canary that changed something the
  predicate ignores would prove nothing).
* **#5 drops the route's step list** to an empty one — the front-door test's count is what catches
  it, since `findall` over an empty list is clean. Aimed at the front door, because the failure is
  a served payload and a model-level check would prove less.
* **#6 stops the route serving `counts`** — the per-window split is the finding, and a route that
  serves the flat list alone hides a step that moved.
* **#7 narrows the spec-reader's heading predicate** to `endswith(':')`, which matches no heading in
  §20.5 (they all end `:**`). The plan reads empty and every comparison above it is vacuous — the
  "predicate that matches nothing reports clean" hazard, aimed at the reader itself.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line fails this script. `__pycache__` is purged
after each write, for the reason `canary_inf001.py` documents.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
S = ROOT / 'src/afya/rollout/service.py'
A = ROOT / 'src/afya/service.py'
T = ROOT / 'tests/ci/test_rollout.py'

CANARIES = [
	# 1. A step's text drifts from §20.5's bullet.
	('a launch step drifts from the section', S,
	 [("	LaunchStep(sequence='Phase 0', step='Finalise telco zero-rating agreements',",
	   "	LaunchStep(sequence='Phase 0', step='Finalise telco zero-rating agreement',")],
	 'test_the_launch_sequence_is_the_sections_three_windows_cell_for_cell', False),

	# 2. A step moves window without changing the total — 18 stays 18, the split moves.
	('a step moves between windows', S,
	 [("	LaunchStep(sequence='Weeks 2–4', step='Scale CHW training to 2,000',",
	   "	LaunchStep(sequence='Launch week', step='Scale CHW training to 2,000',")],
	 'test_the_launch_sequence_is_the_sections_three_windows_cell_for_cell', False),

	# 3. The heading reverts to the slug, dropping the parenthetical §20.5 prints.
	('the window heading drops its parenthetical', S,
	 [("	'Phase 0': 'Phase 0 — Pre-launch (2 weeks before)',",
	   "	'Phase 0': 'Phase 0',")],
	 'test_the_launch_sequence_is_the_sections_three_windows_cell_for_cell', False),

	# 4. The en-dash back to an ASCII hyphen — the defect as it shipped, in the heading.
	('the window heading drifts back to an ASCII hyphen', S,
	 [("	'Weeks 2–4': 'Weeks 2–4',", "	'Weeks 2–4': 'Weeks 2-4',")],
	 'test_the_launch_sequence_is_the_sections_three_windows_cell_for_cell', False),

	# 5. The route serves no steps. `findall` over an empty list is clean, so the front-door count is
	#    what makes the handle check non-vacuous.
	('the launch route serves an empty sequence', A,
	 [("			'steps': [s.model_dump(mode='json') for s in plan.steps],",
	   "			'steps': [],")],
	 'test_the_launch_route_serves_the_sequence_and_no_handle', False),

	# 6. The route stops serving the per-window split — the flat list hides a moved step.
	('the launch route drops the per-window counts', A,
	 [("			'counts': plan.counts,", "			'counts': {},")],
	 'test_the_launch_route_serves_the_sequence_and_no_handle', False),

	# 7. The spec-reader's heading predicate narrowed so it matches nothing. Every heading in §20.5
	#    ends `:**`, so `endswith(':')` finds no window and the plan reads empty — the "predicate that
	#    matches nothing reports clean" hazard, aimed at the reader itself. The test must fail.
	('the spec heading reader matches no window', T,
	 [("		if line.startswith('**') and line.endswith(':**'):",
	   "		if line.startswith('**') and line.endswith(':'):")],
	 'test_the_launch_sequence_is_the_sections_three_windows_cell_for_cell', False),
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
	backup = pathlib.Path(f'/tmp/canary_rollout_launch.{path.name}.bak')
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
