"""Risk register, incident response and operational obligations (spec §23, §24).

§23 is thirty-three named risks with a mitigation column; §24 is six governance bodies, four
operational cadence tables, a support SLA ladder, a training matrix, a funding model and an
incident-response table. All of it was prose. Prose cannot be checked, which is why the mitigation
column is the interesting one: "automated staleness alerts", "bug bounty", "transparency reports",
"disaster recovery", "manual fallback" are claims about software, and each either resolves to a
module in this repo or does not.

`control` is a `module:attr` reference, so the register can be asked whether the mitigation it
names actually exists. `trigger` and `cadence_days` are how an obligation recurs — an obligation
with neither is one nobody can be late for, which is why the model refuses the empty case.
"""
from enum import Enum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Reused rather than restated: §23's mitigations are enforced in exactly the three places §17.5's
# controls are, and two enums describing one thing drift apart.
from afya.security.views import ControlKind

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class RiskDomain(str, Enum):
	"""§23's five subsections. The domain is not decoration: §23.4's risks carry a Very High impact
	at Low likelihood, which is a different disposition from §23.2's High/Medium, and a register
	that flattened them would rank a content-ops slip above proximity deanonymisation."""

	strategic = 'strategic'
	operational = 'operational'
	technical = 'technical'
	privacy_ethical = 'privacy_ethical'
	reputational = 'reputational'


class Rating(str, Enum):
	"""§23's likelihood and impact vocabulary, ordered. The order is the point: `Rank.very_high`
	must outrank `Rank.low` for a register that sorts by exposure to be meaningful at all."""

	low = 'low'
	medium = 'medium'
	high = 'high'
	very_high = 'very_high'

	@property
	def rank(self) -> int:
		return _RANK[self]


_RANK: dict[Rating, int] = {Rating.low: 1, Rating.medium: 2, Rating.high: 3, Rating.very_high: 4}

# §23's impact column uses "Very High" in one row of each of §23.3, §23.4 and §23.5; likelihood
# never exceeds High in the spec. The enum admits it anyway rather than encoding a ceiling the spec
# might later raise — an out-of-range value is a data error, not a shape error.
MAX_LIKELIHOOD = Rating.high


class Risk(BaseModel):
	"""One §23 row. `control` names what discharges the mitigation, in `module:attr` form, or is
	None for a mitigation that is genuinely a human process — and `control_kind` says which.

	A `code` control with no `control` reference is the failure this model exists to make
	unrepresentable, so the validator refuses it: a mitigation claiming software enforcement has to
	say which software.
	"""

	model_config = MODEL_CONFIG
	risk_id: str = Field(pattern=r'^R-[A-Z]\d+$')
	domain: RiskDomain
	statement: str = Field(min_length=1)
	likelihood: Rating
	impact: Rating
	mitigation: str = Field(min_length=1)
	control_kind: ControlKind
	control: str | None = None
	owner: str = Field(min_length=1)

	def exposure(self) -> int:
		"""Likelihood times impact, so the register can be read in order of what to fix first."""
		return self.likelihood.rank * self.impact.rank

	@model_validator(mode='after')
	def _a_code_control_names_its_code(self) -> Self:
		"""A mitigation that claims software enforcement has to name the software. Without this a
		row could read `control_kind=code` with nothing behind it and pass every check that only
		asks whether a kind was given."""
		if self.control_kind is ControlKind.code and not self.control:
			raise ValueError(f'{self.risk_id} claims code enforcement but names no module')
		return self


class RiskAssessment(BaseModel):
	"""A §23 row beside the answer to "does the mitigation exist". `resolves` is False for a code
	control whose named module is absent, and `note` says why — an unresolvable reference is a
	register entry that reads as covered and is not."""

	model_config = MODEL_CONFIG
	risk: Risk
	resolves: bool
	note: str


class IncidentClass(str, Enum):
	"""§24.8's seven incident types, as ids rather than prose rows."""

	data_breach = 'data_breach'
	system_outage = 'system_outage'
	false_alert = 'false_alert'
	misinformation_spike = 'misinformation_spike'
	clinical_content_error = 'clinical_content_error'
	privacy_complaint = 'privacy_complaint'
	security_vulnerability = 'security_vulnerability'


class IncidentSeverity(str, Enum):
	"""§24.3's support SLA ladder, which §24.8's severity column reuses."""

	critical = 'critical'
	high = 'high'
	medium = 'medium'
	low = 'low'


# §24.3's response SLAs, in hours. The spec gives minutes for one row, so the ladder is in hours and
# a quarter-hour critical is 0.25 — one unit means a comparison between two rungs cannot be wrong
# about which is faster. It lives here rather than in the service because `IncidentKind.sla_hours`
# reads it and the model cannot import the service that imports the model.
SUPPORT_SLA_HOURS: dict[IncidentSeverity, float] = {
	IncidentSeverity.critical: 0.25,
	IncidentSeverity.high: 2.0,
	IncidentSeverity.medium: 24.0,
	IncidentSeverity.low: 168.0,
}


class IncidentKind(BaseModel):
	"""One §24.8 row: what the incident is, how bad, what the response is, and — the part that
	makes it a control rather than a paragraph — the deadline it must be discharged within.

	`deadline_hours` is None for the rows §24.8 describes without a number ("rapid response
	protocol", "immediate correction"). Those are not missing data: the spec sets no clock, so
	inventing one would be the fabrication this repo keeps refusing. `sla_hours` carries the §24.3
	ladder entry the severity maps to, which is the number that does exist.
	"""

	model_config = MODEL_CONFIG
	kind: IncidentClass
	severity: IncidentSeverity
	response: str = Field(min_length=1)
	deadline_hours: int | None = None
	deadline_basis: str | None = None
	notifies: list[str] = Field(default_factory=list)

	def sla_hours(self) -> float:
		return SUPPORT_SLA_HOURS[self.severity]


class Incident(BaseModel):
	"""A recorded incident. `opened_at_iso` and `detected_at_iso` are separate because §24.8's
	breach clock starts at detection, and a response measured from when someone noticed is the only
	one the ODPC counts."""

	model_config = MODEL_CONFIG
	incident_id: str = Field(min_length=1)
	kind: IncidentClass
	opened_at_iso: str = Field(min_length=10)
	detected_at_iso: str = Field(min_length=10)
	summary: str = Field(min_length=1)
	affected_count: int = Field(default=0, ge=0)


class IncidentStatus(BaseModel):
	"""Where an incident stands against its own deadline. `overdue` is a fact about the clock, not
	a flag a handler sets — the reason a breach deadline has to be computed rather than asserted."""

	model_config = MODEL_CONFIG
	incident_id: str
	kind: IncidentClass
	severity: IncidentSeverity
	hours_elapsed: float
	deadline_hours: int | None
	hours_remaining: float | None
	overdue: bool
	notifies: list[str]
	response: str


class SupportSla(BaseModel):
	"""§24.3's response ladder, one row per severity."""

	model_config = MODEL_CONFIG
	severity: IncidentSeverity
	definition: str
	response_hours: float
	response_label: str


class GovernanceBody(BaseModel):
	"""One §24.1 row: a body, who sits on it, and what it decides.

	`slug` is what §24's duty rows use as an `owner` (`clinical_advisory_group`, `community_advisory_panel`)
	and `body` is the section's own name for it ("Clinical Advisory Group"). The two are kept apart
	because the owners are lowercase identifiers written into `OBLIGATIONS` and the names are what a
	governance document says — collapsing them would mean either the register carrying prose or the
	section's names being rewritten to slugs.
	"""

	model_config = MODEL_CONFIG
	slug: str = Field(min_length=1)
	body: str = Field(min_length=1)
	composition: list[str] = Field(min_length=1)
	role: str = Field(min_length=1)
	# The §24 duty owners this body accounts for. Stated rather than derived: §24.2–§24.7 name owners
	# as role slugs (`clinical_advisory_group`, `content_lead`) and §24.1 names bodies and the roles
	# that sit on them, so the join is a reading of two vocabularies. It is written down here so the
	# reading can be checked and corrected, rather than living in a reader's head.
	owners: list[str] = Field(default_factory=list)


class SupportChannel(BaseModel):
	"""One §24.3 row: a support channel, its coverage window, and who staffs it.

	`coverage` is the section's own string — "8am–8pm, 7 days" and "24/7 (self-service)" are not the
	same commitment and a boolean `always_on` would flatten the difference between a staffed line and
	a help page. `staffing` is None for the self-service row, where the section writes an em dash
	rather than a headcount; a zero there would read as an unstaffed channel.
	"""

	model_config = MODEL_CONFIG
	channel: str = Field(min_length=1)
	coverage: str = Field(min_length=1)
	staffing: str | None = None
	always_on: bool
	agents: int | None = Field(default=None, ge=0)


class GovernanceReport(BaseModel):
	"""§24.1 and §24.3 crossed against §24's duty rows — who governs, and who answers the phone.

	`unowned_bodies` is the finding. §24.1 names six bodies and §24.2–§24.7 assign duties to owners;
	a body with no duty behind it is a committee that meets and decides nothing, and the register
	cannot tell the difference between it and one that governs. `unstaffed_channels` is the reverse
	for §24.3: a support channel with no coverage window is one a person can reach and nobody reads.
	"""

	model_config = MODEL_CONFIG
	bodies: list[GovernanceBody]
	support_channels: list[SupportChannel]
	duty_owners: list[str]
	unowned_bodies: list[str]
	unlisted_owners: list[str]
	unstaffed_channels: list[str]
	staffed_agents: int
	note: str


class TrainingRow(BaseModel):
	"""One §24.4 row: who is trained, on what, in what format, for how long.

	`hours` is the Duration column as a number so the matrix can be totalled and a cadence read off
	it; `duration` keeps the section's own string, because "2 days" and "4 hours" are both durations
	and only one of them is a number of hours. `audience` is the section's own label and `owner` the
	§24.1 body or §24 role accountable for delivering it, where one can be named without inventing
	one — the radio-partner briefing is run by the comms lead, and nothing in §24 says who trains the
	community leaders.
	"""

	model_config = MODEL_CONFIG
	audience: str = Field(min_length=1)
	content: str = Field(min_length=1)
	format: str = Field(min_length=1)
	duration: str = Field(min_length=1)
	hours: float = Field(gt=0)
	# The §24.1 body that owns this audience's training, joined on the composition §24.1 states.
	body: str | None = None


class FundingStage(BaseModel):
	"""One §24.5 row: a phase band, what pays for it, and what it moves toward.

	`sustainability` is None where the section writes an em dash — the emergency and build phases
	have no sustainability column because they are not meant to sustain, and a fabricated one would
	read as a plan for the thing the next row says has not started yet.
	"""

	model_config = MODEL_CONFIG
	phase: str = Field(min_length=1)
	primary_funding: list[str] = Field(min_length=1)
	sustainability: str | None = None
	# The §21 phases this band pays for, as the range its label states: "Phase 0–1" is 0 through 1,
	# "Phase 6+" is 6 to the last phase. A single ceiling was the first cut and it made the coverage
	# check vacuous — every phase is at or below the last band's ceiling by construction, so the
	# check could never name one. A range can be narrowed and a band dropped, which is what the check
	# is for.
	phase_floor: int = Field(ge=0)
	phase_ceiling: int = Field(ge=0)


class SupportPlan(BaseModel):
	"""§24.4's training matrix and §24.5's funding model as one answer.

	`untrained_audiences` is the finding. §24.4 names seven audiences and §24.1 names six bodies with
	the roles that sit on them; an audience no §24.1 body accounts for is a group of people expected
	to use the product with nobody in the governance structure responsible for teaching them.
	`unfunded_stages` is the other direction: a §21 phase no §24.5 band pays for.
	"""

	model_config = MODEL_CONFIG
	training: list[TrainingRow]
	funding: list[FundingStage]
	refresher: str
	new_feature_training: str
	cost_drivers: list[str]
	cost_mitigations: list[str]
	training_hours: float
	untrained_audiences: list[str]
	unfunded_stages: list[str]
	note: str


class SustainabilityMitigation(BaseModel):
	"""One §24.6 mitigation: what the section proposes, and — where the section names something that
	exists in this repo — a `module:attr` reference the register can resolve.

	§24.6's eight mitigations are the argument that the product survives the outbreak, and seven of
	them name a thing the build either has or has not: the brand that positions it as permanent
	infrastructure, the Tier 1–3 retention engine, the funding band that integrates it into the MoH
	budget, the multi-disease scope, the metric set that measures non-outbreak impact, the partner
	map and the open-source client. Those seven carry a `control` and resolve. The eighth — regional
	expansion — is a plan for other countries and names no artefact, so it carries no reference and
	is reported as unresolvable rather than given one that always lands.
	"""

	model_config = MODEL_CONFIG
	number: int = Field(ge=1, le=8)
	mitigation: str = Field(min_length=1)
	control: str | None = None


class SustainabilityReport(BaseModel):
	"""§24.6's eight mitigations crossed against the artefacts they name.

	Two lists, because the register distinguishes them and this section must too. `process_mitigations`
	is the mitigations naming no artefact at all — a commitment about the world, not a claim about
	the build, which is the `ControlKind.process` case §23's register already carries. `unbacked_
	mitigations` is the sharper failure: a mitigation that *names* a `module:attr` and does not
	resolve, which is a plan pointing at something that is not there.
	"""

	model_config = MODEL_CONFIG
	mitigations: list[SustainabilityMitigation]
	process_mitigations: list[str]
	unbacked_mitigations: list[str]
	note: str


class Obligation(BaseModel):
	"""One recurring §24 duty. `cadence_days` is None for an event-triggered duty, and then
	`trigger` names the event — §24.7's "on change" and "on publish" are real obligations that no
	calendar schedules, and modelling them as cadence 0 would make them look perpetually overdue."""

	model_config = MODEL_CONFIG
	obligation_id: str = Field(pattern=r'^OPS-\d+$')
	section: str
	owner: str = Field(min_length=1)
	duty: str = Field(min_length=1)
	cadence_days: int | None = None
	trigger: str | None = None
	control: str | None = None

	def recurs(self) -> bool:
		return self.cadence_days is not None or self.trigger is not None

	@model_validator(mode='after')
	def _a_duty_recurs_somehow(self) -> Self:
		"""§24 is a list of duties that come round again. A row with neither a cadence nor a trigger
		is one nobody can be late for, which is the state in which a duty quietly stops happening."""
		if not self.recurs():
			raise ValueError(f'{self.obligation_id} has neither a cadence nor a trigger')
		return self


class ObligationStatus(BaseModel):
	model_config = MODEL_CONFIG
	obligation_id: str
	duty: str
	owner: str
	section: str
	cadence_days: int | None
	trigger: str | None
	last_performed_iso: str | None
	due_on_iso: str | None
	overdue: bool


class OpsPosture(BaseModel):
	"""The whole of §23 and §24 as one answer a reviewer can read: what the register says, which
	mitigations resolve, which obligations are late, and how many rows of either name nothing."""

	model_config = MODEL_CONFIG
	risks: list[RiskAssessment]
	unbacked_risks: list[str]
	incident_kinds: list[IncidentKind]
	support_slas: list[SupportSla]
	obligations: list[ObligationStatus]
	overdue_obligations: list[str]
	open_incidents: list[IncidentStatus]
