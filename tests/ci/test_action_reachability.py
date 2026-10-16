"""Gate: every catalogue action's form can actually reach its route.

The defect class is one sentence: **a form that cannot be submitted**. The catalogue describes a
field, a client renders a control for it and puts the value where the catalogue implies, and the
route does not look there. The person fills the form, presses the button, and reads a 422 naming a
field they did set. §11.1 calls this "a control the server refuses", one level below where the
existing gates were pointed.

`test_mobile_catalogue.py` already carries the class, and its `test_no_form_is_asked_for_a_value_it
_cannot_have` reads the route's *body model* to check a hidden field is not one the route requires.
That check has two blind spots, and both of them are the same mistake — it reads one spelling of
"where a field can go":

* it only inspects parameters annotated with a `BaseModel`, so a route taking a bare `list[str]`, a
  scalar or a query parameter is skipped entirely;
* it never asks where the *client* puts a value, so a route that binds a field as a query parameter
  while the catalogue offers it as a body field passes.

**The rule, stated once, is the crossing of two sets.** The catalogue offers fields; a route accepts
them in exactly three places — a path placeholder, the JSON body model, or a query parameter. A
field that is in neither of the three is a control nobody can submit. Both shipped clients agree on
where each goes: `BackendClient.perform` (Kotlin) puts every non-path field into the JSON body for a
write and into the query string for a GET; `Endpoints.buildRequest` (Swift) does the same. So a
write route that reads a field from the query string is a route only a hand-built request can call.

**Read off the OpenAPI document, not off `inspect`.** The document is what a client is generated
from, and it is the only place the three locations appear together: a query parameter is a
`parameters` entry, a body field is a property of the request body's schema, and a placeholder is in
the path. An `inspect`-based reader has to re-derive all three and gets the second one wrong the
moment a route takes a bare list — which is exactly how these defects survived.

**Typed bodies, not open maps.** A `dict[str, str]` body accepts anything, so the document cannot say
which keys a form should send and no check can compare them. That is not a loophole in the gate; it
is the reason three of these routes were unfixable while they stayed open maps. They are typed
models now, and `test_a_write_route_takes_no_open_map_body` keeps them that way.
"""
from functools import lru_cache
from typing import Any

from afya.mobile.actions import catalogue
from afya.service import build_services, create_app

# A body whose schema is an open map or a bare array cannot be compared to a form, so a route that
# keeps one is a route this gate is blind to. Named rather than silently skipped, because "the check
# cannot see this" and "this is fine" are different statements. Empty is the goal; an entry is a
# debt with the route's name on it.
OPEN_BODY_ALLOWED: dict[str, str] = {}


@lru_cache(maxsize=1)
def _app() -> Any:
	"""One app for the module: `create_app` spins up a native engine per call."""
	return create_app(build_services())


@lru_cache(maxsize=1)
def _spec() -> dict[str, Any]:
	return _app().openapi()


def _resolve(schema: Any) -> dict[str, Any]:
	"""A `$ref` followed to its schema, and an absent one read as empty."""
	spec = _spec()
	while isinstance(schema, dict) and '$ref' in schema:
		schema = spec['components']['schemas'][schema['$ref'].split('/')[-1]]
	return schema or {}


def _accepted(method: str, path: str) -> tuple[set[str], str]:
	"""Where a route will look for a value, and what shape its body is.

	Returns the set of names a *client can reach the route with* and a word for the body shape, so
	the gate can say why a field is unreachable rather than only that it is.

	**Method-aware, because the transport is.** A GET has no body: `BackendClient.perform` and
	`Endpoints.buildRequest` both put every non-path field into the query string, so for a GET the
	query parameters are exactly where a client looks. A write is the other way round — both clients
	put every non-path field into the JSON body and send no query string at all. Counting a query
	parameter as accepted on a write is how 32 routes stayed invisible: the route reads a field from
	the query string, the catalogue offers it as a form field, and no client can put it there.
	"""
	op = _spec()['paths'].get(path, {}).get(method.lower())
	if op is None:
		return set(), 'absent'
	accepted = {seg[1:-1] for seg in path.split('/') if seg.startswith('{')}
	params = op.get('parameters') or []
	if method.upper() == 'GET':
		accepted |= {p['name'] for p in params}
	shape = 'none'
	for body in ((op.get('requestBody') or {}).get('content') or {}).values():
		schema = _resolve(body.get('schema'))
		if schema.get('properties'):
			accepted |= set(schema['properties'])
			shape = 'object'
		elif schema.get('additionalProperties'):
			shape = 'map'
		elif schema.get('type') == 'array':
			shape = 'list'
		else:
			shape = 'other'
	return accepted, shape


def _unreachable(actions: list[Any] | None = None) -> dict[str, str]:
	"""Every action with a field its route cannot receive, and the shape that swallowed it.

	An open-map body accepts any key, so a field is never *unreachable* through one — which is the
	honest answer, and the reason the open-map check below is separate rather than folded in here.
	"""
	broken: dict[str, str] = {}
	for act in actions if actions is not None else catalogue():
		accepted, shape = _accepted(act.method, act.path)
		if shape == 'absent':
			continue
		offered = {f.name for f in act.fields}
		if shape == 'map':
			continue
		missing = sorted(offered - accepted)
		if missing:
			broken[act.id] = f'{missing} not accepted by {act.method} {act.path} (body: {shape})'
	return broken


def test_every_field_a_form_offers_is_one_the_route_accepts() -> None:
	"""The gate. A field the route cannot receive is a form that 422s when it is submitted."""
	broken = _unreachable()
	assert broken == {}, (
		f'{len(broken)} catalogue actions offer a field their route cannot receive: {broken}. '
		'A write route binds a field as a path placeholder or a body-model field; both clients put '
		'every non-path field in the JSON body, so a value read from the query string is one no '
		'form can send.'
	)


def test_a_write_route_takes_no_open_map_body() -> None:
	"""An open map cannot be compared to a form, so a route keeping one is a route this gate is blind to.

	`dict[str, str]` was how three of these routes hid: the document said "any object", the check had
	nothing to compare against, and the catalogue offered keys the route's own service call had
	already fixed. Typing the body is what made them checkable, so the absence of one is asserted
	rather than assumed.
	"""
	loose: dict[str, str] = {}
	for act in catalogue():
		_, shape = _accepted(act.method, act.path)
		if shape == 'map' and act.id not in OPEN_BODY_ALLOWED:
			loose[act.id] = f'{act.method} {act.path} takes an open map body'
	# The other direction, so the allow-list cannot accumulate entries for routes that are now typed.
	stale = sorted(set(OPEN_BODY_ALLOWED) - set(loose))
	assert stale == [], f'listed as taking an open body but now typed: {stale}'
	assert loose == {}, f'actions whose body the gate cannot compare: {loose}'


def test_the_gate_catches_a_field_the_route_never_reads() -> None:
	"""Canary, driven against a synthetic action, so it proves the comparison rather than the data.

	The mutation adds a field the route genuinely does not accept — not one spelled differently,
	which is the failure a name-only comparison would let through.
	"""
	from afya.mobile.actions import MobileAction, MobileField

	# A route with a typed body, so the comparison has something to compare against. `/health` is a
	# GET and would be skipped as an absent operation, which is a canary that proves nothing.
	fake = MobileAction(
		id='zzz_invented', title='Invented', group='Test', method='POST', path='/privacy/dpia',
		fields=[MobileField(name='nowhere_to_go', label='Nowhere', type='text')],
	)
	broken = _unreachable([fake])
	assert 'zzz_invented' in broken, 'the gate must flag a field no route accepts'
	assert _unreachable([MobileAction(
		id='zzz_ok', title='Ok', group='Test', method='POST', path='/privacy/dpia',
		fields=[MobileField(name='children_data', label="Children's data", type='bool')],
	)]) == {}, 'a field the route does accept must pass'
