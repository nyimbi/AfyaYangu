"""§17.5 security controls, vulnerability cadence and disclosure.

The row this file exists for is "Secure development — SAST, DAST, dependency scanning in CI": it
was a claim with no CI in the repo. The gate below reads the workflow file and asserts it runs
every command the control table names, so the claim and the workflow cannot drift.
"""
from datetime import date
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from afya.auth.service import AuthService
from afya.privacy.views import RBACRole
from afya.security.service import CI_COMMANDS, SCAN_CADENCE_DAYS, SecurityService
from afya.security.views import ControlKind, VulnerabilityScan
from afya.service import build_services, create_app

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / '.github' / 'workflows' / 'ci.yml'


def test_every_control_names_where_it_is_enforced() -> None:
	svc = SecurityService()
	controls = svc.controls()
	assert len(controls) == 11, '§17.5 lists eleven controls'
	for c in controls:
		assert c.enforced_by.strip(), f'{c.control} names nothing that enforces it'
		if c.kind is ControlKind.code:
			assert c.where, f'{c.control} is a code control with no module named'


def test_workflow_runs_every_command_the_control_table_claims() -> None:
	"""The gate. A control that says "in CI" must name a command the workflow actually runs; a
	workflow that drops the SAST step while the table still claims it is the failure this catches."""
	assert WORKFLOW.exists(), 'the secure-development control claims CI, so a workflow must exist'
	text = WORKFLOW.read_text(encoding='utf-8')
	missing = [cmd for cmd in CI_COMMANDS if cmd not in text]
	assert missing == [], f'the control table claims CI commands the workflow does not run: {missing}'


def test_dast_is_not_claimed_as_ci_enforced() -> None:
	"""§17.5 names DAST, and the workflow does not run it — a dynamic scan needs a live deployment.
	Naming it in CI_COMMANDS would make the row claim a gate that never runs, so it is deliberately
	absent and this test records why rather than leaving it to look like an omission."""
	assert not any('dast' in cmd.lower() for cmd in CI_COMMANDS)
	assert 'dast' in SCAN_CADENCE_DAYS, 'DAST is still a §17.5 obligation, just not a CI one'


def test_a_scan_never_performed_is_overdue() -> None:
	svc = SecurityService()
	obligations = {o.kind: o for o in svc.obligations(date(2026, 10, 10))}
	assert all(o.overdue for o in obligations.values()), 'nothing performed means everything is due'
	assert obligations['sast'].last_performed_iso is None


def test_a_recent_scan_clears_its_obligation_and_an_old_one_does_not() -> None:
	svc = SecurityService()
	svc.record_scan(VulnerabilityScan(scan_id='S1', kind='sast', performed_on_iso='2026-10-01',
	                                  findings_critical=0, findings_high=0, findings_other=2))
	svc.record_scan(VulnerabilityScan(scan_id='S2', kind='penetration', performed_on_iso='2025-01-01',
	                                  findings_critical=0, findings_high=1, findings_other=0))
	by = {o.kind: o for o in svc.obligations(date(2026, 10, 10))}
	assert by['sast'].overdue is False and by['sast'].due_on_iso == '2026-10-31'
	assert by['penetration'].overdue is True, 'a pentest from 21 months ago is overdue on a 90-day cadence'


def test_critical_findings_are_counted_open() -> None:
	svc = SecurityService()
	svc.record_scan(VulnerabilityScan(scan_id='S3', kind='dependency', performed_on_iso='2026-10-05',
	                                  findings_critical=2, findings_high=3, findings_other=1))
	assert svc.open_findings() == (2, 3)


def test_an_unknown_scan_kind_is_refused() -> None:
	"""The model's pattern refuses it at construction, and `record_scan` asserts the kind has a
	cadence — so a new kind added to the pattern without a cadence fails here rather than silently
	becoming an obligation nothing schedules."""
	with pytest.raises(ValidationError):
		VulnerabilityScan(scan_id='S4', kind='vibes', performed_on_iso='2026-10-05',
		                  findings_critical=0, findings_high=0, findings_other=0)
	assert set(SCAN_CADENCE_DAYS) == {'sast', 'dast', 'dependency', 'penetration', 'third_party_audit'}


def test_disclosure_policy_is_public_and_named() -> None:
	policy = SecurityService.disclosure_policy()
	assert policy.contact and policy.acknowledge_within_hours > 0
	assert policy.safe_harbour and policy.in_scope and policy.out_of_scope


# --- the routes ------------------------------------------------------------------------------

def _tokens(services: dict[str, object]) -> tuple[str, str]:
	auth: AuthService = services['auth']  # type: ignore[assignment]
	return (
		auth.provision_staff('ops-0', RBACRole.sysadmin, registrar='MoH ops').access_token,
		auth.provision_staff('ops-1', RBACRole.auditor, registrar='MoH ops').access_token,
	)


async def test_controls_and_posture_are_auditor_scoped() -> None:
	services = build_services()
	_ops, auditor = _tokens(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(services)), base_url='http://t') as c:
		for path in ('/security/controls', '/security/posture'):
			assert (await c.get(path)).status_code in (401, 403), f'{path} must be guarded'
			assert (await c.get(path, headers={'authorization': f'Bearer {auditor}'})).status_code == 200
		# Disclosure is deliberately open: a policy nobody can read is not a policy.
		assert (await c.get('/security/disclosure')).status_code == 200


async def test_posture_reports_the_ci_commands_and_the_overdue_obligations() -> None:
	services = build_services()
	_ops, auditor = _tokens(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(services)), base_url='http://t') as c:
		body = (await c.get('/security/posture', headers={'authorization': f'Bearer {auditor}'})).json()
	assert set(body['ci_enforced']) == set(CI_COMMANDS)
	assert all(o['overdue'] for o in body['process_obligations']), 'no scans recorded yet'


async def test_recording_a_scan_requires_infrastructure_and_refuses_an_unknown_kind() -> None:
	services = build_services()
	sysadmin, auditor = _tokens(services)
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		scan = {'scan_id': 'S9', 'kind': 'sast', 'performed_on_iso': '2026-10-09',
		        'findings_critical': 0, 'findings_high': 0, 'findings_other': 0}
		assert (await c.post('/security/scans', json=scan, headers={'authorization': f'Bearer {auditor}'})).status_code == 403
		assert (await c.post('/security/scans', json=scan, headers={'authorization': f'Bearer {sysadmin}'})).status_code == 200
		bad = {**scan, 'kind': 'vibes'}
		assert (await c.post('/security/scans', json=bad, headers={'authorization': f'Bearer {sysadmin}'})).status_code == 422
