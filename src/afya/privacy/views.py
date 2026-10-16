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
	# Where the grant was made. §SEC-001's registry spans channels — a USSD grant and an app grant
	# are one record — and `record_consent_for_phone` writes through the same door, so without this
	# the log cannot say which session a line came from.
	channel: str = Field(pattern='^(app|ussd|sms|whatsapp|chw|unknown)$', default='app')
	# The language the person was given the explanation in. §SEC-001's first Feature bullet is
	# "plain-language explanations in local languages", and the log's whole design is that an event
	# carries the words the person was shown *then* rather than looking them up now — so it has to
	# record which language those words were in, or a Swahili grant is logged as an English one and
	# the person's own history misdescribes the conversation they had.
	#
	# It is also evidence about the consent itself: DPA 2019 requires consent to be *informed*, and
	# a record that cannot say whether the person could read what she agreed to is a weaker record.
	lang: str = Field(default='en', min_length=2, max_length=8)


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
	# The language `label`, `explains` and `on_withdrawal` are actually in, and whether that is not
	# the one asked for. §SEC-001's first Feature bullet is "plain-language explanations in *local
	# languages*", and `TriageResult.served_in` established the rule this follows: a language with
	# no table is served English and *told so*, rather than shown English a client renders as
	# Dholuo. On this screen that matters more than anywhere else — a person who cannot read the
	# explanation cannot give informed consent to what it describes.
	served_in: str = 'en'
	language_fallback: bool = False


class ConsentEvent(BaseModel):
	"""One thing that happened to a person's consent, as the person reads it back.

	§SEC-001 asks for a *consent audit log visible to the user*, and `ConsentToggle`'s own docstring
	already claimed it carried "the audit entry that set it" — it carried no such field, and the
	ledger behind it was a `dict` with no history at all. A `ConsentRecord` holds the state *now*:
	`withdrawn` is a boolean, so the record of a grant that was later revoked and a grant that never
	happened are the same object with a different flag. "What did I agree to, and when" cannot be
	answered from it.

	`action` is the closed set of things that can happen, and it is closed because an open string
	would let a new code path write an event nobody wrote a sentence for. `label` and `consequence`
	are the catalogue's own words at the time of the event — a person reading back a withdrawal six
	months later is owed what they were told *then*, which is why they are copied onto the event
	rather than looked up from the catalogue at read time.
	"""

	model_config = MODEL_CONFIG
	event_id: str = Field(default_factory=uuid7str)
	# Carried because a purge deletes the record the event was about: resolved from the record at
	# read time, the last line of a person's own history would be the one that disappears.
	subject_ref: str
	at_ms: int = Field(ge=0)
	action: str = Field(pattern='^(granted|withdrawn|sensor_granted|sensor_withdrawn|purged)$')
	category: str
	label: str
	consequence: str
	# The language the label and consequence are in. The event copies the catalogue's words so a
	# reworded catalogue cannot rewrite a person's history; this field is the other half of that,
	# because a copy of the *English* sentence is not what a person who read the Swahili one was
	# shown. A log that could not say which language a line was in would misdescribe the consent it
	# is the record of.
	lang: str = Field(default='en', min_length=2, max_length=8)
	# Where the grant was made. §SEC-001's ledger spans channels — a USSD grant and an app grant are
	# one record — so the log has to say which one this was, or a person cannot tell the session
	# they do not remember from the one they do.
	channel: str = Field(pattern='^(app|ussd|sms|whatsapp|chw|unknown)$', default='app')
	retention_days: int | None = Field(default=None, ge=1, le=3650)
	legal_basis: LegalBasis | None = None


class ConsentHistory(BaseModel):
	"""A subject's own consent log, newest first, with the grants that stand right now.

	`events` empty and `live` empty is a person who has granted nothing — and the two are reported
	separately rather than merged, because "nothing has ever happened" and "everything was withdrawn"
	are different facts about the same blank screen.
	"""

	model_config = MODEL_CONFIG
	subject_ref: str
	events: list[ConsentEvent]
	live: list[str]
	note: str


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


class AccessPurpose(str, Enum):
	"""Why a route reaches the personal data it reaches (§17.4's last sentence).

	The section names no vocabulary — "Access to personal data requires a documented purpose" is the
	whole of it — so the set is derived from what §17.4's own Access cells say each role does with
	another person's data, and `PURPOSE_FOR_SCOPE` below ties each purpose to the scope that carries
	it. Inventing purposes the table does not describe would be a second, quieter spec.

	`consented_care` is the clinician's: the cell is "Patients who have consented to share", and the
	purpose is the share. It is deliberately not `case_management` — a clinician reading through a
	grant is doing a different thing from a CHW managing an assigned case, and a vocabulary that
	collapsed them could not tell the two apart in the ledger, which is the one question the ledger
	exists to answer.
	"""
	case_management = 'case_management'
	outbreak_surveillance = 'outbreak_surveillance'
	contact_tracing = 'contact_tracing'
	community_health_delivery = 'community_health_delivery'
	consented_care = 'consented_care'


# Which scopes reach another person's data, and the purposes each may declare. A scope absent from
# this map needs no purpose because it reaches no one else's record: `self` is the data subject,
# `family` is their own minor (§17.6), and the aggregate scopes carry no person at all.
#
# `assigned` carries four because a CHW's work is four different things — §17.4's cell is "Assigned
# patients, community aggregates", and a case read, a surveillance report, a contact trace and a
# community delivery are distinct enough that one word for all of them would document nothing.
PURPOSE_FOR_SCOPE: dict[str, frozenset[AccessPurpose]] = {
	'assigned': frozenset({
		AccessPurpose.case_management,
		AccessPurpose.outbreak_surveillance,
		AccessPurpose.contact_tracing,
		AccessPurpose.community_health_delivery,
	}),
	'consented_patient': frozenset({AccessPurpose.consented_care}),
}

# Both directions, the `ROLE_ACCESS` idiom: a purpose no scope can declare fails here rather than
# sitting dead in the enum, and a scope that requires purposes must have at least one or the map is
# a gate that refuses everything.
assert set(PURPOSE_FOR_SCOPE) <= {s for scopes in _SCOPE.values() for s in scopes}, \
	'every purpose-requiring scope is a scope §17.4 gives a role'
assert all(PURPOSE_FOR_SCOPE.values()), 'a scope requiring a purpose must offer at least one'
assert {p for ps in PURPOSE_FOR_SCOPE.values() for p in ps} == set(AccessPurpose), \
	'every purpose is declarable by some scope, and no purpose is extra'


class AccessRequest(BaseModel):
	"""One access decision, as it is made and as it is logged.

	`purpose` is optional *here* and mandatory at the route: `check_access` is also called in-process
	— the in-memory list and the tests — where there is no route and nothing to declare. What makes
	it mandatory is `require_scope(..., purpose=...)`, and what proves it did is
	`rbac.undocumented_access()`, which reads the routes and reports the ones reaching another
	person's data with nothing declared. A required field here would break the in-process callers
	for no accountability gain, since a caller that wanted to lie could send any member.
	"""
	model_config = MODEL_CONFIG
	role: RBACRole
	dataset: str
	purpose: AccessPurpose | None = None


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
	"""The processing a DPIA is being run over, one field per topic §17.3 lists.

	The section names eight topics and this carried five, so three of them — location tracking and
	geofencing, contact tracing assistance, and data sharing with health authorities — could not be
	described to the assessment at all. A topic with no field is a topic the DPIA is structurally
	unable to find, which is worse than one it finds and clears: the report reads as complete.
	"""
	model_config = MODEL_CONFIG
	processing_id: str = Field(default_factory=uuid7str)
	raw_sensor_data_retained: bool = False
	automated_decisions: bool = False
	cross_border_transfer: bool = False
	children_data: bool = False
	proximity_logging: bool = False
	location_tracking: bool = False
	contact_tracing: bool = False
	data_sharing_with_authorities: bool = False


class Tier4ActivationRequest(DPIAInput):
	"""§11.1's three keys, §17.3's eight topics, and §24.7's bulletin — one flat body.

	The operator's form offers one control per topic and one per key, because on this form the
	flags *are* the content: §SEC-005's assessment is a statement about what the deployment does,
	and a simplified version would record an assessment nobody made
	(`test_the_privacy_assessment_forms_are_not_simplified`). Both shipped clients put every
	non-path field of a write into the JSON body, so those controls arrive as top-level keys —
	while the route read a nested `dpia_input` object beside `auth`, which no client could build.
	The operator set ten switches and read a 422 naming a field they had set.

	A subclass of `DPIAInput` rather than a second model holding one: the topics are the assessment
	and the assessment is what is being authorised, so the two cannot be described separately
	without one of them going stale. Declared rather than lifted in a `model_validator`, because
	the OpenAPI document is what a client is generated from and a topic that appears only in a
	validator is a topic the document does not list — the same defect one level up.
	"""
	model_config = MODEL_CONFIG
	authorized_by_pheoc: bool = False
	flag_enabled: bool = False
	bulletin_text: str | None = None
	# §17.3's review is a record, so the key names the record it was held by — and nothing else
	# holds it. `dpia_reviewed` used to be a stored boolean, which made it a field a caller could
	# set: a request carrying `dpia_reviewed: true` and no DPIA at all turned the outbreak
	# capabilities on. It is derived now, so there is no path to the key except recording a review.
	dpia_review_id: str | None = None
	# The nested spelling, still accepted: the operator tooling and the tests post the processing
	# as an object, and both spellings describe the same topics. Declared rather than popped, so a
	# body that carried the nested object is still one the document describes.
	dpia_input: DPIAInput | None = None

	@model_validator(mode='before')
	@classmethod
	def _merge_nested_dpia(cls, data: Any) -> Any:
		"""Fold a nested `dpia_input` into the flat topics, so both spellings name one processing."""
		if not isinstance(data, dict) or not isinstance(data.get('dpia_input'), dict):
			return data
		return {**data['dpia_input'], **data}

	def processing(self) -> DPIAInput | None:
		"""The processing this request describes, or None when it describes none.

		None rather than an all-false assessment, because §17.3's key is held by a *recorded review
		of a described processing*: a request that named no processing has nothing for a review to
		cover, and assessing an empty one would report risks about a deployment nobody described.
		"""
		topics = {name: getattr(self, name) for name in DPIAInput.model_fields if name != 'processing_id'}
		if self.dpia_input is None and not any(topics.values()):
			return None
		return DPIAInput(**topics)

	def dpia_reviewed(self) -> bool:
		"""§17.3's key: held only by a recorded review that still covers this processing."""
		return self.dpia_review_id is not None


class DPIAReport(BaseModel):
	model_config = MODEL_CONFIG
	risks: list[str]
	requires_dpia: bool
	blocked: bool


class DPIARecord(BaseModel):
	"""A conducted DPIA, and the answer §17.3's last line needs.

	"Reviewed and updated before each Tier 4 activation" is a statement about a review that
	happened, so the gate cannot be satisfied by a boolean the caller supplies about itself. This
	carries which assessment was reviewed and when, and `covers_current_processing` is what decides
	whether it still answers for the processing now being turned on.
	"""
	model_config = MODEL_CONFIG
	review_id: str = Field(default_factory=uuid7str)
	reviewed_at_iso: str
	reviewed_by: str
	processing_id: str
	fingerprint: str
	topics: list[str]
	risks: list[str]
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


# --- §17.1 instruments and §17.2 principles -------------------------------------------------------

class InstrumentKind(str, Enum):
	"""How binding an instrument is, which is what decides whether a gap in it is a defect or a
	target. Four of §17.1's six are Kenyan law; the ODPC note is regulatory guidance with no
	statute behind it; the WHO Regulations are international law the Republic is a party to and the
	DPA is not."""

	statute = 'statute'
	regulatory_guidance = 'regulatory_guidance'
	international = 'international'


class ObligationKind(str, Enum):
	"""What a §17.1 Implementation cell promises. The four are the spec's own vocabulary, and the
	distinction is load-bearing: a `process` obligation is a human duty with nothing to point at,
	while a `code` one names the software, so a claim that a control exists can be walked rather
	than believed."""

	code = 'code'
	process = 'process'
	registration = 'registration'
	agreement = 'agreement'


class InstrumentObligation(BaseModel):
	"""One Implementation item, transcribed verbatim from §17.1's cell.

	`control` is a `module:attr` reference and is None for a `process` obligation — the same rule
	§23's risk register applies, and for the same reason: a row claiming software enforcement has to
	name the software, so the validator refuses a `code` obligation with nothing behind it.
	"""

	model_config = MODEL_CONFIG
	obligation: str = Field(min_length=1)
	kind: ObligationKind
	control: str | None = None

	@model_validator(mode='after')
	def _a_code_obligation_names_its_code(self) -> Self:
		if self.kind is ObligationKind.code and not self.control:
			raise ValueError(f'{self.obligation} claims code enforcement but names no module')
		return self


class RegulatoryInstrument(BaseModel):
	"""One §17.1 row: the instrument, what it requires, and what the spec says implements it."""

	model_config = MODEL_CONFIG
	instrument: str = Field(min_length=1)
	kind: InstrumentKind
	requirement: str = Field(min_length=1)
	obligations: list[InstrumentObligation] = Field(min_length=1, frozen=True)


class InstrumentAssessment(BaseModel):
	"""A §17.1 obligation beside the answer to "is it actually done".

	`unbacked` is the finding, and it has three ways to be true: a `code` reference that does not
	land, a `registration` or `agreement` with no live record behind it, and a `process` obligation
	with no §24 duty that schedules it — the last being the one that hides, because a process item
	nobody owns reads exactly like a process item somebody does.
	"""

	model_config = MODEL_CONFIG
	instrument: str
	obligation: str
	kind: ObligationKind
	control: str | None
	resolves: bool
	backed: bool
	note: str


class PrincipleImplementation(BaseModel):
	"""One §17.2 principle and every artefact the spec names as its implementation.

	§17.2 writes its Implementation cell as a list — "Content reviewed weekly; user data editable;
	correction workflows" is three claims — and a single boolean over the cell would let two of the
	three be missing while the row read covered. So the artefacts are a list, each with its own
	reference, and `unbacked_artifacts` is what a reviewer wants: the parts of the claim that are
	not there.
	"""

	model_config = MODEL_CONFIG
	principle: str = Field(min_length=1)
	implementation: str = Field(min_length=1)
	artifacts: list[InstrumentObligation] = Field(min_length=1, frozen=True)
	unbacked_artifacts: list[str]
	backed: bool


class RegulatoryReport(BaseModel):
	model_config = MODEL_CONFIG
	instruments: list[RegulatoryInstrument]
	assessments: list[InstrumentAssessment]
	principles: list[PrincipleImplementation]
	unbacked: list[str]
	instrument_count: int
	obligation_count: int
