"""Triage domain models (spec TRI-001/002/003, §6.3 malaria trap, §8.1)."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class RiskLevel(str, Enum):
	low = 'low'
	medium = 'medium'
	malaria_suspect = 'malaria_suspect'
	high = 'high'


EBOLA_SYMPTOMS: frozenset[str] = frozenset({'fever', 'headache', 'muscle_pain', 'sore_throat', 'vomiting', 'diarrhoea', 'rash', 'bleeding'})


class TriageInput(BaseModel):
	model_config = MODEL_CONFIG
	symptoms: list[str] = []
	temperature_c: float = Field(default=36.5, ge=30, le=45)
	ebola_contact: bool = False
	affected_area_travel: bool = False


class TriageResult(BaseModel):
	model_config = MODEL_CONFIG
	risk_level: RiskLevel
	recommendation: str
	treated_as_malaria_first: bool
	escalate_719: bool


class DiaryEntry(BaseModel):
	model_config = MODEL_CONFIG
	entry_id: str = Field(pattern=r'^DIARY-[A-Z0-9]{10,}$')
	subject_ref: str
	day: int = Field(ge=1, le=21)
	symptoms: list[str]
	temperature_c: float = Field(ge=30, le=45)
	synced: bool = False


RECOMMENDATIONS: dict[RiskLevel, str] = {
	RiskLevel.low: 'Monitor; standard hygiene; hydrate; call 719 if worsening.',
	RiskLevel.malaria_suspect: 'Febrile illness: test and treat for malaria FIRST (spec 6.3 malaria trap); call 719 if no improvement in 48h.',
	RiskLevel.medium: 'Contact hotline 719; self-monitor; isolate from household if symptoms progress.',
	RiskLevel.high: 'Isolate immediately; call 719; go to nearest isolation treatment unit.',
}