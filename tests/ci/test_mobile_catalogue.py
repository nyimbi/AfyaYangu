import httpx

from afya.mobile.actions import FIELD_TYPES, catalogue
from afya.service import build_services, create_app


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


async def test_a_client_supplied_field_is_marked_exactly_where_the_route_binds_a_subject() -> None:
	"""The catalogue must not offer a control the route refuses (§11.1).

	Both directions are checked against the route's own guard, not against a list. A `subject_ref`
	field on a route the server binds to the token (`require_self`) must be marked `client_supplied`
	so no form draws it; a `subject_ref` field on a worker route — where naming another person is the
	whole point — must not be, or the client would overwrite the contact with its own subject.
	"""
	import sys

	sys.path.insert(0, 'tests/ci')
	from test_self_scope import _guard_of, WORKER_ROUTES

	app = create_app(build_services())
	checked = 0
	for act in catalogue():
		guarded = _guard_of(app, act.method, act.path) == 'require_self'
		for fld in act.fields:
			if fld.name != 'subject_ref':
				continue
			checked += 1
			assert fld.client_supplied == guarded, (
				f'{act.id} {act.method} {act.path}: field marked client_supplied={fld.client_supplied} '
				f'but the route is {"self-bound" if guarded else "not self-bound"}'
			)
	assert checked >= 35, f'expected the catalogue to carry a subject on many actions, saw {checked}'
