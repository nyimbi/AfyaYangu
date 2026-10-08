import pytest

from afya.privacy.service import PrivacyService
from afya.privacy.views import (
	AccessRequest, BreachEvent, ConsentRecord, DPIAInput, LegalBasis, RBACRole,
)


async def test_consent_roundtrip() -> None:
	svc = PrivacyService()
	rec = await svc.record_consent(ConsentRecord(
		subject_ref='U1', purpose='health_companion', data_types=['demographic'],
		retention_days=730, legal_basis=LegalBasis.legitimate_interest,
	))
	assert svc.has_consent('U1', 'health_companion')
	await svc.withdraw(rec.consent_id)
	assert not svc.has_consent('U1', 'health_companion')
	assert await svc.purge_expired() == 1
	assert await svc.purge_expired() == 0


async def test_legal_obligation_allows_longer_retention() -> None:
	svc = PrivacyService()
	rec = await svc.record_consent(ConsentRecord(
		subject_ref='U2', purpose='notification', data_types=['clinical'],
		retention_days=2000, legal_basis=LegalBasis.legal_obligation,
	))
	assert rec.consent_id


async def test_consent_cap_denied() -> None:
	svc = PrivacyService()
	with pytest.raises(AssertionError):
		await svc.record_consent(ConsentRecord(
			subject_ref='U3', purpose='x', data_types=[], retention_days=1000, legal_basis=LegalBasis.consent,
		))


def test_rbac_scope() -> None:
	svc = PrivacyService()
	assert svc.check_access(AccessRequest(role=RBACRole.chw, dataset='assigned/followup'))
	assert svc.check_access(AccessRequest(role=RBACRole.auditor, dataset='audit_logs'))
	assert not svc.check_access(AccessRequest(role=RBACRole.sysadmin, dataset='clinical/records'))


def test_dpia_blocks_raw_retention() -> None:
	svc = PrivacyService()
	report = svc.assess_dpia(DPIAInput(raw_sensor_data_retained=True))
	assert report.blocked and report.requires_dpia


def test_anonymize_masks_phone() -> None:
	svc = PrivacyService()
	out = svc.anonymize({'phone': '+254712345678', 'location': {'lat': -1.29, 'lon': 36.82}, 'timestamp': '2026-10-07T14:03:22Z'})
	assert '*' in out['phone'] and not out['phone'].endswith('345678')
	assert out['location'] == {'county': 'Coast'}
	assert out['timestamp'] == '2026-10-07'


def test_breach_72h() -> None:
	svc = PrivacyService()
	n1 = svc.breach_notification(BreachEvent(affected_data=['health_status'], affected_count=5, detected_at_days_ago=0))
	n2 = svc.breach_notification(BreachEvent(affected_data=['health_status'], affected_count=5, detected_at_days_ago=3))
	assert n1.odpc_deadline_days == 3 and n1.notify_users
	assert n2.odpc_deadline_days == 0