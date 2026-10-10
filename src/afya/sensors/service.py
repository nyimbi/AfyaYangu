"""Sensor service — tier4-gated derived-metric ingestion + deterministic band engines.

The on-device engines (mobile clients) implement the same bands; server-side is the
surveillance aggregation surface. Raw payloads are rejected structurally by model
config (extra='forbid') — only derived values pass.
"""
from afya.logmixin import LogMixin
from afya.registry.service import FeatureRegistry, Tier
from afya.sensors.views import SenseIngest, SenseKind, SenseVerdict


def resp_band(rate: float) -> SenseVerdict:
	assert 0 <= rate <= 300, 'derived rate bounds'
	if rate < 12 or rate > 25:
		return SenseVerdict(kind=SenseKind.respiration, anomaly=True, band='alert', detail=f'rate {rate} outside 12-25 br/min')
	return SenseVerdict(kind=SenseKind.respiration, anomaly=False, band='normal', detail=f'rate {rate} in range')


def cough_band(per_hour: float) -> SenseVerdict:
	if per_hour >= 30:
		return SenseVerdict(kind=SenseKind.cough, anomaly=True, band='alert', detail=f'{per_hour}/h sustained cough load')
	if per_hour >= 15:
		return SenseVerdict(kind=SenseKind.cough, anomaly=True, band='watch', detail=f'{per_hour}/h elevated')
	return SenseVerdict(kind=SenseKind.cough, anomaly=False, band='normal', detail=f'{per_hour}/h baseline')


def ppg_band(hr: float) -> SenseVerdict:
	assert hr >= 0, 'hr bounds'
	if hr < 45 or hr > 120:
		return SenseVerdict(kind=SenseKind.ppg, anomaly=True, band='alert', detail=f'hr {hr} outside 45-120')
	if hr < 55 or hr > 100:
		return SenseVerdict(kind=SenseKind.ppg, anomaly=True, band='watch', detail=f'hr {hr} borderline')
	return SenseVerdict(kind=SenseKind.ppg, anomaly=False, band='normal', detail=f'hr {hr} in range')


def sleep_band(hours: float) -> SenseVerdict:
	if hours < 5.5:
		return SenseVerdict(kind=SenseKind.sleep, anomaly=True, band='watch', detail=f'{hours}h short sleep')
	return SenseVerdict(kind=SenseKind.sleep, anomaly=False, band='normal', detail=f'{hours}h within target')


def ambient_band(pm25: float) -> SenseVerdict:
	if pm25 > 55.0:
		return SenseVerdict(kind=SenseKind.ambient, anomaly=True, band='alert', detail=f'PM2.5 {pm25} µg/m³ hazardous')
	if pm25 > 35.0:
		return SenseVerdict(kind=SenseKind.ambient, anomaly=True, band='watch', detail=f'PM2.5 {pm25} µg/m³ elevated')
	return SenseVerdict(kind=SenseKind.ambient, anomaly=False, band='normal', detail=f'PM2.5 {pm25} µg/m³ ok')


_ENGINES = {SenseKind.respiration: resp_band, SenseKind.cough: cough_band, SenseKind.ppg: ppg_band, SenseKind.fall: lambda v: SenseVerdict(kind=SenseKind.fall, anomaly=v > 4.0, band='alert' if v > 4.0 else 'normal', detail=f'g-force {v}'), SenseKind.sleep: sleep_band, SenseKind.ambient: ambient_band}


_INGEST_FEATURE: dict[SenseKind, str] = {
	SenseKind.respiration: 'SENS-001',
	SenseKind.cough: 'SENS-002',
	SenseKind.fall: 'SENS-003',
	SenseKind.ppg: 'SENS-005',
	SenseKind.sleep: 'SENS-007',
	SenseKind.ambient: 'SENS-008',
}


class SensorService(LogMixin):
	def __init__(self, registry: FeatureRegistry) -> None:
		self._registry = registry
		self._history: list[SenseIngest] = []
		assert self._history == []

	async def ingest(self, inp: SenseIngest) -> SenseVerdict:
		feat = self._registry.get(_INGEST_FEATURE[inp.kind])
		if feat.tier is Tier.tier4 and not self._registry.tier4_active():
			# Refusal text a person may read: no spec code, no tier number.
			raise PermissionError(f'{inp.kind.value} sensing opens when the outbreak response is activated')
		verdict = _ENGINES[inp.kind](inp.value)
		self._history.append(inp)
		self._history = self._history[-10_000:]
		assert len(self._history) <= 10_000, 'ingest history bounded'
		self._log_info('sense ingested', kind=inp.kind.value, band=verdict.band)
		return verdict

	def history(self) -> list[SenseIngest]:
		return list(self._history)