import pytest


from afya.registry.service import FeatureRegistry, Tier4Activation
from afya.surveillance.service import SurveillanceService
from afya.surveillance.views import CountySignal, Geofence, ProximityToken


async def test_token_ingest_bounded() -> None:
	svc = SurveillanceService(FeatureRegistry())
	await svc.ingest_token(ProximityToken(token='a' * 32, seen_at_ms=1000, county='Nairobi'))
	assert svc.tokens_exposure_check(['a' * 32], window_ms=3600_000, now_ms=2000) == 1
	assert svc.tokens_exposure_check([], window_ms=3600_000, now_ms=2000) == 0


async def test_weekly_signal_zscore() -> None:
	svc = SurveillanceService(FeatureRegistry())
	hist = [CountySignal(county='Busia', week_isoyear=2026, week=w, fever_reports=10, hotline_calls=5, confirmed_cases=0) for w in range(1, 9)]
	r = svc.weekly_signal(hist)
	assert r.risk == 'low' and abs(r.z_score) < 1.0
	spiked = hist[:-1] + [CountySignal(county='Busia', week_isoyear=2026, week=9, fever_reports=50, hotline_calls=5, confirmed_cases=0)]
	assert svc.weekly_signal(spiked).risk == 'high'


async def test_geofence_alert_semantics() -> None:
	svc = SurveillanceService(FeatureRegistry())
	await svc.set_geofence(Geofence(geofence_id='G1', lat=-1.28, lon=36.82, radius_m=10_000, risk_type='general', alert_level='medium'))
	with pytest.raises(AssertionError):
		await SurveillanceService(FeatureRegistry()).set_geofence(Geofence(geofence_id='G2', lat=-1.28, lon=36.82, radius_m=10_000, risk_type='general', alert_level='high'))
	await svc.set_geofence(Geofence(geofence_id='G3', lat=-1.28, lon=36.82, radius_m=5_000, risk_type='outbreak', alert_level='high'))
	assert len(svc.geofences_at(-1.29, 36.81)) == 2
	assert svc.geofences_at(0.0, 34.0) == []


async def test_activation_gate_via_surveillance() -> None:
	reg = FeatureRegistry()
	svc = SurveillanceService(reg)
	assert not await svc.activate_tier4(False, True, True)
	assert await svc.activate_tier4(True, True, True, bulletin='PHEOC trigger')
	assert reg.tier4_active()