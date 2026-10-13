"""§INF-007 — a status feed with a reader, a filter, and nothing that ever wrote one.

The section prints six Contents in one sentence: "School closures, border post status, market
closures, water interruptions, road closures affecting facility access, public transport
disruptions." Two were carried — school closures as an `AlertKind` and border posts as §LOC-005's
`BorderPost` — and the other four had no carrier at all.

The gap had a shape worth naming, because it is not the usual one. `GET /alerting/service-status`
already existed and filtered the feed's `service` category; the category already had a preference
mapping (`facility_alerts`) and the socket already fanned out over it. **Nothing produced a
`service` item.** So the screen was correct, wired, reachable, and permanently empty — a read with
no producer, which is the same failure as a capability with no route wearing the opposite coat.

Each gate below is canaried against a planted defect in `canary_inf007.py`.
"""
import httpx
import pytest

from afya.alerts.service import AlertsService
from afya.alerts.views import SERVICE_STATUS_KINDS, STATES_FOR, ServiceStatus
from afya.alerting.service import AlertingService


def _status(status_id: str = 'SS-1', **kw: object) -> ServiceStatus:
	base: dict[str, object] = {
		'status_id': status_id, 'kind': 'market_closure', 'county': 'Busia',
		'name': 'Budalangi market', 'state': 'closed',
		'detail': 'Closed after flooding; the county is assessing the stalls.',
		'affects_facility_access': False, 'source': 'County Public Health Office',
		'verified': True, 'effective_iso': '2026-10-12',
	}
	base.update(kw)
	return ServiceStatus.model_validate(base)


# --- the six Contents ----------------------------------------------------------------------------

def test_the_six_contents_are_a_closed_set_and_each_has_its_own_states() -> None:
	"""§INF-007's sentence names six things, and a status is only useful if its state maps onto a
	decision. One shared vocabulary would let a school be "interrupted", which answers nothing."""
	assert len(SERVICE_STATUS_KINDS) == 6, 'the section prints six Contents'
	assert set(STATES_FOR) == set(SERVICE_STATUS_KINDS), 'every kind needs states and no kind is extra'
	for kind, states in STATES_FOR.items():
		assert states, f'{kind} has no state a caller could send'
		assert len(set(states)) == len(states), f'{kind} lists a state twice'
	with pytest.raises(Exception, match='market_closure'):
		_status(kind='road_works')


def test_a_state_the_kind_cannot_be_in_is_refused() -> None:
	"""A school is open or closed. `restricted` is a border-post and road state, and a market that
	reports itself "restricted" is a status whose reader cannot tell whether to go."""
	with pytest.raises(Exception, match='is open/closed, not'):
		_status(kind='market_closure', state='restricted')
	assert _status(kind='border_post', state='restricted').state == 'restricted'
	assert _status(kind='water_interruption', state='restored').state == 'restored'
	with pytest.raises(Exception, match='is open/closed, not'):
		_status(kind='school_closure', state='interrupted')


def test_the_road_qualifier_is_the_sections_and_is_enforced() -> None:
	"""§INF-007 qualifies exactly one Content — "road closures **affecting facility access**" — and
	the qualifier is the reason the row is in *this* feed. A closure that does not affect reaching
	care is a traffic report, and carrying it here makes the feed's own name a lie."""
	assert _status(kind='road_closure', state='closed', affects_facility_access=True).headline
	with pytest.raises(Exception, match='affecting facility access'):
		_status(kind='road_closure', state='closed', affects_facility_access=False)
	# The other five are unqualified, so the flag is free on them.
	assert _status(kind='market_closure', affects_facility_access=False).body


def test_the_headline_names_the_place_and_the_state() -> None:
	"""The section says "market closures", and a status naming no market is a rumour: the reader
	cannot tell whether it is *their* market, which is the question they opened the screen to ask."""
	row = _status(kind='water_interruption', name='Kisian borehole 4', state='interrupted',
	              affects_facility_access=False)
	assert row.headline == 'Kisian borehole 4: water interruption — interrupted'
	assert 'Kisian borehole 4' in row.body
	access = _status(kind='road_closure', state='closed', affects_facility_access=True)
	assert 'Reaching a health facility is affected.' in access.body
	assert 'Reaching a health facility is affected.' not in row.body


# --- the producer the read was missing -----------------------------------------------------------

async def test_publishing_a_status_writes_the_feed_the_screen_reads() -> None:
	"""The finding, stated as a test. The route filtered the `service` category and nothing wrote
	one, so the screen answered zero however many closures the county had. The producer publishes
	into the feed rather than storing beside it, so the two surfaces are one fact."""
	feed = AlertingService()
	alerts = AlertsService()
	assert [i for i in feed.feed() if i.category == 'service'] == []

	await alerts.publish_status(_status(), feed)
	items = [i for i in feed.feed() if i.category == 'service']
	assert len(items) == 1
	assert items[0].category == 'service' and items[0].county == 'Busia'
	assert items[0].headline == 'Budalangi market: market closure — closed'
	assert items[0].source == 'County Public Health Office'
	# The feed's own preference mapping is what makes it deliverable, and it already existed.
	from afya.alerting.views import governing_preference
	assert governing_preference('service') == 'facility_alerts'


async def test_an_unverified_status_never_reaches_the_feed() -> None:
	"""§ALT-001's Verification clause governs this feed — "all alerts verified before publishing" —
	so an unverified status is refused by the feed rather than by a second copy of the rule written
	in the status service. One rule, one place, which is why `publish_status` delegates."""
	feed = AlertingService()
	with pytest.raises(AssertionError, match='unverified'):
		await AlertsService().publish_status(_status(verified=False), feed)
	assert [i for i in feed.feed() if i.category == 'service'] == []


async def test_a_status_publishes_with_no_feed_wired_and_still_records() -> None:
	"""An unwired feed is a deployment with no broadcast, not a reason to lose the status: the
	service stores what it was given. `feed=None` is passed rather than omitted so the unwired path
	is exercised by the test suite rather than only in a deployment nobody tested."""
	alerts = AlertsService()
	await alerts.publish_status(_status(), None)
	assert alerts.service_status('Busia')[0].state == 'closed'


# --- the current state, as against the log of announcements --------------------------------------

async def test_a_place_that_reopened_has_one_current_status_not_two() -> None:
	"""A feed is a record of what was announced; a status screen answers "can I go there today". A
	market that closed and reopened has one status — open — and a screen listing both would make the
	reader work out which is current from two dates."""
	feed = AlertingService()
	alerts = AlertsService()
	await alerts.publish_status(_status('SS-1', state='closed', effective_iso='2026-10-10'), feed)
	await alerts.publish_status(_status('SS-2', state='open', effective_iso='2026-10-14'), feed)

	assert len([i for i in feed.feed() if i.category == 'service']) == 2, 'the feed keeps both'
	current = alerts.service_status('Busia')
	assert len(current) == 1 and current[0].state == 'open', 'the screen keeps one'
	assert alerts.service_status()[0].effective_iso == '2026-10-14', 'newest first'


async def test_the_county_filter_scopes_the_status_list() -> None:
	"""A status is about a place in a county. A caller asking about Busia must not be shown a
	Kisumu market as though it were near them."""
	alerts = AlertsService()
	await alerts.publish_status(_status('SS-1'), None)
	await alerts.publish_status(_status('SS-2', county='Kisumu', name='Kibuye market'), None)
	assert [s.county for s in alerts.service_status('Busia')] == ['Busia']
	assert len(alerts.service_status()) == 2
	assert alerts.service_status('Garissa') == []


async def test_the_coverage_report_names_all_six_and_counts_what_is_published() -> None:
	"""The same question §INF-006's `absent` answers for the directory: a deployment with no
	road-closure feed should say so on the screen rather than render a section that is empty because
	nobody publishes it."""
	alerts = AlertsService()
	assert set(alerts.status_coverage()) == set(SERVICE_STATUS_KINDS)
	assert set(alerts.status_coverage().values()) == {0}, 'a fresh deployment carries none'
	await alerts.publish_status(_status('SS-1'), None)
	await alerts.publish_status(_status('SS-2', kind='school_closure', name='Budalangi Primary',
	                                    state='closed', affects_facility_access=False), None)
	coverage = alerts.status_coverage()
	assert coverage['market_closure'] == 1 and coverage['school_closure'] == 1
	assert coverage['road_closure'] == 0 and sum(coverage.values()) == 2


# --- end to end through the real app --------------------------------------------------------------

def _worker_token(auth: object, ref: str) -> dict[str, str]:
	"""A CHW token through the app's own PKCE flow — `provision_staff` refuses a role the app issues."""
	import secrets

	from afya.auth.views import PKCETokenRequest, PKCEStart, s256
	from afya.privacy.views import RBACRole
	verifier = secrets.token_urlsafe(64)[:64]
	code = auth.start_pkce(PKCEStart(  # type: ignore[attr-defined]
		client_id='chw-app', redirect_uri='afya://cb', code_challenge=s256(verifier),
		state=ref + '-state')).authorization_code
	token = auth.exchange_pkce(  # type: ignore[attr-defined]
		PKCETokenRequest(authorization_code=code, client_id='chw-app', redirect_uri='afya://cb',
		                 code_verifier=verifier), RBACRole.chw)
	return {'authorization': f'Bearer {token.access_token}'}


async def test_the_route_publishes_and_the_same_route_reads_it_back() -> None:
	"""The wiring, both directions. A producer with no route is a capability nobody can use, and the
	read that had no producer is the defect this section was."""
	from afya.service import build_services, create_app
	services = build_services()
	app = create_app(services)
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		body = _status().model_dump()
		# Guarded: publishing a status reaches every phone in the county.
		assert (await c.post('/alerting/service-status', json=body)).status_code in (401, 403)
		chw = _worker_token(services['auth'], 'chw-1')
		published = await c.post('/alerting/service-status', headers=chw, json=body)
		assert published.status_code == 200, published.text

		read = await c.get('/alerting/service-status?county=Busia')
		assert read.status_code == 200, read.text
		out = read.json()
		assert out['count'] == 1
		assert out['statuses'][0]['name'] == 'Budalangi market'
		assert out['statuses'][0]['state'] == 'closed'
		assert set(out['coverage']) == set(SERVICE_STATUS_KINDS)
		assert out['coverage']['market_closure'] == 1
		# The same fact is on the alert feed, which is the point of publishing rather than storing.
		assert [i for i in out['items'] if i['category'] == 'service']
		# And it is deliverable: the preference that governs `service` is one a person can set.
		assert out['items'][0]['headline'] == 'Budalangi market: market closure — closed'

		# A status the kind cannot be in is refused at the route, not stored.
		bad = await c.post('/alerting/service-status', headers=chw,
		                   json={**body, 'state': 'restricted'})
		assert bad.status_code == 422, bad.text
