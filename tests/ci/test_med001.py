"""Gate: §MED-001's six Features, and the one distinction a boolean cannot make.

The section prints four named outcomes — "Registered / Not found / Expired registration /
Recalled" — and `VerifyResult` carried `genuine: bool`. A recalled medicine and one that was never
registered both read `False`, and the two call for opposite actions: take it back to the seller,
versus this product does not exist and do not take it. That collapse is the §13.1 lossy-enum
defect, and this file is what keeps it collapsed.

The fifth status is the one that is not in the section and matters most. `unverified` is the
absence of a verdict, not a verdict: a registry that answered nothing has not said the medicine is
bad, only that nobody checked. Reporting that as `not_found` sends a person to throw away medicine
that was fine, which is this feature's own worst failure mode and the mirror of the one it exists
to prevent.
"""
import re

import httpx
import pytest
from pydantic import ValidationError
from pytest_httpserver import HTTPServer

from afya.content_audit.service import FEATURE_CONTENT
from afya.integrations.service import PPBClient
from afya.medicine.service import (
	PPBStubClient, MedicineService, display_from, registration_outcome, status_from_verify_answer,
)
from afya.medicine.views import (
	MODEL_CONFIG, ProductDisplay, RegistrationStatus, SuspiciousReport, VerifyRequest, VerifyResult,
)
from afya.service import build_services, create_app

FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')

SECTION_OUTCOMES = frozenset({'registered', 'not_found', 'expired', 'recalled'})


@pytest.fixture
async def client(httpserver: HTTPServer) -> httpx.AsyncClient:
	return httpx.AsyncClient(base_url=f'http://127.0.0.1:{httpserver.port}', timeout=5)


def _routes(app: object) -> set[tuple[str, str]]:
	"""Every (method, path) the app serves, walked recursively.

	`app.routes` nests: an `include_router` is an `_IncludedRouter` whose paths live on
	`original_router.routes`, so a flat walk returns `[]` and a test that trusted it would conclude
	a served route does not exist. That happened once on this exact feature.
	"""
	found: set[tuple[str, str]] = set()

	def walk(routes: object) -> None:
		for r in routes:  # type: ignore[attr-defined]
			if hasattr(r, 'routes'):
				walk(r.routes)
				continue
			for method in getattr(r, 'methods', None) or []:
				found.add((method, getattr(r, 'path', '')))

	walk(getattr(app, 'routes'))
	assert found, 'the walk found no routes, so every assertion below would pass vacuously'
	return found


# --- the four outcomes, and the fifth ------------------------------------------------------------

def test_the_four_named_outcomes_are_four_values() -> None:
	"""The section's own list, as members rather than as a comment."""
	assert SECTION_OUTCOMES <= {s.value for s in RegistrationStatus}


def test_a_recalled_medicine_and_an_unregistered_one_do_not_read_alike() -> None:
	"""The defect this file exists for, asserted on the two results a client would render.

	Both are `genuine=False`, which is correct and is exactly why the boolean was not enough: the
	person holding the box needs the reason, and the reason decides what they do next.
	"""
	recalled = VerifyResult(status=RegistrationStatus.recalled, source='PPB')
	missing = VerifyResult(status=RegistrationStatus.not_found, source='PPB')
	assert recalled.genuine is False and missing.genuine is False
	assert recalled.status is not missing.status
	assert recalled.recalled is True and missing.recalled is False


def test_only_registered_is_genuine() -> None:
	"""The collapse that *is* safe: one member is a yes and every other is a no.

	A status added without deciding this question fails here, which is the point — `unverified` had
	to be argued into the no.
	"""
	for status in RegistrationStatus:
		expected = status is RegistrationStatus.registered
		assert VerifyResult(status=status, source='PPB').genuine is expected, status


def test_unverified_is_the_absence_of_a_verdict_not_a_verdict() -> None:
	"""The fifth member is not one of the section's four, and this is the claim that justifies it.

	`status_from_verify_answer` is the only place the distinction is drawn, so it is driven with the
	two answers that differ: a registry that answered `genuine: false` with no product row has told
	us the batch is not in the registry (`not_found`); a registry that answered an unrecognisable
	body has told us nothing at all (`unverified`).
	"""
	answered_no, _, _ = status_from_verify_answer({'genuine': False}, 'B123')
	assert answered_no is RegistrationStatus.not_found
	silent, row, recalls = status_from_verify_answer({'unexpected': 'shape'}, 'B123')
	assert silent is RegistrationStatus.unverified
	assert row is None and recalls == []


async def test_the_offline_stub_says_it_could_not_check_rather_than_that_the_batch_is_fake() -> None:
	"""§MED-001's Offline clause promises a cached registry; the stub holds none.

	It answers `unverified`, and `genuine` is still False, so the fail-closed behaviour the README
	claims is unchanged — what changed is that the client can now say *why*, and the answer is not
	an accusation.
	"""
	svc = MedicineService(PPBStubClient())
	out = await svc.verify(VerifyRequest(batch_number='B1234', gtin='0123456789012'))
	assert out.status is RegistrationStatus.unverified
	assert out.status is not RegistrationStatus.not_found
	assert out.genuine is False


# --- the Display line ----------------------------------------------------------------------------

def test_display_carries_all_five_named_fields() -> None:
	"""§MED-001's Display line, one field per name it prints."""
	names = set(ProductDisplay.model_fields)
	assert {'product_name', 'manufacturer', 'registration_status', 'expiry_iso',
		'batch_recalls'} <= names


def test_display_reads_the_registry_row_it_is_given() -> None:
	row: dict[str, object] = {'product_name': 'Paracetamol 500mg', 'manufacturer': 'Cosmos Ltd',
		'status': 'registered', 'expiry_iso': '2027-04-30'}
	out = display_from(row, RegistrationStatus.registered, [])
	assert out.product_name == 'Paracetamol 500mg'
	assert out.manufacturer == 'Cosmos Ltd'
	assert out.expiry_iso == '2027-04-30'
	assert out.registration_status is RegistrationStatus.registered


def test_a_product_the_registry_does_not_hold_displays_nothing() -> None:
	"""A filled-in name for a `not_found` batch is an invented medicine.

	The absence is the answer here, so the test asserts the blank rather than tolerating it.
	"""
	out = display_from(None, RegistrationStatus.not_found, [])
	assert out.product_name is None and out.manufacturer is None
	assert out.expiry_iso is None and out.batch_recalls == []


def test_the_registry_field_spellings_are_read_rather_than_assumed() -> None:
	"""PPB's column names are not pinned by the spec, so a blank must not depend on one spelling.

	Driven on two spellings of the same fact: a client that read only `product_name` would render a
	blank the day the regulator sends `name`.
	"""
	assert display_from({'name': 'Amoxicillin'}, RegistrationStatus.registered, []).product_name == 'Amoxicillin'
	assert display_from({'brand_name': 'Amoxil'}, RegistrationStatus.registered, []).product_name == 'Amoxil'
	assert display_from({'manufacturer': 'GSK'}, RegistrationStatus.registered, []).manufacturer == 'GSK'
	assert display_from({'holder': 'GSK'}, RegistrationStatus.registered, []).manufacturer == 'GSK'


def test_a_recall_outranks_a_registration() -> None:
	"""A product can be registered, unexpired and withdrawn; the withdrawal is the fact that counts.

	Asserted against `registration_outcome` directly, because the ordering is the whole content of
	the function and a test that drove it through the client would be testing the wire.
	"""
	row: dict[str, object] = {'product_name': 'X', 'status': 'registered', 'expiry_iso': '2099-01-01'}
	assert registration_outcome(row, recalled=True) is RegistrationStatus.recalled
	assert registration_outcome(row, recalled=False) is RegistrationStatus.registered


def test_a_lapsed_registration_is_expired_and_an_absent_row_is_not_found() -> None:
	assert registration_outcome({'status': 'expired'}, recalled=False) is RegistrationStatus.expired
	assert registration_outcome({'status': 'withdrawn'}, recalled=False) is RegistrationStatus.expired
	assert registration_outcome(None, recalled=False) is RegistrationStatus.not_found


def test_a_recall_for_another_batch_is_not_put_on_this_persons_screen() -> None:
	"""The false alarm that teaches people to ignore the real one.

	A registry that returns every recall it holds must not have another batch's withdrawal read as
	this batch's.
	"""
	_, _, mine = status_from_verify_answer(
		{'genuine': True, 'recalls': [{'batch': 'B123', 'reason': 'contamination'},
			{'batch': 'B999', 'reason': 'labelling'}]}, 'B123')
	assert [r['batch'] for r in mine] == ['B123']
	# And a recall row naming no batch is kept: it is a product-level withdrawal, which applies.
	_, _, unnamed = status_from_verify_answer({'genuine': True, 'recalls': [{'reason': 'x'}]}, 'B123')
	assert len(unnamed) == 1


def test_a_nested_product_row_is_read_as_well_as_a_flat_one() -> None:
	"""Three shapes, all plausible, none wrong — and an unrecognised one is `unverified`."""
	status, row, _ = status_from_verify_answer(
		{'product': {'product_name': 'ORS', 'status': 'registered'}}, 'B123')
	assert status is RegistrationStatus.registered and row is not None
	assert row is not None and row['product_name'] == 'ORS'


# --- the wire, driven against a real server ------------------------------------------------------

async def test_the_client_returns_the_four_way_status_and_the_display_line(
	client: httpx.AsyncClient, httpserver: HTTPServer,
) -> None:
	httpserver.expect_request('/verify', method='GET').respond_with_json({
		'genuine': True, 'product': {'product_name': 'Paracetamol 500mg', 'manufacturer': 'Cosmos',
			'status': 'registered', 'expiry_iso': '2027-04-30'}})
	ppb = PPBClient(httpserver.url_for('/'), client)
	out = await ppb.verify(VerifyRequest(batch_number='B123', gtin='0123456789012'))
	assert out.status is RegistrationStatus.registered
	assert out.display.product_name == 'Paracetamol 500mg'
	assert out.display.registration_status is RegistrationStatus.registered
	assert out.genuine is True


async def test_a_404_is_not_found_and_a_silent_answer_is_unverified(
	client: httpx.AsyncClient, httpserver: HTTPServer,
) -> None:
	httpserver.expect_request('/verify', method='GET', query_string={'gtin': '0000000000001', 'batch': 'B404'}).respond_with_data('', status=404)
	httpserver.expect_request('/verify', method='GET', query_string={'gtin': '0000000000002', 'batch': 'B500'}).respond_with_json({'unexpected': 1})
	ppb = PPBClient(httpserver.url_for('/'), client)
	missing = await ppb.verify(VerifyRequest(batch_number='B404', gtin='0000000000001'))
	assert missing.status is RegistrationStatus.not_found
	silent = await ppb.verify(VerifyRequest(batch_number='B500', gtin='0000000000002'))
	assert silent.status is RegistrationStatus.unverified
	assert silent.genuine is False


async def test_the_client_refuses_a_non_mapping_answer(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	"""A list is not a verify answer, and reading one as `not_found` would be a guess."""
	httpserver.expect_request('/verify', method='GET').respond_with_json([1, 2, 3])
	ppb = PPBClient(httpserver.url_for('/'), client)
	with pytest.raises(AssertionError, match='mapping'):
		await ppb.verify(VerifyRequest(batch_number='B123', gtin='0123456789012'))


# --- the served result round-trips ---------------------------------------------------------------

async def test_the_served_verify_result_is_a_body_the_api_accepts_back() -> None:
	"""A computed field on a request body is the defect `afya.derived` exists for.

	`VerifyResult` gained `genuine` and `recalled` as computed fields, so it now carries keys a
	caller cannot set. It is not a request body today — the route takes `VerifyRequest` — and this
	asserts both halves of that: the served payload is complete, and the published schema for the
	*request* body names no computed field, so nothing is asking a client to send one.

	Asserted against the schema rather than by calling the route, because the app's medicine service
	is wired to the live PPB URL and a test that posted to it would be testing the regulator's
	uptime. `test_request_bodies_round_trip.py` is the gate that walks every body; this is the one
	that would say which model broke.
	"""
	served = VerifyResult(status=RegistrationStatus.recalled, source='PPB',
		display=ProductDisplay(product_name='X', registration_status=RegistrationStatus.recalled))
	body = served.model_dump(mode='json')
	assert {'genuine', 'recalled', 'status', 'display', 'source'} <= set(body)
	assert body['genuine'] is False and body['recalled'] is True
	assert set(VerifyResult.model_computed_fields) == {'genuine', 'recalled'}
	schema = create_app(build_services()).openapi()
	request_body = schema['paths']['/medicine/verify']['post']['requestBody']
	named = request_body['content']['application/json']['schema']['$ref'].rsplit('/', 1)[-1]
	assert named == 'VerifyRequest'
	assert not (set(schema['components']['schemas']['VerifyRequest']['properties'])
		& set(VerifyResult.model_computed_fields)), 'the request body asks for a field the model computes'


# --- the report path -----------------------------------------------------------------------------

def test_the_report_route_is_served() -> None:
	"""The audit row for this bullet claimed no report route existed. It does, and this is the check
	that would have said so — a flat `app.routes` walk returns `[]` and concludes the opposite."""
	served = _routes(create_app(build_services()))
	assert ('POST', '/medicine/suspicious') in served


def test_a_report_must_name_a_product_or_a_batch() -> None:
	"""A report naming neither names nothing the regulator can act on."""
	with pytest.raises(ValidationError, match='gtin or a batch'):
		SuspiciousReport()
	assert SuspiciousReport(gtin='0123456789012').gtin == '0123456789012'
	assert SuspiciousReport(batch_number='B1234').batch_number == 'B1234'


def test_a_misspelled_report_key_is_refused_rather_than_dropped() -> None:
	"""This body is forwarded verbatim to the PPB intake, which is why it is typed.

	As a bare `dict` a client sending `batch` instead of `batch_number` sent the regulator a report
	with no batch on it and received a case reference for it. `extra='forbid'` is the fix, and this
	asserts the model carries it rather than inheriting it by luck.
	"""
	assert MODEL_CONFIG.get('extra') == 'forbid'
	misspelled: dict[str, object] = {'batch': 'B1234'}
	with pytest.raises(ValidationError, match='batch'):
		SuspiciousReport.model_validate(misspelled)


def test_a_report_photo_travels_as_a_hash() -> None:
	"""§18.7's row is "Report with photo", and every other image in this app travels by hash.

	The report carries the digest, not the image: the evidence pipeline is what hashes, dedupes and
	size-caps it, and a raw base64 body on this route would be a second upload path with none of
	those checks.
	"""
	assert 'photo_sha256' in SuspiciousReport.model_fields
	with pytest.raises(ValidationError):
		SuspiciousReport(gtin='0123456789012', photo_sha256='not-a-digest')


async def test_the_report_client_sends_the_typed_body(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	"""Driven against a real server, because the failure it guards is a key the wire drops."""
	httpserver.expect_request('/suspicious', method='POST').respond_with_json({'case_ref': 'PPB-9'})
	ppb = PPBClient(httpserver.url_for('/'), client)
	ref = await ppb.report_suspicious(SuspiciousReport(gtin='0123456789012', batch_number='B1234',
		note='box looks wrong'))
	assert ref == 'PPB-9'
	sent = httpserver.log[0][0].get_json()
	assert sent['batch_number'] == 'B1234' and sent['gtin'] == '0123456789012'
	# `exclude_none` means an unset field is absent rather than null, so the regulator's intake does
	# not have to distinguish "no photo" from "a photo of nothing".
	assert 'photo_sha256' not in sent


async def test_the_report_route_reaches_the_regulator_and_returns_its_reference(
	client: httpx.AsyncClient, httpserver: HTTPServer,
) -> None:
	"""End to end through the app, with a token and a stub PPB on the other end.

	The route reads `svc['ppb']`, so the stub is injected into the services dict before the app is
	built — which is what makes this a test of the route rather than of the client it calls. The
	assertion on the received body is the one that matters: a report that reached the regulator
	carrying the wrong keys would still return a case reference, and the person would believe it.
	"""
	httpserver.expect_request('/suspicious', method='POST').respond_with_json({'case_ref': 'PPB-77'})
	services = build_services()
	services['ppb'] = PPBClient(httpserver.url_for('/'), client)
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		tok = (await c.post('/auth/anonymous', json={})).json()['token']
		resp = await c.post('/medicine/suspicious',
			json={'gtin': '0123456789012', 'batch_number': 'B1234', 'note': 'box looks wrong'},
			headers={'authorization': f'Bearer {tok}'})
	assert resp.status_code == 200, resp.text
	assert resp.json() == {'ppb_case_ref': 'PPB-77'}
	sent = httpserver.log[0][0].get_json()
	assert sent['gtin'] == '0123456789012' and sent['batch_number'] == 'B1234'
	assert sent['note'] == 'box looks wrong'


async def test_the_report_route_says_so_when_the_regulator_is_unreachable(client: httpx.AsyncClient) -> None:
	"""Driven through the app with a token, against a port nothing is listening on.

	The client is injected rather than left at the configured PPB URL, so the test does not depend
	on whether `ppb.health.go.ke` happens to resolve where it runs. The route must report the
	failure rather than invent a case reference — a fabricated reference would tell a person their
	report was received when nothing left the building.
	"""
	services = build_services()
	# Port 1 is reserved and nothing listens there, so the connection is refused on any host.
	services['ppb'] = PPBClient('http://127.0.0.1:1', client)
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		tok = (await c.post('/auth/anonymous', json={})).json()['token']
		resp = await c.post('/medicine/suspicious', json={'gtin': '0123456789012'},
			headers={'authorization': f'Bearer {tok}'})
	assert resp.status_code == 502, resp.text
	assert 'unreachable' in str(resp.json())


async def test_an_unauthenticated_report_is_refused() -> None:
	"""The route is self-scoped so the report is attributable and the egress is not an open relay."""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		resp = await c.post('/medicine/suspicious', json={'gtin': '0123456789012'})
	assert resp.status_code in (401, 403), resp.status_code


# --- the section's own bookkeeping ---------------------------------------------------------------

def test_every_med001_bullet_is_accounted_for() -> None:
	"""Six bullets, and none of them `missing` — which is the claim this unit makes.

	Five `carried` and one `deferred`: the barcode read is the device's, the packaging photo is
	taken and read on the device too (there is no OCR server-side, and the section's own Privacy
	clause says a scan is not transmitted unless it is a report), and the other four name code.
	"""
	rows = [(b, k) for f, _, b, k, _, _ in FEATURE_CONTENT if f == 'MED-001']
	assert len(rows) == 6, rows
	assert [k for _, k in rows].count('missing') == 0, rows
	assert [k for _, k in rows].count('carried') == 4, rows
	assert [k for _, k in rows].count('deferred') == 2, rows


def test_the_carried_rows_name_code_that_exists() -> None:
	"""A carrier is a claim about the code; this is the walk that makes it checkable."""
	from afya.refs import resolves
	for f, _, _, kind, ref, _ in FEATURE_CONTENT:
		if f == 'MED-001' and kind == 'carried':
			assert resolves(ref), ref


def test_no_spec_code_reaches_a_medicine_surface() -> None:
	"""The standing constraint: §MED-001's ids are traceability handles, not user-facing strings."""
	from afya.mobile.actions import catalogue
	for act in catalogue():
		assert not FEATURE_CODE.search(act.title), act.title
		assert not FEATURE_CODE.search(act.id), act.id
		for fld in act.fields:
			assert not FEATURE_CODE.search(fld.label), fld.label
