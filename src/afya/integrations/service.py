"""Outbound clients for the national systems the app has to talk to (§18.1–18.8).

Each client is a thin adapter over one vendor's documented surface: it asserts the request shape,
raises on a non-2xx, and returns a typed or plain-python result. No client holds state that matters
across calls, so a client can be constructed per request without cost.

The `*_PORT` protocols exist so a service can be handed the inline fallback instead — an offline
deployment degrades to a stub that never fabricates a positive answer, rather than to an exception.
"""
from typing import Any, Protocol

import httpx

from afya.medicine.views import VerifyRequest, VerifyResult

BASE_CONFIG_KEYS = ['jali', 'pheoc', 'mohf', 'ppb', 'adam', 'sha']


class JaliClient:
	"""§18.2 JALI chatbot. The app is the client; JALI holds the conversation."""

	def __init__(self, base_url: str, api_key: str, client: httpx.AsyncClient) -> None:
		self._base = base_url.rstrip('/')
		self._key = api_key
		self._http = client
		assert self._base.startswith('http') and self._key, 'jali config'

	def _headers(self) -> dict[str, str]:
		return {'Authorization': f'Bearer {self._key}', 'accept': 'application/json'}

	async def send_message(self, msisdn: str, body: str) -> dict[str, object]:
		resp = await self._http.post(f'{self._base}/v1/messages', json={'to': msisdn, 'text': body}, headers=self._headers())
		resp.raise_for_status()
		return dict(resp.json())

	async def launch_link(self, context: str, subject_ref: str) -> str:
		"""App → JALI, on demand: a deep link carrying the context the chatbot needs to continue.

		The link carries a pseudonym, never a phone number: JALI already knows the subscriber, and a
		context string that repeats the identity would put a raw identifier in a URL that gets logged
		by every hop between here and there.
		"""
		assert context and subject_ref, 'a launch link needs its context and subject'
		resp = await self._http.post(f'{self._base}/v1/links', json={'context': context, 'subject_ref': subject_ref}, headers=self._headers())
		resp.raise_for_status()
		return str(resp.json()['url'])

	async def corrections(self, since_iso: str) -> list[dict[str, object]]:
		"""JALI → App, on publish. The app caches these so a correction is available offline."""
		resp = await self._http.get(f'{self._base}/v1/corrections', params={'since': since_iso}, headers=self._headers())
		resp.raise_for_status()
		rows = resp.json()
		assert isinstance(rows, list), 'correction payload must be a list'
		return [dict(r) for r in rows]

	async def share_assessment(self, summary: dict[str, object]) -> bool:
		"""App → JALI, on request, consented only. Same consent rule as the ADaM summary, for the same
		reason: a summary pushed without the flag is a disclosure nobody agreed to."""
		assert summary.get('consented') is True, 'assessments are shared only with consent'
		resp = await self._http.post(f'{self._base}/v1/assessments', json=summary, headers=self._headers())
		resp.raise_for_status()
		return resp.status_code < 300

	async def clinician_response(self, assessment_id: str) -> dict[str, object] | None:
		"""JALI → App, on review. `None` while a human has not yet answered, which is not an error."""
		resp = await self._http.get(f'{self._base}/v1/assessments/{assessment_id}/review', headers=self._headers())
		if resp.status_code == 404:
			return None
		resp.raise_for_status()
		return dict(resp.json())


class PheocClient:
	"""§18.3 PHEOC dashboards. Feeds are built by `afya.integrations.feeds`; this only ships them."""

	def __init__(self, base_url: str, client: httpx.AsyncClient, api_key: str = '') -> None:
		self._base = base_url.rstrip('/')
		self._http = client
		self._key = api_key
		assert self._base.startswith('http'), 'pheoc config'

	def _headers(self) -> dict[str, str]:
		out = {'accept': 'application/json'}
		if self._key:
			out['Authorization'] = f'Bearer {self._key}'
		return out

	async def push_signal(self, payload: dict[str, int | str]) -> int:
		resp = await self._http.post(f'{self._base}/signals', json=payload, headers=self._headers())
		resp.raise_for_status()
		return int(resp.json().get('accepted', 0))

	async def push_feed(self, feed: str, rows: list[dict[str, Any]]) -> int:
		"""Push one of the six §18.3 feeds. Refuses an unknown feed name rather than posting to a
		path PHEOC does not serve, and refuses an empty batch so a quiet hour is not read as a
		failed sync."""
		from afya.integrations.feeds import FEED_GRANULARITY
		assert feed in FEED_GRANULARITY, f'unknown PHEOC feed {feed}'
		assert rows, 'refusing to push an empty feed'
		resp = await self._http.post(f'{self._base}/feeds/{feed}', json={'rows': rows, 'granularity': FEED_GRANULARITY[feed]}, headers=self._headers())
		resp.raise_for_status()
		return int(resp.json().get('accepted', len(rows)))


class MoHFFacilityClient:
	"""§18.5 Kenya Master Health Facility List."""

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

	async def report_correction(self, correction: dict[str, object]) -> str:
		"""App → MoHF, on report: a crowdsourced correction. Returns the registry's ticket id."""
		assert correction.get('facility_id') and correction.get('field'), 'a correction needs a facility and a field'
		resp = await self._http.post(f'{self._base}/corrections', json=correction)
		resp.raise_for_status()
		return str(resp.json().get('ticket', ''))

	async def verification_status(self, facility_ids: list[str]) -> dict[str, str]:
		"""MoHF → App, weekly. A facility that lost verification must stop being recommended."""
		assert facility_ids, 'verification needs at least one facility'
		resp = await self._http.get(f'{self._base}/verification', params={'ids': ','.join(facility_ids)})
		resp.raise_for_status()
		data = resp.json()
		assert isinstance(data, dict), 'verification payload must be a mapping'
		return {str(k): str(v) for k, v in data.items()}


class PPBClient:
	"""§18.7 Pharmacy and Poisons Board."""

	def __init__(self, base_url: str, client: httpx.AsyncClient, api_key: str = '') -> None:
		self._base = base_url.rstrip('/')
		self._http = client
		self._key = api_key
		assert self._base.startswith('http'), 'ppb config'

	def _headers(self) -> dict[str, str]:
		out = {'accept': 'application/json'}
		if self._key:
			out['Authorization'] = f'Bearer {self._key}'
		return out

	async def verify(self, req: VerifyRequest) -> VerifyResult:
		resp = await self._http.get(f'{self._base}/verify', params={'gtin': req.gtin, 'batch': req.batch_number}, headers=self._headers())
		if resp.status_code == 404:
			return VerifyResult(genuine=False, source='PPB', notes='batch not registered')
		resp.raise_for_status()
		data = resp.json()
		return VerifyResult(genuine=bool(data.get('genuine', False)), source='PPB')

	async def registry(self, since_iso: str) -> list[dict[str, object]]:
		"""PPB → App, daily: registered products and their current status."""
		resp = await self._http.get(f'{self._base}/registry', params={'since': since_iso}, headers=self._headers())
		resp.raise_for_status()
		rows = resp.json()
		assert isinstance(rows, list), 'registry payload must be a list'
		return [dict(r) for r in rows]

	async def recalls(self, since_iso: str) -> list[dict[str, object]]:
		"""PPB → App, on issue. A recall is the one feed that must not be missed, so it is pulled
		separately from the registry rather than inferred from a status field."""
		resp = await self._http.get(f'{self._base}/recalls', params={'since': since_iso}, headers=self._headers())
		resp.raise_for_status()
		rows = resp.json()
		assert isinstance(rows, list), 'recall payload must be a list'
		return [dict(r) for r in rows]

	async def report_suspicious(self, report: dict[str, object]) -> str:
		"""App → PPB, on report: a suspected falsified medicine, with photo evidence."""
		assert report.get('gtin') or report.get('batch'), 'a suspicious-medicine report needs a gtin or batch'
		resp = await self._http.post(f'{self._base}/suspicious', json=report, headers=self._headers())
		resp.raise_for_status()
		return str(resp.json().get('case_ref', ''))


class SHAClient:
	"""§18.6 SHA (NHIF successor): cover verification, facility acceptance, benefit information.

	Only the hash of a member number ever reaches the service layer (`sha_of_member_no`), but the
	raw number has to cross the wire to SHA — that is what a cover check *is*. It is sent in the
	request body and never logged or persisted here.
	"""

	def __init__(self, base_url: str, client: httpx.AsyncClient, api_key: str = '') -> None:
		self._base = base_url.rstrip('/')
		self._http = client
		self._key = api_key
		assert self._base.startswith('http'), 'sha config'

	def _headers(self) -> dict[str, str]:
		out = {'accept': 'application/json'}
		if self._key:
			out['Authorization'] = f'Bearer {self._key}'
		return out

	async def status(self, req: Any) -> Any:
		"""App → SHA, on request. Returns the `SHAStatus` the insurance service expects."""
		from afya.insurance.views import SHAStatus, sha_of_member_no
		resp = await self._http.post(f'{self._base}/cover/verify', json={'member_no': req.member_no, 'purpose': req.purpose}, headers=self._headers())
		if resp.status_code == 404:
			# Unknown member is not an error: it is a real answer, and it is "no cover".
			return SHAStatus(member_no_hash=sha_of_member_no(req.member_no), product='SHIF', active=False, contributions_current=False)
		resp.raise_for_status()
		data = resp.json()
		return SHAStatus(
			member_no_hash=sha_of_member_no(req.member_no),
			product=str(data.get('product', 'SHIF')), active=bool(data.get('active', False)),
			contributions_current=bool(data.get('contributions_current', False)),
			valid_thru_iso=data.get('valid_thru_iso'),
		)

	async def acceptance_list(self, county: str) -> list[dict[str, object]]:
		"""SHA → App, weekly: which facilities accept SHA. Without this the app recommends a facility
		that will turn the patient away at the desk."""
		resp = await self._http.get(f'{self._base}/facilities', params={'county': county}, headers=self._headers())
		resp.raise_for_status()
		rows = resp.json()
		assert isinstance(rows, list), 'acceptance payload must be a list'
		return [dict(r) for r in rows]

	async def benefits(self, product: str) -> list[dict[str, object]]:
		"""SHA → App, on change: covered services for a product."""
		resp = await self._http.get(f'{self._base}/benefits', params={'product': product}, headers=self._headers())
		resp.raise_for_status()
		rows = resp.json()
		assert isinstance(rows, list), 'benefit payload must be a list'
		return [dict(r) for r in rows]


class InlineJaliPort:
	"""Offline fallback (§18.2): no link, no corrections, no fabricated clinician answer.

	Every method the `JaliPort` protocol declares must be here. A missing one is not a degraded
	feature, it is an `AttributeError` on the route — which is why the route is typed against the
	protocol rather than the concrete client.
	"""

	async def launch_link(self, context: str, subject_ref: str) -> str:
		return ''

	async def corrections(self, since_iso: str) -> list[dict[str, object]]:
		return []

	async def share_assessment(self, summary: dict[str, object]) -> bool:
		# There is nowhere to send it, and reporting success would tell the caller a clinician will
		# see it. False is the honest answer.
		return False

	async def clinician_response(self, assessment_id: str) -> dict[str, object] | None:
		return None


class JaliPort(Protocol):
	async def launch_link(self, context: str, subject_ref: str) -> str: ...
	async def corrections(self, since_iso: str) -> list[dict[str, object]]: ...
	async def share_assessment(self, summary: dict[str, object]) -> bool: ...
	async def clinician_response(self, assessment_id: str) -> dict[str, object] | None: ...


class TelcoGatewayClient:
	"""§18.8 zero-rating configuration and airtime incentives.

	Two separate endpoints because they are two separate agreements: the zero-rating rules tell the
	carrier which traffic not to bill, and the airtime API pays an incentive. A deployment can have
	one without the other, so each is configured independently and each refuses to run unconfigured
	rather than posting to an empty base URL.
	"""

	def __init__(self, zero_rating_url: str, airtime_url: str, api_key: str, client: httpx.AsyncClient) -> None:
		self._zero = zero_rating_url.rstrip('/')
		self._airtime = airtime_url.rstrip('/')
		self._key = api_key
		self._http = client
		assert self._key, 'telco config needs an api key'

	def _headers(self) -> dict[str, str]:
		return {'Authorization': f'Bearer {self._key}', 'accept': 'application/json'}

	async def zero_rating_rules(self) -> list[dict[str, object]]:
		"""Telco → App, on change: which destinations are billed at zero.

		The app needs this to know whether an alert will actually cost the recipient money — a
		zero-rating rule that changed but was not pulled means the app tells people alerts are free
		when they are not.
		"""
		assert self._zero, 'zero-rating is not configured for this deployment'
		resp = await self._http.get(f'{self._zero}/rules', headers=self._headers())
		resp.raise_for_status()
		rows = resp.json()
		assert isinstance(rows, list), 'zero-rating payload must be a list'
		return [dict(r) for r in rows]

	async def disburse_airtime(self, msisdn: str, kes: int, reason: str) -> str:
		"""App → Telco, weekly: an incentive payment. Returns the carrier's reference.

		Bounded here rather than at the caller: an unbounded incentive is a way to drain a budget
		through a single compromised worker token, and this is the last place the amount is still
		checkable.
		"""
		assert self._airtime, 'airtime disbursement is not configured for this deployment'
		assert msisdn.startswith('+') or msisdn.isdigit(), 'airtime needs an msisdn'
		assert 0 < kes <= 500, 'an incentive above 500 KES needs a human, not an API call'
		resp = await self._http.post(f'{self._airtime}/disburse', json={'msisdn': msisdn, 'kes': kes, 'reason': reason}, headers=self._headers())
		resp.raise_for_status()
		return str(resp.json().get('reference', ''))
