"""Canaries for tests/ci/test_loc001.py.

§LOC-001 had one `missing` row and one half of the feature that did not exist. The `missing` row was
the Alert content, and its defect was not that the sentence was absent — the route emitted a
near-verbatim line — but that the section's bracket, `Avoid [specific location]`, was served as
"avoid the named location". The other half, Tier 4's "alert on entry **and exit**", had no carrier:
`geofences_at` answered which zones contain a point and every caller was left to diff it.

So every canary here is a plausible way to keep failing, and each one renders as working code: the
route still answers 200 with a list, an alert still names a place, an entry still fires.

* **The place collapses to the placeholder** (#1) — the alert goes back to naming nothing, which is
  the audit row's own defect restored.
* **The county fallback names nothing either** (#2) — a zone with no label falls to the section's
  unresolvable words rather than narrowing to the county, so the bracket stays unresolved for
  exactly the zones nobody has named.
* **A blank label counts as a label** (#3) — `'  '` is truthy, so a form that tabbed through the
  field produces "Avoid   ." instead of falling through.
* **The exit drops the place it left** (#4) — the exit line keeps the 21-day sentence and stops
  naming what was left, which is the one fact the person needs to know which zone.
* **An exit reads as an all-clear** (#5) — the exit sentence becomes reassurance, which is the
  direction a geofence alert may not fail in: the watch that started on entry is still running.
* **The alert is emitted per position fix** (#6) — the entry fires on every reading, which is how a
  person learns to dismiss the alert and then turns it off.
* **The crossing is recorded with alerts off** (#7) — the Privacy line's "only with consent"
  dropped while the alert still looks correct.
* **Alerts off goes blind** (#8) — the other failure of the same switch: nothing is served at all,
  so a person who disabled logging loses the warning the feature exists to give.
* **The anonymous caller is remembered** (#9) — the open route builds a movement record, and every
  zone after the first reads as already entered.
* **The switch is read from the request** (#10) — `logged` follows the caller's own claim rather
  than the stored decision.
* **The alert is served in the asked-for language** (#11) — the event reports `luo` beside an
  English sentence, so a Dholuo speaker is told the English is Dholuo.
* **The window is retyped on the client** (#12) — `symptom_watch_days` leaves the event and the
  number in the sentence becomes the only copy.
* **The route reverts to the zone list** (#13) — the feature gone at the front door while every
  unit test over the service stays green, which is what the route did before.
* **The entry message says it twice** (#17) — the entry template restates the clause the alert
  already opens with, so the sentence a person reads on entry prints the section's own words twice.
  This one was found by the live probe, not by a test: a unit test over `alert` cannot see it.
* **The privacy note goes one way** (#18) — the reassuring half served for both states, so a person
  who left alerts on is told nothing was kept.
* **The switch route stops binding the token** (#14) — `subject_ref` read from the path without
  comparison, so anyone can enable logging on anyone.
* **The open route grows an unbound subject** (#15) and **the guarded route stops binding the
  token** (#16) — the two ways the subject can end up unbound, caught by the route gate rather than
  by a test of this unit. They are here because the gate is the thing that made the split necessary:
  a canary that proves the gate still fires is the only evidence the split stays enforced.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
L = ROOT / 'src/afya/location/service.py'
S = ROOT / 'src/afya/strings.py'
A = ROOT / 'src/afya/service.py'

CANARIES = [
	# 1. The section's bracket unresolved — the audit row's defect, restored. The route still answers
	#    with a complete sentence and the test that checked only for "You have entered an area" would
	#    pass against it.
	('the place collapses to the placeholder', S,
	 "	label = place_label.strip() if place_label and place_label.strip() else ''\n	if label:\n		return label",
	 "	label = ''\n	if label:\n		return label",
	 'test_the_alert_names_the_specific_location_the_section_brackets'),

	# 2. A zone with no label keeps naming nothing, so the bracket stays unresolved for exactly the
	#    zones nobody has named — which is when the alert is the only thing the person has.
	('the county fallback names nothing', S,
	 "	return table['no_place_county'].format(county=county) if county else table['no_place']",
	 "	return table['no_place']",
	 'test_a_zone_with_no_label_narrows_to_its_county_rather_than_naming_nothing'),

	# 3. A whitespace label treated as a label. `'  '` is truthy, so the alert reads "Avoid   ." —
	#    a sentence with a hole in it, served as if it were complete.
	('a blank label counts as a label', S,
	 "	label = place_label.strip() if place_label and place_label.strip() else ''",
	 "	label = place_label if place_label else ''",
	 'test_a_blank_label_is_not_a_label'),

	# 4. The exit stops naming what was left. The 21-day sentence survives, so the event still reads
	#    as a zone event and the person cannot tell which zone they walked out of.
	('the exit drops the place it left', S,
	 "	return table['exit'].format(place=place)",
	 "	return table['exit'].format(place='')",
	 'test_leaving_a_zone_is_an_exit_and_names_what_was_left'),

	# 5. The exit softened into an all-clear. The one direction this may not fail in: a person who
	#    walks out of an outbreak zone is still inside the 21-day window.
	('an exit reads as an all-clear', S,
	 "			'You have left {place}. The 21-day symptom watch that started when you entered is still '\n			'running — keep monitoring and call 719 if you feel unwell.'",
	 "			'You have left {place}. You are clear — no further monitoring is needed.'",
	 'test_leaving_a_zone_is_an_exit_and_names_what_was_left'),

	# 6. The entry fires on every position fix. The zone set is never written, so the same zone is
	#    announced again on each reading — the shape that makes people disable the feature.
	('the alert is emitted per position fix', L,
	 "		if logging and watch is not None:\n			self._watches[watch.subject_ref] = watch.model_copy(\n				update={'inside': sorted(f.geofence_id for f in now_inside)})",
	 "		if False and watch is not None:\n			self._watches[watch.subject_ref] = watch.model_copy(\n				update={'inside': sorted(f.geofence_id for f in now_inside)})",
	 'test_a_second_fix_inside_the_same_zone_is_not_a_second_entry'),

	# 7. The crossing recorded with alerts off. §LOC-001's Privacy line is "only entry/exit events
	#    logged, and only with consent", and the alert itself still looks right.
	('the crossing is recorded with alerts off', L,
	 "		logging = bool(watch is not None and watch.alerts_enabled)",
	 "		logging = True",
	 'test_alerts_off_still_reports_the_crossing_and_records_nothing'),

	# 8. Alerts off goes blind — the other failure of the same switch, and the one a privacy-minded
	#    implementation ships: the person protected their privacy and lost the warning.
	('alerts off goes blind', L,
	 "		for fence in now_inside:\n			if fence.geofence_id not in was_inside:\n				events.append(self._zone_event(fence, 'entry', logging, lang))",
	 "		for fence in now_inside:\n			if fence.geofence_id not in was_inside and logging:\n				events.append(self._zone_event(fence, 'entry', logging, lang))",
	 'test_alerts_off_still_reports_the_crossing_and_records_nothing'),

	# 9. The anonymous caller remembered. The route is open, so this turns it into a movement record
	#    for every device that calls it — and every zone after the first reads as already entered.
	('the anonymous caller is remembered', L,
	 "		watch = self._watches.get(subject_ref) if subject_ref else None",
	 "		watch = self._watches.setdefault(subject_ref or 'anon', ZoneWatch(subject_ref=subject_ref or 'anon'))",
	 'test_an_anonymous_caller_is_treated_as_someone_who_never_opted_in'),

	# 10. The switch read from the request rather than the store. `logged` follows whatever the
	#     caller claimed, which is a client asserting consent on the person's behalf.
	('the switch is read from the request', L,
	 "		logging = bool(watch is not None and watch.alerts_enabled)",
	 "		logging = watch is not None",
	 'test_the_switch_is_stored_and_not_taken_from_the_request'),

	# 11. The event reports the language that was asked for rather than the one it answered in, so a
	#     Dholuo speaker reads an English sentence believing it is Dholuo.
	('the alert is served in the asked-for language', L,
	 "			logged=logging, lang=answerable(lang),",
	 "			logged=logging, lang=lang,",
	 'test_the_alert_speaks_the_language_the_product_can_answer_in'),

	# 12. The 21-day window leaves the event, so the number in the sentence becomes the only copy and
	#     the client schedules against a second one it typed itself.
	('the window is retyped on the client', L,
	 "			alert=alert, message=zone_transition(lang, event, fence.place_label, alert, fence.county),",
	 "			alert=alert, message=zone_transition(lang, event, fence.place_label, alert, fence.county),\n			symptom_watch_days=0,",
	 'test_the_event_carries_the_21_day_window_it_names'),

	# 13. The route reverts to the zone list, which is what it served before this unit: the sentence
	#     inline, the bracket unresolved, and no entry/exit at all. Every unit test over the service
	#     stays green, which is why the canary names the front-door test.
	('the route reverts to the zone list', A,
	 "		return [e.model_dump(mode='json') for e in location.zones_at(lat, lon, subject_ref, lang)]",
	 "		return [{'geofence_id': f.geofence_id, 'alert': 'You have entered an area where a case was reported. Avoid the named location, monitor for symptoms for 21 days, and call 719 if you feel unwell.'} for f in surveillance.geofences_at(lat, lon)]",
	 'test_the_zone_route_serves_entry_and_exit_through_the_deployment'),

	# 13b. The anonymous route grows a `subject_ref` again. It is the shape this unit first shipped,
	#      and it is an IDOR: the subject is never compared to the token, so one person's crossings
	#      can be read and written by anyone. The route's own gate catches it — which is the point,
	#      since the gate is what makes the split enforceable rather than a convention.
	('the open route grows an unbound subject', A,
	 "	async def surveillance_geofences_at(lat: float, lon: float, lang: str = 'en') -> list[dict[str, object]]:",
	 "	async def surveillance_geofences_at(lat: float, lon: float, subject_ref: str | None = None, lang: str = 'en') -> list[dict[str, object]]:",
	 'tests/ci/test_self_scope.py::test_every_subject_carrying_route_is_guarded'),

	# 13c. The guarded route stops binding the token. Every service test stays green and the route
	#      still answers — with somebody else's crossings if the caller names them.
	('the guarded route stops binding the token', A,
	 "	async def location_zones(subject_ref: str, lat: float, lon: float, lang: str = 'en',\n	                          _subject: str = Depends(require_self())) -> list[dict[str, object]]:",
	 "	async def location_zones(subject_ref: str, lat: float, lon: float, lang: str = 'en',\n	                          _subject: str = Depends(require_scope('self'))) -> list[dict[str, object]]:",
	 'tests/ci/test_self_scope.py::test_every_subject_carrying_route_is_guarded'),

	# 17. The entry message prints the section's sentence twice, which is what the route served before
	#     the live probe caught it.
	('the entry message says it twice', S,
	 "		# section's own words.\n		'entry': '{alert}',",
	 "		# section's own words.\n		'entry': 'You have entered an area where a case was reported. {alert}',",
	 'test_the_entry_message_is_the_alert_and_not_the_alert_twice'),

	# 18. The privacy note served the same way for both states, so the person who consented to being
	#     logged is told nothing was kept — and the switch stops reading as a consent decision.
	('the privacy note goes one way', S,
	 "	return table['logged'] if logged else table['not_logged']",
	 "	return table['not_logged']",
	 'test_the_privacy_note_is_served_both_ways'),

	# 14. The switch route stops binding the token, so a citizen token can enable logging on another
	#     person's subject — the IDOR §17's guards exist to prevent.
	('the switch route stops binding the token', A,
	 "	async def location_set_zone_alerts(subject_ref: str, enabled: bool,\n	                                   _subject: str = Depends(require_self())) -> dict[str, object]:",
	 "	async def location_set_zone_alerts(subject_ref: str, enabled: bool,\n	                                   _subject: str = Depends(require_scope('self'))) -> dict[str, object]:",
	 'test_a_token_may_not_set_another_persons_zone_alerts'),
]

failures = []

# A nonexistent node id makes pytest exit non-zero on a *collection* error, which reads as CAUGHT.
# So every node is collected first and asserted present, and a canary that names a test that is not
# there fails this script rather than passing it.
def _node(canary_node: str) -> str:
	return canary_node if '/' in canary_node else f'tests/ci/test_loc001.py::{canary_node}'

_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only',
	'tests/ci/test_loc001.py', 'tests/ci/test_self_scope.py'],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_loc001.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	# See canary_inf001.py's docstring: a same-second write of the same size reuses the previous
	# canary's bytecode, and the canary then tests code it never mutated.
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
