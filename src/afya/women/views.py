"""Women's health: menstrual cycle tracking (period prediction, fertile window, §17.6 adolescent protections)."""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class CycleLog(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	start_iso: str  # period start date
	cycle_days: int = Field(default=28, ge=20, le=45)
	pain_level: int = Field(default=0, ge=0, le=10)


class CyclePrediction(BaseModel):
	model_config = MODEL_CONFIG
	next_period_iso: str | None
	fertile_window_days: tuple[int, int] | None = None
	cycle_regularity: str = Field(pattern=r'^(regular|irregular|insufficient_data)$')
	advise: str