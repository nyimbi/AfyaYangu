"""Canaries for §20.2's growth levers: the three drifted cells, the abbreviated handle, and the
count-only gate that passed over all of them.

`GROWTH_LEVERS` was carried in code and read by nothing but its own test. The test counted rows and
asserted which two levers were checkable, so it was a **strict subset** of what §20.2 prints — and
three cells had drifted underneath it:

* lever 5's `why` and `action` were swapped, so the section's reason sat where its act belonged and
  the section's act ("Engineering requirements") was absent from the tree entirely;
* lever 6's `why` was an invented sentence — "A health profile nobody completes is not a profile"
  appears nowhere in `docs/spec.md`;
* lever 4's Action cell wrote `CHAN-5`, the abbreviation §7.2's scheme expands to `CHAN-005`.

The first two are the dangerous shape: a swapped cell reads as prose either way, so no reader of the
file and no row count can see it. The third is the "one of two spellings" failure a second time —
every spec-code gate in the tree matches `PREFIX-\\d{3}`, so a two-digit handle is invisible to all
of them.

* **#1 swaps lever 5's `why` and `action` back**, restoring the defect as it shipped. Aimed at the
  cell comparison, which is the only check that reads either value.
* **#2 invents lever 6's `why` again.** Aimed at the cell comparison, for the same reason.
* **#3 restores the abbreviated handle** `CHAN-005` in the cell. Aimed at the *verbatim* comparison,
  not the resolution: normalising the cell is a different defect from mis-resolving it, and only
  `action_cell` is compared against the section.
* **#4 breaks the resolution** — lever 4's `action` no longer equals its cell with the id
  substituted. Aimed at the resolution check, which is what ties the served name to the section.
* **#5 serves the handle again** by making `action` the cell verbatim, so `CHAN-5` reaches
  `/rollout/acquisition/levers`. Aimed at the **front-door** gate, because the failure is a served
  string and a model-level check would prove less.
* **#6 is inverted**: the *same* mutation as #1, aimed at the count-only test, which must stay
  **green**. This records why the cell comparison exists rather than asserting it — if the count test
  ever starts catching a swapped cell, the two have collapsed into one and this file should say so.
  Inverted, so `-v` not `-q`: a passing run under `-q` prints no node name and the "aimed at the
  right node" check could not tell the right test ran from a collection that picked up nothing.
* **#7 drops a lever's served entry** from `lever_plan()`, so §20.2's six rows meet five on the
  wire. Aimed at the front-door test, which is where the missing lever would be felt.

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
_F = 'tests/ci/test_rollout.py'

CANARIES = [
	# 1. Lever 5's why/action swapped again — the defect as it shipped. Aimed at the cell comparison.
	('lever 5 why and action are swapped again', S,
	 [("""		why='Under 15 MB; no account; Android Go; offline',
		action='Engineering requirements',""",
	   """		why='Adoption falls off with every step between intent and use',
		action='Under 15 MB; no account; Android Go; offline',""")],
	 'test_the_lever_table_is_the_sections_six_rows', False),

	# 2. Lever 6's why invented again. Aimed at the cell comparison.
	('lever 6 why is an invented sentence again', S,
	 [("		why='Airtime or data bundles for health profile completion',",
	   "		why='A health profile nobody completes is not a profile',")],
	 'test_the_lever_table_is_the_sections_six_rows', False),

	# 3. The abbreviated handle normalised inside the *cell*, so the verbatim comparison is what
	#    catches it — the resolution would still produce a correct name from a wrong cell.
	('the action cell is normalised off the section', S,
	 [("		action_cell='Structured intermediary programme (CHAN-5)', checkable=False),",
	   "		action_cell='Structured intermediary programme (CHAN-005)', checkable=False),")],
	 'test_the_lever_table_is_the_sections_six_rows', False),

	# 4. The resolution's link to the registry breaks: the served action no longer equals the cell
	#    with the id substituted, so the name is one nobody checked against the section.
	('the lever id resolution stops matching its cell', S,
	 [("		action='Structured intermediary programme (Human Intermediaries)',",
	   "		action='Structured intermediary programme (CHWs)',")],
	 'test_the_lever_table_is_the_sections_six_rows', False),

	# 5. The handle served again — the defect on the wire. Aimed at the front door.
	('the abbreviated handle is served again', S,
	 [("		action='Structured intermediary programme (Human Intermediaries)',",
	   "		action='Structured intermediary programme (CHAN-5)',")],
	 'test_no_spec_handle_reaches_a_lever_surface', False),

	# 6. The finding, inverted. Same mutation as #1, aimed at the count test, which must stay green.
	('the count check stays blind to the same swapped cell', S,
	 [("""		why='Under 15 MB; no account; Android Go; offline',
		action='Engineering requirements',""",
	   """		why='Adoption falls off with every step between intent and use',
		action='Under 15 MB; no account; Android Go; offline',""")],
	 'test_every_lever_is_present_and_only_the_repo_claims_are_checkable', True),

	# 7. A lever dropped from the served plan, so the route answers five where §20.2 prints six.
	#    The mutation is on the *served* list, not on the `unbacked_claims` loop above it: dropping
	#    a lever from the finding would leave the payload's six rows intact and prove nothing.
	('a lever is dropped from the served plan', S,
	 [("			levers=list(GROWTH_LEVERS), unbacked_claims=unbacked,",
	   "			levers=list(GROWTH_LEVERS)[:5], unbacked_claims=unbacked,")],
	 'test_no_spec_handle_reaches_a_lever_surface', False),
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
	backup = pathlib.Path(f'/tmp/canary_rollout_levers.{path.name}.bak')
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
		# `-v`, not `-q`: canary #6 is inverted and passes, and a passing run under `-q` prints no
		# node name at all — so the `aimed` check could not tell the right test ran from a collection
		# that silently picked up nothing.
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
