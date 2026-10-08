"""Chronic disease: BP/glucose logging, refill tracking (hypertension & diabetes, Kenya NCD burden)."""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class BPReading(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	systolic: int = Field(ge=60, le=260)
	diastolic: int = Field(ge=30, le=160)
	pulse: int = Field(default=70, ge=30, le=220)

	@property
	def stage(self) -> str:
		if self.systolic >= 140 or self.diastolic >= 90:
			return 'high'
		if self.systolic >= 130 or self.diastolic >= 85:
			return 'elevated'
		return 'normal'


class GlucoseReading(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	mmol_l: float = Field(gt=0, le=40)
	fasting: bool = True

	@property
	def level(self) -> str:
		if self.fasting:
			return 'high' if self.mmol_l >= 7.0 else ('impaired' if self.mmol_l >= 6.1 else 'normal')
		return 'high' if self.mmol_l >= 11.1 else ('impaired' if self.mmol_l >= 7.8 else 'normal')


class RefillTracker(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	drug: str
	days_remaining: int = Field(ge=0, le=180)
	facility_id: str | None = None