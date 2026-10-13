"""§COM-103's "share with health authorities through a secure, encrypted channel".

The audit row said: "`ContactList.share_consent` is a flag and `summary` reports it, but nothing
transmits a list anywhere — there is no encrypted channel and no share route". The feature was a
checkbox on a form, and the form said the list had been shared.

These tests hold the three gates (consent, a non-empty list, an application-layer key), the two
honesty properties (the message distinguishes held from delivered; the ciphertext is not echoed
back), and the window §COM-103's data handling names.
"""
import json

import httpx
import pytest
from pytest_httpserver import HTTPServer

from afya.community.service import (
	CONTACT_SHARE_RECIPIENT, CONTACT_SHARE_WINDOW_DAYS, CommunityService,
)
from afya.community.views import ContactEntry, ContactList
from afya.crypto.service import CryptoService, Sealed
from afya.integrations.adam import AdamClient


def _crypto(app_layer: bool = True) -> CryptoService:
	"""A deployment with both §SEC-003 keys, or one missing the second on purpose."""
	return CryptoService(
		at_rest_key=b'a' * 32,
		app_layer_key=b'b' * 32 if app_layer else None,
	)


class RecordingAuthority:
	"""A transport that records what it was handed. Structural: it satisfies `HealthAuthorityPort`
	by having the one method, which is the point of the protocol being declared that way."""

	def __init__(self) -> None:
		self.envelopes: list[dict[str, object]] = []

	async def share_contact_list(self, envelope: dict[str, object]) -> str:
		self.envelopes.append(envelope)
		return f'ADAM-{len(self.envelopes)}'


def _listed(svc: CommunityService, subject: str = 's1', consent: bool = True,
            entries: int = 2) -> None:
	svc._contacts[subject] = ContactList(
		subject_ref=subject,
		entries=[ContactEntry(description=f'Person {i}', setting='home') for i in range(entries)],
		share_consent=consent,
	)


@pytest.fixture
async def client(httpserver: HTTPServer) -> httpx.AsyncClient:
	return httpx.AsyncClient(base_url=f'http://127.0.0.1:{httpserver.port}', timeout=5)


# --- the three gates ---------------------------------------------------------------------

async def test_a_share_needs_the_persons_consent() -> None:
	"""§COM-103: "Transmitted only with explicit consent." A share on request would make the flag
	decorative, which is the audit row's own shape."""
	svc = CommunityService(crypto=_crypto(), authority=RecordingAuthority())
	_listed(svc, consent=False)
	with pytest.raises(AssertionError, match='explicit consent'):
		await svc.share_contacts('s1')


async def test_an_empty_list_is_refused_rather_than_sent() -> None:
	"""An empty contact list arriving at the county reads as "this person had no contacts" — a
	claim about the outbreak the person never made."""
	svc = CommunityService(crypto=_crypto(), authority=RecordingAuthority())
	_listed(svc, entries=0)
	with pytest.raises(AssertionError, match='nothing to share'):
		await svc.share_contacts('s1')


async def test_a_deployment_with_no_application_layer_key_refuses_to_share() -> None:
	"""The dangerous direction. Falling back to the at-rest key would put the contacts under the key
	the operator already holds, which is the one layer §SEC-003 says is not enough for a contact
	list.

	The match is on the *service's* own wording and not on "application-layer key", because
	`CryptoService.seal` raises its own refusal with that phrase in it — so a looser match passed
	whether the service refused up front or let the seal fail underneath, which is the difference
	between a gate and a fallback that happens to trip.
	"""
	svc = CommunityService(crypto=_crypto(app_layer=False), authority=RecordingAuthority())
	_listed(svc)
	with pytest.raises(AssertionError, match='the deployment holds no application-layer key'):
		await svc.share_contacts('s1')


async def test_a_service_with_no_crypto_at_all_refuses_to_share() -> None:
	svc = CommunityService(authority=RecordingAuthority())
	_listed(svc)
	with pytest.raises(AssertionError, match='the deployment holds no application-layer key'):
		await svc.share_contacts('s1')


async def test_sharing_a_list_that_is_not_held_is_refused() -> None:
	svc = CommunityService(crypto=_crypto(), authority=RecordingAuthority())
	with pytest.raises(AssertionError, match='no contact list'):
		await svc.share_contacts('nobody')


# --- what actually travels ---------------------------------------------------------------

async def test_the_list_travels_as_ciphertext_and_opens_only_with_the_app_key() -> None:
	"""The section's "secure, encrypted channel", read as a property rather than a label: what the
	transport was handed cannot be read, and the deployment's at-rest key does not open it."""
	authority = RecordingAuthority()
	svc = CommunityService(crypto=_crypto(), authority=authority)
	_listed(svc, entries=3)
	await svc.share_contacts('s1')
	assert len(authority.envelopes) == 1
	sealed = str(authority.envelopes[0]['sealed'])
	blob = Sealed.from_blob(sealed)
	# Nothing about the people is legible in the bytes that travel. Checked against the *decoded*
	# ciphertext and not the base64 spelling of it: a two-character subject ref like 's1' occurs in
	# random base64 often enough that a substring test on the encoded form is noise, and it would
	# fail for the right reason on the wrong evidence.
	for needle in (b'Person', b'subject_ref', b'home'):
		assert needle not in blob.ciphertext, f'{needle!r} is legible in the ciphertext'
	# The at-rest key alone cannot open it — the layer travels with the value.
	assert blob.layer == 'app_layer'
	opened = _crypto().open(blob)
	body = json.loads(opened)
	assert body['subject_ref'] == 's1'
	assert [e['description'] for e in body['entries']] == ['Person 0', 'Person 1', 'Person 2']


async def test_the_at_rest_key_does_not_open_a_shared_contact_list() -> None:
	"""The same property from the other side, and the one that matters for a database dump: a
	reader holding the at-rest key and not the application key gets a failed authentication."""
	from afya.crypto.service import KEY_BYTES
	authority = RecordingAuthority()
	svc = CommunityService(crypto=_crypto(), authority=authority)
	_listed(svc)
	await svc.share_contacts('s1')
	blob = Sealed.from_blob(str(authority.envelopes[0]['sealed']))
	# A deployment that knows only the at-rest key, which is the one an operator holds.
	at_rest_only = CryptoService(at_rest_key=b'a' * KEY_BYTES)
	with pytest.raises(AssertionError, match='no app_layer key'):
		at_rest_only.open(blob)


async def test_the_receipt_does_not_echo_the_ciphertext_back() -> None:
	"""A response carrying `sealed` would put the one value worth protecting into a log, a cache and
	a client's memory for no gain — the caller produced it."""
	svc = CommunityService(crypto=_crypto(), authority=RecordingAuthority())
	_listed(svc)
	receipt = await svc.share_contacts('s1')
	dumped = receipt.model_dump(mode='json')
	assert 'sealed' not in dumped
	assert set(dumped) == {
		'share_id', 'with_who', 'entries', 'shared_at_ms', 'expires_at_ms', 'algorithm', 'message',
	}


async def test_the_share_is_kept_even_when_nothing_carried_it() -> None:
	"""A deployment with no transport still seals and keeps the list, and the receipt says held
	rather than delivered. The flattering answer is the one this closes."""
	svc = CommunityService(crypto=_crypto())
	_listed(svc)
	receipt = await svc.share_contacts('s1')
	assert 'kept on this device' in receipt.message
	# Sealed and held: the envelope is in the outbox, not lost.
	held = svc.shared_contacts('s1')
	assert len(held) == 1
	assert Sealed.from_blob(held[0].sealed).layer == 'app_layer'


async def test_a_delivered_share_says_so() -> None:
	svc = CommunityService(crypto=_crypto(), authority=RecordingAuthority())
	_listed(svc)
	receipt = await svc.share_contacts('s1')
	assert 'sent to the county' in receipt.message
	assert receipt.algorithm == 'AES-256-GCM'
	assert receipt.with_who == CONTACT_SHARE_RECIPIENT


# --- the window, and taking it back -------------------------------------------------------

async def test_the_share_expires_when_the_tracing_window_closes() -> None:
	"""§COM-103's data handling: "Deleted after the contact-tracing window closes." The window is
	read from the constant rather than typed again, so it cannot drift from §COM-102's."""
	svc = CommunityService(crypto=_crypto(), authority=RecordingAuthority())
	_listed(svc)
	receipt = await svc.share_contacts('s1', at_ms=1_000_000)
	assert CONTACT_SHARE_WINDOW_DAYS == 21
	assert receipt.expires_at_ms == 1_000_000 + 21 * 86_400_000


async def test_a_person_can_take_a_share_back() -> None:
	"""§SEC-005's right to delete at any time. A share with no lever would be a retention rule
	with nothing enforcing it."""
	svc = CommunityService(crypto=_crypto(), authority=RecordingAuthority())
	_listed(svc)
	await svc.share_contacts('s1')
	assert svc.summary('s1').shared is True
	assert svc.withdraw_shares('s1') == 1
	assert svc.shared_contacts('s1') == []
	assert svc.summary('s1').shared is False
	# Idempotent: a second withdrawal is not an error.
	assert svc.withdraw_shares('s1') == 0


async def test_the_summary_offers_the_share_before_it_is_made() -> None:
	"""The audit row's own defect: `summary.shared` read the consent flag, so a person was told
	"Shared with the health team." while nothing had been sent. Consent and delivery are now
	different answers, and this is the one in between."""
	svc = CommunityService(crypto=_crypto(), authority=RecordingAuthority())
	_listed(svc, consent=True)
	summary = await svc.save_contacts(svc._contacts['s1'])
	assert summary.shared is False
	assert 'Ready to share' in summary.message


# --- through the real transport ------------------------------------------------------------

async def test_the_share_travels_the_adam_wire(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	"""§18.1's ADaM leg, exercised over a real request rather than a stub."""
	httpserver.expect_request('/contact-lists', method='POST').respond_with_json({'share_ref': 'ADAM-9'})
	adam = AdamClient(httpserver.url_for('/'), client)
	svc = CommunityService(crypto=_crypto(), authority=adam)
	_listed(svc)
	receipt = await svc.share_contacts('s1')
	assert receipt.share_id.startswith('CSH-')
	# The wire carried an envelope, and what was in it was ciphertext.
	body = json.loads(httpserver.log[0][0].get_data())
	assert Sealed.from_blob(body['sealed']).layer == 'app_layer'
	assert body['with_who'] == CONTACT_SHARE_RECIPIENT


async def test_adam_refuses_a_contact_list_that_was_not_sealed(
	client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	"""A caller that skipped the seal is refused at the client, which is the last cheap place to
	say so. No server expectation is registered — a request that got through would fail anyway."""
	adam = AdamClient(httpserver.url_for('/'), client)
	with pytest.raises(AssertionError, match='sealed'):
		await adam.share_contact_list({'subject_ref': 's1', 'with_who': 'County Team'})


async def test_the_route_serves_the_share_for_a_signed_in_person(monkeypatch: pytest.MonkeyPatch) -> None:
	"""A green unit test says nothing about the front door. This drives the route itself.

	The deployment is built with `build_services()` so the composition root is the thing under test
	— a service taking a crypto argument proves nothing about whether production passes one. The
	application-layer key comes from the environment, which is where §SEC-003 says it lives, so the
	test sets it rather than reaching into the service.
	"""
	from afya.service import build_services, create_app
	monkeypatch.setenv('AFYA_APP_LAYER_KEY', 'b' * 64)
	monkeypatch.setenv('AFYA_AT_REST_KEY', 'a' * 64)
	# No ADaM vendor is configured in a test, so the composition root's client would post to the
	# real national URL. Point it at a dead local port instead: the share is sealed and kept either
	# way, and a route test that reached the internet would be a route test that depends on it.
	monkeypatch.setenv('ADAM_URL', 'http://127.0.0.1:9/api')
	svc = build_services()
	app = create_app(svc)
	community: CommunityService = svc['community']  # type: ignore[assignment]
	_listed(community, subject='route-1')
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers = await _citizen(c, 'route-1')
		posted = await c.post('/community/contacts/route-1/share', headers=headers)
		assert posted.status_code == 200, posted.text
		body = posted.json()
		# The ciphertext is not echoed back, and the receipt names the recipient.
		assert 'sealed' not in body
		assert body['entries'] == 2
		# And the share is real: the service holds an envelope sealed under the app-layer key.
		held = community.shared_contacts('route-1')
		assert len(held) == 1
		assert Sealed.from_blob(held[0].sealed).layer == 'app_layer'
		# The dashboard route serves it, still without the ciphertext.
		listed = await c.get('/community/contacts/route-1/shares', headers=headers)
		assert listed.status_code == 200, listed.text
		assert len(listed.json()) == 1
		assert 'sealed' not in listed.json()[0]
		# And §SEC-006's inventory — the dashboard a person actually reads — knows about it.
		inventory = await c.get('/retention/inventory/route-1', headers=headers)
		assert inventory.status_code == 200, inventory.text
		shares = inventory.json()['shared_with']
		assert len(shares) == 1, 'the share did not reach the in-app data dashboard'
		assert shares[0]['with'] == CONTACT_SHARE_RECIPIENT
		assert 'contact list (2 people)' == shares[0]['what']


async def test_the_route_refuses_a_share_without_consent() -> None:
	from afya.service import build_services, create_app
	svc = build_services()
	app = create_app(svc)
	community: CommunityService = svc['community']  # type: ignore[assignment]
	_listed(community, subject='route-2', consent=False)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers = await _citizen(c, 'route-2')
		posted = await c.post('/community/contacts/route-2/share', headers=headers)
	assert posted.status_code == 422, posted.text
	assert 'consent' in posted.json()['detail']


async def _citizen(c: httpx.AsyncClient, subject: str) -> dict[str, str]:
	"""A citizen token naming `subject`, through §SEC-004's no-account path.

	`/community/contacts/*` is `require_self`, which binds the path's `subject_ref` to the token's
	own — so the token has to name the subject the test uses, and an anonymous token minted without
	one would be testing the 403 path and calling it the feature. The PKCE flow is for staff and
	workers (`citizen_anonymous` is not issued through the app), so this is the route.
	"""
	anon = await c.post('/auth/anonymous', json={'subject_ref': subject})
	assert anon.status_code == 200, anon.text
	return {'Authorization': f"Bearer {anon.json()['token']}"}


def test_no_spec_feature_code_reaches_a_shared_field() -> None:
	"""The user's standing constraint: spec ids are backend identifiers and must not surface."""
	import re
	from afya.mobile.actions import catalogue
	FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')
	ours = [a for a in catalogue() if a.id in (
		'share_contacts', 'contact_shares', 'withdraw_contact_shares')]
	assert len(ours) == 3, 'the three share actions must be in the catalogue'
	for act in ours:
		assert FEATURE_CODE.search(act.title) is None
		assert FEATURE_CODE.search(act.path) is None
		assert FEATURE_CODE.search(act.id) is None
		for fl in act.fields:
			assert FEATURE_CODE.search(fl.label) is None
