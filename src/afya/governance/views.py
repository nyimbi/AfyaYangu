"""Data residency, sharing agreements and scale targets (spec §15.3, §15.4, §17.7, §22.5)."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class Jurisdiction(str, Enum):
	kenya = 'kenya'
	african_union = 'african_union'
	outside_africa = 'outside_africa'


class DataClass(str, Enum):
	"""What kind of data a wire carries. The class, not the vendor, decides where it may go:
	the same vendor can carry two classes with different residency rules."""

	case_management = 'case_management'
	contact_tracing = 'contact_tracing'
	citizen_personal = 'citizen_personal'
	anonymised_analytics = 'anonymised_analytics'


# §15.3. Case management and contact tracing are the two the spec says may be deployed on-premise
# at MoH; neither may leave Kenya at all. Citizen personal data may sit anywhere in the AU.
# Only anonymised analytics may be processed outside African jurisdictions.
RESIDENCY_RULES: dict[DataClass, frozenset[Jurisdiction]] = {
	DataClass.case_management: frozenset({Jurisdiction.kenya}),
	DataClass.contact_tracing: frozenset({Jurisdiction.kenya}),
	DataClass.citizen_personal: frozenset({Jurisdiction.kenya, Jurisdiction.african_union}),
	DataClass.anonymised_analytics: frozenset({Jurisdiction.kenya, Jurisdiction.african_union, Jurisdiction.outside_africa}),
}

# §15.3 "No data transfer outside African jurisdictions without explicit legal review." That clause
# is not a prohibition, it is a gate: for these classes an outside-Africa transfer is permitted
# *given* the §17.7 agreement with that party, which is the legal review the sentence names. The
# two sections are one rule, which is why they are enforced together rather than apart.
LEGAL_REVIEW_EXCEPTION: frozenset[DataClass] = frozenset({DataClass.citizen_personal})

# Longest suffix wins, so `.health.go.ke` is not shadowed by a shorter `.ke` rule added later.
HOST_JURISDICTIONS: tuple[tuple[str, Jurisdiction], ...] = (
	('.health.go.ke', Jurisdiction.kenya),
	('.go.ke', Jurisdiction.kenya),
	('.ac.ke', Jurisdiction.kenya),
	('.africastalking.com', Jurisdiction.kenya),  # Nairobi-headquartered; the SMS gateway
	('.safaricom.co.ke', Jurisdiction.kenya),
	('.graph.facebook.com', Jurisdiction.outside_africa),
	('.amazonaws.com', Jurisdiction.outside_africa),
	('.azure.com', Jurisdiction.outside_africa),
	('.googleapis.com', Jurisdiction.outside_africa),
)


class AgreementParty(str, Enum):
	"""§17.7's seven. `cloud_provider` and `research_partner` are plural in reality; they are one
	party each here because the agreement is the unit the spec names."""

	ministry_of_health = 'ministry_of_health'
	county_health = 'county_health'
	adam_icap = 'adam_icap'
	telco = 'telco'
	meta_whatsapp = 'meta_whatsapp'
	cloud_provider = 'cloud_provider'
	research_partner = 'research_partner'


class DataSharingAgreement(BaseModel):
	"""§17.7: "Each agreement specifies purpose, scope, retention, security, and audit rights."

	`signed` is a fact about the world, not a flag anyone may set to make a wire legal — so it is
	paired with `signed_on_iso` and a `legal_review_ref`, and `may_share` requires all three. An
	agreement recorded as signed with no date or review reference is a claim, not an agreement.
	"""

	model_config = MODEL_CONFIG
	party: AgreementParty
	purpose: str = Field(min_length=1)
	scope: list[str] = Field(min_length=1)
	retention_days: int = Field(ge=1)
	security: str = Field(min_length=1)
	audit_rights: str = Field(min_length=1)
	signed: bool = False
	signed_on_iso: str | None = None
	legal_review_ref: str | None = None

	def may_share(self) -> bool:
		"""Whether this agreement permits sharing. The clause fields are non-empty by construction
		(the model refuses an empty one), so the open question is only whether it is *signed* — and
		a signature with no date or review reference is a claim, not an agreement."""
		return self.signed and bool(self.signed_on_iso) and bool(self.legal_review_ref)


class ResidencyDecision(BaseModel):
	"""One egress decision: where a host sits, whether the class may go there, and why."""

	model_config = MODEL_CONFIG
	party: str
	host: str
	jurisdiction: Jurisdiction
	data_class: DataClass
	allowed: bool
	reason: str


class ScaleTarget(BaseModel):
	model_config = MODEL_CONFIG
	metric: str
	target: float
	unit: str
	source: str  # which spec section the number comes from


class CapacityCheck(BaseModel):
	"""§15.4 measured, not assumed.

	`observed` is None for a target the deployment has not measured — reported as unmeasured rather
	than counted as met, because a capacity report that treats silence as compliance is the failure
	mode this whole module exists to avoid.
	"""

	model_config = MODEL_CONFIG
	metric: str
	target: float
	observed: float | None
	unit: str
	within_target: bool | None

	def met(self) -> bool:
		return self.within_target is True


class CapacityReport(BaseModel):
	model_config = MODEL_CONFIG
	checks: list[CapacityCheck]
	unmeasured: list[str]
	all_measured_targets_met: bool


class StackStatus(str, Enum):
	"""Whether the build runs what §15.2 names.

	`shipped` is the layer the repo actually contains; `deferred` is one the spec names and the
	programme has not stood up; `diverged` is a layer running something other than the spec's choice.
	The three are different answers and collapsing them would let a deferral read as a divergence or
	a divergence as compliance.
	"""

	shipped = 'shipped'
	deferred = 'deferred'
	diverged = 'diverged'


class StackLayer(BaseModel):
	"""One §15.2 row: the layer, the technology the section names, and what the build runs.

	`actual` is None where nothing has been stood up, and `evidence` names what in the repo backs the
	claim — a `module:attr` reference for a layer that is code, a path for a layer that is
	configuration. A layer with no evidence is reported rather than trusted: the spec's stack table
	is a claim about what runs, and a claim about what runs with nothing pointing at it is the
	§15.2 version of an unbacked mitigation.
	"""

	model_config = MODEL_CONFIG
	layer: str
	specified: str
	rationale: str
	status: StackStatus
	actual: str | None = None
	evidence: str | None = None
	resolves: bool = False
	note: str | None = None


class ArchitectureComponent(BaseModel):
	"""One box in §15.1's diagram, and the module that is it."""

	model_config = MODEL_CONFIG
	name: str
	band: str
	module: str | None = None
	resolves: bool = False
	note: str | None = None


class StackReport(BaseModel):
	model_config = MODEL_CONFIG
	layers: list[StackLayer]
	components: list[ArchitectureComponent]
	unbacked_layers: list[str]
	unresolved_components: list[str]
	deferred_layers: list[str]
	diverged_layers: list[str]
