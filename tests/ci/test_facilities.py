import pytest

from afya.facilities.service import FacilityService, haversine_km
from afya.facilities.views import (
	CostBand, Facility, FacilityKind, FacilityLevel, NearestRequest, ServiceOffered,
)
from afya.places.views import PlacesService


async def test_haversine_nairobi_machakos() -> None:
	d = haversine_km(-1.2833, 36.8167, -1.5167, 37.2667)
	assert 55 <= d <= 75


async def test_nearest_orders_and_filters() -> None:
	svc = FacilityService()
	await svc.upsert(Facility(facility_id='F1', name='KNH', kind=FacilityKind.ed, county='Nairobi', lat=-1.3, lon=36.8))
	await svc.upsert(Facility(facility_id='F2', name='Kisumu ED', kind=FacilityKind.ed, county='Kisumu', lat=-0.1, lon=34.75))
	await svc.upsert(Facility(facility_id='F3', name='Kilimani Pharmacy', kind=FacilityKind.pharmacy, county='Nairobi', lat=-1.29, lon=36.78))
	ranked = svc.nearest(NearestRequest(lat=-1.29, lon=36.8, kind=FacilityKind.ed))
	ranked = svc.nearest(NearestRequest(lat=-1.29, lon=36.8, kind=FacilityKind.ed, limit=1))
	assert [p[0].facility_id for p in ranked] == ['F1']
	mixed = svc.nearest(NearestRequest(lat=-1.29, lon=36.8, limit=2))
	assert [p[0].facility_id for p in mixed] == ['F1', 'F3']


async def test_ed_status_requires_ed_kind() -> None:
	svc = FacilityService()
	await svc.upsert(Facility(facility_id='F1', name='Pharmacy', kind=FacilityKind.pharmacy, county='X', lat=-1, lon=36))
	with pytest.raises(AssertionError):
		svc.ed_status('F1')


async def test_mohf_ingest_skips_invalid_rows() -> None:
	svc = FacilityService()
	rows = [
		{'facility_id': 'F1', 'name': 'KNH', 'kind': 'ed', 'county': 'Nairobi', 'lat': -1.3, 'lon': 36.8},
		{'facility_id': 'F9', 'name': 'broken', 'kind': 'not_a_kind', 'county': 'X', 'lat': 0.0, 'lon': 36.0},
		{'name': 'missing id'},
	]
	assert await svc.ingest_mohf(rows) == 1
	assert len(svc.nearest(NearestRequest(lat=-1.29, lon=36.8, limit=5))) == 1


async def test_booking_queue_monotonic() -> None:
	svc = FacilityService()
	await svc.upsert(Facility(facility_id='F1', name='A', kind=FacilityKind.ed, county='X', lat=-1, lon=36))
	b1 = await svc.book('F1', '2026-10-08T10:00+03:00', 'BOOK-A1B2C3D4')
	b2 = await svc.book('F1', '2026-10-08T10:30+03:00', 'BOOK-B2C3D4E5')
	assert b2.queue_position == b1.queue_position + 1

# --- §FND-001's finder, §FND-002's capacity screen, §FND-004's SHA field -------------------------

def _seed_pool() -> FacilityService:
	"""Four facilities spanning §FND-001's ladder, services and cost bands."""
	svc = FacilityService()
	for f in (
		Facility(facility_id='F1', name='Kayole Dispensary', kind=FacilityKind.treatment_unit,
			county='Nairobi', lat=-1.28, lon=36.90, level=FacilityLevel.dispensary,
			services=[ServiceOffered.maternal, ServiceOffered.child], accepts_sha=True,
			cost_band=CostBand.free),
		Facility(facility_id='F2', name='Mama Lucy Hospital', kind=FacilityKind.treatment_unit,
			county='Nairobi', lat=-1.29, lon=36.88, level=FacilityLevel.sub_county_hospital,
			services=[ServiceOffered.maternal, ServiceOffered.emergency], accepts_sha=True,
			cost_band=CostBand.low, icu_beds=4, ambulances=2, trauma_capable=True,
			isolation_beds=3, ebola_screening=True),
		Facility(facility_id='F3', name='KNH', kind=FacilityKind.treatment_unit,
			county='Nairobi', lat=-1.30, lon=36.81, level=FacilityLevel.national_referral,
			services=[ServiceOffered.emergency, ServiceOffered.isolation_capacity],
			accepts_sha=False, cost_band=CostBand.high, icu_beds=40, ambulances=6,
			trauma_capable=True, isolation_beds=20),
		Facility(facility_id='F4', name='Kisumu Clinic', kind=FacilityKind.treatment_unit,
			county='Kisumu', lat=-0.10, lon=34.75, level=FacilityLevel.health_centre,
			services=[ServiceOffered.malaria], cost_band=CostBand.low),
	):
		svc._facilities[f.facility_id] = f
	return svc


async def test_the_finder_filters_by_the_four_dimensions_the_section_prints() -> None:
	"""§FND-001's Features: "Search by area name or code" and "Filter by service, level, cost, SHA
	acceptance". Each narrows the pool, and the section's own four compose — a request can ask for
	a referral-level hospital that takes SHA and offers maternity."""
	svc = _seed_pool()
	req = lambda **kw: NearestRequest(lat=-1.29, lon=36.88, limit=10, **kw)  # noqa: E731
	assert [f.facility_id for f, _ in svc.find(req())[0]] == ['F2', 'F1', 'F3', 'F4'], \
		'nearest first, with no radius unless one is asked for'

	by_service, _ = svc.find(req(service=ServiceOffered.emergency))
	assert {f.facility_id for f, _ in by_service} == {'F2', 'F3'}

	by_level, _ = svc.find(req(level=FacilityLevel.national_referral))
	assert [f.facility_id for f, _ in by_level] == ['F3']

	by_cost, _ = svc.find(req(max_cost_band=CostBand.free))
	assert [f.facility_id for f, _ in by_cost] == ['F1'], 'free is the cheapest band, not "under high"'

	by_sha, _ = svc.find(req(accepts_sha=True))
	assert {f.facility_id for f, _ in by_sha} == {'F1', 'F2', 'F4'}, \
		'F3 refuses SHA and is dropped; F4 has not filed it, which is not a refusal'

	composed, _ = svc.find(req(service=ServiceOffered.maternal, accepts_sha=True))
	assert {f.facility_id for f, _ in composed} == {'F1', 'F2'}


async def test_the_search_box_matches_name_county_or_code() -> None:
	"""§FND-001's "Search by area name or code" is one box, so it matches the three things a person
	types into it: the facility's name, its county, or the MoHF code off a card."""
	svc = _seed_pool()
	for query, expected in (('kayole', {'F1'}), ('nairobi', {'F1', 'F2', 'F3'}), ('f2', {'F2'})):
		found, _ = svc.find(NearestRequest(lat=-1.29, lon=36.88, limit=10, query=query))
		assert {f.facility_id for f, _ in found} == expected, query


async def test_a_filter_nothing_published_is_reported_rather_than_applied() -> None:
	"""A pool where nobody filed a cost band must not answer "no facility is affordable" — that
	turns "the county has not filed the row" into a finding about the facilities. The dimension is
	named instead, the same contract `/places/find` keeps."""
	svc = FacilityService()
	svc._facilities['F1'] = Facility(facility_id='F1', name='A', kind=FacilityKind.treatment_unit,
		county='Nairobi', lat=-1.28, lon=36.90)
	found, unanswered = svc.find(NearestRequest(lat=-1.28, lon=36.90, max_cost_band=CostBand.free))
	assert 'cost' in unanswered
	assert len(found) == 1, 'the facility is not dropped for a field nobody published'


async def test_an_unfiled_sha_row_stays_in_a_sha_filtered_list() -> None:
	"""The tri-state the section's own wording asks for: "critical for cost anxiety" is a person
	deciding whether they can afford care, and either default misleads them."""
	svc = _seed_pool()
	found, _ = svc.find(NearestRequest(lat=-1.29, lon=36.88, limit=10, accepts_sha=True))
	ids = {f.facility_id for f, _ in found}
	assert 'F4' in ids, 'Kisumu Clinic has not filed it, which is not a refusal'
	assert 'F3' not in ids, 'KNH refuses it, which is an answer'


async def test_the_emergency_screen_filters_on_capacity_and_excludes_on_absence() -> None:
	"""§FND-002's five Features are capacity questions, and these *do* exclude on absence: a person
	looking for an ICU bed needs a yes, so a facility whose bed count nobody filed cannot provide
	one. That is the opposite of the cost/SHA rule above, and the difference is the section's."""
	svc = _seed_pool()
	req = lambda **kw: NearestRequest(lat=-1.29, lon=36.88, limit=10, **kw)  # noqa: E731
	icu, _ = svc.find(req(min_icu_beds=10))
	assert [f.facility_id for f, _ in icu] == ['F3'], 'only KNH has ten or more, and F1/F4 filed none'

	amb, _ = svc.find(req(needs_ambulance=True))
	assert {f.facility_id for f, _ in amb} == {'F2', 'F3'}

	trauma, _ = svc.find(req(needs_trauma=True))
	assert {f.facility_id for f, _ in trauma} == {'F2', 'F3'}

	iso, _ = svc.find(req(needs_isolation=True))
	assert {f.facility_id for f, _ in iso} == {'F2', 'F3'}


async def test_the_offline_bundle_is_the_radius_plus_the_home_county() -> None:
	"""§FND-001's Offline: "caches facilities within 50 km of the user's home area", with the
	section's own note adding "Full offline bundle for user's home county available on first sync".
	Both clauses are the bundle, because a person near a county border has facilities in their own
	county farther than 50 km that the bundle still owes them."""
	svc = _seed_pool()
	near = svc.offline_bundle(-1.29, 36.88)
	assert {r.facility.facility_id for r in near} == {'F1', 'F2', 'F3'}, 'F4 is 300 km away'

	with_county = svc.offline_bundle(-1.29, 36.88, home_county='Kisumu')
	assert {r.facility.facility_id for r in with_county} == {'F1', 'F2', 'F3', 'F4'}
	assert [r.km for r in with_county] == sorted(r.km for r in with_county), 'nearest first'


async def test_recent_user_reports_are_a_capped_feed_newest_first() -> None:
	"""§FND-001's "Recent user reports ('no malaria tests today,' 'long queue')". The section shows
	them as a feed, so the newest is first and the list is capped — it renders on a screen anyone
	can open, and an uncapped feed is one nobody can read.

	The reporter is a §SEC-004 handle when an identity model is wired and `None` when it is not; it
	is never the reference the caller passed. That is asserted in `test_sec004.py`, and here only the
	feed's own shape is — this service is built without an identity model, so a named reporter is
	published anonymously rather than leaked.
	"""
	from afya.facilities.service import _MAX_REPORTS
	svc = _seed_pool()
	await svc.report('F1', 'no malaria tests today')
	await svc.report('F1', 'long queue', reporter_ref='U-abc')
	feed = svc.recent_reports('F1')
	assert [r.text for r in feed] == ['long queue', 'no malaria tests today']
	assert feed[0].reporter_ref != 'U-abc', 'a subject reference is never the published reporter'
	assert feed[1].reporter_ref is None
	for i in range(_MAX_REPORTS + 5):
		await svc.report('F1', f'report {i}')
	assert len(svc.recent_reports('F1', limit=999)) == _MAX_REPORTS, 'the feed is capped'
	with pytest.raises(AssertionError):
		await svc.report('NOPE', 'ghost facility')


async def test_a_report_on_an_unknown_facility_is_refused() -> None:
	"""The feed hangs off a facility, so a report against an id nobody registered would be stored
	where no screen reads it."""
	svc = _seed_pool()
	with pytest.raises(AssertionError):
		await svc.report('F9', 'no such place')


async def test_the_routes_serve_the_filters_the_bundle_and_the_reports() -> None:
	"""The routes are where §FND-001's gaps were: a client could ask for the nearest facility and
	nothing else, so the section's four filters, its offline cache and its user-report feed had no
	endpoint to reach them through. A capability with no route is a capability nobody can use."""
	import httpx
	from afya.service import build_services, create_app
	services = build_services()
	app = create_app(services)
	svc: FacilityService = services['facilities']  # type: ignore[assignment]
	svc._facilities.update(_seed_pool()._facilities)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		body = (await c.post('/facilities/find', json={
			'lat': -1.29, 'lon': 36.88, 'limit': 10, 'service': 'emergency'})).json()
		assert {r['facility']['facility_id'] for r in body['results']} == {'F2', 'F3'}
		assert body['unanswered'] == []

		body = (await c.post('/facilities/find', json={
			'lat': -1.29, 'lon': 36.88, 'level': 'national_referral'})).json()
		assert [r['facility']['facility_id'] for r in body['results']] == ['F3']

		# A filter nothing in the pool published is named, not applied. This pool is one facility
		# whose county filed no cost band, which is the ordinary state of a registry mid-import.
		svc._facilities.clear()
		svc._facilities['F9'] = Facility(facility_id='F9', name='Unfiled Clinic',
			kind=FacilityKind.treatment_unit, county='Nairobi', lat=-1.28, lon=36.90)
		body = (await c.post('/facilities/find', json={
			'lat': -1.29, 'lon': 36.88, 'max_cost_band': 'free'})).json()
		assert body['unanswered'] == ['cost'], 'nobody published a cost band for this pool'
		assert len(body['results']) == 1, 'and the facility is not dropped for it'

		svc._facilities.clear()
		svc._facilities.update(_seed_pool()._facilities)
		body = (await c.get('/facilities/offline-bundle?lat=-1.29&lon=36.88')).json()
		assert {r['facility']['facility_id'] for r in body} == {'F1', 'F2', 'F3'}

		posted = await c.post('/facilities/F1/reports', json={'text': 'no malaria tests today'})
		assert posted.status_code == 200, posted.text
		feed = (await c.get('/facilities/F1/reports')).json()
		assert [r['text'] for r in feed] == ['no malaria tests today']
		assert (await c.post('/facilities/NOPE/reports', json={'text': 'x'})).status_code == 404


async def test_the_pharmacy_route_carries_the_sections_own_filters() -> None:
	"""§FND-004 is a finder, not just a field: "Open now", "Whether they accept SHA" and distance are
	what the section prints, and the route serves all three over the pharmacy kind only."""
	import httpx
	from afya.places.views import Place, PlaceKind
	from afya.service import build_services, create_app
	services = build_services()
	app = create_app(services)
	places: PlacesService = services['places']  # type: ignore[assignment]
	await places.upsert(Place(osm_id='N1', kind=PlaceKind.pharmacy, name='Good Chemist',
		lat=-1.28, lon=36.90, opening_hours='Mon-Sat 08:00-20:00', accepts_sha=True))
	await places.upsert(Place(osm_id='N2', kind=PlaceKind.pharmacy, name='Night Chemist',
		lat=-1.285, lon=36.905, accepts_sha=False))
	await places.upsert(Place(osm_id='N3', kind=PlaceKind.clinic, name='Not A Chemist',
		lat=-1.286, lon=36.906, accepts_sha=True))
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		body = (await c.get('/places/pharmacies?lat=-1.29&lon=36.88')).json()
		assert {r['place']['osm_id'] for r in body['places']} == {'N1', 'N2'}, 'the clinic is not a chemist'
		body = (await c.get('/places/pharmacies?lat=-1.29&lon=36.88&accepts_sha=true')).json()
		assert [r['place']['osm_id'] for r in body['places']] == ['N1'], \
			'N2 refuses SHA and N3 is a clinic, so the chemist that takes it is the answer'
		body = (await c.get('/places/pharmacies?lat=-1.29&lon=36.88&open_now=true')).json()
		assert [r['place']['osm_id'] for r in body['places']] == ['N1'], 'N2 has no hours filed'
		assert 'directions' in body['places'][0]


def test_the_level_ladder_is_ordered_and_total() -> None:
	"""§FND-001 prints the five rungs in order — dispensary, health centre, sub-county hospital,
	county referral, national referral — and §FND-002's escalation ("nearest facility with ICU") is
	a question about going *up* the ladder. The rank table is asserted total so a member added to
	the enum without a rung fails here rather than sorting last."""
	from afya.facilities.service import _COST_RANK, _LEVEL_RANK
	assert set(_LEVEL_RANK) == set(FacilityLevel) and set(_COST_RANK) == set(CostBand)
	assert _LEVEL_RANK[FacilityLevel.dispensary] < _LEVEL_RANK[FacilityLevel.national_referral]
	assert _COST_RANK[CostBand.free] == 0, 'free is the floor, so `max_cost_band=free` keeps only it'
	assert len(FacilityLevel) == 5, 'the section prints five rungs'
