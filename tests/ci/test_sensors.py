import pytest
from pydantic import ValidationError
from typing import Any

from afya.registry.service import FeatureRegistry, Tier4Activation
from afya.sensors.service import HANDLING, SENSORS, SensorService, cough_band, ppg_band, resp_band
from afya.sensors.views import (
	Availability, BatteryCost, SenseIngest, SenseKind, Sensitivity, SensorSpec,
)


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


# --- §13.1 the capability matrix ------------------------------------------------------------

def test_the_matrix_has_every_spec_row() -> None:
	"""§13.1 is eighteen rows. Each carries the availability §13.1 gives it on both platforms, so a
	row that gained a capability nobody can use would show up here."""
	assert len(SENSORS) == 18
	assert len({s.slug for s in SENSORS}) == 18, 'sensor slugs must be unique'
	by_slug = {s.slug: s for s in SENSORS}
	assert by_slug['gps'].android is Availability.all and by_slug['gps'].ios is Availability.all
	assert by_slug['lidar'].android is Availability.select, '§13.1: select Android flagships only'
	assert by_slug['lidar'].ios is Availability.some, '§13.1: iPhone Pro / iPad Pro'
	assert by_slug['thermometer'].ios is Availability.none, '§13.1 gives iOS no thermometer'
	assert by_slug['heart_rate'].ios is Availability.none


def test_the_sensitivity_column_is_carried_per_sensor() -> None:
	"""The column §17.2's minimisation rule is enforced from. §13.1 marks location, the microphone
	and the rear camera High; Bluetooth and the front camera Medium; the rest Low."""
	by_slug = {s.slug: s for s in SENSORS}
	high = sorted(s.slug for s in SENSORS if s.sensitivity is Sensitivity.high)
	assert high == ['camera_rear', 'gps', 'microphone']
	assert by_slug['bluetooth'].sensitivity is Sensitivity.medium
	assert by_slug['camera_front'].sensitivity is Sensitivity.medium
	assert by_slug['lidar'].sensitivity is Sensitivity.low and by_slug['lidar'].derived_only


def test_a_derived_only_sensor_cannot_be_high_sensitivity() -> None:
	"""Canary at the model. §13.1 writes LiDAR's class as "Low (derived only)" — if the raw stream is
	discarded immediately there is nothing left but the derived metric, so a row claiming both
	derived-only and High is describing two different things."""
	with pytest.raises(ValidationError, match='discards raw data'):
		SensorSpec(slug='x', name='X', android=Availability.all, ios=Availability.all, used_for='y',
		           sensitivity=Sensitivity.high, derived_only=True, battery=BatteryCost.low)


def test_a_retention_cap_on_a_low_sensitivity_sensor_is_refused() -> None:
	"""§14.1/LOC-003 gives location a 21-day rolling window because it is High. A cap on a sensor
	that carries nothing about a person would be a rule with nothing to protect."""
	with pytest.raises(ValidationError, match='carries a retention cap'):
		SensorSpec(slug='x', name='X', android=Availability.all, ios=Availability.all, used_for='y',
		           sensitivity=Sensitivity.low, battery=BatteryCost.low, retention_days=21)


def test_no_class_ever_permits_retaining_a_raw_stream() -> None:
	"""§17.2: "Raw sensor data is never retained." SEC-002: it never leaves the device. The rule is
	stated once per class so it is computed rather than restated, and every class must say never."""
	svc = SensorService(FeatureRegistry())
	assert svc.raw_streams_retained() == []
	assert all(h.raw_may_be_retained is False for h in HANDLING)
	assert len(HANDLING) == 3, 'one handling row per sensitivity class'


def test_high_sensitivity_capture_needs_consent_and_low_does_not() -> None:
	"""§17.4 consent: asking a user to consent to a barometer reading is consent theatre, and not
	asking about their location is the failure §23's privacy risks name."""
	svc = SensorService(FeatureRegistry())
	assert svc.handling(Sensitivity.high).capture_requires_consent is True
	assert svc.handling(Sensitivity.medium).capture_requires_consent is True
	assert svc.handling(Sensitivity.low).capture_requires_consent is False


def test_every_absence_prone_sensor_has_a_fallback() -> None:
	"""§13.1 and §13.2 are one promise: a sensor that can be absent and has no fallback excludes a
	user, which is the principle §13.2 states outright. The two tables live in different modules,
	which is exactly how they can drift."""
	svc = SensorService(FeatureRegistry())
	assert svc.absent_on('android') and svc.absent_on('ios')
	assert svc.missing_fallbacks() == [], 'a §13.1 sensor with no §13.2 fallback'


def test_the_fallback_cross_check_can_actually_report_a_gap() -> None:
	"""Canary for the cross-check: it is only ever seen returning [], which is what a check that
	cannot fail looks like. Drive it with a sensor that carries a feature, can be absent, and is
	named by neither §13.2 nor the alias table — the shape it is meant to catch."""
	from afya.access.service import SENSOR_FALLBACKS
	orphan = SensorSpec(slug='spectrometer', name='Spectrometer', android=Availability.rare,
	                    ios=Availability.none, primary_features=['SENS-099'], used_for='x',
	                    sensitivity=Sensitivity.medium, battery=BatteryCost.low)
	patched = SensorService(FeatureRegistry())
	import afya.sensors.service as mod
	original = mod.SENSORS
	mod.SENSORS = (*original, orphan)
	try:
		assert patched.missing_fallbacks() == ['spectrometer']
	finally:
		mod.SENSORS = original
	# And the real table is clean, so the canary above is what makes the [] meaningful.
	assert patched.missing_fallbacks() == [] and SENSOR_FALLBACKS


def test_an_enhancement_only_sensor_is_not_asked_for_a_fallback() -> None:
	"""§14.8 reaches SENS-008 through five sensors and names the thermometer "where available"; the
	magnetometer carries no feature at all. Losing either costs an enhancement, not a path, so
	§13.2's principle asks nothing of them — which is why they are marked rather than given a
	fabricated fallback."""
	by_slug = {s.slug: s for s in SENSORS}
	assert by_slug['magnetometer'].enhancement_only and by_slug['barometer'].enhancement_only
	assert by_slug['heart_rate'].enhancement_only and by_slug['usb_otg'].enhancement_only
	assert by_slug['magnetometer'].primary_features == [], 'the magnetometer carries no feature'
	# The carriers are not marked: losing one of these removes a path.
	for slug in ('lidar', 'microphone', 'gyroscope', 'gps', 'bluetooth', 'nfc', 'camera_rear', 'thermometer'):
		assert by_slug[slug].enhancement_only is False, f'{slug} is a carrier, not an enhancement'


def test_every_sensor_row_cites_a_registered_feature() -> None:
	"""A sensor row citing a feature the registry does not carry describes hardware bought for a
	capability nobody built."""
	svc = SensorService(FeatureRegistry())
	assert svc.unregistered_sensor_features() == []
	assert any(s.primary_features for s in SENSORS), 'most rows name the features they carry'
	# The negative direction, so the check is not merely a list that always comes back empty.
	with pytest.raises(AssertionError):
		svc.sensor('teleporter')


def test_capabilities_are_served_without_a_spec_code() -> None:
	"""A code may not reach a screen, and the capability list is a screen. The ids stay in
	`primary_features`, which is deliberately not serialised."""
	rows = SensorService(FeatureRegistry()).capabilities()
	assert len(rows) == 18
	assert all('SENS-001' not in str(r) and 'primary_features' not in r for r in rows)
	gps = next(r for r in rows if r['sensor'] == 'gps')
	assert gps['used_for'] == 'Finding care, risk alerts, emergency location'
	assert gps['raw_retained'] is False and gps['needs_consent'] is True
	assert gps['retention_days'] == 21
	assert all(r['raw_retained'] is False for r in rows), 'no sensor may report a retained raw stream'


def test_a_raw_field_name_is_refused_by_name() -> None:
	"""The guard that replaced a dead one. `guard_raw` asserted `not RAW_FORBIDDEN` on a non-empty
	tuple — always false, so it raised whenever called, and nothing called it. `extra='forbid'`
	already rejects the key; this makes the refusal say why, which is the §17.2 reason."""
	with pytest.raises(ValidationError, match='raw sensor fields may not be ingested'):
		SenseIngest.model_validate({'kind': 'respiration', 'subject_ref': 'U1', 'value': 16,
		                            'county': 'N', 'audio': [0.1]})
	# And it does not fire on the legitimate payload.
	ok = SenseIngest(kind=SenseKind.respiration, subject_ref='U1', value=16.0, county='Nairobi')
	assert ok.value == 16.0


# --- routes ---------------------------------------------------------------------------------

def _auditor_app() -> tuple[Any, dict[str, str]]:
	from afya.privacy.views import RBACRole
	from afya.service import build_services, create_app
	svc = build_services()
	auth: Any = svc['auth']
	tok = auth.provision_staff('sens-aud', RBACRole.auditor, registrar='MoH ops').access_token
	return create_app(svc), {'authorization': f'Bearer {tok}'}


async def test_the_matrix_is_public_and_the_coverage_view_is_evidence() -> None:
	"""The matrix names no person, so it is readable by anyone deciding whether the app suits their
	handset. The coverage view is evidence about the build and takes the auditor's scope."""
	import httpx
	app, h = _auditor_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		matrix = (await c.get('/sensors/capabilities')).json()
		assert len(matrix['sensors']) == 18 and set(matrix['platforms']) == {'android', 'ios'}
		assert 'thermometer' in matrix['platforms']['ios'], 'iOS has no thermometer in §13.1'
		assert (await c.get('/sensors/coverage')).status_code in (401, 403)
		coverage = (await c.get('/sensors/coverage', headers=h)).json()
		assert coverage['missing_fallbacks'] == [] and coverage['raw_streams_retained'] == []
		assert coverage['sensor_count'] == 18


async def test_a_sysadmin_is_refused_the_evidence_view() -> None:
	"""§17.4 splits the operator scopes: a sysadmin reads `infrastructure`, an auditor reads
	`audit_logs`. Every read in this family is evidence, so the sysadmin is refused."""
	import httpx
	from afya.privacy.views import RBACRole
	from afya.service import build_services, create_app
	svc = build_services()
	auth: Any = svc['auth']
	sys_tok = auth.provision_staff('sens-sys', RBACRole.sysadmin, registrar='MoH ops').access_token
	app = create_app(svc)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		assert (await c.get('/sensors/coverage', headers={'authorization': f'Bearer {sys_tok}'})).status_code == 403
