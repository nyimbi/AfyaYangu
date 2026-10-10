from typing import Any

import httpx
import pytest
from pytest_httpserver import HTTPServer

from afya.integrations.adam import PII_FIELDS, AdamClient
from afya.integrations.feeds import FEED_CADENCE, FEED_GRANULARITY, MIN_CELL, build as build_feed
from afya.integrations.gateways import AtSmsRestSend, WhatsAppBusinessClient
from afya.integrations.service import (
	JaliClient, MoHFFacilityClient, PPBClient, PheocClient, SHAClient, TelcoGatewayClient,
)
from afya.channels.views import SmsOut
from afya.insurance.views import SHACheckRequest
from afya.medicine.views import VerifyRequest


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
	assert await sender.send(SmsOut(to_msisdn='+254711222333', body='Call 719', segments=1)) == 'ATX_1'


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
	httpserver.expect_request('/v1/assessments/A1/review', method='GET').respond_with_json({'clinician': 'Dr X'})
	jali = JaliClient(httpserver.url_for('/'), 'sk-1', client)
	assert (await jali.launch_link('triage', 'U1')).endswith('/abc')
	assert (await jali.corrections('2026-01-01T00:00:00Z'))[0]['topic'] == 'bleach'
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
	assert await ppb.report_suspicious({'gtin': '0123456789012'}) == 'PPB-5'
	with pytest.raises(AssertionError, match='gtin or batch'):
		await ppb.report_suspicious({})


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
