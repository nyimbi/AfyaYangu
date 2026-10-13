"""Community alerts service — issuance, flood→cholera linkage, school closures, water/air advisories."""

# §MON-005's "point-of-use treatment reminders": how long treated water keeps, and therefore how
# often the reminder is due. WHO's brief ends the boiling method with "allowed to cool naturally ...
# and protected from post-treatment recontamination during storage", and the storage guidance says a
# day; a reminder on a longer interval would remind a household to drink water that has stood too
# long, which is the failure the storage step exists to prevent.
REMINDER_INTERVAL_HOURS = 24
from afya.alerts.views import (
	CHLORINE_TURBIDITY_LIMIT_NTU, SERVICE_STATUS_KINDS, TREATMENT_CAVEATS, TREATMENT_STEPS,
	AirQuality, AlertKind, CommunityAlert, FloodReport, ServiceStatus, StorageGuidance,
	TreatmentGuidance, TreatmentMethod, TreatmentReminder, WaterQuality, WaterSafety,
)
from afya.alerting.views import FeedItem
from afya.logmixin import LogMixin


class AlertsService(LogMixin):
	def __init__(self) -> None:
		self._alerts: dict[str, CommunityAlert] = {}
		self._latest: dict[str, str] = {}  # county+kind -> latest alert id
		self._statuses: list[ServiceStatus] = []
		assert self._alerts == {} and self._latest == {} and self._statuses == []

	async def issue(self, alert: CommunityAlert) -> CommunityAlert:
		assert alert.headline and alert.body, 'alert content required'
		if alert.kind.value.startswith('outbreak_'):
			assert alert.issued_by in ('PHEOC', 'MoH', 'County'), 'outbreak alerts require official issue'
		self._alerts[alert.alert_id] = alert
		self._latest[f'{alert.county}:{alert.kind.value}'] = alert.alert_id
		self._log_warn('community alert issued', kind=alert.kind.value, county=alert.county)
		return alert

	def by_county(self, county: str) -> list[CommunityAlert]:
		return [self._alerts[i] for k, i in self._latest.items() if k.startswith(county + ':')]

	def school_notices(self, county: str) -> list[CommunityAlert]:
		return [a for a in self._alerts.values() if a.county == county and a.kind.value == 'school_closure']

	# --- §9.5 INF-007 service status feed -------------------------------------------------

	async def publish_status(self, status: ServiceStatus, feed: object) -> ServiceStatus:
		"""§INF-007's status, published into the alert feed it is read from.

		The section names six Contents and the tree produced none of them: `/alerting/service-status`
		filtered the feed's `service` category and no code ever wrote one, so the screen answered zero
		however many closures a county had. This is the producer.

		It publishes rather than only storing, because the two surfaces are one fact. A market closure
		a reader finds on the status screen and an alert about the same market arriving on their phone
		are the same event, and a status that lived only in `_statuses` would make them two — which is
		the "published twice and read as two events" failure the status route's own docstring names.
		The feed is written first and `_statuses` second, so the list is a view of what was published
		rather than a second store that can disagree with it.

		`feed` is the `AlertingService`, typed loosely for the reason every cross-module port here is:
		the two are wired at the composition root and neither imports the other's class.
		"""
		publish = getattr(feed, 'publish', None)
		if publish is not None:
			# §ALT-001's Verification clause is the rule that governs this feed, so an unverified
			# status is refused by the feed rather than by a second copy of the rule written here.
			await publish(FeedItem(
				item_id=f'SS-{status.status_id}', category='service', county=status.county,
				headline=status.headline, body=status.body, source=status.source,
				verified=status.verified, published_iso=status.effective_iso))
		self._statuses.append(status)
		self._log_info('service status published', kind=status.kind, county=status.county,
		               state=status.state)
		return status

	def service_status(self, county: str | None = None) -> list[ServiceStatus]:
		"""The current status per place, newest first. A place's later status supersedes its earlier.

		Keyed on `(kind, name)` rather than returned as a log: a market that was closed and has
		reopened has *one* status — open — and a screen that listed both would make a reader work out
		which is current from two dates. The feed keeps both, because a feed is a record of what was
		announced; this is the answer to "can I go there today".
		"""
		latest: dict[tuple[str, str], ServiceStatus] = {}
		for s in self._statuses:
			if county is None or s.county == county:
				latest[(s.kind, s.name)] = s
		return sorted(latest.values(), key=lambda s: s.effective_iso, reverse=True)

	def status_coverage(self) -> dict[str, int]:
		"""§INF-007's six Contents and how many current statuses each carries.

		The same question §INF-006's `absent` answers for the directory, and the reason it is served:
		a deployment that has no road-closure feed should say so on the screen rather than render a
		section that is empty because nobody publishes it.
		"""
		counts = {k: 0 for k in SERVICE_STATUS_KINDS}
		for s in self.service_status():
			counts[s.kind] += 1
		return counts

	def water_alert(self, w: WaterQuality) -> str:
		assert 0 <= w.turbidity_ntu <= 400, 'turbidity bounds'
		if w.unsafe:
			return f'WATER ADVISORY ({w.county}): do not drink without boiling — {"E. coli detected" if w.ecoli_detected else f"turbidity {w.turbidity_ntu:.0f} NTU"}.'
		return f'Water normal for {w.county}.'

	def treatment_guidance(self, w: WaterQuality) -> TreatmentGuidance:
		"""§MON-005's "treatment guidance", as the methods this reading permits.

		Boiling is always offered and is listed first, because WHO's brief calls it "highly
		efficacious, killing human pathogens even in turbid water and at high altitude" — it is the
		one method with no condition attached, which is why it is the one the advisory names.

		Chlorination is offered only when the water is clear enough for it. WHO's Round II
		evaluation states the tested products "should only be used in nonturbid water (<5 NTU)", so
		recommending chlorine on a turbid reading would be recommending it outside the conditions it
		was evaluated in — and the failure is silent: the household doses the water, waits, and
		drinks water that was never disinfected because the turbidity consumed the chlorine.
		"""
		methods = [TreatmentMethod.boil]
		if w.turbidity_ntu <= CHLORINE_TURBIDITY_LIMIT_NTU:
			methods.append(TreatmentMethod.chlorinate)
		methods.extend([TreatmentMethod.filter, TreatmentMethod.solar])
		return TreatmentGuidance(
			county=w.county,
			methods=methods,
			steps=[step for m in methods for step in TREATMENT_STEPS[m]],
			caveats=[TREATMENT_CAVEATS[m] for m in methods],
		)

	def storage_guidance(self, w: WaterQuality, method: TreatmentMethod) -> StorageGuidance:
		"""§MON-005's "safe storage guidance", with the residual the method can leave behind.

		The steps are the boiling brief's own ending — WHO: after a rolling boil the water should be
		"allowed to cool naturally, without the addition of ice, and protected from post-treatment
		recontamination during storage" — plus the two things a household can actually check: a
		covered container, and a tap or a pour rather than a dipped cup.

		The residual figure is carried only for a chlorinated supply, because it is the one method
		that leaves protection behind: WHO's brief states ">=0.5 mg/L after 30 minutes of contact
		time, or >=0.2 mg/L in stored household water". Boiled water has no such number, and a field
		holding one for it would be a figure a reader could not act on.
		"""
		steps = [
			'Keep treated water in a clean container with a lid; never in the one you collected it in.',
			'Pour or use a tap. Do not dip a cup into it — that is how a clean supply is contaminated.',
			'Drink it within a day. Water that has stood for longer should be treated again.',
		]
		if method is TreatmentMethod.chlorinate:
			steps.append(
				'Chlorinated water should still smell faintly of chlorine. If it does not, the '
				'protection is gone — treat it again.'
			)
		return StorageGuidance(
			county=w.county, steps=steps,
			residual_chlorine_mg_l=0.2 if method is TreatmentMethod.chlorinate else None,
		)

	def treatment_reminder(self, w: WaterQuality, method: TreatmentMethod, at_iso: str) -> TreatmentReminder:
		"""§MON-005's "point-of-use treatment reminders", as an instant the device schedules.

		`at_iso` is the time the household treats water, and it is supplied rather than assumed: a
		household that boils in the morning and one that boils at night need different reminders,
		and a service that picked a time would be reminding people who are asleep. The interval
		until the next one is the storage guidance's own "drink it within a day" — a reminder that
		fired less often than the water keeps would be a reminder to drink water that has gone off.
		"""
		from datetime import datetime, timedelta
		try:
			at = datetime.fromisoformat(at_iso)
		except ValueError:
			raise AssertionError(f'{at_iso!r} is not an instant a reminder can be scheduled for') from None
		next_due = at + timedelta(hours=REMINDER_INTERVAL_HOURS)
		return TreatmentReminder(
			county=w.county, due_iso=next_due.isoformat(), method=method,
			message=f'Treat today\'s drinking water ({method.value}) — and keep it covered.',
		)

	def water_safety(self, w: WaterQuality, treated_at_iso: str | None = None) -> WaterSafety:
		"""§MON-005's five Features as one answer: the reading, the advisory, and what to do about it.

		The advisory string is `water_alert`'s, not a second copy — the same fact on two surfaces, and
		a second wording would be the one that drifts. The method the guidance leads with is the one
		the storage guidance and the reminder are then built from, so a notice cannot recommend
		boiling and hand out a chlorine residual figure.
		"""
		guidance = self.treatment_guidance(w)
		# The lead method is the one the reminder is bound to, because a reminder is about what this
		# household actually does; the others are offered with their own storage blocks and no
		# schedule, since the server has been told nothing about them.
		method = guidance.methods[0]
		return WaterSafety(
			county=w.county, unsafe=w.unsafe, advisory=self.water_alert(w),
			treatment=guidance,
			storage=[self.storage_guidance(w, m) for m in guidance.methods],
			reminder=self.treatment_reminder(w, method, treated_at_iso) if treated_at_iso else None,
		)

	@staticmethod
	def air_alert(a: AirQuality) -> str:
		assert 0 <= a.pm25 <= 500, 'pm25 bounds'
		if a.band == 'alert':
			return f'AIR ALERT ({a.county}): PM2.5 {a.pm25:.0f} — limit outdoor exertion; masks for sensitive groups.'
		if a.band == 'watch':
			return f'Air elevated ({a.county}): PM2.5 {a.pm25:.0f} — sensitive groups take care.'
		return f'Air quality normal for {a.county}.'

	async def flood_alert(self, f: FloodReport) -> tuple[str, str]:
		assert f.rainfall_mm_72h >= 0, 'rainfall non-negative'
		if f.cholera_risk == 'high':
			await self.issue(CommunityAlert(
				alert_id=f'AL-FLOOD{abs(hash((f.county, int(f.rainfall_mm_72h)))) % 10 ** 8:08d}',
				kind=AlertKind.outbreak_cholera, county=f.county,
				headline='Flood-driven cholera risk', body='Boil drinking water. Report diarrhoea clusters to 719.',
				issued_by='County',
			))
			return f'FLOOD ALERT ({f.county}): {f.rainfall_mm_72h:.0f} mm/72h — avoid floodwater; cholera risk HIGH.', 'high'
		return f'Flood monitoring ({f.county}): {f.rainfall_mm_72h:.0f} mm/72h, cholera risk {f.cholera_risk}.', f.cholera_risk