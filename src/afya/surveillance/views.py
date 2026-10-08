"""Surveillance Tier-4 models — dormant outbreak superpower (spec §11, §19.4)."""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class CountySignal(BaseModel):
	model_config = MODEL_CONFIG
	county: str
	week_isoyear: int = Field(ge=2024, le=2100)
	week: int = Field(ge=1, le=53)
	fever_reports: int = Field(ge=0)
	hotline_calls: int = Field(ge=0)
	confirmed_cases: int = Field(ge=0)


class SignalReading(BaseModel):
	model_config = MODEL_CONFIG
	county: str
	z_score: float
	risk: str = Field(pattern=r'^(low|moderate|high)$')
	weeks_observed: int = Field(ge=1)


class ProximityToken(BaseModel):
	model_config = MODEL_CONFIG
	token: str = Field(min_length=32, max_length=64)
	seen_at_ms: int
	county: str
	exposure_risk: bool = False


class Geofence(BaseModel):
	model_config = MODEL_CONFIG
	geofence_id: str
	lat: float = Field(ge=-5, le=6)
	lon: float = Field(ge=33, le=43)
	radius_m: int = Field(gt=50, le=50_000)
	risk_type: str = Field(pattern=r'^(general|outbreak)$')
	alert_level: str = Field(pattern=r'^(low|medium|high)$')