"""Location & proximity models (spec §11.5 LOC-002..005, §8.6 LOC-001).

Everything here is Tier 4 except LOC-001's static advisory zones. Raw location never crosses
this boundary: LOC-003 accepts geohashes, never coordinates.
"""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

EBID_ROTATION_MINUTES = 15
LOCATION_WINDOW_DAYS = 21
LOCATION_WINDOW_MAX_DAYS = 28


# --- LOC-002 BLE proximity ---------------------------------------------------------------

class EphemeralId(BaseModel):
	model_config = MODEL_CONFIG
	ebid: str = Field(pattern=r'^[0-9a-f]{32}$')
	rotated_at_ms: int
	rotates_every_minutes: int = EBID_ROTATION_MINUTES


class EncounterToken(BaseModel):
	"""Private Encounter Token — identifies an encounter without identifying a person."""
	model_config = MODEL_CONFIG
	pet: str = Field(min_length=32, max_length=64)
	seen_at_ms: int
	rssi_dbm: int = Field(ge=-120, le=0)
	county: str


class ExposureDeclaration(BaseModel):
	model_config = MODEL_CONFIG
	declaration_id: str
	pet: str = Field(min_length=32, max_length=64)
	declared_at_ms: int
	proxied: bool = True


class ExposureMatch(BaseModel):
	model_config = MODEL_CONFIG
	matched: bool
	encounters: int = Field(ge=0)
	window_days: int = Field(ge=1, le=28)
	message: str


# --- LOC-003 location history ------------------------------------------------------------

class LocationPoint(BaseModel):
	model_config = MODEL_CONFIG
	geohash: str = Field(pattern=r'^[0-9a-z]{5,9}$')
	at_iso: str
	place_label: str | None = Field(default=None, max_length=80)


class LocationHistory(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	points: list[LocationPoint] = Field(default_factory=list)
	consent_granted: bool = False
	window_days: int = Field(default=LOCATION_WINDOW_DAYS, ge=1, le=LOCATION_WINDOW_MAX_DAYS)


class LocationReport(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	points: int = Field(ge=0)
	places: list[str]
	window_days: int = Field(ge=1, le=28)
	shared_with: str | None
	message: str


# --- LOC-004 QR / NFC check-in -----------------------------------------------------------

class CheckInPoint(BaseModel):
	model_config = MODEL_CONFIG
	point_id: str
	kind: str = Field(pattern=r'^(border_post|health_facility|isolation_unit|vaccination_point|school|workplace|event)$')
	label: str
	county: str
	token: str = Field(pattern=r'^[A-Z0-9]{6,16}$')


class CheckIn(BaseModel):
	model_config = MODEL_CONFIG
	checkin_id: str = Field(pattern=r'^CHK-[A-Z0-9]{8,}$')
	point_token: str = Field(pattern=r'^[A-Z0-9]{6,16}$')
	subject_ref: str
	method: str = Field(pattern=r'^(qr|nfc|manual)$')
	at_iso: str
	share_with_authority: bool = False


class CheckInReceipt(BaseModel):
	model_config = MODEL_CONFIG
	checkin_id: str
	point_label: str
	guidance: str
	logged_locally: bool
	shared: bool


# --- LOC-005 border and point-of-entry ---------------------------------------------------

class BorderPost(BaseModel):
	model_config = MODEL_CONFIG
	post_id: str
	name: str
	county: str
	country_pair: str
	queue_minutes: int = Field(ge=0, le=1440)
	screening_required: bool


class TravelerDeclaration(BaseModel):
	model_config = MODEL_CONFIG
	declaration_id: str = Field(pattern=r'^TD-[A-Z0-9]{8,}$')
	subject_ref: str
	destination: str
	arrival_iso: str
	origin_country: str
	symptoms: list[str] = Field(default_factory=list)
	lang: str = 'en'


class TravellerEnrolment(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	monitoring_days: int = Field(default=21, ge=1, le=28)
	enrolled: bool
	report_schedule: list[int]
	message: str
