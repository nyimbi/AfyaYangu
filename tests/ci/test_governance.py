"""§15.3 residency, §17.7 sharing agreements, §15.4 capacity — the three sections that were prose.

Each had zero code: every outbound client posted wherever it was configured, nothing knew whether
any agreement existed, and nothing measured a single target. These tests are written so that the
failure mode they guard against — a document claiming compliance nothing enforces — is a red test.
"""
import httpx
import pytest
from pydantic import ValidationError
from typing import Any

from afya.auth.service import AuthService
from afya.governance.service import SCALE_TARGETS, GovernanceService
from afya.governance.views import AgreementParty, DataClass, DataSharingAgreement, Jurisdiction
from afya.privacy.views import RBACRole
from afya.service import build_services, create_app


def _agreement(party: AgreementParty, signed: bool = True) -> DataSharingAgreement:
	return DataSharingAgreement(
		party=party, purpose='national outbreak response', scope=['case_reports'],
		retention_days=365, security='AES-256-GCM, TLS 1.3', audit_rights='MoH may audit on demand',
		signed=signed, signed_on_iso='2026-01-15' if signed else None,
		legal_review_ref='ODPC-2026-0042' if signed else None,
	)


# --- §15.3 residency -------------------------------------------------------------------------

def test_unknown_host_is_not_assumed_safe() -> None:
	"""The default must fail closed: a host nobody classified is outside Africa until a rule says
	otherwise, because the other default ships a transfer nobody reviewed."""
	svc = GovernanceService()
	assert svc.jurisdiction_of('https://api.example.com/v1') is Jurisdiction.outside_africa
	assert svc.jurisdiction_of('https://jali.health.go.ke/api') is Jurisdiction.kenya
	# Longest suffix wins, so a future `.africastalking.com` rule cannot be shadowed by `.ke`.
	assert svc.jurisdiction_of('https://api.africastalking.com') is Jurisdiction.kenya


def test_case_management_may_not_leave_kenya() -> None:
	svc = GovernanceService()
	refused = svc.residency_decision('ministry_of_health', 'https://eu.example.com', DataClass.case_management)
	assert not refused.allowed and 'may not leave' in refused.reason
	allowed = svc.residency_decision('ministry_of_health', 'https://adam.health.go.ke', DataClass.case_management)
	assert allowed.allowed and allowed.jurisdiction is Jurisdiction.kenya


def test_assert_egress_raises_on_a_forbidden_transfer() -> None:
	svc = GovernanceService()
	with pytest.raises(AssertionError, match='may not leave'):
		svc.assert_egress_allowed('ministry_of_health', 'https://graph.facebook.com', DataClass.contact_tracing)
	# The permitted path returns rather than raising, so a caller can log the decision it made.
	assert svc.assert_egress_allowed('telco', 'https://api.africastalking.com', DataClass.citizen_personal).allowed


def test_outside_africa_needs_a_signed_agreement_not_merely_a_class() -> None:
	"""§15.3's "without explicit legal review" is a gate, and the §17.7 agreement is the review.
	The canary: with no agreement the same transfer that is allowed once signed must be refused."""
	svc = GovernanceService()
	host = 'https://graph.facebook.com'
	refused = svc.residency_decision(AgreementParty.meta_whatsapp.value, host, DataClass.citizen_personal)
	assert not refused.allowed, 'no agreement means no exception'

	svc.register(_agreement(AgreementParty.meta_whatsapp))
	allowed = svc.residency_decision(AgreementParty.meta_whatsapp.value, host, DataClass.citizen_personal)
	assert allowed.allowed and 'signed §17.7 agreement' in allowed.reason

	# An unsigned agreement is not a review either.
	svc2 = GovernanceService()
	svc2.register(_agreement(AgreementParty.meta_whatsapp, signed=False))
	assert not svc2.residency_decision(AgreementParty.meta_whatsapp.value, host, DataClass.citizen_personal).allowed


def test_a_free_text_party_name_clears_nothing() -> None:
	"""The exception keys on a §17.7 party, so an arbitrary string cannot invoke it."""
	svc = GovernanceService()
	svc.register(_agreement(AgreementParty.meta_whatsapp))
	dec = svc.residency_decision('definitely-not-a-party', 'https://graph.facebook.com', DataClass.citizen_personal)
	assert not dec.allowed


def test_anonymised_analytics_may_leave_africa_without_an_agreement() -> None:
	"""The spec permits it outright for anonymised data, so this must not depend on the exception."""
	svc = GovernanceService()
	assert svc.residency_decision('cloud_provider', 'https://s3.amazonaws.com', DataClass.anonymised_analytics).allowed


# --- §17.7 agreements ------------------------------------------------------------------------

def test_agreement_needs_every_clause_the_spec_names() -> None:
	"""§17.7 names five clauses. Each is refused when missing — the model is the gate, so an
	agreement cannot be constructed incomplete and then read as one that permits sharing."""
	base: dict[str, Any] = dict(party=AgreementParty.telco, purpose='zero-rating', scope=['msisdn'],
	                            retention_days=30, security='TLS 1.3', audit_rights='annual')
	DataSharingAgreement(**base)  # the complete one constructs
	for field, empty in (('purpose', ''), ('security', ''), ('audit_rights', ''), ('scope', [])):
		with pytest.raises(ValidationError):
			DataSharingAgreement(**{**base, field: empty})


def test_absent_and_unsigned_are_both_a_refusal() -> None:
	svc = GovernanceService()
	assert not svc.may_share(AgreementParty.county_health), 'an absent agreement is a refusal'
	svc.register(_agreement(AgreementParty.county_health, signed=False))
	assert not svc.may_share(AgreementParty.county_health), 'an unsigned agreement is a refusal'
	svc.register(_agreement(AgreementParty.county_health))
	assert svc.may_share(AgreementParty.county_health)


def test_posture_names_the_seven_parties_and_the_unsigned_ones() -> None:
	svc = GovernanceService()
	posture = svc.sharing_posture()
	assert len(posture['parties']) == 7, '§17.7 names seven parties'  # type: ignore[arg-type]
	assert posture['cleared_to_share'] == []
	assert posture['unsigned'] == sorted(p.value for p in AgreementParty)
	svc.register(_agreement(AgreementParty.ministry_of_health))
	assert svc.sharing_posture()['cleared_to_share'] == ['ministry_of_health']


# --- egress audit ----------------------------------------------------------------------------

def test_egress_audit_flags_a_misconfigured_host() -> None:
	"""A deployment whose ADaM URL points outside Kenya is the failure this reports: the client
	would happily post case data there, and only the config decides."""
	svc = GovernanceService()
	clean = svc.egress_violations({'adam': 'https://adam.health.go.ke/api', 'ppb': 'https://ppb.health.go.ke/api'})
	assert clean == [], 'in-jurisdiction wires are not violations'
	dirty = svc.egress_violations({'adam': 'https://adam.example.com/api'})
	assert len(dirty) == 1 and dirty[0].party == AgreementParty.ministry_of_health.value


def test_egress_audit_skips_unconfigured_wires() -> None:
	svc = GovernanceService()
	assert svc.audit_egress({}) == [], 'no URL means the wire is not configured, not that it passed'


# --- §15.4 capacity --------------------------------------------------------------------------

def test_capacity_report_does_not_count_silence_as_compliance() -> None:
	svc = GovernanceService()
	report = svc.capacity_report()
	assert len(report.checks) == len(SCALE_TARGETS)
	assert len(report.unmeasured) == len(SCALE_TARGETS)
	assert report.all_measured_targets_met is False, 'an unmeasured target is not a met one'


def test_latency_and_recovery_targets_are_upper_bounds() -> None:
	"""The direction matters: a p95 of 250 ms meets a 300 ms target, and 3 hours does not meet a
	1-hour RTO. A report that got this backwards would pass a failing deployment."""
	svc = GovernanceService()
	report = svc.capacity_report({'api_latency_p95_ms': 250, 'recovery_time_hours': 3})
	by = {c.metric: c for c in report.checks}
	assert by['api_latency_p95_ms'].within_target is True
	assert by['recovery_time_hours'].within_target is False
	assert report.all_measured_targets_met is False


def test_capacity_targets_match_the_spec_table() -> None:
	assert len(SCALE_TARGETS) == 13, '§15.4 lists thirteen metrics'
	assert all(row[3] == '§15.4' for row in SCALE_TARGETS)
	assert {row[0] for row in SCALE_TARGETS} >= {'api_latency_p95_ms', 'uptime_pct', 'registered_users'}


# --- the routes ------------------------------------------------------------------------------

async def _client() -> httpx.AsyncClient:
	services = build_services()
	return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(services)), base_url='http://t')


def _sysadmin(services: dict[str, object]) -> str:
	auth: AuthService = services['auth']  # type: ignore[assignment]
	return auth.provision_staff('ops-0', RBACRole.sysadmin, registrar='MoH ops').access_token


async def test_residency_and_capacity_routes_require_the_infrastructure_scope() -> None:
	async with await _client() as c:
		for path in ('/governance/residency', '/governance/capacity', '/governance/egress'):
			assert (await c.get(path)).status_code in (401, 403), f'{path} must be guarded'
		anon = (await c.post('/auth/anonymous', json={'subject_ref': 'U1'})).json()['token']
		assert (await c.get('/governance/egress', headers={'authorization': f'Bearer {anon}'})).status_code == 403


async def test_agreements_route_is_auditor_scoped_and_registers() -> None:
	services = build_services()
	auth: AuthService = services['auth']  # type: ignore[assignment]
	sysadmin = _sysadmin(services)
	auditor = auth.provision_staff('ops-1', RBACRole.auditor, registrar='MoH ops').access_token
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		# The auditor may read the posture but not change it: reading which parties we share with is
		# the audit question; recording an agreement is an operator action.
		assert (await c.get('/governance/agreements', headers={'authorization': f'Bearer {auditor}'})).status_code == 200
		body = _agreement(AgreementParty.telco).model_dump(mode='json')
		assert (await c.post('/governance/agreements', json=body, headers={'authorization': f'Bearer {auditor}'})).status_code == 403
		ok = await c.post('/governance/agreements', json=body, headers={'authorization': f'Bearer {sysadmin}'})
		assert ok.status_code == 200 and 'telco' in ok.json()['cleared_to_share']
		# An incomplete agreement is refused, not registered as one that permits sharing.
		bad = {**body, 'purpose': ''}
		assert (await c.post('/governance/agreements', json=bad, headers={'authorization': f'Bearer {sysadmin}'})).status_code == 422


async def test_capacity_route_refuses_an_unknown_metric() -> None:
	services = build_services()
	sysadmin = _sysadmin(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(services)), base_url='http://t') as c:
		good = await c.post('/governance/capacity', json={'api_latency_p95_ms': 120.0},
		                    headers={'authorization': f'Bearer {sysadmin}'})
		assert good.status_code == 200
		report = good.json()
		assert {c_['metric'] for c_ in report['checks'] if c_['observed'] is not None} == {'api_latency_p95_ms'}
		assert report['all_measured_targets_met'] is True
		bad = await c.post('/governance/capacity', json={'vibes': 10.0}, headers={'authorization': f'Bearer {sysadmin}'})
		assert bad.status_code == 422 and 'vibes' in bad.json()['detail']


async def test_egress_route_reports_the_deployments_own_hosts() -> None:
	services = build_services()
	sysadmin = _sysadmin(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(services)), base_url='http://t') as c:
		out = (await c.get('/governance/egress', headers={'authorization': f'Bearer {sysadmin}'})).json()
		# Default config points every national wire at a .go.ke host and the SMS gateway at
		# Africa's Talking (Kenya), so nothing is in violation; WhatsApp is unconfigured and so
		# produces no decision at all.
		assert out['violations'] == [], out['violations']
		assert {d['party'] for d in out['decisions']} == {
			AgreementParty.ministry_of_health.value, AgreementParty.telco.value,
		}, out['decisions']
