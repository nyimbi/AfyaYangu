"""Environment & community-alert layer: water quality, air quality, flood→cholera risk, school closures, multi-disease outbreak alerts."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class AlertKind(str, Enum):
	outbreak_cholera = 'outbreak_cholera'
	outbreak_malaria = 'outbreak_malaria'
	outbreak_dengue = 'outbreak_dengue'
	outbreak_mpox = 'outbreak_mpox'
	outbreak_rvf = 'outbreak_rvf'
	outbreak_evd = 'outbreak_evd'
	flood = 'flood'
	water_quality = 'water_quality'
	school_closure = 'school_closure'
	public_health_notice = 'public_health_notice'


class CommunityAlert(BaseModel):
	model_config = MODEL_CONFIG
	alert_id: str = Field(pattern=r'^AL-[A-Z0-9]{8,}$')
	kind: AlertKind
	county: str
	headline: str = Field(max_length=80)
	body: str = Field(max_length=400)
	issued_by: str = Field(pattern=r'^(MoH|PHEOC|County|KMD)$')
	multi_disease: bool = False

	@classmethod
	def outbreak(cls, alert_id: str, disease: AlertKind, county: str, headline: str, body: str) -> 'CommunityAlert':
		return cls(alert_id=alert_id, kind=disease, county=county, headline=headline, body=body, issued_by='PHEOC', multi_disease=disease is not AlertKind.outbreak_evd)


class WaterQuality(BaseModel):
	model_config = MODEL_CONFIG
	county: str
	ecoli_detected: bool
	turbidity_ntu: float = Field(ge=0, le=400)

	@property
	def unsafe(self) -> bool:
		return self.ecoli_detected or self.turbidity_ntu > 5.0


class AirQuality(BaseModel):
	model_config = MODEL_CONFIG
	county: str
	pm25: float = Field(ge=0, le=500)

	@property
	def band(self) -> str:
		return 'alert' if self.pm25 > 55 else ('watch' if self.pm25 > 35 else 'normal')


class FloodReport(BaseModel):
	model_config = MODEL_CONFIG
	county: str
	rainfall_mm_72h: float = Field(ge=0, le=500)
	population_at_risk: int = Field(default=0, ge=0)

	@property
	def cholera_risk(self) -> str:
		return 'high' if self.rainfall_mm_72h >= 100 else ('moderate' if self.rainfall_mm_72h >= 50 else 'low')