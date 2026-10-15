"""Monitoring & reminders (spec §9.1, §10.2, §11.3): immunisation schedule, medication adherence,
chronic logs, environmental risk, and the 21-day contact monitoring diary.

Scheduling is pure date arithmetic over an injected `today_iso` so the service stays deterministic
and testable without a clock.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from afya.facilities.service import haversine_km
from afya.facilities.views import FacilityKind
from afya.ids import ref8
from afya.logmixin import LogMixin
from afya.monitoring.views import (
	CATCH_UP_GRACE_WEEKS, DUSK_HOUR, EPI_DUE_WEEKS,
	LARVICIDE_CLASSES, LARVICIDE_INTERVAL_FLOOR_DAYS, REMINDER_LEAD_DAYS, REMINDER_SLOTS,
	SEASONAL_CALENDAR_SOURCE, SEASONAL_FOODS, SUPPLEMENT_RULE, THERAPEUTIC_FEEDING_LABEL,
	AdherenceEvent, AdherenceReport, AdherenceAction, CampaignNotice, ConditionProfile,
	FoodSafetyAlert, HouseholdMonitor, ImmunisationAlert, ImmunisationCatchUp, ImmunisationDue,
	LarvicidingNotice, MedSchedule, MonitoringDay, MonitoringReminder, MonitoringVerdict,
	NutritionGuidance, PeakFlowReading, ProtectionReminder, ReminderSlot, TherapeuticFeedingSite,
	VectorRisk, WeightReading, reminder_times,
)
from afya.alerting.views import FeedItem
from afya.records.service import RecordsService
from afya.records.views import ImmunisationRecord
from afya.sync.views import SyncOp, SyncQueue

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


def support_resources(escalate: bool) -> list[dict[str, str]]:
	"""§MON-009's "psychological support resources", attached to the verdict.

	The resources are §REC-005's, read from the one place they live rather than copied here: the
	monitoring diary is a frightening place to be and the support belongs on the screen the person is
	already looking at, but a second copy of the counselling numbers is a second set to keep current.
	The escalation flag changes the framing and not the numbers — a flagged day says plainly why the
	lines are on the screen, because a person who has just logged a fever should not have to work out
	whether the helpline is for them.
	"""
	from afya.mental.views import COUNSELLING_LINES
	resources = [
		{'kind': 'outbreak_support', 'slug': 'isolation_distress',
		 'title': 'Distress while isolating or in quarantine', 'route': '/mental/outbreak-support/isolation_distress'},
		{'kind': 'coping', 'slug': 'coping_tips', 'title': 'What can I do to cope?', 'route': '/mental/coping'},
	]
	for line in COUNSELLING_LINES:
		resources.append({'kind': 'crisis_line', 'slug': line['name'], 'title': line['name'],
		                  'route': f'tel:{line["number"]}', 'number': line['number'],
		                  'verified': line['verified']})
	if escalate:
		resources.insert(0, {
			'kind': 'escalation_note', 'slug': 'why-this-is-here', 'route': '',
			'title': 'Why these are on this screen',
			'body': 'You logged a warning sign. Waiting for the result of a test or watching for a '
			        'fever is frightening on its own, and that is a normal reaction, not a weakness. '
			        'These lines are for you as well as for the person you are monitoring.'})
	return resources


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
	def __init__(self, wallet: RecordsService | None = None, sync: SyncQueue | None = None) -> None:
		# The wallet, so a dose recorded here reaches the record that outlives the paper card. The
		# dependency runs one way — `records` never imports `monitoring` — which is what makes the
		# wallet the owner of the dose and the tracker a view over it rather than a second store.
		self._wallet: RecordsService | None = wallet
		# §MON-004's "Works with no data connection". A dose taken with no signal is still a dose
		# taken, so it is queued for the sync layer rather than dropped. Absent when the service is
		# built without one, and the dose is then recorded locally and not queued.
		self._sync: SyncQueue | None = sync
		self._campaigns: list[CampaignNotice] = []
		self._dob: dict[str, str] = {}
		self._given: dict[str, set[tuple[str, int]]] = {}
		self._schedules: dict[str, MedSchedule] = {}
		self._adherence: list[AdherenceEvent] = []
		self._monitoring: list[MonitoringDay] = []
		self._households: dict[str, HouseholdMonitor] = {}
		self._conditions: dict[str, ConditionProfile] = {}
		self._breeding: list[dict[str, object]] = []
		self._food_alerts: list[FoodSafetyAlert] = []
		# §MON-007's larviciding rounds. Kept, not merely published: the notice reaches the feed and
		# the *county's* own record of what it is treating has to outlive the feed window, because
		# the next question is "is this drain being treated" and the feed only answers "what is new".
		self._larviciding: list[LarvicidingNotice] = []
		# §MON-003's trend charts need a series, and these two readings had none: `log_peak_flow` and
		# `log_weight` returned a verdict and stored nothing, so two of the four readings the section
		# names had no history to chart. Kept per subject, oldest first.
		self._peak_flow: dict[str, list[tuple[str, int]]] = {}
		self._weight: dict[str, list[tuple[str, float]]] = {}
		assert self._dob == {} and self._monitoring == []

	# --- MON-001 child immunisation ------------------------------------------------------

	async def register_child(self, member_ref: str, dob_iso: str) -> None:
		assert len(dob_iso) >= 10, 'dob required'
		self._dob[member_ref] = dob_iso
		self._given.setdefault(member_ref, set())

	async def record_dose(self, rec: ImmunisationRecord) -> ImmunisationRecord:
		"""§MON-001's "Record doses given (with photo of card)", into the wallet that owns the dose.

		This used to take four scalars and add a tuple to a set of its own, so a dose recorded
		through the child tracker never reached the wallet: `immunisation_gaps`, the vaccination
		certificate and the export all read `RecordsService._imm` and none of them could see it. The
		tracker is the screen a parent uses and the wallet is the record that outlives the paper card
		— the section says so — so a dose filed in the first and absent from the second is the whole
		point of the feature lost at the seam between two modules.

		The record goes to the wallet when the child is in it, and is kept here either way, because
		the schedule has to work for a child whose guardian registered them in the tracker without
		enrolling them as a wallet member.
		"""
		assert rec.member_ref in self._dob, 'unknown child — register dob first'
		assert rec.vaccine in EPI_DUE_WEEKS, f'unknown vaccine {rec.vaccine}'
		assert 0 <= rec.dose_no <= 4, 'dose bounds'
		self._given.setdefault(rec.member_ref, set()).add((rec.vaccine, rec.dose_no))
		if self._wallet is not None and rec.member_ref in self._wallet_members():
			await self._wallet.record_immunisation(rec)
		self._log_info('dose recorded', member=rec.member_ref, vaccine=rec.vaccine,
		               dose=rec.dose_no, on=rec.given_iso, card=bool(rec.card_photo_sha256))
		return rec

	def _wallet_members(self) -> set[str]:
		"""The member refs the wallet knows, read through its own accessor rather than its store."""
		assert self._wallet is not None
		return self._wallet.member_refs()

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

	def missed_dose_alerts(self, member_ref: str, today_iso: str) -> list[ImmunisationAlert]:
		"""§MON-001's "Missed-dose alerts" — the alert, as data the device schedules.

		`schedule` has always been able to say a dose is `overdue`; what the section asked for and
		nothing raised is an alert. Two kinds, because they are two different messages to a parent: a
		dose the child is *behind* on, and one that is *coming* within the 3-day lead. The second is
		what makes the reminder fire before the visit is missed rather than after, and it is why this
		reads `remind_days_before` instead of only the `overdue` rows.

		Not a notification queue: the server states the alert and the device schedules it, on
		§ACC-004's reasoning — the same shape as §REC-004's contraception reminder and §EMG-001's
		countdown, and for the same reason. `due_iso` is the date the alert is about, so a client
		never has to recompute it from the age in weeks.
		"""
		assert member_ref in self._dob, 'unknown child'
		dob = self._dob[member_ref]
		alerts: list[ImmunisationAlert] = []
		for row in self.schedule(member_ref, today_iso):
			due_iso = _iso_add_days(dob, _days_from_weeks(row.due_age_weeks))
			if row.status == 'overdue':
				late = _days_between(due_iso, today_iso)
				alerts.append(ImmunisationAlert(
					member_ref=member_ref, vaccine=row.vaccine, dose_no=row.dose_no, kind='overdue',
					days_overdue=late, due_iso=due_iso,
					message=(f'{row.vaccine} dose {row.dose_no} was due on {due_iso}, {late} days ago. '
					         'Catch-up doses are safe and free — bring the card to any vaccination '
					         'point and no dose needs restarting.')))
			elif row.remind_days_before:
				alerts.append(ImmunisationAlert(
					member_ref=member_ref, vaccine=row.vaccine, dose_no=row.dose_no, kind='due_soon',
					days_overdue=0, due_iso=due_iso,
					message=(f'{row.vaccine} dose {row.dose_no} is due on {due_iso} — '
					         f'{min(row.remind_days_before)} day(s) from now.')))
		return sorted(alerts, key=lambda a: (a.kind != 'overdue', a.due_iso, a.vaccine))

	async def publish_campaign(self, notice: CampaignNotice, feed: object) -> CampaignNotice:
		"""§MON-001's "Campaign notifications (polio, measles)", published into the community feed.

		A campaign is a *service being offered*, not a hazard in a county: its audience is the parents
		of children in an age band, not everyone inside a boundary. So it carries its own shape and is
		delivered through §ALT-001's feed under the immunisation category, where the parent who asked
		for immunisation reminders is the person who receives it — a category with a producer at last,
		which is what the audit row said was missing.

		`feed` is the `AlertingService`, typed loosely for the reason every cross-module port here is:
		the two services are wired at the composition root, and neither imports the other's class.
		"""
		assert notice.counties, 'a campaign with no county reaches nobody'
		assert notice.ends_iso > notice.starts_iso, (
			f'a campaign must end after it begins: {notice.starts_iso} to {notice.ends_iso}')
		low, high = notice.target_age_months
		assert 0 <= low < high <= 216, f'{low}-{high} months is not an age band a campaign can have'
		self._campaigns.append(notice)
		publish = getattr(feed, 'publish', None)
		if publish is not None:
			for county in notice.counties:
				await publish(FeedItem(
					item_id=f'{notice.campaign_id}-{county}', category='immunisation', county=county,
					headline=notice.headline, body=notice.body, source=notice.issued_by,
					verified=True, published_iso=notice.starts_iso))
		self._log_info('campaign published', campaign=notice.campaign_id, disease=notice.disease,
		               counties=len(notice.counties))
		return notice

	def campaigns(self, county: str, on_iso: str) -> list[CampaignNotice]:
		"""The campaigns running in a county on a given day — the question a parent actually asks."""
		return sorted((c for c in self._campaigns
		               if county in c.counties and c.starts_iso <= on_iso <= c.ends_iso),
		              key=lambda c: c.starts_iso)

	# --- MON-004 medication reminders ----------------------------------------------------

	async def add_schedule(self, sched: MedSchedule) -> MedSchedule:
		assert sched.times_per_day * sched.duration_days <= 2190, 'unreasonable total dose count'
		# §MON-004's "Multiple daily reminders": the schedule's own times, computed once here rather
		# than by each client. `times_per_day` is a count and a count cannot be notified at; two
		# clients deriving the instants separately would eventually disagree about when to wake
		# somebody, so the server derives them and serves them.
		sched.reminder_times = reminder_times(sched.times_per_day)
		self._schedules[sched.schedule_id] = sched
		return sched

	async def record_adherence(self, event: AdherenceEvent) -> AdherenceReport:
		assert event.schedule_id in self._schedules, 'unknown schedule'
		self._adherence.append(event)
		# §MON-004's "Works with no data connection". The dose is recorded locally first — that is
		# the point of the bullet — and then queued so it reaches the server when there is a signal.
		# A dose is the highest-frequency health action anyone takes and the one most likely to be
		# logged with no bars, so it must not depend on the network to be kept.
		if self._sync is not None:
			await self._queue_adherence(event)
		return self.adherence(event.schedule_id)

	async def _queue_adherence(self, event: AdherenceEvent) -> None:
		"""Hand the dose to the sync queue, under §16.3's `medication` rule.

		The dataset name is the one `CONFLICT_RULES` already carries for this data, so the strategy
		applied on replay is the spec's own (last-write-wins, "Personal") rather than one chosen here.
		"""
		assert self._sync is not None, 'a queue is required to queue a dose'
		# The *tail* of the id, not the head: a UUID7's first bytes are its millisecond timestamp, so
		# a prefix collides for two doses logged in the same millisecond and the queue — keyed on
		# `op_id` — keeps the last and drops the first. Doses arrive in bursts (a week of them replayed
		# after an outage), which is exactly when a collision costs the most. `CampaignNotice` takes
		# its suffix for the same reason.
		op = SyncOp(
			op_id='OP-' + ref8(),
			dataset='medication',
			client_ts=int(datetime.now(timezone.utc).timestamp() * 1000),
			payload={'schedule_id': event.schedule_id, 'at_iso': event.at_iso,
			         'action': event.action.value},
		)
		await self._sync.enqueue(op)
		self._log_info('dose queued for sync', schedule=event.schedule_id, action=event.action.value)

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

	async def log_peak_flow(self, r: PeakFlowReading, at_iso: str = '') -> dict[str, object]:
		"""Asthma zones per personal best: >=80% green, 50-79% yellow, <50% red (escalate).

		The reading is stored as well as scored, because §MON-003's trend chart is a series and this
		returned a verdict with nothing behind it. `at_iso` is the chart's x-axis; a reading with no
		date cannot be placed on one, and a chart that used the server's clock would put two readings
		taken a month apart on the same day.
		"""
		best = r.personal_best or r.litres_per_min
		pct = round(100.0 * r.litres_per_min / best, 1)
		zone = 'green' if pct >= 80 else ('yellow' if pct >= 50 else 'red')
		advise = {
			'green': 'Asthma well controlled — continue preventer inhaler as prescribed.',
			'yellow': 'Asthma worsening: use reliever inhaler, follow your action plan, see a clinician today.',
			'red': 'MEDICAL EMERGENCY: use reliever now and go to a facility immediately; call 719.',
		}[zone]
		if at_iso:
			self._peak_flow.setdefault(r.subject_ref, []).append((at_iso, r.litres_per_min))
		if zone == 'red':
			self._log_warn('peak flow red zone', sub=r.subject_ref, pct=pct)
		return {'zone': zone, 'pct_of_best': pct, 'advise': advise}

	async def log_weight(self, r: WeightReading, at_iso: str = '') -> dict[str, object]:
		"""Store the weight and return the note. §MON-003's chart reads the series this keeps."""
		if at_iso:
			self._weight.setdefault(r.subject_ref, []).append((at_iso, r.kg))
		return {'kg': r.kg, 'note': 'Log weekly, same time of day, to read a real trend.'}

	def peak_flow_series(self, subject_ref: str) -> list[tuple[str, int]]:
		"""The stored peak-flow readings, oldest first — the chart's input, not the chart."""
		return sorted(self._peak_flow.get(subject_ref, []), key=lambda p: p[0])

	def weight_series(self, subject_ref: str) -> list[tuple[str, float]]:
		return sorted(self._weight.get(subject_ref, []), key=lambda p: p[0])

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
		band = self._rainfall_band(rainfall_mm_72h)
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

	# --- §MON-007 "larviciding campaign notifications" and "personal protection reminders" -----

	async def publish_larviciding(self, notice: LarvicidingNotice, feed: object) -> LarvicidingNotice:
		"""§MON-007's "larviciding campaign notifications", published into §ALT-001's feed.

		A larviciding round is a county operation over named habitats, so it is published under the
		`vector_control` category — which `FEED_PREFERENCE` routes to §ALT-003's "County alerts",
		the section's own option. No new toggle is invented: the audit row said the feed had no
		vector category, and the honest fix is a category with a real preference behind it rather
		than a twelfth switch §ALT-003 never listed.

		Every notice carries `SUPPLEMENT_RULE`, appended here rather than trusted to the caller's
		`body`. The source is unambiguous that larviciding "should never be seen as a substitute for
		ITNs or IRS in areas with significant malaria risk", and a county notice is exactly the
		document in which that sentence goes missing — the round is visible and the nets are not.

		`feed` is the `AlertingService`, typed loosely for the reason every cross-module port here
		is: the two are wired at the composition root and neither imports the other's class.
		"""
		assert notice.first_round_iso, 'a round needs a date'
		label, interval_days = LARVICIDE_CLASSES[notice.larvicide]
		body = f'{notice.body} {SUPPLEMENT_RULE}'
		assert len(body) <= 600, f'a notice body may not exceed 600 characters, got {len(body)}'
		self._larviciding.append(notice)
		publish = getattr(feed, 'publish', None)
		if publish is not None:
			for county in notice.counties:
				await publish(FeedItem(
					item_id=f'{notice.campaign_id}-{county}', category='vector_control', county=county,
					headline=notice.headline, body=body, source=notice.issued_by,
					verified=True, published_iso=notice.first_round_iso))
		self._log_info('larviciding round published', campaign=notice.campaign_id,
		               larvicide=notice.larvicide, counties=len(notice.counties),
		               retreatment_days=interval_days)
		return notice

	def larviciding_rounds(self, county: str, on_iso: str) -> list[LarvicidingNotice]:
		"""The rounds a county has published — the question the person living beside a drain asks.

		A round is not a window with an end: the manual's intervals are re-treatment intervals, so a
		round begun before today is still running until the next one is announced. Filtering on an
		`ends_iso` the model does not carry would answer "nothing is happening" about a programme
		that is mid-round, which is the one wrong answer here.
		"""
		return sorted((n for n in self._larviciding if county in n.counties and n.first_round_iso <= on_iso),
		              key=lambda n: n.first_round_iso)

	def protection_reminder(self, county: str, rainfall_mm_72h: float, at_iso: str) -> ProtectionReminder:
		"""§MON-007's "personal protection reminders", as the instants the device schedules.

		`at_iso` is supplied rather than assumed, the same contract §MON-005's `treatment_reminder`
		keeps: the reminder is anchored to *now*, and a service that picked a time would place the
		net reminder at an hour the household is not going to bed.

		Two reminders, because the section names two protections and they are not the same kind of
		act. The net is a nightly habit the manual ties to a fixed time — biting is "between dusk and
		dawn", with `An. gambiae` and `An. funestus` peaking "an hour before dawn" — so it is placed
		at the next dusk. Draining containers is habitat manipulation, which the manual calls "a
		recurrent activity", and its interval is `LARVICIDE_INTERVAL_FLOOR_DAYS`: the shortest
		re-treatment interval any class in `LARVICIDE_CLASSES` carries, so a household is asked to
		clear standing water at least as often as a county would re-treat the same water.

		The message changes with the rain band rather than being one string. In the dry band the
		source's own position is that vector activity is low and the work is preparation before the
		next rains; in the wet and flood bands the same two acts are urgent. A single string would
		have to be the wet one, and would then be wrong for half the year.
		"""
		assert rainfall_mm_72h >= 0, 'rainfall non-negative'
		try:
			at = datetime.fromisoformat(at_iso)
		except ValueError:
			raise AssertionError(f'{at_iso!r} is not an instant a reminder can be scheduled for') from None
		band = self._rainfall_band(rainfall_mm_72h)
		# The next dusk: biting is a dusk-to-dawn affair, so a reminder anchored at any other hour
		# is a reminder to do the thing at the wrong time of day.
		net_due = at.replace(hour=DUSK_HOUR, minute=0, second=0, microsecond=0)
		if net_due <= at:
			net_due += timedelta(days=1)
		container_due = at + timedelta(days=LARVICIDE_INTERVAL_FLOOR_DAYS)
		if band in ('wet', 'flood'):
			message = ('Rain has raised the mosquito risk here. Drain or cover every container holding '
			           'water, and sleep under your net tonight.')
		else:
			message = ('Low mosquito activity right now — the time to clear standing water and check '
			           'your net for holes, before the next rains.')
		return ProtectionReminder(
			county=county, rainfall_band=band,
			net_due_iso=net_due.isoformat(), container_due_iso=container_due.isoformat(),
			message=message,
		)

	@staticmethod
	def _rainfall_band(rainfall_mm_72h: float) -> str:
		"""The §MON-007 rain bands, in one place because two methods read them.

		`vector_risk` decided this inline and `protection_reminder` needs the same four bands; a
		second copy is a second definition, and the two would eventually disagree about where `wet`
		starts — which is the difference between "keep using your net" and "drain the containers
		now".
		"""
		if rainfall_mm_72h >= 100:
			return 'flood'
		if rainfall_mm_72h >= 50:
			return 'wet'
		return 'normal' if rainfall_mm_72h >= 10 else 'dry'

	def nutrition_guidance(self, age_months: int, month: int | None = None) -> NutritionGuidance:
		"""§MON-008's "infant feeding guidance" and "Seasonal food availability", together.

		The age band is the section's own, unchanged. What `month` adds is the second half of the
		`seasonal_foods` field, which had a name and no data behind it: the band's list is the foods
		appropriate to the age, and the month decides which of the *seasonal* foods are actually
		around. Passing no month returns the age list alone, which is what a caller with no calendar
		position can honestly be served — inventing a month would be answering a question nobody
		asked.

		The two lists are kept apart in the answer rather than merged. A merged list cannot say
		which entry is the age recommendation and which is the harvest, and the parent reading it is
		making two different decisions: what to feed this child, and what to buy this week.
		"""
		assert 0 <= age_months <= 60, 'paediatric nutrition range'
		band = max((row for row in NUTRITION_BY_AGE if row[0] <= age_months), key=lambda r: r[0])
		if month is None:
			return NutritionGuidance(age_months=age_months, guidance=band[1], seasonal_foods=list(band[2]))
		assert 1 <= month <= 12, f'{month} is not a month'
		in_season = sorted(
			label for label, _source_name, months, all_year in SEASONAL_FOODS
			if month in months or all_year
		)
		return NutritionGuidance(
			age_months=age_months, guidance=band[1], seasonal_foods=list(band[2]),
			month=month, in_season=in_season, calendar_source=SEASONAL_CALENDAR_SOURCE,
		)

	def therapeutic_feeding_centres(self, facilities: Any, county: str, lat: float, lon: float,
	                                limit: int = 5) -> list[TherapeuticFeedingSite]:
		"""§MON-008's "therapeutic feeding programme locations", over §FND-001's registry.

		The kind is `FacilityKind.therapeutic_feeding` and the vocabulary served with each site is
		Kenya's own IMAM programme set — `OTP`, `SC`, `SFP` — because this is the one bullet in the
		section that could *not* be sourced from OpenStreetMap: there is no OSM tag for a therapeutic
		feeding centre or a malnutrition treatment site. The research established that three ways
		(the `healthcare` key's 31 values, the `amenity` key's feeding values, which are all animal
		feeding, and a live taginfo search for `malnutrition` returning no structured keys), so a
		place-based vocabulary had no source at all while the national guideline has one.

		The programme *definitions* travel with every result rather than being asserted per site.
		The registry records that a facility is a therapeutic feeding site; it does not record which
		of the three programmes it runs, and a parent who took an out-patient programme's definition
		as this site's would bring a child with complications to a queue that cannot admit them. What
		the payload can honestly say is what the three programmes are, and that is what it says.

		An empty list is a county where nothing is filed, which is a real answer and a different one
		from "there is no such programme here" — so the caller gets the list and the log records the
		distinction. `facilities` is the `FacilityService`, typed loosely for the reason the feed port
		is: the two are wired at the composition root and this module does not import that class.
		"""
		assert limit >= 1, 'a finder returning nothing is not a finder'
		pool = [f for f in facilities.all_facilities()
		        if f.county == county and f.kind is FacilityKind.therapeutic_feeding]
		if not pool:
			self._log_info('no therapeutic feeding site filed', county=county)
			return []
		ranked = sorted(((f, haversine_km(lat, lon, f.lat, f.lon)) for f in pool), key=lambda p: p[1])
		return [
			TherapeuticFeedingSite(
				facility_id=f.facility_id, name=f.name, county=f.county,
				kind=f.kind.value, label=THERAPEUTIC_FEEDING_LABEL,
				distance_km=round(km, 1), level=f.level.value if f.level else None,
			)
			for f, km in ranked[:limit]
		]

	# --- MON-009 21-day contact monitoring ------------------------------------------------

	def enrol(self, subject_ref: str, officer: str | None = None, officer_number: str | None = None) -> HouseholdMonitor:
		"""Enrol a contact for 21 days; requires the outbreak event to be open (§11.1).

		A name without a number is accepted: the officer is assigned from a roster that may not have
		synced, and refusing enrolment over that would withhold the diary — the one thing a contact
		cannot wait for — to protect a contact detail. What a name without a number may not do is
		*present itself as a dialable line*; `monitoring_officer_line` is where that is decided.
		"""
		household = HouseholdMonitor(subject_ref=subject_ref, monitoring_officer=officer,
		                             monitoring_officer_number=officer_number)
		self._households[subject_ref] = household
		self._log_info('contact enrolled for monitoring', sub=subject_ref, officer=officer)
		return household

	async def log_day(self, entry: MonitoringDay) -> MonitoringVerdict:
		assert entry.subject_ref in self._households, 'not enrolled for monitoring'
		household = self._households[entry.subject_ref]
		# §MON-009's "location logging (with consent) to support contact tracing". The consent is the
		# household's recorded decision, not the entry's own `location_logged` boolean: a client that
		# set that flag true would be asserting the person's consent on their behalf, which is the
		# one thing a consent flag may never be. An entry claiming a location without consent is
		# refused rather than silently stored without it.
		if entry.location_logged:
			assert household.location_consent, (
				'location logging needs consent recorded against the household')
		# A member's day is filed against the member, and the contact's diary stays the contact's:
		# the predecessor accepted `household_member` and read nothing, so a member's fever counted
		# as the contact's and the member had no series of their own.
		if entry.household_member is not None:
			assert entry.household_member in household.members, (
				f'{entry.household_member} is not a member of this household')
		self._monitoring.append(entry)
		flagged = sorted(set(entry.symptoms) & MONITORING_ALERT_SYMPTOMS)
		fever = entry.temperature_c >= 38.0
		escalate = fever or bool(flagged)
		notify_chw = escalate and household.monitoring_officer is not None
		remaining = max(0, MONITORING_DAYS - entry.day)
		# Whose reading this is, named in the message. One household shares one diary, so "a fever was
		# recorded" without saying for whom is a message the contact has to decode — and the decode is
		# the moment they are least able to make it.
		who = f'for {entry.household_member}' if entry.household_member else 'for you'
		if escalate:
			reason = 'fever' if fever else ', '.join(flagged)
			message = (f'Day {entry.day}: {reason} recorded {who}. Call 719 now and await instructions '
			           '— do not travel by public transport.')
		else:
			message = (f'Day {entry.day} of {MONITORING_DAYS} logged {who}, no warning signs. '
			           f'{remaining} days to go.')
		if escalate:
			self._log_warn('monitoring escalation', sub=entry.subject_ref, day=entry.day)
		from afya.sensors.service import source_class
		reading = source_class(entry.source)
		return MonitoringVerdict(
			subject_ref=entry.subject_ref, day=entry.day, days_remaining=remaining,
			escalate=escalate, notify_chw=notify_chw, message=message,
			clinical_grade=reading.clinical_grade, reading_source=entry.source,
			support=support_resources(escalate),
		)

	def diary(self, subject_ref: str) -> list[MonitoringDay]:
		"""The contact's own 21-day window — entries filed *for* a household member excluded.

		A member's day is stored under the same `subject_ref` so the two live in one 21-day window,
		which is what "the same interface" means; leaving them in this list would put a household
		member's fever into the contact's own series, which is the predecessor's defect exactly — it
		accepted `household_member` and read nothing.
		"""
		return sorted([e for e in self._monitoring
		               if e.subject_ref == subject_ref and e.household_member is None],
		              key=lambda e: e.day)

	def member_diary(self, subject_ref: str, member_ref: str) -> list[MonitoringDay]:
		"""One household member's readings, from the same diary the contact's own are filed in.

		"The same interface" means one 21-day window with the member's days inside it — so the filter
		is on the member and the household is checked first, because a member of somebody else's
		household reading this would be served a diary they have no relationship to.
		"""
		household = self._households.get(subject_ref)
		assert household is not None, 'not enrolled for monitoring'
		assert member_ref in household.members, f'{member_ref} is not a member of this household'
		return sorted([e for e in self._monitoring
		               if e.subject_ref == subject_ref and e.household_member == member_ref],
		              key=lambda e: e.day)

	def remove_household_member(self, subject_ref: str, member_ref: str) -> HouseholdMonitor:
		household = self._households.get(subject_ref)
		assert household is not None, 'not enrolled for monitoring'
		assert member_ref in household.members, f'{member_ref} is not a member of this household'
		household.members.remove(member_ref)
		self._log_info('household member removed', sub=subject_ref, members=len(household.members))
		return household

	def add_household_member(self, subject_ref: str, member_ref: str) -> HouseholdMonitor:
		"""§MON-009's household monitoring. The member is monitored through the contact's diary.

		`member_ref` is a handle, not a name: the section says household members are monitored in the
		same interface, and the minimum that makes that true is an identifier the contact recognises.
		A name would put a second person's identity into a record kept for the first.
		"""
		household = self._households.get(subject_ref)
		assert household is not None, 'not enrolled for monitoring'
		assert member_ref and member_ref != subject_ref, 'a household member is somebody else'
		if member_ref not in household.members:
			household.members.append(member_ref)
		self._log_info('household member added', sub=subject_ref, members=len(household.members))
		return household

	def record_location_consent(self, subject_ref: str, granted: bool, at_iso: str) -> HouseholdMonitor:
		"""Record the contact's decision about location logging, and when they made it.

		Revocable in both directions, because consent that cannot be withdrawn is not consent. The
		timestamp is kept so a later reader can see the decision was made rather than assumed, and so
		a withdrawal is distinguishable from never having agreed.
		"""
		household = self._households.get(subject_ref)
		assert household is not None, 'not enrolled for monitoring'
		assert at_iso, 'a consent decision is dated'
		household.location_consent = granted
		household.location_consent_at_iso = at_iso
		self._log_info('location consent recorded', sub=subject_ref, granted=granted, at=at_iso)
		return household

	def reminders(self, subject_ref: str, day: int) -> MonitoringReminder:
		"""§MON-009's twice-daily reminders, derived from what was logged.

		The slots are the two a day has and a day is complete when both are in — which is what makes
		this checkable rather than a notification queue. §11.3's adherence design says reminders
		"escalate in urgency if missed", so the escalation is computed from the *window* and not only
		from today: a person who has missed four days needs a firmer message than one who has missed
		this morning, and a surface that only knows about today cannot tell them apart.
		"""
		assert 1 <= day <= MONITORING_DAYS, f'day {day} outside the 21-day window'
		done = self._slots_logged(subject_ref, day)
		missing = [s.value for s in REMINDER_SLOTS if s not in done]
		complete = not missing
		# Days with a *half* check-in count as missed. A ladder that only counts days with no entry
		# at all never fires for the person who logs every morning and forgets every evening, which
		# is the commonest way a 21-day diary is lost.
		missed_days = len([d for d in range(1, day + 1) if not self._day_complete(subject_ref, d)])
		if complete:
			escalation, message = 'none', f'Day {day} of {MONITORING_DAYS}: both check-ins logged.'
		elif missed_days >= 4:
			escalation = 'urgent'
			message = (f'{missed_days} day(s) without a full check-in. Please log now, or call 719 — '
			           'the diary only works if it is kept.')
		elif missed_days >= 2:
			escalation, message = 'firm', (f'{missed_days} day(s) missed. Log your temperature now and '
			                              'set a reminder for this evening.')
		else:
			escalation, message = 'gentle', f'Still to log today: {", ".join(missing)}.'
		return MonitoringReminder(subject_ref=subject_ref, day=day,
		                          due=[s.value for s in REMINDER_SLOTS], logged=[s.value for s in done],
		                          missing=missing, complete=complete, escalation=escalation, message=message)

	def _slots_logged(self, subject_ref: str, day: int) -> list[ReminderSlot]:
		"""Which of a day's two slots are in — the one place "complete" is decided.

		A slot counts as logged when an entry names it. When no entry names one — a client that
		predates the field, or a person logging without picking — the entries are assigned to the
		slots in order, because counting is the best a service can do without being told. Only the
		contact's own entries count: a member's morning does not discharge the contact's, and a
		household of five could otherwise keep one person's diary complete for them.
		"""
		entries = [e for e in self._monitoring
		           if e.subject_ref == subject_ref and e.day == day and e.household_member is None]
		named = {e.slot for e in entries if e.slot is not None}
		if named:
			return sorted(named, key=REMINDER_SLOTS.index)
		return list(REMINDER_SLOTS[:len(entries)])

	def _day_complete(self, subject_ref: str, day: int) -> bool:
		"""Whether both of a day's slots are in — the unit §MON-009's reminders escalate on."""
		return set(REMINDER_SLOTS) <= set(self._slots_logged(subject_ref, day))

	def monitoring_officer_line(self, subject_ref: str) -> dict[str, str]:
		"""§MON-009's "direct line to the assigned monitoring officer".

		When no officer is assigned this says so rather than serving an empty line: a person told to
		call their officer and given no number will wait, and waiting is the one thing a contact under
		monitoring cannot do. The fallback is 719, which is staffed.
		"""
		household = self._households.get(subject_ref)
		assert household is not None, 'not enrolled for monitoring'
		if household.monitoring_officer and household.monitoring_officer_number:
			return {'assigned': 'True', 'officer': household.monitoring_officer,
			        'line': f'tel:{household.monitoring_officer_number}',
			        'message': f'Your monitoring officer is {household.monitoring_officer}. Call them first for anything about your monitoring.'}
		if household.monitoring_officer:
			# Named but not dialable: the honest answer names the officer *and* gives the line that
			# will actually be answered, rather than a screen with a name and a dead button.
			return {'assigned': 'True', 'officer': household.monitoring_officer, 'line': 'tel:719',
			        'message': f'Your monitoring officer is {household.monitoring_officer}, but their direct number has not reached the app yet. Call 719 — it is staffed — and ask for them by name.'}
		return {'assigned': 'False', 'officer': '', 'line': 'tel:719',
		        'message': 'No monitoring officer is assigned to you yet. Call 719 — it is staffed — and say you are on a 21-day contact diary.'}

	def adherence_reminder_days(self, subject_ref: str) -> list[int]:
		"""Days in the 21-day window with no entry — the adherence surface (§11.3 escalation).

		The contact's own days only. A household member's reading filed under the same window is not
		the contact's check-in, so counting it would report a diary as kept on the strength of
		somebody else's temperature.
		"""
		logged = {e.day for e in self._monitoring
		          if e.subject_ref == subject_ref and e.household_member is None}
		missing = [d for d in range(1, MONITORING_DAYS + 1) if d not in logged]
		assert len(missing) <= MONITORING_DAYS, 'window bounded'
		return missing
