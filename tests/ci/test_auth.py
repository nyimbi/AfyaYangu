"""Behavioural tests for afya.auth (§15.5, §17).

The security properties matter more than the happy path, so most of what follows asserts a refusal:
a redeemed code, a wrong verifier, an unissued role, a mismatched idempotency body, a rate-limited
device. Each is a way an attacker or a buggy client would otherwise get through.
"""
import secrets

import httpx
import pytest
from pydantic import ValidationError

from afya.auth.service import AuthService
from afya.auth.views import (
	ACCESS_TOKEN_TTL_SECONDS, PKCEStart, PKCETokenRequest, RateLimitDecision, fingerprint, s256,
	verify_pkce,
)
from afya.privacy.views import RBACRole
from afya.service import create_app

VERIFIER = secrets.token_urlsafe(64)[:64]


def _start(svc: AuthService, client_id: str = 'chw-app') -> str:
	return svc.start_pkce(PKCEStart(
		client_id=client_id, redirect_uri='afya://cb', code_challenge=s256(VERIFIER), state='state-1234',
	)).authorization_code


def _exchange(svc: AuthService, code: str, role: RBACRole = RBACRole.chw, client_id: str = 'chw-app'):  # type: ignore[no-untyped-def]
	return svc.exchange_pkce(PKCETokenRequest(
		authorization_code=code, client_id=client_id, redirect_uri='afya://cb', code_verifier=VERIFIER,
	), role)


# --- PKCE ----------------------------------------------------------------------------------

def test_s256_is_base64url_without_padding() -> None:
	# RFC 7636 appendix B test vector.
	assert s256('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk') == 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM'


def test_verify_pkce_rejects_a_different_verifier() -> None:
	assert verify_pkce(VERIFIER, s256(VERIFIER)) is True
	assert verify_pkce(VERIFIER + 'x', s256(VERIFIER)) is False


def test_pkce_start_refuses_plain_challenge_method() -> None:
	svc = AuthService()
	with pytest.raises(ValidationError):
		PKCEStart(client_id='c', redirect_uri='afya://cb', code_challenge=s256(VERIFIER),
			code_challenge_method='plain', state='state-1234')


def test_exchange_issues_a_scoped_worker_token() -> None:
	svc = AuthService()
	token = _exchange(svc, _start(svc))
	assert token.role == 'chw'
	assert token.scopes == ['assigned', 'community_aggregate']
	assert token.expires_in == ACCESS_TOKEN_TTL_SECONDS
	assert svc.resolve_worker(token.access_token).role == 'chw'


def test_authorization_code_is_single_use() -> None:
	svc = AuthService()
	code = _start(svc)
	_exchange(svc, code)
	with pytest.raises(AssertionError, match='already redeemed'):
		_exchange(svc, code)


def test_exchange_refuses_a_verifier_that_does_not_match_the_challenge() -> None:
	svc = AuthService()
	code = _start(svc)
	with pytest.raises(AssertionError, match='verifier does not match'):
		svc.exchange_pkce(PKCETokenRequest(
			authorization_code=code, client_id='chw-app', redirect_uri='afya://cb',
			code_verifier=secrets.token_urlsafe(64)[:64],
		), RBACRole.chw)


def test_exchange_refuses_a_different_client_or_redirect() -> None:
	svc = AuthService()
	with pytest.raises(AssertionError, match='different client'):
		_exchange(svc, _start(svc, client_id='chw-app'), client_id='someone-else')
	svc2 = AuthService()
	code = svc2.start_pkce(PKCEStart(client_id='c', redirect_uri='afya://one', code_challenge=s256(VERIFIER), state='state-1234')).authorization_code
	with pytest.raises(AssertionError, match='redirect_uri'):
		svc2.exchange_pkce(PKCETokenRequest(
			authorization_code=code, client_id='c', redirect_uri='afya://two', code_verifier=VERIFIER,
		), RBACRole.chw)


def test_exchange_refuses_operational_roles() -> None:
	"""sysadmin and auditor are provisioned operationally; the app must not hand them out."""
	svc = AuthService()
	for role in (RBACRole.sysadmin, RBACRole.auditor):
		with pytest.raises(AssertionError, match='not issued through the app'):
			_exchange(svc, _start(svc), role=role)


def test_exchange_refuses_an_unknown_code() -> None:
	svc = AuthService()
	with pytest.raises(AssertionError, match='unknown authorization code'):
		_exchange(svc, 'not-a-real-code')


# --- anonymous tokens ----------------------------------------------------------------------

async def test_anonymous_token_is_opaque_and_subject_bound() -> None:
	svc = AuthService()
	token = await svc.issue_anonymous()
	assert len(token.token) >= 32, 'token must carry real entropy'
	assert svc.resolve_anonymous(token.token).subject_ref == token.subject_ref
	assert token.subject_ref.startswith('anon-'), 'a fresh anonymous subject is assigned, not supplied'


async def test_anonymous_token_carries_no_personal_data() -> None:
	"""The token string must not encode the subject, or a leaked token leaks its holder."""
	svc = AuthService()
	token = await svc.issue_anonymous()
	assert token.subject_ref not in token.token


def test_unknown_anonymous_token_is_refused() -> None:
	with pytest.raises(AssertionError, match='unknown or revoked'):
		AuthService().resolve_anonymous('nope')


async def test_revoked_token_stops_resolving() -> None:
	svc = AuthService()
	token = await svc.issue_anonymous()
	assert await svc.revoke(token.token) == 1
	with pytest.raises(AssertionError):
		svc.resolve_anonymous(token.token)


# --- idempotency ---------------------------------------------------------------------------

def test_same_key_and_body_replays_the_first_response() -> None:
	svc = AuthService()
	svc.store('k1', '{"a": 1}', {'ok': True}, 201)
	rec = svc.replay('k1', '{"a": 1}')
	assert rec is not None and rec.response == {'ok': True} and rec.status_code == 201


def test_same_key_with_a_different_body_is_refused() -> None:
	"""Returning the earlier response here would silently drop a real write."""
	svc = AuthService()
	svc.store('k1', '{"a": 1}', {'ok': True}, 200)
	with pytest.raises(AssertionError, match='different request body'):
		svc.replay('k1', '{"a": 2}')


def test_unseen_key_is_not_a_replay() -> None:
	assert AuthService().replay('never-used', '{}') is None


def test_purge_drops_expired_keys() -> None:
	svc = AuthService()
	svc.store('old', '{}', {'ok': True}, 200)
	svc._idempotency['old'].stored_at_ms = 0
	assert svc.purge_expired_keys() == 1
	assert svc.replay('old', '{}') is None


def test_fingerprint_distinguishes_whitespace() -> None:
	assert fingerprint('{"a":1}') != fingerprint('{"a": 1}')


# --- rate limiting -------------------------------------------------------------------------

def test_rate_limit_allows_a_burst_then_refuses() -> None:
	svc = AuthService()
	decisions = [svc.check_rate('dev-1', at_ms=1_000 + i) for i in range(200)]
	assert decisions[0].allowed is True
	assert decisions[-1].allowed is False
	last = decisions[-1]
	assert isinstance(last, RateLimitDecision) and last.retry_after_seconds == 60 and last.remaining == 0


def test_rate_limit_is_per_device() -> None:
	"""One noisy client must not consume a neighbour's budget."""
	svc = AuthService()
	for i in range(200):
		svc.check_rate('noisy', at_ms=1_000 + i)
	assert svc.check_rate('quiet', at_ms=2_000).allowed is True


def test_rate_limit_window_slides() -> None:
	svc = AuthService()
	for i in range(200):
		svc.check_rate('dev-1', at_ms=1_000 + i)
	# A minute later the earlier hits have aged out of the window.
	assert svc.check_rate('dev-1', at_ms=1_000 + 200 + 61_000).allowed is True


def test_rate_limit_requires_a_device_id() -> None:
	with pytest.raises(AssertionError, match='per device'):
		AuthService().check_rate('')


# --- HTTP surface and enforcement ----------------------------------------------------------

@pytest.fixture
async def client() -> httpx.AsyncClient:
	transport = httpx.ASGITransport(app=create_app())
	return httpx.AsyncClient(transport=transport, base_url='http://testserver')


async def _worker(client: httpx.AsyncClient, role: str = 'chw') -> str:
	authz = (await client.post('/auth/pkce/authorize', json={
		'client_id': 'app', 'redirect_uri': 'afya://cb', 'code_challenge': s256(VERIFIER), 'state': 'state-1234',
	})).json()
	out = (await client.post('/auth/pkce/token', params={'role': role}, json={
		'authorization_code': authz['authorization_code'], 'client_id': 'app',
		'redirect_uri': 'afya://cb', 'code_verifier': VERIFIER,
	})).json()
	return str(out['access_token'])


async def test_whoami_requires_a_token(client: httpx.AsyncClient) -> None:
	assert (await client.get('/auth/whoami')).status_code == 401
	assert (await client.get('/auth/whoami', headers={'Authorization': 'Bearer nonsense'})).status_code == 401


async def test_anonymous_flow_over_http(client: httpx.AsyncClient) -> None:
	token = (await client.post('/auth/anonymous', json={})).json()
	me = (await client.get('/auth/whoami', headers={'Authorization': f'Bearer {token["token"]}'})).json()
	assert me['role'] == 'citizen_anonymous' and me['subject_ref'] == token['subject_ref']


async def test_case_reporting_requires_a_worker_token(client: httpx.AsyncClient) -> None:
	"""A citizen token may not file a case report: it is a CHW-assigned action (§17 RBAC)."""
	case = {'report_id': 'CR-ABCD1234', 'chw_ref': 'chw-1', 'county': 'Busia', 'community': 'Budalangi', 'symptoms': ['fever']}
	assert (await client.post('/community/cases', json=case)).status_code == 401
	anon = (await client.post('/auth/anonymous', json={})).json()['token']
	assert (await client.post('/community/cases', json=case, headers={'Authorization': f'Bearer {anon}'})).status_code == 403
	chw = await _worker(client, 'chw')
	assert (await client.post('/community/cases', json=case, headers={'Authorization': f'Bearer {chw}'})).status_code == 200


async def test_aggregate_analytics_are_not_readable_by_a_chw(client: httpx.AsyncClient) -> None:
	cells = [{'cell_id': 'c1', 'county': 'Busia', 'population': 1000, 'fever_reports': 50, 'cough_events': 0, 'encounter_density': 0.1, 'facility_reports': 3}]
	chw = await _worker(client, 'chw')
	assert (await client.post('/ai/hotspots', json=cells, headers={'Authorization': f'Bearer {chw}'})).status_code == 403
	officer = await _worker(client, 'county_officer')
	assert (await client.post('/ai/hotspots', json=cells, headers={'Authorization': f'Bearer {officer}'})).status_code == 200


async def test_idempotency_key_replays_over_http(client: httpx.AsyncClient) -> None:
	body = {'facility_id': 'F9', 'name': 'Test', 'kind': 'ed', 'county': 'Nairobi', 'lat': -1.3, 'lon': 36.8, 'ed_status': 'operational'}
	headers = {'Idempotency-Key': 'idem-http-1'}
	first = await client.post('/facilities', json=body, headers=headers)
	second = await client.post('/facilities', json=body, headers=headers)
	assert first.status_code == second.status_code == 200
	assert first.text == second.text, 'the first response is replayed verbatim'


async def test_idempotency_key_reuse_with_new_body_is_a_conflict(client: httpx.AsyncClient) -> None:
	body = {'facility_id': 'F9', 'name': 'Test', 'kind': 'ed', 'county': 'Nairobi', 'lat': -1.3, 'lon': 36.8, 'ed_status': 'operational'}
	headers = {'Idempotency-Key': 'idem-http-2'}
	await client.post('/facilities', json=body, headers=headers)
	changed = {**body, 'name': 'Different'}
	assert (await client.post('/facilities', json=changed, headers=headers)).status_code == 409


async def test_rate_limit_returns_429_with_retry_after(client: httpx.AsyncClient) -> None:
	headers = {'X-Device-Id': 'flood-device'}
	codes = [(await client.get('/health', headers=headers)).status_code for _ in range(170)]
	assert 200 in codes and 429 in codes
	assert codes.index(429) > 100, 'the burst allowance must absorb normal retries'
	limited = await client.get('/health', headers=headers)
	assert limited.headers['retry-after'] == '60'


async def test_other_devices_are_unaffected_by_a_flood(client: httpx.AsyncClient) -> None:
	for _ in range(170):
		await client.get('/health', headers={'X-Device-Id': 'flood-device-2'})
	assert (await client.get('/health', headers={'X-Device-Id': 'innocent'})).status_code == 200
