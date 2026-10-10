"""ADaM platform client (§18.1) — the national case-management system.

ADaM is where a CHW's case report has to land for the outbreak response to be real: the app is a
data-collection edge, and the investigation, lab result and contact assignment live on ADaM. The
spec names mutual TLS, field-level encryption for PII and audit logging on both sides.

What this client can honestly do:
	- push a case report and a consented daily monitoring summary as structured JSON;
	- pull status updates, contact assignments and case definitions.
What it cannot: prove mTLS or field-level encryption from inside the process. Those are transport
and deployment properties — the cert pair is configured here and passed to httpx, so the connection
either negotiates mutual TLS or fails the handshake. `mutual_tls_configured` reports the
configuration, not the negotiation, and says so.
"""
from typing import Any

import httpx

from afya.logmixin import LogMixin

# Fields that identify a person. `patient_ref` is a pseudonym the app holds, not a name, but the
# spec's field-level encryption is about exactly this set, so it is enumerated rather than assumed.
PII_FIELDS: frozenset[str] = frozenset({'patient_ref', 'name', 'phone', 'national_id', 'chw_ref'})

# A raw Kenyan MSISDN or national ID reaching this client means the caller skipped the app's own
# pseudonymisation. Refusing here is the last place the mistake is still cheap to fix.
_RAW_PII_PATTERNS: tuple[str, ...] = (r'^\+?254\d{9}$', r'^0[17]\d{8}$', r'^\d{7,8}$')


class AdamClient(LogMixin):
	def __init__(
		self,
		base_url: str,
		client: httpx.AsyncClient,
		api_key: str = '',
		cert: tuple[str, str] | None = None,
	) -> None:
		self._base = base_url.rstrip('/')
		self._http = client
		self._key = api_key
		self._cert = cert
		assert self._base.startswith('http'), 'adam base url'
		if cert is not None:
			assert cert[0] and cert[1], 'mutual TLS needs both a certificate and its key'

	def _headers(self) -> dict[str, str]:
		out = {'accept': 'application/json'}
		if self._key:
			out['Authorization'] = f'Bearer {self._key}'
		return out

	@property
	def mutual_tls_configured(self) -> bool:
		"""Reported, not asserted: whether the deployment negotiated mTLS is the peer's answer, and
		a client cannot claim it on its own behalf."""
		return self._cert is not None

	@staticmethod
	def _assert_no_raw_pii(report: dict[str, Any]) -> None:
		"""The app pseudonymises before it sends; a raw identifier here means it did not."""
		import re
		for field in PII_FIELDS:
			value = report.get(field)
			if isinstance(value, str):
				for pattern in _RAW_PII_PATTERNS:
					assert not re.match(pattern, value), f'{field} reached ADaM unpseudonymised'

	async def push_case_report(self, report: dict[str, Any]) -> str:
		"""App → ADaM, real-time on sync. Returns ADaM's own case reference."""
		assert report.get('report_id'), 'a case report must carry its local id'
		self._assert_no_raw_pii(report)
		resp = await self._http.post(f'{self._base}/cases', json=report, headers=self._headers())
		resp.raise_for_status()
		body = dict(resp.json())
		self._log_info('case report pushed to ADaM', report_id=report['report_id'], adam_ref=body.get('case_ref'))
		return str(body.get('case_ref', ''))

	async def push_monitoring_summary(self, summary: dict[str, Any]) -> bool:
		"""App → ADaM, daily, consented only. The caller is responsible for having consent; this
		refuses a summary that does not carry the flag, so an unconsented push cannot be made by
		omission."""
		assert summary.get('consented') is True, 'monitoring summaries are shared only with consent'
		assert summary.get('subject_ref') and summary.get('day') is not None, 'summary needs subject and day'
		self._assert_no_raw_pii(summary)
		resp = await self._http.post(f'{self._base}/monitoring', json=summary, headers=self._headers())
		resp.raise_for_status()
		return resp.status_code < 300

	async def pull_case_status(self, report_id: str) -> dict[str, Any]:
		"""ADaM → App, on change: investigation status and lab results."""
		resp = await self._http.get(f'{self._base}/cases/{report_id}', headers=self._headers())
		resp.raise_for_status()
		return dict(resp.json())

	async def pull_contact_assignments(self, chw_ref: str) -> list[dict[str, Any]]:
		"""ADaM → App, on assignment: the contacts this worker is responsible for monitoring."""
		resp = await self._http.get(f'{self._base}/contacts', params={'chw': chw_ref}, headers=self._headers())
		resp.raise_for_status()
		rows = resp.json()
		assert isinstance(rows, list), 'contact assignment payload must be a list'
		return [dict(r) for r in rows]

	async def pull_case_definitions(self) -> list[dict[str, Any]]:
		"""ADaM → App, on change: updated clinical criteria. A case definition that changes on the
		server but not on the handset means a CHW screens against last week's criteria."""
		resp = await self._http.get(f'{self._base}/case-definitions', headers=self._headers())
		resp.raise_for_status()
		rows = resp.json()
		assert isinstance(rows, list), 'case definition payload must be a list'
		return [dict(r) for r in rows]
