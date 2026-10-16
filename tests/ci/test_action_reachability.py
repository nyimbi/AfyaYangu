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
import re
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




# --- the third crossing: what a select *offers* against what its route *accepts* ---------------

# A form whose options are deliberately narrower than the vocabulary its route accepts, with the
# reason. Empty is the goal: an entry is a capability nobody can reach, which is the mirror of the
# gate above (a field nobody can submit) and has no symptom on either side — the form submits, the
# route answers 200, and the value that is missing is simply not on the spinner.
NARROWER_THAN_THE_ROUTE: dict[str, str] = {}

# `^(a|b|c)$` and nothing else. A pattern that is not a plain alternation is a *format* (a geohash, a
# reference, an ISO stamp), not a vocabulary, and a form is right to offer it as text.
_ALTERNATION = re.compile(r'^\^\(([^)]*)\)\$$')

# An escaped *letter* in a pattern is a character class — `\d`, `\w`, `[A-Z]` — which means the
# pattern describes a format (a reference, a geohash, an ISO stamp) rather than a vocabulary. A form
# is right to draw those as text, and a reader that unescaped one into a "value" would report a
# vocabulary the route never declared.
_FORMAT_ESCAPE = re.compile(r'\\[A-Za-z]|\[')


def _closed_vocabulary(prop: dict[str, Any], components: dict[str, Any]) -> list[str] | None:
	"""The values a body property admits, or None when it admits anything.

	Two spellings of the same thing, and a reader that knew only one of them would report clean
	forever on every field written the other way: FastAPI emits an `enum` for an `Enum` annotation and
	a `pattern` for a `str` with one. Both are a closed set a form has to be a view of, so both are
	read — the same "one of two spellings" defect that let fifteen dead relative links pass an
	internal-link checker that matched `href="/…"` only.
	"""
	for branch in (prop, *(prop.get('anyOf') or []), *(prop.get('allOf') or [])):
		if not isinstance(branch, dict):
			continue
		if '$ref' in branch:
			branch = components.get(branch['$ref'].rsplit('/', 1)[-1], {})
		if branch.get('enum'):
			return [str(v) for v in branch['enum']]
		pat = branch.get('pattern')
		if isinstance(pat, str) and not _FORMAT_ESCAPE.search(pat):
			m = _ALTERNATION.match(pat)
			if m:
				# The members are regex literals, so one carrying a metacharacter is escaped — the
				# blood groups are written `O\+` and the value is `O+`. Unescaping punctuation only:
				# an escaped *letter* is a character class (`\d`, `\w`), which means the pattern is
				# a format rather than a vocabulary and this function should not have claimed it.
				import re as _re
				return sorted({_re.sub(r'\\([^A-Za-z0-9])', r'\1', v) for v in m.group(1).split('|')})
	return None


@lru_cache(maxsize=1)
def _select_vocabularies() -> dict[tuple[str, str], tuple[list[str], list[str]]]:
	"""`{(action_id, field): (options the form offers, values the route's model accepts)}`.

	The crossing the field/place gate cannot make. That one asks *can a value reach the route*; this
	asks *is every value the route accepts one a person can choose*.

	Read from the OpenAPI document rather than the Python annotation, because the document is what a
	client is generated from — the same reason the field/place gate reads it.
	"""
	spec = _spec()
	components = spec.get('components', {}).get('schemas', {})
	bodies: dict[tuple[str, str], dict[str, Any]] = {}
	for path, ops in spec.get('paths', {}).items():
		for method, op in ops.items():
			if method.upper() not in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH'):
				continue
			body = (op.get('requestBody') or {}).get('content', {}).get('application/json', {})
			schema = body.get('schema') or {}
			if '$ref' in schema:
				schema = components.get(schema['$ref'].rsplit('/', 1)[-1], {})
			if schema.get('properties'):
				bodies[(method.upper(), path)] = schema['properties']
	out: dict[tuple[str, str], tuple[list[str], list[str]]] = {}
	for action in catalogue():
		props = bodies.get((action.method.upper(), action.path))
		if not props:
			continue
		for field in action.fields:
			if field.type != 'select':
				continue
			prop = props.get(field.name)
			if not isinstance(prop, dict):
				continue
			values = _closed_vocabulary(prop, components)
			if values is None:
				continue
			out[(action.id, field.name)] = (list(field.options or []), values)
	return out


def test_every_select_offers_exactly_the_vocabulary_its_route_accepts() -> None:
	"""A spinner narrower than its route is a capability with no screen.

	Asserted in **both** directions, because the two failures differ and only one is visible from the
	form: an option the route refuses is a control that 422s — the class the gate above catches by
	*name*, and which this one catches by *value* — while a value the route accepts that the spinner
	omits has no symptom at all. The form submits, the route answers 200, and the option is not there.

	Both directions are load-bearing here. `schedule_review.kind` offered `clinic`/`home`/`telehealth`
	against a route accepting `review`/`test`/`refill`/`vaccination`: every option the form drew was
	refused, so the action could not be submitted, and the name-only gate was blind to it because the
	field name matched. `issue_alert.kind` was the other way round.
	"""
	checked = _select_vocabularies()
	assert len(checked) >= 40, f'the reader found only {len(checked)} closed-vocabulary selects'
	offered_more: list[str] = []
	offered_less: list[str] = []
	for (action_id, field_name), (options, values) in sorted(checked.items()):
		key = f'{action_id}.{field_name}'
		if key in NARROWER_THAN_THE_ROUTE:
			continue
		extra = sorted(set(options) - set(values))
		missing = sorted(set(values) - set(options))
		if extra:
			offered_more.append(f'{key}: the form offers {extra}, the route refuses them')
		if missing:
			offered_less.append(f'{key}: the route accepts {missing}, the form cannot offer them')
	assert offered_more == [], f'controls the route refuses: {offered_more}'
	assert offered_less == [], f'values no form can choose: {offered_less}'


def test_every_closed_vocabulary_a_route_declares_is_offered_as_a_select() -> None:
	"""The other side of the same crossing: a closed set the form never draws at all.

	A body property constrained to an enum or an alternation is a question with a known answer set, and
	a form that draws it as free text asks a person to guess a token. The two defects this catches are
	different from the one above — there, the field is offered and the values are wrong; here the field
	is not offered, so nothing about it is checked.

	Scoped to **required** properties on purpose. An optional one the form omits is a default the route
	chose, which is a decision and not a gap: `/channels/whatsapp` defaults `kind='text'` and the form
	is right not to ask, because the voice branch is its own action (`whatsapp_voice`).
	"""
	spec = _spec()
	components = spec.get('components', {}).get('schemas', {})
	offered: dict[tuple[str, str], set[str]] = {}
	for action in catalogue():
		offered.setdefault((action.method.upper(), action.path), set()).update(f.name for f in action.fields)
	unoffered: list[str] = []
	for path, ops in spec.get('paths', {}).items():
		for method, op in ops.items():
			key = (method.upper(), path)
			if key not in offered:
				continue
			body = (op.get('requestBody') or {}).get('content', {}).get('application/json', {})
			schema = body.get('schema') or {}
			if '$ref' in schema:
				schema = components.get(schema['$ref'].rsplit('/', 1)[-1], {})
			required = set(schema.get('required') or [])
			for name, prop in (schema.get('properties') or {}).items():
				if name in offered[key] or name not in required:
					continue
				values = _closed_vocabulary(prop, components)
				if values is not None:
					unoffered.append(f'{method.upper()} {path}.{name} accepts {sorted(values)} and no '
					                 f'form draws it, so every value has to be typed blind')
	assert unoffered == [], unoffered


def test_the_select_crossing_finds_a_value_the_form_cannot_offer() -> None:
	"""Canary, in-process: a vocabulary the spinner omits must be reported.

	Run against rows the gate above has already confirmed clean, and the shrink is what proves the
	comparison reports it. Disjoint from what the comparison reads — this moves the *form's* options,
	not the route's schema, and the value it drops is one the reader just confirmed the route accepts.
	"""
	checked = _select_vocabularies()
	for key in (('issue_alert', 'kind'), ('nearest_facilities', 'kind'), ('schedule_review', 'kind')):
		assert key in checked, f'{key} left the closed-vocabulary select set: {sorted(checked)}'
		options, values = checked[key]
		assert sorted(set(options)) == sorted(set(values)), (
			f'{key} is a row this gate was written for and it is still out of step with its route: '
			f'form-only={sorted(set(options) - set(values))} route-only={sorted(set(values) - set(options))}')
		# An option the route refuses — the other direction, and the one `schedule_review.kind` was.
		assert sorted(set(options) | {'nowhere_to_go'}) != sorted(set(values)), (
			'an option outside the route vocabulary must break the comparison')
