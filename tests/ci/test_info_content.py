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


async def test_a_rendition_travels_with_its_article_and_is_not_its_own_entry() -> None:
	"""§INF-003's and §INF-008's Format cells — illustrations, audio versions, video versions, audio
	clips — as served. A rendition is not an item a reader opens: its body is empty by construction,
	so a list entry for one is a blank card beside the article it belongs to. It reaches the client as
	`renditions` on the article instead, which is also what lets a client know an audio version exists
	before it has rendered the text."""
	from afya.info.views import ContentFormat

	svc = InfoService()
	lib = svc.library('en')
	assert lib, 'the corpus must serve something'
	# No served entry is a rendition, and none is blank — the two are the same defect from either end.
	assert all(c.rendition_of is None for c in lib), 'a rendition must not be a library entry'
	assert all(c.body.strip() for c in lib), 'a blank card is not content'
	# Every rendition points at a parent that is actually served, and carries a file.
	served = {c.slug for c in lib}
	renditions = [c for c in svc._content.values() if c.rendition_of is not None]
	assert renditions, 'the corpus must carry at least one rendition or the format cells are empty'
	for r in renditions:
		assert r.rendition_of in served, f'{r.slug} is a rendition of nothing served'
		assert r.media_ref, f'{r.slug} names no file'
		assert not r.format.is_text, f'{r.slug} is a text format and should be an article'
	# And the lookup returns them by parent, so a client can render the article with its renditions.
	parent = next(c for c in lib if svc.renditions_of(c.slug))
	attached = svc.renditions_of(parent.slug)
	assert attached and all(a.rendition_of == parent.slug for a in attached)
	assert {a.format for a in attached} <= set(ContentFormat)


async def test_the_library_route_serves_renditions_under_their_parent() -> None:
	"""The route, not just the service: `renditions` is a key on each served article, with the format
	and the file. A client that had to ask a second time would render the text before knowing it had
	an audio version, which is the reason the two are one payload."""
	from afya.info.views import ContentFormat

	app = create_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		rows = (await c.get('/info/library?lang=en')).json()
	assert rows
	assert all('renditions' in r for r in rows), 'every article carries the key, empty or not'
	with_media = [r for r in rows if r['renditions']]
	assert with_media, 'at least one article must carry a rendition or the format cells are unserved'
	# The non-text formats, read off the enum: a hand-written set here would have to be widened every
	# time a format is added, and the one that is not widened is the one that goes unchecked.
	non_text = {f.value for f in ContentFormat if not f.is_text}
	for row in with_media:
		for rend in row['renditions']:
			assert rend['format'] in non_text, rend
			assert rend['media_ref'] and rend['title'], rend
			assert 'INF-' not in rend['media_ref'], 'a spec code must not reach a file path'


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
	"""§6.5's workflow and staleness audit as routes, not as a paragraph.

	The walk is one arrow read across the two rows of a slug, which is what makes the six steps one
	sequence. The English row is the source text, so it goes draft → clinical review → published and
	has no translation step to walk; the Swahili row is created at `translation` and carries
	back-translation → community validation → published. The two verification stages are gated on
	their evidence, so each is refused until its record is on file.
	"""
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
		# An English row has no translation step: the source text cannot be rendered back into itself.
		assert (await c.post('/info/content/x/advance?to=translation', headers=h)).status_code == 422
		for stage in ('clinical_review', 'published'):
			assert (await c.post(f'/info/content/x/advance?to={stage}', headers=h)).status_code == 200
		assert 's' in {r['slug'] for r in (await c.get('/info/library?lang=en')).json()}, 'published content is served'
		# The translated row enters the workflow at `translation` and cannot leave it without evidence.
		assert (await c.post('/info/content', json=_governed(item_id='x-sw', lang='sw', stage='translation'), headers=h)).status_code == 200
		assert (await c.post('/info/content/x-sw/advance?to=back_translation', headers=h)).status_code == 422
		back = {'item_id': 'x-sw', 'translated_by': 'MoH translator', 'back_translated_by': 'WHO verifier',
		        'back_translation': 'b'}
		assert (await c.post('/info/content/back-translation', json=back, headers=h)).status_code == 200
		assert (await c.post('/info/content/x-sw/advance?to=back_translation', headers=h)).status_code == 200
		# Community validation cannot precede the back-translation the community is shown.
		assert (await c.post('/info/content/community-validation', json={
			'item_id': 'x-sw', 'validated_by': 'Elder A', 'validator_role': 'community elder'}, headers=h)).status_code == 200
		assert (await c.post('/info/content/x-sw/advance?to=community_validation', headers=h)).status_code == 200
		assert (await c.post('/info/content/x-sw/advance?to=published', headers=h)).status_code == 200
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
