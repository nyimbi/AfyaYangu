"""Surveillance service — signal aggregation, geofence registry, PHEOC activation gate, append-only PET store."""
import statistics
from typing import Any

from afya.logmixin import LogMixin
from afya.registry.service import FeatureRegistry
from afya.surveillance.views import CountySignal, Geofence, ProximityToken, SignalReading


def _risk_band(z: float) -> str:
	if z >= 2.5:
		return 'high'
	if z >= 1.5:
		return 'moderate'
	return 'low'


def estimate_breath_rate(series: list[float], fps: float = 30.0) -> float:
	"""LiDAR chest-motion series (derived on-device) -> breaths/min by peak counting (§14.1).
	Accepts the variance/motion series only — never raw depth frames (§17.2)."""
	assert 0.5 <= fps <= 120, 'capture fps bounds'
	assert 30 <= len(series) <= 6000, 'need a window >= 1 s'
	mean = sum(series) / len(series)
	centered = [v - mean for v in series]
	window = int(fps * 1.5)  # >= 1.5 s of motion context for peak counting
	peaks = 0
	for i in range(1, len(centered) - 1):
		lo = centered[max(0, i - window):i]
		hi = centered[i + 1:i + 1 + window]
		if centered[i] > 0 and (not lo or centered[i] >= max(lo)) and (not hi or centered[i] > max(hi)):
			peaks += 1
	seconds = len(series) / fps
	rate = 60.0 * peaks / seconds
	assert 0 < rate < 200, 'estimate in plausible envelope'
	return round(rate, 1)


class SurveillanceService(LogMixin):
	def __init__(self, registry: FeatureRegistry, privacy: Any | None = None) -> None:
		self._registry = registry
		self._privacy = privacy  # §24.7: the DPO's DPIA is the key this gate reads, not a boolean
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

	def assess_tier4(self, inp: Any) -> Any:
		"""The DPIA for the activation being requested. §24.7 puts the DPIA before each Tier-4
		activation, and the risk the gate exists for is the one `raw_sensor_data_retained` names —
		so the flag is read from the assessment, not asserted by the caller."""
		return self._privacy.assess_dpia(inp) if self._privacy is not None else None

	async def activate_tier4(self, authorized_by_pheoc: bool, dpia_reviewed: bool, flag_enabled: bool, bulletin: str | None = None, dpia: Any | None = None) -> bool:
		from afya.registry.service import Tier4Activation
		if dpia is not None and getattr(dpia, 'blocked', False):
			# A blocked DPIA is not "reviewed": §17.2's data-minimisation violation cannot be
			# acknowledged away by a caller passing dpia_reviewed=True alongside it.
			dpia_reviewed = False
		activation = Tier4Activation(authorized_by_pheoc=authorized_by_pheoc, dpia_reviewed=dpia_reviewed, flag_enabled=flag_enabled, bulletin_text=bulletin)
		self._registry.activate(activation)
		active = self._registry.tier4_active()
		self._log_warn('tier4 gate evaluated', active=active, unmet=activation.unmet_keys())
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

	def weekly_signal(self, history: list[CountySignal], disease: str | None = None) -> SignalReading:
		assert history, 'no signal history'
		disease = disease or history[0].disease
		assert all(h.disease == disease for h in history), 'single-disease aggregation'
		county = history[0].county
		assert all(h.county == county for h in history), 'single-county aggregation'
		primary = [h.fever_reports for h in history]
		base = primary[:-1] or primary
		mean = statistics.fmean(base)
		stdev = statistics.pstdev(base) or 1.0
		z = (primary[-1] - mean) / stdev
		risk = _risk_band(z)
		self._log_info('weekly signal', county=county, disease=disease, z=round(z, 2))
		return SignalReading(county=county, z_score=round(z, 2), risk=risk, weeks_observed=len(history), disease=disease)
