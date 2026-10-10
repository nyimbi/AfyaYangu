"""Privacy domain models — DPA 2019 / ODPC / Digital Health Act 2023 (spec §17)."""
from enum import Enum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class ConsentCategory(str, Enum):
	"""§SEC-001's eight consent categories, verbatim. Consent granularity is the claim, so the
	categories are a closed set rather than whatever string a caller sends."""
	symptom_storage = 'symptom_storage'
	location_tracking = 'location_tracking'
	proximity_logging = 'proximity_logging'
	sensor_monitoring = 'sensor_monitoring'
	share_health_authorities = 'share_health_authorities'
	share_chw = 'share_chw'
	cloud_backup = 'cloud_backup'
	research = 'research'


class ConsentScope(BaseModel):
	"""What one §SEC-001 category covers, and what withdrawing it costs.

	§SEC-001 requires "a clear statement of consequences of revocation" for every category, and that
	statement is the part a person reads. It is data here so a toggle cannot ship without one.
	"""
	model_config = MODEL_CONFIG
	category: ConsentCategory
	label: str = Field(min_length=1)
	# The plain-language sentence shown beside the toggle. No spec code reaches it.
	explains: str = Field(min_length=1)
	on_withdrawal: str = Field(min_length=1)
	# True only for `research`, which §SEC-001 marks "opt-in, separate": it must never be bundled
	# with a category a user needs to use the product.
	separate_from_core: bool = False
	# §SEC-001: "Sensor monitoring (each sensor separately)". The categories a sensor maps to are
	# per-sensor, so this lists the sensitivity classes it can cover rather than one blanket grant.
	per_sensor: bool = False

	@model_validator(mode='after')
	def _only_research_is_separate(self) -> Self:
		"""§SEC-001 marks research alone as "opt-in, separate". A second separate category would mean
		some other consent was being withheld from the core flow too, which the spec does not say."""
		if self.separate_from_core and self.category is not ConsentCategory.research:
			raise ValueError(f'{self.category.value} is not marked separate by §SEC-001')
		return self


class ConsentToggle(BaseModel):
	"""One grant, resolved. §SEC-001 wants granular toggles, one-tap revocation, and a consent audit
	log visible to the user — so a toggle carries its own state and the audit entry that set it."""
	model_config = MODEL_CONFIG
	category: ConsentCategory
	label: str
	explains: str
	on_withdrawal: str
	granted: bool
	# For `sensor_monitoring`: the per-sensor grants, because §SEC-001 asks for each sensor
	# separately and a single boolean would collapse eight decisions into one.
	sensors: dict[str, bool] = {}
	separate_from_core: bool = False
	revocable: bool = True


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


class Principal(BaseModel):
	"""Who the request is, as resolved from its token (§17 RBAC).

	Both halves travel together because a route that serves personal data needs the role as well
	as the subject: `self` scope alone cannot distinguish a citizen reading their own record from
	one naming a stranger's.
	"""

	model_config = MODEL_CONFIG
	subject_ref: str
	role: RBACRole


# Roles that act only for themselves. A worker role reaches other people's records through its own
# scoped routes, never by naming a subject on a citizen endpoint.
CITIZEN_ROLES: frozenset[RBACRole] = frozenset({RBACRole.citizen_anonymous, RBACRole.citizen_identified})


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
	# §24.8's clock is the DPA's 72 hours from detection, so a breach notified after it is a
	# different fact from one notified inside it — and `odpc_deadline_days` clamped at zero made
	# the two identical. `overdue` carries the distinction the deadline itself loses.
	overdue: bool = False


class AuditEntry(BaseModel):
	model_config = MODEL_CONFIG
	entry_id: str = Field(default_factory=uuid7str)
	role: RBACRole
	dataset: str
	allowed: bool
	ref: dict[str, Any] = Field(default_factory=dict)