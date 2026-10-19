"""§8.6 LOC-001: geofenced risk alerts, and the two halves that were not there.

The section asks for four things and the audit carried three. The one row that was `missing` is the
**Alert content**, and it was missing in a specific way: the route emitted a near-verbatim line
inline, so the sentence existed and nothing resolved to it — and the section's own bracket,
`Avoid [specific location]`, was served as "avoid the named location". That is the one action the
sentence asks a person to take, asked of a place the sentence declined to name.

The other half had no carrier at all. Tier 4 asks the system to "alert on entry **and exit**", and
nothing derived a crossing from a position: `geofences_at` answered which zones contain a point, and
every caller was left to diff that against the last answer. The tests worth reading are about the
two directions that a geofence feature fails in:

* **A zone is an event, not a reading.** A person walking across a 5 km zone must be told once, on
  the way in, and once on the way out — not on every GPS fix. An alert that fires per fix is one
  people turn off, and a turned-off alert is the feature gone.
* **"Fully disableable" does not mean blind.** With alerts off the crossing is still *reported* —
  the person standing in a zone is owed that warning — but nothing is recorded, which is the
  Privacy line ("Only entry/exit events logged, and only with consent") made checkable rather than
  asserted in a docstring. A feature that went silent when disabled would make the privacy control
  cost the person the warning it exists to give.
"""
import ast
import pathlib
import re

import httpx
import pytest

from afya.location.service import LocationService
from afya.location.views import ZoneEvent, ZoneWatch
from afya.registry.service import FeatureRegistry
from afya.service import build_services, create_app
from afya.strings import (
	GEOFENCE_ALERT_STRINGS, answerable, geofence_alert, zone_place, zone_privacy_note,
)
from afya.surveillance.service import SurveillanceService
from afya.surveillance.views import Geofence

FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')

ROOT = pathlib.Path(__file__).resolve().parents[2]

# Nairobi, and a point far enough away to be outside every zone the tests draw.
INSIDE = (-1.2864, 36.8172)
OUTSIDE = (-1.4000, 36.8172)


def _svc(*fences: Geofence) -> LocationService:
	"""A service wired to §11.1's real registry, in the shape the deployment wires it.

	The collaborator is `SurveillanceService.geofences_at` itself rather than a lambda returning the
	list: a stub that ignored the coordinates would answer "inside" for every point, and the exit
	half of this feature is entirely about a point that is *not* inside — so a stub would make every
	exit test pass for the wrong reason, or fail for one.
	"""
	registry = SurveillanceService(FeatureRegistry())
	# Written to the registry's own store rather than through `set_geofence`, which is `async` and has
	# nothing to await; every fence these tests build is legal under the rule that method enforces
	# (high alert only on an outbreak zone), and the route that enforces it is exercised at the front
	# door below. Bypassing it here would let a fixture register a zone the product refuses.
	registry._geofences.extend(fences)  # noqa: SLF001  the registry's own store, not a second one
	return LocationService(None, None, registry.geofences_at)


def _fence(fid: str, *, label: str | None = None, county: str = '',
           risk_type: str = 'outbreak', alert_level: str = 'high') -> Geofence:
	return Geofence(geofence_id=fid, lat=INSIDE[0], lon=INSIDE[1], radius_m=5_000,
	                risk_type=risk_type, alert_level=alert_level, place_label=label, county=county)


async def _citizen(c: httpx.AsyncClient, subject: str | None = None) -> tuple[dict[str, str], str]:
	tok = (await c.post('/auth/anonymous', json={'subject_ref': subject} if subject else {})).json()
	return {'Authorization': f'Bearer {tok["token"]}'}, str(tok['subject_ref'])


async def _county_officer(c: httpx.AsyncClient) -> dict[str, str]:
	"""A county health team token through the app's own PKCE flow — §17.4's `county_aggregate`.

	A zone is drawn by the county health authority, which is why the citizen token is refused by
	`/surveillance/geofence`: the same route that draws an outbreak zone over Nairobi must not be
	reachable by anyone who can install the app."""
	from afya.auth.views import s256
	verifier = 'v' * 64
	authz = (await c.post('/auth/pkce/authorize', json={
		'client_id': 'app', 'redirect_uri': 'afya://cb', 'code_challenge': s256(verifier), 'role': 'county_officer',
		'state': 'state-1234'})).json()
	tok = (await c.post('/auth/pkce/token', params={'role': 'county_officer'}, json={
		'authorization_code': authz['authorization_code'], 'client_id': 'app',
		'redirect_uri': 'afya://cb', 'code_verifier': verifier})).json()
	return {'Authorization': f'Bearer {tok["access_token"]}'}


# --- Alert content: the section's sentence, and its bracket ----------------------------------------

def test_the_alert_names_the_specific_location_the_section_brackets() -> None:
	"""`Avoid [specific location]` is the load-bearing part of the sentence, so the test asserts the
	*label* reached the alert rather than that an alert was served. A response carrying the right
	sentence with the bracket unresolved is exactly the defect the row recorded, and a test that
	checked only for "You have entered an area" would pass against it."""
	svc = _svc(_fence('G1', label='Kasese market', county='Busia'))
	events = svc.zones_at(*INSIDE)
	assert len(events) == 1
	alert = events[0].alert
	assert 'Avoid Kasese market.' in alert, alert
	assert 'the named location' not in alert
	assert 'Monitor for symptoms for 21 days. Call 719 if you feel unwell.' in alert


def test_the_entry_message_is_the_alert_and_not_the_alert_twice() -> None:
	"""The live probe found this and no unit test had. The alert already opens with "You have
	entered an area where a case was reported", and the entry template said it again — so the
	message a person actually reads on entry printed the section's sentence twice. A unit test over
	`alert` alone cannot see it, which is why this one reads `message`."""
	svc = _svc(_fence('G1', label='Kasese market', county='Busia'))
	event = svc.zones_at(*INSIDE)[0]
	assert event.message == event.alert
	assert event.message.count('You have entered an area where a case was reported') == 1, event.message


def test_the_alert_is_the_sections_own_sentence() -> None:
	"""The section prints its Alert content in full, so the served string is checked against the
	section rather than against a copy of itself in this file."""
	spec = (ROOT / 'docs/spec.md').read_text()
	row = re.search(r'\*\*Alert content:\*\* "([^"]+)"', spec)
	assert row is not None, 'the section no longer prints its Alert content'
	printed = row.group(1)
	# The one substitution the section invites is the bracket.
	assert printed.replace('[specific location]', 'Kasese market') == geofence_alert('en', 'Kasese market')


def test_a_zone_with_no_label_narrows_to_its_county_rather_than_naming_nothing() -> None:
	"""`place_label` is optional because a zone can be registered before anyone has named it. The
	fallback must still be a place: "the area this alert covers in Busia County" is somewhere a
	person can avoid, and "the named location" is not. The county is the furthest the registry
	actually knows, and the alert stops there rather than inventing a landmark."""
	svc = _svc(_fence('G1', county='Busia'))
	alert = svc.zones_at(*INSIDE)[0].alert
	assert 'Avoid the area this alert covers in Busia County.' in alert


def test_a_zone_with_neither_label_nor_county_says_so_rather_than_inventing_one() -> None:
	"""The last resort, and it has to exist: a registry row with neither field. Naming a place the
	registry does not have would send someone away from the wrong place, which is worse than saying
	the alert covers an area it cannot narrow."""
	place = zone_place('en', None, '')
	assert place == GEOFENCE_ALERT_STRINGS['en']['no_place']
	assert 'County' not in place and 'named' not in place


def test_a_blank_label_is_not_a_label() -> None:
	"""Whitespace is what a form sends when someone tabs through a field, and `'  '` is truthy — so
	a zone whose label was typed as spaces would otherwise be served "Avoid   ." rather than falling
	through to its county."""
	svc = _svc(_fence('G1', label='   ', county='Busia'))
	assert 'Avoid the area this alert covers in Busia County.' in svc.zones_at(*INSIDE)[0].alert


def test_the_alert_speaks_the_language_the_product_can_answer_in() -> None:
	"""§ACC-002's rule, applied rather than restated: a language with a table is answered in it, and
	a language without one is answered in English *and knows it* through `lang` on the event. A
	Dholuo speaker served English without being told would read it believing it is Dholuo."""
	svc = _svc(_fence('G1', label='Kasese market'))
	swahili = svc.zones_at(*INSIDE, lang='sw')[0]
	assert 'Umeingia eneo ambalo kesi iliripotiwa' in swahili.alert
	assert swahili.lang == 'sw'
	luo = svc.zones_at(*INSIDE, lang='luo')[0]
	assert luo.lang == answerable('luo') == 'en'


# --- entry and exit: a zone crossing is an event, not a reading -------------------------------------

def test_a_second_fix_inside_the_same_zone_is_not_a_second_entry() -> None:
	"""The defect this half of the feature is most likely to ship with: alert on every position fix,
	which is how a person learns to dismiss the alert. Two fixes inside one zone are one entry."""
	svc = _svc(_fence('G1', label='Kasese market', county='Busia'))
	svc.set_zone_alerts('U-1', True)
	assert [e.event for e in svc.zones_at(*INSIDE, subject_ref='U-1')] == ['entry']
	assert svc.zones_at(*INSIDE, subject_ref='U-1') == []


def test_leaving_a_zone_is_an_exit_and_names_what_was_left() -> None:
	"""Tier 4's "alert on entry **and exit**". The exit is the one a client is likeliest to render as
	an all-clear, so it names the place that was left and says the watch is still running."""
	svc = _svc(_fence('G1', label='Kasese market', county='Busia'))
	svc.set_zone_alerts('U-1', True)
	assert [e.event for e in svc.zones_at(*INSIDE, subject_ref='U-1')] == ['entry']
	events = svc.zones_at(*OUTSIDE, subject_ref='U-1')
	assert [e.event for e in events] == ['exit']
	assert 'Kasese market' in events[0].message
	assert '21-day symptom watch' in events[0].message
	assert 'safe' not in events[0].message.lower(), 'an exit is not an all-clear'


def test_an_exit_can_name_a_zone_the_registry_no_longer_returns() -> None:
	"""A zone is left by walking out of it, so the registry's answer for the current point does not
	contain it — an exit built from that answer alone could not name the place. The device keeps the
	fence it announced, which is why `_seen_fences` exists. A withdrawal (the county lifting the
	zone) and a departure are the same event here, and both are owed to the person who was told
	about the zone."""
	svc = _svc(_fence('G1', label='Kasese market', county='Busia'))
	svc.set_zone_alerts('U-1', True)
	svc.zones_at(*INSIDE, subject_ref='U-1')
	svc._zones = lambda lat, lon: []  # noqa: SLF001  the zone is lifted while the person is in it
	events = svc.zones_at(*INSIDE, subject_ref='U-1')
	assert [e.event for e in events] == ['exit']
	assert 'Kasese market' in events[0].message


def test_a_zone_left_and_re_entered_is_two_entries() -> None:
	"""`inside` is the zone set as of the last check, so walking out and back in is a new entry. The
	alternative — remembering every zone ever entered — would silence the second warning, which is
	the one that matters if the person has been away for days."""
	svc = _svc(_fence('G1', label='Kasese market', county='Busia'))
	svc.set_zone_alerts('U-1', True)
	assert [e.event for e in svc.zones_at(*INSIDE, subject_ref='U-1')] == ['entry']
	assert [e.event for e in svc.zones_at(*OUTSIDE, subject_ref='U-1')] == ['exit']
	assert [e.event for e in svc.zones_at(*INSIDE, subject_ref='U-1')] == ['entry']


def test_two_zones_at_one_point_are_two_events() -> None:
	"""A county can draw an outbreak zone inside a general advisory one, and both sentences are
	owed: the outer one carries the advisory and the inner one the case. Collapsing them would
	serve whichever the registry happened to list first."""
	svc = _svc(_fence('G1', label='Busia town', county='Busia'),
	           _fence('G2', label='Busia market', county='Busia', risk_type='general', alert_level='medium'))
	svc.set_zone_alerts('U-1', True)
	events = svc.zones_at(*INSIDE, subject_ref='U-1')
	assert sorted(e.geofence_id for e in events) == ['G1', 'G2']
	assert all(e.event == 'entry' for e in events)
	assert {e.place_label for e in events} == {'Busia town', 'Busia market'}


# --- privacy: "only entry/exit events logged, and only with consent" --------------------------------

def test_alerts_off_still_reports_the_crossing_and_records_nothing() -> None:
	"""The Privacy line, made checkable. "Fully disableable" may not mean "blind": the person is
	still told they are in a zone, because that warning is the feature. What they are not owed is a
	record of it — so `logged` is False and `inside` is not written."""
	svc = _svc(_fence('G1', label='Kasese market', county='Busia'))
	svc.set_zone_alerts('U-1', False)
	events = svc.zones_at(*INSIDE, subject_ref='U-1')
	assert [e.event for e in events] == ['entry']
	assert all(e.logged is False for e in events)
	assert svc.zone_watch('U-1').inside == [], 'a crossing was recorded with alerts off'


def test_alerts_on_records_the_crossing() -> None:
	svc = _svc(_fence('G1', label='Kasese market', county='Busia'))
	svc.set_zone_alerts('U-1', True)
	assert [e.logged for e in svc.zones_at(*INSIDE, subject_ref='U-1')] == [True]
	assert svc.zone_watch('U-1').inside == ['G1']


def test_an_anonymous_caller_is_treated_as_someone_who_never_opted_in() -> None:
	"""The route is open, so this is the shape most calls have. Nothing about the caller is recorded
	and every zone reads as an entry — which is the honest answer for a device that has not said who
	it is, and the only one that cannot be used to build a movement record from an open route."""
	svc = _svc(_fence('G1', label='Kasese market', county='Busia'))
	first = svc.zones_at(*INSIDE)
	second = svc.zones_at(*INSIDE)
	assert [e.event for e in first] == ['entry'] and [e.event for e in second] == ['entry']
	assert all(e.logged is False for e in first + second)
	assert svc._watches == {}


def test_the_switch_is_stored_and_not_taken_from_the_request() -> None:
	"""A client that sent `alerts_enabled=true` with each position fix would be asserting the
	person's consent on their behalf. The switch is set through one route and read by the other, so
	the only way to be logged is to have asked to be.

	The watch is created **and turned off** before the check, not left absent: with no watch at all,
	"the person opted out" and "this subject has never been heard of" are the same branch, and a
	`logging` that read `watch is not None` would pass a test built the other way. The off switch has
	to be a real off.
	"""
	svc = _svc(_fence('G1', label='Kasese market', county='Busia'))
	svc.set_zone_alerts('U-1', False)
	assert svc.zone_watch('U-1').alerts_enabled is False, 'the switch was not stored'
	assert svc.zones_at(*INSIDE, subject_ref='U-1')[0].logged is False


def test_turning_alerts_off_does_not_forget_the_zones_already_crossed() -> None:
	"""Otherwise the switch is also a "re-announce everything" button: a person toggling alerts off
	and on would be told on the way back on that they had *entered* a zone they never left."""
	svc = _svc(_fence('G1', label='Kasese market', county='Busia'))
	svc.set_zone_alerts('U-1', True)
	svc.zones_at(*INSIDE, subject_ref='U-1')
	svc.set_zone_alerts('U-1', False)
	assert svc.zone_watch('U-1').inside == ['G1']
	assert svc.zones_at(*INSIDE, subject_ref='U-1') == []


def test_the_watch_defaults_to_off_for_a_subject_nobody_has_heard_of() -> None:
	"""Absent means off, not unknown. An alerts-on default would alert every device in Kenya the
	first time a county drew a zone, and the section's Tier 1 behaviour is explicitly *opt-in*."""
	watch = _svc().zone_watch('U-nobody')
	assert watch == ZoneWatch(subject_ref='U-nobody')
	assert watch.alerts_enabled is False and watch.inside == []


# --- what the event carries -------------------------------------------------------------------------

def test_the_event_carries_the_zones_own_risk_fields() -> None:
	"""A client drawing the zone needs the level and the kind, not just the sentence: §11.1's
	registry distinguishes an outbreak zone from a general advisory one, and the client cannot read
	that back out of the alert text."""
	svc = _svc(_fence('G1', label='Busia market', county='Busia', risk_type='general', alert_level='medium'))
	event = svc.zones_at(*INSIDE)[0]
	assert (event.risk_type, event.alert_level, event.county) == ('general', 'medium', 'Busia')


def test_the_privacy_note_is_served_both_ways() -> None:
	"""§LOC-001's Privacy line addressed to the person, not only checkable in the payload. The two
	notes are different sentences because they answer different questions: one says nothing was kept,
	the other says something was, and a feature that served only the reassuring half would be
	describing a consent decision as a preference."""
	svc = _svc(_fence('G1', label='Kasese market', county='Busia'))
	svc.set_zone_alerts('U-1', False)
	off = svc.zones_at(*INSIDE, subject_ref='U-1')[0]
	assert off.privacy_note == zone_privacy_note('en', False)
	assert 'not recorded' in off.privacy_note and 'Alerts are off' in off.privacy_note

	svc.set_zone_alerts('U-2', True)
	on = svc.zones_at(*INSIDE, subject_ref='U-2')[0]
	assert on.privacy_note == zone_privacy_note('en', True)
	assert on.privacy_note != off.privacy_note
	assert 'recorded on this phone' in on.privacy_note


def test_the_note_tells_an_anonymous_caller_they_never_opted_in() -> None:
	"""`logged=False` is reached by two opposite facts, and this route serves both.

	`/surveillance/geofences-at` is open and passes no subject, so an anonymous caller reaches the
	same branch as a person who switched alerts off — and the single sentence that used to sit there
	told them "Alerts are off", which is a setting they do not have. Naming a choice nobody made is
	the same defect as naming a transmission nobody performed: the sentence asserts something the
	boolean does not establish. All three states are asserted together so a future edit that
	collapses two of them fails here rather than in the field.
	"""
	svc = _svc(_fence('G1', label='Kasese market', county='Busia'))
	svc.set_zone_alerts('U-1', False)
	svc.set_zone_alerts('U-2', True)
	anonymous = svc.zones_at(*INSIDE)[0]
	off = svc.zones_at(*INSIDE, subject_ref='U-1')[0]
	on = svc.zones_at(*INSIDE, subject_ref='U-2')[0]
	assert (anonymous.logged, off.logged, on.logged) == (False, False, True)
	assert anonymous.privacy_note == zone_privacy_note('en', False, anonymous=True)
	assert len({anonymous.privacy_note, off.privacy_note, on.privacy_note}) == 3, (
		'the three states are three sentences: two of them are a choice and one is the absence of one'
	)
	assert 'Alerts are off' not in anonymous.privacy_note, (
		'an open route may not tell a caller about a switch they never touched'
	)
	assert 'not signed in' in anonymous.privacy_note
	# Swahili carries the same split rather than falling back to one sentence for both.
	assert zone_privacy_note('sw', False, anonymous=True) != zone_privacy_note('sw', False)


def test_the_event_carries_the_21_day_window_it_names() -> None:
	"""The sentence says "21 days" and the client has to schedule against the same number. A second
	copy typed into the client is one that drifts from the string, so the window is a field."""
	assert _svc(_fence('G1')).zones_at(*INSIDE)[0].symptom_watch_days == 21


def test_an_event_refuses_an_unknown_direction() -> None:
	"""`entry` and `exit` are the two the section names, and a third would be a client rendering a
	sentence nobody wrote."""
	from pydantic import ValidationError
	with pytest.raises(ValidationError):
		ZoneEvent.model_validate({'event': 'passing', 'geofence_id': 'G1', 'risk_type': 'general',
		                          'alert_level': 'low', 'alert': 'a', 'message': 'b', 'logged': False})


def test_a_deployment_with_no_zone_registry_has_no_zones() -> None:
	"""Not an error: a deployment with no surveillance wired has no zones to be in, and inventing an
	empty registry would be a second copy of §11.1's state. The second case is the one that matters —
	a service constructed with no collaborator at all, which is what a unit test or a partial
	deployment does."""
	assert _svc().zones_at(*INSIDE) == []
	assert LocationService().zones_at(*INSIDE) == []
	assert LocationService().zones_at(*INSIDE) == [] and _svc(_fence('G1')).zones_at(*OUTSIDE) == []


# --- layering ---------------------------------------------------------------------------------------

def test_the_surveillance_module_does_not_reach_into_location() -> None:
	"""`afya.location.service` imports `afya.surveillance.views.Geofence` at runtime — a Protocol
	method's annotation is evaluated when the class object is created, so a `TYPE_CHECKING` guard
	would not do. That is only safe while the edge runs one way."""
	tree = ast.parse((ROOT / 'src/afya/surveillance/service.py').read_text())
	imported: set[str] = set()
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			imported |= {a.name for a in node.names}
		elif isinstance(node, ast.ImportFrom) and node.module:
			imported.add(node.module)
	assert not [m for m in imported if m.startswith('afya.location')], (
		f'afya.surveillance.service imports afya.location: {sorted(imported)}')


# --- the front door ---------------------------------------------------------------------------------

async def test_the_zone_route_serves_entry_and_exit_through_the_deployment(tmp_path) -> None:
	"""The service tests above construct the collaborators by hand; this one proves the *deployment*
	wires the zone registry into `LocationService` and that the two switches are reachable. A unit
	test that builds the service itself proves the call and nothing about `build_services`."""
	app = create_app(build_services(db_path=str(tmp_path / 'afya.db')))
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers, subject = await _citizen(c)
		county = await _county_officer(c)
		fence = await c.post('/surveillance/geofence', headers=county, json={
			'geofence_id': 'G1', 'lat': INSIDE[0], 'lon': INSIDE[1], 'radius_m': 5_000,
			'risk_type': 'outbreak', 'alert_level': 'high',
			'place_label': 'Kasese market', 'county': 'Busia'})
		assert fence.status_code == 200, fence.text

		off = await c.get('/surveillance/geofences-at', params={'lat': INSIDE[0], 'lon': INSIDE[1]})
		assert off.status_code == 200, off.text
		events = off.json()
		assert [e['event'] for e in events] == ['entry']
		assert 'Avoid Kasese market.' in events[0]['alert']
		assert events[0]['logged'] is False, 'an open route recorded a crossing'

		on = await c.post(f'/location/zone-alerts/{subject}', headers=headers, json={'enabled': True})
		assert on.status_code == 200, on.text
		assert on.json()['alerts_enabled'] is True

		tracked = await c.get(f'/location/zones/{subject}', headers=headers, params={
			'lat': INSIDE[0], 'lon': INSIDE[1]})
		assert tracked.status_code == 200, tracked.text
		assert tracked.json()[0]['logged'] is True
		assert (await c.get(f'/location/zone-alerts/{subject}', headers=headers)).json()['inside'] == ['G1']


async def test_a_token_may_not_set_another_persons_zone_alerts(tmp_path) -> None:
	"""The switch is a consent decision, so a route that read `subject_ref` from the path without
	comparing it to the token would let anyone enable logging on anyone — the scope check passes for
	every citizen while the subject is whoever the caller typed."""
	app = create_app(build_services(db_path=str(tmp_path / 'afya.db')))
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers, _mine = await _citizen(c)
		_, theirs = await _citizen(c)
		for method, kwargs in (('get', {}), ('post', {'params': {'enabled': True}})):
			call = getattr(c, method)
			resp = await call(f'/location/zone-alerts/{theirs}', headers=headers, **kwargs)
			assert resp.status_code == 403, f'{method}: {resp.status_code} {resp.text}'


async def test_the_zone_routes_serve_no_spec_feature_code(tmp_path) -> None:
	"""§3.3 principle 9: a spec id is an internal handle. The alert is a sentence a person reads on
	a phone at the edge of a zone, which is the surface where a code would do the most damage."""
	app = create_app(build_services(db_path=str(tmp_path / 'afya.db')))
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers, subject = await _citizen(c)
		await c.post('/surveillance/geofence', headers=await _county_officer(c), json={
			'geofence_id': 'G1', 'lat': INSIDE[0], 'lon': INSIDE[1], 'radius_m': 5_000,
			'risk_type': 'outbreak', 'alert_level': 'high', 'place_label': 'Kasese market',
			'county': 'Busia'})
		bodies = [
			(await c.get(f'/location/zones/{subject}', headers=headers, params={
				'lat': INSIDE[0], 'lon': INSIDE[1]})).text,
			(await c.get('/surveillance/geofences-at', params={
				'lat': INSIDE[0], 'lon': INSIDE[1]})).text,
			(await c.get(f'/location/zone-alerts/{subject}', headers=headers)).text,
			(await c.post(f'/location/zone-alerts/{subject}', headers=headers,
			              params={'enabled': False})).text,
			(await c.get('/mobile/actions')).text,
		]
		for body in bodies:
			assert not FEATURE_CODE.search(body), body
