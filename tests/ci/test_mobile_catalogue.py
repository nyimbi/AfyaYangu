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
	from test_self_scope import _guard_of

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


# Catalogue actions whose form cannot fill a required field of the body model its route takes.
# Each is a defect of one class — "a form that cannot fill its own route" — found by the gate below,
# not a licence to keep them. The dict is the fix queue, and the gate is what keeps it honest: an
# entry that no longer fails must come off, or the list becomes a place to hide new ones.
#
# The route is still reachable by a client that sends the field itself (an app that knows its own
# device id, a batch replay carrying the timestamp the report was made at). What is broken is the
# *form*: the catalogue is the contract a generic client renders, and a form missing a required
# field produces a 422 the person cannot fix because the control is not on the screen.
_UNFILLABLE: dict[str, str] = {
	'book_appointment': '`Booking` requires facility_id (the route already takes it in the path, so '
		'the body duplicates it) and queue_position (the server assigns the place in the queue)',
	'emergency_card': '`EmergencyCard` requires emergency_contacts, but the form offers '
		'emergency_contact as one string — the catalogue and the model disagree on the name',
	'water_advisory': '`WaterQuality` requires ecoli_detected, but the form offers ecoli',
	'fairness_audit': '`FairnessAudit` requires passed and action, both derived by `audit_fairness` '
		'from the axes it is given — neither should be required of a caller',
	'wellbeing_check': '`WHO5` requires scores as a list of five, but the form offers five separate '
		'integers s1..s5 — the catalogue and the model disagree on the shape',
	'log_location': '`LocationPoint` requires geohash and at_iso; the form offers a single `point` '
		'and no timestamp, so a client cannot say where or when',
}


def _missing_body_fields(path: str, offered: set[str], required: set[str]) -> set[str]:
	"""The comparison, as a function, so it can be driven against inputs the live catalogue lacks.

	A path placeholder is filled by the client's own routing, not by a body field — `book_appointment`
	posts to `/facilities/{facility_id}/booking` and the model's `facility_id` is the same value the
	URL already carries, so a form that does not offer it is complete. The exemption changes no
	verdict anywhere in the current catalogue, which is exactly why it is extracted: an unexercised
	branch inside a gate is a branch nobody has watched fail.
	"""
	return required - offered - {seg[1:-1] for seg in path.split('/') if seg.startswith('{')}


def test_the_comparison_exempts_path_placeholders() -> None:
	"""Canary for the exemption above, driven directly because the live data cannot reach it."""
	assert _missing_body_fields('/facilities/{facility_id}/booking', {'slot_iso'}, {'facility_id', 'slot_iso'}) == set()
	assert _missing_body_fields('/facilities/{facility_id}/booking', {'slot_iso'}, {'facility_id', 'queue_position'}) == {'queue_position'}
	# And a placeholder that is *not* in the path is still a gap.
	assert _missing_body_fields('/medicine/stock', {'drug'}, {'facility_id', 'drug'}) == {'facility_id'}


async def test_every_action_can_fill_the_body_its_route_requires() -> None:
	"""The gate that would have caught `report_stock`: a form missing a field its route demands.

	`test_every_action_path_exists_in_app` checks the *route* exists. Nothing checked that the
	catalogue's own field list covers what the route's body model requires, so an action could
	point at a live route and still be unfillable — which is what `report_stock` was: the model
	required `reported_by`, no form offered it, and a client rendering the catalogue's fields got a
	422 naming a field it had no way to set. That is §11.1's "a control the server refuses", one
	level below where it was being checked.
	"""
	import inspect

	from pydantic import BaseModel

	app = create_app(build_services())
	by_route: dict[tuple[str, str], object] = {}

	def walk(routes: object) -> None:
		for r in routes:  # type: ignore[attr-defined]
			if hasattr(r, 'routes'):
				walk(r.routes)
				continue
			for method in getattr(r, 'methods', None) or []:
				by_route[(method, getattr(r, 'path', ''))] = getattr(r, 'endpoint', None)

	walk(app.routes)
	assert by_route, 'the walk found no routes, so this gate would pass vacuously'

	unfillable: dict[str, str] = {}
	for act in catalogue():
		if act.method not in ('POST', 'PUT', 'PATCH'):
			continue
		ep = by_route.get((act.method, act.path))
		if ep is None:
			continue
		offered = {f.name for f in act.fields}
		for param in inspect.signature(ep).parameters.values():  # type: ignore[arg-type]
			ann = param.annotation
			if not (isinstance(ann, type) and issubclass(ann, BaseModel)):
				continue
			required = {k for k, v in ann.model_fields.items() if v.is_required()}
			gap = _missing_body_fields(act.path, offered, required)
			if gap:
				unfillable[act.id] = f'{sorted(gap)} not in the form'

	assert set(unfillable) <= set(_UNFILLABLE), (
		'actions whose form cannot fill their own route: '
		f'{ {k: v for k, v in unfillable.items() if k not in _UNFILLABLE} }'
	)
	stale = sorted(set(_UNFILLABLE) - set(unfillable))
	assert stale == [], f'listed as unfillable but now fills its route: {stale}'
