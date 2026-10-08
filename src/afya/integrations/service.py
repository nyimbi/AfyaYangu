import httpx

from afya.medicine.views import VerifyRequest, VerifyResult

BASE_CONFIG_KEYS = ['jali', 'pheoc', 'mohf', 'ppb']


class JaliClient:
	def __init__(self, base_url: str, api_key: str, client: httpx.AsyncClient) -> None:
		self._base = base_url.rstrip('/')
		self._key = api_key
		self._http = client
		assert self._base.startswith('http') and self._key, 'jali config'

	async def send_message(self, msisdn: str, body: str) -> dict[str, object]:
		resp = await self._http.post(
			f'{self._base}/v1/messages',
			json={'to': msisdn, 'text': body},
			headers={'Authorization': f'Bearer {self._key}'},
		)
		resp.raise_for_status()
		return dict(resp.json())


class PheocClient:
	def __init__(self, base_url: str, client: httpx.AsyncClient) -> None:
		self._base = base_url.rstrip('/')
		self._http = client
		assert self._base.startswith('http'), 'pheoc config'

	async def push_signal(self, payload: dict[str, int | str]) -> int:
		resp = await self._http.post(f'{self._base}/signals', json=payload)
		resp.raise_for_status()
		return int(resp.json().get('accepted', 0))


class MoHFFacilityClient:
	def __init__(self, base_url: str, client: httpx.AsyncClient) -> None:
		self._base = base_url.rstrip('/')
		self._http = client
		assert self._base.startswith('http'), 'mohf config'

	async def download_facilities(self, county: str) -> list[dict[str, object]]:
		resp = await self._http.get(f'{self._base}/facilities', params={'county': county})
		resp.raise_for_status()
		rows = resp.json()
		assert isinstance(rows, list), 'facility list payload'
		return rows


class PPBClient:
	def __init__(self, base_url: str, client: httpx.AsyncClient) -> None:
		self._base = base_url.rstrip('/')
		self._http = client
		assert self._base.startswith('http'), 'ppb config'

	async def verify(self, req: VerifyRequest) -> VerifyResult:
		resp = await self._http.get(f'{self._base}/verify', params={'gtin': req.gtin, 'batch': req.batch_number})
		if resp.status_code == 404:
			return VerifyResult(genuine=False, source='PPB', notes='batch not registered')
		resp.raise_for_status()
		data = resp.json()
		return VerifyResult(genuine=bool(data.get('genuine', False)), source='PPB')