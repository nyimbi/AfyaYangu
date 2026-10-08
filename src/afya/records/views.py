"""Records domain models — family health wallet, immunisations, growth monitoring (REC-001..003)."""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class WalletMember(BaseModel):
	model_config = MODEL_CONFIG
	member_ref: str
	name: str | None = None
	dob_iso: str
	is_minor: bool = False
	guardian_ref: str | None = None


class ImmunisationRecord(BaseModel):
	model_config = MODEL_CONFIG
	member_ref: str
	vaccine: str
	dose_no: int = Field(ge=1)
	given_iso: str
	batch: str | None = None


# Kenya EPI doses due within first 12 months (vaccine -> 1-indexed dose numbers)
EPI_SCHEDULE: dict[str, list[int]] = {
	'BCG': [1], 'OPV': [1, 2, 3, 4], 'PCV10': [1, 2, 3], 'DPT-HepB-Hib': [1, 2, 3],
	'RV1': [1, 2], 'IPV': [2], 'MMR': [1, 2],
}


class GrowthRecord(BaseModel):
	model_config = MODEL_CONFIG
	member_ref: str
	age_months: int = Field(ge=0, le=60)
	weight_kg: float = Field(gt=0, le=60)
	height_cm: float = Field(gt=20, le=140)


class GrowthFlag(BaseModel):
	model_config = MODEL_CONFIG
	member_ref: str
	flag: str = Field(pattern=r'^(normal|underweight|stunted)$')

MEDICATION_SCHEDULE: dict[str, list[int]] = {}


class MedReminder(BaseModel):
	model_config = MODEL_CONFIG
	member_ref: str
	drug: str
	times_per_day: int = Field(ge=1, le=6)
	started_iso: str
	channel: str = Field(pattern=r'^(sms|native|whatsapp)$')