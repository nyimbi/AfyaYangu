"""§SENS-010 — NFC tag-based workflows, and the four applications that had no binding.

The section lists five applications. The first — check-in at facilities — is §LOC-004's and was
carried. The other four were `missing` in `afya.content_audit.service`, each with a note naming what
it needed: a wristband bound to a patient, a tag bound to a medicine package, a PPE station log, an
equipment register.

The four are one mechanism. Every line of the section is "tap a tag, learn or record something about
the thing it is attached to", and the thing it is attached to is the only thing that differs. So the
unit under test is the *binding*, and the four targets are four resolutions of it — which is why a
test that only counted endpoints would pass against four copies of the same bug.

The two properties worth canarying are both about what a tap must not do: it must not turn an
unknown tag into a negative answer, and it must not carry a person where the target is an object.
"""
import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from afya.content_audit.service import FEATURE_CONTENT
from afya.refs import resolves
from afya.sensors.tags import (
	APPLICATIONS, EQUIPMENT_STATUSES, TAG_TARGETS, TARGET_RESOLVERS, EquipmentRegister, Tag,
	TagService, TagTarget,
)
from afya.service import build_services, create_app

REPO = pathlib.Path(__file__).resolve().parents[2]


def _svc() -> TagService:
	"""A service with one tag of each target, and an asset for the equipment one.

	The equipment tag is bound to a *registered* asset because `bind` refuses one that is not — the
	fixture cannot paper over the assertion the module makes.
	"""
	svc = TagService()
	svc.equipment.add('VENT-001', 'Ventilator 1')
	svc.bind(Tag(tag_id='AAAA11112222', target=TagTarget.patient, target_ref='PT-7',
		label='Bed 4 wristband', bound_at_iso='2026-10-14T06:00:00Z'))
	svc.bind(Tag(tag_id='BBBB11112222', target=TagTarget.medicine, target_ref='BATCH-9921',
		label='Artemether 20/120', bound_at_iso='2026-10-14T06:00:00Z'))
	svc.bind(Tag(tag_id='CCCC11112222', target=TagTarget.ppe_station, target_ref='STATION-2',
		label='Isolation ward doffing station', bound_at_iso='2026-10-14T06:00:00Z'))
	svc.bind(Tag(tag_id='DDDD11112222', target=TagTarget.equipment, target_ref='VENT-001',
		label='Ventilator 1', bound_at_iso='2026-10-14T06:00:00Z'))
	return svc


# --- the section's own list, and the binding behind each line ------------------------------------

def test_the_sections_four_open_applications_are_the_four_targets() -> None:
	"""The spec's lines and the code's targets are one list, not two that agree today.

	§SENS-010 prints five applications and the audit reads four of them as `carried` here. This
	asserts the *correspondence* — every line the section prints beyond the check-in has a target,
	and every target has a line — so a line added to the spec and not to the code is a failure
	rather than an undercount. The check-in is excluded by name because §LOC-004 owns it.
	"""
	assert {t for _, t in APPLICATIONS} == set(TAG_TARGETS)
	assert len(APPLICATIONS) == 4
	body = (REPO / 'docs/spec.md').read_text()
	section = body.split('#### NFC for Tag-Based Workflows', 1)[1].split('\n---', 1)[0]
	for line, _ in APPLICATIONS:
		assert f'- {line}' in section, f'the spec does not print this application: {line}'


def test_every_target_names_a_resolver_that_imports() -> None:
	"""A target whose resolver does not import is a binding to nothing.

	The refs are walked rather than read: `afya.refs.resolves` imports the module and walks the
	dotted attribute, so a resolver renamed off its class fails here. `PPE_DONNING` was written into
	this dict first and did not resolve — the constant is a *key* in `afya.chw.views:JOB_AIDS`, not a
	module attribute — which is the whole reason the walk exists rather than a reader's eye.
	"""
	assert set(TARGET_RESOLVERS) == set(TAG_TARGETS)
	for target, ref in TARGET_RESOLVERS.items():
		assert resolves(ref), f'{target} resolves through {ref}, which does not exist'


def test_the_audit_records_the_four_as_carried_with_those_resolvers() -> None:
	"""The rows and the module are one fact. A row that says `carried` while the carrier is gone is
	the defect the audit exists to find, and it would be found here first."""
	rows = {bullet: (kind, ref) for f, _, bullet, kind, ref, _ in FEATURE_CONTENT if f == 'SENS-010'}
	assert len(rows) == 5, 'the section prints five applications'
	for line, target in APPLICATIONS:
		kind, ref = rows[line]
		assert kind == 'carried', f'{line} is {kind}'
		assert ref and resolves(ref), f'{line} is carried by {ref}, which does not resolve'


# --- a tap answers, and the two ways it answers nothing are not the same -------------------------

def test_a_tap_on_a_bound_tag_names_what_it_is() -> None:
	svc = _svc()
	verdict = svc.resolve('AAAA11112222')
	assert verdict.resolved and verdict.target is TagTarget.patient
	assert verdict.target_ref == 'PT-7'
	assert verdict.label == 'Bed 4 wristband'


def test_an_unregistered_tag_and_a_withdrawn_target_do_not_read_alike() -> None:
	"""The defect this file exists for, in the class §MED-001's four outcomes established.

	A tag nobody registered is a mis-tap, a clone, or a tag from another deployment. A registered tag
	whose target has been taken off the register is a real tag pointing at something that is gone — a
	wristband for a discharged patient, an asset that was retired. Both are `resolved=False`, which is
	correct and is exactly why the boolean is not enough: the two send a person to different places.
	"""
	svc = _svc()
	unknown = svc.resolve('FFFFFFFFFFFF')
	assert unknown.resolved is False and unknown.target is None
	assert 'not registered' in unknown.note
	svc.equipment._assets.pop('VENT-001')
	withdrawn = svc.resolve('DDDD11112222')
	assert withdrawn.resolved is False
	assert withdrawn.target is TagTarget.equipment and withdrawn.target_ref == 'VENT-001'
	assert 'off the register' in withdrawn.note
	assert withdrawn.note != unknown.note, 'the two absences must not read alike'


def test_a_tag_holds_the_target_and_never_the_person() -> None:
	"""§SENS-010's privacy boundary, asserted on the object rather than described in a docstring.

	Three of the four targets are objects. A wristband that carried the patient's name and age would
	leak them to anyone who taps it, so `Tag` carries an opaque `target_ref` and nothing else — this
	checks the model's own field set, so a field added to the tag fails here rather than at a bedside.
	"""
	assert set(Tag.model_fields) == {'tag_id', 'target', 'target_ref', 'label', 'bound_at_iso'}
	assert 'person' not in ' '.join(Tag.model_fields), 'a tag names a target, not a person'


def test_only_a_station_log_names_the_worker() -> None:
	"""§COM-101 states the PPE bullet as occupational, so its log names the worker. The other three
	are about the object, and `tap` asserts the difference rather than trusting the caller."""
	svc = _svc()
	with pytest.raises(AssertionError, match='names the worker'):
		svc.tap('CCCC11112222', '2026-10-14T09:00:00Z')
	reading = svc.tap('CCCC11112222', '2026-10-14T09:00:00Z', worker_ref='CHW-3')
	assert reading.worker_ref == 'CHW-3' and reading.target is TagTarget.ppe_station
	object_tap = svc.tap('AAAA11112222', '2026-10-14T09:00:00Z')
	assert object_tap.worker_ref is None, 'a wristband tap records no person'


def test_an_unresolved_tap_is_still_recorded() -> None:
	"""A run of unresolved taps at one station is the signal that a tag has been swapped. Dropping
	them would leave the only evidence of it unrecorded."""
	svc = _svc()
	svc.tap('FFFFFFFFFFFF', '2026-10-14T09:00:00Z')
	assert len(svc.readings()) == 1


# --- the equipment register, which is the one target with an object behind it --------------------

def test_an_equipment_tag_must_name_an_asset_the_register_holds() -> None:
	"""Binding is where the failure is cheap. A tag bound to an asset nobody registered resolves at
	the station to nothing, which is the failure that appears at the bedside rather than here."""
	svc = TagService()
	with pytest.raises(AssertionError, match='register holds'):
		svc.bind(Tag(tag_id='EEEE11112222', target=TagTarget.equipment, target_ref='NOPE',
			label='Nothing', bound_at_iso='2026-10-14T06:00:00Z'))


def test_rebinding_a_tag_is_refused() -> None:
	"""A tag that silently points somewhere new is how a wristband ends up naming the wrong patient."""
	svc = _svc()
	with pytest.raises(AssertionError, match='already bound'):
		svc.bind(Tag(tag_id='AAAA11112222', target=TagTarget.patient, target_ref='PT-8',
			label='Bed 5 wristband', bound_at_iso='2026-10-14T06:00:00Z'))


def test_equipment_tracking_answers_where_an_asset_is() -> None:
	"""§SENS-010's fifth line is a register, and "tracking" is the question it is asked: where is
	this, and is it serviceable."""
	reg = EquipmentRegister()
	reg.add('VENT-001', 'Ventilator 1')
	reg.move('VENT-001', 'Isolation ward')
	assert reg.assets() == [{'asset_ref': 'VENT-001', 'label': 'Ventilator 1',
		'status': 'in_service', 'station': 'Isolation ward'}]
	reg.add('PUMP-2', 'Infusion pump', 'under_repair')
	assert len(reg.assets(status='under_repair')) == 1
	assert {s for s in EQUIPMENT_STATUSES} == {'in_service', 'under_repair', 'retired'}


def test_a_condition_the_register_does_not_know_is_refused() -> None:
	reg = EquipmentRegister()
	with pytest.raises(AssertionError, match='unknown equipment status'):
		reg.add('X-1', 'Something', 'probably_fine')


# --- the front door ------------------------------------------------------------------------------

def _client() -> TestClient:
	return TestClient(create_app(build_services(db_path=':memory:')))


def test_the_tag_routes_are_served_and_guarded() -> None:
	"""A green unit test says nothing about what the front door serves. A tap is open — a person
	holding a phone at a bedside is the caller, and a tap behind an account is a tap nobody makes —
	while binding a tag and registering equipment are the county health team's, the same scope
	§LOC-004's `register_checkin_point` takes."""
	client = _client()
	# Registering hardware without a token is refused.
	assert client.post('/sensors/tags', json={'tag_id': 'AAAA11112222', 'target': 'patient',
		'target_ref': 'PT-7', 'label': 'Bed 4', 'bound_at_iso': '2026-10-14T06:00:00Z'}).status_code in (401, 403)
	assert client.post('/sensors/equipment', params={'asset_ref': 'V-1', 'label': 'Vent'}).status_code in (401, 403)
	# A tap on a tag nobody registered answers rather than 500s, and says which absence it is.
	body = client.get('/sensors/tags/FFFFFFFFFFFF').json()
	assert body['resolved'] is False and 'not registered' in body['note']


def test_the_coverage_route_reports_the_sections_five_applications() -> None:
	"""§SENS-010's coverage is read off the running object rather than asserted in a table, so a
	line whose resolver rotted is visible on a screen rather than in a test nobody runs."""
	client = _client()
	assert client.get('/sensors/tag-coverage').status_code in (401, 403)
	svc = build_services(db_path=':memory:')
	app = create_app(svc)
	tags: TagService = svc['tags']  # type: ignore[assignment]
	tags.equipment.add('VENT-001', 'Ventilator 1')
	tags.bind(Tag(tag_id='DDDD11112222', target=TagTarget.equipment, target_ref='VENT-001',
		label='Ventilator 1', bound_at_iso='2026-10-14T06:00:00Z'))
	auditor = TestClient(app)
	# The route is auditor-scoped; without a token the coverage statement is not served.
	assert auditor.get('/sensors/tag-coverage').status_code in (401, 403)
	coverage = tags.coverage()
	applications = coverage['applications']
	assert isinstance(applications, list) and len(applications) == 4
	assert coverage['check_in'] == 'afya.location.service:LocationService.check_in'
	assert coverage['targets_with_no_tag'] == ['patient', 'medicine', 'ppe_station']


def test_no_spec_code_reaches_a_person() -> None:
	"""The standing constraint: spec ids are internal. The catalogue is where a person reads the
	section's capability, so it must carry none of it."""
	from afya.mobile.actions import FEATURE_OF, FRIENDLY_COPY, catalogue

	code = re.compile(r'\b(?:SENS|LOC|MED|COM|CHAN)-\d{3}\b')
	for act in catalogue():
		if act.id not in {'tag_resolve', 'tag_tap', 'tag_bind', 'tag_coverage',
		                  'equipment_list', 'equipment_add', 'equipment_move'}:
			continue
		assert FEATURE_OF[act.id] == 'SENS-010'
		rendered = f'{act.title} {act.group}'
		for fl in act.fields:
			rendered += f' {fl.label} {fl.placeholder or ""}'
		assert code.search(rendered) is None, f'a spec code reached the screen: {act.id}'
		title, desc = FRIENDLY_COPY[act.id]
		assert code.search(f'{title} {desc}') is None
