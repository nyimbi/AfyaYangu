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
import ast
import pathlib
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
			# **Both** content types. A route taking `kind: EvidenceKind = Form(...)` carries its
			# vocabulary under `multipart/form-data`, not `application/json`, so a reader that knew
			# only the JSON spelling reported four POST selects as unguarded when the document had
			# them all along — `submit_evidence.kind`, `voice_audio.lang`, `voice_audio.purpose` and
			# `whatsapp_voice.voice_note_lang`. The same "one of two spellings" defect, one layer
			# down: this time the spelling is the media type.
			content = (op.get('requestBody') or {}).get('content', {})
			for media in ('application/json', 'multipart/form-data'):
				schema = (content.get(media) or {}).get('schema') or {}
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


# --- the third crossing: a form select against a vocabulary only a handler assert knows -----------
#
# The two gates above compare a form's options against the route's *model*. Both pass on a field
# whose real vocabulary lives in an `assert` inside the handler, because the OpenAPI document serves
# the model and the model took any string. That is how `issue_alert.issued_by` offered `KMD` — the
# model's pattern admitted it and `AlertsService.issue` refused it for all eight `outbreak_*` kinds —
# while every schema-reading check reported clean.
#
# **A vocabulary enforced by an assert rather than by the model has a drift horizon and no symptom.**
# The document, the form and the assert agree on the day they are written; the day one moves, a
# control is a 422 the document promises cannot happen, and nothing fails. So the crossing is made
# here, from the source, in three parts:
#
#   * `_asserted_vocabularies()` reads every closed-set membership assert in `src/afya` — in **both**
#     spellings of the set (an inline tuple and a module-level constant, reached by name), because a
#     reader that knew only the first would report clean on every vocabulary written the second way.
#   * `_guarded_fields()` resolves each to the **model field** it guards, through the enclosing
#     function's annotated parameter. A name-only matcher is not enough: `status` is a field of
#     `ChwCase`, `TaggedEquipment` and `MilestoneReport` at once, and matching by name alone reports
#     five mismatches that are collisions rather than defects.
#   * `test_a_models_vocabulary_is_no_wider_than_the_assert_that_guards_it` asserts the model's
#     declared set is a **subset** of the assert's, and `..._the_form_offers...` asserts the form's
#     options are a **subset** of it too. A value the model admits that no assert admits is a 422 the
#     document promises cannot happen; an option the assert refuses is the same defect one layer up.

SRC = pathlib.Path(__file__).resolve().parents[2] / 'src' / 'afya'


def _derived_collections() -> dict[tuple[str, str], tuple[str, ...]]:
	"""Module-level names bound to a **comprehension over a literal tuple of calls**.

	The third spelling of a closed set, and the one that made this reader necessary: `sync/views.py`
	writes §16.3's matrix as a tuple of `ConflictRule(...)` and then

	    STRATEGY_MATRIX: dict[str, ConflictStrategy] = {r.dataset: r.strategy for r in CONFLICT_RULES}

	so the vocabulary the route's own guard reads (`op.dataset in STRATEGY_MATRIX`) is a *computed*
	name. `_string_collections()` reads only literal collections, so it saw nothing here, and
	`SyncOp.dataset` is a bare `str` in the document as well — the set was invisible from both sides at
	once, which is why the form's hand-copied `SYNC_DATASETS` list could drift with no symptom.

	Scoped to the shape that has no other carrier: a comprehension whose single generator iterates a
	module-level literal tuple/list of calls, keyed by `element.attr`. The enum spelling
	(`[k.value for k in AlertKind]`) is deliberately out — an enum already reaches the document as an
	`enum`, so the schema gate sees it and a second reader would be a duplicate, not a coverage gain.
	"""
	out: dict[tuple[str, str], tuple[str, ...]] = {}
	for path in SRC.rglob('*.py'):
		tree = ast.parse(path.read_text())
		# the literal tuple-of-calls collections this file defines, by name
		literals: dict[str, list[ast.Call]] = {}
		for node in tree.body:
			target: ast.expr | None = None
			value: ast.expr | None = None
			if isinstance(node, ast.AnnAssign):
				target, value = node.target, node.value
			elif isinstance(node, ast.Assign) and len(node.targets) == 1:
				target, value = node.targets[0], node.value
			if not isinstance(target, ast.Name) or not isinstance(value, (ast.Tuple, ast.List)):
				continue
			if value.elts and all(isinstance(e, ast.Call) for e in value.elts):
				literals[target.id] = [e for e in value.elts if isinstance(e, ast.Call)]
		if not literals:
			continue
		for node in tree.body:
			target = None
			value = None
			if isinstance(node, ast.AnnAssign):
				target, value = node.target, node.value
			elif isinstance(node, ast.Assign) and len(node.targets) == 1:
				target, value = node.targets[0], node.value
			if not isinstance(target, ast.Name) or not isinstance(value, ast.DictComp):
				continue
			if len(value.generators) != 1 or not isinstance(value.generators[0].iter, ast.Name):
				continue
			source = literals.get(value.generators[0].iter.id)
			# the key must be `element.attr` on the comprehension's own target
			var = value.generators[0].target
			key = value.key
			if source is None or not isinstance(var, ast.Name):
				continue
			if not (isinstance(key, ast.Attribute) and isinstance(key.value, ast.Name) and key.value.id == var.id):
				continue
			values: list[str] = []
			for call in source:
				kw = next((k for k in call.keywords if k.arg == key.attr), None)
				if kw is None or not isinstance(kw.value, ast.Constant) or not isinstance(kw.value.value, str):
					values = []
					break
				values.append(kw.value.value)
			if values:
				out[(str(path), target.id)] = tuple(values)
	return out


def _string_collections() -> dict[tuple[str, str], tuple[str, ...]]:
	"""Every module-level name bound to a literal collection of strings, keyed `(file, name)`.

	Both spellings of a collection: written out, and computed by a comprehension over one that is
	written out (see `_derived_collections`). A reader that knew only the first reports clean on the
	second, which is how `SyncOp.dataset` stayed invisible.
	"""
	out: dict[tuple[str, str], tuple[str, ...]] = {}
	for path in SRC.rglob('*.py'):
		for node in ast.parse(path.read_text()).body:
			value: ast.expr | None = None
			name: str | None = None
			if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
				value, name = node.value, node.target.id
			elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
				value, name = node.value, node.targets[0].id
			if name is None:
				continue
			if isinstance(value, (ast.Tuple, ast.List, ast.Set)) and value.elts:
				literals = [e.value for e in value.elts
				            if isinstance(e, ast.Constant) and isinstance(e.value, str)]
				if len(literals) == len(value.elts):
					out[(str(path), name)] = tuple(literals)
	out.update(_derived_collections())
	return out


def _models() -> dict[str, dict[str, str]]:
	"""Every model class's annotated fields, by name."""
	models: dict[str, dict[str, str]] = {}
	for path in SRC.rglob('*.py'):
		for node in ast.parse(path.read_text()).body:
			if not isinstance(node, ast.ClassDef):
				continue
			fields = {st.target.id: ast.unparse(st.annotation) for st in node.body
			          if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name)}
			if fields:
				models[node.name] = fields
	return models


@lru_cache(maxsize=1)
def _asserted_vocabularies() -> dict[tuple[str, str], tuple[tuple[str, ...], str]]:
	"""`{(model, field): (values the assert admits, where it is)}` for every closed-set assert.

	Both spellings of the set, and the model resolved through the enclosing function's annotated
	parameter — an assert whose subject cannot be tied to a model is left out and named by the
	coverage floor below, rather than silently compared against a same-named field elsewhere.
	"""
	consts = _string_collections()
	models = _models()
	out: dict[tuple[str, str], tuple[tuple[str, ...], str]] = {}
	for path in sorted(SRC.rglob('*.py')):
		tree = ast.parse(path.read_text())
		for fn in ast.walk(tree):
			if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
				continue
			# the models this function's parameters are annotated with, in order
			params = [ast.unparse(a.annotation).replace('| None', '').replace('None |', '').strip()
			          for a in fn.args.args + fn.args.kwonlyargs + fn.args.posonlyargs
			          if a.annotation is not None]
			for node in ast.walk(fn):
				# Two spellings of the refusal itself, and a reader that knew only the first reports
				# clean on every vocabulary written the second way: `assert x in (...)`, and
				# `if x not in (...): raise HTTPException(422, ...)` — which is how
				# `info_set_dashboard`'s `risk_level` and the review `regime` are enforced. The
				# `not in` branch is taken only when it raises, so a plain filter is not a vocabulary.
				if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
					test = node.test
				elif isinstance(node, ast.If) and isinstance(node.test, ast.Compare) \
						and any(isinstance(op, ast.NotIn) for op in node.test.ops) \
						and any(isinstance(n, ast.Raise) for b in node.body for n in ast.walk(b)):
					test = node.test
				else:
					continue
				if not any(isinstance(op, (ast.In, ast.NotIn)) for op in test.ops):
					continue
				subject = test.left
				field = subject.attr if isinstance(subject, ast.Attribute) else (
					subject.id if isinstance(subject, ast.Name) else None)
				if field is None:
					continue
				coll = test.comparators[0]
				values: tuple[str, ...] | None = None
				label = ''
				if isinstance(coll, (ast.Tuple, ast.List, ast.Set)) and coll.elts:
					literals = [e.value for e in coll.elts
					            if isinstance(e, ast.Constant) and isinstance(e.value, str)]
					if len(literals) == len(coll.elts):
						values, label = tuple(literals), 'literal'
				elif isinstance(coll, ast.Name):
					for (owner_file, name), vals in consts.items():
						if name == coll.id:
							values, label = vals, f'{pathlib.Path(owner_file).name}:{name}'
							break
				if values is None:
					continue
				for model in params:
					if field in models.get(model, {}):
						out[(model, field)] = (values, f'{path}:{node.lineno} ({label})')
	return out


@lru_cache(maxsize=1)
def _route_vocabularies() -> dict[tuple[str, str], tuple[tuple[str, ...], str]]:
	"""`{(route path, field): (values, where)}` for vocabularies on a route's **bare** parameters.

	A route that takes `risk_level: str = Body(...)` has no model, so the reader above cannot attach
	the vocabulary to a field and the crossing is skipped. `info_set_dashboard` is exactly that, and
	it is where the fourth spelling lives: `if risk_level not in ('low','moderate','high'): raise
	HTTPException(422, ...)`. The decorator is what ties the vocabulary to the route here, so a form
	on that path can still be compared.
	"""
	consts = _string_collections()
	out: dict[tuple[str, str], tuple[tuple[str, ...], str]] = {}
	for path in sorted(SRC.rglob('*.py')):
		tree = ast.parse(path.read_text())
		for fn in ast.walk(tree):
			if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
				continue
			route = None
			for dec in fn.decorator_list:
				if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) \
						and dec.func.attr in ('get', 'post', 'put', 'delete', 'patch'):
					if dec.args and isinstance(dec.args[0], ast.Constant) \
							and isinstance(dec.args[0].value, str):
						route = dec.args[0].value
			if route is None:
				continue
			for node in ast.walk(fn):
				if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
					test = node.test
				elif isinstance(node, ast.If) and isinstance(node.test, ast.Compare) \
						and any(isinstance(op, ast.NotIn) for op in node.test.ops) \
						and any(isinstance(n, ast.Raise) for b in node.body for n in ast.walk(b)):
					test = node.test
				else:
					continue
				if not any(isinstance(op, (ast.In, ast.NotIn)) for op in test.ops):
					continue
				subject = test.left
				field = subject.attr if isinstance(subject, ast.Attribute) else (
					subject.id if isinstance(subject, ast.Name) else None)
				if field is None:
					continue
				coll = test.comparators[0]
				values: tuple[str, ...] | None = None
				label = ''
				if isinstance(coll, (ast.Tuple, ast.List, ast.Set)) and coll.elts:
					literals = [e.value for e in coll.elts
					            if isinstance(e, ast.Constant) and isinstance(e.value, str)]
					if len(literals) == len(coll.elts):
						values, label = tuple(literals), 'literal'
				elif isinstance(coll, ast.Name):
					for (owner_file, name), vals in consts.items():
						if name == coll.id:
							values, label = vals, f'{pathlib.Path(owner_file).name}:{name}'
							break
				if values is None:
					continue
				_merge_route_guard(out, route, field, values, f'{path}:{node.lineno} ({label})')
	for route, field, values, where in _enum_constructor_vocabularies():
		_merge_route_guard(out, route, field, values, where)
	for route, field, values, where in _hand_built_model_vocabularies():
		_merge_route_guard(out, route, field, values, where)
	return out


def _merge_route_guard(out: dict[tuple[str, str], tuple[tuple[str, ...], str]],
		route: str, field: str, values: tuple[str, ...], where: str) -> None:
	"""Record a route's guard on a field, **intersecting** with any already recorded.

	A field can be guarded twice, and a value has to pass both. `/info/dashboard/{county}` refuses
	`risk_level` outside `('low','moderate','high')` in the handler *and* builds
	`CountyRisk(risk_level=...)`, whose own pattern admits the same three — but canary 16 narrows the
	handler tuple to two and the model guard, recorded second, used to overwrite it and admit `high`
	again. The gate then passed on a route that refuses the form's value. Intersecting is the only
	semantics that is right under both: the vocabulary a value must satisfy is what every guard
	admits, so the narrowest wins and neither reader can hide the other's narrowing.
	"""
	previous = out.get((route, field))
	if previous is None:
		out[(route, field)] = (values, where)
		return
	shared = tuple(v for v in previous[0] if v in values)
	out[(route, field)] = (shared, f'{previous[1]} & {where}')


def _enum_members() -> dict[str, tuple[str, ...]]:
	"""Every `Enum` class in the tree, by name, as its members' **values**.

	The values, not the member names: a route that does `ConnectionClass(connection)` accepts the
	strings a client sends, and for these enums the two can differ (`high_ebola_suspicion = 'high'`),
	so reading member names would compare a form against a vocabulary no client ever sends.
	"""
	out: dict[str, tuple[str, ...]] = {}
	for path in SRC.rglob('*.py'):
		for node in ast.parse(path.read_text()).body:
			if not isinstance(node, ast.ClassDef):
				continue
			if not any('Enum' in ast.unparse(base) for base in node.bases):
				continue
			values = [st.value.value for st in node.body
			          if isinstance(st, ast.Assign) and isinstance(st.targets[0], ast.Name)
			          and isinstance(st.value, ast.Constant) and isinstance(st.value.value, str)]
			if values:
				out[node.name] = tuple(values)
	return out


def _enum_constructor_vocabularies() -> list[tuple[str, str, tuple[str, ...], str]]:
	"""The seventh spelling: `Enum(value)` inside a `try`, refused by the `except ValueError`.

	`/sync/flush` takes `connection: str = Body('wifi', embed=True)` and then

	    try:
	        conn = ConnectionClass(connection)
	    except ValueError as exc:
	        raise HTTPException(status_code=422, detail=f'unknown connection class {connection}')

	The vocabulary is the enum's member values and it is enforced — probed at the front door,
	`connection='zzz'` is a 422 while the three members are 200. But it is invisible to every reader
	that looks for a comparison: there is none, so the set has no literal to find, and the document
	serves a bare `str` besides. `flush_sync.connection` was unchecked until this reader existed; the
	form and the enum agree, which is luck rather than a gate.

	Scoped to a **bare `str` parameter of the route's own signature**, which is what keeps this from
	matching the ~30 internal `Enum(...)` coercions (`RBACRole(role)` in `require_token`,
	`ConsentCategory(...)` in a label helper) that no form can reach.
	"""
	enums = _enum_members()
	out: list[tuple[str, str, tuple[str, ...], str]] = []
	for path in sorted(SRC.rglob('*.py')):
		tree = ast.parse(path.read_text())
		for fn in ast.walk(tree):
			if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
				continue
			route = None
			for dec in fn.decorator_list:
				if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) \
						and dec.func.attr in ('get', 'post', 'put', 'delete', 'patch'):
					if dec.args and isinstance(dec.args[0], ast.Constant) \
							and isinstance(dec.args[0].value, str):
						route = dec.args[0].value
			if route is None:
				continue
			bare = {a.arg for a in fn.args.args + fn.args.kwonlyargs
			        if a.annotation is not None and ast.unparse(a.annotation).strip() == 'str'}
			for node in ast.walk(fn):
				if not isinstance(node, ast.Try):
					continue
				if not any(h.type is not None and 'ValueError' in ast.unparse(h.type)
				           for h in node.handlers):
					continue
				for call in [n for b in node.body for n in ast.walk(b)]:
					if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
							and call.func.id in enums and call.args):
						continue
					arg = call.args[0]
					field = arg.id if isinstance(arg, ast.Name) else (
						arg.attr if isinstance(arg, ast.Attribute) else None)
					if field is not None and field in bare:
						out.append((route, field, enums[call.func.id],
							f'{path}:{node.lineno} ({call.func.id} member values)'))
	return out


def _model_pattern_vocabularies() -> dict[str, dict[str, tuple[str, ...]]]:
	"""`{model: {field: values}}` for every `Field(pattern=r'^(a|b|c)$')` in the source.

	Read from the **source**, not the OpenAPI document, because the routes that need this reader are
	precisely the ones whose model never reaches the document: a multipart route declares
	`purpose: str = Form('symptoms')` and builds its model inside the handler, so the schema serves a
	bare `str` and the alternation exists only in the class.
	"""
	import re
	out: dict[str, dict[str, tuple[str, ...]]] = {}
	for path in SRC.rglob('*.py'):
		for node in ast.parse(path.read_text()).body:
			if not isinstance(node, ast.ClassDef):
				continue
			fields: dict[str, tuple[str, ...]] = {}
			for st in node.body:
				if not isinstance(st, ast.AnnAssign) or not isinstance(st.target, ast.Name):
					continue
				rendered = ast.unparse(st.value) if st.value is not None else ''
				hit = re.search(r"pattern=r?'\^\(([^)]+)\)\$'", rendered)
				if hit and '|' in hit.group(1):
					fields[st.target.id] = tuple(hit.group(1).split('|'))
			if fields:
				out[node.name] = fields
	return out


def _hand_built_model_vocabularies() -> list[tuple[str, str, tuple[str, ...], str]]:
	"""The eighth spelling: the route builds a model from its own bare parameters.

	`POST /access/voice/audio` takes `purpose: str = Form('symptoms')` — a bare `str` in the signature
	and in the document — and then

	    req = VoiceAudioRequest(subject_ref=subject_ref, lang=lang, purpose=purpose)

	where `VoiceAudioRequest.purpose` is `Field(pattern=r'^(symptoms|note)$')`. The vocabulary is real
	and it is enforced (the model raises inside a `try` and the handler turns that into a 422), but it
	is in a class the route's signature does not mention, so every reader above misses it. The same
	route is multipart, which is why the document is no help either: the two blind spots coincide.

	Scoped to a construction that names at least one of the **route's own parameters**, which is what
	separates a handler assembling its input from the ~hundreds of models built from other models'
	fields.
	"""
	patterns = _model_pattern_vocabularies()
	out: list[tuple[str, str, tuple[str, ...], str]] = []
	for path in sorted(SRC.rglob('*.py')):
		tree = ast.parse(path.read_text())
		for fn in ast.walk(tree):
			if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
				continue
			route = None
			for dec in fn.decorator_list:
				if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) \
						and dec.func.attr in ('get', 'post', 'put', 'delete', 'patch'):
					if dec.args and isinstance(dec.args[0], ast.Constant) \
							and isinstance(dec.args[0].value, str):
						route = dec.args[0].value
			if route is None:
				continue
			params = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
			for call in ast.walk(fn):
				if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
						and call.func.id in patterns):
					continue
				named = {k.arg for k in call.keywords if k.arg} & params
				if not named:
					continue
				for field, values in patterns[call.func.id].items():
					if field in named:
						out.append((route, field, values,
							f'{path}:{call.lineno} ({call.func.id}.{field})'))
	return out


def test_a_form_offers_no_value_a_routes_own_guard_refuses() -> None:
	"""The same crossing for a vocabulary on a bare parameter, where there is no model to attach it to.

	`POST /info/dashboard/{county}` takes `risk_level: str` and refuses anything outside its own
	three with a `raise`, so the document serves a bare `str` and neither the model-based reader nor
	the OpenAPI-based gates can compare it. It agrees today; the check is here because a vocabulary
	enforced by a raise is one no schema reader can see, which is the whole reason this unit exists.
	"""
	guarded = _route_vocabularies()
	# An exact set, for the same reason as the assert reader's: a floor set at the count it guards
	# can never fail, and this one read `>= 1` while the reader was finding three. Losing the enum
	# spelling would drop eight of these eleven and pass a floor.
	assert set(guarded) == {
		('/access/voice/audio', 'purpose'),
		('/analytics/dashboards/{dashboard}', 'dashboard'),
		('/governance/residency/check', 'data_class'),
		('/info/content/governance', 'regime'),
		('/info/content/{item_id}/advance', 'to'),
		('/info/dashboard/{county}', 'risk_level'),
		('/info/decision-tree', 'token'),
		('/rollout/status', 'phase'),
		('/sync/batch', 'connection'),
		('/sync/flush', 'connection'),
		('/sync/policy', 'connection'),
		('/sync/state', 'connection'),
	}, f'route-scoped vocabularies moved: {sorted(guarded)}'
	refused: list[str] = []
	for action in catalogue():
		for field in action.fields:
			if field.type != 'select':
				continue
			hit = guarded.get((action.path, field.name))
			if hit is None:
				continue
			values, where = hit
			extra = sorted(set(field.options or []) - set(values))
			if extra:
				refused.append(f'{action.id}.{field.name}: the form offers {extra}, the guard at {where} '
				               f'admits only {sorted(values)}')
	assert refused == [], f'controls the route refuses: {refused}'


@lru_cache(maxsize=1)
def _model_fields_in_document() -> dict[tuple[str, str], tuple[list[str], str]]:
	"""`{(model, field): (values the document declares, spelling)}` — both spellings, as above."""
	spec = _spec()
	components = spec.get('components', {}).get('schemas', {})
	out: dict[tuple[str, str], tuple[list[str], str]] = {}
	for model, schema in components.items():
		for field, prop in ((schema or {}).get('properties') or {}).items():
			values = _closed_vocabulary(prop, components)
			if values is not None:
				out[(model, field)] = (values, 'enum' if prop.get('enum') else 'pattern')
	return out


def test_a_models_vocabulary_is_no_wider_than_the_assert_that_guards_it() -> None:
	"""The KMD crossing: a value the document admits that no handler assert admits.

	`CommunityAlert.issued_by` was `Field(pattern=r'^(MoH|PHEOC|County|KMD)$')` and
	`AlertsService.issue` asserted `in ('MoH', 'PHEOC', 'County')` for the outbreak kinds. Every
	schema-reading gate passed — the form matched the model, and the model matched the form — while
	the route refused a value the document said it took. A person picked "KMD" from a spinner and read
	a 422 about a field they had set, on a screen the schema had told them was fine.

	The check is a **subset**, not equality: an assert may be narrower than the document on purpose
	(a field the model admits for a read and the handler refuses for a write), but a value no assert
	admits at all is a refusal the document cannot express, and a form built from the document cannot
	warn anyone.
	"""
	asserted = _asserted_vocabularies()
	# The key set is pinned, not floored. A `>= 4` floor was written when the reader found exactly
	# four, so it could never fail: canary 13 stopped naming `ALERT_ISSUERS` and the count fell to
	# four, which passed. A floor set at the count it guards is a gate that asserts nothing, and the
	# whole point of this register is that losing a site is visible. An exact set makes a *new*
	# vocabulary a deliberate acknowledgement too, which is what a coverage register is for.
	assert set(asserted) == {
		('BloodRequest', 'urgency'),
		('ChwProfile', 'provisioned_by'),
		('CommunityAlert', 'issued_by'),
		('PeerAlert', 'verified_by'),
		('SyncOp', 'dataset'),
	}, f'assert-guarded vocabularies moved: {sorted(asserted)}'
	declared = _model_fields_in_document()
	wider: list[str] = []
	for (model, field), (values, where) in sorted(asserted.items()):
		doc = declared.get((model, field))
		if doc is None:
			continue
		unadmitted = sorted(set(doc[0]) - set(values))
		if unadmitted:
			wider.append(f'{model}.{field}: the document admits {unadmitted}, the assert at {where} '
			             f'admits only {sorted(values)}')
	assert wider == [], f'the schema promises values the route refuses: {wider}'


def test_a_form_offers_no_value_the_assert_that_guards_it_refuses() -> None:
	"""The other layer of the same crossing: the form against the assert, not against the model.

	Once the model and the assert agree, the form is the remaining copy. It is compared to the
	assert's set rather than the model's, because the assert is what actually refuses at runtime and
	a form derived from a model that a handler narrows is a form offering values the handler rejects.
	"""
	asserted = _asserted_vocabularies()
	spec = _spec()
	components = spec.get('components', {}).get('schemas', {})
	bodies: dict[tuple[str, str], str | None] = {}
	for path, ops in spec.get('paths', {}).items():
		for method, op in ops.items():
			body = (op.get('requestBody') or {}).get('content', {}).get('application/json', {})
			schema = body.get('schema') or {}
			name = None
			while isinstance(schema, dict) and '$ref' in schema:
				name = schema['$ref'].rsplit('/', 1)[-1]
				schema = components.get(name, {})
			bodies[(method.upper(), path)] = name
	refused: list[str] = []
	for action in catalogue():
		model = bodies.get((action.method.upper(), action.path))
		if model is None:
			continue
		for field in action.fields:
			if field.type != 'select':
				continue
			hit = asserted.get((model, field.name))
			if hit is None:
				continue
			values, where = hit
			extra = sorted(set(field.options or []) - set(values))
			if extra:
				refused.append(f'{action.id}.{field.name}: the form offers {extra}, the assert at {where} '
				               f'admits only {sorted(values)}')
	assert refused == [], f'controls the handler refuses: {refused}'
