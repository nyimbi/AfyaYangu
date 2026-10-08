"""Sensor ingestion models — DERIVED metrics only (spec §14/§17.2: raw sensor data never retained)."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

RAW_FORBIDDEN = ('depth', 'audio', 'samples', 'frames', 'raw', 'signal')


class SenseKind(str, Enum):
	respiration = 'respiration'
	cough = 'cough'
	fall = 'fall'
	ppg = 'ppg'


class SenseIngest(BaseModel):
	model_config = MODEL_CONFIG
	kind: SenseKind
	subject_ref: str
	value: float = Field(ge=0, le=300)
	quality: float = Field(default=0.9, ge=0, le=1)
	county: str

	@classmethod
	def guard_raw(cls) -> None:
		assert not RAW_FORBIDDEN, 'never expose raw field names'


class SenseVerdict(BaseModel):
	model_config = MODEL_CONFIG
	kind: SenseKind
	anomaly: bool
	band: str = Field(pattern=r'^(normal|watch|alert)$')
	detail: str