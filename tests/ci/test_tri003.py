"""§11.2 TRI-003 — the Ebola branch's four Additional inputs and three Outputs that had no carrier.

The section prints three Additional inputs and four Outputs. The classification and the contact
list were implemented; the other five were not, and they failed in three ways:

- **"Specific exposure history (funeral attendance, healthcare work, contact with a case,
  consumption of bushmeat)"** — the input carried one `ebola_contact` boolean, so a funeral and a
  bushmeat exposure read identically to the classifier. They are not the same exposure: one is
  contact with a body, the other contact with an animal source, and the notification the county
  team receives has to say which.
- **"Isolation status"** — the result said "isolate immediately" as advice and carried no input.
  "Isolate now" to someone already in a separate room is a different message from "isolate now" to
  someone who is not, and the section names the input because it changes the answer.
- **"Immediate action (call 719, do not travel by public transport, await instructions)"** — the
  high-risk recommendation named 719 and isolation and never mentioned transport. The transport
  instruction is the one that stops a person carrying the virus onto a matatu, and it was simply
  absent from the payload.
- **"Isolation guidance for the household"** — `JOB_AIDS["isolation_basics"]` is CHW-facing
  reference material behind §5.3's job-aid route, not an output of triage, and a person triaged at
  home cannot reach it.

The clinical content rests on two archived sources — WHO's Ebola disease fact sheet (24 April 2025)
and CDC's About Ebola Disease page — recorded in `sources/INDEX.md` under "Ebola transmission".
The fact sheet is where the 21-day window, the contact-with-a-body route and the animal-source
route come from. It does **not** give a household isolation procedure, so the guidance carries its
provenance rather than implying a citation the source does not hold.

Each gate below is canaried against a planted defect in `canary_tri003.py`.
"""
import httpx
import pytest
from pydantic import ValidationError

from afya.privacy.service import PrivacyService
from afya.privacy.views import ConsentCategory, ConsentRecord, LegalBasis
from afya.registry.service import FeatureRegistry
from afya.triage.service import TriageService
from afya.triage.views import (
	EBOLA_EXPOSURES, HOUSEHOLD_ISOLATION_GUIDANCE, IMMEDIATE_ACTIONS, RiskLevel, TriageInput,
)


def _svc(privacy: PrivacyService | None = None) -> TriageService:
	return TriageService(FeatureRegistry(), privacy)


def _ebola_input(**kw: object) -> TriageInput:
	"""A triage that lands on the Ebola branch: a fever with contact history, §8.1's own rung."""
	return TriageInput(symptoms=['fever', 'headache'], temperature_c=38.2,
	                   ebola_contact=True, county='Garissa', **kw)  # type: ignore[arg-type]


async def _consented(subject: str = 's1') -> PrivacyService:
	"""A consent ledger holding §SEC-001's `share_health_authorities` grant for `subject`.

	The grant is the section's own permission in the section's own words — "sharing this person's
	health data with a health authority" — which is why §11.2's Escalation reads it rather than
	inventing a category of its own.
	"""
	privacy = PrivacyService()
	await privacy.record_consent(ConsentRecord(
		subject_ref=subject, purpose=ConsentCategory.share_health_authorities.value,
		data_types=[ConsentCategory.share_health_authorities.value],
		retention_days=365, legal_basis=LegalBasis.consent))
	return privacy


async def _token(c: httpx.AsyncClient, subject: str = 's') -> dict[str, str]:
	tok = (await c.post('/auth/anonymous', json={'subject_ref': subject})).json()['token']
	return {'authorization': f'Bearer {tok}'}


def _worker_token(auth: object, role: object, ref: str) -> dict[str, str]:
	"""A worker token through the app's own flow — PKCE, because `chw` is not provisionable.

	`provision_staff` refuses a role the app issues, and that refusal is the point: the only way to
	hold `assigned` is to have gone through the flow a real CHW goes through, so a test that minted
	one by hand would be testing a token no deployment can produce.
	"""
	import secrets

	from afya.auth.views import PKCETokenRequest, PKCEStart, s256
	verifier = secrets.token_urlsafe(64)[:64]
	code = auth.start_pkce(PKCEStart(  # type: ignore[attr-defined]
		client_id='chw-app', redirect_uri='afya://cb', code_challenge=s256(verifier),
		state=ref + '-state')).authorization_code
	token = auth.exchange_pkce(  # type: ignore[attr-defined]
		PKCETokenRequest(authorization_code=code, client_id='chw-app', redirect_uri='afya://cb',
		                 code_verifier=verifier), role)
	return {'authorization': f'Bearer {token.access_token}'}


# --- the four named exposures -------------------------------------------------------------------

def test_the_four_named_exposures_are_a_closed_vocabulary() -> None:
	"""§11.2 names four routes and they are the section's own words, snake_cased.

	Closed for the reason `RED_FLAGS` is: an exposure list a client can extend is one the
	classifier cannot reason about, and `model_post_init` refuses an unknown one rather than
	silently accepting a string nothing reads.
	"""
	assert EBOLA_EXPOSURES == ('funeral_attendance', 'healthcare_work', 'case_contact',
	                           'bushmeat_consumption')
	assert TriageInput(symptoms=[], exposures=['funeral_attendance']).exposures == ['funeral_attendance']
	with pytest.raises(ValidationError, match='unknown exposure'):
		TriageInput(symptoms=[], exposures=['touched_a_bat'])

def test_a_named_exposure_is_contact_history_without_the_boolean() -> None:
	"""The four named routes *are* §8.1's epidemiological criteria in detail, so reporting one has
	to count as exposure history on its own.

	A person who reports healthcare work without protective equipment has had contact, whether or
	not they also ticked a boolean labelled "contact with a case" — and the classifier's whole
	Ebola rung keys on `exposure_history`. If the four fed nothing, the section's Additional inputs
	would be a form the person fills in and the algorithm ignores.
	"""
	for exposure in EBOLA_EXPOSURES:
		assert TriageInput(symptoms=[], exposures=[exposure]).exposure_history is True, exposure
	# And the four are distinguishable, which is the defect the audit found: one boolean made a
	# funeral and a bushmeat exposure the same fact.
	funeral = TriageInput(symptoms=[], exposures=['funeral_attendance'])
	bushmeat = TriageInput(symptoms=[], exposures=['bushmeat_consumption'])
	assert funeral.exposures != bushmeat.exposures
	assert funeral.exposure_notes != bushmeat.exposure_notes


def test_each_exposure_says_what_it_means_in_its_own_words() -> None:
	"""A route with no explanation is a frightening fact with no use.

	Each note ends at the 21-day window, because the WHO fact sheet gives one incubation range for
	the disease rather than one per route — and it is the *source's* range, "2 to 21 days", which
	is why the notes say 21 and not 14.
	"""
	notes = TriageInput(symptoms=[], exposures=list(EBOLA_EXPOSURES)).exposure_notes
	assert len(notes) == len(EBOLA_EXPOSURES)
	assert all('21 days' in n for n in notes), notes
	assert len(set(notes)) == len(notes), 'each route gets its own sentence'


def test_the_exposure_notes_do_not_reorder_with_the_request() -> None:
	"""Two clients sending the same set in different orders get the same list in the same order.

	The notes are rendered in the order `EBOLA_EXPOSURES` lists the routes, not in the order the
	request happened to carry them — a list that reshuffles between two identical reports is a list
	the reader has to re-read, and the notification the county team reads would reshuffle too.
	"""
	forwards = TriageInput(symptoms=[], exposures=['funeral_attendance', 'bushmeat_consumption'])
	backwards = TriageInput(symptoms=[], exposures=['bushmeat_consumption', 'funeral_attendance'])
	assert forwards.exposure_notes == backwards.exposure_notes
	assert forwards.exposure_notes[0].startswith('You were near the body')


def test_a_reported_exposure_reaches_the_ebola_branch_through_assess() -> None:
	"""End to end through the classifier: the section's input changes the section's output."""
	svc = _svc()
	without = svc.assess(TriageInput(symptoms=['fever'], temperature_c=38.2))
	with_exposure = svc.assess(TriageInput(symptoms=['fever'], temperature_c=38.2,
	                                        exposures=['funeral_attendance'], county='Garissa'))
	assert without.risk_level is RiskLevel.malaria_suspect
	assert with_exposure.risk_level is RiskLevel.high_ebola_suspicion, (
		'a reported funeral attendance is contact history and the fever is no longer a malaria case'
	)


# --- isolation status ---------------------------------------------------------------------------

def test_isolation_status_is_three_answers_not_two() -> None:
	"""§11.2 names the input; `None` is the third answer and it is the one a client omits.

	"Not asked" and "not isolated" produce the same guidance and different *messages*, which is why
	the field is optional rather than defaulting to `not_isolated` — a default would make every
	caller that never asked claim the person told them.
	"""
	assert TriageInput(symptoms=[]).isolation is None
	with pytest.raises(Exception):
		TriageInput(symptoms=[], isolation='quarantined')  # type: ignore[arg-type]


def test_the_guidance_says_whether_the_person_is_already_isolating() -> None:
	"""The same eight lines read as confirmation to one person and as instruction to another."""
	svc = _svc()
	not_yet = svc.assess(_ebola_input(isolation='not_isolated'))
	at_home = svc.assess(_ebola_input(isolation='isolated_at_home'))
	assert not_yet.household_isolation is not None and at_home.household_isolation is not None
	assert not_yet.household_isolation.already_isolating is False
	assert at_home.household_isolation.already_isolating is True
	assert not_yet.household_isolation.guidance == at_home.household_isolation.guidance
	# The whole list, not a subset: the block is the household's instructions and a truncated one
	# is a family told to separate and not told what to do with the bedding.
	assert not_yet.household_isolation.guidance == list(HOUSEHOLD_ISOLATION_GUIDANCE)
	assert len(HOUSEHOLD_ISOLATION_GUIDANCE) >= 6


# --- the immediate action list ------------------------------------------------------------------

def test_the_three_immediate_actions_all_travel() -> None:
	"""§11.2 prints three and the audit found one of them absent: the transport instruction.

	All three, in the section's order, on every Ebola-suspicion result.
	"""
	svc = _svc()
	out = svc.assess(_ebola_input())
	assert [a.step for a in out.immediate_actions] == [s for s, _, _ in IMMEDIATE_ACTIONS]
	assert [a.step for a in out.immediate_actions] == ['call', 'do_not_travel', 'await_instructions']
	travel = next(a for a in out.immediate_actions if a.step == 'do_not_travel')
	assert 'public transport' in travel.instruction.lower()
	assert travel.detail, 'an instruction with no detail is a sentence a person cannot act on'


def test_the_immediate_actions_are_absent_from_every_other_rung() -> None:
	"""An Output on the wrong rung is as wrong as a missing one.

	"Await instructions" is not a sentence for a person with a mild fever, and a household
	isolation block served to someone whose triage said "monitor; hydrate" would tell a family to
	separate over a headache.
	"""
	svc = _svc()
	for inp in (TriageInput(symptoms=['fever'], temperature_c=38.6),
	            TriageInput(symptoms=['fever', 'headache', 'vomiting', 'rash'], temperature_c=38.5),
	            TriageInput(symptoms=[], temperature_c=37.0)):
		out = svc.assess(inp)
		assert out.risk_level is not RiskLevel.high_ebola_suspicion
		assert out.immediate_actions == [] and out.household_isolation is None


def test_the_result_refuses_the_pair_without_the_classification() -> None:
	"""The gate is the model's, not the service's, so a hand-built result cannot carry the pair.

	A service-level assert is only reached by callers that go through the service; a route that
	constructed a `TriageResult` would not touch it.
	"""
	from afya.triage.views import HouseholdIsolation, ImmediateAction, TriageResult
	with pytest.raises(Exception, match='immediate-action list belongs to the Ebola'):
		TriageResult(risk_level=RiskLevel.low, recommendation='Monitor.', treated_as_malaria_first=False,
		             escalate_719=False, immediate_actions=[ImmediateAction(
		                 step='call', instruction='Call 719', detail='now')])
	with pytest.raises(Exception, match='household isolation guidance belongs to the Ebola'):
		TriageResult(risk_level=RiskLevel.medium, recommendation='Contact hotline.', treated_as_malaria_first=False,
		             escalate_719=True, household_isolation=HouseholdIsolation(
		                 guidance=list(HOUSEHOLD_ISOLATION_GUIDANCE), provenance='WHO'))
	# The escalation flag is the same kind of claim: a result that says the county was told about a
	# malaria case is a result telling a person something untrue about where their data went.
	with pytest.raises(Exception, match='the county team is notified of an Ebola suspicion'):
		TriageResult(risk_level=RiskLevel.low, recommendation='Monitor.', treated_as_malaria_first=False,
		             escalate_719=False, county_rrt_notified=True, county_rrt_note='Told.')
	with pytest.raises(Exception, match='a notification is reported with the sentence'):
		TriageResult(risk_level=RiskLevel.high_ebola_suspicion, recommendation='Isolate.', treated_as_malaria_first=False,
		             escalate_719=True, immediate_actions=[ImmediateAction(
		                 step=s, instruction=i, detail=d) for s, i, d in IMMEDIATE_ACTIONS],
		             household_isolation=HouseholdIsolation(
		                 guidance=list(HOUSEHOLD_ISOLATION_GUIDANCE), provenance='WHO'),
		             county_rrt_notified=True)


# --- the escalation, and the consent it is conditioned on ---------------------------------------

async def test_the_county_team_is_notified_only_with_consent() -> None:
	"""§11.2's Escalation is "an automatic, consented notification … if the user opts in".

	Both halves are checked: the notification goes when the person holds §SEC-001's
	`share_health_authorities` consent, and does not when they do not. The second half is the one a
	gate can miss — a `notify_county_rrt` that never consults the ledger passes the first.
	"""
	inp = _ebola_input(exposures=['funeral_attendance'])
	consented = _svc(await _consented('s1'))
	result = consented.assess(inp)
	notification = consented.notify_county_rrt(inp, result, 's1')
	assert notification is not None, 'the person consented, so the team is told'
	assert notification.county == 'Garissa' and notification.exposures == ['funeral_attendance']
	assert consented.rrt_notifications('Garissa') == [notification]

	declined = _svc(await _consented('someone_else'))
	other = declined.assess(inp)
	assert declined.notify_county_rrt(inp, other, 's1') is None, (
		'consent is held per person; s1 consented, not this service\'s subject'
	)
	assert declined.rrt_notifications('Garissa') == []

	unwired = _svc()
	assert unwired.notify_county_rrt(inp, unwired.assess(inp), 's1') is None, (
		'a service with no consent ledger cannot establish consent, so it does not notify'
	)


async def test_the_escalation_is_not_raised_for_another_classification() -> None:
	"""An Ebola-suspected result triggers it. A malaria case does not.

	The ledger is wired and the person has consented, so the classification is the *only* thing
	that can make this `None`. A test that left the ledger unwired would pass for the wrong reason
	— it would be asserting the unwired refusal, which is a different gate.
	"""
	svc = _svc(await _consented('s1'))
	malaria = TriageInput(symptoms=['fever'], temperature_c=38.6, county='Garissa')
	result = svc.assess(malaria)
	assert result.risk_level is RiskLevel.malaria_suspect
	assert svc.notify_county_rrt(malaria, result, 's1') is None
	assert svc.rrt_notifications('Garissa') == []


async def test_a_notification_with_no_county_goes_nowhere() -> None:
	"""The team is a county team. Without a county there is nobody to address it to.

	Consent is held here too, so the missing county is the only reason it does not go — three
	conditions, three tests, each one leaving exactly one of them unmet.
	"""
	svc = _svc(await _consented('s1'))
	inp = TriageInput(symptoms=['fever', 'headache'], temperature_c=38.2, ebola_contact=True)
	assert svc.notify_county_rrt(inp, svc.assess(inp), 's1') is None
	assert svc.rrt_notifications('') == []


async def test_the_notification_names_no_person_and_no_case_unless_given_one() -> None:
	"""§COM-102's rule from the other end: an alert about a case carries nothing that identifies it.

	`subject_ref` travels because the team has to reach the person, and it is a pseudonymous
	reference — but a notification that named a case would be a case identifier moving through a
	channel that has no need for one.
	"""
	svc = _svc(await _consented('s1'))
	inp = _ebola_input()
	notification = svc.notify_county_rrt(inp, svc.assess(inp), 's1')
	assert notification is not None
	assert notification.case_ref is None
	assert notification.subject_ref == 's1'
	body = f'{notification.headline} {notification.body}'
	assert 'funeral' not in body.lower() or 'contact' in body.lower(), (
		'the body says what to do; the exposures travel as slugs the team reads'
	)


# --- end to end through the real app ------------------------------------------------------------

async def test_the_route_escalates_only_for_a_caller_who_consented() -> None:
	"""The wiring: the route reads the ledger, and the result says which of the two it was.

	A client cannot tell a decline from a non-event, so the note distinguishes them — and a person
	who declined must never be told a team was told. The dormant half is asserted first, because
	§11.2 sits behind §11.1's gate and a test that skipped the gate would be testing a route that
	is unreachable in the deployment it describes.
	"""
	from afya.registry.service import Tier4Activation
	from afya.service import build_services, create_app
	services = build_services()
	app = create_app(services)
	triage: TriageService = services['triage']  # type: ignore[assignment]
	body = {'symptoms': ['fever', 'headache'], 'temperature_c': 38.2, 'ebola_contact': True,
	        'county': 'Garissa', 'exposures': ['funeral_attendance'], 'isolation': 'not_isolated'}
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		head = await _token(c, 's1')
		dormant = await c.post('/triage/evd', headers=head, json=body)
		assert dormant.status_code == 403, dormant.text

		# §11.1's three-key gate, opened. The route is not reachable before this and the escalation
		# cannot be reached after it without consent, which is the pair of conditions §11.2 names.
		registry: FeatureRegistry = services['registry']  # type: ignore[assignment]
		registry.activate(Tier4Activation(authorized_by_pheoc=True, flag_enabled=True,
		                                  dpia_review_id='DPIA-2026-10'))
		privacy: PrivacyService = services['privacy']  # type: ignore[assignment]
		await privacy.record_consent(ConsentRecord(
			subject_ref='s1', purpose=ConsentCategory.share_health_authorities.value,
			data_types=[ConsentCategory.share_health_authorities.value],
			retention_days=365, legal_basis=LegalBasis.consent))

		told = await c.post('/triage/evd', headers=head, json=body)
		assert told.status_code == 200, told.text
		assert told.json()['risk_level'] == 'high_ebola_suspicion'
		assert told.json()['county_rrt_notified'] is True, told.text
		assert [n.subject_ref for n in triage.rrt_notifications('Garissa')] == ['s1']
		assert told.json()['household_isolation']['already_isolating'] is False
		assert [a['step'] for a in told.json()['immediate_actions']] == [
			'call', 'do_not_travel', 'await_instructions']

		# The same person, consent withdrawn — the notification stops and the result says so.
		declined = await c.post('/triage/evd', headers=await _token(c, 's2'), json=body)
		assert declined.status_code == 200, declined.text
		assert declined.json()['county_rrt_notified'] is False
		assert declined.json()['county_rrt_note'], 'a decline is explained, not silent'
		assert [n.subject_ref for n in triage.rrt_notifications('Garissa')] == ['s1'], (
			's2 never consented and no notification names them'
		)

		# And anonymously, which §8.1's Tier 1 triage requires: no token is still an answer.
		anon = await c.post('/triage/preliminary', json={
			'symptoms': ['fever'], 'temperature_c': 38.6, 'county': 'Garissa'})
		assert anon.status_code == 200, anon.text
		assert anon.json()['risk_level'] == 'malaria_suspect'
		assert anon.json()['immediate_actions'] == [], 'the Ebola pair is not on this rung'


async def test_the_county_view_is_scoped_and_shows_what_was_sent() -> None:
	"""§11.2's Escalation from the team's side. The route is an operator scope, not a citizen one.

	Both halves: a citizen is refused, and the worker who holds the scope reads the notification
	with the exposures on it. The refusal alone would pass against a route that returned an empty
	list to everyone.
	"""
	from afya.privacy.views import RBACRole
	from afya.registry.service import Tier4Activation
	from afya.service import build_services, create_app
	services = build_services()
	app = create_app(services)
	triage: TriageService = services['triage']  # type: ignore[assignment]
	registry: FeatureRegistry = services['registry']  # type: ignore[assignment]
	privacy: PrivacyService = services['privacy']  # type: ignore[assignment]
	registry.activate(Tier4Activation(authorized_by_pheoc=True, flag_enabled=True,
	                                  dpia_review_id='DPIA-2026-10'))
	await privacy.record_consent(ConsentRecord(
		subject_ref='s1', purpose=ConsentCategory.share_health_authorities.value,
		data_types=[ConsentCategory.share_health_authorities.value],
		retention_days=365, legal_basis=LegalBasis.consent))
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		head = await _token(c, 's1')
		await c.post('/triage/evd', headers=head, json={
			'symptoms': ['fever', 'headache'], 'temperature_c': 38.2, 'ebola_contact': True,
			'county': 'Garissa', 'exposures': ['funeral_attendance'],
			'isolation': 'isolated_at_home'})
		# A citizen token cannot read the county's queue — the escalation is one-way by design.
		assert (await c.get('/triage/rrt/Garissa', headers=head)).status_code == 403
		# The team's own scope reads it, and reads what the person reported.
		chw = _worker_token(services['auth'], RBACRole.chw, 'chw-1')
		read = await c.get('/triage/rrt/Garissa', headers=chw)
		assert read.status_code == 200, read.text
		rows = read.json()
		assert [r['county'] for r in rows] == ['Garissa']
		assert rows[0]['exposures'] == ['funeral_attendance']
		assert rows[0]['isolation'] == 'isolated_at_home'
		assert rows[0]['case_ref'] is None
		# A county with nothing filed reads an empty queue rather than another county's.
		assert (await c.get('/triage/rrt/Busia', headers=chw)).json() == []
		assert len(triage.rrt_notifications('Garissa')) == 1
