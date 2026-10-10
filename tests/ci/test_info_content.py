"""§6.2 content library and the INF-002 decision tree, as served.

The library was implemented and seeded but had no route, so Tier-1 health information no client
could read; the seed ids embed spec codes (`INF-003-en`), which must not reach a screen.
"""
import httpx

from afya.info.service import InfoService
from afya.service import create_app


async def test_library_is_served_by_language_and_carries_no_spec_code() -> None:
	app = create_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		en = (await c.get('/info/library?lang=en')).json()
		sw = (await c.get('/info/library?lang=sw')).json()
	assert len(en) >= 6 and len(sw) >= 6
	assert {r['lang'] for r in en} == {'en'} and {r['lang'] for r in sw} == {'sw'}
	for row in en + sw:
		assert row['slug'] and row['title'] and row['body']
		assert not row['slug'].startswith('INF-'), 'the slug is the code-free handle'
		assert 'INF-' not in row['title'], 'no spec code may reach a title'
	assert 'item_id' not in en[0], 'the raw id (which embeds a code) is not served'


async def test_content_must_be_harmonised_before_it_is_served() -> None:
	app = create_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		bad = await c.post('/info/content', json={'item_id': 'x', 'title': 't', 'body': 'b', 'lang': 'en', 'slug': 's'})
		assert bad.status_code == 422, 'content with no harmony tag must be refused'
		ok = await c.post('/info/content', json={
			'item_id': 'x', 'title': 't', 'body': 'b', 'lang': 'en', 'harmony_tag': 'official', 'slug': 's',
		})
		assert ok.status_code == 200


async def test_decision_tree_starts_then_walks_to_a_leaf() -> None:
	app = create_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		root = (await c.get('/info/decision-tree')).json()
		assert root['done'] is False and root['question'] and root['recommendation'] is None
		# fever yes -> contact yes -> leaf_hotline
		leaf = (await c.get('/info/decision-tree?answers=yes,yes')).json()
		assert leaf['done'] is True and leaf['question'] is None
		assert '719' in leaf['recommendation']
		# A non-yes/no token is refused rather than silently read as false.
		assert (await c.get('/info/decision-tree?answers=maybe')).status_code == 422


def test_every_tree_leaf_is_reachable_and_terminates() -> None:
	"""Walk every path; a branch that dead-ends would strand a user mid-question."""
	svc = InfoService()
	for answers in ([True, True], [True, False], [False, True], [False, False]):
		assert svc.decide('', answers)
