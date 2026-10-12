"""Sensor service — tier4-gated derived-metric ingestion + deterministic band engines.

The on-device engines (mobile clients) implement the same bands; server-side is the
surveillance aggregation surface. Raw payloads are rejected structurally by model
config (extra='forbid') — only derived values pass.
"""
from afya.logmixin import LogMixin
from afya.registry.service import FeatureRegistry, Tier
from afya.sensors.views import (
	AccuracyClaim, Availability, BatteryCost, Confidence, DeviceProvenance, Handling,
	MeasurementSource, QualifiedVerdict, Sensitivity, SenseIngest, SenseKind, SenseVerdict, SensorSpec,
	SourceClass,
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

# §13.1's row name and its Android and iOS cells, verbatim, paired to the rows above by slug. The `Availability` enum
# normalises these, and the normalisation loses information the section carries: "Rare" and "Very
# rare" both become `rare`, and "Some", "iPhone Pro / iPad Pro" and "Limited" all become `some`. The
# collapse is sound for the one predicate §13.2 is keyed on — `all` is the only value that is not
# absence-prone — but a client rendering a capability matrix should read the section's words, because
# `rare` for a thermometer understates "Very rare" and `some` for USB/OTG overstates "Limited".
SPEC_AVAILABILITY: tuple[tuple[str, str, str, str], ...] = (
	('lidar', 'LiDAR', 'Select flagships', 'iPhone Pro / iPad Pro'),
	('microphone', 'Microphone', 'All', 'All'),
	('accelerometer', 'Accelerometer', 'All', 'All'),
	('gyroscope', 'Gyroscope', 'Most', 'All'),
	('magnetometer', 'Magnetometer', 'Most', 'All'),
	('barometer', 'Barometer', 'Some', 'Most'),
	('ambient_light', 'Ambient light', 'All', 'All'),
	('proximity', 'Proximity', 'All', 'All'),
	('gps', 'GPS / GNSS', 'All', 'All'),
	('bluetooth', 'Bluetooth LE', 'All', 'All'),
	('nfc', 'NFC', 'Most', 'Most'),
	('camera_rear', 'Camera (rear)', 'All', 'All'),
	('camera_front', 'Camera (front)', 'All', 'All'),
	('flash', 'Flash / LED', 'All', 'All'),
	('screen', 'Screen', 'All', 'All'),
	('thermometer', 'Thermometer', 'Very rare', 'None'),
	('heart_rate', 'Heart rate (optical)', 'Rare', 'None'),
	('usb_otg', 'USB / OTG', 'Most', 'Limited'),
)

# The section's nine Android/iOS spellings, mapped. Every cell in §13.1 must appear here, so a
# revision that writes a tenth fails at import rather than being silently normalised into a
# neighbour — which is the failure mode this table exists to make impossible.
AVAILABILITY_SPELLINGS: dict[str, Availability] = {
	'All': Availability.all,
	'Most': Availability.most,
	'Some': Availability.some,
	'Select flagships': Availability.select,
	'iPhone Pro / iPad Pro': Availability.some,
	'Rare': Availability.rare,
	'Very rare': Availability.rare,
	'Limited': Availability.some,
	'None': Availability.none,
}

# §13.1 feature ids the row's own cell does not name, and where they come from instead. USB/OTG's
# cell reads "External thermometer, BP cuff" with no id; §14.9 is the section that gives it SENS-009,
# so the attribution is real but it is not §13.1's. Named here so the comparison against the section
# is exact rather than a superset test that would tolerate any addition.
SPEC_FEATURE_ADDITIONS: dict[str, tuple[str, ...]] = {'usb_otg': ('SENS-009',)}

_SPEC_AVAILABILITY_BY_SLUG: dict[str, tuple[str, str]] = {slug: (a, i) for slug, _, a, i in SPEC_AVAILABILITY}
assert set(_SPEC_AVAILABILITY_BY_SLUG) == {s.slug for s in SENSORS}, '§13.1 availability must name every sensor row'
for _s in SENSORS:
	_android_cell, _ios_cell = _SPEC_AVAILABILITY_BY_SLUG[_s.slug]
	assert AVAILABILITY_SPELLINGS[_android_cell] is _s.android, (
		f'{_s.slug}: §13.1 android cell {_android_cell!r} is not {_s.android.value}')
	assert AVAILABILITY_SPELLINGS[_ios_cell] is _s.ios, (
		f'{_s.slug}: §13.1 ios cell {_ios_cell!r} is not {_s.ios.value}')

# §11.6's Sensor-Based Monitoring table, all eight rows. It is §13.1 read the other way round —
# feature first, then the sensors that carry it — and the two sections disagree in three places, so
# carrying it is what makes the disagreement visible instead of a reader having to notice it.
#
# `sensors` holds §11.6's own cell, verbatim, because the disagreements are *in the cell*: SENS-005
# names three sensors where §13.1 gives it four, SENS-006 names "HealthKit / Health Connect" and
# SENS-007 "wearables", neither of which is a §13.1 sensor row at all.
SPEC_SENSOR_FEATURES: tuple[tuple[str, str, str], ...] = (
	('SENS-001', 'LiDAR respiration monitoring', 'LiDAR'),
	('SENS-002', 'Acoustic cough and respiratory monitoring', 'Microphone'),
	('SENS-003', 'Fall detection and collapse alert', 'Accelerometer, gyroscope'),
	('SENS-004', 'Camera-based symptom capture', 'Camera'),
	('SENS-005', 'Screen/camera PPG health monitoring', 'Camera, flash, screen'),
	('SENS-006', 'Wearable integration', 'BLE, HealthKit / Health Connect'),
	('SENS-007', 'Sleep and activity monitoring', 'Accelerometer, wearables'),
	('SENS-008', 'Ambient environmental sensing', 'Barometer, thermometer (where available)'),
)

# §11.6 sensor names that are not §13.1 rows, and what they mean. Both are platform surfaces rather
# than handset sensors: HealthKit/Health Connect is the OS health store and a wearable is the §14.6
# integration that reads it. Mapping them onto a §13.1 slug would invent a sensor row §13.1 does not
# have, so they are named as unmapped and the cross-check reports them rather than dropping them.
UNMAPPED_SENSOR_NAMES: dict[str, str] = {
	'HealthKit / Health Connect': 'the OS health store; reached through Bluetooth LE (§14.6)',
	'wearables': 'the §14.6 integration; the device pairs over Bluetooth LE',
}

# §11.6's sensor spellings, mapped onto §13.1 slugs. Declared rather than guessed, because the two
# sections name the same hardware differently — §11.6 writes "gyroscope", "flash" and "BLE" where
# §13.1 writes "Gyroscope", "Flash / LED" and "Bluetooth LE" — and a fuzzy matcher would silently
# read "flash" as matching nothing and report a false omission.
#
# `Camera` maps to *both* §13.1 camera rows, which is the point: §11.6 does not distinguish rear
# from front and §13.1 does, so the ambiguity surfaces as a real disagreement on SENS-004 and
# SENS-005 rather than being resolved by a guess about which camera the section meant.
SPEC_SENSOR_NAME_ALIASES: dict[str, tuple[str, ...]] = {
	'LiDAR': ('lidar',),
	'Microphone': ('microphone',),
	'Accelerometer': ('accelerometer',),
	'gyroscope': ('gyroscope',),
	'Camera': ('camera_rear', 'camera_front'),
	'flash': ('flash',),
	'screen': ('screen',),
	'BLE': ('bluetooth',),
	'Barometer': ('barometer',),
	'thermometer': ('thermometer',),
	'HealthKit / Health Connect': (),
	'wearables': (),
}


def _sensor_slugs_in(cell: str) -> tuple[set[str], set[str], dict[str, tuple[str, ...]]]:
	"""What a §11.6 cell names: the slugs it covers, the names that are no §13.1 row, and the names
	that are ambiguous.

	Returns (covered, unmapped, ambiguous). `covered` is the union of every alias target, so a cell
	reading "Camera" covers both §13.1 camera rows — the ambiguity is reported separately rather than
	left to surface as a spurious omission on one row and a spurious extra on the other.
	"""
	assert SPEC_SENSOR_NAME_ALIASES, 'the alias table must not be empty'
	covered: set[str] = set()
	unmapped: set[str] = set()
	ambiguous: dict[str, tuple[str, ...]] = {}
	for part in cell.split(','):
		# §14.8's "where available" is an enhancement note, not a different sensor, so the
		# parenthetical comes off before the lookup.
		name = part.split('(')[0].strip()
		if not name:
			continue
		if name not in SPEC_SENSOR_NAME_ALIASES:
			raise AssertionError(f'§11.6 names {name!r}, which the alias table does not map')
		targets = SPEC_SENSOR_NAME_ALIASES[name]
		if not targets:
			unmapped.add(name)
			continue
		if len(targets) > 1:
			ambiguous[name] = targets
		covered.update(targets)
	return covered, unmapped, ambiguous

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

# §14.9 SENS-009's provenance classes. A reading is clinical grade when a device measured it;
# everything else is a number a person produced, which is a different thing to triage on.
SOURCES: tuple[SourceClass, ...] = (
	SourceClass(source=MeasurementSource.manual, label='Typed in by hand', clinical_grade=False,
		patient_entered=True, paired_device=False,
		note='a number a person entered, from memory or from a device they read themselves'),
	SourceClass(source=MeasurementSource.ble_device, label='Paired device (Bluetooth)',
		clinical_grade=True, patient_entered=False, paired_device=True,
		note='a paired cuff, thermometer, oximeter, glucometer, scale or ECG reported this value'),
	SourceClass(source=MeasurementSource.usb_otg, label='Paired device (cable)',
		clinical_grade=True, patient_entered=False, paired_device=True,
		note='a device attached by cable reported this value'),
	SourceClass(source=MeasurementSource.facility, label='Health facility',
		clinical_grade=True, patient_entered=False, paired_device=True,
		note='a health worker took this reading at a facility'),
)

_SOURCE_BY_CLASS: dict[MeasurementSource, SourceClass] = {s.source: s for s in SOURCES}


def source_class(source: MeasurementSource) -> SourceClass:
	for row in SOURCES:
		if row.source is source:
			return row
	raise AssertionError(f'no provenance class for {source}')


# §14's accuracy statements, per capability, each with the disclosure it obliges. §14.5 is the
# one the spec marks as an ethical requirement rather than a refinement, so its row is the only one
# carrying `bias_disclosure_required` — and the validator makes it state a skin-tone limitation
# rather than merely flag that one is owed.
ACCURACY: tuple[AccuracyClaim, ...] = (
	AccuracyClaim(kind=SenseKind.respiration, capability='Contactless breathing rate',
		stated_accuracy='expected error under 1 breath per minute in controlled conditions, wider in practice',
		limitations=['needs a relatively still subject', 'clothing and bedding reduce accuracy',
			'not a substitute for clinical assessment'],
		disclosure='An estimate of your breathing rate, not a measurement. It is less reliable if you are moving or under a blanket.',
		not_diagnostic=True, confidence_indicator=True),
	AccuracyClaim(kind=SenseKind.cough, capability='Cough and breathing sounds',
		stated_accuracy='background noise reduces accuracy; it cannot tell one cough from another',
		limitations=['background noise reduces accuracy',
			'cannot distinguish a dangerous cough from any other cough'],
		disclosure='Counts coughs. It cannot tell what is causing them, so it is not a diagnosis.',
		not_diagnostic=True),
	AccuracyClaim(kind=SenseKind.fall, capability='Fall and collapse detection',
		stated_accuracy='machine learning reduces false alarms, but they will happen',
		limitations=['false alarms will happen', 'a slow slide to the floor may not register'],
		disclosure='Detects a fall and asks if you are all right. It can miss a fall or raise a false alarm.',
		not_diagnostic=True),
	AccuracyClaim(kind=SenseKind.ppg, capability='Heart rate, and estimated blood pressure and oxygen',
		stated_accuracy='heart rate is reasonably accurate to about 5 beats per minute; blood pressure and oxygen are less accurate than a cuff or a pulse oximeter and vary by device, skin tone and technique',
		limitations=['less accurate than a cuff or pulse oximeter', 'varies by device and by technique',
			'accuracy varies with skin pigmentation'],
		disclosure='An estimate only, and it is less reliable on darker skin. Always confirm with a health worker or a proper device.',
		not_diagnostic=True, estimate_only=True, bias_disclosure_required=True, quality_floor=0.5),
	AccuracyClaim(kind=SenseKind.sleep, capability='Sleep and activity',
		stated_accuracy='derived from movement and phone use, not from a sleep study',
		limitations=['inferred from movement, so a still awake person can read as asleep'],
		disclosure='Sleep and activity are worked out from how you move, so they can be wrong.',
		not_diagnostic=True),
	AccuracyClaim(kind=SenseKind.ambient, capability='Surroundings — pressure, light, noise, temperature',
		stated_accuracy='a reading of the room or the weather, not of a person',
		limitations=['air quality by camera haze is only used where it has been validated'],
		disclosure='Reads your surroundings. It says nothing about your health on its own.',
		not_diagnostic=False),
)

_ACCURACY_BY_KIND: dict[SenseKind, AccuracyClaim] = {a.kind: a for a in ACCURACY}
assert set(_ACCURACY_BY_KIND) == set(SenseKind), 'every sense kind needs a stated accuracy and a disclosure'


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
		"""Validate a derived reading and return its band. The band is the verdict; the disclosure
		that has to travel beside it is `qualified_verdict`."""
		return (await self.qualified_verdict(inp)).verdict

	async def qualified_verdict(self, inp: SenseIngest) -> QualifiedVerdict:
		"""A verdict plus what the app owes the person about it (§14's accuracy statements).

		§14.5 makes this an ethical requirement rather than a refinement: "PPG accuracy varies with
		skin pigmentation … the app must disclose known accuracy limitations". Two things are
		reported because they fail independently — a reading can be in range *and* unreliable — and
		`inp.quality` is finally consulted here: §14.5's own hedge is "blood oxygen saturation, where
		signal quality permits", which until now nothing enforced.
		"""
		feat = self._registry.get(_INGEST_FEATURE[inp.kind])
		if feat.tier is Tier.tier4 and not self._registry.tier4_active():
			# Refusal text a person may read: no spec code, no tier number.
			raise PermissionError(f'{inp.kind.value} sensing opens when the outbreak response is activated')
		verdict = _ENGINES[inp.kind](inp.value)
		claim = _ACCURACY_BY_KIND[inp.kind]
		if inp.quality < claim.quality_floor:
			# Below the floor the reading is not reported as a reading at all — the band would be a
			# number presented as a measurement, which is exactly what the disclosure exists to stop.
			confidence = Confidence.not_available
		elif inp.quality < min(1.0, claim.quality_floor + 0.25):
			confidence = Confidence.low_quality
		else:
			confidence = Confidence.good
		disclosure = claim.disclosure
		if confidence is Confidence.low_quality:
			disclosure = f'This reading is unclear, so treat it as a rough guide. {disclosure}'
		elif confidence is Confidence.not_available:
			disclosure = 'This reading was not clear enough to use. Try again, or use a proper device.'
		self._history.append(inp)
		self._history = self._history[-10_000:]
		assert len(self._history) <= 10_000, 'ingest history bounded'
		self._log_info('sense ingested', kind=inp.kind.value, band=verdict.band,
		               confidence=confidence.value)
		return QualifiedVerdict(
			verdict=verdict, confidence=confidence, disclosure=disclosure,
			limitations=list(claim.limitations), not_diagnostic=claim.not_diagnostic,
			seek_clinician=claim.not_diagnostic and verdict.anomaly,
		)

	def accuracy_claims(self) -> list[AccuracyClaim]:
		"""§14's accuracy statements and the disclosures they oblige."""
		return list(ACCURACY)

	def undisclosed_limitations(self) -> list[str]:
		"""Capabilities whose limitations are known and unstated — the thing §14.5 forbids. Empty
		on a correct build, which is what makes it a check rather than a report."""
		return sorted(a.kind.value for a in ACCURACY if not a.disclosure or not a.limitations)

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

	def sensor_feature_disagreements(self) -> list[str]:
		"""§11.6's feature→sensor table crossed against §13.1's sensor→feature table.

		The two sections describe one mapping from opposite ends, and they disagree. This reports the
		differences rather than reconciling them, because each is a fact about the spec: §13.1 gives
		SENS-005 four carrier sensors and §11.6 names three, §11.6 reaches SENS-006 and SENS-007
		through "HealthKit / Health Connect" and "wearables" which are not §13.1 sensor rows, and a
		feature §13.1 attributes to a sensor §11.6 never lists is a mapping that exists in one
		section only.

		A disagreement is not automatically a defect in the code — the code follows §13.1, which is
		the section that classifies the sensors. It is a defect in *one of the sections*, and the
		report says which pair disagrees so a reader can take it to whoever owns the spec.
		"""
		# §13.1 read backwards: feature -> the slugs that carry it.
		from_thirteen: dict[str, set[str]] = {}
		for spec in SENSORS:
			for feature_id in spec.primary_features:
				from_thirteen.setdefault(feature_id, set()).add(spec.slug)
		findings: list[str] = []
		for feature_id, _, cell in SPEC_SENSOR_FEATURES:
			covered, unmapped, ambiguous = _sensor_slugs_in(cell)
			for name in sorted(unmapped):
				findings.append(
					f'§11.6 {feature_id} names {name!r}, which is no §13.1 sensor row '
					f'({UNMAPPED_SENSOR_NAMES[name]})')
			# A slug reached through an ambiguous name is excluded from the set difference below:
			# the ambiguity line already says the row cannot distinguish the two, and reporting it
			# again as an omission on one row and an extra on the next would triple-count one fact.
			from_ambiguous: set[str] = set()
			for name, targets in sorted(ambiguous.items()):
				findings.append(
					f'§11.6 {feature_id} names {name!r}, which §13.1 splits into '
					f'{", ".join(targets)} — the row cannot say which it means')
				from_ambiguous.update(targets)
			claimed = from_thirteen.get(feature_id, set())
			for slug in sorted((claimed - covered) - from_ambiguous):
				findings.append(
					f'§13.1 gives {feature_id} the {slug} sensor; §11.6 lists {cell!r} and omits it')
			for slug in sorted((covered - claimed) - from_ambiguous):
				findings.append(
					f'§11.6 gives {feature_id} the {slug} sensor; §13.1 does not carry it for that feature')
		return findings

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
		are dropped and `used_for` carries the meaning, because a code may not reach a screen.

		`android` and `ios` are §13.1's own cells rather than the normalised enum, because the enum
		is lossy where a person is reading: it cannot tell "Very rare" from "Rare" or "Limited" from
		"Some", so serving it would tell a user their handset is supported on the same terms as one
		the section called "Limited". `absence_prone` carries the normalised answer, which is the
		only thing the enum is for.
		"""
		by_slug = {slug: (a, i) for slug, _, a, i in SPEC_AVAILABILITY}
		return [
			{
				'sensor': s.slug, 'name': s.name,
				'android': by_slug[s.slug][0], 'ios': by_slug[s.slug][1],
				'android_availability': s.android.value, 'ios_availability': s.ios.value,
				'absence_prone': s.can_be_absent(),
				'used_for': s.used_for, 'sensitivity': s.sensitivity.value,
				'derived_only': s.derived_only, 'battery': s.battery.value,
				'retention_days': s.retention_days,
				'raw_retained': self.handling(s.sensitivity).raw_may_be_retained,
				'needs_consent': self.handling(s.sensitivity).capture_requires_consent,
			}
			for s in SENSORS
		]

	def source_classes(self) -> list[SourceClass]:
		"""§14.9's provenance classes, each stating whether it makes a reading clinical grade."""
		return list(SOURCES)

	def clinical_grade_sources(self) -> list[str]:
		return sorted(s.source.value for s in SOURCES if s.clinical_grade)

	def external_device_gap(self) -> DeviceProvenance:
		"""§14.9 SENS-009's own claim, as a check rather than a sentence.

		The section's value is that a paired device "converts consumer measurements into
		clinical-grade data, improving triage accuracy". That is only true if a reading records
		where it came from, and only meaningful if some reader acts on it. Both halves are reported
		here: the classes that exist, and the reading models that carry one.
		"""
		from afya.chronic.views import BPReading, GlucoseReading
		from afya.monitoring.views import MonitoringDay
		carriers = {
			'BPReading': BPReading.model_fields.get('source') is not None,
			'GlucoseReading': GlucoseReading.model_fields.get('source') is not None,
			'MonitoringDay': MonitoringDay.model_fields.get('source') is not None,
		}
		return DeviceProvenance(
			classes=list(SOURCES),
			clinical_grade_sources=self.clinical_grade_sources(),
			readings_carrying_provenance=carriers,
			unprovenanced_readings=sorted(k for k, v in carriers.items() if not v),
		)

	def raw_streams_retained(self) -> list[str]:
		"""Sensors whose class permits keeping the raw stream. §17.2 and SEC-002 say never, for any
		class, so this must always be empty — and it is a method rather than a constant so the claim
		is computed from the table rather than restated beside it."""
		return sorted(s.slug for s in SENSORS if self.handling(s.sensitivity).raw_may_be_retained)