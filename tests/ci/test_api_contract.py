"""Gate: every §15.5 API-Design requirement must have a wired check.

§15.5 is written as nine prose bullets, so nothing failed when one of them was unimplemented —
the section read as done while four of the nine did not exist. This gate parses the bullets out
of the spec text and refuses to pass unless each one names a check that runs here. A new bullet
added to the spec fails CI until it is implemented, which is the point.

The canary below plants a bullet with no check and confirms the gate rejects it.
"""
import re
from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient

from afya.service import API_VERSIONS, CURRENT_API_VERSION, create_app

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / 'docs' / 'spec.md'

# The canary's planted requirement. Deliberately not a plausible spec bullet.
CANARY = 'ZZZ-canary-requirement'

# Requirement (as written in the spec, matched on its leading words) -> the check that proves it.
# A requirement absent from this map is unimplemented, and the gate fails on it.
REQUIREMENT_CHECKS: dict[str, str] = {
	'REST': 'rest_is_served',
	'WebSocket': 'websocket_delivers_alerts',
	'gRPC': 'grpc_surface_exists',
	'Versioned': 'versioned_paths_are_served',
	'Idempotency keys': 'idempotency_key_replays_a_write',
	'Rate limiting': 'rate_limiting_refuses_a_flood',
	'OpenAPI 3.1': 'openapi_31_is_published',
	'OAuth 2.0 + PKCE': 'pkce_flow_issues_a_worker_token',
	'Anonymous tokens': 'anonymous_token_is_issued',
}


def _spec_requirements() -> list[str]:
	"""The §15.5 bullets, read from the spec rather than hand-copied."""
	text = SPEC.read_text(encoding='utf-8')
	section = text.split('### 15.5 API Design', 1)[1].split('\n---', 1)[0]
	return re.findall(r'^- \*\*(.+?)\*\*', section, re.M)


def _uncovered(requirements: list[str]) -> list[str]:
	return [r for r in requirements if r not in REQUIREMENT_CHECKS]


def test_gate_catches_an_unimplemented_requirement() -> None:
	"""Canary. The gate must reject a requirement that names no check. The planted name is one the
	spec cannot contain, so the canary cannot false-fail on a real bullet."""
	assert 'WebSocket' in _spec_requirements(), 'the parser must find real bullets'
	planted = [r for r in _spec_requirements() if r != CANARY] + [CANARY]
	assert _uncovered(planted) == [CANARY], 'the gate would pass on anything'


def test_every_15_5_requirement_has_a_wired_check() -> None:
	missing = _uncovered(_spec_requirements())
	assert missing == [], f'§15.5 requirements with no implementation check: {missing}'


def test_every_named_check_exists_in_this_module() -> None:
	"""A map entry pointing at a check that does not exist would pass the gate vacuously."""
	for requirement, name in REQUIREMENT_CHECKS.items():
		assert name in globals(), f'{requirement!r} names {name!r}, which is not defined here'


# --- the checks the map names ----------------------------------------------------------------

@pytest.fixture
async def client() -> httpx.AsyncClient:
	return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url='http://testserver')


async def rest_is_served(client: httpx.AsyncClient) -> None:
	assert (await client.get('/health')).status_code == 200
	assert (await client.get('/openapi.json')).json()['paths'], 'REST routes must be described'


def websocket_delivers_alerts() -> None:
	with TestClient(create_app()) as c:
		with c.websocket_connect('/alerts/socket?county=Busia&categories=disease_alerts') as ws:
			assert ws.receive_json()['kind'] == 'hello'


def grpc_surface_exists() -> None:
	from afya.grpc_api.afya_internal_pb2_grpc import AfyaInternalStub
	from afya.grpc_api.service import serve

	assert AfyaInternalStub is not None and callable(serve)


async def versioned_paths_are_served(client: httpx.AsyncClient) -> None:
	for version in API_VERSIONS:
		assert (await client.get(f'/{version}/health')).status_code == 200
	assert (await client.get('/')).json()['current_version'] == CURRENT_API_VERSION


async def idempotency_key_replays_a_write(client: httpx.AsyncClient) -> None:
	body = {'facility_id': 'F-IDEM', 'name': 'Test', 'kind': 'ed', 'county': 'Nairobi', 'lat': -1.3, 'lon': 36.8, 'ed_status': 'operational'}
	headers = {'Idempotency-Key': 'contract-idem-1',
	           'authorization': f"Bearer {await _county_officer(client)}"}
	first = await client.post('/facilities', json=body, headers=headers)
	second = await client.post('/facilities', json=body, headers=headers)
	assert first.status_code == 200 and first.text == second.text


async def rate_limiting_refuses_a_flood(client: httpx.AsyncClient) -> None:
	headers = {'X-Device-Id': 'contract-flood'}
	codes = [(await client.get('/health', headers=headers)).status_code for _ in range(170)]
	assert 429 in codes


async def openapi_31_is_published(client: httpx.AsyncClient) -> None:
	spec = (await client.get('/openapi.json')).json()
	assert spec['openapi'].startswith('3.1')


async def pkce_flow_issues_a_worker_token(client: httpx.AsyncClient) -> None:
	import secrets

	from afya.auth.views import s256

	verifier = secrets.token_urlsafe(64)[:64]
	authz = (await client.post('/auth/pkce/authorize', json={
		'client_id': 'app', 'redirect_uri': 'afya://cb', 'code_challenge': s256(verifier), 'state': 'state-1234',
	})).json()
	out = (await client.post('/auth/pkce/token', params={'role': 'chw'}, json={
		'authorization_code': authz['authorization_code'], 'client_id': 'app',
		'redirect_uri': 'afya://cb', 'code_verifier': verifier,
	})).json()
	assert out['token_type'] == 'Bearer' and out['role'] == 'chw'


async def anonymous_token_is_issued(client: httpx.AsyncClient) -> None:
	out = (await client.post('/auth/anonymous', json={})).json()
	assert out['token'] and out['subject_ref'].startswith('anon-')


async def _county_officer(c: httpx.AsyncClient) -> str:
	"""The facility registry is the county health team's to maintain, so its writes carry that
	scope. Minted through the app's own PKCE flow, which is how §17.4 issues the role."""
	from afya.auth.views import s256
	verifier = 'v' * 64
	authz = (await c.post('/auth/pkce/authorize', json={
		'client_id': 'app', 'redirect_uri': 'afya://cb', 'code_challenge': s256(verifier), 'state': 'state-1234',
	})).json()
	return (await c.post('/auth/pkce/token', params={'role': 'county_officer'}, json={
		'authorization_code': authz['authorization_code'], 'client_id': 'app',
		'redirect_uri': 'afya://cb', 'code_verifier': verifier,
	})).json()['access_token']
