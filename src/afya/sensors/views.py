"""Sensor ingestion models — DERIVED metrics only (spec §14/§17.2: raw sensor data never retained).

Also §13.1's capability matrix: which sensors exist, how available each is, and the sensitivity
class that decides how the derived metric may be handled.
"""
from enum import Enum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# Field names that would mean a raw stream reached a model. Nothing may carry one — §17.2 forbids
# retaining raw sensor data at all, and SEC-002 forbids it leaving the device.
RAW_FORBIDDEN = ('depth', 'audio', 'samples', 'frames', 'raw', 'signal')


class Sensitivity(str, Enum):
	"""§13.1's Data Sensitivity column. It is the column §17.2's minimisation rule is enforced from."""
	low = 'low'
	medium = 'medium'
	high = 'high'

	@property
	def rank(self) -> int:
		return _SENSITIVITY_RANK[self]


_SENSITIVITY_RANK: dict[Sensitivity, int] = {Sensitivity.low: 1, Sensitivity.medium: 2, Sensitivity.high: 3}


class Availability(str, Enum):
	"""§13.1's Android/iOS columns, normalised. `all` is the only value that is not absence-prone."""
	all = 'all'
	most = 'most'
	some = 'some'
	select = 'select'
	rare = 'rare'
	none = 'none'


class BatteryCost(str, Enum):
	negligible = 'negligible'
	very_low = 'very_low'
	low = 'low'
	medium = 'medium'
	high = 'high'


class SensorSpec(BaseModel):
	"""One row of §13.1. `primary_features` holds spec ids and is never served — a person reads
	`used_for` instead (see `tests/ci/test_ui_vocabulary.py`)."""
	model_config = MODEL_CONFIG
	slug: str = Field(pattern=r'^[a-z][a-z0-9_]*$')
	name: str = Field(min_length=1)
	android: Availability
	ios: Availability
	primary_features: list[str] = []
	used_for: str = Field(min_length=1)
	sensitivity: Sensitivity
	# True when §13.1 marks the row "derived only": the raw stream is discarded on-device and only
	# the derived metric exists at all.
	derived_only: bool = False
	battery: BatteryCost
	# Only where §14 names a figure. §14.1's LOC-003 gives a 21-day rolling window; no other sensor
	# spec states one, and inventing the rest would be inventing a commitment.
	retention_days: int | None = Field(default=None, ge=1)
	# True when §13.1 lists the sensor as an enhancement rather than a carrier: the features it names
	# run without it. §14.8 reaches SENS-008 through five sensors and names the thermometer "where
	# available"; the magnetometer carries no feature at all. Losing such a sensor removes no path,
	# so §13.2's principle ("no user is excluded because of their device") asks nothing of it.
	enhancement_only: bool = False
	# True when reaching the sensor needs a runtime permission the user can refuse. §13.2's row for
	# the microphone reads "No microphone **access**", which is why it exists despite the hardware
	# being on every device — a denied permission is an absent sensor. The accelerometer is on every
	# device and cannot be denied, which is why §13.2 has no row for it.
	permission_gated: bool = False

	def universal(self) -> bool:
		return self.android is Availability.all and self.ios is Availability.all

	def can_be_absent(self) -> bool:
		"""Whether a user can reach the app without this sensor — absent hardware, or a permission
		they declined. This is the predicate §13.2's table is keyed on."""
		return self.permission_gated or not self.universal()

	@model_validator(mode='after')
	def _a_derived_only_sensor_cannot_be_high_sensitivity(self) -> Self:
		"""§13.1 writes LiDAR's class as "Low (derived only)" — the parenthesis is the reason. If the
		raw stream is discarded immediately, the only thing left to classify is the derived metric,
		so a row claiming both derived-only and High would be describing two different things."""
		if self.derived_only and self.sensitivity is not Sensitivity.low:
			raise ValueError(f'{self.slug} discards raw data, so nothing about it can be {self.sensitivity.value} sensitivity')
		return self

	@model_validator(mode='after')
	def _a_retention_cap_only_applies_to_something_sensitive(self) -> Self:
		if self.retention_days is not None and self.sensitivity is Sensitivity.low:
			raise ValueError(f'{self.slug} is low sensitivity but carries a retention cap')
		return self


class Handling(BaseModel):
	"""What a sensitivity class permits. §17.2 and SEC-002 fix one field of this for every class:
	raw sensor data is never retained and never leaves the device, so `raw_may_be_retained` is
	False throughout — that is the point of stating it per class rather than once in prose."""
	model_config = MODEL_CONFIG
	sensitivity: Sensitivity
	raw_may_be_retained: bool
	capture_requires_consent: bool
	share_requires_consent: bool
	note: str = Field(min_length=1)


class MeasurementSource(str, Enum):
	"""Where a vital-sign reading came from.

	§14.9's claim is that a paired device "converts consumer measurements into clinical-grade
	data, improving triage accuracy" — a claim about *provenance*. Until a reading carried it, a
	cuff measurement and a number typed from memory were the same row, and the improvement the
	section promises had nowhere to appear.
	"""
	manual = 'manual'
	ble_device = 'ble_device'
	usb_otg = 'usb_otg'
	facility = 'facility'


class SourceClass(BaseModel):
	"""What one provenance class means for how a reading may be read.

	`clinical_grade` is a boolean rather than a trust weight on purpose: §14.9 says a paired device
	improves accuracy, and it does not say by how much. A fabricated coefficient would look like
	rigour while resting on nothing, so what travels is the fact a triage reader can act on —
	whether a person measured this or a device did.
	"""
	model_config = MODEL_CONFIG
	source: MeasurementSource
	label: str = Field(min_length=1)
	clinical_grade: bool
	patient_entered: bool
	paired_device: bool
	note: str = Field(min_length=1)

	@model_validator(mode='after')
	def _only_a_paired_device_reaches_clinical_grade(self) -> Self:
		"""§14.9's value is the pairing. A class claiming clinical grade with no device behind it is
		exactly what the section exists to distinguish from a hand-entered number."""
		if self.clinical_grade and not self.paired_device:
			raise ValueError(f'{self.source.value} is clinical grade without a paired device')
		return self

	@model_validator(mode='after')
	def _a_patient_entered_reading_is_not_a_device_reading(self) -> Self:
		if self.patient_entered and (self.paired_device or self.clinical_grade):
			raise ValueError(f'{self.source.value} cannot be both patient-entered and device-measured')
		return self


class DeviceProvenance(BaseModel):
	"""§14.9 SENS-009's claim as a check: which provenance classes exist, and which readings carry
	one. `unprovenanced_readings` is the gap — a reading a triage decision is made on that cannot
	say whether a device measured it."""
	model_config = MODEL_CONFIG
	classes: list[SourceClass]
	clinical_grade_sources: list[str]
	readings_carrying_provenance: dict[str, bool]
	unprovenanced_readings: list[str]


class SenseKind(str, Enum):
	respiration = 'respiration'
	cough = 'cough'
	fall = 'fall'
	ppg = 'ppg'
	sleep = 'sleep'
	ambient = 'ambient'


class SenseIngest(BaseModel):
	model_config = MODEL_CONFIG
	kind: SenseKind
	subject_ref: str
	value: float = Field(ge=0, le=300)
	quality: float = Field(default=0.9, ge=0, le=1)
	county: str

	@model_validator(mode='before')
	@classmethod
	def _no_raw_field_name_reaches_an_ingest(cls, data: object) -> object:
		"""The raw-stream refusal, stated where it holds — on what actually arrived.

		`extra='forbid'` already rejects an undeclared key, which is what stops `depth=[...]` — but
		it rejects it as "extra field", and the reason it must be rejected is §17.2. Running before
		validation lets this inspect the incoming payload and refuse it by name.

		The previous `guard_raw` asserted `not RAW_FORBIDDEN` on a non-empty tuple: always false, so
		it raised whenever anything called it, and nothing did. A guard that cannot pass and is never
		reached is not a guard.
		"""
		if isinstance(data, dict):
			raw = sorted(k for k in data if isinstance(k, str) and any(w in k.lower() for w in RAW_FORBIDDEN))
			if raw:
				raise ValueError(f'raw sensor fields may not be ingested (§17.2): {", ".join(raw)}')
		return data


class SenseVerdict(BaseModel):
	model_config = MODEL_CONFIG
	kind: SenseKind
	anomaly: bool
	band: str = Field(pattern=r'^(normal|watch|alert)$')
	detail: str