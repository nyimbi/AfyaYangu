"""Gate: §MED-004's six Features and its three Anti-gaming controls.

The section asks two different questions and only one of them had an answer. `stock_for` is keyed
on (drug, facility) and needs both, so it answers "is this drug at this place" — but the section's
own example is "available at [pharmacy], 2 hours ago", which is a person holding a prescription and
wanting a list of places. `search_stock` is the other question, and `StockAvailability` is what
makes the example a sentence rather than a lookup.

The Anti-gaming clause is where this feature is easiest to get wrong in the direction that looks
like success. A crowdsourced availability map with no proximity check is a map of wherever the
loudest reporter lives; one that refuses a report it cannot place is a map that excludes every
phone without a GPS fix, which is the accessibility failure §ACC-001 exists to prevent. Both
failures look like working code, so both directions are pinned below.
"""
import re

import httpx
import pytest
from pydantic import ValidationError

from afya.content_audit.service import FEATURE_CONTENT
from afya.facilities.service import FacilityService, haversine_km
from afya.facilities.views import Facility, FacilityKind
from afya.medicine.service import (
	STOCK_REPORT_MAX_KM, MedicineService, _geohash_centre, _now_iso, essential_slug,
)
from afya.medicine.views import ESSENTIAL_MEDICINES, StockAvailability, StockReport
from afya.mobile.actions import FEATURE_OF, catalogue
from afya.refs import resolves
from afya.service import build_services, create_app

FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')

# Encoded from real Kenyan coordinates, so the proximity assertions are about geography rather than
# about the encoder agreeing with the decoder. KNH is the facility in every distance test below.
KNH_LAT, KNH_LON = -1.3, 36.8
GEOHASH_AT_KNH = 'kzf0t7'
GEOHASH_AT_KISUMU = 'kzbxqv'


class _NoRegistry:
	"""A PPB port that fails if called: these tests are about stock, and a verify here would mean the
	wrong service answered."""

	async def verify(self, req: object) -> object:
		raise AssertionError(f'the stock tests do not verify medicine (got {req!r})')


def _svc() -> MedicineService:
	return MedicineService(_NoRegistry())  # type: ignore[arg-type]


def _report(report_id: str, *, drug: str = 'Insulin', facility_id: str = 'F1', in_stock: bool = True,
	reported_by: str = 'CHW-1', at_iso: str | None = None,
	geohash: str | None = None) -> StockReport:
	return StockReport(report_id=report_id, facility_id=facility_id, drug=drug, in_stock=in_stock,
		reported_by=reported_by, at_iso=at_iso, reporter_geohash=geohash)


def _knh() -> Facility:
	return Facility(facility_id='F1', name='Kenyatta National Hospital', kind=FacilityKind.ed,
		county='Nairobi', lat=KNH_LAT, lon=KNH_LON)


def _served(app: object) -> set[tuple[str, str]]:
	"""Every (method, path) the app serves, walked recursively.

	`app.routes` nests: an `include_router` is an `_IncludedRouter` whose paths live on
	`original_router.routes`, so a flat walk returns `[]` and a test that trusted it would conclude
	a served route does not exist. That is how a stale audit row got written on this codebase once.
	"""
	found: set[tuple[str, str]] = set()

	def walk(routes: object) -> None:
		for r in routes:  # type: ignore[attr-defined]
			if hasattr(r, 'routes'):
				walk(r.routes)
				continue
			for method in getattr(r, 'methods', None) or []:
				found.add((method, getattr(r, 'path', '')))

	walk(getattr(app, 'routes'))
	assert found, 'the walk found no routes, so every assertion below would pass vacuously'
	return found


async def _token(c: httpx.AsyncClient) -> dict[str, str]:
	return {'authorization': f"Bearer {(await c.post('/auth/anonymous', json={})).json()['token']}"}


# --- the search that `stock_for` cannot answer ---------------------------------------------------

async def test_a_search_finds_a_drug_across_facilities() -> None:
	"""The feature's own question, and the one the old shape could not be asked.

	`stock_for` needs a facility, so a person with a prescription had no way to ask where the
	medicine is — which is the whole of "Search for a medicine".
	"""
	svc = _svc()
	for i, fac in enumerate(('F1', 'F2', 'F3')):
		await svc.report_stock(_report(f'STOCK-{i:06d}', facility_id=fac,
			at_iso=f'2026-10-12T0{i}:00:00+00:00'))
	found = svc.search_stock('insulin')
	assert {a.facility_id for a in found} == {'F1', 'F2', 'F3'}, found
	assert len(svc.stock_for('Insulin', 'F1')) == 1


async def test_a_search_says_nothing_rather_than_guessing() -> None:
	svc = _svc()
	assert svc.search_stock('insulin') == []
	with pytest.raises(AssertionError):
		svc.search_stock('   ')


async def test_a_search_returns_one_row_per_drug_and_place() -> None:
	"""Ten reports about one pair are one answer with `reports=10`, not ten answers.

	A list of ten identical rows is not "where can I get this" — it is the crowd's raw feed, and a
	person reading it learns nothing the newest row did not already say.
	"""
	svc = _svc()
	for i in range(10):
		await svc.report_stock(_report(f'STOCK-{i:06d}', at_iso=f'2026-10-12T{i:02d}:00:00+00:00'))
	rows = svc.search_stock('insulin')
	assert len(rows) == 1 and rows[0].reports == 10, rows


async def test_a_search_is_capped() -> None:
	svc = _svc()
	for i in range(5):
		await svc.report_stock(_report(f'STOCK-{i:06d}', facility_id=f'F{i}', at_iso=_now_iso()))
	assert len(svc.search_stock('insulin', limit=2)) == 2


# --- "prioritised" ------------------------------------------------------------------------------

def test_the_essential_list_is_the_sections_eight() -> None:
	"""The section prints eight in parentheses; a list that dropped one is a different promise."""
	assert len(ESSENTIAL_MEDICINES) == 8, ESSENTIAL_MEDICINES
	slugs = {m.slug for m in ESSENTIAL_MEDICINES}
	assert slugs == {'insulin', 'arvs', 'tb-drugs', 'oxytocin', 'malaria-acts', 'ors', 'zinc',
		'contraceptives'}, slugs
	for m in ESSENTIAL_MEDICINES:
		assert m.label and m.aliases, m


async def test_an_essential_medicine_sorts_before_a_plain_one() -> None:
	""""Prioritised" is an ordering, and an ordering nothing applies is a comment.

	The vitamin is *fresher* than the insulin, so a sort by recency alone would put it first. The
	essential flag has to outrank the age, or the list is prioritised in name only.
	"""
	svc = _svc()
	await svc.report_stock(_report('STOCK-AAAAAA', drug='Vitamin C', at_iso='2026-10-12T09:00:00+00:00'))
	await svc.report_stock(_report('STOCK-BBBBBB', drug='Insulin', at_iso='2026-10-01T09:00:00+00:00'))
	rows = svc.search_stock('i')
	assert [r.drug for r in rows] == ['Insulin', 'Vitamin C'], rows
	assert rows[0].essential and not rows[1].essential


def test_an_essential_name_matches_on_whole_words() -> None:
	"""The reason this is not `in`: "insulin" is a substring of "insulinoma" and "act" of "contact".

	A tumour is not a medicine and a contact is not a malaria ACT, and a substring match would
	prioritise both — a wrong answer wearing a right answer's clothes.
	"""
	assert essential_slug('Insulin') == 'insulin'
	assert essential_slug('insulinoma') is None
	assert essential_slug('Malaria ACTs') == 'malaria-acts'
	assert essential_slug('contact lens solution') is None
	assert essential_slug('  ZINC sulphate  ') == 'zinc'
	assert essential_slug('paracetamol') is None
	assert essential_slug('') is None


def test_an_essential_medicine_is_reachable_by_the_names_a_crowd_uses() -> None:
	"""A report arrives as whatever the reporter typed, so the alias list is the join key."""
	for drug, slug in (('ARVs', 'arvs'), ('dolutegravir', 'arvs'), ('TLD', 'arvs'),
		('coartem', 'malaria-acts'), ('ORS', 'ors'), ('family planning', 'contraceptives'),
		('rifampicin', 'tb-drugs'), ('pitocin', 'oxytocin')):
		assert essential_slug(drug) == slug, drug


# --- "2 hours ago" ------------------------------------------------------------------------------

def test_a_report_carries_the_time_it_was_made() -> None:
	"""The section's sentence needs a timestamp, and `StockReport` carried none until this unit."""
	assert 'at_iso' in StockReport.model_fields


async def test_an_availability_carries_a_duration_and_the_instant_beside_it() -> None:
	"""A number a screen prints, and the fact it came from.

	Age is a duration rather than a timestamp because "clearly" means a client renders it without
	diffing against its own clock — a phone whose clock is wrong would print a wrong age, and one
	with no clock could not print any. The instant travels too, so the claim stays auditable.
	"""
	svc = _svc()
	await svc.report_stock(_report('STOCK-AAAAAA', at_iso='2026-10-12T07:00:00+00:00'))
	row = svc.availability_for('insulin', 'F1')
	assert row is not None
	assert row.reported_at_iso == '2026-10-12T07:00:00+00:00'
	assert isinstance(row.age_hours, float) and row.age_hours > 0


async def test_an_older_clients_report_has_no_age_rather_than_a_wrong_one() -> None:
	"""`at_iso` is optional, and a missing one must not become an age measured from now.

	That would make every report from a client that predates the field look like it was filed this
	second — the freshest possible reading of the oldest possible data.
	"""
	svc = _svc()
	await svc.report_stock(_report('STOCK-AAAAAA'))
	row = svc.availability_for('insulin', 'F1')
	assert row is not None
	assert row.age_hours is None and row.reported_at_iso is None
	# An undated row sorts last rather than first, so it cannot displace a dated report.
	await svc.report_stock(_report('STOCK-BBBBBB', drug='Insulin pen', at_iso='2026-10-12T09:00:00+00:00'))
	assert [r.age_hours is None for r in svc.search_stock('insulin')] == [False, True]


# --- the restock alert ---------------------------------------------------------------------------

async def test_the_restock_alert_fires_on_the_transition() -> None:
	"""Out of stock, then in stock: the one event the section asks to be told about."""
	svc = _svc()
	assert await svc.report_stock(_report('STOCK-AAAAAA', in_stock=False,
		at_iso='2026-10-01T09:00:00+00:00')) is None
	alert = await svc.report_stock(_report('STOCK-BBBBBB', in_stock=True,
		at_iso='2026-10-12T09:00:00+00:00'))
	assert alert is not None
	assert alert.drug == 'Insulin' and alert.facility_id == 'F1'
	assert alert.became_available_at_iso == '2026-10-12T09:00:00+00:00'
	assert alert.out_of_stock_since_iso == '2026-10-01T09:00:00+00:00'
	assert svc.restock_alerts() == [alert]


async def test_a_second_in_stock_report_is_not_news() -> None:
	"""The state is not the event. A crowd repeating "it is here" is not a restock."""
	svc = _svc()
	await svc.report_stock(_report('STOCK-AAAAAA', in_stock=True, at_iso='2026-10-01T09:00:00+00:00'))
	assert await svc.report_stock(_report('STOCK-BBBBBB', in_stock=True,
		at_iso='2026-10-12T09:00:00+00:00')) is None
	assert svc.restock_alerts() == []


async def test_a_stockout_is_not_a_restock() -> None:
	svc = _svc()
	assert await svc.report_stock(_report('STOCK-AAAAAA', in_stock=False, at_iso=_now_iso())) is None
	assert svc.restock_alerts() == []


async def test_the_alert_is_scoped_to_one_facility() -> None:
	svc = _svc()
	for rid, fac in (('STOCK-AAAAAA', 'F1'), ('STOCK-BBBBBB', 'F2')):
		await svc.report_stock(_report(rid, facility_id=fac, in_stock=False,
			at_iso='2026-10-01T09:00:00+00:00'))
	await svc.report_stock(_report('STOCK-CCCCCC', facility_id='F2', at_iso='2026-10-12T09:00:00+00:00'))
	assert [a.facility_id for a in svc.restock_alerts()] == ['F2']
	assert svc.restock_alerts('F1') == []


async def test_the_availability_shown_is_the_newest_by_time_not_by_arrival() -> None:
	"""A report queued offline and flushed later is older than one filed after it.

	Reading arrival order would make the offline report the newest thing anyone knows, and the
	availability a person sees would be the one that travelled slowest.
	"""
	svc = _svc()
	await svc.report_stock(_report('STOCK-BBBBBB', in_stock=False, at_iso='2026-10-12T09:00:00+00:00'))
	# Filed first, made last.
	await svc.report_stock(_report('STOCK-AAAAAA', in_stock=True, at_iso='2026-10-01T09:00:00+00:00'))
	row = svc.availability_for('insulin', 'F1')
	assert row is not None and row.in_stock is False, row
	assert row.reported_at_iso == '2026-10-12T09:00:00+00:00'


async def test_a_stale_stockout_does_not_make_a_restock_out_of_nothing() -> None:
	"""The alert's own notion of "previous", which is a second ordering and a second chance to get
	it wrong.

	`_latest` decides what the last thing anyone said was, and it is asked *before* the incoming
	report is stored. Here the store's newest-by-time report already says in stock, and a stale
	stockout sits behind it in arrival order — so a report arriving now that says in stock is the
	same news a second time. Read in arrival order, the stale stockout is "the last word" and the
	alert fires again, telling people a medicine came back that never went away.
	"""
	svc = _svc()
	await svc.report_stock(_report('STOCK-AAAAAA', in_stock=True, at_iso='2026-10-12T09:00:00+00:00'))
	await svc.report_stock(_report('STOCK-BBBBBB', in_stock=False, at_iso='2026-10-01T09:00:00+00:00'))
	assert await svc.report_stock(_report('STOCK-CCCCCC', in_stock=True,
		at_iso='2026-10-13T09:00:00+00:00')) is None
	assert svc.restock_alerts() == []


# --- anti-gaming: proximity ----------------------------------------------------------------------

def test_a_geohash_decodes_to_the_cell_that_contains_it() -> None:
	"""The decoder is what the proximity test rests on, so it is checked against a real coordinate."""
	lat, lon = _geohash_centre(GEOHASH_AT_KNH)
	assert haversine_km(lat, lon, KNH_LAT, KNH_LON) < 1.0
	lat2, lon2 = _geohash_centre(GEOHASH_AT_KISUMU)
	assert haversine_km(lat2, lon2, KNH_LAT, KNH_LON) > 200


def test_a_coarse_cell_is_refused_rather_than_silently_rounded() -> None:
	"""§LOC-003's rule: raw location never crosses this boundary, and neither does a cell so coarse
	it is a region. A two-character geohash is not a position near a facility, it is a county."""
	with pytest.raises(AssertionError):
		_geohash_centre('kz')
	with pytest.raises(AssertionError):
		_geohash_centre('kzf0!')


def test_a_report_from_far_away_is_not_near_the_facility() -> None:
	svc = _svc()
	assert svc.within_proximity(_report('STOCK-AAAAAA', geohash=GEOHASH_AT_KISUMU), _knh(),
		STOCK_REPORT_MAX_KM) is False


def test_a_report_from_the_facility_is_near_it() -> None:
	svc = _svc()
	assert svc.within_proximity(_report('STOCK-AAAAAA', geohash=GEOHASH_AT_KNH), _knh(),
		STOCK_REPORT_MAX_KM) is True


def test_an_unplaceable_report_has_not_shown_that_it_is_near() -> None:
	"""`False`, and the caller decides — which is what keeps §13.2's `gps` fallback alive.

	The predicate answers "is this report from here", and a report with no cell has not shown that
	it is. The route skips the check for a missing geohash rather than reading this `False` as a
	refusal, so a phone without a fix can still report.
	"""
	svc = _svc()
	assert svc.within_proximity(_report('STOCK-AAAAAA'), _knh(), STOCK_REPORT_MAX_KM) is False


# --- anti-gaming: reporter weight -----------------------------------------------------------------

def test_a_reporter_with_no_history_starts_at_the_middle() -> None:
	"""An unknown reporter is not a distrusted one. Starting at the floor would silence every new
	person, which is the opposite of what a crowdsourced map needs."""
	assert _svc().reporter_weight('CHW-NOBODY') == 5


async def test_a_reporter_whose_report_is_contradicted_loses_a_point() -> None:
	svc = _svc()
	await svc.report_stock(_report('STOCK-AAAAAA', in_stock=True, reported_by='CHW-1',
		at_iso='2026-10-01T09:00:00+00:00'))
	await svc.report_stock(_report('STOCK-BBBBBB', in_stock=False, reported_by='CHW-2',
		at_iso='2026-10-12T09:00:00+00:00'))
	assert svc.reporter_weight('CHW-1') == 4
	# CHW-2 is the newest, so nobody has contradicted them *yet* — being the one who disagreed is
	# not itself evidence, and paying for it would reward whoever reports last regardless of what
	# they said. Their weight moves the day a third report lands.
	assert svc.reporter_weight('CHW-2') == 5


async def test_a_reporter_whose_report_stands_gains_a_point() -> None:
	svc = _svc()
	await svc.report_stock(_report('STOCK-AAAAAA', in_stock=True, reported_by='CHW-1',
		at_iso='2026-10-01T09:00:00+00:00'))
	await svc.report_stock(_report('STOCK-BBBBBB', in_stock=True, reported_by='CHW-2',
		at_iso='2026-10-12T09:00:00+00:00'))
	assert svc.reporter_weight('CHW-1') == 6


async def test_a_report_nobody_has_contradicted_yet_is_not_evidence_either_way() -> None:
	"""Silence is not agreement. The newest report has no later report to stand against, so it
	moves no weight — counting it as confirmed would reward whoever reported last, always."""
	svc = _svc()
	await svc.report_stock(_report('STOCK-AAAAAA', reported_by='CHW-1',
		at_iso='2026-10-12T09:00:00+00:00'))
	assert svc.reporter_weight('CHW-1') == 5


def test_the_weight_is_derived_and_cannot_be_supplied() -> None:
	"""A client that sets its own weight has none. The field is on the *answer*, not the request."""
	assert 'reporter_weight' not in StockReport.model_fields
	assert 'reporter_weight' in StockAvailability.model_fields
	with pytest.raises(ValidationError):
		StockReport.model_validate({'report_id': 'STOCK-AAAAAA', 'facility_id': 'F1', 'drug': 'Insulin',
			'in_stock': True, 'reported_by': 'CHW-1', 'reporter_weight': 10})


async def test_the_reporter_is_the_token_and_not_the_body() -> None:
	"""The second half of "derived, not supplied", and the half a field check cannot see.

	`reporter_weight` is not on the request, but `reported_by` is — and the weight is computed from
	`reported_by`. On an ungated route that makes the identity behind the control whatever the
	client typed, so a reporter with a contradicted record files the next report under a fresh name
	and starts at the middle again. The weight is only a weight if the history belongs to one
	reporter, so the token wins when there is one.
	"""
	services = build_services()
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		tok = (await c.post('/auth/anonymous', json={})).json()['token']
		hdrs = {'authorization': f'Bearer {tok}'}
		me = (await c.get('/auth/whoami', headers=hdrs)).json()['subject_ref']
		resp = await c.post('/medicine/stock', headers=hdrs, json={'report_id': 'STOCK-AAAAAA',
			'facility_id': 'F1', 'drug': 'Insulin', 'in_stock': True, 'reported_by': 'SOMEONE-ELSE'})
		assert resp.status_code == 200, resp.text
	medicine = services['medicine']
	assert isinstance(medicine, MedicineService)
	rows = medicine.stock_for('Insulin', 'F1')
	assert len(rows) == 1 and rows[0].reported_by == me, rows
	assert medicine.reporter_weight('SOMEONE-ELSE') == 5, 'the typed name acquired a history it does not own'


async def test_a_report_with_no_token_is_still_recorded_under_its_own_name() -> None:
	"""§13.2 again: the route is ungated on purpose, so a reporter with no token must still land.

	The body's `reported_by` is the fallback rather than dead weight — a report that arrived over a
	queued offline batch or from a client that has not enrolled carries the name it was filed under.
	"""
	services = build_services()
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		resp = await c.post('/medicine/stock', json={'report_id': 'STOCK-AAAAAA', 'facility_id': 'F1',
			'drug': 'Insulin', 'in_stock': True, 'reported_by': 'CHW-1'})
	assert resp.status_code == 200, resp.text
	medicine = services['medicine']
	assert isinstance(medicine, MedicineService)
	rows = medicine.stock_for('Insulin', 'F1')
	assert len(rows) == 1 and rows[0].reported_by == 'CHW-1', rows


async def test_the_weight_is_clamped() -> None:
	"""A reporter contradicted thirty times is a low-weight source, not a negative one."""
	svc = _svc()
	for i in range(30):
		await svc.report_stock(_report(f'STOCK-{i:06d}', in_stock=True, reported_by='CHW-1',
			at_iso=f'2026-09-{i % 28 + 1:02d}T09:00:00+00:00'))
		await svc.report_stock(_report(f'STOCK-{i + 100:06d}', in_stock=False, reported_by='CHW-2',
			at_iso=f'2026-10-{i % 28 + 1:02d}T09:00:00+00:00'))
	assert svc.reporter_weight('CHW-1') == 1
	assert 1 <= svc.reporter_weight('CHW-2') <= 10


# --- the served surface --------------------------------------------------------------------------

def test_the_med004_routes_are_served() -> None:
	served = _served(create_app(build_services()))
	for expected in (('GET', '/medicine/stock/search'), ('GET', '/medicine/stock/availability'),
		('GET', '/medicine/stock/alerts'), ('GET', '/medicine/essential')):
		assert expected in served, (expected, sorted(served))


async def test_the_essential_list_is_served_without_a_token() -> None:
	"""A constant the section prints, needed before a client can render "prioritised"."""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		resp = await c.get('/medicine/essential')
	assert resp.status_code == 200, resp.text
	body = resp.json()
	assert len(body) == 8 and {m['slug'] for m in body} == {m.slug for m in ESSENTIAL_MEDICINES}
	assert all(m['label'] for m in body)


async def test_a_stock_report_travels_through_the_route_and_comes_back_with_its_alert() -> None:
	"""End to end, with a token, against the facility the report names.

	The geohash is real and at KNH, so this exercises the proximity check on the served path rather
	than only on the predicate — a route that forgot to call it would pass every test above.
	"""
	services = build_services()
	facilities: FacilityService = services['facilities']  # type: ignore[assignment]
	await facilities.upsert(_knh())
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		hdrs = await _token(c)
		base = {'report_id': 'STOCK-AAAAAA', 'facility_id': 'F1', 'drug': 'Insulin',
			'reported_by': 'CHW-1', 'reporter_geohash': GEOHASH_AT_KNH}
		out = await c.post('/medicine/stock', headers=hdrs,
			json={**base, 'in_stock': False, 'at_iso': '2026-10-01T09:00:00+00:00'})
		assert out.status_code == 200, out.text
		assert 'restock_alert' not in out.json()
		back = await c.post('/medicine/stock', headers=hdrs, json={**base, 'report_id': 'STOCK-BBBBBB',
			'in_stock': True, 'at_iso': '2026-10-12T09:00:00+00:00'})
		assert back.status_code == 200, back.text
		alert = back.json()['restock_alert']
		assert alert['drug'] == 'Insulin'
		assert alert['out_of_stock_since_iso'] == '2026-10-01T09:00:00+00:00'
		row = await c.get('/medicine/stock/availability', headers=hdrs,
			params={'drug': 'Insulin', 'facility_id': 'F1'})
		assert row.status_code == 200, row.text
		assert row.json()['in_stock'] is True
		assert row.json()['facility_name'] == 'Kenyatta National Hospital'
		found = await c.get('/medicine/stock/search', headers=hdrs, params={'q': 'insulin'})
		assert found.status_code == 200, found.text
		assert found.json()[0]['facility_name'] == 'Kenyatta National Hospital'
		alerts = await c.get('/medicine/stock/alerts', headers=hdrs)
		assert alerts.status_code == 200 and len(alerts.json()) == 1


async def test_a_report_from_another_county_is_refused() -> None:
	"""The Anti-gaming control, on the served path: a 422 rather than a silent drop.

	A report that vanished would look like a network fault to the person who filed it, and they
	would file it again from the same place.
	"""
	services = build_services()
	facilities: FacilityService = services['facilities']  # type: ignore[assignment]
	await facilities.upsert(_knh())
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		hdrs = await _token(c)
		resp = await c.post('/medicine/stock', headers=hdrs, json={'report_id': 'STOCK-AAAAAA',
			'facility_id': 'F1', 'drug': 'Insulin', 'in_stock': True, 'reported_by': 'CHW-1',
			'reporter_geohash': GEOHASH_AT_KISUMU})
	assert resp.status_code == 422, resp.text
	assert 'too far' in str(resp.json())


async def test_a_report_with_no_location_is_still_accepted() -> None:
	"""§13.2's `gps` fallback: a phone without a fix must not lose the ability to report.

	The predicate returns `False` for this report, so a route that read `False` as a refusal would
	reject every such report — the accessibility failure §ACC-001 exists to prevent.
	"""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		hdrs = await _token(c)
		resp = await c.post('/medicine/stock', headers=hdrs, json={'report_id': 'STOCK-AAAAAA',
			'facility_id': 'F-UNKNOWN', 'drug': 'Insulin', 'in_stock': True, 'reported_by': 'CHW-1'})
	assert resp.status_code == 200, resp.text
	assert resp.json()['ok'] is True


async def test_a_report_naming_a_facility_nobody_knows_is_refused_when_it_can_be_placed() -> None:
	"""Only when it can be placed: proximity is a claim about a facility, so there has to be one."""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		hdrs = await _token(c)
		resp = await c.post('/medicine/stock', headers=hdrs, json={'report_id': 'STOCK-AAAAAA',
			'facility_id': 'F-NOPE', 'drug': 'Insulin', 'in_stock': True, 'reported_by': 'CHW-1',
			'reporter_geohash': GEOHASH_AT_KNH})
	assert resp.status_code == 404, resp.text


async def test_the_stock_reads_need_a_token() -> None:
	"""The reports are attributable and the reads are self-scoped; an open availability map is a map
	anyone can poison anonymously."""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		for path in ('/medicine/stock/search?q=insulin',
			'/medicine/stock/availability?drug=x&facility_id=y', '/medicine/stock/alerts'):
			resp = await c.get(path)
			assert resp.status_code in (401, 403), (path, resp.status_code)


async def test_an_unknown_pair_is_a_404_rather_than_an_empty_answer() -> None:
	""""Nobody has reported this" and "it is not there" are different answers, and a defaulted
	`in_stock=False` would tell a person a medicine is unavailable because no one checked."""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		hdrs = await _token(c)
		resp = await c.get('/medicine/stock/availability', headers=hdrs,
			params={'drug': 'Insulin', 'facility_id': 'F1'})
	assert resp.status_code == 404, resp.text


# --- the section's own bookkeeping ----------------------------------------------------------------

def test_every_med004_bullet_is_accounted_for() -> None:
	"""Six Features and three Anti-gaming controls, none of them `missing`."""
	rows = [(b, k) for f, _, b, k, _, _ in FEATURE_CONTENT if f == 'MED-004']
	assert len(rows) == 9, rows
	assert [k for _, k in rows].count('missing') == 0, rows
	assert [k for _, k in rows].count('carried') == 9, rows
	assert {b for b, _ in rows} >= {'Search for a medicine', 'Require location proximity to report',
		'Weight reports by reporter reliability', 'Show report age clearly'}, rows


def test_the_carried_rows_name_code_that_exists() -> None:
	for f, _, _, kind, ref, _ in FEATURE_CONTENT:
		if f == 'MED-004' and kind == 'carried':
			assert resolves(ref), ref
	assert resolves('afya.medicine.service:MedicineService.search_stock')


def test_every_med004_action_reaches_a_route_that_exists() -> None:
	"""A catalogue entry pointing at a route nobody serves is a screen that 404s."""
	served = _served(create_app(build_services()))
	med = [a for a in catalogue() if FEATURE_OF.get(a.id) == 'MED-004']
	assert len(med) == 6, [a.id for a in med]
	for act in med:
		assert (act.method, act.path) in served, (act.id, act.method, act.path)


def test_no_spec_code_reaches_a_stock_surface() -> None:
	"""The standing constraint: §MED-004's ids are traceability handles, not user-facing strings."""
	for act in catalogue():
		assert not FEATURE_CODE.search(act.title), act.title
		assert not FEATURE_CODE.search(act.id), act.id
		for fld in act.fields:
			assert not FEATURE_CODE.search(fld.label), fld.label
			assert not FEATURE_CODE.search(fld.placeholder or ''), fld.placeholder
	for m in ESSENTIAL_MEDICINES:
		assert not FEATURE_CODE.search(m.label) and not FEATURE_CODE.search(m.slug), m
