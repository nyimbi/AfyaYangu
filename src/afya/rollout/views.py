"""Rollout phases, growth levers and the retention engine (spec §20, §21).

§20 and §21 are the two sections a programme manager reads: six phases, six growth levers, nine
retention mechanisms and a launch sequence. They read as marketing, and two of their claims are
about *this repo* — §20.2 lever 3 says "open-source client" and §20.2 lever 5 says "Under 15 MB".
Neither was checkable, and a claim about the artefact that nobody can check is a claim that stays
true by nobody looking.

The phases are also a real gate. §21.1 assigns each phase a tier ceiling, and §11.1 gives Tier 4 a
three-key gate; a phase that says "Tier 1–2" while the deployment has Tier 4 active is a rollout
that skipped three phases, which is the thing a phased rollout exists to prevent.
"""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Self

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class Phase(str, Enum):
	"""§21.1's seven phases, in order. Phase 0 is the build itself and carries no tier."""

	phase_0_foundation = 'phase_0_foundation'
	phase_1_information = 'phase_1_information'
	phase_2_utility = 'phase_2_utility'
	phase_3_retention = 'phase_3_retention'
	phase_4_daily_habit = 'phase_4_daily_habit'
	phase_5_outbreak_ready = 'phase_5_outbreak_ready'
	phase_6_scale = 'phase_6_scale'

	@property
	def order(self) -> int:
		return list(Phase).index(self)


class PhaseSpec(BaseModel):
	"""One §21.1 row. `max_tier` is the ceiling the phase authorises and `channels` the CHAN ids it
	opens; both are None/empty for Phase 0, which delivers nothing to a user."""

	model_config = MODEL_CONFIG
	phase: Phase
	timeline: str = Field(min_length=1)
	objective: str = Field(min_length=1)
	channels: list[str]
	max_tier: int | None = Field(default=None, ge=1, le=4)
	weeks_start: int
	weeks_end: int | None

	@model_validator(mode='after')
	def _a_phase_with_a_tier_has_channels(self) -> Self:
		"""A phase that opens a tier without naming a channel is one that promises capability with
		no way to reach a person — §21.1's Channels column is empty only for Phase 0."""
		if self.max_tier is not None and not self.channels:
			raise ValueError(f'{self.phase.value} authorises tier {self.max_tier} over no channel')
		return self

	def span(self) -> str:
		return self.timeline


class GrowthLever(BaseModel):
	"""One §20.2 row. `checkable` is True only where the lever makes a claim about this repo, and
	then `check` names the property the code must hold. The other four are partnership or design
	commitments with no artefact to inspect, and they say so rather than being given a fake check."""

	model_config = MODEL_CONFIG
	number: int = Field(ge=1, le=6)
	lever: str = Field(min_length=1)
	why: str = Field(min_length=1)
	action: str = Field(min_length=1)
	checkable: bool
	check: str | None = None

	@model_validator(mode='after')
	def _a_checkable_lever_names_its_check(self) -> Self:
		if self.checkable and not self.check:
			raise ValueError(f'lever {self.number} is checkable but names no check')
		return self


class AntiPattern(BaseModel):
	"""§20.2's "What does not work" list. Named so the design can be checked against it: a login
	wall, a 60 MB app, a name with "Ebola" in it and unrequested push are each a property someone
	could ship by accident, and the list is what makes them refusable."""

	model_config = MODEL_CONFIG
	antipattern: str = Field(min_length=1)
	why: str = Field(min_length=1)
	checkable: bool = False
	check: str | None = None


class RetentionMechanism(BaseModel):
	"""One §20.6 row: the mechanism, the feature that carries it, and how often it brings a person
	back. `cadence_days` is None for the "as needed" rows, which is the honest answer — a facility
	finder does not schedule a return visit."""

	model_config = MODEL_CONFIG
	mechanism: str = Field(min_length=1)
	feature_id: str = Field(pattern=r'^[A-Z]{3,4}-\d{3}$')
	frequency: str = Field(min_length=1)
	cadence_days: int | None = None
	registered: bool = False

	def returns_regularly(self) -> bool:
		return self.cadence_days is not None


class LaunchStep(BaseModel):
	model_config = MODEL_CONFIG
	sequence: str
	step: str = Field(min_length=1)


class RolloutStatus(BaseModel):
	"""Where a deployment sits in §21's plan, and whether that is consistent with what is active.

	`phase_mismatch` is the finding: a tier active above the current phase's ceiling means the
	rollout skipped its own gate, and the report names both the phase and the tier rather than
	returning a boolean.
	"""

	model_config = MODEL_CONFIG
	phase: Phase
	objective: str
	max_tier: int | None
	active_tier: int
	phase_mismatch: bool
	channels_open: list[str]
	note: str


class ReadinessReport(BaseModel):
	"""§20.2's two repo claims plus §20.6's registry coverage, as one answer.

	`unregistered_retention_features` is the §20.6 table crossed against the registry: the section
	names nine features as the reason a person comes back, and a retention engine built on a
	feature that is not registered is a plan, not a product.
	"""

	model_config = MODEL_CONFIG
	open_source: bool
	license: str | None
	apk_base_size_mb: float | None
	apk_within_budget: bool | None
	retention_mechanisms: list[RetentionMechanism]
	unregistered_retention_features: list[str]
	antipatterns: list[AntiPattern]
	note: str
