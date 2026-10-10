"""Sensor service — tier4-gated derived-metric ingestion + deterministic band engines.

The on-device engines (mobile clients) implement the same bands; server-side is the
surveillance aggregation surface. Raw payloads are rejected structurally by model
config (extra='forbid') — only derived values pass.
"""
from afya.logmixin import LogMixin
from afya.registry.service import FeatureRegistry, Tier
from afya.sensors.views import (
	Availability, BatteryCost, Handling, Sensitivity, SenseIngest, SenseKind, SenseVerdict, SensorSpec,
)

# §13.1's Full Sensor Inventory, all eighteen rows. The Data Sensitivity column is the load-bearing
# one: §17.2's minimisation rule and SEC-002's "raw sensor data never leaves the device" are claims
# about *this* classification, so it belongs in code rather than in a table nobody checks.
#
# `used_for` is the plain-language rendering of the Primary Features column, because a spec id may
# not reach a surface a person reads (tests/ci/test_ui_vocabulary.py).
SENSORS: tuple[SensorSpec, ...] = (
	SensorSpec(slug='lidar', name='LiDAR', android=Availability.select, ios=Availability.some,
		primary_features=['SENS-001'], used_for='Contactless breathing measurement',
		sensitivity=Sensitivity.low, derived_only=True, battery=BatteryCost.medium),
	SensorSpec(slug='microphone', name='Microphone', android=Availability.all, ios=Availability.all,
		primary_features=['SENS-002', 'ACC-002', 'CHAN-003'], used_for='Cough and breathing sounds, voice input',
		sensitivity=Sensitivity.high, battery=BatteryCost.low, permission_gated=True),
	SensorSpec(slug='accelerometer', name='Accelerometer', android=Availability.all, ios=Availability.all,
		primary_features=['SENS-003', 'SENS-007'], used_for='Fall detection, sleep and activity',
		sensitivity=Sensitivity.low, battery=BatteryCost.very_low),
	SensorSpec(slug='gyroscope', name='Gyroscope', android=Availability.most, ios=Availability.all,
		primary_features=['SENS-003'], used_for='Fall detection', sensitivity=Sensitivity.low,
		battery=BatteryCost.very_low),
	SensorSpec(slug='magnetometer', name='Magnetometer', android=Availability.most, ios=Availability.all,
		used_for='Compass bearing', sensitivity=Sensitivity.low, battery=BatteryCost.very_low,
		enhancement_only=True),
	SensorSpec(slug='barometer', name='Barometer', android=Availability.some, ios=Availability.most,
		primary_features=['SENS-008'], used_for='Air pressure and altitude', sensitivity=Sensitivity.low,
		battery=BatteryCost.very_low, enhancement_only=True),
	SensorSpec(slug='ambient_light', name='Ambient light', android=Availability.all, ios=Availability.all,
		used_for='Screen brightness', sensitivity=Sensitivity.low, battery=BatteryCost.negligible),
	SensorSpec(slug='proximity', name='Proximity', android=Availability.all, ios=Availability.all,
		used_for='Screen off during a call', sensitivity=Sensitivity.low, battery=BatteryCost.negligible),
	SensorSpec(slug='gps', name='GPS / GNSS', android=Availability.all, ios=Availability.all,
		primary_features=['LOC-001', 'LOC-003', 'FND-001', 'EMG-001'],
		used_for='Finding care, risk alerts, emergency location', sensitivity=Sensitivity.high,
		battery=BatteryCost.high, retention_days=21, permission_gated=True),
	SensorSpec(slug='bluetooth', name='Bluetooth LE', android=Availability.all, ios=Availability.all,
		primary_features=['LOC-002', 'SENS-006'], used_for='Nearby contact logging, wearables',
		sensitivity=Sensitivity.medium, battery=BatteryCost.medium, permission_gated=True),
	SensorSpec(slug='nfc', name='NFC', android=Availability.most, ios=Availability.most,
		primary_features=['LOC-004'], used_for='Tap to check in', sensitivity=Sensitivity.low,
		battery=BatteryCost.negligible, permission_gated=True),
	SensorSpec(slug='camera_rear', name='Camera (rear)', android=Availability.all, ios=Availability.all,
		primary_features=['MED-001', 'SENS-004', 'REC-001'], used_for='Medicine checks, symptom photos, health cards',
		sensitivity=Sensitivity.high, battery=BatteryCost.medium, permission_gated=True),
	SensorSpec(slug='camera_front', name='Camera (front)', android=Availability.all, ios=Availability.all,
		primary_features=['SENS-005'], used_for='Heart rate from the screen', sensitivity=Sensitivity.medium,
		battery=BatteryCost.medium, permission_gated=True),
	SensorSpec(slug='flash', name='Flash / LED', android=Availability.all, ios=Availability.all,
		primary_features=['SENS-005'], used_for='Light for heart-rate readings', sensitivity=Sensitivity.low,
		battery=BatteryCost.low),
	SensorSpec(slug='screen', name='Screen', android=Availability.all, ios=Availability.all,
		primary_features=['SENS-005'], used_for='The interface, and light for heart-rate readings',
		sensitivity=Sensitivity.low, battery=BatteryCost.medium),
	SensorSpec(slug='thermometer', name='Thermometer', android=Availability.rare, ios=Availability.none,
		primary_features=['SENS-008'], used_for='Body temperature', sensitivity=Sensitivity.low,
		battery=BatteryCost.negligible),
	SensorSpec(slug='heart_rate', name='Heart rate (optical)', android=Availability.rare, ios=Availability.none,
		primary_features=['SENS-005'], used_for='Heart rate', sensitivity=Sensitivity.medium,
		battery=BatteryCost.medium, enhancement_only=True),
	SensorSpec(slug='usb_otg', name='USB / OTG', android=Availability.most, ios=Availability.some,
		primary_features=['SENS-009'], used_for='Thermometers and blood pressure cuffs',
		sensitivity=Sensitivity.medium, battery=BatteryCost.negligible, enhancement_only=True),
)

# What each class permits (§17.2 minimisation, SEC-002 on-device processing, §17.4 consent). Every
# class carries `raw_may_be_retained=False`, which is the rule §13.1's "derived only" note states for
# one sensor and §14's privacy sections state for the rest. Stating it per class is what makes it
# checkable rather than a sentence in a document.
HANDLING: tuple[Handling, ...] = (
	Handling(sensitivity=Sensitivity.low, raw_may_be_retained=False, capture_requires_consent=False,
		share_requires_consent=False,
		note='device state and derived readings; nothing about a person is inferred from it'),
	Handling(sensitivity=Sensitivity.medium, raw_may_be_retained=False, capture_requires_consent=True,
		share_requires_consent=True,
		note='identifies a device or a body measurement; needs consent before it is collected'),
	Handling(sensitivity=Sensitivity.high, raw_may_be_retained=False, capture_requires_consent=True,
		share_requires_consent=True,
		note='location, voice, face or photograph — a person is identifiable from it'),
)

_HANDLING_BY_CLASS: dict[Sensitivity, Handling] = {h.sensitivity: h for h in HANDLING}


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

	# --- §13.1 the capability matrix ------------------------------------------------------------

	@staticmethod
	def sensors() -> list[SensorSpec]:
		return list(SENSORS)

	@staticmethod
	def sensor(slug: str) -> SensorSpec:
		for spec in SENSORS:
			if spec.slug == slug:
				return spec
		raise AssertionError(f'{slug} is not a §13.1 sensor')

	@staticmethod
	def handling(sensitivity: Sensitivity) -> Handling:
		return _HANDLING_BY_CLASS[sensitivity]

	def absent_on(self, platform: str) -> list[str]:
		"""The §13.1 sensors a platform cannot rely on. `all` is the only availability that is not
		absence-prone, so everything else is a sensor some device in the fleet will not have."""
		assert platform in ('android', 'ios'), 'known platform'
		return sorted(s.slug for s in SENSORS if getattr(s, platform) is not Availability.all)

	def missing_fallbacks(self) -> list[str]:
		"""§13.1 sensors that carry a feature, can be absent, and have no §13.2 fallback.

		The two tables are one promise — a sensor that can be absent and has no fallback excludes a
		user — and §13.2 keys its rows on the sensor, so this does too. The exclusions are the ones
		the spec itself makes: a sensor that is one of several carriers for its feature, or that
		carries no feature at all, costs an enhancement when it is missing, and §13.2 asks nothing of
		it (see `enhancement_only`).

		`can_be_absent` is the predicate, not `universal`: §13.2's microphone row reads "No
		microphone **access**", so a permission the user declined is an absent sensor even though the
		hardware is on every handset. Keying on hardware alone missed exactly that, which a canary
		found.
		"""
		from afya.access.service import SENSOR_FALLBACKS
		# §13.2 names `camera` where §13.1 splits rear and front, and `wearable` where §13.1 has no
		# row at all (a wearable is a §14.6 integration, not a handset sensor).
		aliases: dict[str, str] = {'camera_rear': 'camera', 'camera_front': 'camera'}
		missing: list[str] = []
		for spec in SENSORS:
			if not spec.can_be_absent() or spec.enhancement_only or not spec.primary_features:
				continue
			if aliases.get(spec.slug, spec.slug) in SENSOR_FALLBACKS:
				continue
			missing.append(spec.slug)
		return sorted(missing)

	def unregistered_sensor_features(self) -> list[str]:
		"""§13.1 feature ids the registry does not carry. A sensor row citing a feature that does not
		exist describes hardware bought for a capability nobody built."""
		missing: set[str] = set()
		for spec in SENSORS:
			for feature_id in spec.primary_features:
				try:
					self._registry.get(feature_id)
				except KeyError:
					missing.add(feature_id)
		return sorted(missing)

	def capabilities(self) -> list[dict[str, object]]:
		"""§13.1 rendered for a client: the sensor rows with the handling each class permits. Spec ids
		are dropped and `used_for` carries the meaning, because a code may not reach a screen."""
		return [
			{
				'sensor': s.slug, 'name': s.name, 'android': s.android.value, 'ios': s.ios.value,
				'used_for': s.used_for, 'sensitivity': s.sensitivity.value,
				'derived_only': s.derived_only, 'battery': s.battery.value,
				'retention_days': s.retention_days,
				'raw_retained': self.handling(s.sensitivity).raw_may_be_retained,
				'needs_consent': self.handling(s.sensitivity).capture_requires_consent,
			}
			for s in SENSORS
		]

	def raw_streams_retained(self) -> list[str]:
		"""Sensors whose class permits keeping the raw stream. §17.2 and SEC-002 say never, for any
		class, so this must always be empty — and it is a method rather than a constant so the claim
		is computed from the table rather than restated beside it."""
		return sorted(s.slug for s in SENSORS if self.handling(s.sensitivity).raw_may_be_retained)