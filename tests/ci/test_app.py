import httpx
import pytest

from afya.service import create_app


@pytest.fixture
async def client() -> httpx.AsyncClient:
	transport = httpx.ASGITransport(app=create_app())
	return httpx.AsyncClient(transport=transport, base_url='http://testserver')


async def test_health(client: httpx.AsyncClient) -> None:
	out = (await client.get('/health')).json()
	assert out['status'] == 'ok' and out['version'] == '2.0.0' and out['tier4'] is False


async def test_features_exclude_dormant_tier4(client: httpx.AsyncClient) -> None:
	ids = [f['id'] for f in (await client.get('/features')).json()]
	assert 'TRI-001' in ids and 'TRI-003' not in ids


async def test_triage_preliminary_malaria_trap(client: httpx.AsyncClient) -> None:
	resp = (await client.post('/triage/preliminary', json={'symptoms': ['fever'], 'temperature_c': 38.8})).json()
	assert resp['risk_level'] == 'malaria_suspect'
	contact = (await client.post('/triage/preliminary', json={'symptoms': ['fever'], 'temperature_c': 38.2, 'ebola_contact': True})).json()
	assert contact['risk_level'] != 'malaria_suspect' or contact['escalate_719']


async def test_triage_evd_forbidden_when_dormant(client: httpx.AsyncClient) -> None:
	assert (await client.post('/triage/evd', json={'symptoms': ['fever'], 'temperature_c': 39.0})).status_code == 403


async def test_tier4_activation_gate(client: httpx.AsyncClient) -> None:
	denied = (await client.post('/tier4/activate', json={'authorized_by_pheoc': False, 'dpia_reviewed': True, 'flag_enabled': True})).json()
	assert denied == {'activated': False}
	granted = (await client.post('/tier4/activate', json={'authorized_by_pheoc': True, 'dpia_reviewed': True, 'flag_enabled': True})).json()
	assert granted == {'activated': True}
	assert (await client.get('/health')).json()['tier4'] is True