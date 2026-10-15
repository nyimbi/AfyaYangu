from typing import Any

import httpx
import pytest
from pytest_httpserver import HTTPServer

from pydantic import ValidationError

from afya.integrations.adam import PII_FIELDS, AdamClient
from afya.integrations.feeds import FEED_CADENCE, FEED_GRANULARITY, MIN_CELL, build as build_feed
from afya.integrations.gateways import AtSmsRestSend, WhatsAppBusinessClient
from afya.integrations.service import (
	JaliClient, MoHFFacilityClient, PPBClient, PheocClient, SHAClient, TelcoGatewayClient,
)
from afya.channels.views import SmsOut
from afya.insurance.views import SHACheckRequest
from afya.medicine.views import SuspiciousReport, VerifyRequest


@pytest.fixture
async def client(httpserver: HTTPServer) -> httpx.AsyncClient:
	return httpx.AsyncClient(base_url=f'http://127.0.0.1:{httpserver.port}', timeout=5)


async def test_jali_message(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	httpserver.expect_request('/v1/messages', method='POST').respond_with_json({'id': 'm1', 'status': 'sent'})
	jali = JaliClient(httpserver.url_for('/'), 'sk-1', client)
	out = await jali.send_message('+254711222333', 'Fever info')
	assert out['id'] == 'm1'


async def test_pheoc_signal_push(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	httpserver.expect_request('/signals', method='POST').respond_with_json({'accepted': 3})
	pheoc = PheocClient(httpserver.url_for('/'), client)
	assert await pheoc.push_signal({'county': 'Busia'}) == 3


async def test_mohf_download(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	httpserver.expect_request('/facilities', method='GET').respond_with_json([{'name': 'KNH'}])
	mohf = MoHFFacilityClient(httpserver.url_for('/'), client)
	assert (await mohf.download_facilities('Nairobi'))[0]['name'] == 'KNH'


async def test_at_sms_rest_send(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	httpserver.expect_request('/version1/messaging', method='POST').respond_with_json({'SMSMessageData': {'Recipients': [{'messageId': 'ATX_1'}]}})
	sender = AtSmsRestSend(httpserver.url_for('/'), 'k1', 'afya', client)
	# `zero_rated` is stated rather than defaulted (see `test_channel_cost.py`), and it is stated
	# *false* on purpose: the transport is a transport, and this asserts it puts a message on the wire
	# whether or not the carrier has agreed to carry it free. The flag used to default to true and the
	# port asserted it, so the charging case could not be expressed — and an outbreak alert must not be
	# dropped because the telco paperwork lapsed.
	msg = SmsOut(to_msisdn='+254711222333', body='Call 719', segments=1, zero_rated=False)
	assert await sender.send(msg) == 'ATX_1'


async def test_whatsapp_business_send(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	httpserver.expect_request('/v22.0/PHONE_ID/messages', method='POST').respond_with_json({'messages': [{'id': 'wamid.1'}]})
	wa = WhatsAppBusinessClient('PHONE_ID', 'tok', client, api_base=httpserver.url_for('/'))
	assert await wa.send_text('+254711222333', 'Tafuta kituo') == 'wamid.1'


async def test_ppb_verify_paths(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	ppb = PPBClient(httpserver.url_for('/'), client)
	httpserver.expect_request('/verify', query_string={'gtin': '0123456789012', 'batch': 'B123'}, method='GET').respond_with_json({'genuine': True})
	httpserver.expect_request('/verify', query_string={'gtin': '0123456789019', 'batch': 'B999'}, method='GET').respond_with_json({'error': 'not found'}, status=404)
	ok = await ppb.verify(VerifyRequest(batch_number='B123', gtin='0123456789012'))
	assert ok.genuine and ok.source == 'PPB'
	bad = await ppb.verify(VerifyRequest(batch_number='B999', gtin='0123456789019'))
	assert not bad.genuine and 'not registered' in (bad.notes or '')

# --- §18.1 ADaM ---------------------------------------------------------------------------


async def test_adam_push_and_pull(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	httpserver.expect_request('/cases', method='POST').respond_with_json({'case_ref': 'ADAM-77'})
	httpserver.expect_request('/cases/RPT-1', method='GET').respond_with_json({'status': 'lab_pending'})
	httpserver.expect_request('/contacts', method='GET').respond_with_json([{'contact_ref': 'C1'}])
	httpserver.expect_request('/case-definitions', method='GET').respond_with_json([{'name': 'EVD suspect'}])
	adam = AdamClient(httpserver.url_for('/'), client)
	assert await adam.push_case_report({'report_id': 'RPT-1', 'patient_ref': 'P-abc123'}) == 'ADAM-77'
	assert (await adam.pull_case_status('RPT-1'))['status'] == 'lab_pending'
	assert (await adam.pull_contact_assignments('chw-1'))[0]['contact_ref'] == 'C1'
	assert (await adam.pull_case_definitions())[0]['name'] == 'EVD suspect'


async def test_adam_refuses_unconsented_monitoring(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	"""The consent flag is checked with `is True`, so leaving it off is a refusal, not a default."""
	adam = AdamClient(httpserver.url_for('/'), client)
	with pytest.raises(AssertionError, match='consent'):
		await adam.push_monitoring_summary({'subject_ref': 'U1', 'day': '2026-10-10'})
	with pytest.raises(AssertionError, match='consent'):
		await adam.push_monitoring_summary({'subject_ref': 'U1', 'day': '2026-10-10', 'consented': 'yes'})


async def test_adam_refuses_raw_pii_on_the_wire(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	"""§18.1 field-level encryption assumes pseudonyms. A raw MSISDN or national ID reaching this
	client means the caller skipped pseudonymisation, and this is the last cheap place to say so."""
	adam = AdamClient(httpserver.url_for('/'), client)
	# No server expectation is registered: a request that got through would fail the test anyway.
	for value in ('+254712345678', '0712345678', '12345678'):
		with pytest.raises(AssertionError, match='unpseudonymised'):
			await adam.push_case_report({'report_id': 'RPT-2', 'patient_ref': value})
	# A pseudonym passes, so the guard is not simply refusing every case report.
	httpserver.expect_request('/cases', method='POST').respond_with_json({'case_ref': 'OK'})
	assert await adam.push_case_report({'report_id': 'RPT-3', 'patient_ref': 'P-9f2c'}) == 'OK'


def test_adam_reports_mtls_rather_than_claiming_it() -> None:
	"""mTLS is a deployment property. The client reports the configuration and nothing more."""
	import httpx as _httpx
	c = _httpx.AsyncClient()
	assert AdamClient('https://adam.example/api', c).mutual_tls_configured is False
	assert AdamClient('https://adam.example/api', c, cert=('c.pem', 'k.pem')).mutual_tls_configured is True
	with pytest.raises(AssertionError, match='mutual TLS'):
		AdamClient('https://adam.example/api', c, cert=('c.pem', ''))


def test_pii_fields_are_enumerated() -> None:
	assert 'patient_ref' in PII_FIELDS and 'national_id' in PII_FIELDS


# --- §18.3 PHEOC feeds ---------------------------------------------------------------------


def _geofence_events(cell: str, n_subjects: int) -> list[dict[str, object]]:
	return [
		{'cell_id': cell, 'county': 'Busia', 'direction': 'entry' if i % 2 == 0 else 'exit', 'subject_ref': f'S{i}'}
		for i in range(n_subjects)
	]


def test_geofence_feed_suppresses_a_cell_below_ten() -> None:
	"""§18.3 "Aggregated, min cell 10". A cell of three is not an aggregate, it is a location trace
	with a county label on it, so the builder drops it rather than emitting it with a caveat."""
	rows, withheld = build_feed('geofence_events', _geofence_events('CELL-A', 3))
	assert rows == [] and withheld == 1, 'a three-person cell must not be emitted'
	assert build_feed('geofence_events', _geofence_events('CELL-B', 9))[0] == []
	ten, kept = build_feed('geofence_events', _geofence_events('CELL-C', 10))
	assert len(ten) == 1 and ten[0]['distinct_subjects'] == MIN_CELL and kept == 0
	assert 'subject_ref' not in ten[0], 'the feed carries a count, never the subjects themselves'


def test_geofence_feed_counts_a_repeat_visitor_once() -> None:
	"""Ten events from four people is four people. Counting events instead of subjects would clear
	the min-cell floor with a cell that describes four."""
	events = _geofence_events('CELL-D', 4) * 3
	assert build_feed('geofence_events', events)[0] == []


def test_symptom_feed_holds_the_floor_too() -> None:
	"""A second egress path with the same rule. Enforcing min-cell at one exit is not enforcing it."""
	cell = {'cell_id': 'C1', 'county': 'Busia', 'population': 9, 'fever_reports': 2, 'cough_events': 1, 'encounter_density': 0.1, 'facility_reports': 1}
	assert build_feed('symptom_reports', [cell]) == ([], 1)
	assert build_feed('symptom_reports', [{**cell, 'population': 10}])[0].__len__() == 1


def test_case_feed_carries_no_patient_reference() -> None:
	"""The feed is a dashboard input, not a second copy of the case file."""
	row = {'report_id': 'RPT-1', 'county': 'Busia', 'facility': 'Busia DH', 'patient_ref': 'P-abc', 'suspected_disease': 'evd'}
	out, _ = build_feed('case_reports', [row])
	assert out[0]['report_id'] == 'RPT-1'
	assert 'patient_ref' not in out[0]


def test_ai_feeds_never_self_publish_or_self_action() -> None:
	"""§19.3: the early-warning signal informs a human; it does not raise a public alert, and a
	resource recommendation is not actioned by the system that made it."""
	warn, _ = build_feed('early_warning', [{'county': 'Busia', 'z_score': 3.1, 'band': 'high', 'reasons': ['fever spike']}])
	assert warn[0]['public_alert'] is False
	res, _ = build_feed('resource_deployment', [{'county': 'Busia', 'resource': 'ORS', 'quantity': 500}])
	assert res[0]['auto_actioned'] is False


def test_every_feed_declares_its_granularity_and_cadence() -> None:
	assert set(FEED_GRANULARITY) == set(FEED_CADENCE) == {
		'symptom_reports', 'case_reports', 'geofence_events', 'misinformation_flags', 'early_warning', 'resource_deployment',
	}
	assert FEED_GRANULARITY['geofence_events'] == 'aggregated_min_cell_10'
	assert build_feed('case_reports', []) == ([], 0), 'an empty feed is a quiet hour, not an error'
	with pytest.raises(AssertionError, match='unknown PHEOC feed'):
		build_feed('not_a_feed', [])


async def test_pheoc_push_refuses_an_empty_batch(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	pheoc = PheocClient(httpserver.url_for('/'), client)
	with pytest.raises(AssertionError, match='empty feed'):
		await pheoc.push_feed('case_reports', [])
	httpserver.expect_request('/feeds/case_reports', method='POST').respond_with_json({'accepted': 1})
	assert await pheoc.push_feed('case_reports', [{'report_id': 'R', 'county': 'Busia'}]) == 1


# --- §18.2 / 18.5 / 18.6 / 18.7 / 18.8 -----------------------------------------------------


async def test_jali_full_wire(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	httpserver.expect_request('/v1/links', method='POST').respond_with_json({'url': 'https://jali.health.go.ke/go/abc'})
	httpserver.expect_request('/v1/corrections', method='GET').respond_with_json([{'topic': 'bleach'}])
	httpserver.expect_request('/v1/assessments', method='POST').respond_with_json({'assessment_ref': 'A1'})
	httpserver.expect_request('/v1/assessments/A1/review', method='GET').respond_with_json({'clinician': 'Dr X'})
	jali = JaliClient(httpserver.url_for('/'), 'sk-1', client)
	assert (await jali.launch_link('triage', 'U1')).endswith('/abc')
	assert (await jali.corrections('2026-01-01T00:00:00Z'))[0]['topic'] == 'bleach'
	# The push returns the ref the review is pulled by, so the two rows of §18.2's table are one
	# wire rather than two: without it the app has an id for nothing.
	assert await jali.share_assessment({'subject_ref': 'U1', 'consented': True}) == 'A1'
	review = await jali.clinician_response('A1')
	assert review is not None and review['clinician'] == 'Dr X'


async def test_jali_unreviewed_assessment_is_none_not_an_error(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	"""`None` is "a human has not answered yet" — a state, not a 404."""
	httpserver.expect_request('/v1/assessments/A2/review', method='GET').respond_with_json({'error': 'no'}, status=404)
	jali = JaliClient(httpserver.url_for('/'), 'sk-1', client)
	assert await jali.clinician_response('A2') is None


async def test_jali_refuses_unconsented_assessment_share(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	jali = JaliClient(httpserver.url_for('/'), 'sk-1', client)
	with pytest.raises(AssertionError, match='consent'):
		await jali.share_assessment({'subject_ref': 'U1'})


async def test_mohf_correction_and_verification(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	httpserver.expect_request('/corrections', method='POST').respond_with_json({'ticket': 'T-9'})
	httpserver.expect_request('/verification', method='GET').respond_with_json({'F1': 'verified', 'F2': 'unverified'})
	mohf = MoHFFacilityClient(httpserver.url_for('/'), client)
	assert await mohf.report_correction({'facility_id': 'F1', 'field': 'phone'}) == 'T-9'
	status = await mohf.verification_status(['F1', 'F2'])
	assert status['F2'] == 'unverified'
	with pytest.raises(AssertionError, match='facility and a field'):
		await mohf.report_correction({'facility_id': 'F1'})


async def test_sha_cover_verify_and_unknown_member(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	"""An unknown member is a real answer — "no cover" — not a transport failure."""
	# Matched on the request body, not just the path: the same endpoint answers both cases, and a
	# path-only expectation would serve the first registration for both.
	httpserver.expect_request('/cover/verify', method='POST', json={'member_no': 'M123456', 'purpose': 'facility_visit'}).respond_with_json(
		{'product': 'SHIF', 'active': True, 'contributions_current': True, 'valid_thru_iso': '2027-06-30'})
	httpserver.expect_request('/cover/verify', method='POST', json={'member_no': 'M999999', 'purpose': 'facility_visit'}).respond_with_json(
		{'error': 'unknown'}, status=404)
	sha = SHAClient(httpserver.url_for('/'), client)
	out = await sha.status(SHACheckRequest(member_no='M123456'))
	assert out.active and out.product == 'SHIF'
	assert out.member_no_hash != 'M123456', 'only the hash leaves the service'

	unknown = await sha.status(SHACheckRequest(member_no='M999999'))
	assert unknown.active is False


async def test_sha_acceptance_and_benefits(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	httpserver.expect_request('/facilities', method='GET').respond_with_json([{'facility_id': 'F1', 'accepts_sha': True}])
	httpserver.expect_request('/benefits', method='GET').respond_with_json([{'service': 'outpatient'}])
	sha = SHAClient(httpserver.url_for('/'), client)
	assert (await sha.acceptance_list('Nairobi'))[0]['accepts_sha'] is True
	assert (await sha.benefits('SHIF'))[0]['service'] == 'outpatient'


async def test_ppb_registry_recalls_and_report(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	httpserver.expect_request('/registry', method='GET').respond_with_json([{'gtin': '0123456789012'}])
	httpserver.expect_request('/recalls', method='GET').respond_with_json([{'batch': 'B1', 'reason': 'contamination'}])
	httpserver.expect_request('/suspicious', method='POST').respond_with_json({'case_ref': 'PPB-5'})
	ppb = PPBClient(httpserver.url_for('/'), client)
	assert (await ppb.registry('2026-01-01T00:00:00Z'))[0]['gtin'] == '0123456789012'
	assert (await ppb.recalls('2026-01-01T00:00:00Z'))[0]['batch'] == 'B1'
	assert await ppb.report_suspicious(SuspiciousReport(gtin='0123456789012')) == 'PPB-5'
	with pytest.raises(ValidationError, match='gtin or a batch'):
		SuspiciousReport()


async def test_telco_zero_rating_and_bounded_airtime(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	httpserver.expect_request('/rules', method='GET').respond_with_json([{'prefix': '719', 'rate': 0}])
	httpserver.expect_request('/disburse', method='POST').respond_with_json({'reference': 'AT-1'})
	telco = TelcoGatewayClient(httpserver.url_for('/'), httpserver.url_for('/'), 'k1', client)
	assert (await telco.zero_rating_rules())[0]['rate'] == 0
	assert await telco.disburse_airtime('+254712345678', 100, 'chw incentive') == 'AT-1'
	# An unbounded incentive is a way to drain a budget through one compromised token.
	with pytest.raises(AssertionError, match='above 500'):
		await telco.disburse_airtime('+254712345678', 100_000, 'x')
	with pytest.raises(AssertionError, match='above 500'):
		await telco.disburse_airtime('+254712345678', 0, 'x')


async def test_telco_refuses_an_unconfigured_agreement(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	"""Zero-rating and airtime are separate agreements; each refuses on its own rather than posting
	to an empty base URL, which would be a request to the current host under a relative path."""
	telco = TelcoGatewayClient('', httpserver.url_for('/'), 'k', client)
	with pytest.raises(AssertionError, match='zero-rating is not configured'):
		await telco.zero_rating_rules()
	other = TelcoGatewayClient(httpserver.url_for('/'), '', 'k', client)
	with pytest.raises(AssertionError, match='airtime disbursement is not configured'):
		await other.disburse_airtime('+254712345678', 10, 'x')



# --- inbound webhooks are signed, not open --------------------------------------------------

WEBHOOK_SECRET = 'test-webhook-secret'


@pytest.fixture
def webhook_env(monkeypatch: pytest.MonkeyPatch) -> str:
	"""Configure the shared secret for one test. `require_webhook` reads it per request, so a
	monkeypatched value is what the guard sees — and it is undone afterwards, so no later test
	inherits a configured deployment and passes for the wrong reason."""
	monkeypatch.setenv('AFYA_WEBHOOK_SECRET', WEBHOOK_SECRET)
	return WEBHOOK_SECRET


@pytest.fixture
def no_webhook_env(monkeypatch: pytest.MonkeyPatch) -> None:
	"""An unconfigured deployment. Explicit, because the alternative is whatever the previous test
	happened to leave in the environment."""
	monkeypatch.delenv('AFYA_WEBHOOK_SECRET', raising=False)


def _signed(body: dict[str, Any], secret: str = WEBHOOK_SECRET) -> tuple[bytes, dict[str, str]]:
	"""Sign a webhook body the way a carrier would. Returns the raw bytes and the headers."""
	import hashlib
	import hmac
	import json
	raw = json.dumps(body).encode()
	sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
	return raw, {'content-type': 'application/json', 'x-afya-signature': sig}


# --- §18 over HTTP: the wiring, which is the part that breaks silently -----------------------


async def test_integration_routes_are_reachable_and_guarded(no_webhook_env: None) -> None:
	"""Every §18 client existed and no route reached it, so §18 was "done" in the sense that code
	existed. These drive the routes: a 404 here means a wire the spec names is not connected, and a
	200 on a guarded route without a token means the guard was forgotten."""
	import httpx as _httpx

	from afya.service import build_services, create_app

	app = create_app(build_services())
	transport = _httpx.ASGITransport(app=app)
	async with _httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		status = await c.get('/integrations/status')
		assert status.status_code == 200
		body = status.json()
		assert body['wired'] == ['adam', 'jali', 'mohf', 'pheoc', 'ppb', 'sha', 'telco']
		assert set(body['pheoc_feeds']) == set(FEED_GRANULARITY)
		assert body['adam_mutual_tls'] is False, 'no cert configured in dev'

		catalogue = (await c.get('/integrations/pheoc/feeds')).json()
		assert len(catalogue['feeds']) == 6 and catalogue['min_cell'] == MIN_CELL

		# Guarded wires refuse an unauthenticated caller rather than reaching the vendor. The status
		# must be exactly 401: a 422 or 502 here would also be produced by an *unguarded* route whose
		# vendor call failed, so accepting one would let a dropped guard pass this test.
		for method, path in (
			('post', '/integrations/adam/cases'), ('get', '/integrations/adam/case-definitions'),
			('post', '/facilities/import-mohf'), ('post', '/integrations/telco/airtime'),
			('get', '/integrations/adam/contacts'), ('get', '/insurance/sha/facilities'),
		):
			resp = await (c.post(path, json={}) if method == 'post' else c.get(path))
			assert resp.status_code == 401, f'{path} answered {resp.status_code} without a token, not 401'
		# A carrier has no app token, so the webhooks are guarded by a signature instead — and with
		# no secret configured the honest answer is 503, not an open endpoint. An unauthenticated
		# webhook is an open write attributed to a real person.
		assert (await c.post('/integrations/telco/sms/inbound', json={'from': '0712345678', 'text': 'x'})).status_code == 503
		assert (await c.post('/channels/ussd/callback', json={'session_id': 's', 'phone_number': '+254711222333', 'text': ''})).status_code == 503


async def test_the_clinician_review_route_refuses_a_caller_with_no_token() -> None:
	"""§18.2's fourth row is a clinician's answer about one person's assessment, and it was the only
	unguarded route on the §18 surface that serves a person's data: it answered 200 with no token at
	all, so anyone could read any assessment by guessing an id.

	The other guard tests could not see it. `test_self_scope.py`'s gate keys on a route naming a
	*subject*, and this one names an `assessment_id` — a vendor reference, not a subject — so the
	route sat outside the gate's jurisdiction while serving exactly the data the gate exists for.
	This asserts the front door, and `test_the_integration_surface_has_no_unguarded_person_route`
	asserts the whole surface so the next such route fails there rather than here.
	"""
	import httpx as _httpx

	from afya.service import build_services, create_app

	app = create_app(build_services())
	async with _httpx.AsyncClient(transport=_httpx.ASGITransport(app=app), base_url='http://t') as c:
		for headers in ({}, {'authorization': 'Bearer nonsense'}):
			resp = await c.get('/integrations/jali/assessments/A1/review', headers=headers)
			assert resp.status_code == 401, f'{resp.status_code} without a usable token, not 401'
		# The sibling that pushes the same person's assessment is guarded, so the pair cannot
		# disagree about who may touch it — which is the shape the ADaM twin already had.
		assert (await c.post('/integrations/jali/assessments', json={'consented': True})).status_code == 401


async def test_an_unconsented_assessment_is_refused_at_the_boundary_not_only_in_the_client() -> None:
	"""The consent rule lived in `JaliClient` and nowhere else, and JALI has two implementations: the
	client, and `InlineJaliPort`, which is what runs whenever no JALI key is configured — the default
	a deployment without the integration has. `InlineJaliPort.share_assessment` has no assert, so an
	unconsented summary was accepted and answered 200 on the offline port while the identical call
	was refused on the online one.

	A control present in one of two implementations is a control at half the paths, and which half
	you get is a configuration detail the caller cannot see. The route is the boundary both share,
	so the rule is enforced there, and this drives the front door with the offline port in place.
	"""
	import httpx as _httpx

	from afya.auth.views import s256
	from afya.service import build_services, create_app

	services = build_services()
	# The premise of the test: this is the offline port, the one whose `share_assessment` carries no
	# consent assert of its own. If a JALI key were configured the premise would be false and the
	# test would be passing for the client's reason rather than the boundary's.
	assert services['jali'].__class__.__name__ == 'InlineJaliPort', services['jali'].__class__.__name__
	app = create_app(services)
	verifier = 'v' * 64
	async with _httpx.AsyncClient(transport=_httpx.ASGITransport(app=app), base_url='http://t') as c:
		authz = (await c.post('/auth/pkce/authorize', json={
			'client_id': 'app', 'redirect_uri': 'afya://cb', 'code_challenge': s256(verifier), 'state': 'state-1234',
		})).json()
		chw = (await c.post('/auth/pkce/token', params={'role': 'chw'}, json={
			'authorization_code': authz['authorization_code'], 'client_id': 'app',
			'redirect_uri': 'afya://cb', 'code_verifier': verifier,
		})).json()['access_token']
		h = {'authorization': f'Bearer {chw}'}
		# No flag, and a flag that is merely truthy rather than `True`: the check is `is True`, so a
		# string or a 1 cannot stand in for consent somebody actually gave.
		for body in ({'subject_ref': 'U1'}, {'subject_ref': 'U1', 'consented': 'yes'}, {'subject_ref': 'U1', 'consented': 1}):
			resp = await c.post('/integrations/jali/assessments', json=body, headers=h)
			assert resp.status_code == 403, f'{body} was accepted with {resp.status_code}'
		assert (await c.post('/integrations/jali/assessments', json={'subject_ref': 'U1', 'consented': True}, headers=h)).status_code == 200


# The §18 routes that must carry no guard, each with the reason. These serve no person's data:
# published content, a capability list, or a health of the deployment. Naming them is what makes
# the surface check below a decision rather than a blanket rule that someone would have to weaken.
OPEN_INTEGRATION_ROUTES: dict[tuple[str, str], str] = {
	('GET', '/integrations/status'): 'the wiring report: which systems are configured, and no person in it',
	('GET', '/integrations/pheoc/feeds'): 'the feed catalogue: names, granularity and the min-cell floor',
	('GET', '/integrations/telco/zero-rating'): 'which domains are zero-rated, which is carrier configuration',
	('GET', '/integrations/jali/corrections'): 'published health corrections, meant to be shown to everyone',
}


def _integration_routes(app: Any) -> list[tuple[str, str]]:
	inner = next((getattr(r, 'app') for r in app.routes if hasattr(getattr(r, 'app', None), 'routes')), app)
	out: list[tuple[str, str]] = []
	for route in getattr(inner, 'routes', []):
		path = getattr(route, 'path', '')
		if not path.startswith('/integrations'):
			continue
		for method in sorted(getattr(route, 'methods', set()) - {'HEAD', 'OPTIONS'}):
			out.append((method, path))
	return sorted(out)


def _guard_name(app: Any, method: str, path: str) -> str | None:
	inner = next((getattr(r, 'app') for r in app.routes if hasattr(getattr(r, 'app', None), 'routes')), app)
	for route in getattr(inner, 'routes', []):
		if getattr(route, 'path', None) != path or method not in getattr(route, 'methods', set()):
			continue
		for dep in getattr(getattr(route, 'dependant', None), 'dependencies', []):
			name = getattr(dep.call, '__qualname__', '')
			for guard in ('require_webhook', 'require_self_or_guardian', 'require_self', 'require_any_scope', 'require_scope'):
				if guard in name:
					return guard
	return None


def test_the_integration_surface_has_no_unguarded_person_route() -> None:
	"""The gate, scoped to §18. Every route on the integration surface either carries a guard or is
	named in `OPEN_INTEGRATION_ROUTES` with the reason it serves no person's data.

	This is the check the review route needed and did not have. It is deliberately scoped to
	`/integrations` rather than to the whole app: `test_self_scope.py` owns the app-wide personal
	data surface, and a second gate over the same ground would drift against it. What this adds is
	the jurisdiction that gate cannot see — routes that name a vendor reference instead of a subject.
	"""
	from afya.service import build_services, create_app

	app = create_app(build_services())
	unguarded = [(m, p) for m, p in _integration_routes(app)
	             if _guard_name(app, m, p) is None and (m, p) not in OPEN_INTEGRATION_ROUTES]
	assert unguarded == [], (
		f'§18 routes that reach a person with no guard: {unguarded}. '
		'Add the guard, or name the route in OPEN_INTEGRATION_ROUTES with the reason it holds no personal data.'
	)


def test_the_open_integration_routes_are_still_open_and_still_real() -> None:
	"""The list must not drift into a place a guard was dropped: every entry must name a route that
	exists and still carries no guard, and every guarded route must stay out of it."""
	from afya.service import build_services, create_app

	app = create_app(build_services())
	paths = set(_integration_routes(app))
	for (method, path), reason in OPEN_INTEGRATION_ROUTES.items():
		assert (method, path) in paths, f'{method} {path} is named as open but no such route exists'
		assert _guard_name(app, method, path) is None, f'{method} {path} is named as open but carries a guard'
		assert len(reason) > 20, f'{method} {path} has no real reason, only {reason!r}'


def test_the_integration_surface_gate_catches_an_unguarded_person_route() -> None:
	"""Canary. The defect is planted as a route under a vendor-shaped name, which is the shape that
	fooled the app-wide gate — a subject-name key would not see it, and this one must."""
	from fastapi import FastAPI

	planted = FastAPI()

	@planted.get('/integrations/jali/assessments/{assessment_id}/review')
	async def planted_review(assessment_id: str) -> dict[str, str]:
		return {'review': assessment_id}

	bad = [(m, p) for m, p in _integration_routes(planted)
	       if _guard_name(planted, m, p) is None and (m, p) not in OPEN_INTEGRATION_ROUTES]
	assert bad == [('GET', '/integrations/jali/assessments/{assessment_id}/review')], f'the gate missed it: {bad}'


async def test_pheoc_preview_applies_the_same_suppression_as_the_push() -> None:
	"""A preview that disagrees with the wire is worse than no preview: it would show a dashboard
	operator rows the push drops, and they would never know which is real."""
	import httpx as _httpx

	from afya.auth.views import s256
	from afya.service import build_services, create_app

	app = create_app(build_services())
	async with _httpx.AsyncClient(transport=_httpx.ASGITransport(app=app), base_url='http://t') as c:
		verifier = 'v' * 64
		authz = (await c.post('/auth/pkce/authorize', json={
			'client_id': 'app', 'redirect_uri': 'afya://cb', 'code_challenge': s256(verifier), 'state': 'state-1234',
		})).json()
		token = (await c.post('/auth/pkce/token', params={'role': 'pheoc_analyst'}, json={
			'authorization_code': authz['authorization_code'], 'client_id': 'app',
			'redirect_uri': 'afya://cb', 'code_verifier': verifier,
		})).json()['access_token']
		headers = {'authorization': f'Bearer {token}'}

		small = _geofence_events('CELL-X', 4)
		preview = await c.post('/integrations/pheoc/feeds/geofence_events/preview', json=small, headers=headers)
		assert preview.status_code == 200
		assert preview.json()['rows'] == [], 'the preview must not show a suppressed cell'
		assert preview.json()['cells_withheld'] == 1, 'one cell withheld, not one row per event'

		big = await c.post('/integrations/pheoc/feeds/geofence_events/preview', json=_geofence_events('CELL-Y', 12), headers=headers)
		assert len(big.json()['rows']) == 1 and big.json()['cells_withheld'] == 0

		# The county role cannot push a national feed, and the citizen cannot either.
		anon = (await c.post('/auth/anonymous', json={'subject_ref': 'U1'})).json()['token']
		denied = await c.post('/integrations/pheoc/feeds/geofence_events/preview', json=big.json()['rows'],
		                      headers={'authorization': f'Bearer {anon}'})
		assert denied.status_code == 403


async def test_hotline_follow_up_lands_in_the_feed(webhook_env: str) -> None:
	"""§18.4's inbound half: the follow-up is recorded where the person actually sees it, not in a
	table nothing reads."""
	import httpx as _httpx

	from afya.service import build_services, create_app

	services = build_services()
	app = create_app(services)
	async with _httpx.AsyncClient(transport=_httpx.ASGITransport(app=app), base_url='http://t') as c:
		body = {'case_ref': 'C-1', 'message': 'Your lab result is ready; visit the facility.', 'county': 'Busia'}
		raw, headers = _signed(body)
		resp = await c.post('/integrations/hotline/follow-up', content=raw, headers=headers)
		assert resp.status_code == 200 and resp.json()['recorded'] is True
		feed = (await c.get('/alerting/feed')).json()['items']
		assert any('719 hotline' in item['headline'] for item in feed), feed

		# Unsigned, or signed with the wrong secret, is someone else speaking as the national
		# hotline — into a feed a citizen reads.
		assert (await c.post('/integrations/hotline/follow-up', json=body)).status_code == 401
		bad_raw, bad_headers = _signed(body, 'not-the-secret')
		assert (await c.post('/integrations/hotline/follow-up', content=bad_raw, headers=bad_headers)).status_code == 401

		# An outcome code without consent is not recorded — the code alone names a caller.
		out_raw, out_h = _signed({'outcome_code': 'transported'})
		out = await c.post('/integrations/hotline/outcome', content=out_raw, headers=out_h)
		assert out.json()['recorded'] is False
		con_raw, con_h = _signed({'outcome_code': 'transported', 'consented': True})
		consented = await c.post('/integrations/hotline/outcome', content=con_raw, headers=con_h)
		assert consented.json()['recorded'] is True


async def test_inbound_sms_is_routed_by_intent(webhook_env: str) -> None:
	"""A free-text SMS is not a USSD menu selection. Routing it through the menu parser would refuse
	every real message with "USSD selections numeric"."""
	import httpx as _httpx

	from afya.service import build_services, create_app

	app = create_app(build_services())
	async with _httpx.AsyncClient(transport=_httpx.ASGITransport(app=app), base_url='http://t') as c:
		raw, headers = _signed({'from': '0712345678', 'text': 'I have fever'})
		resp = await c.post('/integrations/telco/sms/inbound', content=raw, headers=headers)
		assert resp.status_code == 200
		assert 'malaria' in resp.json()['reply'].lower()
		empty_raw, empty_h = _signed({'from': '0712345678', 'text': '  '})
		empty = await c.post('/integrations/telco/sms/inbound', content=empty_raw, headers=empty_h)
		assert empty.status_code == 422


async def test_inbound_sms_reads_the_language_prefix_off_the_body(webhook_env: str) -> None:
	"""§CHAN-1's Format: "local language option via keyword (e.g., prefix `SW`, `LU`, `KY`)".

	Through the front door, because the mechanism's whole defect was that it existed nowhere a
	sender could reach: the route took `lang` as a *query parameter*, and the person sending a text
	cannot set one. The prefix is now read off the body, and the answer says which language was
	served — a person who prefixed `LU` and is answered in English must be able to see that.
	"""
	import httpx as _httpx

	from afya.service import build_services, create_app

	app = create_app(build_services())
	async with _httpx.AsyncClient(transport=_httpx.ASGITransport(app=app), base_url='http://t') as c:
		# Kiswahili has a table, so the prefix changes the language served and not just the report.
		raw, headers = _signed({'from': '0712345678', 'text': 'SW nina homa'})
		sw = (await c.post('/integrations/telco/sms/inbound', content=raw, headers=headers)).json()
		assert sw['lang'] == 'sw' and sw['language_fallback'] is False, sw
		# The fever entry reaches §6.3's malaria trap, and the trap's sentence comes back in the
		# language the prefix asked for — which is the whole point of reading it off the body.
		assert 'malaria' in sw['reply'].lower(), sw['reply']
		# Dholuo is one of §CHAN-1's three prefixes and has no table, so the ask is honoured and the
		# fallback is *reported* rather than hidden behind a prefix that implied a translation.
		raw, headers = _signed({'from': '0712345678', 'text': 'LU an gi tuo'})
		luo = (await c.post('/integrations/telco/sms/inbound', content=raw, headers=headers)).json()
		assert luo['lang'] == 'en' and luo['language_fallback'] is True, luo
		# A prefix with nothing after it is a message with no report in it.
		raw, headers = _signed({'from': '0712345678', 'text': 'SW:'})
		assert (await c.post('/integrations/telco/sms/inbound', content=raw, headers=headers)).status_code == 422


async def test_the_callback_keyword_files_a_request(webhook_env: str) -> None:
	"""§CHAN-1's Inbound use case "Callback requests (`CALLBACK`)", on the keyword leg.

	The section prints the keyword and the USSD prompt collects the same request; this is the half
	that arrives as free text. It is matched as a whole word, because "callback" inside a longer
	message is a person writing *about* a call, and a queue entry against someone who asked for
	nothing is worse than no entry.
	"""
	import httpx as _httpx

	from afya.channels.service import ChannelService
	from afya.service import build_services, create_app

	services = build_services()
	app = create_app(services)
	channels: ChannelService = services['channels']  # type: ignore[assignment]
	async with _httpx.AsyncClient(transport=_httpx.ASGITransport(app=app), base_url='http://t') as c:
		raw, headers = _signed({'from': '0712345678', 'text': 'CALLBACK'})
		out = (await c.post('/integrations/telco/sms/inbound', content=raw, headers=headers)).json()
		assert out['intent'] == 'callback' and out['request_id'].startswith('CB-'), out
		assert 'call you back' in out['reply'].lower(), out['reply']
		queued = channels.callback_requests()
		assert len(queued) == 1 and queued[0].symptom is None, queued
		assert queued[0].msisdn == '+254712345678', 'filed against the E.164 spelling, not the carrier\'s'
		# A message that mentions a callback without being one is not a request.
		raw, headers = _signed({'from': '0712345678', 'text': 'please callback me tomorrow'})
		mentioned = (await c.post('/integrations/telco/sms/inbound', content=raw, headers=headers)).json()
		assert mentioned.get('intent') != 'callback', mentioned
		assert 'call you back' not in mentioned['reply'].lower(), mentioned['reply']
		assert len(channels.callback_requests()) == 1, 'a mention is not a request'


def test_every_spec_18_client_is_exported_and_wired() -> None:
	"""The integrations package's `__all__` and `build_services` must agree with the spec's list of
	systems, so a client cannot be added to the code and left unreachable from the app."""
	import afya.integrations.views as v
	from afya.service import build_services

	services = build_services()
	for name in ('adam', 'jali', 'pheoc', 'mohf', 'ppb', 'sha', 'telco'):
		assert name in services, f'§18 system {name} is not wired'
	for exported in ('AdamClient', 'JaliClient', 'PheocClient', 'MoHFFacilityClient', 'PPBClient', 'SHAClient', 'TelcoGatewayClient'):
		assert exported in v.__all__, exported
