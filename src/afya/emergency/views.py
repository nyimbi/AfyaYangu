"""Emergency domain models (EMG-001..003)."""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class SOSEvent(BaseModel):
	model_config = MODEL_CONFIG
	sos_id: str = Field(pattern=r'^SOS-[A-Z0-9]{6,}$')
	lat: float = Field(ge=-5, le=6)
	lon: float = Field(ge=33, le=43)
	symptoms: list[str] = []
	severity: str = Field(pattern=r'^(low|medium|high)$')


class SOSDispatch(BaseModel):
	model_config = MODEL_CONFIG
	sos_id: str
	notified: list[str]
	actions: list[str]


class IMUSample(BaseModel):
	model_config = MODEL_CONFIG
	x: float
	y: float
	z: float
	timestamp_ms: int


class FallResult(BaseModel):
	model_config = MODEL_CONFIG
	fall_detected: bool
	peak_g: float
	auto_alert: bool


class EmergencyCard(BaseModel):
	model_config = MODEL_CONFIG
	name: str
	blood_group: str
	allergies: list[str]
	conditions: list[str]
	emergency_contact: str = Field(pattern=r'^\+?\d{7,15}$')