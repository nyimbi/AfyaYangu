import pytest

from afya.auth.service import AuthService
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


async def test_access_is_logged_durably(tmp_path) -> None:
	"""§17.4: "All access is logged." The log was an in-memory list, so it survived exactly as long
	as the process did, and the `audit_log` table in the schema was never written to."""
	from afya.persistence.service import SqliteStore

	db = str(tmp_path / 'afya.db')
	svc = PrivacyService(SqliteStore(db))
	assert await svc.check_access_logged(AccessRequest(role=RBACRole.chw, dataset='assigned/followup'))
	assert not await svc.check_access_logged(AccessRequest(role=RBACRole.sysadmin, dataset='clinical/records'))

	# A new process reading the same file still sees both decisions, refusals included.
	rows = await SqliteStore(db).audit_entries()
	assert len(rows) == 2
	role, dataset, allowed, at_ms = rows[0]  # most recent first
	assert (role, dataset, allowed) == ('sysadmin', 'clinical/records', False), 'refusals must be logged too'
	assert at_ms > 0


async def test_access_log_is_append_only(tmp_path) -> None:
	"""A control that can be rewritten is not a record. The store exposes insert and read only."""
	from afya.persistence.service import SqliteStore

	db = str(tmp_path / 'afya.db')
	store = SqliteStore(db)
	await store.append_audit('chw', 'assigned/followup', True, 1)
	assert not hasattr(store, 'update_audit') and not hasattr(store, 'delete_audit'), 'no mutation path may exist'
	assert len(await store.audit_entries()) == 1
	assert len(await SqliteStore(db).audit_entries()) == 1


async def test_access_log_endpoint_is_auditor_only_and_records_real_access(tmp_path) -> None:
	"""Readable, and only by the role whose scope is `audit_logs`; a write-only log cannot answer
	"who looked at this record". Driven over HTTP, because the wiring is the part that can break —
	canarying this test against an unlogged `require_scope` must fail it."""
	import httpx

	from afya.auth.views import s256
	from afya.service import build_services, create_app

	services = build_services(db_path=str(tmp_path / 'afya.db'))
	app = create_app(services)
	verifier = 'v' * 64
	challenge = s256(verifier)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		async def worker(role: str) -> str:
			authz = (await c.post('/auth/pkce/authorize', json={
				'client_id': 'app', 'redirect_uri': 'afya://cb', 'code_challenge': challenge, 'state': 'state-1234',
			})).json()
			return str((await c.post('/auth/pkce/token', params={'role': role}, json={
				'authorization_code': authz['authorization_code'], 'client_id': 'app',
				'redirect_uri': 'afya://cb', 'code_verifier': verifier,
			})).json()['access_token'])

		anon = (await c.post('/auth/anonymous', json={'subject_ref': 'U1'})).json()['token']
		assert (await c.get('/privacy/access-log', headers={'authorization': f'Bearer {anon}'})).status_code == 403

		# `auditor` is not issuable through the app flow — auditors do not use the mobile client —
		# so it is provisioned, and only a sysadmin may do the provisioning.
		assert (await c.post('/auth/pkce/token', params={'role': 'auditor'}, json={
			'authorization_code': 'x', 'client_id': 'app', 'redirect_uri': 'afya://cb', 'code_verifier': verifier,
		})).status_code == 401, 'the app flow must not issue an auditor token'
		body = {'operator_ref': 'ops-1', 'registrar': 'MoH ops', 'role': 'auditor'}
		assert (await c.post('/auth/staff/provision', json=body, headers={'authorization': f'Bearer {anon}'})).status_code == 403
		# A sysadmin token cannot come from the app flow either, so the first one is minted directly.
		auth_svc: AuthService = services['auth']  # type: ignore[assignment]
		sysadmin = auth_svc.provision_staff('ops-0', RBACRole.sysadmin, registrar='MoH ops').access_token
		assert (await c.post('/auth/staff/provision', json=body, headers={'authorization': f'Bearer {sysadmin}'})).status_code == 200

		# A guarded route the chw may use, then the auditor reads back what it recorded.
		chw = await worker('chw')
		assert (await c.get('/chw/chw-1/cases', headers={'authorization': f'Bearer {chw}'})).status_code == 200
		auditor = str((await c.post('/auth/staff/provision', json=body,
		                            headers={'authorization': f'Bearer {sysadmin}'})).json()['access_token'])
		log = (await c.get('/privacy/access-log', headers={'authorization': f'Bearer {auditor}'})).json()
		assert log['durable'] is True
		entries = log['entries']
		assert any(e['role'] == 'chw' and e['dataset'] == 'assigned' and e['allowed'] for e in entries), entries
		# Refusals are recorded too, including the citizen's attempt to read this very log.
		assert any(e['role'] == 'citizen_anonymous' and e['dataset'] == 'audit_logs' and not e['allowed'] for e in entries), entries


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