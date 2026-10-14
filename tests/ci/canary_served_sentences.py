"""Canaries for the three served sentences that asserted more than their boolean established.

One defect class, three surfaces, and in each the code computes a correct boolean and then renders a
sentence naming *one* of the two or three facts that reach the same branch:

1. **§CHAN-2's closing USSD screen.** `location=True` is the *consent* the first prompt collected;
   the screen said "Your location was shared", which is a transmission. A USSD session carries no
   coordinates — `CallbackRequest.location_shared`'s own docstring says so.
2. **§LOC-001's privacy note on an open route.** `logged=False` is reached by a person who switched
   alerts off *and* by a caller with no subject at all; `/surveillance/geofences-at` passes no
   subject, and the single sentence told an anonymous caller "Alerts are off" — a switch they never
   touched.
3. **`ChwService.activity_summary`.** `period` was echoed into the response and otherwise ignored,
   so the supervision note was decided by a lifetime count while the mobile catalogue offered the
   screen as "My activity this week". **#4** is the same defect one level up: the route's default was
   the literal `'2026-W41'`, so the week a caller who left the parameter out was asking about was
   fixed at deployment.

Every mutation is the *pre-fix* code, which is the cheap wrong version by construction. A canary that
passes is a bug in the canary, so a MISSED line fails this script.

The `__pycache__` purge after each write is load-bearing for the reason `canary_inf001.py` documents:
a same-second write of the same size reuses the previous canary's bytecode, and canary #3's patch is
`period`-shaped — the same length as the line it replaces is not, but the class of bug is real and
the purge costs nothing.

Reverted from a `cp` backup, never with `git checkout --`: the mutation and the real change live in
the same uncommitted tree.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
STRINGS = ROOT / 'src/afya/strings.py'
LOC = ROOT / 'src/afya/location/service.py'
CHW = ROOT / 'src/afya/chw/service.py'
ROUTES = ROOT / 'src/afya/service.py'

CANARIES = [
	# 1. The consent sentence goes back to claiming a transmission. This is the exact pre-fix string,
	#    so the mutation is disjoint from the blocklist the test asserts (`was shared`) by definition.
	('the USSD close claims the location was shared', STRINGS,
		"		'location': 'You agreed to share your location if a health worker asks for it.',",
		"		'location': 'Your location was shared.',",
		'test_the_closing_screen_reports_the_consent_rather_than_a_transmission'),

	# 2. The privacy note collapses to one sentence for both states, which is the pre-fix shape: an
	#    anonymous caller is then told about a switch they do not have.
	('the privacy note names an alerts choice an anonymous caller never made', LOC,
		"			privacy_note=zone_privacy_note(lang, logging, anonymous=anonymous),",
		"			privacy_note=zone_privacy_note(lang, logging),",
		'test_the_note_tells_an_anonymous_caller_they_never_opted_in'),

	# 3. `period` is ignored again, so the note is decided by a lifetime count. The filter is dropped
	#    rather than the parameter, because the parameter was never the problem — it was always there.
	('the activity summary ignores the period it names', CHW,
		"		rows = [e for e in self._activity if e.chw_ref == chw_ref and _in_period(e.at_iso, period)]",
		"		rows = [e for e in self._activity if e.chw_ref == chw_ref]",
		'test_the_summary_is_scoped_to_the_period_it_names'),

	# 4. The route's default goes back to the literal week, so "My activity this week" reads week 41
	#    for the life of the deployment. Same defect one level up from #3: the period is named by the
	#    caller's absence rather than by the clock.
	('the activity route defaults to a fixed week rather than the running one', ROUTES,
		"		if not period:\n			iso_year, iso_week, _ = datetime.now(timezone.utc).date().isocalendar()\n			period = f'{iso_year}-W{iso_week:02d}'",
		"		period = period or '2026-W41'",
		'test_the_activity_route_defaults_to_the_week_it_is_running_in'),
]

NODES = {
	'test_the_closing_screen_reports_the_consent_rather_than_a_transmission': 'tests/ci/test_chan_callbacks.py',
	'test_the_note_tells_an_anonymous_caller_they_never_opted_in': 'tests/ci/test_loc001.py',
	'test_the_summary_is_scoped_to_the_period_it_names': 'tests/ci/test_chw.py',
	'test_the_activity_route_defaults_to_the_week_it_is_running_in': 'tests/ci/test_chw.py',
}

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_served_sentences.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly',
			f'{NODES[node]}::{node}'], cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	print(f'{"CAUGHT " if caught else "MISSED "} {name}')
	if not caught:
		failures.append(name)
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
