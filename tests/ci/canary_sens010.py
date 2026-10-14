"""Canaries for the §SENS-010 gates in tests/ci/test_sens010.py.

Four ways this gate can fail open, each of which gets a canary — because a gate whose exit 0 has
never been watched turning to 1 is not evidence that it ran anything.

* **The two absences read alike.** The test that matters most is
  `test_an_unregistered_tag_and_a_withdrawn_target_do_not_read_alike`, and its blind spot is the
  *class* of defect §MED-001's four outcomes established: collapsing two different reasons into one
  boolean. Canary #1 collapses them, which is what a later "simplification" would do.
* **The tag carries the person.** `test_a_tag_holds_the_target_and_never_the_person` asserts the
  model's field set. Canary #2 adds a field a wristband would plausibly carry, which is exactly how
  a privacy boundary erodes — one useful field at a time.
* **The resolver rots.** `test_every_target_names_a_resolver_that_imports` walks the refs. Canary #3
  points one at an attribute that does not exist, the mistake actually made while writing this
  module (`PPE_DONNING` is a key in `JOB_AIDS`, not a module attribute).
* **The audit and the module drift.** Canary #4 marks a §SENS-010 row `missing` again while the code
  that carries it is still there — the row going stale in the direction that reports a gap nobody
  has.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
TAGS = ROOT / 'src/afya/sensors/tags.py'
AUDIT = ROOT / 'src/afya/content_audit/service.py'

CANARIES = [
	# 1. The two ways a tap answers nothing are collapsed into one. Every other test in the file
	#    accepts this: both are still `resolved=False` with a note, and only the note's content and
	#    the `target_ref` distinguish them.
	('an unregistered tag and a withdrawn target read alike', TAGS,
	 "\t\t\t\treturn TagVerdict(tag_id=tag_id, resolved=False, target=tag.target,\n"
	 "\t\t\t\t\ttarget_ref=tag.target_ref,\n"
	 "\t\t\t\t\tnote='This tag is registered, but the equipment it named has been taken off the register.')",
	 "\t\t\t\treturn TagVerdict(tag_id=tag_id, resolved=False,\n"
	 "\t\t\t\t\tnote='This tag is not registered here. Check that you tapped the right one.')",
	 'test_an_unregistered_tag_and_a_withdrawn_target_do_not_read_alike'),

	# 2. The tag grows a field a wristband would plausibly carry. This is the privacy boundary
	#    eroding the way it actually does — one useful field at a time, each defensible alone.
	('the tag carries the person it is attached to', TAGS,
	 "\ttarget_ref: str = Field(min_length=1)\n\tlabel: str = Field(min_length=1)\n\tbound_at_iso: str",
	 "\ttarget_ref: str = Field(min_length=1)\n\tpatient_name: str = Field(default='', min_length=0)\n\tlabel: str = Field(min_length=1)\n\tbound_at_iso: str",
	 'test_a_tag_holds_the_target_and_never_the_person'),

	# 3. A resolver points at an attribute that does not exist. `resolves` walks the dotted path, so
	#    a rename off the class fails here rather than at a call site that no longer exists — and this
	#    is the mistake made while writing the module, not a hypothetical.
	('a target names a resolver that does not exist', TAGS,
	 "\t'patient': 'afya.records.service:RecordsService.wallet',",
	 "\t'patient': 'afya.records.service:RecordsService.wristband_lookup',",
	 'test_every_target_names_a_resolver_that_imports'),

	# 4. A row the code carries is filed as a gap again. The audit's own gate (`unresolved == []`)
	#    would not see it — a `missing` row has no ref to rot — so only the row-level assertion can.
	('a carried application is filed as missing again', AUDIT,
	 "\t('SENS-010', 'Applications', 'Equipment tracking', 'carried', 'afya.sensors.tags:EquipmentRegister',",
	 "\t('SENS-010', 'Applications', 'Equipment tracking', 'missing', None,",
	 'test_the_audit_records_the_four_as_carried_with_those_resolvers'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_sens010.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	target = f'tests/ci/test_sens010.py::{node}'
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', target],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
		# Caught for the *right* reason: the failure must name the node the canary aimed at, not a
		# collection error or a sibling's breakage from the same edit.
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
