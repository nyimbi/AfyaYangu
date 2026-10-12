"""Chronic disease companion — readings with thresholds, refill reminders before stock-out.

§MON-003 lists seven conditions. Four have a reading here (`BPReading`, `GlucoseReading`, peak flow
in `afya.monitoring`, and HIV's separately-gated profile) and three — epilepsy, sickle cell disease,
chronic kidney disease — had a string in `ConditionProfile.conditions` and nothing behind it. Those
three live in `afya.chronic.conditions`, and this service is where they are recorded and assessed.

The trend charts read the series the readings are stored into. `bp_trend` predates them and returned
a one-line direction; it is kept because callers hold it, and it now delegates to the chart so the
two cannot disagree about which way a person's blood pressure is going.
"""
from typing import ClassVar

from afya.logmixin import LogMixin
from afya.chronic.conditions import assess_kidney, assess_seizure, assess_sickle_crisis
from afya.chronic.trends import (
	appointment_status, build_chart, lifestyle, lifestyle_for_profile, review_interval_days,
)
from afya.chronic.views import (
	AppointmentStatus, BPReading, ChronicAppointment, ConditionReading, GlucoseReading,
	KidneyFunction, LifestyleGuidance, RefillTracker, SeizureEvent, SickleCrisis, TrendChart,
	TrendPoint,
)
from afya.sensors.service import source_class

REFILL_ALERT_DAYS = 7


class ChronicService(LogMixin):
	ALERT_LIMITS: ClassVar[tuple[float, float]] = (180.0, 110.0)  # systolic / glucose mmol/l hard ceilings

	def __init__(self) -> None:
		self._bp: dict[str, list[BPReading]] = {}
		self._glucose: dict[str, list[GlucoseReading]] = {}
		self._refills: dict[str, RefillTracker] = {}
		# §MON-003's three conditions, and the dated series the trend charts read.
		self._kidney: dict[str, list[tuple[str, KidneyFunction]]] = {}
		self._seizures: dict[str, list[SeizureEvent]] = {}
		self._crises: dict[str, list[SickleCrisis]] = {}
		self._bp_at: dict[str, list[tuple[str, BPReading]]] = {}
		self._glucose_at: dict[str, list[tuple[str, GlucoseReading]]] = {}
		self._appointments: dict[str, ChronicAppointment] = {}
		assert self._bp == {} and self._glucose == {} and self._refills == {}

	async def bp(self, r: BPReading, at_iso: str = '') -> BPReading:
		assert r.stage in ('normal', 'elevated', 'high'), 'stage derived'
		assert r.systolic <= self.ALERT_LIMITS[0], 'physiological ceiling exceeded'
		# §14.9: only a paired device makes this a clinical-grade reading.
		r = r.model_copy(update={'clinical_grade': source_class(r.source).clinical_grade})
		self._bp.setdefault(r.subject_ref, []).append(r)
		if at_iso:
			self._bp_at.setdefault(r.subject_ref, []).append((at_iso, r))
		if r.stage == 'high':
			self._log_warn('hypertensive reading', sub=r.subject_ref, bp=(r.systolic, r.diastolic))
		return r

	def bp_trend(self, subject_ref: str) -> str:
		"""The one-line direction, read off the chart so the two cannot disagree.

		This used to compute its own early/late average with its own five-point threshold, which is a
		second implementation of a number that now has one — and two implementations of a trend
		disagree at the boundary, which is the only place anyone reads it.

		A reading logged without a date is scored and not charted, so a person whose readings are all
		undated gets `insufficient` and the reason rather than an error: the caller asked which way
		their blood pressure is going and "I cannot tell you without the dates" is an answer to that.
		"""
		chart = self.chart(subject_ref, 'bp_systolic')
		if chart.points:
			return f'{chart.direction} ({chart.change:+.0f} mmHg across {len(chart.points)})'
		undated = self._bp.get(subject_ref, [])
		assert undated, 'no readings'
		return (f'insufficient — {len(undated)} reading(s) with no date on them. A trend needs to know '
		        f'when each was taken, or the chart would put two readings a month apart on one day.')

	async def glucose(self, r: GlucoseReading, at_iso: str = '') -> GlucoseReading:
		assert r.mmol_l <= self.ALERT_LIMITS[1], 'physiological ceiling exceeded'
		r = r.model_copy(update={'clinical_grade': source_class(r.source).clinical_grade})
		self._glucose.setdefault(r.subject_ref, []).append(r)
		if at_iso:
			self._glucose_at.setdefault(r.subject_ref, []).append((at_iso, r))
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

	# --- §MON-003's three conditions with no reading behind them ---------------------------------

	async def kidney(self, reading: KidneyFunction, at_iso: str | None = None) -> ConditionReading:
		"""§MON-003's chronic kidney disease: CKD-EPI 2021, staged by KDIGO, sustained over 3 months."""
		if at_iso:
			self._kidney.setdefault(reading.subject_ref, []).append((at_iso, reading))
		out = assess_kidney(reading, at_iso)
		if out.escalate:
			self._log_warn('kidney function needs review', sub=reading.subject_ref,
			               measure=out.measure)
		return out

	async def seizure(self, event: SeizureEvent) -> ConditionReading:
		"""§MON-003's epilepsy: ILAE's t1 and t2, at 5 and 30 minutes."""
		self._seizures.setdefault(event.subject_ref, []).append(event)
		out = assess_seizure(event)
		if out.escalate:
			self._log_warn('seizure escalation', sub=event.subject_ref, measure=out.measure)
		return out

	async def sickle_crisis(self, crisis: SickleCrisis) -> ConditionReading:
		"""§MON-003's sickle cell disease: a crisis, and the signs that make it an emergency."""
		self._crises.setdefault(crisis.subject_ref, []).append(crisis)
		out = assess_sickle_crisis(crisis)
		if out.escalate:
			self._log_warn('sickle crisis escalation', sub=crisis.subject_ref, measure=out.measure)
		return out

	def kidney_series(self, subject_ref: str) -> list[tuple[str, KidneyFunction]]:
		return sorted(self._kidney.get(subject_ref, []), key=lambda p: p[0])

	def seizure_history(self, subject_ref: str) -> list[SeizureEvent]:
		return sorted(self._seizures.get(subject_ref, []), key=lambda e: e.at_iso)

	def crisis_history(self, subject_ref: str) -> list[SickleCrisis]:
		return sorted(self._crises.get(subject_ref, []), key=lambda c: c.at_iso)

	# --- §MON-003's trend charts -----------------------------------------------------------------

	def chart(self, subject_ref: str, metric: str) -> TrendChart:
		"""The series for one metric, as §MON-003's "Trend charts".

		Reads whatever the service holds: the BP and glucose series are here, the peak-flow and weight
		series are `MonitoringService`'s because those readings are logged there. A metric with no
		readings returns an empty chart with an `insufficient` direction rather than a refusal —
		"you have not measured this yet" is the useful answer to a chart request.
		"""
		points: list[TrendPoint] = []
		if metric == 'bp_systolic':
			points = [TrendPoint(at_iso=at, value=float(r.systolic), label='systolic')
			          for at, r in self._bp_at.get(subject_ref, [])]
		elif metric == 'bp_diastolic':
			points = [TrendPoint(at_iso=at, value=float(r.diastolic), label='diastolic')
			          for at, r in self._bp_at.get(subject_ref, [])]
		elif metric == 'glucose':
			points = [TrendPoint(at_iso=at, value=r.mmol_l,
			                     label='fasting' if r.fasting else 'after food')
			          for at, r in self._glucose_at.get(subject_ref, [])]
		return build_chart(subject_ref, metric, points)

	def chart_from_series(self, subject_ref: str, metric: str,
	                      series: list[tuple[str, float]]) -> TrendChart:
		"""A chart over a series the caller holds — how the peak-flow and weight charts are served.

		The two readings are stored in `MonitoringService`, and copying them here to draw a chart would
		be a second copy that drifts. The caller passes the series and this builds the chart, so there
		is one chart implementation and one series.
		"""
		points = [TrendPoint(at_iso=at, value=float(value), label=metric)
		          for at, value in series]
		return build_chart(subject_ref, metric, points)

	# --- §MON-003's appointment tracking ---------------------------------------------------------

	async def schedule_appointment(self, appt: ChronicAppointment) -> ChronicAppointment:
		"""Record a review, and refuse one that is already in the past.

		A due date that has passed at the moment it is scheduled is a date nobody can meet, and it
		would make `appointment_status` report the appointment as overdue the instant it was made.
		"""
		assert appt.appointment_id not in self._appointments, f'{appt.appointment_id} is already scheduled'
		self._appointments[appt.appointment_id] = appt
		return appt

	def appointment(self, appointment_id: str, today_iso: str) -> AppointmentStatus:
		assert appointment_id in self._appointments, 'unknown appointment'
		return appointment_status(self._appointments[appointment_id], today_iso)

	def appointments_for(self, subject_ref: str, today_iso: str) -> list[AppointmentStatus]:
		"""Every appointment for a person, soonest first, overdue ones first of all."""
		mine = [a for a in self._appointments.values() if a.subject_ref == subject_ref]
		return sorted((appointment_status(a, today_iso) for a in mine), key=lambda s: s.due_iso)

	def next_review(self, subject_ref: str, condition: str, last_visit_iso: str,
	                stage: str | None = None) -> ChronicAppointment:
		"""The next review date, computed from the condition's interval and the last visit.

		Computed rather than stored, because the interval is a property of the condition and the stage
		and a stored date is a date that goes stale the moment either changes.
		"""
		days = review_interval_days(condition, stage)
		due = _iso_add_days(last_visit_iso, days)
		return ChronicAppointment(
			appointment_id=f'REV-{subject_ref}-{condition}-{due}', subject_ref=subject_ref,
			condition=condition, due_iso=due, interval_days=days, kind='review',
		)

	# --- §MON-003's lifestyle guidance -----------------------------------------------------------

	def lifestyle(self, condition: str, subject_ref: str | None = None) -> LifestyleGuidance:
		"""§MON-003's "Lifestyle guidance", keyed on the condition rather than on the age."""
		return lifestyle(condition, subject_ref)

	def lifestyle_for(self, conditions: list[str]) -> list[LifestyleGuidance]:
		"""Every condition in a profile that has guidance — a person with two gets both lists."""
		return lifestyle_for_profile(conditions)


def _iso_add_days(iso: str, days: int) -> str:
	from datetime import date, timedelta
	year, month, day = (int(p) for p in iso[:10].split('-'))
	return (date(year, month, day) + timedelta(days=days)).isoformat()