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


# --- The guard/subject crossing ------------------------------------------------------------------
#
# The reachability gate above crosses *fields against places a value can go*. This one crosses the
# same fields against a different question: does the route's guard **require** a subject the form
# has no way to name? It is a separate gate because the failure is invisible to the first one — a
# route whose guard 422s for a missing subject accepts every field the form offers, so `_unreachable`
# reports it clean while the form cannot be submitted.

# Names a client puts a subject under. `_s()` marks `subject_ref` `client_supplied`, which is what
# makes both clients inject the device's own subject; a member or guardian ref is drawn instead.
# `ref` is here for the same reason `test_self_scope.py` carries it: it is the last-resort spelling
# a route uses for a person's own handle (`/triage/{ref}/diary/trend`), and a gate that omits it
# reports every one of those routes as nameless when the form fills the placeholder correctly.
SUBJECT_NAMES: frozenset[str] = frozenset({
	'subject_ref', 'member_ref', 'guardian_ref', 'family_ref', 'chw_ref', 'ref',
})

# Actions whose route guard requires a subject the form cannot supply, each with the reason it is
# not a defect. Empty is the goal; an entry is a decision someone made and can be argued with.
UNNAMABLE_SUBJECT_ALLOWED: dict[str, str] = {}


def _guard_of(method: str, path: str) -> Any:
	"""The guard function a route depends on, or None. The closure is where its settings live.

	`test_self_scope.py` reads the same graph for the guard's *name*; this reads its captured
	arguments, because `require_self(names_subject=False)` and the default are the same guard by
	name and opposite in what they demand.
	"""
	app = _app()
	inner = next((getattr(r, 'app') for r in app.routes if hasattr(getattr(r, 'app', None), 'routes')), app)
	for route in getattr(inner, 'routes', []):
		if getattr(route, 'path', None) != path or method.upper() not in getattr(route, 'methods', set()):
			continue
		for dep in getattr(getattr(route, 'dependant', None), 'dependencies', []):
			name = getattr(dep.call, '__qualname__', '')
			if 'require_self' in name or 'require_self_or_guardian' in name:
				return dep.call
	return None


def _demands_a_subject(method: str, path: str) -> bool:
	"""Whether the route's guard refuses a request that names no subject.

	A guard that binds the subject itself — `names_subject=False` — takes the token's own and needs
	nothing from the form, so an action offering no subject field is complete. The default guard
	reads the subject out of the path, query or body and 422s when it finds none.
	"""
	guard = _guard_of(method, path)
	if guard is None:
		return False
	import inspect
	try:
		bound = inspect.getclosurevars(guard).nonlocals
	except TypeError:
		return True
	if 'names_subject' in bound:
		return bool(bound['names_subject'])
	# `require_self_or_guardian` always demands one: it compares the named member against the
	# caller's wallet, so a request naming nobody has nothing to check.
	return True


def _unsuppliable_subjects(actions: list[Any] | None = None) -> dict[str, str]:
	"""Actions whose route demands a subject and whose form offers no field to carry it."""
	broken: dict[str, str] = {}
	for act in actions if actions is not None else catalogue():
		if not _demands_a_subject(act.method, act.path):
			continue
		offered = {f.name for f in act.fields} | {seg[1:-1] for seg in act.path.split('/') if seg.startswith('{')}
		if not (offered & SUBJECT_NAMES):
			broken[act.id] = f'{act.method} {act.path} requires a subject the form cannot name'
	return broken


def test_every_action_can_name_the_subject_its_guard_requires() -> None:
	"""The gate. A guard that 422s for a missing subject, on a form that offers none, is a form
	whose submit button produces "this request must name the subject it acts for" — a refusal
	naming a control the person was never shown."""
	broken = _unsuppliable_subjects()
	unexplained = {k: v for k, v in broken.items() if k not in UNNAMABLE_SUBJECT_ALLOWED}
	assert unexplained == {}, (
		f'{len(unexplained)} catalogue actions cannot name the subject their route guard requires: '
		f'{unexplained}. Add the field the guard reads, or bind the subject from the token.'
	)
	stale = sorted(set(UNNAMABLE_SUBJECT_ALLOWED) - set(broken))
	assert stale == [], f'excused as unnamable but the form can name it now: {stale}'


def test_the_gate_catches_a_form_that_cannot_name_its_subject() -> None:
	"""Canary against a synthetic action, so it proves the crossing rather than the data.

	The mutation *removes* the subject field rather than renaming it: a name-only comparison would
	let a renamed-but-still-present field through, and the defect is the absence of any field the
	guard will read.
	"""
	from afya.mobile.actions import MobileAction, MobileField

	# `/community/contacts` is `require_self` with the default `names_subject=True`, so it demands
	# one. The first version of this canary named `/records/timeline`, which binds the subject from
	# the token — `_demands_a_subject` correctly returned False and the canary proved nothing about
	# the crossing it exists to test. A canary pointed at a route that does not demand a subject
	# cannot fire, and a canary that cannot fire is a canary that did not run.
	fake = MobileAction(
		id='zzz_nameless', title='Nameless', group='Test', method='POST', path='/community/contacts',
		fields=[MobileField(name='nothing', label='Nothing', type='text')],
	)
	assert 'zzz_nameless' in _unsuppliable_subjects([fake]), 'the gate must flag a form with no subject'
	# And the same route passes once the field the guard reads is offered.
	assert _unsuppliable_subjects([MobileAction(
		id='zzz_named', title='Named', group='Test', method='POST', path='/community/contacts',
		fields=[MobileField(name='subject_ref', label='Me', type='text', client_supplied=True)],
	)]) == {}, 'a form offering the subject must pass'
	# A guard that binds the subject itself needs nothing from the form, so offering none is correct.
	assert _unsuppliable_subjects([MobileAction(
		id='zzz_bound', title='Bound', group='Test', method='GET', path='/chronic/lifestyle',
		fields=[MobileField(name='condition', label='Condition', type='text')],
	)]) == {}, 'names_subject=False must not be read as demanding one'
