"""Canaries for tests/ci/test_acc001.py.

§ACC-001 prints two Features one line apart — "Simplified forms" and "Optional 'simple mode' that
hides advanced features" — and only the second was built. `AccessProfile.simple_mode` and
`AccessService.screens` drop whole screens, and every form on the screens that remained asked
exactly what it asked everybody else. The canaries are the cheap ways to reproduce that substitution
and the ways a drop list goes wrong once it exists:

* **#1** is the defect exactly as it was found: the flag reaches the screens and not the forms.
* **#2** is the dangerous direction of a simplification — a form that cannot fill its own route. The
  client draws a control the server refuses, which is §11.1's failure read backwards.
* **#3** is the other dangerous direction: a form simplified to nothing is a screen with no way
  forward, worse than the long form it replaced.
* **#4** is the silent-rename failure. A drop entry naming a field that no longer exists simplifies
  *nothing* and reports success, so the table rots while the test stays green — the same shape as
  the drift gates in this repo that went on passing after a move.
* **#5** and **#6** are the two halves of the third state: a client forced to send its own setting
  back (a second place for one preference to live), and a default that flips so a caller who asked
  for nothing gets the short form.
* **#7** is the diary entry, and it is the one the table taught: `temperature_c` and `red_flags`
  look droppable and are what `/triage/{ref}/diary/trend` reads, so dropping them leaves every entry
  at the default 36.5 with no flag and the trend screen reporting "no change" forever.
* **#8** makes the route walk non-recursive — the shape that reports six routes and calls itself an
  inventory, so every drop check above it passes vacuously.
* **#9** drops the path-placeholder collection, so a route like `/facilities/{facility_id}/ed-status`
  reads as requiring nothing and its field becomes droppable.
* **#10** is the cross-cutting claim: the drop list applied to the operator forms too, because
  §ACC-001 is not a citizen-only feature.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script. The `__pycache__`
purge after each write is load-bearing for the reason `canary_inf001.py` documents: a same-second
write of the same size reuses the previous canary's bytecode and the canary then tests code it never
mutated.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
F = ROOT / 'src/afya/access/forms.py'
G = ROOT / 'src/afya/service.py'
IDS = ROOT / 'src/afya/ids.py'
V = ROOT / 'src/afya/triage/views.py'

CANARIES = [
	# 1. The flag reaches the screens and not the forms — the defect exactly as it was found. The
	#    route keeps serving the full catalogue to a caller who turned simple mode on.
	('the route ignores the simple-mode flag', G,
	 "\t\tif simple:\n\t\t\tacts = simplified(acts, required_fields(app))",
	 "\t\tif False:\n\t\t\tacts = simplified(acts, required_fields(app))",
	 'test_the_catalogue_route_serves_a_simplified_form_when_asked'),

	# 2. A field the route requires is dropped, so the simplified form cannot fill its own route.
	#    `lat`/`lon` are required on `/places/testing-sites`, so dropping them leaves the client
	#    building a request the server refuses — §11.1's "a control the server refuses" backwards.
	#    (The first version of this canary added `subject_ref`, which is `client_supplied` and not on
	#    the catalogue action at all: the drop list and the route's required set are keyed on
	#    different vocabularies, and a mutation has to be a field the *action* carries to be a defect.)
	('a simplified form drops a required field', F,
	 "\t'testing_sites': ('limit', 'max_cost_kes', 'max_turnaround_hours'),",
	 "\t'testing_sites': ('limit', 'max_cost_kes', 'max_turnaround_hours', 'lat'),",
	 'test_no_simplified_form_drops_a_field_its_route_requires'),

	# 3. A form simplified to nothing. `sos_countdown` draws a path reference, a severity, a
	#    position and a delay; dropping all four leaves a screen that opens and has no way forward on
	#    it, which is worse than the long form it replaced.
	('a simplified form is left with nothing drawn', F,
	 "\t'sos_countdown': ('channel',),",
	 "\t'sos_countdown': ('channel', 'ref', 'severity', 'lat', 'lon', 'at_ms', 'seconds'),",
	 'test_no_simplified_form_is_left_with_nothing_to_fill_in'),

	# 4. A drop entry names a field that is not on the action — a rename that the table did not
	#    follow. It simplifies nothing and reports success, which is how a curation rots.
	('a drop entry names a field that no longer exists', F,
	 "\t'record_dose': ('card_photo_sha256',),",
	 "\t'record_dose': ('card_photo_sha256_renamed',),",
	 'test_every_dropped_field_exists_on_the_action_it_is_dropped_from'),

	# 5. The stored profile is not consulted, so simple mode is a setting the client has to send
	#    back on every request — the second place for one preference to live that the route's own
	#    docstring says it is avoiding.
	('the stored profile is not consulted', G,
	 "\t\tsimple = simple_mode if simple_mode is not None else (\n\t\t\tsubject_ref is not None and access.profile(subject_ref).simple_mode)",
	 "\t\tsimple = simple_mode if simple_mode is not None else False",
	 'test_simple_mode_is_read_from_the_stored_profile_rather_than_the_request'),

	# 6. The default flips: a caller who asked for nothing gets the short form. The long form is the
	#    default and the short one is the opt-in, and inverting that hides questions from people who
	#    never chose to lose them.
	('the default is the simplified form', G,
	 "\t\tsimple = simple_mode if simple_mode is not None else (\n\t\t\tsubject_ref is not None and access.profile(subject_ref).simple_mode)",
	 "\t\tsimple = True",
	 'test_the_full_catalogue_is_what_the_client_gets_by_default'),

	# 7. The diary drops what the trend screen reads. `diary_trend` computes its direction from
	#    `temperature_c` and `red_flags` on the *entry* form; dropping them leaves every entry at the
	#    default with no flag, and the trend screen answers "no change" correctly about the data it
	#    was given and wrongly about the person.
	('the diary drops what the trend screen reads', F,
	 "\t'symptom_diary': ('logged_at_iso',),",
	 "\t'symptom_diary': ('logged_at_iso', 'temperature_c', 'red_flags'),",
	 'test_the_diary_keeps_the_two_fields_the_trend_screen_reads'),

	# 8. The route walk stops at the top level. FastAPI mounts routers, so a non-recursive pass finds
	#    the handful of routes on the app itself and every drop check above it passes vacuously —
	#    "found nothing" and "found six" are the same answer to a gate that only asserts absence.
	('the route walk is not recursive', F,
	 "\t\t\tif hasattr(route, 'routes'):\n\t\t\t\twalk(route.routes)\n\t\t\t\tcontinue",
	 "\t\t\tif False:\n\t\t\t\twalk(route.routes)\n\t\t\t\tcontinue",
	 'test_the_route_walk_finds_the_whole_app_rather_than_its_first_six_routes'),

	# 9. Path placeholders are not collected. FastAPI does not leave them in the endpoint signature,
	#    so `/facilities/{facility_id}/ed-status` reads as requiring nothing and the field that fills
	#    the brace becomes droppable — a client building a URL with braces in it.
	('path placeholders are not collected', F,
	 "\t\t\tnames |= {seg[1:-1] for seg in path.split('/') if seg.startswith('{') and seg.endswith('}')}",
	 "\t\t\tnames |= set()",
	 'test_the_required_reader_sees_required_fields_and_defaults_the_rest'),

	# 10. The simplification is applied to the citizen set only. §ACC-001 is cross-cutting — an
	#     operator on a phone benefits identically — so the operator forms are in the table and a
	#     filter that kept them out would be the section read as a citizen feature.
	('the drop list is scoped to citizen actions', F,
	 "\t\tdropped = set(SIMPLE_FORM_DROPS.get(act.id, ()))",
	 "\t\tdropped = set(SIMPLE_FORM_DROPS.get(act.id, ())) if act.group in ('Triage', 'Emergency') else set()",
	 'test_the_simple_catalogue_is_strictly_smaller'),

	# 11. The reference goes back to being a UUID7 read short, which is what the diary filed under
	#     and what collided across a 256 ms window. The mutation is a *slice of the timestamp*, not a
	#     suffix: `str(uuid7())[-8:]` is 32 bits of random field and would not have reproduced the
	#     defect at all — the first version of this canary used it, passed, and was the canary being
	#     wrong rather than the gate being blind. A mutation has to be the shape of the bug.
	('the reference is a truncated UUID7 again', IDS,
	 "\twith _REF_LOCK:\n\t\tn = next(_REF_SEQ)\n\treturn f'{_REF_PREFIX:03X}{n & 0xFFFFF:05X}'",
	 "\twith _REF_LOCK:\n\t\tn = next(_REF_SEQ)\n\treturn str(uuid7()).replace('-', '').upper()[:8]",
	 'test_ref8_does_not_repeat_across_a_burst'),

	# 12. The counter is replaced by a read of the clock, which is the original defect in its general
	#     form: fifty thousand calls span far more than the window the timestamp is constant across,
	#     so the collision is certain. (The first version of this canary drew 32 random bits instead,
	#     which collides about 27% of the time over 50,000 draws — it missed twice in a row. A
	#     probabilistic canary is not a gate, so the mutation is one that *must* collide. The `import`
	#     is inside the function on purpose: a mutation that raised `NameError` would be "caught" for
	#     a reason that has nothing to do with the property under test.)
	('the reference is read off the clock rather than counted', IDS,
	 "\twith _REF_LOCK:\n\t\tn = next(_REF_SEQ)\n\treturn f'{_REF_PREFIX:03X}{n & 0xFFFFF:05X}'",
	 "\twith _REF_LOCK:\n\t\timport time\n\t\tn = int(time.time() * 1000) & 0xFFFFF\n\treturn f'{_REF_PREFIX:03X}{n:05X}'",
	 'test_ref8_does_not_repeat_across_a_burst'),

	# 13. The diary model stops minting and takes whatever the caller sends as the key. The route
	#     files under `entry_id`, so a client that replays the same body twice with no id still
	#     overwrites — the store's key is the client's to choose.
	('the diary entry id is not minted', V,
	 "\tentry_id: str = Field(default_factory=lambda: 'DIARY-' + ref8())",
	 "\tentry_id: str = ''",
	 'test_two_diary_entries_in_the_same_breath_are_two_entries'),
]


def _node(canary_node: str) -> str:
	if '/' in canary_node:
		return canary_node
	file = 'tests/ci/test_ids.py' if canary_node.startswith('test_ref8') or \
		canary_node == 'test_two_diary_entries_in_the_same_breath_are_two_entries' else \
		'tests/ci/test_acc001.py'
	return f'{file}::{canary_node}'


_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only',
	'tests/ci/test_acc001.py', 'tests/ci/test_ids.py'],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_acc001.{path.name}.bak')
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
