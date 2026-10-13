"""Community alerts service — issuance, flood→cholera linkage, school closures, water/air advisories."""
from afya.alerts.views import (
	SERVICE_STATUS_KINDS, AirQuality, AlertKind, CommunityAlert, FloodReport, ServiceStatus,
	WaterQuality,
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