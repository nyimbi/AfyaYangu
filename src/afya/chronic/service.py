"""Chronic disease companion — readings with thresholds, refill reminders before stock-out."""
from typing import ClassVar

from afya.logmixin import LogMixin
from afya.chronic.views import BPReading, GlucoseReading, RefillTracker
from afya.sensors.service import source_class

REFILL_ALERT_DAYS = 7


class ChronicService(LogMixin):
	ALERT_LIMITS: ClassVar[tuple[float, float]] = (180.0, 110.0)  # systolic / glucose mmol/l hard ceilings

	def __init__(self) -> None:
		self._bp: dict[str, list[BPReading]] = {}
		self._glucose: dict[str, list[GlucoseReading]] = {}
		self._refills: dict[str, RefillTracker] = {}
		assert self._bp == {} and self._glucose == {} and self._refills == {}

	async def bp(self, r: BPReading) -> BPReading:
		assert r.stage in ('normal', 'elevated', 'high'), 'stage derived'
		assert r.systolic <= self.ALERT_LIMITS[0], 'physiological ceiling exceeded'
		# §14.9: only a paired device makes this a clinical-grade reading.
		r = r.model_copy(update={'clinical_grade': source_class(r.source).clinical_grade})
		self._bp.setdefault(r.subject_ref, []).append(r)
		if r.stage == 'high':
			self._log_warn('hypertensive reading', sub=r.subject_ref, bp=(r.systolic, r.diastolic))
		return r

	def bp_trend(self, subject_ref: str) -> str:
		hist = self._bp.get(subject_ref, [])
		assert hist, 'no readings'
		sys = [r.systolic for r in hist]
		if len(sys) < 3:
			return 'insufficient (need >= 3 readings)'
		early, late = sum(sys[:3]) / 3, sum(sys[-3:]) / 3
		inc = late - early
		return f"{'worsening' if inc > 5 else ('improving' if inc < -5 else 'stable')} ({inc:+.0f} mmHg across {len(sys)})"

	async def glucose(self, r: GlucoseReading) -> GlucoseReading:
		assert r.mmol_l <= self.ALERT_LIMITS[1], 'physiological ceiling exceeded'
		r = r.model_copy(update={'clinical_grade': source_class(r.source).clinical_grade})
		self._glucose.setdefault(r.subject_ref, []).append(r)
		if r.level == 'high':
			self._log_warn('hyperglycaemia', sub=r.subject_ref, val=r.mmol_l)
		return r

	async def set_refill(self, t: RefillTracker) -> bool:
		self._refills[f'{t.subject_ref}:{t.drug}'] = t
		due = t.days_remaining <= REFILL_ALERT_DAYS
		if due:
			self._log_info('refill alert', drug=t.drug, days=t.days_remaining)
		return due

	def refill_due(self, subject_ref: str) -> list[RefillTracker]:
		out = [t for k, t in self._refills.items() if k.startswith(subject_ref + ':') and t.days_remaining <= REFILL_ALERT_DAYS]
		assert all(t.days_remaining >= 0 for t in out)
		return out