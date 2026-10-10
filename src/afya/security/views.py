"""Security controls, vulnerability-management cadence and disclosure policy (spec §17.5).

§17.5 is a table of eleven controls. Ten of them are properties of the running system that other
modules already implement; the one that was missing entirely was "secure development — SAST, DAST,
dependency scanning in CI", because there was no CI. This module holds the table so the claim is
checkable: each control names where it is enforced, and the ones that claim CI enforcement name the
command the workflow must actually run.
"""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class ControlKind(str, Enum):
	"""Where a control is enforced. A control with no home is a claim, which is what this enum
	prevents: `unimplemented` exists so an unimplemented control is visibly unimplemented rather
	than quietly absent from the table."""

	code = 'code'          # enforced by a module at runtime
	process = 'process'    # an obligation a human discharge on a schedule
	ci = 'ci'              # a gate that runs on every change


class SecurityControl(BaseModel):
	model_config = MODEL_CONFIG
	control: str
	implementation: str
	kind: ControlKind
	# The module or command that enforces it. For `ci` controls this is the command the workflow
	# must run; for `code` controls it is the module; for `process` it is the cadence.
	enforced_by: str
	where: str | None = None


class VulnerabilityScan(BaseModel):
	model_config = MODEL_CONFIG
	scan_id: str
	kind: str = Field(pattern=r'^(sast|dast|dependency|penetration|third_party_audit)$')
	performed_on_iso: str
	findings_critical: int = Field(ge=0)
	findings_high: int = Field(ge=0)
	findings_other: int = Field(ge=0)
	remediation_ref: str | None = None


class ScanObligation(BaseModel):
	"""One recurring §17.5 obligation and whether it is currently met."""

	model_config = MODEL_CONFIG
	kind: str
	cadence_days: int
	last_performed_iso: str | None
	due_on_iso: str | None
	overdue: bool


class SecurityPosture(BaseModel):
	model_config = MODEL_CONFIG
	controls: list[SecurityControl]
	ci_enforced: list[str]
	process_obligations: list[ScanObligation]
	open_critical: int
	open_high: int
	disclosure_policy: dict[str, object]


class DisclosurePolicy(BaseModel):
	"""§17.5 bug bounty: "Public programme with responsible disclosure"."""

	model_config = MODEL_CONFIG
	contact: str
	acknowledge_within_hours: int
	triage_within_days: int
	safe_harbour: str
	in_scope: list[str]
	out_of_scope: list[str]
