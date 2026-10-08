import pytest

from afya.registry.service import FeatureRegistry, Tier4Activation
from afya.sensors.service import SensorService, cough_band, ppg_band, resp_band
from afya.sensors.views import SenseIngest, SenseKind


@pytest.fixture
def svc() -> SensorService:
	return SensorService(FeatureRegistry())


def test_respiration_bands() -> None:
	assert resp_band(16).band == 'normal'
	out = resp_band(9.0)
	assert out.anomaly and out.band == 'alert' and '12-25' in out.detail


def test_cough_bands() -> None:
	assert cough_band(5).band == 'normal'
	assert cough_band(18).band == 'watch'
	assert cough_band(31).band == 'alert'


def test_ppg_bands() -> None:
	assert ppg_band(72).band == 'normal'
	assert ppg_band(50).band == 'watch'
	assert ppg_band(140).band == 'alert'


async def test_fall_not_tier4_gated(svc: SensorService) -> None:
	v = await svc.ingest(SenseIngest(kind=SenseKind.fall, subject_ref='U1', value=5.5, county='Nairobi'))
	assert v.anomaly


async def test_tier4_dormant_rejects_respiration(svc: SensorService) -> None:
	with pytest.raises(PermissionError):
		await svc.ingest(SenseIngest(kind=SenseKind.respiration, subject_ref='U1', value=30.0, county='Nairobi'))


async def test_tier4_active_accepts_respiration() -> None:
	reg = FeatureRegistry(Tier4Activation(authorized_by_pheoc=True, dpia_reviewed=True, flag_enabled=True))
	svc = SensorService(reg)
	v = await svc.ingest(SenseIngest(kind=SenseKind.respiration, subject_ref='U1', value=30.0, county='Nairobi'))
	assert v.anomaly and v.band == 'alert'
	assert len(svc.history()) == 1


def test_raw_fields_structurally_rejected() -> None:
	from pydantic import ValidationError
	with pytest.raises(ValidationError):
		SenseIngest.model_validate({'kind': 'respiration', 'subject_ref': 'U1', 'value': 16, 'county': 'N', 'depth': [1.0, 2.0]})

def test_breath_rate_estimation() -> None:
	import math as _m
	from afya.surveillance.service import estimate_breath_rate
	fps = 30.0
	# 16 bpm -> 3.75 s period over 8 s
	series = [1.0 * _m.sin(2 * 3.14159 * 16 / 60 * t / fps) for t in range(240)]
	rate = estimate_breath_rate(series, fps)
	assert 13 <= rate <= 19
	series_fast = [1.0 * _m.sin(2 * 3.14159 * 24 / 60 * t / fps) for t in range(240)]
	rate_fast = estimate_breath_rate(series_fast, fps)
	assert 20 <= rate_fast <= 28
