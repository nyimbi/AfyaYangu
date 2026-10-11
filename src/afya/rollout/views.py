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
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from afya.registry.taxonomy import id_pattern

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


class Deliverable(BaseModel):
	"""One §21.2–21.7 deliverable: what the phase ships, and — where the phase's own words name one
	— the registry feature that carries it.

	`feature_id` is None for a deliverable that is an operational act rather than a capability:
	"Zero-rated app data" is a telco agreement, "Facility data loaded for all 47 counties" is a data
	load. Those are not unmodelled features, they are not features at all, and marking them as
	unbuilt would be the register crying wolf.

	The mapping is the point of the model. A phase that lists a deliverable naming a feature the
	registry does not carry is a plan for a capability nobody built, and §21 is the section a
	programme manager schedules against — which is why the tier ceiling alone was never enough.
	"""

	model_config = MODEL_CONFIG
	text: str = Field(min_length=1)
	# §7.2's prefix table, not a second copy of it — a hand-written prefix class is what fell
	# one prefix behind before (see `registry.taxonomy.id_pattern`).
	feature_id: str | None = Field(default=None, pattern=id_pattern())


class SuccessCriterion(BaseModel):
	"""One §21 success criterion: a number the phase is judged by, and the §22 KPI it restates.

	§21.3 says "300,000 installs" and §22.2 sets `app_downloads` at 2,000,000; §21.4 says "25%
	DAU/MAU" and §22.1 sets `retention_dau_mau` at 35%. The two sections disagree in both
	directions, and a criterion with no KPI behind it is a phase exit nobody can compute. So the
	KPI is resolved where one exists, the value is carried verbatim, and the disagreement is
	reported rather than averaged away — the spec is the product owner's and picking a winner here
	would be this code overruling it.

	`value` is a float and `operator` says which direction passes, because "40% D30 retention" and
	"<5% daily battery impact" are both criteria and only one of them is a floor.
	"""

	model_config = MODEL_CONFIG
	text: str = Field(min_length=1)
	value: float = Field(ge=0)
	unit: str = Field(min_length=1)
	operator: Literal['at_least', 'at_most'] = 'at_least'
	kpi_id: str | None = None

	def agrees_with(self, kpi_target: float) -> bool:
		"""Whether this criterion states the same number as the §22 KPI it names.

		Equality rather than a tolerance: the two sections state round figures, so a 10% gap is a
		different commitment and not a rounding artefact — §21.4's 25% against §22.1's 35% is the
		one that matters, because it is the retention engine's own exit criterion.
		"""
		return self.kpi_id is not None and abs(self.value - kpi_target) < 1e-9


class PhasePlan(BaseModel):
	"""One §21.2–21.7 section: the phase's objective, its deliverables, its success criteria and
	— for §21.6 only — the testing the section requires before the phase exits.

	This is what §21.1's table cannot carry. The table gives a ceiling and a channel set; the
	sections give the work. A rollout planned from the table alone schedules seven gates and
	describes none of them.
	"""

	model_config = MODEL_CONFIG
	phase: Phase
	objective: str = Field(min_length=1)
	deliverables: list[Deliverable] = Field(min_length=1)
	criteria: list[SuccessCriterion]
	testing: list[str] = Field(default_factory=list)
	rationale: str | None = None


class PhaseReadiness(BaseModel):
	"""One phase's plan crossed against what exists, as the answer a programme manager reads.

	Three findings, and they are different problems: `unbuilt_deliverables` is a plan naming a
	capability the registry does not carry; `unregistered_features` is the same failure caught at
	the id level; `criterion_drift` is §21 and §22 stating different numbers for the same measure.
	`unmeasurable_criteria` is the fourth — a criterion with no KPI behind it, which is a phase exit
	that cannot be computed at all.
	"""

	model_config = MODEL_CONFIG
	phase: Phase
	objective: str
	deliverable_count: int
	feature_deliverables: int
	unbuilt_deliverables: list[str]
	unregistered_features: list[str]
	criteria: list[SuccessCriterion]
	criterion_drift: list[str]
	unmeasurable_criteria: list[str]
	testing: list[str]
	ready: bool
	note: str


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


class ModuleDelivery(BaseModel):
	"""One §16.5 row: a component, its size, and how it reaches the device.

	§16.5 is the table §19.1's "loaded as needed, not all at once" points at, and the two sections
	disagree unless the delivery column is carried: a 20 MB speech model is only compatible with a
	15 MB base install because the section makes it on-demand. `automatic` marks the one row that
	arrives without the person asking (the per-county facility cache), because it is the only row
	whose size is spent on every install whether or not anyone wants it.
	"""

	model_config = MODEL_CONFIG
	component: str = Field(min_length=1)
	size_mb: float = Field(ge=0)
	delivery: str = Field(pattern=r'^(initial|on_demand|automatic)$')
	condition: str | None = None

	@property
	def at_install(self) -> bool:
		return self.delivery in ('initial', 'automatic')


class AppSizePlan(BaseModel):
	"""§16.5 as one answer: what ships at install, what a person may pull later, and whether the base
	install stays under the budget two other sections state.

	`base_install_mb` sums the initial rows and `within_budget` compares it against §20.2 lever 5's
	15 MB — the same number §16.5's own "Base install under 15 MB" line gives, which is why the plan
	reads the budget from the KPI table rather than restating it. The on-demand total is reported
	separately rather than added: a plan whose full module set exceeds the budget is not a plan whose
	*install* does, and §16.5's own ~60 MB total is the section saying so.
	"""

	model_config = MODEL_CONFIG
	components: list[ModuleDelivery]
	base_install_mb: float = Field(ge=0)
	on_demand_mb: float = Field(ge=0)
	full_install_mb: float = Field(ge=0)
	budget_mb: float = Field(gt=0)
	within_budget: bool
	note: str


class AcquisitionChannel(BaseModel):
	"""One §20.3 row: a channel, the job it does in acquisition, and the tactics that do it.

	`channel` is §5.2's slug and `label` is §20.3's own word for it, and both are kept because the
	two are not the same set. §20.3 says "App stores" where §5.2's channel is `native`: the app store
	is how the app is *found*, the app is what is found, and collapsing the label into the slug
	without saying so would read as the section having named a channel the registry does not carry.

	`tactics` is the section's Tactics cell split on its semicolons, so "Daily segments, call-ins,
	drama vignettes" is three tactics rather than one string — a plan whose tactics are a paragraph
	is a plan nobody can assign.
	"""

	model_config = MODEL_CONFIG
	channel: str = Field(min_length=1)
	label: str = Field(min_length=1)
	role: str = Field(min_length=1)
	tactics: list[str] = Field(min_length=1)
	# The registry feature that carries the channel, where §7.2 gives one. §20.3 is a plan to
	# acquire through a channel; a channel with no capability behind it is a media buy.
	feature_id: str | None = Field(default=None, pattern=id_pattern())


class PartnerType(BaseModel):
	"""One §20.4 row: a category of partner, the partners the section names in it, and what they
	bring.

	`partners` is the Specific partners cell split on its commas — "Kenya Red Cross, AMREF Health
	Africa, Living Goods, Medic, Dimagi" is five organisations, and a count that said one would let
	a map of four names pass as a map of ten rows.
	"""

	model_config = MODEL_CONFIG
	partner_type: str = Field(min_length=1)
	partners: list[str] = Field(min_length=1)
	role: str = Field(min_length=1)


class AcquisitionPlan(BaseModel):
	"""§20.3 and §20.4 as one answer, crossed against §5.2's channels and §20.2's levers.

	Two findings, and they are the two ways an acquisition plan is a document rather than a plan.

	`unmapped_channels` is a §5.2 channel §20.3 gives no acquisition role for — a channel the product
	can reach someone through and no plan to reach them. `unsourced_levers` is the reverse and the
	sharper one: §20.2's levers name specific organisations ("Negotiate with Safaricom, Airtel,
	Telkom before launch", "Co-brand with Kenya Red Cross, AMREF, WHO, faith networks") and §20.4 is
	the section that says who is actually a partner. A lever whose action rests on a partner the
	partnership map does not list is a growth strategy waiting on an agreement nobody signed.
	"""

	model_config = MODEL_CONFIG
	channels: list[AcquisitionChannel]
	partner_types: list[PartnerType]
	partner_count: int
	unmapped_channels: list[str]
	lever_partners: dict[str, list[str]]
	unsourced_levers: list[str]
	note: str
