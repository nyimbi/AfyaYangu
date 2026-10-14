"""Canaries for tests/ci/test_acc005.py.

§ACC-005's eighth Target was `missing` while the other seven were carried: no flag on
`DeviceCompatibility`, no bucket anywhere, nothing that recorded or handled a screen constraint. The
canaries are the ways a bucket table goes wrong once it exists — and the first one is the way this
kind of table usually goes wrong, which is that it says "supported" and changes nothing:

* **#1** is that defect: the narrow row made identical to the regular one. Every field exists, the
  route serves, and a 320dp handset lays out exactly as a tablet. It is `charging_adaptive` again —
  a flag with no referent.
* **#2** is the move the section invites and forbids: shrinking the control to fit the small screen.
  A small screen is where a thumb misses, so this is the change that reads as diligence.
* **#3** is the off-by-one at the boundary, where a 600dp tablet gets the phone layout.
* **#4** keys the bucket on width instead of the shorter side, so the layout re-arranges on rotation.
* **#5** leaves the layout unreachable — the table is served and no client can open it.
* **#6** restates the bucket boundaries as this deployment's numbers rather than the platform's, so
  the code no longer matches the source it cites.
* **#7** puts the width on the profile, which is a second place for one fact to live and lets one
  account claim two screen sizes.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script. The `__pycache__`
purge after each write is load-bearing for the reason `canary_inf001.py` documents.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
V = ROOT / 'src/afya/access/views.py'
S = ROOT / 'src/afya/access/service.py'
G = ROOT / 'src/afya/service.py'
M = ROOT / 'src/afya/mobile/actions.py'

CANARIES = [
	# 1. The narrow bucket becomes the regular one with a different name. Every field is present, the
	#    route serves, and a 320dp handset lays out exactly as a tablet — the defect this unit was
	#    about, one level down.
	('the narrow layout changes nothing', S,
	 "\tScreenLayout(bucket='narrow', smallest_width_dp=NARROW_WIDTH_DP, columns=1, scrolls=True,\n\t             pictogram_dp=32, touch_target_dp=56, label_lines=2, degrades=''),",
	 "\tScreenLayout(bucket='narrow', smallest_width_dp=NARROW_WIDTH_DP, columns=2, scrolls=True,\n\t             pictogram_dp=48, touch_target_dp=64, label_lines=1, degrades=''),",
	 'test_the_narrow_layout_differs_in_more_than_its_width'),

	# 2. The control is shrunk to fit the small screen. This is the change that looks like answering
	#    the constraint and is the failure §ACC-001's whole bullet list is against.
	('a screen bucket shrinks the control below the floor', S,
	 "\t             pictogram_dp=32, touch_target_dp=56, label_lines=2, degrades=''),",
	 "\t             pictogram_dp=32, touch_target_dp=40, label_lines=2, degrades=''),",
	 'test_a_screen_bucket_never_shrinks_a_control_below_the_floor'),

	# 3. The boundary is exclusive, so a 600dp tablet gets the phone layout and a 7-inch device is
	#    laid out in one column.
	('the tablet boundary is off by one', S,
	 "\t\t\tif smallest_width_dp >= floor:\n\t\t\t\tchosen = bucket",
	 "\t\t\tif smallest_width_dp > floor:\n\t\t\t\tchosen = bucket",
	 'test_the_shorter_side_selects_the_bucket'),

	# 4. The bucket is keyed on a width the caller supplies rather than on the shorter side. A layout
	#    keyed on width gives a phone two columns in landscape and one in portrait, so the app
	#    re-arranges itself on rotation for a reason that has nothing to do with the space available.
	('the bucket is keyed on an orientation-dependent width', S,
	 "\tdef screen_bucket(smallest_width_dp: int) -> str:",
	 "\tdef screen_bucket(smallest_width_dp: int, width_dp: int | None = None) -> str:",
	 'test_the_short_side_does_not_change_when_the_phone_is_turned'),

	# 5. The table is served and nothing opens it. A capability nobody can reach is a capability that
	#    is not there — the `report_stock` rule.
	('the layout table is unreachable', M,
	 "\t\t_a('screen_layouts', 'How the app fits my screen', 'Access', 'GET', '/access/screen-layouts', []),",
	 "",
	 'test_the_layouts_are_reachable_from_the_catalogue'),

	# 6. The boundaries become this deployment's numbers instead of the platform's. The code still
	#    works and no longer matches the source the audit row cites.
	('the boundaries are not the platform\'s figures', V,
	 "NARROW_WIDTH_DP = 320\nTABLET_WIDTH_DP = 600",
	 "NARROW_WIDTH_DP = 360\nTABLET_WIDTH_DP = 640",
	 'test_the_buckets_are_the_platforms_published_figures'),

	# 7. The width goes on the profile. A screen is a property of the handset, and a profile field is
	#    a second place for one fact to live — the same objection §ACC-001's route makes to a client
	#    sending its own simple-mode setting back.
	('the screen width is a profile setting', V,
	 "\tread_aloud: bool = True\n\tvoice_input: bool = False\n\tlang: str = 'en'",
	 "\tread_aloud: bool = True\n\tvoice_input: bool = False\n\tlang: str = 'en'\n\tsmallest_width_dp: int = 320",
	 'test_the_narrow_question_stays_on_the_form_that_answers_it'),

	# 8. The compatibility answer stops carrying the layouts, so the bullet's claim is not reachable
	#    from the route that answers the device question.
	('the compatibility answer drops the layouts', S,
	 "\t\t\t\tsmallest_width_dp=smallest_width_dp, screen_layouts=self.screen_layouts(),\n\t\t\t)\n\t\treturn DeviceCompatibility(",
	 "\t\t\t\tsmallest_width_dp=smallest_width_dp, screen_layouts=[],\n\t\t\t)\n\t\treturn DeviceCompatibility(",
	 'test_the_compatibility_answer_carries_the_screen_layouts'),

	# 9. The width stops being bounded at the boundary, so a client that sends 0 gets a 500 with a
	#    stack trace instead of a 422 — which is what the first version of the route did. A refusal a
	#    person can act on is the answer; a traceback is not.
	('the width is not bounded at the boundary', G,
	 "\tasync def access_compat(platform: str, smallest_width_dp: int = Query(default=320, ge=1)) -> dict[str, object]:",
	 "\tasync def access_compat(platform: str, smallest_width_dp: int = 320) -> dict[str, object]:",
	 'test_the_route_serves_the_layout_for_the_width_it_was_given'),
]


def _node(canary_node: str) -> str:
	return canary_node if '/' in canary_node else f'tests/ci/test_acc005.py::{canary_node}'


_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only',
	'tests/ci/test_acc005.py'], cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_acc005.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
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
