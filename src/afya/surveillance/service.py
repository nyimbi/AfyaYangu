"""Surveillance service — signal aggregation, geofence registry, PHEOC activation gate, append-only PET store."""
import statistics

from afya.logmixin import LogMixin
from afya.registry.service import FeatureRegistry
from afya.surveillance.views import CountySignal, Geofence, ProximityToken, SignalReading


def _risk_band(z: float) -> str:
	if z >= 2.5:
		return 'high'
	if z >= 1.5:
		return 'moderate'
	return 'low'


class SurveillanceService(LogMixin):
	def __init__(self, registry: FeatureRegistry) -> None:
		self._registry = registry
		self._tokens: list[ProximityToken] = []
		self._geofences: list[Geofence] = []
		assert self._tokens == [] and self._geofences == []

	async def ingest_token(self, token: ProximityToken) -> None:
		assert len(token.token) >= 32, 'PET minimum entropy'
		self._tokens.append(token)
		self._tokens = self._tokens[-100_000:]
		assert len(self._tokens) <= 100_000, 'token store bounded'

	def tokens_exposure_check(self, own_tokens: list[str], window_ms: int, now_ms: int) -> int:
		assert window_ms > 0 and now_ms > 0, 'window/now positive'
		own = set(own_tokens)
		return len([t for t in self._tokens if t.token in own and now_ms - t.seen_at_ms <= window_ms])

	async def activate_tier4(self, authorized_by_pheoc: bool, dpia_reviewed: bool, flag_enabled: bool, bulletin: str | None = None) -> bool:
		from afya.registry.service import Tier4Activation
		activation = Tier4Activation(authorized_by_pheoc=authorized_by_pheoc, dpia_reviewed=dpia_reviewed, flag_enabled=flag_enabled, bulletin_text=bulletin)
		self._registry.__init__(activation)
		active = self._registry.tier4_active()
		self._log_warn('tier4 gate evaluated', active=active)
		return active

	async def set_geofence(self, fence: Geofence) -> Geofence:
		assert fence.risk_type == 'outbreak' or fence.alert_level != 'high', 'high alert only for outbreak geofences'
		self._geofences.append(fence)
		return fence

	def geofences_at(self, lat: float, lon: float) -> list[Geofence]:
		import math
		def inside(f: Geofence) -> bool:
			dx = 111_320.0 * (f.lon - lon) * math.cos(math.radians(lat))
			dy = 110_574.0 * (f.lat - lat)
			return (dx * dx + dy * dy) ** 0.5 <= f.radius_m
		return [f for f in self._geofences if inside(f)]

	def weekly_signal(self, history: list[CountySignal]) -> SignalReading:
		assert history, 'no signal history'
		county = history[0].county
		assert all(h.county == county for h in history), 'single-county aggregation'
		primary = [h.fever_reports for h in history]
		base = primary[:-1] or primary
		mean = statistics.fmean(base)
		stdev = statistics.pstdev(base) or 1.0
		z = (primary[-1] - mean) / stdev
		risk = _risk_band(z)
		self._log_info('weekly signal', county=county, z=round(z, 2))
		return SignalReading(county=county, z_score=round(z, 2), risk=risk, weeks_observed=len(history))