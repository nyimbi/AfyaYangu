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

from afya.operations.service import (
	MITIGATION_DIVERGENCES, OBLIGATIONS, RCA_DEADLINE_DAYS, RISKS, OperationsService,
)
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


def _spec_rows(heading: str, stop: str, columns: int, header: str) -> list[list[str]]:
	"""A spec table's rows read out of `docs/spec.md`, so a revision to the section fails here.

	`header` is the first cell of the table's header row, passed in rather than enumerated: the
	first cut of this helper listed three header names and silently swallowed the two tables whose
	header it had not thought of, which is a checker enumerating one of the ways its target can be
	written. The caller knows which table it is reading.

	Shared by §23 and §24. It sits above both because §23's register is compared cell for cell for
	the same reason §24.1's governance bodies are: a check on row *counts* cannot see a row whose
	*cells* drifted, and five cells across §23's thirty-three rows had.
	"""
	from pathlib import Path
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	section = text.split(heading, 1)[1].split(stop, 1)[0]
	rows: list[list[str]] = []
	for line in section.splitlines():
		if not line.startswith('|') or set(line) <= set('|-: '):
			continue
		cells = [c.strip() for c in line.strip('|').split('|')]
		if len(cells) != columns or cells[0] == header:
			continue
		rows.append(cells)
	return rows


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


# §23's five tables, in the spec's own order. The heading is the section heading and the stop is the
# next thing the file writes, so each table is read out of its own subsection rather than by position.
_RISK_TABLES = (
	('### 23.1 Strategic Risks', '\n### 23.2'),
	('### 23.2 Operational Risks', '\n### 23.3'),
	('### 23.3 Technical Risks', '\n### 23.4'),
	('### 23.4 Privacy and Ethical Risks', '\n### 23.5'),
	('### 23.5 Reputational Risks', '\n---'),
)


def _spec_risk_rows() -> list[list[str]]:
	"""§23's thirty-three rows read out of `docs/spec.md`, in file order.

	File order and register order are the same order — `RISKS` is written §23.1 through §23.5 and the
	ids are assigned here rather than read from the section, which numbers none of its rows. That is
	what lets the comparison be positional and therefore cell-exact; a `risk_id`-keyed comparison
	would need the section to carry ids it does not have.
	"""
	rows: list[list[str]] = []
	for heading, stop in _RISK_TABLES:
		rows += _spec_rows(heading, stop, 4, 'Risk')
	return rows


def test_the_register_is_the_sections_table_cell_for_cell() -> None:
	"""The gate §23 never had, and the reason the row-count test above is not enough.

	`test_the_register_has_every_spec_row` asserts 5 + 7 + 9 + 7 + 5 and passes for a register whose
	every cell has drifted — a count is blind to content, which is the strict-subset failure: the
	predicate is a subset of the thing it claims to test, so it fails open and it fails toward
	"clean". Five cells had drifted green while it passed:

	* **R-O7's likelihood** read `medium` against §23.2's `High`, a plain transcription error, and the
	  one that changes behaviour: `Risk.exposure()` is likelihood × impact, so the register ranked
	  alert fatigue *below* the rows around it and would have sorted it later on a fix-first list.
	* **R-P7's mitigation** dropped "open source" — the one mitigation in that row that is checkable
	  from outside the repo, and the repo has a `LICENSE` at its root. The row read as covered while
	  naming two mechanisms where §23.4 names three.
	* **R-S1's mitigation** dropped "before launch", which is the whole of what makes a zero-rating
	  agreement a mitigation: an agreement signed after launch is a response to the risk, not a
	  control on it.
	* **R-S2's statement** carried `an Ebola app` where §23.2 quotes the brand `"Ebola app"`. The
	  quotes are the row — the risk is being *branded* as an outbreak app, and the paraphrase made it
	  read as being one.

	The remaining divergence is R-T2, where the *section* is what is out of date (§23.3 names Flutter;
	§15.2 records Flutter → SwiftUI + Kotlin and the clients are native). It is excused by name
	through `MITIGATION_DIVERGENCES` rather than left to pass, so an *unrecorded* divergence fails
	here and the two states stay distinguishable — a gate that skipped any row it could not explain
	would be the same failure as the count check, one level up.
	"""
	spec = _spec_risk_rows()
	assert len(spec) == 33, f'§23 lists thirty-three risks, found {len(spec)}'
	assert len(RISKS) == len(spec)

	def _rating(cell: str) -> str:
		return cell.strip().lower().replace(' ', '_')

	mismatched: list[str] = []
	for (statement, likelihood, impact, mitigation), risk in zip(spec, RISKS):
		# §23.2 writes `Branded as "Ebola app"`; the double quotes are the section's own quoting of
		# the brand and the register carries them verbatim, so no stripping is needed here. What *is*
		# stripped is `**`, which §24's tables use for emphasis and §23's do not — kept so this
		# comparison and the §24 ones normalise alike and a later emphasis pass on §23 cannot read as
		# a cell drift.
		if risk.statement != statement.replace('**', ''):
			mismatched.append(f'{risk.risk_id} statement: §23 {statement!r} vs register {risk.statement!r}')
		if risk.likelihood.value != _rating(likelihood):
			mismatched.append(f'{risk.risk_id} likelihood: §23 {likelihood} vs register {risk.likelihood.value}')
		if risk.impact.value != _rating(impact):
			mismatched.append(f'{risk.risk_id} impact: §23 {impact} vs register {risk.impact.value}')
		if risk.mitigation != mitigation and risk.risk_id not in MITIGATION_DIVERGENCES:
			mismatched.append(f'{risk.risk_id} mitigation: §23 {mitigation!r} vs register {risk.mitigation!r}')
	assert mismatched == [], '§23 cells drifted from the register: ' + '; '.join(mismatched)


def test_the_recorded_mitigation_divergences_are_still_divergences() -> None:
	"""A recorded divergence that has since been reconciled is a stale excuse, and a stale excuse
	exempts a row from the gate above for no reason.

	This is the other half of the cell test: that one reads the map to *excuse* a cell, so a map
	entry naming a row that now matches the section silently widens the gate's blind spot. Same shape
	as the §13.1 lossy-enum defect — a note a reader cannot check is a note that drifts.
	"""
	spec = {r.risk_id: row for r, row in zip(RISKS, _spec_risk_rows())}
	for risk_id, reason in MITIGATION_DIVERGENCES.items():
		assert spec[risk_id][3] != next(r.mitigation for r in RISKS if r.risk_id == risk_id), (
			f'{risk_id} is recorded as a mitigation divergence but now carries §23 verbatim — '
			f'remove it from MITIGATION_DIVERGENCES')
		assert '§' in reason, f'{risk_id} divergence names no spec section: {reason!r}'


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


# --- §24.1 governance, §24.3 support channels -------------------------------------------------

def test_the_governance_bodies_are_the_sections_six_rows() -> None:
	"""§24.1, cell for cell. The composition cell is the section's, split on its commas — the
	Operations Cell is four roles, and a body carrying one string would be a committee of one."""
	from afya.operations.service import GOVERNANCE_BODIES
	spec = _spec_rows('### 24.1 Governance', '\n### ', 3, 'Body')
	assert len(spec) == 6, f'§24.1 lists six bodies, found {len(spec)}'
	assert [b.body for b in GOVERNANCE_BODIES] == [r[0].replace('**', '') for r in spec]
	assert [b.role for b in GOVERNANCE_BODIES] == [r[2] for r in spec]
	for row, (_, composition, _role) in zip(GOVERNANCE_BODIES, spec):
		assert row.composition == [c.strip() for c in composition.split(',')], f'{row.body} composition'


def test_every_duty_owner_sits_on_a_governance_body() -> None:
	"""The finding. §24.2–§24.7 assign duties to owners and §24.1 seats those roles on bodies; an
	owner on no body is a duty with nobody accountable for it."""
	report = OperationsService().governance()
	assert report.unlisted_owners == [], f'duty owners seated on no §24.1 body: {report.unlisted_owners}'
	assert report.duty_owners == sorted({o.owner for o in OBLIGATIONS})
	# The reverse is reported rather than repaired, and the Steering Committee is the honest instance:
	# its role is "strategic direction, funding, escalation", none of which is a recurring duty §24
	# schedules. A body given a fabricated owner to clear the list would be the register lying.
	assert report.unowned_bodies == ['Steering Committee'], (
		'a body accounting for no §24 duty must be named, not quietly given one')
	assert 'clinical_advisory_group' in next(b for b in report.bodies if b.body == 'Clinical Advisory Group').owners
	assert 'dpo' in next(b for b in report.bodies if b.body == 'Privacy and Ethics Board').owners


def test_the_support_channels_are_the_sections_five_rows() -> None:
	"""§24.3's coverage column, verbatim. "8am–8pm, 7 days" and "24/7 (self-service)" are different
	commitments and a boolean would flatten the difference between a staffed line and a help page."""
	from afya.operations.service import SUPPORT_CHANNELS
	spec = _spec_rows('### 24.3 Support Operations', '\n**Response SLAs', 3, 'Channel')
	assert len(spec) == 5, f'§24.3 lists five support channels, found {len(spec)}'
	assert [c.channel for c in SUPPORT_CHANNELS] == [r[0] for r in spec]
	assert [c.coverage for c in SUPPORT_CHANNELS] == [r[1] for r in spec]
	report = OperationsService().governance()
	assert report.unstaffed_channels == [], 'every channel has a coverage window'
	assert report.staffed_agents == 8, '§24.3 rosters five WhatsApp agents and three on the phone'
	# The self-service row carries an em dash in the Staffing column, which is not a headcount of
	# zero — a zero would read as an unstaffed channel rather than one nobody is rostered on.
	help_row = next(c for c in SUPPORT_CHANNELS if c.channel == 'In-app help')
	assert help_row.staffing is None and help_row.agents is None and help_row.always_on
	assert sum(c.always_on for c in SUPPORT_CHANNELS) == 3, 'in-app, CHW escalation and incidents are 24/7'


def test_the_canary_watches_the_owner_join_fire() -> None:
	"""Canary. Seat a duty owner on no body and the join must name it. If this passes, the check is
	comparing the owner list against itself."""
	from afya.operations import service as os_
	original = os_.GOVERNANCE_BODIES
	try:
		os_.GOVERNANCE_BODIES = tuple(
			b.model_copy(update={'owners': [o for o in b.owners if o != 'dpo']})
			if b.slug == 'privacy_and_ethics_board' else b for b in original)
		unlisted = os_.OperationsService().governance().unlisted_owners
		assert unlisted == ['dpo'], f'the unseated owner went unnoticed: {unlisted}'
	finally:
		os_.GOVERNANCE_BODIES = original
	assert os_.OperationsService().governance().unlisted_owners == [], 'canary left the module mutated'


async def test_the_governance_route_is_scoped_and_serves_both_tables() -> None:
	app, headers = _ops_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		assert (await c.get('/operations/governance')).status_code in (401, 403)
		r = await c.get('/operations/governance', headers=headers['auditor'])
		assert r.status_code == 200, r.text
		body = r.json()
		assert len(body['bodies']) == 6 and len(body['support_channels']) == 5
		assert body['unowned_bodies'] == ['Steering Committee']
		assert body['staffed_agents'] == 8
		# The sysadmin holds `infrastructure`, not `audit_logs`: §17.4 gives the evidence reads to the
		# auditor, and this route names roles and headcounts.
		assert (await c.get('/operations/governance', headers=headers['sysadmin'])).status_code == 403


# --- §24.4 training, §24.5 funding ------------------------------------------------------------

def test_the_training_matrix_is_the_sections_seven_rows() -> None:
	"""§24.4, cell for cell. `hours` is the Duration column as a number so the matrix can be
	totalled; the section's own string stays beside it, because "2 days" and "4 hours" are both
	durations and only one of them is a number of hours."""
	from afya.operations.service import TRAINING
	spec = _spec_rows('### 24.4 Training', '\n**Refresher', 4, 'Audience')
	assert len(spec) == 7, f'§24.4 lists seven audiences, found {len(spec)}'
	assert [t.audience for t in TRAINING] == [r[0] for r in spec]
	assert [t.content for t in TRAINING] == [r[1] for r in spec]
	assert [t.format for t in TRAINING] == [r[2] for r in spec]
	assert [t.duration for t in TRAINING] == [r[3] for r in spec]
	# An 8-hour training day, which is what makes "2 days" comparable with "4 hours" at all.
	expected = {'2 days': 16.0, '4 hours': 4.0, '1 day': 8.0, '3 days': 24.0, '2 hours': 2.0, '1 hour': 1.0}
	for t in TRAINING:
		assert t.hours == expected[t.duration], f'{t.audience}: {t.duration}'
	report = OperationsService().support_plan()
	assert report.training_hours == 71.0
	assert report.refresher == 'Quarterly' and report.new_feature_training == 'On release'


def test_the_funding_model_is_the_sections_four_bands_and_covers_every_phase() -> None:
	"""§24.5, cell for cell, with the primary-funding cell split on its commas. The finding is the
	other direction: a §21 phase no band pays for is a phase nothing funds."""
	from afya.operations.service import FUNDING
	spec = _spec_rows('### 24.5 Funding Model', '\n**Cost drivers', 3, 'Phase')
	assert len(spec) == 4, f'§24.5 lists four bands, found {len(spec)}'
	assert [f.phase for f in FUNDING] == [r[0] for r in spec]
	for band, (_, funding, _sustain) in zip(FUNDING, spec):
		parts = [p.strip() for p in funding.replace(' + ', ', ').split(',')]
		assert band.primary_funding == parts, f'{band.phase} funding'
	report = OperationsService().support_plan()
	assert report.unfunded_stages == [], f'§21 phases no §24.5 band funds: {report.unfunded_stages}'
	# The bands tile §21's seven phases with no gap and no overlap. A single ceiling per band was the
	# first cut and it made the coverage check vacuous — every phase is at or below the last band's
	# ceiling by construction, so the check could never name one.
	covered = [n for f in FUNDING for n in range(f.phase_floor, f.phase_ceiling + 1)]
	assert sorted(covered) == list(range(7)), f'§24.5 must tile §21 phases 0-6: {sorted(covered)}'
	# The em dash in the sustainability column is None, not an empty string: the emergency and build
	# bands are not meant to sustain, and a fabricated answer would read as a plan for the
	# integration the next row says has not begun.
	assert [f.sustainability for f in FUNDING[:2]] == [None, None]
	assert FUNDING[-1].sustainability == 'Fully integrated into national health budget'


def test_an_audience_no_governance_body_accounts_for_is_reported() -> None:
	"""The finding. §24.4 names seven audiences and §24.1 names six bodies; an audience no body
	accounts for is a group expected to use the product with nobody responsible for teaching them."""
	report = OperationsService().support_plan()
	assert report.untrained_audiences == ['Facility staff', 'Radio partners'], (
		'the audiences with no §24.1 body must be named, not quietly assigned one')
	# CHWs sit on the Community Advisory Panel and support agents staff the Operations Cell, so those
	# two audiences do resolve — the list is short because the join is narrow, not because it is off.
	by_audience = {t.audience: t.body for t in report.training}
	assert by_audience['CHWs'] == 'Community Advisory Panel'
	assert by_audience['Support agents'] == 'Operations Cell'
	assert sum(t.body is not None for t in report.training) == 5


def test_the_cost_drivers_and_mitigations_are_the_sections_lists() -> None:
	"""§24.5's two closing lists, verbatim. A cost driver dropped is a line item nobody budgeted."""
	from afya.operations.service import COST_DRIVERS, COST_MITIGATIONS
	assert COST_DRIVERS == ('Engineering', 'content', 'translation', 'cloud', 'SMS/WhatsApp',
	                        'support', 'training', 'evaluation')
	assert len(COST_MITIGATIONS) == 5
	assert COST_MITIGATIONS[0].startswith('Zero-rating reduces user cost')
	# The open-source mitigation is the same claim §20.2 lever 3 makes, and §24.5 is where it is
	# counted as a cost saving rather than as a trust measure.
	assert any('Open-source' in m for m in COST_MITIGATIONS)


def test_the_canary_watches_the_audience_join_fire() -> None:
	"""Canary. Give the radio partners a body and the untrained list must lose them. If this passes,
	the check is comparing the training list against itself."""
	from afya.operations import service as os_
	original = os_.TRAINING
	try:
		os_.TRAINING = tuple(
			t.model_copy(update={'body': 'Operations Cell'}) if t.audience == 'Radio partners' else t
			for t in original)
		untrained = os_.OperationsService().support_plan().untrained_audiences
		assert untrained == ['Facility staff'], f'the join went unnoticed: {untrained}'
	finally:
		os_.TRAINING = original
	assert os_.OperationsService().support_plan().untrained_audiences == ['Facility staff', 'Radio partners']


async def test_the_support_plan_route_is_scoped_and_serves_both_tables() -> None:
	app, headers = _ops_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		assert (await c.get('/operations/support-plan')).status_code in (401, 403)
		r = await c.get('/operations/support-plan', headers=headers['auditor'])
		assert r.status_code == 200, r.text
		body = r.json()
		assert len(body['training']) == 7 and len(body['funding']) == 4
		assert body['training_hours'] == 71.0
		assert body['unfunded_stages'] == []
		assert (await c.get('/operations/support-plan', headers=headers['sysadmin'])).status_code == 403


# --- §24.6 sustainability ---------------------------------------------------------------------

def test_the_sustainability_mitigations_are_the_sections_eight() -> None:
	"""§24.6's eight numbered mitigations, verbatim. A mitigation dropped is an argument for the
	product's survival that nobody is making."""
	import re
	from pathlib import Path
	from afya.operations.service import SUSTAINABILITY
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	section = text.split('### 24.6 Sustainability Beyond the Outbreak', 1)[1].split('\n### ', 1)[0]
	# The section's mitigations are a numbered list with the lead bolded, so the text is the rest of
	# the line after the bolded clause — which is what `mitigation` carries.
	spec = [re.sub(r'\*\*', '', m.group(1)).strip()
	        for m in re.finditer(r'^\d+\.\s+(.*)$', section, flags=re.MULTILINE)]
	assert len(spec) == 8, f'§24.6 lists eight mitigations, found {len(spec)}'
	assert [m.mitigation for m in SUSTAINABILITY] == spec
	assert [m.number for m in SUSTAINABILITY] == list(range(1, 9))


def test_every_mitigation_naming_an_artefact_resolves_and_the_rest_say_so() -> None:
	"""The finding. Seven name something in this build and resolve; the eighth names no artefact and
	is reported as a process commitment rather than given a reference that always lands."""
	svc = OperationsService()
	report = svc.sustainability()
	assert report.unbacked_mitigations == [], f'§24.6 naming a missing artefact: {report.unbacked_mitigations}'
	assert report.process_mitigations == ['8. Regional expansion shares cost across countries']
	# `resolve(None)` returns True — the §23 convention that a process control resolves by
	# definition — which is why the process list is computed from `control is None` rather than read
	# off `resolve`. A check that took resolve's word for it would report eight of eight.
	assert svc.resolve(None) is True
	assert sum(m.control is not None for m in report.mitigations) == 7
	# §24.6 mitigation 3 is the same integration §24.5's last band states, and it resolves against
	# the funding table rather than against a second copy of the claim.
	assert next(m for m in report.mitigations if m.number == 3).control == 'afya.operations.service:FUNDING'


def test_the_canary_watches_the_sustainability_check_fire() -> None:
	"""Canary. Point a mitigation at a module this build does not have and the check must name it.
	If this passes, the check is resolving against nothing."""
	from afya.operations import service as os_
	original = os_.SUSTAINABILITY
	try:
		os_.SUSTAINABILITY = tuple(
			m.model_copy(update={'control': 'afya.nothing.service:MISSING'}) if m.number == 7 else m
			for m in original)
		unbacked = os_.OperationsService().sustainability().unbacked_mitigations
		assert len(unbacked) == 1 and 'Open-source community' in unbacked[0], f'went unnoticed: {unbacked}'
	finally:
		os_.SUSTAINABILITY = original
	assert os_.OperationsService().sustainability().unbacked_mitigations == [], 'canary left the module mutated'


async def test_the_sustainability_route_is_scoped_and_serves_the_mitigations() -> None:
	app, headers = _ops_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		assert (await c.get('/operations/sustainability')).status_code in (401, 403)
		r = await c.get('/operations/sustainability', headers=headers['auditor'])
		assert r.status_code == 200, r.text
		body = r.json()
		assert len(body['mitigations']) == 8
		assert body['unbacked_mitigations'] == []
		assert len(body['process_mitigations']) == 1
		assert (await c.get('/operations/sustainability', headers=headers['sysadmin'])).status_code == 403
