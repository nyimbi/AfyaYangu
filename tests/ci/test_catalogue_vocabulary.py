"""The catalogue's vocabulary, crossed against what both clients draw and what both send.

A field is a question, and every part of its shape is a claim about a control:

* `type` says which control. A type neither client has a branch for is a field that reaches a
  screen as a bare text box (both clients' `default:` arm), so its value is whatever was typed.
* `options` says the answer is a **closed set**. That is only true if a control offers the set, and
  both clients offer `options` for `select` alone. An `options` list on any other type is a
  vocabulary that lives on the wire and nowhere on the screen.
* `placeholder` is drawn by the text controls — `text`, `textarea`, `int`, `decimal` — and by
  nothing else. A hint on a `bool`, `select` or `file` is a constraint no person ever sees; seven of
  them shipped that way, including one that was the *only* statement of a route's refusal.
* `accept` is the picker's filter, and `form` is the transport of the whole body. A `file` field
  with no accepted type was a picker offering everything; a body half multipart is a request no
  route parses.
* `required` is filled at serve time from the route. A field the server mints can never be required
  by the route, because no form could ever supply it.

The three crossings the audit started from are the same shape one level out: a `condition` naming a
field the action lacks, an `equals_any` naming an answer no control offers, and an `any_of` naming a
field that is not on the form. Each makes a rule that reads as conditional and behaves as dead.

The gates read three things, and the split matters:

1. **The served catalogue** (`marked(catalogue(), required_fields(app))`) — what a client parses.
   These assertions are about the document, and they hold for any future action without a new test.
2. **The client sources** — which controls each client draws, and which it does not. A Python
   assertion cannot observe a Kotlin `when` branch, so the branch is read as text. Both clients are
   read, because a rule one client honours is a rule the other can drop.
3. **The route's own model**, for the one crossing the catalogue cannot see by itself: a condition
   that claims a route refuses a combination. Those are pinned in `test_conditional_required.py`;
   this file pins that the *vocabulary* a condition is written in is one the form can produce.
"""
import pathlib

from afya.access.forms import required_fields
from afya.mobile.actions import MobileAction, catalogue, crossings, marked
from afya.service import build_services, create_app

REPO = pathlib.Path(__file__).resolve().parents[2]
KOTLIN = REPO / 'android/app/src/main/java/ke/go/health/afyayangu/ActionsActivity.kt'
SWIFT = REPO / 'ios/AfyaYangu/Features.swift'
SWIFT_WIRE = REPO / 'ios/AfyaYangu/Endpoints.swift'

# The types each client draws a text box for, and therefore the only types whose `placeholder` is
# on a screen. `list` and `path` are text boxes too — a list is comma text that the encoder splits,
# a path is a URL segment — and both fall into the clients' text arm. Read from the sources below,
# but stated here as the claim the sources are checked against: a client that grows a fifth text
# arm must update this line, which is the point.
TEXT_TYPES = ('text', 'textarea', 'int', 'decimal', 'list', 'path')


def _served() -> list[dict]:
	"""The whole catalogue as a client receives it, `required` marked from the routes."""
	app = create_app(build_services())
	return [a.model_dump(mode='json') for a in marked(catalogue(), required_fields(app))]


def _drawn(act: dict) -> list[dict]:
	"""The fields a form draws: a client-supplied subject and a server reference are not questions."""
	return [f for f in act['fields']
	        if not f.get('client_supplied') and not f.get('server_assigned')]


# --- what each client actually draws -----------------------------------------------------------

def test_both_clients_draw_a_control_for_every_field_type_the_catalogue_can_emit() -> None:
	"""Every type has a branch, and the branches are named, not fallen into.

	Both clients end their switch with `default:` — a text box — so an unknown type is not a
	missing control, it is a control that accepts anything. That is the failure this gate is about:
	`list` on Android fell into `default` and the comma text was sent as one string until `typed()`
	grew a branch for it. A type the catalogue can emit and a client does not name is a field whose
	wire shape is the client's guess.
	"""
	kotlin = KOTLIN.read_text()
	swift = SWIFT.read_text()
	# Android's renderer: one branch per type, and the ones it does not name are text boxes.
	for t in ('bool', 'select', 'file', 'textarea', 'int', 'decimal'):
		assert f'"{t}" ->' in kotlin, f'Android has no branch for {t!r}'
	# Swift's renderer: the same, and its `default` arm is the text box.
	for t in ('bool', 'select', 'textarea', 'file'):
		assert f'case "{t}":' in swift, f'iOS has no branch for {t!r}'
	# A `list` is not its own control on either client: it is text that is split into an array, so
	# the branch that matters is the *encoder's*, asserted below.
	assert 'case "list":' in SWIFT_WIRE.read_text(), 'iOS does not name `list` in its wire encoder'
	assert '"list" -> JSONArray(' in kotlin, 'Android does not name `list` in its wire encoder'


def test_options_are_only_where_a_client_offers_a_set() -> None:
	"""`options` on a type neither client offers as a set is a closed vocabulary nobody can select.

	Android offers `options` in its `select` branch and nowhere else; iOS in its `select` branch and
	nowhere else. A path field carrying three slugs was therefore a text box on both, and the route
	refused every near miss with a 422 on a form that looked complete. The fix is in the catalogue:
	either the set is a `select`, or the vocabulary is spelled in the placeholder of a text control.
	"""
	kotlin = KOTLIN.read_text()
	swift = SWIFT.read_text()
	# The claim about the sources: options are read in exactly one branch each.
	assert 'val items = if (f.required) f.options ?: emptyList()' in kotlin, (
		'Android no longer reads options in its select branch, so this gate is checking the wrong client')
	assert 'ForEach(field.options ?? [], id: \\.self)' in swift, (
		'iOS no longer reads options in its select branch, so this gate is checking the wrong client')
	bad = [f"{a['id']}.{f['name']} ({f['type']})" for a in _served() for f in a['fields']
	       if f.get('options') and f['type'] != 'select']
	assert bad == [], (
		'fields offer a closed set on a type neither client draws a chooser for, so the value is '
		f'typed past the vocabulary: {bad}')


def test_a_placeholder_is_only_where_a_client_draws_it() -> None:
	"""A hint on a toggle, a picker or a file button is a constraint that exists on no screen.

	Seven placeholders shipped on `bool` and `select` fields — "yes if you cannot book ahead" on a
	toggle, "wifi" on a picker, "optional" on three more — and neither client draws a hint on either
	control, so each was prose in the served document and nothing on the phone. `_a()` now refuses
	the combination at construction; this is the same claim read off the served document, so a
	catalogue built elsewhere cannot ship one.
	"""
	kotlin = KOTLIN.read_text()
	swift = SWIFT.read_text()
	# The claim about the sources: only the text controls carry a hint.
	assert 'hint = f.placeholder' in kotlin and 'text = f.placeholder' not in kotlin
	assert 'field.placeholder.map' in swift
	bad = [f"{a['id']}.{f['name']} ({f['type']})" for a in _served() for f in a['fields']
	       if f.get('placeholder') and f['type'] not in TEXT_TYPES]
	assert bad == [], f'placeholders on controls that do not draw one: {bad}'
	# And the other direction: the type whose whole job is a hint still has them, so the rule above
	# is not passing because nobody writes placeholders any more.
	hinted = {f['type'] for a in _served() for f in a['fields'] if f.get('placeholder')}
	assert hinted, 'no placeholder anywhere — the gate above would pass vacuously'
	assert hinted <= set(TEXT_TYPES), hinted


def test_a_file_is_a_picker_with_an_accepted_type_in_a_multipart_body() -> None:
	"""A `file` is a part, not a value: it needs a filter for the picker and a form body to ride in.

	Both clients choose their picker from `accept` (iOS picks the photo library for an image and the
	document picker otherwise; Android passes it as the intent's type), and both send multipart when
	the action is marked `form`. A file field without an accepted type offered every file on the
	device, and a file action without `form` was sent as JSON and refused before the handler ran.
	"""
	kotlin = KOTLIN.read_text()
	swift = SWIFT.read_text()
	assert 'a.fields.firstOrNull { it.type == "file" }?.accept ?: "*/*"' in kotlin, (
		'Android does not read the file field’s accept for its picker')
	assert '(field.accept ?? "").hasPrefix("image")' in swift, (
		'iOS does not choose its picker from the file field’s accept')
	assert 'action.fields.contains(where: { $0.form == true })' in SWIFT_WIRE.read_text(), (
		'iOS does not read the server’s form mark for its transport')
	assert 'val form = a.fields.any { it.form }' in kotlin, (
		'Android does not read the server’s form mark for its transport')

	bad: list[str] = []
	for act in _served():
		files = [f for f in act['fields'] if f['type'] == 'file']
		for f in files:
			if not f.get('accept'):
				bad.append(f"{act['id']}.{f['name']}: a file with no accepted type")
			if not f.get('form'):
				bad.append(f"{act['id']}.{f['name']}: a file outside a multipart body")
		if files and not all(f.get('form') for f in act['fields']):
			bad.append(f"{act['id']}: a multipart body with JSON fields in it")
	assert bad == [], f'file fields a client cannot supply: {bad}'
	assert any(f['type'] == 'file' for a in _served() for f in a['fields']), (
		'no file field anywhere — this gate would pass vacuously')


def test_a_list_is_sent_as_an_array_by_both_clients() -> None:
	"""`type='list'` is a comma-separated *text* control and a JSON *array* on the wire.

	The route's model is `list[str]`, so a client that sent the comma text would be refused. Android
	splits in `typed()`; iOS splits in `jsonValue` and joins it back only where the transport is a
	query string or a form part. Both halves are read, because a client can encode correctly in one
	transport and not the other.
	"""
	kotlin = KOTLIN.read_text()
	assert '"list" -> JSONArray(raw.split(",").map { it.trim() }.filter { it.isNotEmpty() })' in kotlin, (
		'Android sends a list as text rather than as an array')
	swift = SWIFT_WIRE.read_text()
	assert 'case "list": return trimmed.split(separator: ",")' in swift, (
		'iOS sends a list as text rather than as an array')
	# A GET carries the array as comma text in the query string, which is the one transport where a
	# repeated parameter would be ambiguous. Both clients do this, and the route reads a list from a
	# query only if the model declares one — so a list field on a GET is a shape to check, not to
	# assume.
	assert 'joined(separator: ",")' in swift
	get_lists = [f"{a['id']}.{f['name']}" for a in _served()
	             if a['method'] == 'GET' for f in a['fields'] if f['type'] == 'list']
	assert get_lists == [], f'list fields on a GET, where the array becomes query text: {get_lists}'


# --- the catalogue's own crossings --------------------------------------------------------------

def test_a_condition_names_a_field_the_form_draws_and_an_answer_a_control_can_produce() -> None:
	"""A condition is only a rule if the form can make it true and the person can see it.

	Three crossings, each a rule that reads as conditional and behaves as dead:

	* `when` naming a field the action does not carry — both clients evaluate the condition against
	  `""` and it never fires;
	* `when` naming a field that is not drawn — the trigger is a subject or a server reference, so
	  no person can answer it;
	* `equals_any` naming a value the trigger cannot produce — a `select` offers its `options`, a
	  `bool` offers `"true"`/`"false"`, and nothing else offers a closed set at all.

	The last two are `crossings()`, the predicate `_a()` refuses to build against — one function,
	two callers. The *drawing* half is this file's own, because the catalogue does not know which
	fields a client chooses not to draw.
	"""
	bad: list[str] = []
	for act in _served():
		drawn = {f['name'] for f in _drawn(act)}
		for f in act['fields']:
			cond = f.get('condition')
			if cond and cond['when'] in {x['name'] for x in act['fields']} and cond['when'] not in drawn:
				bad.append(f"{act['id']}.{f['name']}: names {cond['when']!r}, which no form draws")
	# The shared predicate, over the served document. `marked()` rebuilds each action with
	# `model_copy`, so this reads the same actions the client parses rather than the constructor's
	# private list.
	for act in _served():
		rebuilt = MobileAction.model_validate(act)
		bad += crossings(rebuilt)
	assert bad == [], f'conditions a form cannot satisfy: {bad}'


def test_an_either_or_group_names_fields_the_form_draws_and_none_it_always_demands() -> None:
	"""`any_of` is satisfied by *one* member, so a member nobody can answer makes the group a refusal.

	`marked()` already refuses a group naming a field the action lacks and one the route always
	requires. What it cannot see is the client's own drawing rule: a group whose only members are
	undrawn is a group no form can satisfy, and both clients would refuse every submission.
	"""
	bad: list[str] = []
	for act in _served():
		drawn = {f['name'] for f in _drawn(act)}
		for group in act.get('any_of') or []:
			if not set(group['fields']) & drawn:
				bad.append(f"{act['id']}: any_of {group['fields']} has no drawn member")
			if group.get('when') and group['when'] not in drawn:
				bad.append(f"{act['id']}: any_of gated on {group['when']!r}, which no form draws")
	assert bad == [], f'either/or groups a form cannot satisfy: {bad}'


def test_a_server_assigned_value_is_never_one_the_route_requires() -> None:
	"""A value nobody knows until the request arrives cannot be a value the route refuses without.

	`_auto()` exists so a reference is minted server-side and an omitted field is a complete
	request. A field marked `server_assigned` and *also* required is a request no form can complete:
	the client does not draw it, the route refuses without it, and the refusal names a field the
	person was never shown.
	"""
	bad = [f"{a['id']}.{f['name']}" for a in _served() for f in a['fields']
	       if f.get('server_assigned') and f['required']]
	assert bad == [], f'server-assigned fields the route requires: {bad}'
	# And the marking still happens: the population of server-assigned fields is not empty, so the
	# assertion above is not passing because nothing carries the flag.
	assert any(f.get('server_assigned') for a in _served() for f in a['fields'])


def test_the_whole_vocabulary_is_exercised_by_the_served_catalogue() -> None:
	"""A canary for the gates above: every type and every flag must appear somewhere.

	Six of the assertions above are of the form "no field does X". A catalogue that stopped emitting
	`options`, `condition`, `distinct_from` or `file` would satisfy all of them while testing nothing.
	"""
	served = _served()
	types = {f['type'] for a in served for f in a['fields']}
	assert {'select', 'list', 'path', 'file', 'bool', 'textarea', 'int', 'decimal', 'text'} <= types, types
	flags = {k for a in served for f in a['fields'] for k in ('options', 'placeholder', 'condition',
	                                                          'distinct_from', 'accept', 'form',
	                                                          'server_assigned', 'client_supplied')
	         if f.get(k)}
	assert flags == {'options', 'placeholder', 'condition', 'distinct_from', 'accept', 'form',
	                 'server_assigned', 'client_supplied'}, f'flags no field carries: {flags}'
	conditions = [(a['id'], f['name']) for a in served for f in a['fields'] if f.get('condition')]
	assert len(conditions) >= 4, f'the condition population collapsed to {conditions}'
