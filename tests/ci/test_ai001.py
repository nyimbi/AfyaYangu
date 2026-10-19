"""§AI-001 community-level risk prediction: five Inputs, three Outputs, one floor.

The section names five Inputs, three Outputs and a privacy rule. Three of the five Inputs were
carried (`fever_reports`, `cough_events`, `encounter_density`, `facility_reports`) and two were not,
and two of the three Outputs had no carrier at all:

* **geofence entries** existed as `integrations.feeds.build_geofence_feed`'s distinct-subject
  aggregation — floored at 10, for county teams — and never reached the model;
* **search and content-engagement signals** existed as §AI-003's `facility_search` and
  `medicine_search` ledger rows and likewise never reached the model;
* **transmission cluster identification** had no carrier: the map carried one `Hotspot` per cell and
  `MisinfoCluster` clusters rumours, which is a different quantity;
* **resource deployment recommendations** had a *builder* — `build_resource_feed` — and no producer,
  so §18.3's `resource_deployment` feed was a builder with no caller.

Two of those are the read-with-no-producer shape §INF-007 was; one is its opposite, a builder with no
producer. Both are failures that render as working code.

Each gate below is canaried against a planted defect in `canary_ai001.py`.
"""
from datetime import date
from typing import Any

import httpx
import pytest

from afya.ai.service import MIN_CELL_SIZE, AIService
from afya.ai.views import (
	AggregateCell, HotspotMap, ResourceRecommendation, TransmissionCluster,
)
from afya.integrations.feeds import build as build_feed


def _cell(cell_id: str, county: str, population: int, fever: int = 0, **kw: Any) -> AggregateCell:
	base: dict[str, Any] = {
		'cell_id': cell_id, 'county': county, 'population': population, 'fever_reports': fever,
		'cough_events': 0, 'encounter_density': 0.2, 'facility_reports': 0,
	}
	base.update(kw)
	return AggregateCell(**base)


# --- the five Inputs --------------------------------------------------------------------------

def test_the_section_names_five_inputs_and_the_cell_carries_them() -> None:
	"""§AI-001's Inputs sentence, in the section's order: "Aggregated symptom reports, geofence
	entries, proximity encounter density, crowdsourced facility reports, search and content-engagement
	signals." Five, and the cell has a field for each — which is the only version of "carried" a
	reader can check."""
	fields = set(AggregateCell.model_fields)
	assert {'fever_reports', 'cough_events'} <= fields, 'aggregated symptom reports'
	assert 'geofence_entries' in fields, 'geofence entries'
	assert 'encounter_density' in fields, 'proximity encounter density'
	assert 'facility_reports' in fields, 'crowdsourced facility reports'
	assert 'search_signals' in fields, 'search and content-engagement signals'
	# The two that were absent are optional, so a deployment with no geofence feed sends a cell rather
	# than omitting one: an absent input is a zero, and the hotspot's reason names the zero.
	assert _cell('c1', 'Busia', 1000).geofence_entries == 0
	assert _cell('c1', 'Busia', 1000).search_signals == 0


def test_every_input_moves_the_score_and_fever_dominates() -> None:
	"""All five inputs are read, not four of five with a field sitting unused. The weights are the
	model's own — the section states none — and fever carries it because fever is what the product
	collects at scale. A field that is on the model and not in the score is the defect this closes."""
	svc = AIService()
	base = svc._signal_score(_cell('c1', 'Busia', 10_000))
	for field, bump in (('fever_reports', 100), ('cough_events', 100), ('facility_reports', 100),
	                    ('geofence_entries', 100), ('search_signals', 100)):
		moved = svc._signal_score(_cell('c1', 'Busia', 10_000, **{field: bump}))
		assert moved > base, f'{field} is on the cell and not in the score'
	# Every term is a *rate*: the same count in a cell ten times the size is a smaller signal.
	small = svc._signal_score(_cell('c1', 'Busia', 1_000, fever_reports=100))
	large = svc._signal_score(_cell('c1', 'Busia', 10_000, fever_reports=100))
	assert small > large, 'a count is not a rate, and a model that adds counts ranks by cell size'


def test_the_bridge_reads_the_signal_ledger_the_product_already_writes() -> None:
	"""§AI-001's fifth Input. The signals were in the ledger and not in the model: `facility_search`
	and `medicine_search` are §AI-003's own signals, recorded by the routes that own those surfaces,
	and `cells_from_signals` is the wire between them."""
	from afya.ai.views import SignalEvent
	import asyncio

	svc = AIService()
	today = date.today().isoformat()

	async def _seed() -> None:
		for i in range(7):
			await svc.record_signal_event(SignalEvent(county='Busia', at_iso=today,
				signal='facility_search' if i % 2 else 'medicine_search', event_ref=f's{i}'))
		for i in range(3):
			await svc.record_signal_event(SignalEvent(county='Busia', at_iso=today,
				signal='fever_triage', event_ref=f'f{i}'))
		# Another county's signals are not this county's.
		await svc.record_signal_event(SignalEvent(county='Kisumu', at_iso=today,
			signal='facility_search', event_ref='k0'))

	asyncio.run(_seed())
	cell = svc.cells_from_signals('Busia', 'c1', 1_000, at_iso=today)
	assert cell.search_signals == 7, 'both search signals are the section one signal'
	assert cell.fever_reports == 3
	assert svc.cells_from_signals('Kisumu', 'c2', 1_000, at_iso=today).search_signals == 1
	# The geofence count is the caller's, because the floor lives in the module that owns the
	# aggregation and a second copy of it here is a second floor that can differ.
	assert cell.geofence_entries == 0
	assert svc.cells_from_signals('Busia', 'c1', 1_000, at_iso=today, geofence_entries=40).geofence_entries == 40
	# A cell below the floor is *built* and left for `hotspots` to suppress and count: pre-filtering
	# here would hide the suppression from the report that exists to state it.
	small = svc.cells_from_signals('Busia', 'c3', 4, at_iso=today)
	assert svc.hotspots([small]).suppressed_cells == 1


def test_the_bridge_keeps_facility_reports_and_search_signals_apart() -> None:
	"""Two of the section's five Inputs are different quantities. Reading the search ledger into
	`facility_reports` would make them one number wearing two names, and the cell's `reason` would
	then report the same figure twice as though it were two findings."""
	import asyncio

	from afya.ai.views import SignalEvent
	svc = AIService()

	async def _seed() -> None:
		for i in range(5):
			await svc.record_signal_event(SignalEvent(county='Busia', at_iso=date.today().isoformat(),
				signal='medicine_search', event_ref=f'm{i}'))

	asyncio.run(_seed())
	cell = svc.cells_from_signals('Busia', 'c1', 1_000, facility_reports=2)
	assert cell.search_signals == 5 and cell.facility_reports == 2


# --- the second Output: clusters ---------------------------------------------------------------

def _pair(**kw: Any) -> list[AggregateCell]:
	"""Two adjacent cells in one county, both above baseline, plus a far one below it."""
	return [
		_cell('c1', 'Busia', 10_000, fever_reports=900, lat=-0.10, lon=34.00, **kw),
		_cell('c2', 'Busia', 10_000, fever_reports=880, lat=-0.12, lon=34.01, **kw),
		_cell('c3', 'Kisumu', 10_000, fever_reports=5, lat=-1.00, lon=35.00, **kw),
	]


def test_two_adjacent_cells_above_baseline_are_one_cluster_not_two_hotspots() -> None:
	"""§AI-001's "transmission cluster identification". Two cells at 1.2σ that touch are one event a
	response team treats as one, and a map that lists them as two hotspots tells PHEOC to send two
	teams. The `links` are what make it a cluster rather than a list of ids."""
	svc = AIService()
	out = svc.hotspots(_pair())
	assert len(out.clusters) == 1, out.clusters
	cluster = out.clusters[0]
	assert isinstance(cluster, TransmissionCluster)
	assert sorted(cluster.cell_ids) == ['c1', 'c2']
	assert cluster.counties == ['Busia'], 'the cluster is in one county here'
	assert len(cluster.links) == 1
	link = cluster.links[0]
	assert {link.from_cell, link.to_cell} == {'c1', 'c2'}
	assert 0 < link.km < svc.CLUSTER_RADIUS_KM
	assert 'c1' in cluster.reason and 'adjacent' in cluster.reason


def test_cells_further_apart_than_the_radius_are_not_one_cluster() -> None:
	"""Adjacency is a spatial claim. Two cells above baseline at opposite ends of the country are two
	events, and joining them would name a cluster that no response team could surround.

	Both are hotspots here on purpose: a test with one above baseline and one below would pass
	whatever the radius, because the below-baseline cell is filtered before clustering runs — so it
	would be testing the baseline filter while claiming to test the distance.
	"""
	svc = AIService()
	far = [
		_cell('c1', 'Busia', 10_000, fever_reports=900, lat=-0.10, lon=34.00),
		_cell('c2', 'Kisumu', 10_000, fever_reports=880, lat=-1.00, lon=35.00),
		_cell('low', 'Busia', 10_000, fever_reports=5, lat=-0.30, lon=34.30),
	]
	out = svc.hotspots(far)
	assert len(out.hotspots) == 2, 'both are above baseline and both are hotspots'
	assert out.clusters == [], 'and they are not one cluster'


def test_a_cell_with_no_position_is_reported_as_unlinkable_not_dropped() -> None:
	"""A cell that arrived from a sub-county rollup has no centroid. "We could not tell whether this
	cell touches the others" is a fact PHEOC can act on, and a cluster that quietly omitted it would
	read as complete."""
	svc = AIService()
	cells = [
		_cell('c1', 'Busia', 10_000, fever_reports=900, lat=-0.10, lon=34.00),
		_cell('c2', 'Busia', 10_000, fever_reports=880, lat=-0.12, lon=34.01),
		_cell('c9', 'Busia', 10_000, fever_reports=870),  # no position
		_cell('low', 'Busia', 10_000, fever_reports=5, lat=-0.30, lon=34.30),
	]
	out = svc.hotspots(cells)
	assert len(out.clusters) == 1
	assert sorted(out.clusters[0].cell_ids) == ['c1', 'c2'], 'the two with positions'
	assert 'could not be linked' in out.clusters[0].reason, out.clusters[0].reason


def test_a_cluster_can_never_name_a_suppressed_cell() -> None:
	"""The ordering that makes the privacy rule hold. Suppression is applied to the cells that go in,
	so a cluster is built only from cells that already cleared `MIN_CELL_SIZE` — a cluster whose
	reason named a cell of four people would re-identify exactly what the floor exists to prevent,
	and a cluster built before suppression would do it through the back door."""
	svc = AIService()
	cells = [
		_cell('c1', 'Busia', 10_000, fever_reports=900, lat=-0.10, lon=34.00),
		_cell('tiny', 'Busia', 4, fever_reports=4, lat=-0.1005, lon=34.0005),
	]
	out = svc.hotspots(cells)
	assert out.suppressed_cells == 1
	named = {cid for c in out.clusters for cid in c.cell_ids}
	assert 'tiny' not in named
	assert 'tiny' not in out.explanation


def test_one_cell_above_baseline_is_a_hotspot_and_not_a_cluster() -> None:
	"""A cluster is a connected set of cells that are *all* above baseline. A lone cell is what
	`hotspots` already carries, and a "cluster" of one would inflate the count a county reads as how
	many events it has.

	The neighbour here is deliberately **within the cluster radius and below baseline**: if it were
	far away, a version that clustered every eligible cell rather than every hotspot would still
	produce nothing and the test would pass for the wrong reason.
	"""
	svc = AIService()
	out = svc.hotspots([
		_cell('c1', 'Busia', 10_000, fever_reports=900, lat=-0.10, lon=34.00),
		_cell('near', 'Busia', 10_000, fever_reports=5, lat=-0.105, lon=34.005),  # 0.7 km away
		_cell('low', 'Busia', 10_000, fever_reports=4, lat=-0.60, lon=34.60),
	])
	assert len(out.hotspots) == 1 and out.hotspots[0].cell_id == 'c1'
	assert out.clusters == [], 'a below-baseline neighbour is not part of a transmission cluster'


# --- the third Output: recommendations ---------------------------------------------------------

def test_a_cluster_recommends_a_team_and_a_quantity_is_not_invented() -> None:
	"""§AI-001's "resource deployment recommendations". A recommendation has to trace to a finding:
	a cluster is verified by sampling, which is what a rapid response team does, and that is a
	quantity the map can decide. Test kits depend on the cluster population and a stock position this
	service does not hold, so `quantity` is `None` there — a modelled number wearing the authority of
	a recommendation is worse than an absent one."""
	svc = AIService()
	out = svc.hotspots(_pair())
	recs = {r.resource: r for r in out.recommendations}
	assert recs['rapid_response_team'].quantity == 1
	assert recs['rapid_response_team'].county == 'Busia'
	assert out.clusters[0].cluster_id in recs['rapid_response_team'].rationale
	assert recs['test_kits'].quantity is None, 'the section does not determine this one'
	assert all(not r.auto_actioned for r in out.recommendations)


def test_a_recommendation_cannot_action_itself() -> None:
	"""§19.3 keeps a human in the loop. A row that actioned itself would be the system deploying
	teams, which is the one thing the section's "Consumers: County health teams, PHEOC" forbids."""
	with pytest.raises(Exception, match='human in the loop'):
		ResourceRecommendation(county='Busia', resource='rapid_response_team', quantity=1,
			unit='team(s)', rationale='x', auto_actioned=True)


def test_a_lone_hotspot_gets_communication_and_not_a_deployment() -> None:
	"""One cell above baseline is a signal to check, not a finding to deploy against. A map that
	sent a rapid response team to every elevated cell would spend the teams on noise.

	The lone hotspot is in a county whose *neighbour* is above baseline too — so the two counties
	differ only in whether their cells form a cluster, which is the distinction the recommendation
	rule turns on. Two counties that differ in nothing else is what makes this a test of the rule.
	"""
	svc = AIService()
	out = svc.hotspots([
		_cell('c1', 'Busia', 10_000, fever_reports=900, lat=-0.10, lon=34.00),
		_cell('c2', 'Busia', 10_000, fever_reports=880, lat=-0.12, lon=34.01),   # clusters with c1
		_cell('c3', 'Kisumu', 10_000, fever_reports=870, lat=-1.00, lon=35.00),  # alone
		_cell('low', 'Kisumu', 10_000, fever_reports=4, lat=-1.60, lon=35.60),
	])
	assert len(out.clusters) == 1 and out.clusters[0].counties == ['Busia']
	by_county = {(r.county, r.resource) for r in out.recommendations}
	assert ('Busia', 'rapid_response_team') in by_county, 'a cluster gets a team'
	assert ('Kisumu', 'rapid_response_team') not in by_county, 'a lone hotspot does not'
	assert ('Kisumu', 'risk_communication') in by_county


def test_no_hotspot_means_no_recommendation_at_all() -> None:
	"""The map with nothing above baseline has nothing to recommend, and an empty list is the honest
	answer — a default recommendation would be advice with no finding behind it."""
	svc = AIService()
	out = svc.hotspots([_cell('c1', 'Busia', 10_000, fever_reports=1),
	                    _cell('c2', 'Busia', 10_000, fever_reports=1)])
	assert out.hotspots == [] and out.clusters == [] and out.recommendations == []


# --- the feed the third Output was missing a producer for ---------------------------------------

def test_the_recommendations_render_as_the_pheoc_feed_that_had_no_producer() -> None:
	"""`build_resource_feed` existed and rendered a `resource_deployment` feed and **nothing produced
	its recommendations**. This is that producer: the map's own recommendations, through the
	section's §18.3 feed, with `auto_actioned` false on every row."""
	svc = AIService()
	recs = svc.hotspots(_pair()).recommendations
	rows, withheld = build_feed('resource_deployment', [r.model_dump(mode='json') for r in recs])
	assert rows and withheld == 0
	assert all(r['auto_actioned'] is False for r in rows)
	assert all(r['county'] == 'Busia' for r in rows)
	assert all(r['granularity'] == 'county' for r in rows), '§18.3 fixes the granularity'


def test_the_map_keeps_its_shape_for_a_caller_that_only_reads_hotspots() -> None:
	"""The two new Outputs are defaulted rather than required, so the suppression-only path — every
	cell below the floor, nothing may be published — does not have to invent an empty cluster list,
	and a client reading `hotspots`/`explanation` keeps working."""
	svc = AIService()
	out = svc.hotspots([_cell('s1', 'Busia', 9, fever_reports=9)])
	assert isinstance(out, HotspotMap)
	assert out.clusters == [] and out.recommendations == []
	assert out.suppressed_cells == 1 and 'nothing may be published' in out.explanation
	assert set(out.model_dump(mode='json')) >= {'hotspots', 'suppressed_cells', 'consumers',
	                                            'explanation', 'clusters', 'recommendations'}


# --- end to end through the real app -------------------------------------------------------------

async def _county_officer(c: httpx.AsyncClient) -> str:
	"""A county health team token through the app's own PKCE flow — §17.4's `county_aggregate`."""
	from afya.auth.views import s256
	verifier = 'v' * 64
	authz = (await c.post('/auth/pkce/authorize', json={
		'client_id': 'app', 'redirect_uri': 'afya://cb', 'code_challenge': s256(verifier), 'role': 'county_officer',
		'state': 'state-1234'})).json()
	return (await c.post('/auth/pkce/token', params={'role': 'county_officer'}, json={
		'authorization_code': authz['authorization_code'], 'client_id': 'app',
		'redirect_uri': 'afya://cb', 'code_verifier': verifier})).json()['access_token']


async def test_the_map_route_serves_the_clusters_and_the_recommendations() -> None:
	"""The three Outputs over one request. The route served hotspots and the other two had no carrier
	at all, so a county team reading it could not see the cluster it was being told to surround."""
	from afya.service import build_services, create_app
	services = build_services()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(services)),
	                             base_url='http://t') as c:
		body = [cell.model_dump(mode='json') for cell in _pair()]
		assert (await c.post('/ai/hotspots', json=body)).status_code in (401, 403)
		token = await _county_officer(c)
		r = await c.post('/ai/hotspots', json={'cells': body}, headers={'authorization': f'Bearer {token}'})
		assert r.status_code == 200, r.text
		out = r.json()
		assert len(out['hotspots']) == 2
		assert len(out['clusters']) == 1 and out['clusters'][0]['cell_ids'] == ['c1', 'c2']
		assert {x['resource'] for x in out['recommendations']} >= {'rapid_response_team', 'test_kits'}


async def test_the_deploy_route_produces_the_feed_and_refuses_a_caller_without_the_scope() -> None:
	"""The producer, over the wire. §18.3's `resource_deployment` feed is AI → PHEOC, county, daily,
	and this is the route that makes the arrow real."""
	from afya.service import build_services, create_app
	services = build_services()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(services)),
	                             base_url='http://t') as c:
		body = [cell.model_dump(mode='json') for cell in _pair()]
		assert (await c.post('/ai/hotspots/deploy', json=body)).status_code in (401, 403)
		token = await _county_officer(c)
		r = await c.post('/ai/hotspots/deploy', json=body,
		                 headers={'authorization': f'Bearer {token}'})
		# PHEOC is not reachable from a test, so the transport fails — and that is the assertion:
		# the route got as far as pushing, rather than 422-ing on a recommendation it never built.
		assert r.status_code in (200, 502), r.text
		if r.status_code == 200:
			assert r.json()['feed'] == 'resource_deployment'


async def test_the_deploy_route_answers_a_map_with_nothing_to_recommend() -> None:
	"""A map with no cluster and no isolated hotspot has nothing to deploy against. The transport
	refuses an empty batch on purpose, so the route names the reason rather than surfacing that
	refusal as though the caller had sent something malformed."""
	from afya.service import build_services, create_app
	services = build_services()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(services)),
	                             base_url='http://t') as c:
		body = [_cell('c1', 'Busia', 10_000, fever_reports=1).model_dump(mode='json')]
		token = await _county_officer(c)
		r = await c.post('/ai/hotspots/deploy', json=body,
		                 headers={'authorization': f'Bearer {token}'})
		assert r.status_code == 200, r.text
		assert r.json()['recommendations'] == 0 and 'nothing to recommend' in r.json()['note']


def test_the_floor_is_still_ten_and_the_cell_is_still_the_denominator() -> None:
	"""The privacy rule is unchanged by any of this: §AI-001's "Minimum cell size of 10 to prevent
	re-identification" is the same constant, and `population` is what it tests."""
	assert MIN_CELL_SIZE == 10
	svc = AIService()
	out = svc.hotspots([_cell('big', 'Busia', 10_000, fever_reports=900),
	                    _cell('mid', 'Busia', 10_000, fever_reports=5),
	                    _cell('small', 'Busia', 9, fever_reports=9)])
	assert out.suppressed_cells == 1 and {h.cell_id for h in out.hotspots} == {'big'}
