"""Privacy domain models — DPA 2019 / ODPC / Digital Health Act 2023 (spec §17)."""
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from afya.ids import uuid7str

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class LegalBasis(str, Enum):
	consent = 'consent'
	legal_obligation = 'legal_obligation'
	legitimate_interest = 'legitimate_interest'


class ConsentRecord(BaseModel):
	model_config = MODEL_CONFIG
	consent_id: str = Field(default_factory=uuid7str)
	subject_ref: str
	purpose: str
	data_types: list[str]
	retention_days: int = Field(ge=1, le=3650)
	legal_basis: LegalBasis
	withdrawn: bool = False


class RBACRole(str, Enum):
	citizen_anonymous = 'citizen_anonymous'
	citizen_identified = 'citizen_identified'
	chw = 'chw'
	clinician = 'clinician'
	county_officer = 'county_officer'
	pheoc_analyst = 'pheoc_analyst'
	sysadmin = 'sysadmin'
	auditor = 'auditor'


_SCOPE: dict[RBACRole, set[str]] = {
	RBACRole.citizen_anonymous: {'self'},
	RBACRole.citizen_identified: {'self', 'family'},
	RBACRole.chw: {'assigned', 'community_aggregate'},
	RBACRole.clinician: {'consented_patient'},
	RBACRole.county_officer: {'county_aggregate'},
	RBACRole.pheoc_analyst: {'national_aggregate'},
	RBACRole.sysadmin: {'infrastructure'},
	RBACRole.auditor: {'audit_logs'},
}


class AccessRequest(BaseModel):
	model_config = MODEL_CONFIG
	role: RBACRole
	dataset: str


class DPIAInput(BaseModel):
	model_config = MODEL_CONFIG
	processing_id: str = Field(default_factory=uuid7str)
	raw_sensor_data_retained: bool = False
	automated_decisions: bool = False
	cross_border_transfer: bool = False
	children_data: bool = False
	proximity_logging: bool = False


class DPIAReport(BaseModel):
	model_config = MODEL_CONFIG
	risks: list[str]
	requires_dpia: bool
	blocked: bool


class BreachEvent(BaseModel):
	model_config = MODEL_CONFIG
	breach_id: str = Field(default_factory=uuid7str)
	detected_at_days_ago: int = 0
	affected_data: list[str]
	affected_count: int = 0


class BreachNotification(BaseModel):
	model_config = MODEL_CONFIG
	notification_id: str = Field(default_factory=uuid7str)
	odpc_deadline_days: int
	notify_users: bool
	summary: str


class AuditEntry(BaseModel):
	model_config = MODEL_CONFIG
	entry_id: str = Field(default_factory=uuid7str)
	role: RBACRole
	dataset: str
	allowed: bool
	ref: dict[str, Any] = Field(default_factory=dict)