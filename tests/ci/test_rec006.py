"""§REC-006 — blood donor matching, and the two Features that had no carrier.

The section prints five Features and three had carriers. The two that did not failed from opposite
sides of the same table:

- **"Receive alerts when your blood type is urgently needed nearby"** — `BloodService.match` was
  fully implemented and answers the *requester's* question: who can I call, ranked. Nobody answered
  the *donor's* question, which is what the bullet is about — my group is needed, here. So the
  request's own `urgency` field was carried and read by nobody, and a donor could be a perfect match
  for a critical request in their own county and never learn of it.
- **"Find donation centres"** — `PlaceKind` had eight members and none of them was a donation
  centre, so no route could list one. The vocabulary is not invented: OpenStreetMap documents both
  kinds, and documents them as *different things* — `healthcare=blood_donation` is a site where a
  person gives blood, `healthcare=blood_bank` is where donated blood is stored. A finder that
  collapsed the two would put a storage site in a donor's results and call it a place to give blood.
  Both definitions are archived at `sources/osm-healthcare-tags/`.

The gates below are canaried against a planted defect in `canary_rec006.py`.
"""
import httpx
import pytest

from afya.blood.views import (
	DONATION_SITE_KINDS, URGENCY_DEPTH, URGENCY_REACH, BloodRequest, BloodService, Donor,
)
from afya.integrations.overpass import overpass_query, parse_overpass
from afya.places.views import Place, PlaceKind, PlacesService
from afya.service import build_services, create_app

TODAY = '2026-10-08'

# A five-county world in a line: Nairobi — Kiambu — Nakuru — Kisumu — Siaya. Kiambu is one hop from
# Nairobi and Nakuru is two, so a critical request that reaches two hops is *not* the same set as an
# urgent one that reaches one — which a two-county world cannot show. The real table is 47 counties
# with 113 pairs, which the §INF-001 gate derives separately; this file does not restate it.
ADJACENCY = {
	'Nairobi': ('Kiambu',), 'Kiambu': ('Nairobi', 'Nakuru'), 'Nakuru': ('Kiambu', 'Kisumu'),
	'Kisumu': ('Nakuru', 'Siaya'), 'Siaya': ('Kisumu',),
}


async def _donors(*rows: tuple[str, str, str]) -> BloodService:
	svc = BloodService()
	for ref, group, county in rows:
		await svc.register(Donor(donor_ref=ref, blood_group=group, county=county))
	return svc


def _req(group: str = 'B+', county: str = 'Nairobi', urgency: str = 'critical') -> BloodRequest:
	return BloodRequest(request_id='R1', blood_group=group, county=county, urgency=urgency)


def _place(osm_id: str, kind: PlaceKind, name: str, lat: float, lon: float, county: str) -> Place:
	return Place(osm_id=osm_id, kind=kind, name=name, lat=lat, lon=lon, county=county)


# --- "Receive alerts when your blood type is urgently needed nearby" -----------------------------

async def test_a_donor_whose_group_the_request_names_is_alerted_first_and_knows_which_group() -> None:
	"""The bullet's own three words, as three fields: *your blood type*, *needed*, *nearby*.

	A B+ patient can be given O- blood, so most alerts go to a donor whose group is not the one on
	the request. That is exactly why the alert carries both: "B+ is needed" and "your O- can be
	given to a B+ patient" are different sentences, and a donor told only the first has to work out
	whether it applies to them.
	"""
	svc = BloodService()
	await svc.register(Donor(donor_ref='D-BPOS', blood_group='B+', county='Nairobi'))
	await svc.register(Donor(donor_ref='D-ONEG', blood_group='O-', county='Nairobi'))
	alerts = svc.donor_alerts(_req('B+', 'Nairobi', 'critical'), TODAY, ADJACENCY)
	by_ref = {a.donor_ref: a for a in alerts}
	assert set(by_ref) == {'D-BPOS', 'D-ONEG'}
	assert by_ref['D-BPOS'].requested_group == 'B+' and by_ref['D-BPOS'].donor_group == 'B+'
	assert by_ref['D-ONEG'].requested_group == 'B+' and by_ref['D-ONEG'].donor_group == 'O-'
	assert by_ref['D-BPOS'].message.startswith('Critical need for B+ blood in your county.')
	assert 'O-' in by_ref['D-ONEG'].message and 'B+' in by_ref['D-ONEG'].message


async def test_urgency_decides_the_reach_and_a_routine_request_does_not_wake_a_neighbour() -> None:
	"""The request's own `urgency` field, which was carried and read by nobody.

	Three behaviours, each of which a filter would get wrong:

	* A `routine` request notifies the exact group in its own county and nobody else. A routine need
	  is met from the stock list, and waking donors for it spends their goodwill for nothing. The
	  Kiambu B+ donor is the one that makes this an assertion about *reach* rather than about
	  *depth*: with no exact-group donor next door, widening the reach alone would change nothing and
	  the table's first row would go untested.
	* An `urgent` request reaches the compatible groups in the county and the counties that touch it.
	* A `critical` request reaches two hops out — Nakuru, which does not touch Nairobi — and that is
	  what makes `URGENCY_REACH`'s top row a decision rather than a duplicate of the middle one. A
	  county hospital short of B+ calls Kiambu because a donor an hour away is a donor; it calls
	  Nakuru because a donor three hours away still beats no unit at all.
	"""
	svc = await _donors(('D-NBO-B', 'B+', 'Nairobi'), ('D-NBO-O', 'O+', 'Nairobi'),
	                    ('D-KIA-O', 'O-', 'Kiambu'), ('D-KIA-B', 'B+', 'Kiambu'),
	                    ('D-NAK-O', 'O-', 'Nakuru'), ('D-KSI-O', 'O-', 'Kisumu'))

	routine = svc.donor_alerts(_req('B+', 'Nairobi', 'routine'), TODAY, ADJACENCY)
	assert [a.donor_ref for a in routine] == ['D-NBO-B'], 'routine reached beyond its own county'

	urgent = svc.donor_alerts(_req('B+', 'Nairobi', 'urgent'), TODAY, ADJACENCY)
	assert {a.donor_ref for a in urgent} == {'D-NBO-B', 'D-NBO-O', 'D-KIA-O', 'D-KIA-B'}, (
		'urgent must reach the compatible groups in the county and the counties that touch it')
	assert {a.distance_counties for a in urgent} == {0, 1}
	away = next(a for a in urgent if a.donor_ref == 'D-KIA-O')
	assert away.county == 'Kiambu' and '1 county from Nairobi' in away.message

	critical = svc.donor_alerts(_req('B+', 'Nairobi', 'critical'), TODAY, ADJACENCY)
	assert {a.donor_ref for a in critical} == {a.donor_ref for a in urgent} | {'D-NAK-O'}, (
		'critical must add the county two hops out and stop there: Kisumu is three')
	assert next(a for a in critical if a.donor_ref == 'D-NAK-O').distance_counties == 2
	assert '2 counties from Nairobi' in next(a for a in critical if a.donor_ref == 'D-NAK-O').message


async def test_a_donor_inside_the_90_day_window_is_not_invited_to_donate() -> None:
	"""The interval is a rule about the donor, and an alert is an invitation to break it.

	`_eligible` is the same function `match` and `record_donation` use, so a donor cannot be
	eligible to one caller and ineligible to another — the failure this rules out is a donor who
	recently gave blood being woken by an alert that the eligibility tracker would have suppressed.
	"""
	svc = await _donors(('D-FRESH', 'O-', 'Nairobi'), ('D-RECENT', 'O-', 'Nairobi'))
	await svc.record_donation('D-RECENT', '2026-10-01')  # seven days ago, interval is 90
	alerts = svc.donor_alerts(_req('O-', 'Nairobi', 'critical'), TODAY, ADJACENCY)
	assert [a.donor_ref for a in alerts] == ['D-FRESH']
	assert svc._eligible(svc._donors['D-RECENT'], TODAY) is False  # noqa: SLF001 - the shared rule


async def test_a_donor_whose_group_cannot_be_given_to_the_patient_is_not_alerted() -> None:
	"""Compatibility is not a filter on the county, and the dangerous direction is the wrong one.

	An A+ donor cannot give to a B+ patient. An alert that reached them anyway would bring a donor
	to a facility to be turned away, which is worse than not calling: it spends the one thing a
	donor list runs on.
	"""
	svc = await _donors(('D-APOS', 'A+', 'Nairobi'), ('D-ABPOS', 'AB+', 'Nairobi'))
	assert svc.donor_alerts(_req('B+', 'Nairobi', 'critical'), TODAY, ADJACENCY) == []
	assert {a.donor_ref for a in svc.donor_alerts(_req('AB+', 'Nairobi', 'critical'), TODAY, ADJACENCY)} \
		== {'D-APOS', 'D-ABPOS'}, 'AB+ takes every group, so both are reachable'


def test_the_reach_table_covers_every_urgency_the_request_model_accepts() -> None:
	"""`BloodRequest.urgency` is `routine|urgent|critical` and the table must have a row for each.

	A missing row would raise on the one request whose urgency nobody tested, and the model's own
	pattern is what fixes the set. The reach values must also be **three distinct numbers**: a table
	whose top two rows agreed would be a field that decides nothing, which is the defect this whole
	bullet was — `urgency` was carried on the request and read by nobody.
	"""
	assert set(URGENCY_REACH) == {'routine', 'urgent', 'critical'}
	assert set(URGENCY_DEPTH) == set(URGENCY_REACH)
	assert URGENCY_REACH['routine'] == 0, 'a routine request must not reach a neighbouring county'
	assert URGENCY_DEPTH['routine'] == 0, 'a routine request must not reach a compatible group'
	assert len(set(URGENCY_REACH.values())) == 3, (
		f'each urgency must reach a different distance, or the field decides nothing: {URGENCY_REACH}')


# --- "Find donation centres" ---------------------------------------------------------------------

def test_the_two_kinds_are_the_sources_own_and_are_not_synonyms() -> None:
	"""The distinction the finder turns on, taken from the source rather than invented.

	OpenStreetMap documents both, and defines them apart. If the two collapsed into one member the
	finder could not tell a donor where to give blood from where blood is kept, and the default —
	`blood_donation` — would be meaningless.
	"""
	assert set(DONATION_SITE_KINDS) == {'blood_donation', 'blood_bank'}
	assert PlaceKind('blood_donation') is PlaceKind.blood_donation
	assert PlaceKind('blood_bank') is PlaceKind.blood_bank
	assert 'give blood' in DONATION_SITE_KINDS['blood_donation']
	assert 'stored' in DONATION_SITE_KINDS['blood_bank']


def test_the_importer_reads_the_healthcare_key_and_not_only_the_amenity_key() -> None:
	"""The two OSM vocabularies are separate namespaces, and the donation tags are in the second.

	`amenity=blood_donation` is not a value OSM defines, so a query that looked only under `amenity`
	would return an empty set while appearing to work — and an importer that read only `amenity`
	would silently drop every donation site the query found. The query and the parser have to agree
	on the key, which is why both are asserted here.
	"""
	q = overpass_query(-1.5, 36.5, -1.0, 37.0)
	assert 'healthcare' in q and 'blood_donation' in q and 'blood_bank' in q, q
	payload = {'elements': [
		{'type': 'node', 'id': 1, 'lat': -1.29, 'lon': 36.82,
		 'tags': {'healthcare': 'blood_donation', 'name': 'Nairobi Blood Donation Centre'}},
		{'type': 'node', 'id': 2, 'lat': -1.30, 'lon': 36.83,
		 'tags': {'healthcare': 'blood_bank', 'name': 'KNH Blood Bank'}},
		{'type': 'node', 'id': 3, 'lat': -1.31, 'lon': 36.84,
		 'tags': {'amenity': 'pharmacy', 'name': 'Good Chemist'}},
	]}
	kinds = {p.name: p.kind for p in parse_overpass(payload)}
	assert kinds['Nairobi Blood Donation Centre'] is PlaceKind.blood_donation
	assert kinds['KNH Blood Bank'] is PlaceKind.blood_bank
	assert kinds['Good Chemist'] is PlaceKind.pharmacy, 'the amenity key must still be read'


async def test_the_finder_defaults_to_where_a_person_can_give_blood() -> None:
	"""The default is the answer to the question a donor is asking.

	A storage site is somewhere the blood already is, not somewhere a donor can go. Returning both
	by default would put a place a donor cannot use at the top of a distance-sorted list, and
	`blood_bank` is offered only when it is named.
	"""
	places = PlacesService()
	await places.upsert(_place('N1', PlaceKind.blood_donation, 'City Donation Centre', -1.286, 36.817, 'Nairobi'))
	await places.upsert(_place('N2', PlaceKind.blood_bank, 'National Blood Bank', -1.300, 36.800, 'Nairobi'))
	await places.upsert(_place('N3', PlaceKind.pharmacy, 'Good Chemist', -1.280, 36.810, 'Nairobi'))
	svc = BloodService()

	default = svc.donation_centres(places, -1.286, 36.817)
	assert [c.place_id for c in default] == ['N1'], 'the default must not include a storage site'
	assert default[0].label == DONATION_SITE_KINDS['blood_donation']
	assert default[0].distance_km >= 0

	both = svc.donation_centres(places, -1.286, 36.817, kinds=('blood_donation', 'blood_bank'))
	assert {c.place_id for c in both} == {'N1', 'N2'}
	assert {c.kind for c in both} == {'blood_donation', 'blood_bank'}
	assert len({c.label for c in both}) == 2, 'the two kinds must not be presented as one'

	with pytest.raises(AssertionError):
		svc.donation_centres(places, -1.286, 36.817, kinds=('clinic',))

	assert svc.donation_centres(PlacesService(), -1.286, 36.817) == [], (
		'a deployment whose import has not run has no answer, and an empty list is that answer')


# --- the front door ------------------------------------------------------------------------------

async def _token(c: httpx.AsyncClient, subject: str = 'U1') -> dict[str, str]:
	tok = (await c.post('/auth/anonymous', json={'subject_ref': subject})).json()['token']
	return {'Authorization': f'Bearer {tok}'}


async def test_the_routes_serve_the_alerts_and_the_centres() -> None:
	"""Both features present in the service and reachable at the front door.

	`/blood/alerts` is the one that matters: `match` already had a route, so a green test over the
	service would pass while the bullet had no route at all. The centre route is served for a
	county with nothing imported, and answers with an empty list rather than raising — a finder that
	500s where there is no data is a screen that blames the person.
	"""
	svc = build_services()
	app = create_app(svc)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		h = await _token(c)
		# The donor list is personal data, so enrolment and every read of it carry the caller's own
		# token: `self` scope is what makes the row theirs rather than a public register.
		for ref, group, county in (('D1', 'O-', 'Nairobi'), ('D2', 'B+', 'Nairobi'),
		                           ('D3', 'A+', 'Nairobi'), ('D4', 'O-', 'Kiambu')):
			assert (await c.post('/blood/donors', json={
				'donor_ref': ref, 'blood_group': group, 'county': county}, headers=h)).status_code == 200

		alerts = await c.post('/blood/alerts', json={
			'request_id': 'R1', 'blood_group': 'B+', 'county': 'Nairobi', 'urgency': 'critical'}, headers=h)
		assert alerts.status_code == 200, alerts.text
		refs = {a['donor_ref'] for a in alerts.json()}
		assert refs == {'D1', 'D2', 'D4'}, (
			f'A+ cannot be given to a B+ patient, and the critical request must reach Kiambu: {alerts.json()}')
		away = next(a for a in alerts.json() if a['donor_ref'] == 'D4')
		assert away['distance_counties'] == 1 and away['county'] == 'Kiambu', away
		assert all(a['request_id'] == 'R1' and a['urgency'] == 'critical' for a in alerts.json())
		assert all('B+' in a['message'] for a in alerts.json())

		# A routine request in the same county reaches the exact group and nobody else.
		routine = await c.post('/blood/alerts', json={
			'request_id': 'R2', 'blood_group': 'B+', 'county': 'Nairobi', 'urgency': 'routine'}, headers=h)
		assert [a['donor_ref'] for a in routine.json()] == ['D2'], (
			'a routine need is met from the stock list; it must not wake the O- donor')

		centres = await c.get('/blood/donation-centres', params={'lat': -1.286, 'lon': 36.817}, headers=h)
		assert centres.status_code == 200, centres.text
		assert centres.json() == [], 'a county with nothing imported answers with nothing'

		bad = await c.get('/blood/donation-centres',
		                  params={'lat': -1.286, 'lon': 36.817, 'kind': 'clinic'}, headers=h)
		assert bad.status_code == 422, 'a kind that is not a donation site must be refused'


async def test_no_spec_feature_code_reaches_anything_a_donor_reads() -> None:
	"""The alert message and the centre label are read by a person, and carry no internal id."""
	import re
	code = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')

	svc = await _donors(('D1', 'O-', 'Nairobi'), ('D2', 'B+', 'Kiambu'))
	places = PlacesService()
	await places.upsert(_place('N1', PlaceKind.blood_donation, 'City Donation Centre',
	                           -1.286, 36.817, 'Nairobi'))
	strings = [a.message for a in svc.donor_alerts(_req('B+', 'Nairobi', 'critical'), TODAY, ADJACENCY)]
	strings += [c.label for c in BloodService().donation_centres(places, -1.286, 36.817)]
	assert strings, 'a vacuous check over nothing reads as a pass'
	for s in strings:
		assert not code.search(s), s
