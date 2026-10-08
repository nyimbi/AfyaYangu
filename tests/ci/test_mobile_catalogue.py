import httpx

from afya.mobile.actions import FIELD_TYPES, catalogue
from afya.service import create_app


async def test_catalogue_size_and_shape() -> None:
	acts = catalogue()
	assert len(acts) >= 52, 'every backend feature must be exposed'
	for act in acts:
		assert act.id and act.title and act.group
		for fld in act.fields:
			assert fld.type in FIELD_TYPES
	assert {a.id for a in acts}.__len__() == len(acts), 'action ids unique'


async def test_every_action_path_exists_in_app() -> None:
	"""Invariant: catalogue drift is impossible — every action must map to a served route."""
	app = create_app()
	openapi = app.openapi()
	known = set()
	for path, ops in openapi['paths'].items():
		for method in ops:
			known.add(f'{method.upper()} {path}')
	for act in catalogue():
		key = f'{act.method} {act.path}'
		assert key in known, f'catalogue drift: {key} not served'


async def test_field_types_whitelist() -> None:
	for act in catalogue():
		for fld in act.fields:
			assert fld.type in FIELD_TYPES


async def test_actions_endpoint_served() -> None:
	app = create_app()
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		out = (await c.get('/mobile/actions')).json()
		assert len(out) >= 52 and all('fields' in x and 'path' in x for x in out)
