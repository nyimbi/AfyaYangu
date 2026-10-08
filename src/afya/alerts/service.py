"""Community alerts service — issuance, flood→cholera linkage, school closures, water/air advisories."""
from afya.alerts.views import AirQuality, AlertKind, CommunityAlert, FloodReport, WaterQuality
from afya.logmixin import LogMixin


class AlertsService(LogMixin):
	def __init__(self) -> None:
		self._alerts: dict[str, CommunityAlert] = {}
		self._latest: dict[str, str] = {}  # county+kind -> latest alert id
		assert self._alerts == {} and self._latest == {}

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