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


# --- §17.1 instruments and §17.2 principles -------------------------------------------------------

def _spec_rows(heading: str, stop: str, columns: int) -> list[list[str]]:
	"""A spec table's rows, read out of `docs/spec.md` so a revision fails here."""
	from pathlib import Path
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	section = text.split(heading, 1)[1].split(stop, 1)[0]
	rows: list[list[str]] = []
	for line in section.splitlines():
		if not line.startswith('|') or set(line) <= set('|-: '):
			continue
		cells = [c.strip() for c in line.strip('|').split('|')]
		if len(cells) != columns or cells[0] == 'Instrument' or cells[0] == 'Principle':
			continue
		rows.append(cells)
	return rows


def _items(cell: str) -> list[str]:
	"""One Implementation cell split into the claims it makes.

	§17.1 separates its items with semicolons and §17.2's data-minimisation row separates two with a
	full stop — "Only data necessary for the specific purpose is collected. Raw sensor data is never
	retained." Both are lists of claims and a checker that knew only the semicolon would read that
	row as one claim, which is the "enumerates one of the two ways to write X" failure. Trailing
	periods are stripped so the two spellings compare equal.
	"""
	import re
	return [p.strip().rstrip('.') for p in re.split(r';\s*|\.\s+|,\s*', cell) if p.strip()]


def _strip_md(cell: str) -> str:
	return cell.replace('**', '').strip()


def test_the_six_instruments_are_the_sections_rows() -> None:
	"""§17.1, cell for cell. `instrument` and `requirement` are the section's own words — a revision
	to either fails here until the table moves with it."""
	from afya.privacy.service import REGULATORY_INSTRUMENTS
	spec = _spec_rows('### 17.1 Regulatory Framework', '\n### ', 3)
	assert len(spec) == 6
	assert [r.instrument for r in REGULATORY_INSTRUMENTS] == [_strip_md(r[0]) for r in spec]
	assert [r.requirement for r in REGULATORY_INSTRUMENTS] == [_strip_md(r[1]) for r in spec]


def test_every_implementation_item_is_a_row_not_a_cell() -> None:
	"""The Implementation cell is a semicolon list — "Consent registry; data minimisation by design;
	retention schedule; user data controls" is four claims — and a single boolean over the cell
	would let three of the four be missing while the row read covered. So the split is the test:
	every item of every cell appears as its own obligation, and nothing is dropped."""
	from afya.privacy.service import REGULATORY_INSTRUMENTS
	spec = _spec_rows('### 17.1 Regulatory Framework', '\n### ', 3)
	for row, cells in zip(REGULATORY_INSTRUMENTS, spec, strict=True):
		items = _items(_strip_md(cells[2]))
		assert [o.obligation for o in row.obligations] == items, row.instrument


def test_the_seven_principles_are_the_sections_rows() -> None:
	"""§17.2, cell for cell, with the Implementation cell split the same way — "Content reviewed
	weekly; user data editable; correction workflows" is three claims about three different
	modules, and it is the cell where a single boolean would hide the most."""
	from afya.privacy.service import PRIVACY_PRINCIPLES
	spec = _spec_rows('### 17.2 Privacy Principles and Implementation', '\n### ', 2)
	assert len(spec) == 7
	assert [name for name, _, _ in PRIVACY_PRINCIPLES] == [_strip_md(r[0]) for r in spec]
	assert [impl for _, impl, _ in PRIVACY_PRINCIPLES] == [_strip_md(r[1]) for r in spec]
	for (_name, _impl, artifacts), cells in zip(PRIVACY_PRINCIPLES, spec, strict=True):
		items = _items(_strip_md(cells[1]))
		assert [a.obligation for a in artifacts] == items, cells[0]


def test_every_obligation_resolves_or_is_reported() -> None:
	"""The point of the register. Every `code` obligation must name a module that exists, and the
	report must carry an entry for each one that does not — a register whose gaps were silently
	absorbed would be the failure it exists to catch."""
	from afya.privacy.service import REGULATORY_INSTRUMENTS
	from afya.refs import resolves
	report = PrivacyService().regulatory_report()
	assert report.instrument_count == len(REGULATORY_INSTRUMENTS) == 6
	assert report.obligation_count == sum(len(r.obligations) for r in REGULATORY_INSTRUMENTS)
	assert len(report.assessments) == report.obligation_count
	by_name = {(a.instrument, a.obligation): a for a in report.assessments}
	for a in report.assessments:
		if a.kind.value == 'code':
			assert a.resolves == resolves(a.control) is True, f'{a.instrument}: {a.obligation} names {a.control}'
	assert set(report.unbacked) == {
		f'{a.instrument}: {a.obligation}' for a in report.assessments if not a.backed
	} | {
		f'§17.2 {p.principle}: {u}' for p in report.principles for u in p.unbacked_artifacts
	}, 'the finding list and the assessments disagree'
	assert by_name, 'every obligation is assessed'


def test_the_canary_watches_an_unresolvable_reference_fire() -> None:
	"""A register that reports its own gaps is only worth anything if it can report one. The
	reference below is a plausible-looking `module:attr` pointing at a method that does not exist,
	which is exactly the shape §17.1's "Security controls; incident response" cell could rot into
	when a method is renamed off a class."""
	from afya.privacy.service import PrivacyService
	from afya.privacy.views import InstrumentObligation, ObligationKind
	svc = PrivacyService()
	bad = InstrumentObligation(obligation='a control that is not there', kind=ObligationKind.code,
		control='afya.operations.service:OperationsService.no_such_method')
	assert svc._assess('canary', bad, frozenset(), frozenset()).backed is False, \
		'the canary did not fire: a broken reference read as backed'
	good = InstrumentObligation(obligation='a control that is there', kind=ObligationKind.code,
		control='afya.operations.service:OperationsService.status')
	assert svc._assess('canary', good, frozenset(), frozenset()).backed is True


def test_a_process_obligation_with_no_duty_behind_it_is_unbacked() -> None:
	"""§17.1's DPO appointment and §17.2's "legal obligation basis for mandatory disease
	notification only" are process claims with no module to walk, and a process item nobody owns
	reads exactly like one somebody does — which is why the check is against §24's duty register
	rather than against nothing."""
	from afya.operations.service import OBLIGATIONS
	from afya.privacy.service import PrivacyService
	from afya.privacy.views import InstrumentObligation, ObligationKind
	svc = PrivacyService()
	assert any(o.duty.lower() == 'moh registration' for o in OBLIGATIONS), \
		'the §24 register lost the duty §17.1 names'
	owned = svc._assess('x', InstrumentObligation(obligation='MoH registration', kind=ObligationKind.process),
		frozenset(), frozenset())
	assert owned.backed is True and 'owns it' in owned.note
	orphan = svc._assess('x', InstrumentObligation(obligation='nobody owns this', kind=ObligationKind.process),
		frozenset(), frozenset())
	assert orphan.backed is False and orphan.note == 'no §24 duty schedules this'


def test_the_legal_obligation_basis_is_refused_for_anything_but_notification() -> None:
	"""§17.2's lawfulness row is "Consent-based for all citizen data; legal obligation basis for
	mandatory disease notification **only**", and "only" is the word doing the work. Until this
	assert existed the basis was a label a caller chose, so the one door the section holds shut was
	open to any purpose: a person's symptom history could be filed against a statute instead of
	against their consent and the ledger would show a lawful record."""
	from afya.privacy.service import MANDATORY_NOTIFICATION_PURPOSES, PrivacyService
	svc = PrivacyService()
	assert svc.case_report_basis('case_report') is LegalBasis.legal_obligation
	assert svc.case_report_basis('symptom_storage') is LegalBasis.consent
	assert 'case_report' in MANDATORY_NOTIFICATION_PURPOSES


async def test_recording_a_statutory_basis_for_a_consent_purpose_is_refused() -> None:
	"""The assert, exercised through the one entry point that writes the ledger."""
	from afya.privacy.service import PrivacyService
	svc = PrivacyService()
	with pytest.raises(AssertionError, match='not a mandatory disease notification'):
		await svc.record_consent(ConsentRecord(
			subject_ref='U1', purpose='health_companion', data_types=['demographic'],
			retention_days=3650, legal_basis=LegalBasis.legal_obligation))
	recorded = await svc.record_consent(ConsentRecord(
		subject_ref='U1', purpose='case_report', data_types=['clinical'],
		retention_days=3650, legal_basis=LegalBasis.legal_obligation))
	assert recorded.consent_id, 'a mandatory notification may be filed on the statutory basis'
	# And consent still works for everything else, so the rule is not refusing the ordinary path.
	await svc.record_consent(ConsentRecord(subject_ref='U1', purpose='health_companion',
		data_types=['demographic'], retention_days=730, legal_basis=LegalBasis.consent))


async def test_the_regulatory_report_is_auditor_scoped_and_the_ids_stay_in_it() -> None:
	"""The evidence surface: §17.1's instrument names and the `module:attr` references are the
	finding, so they are served — to the auditor, who is who the finding is for. The public
	`/privacy/consent` catalogue is the surface a person reads and carries neither."""
	import httpx
	from afya.service import build_services, create_app
	services = build_services()
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		assert (await c.get('/privacy/regulatory')).status_code in (401, 403), 'unguarded'
		tok = (await c.post('/auth/anonymous', json={})).json()['token']
		assert (await c.get('/privacy/regulatory', headers={'authorization': f'Bearer {tok}'})).status_code == 403
		# `auditor` is not issuable through the app flow, so it is provisioned by a sysadmin.
		auth_svc: AuthService = services['auth']  # type: ignore[assignment]
		sysadmin = auth_svc.provision_staff('ops-0', RBACRole.sysadmin, registrar='MoH ops').access_token
		auditor = str((await c.post('/auth/staff/provision',
			json={'operator_ref': 'ops-1', 'registrar': 'MoH ops', 'role': 'auditor'},
			headers={'authorization': f'Bearer {sysadmin}'})).json()['access_token'])
		out = (await c.get('/privacy/regulatory', headers={'authorization': f'Bearer {auditor}'})).json()
	assert out['instrument_count'] == 6 and len(out['principles']) == 7
	assert any('Kenya Data Protection Act 2019' == i['instrument'] for i in out['instruments'])
	assert 'unbacked' in out, 'the finding is what the auditor is reading this for'
