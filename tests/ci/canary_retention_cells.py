"""Canaries for §SEC-005's retention table, whose cells nothing compared to the section.

The table carried a `days` and a `trigger` per data type and every test over it checked internal
consistency — a finite window, a trigger in a three-member set, `user_can_delete` agreeing with
`USER_DELETABLE`. Nothing read `docs/spec.md`. So `photos` could say `{'days': 30, 'trigger':
'automatic'}` against a section row reading "Until clinical review complete" / "Automatic **unless
user retains**", and both halves of that drift were load-bearing:

* the **30 days** is a window §SEC-005 does not state — it names an event, a clinical review;
* the plain **`automatic`** dropped the carve-out, so `purge_expired` deleted a photo the person had
  chosen to keep. That is the section's own exception, removed by the code that exists to enforce it,
  and no test could see it because the trigger was only ever compared to a three-member set.

Each mutation is *disjoint* from what its predicate reads:

* **#1** restores the shipped defect exactly — `photos` on a plain automatic clock. Aimed at the
  purge test, because that is the consequence: the row is still *valid* (a member of the trigger
  set, a finite window), so the consistency test passes and only the carve-out test can catch it.
* **#2** changes the derived window without touching the stated cell, which is a *different* claim
  from #1: the section's figure is intact and this build's reading of it has moved. Aimed at the
  spec-comparison test, which is the one that reads the section rather than the table.
* **#3** edits the stated cell to agree with the derived number — the "invent a reconciliation"
  move, which would make `within_statement` true for a row whose section states an event. Aimed at
  the comparison test: it fails because the cell no longer matches `docs/spec.md`.
* **#4** makes `is_automatic` read the trigger string directly again, which is the *mechanism* by
  which the carve-out was lost, separate from the data that carries it.
* **#5** removes `consent_records`' empty stated cells, so a row this build adds beyond §SEC-005
  presents itself as a stated requirement. Aimed at the front-door test's stated-row rule.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree).
`__pycache__` is purged after each write, for the reason `canary_inf001.py` documents. A canary that
passes is a bug in the canary, so a MISSED line fails this script.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
V = ROOT / 'src/afya/retention/views.py'
S = ROOT / 'src/afya/retention/service.py'

CANARIES = [
	# 1. The defect as it shipped: the carve-out gone from *both* the section cell this build carries
	#    and the mechanism, so `purge_expired` deletes what the person kept. Both halves move together
	#    on purpose — moving the trigger alone trips the module-level assert in `views.py`, and a
	#    canary that trips an import guard never runs its test, so it would prove nothing about the
	#    test. Disjoint from #2 (which moves the window) and #4 (which moves the reader).
	('the carve-out is gone from the cell and the clock', V,
	 "	'photos': {'days': 30, 'trigger': 'automatic_unless_retained',\n"
	 "		'stated': 'Until clinical review complete', 'stated_trigger': 'Automatic unless user retains'},",
	 "	'photos': {'days': 30, 'trigger': 'automatic',\n"
	 "		'stated': 'Until clinical review complete', 'stated_trigger': 'Automatic'},",
	 'test_every_retention_cell_is_the_sections_own'),

	# 2. The derived window moves and the section's stated cell does not. A different claim from #1:
	#    the section's figure is intact, this build's reading of it has drifted.
	('the derived photo window drifts from the section', V,
	 "	'photos': {'days': 30, 'trigger': 'automatic_unless_retained',",
	 "	'photos': {'days': 45, 'trigger': 'automatic_unless_retained',",
	 'test_every_retention_cell_is_the_sections_own'),

	# 3. The stated cell is edited to agree with the derived number — inventing a reconciliation the
	#    section does not state, which is the move `within_statement` exists to make impossible. The
	#    trigger cell is left alone so the module-level assert stays satisfied and the *test* is what
	#    catches this, not an import guard. Aimed at the comparison test, which reads `docs/spec.md`.
	('the stated cell is rewritten to match the build', V,
	 "		'stated': 'Until clinical review complete', 'stated_trigger': 'Automatic unless user retains'},",
	 "		'stated': '30 days', 'stated_trigger': 'Automatic unless user retains'},",
	 'test_every_retention_cell_is_the_sections_own'),

	# 4. The mechanism the carve-out was lost through: the trigger compared as a string again, so
	#    `automatic_unless_retained` reads as automatic. Disjoint from #1, which changes the data —
	#    this changes the reader, and would defeat the carve-out even with the row correct.
	('is_automatic stops reading the carve-out', S,
	 "		return RETENTION_TABLE[data_type]['trigger'] == 'automatic'",
	 "		return str(RETENTION_TABLE[data_type]['trigger']).startswith('automatic')",
	 'test_a_retained_photo_is_not_purged_by_the_automatic_clock'),

	# 5. A row beyond §SEC-005 presents itself as a stated requirement, which is what the empty cells
	#    exist to prevent. Aimed at the front-door test's stated-row rule.
	('a build addition claims to be a stated row', V,
	 "	'consent_records': {'days': 3650, 'trigger': 'policy', 'stated': '',\n		'stated_trigger': ''},",
	 "	'consent_records': {'days': 3650, 'trigger': 'policy', 'stated': '3650 days',\n		'stated_trigger': 'Policy-driven'},",
	 'test_every_retention_cell_is_the_sections_own'),
]

_FILES = {
	'test_a_retained_photo_is_not_purged_by_the_automatic_clock': 'tests/ci/test_retention.py',
	'test_every_retention_cell_is_the_sections_own': 'tests/ci/test_retention.py',
}

# A canary whose test does not exist would "pass" for the wrong reason, so collection is asserted
# for every file a canary aims at, before anything is mutated.
for _f in sorted(set(_FILES.values())):
	_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only', _f],
		cwd=ROOT, capture_output=True, text=True)
	assert _collected.returncode == 0, _collected.stdout[-2000:]

failures = []
for name, path, old, new, node in CANARIES:
	f = _FILES[node]
	backup = pathlib.Path(f'/tmp/canary_retention_cells.{path.name}.bak')
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
		# `-v`, not `-q`: a passing run under `-q` prints no node name, so `aimed` could not tell
		# the right test ran from a collection that silently picked up nothing.
		proc = subprocess.run(['uv', 'run', 'pytest', '-v', '-p', 'no:randomly', f'{f}::{node}'],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
		aimed = node in proc.stdout
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
		for cache in path.parent.rglob('__pycache__'):
			shutil.rmtree(cache, ignore_errors=True)
	ok = caught and aimed
	print(f'{"CAUGHT " if ok else "MISSED "} {name}')
	if not ok:
		failures.append(name)
		print(f'  returncode={proc.returncode} aimed_at_node={aimed}')
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
