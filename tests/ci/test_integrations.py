import pytest
from pytest_httpserver import HTTPServer

from afya.integrations.service import JaliClient, MoHFFacilityClient, PPBClient, PheocClient
from afya.medicine.views import VerifyRequest
import httpx


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


async def test_ppb_verify_paths(client: httpx.AsyncClient, httpserver: HTTPServer) -> None:
	ppb = PPBClient(httpserver.url_for('/'), client)
	httpserver.expect_request('/verify', query_string={'gtin': '0123456789012', 'batch': 'B123'}, method='GET').respond_with_json({'genuine': True})
	httpserver.expect_request('/verify', query_string={'gtin': '0123456789019', 'batch': 'B999'}, method='GET').respond_with_json({'error': 'not found'}, status=404)
	ok = await ppb.verify(VerifyRequest(batch_number='B123', gtin='0123456789012'))
	assert ok.genuine and ok.source == 'PPB'
	bad = await ppb.verify(VerifyRequest(batch_number='B999', gtin='0123456789019'))
	assert not bad.genuine and 'not registered' in (bad.notes or '')