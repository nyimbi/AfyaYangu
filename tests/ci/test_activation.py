"""Gate: §11.1's activation model — five triggers, three scopes, and the deactivation clause.

§11.1 is a five-row table of triggers, scopes and the features each one activates, and §11's opening
sentence says what it is for: "Dormant until triggered by PHEOC. Activates automatically for users in
affected areas." The code had one boolean over three keys, so the model was not the section's in
either direction — the individual triggers (rows 3–5, activating MON-009, LOC-001 and LOC-002 for
*one person*) could not fire at all without a national declaration, and the county trigger (row 2)
could not either.

What is tested is the scope resolution, not only the table's transcription: that a contact gets their
diary in a county with no declared event, that a person in a risk zone is not a person identified as
a contact, that a case in Busia does not turn Garissa's alerts on, and that the Tier-4 features §11.1
never names are reported rather than silently gated behind the declaration.
"""
import re
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from afya.registry.activation import (
	DIVERGENCES, TIER4_DATA_TYPES, TRIGGERS, TRIGGERED_FEATURES, SubjectCondition, TriggerFiring,
	TriggerScope, triggers_for, unassigned,
)
from afya.registry.gate import ActivationService
from afya.registry.service import FeatureRegistry, Tier, Tier4Activation
from afya.retention.views import RETENTION_TABLE

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / 'docs' / 'spec.md'

FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')


def _spec_rows() -> list[list[str]]:
	"""§11.1's table, read out of the spec. Located by heading and taken as the five rows under it —
	the section has one table, and reading it is what makes a revision fail here rather than passing
	against a section that no longer says what the code claims."""
	lines = SPEC.read_text(encoding='utf-8').splitlines()
	start = next(i for i, ln in enumerate(lines) if ln.startswith('### 11.1 '))
	rows: list[list[str]] = []
	for ln in lines[start:]:
		if rows and ln.startswith('**Deactivation'):
			break
		if not ln.startswith('|'):
			continue
		cells = [c.strip() for c in ln.strip('|').split('|')]
		if set(''.join(cells)) <= set('-: ') or cells[0] == 'Trigger':
			continue
		rows.append(cells)
	assert len(rows) == 5, f'§11.1 should have five trigger rows, found {len(rows)}'
	return rows


def _svc(active: bool = False) -> ActivationService:
	return ActivationService(FeatureRegistry(Tier4Activation(
		authorized_by_pheoc=active, dpia_review_id='r1' if active else None, flag_enabled=active,
	)))


async def _fired(svc: ActivationService, number: int, **kw: object) -> None:
	row = next(t for t in TRIGGERS if t.number == number)
	base: dict[str, object] = {
		'fired_at_iso': '2026-10-11T09:00:00+00:00', 'fired_by': 'PHEOC duty officer',
		'evidence': 'lab confirmation ref LAB-2026-4417',
	}
	await svc.fire(TriggerFiring(trigger_number=number, scope=row.scope, **{**base, **kw}))  # type: ignore[arg-type]


def _tier4() -> frozenset[str]:
	return frozenset(s.id for s in FeatureRegistry().by_tier(Tier.tier4))


# --- §11.1's table, row for row -------------------------------------------------------------------

def test_every_spec_row_is_carried_verbatim() -> None:
	"""Trigger, Scope and Features against the section's own words. The Features cell keeps its
	parenthetical because row 2's is `LOC-001 (dynamic geofences)` and the parenthetical says *what*
	that activation turns on."""
	spec_rows = _spec_rows()
	assert len(TRIGGERS) == len(spec_rows)
	for row, cells in zip(TRIGGERS, spec_rows):
		trigger, scope, features = cells
		assert row.trigger == trigger, f'row {row.number}: trigger'
		assert row.scope_label == scope, f'row {row.number}: scope'
		assert row.features_label == features, f'row {row.number}: features cell'


def test_the_features_cell_parses_to_the_ids_it_names() -> None:
	"""`features` is the cell parsed, so the two cannot disagree — an id added to the cell and not to
	the tuple would be activated on paper and not in code.

	The id shape is `[A-Z]{2,3}` and not `[A-Z]{3}`: `AI-001` is two letters, and a three-letter
	pattern silently dropped it from row 1's cell while the set comparison still looked meaningful."""
	for row in TRIGGERS:
		assert set(row.features) == set(re.findall(r'[A-Z]{2,3}-\d{3}', row.features_label)), \
			f'row {row.number}: the parsed ids do not match the cell'
		assert len(row.features) == len(set(row.features)), f'row {row.number}: duplicate id'
		for fid in row.features:
			assert FEATURE_CODE.fullmatch(fid), f'row {row.number}: {fid} is not a feature id'


def test_the_scopes_are_the_sections_three() -> None:
	assert [t.scope for t in TRIGGERS] == [
		TriggerScope.national_or_county, TriggerScope.county,
		TriggerScope.individual, TriggerScope.individual, TriggerScope.individual,
	]
	assert [t.scope_label for t in TRIGGERS] == [
		'National or county', 'County', 'Individual', 'Individual', 'Individual',
	]


def test_every_individual_trigger_names_its_own_condition() -> None:
	"""Three individual rows, three different facts. A single `is_individual` flag would make rows 3,
	4 and 5 one trigger, which is the collapse the global gate performed one level up."""
	individual = [t for t in TRIGGERS if t.scope is TriggerScope.individual]
	assert [t.condition for t in individual] == [
		SubjectCondition.is_contact, SubjectCondition.in_risk_zone, SubjectCondition.requested,
	]
	assert all(t.condition is None for t in TRIGGERS if t.scope is not TriggerScope.individual)


# --- scope resolution: the thing the global gate could not do -------------------------------------

async def test_a_contact_gets_the_diary_with_no_declared_event() -> None:
	"""The defect in one test. MON-009 is activated by rows 3 and 5 — for *one person* — and under
	`if not registry.tier4_active()` a contact could not get their 21-day diary until PHEOC declared
	a national event. §11's own constraint says the opposite."""
	svc = _svc(active=False)
	assert not svc.feature_available('MON-009', svc.state(subject_ref='sub-1')), 'not a contact yet'
	await _fired(svc, 3, subject_ref='sub-1')
	assert svc.feature_available('MON-009', svc.state(subject_ref='sub-1')), \
		'a contact gets the diary with no declared event'
	assert not svc.state(subject_ref='sub-1').pheoc_event_active, 'and no declaration happened'
	assert not svc.feature_available('MON-009', svc.state(subject_ref='sub-2')), \
		'and only the contact does'


async def test_a_person_in_a_risk_zone_is_not_a_contact() -> None:
	"""Rows 3 and 4 are different facts with different features: MON-009 for a contact, LOC-001 and
	ALT-004 for someone in a risk zone. A single individual flag would give both to both."""
	svc = _svc()
	await _fired(svc, 4, subject_ref='sub-1', county='Busia')
	state = svc.state(county='Busia', subject_ref='sub-1')
	assert svc.feature_available('ALT-004', state)
	assert not svc.feature_available('MON-009', state), 'being in a risk zone is not being a contact'


async def test_a_county_case_activates_for_that_county_only() -> None:
	"""Row 2's scope is the county. A confirmed case in Busia must not turn geofenced alerts on for
	Garissa, which is the scope error a global gate makes by construction."""
	svc = _svc()
	await _fired(svc, 2, county='Busia')
	assert svc.feature_available('ALT-004', svc.state(county='Busia'))
	assert not svc.feature_available('ALT-004', svc.state(county='Garissa'))
	assert not svc.feature_available('ALT-004', svc.state(county=None)), 'no county, no county trigger'


async def test_the_declared_event_still_activates_its_row() -> None:
	"""Row 1, and the three-key gate is what makes it true: a declaration with the DPIA or the flag
	missing is not a declaration. §11.1's own Appendix-D question 3 leaves who holds the keys open,
	and §24.7 puts the DPIA before each activation."""
	active = _svc(active=True)
	await _fired(active, 1, evidence='PHEOC bulletin 2026-41')
	state = active.state()
	assert state.pheoc_event_active
	for fid in ('ALT-004', 'LOC-002', 'LOC-003', 'COM-101', 'AI-001'):
		assert active.feature_available(fid, state), f'{fid} is row 1’s'

	unkeyed = _svc(active=False)
	await _fired(unkeyed, 1)
	assert not unkeyed.state().pheoc_event_active, 'a firing with the keys unheld is not an event'


async def test_a_feature_with_two_triggers_is_reachable_by_either() -> None:
	"""MON-009 is rows 3 and 5, ALT-004 is rows 1, 2 and 4, LOC-002 is rows 1 and 5. Reachable by
	either, which is why resolution is an `any` over the rows and not a lookup of one."""
	assert [t.number for t in triggers_for('MON-009')] == [3, 5]
	assert [t.number for t in triggers_for('ALT-004')] == [1, 2, 4]
	assert [t.number for t in triggers_for('LOC-002')] == [1, 5]

	svc = _svc()
	await _fired(svc, 5, subject_ref='sub-1')
	state = svc.state(subject_ref='sub-1')
	assert svc.feature_available('MON-009', state), 'row 5 alone is enough'
	assert svc.feature_available('LOC-002', state)


def test_a_feature_below_tier4_is_always_available() -> None:
	"""§7.3: cross-cutting and Tier 1 are always available. The activation model must not touch them,
	or a request with no county and no subject would find the product switched off."""
	svc = _svc()
	state = svc.state()
	for fid in ('INF-001', 'TRI-001', 'FND-001', 'SEC-001', 'ACC-003'):
		assert svc.feature_available(fid, state), f'{fid} is below Tier 4'


async def test_a_tier4_feature_with_no_trigger_follows_the_declaration() -> None:
	"""§11's opening sentence makes Tier 4 dormant until PHEOC triggers it, and §11.1 does not
	enumerate twelve of the eighteen Tier-4 features. They follow the declaration — refusing them
	outright would be stricter than the section — and `unassigned()` is where the gap is reported."""
	ids = unassigned(_tier4())
	assert ids, 'the gate must not be vacuous: some Tier-4 feature has no row'
	svc = _svc()
	for fid in ids:
		assert not svc.feature_available(fid, svc.state()), f'{fid} dormant with no declaration'

	declared = _svc(active=True)
	await _fired(declared, 1)
	for fid in ids:
		assert declared.feature_available(fid, declared.state()), f'{fid} follows the declaration'


def test_unassigned_names_the_gap_rather_than_claiming_coverage() -> None:
	"""A check that read §11.1's table alone would report perfect coverage forever. The twelve
	features the table never names are the finding, and they are read off the *registry*.

	Twelve and not eleven, and the difference is the divergence: §11.1 names seven features, six of
	them Tier 4, and eighteen minus six is twelve. `LOC-001` is the seventh and is Tier 1, so it is
	triggered and not Tier 4 at once — which is why this count is asserted rather than described."""
	tier4 = _tier4()
	assert len(tier4) == 18
	assert set(TRIGGERED_FEATURES) <= tier4 | {'LOC-001'}
	assert len(unassigned(tier4)) == 12
	assert 'SENS-001' in unassigned(tier4), 'LiDAR respiration has no §11.1 row'
	assert 'LOC-001' not in unassigned(tier4), 'it is triggered; §7.3 puts it in Tier 1'


def test_the_loc_001_divergence_is_recorded_not_resolved() -> None:
	"""§11.1 rows 2 and 4 activate LOC-001; §7.3 lists it under Tier 1. A feature cannot be both
	always-on and dormant behind a gate. The code follows §7.3 and the divergence is written down,
	because picking one silently is how the next reader loses an afternoon to it."""
	assert 'LOC-001' in DIVERGENCES
	assert '§7.3' in DIVERGENCES['LOC-001'] and '§11.1' in DIVERGENCES['LOC-001']
	assert _svc().feature_available('LOC-001', _svc().state()), 'followed §7.3: always available'


# --- the refusal says what would change it ---------------------------------------------------------

def test_a_refusal_names_the_trigger_that_would_fire() -> None:
	"""§11.1's rows are the only thing that turns a Tier-4 feature on, so a refusal names the ones
	that would. A person told "not available" with no way to find out what changes it has a switch
	that refuses them, which is what §11.1 exists to prevent."""
	svc = _svc()
	contact_reason = svc.reason('MON-009', svc.state(subject_ref='sub-1'))
	assert 'you are identified as a contact' in contact_reason
	assert 'you ask for it' in contact_reason, 'row 5 is the other way MON-009 turns on'

	county_reason = svc.reason('ALT-004', svc.state(county='Busia'))
	assert 'a case is confirmed in your county' in county_reason
	assert 'the outbreak response is activated' in county_reason, 'row 1 also activates ALT-004'

	assert svc.reason('MON-009', svc.state(subject_ref='sub-1')) != svc.reason('ALT-004', svc.state())
	assert svc.reason('SENS-001', svc.state()) == 'This turns on when the outbreak response is activated.'


async def test_an_available_feature_is_not_given_a_refusal() -> None:
	"""The other branch, which a test of refusals alone never reaches: a contact asking why the diary
	is on must not be told what would turn it on."""
	svc = _svc()
	await _fired(svc, 3, subject_ref='sub-1')
	assert svc.reason('MON-009', svc.state(subject_ref='sub-1')) == 'This is available for you now.'


def test_no_refusal_carries_a_spec_code() -> None:
	"""The codes are internal. A refusal is read by the person refused."""
	svc = _svc()
	for fid in ('MON-009', 'ALT-004', 'LOC-002', 'COM-101', 'SENS-001'):
		for state in (svc.state(), svc.state(county='Busia', subject_ref='sub-1')):
			sentence = svc.reason(fid, state)
			assert not FEATURE_CODE.search(sentence), sentence


# --- firing a trigger ------------------------------------------------------------------------------

async def test_a_firing_must_carry_its_scope_own_evidence() -> None:
	"""The three scopes need different things true and the model refuses a firing that does not carry
	them: a county trigger with no county, an individual one with no person, a declaration about one
	person. That is the check the global gate could not make — it had nowhere to put either."""
	svc = _svc()
	with pytest.raises(AssertionError):
		await _fired(svc, 2)  # county trigger, no county
	with pytest.raises(AssertionError):
		await _fired(svc, 3)  # individual trigger, no subject
	with pytest.raises(AssertionError):
		await _fired(svc, 1, subject_ref='sub-1')  # a declaration is not about one person
	assert svc.firings() == [], 'a refused firing is not recorded'

	await _fired(svc, 2, county='Busia')
	assert len(svc.firings()) == 1


async def test_a_county_firing_cannot_smuggle_in_a_subject() -> None:
	"""A county trigger reaches a county; an individual one reaches a person. A firing that is both
	would be counted in the notified set by its subject and in the counties by its county, so the
	close would tell a person about an activation that was never about them.

	This is the invariant `deactivate`'s subject filter rests on, and it was only an accident before:
	nothing refused a county firing carrying a `subject_ref`, so the filter that keeps such a person
	out of the notified set was the only thing doing the work — and a canary that widened the filter
	passed every test, which is how the hole showed up."""
	svc = _svc()
	with pytest.raises(AssertionError):
		await _fired(svc, 2, county='Busia', subject_ref='sub-9')
	await _fired(svc, 2, county='Busia', subject_ref=None)
	assert svc.firings()[0].subject_ref is None


async def test_a_firing_without_evidence_or_an_actor_is_refused() -> None:
	"""A trigger is a determination somebody made, and a firing recorded without either is
	indistinguishable from one recorded by accident. The model refuses it before `fire` is reached,
	which is why the construction itself is the thing under test."""
	svc = _svc()
	assert svc.firings() == []
	with pytest.raises(ValidationError):
		TriggerFiring(trigger_number=2, scope=TriggerScope.county, county='Busia',
			fired_at_iso='2026-10-11T09:00:00+00:00', fired_by='x')  # type: ignore[call-arg]  # no evidence
	with pytest.raises(ValidationError):
		TriggerFiring(trigger_number=2, scope=TriggerScope.county, county='Busia',
			fired_at_iso='2026-10-11T09:00:00+00:00', evidence='x')  # type: ignore[call-arg]  # no actor


# --- §11.1's deactivation clause -------------------------------------------------------------------

def test_deactivation_starts_the_clocks_from_the_retention_table() -> None:
	"""Three sentences, three fields. The clocks are read from §17's table rather than written here —
	§11.1 says the clocks begin, not how long they run, and a second copy of "21 days" is the drift
	§5.2's APK budget and §22.5 already demonstrated between them."""
	report = _svc().deactivate('2026-10-11T12:00:00+00:00', 'PHEOC director')
	assert {c.data_type for c in report.clocks} == set(TIER4_DATA_TYPES)
	for clock in report.clocks:
		row = RETENTION_TABLE[clock.data_type]
		assert clock.retention_days == row['days']
		assert clock.deletion_trigger == row['trigger']
		assert clock.started_at_iso == '2026-10-11T12:00:00+00:00'
		assert clock.expires_at_iso.startswith('2026-11-01'), f'{clock.data_type}: 21 days from close'


async def test_deactivation_notifies_the_people_the_triggers_reached() -> None:
	""""Users are notified." The subjects are read off the individual firings — the people a trigger
	actually reached — and the counties off the county firings, because notifying a county nobody
	activated in is a message about an event that did not concern them."""
	svc = _svc()
	await _fired(svc, 3, subject_ref='sub-1')
	await _fired(svc, 4, subject_ref='sub-2', county='Busia')
	await _fired(svc, 2, county='Busia')
	await _fired(svc, 1, evidence='PHEOC bulletin')
	report = svc.deactivate('2026-10-11T12:00:00+00:00', 'PHEOC director')
	assert report.subjects_notified == ('sub-1', 'sub-2')
	assert report.counties_notified == ('Busia',)
	assert '2 people are told' in report.sentence
	assert 'sub-1' not in report.sentence, 'the sentence is read by a person, not a database'


def test_deactivation_clears_the_firings_and_says_so_when_none_fired() -> None:
	"""Closing with nothing fired is allowed and reported as an empty set: it is the honest answer,
	and refusing it would block a close on a deployment whose firings predate this service."""
	svc = _svc()
	report = svc.deactivate('2026-10-11T12:00:00+00:00', 'PHEOC director')
	assert report.subjects_notified == ()
	assert 'No one was reached' in report.sentence
	assert svc.firings() == [], 'a closed event leaves no open firings'
	assert not svc.state().pheoc_event_active


async def test_a_closed_event_stops_activating_its_features() -> None:
	"""The clause's purpose. §11.1 says the clocks *begin* at close, so the firings cannot keep
	resolving features — an event that is closed and a gate that is still open is the state the
	sentence exists to prevent."""
	svc = _svc(active=True)
	await _fired(svc, 1)
	await _fired(svc, 3, subject_ref='sub-1')
	assert svc.feature_available('MON-009', svc.state(subject_ref='sub-1'))

	svc.deactivate('2026-10-11T12:00:00+00:00', 'PHEOC director')
	assert not svc.feature_available('MON-009', svc.state(subject_ref='sub-1')), \
		'the diary does not stay on after the event closes'


def test_every_tier4_data_type_has_a_retention_window() -> None:
	"""A clock cannot be computed for a type §17's table does not define — `policy_for` refuses an
	unknown type, which is the §17 rule this list inherits."""
	for data_type in TIER4_DATA_TYPES:
		assert data_type in RETENTION_TABLE


# --- what the app serves ---------------------------------------------------------------------------

async def _client(tmp_path: Path) -> tuple[httpx.AsyncClient, dict[str, object]]:
	from afya.service import build_services, create_app

	services = build_services(db_path=str(tmp_path / 'afya.db'))
	return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(services)), base_url='http://t'), services


async def _tokens(c: httpx.AsyncClient, services: dict[str, object]) -> tuple[dict[str, str], dict[str, str]]:
	"""A citizen's own token and a sysadmin's: the two roles that reach the two halves of §11.1. Row 5
	is fired by the person it concerns, the operator routes by whoever holds the keys."""
	from afya.privacy.views import RBACRole

	anon = (await c.post('/auth/anonymous', json={'subject_ref': 'U1'})).json()['token']
	auth = services['auth']
	sysadmin = auth.provision_staff('ops-0', RBACRole.sysadmin, registrar='MoH ops').access_token  # type: ignore[attr-defined]
	return {'authorization': f'Bearer {anon}'}, {'authorization': f'Bearer {sysadmin}'}


async def _declare(c: httpx.AsyncClient, headers: dict[str, str]) -> None:
	"""Record §11.1 row 1 — the declaration every Tier-4 surface is dormant without."""
	resp = await c.post('/tier4/activation/fire', headers=headers, json={
		'firing_id': 'TF-00000001', 'trigger_number': 1, 'scope': 'national_or_county',
		'evidence': 'PHEOC bulletin 2026-41', 'fired_by': 'PHEOC duty officer',
		'fired_at_iso': '2026-10-11T09:00:00+00:00',
	})
	assert resp.status_code == 200, resp.text


async def test_a_person_can_activate_outbreak_monitoring_for_themselves(tmp_path) -> None:
	"""Row 5 over HTTP, which is the end the row exists for. The operator route is
	`infrastructure`-scoped and a citizen does not hold it, so without this route the one trigger a
	person fires about themselves is the one they cannot fire."""
	c, services = await _client(tmp_path)
	async with c:
		citizen, _ = await _tokens(c, services)
		before = await c.post('/monitoring/contact/enrol', json={'subject_ref': 'U1'}, headers=citizen)
		assert before.status_code == 403
		assert 'you are identified as a contact' in before.json()['detail']
		assert not FEATURE_CODE.search(before.json()['detail'])

		asked = await c.post('/tier4/activation/request', json={'county': 'Busia'}, headers=citizen)
		assert asked.status_code == 200, asked.text
		assert set(asked.json()['activated']) == {'MON-009', 'LOC-002'}, 'row 5 names exactly these'
		assert 'U1' not in asked.json()['message']

		after = await c.post('/monitoring/contact/enrol', json={'subject_ref': 'U1'}, headers=citizen)
		assert after.status_code == 200, after.text

		assert (await c.get('/tier4/activation', headers=citizen)).status_code == 403, \
			'a citizen does not read the operator view'


async def test_the_activation_view_serves_the_table_the_gap_and_the_firings(tmp_path) -> None:
	"""The operator view: §11.1's five rows with what is firing, the features no row turns on, and the
	recorded firings. An operator deciding whether to close an event reads this."""
	c, services = await _client(tmp_path)
	async with c:
		_, sysadmin = await _tokens(c, services)
		empty = await c.get('/tier4/activation', headers=sysadmin)
		assert empty.status_code == 200, empty.text
		body = empty.json()
		assert [t['number'] for t in body['triggers']] == [1, 2, 3, 4, 5]
		assert all(t['firing'] is False for t in body['triggers'])
		assert len(body['unassigned_features']) == 12
		assert 'LOC-001' in body['divergences']
		assert body['firings'] == []

		fired = await c.post('/tier4/activation/fire', headers=sysadmin, json={
			'firing_id': 'TF-00000002', 'trigger_number': 2, 'scope': 'county', 'county': 'Busia',
			'evidence': 'lab confirmation LAB-2026-4417', 'fired_by': 'PHEOC duty officer',
			'fired_at_iso': '2026-10-11T09:00:00+00:00',
		})
		assert fired.status_code == 200, fired.text

		county = (await c.get('/tier4/activation', params={'county': 'Busia'}, headers=sysadmin)).json()
		assert county['triggers'][1]['firing'] is True, 'row 2 is firing for Busia'
		assert len(county['firings']) == 1
		garissa = (await c.get('/tier4/activation', params={'county': 'Garissa'}, headers=sysadmin)).json()
		assert garissa['triggers'][1]['firing'] is False, 'and not for Garissa'


async def test_a_scope_less_firing_is_a_422_not_a_500(tmp_path) -> None:
	"""The model's own refusal, surfaced. A county firing with no county is a bad request, and an
	uncaught AssertionError would be a 500 that reads as a server fault."""
	c, services = await _client(tmp_path)
	async with c:
		_, sysadmin = await _tokens(c, services)
		resp = await c.post('/tier4/activation/fire', headers=sysadmin, json={
			'firing_id': 'TF-00000003', 'trigger_number': 2, 'scope': 'county',
			'evidence': 'x', 'fired_by': 'y', 'fired_at_iso': '2026-10-11T09:00:00+00:00',
		})
		assert resp.status_code == 422
		assert 'must name the county' in resp.json()['detail']


async def test_closing_the_event_resets_the_gate_and_returns_the_clocks(tmp_path) -> None:
	"""§11.1's closing clause over HTTP, and the three-key gate is cleared with it — otherwise the
	clocks start while the event is still on, which is the contradiction the clause is written
	against."""
	c, services = await _client(tmp_path)
	async with c:
		_, sysadmin = await _tokens(c, services)
		from afya.registry.service import Tier4Activation as Keys
		services['registry'].activate(Keys(  # type: ignore[attr-defined]
			authorized_by_pheoc=True, dpia_review_id='r1', flag_enabled=True))
		assert (await c.get('/health')).json()['tier4'] is True

		resp = await c.post('/tier4/deactivate', headers=sysadmin, params={
			'at_iso': '2026-10-11T12:00:00+00:00', 'closed_by': 'PHEOC director',
		})
		assert resp.status_code == 200, resp.text
		body = resp.json()
		assert {cl['data_type'] for cl in body['clocks']} == set(TIER4_DATA_TYPES)
		assert body['closed_by'] == 'PHEOC director'
		assert (await c.get('/health')).json()['tier4'] is False, 'the gate closes with the event'


async def test_the_operator_routes_refuse_a_citizen(tmp_path) -> None:
	"""The other direction of the scope check: firing a trigger and closing an event are operator
	acts. A citizen holding a valid token must not reach them."""
	c, services = await _client(tmp_path)
	async with c:
		citizen, _ = await _tokens(c, services)
		assert (await c.post('/tier4/activation/fire', headers=citizen, json={
			'firing_id': 'TF-00000004', 'trigger_number': 1, 'scope': 'national_or_county',
			'evidence': 'x', 'fired_by': 'y', 'fired_at_iso': '2026-10-11T09:00:00+00:00',
		})).status_code == 403
		assert (await c.post('/tier4/deactivate', headers=citizen, params={
			'at_iso': '2026-10-11T12:00:00+00:00', 'closed_by': 'x',
		})).status_code == 403


async def test_the_proximity_route_resolves_row_one_and_claims_no_more(tmp_path) -> None:
	"""LOC-002 is rows 1 and 5. An encounter token is anonymous by construction — "identifies an
	encounter without identifying a person" (§11.5) — so this route can only resolve row 1, and it
	must refuse while the event is off rather than logging an encounter nobody activated."""
	c, services = await _client(tmp_path)
	async with c:
		_, sysadmin = await _tokens(c, services)
		token = {'pet': 'p' * 32, 'seen_at_ms': 1_760_000_000_000, 'rssi_dbm': -70, 'county': 'Busia'}
		off = await c.post('/location/proximity/encounter', json=token)
		assert off.status_code == 403
		assert 'the outbreak response is activated' in off.json()['detail']

		from afya.registry.service import Tier4Activation as Keys
		services['registry'].activate(Keys(  # type: ignore[attr-defined]
			authorized_by_pheoc=True, dpia_review_id='r1', flag_enabled=True))
		await _declare(c, sysadmin)
		assert (await c.post('/location/proximity/encounter', json=token)).status_code == 200


def test_the_activation_service_is_wired_into_the_app() -> None:
	"""The model is only a model until a route reaches it. This is the wiring, not the route."""
	from afya.service import build_services

	services = build_services()
	assert isinstance(services['activation'], ActivationService)
	assert services['activation'].firings() == []  # type: ignore[attr-defined]


# --- the client surface, which is where the individual triggers were invisible ---------------------

def _shown(feature_available: object, ids: set[str]) -> set[str]:
	"""The dormant controls a catalogue predicate would reveal. Kept as a pure-function probe so a
	canary can run the predicate against a planted one without an app."""
	from afya.mobile.actions import available

	shown = {a.id for a in available(False, None, feature_available=feature_available)}  # type: ignore[arg-type]
	return shown & ids


def test_the_catalogue_predicate_is_asked_per_feature() -> None:
	"""The pure-function half, where a canary can plant a predicate. Two features on different §11.1
	rows must resolve independently: an always-on Tier-1 feature is never asked, and the two the
	model allows are revealed while the ones it refuses stay hidden."""
	diary = {'enrol_monitoring', 'monitoring_day', 'monitoring_diary'}
	assert _shown(lambda _fid: False, diary) == set(), 'nothing activated, nothing shown'
	assert _shown(lambda _fid: True, diary) == diary, 'row 3 or 5 reveals all three'
	# A predicate that answers True only for the diary's feature still reveals the diary, so the
	# per-feature call is real and not a single global answer.
	assert _shown(lambda fid: fid == 'MON-009', diary) == diary
	assert _shown(lambda fid: fid == 'ALT-004', diary) == set(), 'the wrong feature reveals nothing'


async def test_a_contact_is_shown_the_diary_the_server_would_serve_them(tmp_path) -> None:
	"""The dormancy bug wearing its last hat. The catalogue withheld every Tier-4 control behind the
	one PHEOC boolean, so a person who had asked for monitoring was shown no diary — while
	`/monitoring/contact/enrol` would have served them. A hidden control and a refusing one are the
	same failure from the person's side, and §11.1's individual rows exist to prevent both.

	The claim is made against the *served* payload, because the pure function could agree with the
	route and both be wrong about what a phone draws.
	"""
	c, services = await _client(tmp_path)
	async with c:
		citizen, _ = await _tokens(c, services)
		diary = {'enrol_monitoring', 'monitoring_day', 'monitoring_diary'}

		before = {a['id'] for a in (await c.get('/mobile/actions', headers=citizen)).json()}
		assert not (before & diary), 'no diary before anything activates it'

		assert (await c.post('/tier4/activation/request', json={'county': 'Busia'},
		                     headers=citizen)).status_code == 200
		after = {a['id'] for a in (await c.get('/mobile/actions', headers=citizen)).json()}
		assert diary <= after, f'row 5 activates the diary; the client still hides {sorted(diary - after)}'
		# And the controls the person cannot reach stay hidden: row 5 names MON-009 and LOC-002, not
		# the CHW reporting module, and offering a screen that would 403 is the same defect inverted.
		assert 'submit_case' not in after, 'row 5 does not activate the CHW module'
		assert 'send_exposure_notice' not in after, 'nor ALT-004'


async def test_a_county_case_shows_the_county_its_controls(tmp_path) -> None:
	"""Row 2 is scoped to a county, so the caller's own county decides. A caller in Garissa must not
	be shown Busia's activation, and the route takes `county` for exactly this reason.

	ALT-004 is the feature to check here and not LOC-002: row 2 activates `LOC-001, ALT-004`, and
	LOC-002 belongs to rows 1 and 5. Asserting LOC-002 would have been a test of a claim §11.1 does
	not make — and it would have passed had I widened row 2 to include it, which is a worse outcome
	than the failure that caught it.

	`ack_exposure` rather than `send_exposure_notice`, and the first attempt at this test got that
	wrong: both are ALT-004, but `send_exposure_notice` also carries an `assigned` operator scope, so
	a sysadmin's own §17.4 scope hid it and the activation claim read as a failure of activation.
	Two filters acting on one control means the test has to name the one where only the filter under
	test applies.
	"""
	c, services = await _client(tmp_path)
	async with c:
		_, sysadmin = await _tokens(c, services)
		fired = await c.post('/tier4/activation/fire', headers=sysadmin, json={
			'firing_id': 'TF-00000005', 'trigger_number': 2, 'scope': 'county', 'county': 'Busia',
			'evidence': 'lab confirmation LAB-2026-4417', 'fired_by': 'PHEOC duty officer',
			'fired_at_iso': '2026-10-11T09:00:00+00:00',
		})
		assert fired.status_code == 200, fired.text
		busia = {a['id'] for a in (await c.get('/mobile/actions', params={'county': 'Busia'}, headers=sysadmin)).json()}
		garissa = {a['id'] for a in (await c.get('/mobile/actions', params={'county': 'Garissa'}, headers=sysadmin)).json()}
		assert 'ack_exposure' in busia, 'row 2 activates ALT-004 for the county it names'
		assert 'ack_exposure' not in garissa, 'and not for a county with no case'
		assert 'enrol_monitoring' not in busia, 'row 2 does not activate the contact diary'
