"""Photo + textual evidence submission models (SENS-004, community reporting; §6, §17.2)."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class EvidenceKind(str, Enum):
	rash = 'rash'
	red_eye = 'red_eye'
	pallor = 'pallor'
	scene_photo = 'scene_photo'


class EvidenceSubmission(BaseModel):
	model_config = MODEL_CONFIG
	submission_id: str = Field(pattern=r'^EV-[ A-Z0-9]{10,}$')  # generated server-side
	kind: EvidenceKind
	subject_ref: str
	county: str
	image_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
	mime: str = Field(pattern=r'^image/(jpeg|webp|png)$')
	size_bytes: int = Field(ge=1000, le=8_388_608)  # 8 MB cap (§16.4 image compression)
	note: str = Field(default='', max_length=1000)

	@field_validator('note')
	@classmethod
	def strip_note(cls, v: str) -> str:
		return v.strip()


class EvidenceReceipt(BaseModel):
	model_config = MODEL_CONFIG
	submission_id: str
	storage_ref: str
	deduped: bool
	gated: bool
	received_at_ms: int


class EvidenceView(BaseModel):
	model_config = MODEL_CONFIG
	kind: EvidenceKind
	subject_ref: str
	county: str
	note: str
	size_bytes: int
	image_sha256: str