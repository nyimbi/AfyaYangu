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

	async def check_access_logged(self, req: AccessRequest) -> bool:
		"""`check_access` plus the durable entry §17.4 requires. Every guarded route goes through
		here, so the log covers real access rather than only the calls a test happens to make.

		The in-memory list is kept because it is cheap and readable in-process; it is not the
		record. Before this the record was *only* that list, so an access log survived exactly as
		long as the process did.
		"""
		allowed = self.check_access(req)
		if self._store is not None:
			import time
			await self._store.append_audit(req.role.value, req.dataset, allowed, int(time.time() * 1000))
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
		"""§24.8's 72-hour ODPC notification, measured from when the breach was detected.

		The deadline floors at zero — the DPA gives a fixed window, not a negative one — but the
		floor loses the fact that matters: a breach notified three days late and one notified with
		three days to spare both reported `0`, which is a report that cannot tell a met statutory
		duty from a missed one. `overdue` carries it.
		"""
		deadline = max(0, 3 - event.detected_at_days_ago)
		high_risk = {'health_status', 'location', 'identity'}
		notify = event.affected_count > 100 or high_risk.intersection(event.affected_data) != set()
		if event.detected_at_days_ago > 3:
			self._log_error('ODPC notification deadline missed', days_ago=event.detected_at_days_ago)
		return BreachNotification(
			odpc_deadline_days=deadline,
			notify_users=notify,
			overdue=event.detected_at_days_ago > 3,
			summary=f"breach affecting {', '.join(event.affected_data)} (n={event.affected_count})",
		)

	async def purge_expired(self) -> int:
		return len([c for c in list(self._consents.values()) if c.withdrawn and self._consents.pop(c.consent_id)])