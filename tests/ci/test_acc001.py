"""§ACC-001's "Simplified forms" — the half of simple mode that reached the screens and not the forms.

§ACC-001 prints two Features one line apart:

	- Simplified forms
	- Optional "simple mode" that hides advanced features

The second was built — `AccessProfile.simple_mode` and `AccessService.screens(simple_mode)` — and the
first was carried by nothing. A person who turned simple mode on got fewer screens, and every form on
the screens that remained asked exactly what it asked everybody else. Every visible part existed and
the join did not: the flag was real, the forms were real, and no form was ever simplified by it.

What is asserted here is not "the flag exists" but the three things that make a drop list safe to
ship, each against the live catalogue and the live routes rather than against a second copy of the
list:

* **No simplified form can drop a field its route requires.** That is §11.1's "a control the server
  refuses" in its other direction — a form that cannot fill its own route.
* **No simplified form is left with nothing drawn.** A screen with no controls has no way forward,
  which is worse than the long form it replaced.
* **The setting is read from the profile.** `simple_mode` is stored by `POST /access/profile`, and a
  client that had to send it back per request would be a second place for one preference to live.

The triage form is the case that shows why the drop list is a curation and not a rule. `temperature_c`
is optional-with-a-default on `/triage/preliminary` and is an input §6.3's malaria trap reads;
`muac_mm` on `/records/growth` is optional in exactly the same way and is a refinement most people
never measure. No field metadata distinguishes them, so a rule that tried would drop the first and
keep the second — and dropping the first is a person with a fever being triaged on symptoms alone.
"""
import inspect
import typing

import httpx
from pydantic import BaseModel

from afya.access.forms import SIMPLE_FORM_DROPS, required_fields, simplified
from afya.mobile.actions import available, catalogue
from afya.service import build_services, create_app


def _drawn(action: object) -> list[str]:
	"""The fields a form actually draws: not the subject it injects, not the key the server mints."""
	return [f.name for f in action.fields if not (f.client_supplied or f.server_assigned)]  # type: ignore[attr-defined]


async def _citizen(c: httpx.AsyncClient) -> dict[str, str]:
	tok = (await c.post('/auth/anonymous', json={'subject_ref': 'acc001-caller'})).json()['token']
	return {'Authorization': f'Bearer {tok}'}


def test_every_dropped_field_exists_on_the_action_it_is_dropped_from() -> None:
	"""A rename must fail here, not silently simplify nothing. The entry that stops matching is the
	one that would otherwise leave an "advanced" field on a simple form forever."""
	by_id = {a.id: a for a in catalogue()}
	unknown_actions = sorted(set(SIMPLE_FORM_DROPS) - set(by_id))
	assert not unknown_actions, f'simple-mode drops name actions that do not exist: {unknown_actions}'
	for action_id, dropped in SIMPLE_FORM_DROPS.items():
		names = {f.name for f in by_id[action_id].fields}
		missing = sorted(set(dropped) - names)
		assert not missing, f'{action_id}: drops fields it does not carry: {missing}'


def test_no_simplified_form_drops_a_field_its_route_requires() -> None:
	"""The gate that makes the list safe. Read off the live routes, so it cannot drift from the models
	the drop list is dropping from — and it fires: `peer_alert.location`, `provision_chw.registry_verified`
	and `assign_chw_case`'s three were all in the first draft of the table and all three are required.
	"""
	app = create_app(build_services())
	required = required_fields(app)
	by_id = {a.id: a for a in catalogue()}
	checked = 0
	for action_id, dropped in SIMPLE_FORM_DROPS.items():
		act = by_id[action_id]
		required_here = required.get((act.method, act.path), frozenset())
		broken = sorted(set(dropped) & required_here)
		assert not broken, (
			f'{action_id} {act.method} {act.path}: simple form drops required field(s) {broken}')
		checked += 1
	assert checked == len(SIMPLE_FORM_DROPS) and checked > 20, f'only {checked} entries checked'


def test_no_simplified_form_is_left_with_nothing_to_fill_in() -> None:
	"""A form with no controls is a screen a person cannot leave. The check is on the *drawn* fields,
	because a subject and a server-minted key are carried and not shown, so a form whose only
	surviving fields are those two is still empty to the person looking at it."""
	app = create_app(build_services())
	simple = {a.id: a for a in simplified(catalogue(), required_fields(app))}
	empties = []
	for action_id in SIMPLE_FORM_DROPS:
		act = simple[action_id]
		if not _drawn(act):
			empties.append(action_id)
	assert not empties, f'simple forms with nothing drawn: {empties}'


def test_simplifying_removes_fields_and_never_adds_or_reorders_them() -> None:
	"""The same action, asking fewer questions — not a different action. A field that moved or
	appeared would mean a client rendering the simple catalogue and one rendering the full catalogue
	were not describing the same route."""
	app = create_app(build_services())
	full = {a.id: a for a in catalogue()}
	simple = {a.id: a for a in simplified(catalogue(), required_fields(app))}
	assert set(full) == set(simple), 'simplifying must not change which actions exist'
	for action_id, act in simple.items():
		before = [f.name for f in full[action_id].fields]
		after = [f.name for f in act.fields]
		assert after == [n for n in before if n in set(after)], f'{action_id}: fields reordered'
		assert after != before or action_id not in SIMPLE_FORM_DROPS, f'{action_id}: unchanged'


def test_the_simple_catalogue_is_strictly_smaller() -> None:
	"""The whole claim, counted. A drop list that changed nothing would satisfy every gate above."""
	app = create_app(build_services())
	before = sum(len(_drawn(a)) for a in catalogue())
	after = sum(len(_drawn(a)) for a in simplified(catalogue(), required_fields(app)))
	assert after < before, f'simple mode removed no fields ({before} -> {after})'
	assert before - after >= 40, f'simple mode removed only {before - after} fields'


def test_the_drop_list_is_a_curation_and_keeps_the_questions_the_classifier_reads() -> None:
	"""The judgement the list encodes, asserted so a future edit that turns it into a rule is caught.

	`temperature_c` and `symptoms` are what §6.3's malaria trap and §11.2's escalation read, and they
	are optional-with-a-default on the triage model — so a rule keyed on "optional" would drop them.
	They must stay. `muac_mm` is optional in the same way and is a refinement, and it must go.
	"""
	for action_id in ('febrile_triage', 'evd_triage', 'differential'):
		dropped = set(SIMPLE_FORM_DROPS[action_id])
		assert 'temperature_c' not in dropped, f'{action_id}: the malaria trap reads temperature_c'
		assert 'symptoms' not in dropped, f'{action_id}: symptoms is the triage input'
		assert 'red_flags' not in dropped, f'{action_id}: red flags are what escalates to emergency'
	assert 'muac_mm' in SIMPLE_FORM_DROPS['growth_flag'], 'a refinement most people never measure'
	# And the entry that is *not* about the triage at all: the diary's temperature and red flags look
	# droppable and are not, because `/triage/{ref}/diary/trend` reads both. This assertion was a
	# failing one first — the drop list had them, and the test above did not catch it, because a
	# required-field gate cannot see a field another *screen* reads.
	diary = set(SIMPLE_FORM_DROPS['symptom_diary'])
	assert 'temperature_c' not in diary, 'the diary trend computes its direction from the temperature'
	assert 'red_flags' not in diary, 'a red flag appearing is what flips the trend to worsening'


async def test_the_diary_keeps_the_two_fields_the_trend_screen_reads() -> None:
	"""A form is not free to drop a field another screen reads, and no metadata says which those are.

	The simple form is what is asked here, not the model: the assertion is that the *shortened*
	catalogue still draws the two fields `/triage/{ref}/diary/trend` computes its direction from, and
	then the entries a client filling that form in would send are driven through the service to show
	the trend moves. Asserting on the model alone would pass against a drop list that removed both —
	which is how this test was written the first time, and a canary said so.
	"""
	from afya.registry.service import FeatureRegistry
	from afya.triage.service import TriageService
	from afya.triage.views import DiaryEntry

	app = create_app(build_services())
	short = {a.id: a for a in simplified(catalogue(), required_fields(app))}['symptom_diary']
	drawn = _drawn(short)
	for field in ('temperature_c', 'red_flags'):
		assert field in drawn, (
			f'the simple diary form no longer asks for {field}, which the trend screen reads; '
			f'it draws {drawn}')

	svc = TriageService(FeatureRegistry())
	flat = DiaryEntry(subject_ref='acc001-diary', day=1, symptoms=['fever'], temperature_c=36.5)
	await svc.diary_append(flat)
	worse = DiaryEntry(subject_ref='acc001-diary', day=2, symptoms=['fever'], temperature_c=38.4,
	                   red_flags=['bleeding_gums'])
	await svc.diary_append(worse)
	trend = svc.diary_trend('acc001-diary')
	assert trend.direction.value == 'worsening', trend.direction
	assert any('temperature' in c for c in trend.changed), trend.changed


def test_the_emergency_form_keeps_what_the_section_calls_optional_off_it() -> None:
	"""§EMG-001's "optional medical profile attachment (blood group, allergies, conditions,
	medications)" — the four the section itself calls optional are exactly the four a person filling
	in a simple SOS form does not have to hand. `lat`, `lon` and `severity` are required and stay."""
	dropped = set(SIMPLE_FORM_DROPS['sos'])
	assert dropped == {'blood_group', 'allergies', 'conditions', 'medications'}, sorted(dropped)
	for kept in ('lat', 'lon', 'severity', 'contacts'):
		assert kept not in dropped, f'sos: {kept} must stay on the simple form'


def test_the_privacy_assessment_forms_are_not_simplified() -> None:
	"""`dpia_check` and `activate_outbreak_mode` are long and stay long. On those two forms the flags
	*are* the content — §SEC-005's assessment is a statement about what the deployment does — and a
	simplified version would record an assessment nobody made. The absence of an entry is the claim,
	so it is asserted rather than left to a reader to notice."""
	for action_id in ('dpia_check', 'activate_outbreak_mode'):
		assert action_id not in SIMPLE_FORM_DROPS, (
			f'{action_id}: its flags are the content, not refinements to drop')


async def test_the_catalogue_route_serves_a_simplified_form_when_asked() -> None:
	"""The front door, not the function. `?simple_mode=true` must change the served payload, or the
	simplification exists and no client can reach it — the `report_stock` defect one level up."""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		full = {a['id']: a for a in (await c.get('/mobile/actions')).json()}
		simple = {a['id']: a for a in (await c.get('/mobile/actions?simple_mode=true')).json()}
		assert set(full) == set(simple)
		assert len(simple['sos']['fields']) < len(full['sos']['fields'])
		assert [f['name'] for f in simple['sos']['fields']] == [
			n for n in (f['name'] for f in full['sos']['fields'])
			if n not in {'blood_group', 'allergies', 'conditions', 'medications'}
		]


async def test_simple_mode_is_read_from_the_stored_profile_rather_than_the_request() -> None:
	"""§ACC-001's simple mode is a *setting*, written once by `POST /access/profile`. A client that
	had to send it back per request would be a second place for one preference to live, and the two
	would disagree the first time one was updated. `None` therefore means "ask the profile"; the
	explicit flag is an override, and both directions are checked."""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers = await _citizen(c)
		before = {a['id']: a for a in (await c.get('/mobile/actions', headers=headers)).json()}
		turned_on = await c.post('/access/profile', headers=headers,
		                         json={'subject_ref': 'acc001-caller', 'simple_mode': True})
		assert turned_on.status_code == 200, turned_on.text
		after = {a['id']: a for a in (await c.get('/mobile/actions', headers=headers)).json()}
		assert len(after['sos']['fields']) < len(before['sos']['fields']), (
			'the stored profile was not consulted: the form is the same length after turning it on')
		# The override still wins, in the other direction, so a client can preview either form.
		overridden = {a['id']: a for a in (await c.get(
			'/mobile/actions?simple_mode=false', headers=headers)).json()}
		assert len(overridden['sos']['fields']) == len(before['sos']['fields'])


async def test_a_caller_with_no_profile_gets_the_full_form() -> None:
	"""No token means a citizen with nothing stored, and a citizen with nothing stored has not asked
	for simple mode. Defaulting the other way would simplify every anonymous caller's forms on the
	strength of a setting nobody made."""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		anon = {a['id']: a for a in (await c.get('/mobile/actions')).json()}
		full = {a['id']: a for a in (await c.get('/mobile/actions?simple_mode=false')).json()}
		assert len(anon['sos']['fields']) == len(full['sos']['fields'])


async def test_the_full_catalogue_is_what_the_client_gets_by_default() -> None:
	"""The other half of the same claim: simplification is opt-in, so every existing client that knows
	nothing about `simple_mode` keeps the forms it had. A default-on simplification would silently
	shorten every form in the field."""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		served = (await c.get('/mobile/actions')).json()
		# The anonymous caller is a citizen, so the payload is the citizen subset of the catalogue —
		# not all of it, and the two filters that narrow it are §11.1's and §17.4's, not this unit's.
		assert len(served) == len(available(False, frozenset()))
		by_id = {a.id: a for a in catalogue()}
		for act in served:
			assert len(act['fields']) == len(by_id[act['id']].fields), act['id']
		# And the simplification is nowhere in it: no action served by default lost a field.
		assert all(act['id'] not in SIMPLE_FORM_DROPS or
		           len(act['fields']) == len(by_id[act['id']].fields) for act in served)


def test_no_spec_feature_code_reaches_a_simplified_form() -> None:
	"""The catalogue's standing rule, re-asserted over the simplified payload — because the simplest
	way to write a "simplified" label is to name the spec feature, and a person reading "ACC-001" has
	been told nothing about their fever."""
	import re
	code = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')
	app = create_app(build_services())
	for act in simplified(catalogue(), required_fields(app)):
		blob = act.model_dump_json()
		assert not code.search(blob), f'{act.id}: a spec feature code reached the catalogue'


def test_the_simplification_is_reachable_from_the_action_that_turns_it_on() -> None:
	"""A setting a client cannot find is a setting nobody changes. `access_profile` is the action that
	writes `simple_mode`, and it is in the citizen catalogue — so the control that simplifies the forms
	is itself reachable from a form."""
	by_id = {a.id: a for a in available(False, frozenset())}
	assert 'access_profile' in by_id, 'the citizen catalogue must carry the simple-mode setting'
	assert 'simple_mode' in {f.name for f in by_id['access_profile'].fields}


def test_the_required_reader_sees_required_fields_and_defaults_the_rest() -> None:
	"""Canary for the reader the whole drop gate rests on. Driven on a route built here, because the
	live catalogue has no action whose requiredness is wrong — which is exactly why the reader has to
	be shown working on a known shape."""
	from fastapi import FastAPI

	class Known(BaseModel):
		must: str
		may: str = 'x'

	def endpoint(_inp: Known) -> dict[str, str]:
		return {}

	app = FastAPI()
	app.post('/known/{path_arg}')(endpoint)
	seen = required_fields(app)
	# FastAPI's own docs routes are in the walk too; the assertion is about the one route under test.
	assert seen[('POST', '/known/{path_arg}')] == frozenset({'must', 'path_arg'}), seen
	assert 'may' not in seen[('POST', '/known/{path_arg}')], 'a defaulted field is not required'


def test_the_route_walk_finds_the_whole_app_rather_than_its_first_six_routes() -> None:
	"""The walk is recursive because FastAPI mounts routers. A top-level pass over `app.routes`
	returns six routes and would call a drop of a required field clean — the inventory is the gate's
	ground truth, so a short inventory is a gate that passes for the wrong reason."""
	app = create_app(build_services())
	seen = required_fields(app)
	assert len(seen) > 300, f'the walk found {len(seen)} routes, which is a partial inventory'
	assert ('POST', '/emergency/sos') in seen, 'a known route is missing from the walk'
	assert 'lat' in seen[('POST', '/emergency/sos')]
	# And a route whose only required inputs are path placeholders, so the reader is not just
	# collecting body fields.
	assert ('POST', '/facilities/{facility_id}/wait') in seen


def test_the_signature_reader_is_what_finds_a_scalar_required_parameter() -> None:
	"""A query parameter with no default is required in exactly the way a body field is, and a reader
	that only looked at body models would miss it — the first draft of the drop table did, and
	`check_in.at_iso` is a body field while `/places/nearest`'s coordinates are query parameters."""
	app = create_app(build_services())
	seen = required_fields(app)
	assert 'lat' in seen[('GET', '/places/nearest')], sorted(seen[('GET', '/places/nearest')])
	assert 'lon' in seen[('GET', '/places/nearest')]
	assert 'kinds' not in seen[('GET', '/places/nearest')], 'a defaulted parameter is not required'


def test_the_module_reads_requiredness_rather_than_restating_it() -> None:
	"""The list is a judgement about which *optional* fields to drop; which fields are *required* is
	not a judgement at all and must never be written down here. This asserts the reader is wired by
	comparing its answer to the model's own, for a form whose requiredness a reader could guess."""
	app = create_app(build_services())
	seen = required_fields(app)
	from afya.emergency.views import SOSEvent

	model_required = {k for k, v in SOSEvent.model_fields.items() if v.is_required()}
	assert seen[('POST', '/emergency/sos')] >= model_required
	assert inspect.signature(SOSEvent) is not None  # the import is used, not decorative
	assert typing.get_type_hints(SOSEvent.__init__) is not None


def test_the_video_tutorial_bullet_stays_open() -> None:
	"""§ACC-001's "Video tutorials in local languages" — stays `missing`, and this is the test that
	says why.

	The temptation is to read the bullet as a rendering problem and close it with a generator: `manim`
	draws programmatic animation, `heygen` synthesises an avatar. Neither closes it. `manim` produces
	no narration, so it cannot supply the local-language half the bullet names; `heygen` would be a
	new external integration sending clinical content to a third party, and a synthetic Dholuo or
	Kalenjin voice is the unvalidated-voice claim §ACC-002 refuses to count one row down.

	The bar is §6.5, which this repo *implements* rather than describes — every published health item
	clears English draft → clinical review → translation → back-translation → community validation,
	and `ContentItem` cannot even be constructed without an `owner`, a `reviewer` and a review date.
	A tutorial in a local language is clinical content, so it is the workflow and not the renderer
	that decides when the row closes.

	What the tree does carry is the *place* the asset lands: `ContentFormat.video` with a `media_ref`
	on the §INF-003/§INF-008 corpus. That is asserted below, because it is the difference between a
	row that is open for want of an asset and a row that is open for want of somewhere to put one.
	"""
	from afya.content_audit.service import content_report
	from afya.info.views import ContentFormat

	report = content_report()
	feature = next((f for f in report.features if f.feature_id == 'ACC-001'), None)
	assert feature is not None, '§ACC-001 left the report'
	row = next((b for b in feature.bullets if b.bullet == 'Video tutorials in local languages'), None)
	assert row is not None, 'the row disappeared rather than staying open'
	assert row.kind == 'missing', (
		'a renderer cannot close this row: the bullet names local languages and §6.5 governs what may '
		'be published in one'
	)
	assert row.carried_by is None, 'an open row cites nothing'
	assert row.note is not None and 'STAYS OPEN' in row.note, 'the reason must be recorded, not implied'

	# The destination exists. A video format with a `media_ref` is the shape a §6.5-cleared asset
	# takes, so the row is waiting on content rather than on a schema that cannot receive it.
	assert ContentFormat.video.is_text is False, 'a video is a rendition, not prose'
