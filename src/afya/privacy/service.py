"""Privacy service — consent ledger, DPIA gate, RBAC, anonymization, breach notification (spec §17)."""
from typing import Any

from afya.logmixin import LogMixin
from afya.privacy.views import (
	AccessRequest, BreachEvent, BreachNotification, ConsentRecord, DPIAInput, DPIAReport,
	LegalBasis, RBACRole, _SCOPE,
)


class PrivacyService(LogMixin):
	def __init__(self, store=None) -> None:
		self._consents: dict[str, ConsentRecord] = {}
		self._audit: list[tuple[bool, AccessRequest]] = []
		self._store = store
		assert self._consents == {} and self._audit == []

	async def record_consent(self, record: ConsentRecord) -> ConsentRecord:
		assert record.subject_ref, 'subject_ref required'
		assert record.purpose, 'purpose required'
		if not record.legal_basis is LegalBasis.legal_obligation:
			assert record.retention_days <= 730, 'health data retention must be bounded (24 months cap)'
		self._consents[record.consent_id] = record
		if self._store is not None:
			await self._store.save_consent(record)
		self._log_info('consent recorded', consent_id=record.consent_id)
		return record

	def has_consent(self, subject_ref: str, purpose: str) -> bool:
		out = any(
			c.subject_ref == subject_ref and c.purpose == purpose and not c.withdrawn
			for c in self._consents.values()
		)
		return out

	async def withdraw(self, consent_id: str) -> ConsentRecord:
		rec = self._consents[consent_id]
		rec.withdrawn = True
		if self._store is not None:
			await self._store.save_consent(rec)
		self._log_warn('consent withdrawn', consent_id=consent_id)
		return rec

	def check_access(self, req: AccessRequest) -> bool:
		allowed = any(req.dataset.startswith(scope) or req.dataset == scope for scope in _SCOPE.get(req.role, set()))
		self._audit.append((allowed, req))
		return allowed

	def audit_log(self) -> list[tuple[bool, AccessRequest]]:
		return list(self._audit)

	def assess_dpia(self, inp: DPIAInput) -> DPIAReport:
		risks: list[str] = []
		if inp.raw_sensor_data_retained:
			risks.append('raw sensor data retention violates data minimisation (spec 17.2)')
		if inp.automated_decisions:
			risks.append('automated health risk decisions require human override')
		if inp.cross_border_transfer:
			risks.append('cross-border transfer requires ODPC approval + SCCs')
		if inp.children_data:
			risks.append('children data requires guardian consent path')
		if inp.proximity_logging:
			risks.append('proximity logging requires opt-in transparency per DESIRE lesson')
		blocked = 'raw sensor data retention violates data minimisation (spec 17.2)' in risks
		return DPIAReport(risks=risks, requires_dpia=bool(risks), blocked=blocked)

	def anonymize(self, data: dict[str, Any]) -> dict[str, Any]:
		assert isinstance(data, dict), 'data must be dict'
		out = dict(data)
		if 'phone' in out:
			assert isinstance(out['phone'], str), 'phone must be str'
			out['phone'] = out['phone'][:6] + '*' * max(0, len(out['phone']) - 6)
		if 'national_id' in out:
			out['national_id'] = '****'
		if 'location' in out:
			lat, lon = out['location'].get('lat'), out['location'].get('lon')
			out['location'] = {'county': self._county_approx(lat, lon) if lat is not None else 'unknown'}
		if 'timestamp' in out:
			ts = out['timestamp']
			out['timestamp'] = ts[:10] if isinstance(ts, str) else str(ts)[:10]
		return out

	@staticmethod
	def _county_approx(lat: float, lon: float) -> str:
		assert -5.0 < lat < 6.0 and 33.0 < lon < 43.0, 'coords outside Kenya bounds'
		if lat < -0.5:
			return 'Coast'
		if lat > 1.0:
			return 'Northern'
		return 'Central'

	def breach_notification(self, event: BreachEvent) -> BreachNotification:
		deadline = max(0, 3 - event.detected_at_days_ago)
		high_risk = {'health_status', 'location', 'identity'}
		notify = event.affected_count > 100 or high_risk.intersection(event.affected_data) != set()
		return BreachNotification(
			odpc_deadline_days=deadline,
			notify_users=notify,
			summary=f"breach affecting {', '.join(event.affected_data)} (n={event.affected_count})",
		)

	async def purge_expired(self) -> int:
		return len([c for c in list(self._consents.values()) if c.withdrawn and self._consents.pop(c.consent_id)])