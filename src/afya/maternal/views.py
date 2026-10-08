"""Maternal health: pregnancy, 8-contact ANC schedule (Kenya WHO 2016+ model), danger signs escalation."""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

ANC_CONTACTS_WEEKS = (12, 20, 26, 30, 34, 36, 38, 40)
DANGER_SIGNS = ('bleeding', 'severe_headache', 'blurred_vision', 'convulsions', 'severe_swelling', 'reduced_fetal_movement', 'fever', 'abdominal_pain', 'water_breaks')


class Pregnancy(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	edd_iso: str  # estimated date of delivery
	delivery_plan_facility_id: str | None = None
	lmp_week: int = Field(default=8, ge=1, le=42)


class ANCRecord(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	contact_no: int = Field(ge=1, le=8)
	done_iso: str
	facility_id: str | None = None


class DangerAssessment(BaseModel):
	model_config = MODEL_CONFIG
	signs: list[str]
	escalate: bool
	message: str