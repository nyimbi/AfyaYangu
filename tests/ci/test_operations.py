"""§23 risk register and §24 operational duties, incident response and support SLAs.

§23 is a table whose mitigation column names software — "automated staleness alerts", "bug bounty",
"transparency reports", "manual fallback" — and nothing checked whether any of it existed. §24 is
six governance bodies, four cadence tables, an SLA ladder and an incident-response table, all prose.

The gate this file is built around is `resolve`: every §23 mitigation that claims code enforcement
must name a module in this repo that imports. A register that reads as covered and is not is the
failure mode, so the test walks all thirty-three rows and fails on the first one that does not land.
"""
import httpx
import pytest
from pydantic import ValidationError
from typing import Any

from afya.operations.service import OBLIGATIONS, RCA_DEADLINE_DAYS, RISKS, OperationsService
from afya.operations.views import (
	SUPPORT_SLA_HOURS, Incident, IncidentClass, IncidentSeverity, Obligation, Rating, Risk, RiskDomain,
)
from afya.privacy.views import RBACRole
from afya.security.views import ControlKind
from afya.service import build_services, create_app

TODAY = '2026-10-10'


def _ops_app() -> tuple[Any, dict[str, dict[str, str]]]:
	"""One service instance, so the tokens the app checks are the ones its auth service minted.

	Two tokens, because §17.4 gives the two operational roles different scopes: the read routes
	take `audit_logs` (the auditor's) and the writes take `infrastructure` (the sysadmin's). Using
	one token for both would have made the read assertions pass on a 403 body — the routes are
	right to refuse a sysadmin a dataset the spec does not give it."""
	svc = build_services()
	auth: Any = svc['auth']
	return create_app(svc), {
		'auditor': {'authorization': f"Bearer {auth.provision_staff('ops-aud', RBACRole.auditor, registrar='MoH ops').access_token}"},
		'sysadmin': {'authorization': f"Bearer {auth.provision_staff('ops-sys', RBACRole.sysadmin, registrar='MoH ops').access_token}"},
	}


# --- §23 the register ------------------------------------------------------------------------

def test_the_register_has_every_spec_row() -> None:
	"""§23's five subsections are 5 + 7 + 9 + 7 + 5 rows. A register that quietly lost one would
	still sort and still print; the counts are what make the omission visible."""
	svc = OperationsService()
	counts = {d: len(svc.risks(d)) for d in RiskDomain}
	assert counts == {
		RiskDomain.strategic: 5, RiskDomain.operational: 7, RiskDomain.technical: 9,
		RiskDomain.privacy_ethical: 7, RiskDomain.reputational: 5,
	}, f'§23 row counts drifted: {counts}'
	assert len(RISKS) == 33


def test_every_mitigation_naming_code_resolves() -> None:
	"""The gate. A §23 mitigation that says it is enforced in software has to name software that
	imports — otherwise the register reports a risk as handled on the strength of a string."""
	svc = OperationsService()
	unbacked = svc.unbacked()
	assert unbacked == [], f'§23 mitigations naming controls that do not exist: {unbacked}'
	code_rows = [r for r in RISKS if r.control_kind is ControlKind.code]
	assert len(code_rows) >= 20, 'most of §23 names software; a register of process rows would be a dodge'


def test_a_code_control_with_no_reference_is_refused_at_construction() -> None:
	"""Canary for the gate above, at the model rather than the register: a row claiming code
	enforcement with nothing behind it cannot be built, so it cannot reach `unbacked` at all."""
	with pytest.raises(ValidationError, match='claims code enforcement'):
		Risk(risk_id='R-X1', domain=RiskDomain.technical, statement='x', likelihood=Rating.low,
		     impact=Rating.low, mitigation='y', control_kind=ControlKind.code, owner='z')


def test_the_canary_watches_the_register_fail_on_a_dead_reference() -> None:
	"""The gate must fail on a reference that is well-formed and wrong, not only on a missing one."""
	svc = OperationsService()
	assert svc.resolve('afya.info.service:InfoService.stale') is True
	assert svc.resolve('afya.info.service:InfoService.no_such_method') is False
	assert svc.resolve('afya.nope.service:Thing') is False
	assert svc.resolve('afya.info.service') is False, 'a reference with no attribute is not a reference'


def test_exposure_ranks_by_likelihood_times_impact() -> None:
	"""§23's ratings have an order and the register sorts on it. The product, not the impact alone:
	§23 rates proximity deanonymisation Low likelihood against Very High impact, which is a
	different disposition from a High/High row — treating Very High impact as automatically first
	would rank a rare catastrophe above a likely one, which is not what the column says."""
	svc = OperationsService()
	assert Rating.very_high.rank > Rating.high.rank > Rating.medium.rank > Rating.low.rank
	rows = svc.risks()
	exposures = [r.exposure() for r in rows]
	assert exposures == sorted(exposures, reverse=True), 'the register must be ordered by exposure'
	assert rows[0].exposure() == 9, '§23 has no row above High likelihood, so 3x3 is the ceiling'
	very_high = [r for r in rows if r.impact is Rating.very_high]
	# §23.3's security breach, §23.4's location misuse, proximity deanonymisation, surveillance
	# creep and misuse by authorities, and §23.5's failure during an outbreak.
	assert sorted(r.risk_id for r in very_high) == ['R-P1', 'R-P2', 'R-P4', 'R-P7', 'R-R2', 'R-T7']
	assert all(r.exposure() <= 9 for r in very_high), 'Low/Medium likelihood caps the Very High rows'
	assert all(r.likelihood is not Rating.very_high for r in rows), '§23 rates no risk Very High likelihood'


# --- §24.8 incident response ------------------------------------------------------------------

def test_every_spec_incident_type_is_present_with_its_severity() -> None:
	kinds = {k.kind: k for k in OperationsService.incident_kinds()}
	assert set(kinds) == set(IncidentClass), '§24.8 lists seven incident types'
	assert kinds[IncidentClass.data_breach].severity is IncidentSeverity.critical
	assert kinds[IncidentClass.clinical_content_error].severity is IncidentSeverity.critical
	assert kinds[IncidentClass.privacy_complaint].severity is IncidentSeverity.medium
	assert kinds[IncidentClass.security_vulnerability].severity is IncidentSeverity.high


def test_the_breach_deadline_is_the_statutory_72_hours_and_counts_from_detection() -> None:
	"""§24.8: "notify ODPC within 72h". The clock runs from detection, so an incident written up
	late does not buy time — measuring from `opened_at_iso` would do exactly that."""
	svc = OperationsService()
	breach = Incident(incident_id='I1', kind=IncidentClass.data_breach, summary='lost device',
	                  opened_at_iso='2026-10-05T09:00:00Z', detected_at_iso='2026-10-05T09:00:00Z')
	opened_late = breach.model_copy(update={'opened_at_iso': '2026-10-08T09:00:00Z'})
	assert svc.status(breach, '2026-10-05T09:00:00Z').hours_remaining == 72.0
	# Written up three days late, the clock is unchanged — detection is what starts it.
	assert svc.status(opened_late, '2026-10-05T09:00:00Z').hours_remaining == 72.0
	assert svc.status(breach, '2026-10-08T09:00:00Z').hours_remaining == 0.0
	assert svc.status(breach, '2026-10-08T09:00:00Z').overdue is False, 'exactly 72h is inside the window'


def test_a_breach_two_days_late_is_not_reported_as_on_time() -> None:
	"""The defect this module was built around. `max(0, 3 - days_ago)` made a breach notified three
	days late and one notified with three days to spare both report `0` — a report that cannot tell
	a met statutory duty from a missed one."""
	svc = OperationsService()
	late = Incident(incident_id='I2', kind=IncidentClass.data_breach, summary='x',
	                opened_at_iso='2026-10-05T09:00:00Z', detected_at_iso='2026-10-05T09:00:00Z')
	on_time = svc.status(late, '2026-10-08T06:00:00Z')
	missed = svc.status(late, '2026-10-09T09:00:00Z')
	assert on_time.overdue is False and on_time.hours_remaining == 3.0
	assert missed.overdue is True and missed.hours_remaining == -24.0
	assert missed.notifies == ['odpc', 'affected_users', 'pheoc'], 'the deadline names who is owed it'


def test_an_incident_with_no_spec_deadline_is_not_given_an_invented_one() -> None:
	"""§24.8 describes the outage and the false-alert responses without a number. The row carries
	None and the §24.3 ladder entry instead, because a fabricated deadline reads as a commitment."""
	svc = OperationsService()
	outage = svc.kind_spec(IncidentClass.system_outage)
	assert outage.deadline_hours is None and outage.deadline_basis is None
	assert outage.sla_hours() == SUPPORT_SLA_HOURS[IncidentSeverity.critical]
	false_alert = svc.kind_spec(IncidentClass.false_alert)
	assert false_alert.deadline_hours is None and false_alert.sla_hours() == 2.0


def test_the_rca_deadline_is_five_days_from_detection() -> None:
	svc = OperationsService()
	incident = Incident(incident_id='I3', kind=IncidentClass.system_outage, summary='x',
	                    opened_at_iso='2026-10-05T09:00:00Z', detected_at_iso='2026-10-06T09:00:00Z')
	assert svc.rca_due_on(incident) == '2026-10-11'
	assert RCA_DEADLINE_DAYS == 5


def test_detection_cannot_precede_opening() -> None:
	svc = OperationsService()
	with pytest.raises(AssertionError, match='detection cannot precede'):
		svc.open_incident(Incident(incident_id='I4', kind=IncidentClass.data_breach, summary='x',
		                           opened_at_iso='2026-10-06T09:00:00Z', detected_at_iso='2026-10-05T09:00:00Z'))


# --- §24.3 support SLAs -----------------------------------------------------------------------

def test_the_sla_ladder_is_ordered_and_matches_the_spec() -> None:
	"""§24.3: critical 15 minutes, high 2 hours, medium 24 hours, low 1 week. Ordered so that a
	severity raised on an incident can only tighten its response, never loosen it."""
	slas = {s.severity: s for s in OperationsService.support_slas()}
	assert slas[IncidentSeverity.critical].response_hours == 0.25
	assert slas[IncidentSeverity.high].response_hours == 2.0
	assert slas[IncidentSeverity.medium].response_hours == 24.0
	assert slas[IncidentSeverity.low].response_hours == 168.0
	assert slas[IncidentSeverity.critical].response_label == '15 minutes'
	ordered = [slas[s].response_hours for s in (IncidentSeverity.critical, IncidentSeverity.high,
	                                            IncidentSeverity.medium, IncidentSeverity.low)]
	assert ordered == sorted(ordered), 'the ladder must be monotonic'


# --- §24 duties -------------------------------------------------------------------------------

def test_every_duty_recurs_somehow() -> None:
	"""Canary at the model: §24 is duties that come round again, and one with neither a cadence nor
	a trigger is a duty nobody can be late for."""
	with pytest.raises(ValidationError, match='neither a cadence nor a trigger'):
		Obligation(obligation_id='OPS-99', section='§24.2', owner='nobody', duty='a duty with no recurrence')


def test_a_duty_never_performed_is_overdue_not_exempt() -> None:
	svc = OperationsService()
	statuses = {s.obligation_id: s for s in svc.obligation_status(TODAY)}
	# §24.2's clinical review and §24.7's annual reviews all have cadences and none has been done.
	for oid in ('OPS-1', 'OPS-2', 'OPS-3', 'OPS-4', 'OPS-7', 'OPS-8', 'OPS-9', 'OPS-10'):
		assert statuses[oid].overdue is True and statuses[oid].due_on_iso is None, oid
	assert statuses['OPS-1'].cadence_days == 7, 'outbreak clinical review is weekly (§24.2)'


def test_an_event_triggered_duty_carries_no_due_date() -> None:
	"""§24.7's "on change" and "on publish" are real obligations no calendar schedules. Giving them
	cadence 0 would make them permanently overdue and the overdue list meaningless."""
	svc = OperationsService()
	statuses = {s.obligation_id: s for s in svc.obligation_status(TODAY)}
	for oid in ('OPS-5', 'OPS-6', 'OPS-11', 'OPS-12', 'OPS-13', 'OPS-14'):
		assert statuses[oid].cadence_days is None and statuses[oid].trigger, oid
		assert statuses[oid].overdue is False, f'{oid} is triggered, not scheduled'
	# §24.7's DPIA duty is the one wired into the Tier-4 gate, so it names the control.
	assert statuses['OPS-6'].trigger == 'before each Tier 4 activation'


def test_recording_a_duty_clears_it_and_a_stale_one_comes_back() -> None:
	svc = OperationsService()
	svc.mark_performed('OPS-1', '2026-10-08')
	statuses = {s.obligation_id: s for s in svc.obligation_status(TODAY)}
	assert statuses['OPS-1'].overdue is False and statuses['OPS-1'].due_on_iso == '2026-10-15'
	assert statuses['OPS-2'].overdue is True, 'a monthly duty performed never is still overdue'
	# Two days later the weekly cadence has expired again.
	statuses = {s.obligation_id: s for s in svc.obligation_status('2026-10-16')}
	assert statuses['OPS-1'].overdue is True
	with pytest.raises(AssertionError, match='is not a §24 duty'):
		svc.mark_performed('OPS-999', TODAY)


def test_the_dpia_duty_names_the_gate_that_enforces_it() -> None:
	"""§24.7's "DPIA update before each Tier 4 activation" is not a calendar item — it is the key
	the Tier-4 gate reads. The register must point at the code, not at a reminder."""
	svc = OperationsService()
	dpia = next(o for o in OBLIGATIONS if o.obligation_id == 'OPS-6')
	assert dpia.control == 'afya.privacy.service:PrivacyService.assess_dpia'
	assert svc.resolve(dpia.control) is True


# --- routes -----------------------------------------------------------------------------------

async def test_the_routes_are_scoped_and_refuse_an_anonymous_caller() -> None:
	app, tok = _ops_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
		for path in ('/operations/risks', '/operations/incidents', '/operations/duties'):
			assert (await c.get(path)).status_code in (401, 403), path
			# §17.4 gives the sysadmin `infrastructure`, not `audit_logs`: the evidence views are
			# the auditor's, and a read route that accepted either would be widening a role.
			assert (await c.get(path, headers=tok['sysadmin'])).status_code == 403, path
		assert (await c.get('/operations/risks', headers=tok['auditor'])).json()['unbacked_risks'] == []
		assert len((await c.get('/operations/duties', headers=tok['auditor'])).json()['duties']) == len(OBLIGATIONS)


async def test_the_posture_reports_what_it_has_not_measured() -> None:
	"""§23's register and §24's duties both report absence rather than silence: an empty
	`unbacked_risks` is a real answer only because the test above proves the check can fail."""
	app, tok = _ops_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
		incidents = (await c.get('/operations/incidents', headers=tok['auditor'])).json()
		assert len(incidents['incident_kinds']) == 7 and len(incidents['support_slas']) == 4
		assert incidents['open_incidents'] == []
		duties = (await c.get('/operations/duties', headers=tok['auditor'])).json()
		assert len(duties['overdue']) == 8, 'nothing has been performed, so every cadence duty is late'
		assert duties['event_triggered'] == ['OPS-5', 'OPS-6', 'OPS-11', 'OPS-12', 'OPS-13', 'OPS-14']


async def test_an_incident_can_be_opened_and_read_back_against_its_deadline() -> None:
	app, tok = _ops_app()
	h = tok['sysadmin']
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
		opened = (await c.post('/operations/incidents', headers=h, json={
			'incident_id': 'INC-1', 'kind': 'data_breach', 'summary': 'laptop lost',
			'opened_at_iso': '2026-10-09T09:00:00Z', 'detected_at_iso': '2026-10-09T09:00:00Z',
			'affected_count': 12,
		})).json()
		assert opened['deadline_hours'] == 72 and opened['overdue'] is False
		assert opened['rca_due_on'] == '2026-10-14'
		assert 'odpc' in opened['notifies']
		listed = (await c.get('/operations/incidents', headers=tok['auditor'])).json()['open_incidents']
		assert listed[0]['incident_id'] == 'INC-1'
		# An unknown incident type is refused rather than stored as an unclassifiable row.
		assert (await c.post('/operations/incidents', headers=h, json={
			'incident_id': 'INC-2', 'kind': 'alien_invasion', 'summary': 'x',
			'opened_at_iso': '2026-10-09T09:00:00Z', 'detected_at_iso': '2026-10-09T09:00:00Z',
		})).status_code == 422


async def test_a_duty_can_be_marked_done_through_the_route() -> None:
	app, tok = _ops_app()
	h = tok['sysadmin']
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
		out = (await c.post('/operations/duties/OPS-8/performed', params={'on_iso': '2026-10-01'}, headers=h)).json()
		assert out['ok'] is True and 'OPS-8' not in out['overdue']
		assert (await c.post('/operations/duties/OPS-999/performed', params={'on_iso': TODAY}, headers=h)).status_code == 422
