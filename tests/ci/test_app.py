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
	assert contact['risk_level'] == 'high' and contact['escalate_719']


async def test_triage_evd_forbidden_when_dormant(client: httpx.AsyncClient) -> None:
	assert (await client.post('/triage/evd', json={'symptoms': ['fever'], 'temperature_c': 39.0})).status_code == 403


async def test_facility_nearest_and_status(client: httpx.AsyncClient) -> None:
	await client.post('/facilities', json={'facility_id': 'F1', 'name': 'KNH', 'kind': 'ed', 'county': 'Nairobi', 'lat': -1.3, 'lon': 36.8, 'ed_status': 'operational'})
	out = (await client.post('/facilities/nearest', json={'lat': -1.29, 'lon': 36.8, 'kind': 'ed', 'limit': 1})).json()
	assert out[0]['facility']['facility_id'] == 'F1'
	st = (await client.get('/facilities/F1/ed-status')).json()
	assert st['status'] == 'operational'
	assert (await client.post('/facilities/F1/booking', json={'booking_id': 'BOOK-A1B2C3D4', 'facility_id': 'F1', 'slot_iso': '2026-10-09T10:00+03:00', 'queue_position': 1})).json()['queue_position'] == 1


async def test_medicine_endpoints(client: httpx.AsyncClient) -> None:
	out = (await client.post('/medicine/interactions', json={'drugs': ['warfarin', 'aspirin']})).json()
	assert 'MAJOR' in out[0]
	dose = (await client.post('/medicine/dose', json={'drug': 'paracetamol', 'weight_kg': 20.0, 'mg_per_kg': 15.0})).json()
	assert dose['total_mg'] == 300.0


async def test_sos_endpoint(client: httpx.AsyncClient) -> None:
	out = (await client.post('/emergency/sos', json={'sos_id': 'SOS-AAA111BBB', 'lat': -1.3, 'lon': 36.8, 'severity': 'high', 'symptoms': ['fever']})).json()
	assert '719-hotline' in out['notified']


async def test_whatsapp_and_ussd_endpoints(client: httpx.AsyncClient) -> None:
	wa = (await client.post('/channels/whatsapp', json={'from_msisdn': '+254711222333', 'body': 'find facility'})).json()
	assert 'nearest facility' in wa['reply']
	ussd = (await client.post('/channels/ussd', json={'session_id': 's1', 'msisdn': '+254711222333', 'text': ''})).json()
	assert ussd['menu'].startswith('CON Afya Yangu')
	sms = (await client.post('/channels/sms?to_msisdn=%2B254711222333&body=Call%20719')).json()
	assert sms['segments'] == 1


async def test_sync_endpoints(client: httpx.AsyncClient) -> None:
	op = {'op_id': 'OP-AAA111222', 'dataset': 'symptom_logs', 'client_ts': 100, 'server_version': 0, 'payload': {}}
	assert (await client.post('/sync/ops', json=op)).json() == {'queued': True}
	flushed = (await client.post('/sync/flush')).json()
	assert flushed['synced'] == 1
	assert (await client.post('/sync/ops', json={**op, 'op_id': 'OP-BBB222333', 'dataset': 'nope'})).status_code == 422


async def test_records_and_privacy_endpoints(client: httpx.AsyncClient) -> None:
	mem = {'member_ref': 'M1', 'dob_iso': '2015-01-01', 'guardian_ref': 'G1'}
	assert (await client.post('/records/member', json=mem)).json() == {'ok': True}
	assert (await client.post('/records/member', json={'member_ref': 'KID', 'dob_iso': '2015-01-01'})).status_code == 400
	gaps = (await client.get('/records/M1/immunisation-gaps')).json()
	assert 'BCG dose 1' in gaps
	dpia = (await client.post('/privacy/dpia', json={'raw_sensor_data_retained': True})).json()
	assert dpia['blocked'] is True


async def test_tier4_activation_gate(client: httpx.AsyncClient) -> None:
	denied = (await client.post('/tier4/activate', json={'authorized_by_pheoc': False, 'dpia_reviewed': True, 'flag_enabled': True})).json()
	assert denied == {'activated': False}
	granted = (await client.post('/tier4/activate', json={'authorized_by_pheoc': True, 'dpia_reviewed': True, 'flag_enabled': True})).json()
	assert granted == {'activated': True}
	assert (await client.get('/health')).json()['tier4'] is True
	assert (await client.post('/triage/evd', json={'symptoms': ['fever'], 'temperature_c': 39.2, 'ebola_contact': True})).json()['risk_level'] == 'high'