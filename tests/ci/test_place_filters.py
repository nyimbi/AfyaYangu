"""§FND-003's and §FND-005's filter dimensions, applied rather than declared.

Both sections' Features cells are filter lists — "Filter by test, cost, hours, results turnaround"
and "Filter by vaccine, age eligibility, cost (usually free), hours, whether walk-in or appointment"
— and `Place` is an OSM-normalised POI that carried none of them, so the finder routes took
`lat`/`lon`/`limit` and returned everything. A filter that is not applied is a screen that shows
every facility and calls the list filtered.

The second thing these tests pin is the distinction the fields are tri-state for: a facility with no
`tests` published is not one that does no tests, and a `0` default on `cost_kes` would answer "nobody
told us the price" as "this is free" on the screen someone uses to decide whether they can afford to
go.
"""
import httpx
import pytest
from pydantic import ValidationError

from afya.places.views import Place, PlaceKind, PlacesService, TestOffering, VaccineOffering

NAIROBI = (-1.2921, 36.8219)


def _service() -> PlacesService:
	svc = PlacesService()
	return svc


async def _seed(svc: PlacesService, places: list[Place]) -> None:
	for p in places:
		await svc.upsert(p)


async def test_the_test_finder_filters_by_the_dimensions_the_section_names() -> None:
	"""§FND-003. Four filters, and each one narrows the pool — the point being that the route can now
	answer "a malaria test under 500 shillings with results today" instead of returning every clinic
	in the county."""
	svc = _service()
	await _seed(svc, [
		Place(osm_id='N1', kind=PlaceKind.testing_site, name='Kayole Lab', lat=-1.28, lon=36.88,
			opening_hours='Mon-Sat 08:00-17:00',
			tests=[TestOffering(name='Malaria RDT', cost_kes=300, turnaround_hours=1),
				TestOffering(name='HIV', cost_kes=0, turnaround_hours=24)]),
		Place(osm_id='N2', kind=PlaceKind.testing_site, name='Eastleigh Lab', lat=-1.27, lon=36.85,
			tests=[TestOffering(name='General laboratory panels', cost_kes=2500, turnaround_hours=72)]),
		Place(osm_id='N3', kind=PlaceKind.testing_site, name='Unpriced Clinic', lat=-1.29, lon=36.82),
	])

	found, unanswered = svc.find(*NAIROBI, {PlaceKind.testing_site}, test='malaria')
	assert [p.name for p, _ in found] == ['Kayole Lab'] and unanswered == []

	found, _ = svc.find(*NAIROBI, {PlaceKind.testing_site}, max_cost_kes=500)
	assert {p.name for p, _ in found} == {'Kayole Lab', 'Unpriced Clinic'}, \
		'an unpriced place is not a place above the ceiling'

	found, _ = svc.find(*NAIROBI, {PlaceKind.testing_site}, max_turnaround_hours=2)
	assert [p.name for p, _ in found] == ['Kayole Lab']


async def test_a_dimension_nothing_published_is_reported_not_silently_filtered() -> None:
	"""The finding. Filtering a facility out because its row has no `tests` turns "nobody has filled
	this in" into "this clinic does not test for HIV" — a wrong answer on a health screen, arrived at
	by a filter that looks like it worked."""
	svc = _service()
	await _seed(svc, [Place(osm_id='N1', kind=PlaceKind.testing_site, name='Kayole Lab',
		lat=-1.28, lon=36.88)])

	found, unanswered = svc.find(*NAIROBI, {PlaceKind.testing_site}, test='malaria')
	assert unanswered == ['test'], 'the dimension is named'
	assert [p.name for p, _ in found] == ['Kayole Lab'], \
		'the place is still listed: nothing published is not nothing offered'

	found, unanswered = svc.find(*NAIROBI, {PlaceKind.testing_site},
		test='malaria', max_cost_kes=100, max_turnaround_hours=4)
	assert unanswered == ['test', 'results turnaround', 'cost'], 'each unanswerable dimension is named'


async def test_the_vaccination_finder_filters_by_age_and_walk_in() -> None:
	"""§FND-005. Age is in months so one band covers the infant schedule and school campaigns, and
	`walk_in_only` is the one filter that *does* exclude on absence — a person turning up without an
	appointment needs a yes, not a maybe."""
	svc = _service()
	await _seed(svc, [
		Place(osm_id='N1', kind=PlaceKind.vaccination_point, name='Kayole Health Centre',
			lat=-1.28, lon=36.88, opening_hours='Mon-Fri 08:00-16:00',
			vaccines=[VaccineOffering(name='Measles-Rubella', cost_kes=0,
				min_age_months=9, max_age_months=59, walk_in=True)]),
		Place(osm_id='N2', kind=PlaceKind.vaccination_point, name='Private Clinic',
			lat=-1.27, lon=36.85,
			vaccines=[VaccineOffering(name='HPV', cost_kes=4500, min_age_months=108,
				max_age_months=168, walk_in=False)]),
	])

	found, unanswered = svc.find(*NAIROBI, {PlaceKind.vaccination_point}, age_months=12)
	assert [p.name for p, _ in found] == ['Kayole Health Centre'] and unanswered == []
	found, _ = svc.find(*NAIROBI, {PlaceKind.vaccination_point}, age_months=140)
	assert [p.name for p, _ in found] == ['Private Clinic'], 'the band is inclusive'
	found, _ = svc.find(*NAIROBI, {PlaceKind.vaccination_point}, vaccine='hpv')
	assert [p.name for p, _ in found] == ['Private Clinic'], 'the name match is case-insensitive'
	found, _ = svc.find(*NAIROBI, {PlaceKind.vaccination_point}, walk_in_only=True)
	assert [p.name for p, _ in found] == ['Kayole Health Centre']
	found, _ = svc.find(*NAIROBI, {PlaceKind.vaccination_point}, max_cost_kes=0)
	assert [p.name for p, _ in found] == ['Kayole Health Centre'], 'free means zero'


def test_cost_and_walk_in_are_tri_state() -> None:
	"""The same rule `EmergencyCard.organ_donor` follows. `0` for "unknown" reads as "free" and
	`False` for "unknown" reads as "appointment only" — both send a person somewhere on a wrong
	assumption about money or about whether they will be seen."""
	offering = TestOffering(name='HIV')
	assert offering.cost_kes is None and offering.turnaround_hours is None
	assert VaccineOffering(name='Polio').walk_in is None
	assert VaccineOffering(name='Polio', cost_kes=0).cost_kes == 0, 'free is expressible, and it is 0'


def test_an_age_band_that_excludes_everyone_is_refused() -> None:
	"""A band with its bounds the wrong way round filters every child out and reports "no vaccination
	points near you" — a bug that reads as an answer."""
	with pytest.raises(ValidationError):
		VaccineOffering(name='Measles', min_age_months=60, max_age_months=9)


def test_an_empty_pool_is_an_empty_list_not_a_server_error() -> None:
	"""A locator whose OSM import has not run has no answer, and that is what the screen should say."""
	svc = _service()
	found, unanswered = svc.find(*NAIROBI, {PlaceKind.testing_site}, test='malaria')
	assert found == []
	assert unanswered == [], 'no pool at all is not a dimension the data failed to answer'


async def test_the_routes_serve_the_filters_and_the_unanswered_dimensions() -> None:
	"""The routes are where the finding was: they took `lat`/`lon`/`limit` and nothing else, so a
	client had no way to ask the question the section's Features cell describes."""
	from afya.service import build_services, create_app
	services = build_services()
	app = create_app(services)
	places: PlacesService = services['places']  # type: ignore[assignment]
	await _seed(places, [
		Place(osm_id='N1', kind=PlaceKind.testing_site, name='Kayole Lab', lat=-1.28, lon=36.88,
			tests=[TestOffering(name='Malaria RDT', cost_kes=300, turnaround_hours=1)]),
		Place(osm_id='N2', kind=PlaceKind.vaccination_point, name='Kayole Health Centre',
			lat=-1.28, lon=36.88,
			vaccines=[VaccineOffering(name='Measles-Rubella', cost_kes=0, walk_in=True)]),
	])
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		body = (await c.get('/places/testing-sites?lat=-1.29&lon=36.82&test=malaria')).json()
		assert [r['place']['name'] for r in body['places']] == ['Kayole Lab']
		assert body['unanswered'] == []
		body = (await c.get('/places/testing-sites?lat=-1.29&lon=36.82&max_cost_kes=100')).json()
		assert body['places'] == [], 'the lab costs 300, over the ceiling'
		body = (await c.get('/places/vaccination-points?lat=-1.29&lon=36.82&walk_in_only=true')).json()
		assert [r['place']['name'] for r in body['places']] == ['Kayole Health Centre']


# --- §FND-003's test types and §FND-004's SHA acceptance --------------------------------------

async def test_the_seven_test_types_are_a_closed_vocabulary() -> None:
	"""§FND-003 prints seven "Test types (context-dependent)" and `TestOffering.name` was free text,
	so the seven had no vocabulary behind them: a deployment that wrote "RDT" was offering a test
	the filter could not recognise, and the screen's filter chips could not be generated from the
	spec. The set is closed for the same reason `RED_FLAGS` is — an open string is a value nothing
	filters on and nothing can render."""
	from afya.places.views import TestType
	assert len(TestType) == 7, 'the section prints seven'
	assert {t.value for t in TestType} == {
		'malaria_rdt_microscopy', 'typhoid', 'hiv', 'tb', 'covid19', 'ebola', 'general_lab'}
	with pytest.raises(ValidationError):
		TestOffering(name='Malaria', test_type='malaria')  # type: ignore[arg-type]


async def test_the_test_type_filter_matches_the_closed_set_not_the_name() -> None:
	"""The section's filter is "Filter by test", and a person typing "RDT" and a chip generated from
	the spec are two different queries. `test_type` answers the second; `test` stays for the first."""
	from afya.places.views import TestType
	svc = _service()
	await _seed(svc, [
		Place(osm_id='N1', kind=PlaceKind.testing_site, name='Kayole Lab', lat=-1.28, lon=36.90,
			tests=[TestOffering(name='Malaria rapid test', test_type=TestType.malaria_rdt_microscopy)]),
		Place(osm_id='N2', kind=PlaceKind.testing_site, name='Buruburu Lab', lat=-1.29, lon=36.88,
			tests=[TestOffering(name='HIV screening', test_type=TestType.hiv)]),
	])
	found, unanswered = svc.find(*NAIROBI, {PlaceKind.testing_site}, test_type=TestType.hiv)
	assert [p.osm_id for p, _ in found] == ['N2'], 'the free-text name must not decide this'
	assert unanswered == []
	# The free-text search still works over the name, which is what a person types.
	found, _ = svc.find(*NAIROBI, {PlaceKind.testing_site}, test='rapid')
	assert [p.osm_id for p, _ in found] == ['N1']


async def test_a_test_type_nothing_published_is_reported_not_filtered() -> None:
	"""The tri-state contract, extended to the new dimension: a facility whose `tests` carry no
	`test_type` has not said it does no HIV tests, so the filter reports the dimension rather than
	dropping the facility from a list that then reads as an answer."""
	svc = _service()
	await _seed(svc, [Place(osm_id='N1', kind=PlaceKind.testing_site, name='Lab', lat=-1.28, lon=36.90,
		tests=[TestOffering(name='Something', cost_kes=100)])])
	from afya.places.views import TestType
	found, unanswered = svc.find(*NAIROBI, {PlaceKind.testing_site}, test_type=TestType.hiv)
	assert 'test type' in unanswered
	assert len(found) == 1, 'the facility is not dropped — nobody said it does not test for HIV'


async def test_sha_acceptance_is_tri_state_and_an_unfiled_row_stays() -> None:
	"""§FND-004's "Whether they accept SHA" and §FND-001's identical field. A defaulted `False`
	would tell a person their insurance is refused when the county simply has not filed the row, so
	the filter keeps the unpublished facility and the screen shows it as unconfirmed."""
	svc = _service()
	await _seed(svc, [
		Place(osm_id='N1', kind=PlaceKind.pharmacy, name='Good Chemist', lat=-1.28, lon=36.90,
			accepts_sha=True),
		Place(osm_id='N2', kind=PlaceKind.pharmacy, name='Cash Only', lat=-1.285, lon=36.905,
			accepts_sha=False),
		Place(osm_id='N3', kind=PlaceKind.pharmacy, name='Unfiled', lat=-1.286, lon=36.906),
	])
	found, unanswered = svc.find(*NAIROBI, {PlaceKind.pharmacy}, accepts_sha=True)
	ids = [p.osm_id for p, _ in found]
	assert 'N1' in ids and 'N2' not in ids, 'a refusal is an answer and excludes'
	assert 'N3' in ids, 'nobody filed it, which is not a refusal'
	assert unanswered == []


async def test_a_sha_filter_nothing_published_is_reported() -> None:
	svc = _service()
	await _seed(svc, [Place(osm_id='N1', kind=PlaceKind.pharmacy, name='Chemist', lat=-1.28, lon=36.90)])
	found, unanswered = svc.find(*NAIROBI, {PlaceKind.pharmacy}, accepts_sha=True)
	assert 'SHA acceptance' in unanswered
	assert len(found) == 1
