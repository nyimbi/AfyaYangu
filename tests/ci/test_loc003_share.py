"""§LOC-003's "Report shared with health authorities through a secure channel".

The audit row was `carried` and cited `afya.location.views:LocationReport` — a *data shape*, which
is what the report is read as and shares nothing. What actually existed was a `share: bool`
parameter on `build_report` that composed "Report generated and shared as coarse locations only."
from the flag, wrote a log line, and put nothing on the wire. So the person was told the county
held their report, and §SEC-006's dashboard — which reads the share ledger — would have answered
"nothing shared".

These tests hold the three gates (consent, a history to share, an application-layer key), the two
honesty properties (the message distinguishes held from delivered; the ciphertext is not echoed
back), the generalisation the section names, and the ledger the dashboard reads.
"""
import json

import httpx
import pytest

from afya.crypto.service import CryptoService, Sealed
from afya.location.service import SHARE_AUTHORITY_CATEGORY, LocationService
from afya.location.views import LocationPoint


def _crypto(app_layer: bool = True) -> CryptoService:
	"""A deployment with both §SEC-003 keys, or one missing the second on purpose."""
	return CryptoService(
		at_rest_key=b'a' * 32,
		app_layer_key=b'b' * 32 if app_layer else None,
	)


def _sealer(crypto: CryptoService):
	"""§SEC-003's application-layer key as the one object the location module calls with it.

	Written here rather than imported from `afya.service` on purpose: importing the composition
	root's helper would make this suite pass for a reason that has nothing to do with the service
	under test. `test_the_route_*` below drives the real one.
	"""
	class _Sealer:
		@property
		def available(self) -> bool:
			return crypto.has_app_layer

		def __call__(self, plaintext: bytes) -> str:
			assert crypto.has_app_layer, (
				'no application-layer key is configured, so a location report cannot be sealed; '
				'refusing rather than sharing it under the at-rest key alone')
			return str(crypto.seal(plaintext, app_layer=True).to_blob())
	return _Sealer()


class RecordingAuthority:
	"""A transport that records what it was handed. Structural: it satisfies
	`LocationAuthorityPort` by having the one method, which is the point of the protocol."""

	def __init__(self) -> None:
		self.envelopes: list[dict[str, object]] = []

	async def deliver_report(self, envelope: dict[str, object]) -> str:
		self.envelopes.append(envelope)
		return f'RPT-{len(self.envelopes)}'


class FailingAuthority:
	"""A transport that exists and is unreachable, which §LOC-003's own story treats as normal."""

	async def deliver_report(self, envelope: dict[str, object]) -> str:
		raise ConnectionError('no route to the county endpoint')


def _history(svc: LocationService, subject: str = 'U-1', points: int = 2) -> None:
	svc.enable_history(subject)
	for i in range(points):
		svc.log_location(subject, LocationPoint(geohash=f'kzcvx{i}234', at_iso=f'2026-10-0{i + 1}T00:00:00Z'))


def _consent(*granted: str):
	"""A consent ledger that holds §SEC-001's sharing category for the named subjects.

	The tracking consent is `enable_history`, so a subject listed here has both — which is the
	ordinary state of a person who taps through the whole flow.
	"""
	def holds(subject_ref: str, category: str) -> bool:
		return category == SHARE_AUTHORITY_CATEGORY and subject_ref in granted
	return holds


def _svc(**over: object) -> LocationService:
	"""The ordinary deployment: a key, a consent ledger for U-1, and whatever the test overrides."""
	base: dict[str, object] = {
		'sealer': _sealer(_crypto()), 'share_consent': _consent('U-1'),
	}
	base.update(over)
	return LocationService(**base)  # type: ignore[arg-type]


# --- the category is the enum's own value --------------------------------------------------

def test_the_category_the_location_module_holds_is_sec001s_own() -> None:
	"""`afya.location` keeps no import edge to `afya.privacy`, so it spells the category itself. A
	copy that drifted would be a share gated on a permission nobody can grant — which passes every
	test that hands the service a fake ledger and fails for every real person."""
	from afya.privacy.views import ConsentCategory
	assert SHARE_AUTHORITY_CATEGORY == ConsentCategory.share_health_authorities.value


async def test_the_real_ledger_opens_the_gate_the_fake_ledger_stands_in_for() -> None:
	"""The fake above answers `category == SHARE_AUTHORITY_CATEGORY`, so it would satisfy a gate
	written against the wrong string. This drives the composition root's own helper and a real
	`PrivacyService`: a grant filed under §SEC-001's category lets the share through, and the same
	ledger with the grant withdrawn refuses it.

	Without this, `test_the_category_the_location_module_holds_is_sec001s_own` and the route tests
	would each pass while the two ends never met.
	"""
	from afya.privacy.service import PrivacyService
	from afya.privacy.views import ConsentRecord, LegalBasis
	from afya.service import _share_authority_consent
	privacy = PrivacyService()
	record = ConsentRecord(subject_ref='U-1', purpose=SHARE_AUTHORITY_CATEGORY,
	                       data_types=['location_history'], retention_days=21,
	                       legal_basis=LegalBasis.consent, lang='en')
	await privacy.record_consent(record)
	svc = LocationService(sealer=_sealer(_crypto()), authority=RecordingAuthority(),
	                      share_consent=_share_authority_consent(privacy))
	_history(svc)
	receipt = await svc.share_report('U-1')
	assert receipt.delivered is True

	# Withdrawn is not consent — the same rule `has_consent` applies, and the one that makes
	# revocation one tap rather than a request.
	await privacy.withdraw(record.consent_id)
	svc2 = LocationService(sealer=_sealer(_crypto()), authority=RecordingAuthority(),
	                       share_consent=_share_authority_consent(privacy))
	_history(svc2)
	with pytest.raises(AssertionError, match='share with health authorities'):
		await svc2.share_report('U-1')


# --- the three gates ---------------------------------------------------------------------

async def test_a_share_needs_a_history_that_was_consented_to() -> None:
	"""§LOC-003: "If the user tests positive and consents". `enable_history` is that consent, and a
	share on request without it would make the consent decorative — the audit row's own shape."""
	svc = _svc()
	with pytest.raises(AssertionError, match='no history on file'):
		await svc.share_report('U-nobody')


async def test_a_history_without_the_tracking_consent_cannot_be_shared() -> None:
	"""The state is reachable: `LocationHistory.consent_granted` defaults to `False`, so a history
	written by a path that did not consent is a history that must not leave."""
	from afya.location.views import LocationHistory
	svc = _svc()
	svc._histories['U-1'] = LocationHistory(subject_ref='U-1', consent_granted=False)
	with pytest.raises(AssertionError, match='explicit consent'):
		await svc.share_report('U-1')


async def test_a_diary_without_the_sharing_permission_cannot_be_shared() -> None:
	"""The defect the first cut of this unit had, and the reason it is a separate test.

	`enable_history` records §LOC-003's `location_tracking` decision. §SEC-001's
	`share_health_authorities` is a *different toggle* — "Counts of illness, with no names, go to the
	Ministry" — and the first cut read the tracking flag as the sharing permission, so a person who
	allowed a diary and refused the Ministry had their diary sent anyway. The two are asserted apart
	so a future change cannot collapse them again.
	"""
	svc = _svc(share_consent=_consent())  # a diary, no Ministry permission
	_history(svc)
	with pytest.raises(AssertionError, match='share with health authorities'):
		await svc.share_report('U-1')
	assert svc.shared_reports('U-1') == [], 'a refused share leaves no envelope'


async def test_a_deployment_with_no_consent_ledger_refuses_to_share() -> None:
	"""Fail closed. A service that cannot ask the question must not answer it yes."""
	svc = _svc(share_consent=None)
	_history(svc)
	with pytest.raises(AssertionError, match='share with health authorities'):
		await svc.share_report('U-1')


async def test_a_deployment_with_no_application_layer_key_refuses_to_share() -> None:
	"""The dangerous direction. Falling back to the at-rest key would put a location history under
	the key the operator already holds, which is the one layer §SEC-003 says is not enough for it —
	and a location history is the one record that can put a person somewhere.

	The match is on the *service's* own wording rather than on "application-layer key", because the
	composition root's sealer raises its own refusal containing that phrase — a looser match would
	pass whether the service refused up front or let the seal fail underneath, which is the
	difference between a gate and a fallback that happens to trip.
	"""
	svc = _svc(sealer=_sealer(_crypto(app_layer=False)))
	_history(svc)
	with pytest.raises(AssertionError, match='the deployment holds no application-layer key'):
		await svc.share_report('U-1')


async def test_a_service_with_no_sealer_at_all_refuses_to_share() -> None:
	svc = _svc(sealer=None)
	_history(svc)
	with pytest.raises(AssertionError, match='the deployment holds no application-layer key'):
		await svc.share_report('U-1')


# --- what actually travels ---------------------------------------------------------------

async def test_what_travels_is_a_coarse_cell_and_never_the_coordinate() -> None:
	"""§LOC-003's "Geohashing anonymises location data before sharing", read as a property of the
	bytes rather than a label on the row.

	The service was written with `{p.geohash for p in history.points}` — the *full* 9-character
	geohash — so the generalisation the section names was not applied on the one path that leaves
	the device. `_geohash_cell` truncates to five characters, which is roughly a 4.9 km × 4.9 km
	box; nine characters is a doorway.
	"""
	authority = RecordingAuthority()
	crypto = _crypto()
	svc = _svc(sealer=_sealer(crypto), authority=authority)
	_history(svc)
	await svc.share_report('U-1')
	sealed = str(authority.envelopes[0]['sealed'])
	body = json.loads(crypto.open(Sealed.from_blob(sealed)))
	assert body['cells'] == ['kzcvx'], 'the full geohash left the device'
	assert all(len(c) == 5 for c in body['cells'])


async def test_the_report_travels_as_ciphertext_and_the_at_rest_key_does_not_open_it() -> None:
	authority = RecordingAuthority()
	svc = _svc(authority=authority)
	_history(svc)
	await svc.share_report('U-1')
	blob = Sealed.from_blob(str(authority.envelopes[0]['sealed']))
	assert blob.layer == 'app_layer', 'the layer travels with the value'
	for needle in (b'kzcvx', b'subject_ref', b'cells'):
		assert needle not in blob.ciphertext, f'{needle!r} is legible in the ciphertext'
	# A deployment that knows only the at-rest key — the one an operator holds — cannot read it.
	from afya.crypto.service import KEY_BYTES
	at_rest_only = CryptoService(at_rest_key=b'a' * KEY_BYTES)
	with pytest.raises(AssertionError, match='no app_layer key'):
		at_rest_only.open(blob)


async def test_the_receipt_does_not_echo_the_ciphertext_back() -> None:
	svc = _svc(authority=RecordingAuthority())
	_history(svc)
	receipt = await svc.share_report('U-1')
	dumped = receipt.model_dump(mode='json')
	assert 'sealed' not in dumped
	assert set(dumped) == {
		'share_id', 'with_who', 'places', 'shared_at_ms', 'algorithm', 'delivered', 'message',
	}


# --- held versus delivered ---------------------------------------------------------------

async def test_a_share_that_could_not_be_delivered_is_kept_and_says_so() -> None:
	"""§16.1 principle 5 — nothing is lost — and the reason it matters here: the person sharing a
	location history is a person who has been told they tested positive, which is not a moment to
	depend on the county's endpoint being up. The flattering answer is the one this closes."""
	svc = _svc(authority=FailingAuthority())
	_history(svc)
	receipt = await svc.share_report('U-1')
	assert receipt.delivered is False
	assert 'kept on this device' in receipt.message
	held = svc.shared_reports('U-1')
	assert len(held) == 1, 'the sealed report was lost when the transport failed'
	assert Sealed.from_blob(held[0].sealed).layer == 'app_layer'


async def test_a_delivered_share_says_so_and_names_an_office_not_a_person() -> None:
	authority = RecordingAuthority()
	svc = _svc(authority=authority)
	_history(svc)
	receipt = await svc.share_report('U-1')
	assert receipt.delivered is True
	assert 'sent to county health team' in receipt.message
	assert receipt.algorithm == 'AES-256-GCM'
	assert receipt.share_id.startswith('LSH-')
	assert len(authority.envelopes) == 1


async def test_a_deployment_with_no_transport_still_seals_and_keeps_the_report() -> None:
	"""A deployment with no endpoint is the state the composition root wires, so this is the path
	production actually takes until an endpoint is configured."""
	svc = _svc()
	_history(svc)
	receipt = await svc.share_report('U-1')
	assert receipt.delivered is False
	assert len(svc.shared_reports('U-1')) == 1


async def test_a_second_share_to_one_recipient_reuses_the_envelope() -> None:
	"""Sealing again would leave the first envelope in the outbox forever, so §SEC-006's dashboard
	would show two shares where the person made one."""
	svc = _svc(authority=RecordingAuthority())
	_history(svc)
	first = await svc.share_report('U-1')
	second = await svc.share_report('U-1')
	assert second.share_id == first.share_id
	assert len(svc.shared_reports('U-1')) == 1


# --- the report itself claims nothing ----------------------------------------------------

def test_the_report_on_the_persons_screen_never_claims_a_share() -> None:
	"""The defect this whole unit exists for. `build_report` took a `share` flag and composed the
	sharing sentence from it, so the person's own screen asserted a disclosure that had not
	happened. There is no flag now, and the sentence says only what the method did."""
	svc = _svc(authority=RecordingAuthority())
	_history(svc)
	report = svc.build_report('U-1')
	assert report.shared_with is None
	assert report.message == 'Report generated on your phone. Nothing has been sent.'
	assert 'shared' not in report.message.lower()
	# And building the report did not share anything behind the person's back.
	assert svc.shared_reports('U-1') == []


# --- through the front door --------------------------------------------------------------

async def _citizen(c: httpx.AsyncClient, subject: str) -> dict[str, str]:
	anon = await c.post('/auth/anonymous', json={'subject_ref': subject})
	assert anon.status_code == 200, anon.text
	return {'Authorization': f"Bearer {anon.json()['token']}"}


async def _grant_sharing(privacy: object, subject: str) -> None:
	"""File §SEC-001's sharing grant in the composed deployment's own ledger.

	The route is gated on the real ledger, so a route test that skipped this would be asserting the
	422 path and calling it the feature — the shape the standing rule about route tests names.
	"""
	from afya.privacy.views import ConsentRecord, LegalBasis
	await privacy.record_consent(ConsentRecord(  # type: ignore[attr-defined]
		subject_ref=subject, purpose=SHARE_AUTHORITY_CATEGORY, data_types=['location_history'],
		retention_days=21, legal_basis=LegalBasis.consent, lang='en'))


async def test_the_route_shares_for_a_signed_in_person_and_reaches_the_dashboard(
		monkeypatch: pytest.MonkeyPatch) -> None:
	"""A green unit test says nothing about the front door. This drives the routes.

	The deployment is built with `build_services()` so the composition root is under test — a
	service handed a sealer proves nothing about whether production passes one. The application
	layer key comes from the environment, which is where §SEC-003 says it lives.
	"""
	from afya.service import build_services, create_app
	monkeypatch.setenv('AFYA_APP_LAYER_KEY', 'b' * 64)
	monkeypatch.setenv('AFYA_AT_REST_KEY', 'a' * 64)
	svc = build_services()
	app = create_app(svc)
	location: LocationService = svc['location']  # type: ignore[assignment]
	_history(location, subject='route-1')
	await _grant_sharing(svc['privacy'], 'route-1')
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers = await _citizen(c, 'route-1')
		report = await c.get('/location/history/route-1/report', headers=headers)
		assert report.status_code == 200, report.text
		assert report.json()['shared_with'] is None
		assert 'Nothing has been sent' in report.json()['message']

		posted = await c.post('/location/history/route-1/share', headers=headers)
		assert posted.status_code == 200, posted.text
		body = posted.json()
		assert 'sealed' not in body
		# Both points fall in the one five-character cell, so the report names one place — which is
		# the generalisation doing its job, and the count the ledger row has to agree with.
		assert body['places'] == 1
		# No transport is wired by the composition root, so the honest answer is held.
		assert body['delivered'] is False
		# The share is real: an envelope sealed under the app-layer key is held.
		held = location.shared_reports('route-1')
		assert len(held) == 1
		assert Sealed.from_blob(held[0].sealed).layer == 'app_layer'
		# The listing serves it, still without the ciphertext.
		listed = await c.get('/location/history/route-1/shares', headers=headers)
		assert listed.status_code == 200, listed.text
		assert len(listed.json()) == 1
		assert 'sealed' not in listed.json()[0]
		# A share that was *not* delivered must not be in the ledger: the dashboard says what the
		# county holds, and claiming a report the county never received is the defect again.
		inventory = await c.get('/retention/inventory/route-1', headers=headers)
		assert inventory.status_code == 200, inventory.text
		assert inventory.json()['shared_with'] == []


async def test_the_route_refuses_a_share_with_no_history() -> None:
	from afya.service import build_services, create_app
	svc = build_services()
	app = create_app(svc)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers = await _citizen(c, 'route-2')
		posted = await c.post('/location/history/route-2/share', headers=headers)
	assert posted.status_code == 422, posted.text
	assert 'no history on file' in posted.json()['detail']


async def test_the_route_binds_the_report_to_the_token_holder() -> None:
	"""`require_self` — a caller naming someone else's history is refused rather than served it."""
	from afya.service import build_services, create_app
	svc = build_services()
	app = create_app(svc)
	location: LocationService = svc['location']  # type: ignore[assignment]
	_history(location, subject='someone-else')
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers = await _citizen(c, 'route-3')
		posted = await c.post('/location/history/someone-else/share', headers=headers)
	assert posted.status_code == 403, posted.text


async def test_a_delivered_share_reaches_the_ledger_the_dashboard_reads(
		monkeypatch: pytest.MonkeyPatch) -> None:
	"""§SEC-006's "what has been shared, with whom, when" reads `RetentionService.inventory`. A
	share that did not reach it would leave the dashboard answering "nothing shared" about a report
	the person believes the county holds — which is the audit row's defect in a different field.

	The key comes from the environment, as §SEC-003 says it does, and only the *transport* is fitted
	by hand: the composition root deliberately leaves it unwired, because an endpoint is a
	deployment's and a test that reached the internet would be a test that depends on it.
	"""
	from afya.service import build_services, create_app
	monkeypatch.setenv('AFYA_APP_LAYER_KEY', 'b' * 64)
	monkeypatch.setenv('AFYA_AT_REST_KEY', 'a' * 64)
	svc = build_services()
	app = create_app(svc)
	location: LocationService = svc['location']  # type: ignore[assignment]
	_history(location, subject='route-4')
	await _grant_sharing(svc['privacy'], 'route-4')
	location._authority = RecordingAuthority()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers = await _citizen(c, 'route-4')
		posted = await c.post('/location/history/route-4/share', headers=headers)
		assert posted.status_code == 200, posted.text
		assert posted.json()['delivered'] is True
		inventory = await c.get('/retention/inventory/route-4', headers=headers)
		assert inventory.status_code == 200, inventory.text
		shares = inventory.json()['shared_with']
		assert len(shares) == 1, 'the delivered share did not reach the in-app data dashboard'
		assert shares[0]['with'] == 'county health team'
		assert shares[0]['what'] == 'location report (1 place)'


# --- what the client is offered ------------------------------------------------------------

def test_no_spec_feature_code_reaches_a_served_location_field() -> None:
	"""The standing constraint: spec ids are backend identifiers and must not surface.

	Also pins the shape the unit closed. `location_report` used to carry a `share` field, so the
	form offered a switch that sent nothing while the screen said it had — a field on a *read*
	action whose only effect was the sentence the server composed from it.
	"""
	import re
	from afya.mobile.actions import catalogue
	FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')
	ours = [a for a in catalogue() if a.id in (
		'location_report', 'share_location_report', 'location_report_shares')]
	assert len(ours) == 3, 'the three report actions must be in the catalogue'
	for act in ours:
		for text in (act.title, act.path, act.id):
			assert FEATURE_CODE.search(text) is None, text
		for fl in act.fields:
			assert FEATURE_CODE.search(fl.label) is None, fl.label
	read = next(a for a in ours if a.id == 'location_report')
	assert [f.name for f in read.fields] == ['subject_ref'], (
		'the report is a read; a field on it that only changes a sentence is the defect again')
