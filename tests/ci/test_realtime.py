"""Behavioural tests for afya.realtime and §15.5 versioning.

Two properties carry the weight here. First, a socket is a transport and never the source of
truth: an alert that fired while a client was offline must still be in the REST feed. Second, a
subscriber's categories are *preference* names while a feed item's category is a *feed* category,
and a mapping that silently fails to match would deliver nothing at all — which is exactly the
bug these tests were written after.
"""
import httpx
import pytest
from starlette.testclient import TestClient

from afya.alerting.views import FEED_CATEGORIES, FEED_PREFERENCE, TOGGLEABLE, FeedItem, governing_preference
from afya.realtime.service import RealtimeService
from afya.realtime.views import KNOWN_CATEGORIES, SocketSubscription
from afya.service import API_VERSIONS, CURRENT_API_VERSION, create_app

ISO = '2026-10-10T10:00:00Z'


def _item(category: str = 'outbreak', county: str | None = 'Busia', item_id: str = 'A1') -> FeedItem:
	return FeedItem(
		item_id=item_id, category=category, headline='Cholera cases rising', body='Boil water.',
		source='MoH', verified=True, published_iso=ISO, county=county,
	)


# --- the two vocabularies, and the mapping between them --------------------------------------

def test_every_feed_category_is_governed_by_a_real_preference() -> None:
	"""The bug this file exists for: an unmapped feed category can never be subscribed to."""
	assert set(FEED_PREFERENCE) == set(FEED_CATEGORIES)
	for feed_category in FEED_CATEGORIES:
		assert governing_preference(feed_category) in TOGGLEABLE, f'{feed_category} governed by an unsettable preference'


def test_known_categories_are_the_feed_scoped_preferences() -> None:
	"""A subscriber may not name a preference no feed item is ever governed by: the server would
	be promising a delivery it cannot make."""
	assert KNOWN_CATEGORIES == frozenset(FEED_PREFERENCE.values())
	assert 'medication_reminders' not in KNOWN_CATEGORIES, 'no feed item is governed by a reminder'
	assert 'exposure_notification' not in KNOWN_CATEGORIES, 'critical alerts are per subject, not broadcast'


def test_governing_preference_refuses_an_unknown_category() -> None:
	with pytest.raises(AssertionError, match='unknown feed category'):
		governing_preference('not_a_real_category')


# --- subscription matching --------------------------------------------------------------------

def test_subscription_matches_by_governing_preference() -> None:
	sub = SocketSubscription(county='Busia', categories=['disease_alerts'])
	assert sub.wants(_item('outbreak')) is True, 'an outbreak is governed by disease_alerts'
	assert sub.wants(_item('flood')) is False, 'a flood is governed by county_alerts'


def test_subscription_county_filter() -> None:
	busia = SocketSubscription(county='Busia', categories=['disease_alerts'])
	assert busia.wants(_item('outbreak', county='Nairobi')) is False
	assert busia.wants(_item('outbreak', county='Busia')) is True
	# A national item (county=None) reaches every county: it is not about somewhere else.
	assert busia.wants(_item('outbreak', county=None)) is True
	assert SocketSubscription(county=None, categories=['disease_alerts']).wants(_item('outbreak', county='Marsabit')) is True


def test_disabled_subscription_receives_nothing() -> None:
	assert SocketSubscription(county=None, categories=['disease_alerts'], enabled=False).wants(_item('outbreak')) is False


# --- fan-out ----------------------------------------------------------------------------------

def test_publish_reaches_only_matching_subscribers() -> None:
	svc = RealtimeService()
	busia = svc.subscribe(SocketSubscription(county='Busia', categories=['disease_alerts']))
	nairobi = svc.subscribe(SocketSubscription(county='Nairobi', categories=['disease_alerts']))
	assert svc.publish(_item('outbreak', county='Busia')) == 1
	assert busia.queue.qsize() == 1 and nairobi.queue.qsize() == 0


def test_publish_refuses_an_unverified_item() -> None:
	"""The REST path refuses these; a socket must not be the way around it (§ALT-001)."""
	svc = RealtimeService()
	svc.subscribe(SocketSubscription())
	unverified = _item().model_copy(update={'verified': False})
	with pytest.raises(AssertionError, match='unverified'):
		svc.publish(unverified)


def test_a_stalled_subscriber_is_dropped_not_awaited() -> None:
	"""One phone that stopped reading must not delay the alert for everyone else in the county."""
	svc = RealtimeService()
	stalled = svc.subscribe(SocketSubscription())
	healthy = svc.subscribe(SocketSubscription())
	for i in range(70):  # past SOCKET_QUEUE_DEPTH
		svc.publish(_item(item_id=f'A{i}'))
		healthy.queue.get_nowait()  # this client is keeping up
	assert stalled.closed is True and stalled.dropped > 0
	assert healthy.closed is False, 'the subscriber that kept reading must keep receiving'
	assert svc.stats().connections == 1
	assert healthy.queue.qsize() == 0, 'the drained queue must not have lost a frame'


def test_unsubscribe_is_idempotent() -> None:
	svc = RealtimeService()
	sub = svc.subscribe(SocketSubscription())
	assert svc.unsubscribe(sub) == 1
	assert svc.unsubscribe(sub) == 0, 'a socket can close twice: client hang-up, then teardown'


def test_stats_are_aggregate() -> None:
	svc = RealtimeService()
	svc.subscribe(SocketSubscription(county='Busia'))
	svc.subscribe(SocketSubscription(county='Busia'))
	svc.subscribe(SocketSubscription(county='Nairobi'))
	svc.publish(_item('outbreak', county='Busia'))
	stats = svc.stats()
	assert stats.connections == 3 and stats.counties == 2 and stats.delivered == 2


# --- the socket itself ------------------------------------------------------------------------

def test_socket_greets_then_delivers_a_matching_alert() -> None:
	app = create_app()
	with TestClient(app) as c:
		with c.websocket_connect('/alerts/socket?county=Busia&categories=disease_alerts') as ws:
			hello = ws.receive_json()
			assert hello['kind'] == 'hello' and hello['subscription']['county'] == 'Busia'
			published = c.post('/alerting/feed', json=_item().model_dump(mode='json')).json()
			assert published['delivered_realtime'] == 1
			frame = ws.receive_json()
			assert frame['kind'] == 'alert' and frame['item']['category'] == 'outbreak'


def test_socket_does_not_deliver_an_unmatched_county() -> None:
	app = create_app()
	with TestClient(app) as c:
		with c.websocket_connect('/alerts/socket?county=Busia&categories=disease_alerts') as ws:
			assert ws.receive_json()['kind'] == 'hello'
			published = c.post('/alerting/feed', json=_item(county='Nairobi').model_dump(mode='json')).json()
			assert published['delivered_realtime'] == 0


def test_socket_refuses_an_unknown_category_and_says_which() -> None:
	app = create_app()
	with TestClient(app) as c:
		with c.websocket_connect('/alerts/socket?categories=medication_reminders') as ws:
			frame = ws.receive_json()
			assert frame['kind'] == 'error' and 'medication_reminders' in frame['message']


def test_default_subscription_names_every_feed_scoped_preference() -> None:
	app = create_app()
	with TestClient(app) as c:
		with c.websocket_connect('/alerts/socket') as ws:
			named = set(ws.receive_json()['subscription']['categories'])
			assert named == set(KNOWN_CATEGORIES)


def test_socket_delivery_leaves_the_rest_feed_intact() -> None:
	"""§16.1: a client that was offline when the alert fired must still find it. The socket is a
	transport, so the durable write cannot depend on anyone being connected."""
	app = create_app()
	with TestClient(app) as c:
		c.post('/alerting/feed', json=_item(item_id='OFFLINE-1').model_dump(mode='json'))
		feed = c.get('/alerting/feed?county=Busia').json()
		assert [i['item_id'] for i in feed] == ['OFFLINE-1']


def test_socket_stats_endpoint() -> None:
	app = create_app()
	with TestClient(app) as c:
		assert c.get('/alerts/socket/stats').json() == {'connections': 0, 'counties': 0, 'delivered': 0}
		with c.websocket_connect('/alerts/socket?county=Busia') as ws:
			ws.receive_json()
			assert c.get('/alerts/socket/stats').json()['connections'] == 1


# --- §15.5 versioning -------------------------------------------------------------------------

@pytest.fixture
async def client() -> httpx.AsyncClient:
	return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url='http://testserver')


@pytest.mark.parametrize('path', ['/health', '/v1/health', '/mobile/actions', '/v1/mobile/actions'])
async def test_versioned_and_bare_paths_both_serve(client: httpx.AsyncClient, path: str) -> None:
	assert (await client.get(path)).status_code == 200


async def test_versioned_path_refuses_what_the_bare_path_refuses(client: httpx.AsyncClient) -> None:
	"""A version is not a way around the guard: the same token rule applies on both spellings."""
	assert (await client.get('/v1/auth/whoami')).status_code == 401
	assert (await client.get('/auth/whoami')).status_code == 401


async def test_index_advertises_the_current_version(client: httpx.AsyncClient) -> None:
	index = (await client.get('/')).json()
	assert index['current_version'] == CURRENT_API_VERSION
	assert index['versions'] == list(API_VERSIONS)


async def test_published_spec_describes_the_api_not_the_mount_table(client: httpx.AsyncClient) -> None:
	"""A facade app publishes an empty spec. Ours must publish the API's own 160-odd operations."""
	spec = (await client.get('/openapi.json')).json()
	assert spec['openapi'].startswith('3.1'), '§15.5 asks for OpenAPI 3.1'
	assert len(spec['paths']) > 100
	assert '/health' in spec['paths'], 'the spec describes real routes, not a mount table'


async def test_versioned_spec_is_served_too(client: httpx.AsyncClient) -> None:
	assert (await client.get('/v1/openapi.json')).status_code == 200


async def test_rate_limiting_still_applies_under_a_version(client: httpx.AsyncClient) -> None:
	"""The middleware lives on the API app, which is mounted — so it must still run per request."""
	headers = {'X-Device-Id': 'flood-versioned'}
	codes = [(await client.get('/v1/health', headers=headers)).status_code for _ in range(170)]
	assert 429 in codes, 'the rate limiter must not be bypassed by pinning a version'
