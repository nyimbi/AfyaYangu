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
