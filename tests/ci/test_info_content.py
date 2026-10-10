"""§6.2 content library and the INF-002 decision tree, as served.

The library was implemented and seeded but had no route, so Tier-1 health information no client
could read; the seed ids embed spec codes (`INF-003-en`), which must not reach a screen.
"""
import httpx

from afya.auth.service import AuthService
from afya.info.service import InfoService
from afya.privacy.views import RBACRole
from afya.service import build_services, create_app


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


def _governed(**overrides: object) -> dict[str, object]:
	body: dict[str, object] = {
		'item_id': 'x', 'title': 't', 'body': 'b', 'lang': 'en', 'harmony_tag': 'official', 'slug': 's',
		'owner': 'MoH Health Promotion Unit', 'reviewer': 'Clinical advisory group',
		'reviewed_on_iso': '2026-10-01', 'version': 1,
	}
	return {**body, **overrides}


async def test_content_must_be_harmonised_and_governed_before_it_is_served() -> None:
	services = build_services()
	auth: AuthService = services['auth']  # type: ignore[assignment]
	sysadmin = auth.provision_staff('ops-0', RBACRole.sysadmin, registrar='MoH ops').access_token
	h = {'authorization': f'Bearer {sysadmin}'}
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		# Publishing content is an operator action: a citizen may not write what the Ministry says.
		anon = (await c.post('/auth/anonymous', json={'subject_ref': 'U1'})).json()['token']
		assert (await c.post('/info/content', json=_governed(), headers={'authorization': f'Bearer {anon}'})).status_code == 403
		# §6.2: no harmony tag, no content.
		bad = await c.post('/info/content', json=_governed(harmony_tag=None), headers=h)
		assert bad.status_code == 422, 'content with no harmony tag must be refused'
		# §6.5: no owner, reviewer, date or version, no item — refused by the model, not by a check.
		for missing in ('owner', 'reviewer', 'reviewed_on_iso', 'version'):
			body = _governed()
			del body[missing]
			assert (await c.post('/info/content', json=body, headers=h)).status_code == 422, f'{missing} is required'
		assert (await c.post('/info/content', json=_governed(), headers=h)).status_code == 200


async def test_the_workflow_and_staleness_audit_are_reachable() -> None:
	"""§6.5's workflow and staleness audit as routes, not as a paragraph. The item is written as a
	draft, advanced one step at a time, and only becomes servable at `published`."""
	services = build_services()
	auth: AuthService = services['auth']  # type: ignore[assignment]
	sysadmin = auth.provision_staff('ops-0', RBACRole.sysadmin, registrar='MoH ops').access_token
	auditor = auth.provision_staff('ops-1', RBACRole.auditor, registrar='MoH ops').access_token
	h = {'authorization': f'Bearer {sysadmin}'}
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		assert (await c.post('/info/content', json=_governed(stage='draft'), headers=h)).status_code == 200
		served = {r['slug'] for r in (await c.get('/info/library?lang=en')).json()}
		assert 's' not in served, 'a draft must not be served'
		# A jump to published is refused; the walk is one step at a time.
		assert (await c.post('/info/content/x/advance?to=published', headers=h)).status_code == 422
		for stage in ('clinical_review', 'translation', 'back_translation', 'community_validation', 'published'):
			assert (await c.post(f'/info/content/x/advance?to={stage}', headers=h)).status_code == 200
		assert 's' in {r['slug'] for r in (await c.get('/info/library?lang=en')).json()}, 'published content is served'
		# The governance view is auditor-scoped and names the staleness audit.
		assert (await c.get('/info/content/governance', headers=h)).status_code == 403
		gov = (await c.get('/info/content/governance?today_iso=2026-10-10', headers={'authorization': f'Bearer {auditor}'})).json()
		assert gov['workflow'][-1] == 'published' and gov['cadence_days'] == 30
		assert any(i['item_id'] == 'x' and i['owner'] for i in gov['items'])


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
