"""Canaries for §16.5's stated total — the section that contradicts its own table.

§16.5's nine rows sum to 78 MB and its closing line says "**Total with all modules:** ~60 MB". The
code carried neither number against the other: `full_install_mb` was computed and compared to
nothing, so an 18 MB self-contradiction inside one section was invisible to every test in the tree.
The repair carries the stated figure and reports the disagreement instead of resolving it — the
tempting fix is to make the arithmetic agree, and that is the defect these canaries aim at.

Each mutation is *disjoint* from what its predicate reads:

* **#1 resolves the contradiction in code** — `full` is capped at the stated total, so the plan
  agrees with the section by construction. This is the defect the unit exists to prevent, and it is
  aimed at the test that pins 78, because a plan that reported 60 would satisfy every other check in
  the file (the row count, the per-row sizes, the delivery split) while asserting a total the table
  does not reach.
* **#2 drops the stated figure from the served plan.** Aimed at the front-door test: a model-level
  check would prove the service computes it, and the finding is a payload an auditor reads.
* **#3 drifts the constant off the section** — 60 → 65. Aimed at the test that reads the figure out
  of `docs/spec.md`, which is the only check that ties the constant to the section rather than to
  itself. A test comparing the constant to a literal in the same file would move with it.
* **#4 drops the gap sentence from the note** while leaving the flag false. Aimed at the served
  test's note assertion: `within_statement: false` with no figures beside it reads as a budget
  breach, which is the opposite of what the finding says. The mutation is on the note, not on the
  flag, so the boolean assertions still pass and only the sentence check fires.
* **#5 makes the comparison exclusive** (`full < STATED_TOTAL_MB`) — a strictly stronger predicate
  than the section's `~` supports. It does not change today's verdict (78 is not under 60 either
  way), so nothing fires; this canary is **inverted** and records that the direction of the
  comparison is not what any test currently pins, rather than pretending a green run proves it.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). `__pycache__`
is purged after each write, for the reason `canary_inf001.py` documents. A canary that passes is a
bug in the canary, so a MISSED line fails this script.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
S = ROOT / 'src/afya/rollout/service.py'
_F = 'tests/ci/test_rollout.py'

CANARIES = [
	# 1. The contradiction resolved in code: the total is capped at the stated figure, so the plan
	#    agrees with §16.5 by construction and the finding disappears. Aimed at the test pinning 78.
	('the module total is capped at the stated figure', S,
	 "		full = round(base + on_demand + sum(m.size_mb for m in MODULES if m.delivery == 'automatic'), 2)",
	 "		full = min(round(base + on_demand + sum(m.size_mb for m in MODULES if m.delivery == 'automatic'), 2), STATED_TOTAL_MB)",
	 'test_the_sections_stated_total_is_carried_and_its_rows_do_not_reach_it'),

	# 2. The stated figure dropped from the served plan, so the route answers the table without the
	#    number it disagrees with. Aimed at the front door, because the finding is a payload.
	('the served plan drops the stated total', S,
	 "			stated_total_mb=STATED_TOTAL_MB, within_statement=within_statement,",
	 "",
	 'test_the_app_size_route_serves_the_stated_total_and_the_disagreement'),

	# 3. The constant drifts off the section. Aimed at the test that reads the figure from
	#    `docs/spec.md`, which is the only check that can see the drift.
	('the carried total drifts off the section', S,
	 "STATED_TOTAL_MB: float = 60.0",
	 "STATED_TOTAL_MB: float = 65.0",
	 'test_the_sections_stated_total_is_carried_and_its_rows_do_not_reach_it'),

	# 4. The flag stays false and the sentence naming both figures is dropped, so the served payload
	#    reports a disagreement without saying what disagrees with what.
	('the note stops naming the two figures', S,
	 "			notes.append(\n"
	 "				f'the nine rows sum to {full:g} MB against §16.5\\'s stated ~{STATED_TOTAL_MB:g} MB, '\n"
	 "				f'a {full - STATED_TOTAL_MB:g} MB gap the section does not explain')",
	 "			pass",
	 'test_the_app_size_route_serves_the_stated_total_and_the_disagreement'),

	# 5. Inverted: the comparison made strict, which the section's `~` does not support. Nothing
	#    currently pins the direction, so this must stay green — it records that fact rather than
	#    asserting a gate that is not there.
	('the comparison direction is not pinned by any test', S,
	 "		within_statement = full <= STATED_TOTAL_MB",
	 "		within_statement = full < STATED_TOTAL_MB",
	 'test_the_sections_stated_total_is_carried_and_its_rows_do_not_reach_it'),
]

# A canary whose test does not exist would "pass" for the wrong reason, so collection is asserted
# before anything is mutated.
_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only', _F],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_KNOWN = {line.strip().split('::')[-1] for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({c[4] for c in CANARIES if c[4] not in _KNOWN})
assert not _missing, f'canaries name tests that do not exist: {_missing}'


failures = []
for name, path, old, new, node in CANARIES:
	inverted = name == 'the comparison direction is not pinned by any test'
	backup = pathlib.Path(f'/tmp/canary_app_size_total.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	# A same-second write of the same size reuses the previous canary's bytecode, and the canary then
	# tests code it never mutated. Purged for the file just written.
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		# `-v`, not `-q`: canary #5 is inverted and passes, and a passing run under `-q` prints no
		# node name at all — so the `aimed` check could not tell the right test ran from a collection
		# that silently picked up nothing.
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
