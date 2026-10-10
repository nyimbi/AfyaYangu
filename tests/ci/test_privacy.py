import pytest
from pydantic import ValidationError

from afya.auth.service import AuthService
from afya.privacy.service import PrivacyService
from afya.privacy.views import (
	AccessRequest, BreachEvent, ConsentCategory, ConsentRecord, ConsentScope, DPIAInput, LegalBasis,
	RBACRole,
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
	# §24.8's clock floors at zero — the DPA gives a fixed window, not a negative one — so the
	# deadline alone cannot tell a breach notified on time from one notified late. `overdue` is
	# what carries it: without that field a three-day-late notification and a three-day-early one
	# both read `0`, which is a report that cannot distinguish a met statutory duty from a missed.
	late = svc.breach_notification(BreachEvent(affected_data=['health_status'], affected_count=5, detected_at_days_ago=5))
	assert n1.odpc_deadline_days == 3 and n1.notify_users and n1.overdue is False
	assert n2.odpc_deadline_days == 0 and n2.overdue is False
	assert late.odpc_deadline_days == 0 and late.overdue is True

# --- §SEC-001 consent categories ------------------------------------------------------------

async def test_the_catalogue_has_the_eight_spec_categories() -> None:
	"""§SEC-001 lists eight consent categories. Granularity is the whole claim — one blanket
	"agree" toggle is what the section exists to replace — so the set is closed and pinned."""
	svc = PrivacyService()
	cats = [c.category for c in svc.consent_catalogue()]
	assert len(cats) == 8
	assert set(cats) == {
		ConsentCategory.symptom_storage, ConsentCategory.location_tracking,
		ConsentCategory.proximity_logging, ConsentCategory.sensor_monitoring,
		ConsentCategory.share_health_authorities, ConsentCategory.share_chw,
		ConsentCategory.cloud_backup, ConsentCategory.research,
	}


async def test_every_category_states_the_consequence_of_withdrawal() -> None:
	"""§SEC-001 requires "a clear statement of consequences of revocation". A toggle without one
	asks a person to give something up without telling them what it costs, so the sentence is a
	required field rather than a nicety."""
	for scope in PrivacyService().consent_catalogue():
		assert scope.label and scope.explains and scope.on_withdrawal
		assert scope.on_withdrawal.endswith('.'), 'the consequence is a sentence, not a fragment'


async def test_only_research_is_separate_from_core() -> None:
	"""§SEC-001 marks research "opt-in, separate". A second separate category would mean something
	else was being withheld from the core flow, which the spec does not say."""
	svc = PrivacyService()
	separate = [c.category for c in svc.consent_catalogue() if c.separate_from_core]
	assert separate == [ConsentCategory.research]


def test_a_non_research_category_cannot_be_marked_separate() -> None:
	"""Canary at the model: the validator must refuse the mistake, not merely be absent."""
	with pytest.raises(ValidationError, match='not marked separate'):
		ConsentScope(category=ConsentCategory.location_tracking, label='x', explains='y',
		             on_withdrawal='z.', separate_from_core=True)


async def test_sensor_monitoring_is_one_decision_per_sensor() -> None:
	"""§SEC-001: "Sensor monitoring (each sensor separately)". The category enumerates the §13.1
	matrix, so a sensor added to §13.1 without a consent entry would be a measurement nobody
	consented to."""
	from afya.sensors.service import SENSORS
	svc = PrivacyService()
	rows = svc.sensor_consents()
	assert len(rows) == len(SENSORS) == 18
	assert {r['sensor'] for r in rows} == {s.slug for s in SENSORS}
	toggles = svc.consent_toggles()
	sm = next(t for t in toggles if t.category is ConsentCategory.sensor_monitoring)
	assert len(sm.sensors) == 18 and not any(sm.sensors.values()), 'opt-in means off by default'


async def test_the_per_sensor_consent_needs_the_sensor_named() -> None:
	"""A blanket `sensor_monitoring` grant is not a per-sensor grant, which is the distinction
	§SEC-001 draws. Naming the sensor is what makes it consent to *that* measurement."""
	svc = PrivacyService()
	await svc.record_consent(ConsentRecord(
		subject_ref='U9', purpose=ConsentCategory.sensor_monitoring.value, data_types=['sensor'],
		retention_days=90, legal_basis=LegalBasis.consent))
	assert svc.has_category_consent('U9', ConsentCategory.sensor_monitoring) is True
	assert svc.sensor_consented('U9', 'gps') is False, 'the blanket grant names no sensor'
	assert svc.sensor_consented('U9', 'microphone') is False


async def test_a_named_sensor_grant_is_recognised_and_revocable() -> None:
	svc = PrivacyService()
	rec = await svc.record_consent(ConsentRecord(
		subject_ref='U8', purpose='sensor_monitoring:gps', data_types=['location'],
		retention_days=21, legal_basis=LegalBasis.consent))
	assert svc.sensor_consented('U8', 'gps') is True
	assert svc.sensor_consented('U8', 'camera_rear') is False, 'consent to one sensor is not consent to another'
	await svc.withdraw(rec.consent_id)
	assert svc.sensor_consented('U8', 'gps') is False, 'one-tap revocation (§SEC-001)'


async def test_a_granted_category_resolves_into_its_toggle() -> None:
	svc = PrivacyService()
	toggles = svc.consent_toggles(granted={'location_tracking': True})
	assert len(toggles) == 8
	assert [t.category.value for t in toggles if t.granted] == ['location_tracking']
	assert all(t.revocable for t in toggles), '§SEC-001: one-tap revocation on every category'


async def test_low_sensitivity_sensors_are_marked_as_needing_no_grant() -> None:
	"""§17.2 does not require consent for a barometer reading, and asking for one is consent
	theatre. The row still appears — §SEC-001's granularity is per sensor — but marked."""
	svc = PrivacyService()
	by_sensor = {r['sensor']: r for r in svc.sensor_consents()}
	assert by_sensor['barometer']['needs_consent'] is False
	assert by_sensor['gps']['needs_consent'] is True
	assert by_sensor['microphone']['needs_consent'] is True
	assert all(r['raw_retained'] is False for r in svc.sensor_consents()), '§SEC-002'


async def test_the_consent_catalogue_route_serves_toggles_without_codes() -> None:
	"""The catalogue is what a person reads, so it carries no spec code — and it is public,
	because someone deciding whether to use the app is who the plain-language text is for."""
	import httpx
	import re
	from afya.service import create_app
	app = create_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		out = (await c.get('/privacy/consent')).json()
		assert len(out['toggles']) == 8 and len(out['sensors']) == 18
		body = str(out)
		assert re.search(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b', body) is None, \
			'a spec code reached a surface a person reads'
		sm = next(t for t in out['toggles'] if t['category'] == 'sensor_monitoring')
		assert len(sm['sensors']) == 18 and not any(sm['sensors'].values())


async def test_the_catalogue_route_will_not_show_a_stranger_your_grants() -> None:
	"""Consent state is personal data, and this route is public because the catalogue is. That
	combination is why it carries no subject parameter at all: a subject a caller could name would
	be a stranger's reference they could type, which is the IDOR shape `require_self` exists to
	prevent. The token is the only subject it reads."""
	import httpx
	from afya.privacy.views import ConsentRecord, LegalBasis
	from afya.service import build_services, create_app
	services = build_services(db_path='/tmp/afya-consent-idor.db')
	svc: PrivacyService = services['privacy']  # type: ignore[assignment]
	await svc.record_consent(ConsentRecord(subject_ref='OWNER', purpose='location_tracking',
		data_types=['location'], retention_days=90, legal_basis=LegalBasis.consent))
	await svc.record_consent(ConsentRecord(subject_ref='OWNER', purpose='sensor_monitoring:gps',
		data_types=['location'], retention_days=21, legal_basis=LegalBasis.consent))
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		other = (await c.post('/auth/anonymous', json={'subject_ref': 'OTHER'})).json()['token']
		out = (await c.get('/privacy/consent', headers={'authorization': f'Bearer {other}'})).json()
		assert [t['category'] for t in out['toggles'] if t['granted']] == [], 'a stranger read a live grant'
		owner = (await c.post('/auth/anonymous', json={'subject_ref': 'OWNER'})).json()['token']
		out = (await c.get('/privacy/consent', headers={'authorization': f'Bearer {owner}'})).json()
		assert [t['category'] for t in out['toggles'] if t['granted']] == ['location_tracking']
		sm = next(t for t in out['toggles'] if t['category'] == 'sensor_monitoring')
		assert [k for k, v in sm['sensors'].items() if v] == ['gps']
