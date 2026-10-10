"""Monitoring & reminders (spec §9.1, §10.2, §11.3): immunisation schedule, medication adherence,
chronic logs, environmental risk, and the 21-day contact monitoring diary.

Scheduling is pure date arithmetic over an injected `today_iso` so the service stays deterministic
and testable without a clock.
"""
from afya.logmixin import LogMixin
from afya.monitoring.views import (
	CATCH_UP_GRACE_WEEKS, EPI_DUE_WEEKS, REMINDER_LEAD_DAYS, AdherenceEvent, AdherenceReport,
	AdherenceAction, ConditionProfile, FoodSafetyAlert, HouseholdMonitor, ImmunisationCatchUp,
	ImmunisationDue, MedSchedule, MonitoringDay, MonitoringVerdict, NutritionGuidance,
	PeakFlowReading, VectorRisk, WeightReading,
)

# Danger symptoms for a monitored contact (MON-009): any of these, or fever, escalates.
MONITORING_ALERT_SYMPTOMS: frozenset[str] = frozenset(
	{'fever', 'fatigue', 'muscle_pain', 'headache', 'sore_throat', 'vomiting', 'diarrhoea', 'rash', 'bleeding', 'hiccups'}
)
MONITORING_DAYS = 21

NUTRITION_BY_AGE: tuple[tuple[int, str, list[str]], ...] = (
	(0, 'Exclusive breastfeeding for the first 6 months — no water, no porridge.', ['breast milk']),
	(6, 'Start soft mashed foods alongside breastfeeding; add iron-rich foods daily.', ['mashed pumpkin', 'avocado', 'well-cooked beans']),
	(12, 'Family foods, three meals plus two snacks; keep breastfeeding to 2 years.', ['ugali', 'sukuma wiki', 'eggs', 'small fish']),
	(24, 'Balanced plate at every meal; watch for worms and give deworming when due.', ['githeri', 'milk', 'fruit in season']),
)


def _days_from_weeks(weeks: int) -> int:
	assert weeks >= 0, 'age weeks non-negative'
	return weeks * 7


def _iso_add_days(iso: str, days: int) -> str:
	"""Minimal civil-date arithmetic on YYYY-MM-DD (no clock, no tz)."""
	from datetime import date, timedelta
	year, month, day = (int(p) for p in iso[:10].split('-'))
	return (date(year, month, day) + timedelta(days=days)).isoformat()


def _days_between(iso_a: str, iso_b: str) -> int:
	from datetime import date
	a = date(*(int(p) for p in iso_a[:10].split('-')))
	b = date(*(int(p) for p in iso_b[:10].split('-')))
	return (b - a).days


class MonitoringService(LogMixin):
	def __init__(self) -> None:
		self._dob: dict[str, str] = {}
		self._given: dict[str, set[tuple[str, int]]] = {}
		self._schedules: dict[str, MedSchedule] = {}
		self._adherence: list[AdherenceEvent] = []
		self._monitoring: list[MonitoringDay] = []
		self._households: dict[str, HouseholdMonitor] = {}
		self._conditions: dict[str, ConditionProfile] = {}
		self._breeding: list[dict[str, object]] = []
		self._food_alerts: list[FoodSafetyAlert] = []
		assert self._dob == {} and self._monitoring == []

	# --- MON-001 child immunisation ------------------------------------------------------

	async def register_child(self, member_ref: str, dob_iso: str) -> None:
		assert len(dob_iso) >= 10, 'dob required'
		self._dob[member_ref] = dob_iso
		self._given.setdefault(member_ref, set())

	async def record_dose(self, member_ref: str, vaccine: str, dose_no: int, given_iso: str) -> None:
		assert member_ref in self._dob, 'unknown child — register dob first'
		assert vaccine in EPI_DUE_WEEKS, f'unknown vaccine {vaccine}'
		assert 0 <= dose_no <= 4, 'dose bounds'
		self._given.setdefault(member_ref, set()).add((vaccine, dose_no))
		self._log_info('dose recorded', member=member_ref, vaccine=vaccine, dose=dose_no, on=given_iso)

	def schedule(self, member_ref: str, today_iso: str) -> list[ImmunisationDue]:
		"""Full EPI schedule with per-dose status and the 3-day/1-day reminder leads."""
		assert member_ref in self._dob, 'unknown child'
		dob = self._dob[member_ref]
		age_days = _days_between(dob, today_iso)
		given = self._given.get(member_ref, set())
		rows: list[ImmunisationDue] = []
		for vaccine, doses in EPI_DUE_WEEKS.items():
			for dose_no, due_weeks in doses:
				due_day = _days_from_weeks(due_weeks)
				if (vaccine, dose_no) in given:
					status = 'given'
				elif age_days >= due_day + _days_from_weeks(CATCH_UP_GRACE_WEEKS):
					status = 'overdue'
				elif age_days >= due_day:
					status = 'due'
				else:
					status = 'upcoming'
				leads = [d for d in REMINDER_LEAD_DAYS if 0 <= due_day - age_days <= d] if status in ('due', 'upcoming') else []
				rows.append(ImmunisationDue(
					member_ref=member_ref, vaccine=vaccine, dose_no=dose_no, due_age_weeks=due_weeks,
					status=status, remind_days_before=sorted(leads),
				))
		assert rows, 'schedule never empty for a known child'
		return rows

	def catch_up(self, member_ref: str, today_iso: str) -> ImmunisationCatchUp:
		defaulted = [f'{r.vaccine} dose {r.dose_no}' for r in self.schedule(member_ref, today_iso) if r.status == 'overdue']
		advise = (
			f'{len(defaulted)} dose(s) behind schedule. Bring the child to the nearest vaccination point — '
			'catch-up doses are safe and free, and no dose needs restarting.'
			if defaulted else 'No missed doses: the child is up to date.'
		)
		return ImmunisationCatchUp(member_ref=member_ref, defaulted=defaulted, advise=advise)

	# --- MON-004 medication reminders ----------------------------------------------------

	async def add_schedule(self, sched: MedSchedule) -> MedSchedule:
		assert sched.times_per_day * sched.duration_days <= 2190, 'unreasonable total dose count'
		self._schedules[sched.schedule_id] = sched
		return sched

	async def record_adherence(self, event: AdherenceEvent) -> AdherenceReport:
		assert event.schedule_id in self._schedules, 'unknown schedule'
		self._adherence.append(event)
		return self.adherence(event.schedule_id)

	def adherence(self, schedule_id: str) -> AdherenceReport:
		sched = self._schedules[schedule_id]
		events = [e for e in self._adherence if e.schedule_id == schedule_id]
		taken = len([e for e in events if e.action is AdherenceAction.taken])
		skipped = len([e for e in events if e.action is AdherenceAction.skipped])
		snoozed = len([e for e in events if e.action is AdherenceAction.snoozed])
		expected = sched.times_per_day * sched.duration_days
		pct = round(100.0 * taken / expected, 1) if expected else 0.0
		refill_due = pct >= 85.0 and expected - taken <= sched.refill_at_days_left * sched.times_per_day
		assert 0.0 <= pct <= 100.0, 'adherence bounded'
		return AdherenceReport(
			schedule_id=schedule_id, expected_doses=expected, taken=taken, skipped=skipped,
			snoozed=snoozed, adherence_pct=pct, refill_due=refill_due,
		)

	# --- MON-003 chronic log -------------------------------------------------------------

	async def log_peak_flow(self, r: PeakFlowReading) -> dict[str, object]:
		"""Asthma zones per personal best: >=80% green, 50-79% yellow, <50% red (escalate)."""
		best = r.personal_best or r.litres_per_min
		pct = round(100.0 * r.litres_per_min / best, 1)
		zone = 'green' if pct >= 80 else ('yellow' if pct >= 50 else 'red')
		advise = {
			'green': 'Asthma well controlled — continue preventer inhaler as prescribed.',
			'yellow': 'Asthma worsening: use reliever inhaler, follow your action plan, see a clinician today.',
			'red': 'MEDICAL EMERGENCY: use reliever now and go to a facility immediately; call 719.',
		}[zone]
		if zone == 'red':
			self._log_warn('peak flow red zone', sub=r.subject_ref, pct=pct)
		return {'zone': zone, 'pct_of_best': pct, 'advise': advise}

	async def log_weight(self, r: WeightReading) -> dict[str, object]:
		return {'kg': r.kg, 'note': 'Log weekly, same time of day, to read a real trend.'}

	async def set_conditions(self, profile: ConditionProfile) -> ConditionProfile:
		if any(c.lower() == 'hiv' for c in profile.conditions):
			assert profile.hiv_pin_set, 'HIV status requires a separate PIN (§9.1)'
		self._conditions[profile.subject_ref] = profile
		return profile

	def shareable_report(self, subject_ref: str) -> dict[str, object]:
		"""Clinician-facing report. HIV is excluded unless separately consented (§9.1)."""
		profile = self._conditions.get(subject_ref)
		conditions = [c for c in (profile.conditions if profile else []) if c.lower() != 'hiv']
		return {
			'subject_ref': subject_ref,
			'conditions': conditions,
			'withheld': ['HIV status (separate consent required)'] if profile and any(c.lower() == 'hiv' for c in profile.conditions) else [],
			'note': 'Bring this report to your appointment; it does not replace your clinic card.',
		}

	# --- MON-005..008 environment & nutrition --------------------------------------------

	def vector_risk(self, county: str, rainfall_mm_72h: float, livestock_adjacent: bool = False) -> VectorRisk:
		assert rainfall_mm_72h >= 0, 'rainfall non-negative'
		band = 'flood' if rainfall_mm_72h >= 100 else ('wet' if rainfall_mm_72h >= 50 else ('normal' if rainfall_mm_72h >= 10 else 'dry'))
		malaria_season = band in ('wet', 'flood')
		rvf = livestock_adjacent and band in ('wet', 'flood')
		if rvf:
			advise = 'Rift Valley fever risk for livestock-adjacent households: avoid contact with aborting animals; boil milk; report livestock deaths.'
		elif malaria_season:
			advise = 'Standing water after rain breeds mosquitoes: drain containers, use nets every night, and test any fever for malaria.'
		else:
			advise = 'Low vector activity: keep using nets, and clear containers before the next rains.'
		return VectorRisk(county=county, rainfall_band=band, malaria_season=malaria_season, rvf_alert=rvf, advise=advise)

	async def report_breeding_site(self, county: str, lat: float, lon: float, description: str) -> dict[str, object]:
		self._breeding.append({'county': county, 'lat': lat, 'lon': lon, 'description': description})
		self._log_info('breeding site reported', county=county)
		return {'routed_to': f'{county} county public health office', 'reported': len(self._breeding)}

	async def issue_food_alert(self, alert: FoodSafetyAlert) -> FoodSafetyAlert:
		self._food_alerts.append(alert)
		self._log_warn('food safety alert', kind=alert.kind, county=alert.county)
		return alert

	def food_alerts(self, county: str) -> list[FoodSafetyAlert]:
		return [a for a in self._food_alerts if a.county == county]

	def nutrition_guidance(self, age_months: int) -> NutritionGuidance:
		assert 0 <= age_months <= 60, 'paediatric nutrition range'
		band = max((row for row in NUTRITION_BY_AGE if row[0] <= age_months), key=lambda r: r[0])
		return NutritionGuidance(age_months=age_months, guidance=band[1], seasonal_foods=list(band[2]))

	# --- MON-009 21-day contact monitoring ------------------------------------------------

	def enrol(self, subject_ref: str, officer: str | None = None) -> HouseholdMonitor:
		"""Enrol a contact for 21 days; requires the outbreak event to be open (§11.1)."""
		household = HouseholdMonitor(subject_ref=subject_ref, monitoring_officer=officer)
		self._households[subject_ref] = household
		self._log_info('contact enrolled for monitoring', sub=subject_ref)
		return household

	async def log_day(self, entry: MonitoringDay) -> MonitoringVerdict:
		assert entry.subject_ref in self._households, 'not enrolled for monitoring'
		self._monitoring.append(entry)
		flagged = sorted(set(entry.symptoms) & MONITORING_ALERT_SYMPTOMS)
		fever = entry.temperature_c >= 38.0
		escalate = fever or bool(flagged)
		household = self._households[entry.subject_ref]
		notify_chw = escalate and household.monitoring_officer is not None
		remaining = max(0, MONITORING_DAYS - entry.day)
		if escalate:
			reason = 'fever' if fever else ', '.join(flagged)
			message = f'Day {entry.day}: {reason} recorded. Call 719 now and await instructions — do not travel by public transport.'
		else:
			message = f'Day {entry.day} of {MONITORING_DAYS} logged, no warning signs. {remaining} days to go.'
		if escalate:
			self._log_warn('monitoring escalation', sub=entry.subject_ref, day=entry.day)
		from afya.sensors.service import source_class
		reading = source_class(entry.source)
		return MonitoringVerdict(
			subject_ref=entry.subject_ref, day=entry.day, days_remaining=remaining,
			escalate=escalate, notify_chw=notify_chw, message=message,
			clinical_grade=reading.clinical_grade, reading_source=entry.source,
		)

	def diary(self, subject_ref: str) -> list[MonitoringDay]:
		return sorted([e for e in self._monitoring if e.subject_ref == subject_ref], key=lambda e: e.day)

	def adherence_reminder_days(self, subject_ref: str) -> list[int]:
		"""Days in the 21-day window with no entry — the adherence surface (§11.3 escalation)."""
		logged = {e.day for e in self._monitoring if e.subject_ref == subject_ref}
		missing = [d for d in range(1, MONITORING_DAYS + 1) if d not in logged]
		assert len(missing) <= MONITORING_DAYS, 'window bounded'
		return missing
