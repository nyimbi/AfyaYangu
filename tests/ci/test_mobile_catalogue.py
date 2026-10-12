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
# Empty as of §MED-004's follow-up, which fixed all six: `Booking`/`FairnessAudit` split into a
# request and a result so the verdict stopped being an input, `LocationPoint` and `WHO5` had their
# forms reshaped to the model, and two were renames the catalogue had simply got wrong. It stays a
# dict rather than being deleted, because the gate below is what makes the next one visible.
_UNFILLABLE: dict[str, str] = {}


def _missing_body_fields(path: str, offered: set[str], required: set[str]) -> set[str]:
	"""The comparison, as a function, so it can be driven against inputs the live catalogue lacks.

	A path placeholder is filled by the client's own routing, not by a body field — `book_appointment`
	posts to `/facilities/{facility_id}/booking` and the model's `facility_id` is the same value the
	URL already carries, so a form that does not offer it is complete. The exemption changes no
	verdict anywhere in the current catalogue, which is exactly why it is extracted: an unexercised
	branch inside a gate is a branch nobody has watched fail.
	"""
	return required - offered - {seg[1:-1] for seg in path.split('/') if seg.startswith('{')}


def _resolved_path(path: str, offered: dict[str, str]) -> str:
	"""The URL a client builds, given each field's value keyed by the field's own name.

	Both shipped clients substitute a placeholder with the value of the field that *names* it —
	Android's `BackendClient.perform` builds `pathValues[f.name]` and replaces `{f.name}`; iOS's
	`Endpoints.buildRequest` matches the token to the field by name and only falls back to position
	when no field carries the token's name. So a field called `id` on a path with `{facility_id}`
	leaves the braces in the URL on one client and lands in the wrong segment on the other. Extracted
	so the substitution can be driven against inputs the live catalogue no longer has.
	"""
	out = path
	for name, value in offered.items():
		out = out.replace('{' + name + '}', value)
	return out


def test_a_path_placeholder_is_named_by_the_field_that_fills_it() -> None:
	"""Canary for the substitution above, on the shapes that were live before the fix."""
	assert _resolved_path('/facilities/{facility_id}/ed-status', {'facility_id': 'F1'}) == '/facilities/F1/ed-status'
	# The defect as it was: a field named `id` filling a `{facility_id}` placeholder.
	assert _resolved_path('/facilities/{facility_id}/ed-status', {'id': 'F1'}) == '/facilities/{facility_id}/ed-status'


async def test_every_path_placeholder_is_backed_by_a_field_of_that_name() -> None:
	"""A path placeholder no field names is a route neither client can reach.

	This is the defect that made eighteen actions unreachable on Android and one on iOS: the field
	was named `id`/`ref` while the placeholder was `{facility_id}`/`{member_ref}`, and Android
	substitutes by name, so the literal `{facility_id}` went to the server — `/facilities/{facility_id}/ed-status`
	returned 500, and the records actions 403. Nothing checked it, because `test_every_action_path_exists_in_app`
	compares the action's path string to the served route, and the *template* matched on both sides.
	"""
	app = create_app(build_services())
	openapi = app.openapi()
	served = {f'{m.upper()} {p}' for p, ops in openapi['paths'].items() for m in ops}
	broken: dict[str, str] = {}
	for act in catalogue():
		placeholders = {seg[1:-1] for seg in act.path.split('/') if seg.startswith('{')}
		if not placeholders:
			continue
		path_fields = {f.name for f in act.fields if f.type == 'path'}
		unbacked = placeholders - path_fields
		if unbacked:
			broken[act.id] = f'{sorted(unbacked)} not named by a path field (has {sorted(path_fields)})'
			continue
		# And the value a client puts in must still land on the served route.
		filled = _resolved_path(act.path, {name: 'V' for name in placeholders})
		if filled != act.path and f'{act.method} {act.path}' not in served:
			broken[act.id] = f'{act.method} {act.path} is not a served route'
	assert broken == {}, f'catalogue paths a client cannot fill: {broken}'
	checked = sum(1 for a in catalogue() if '{' in a.path)
	assert checked >= 60, f'expected the catalogue to carry many path actions, saw {checked}'


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


# Fields a form must not draw, and why. `client_supplied` means the client knows the value and the
# person does not; `server_assigned` means nobody knows it until the request arrives. Both were
# carried as plain fields with a placeholder that read like an instruction ("generated for you"),
# so a form drew an empty box and a required-field check refused the submission for leaving it
# blank — §11.1's "a control the server refuses", in its other direction: a control the form
# demands and nobody can supply.
_UNDRAWABLE_REASONS = {
	'client_supplied': 'the client supplies it from its own identity and no form may draw it',
	'server_assigned': 'the server mints it; a form could only ask a person to invent a key',
}


def _undrawable(field: object) -> bool:
	"""Whether a form must leave this field off the screen, as a function so it can be canaried."""
	return bool(getattr(field, 'client_supplied', False) or getattr(field, 'server_assigned', False))


def test_the_undrawable_check_sees_both_flags() -> None:
	"""Canary, driven on constructed fields because the live catalogue carries one of each."""
	from afya.mobile.actions import MobileField

	assert _undrawable(MobileField(name='subject_ref', label='Me', type='text', client_supplied=True))
	assert _undrawable(MobileField(name='doc_id', label='Reference', type='text', server_assigned=True))
	assert not _undrawable(MobileField(name='slot_iso', label='Appointment time', type='text'))


async def test_no_form_is_asked_for_a_value_it_cannot_have() -> None:
	"""The gate for the class: a required body field the catalogue carries but must not draw.

	`test_every_action_can_fill_the_body_its_route_requires` checks the field is *offered*. This
	checks the other half — that a field the form is told to hide is not one the route requires.
	`entry_id` was both: the model required it, the catalogue carried it with the placeholder
	"generated for you", and the clients hide an undrawn field, so the submission went without it and
	the server answered 422 naming a field the person had no control for.
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

	broken: dict[str, str] = {}
	checked = 0
	for act in catalogue():
		ep = by_route.get((act.method, act.path))
		if ep is None:
			continue
		# Only `server_assigned` is checked here. A `client_supplied` field is also undrawn, and it
		# is *meant* to be required and *meant* to fill a path segment: the client injects its own
		# subject into both, which is what `perform`/`buildRequest` do before the request goes out.
		# A server-assigned reference is the opposite — nobody has it until the request arrives — so
		# requiring one, or asking it to fill a URL, is a request no form can complete.
		assigned = {f.name for f in act.fields if f.server_assigned}
		checked += len(assigned)
		if not assigned:
			continue
		placeholders = {seg[1:-1] for seg in act.path.split('/') if seg.startswith('{')}
		hidden_and_needed = assigned & placeholders
		if hidden_and_needed:
			broken[act.id] = f'{sorted(hidden_and_needed)} server-assigned but fills the path'
		for param in inspect.signature(ep).parameters.values():  # type: ignore[arg-type]
			ann = param.annotation
			if not (isinstance(ann, type) and issubclass(ann, BaseModel)):
				continue
			required = {k for k, v in ann.model_fields.items() if v.is_required()}
			clash = assigned & required
			if clash:
				broken[act.id] = f'{sorted(clash)} required by {ann.__name__} but hidden from the form'
	assert broken == {}, f'forms asked for values they cannot have: {broken}'
	assert checked >= 10, f'expected the catalogue to carry many server-assigned fields, saw {checked}'


async def test_every_server_assigned_field_has_a_default_on_its_model() -> None:
	"""A field the form hides is only safe if omitting it is a complete request.

	Marking a field `server_assigned` without defaulting it on the model would move the 422 rather
	than remove it: the form stops asking, the model still requires, and every submission fails.
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

	broken: dict[str, str] = {}
	checked = 0
	for act in catalogue():
		assigned = {f.name for f in act.fields if f.server_assigned}
		if not assigned:
			continue
		ep = by_route.get((act.method, act.path))
		if ep is None:
			continue
		for param in inspect.signature(ep).parameters.values():  # type: ignore[arg-type]
			ann = param.annotation
			if not (isinstance(ann, type) and issubclass(ann, BaseModel)):
				continue
			for name in sorted(assigned):
				mf = ann.model_fields.get(name)
				if mf is None:
					continue
				checked += 1
				if mf.is_required():
					broken[act.id] = f'{ann.__name__}.{name} is marked server_assigned but required'
	assert broken == {}, f'server-assigned fields a request must still carry: {broken}'
	assert checked >= 10, f'expected the catalogue to carry many server-assigned fields, saw {checked}'
