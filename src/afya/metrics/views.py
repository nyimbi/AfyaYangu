"""Success-metric models (spec §22).

§22 is eight tables of targets — north star, reach, engagement, health outcome, technical, privacy
and trust, equity — plus an evaluation framework. The rule this module carries is the one §15.4's
capacity report already applies: a target with no measurement is *unmeasured*, not met. A success
report built from silence is the failure mode, and it is worse here than at §15.4 because these are
the numbers a funder reads.

`EquityCut` is the second rule. §22.7 and §22.8 require the equity metrics disaggregated by gender,
geography, age and device; a headline "50% female" with no cut behind it cannot be checked, and a
metric whose whole purpose is a disparity must not be reportable as a single aggregate.
"""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class MetricFamily(str, Enum):
	"""§22's subsections, one per table. The family is what a report groups by."""

	north_star = 'north_star'
	reach = 'reach'
	engagement = 'engagement'
	health_outcome = 'health_outcome'
	technical = 'technical'
	privacy_trust = 'privacy_trust'
	equity = 'equity'


class EquityAxis(str, Enum):
	"""§22.8: "Disaggregated analysis by gender, geography, age, device." The four cuts an equity
	metric must carry, named as data so a report can say which it is missing."""

	gender = 'gender'
	geography = 'geography'
	age = 'age'
	device = 'device'


class Kpi(BaseModel):
	"""One §22 target. `higher_is_better` is False where being under the target is the pass — a
	median care-seeking time, a battery drain, a complaint rate — because a report that got the
	direction backwards would pass a 40-hour care-seeking delay as comfortably under a 24-hour cap."""

	model_config = MODEL_CONFIG
	kpi_id: str
	name: str
	definition: str
	target: float
	unit: str
	family: MetricFamily
	higher_is_better: bool
	source: str  # the §22 subsection the row comes from
	modelled: bool = False  # §22.1 "Lives saved" is estimated by modelling, so it has no fixed target
	measurement: str | None = None  # §22.2–§22.4's Measurement cell, verbatim; those are the only
	# three of §22's seven tables that print the column, so the field is absent rather than invented
	# for the other four. It is the cell that says *where the number comes from* — "Station surveys",
	# "Comms log", "MON-009 data" — and without it a target is a figure with no route to it.
	also_printed_at: list[str] = Field(default_factory=list)  # §22 subsections that print this row a
	# second time. §22.1's "Retention / DAU/MAU ratio / 35%" and §22.3's "DAU/MAU / 35% / Derived" are
	# one KPI, so the register carries it once and a reader of §22.3 alone would find six rows where
	# the section prints seven.


class Measurement(BaseModel):
	"""One observed value, optionally cut by the equity axes it is broken down along.

	`source` is the record of *who observed it* on this particular reading, not §22's Measurement
	column: that column is a property of the KPI (`Kpi.measurement`) and is the same for every
	reading of it, so restating it per row would be a second copy that can drift. The default is a
	sentence rather than a `None` because a measurement with no attribution is one nobody can chase.
	"""

	model_config = MODEL_CONFIG
	kpi_id: str
	observed: float = Field(ge=0)
	as_at_iso: str
	cuts: dict[str, str] = Field(default_factory=dict)
	source: str = 'deployment telemetry'


class KpiResult(BaseModel):
	"""A target beside its measurement. `within_target` is None when nothing was measured."""

	model_config = MODEL_CONFIG
	kpi_id: str
	name: str
	family: MetricFamily
	target: float
	observed: float | None
	unit: str
	within_target: bool | None
	gap: float | None

	def met(self) -> bool:
		return self.within_target is True


class MetricReport(BaseModel):
	"""A §22 report. `all_measured_targets_met` ignores the unmeasured rather than counting them as
	passes, so a report that measured nothing is not a green one — it is an empty one, and
	`unmeasured` says so."""

	model_config = MODEL_CONFIG
	as_at_iso: str
	results: list[KpiResult]
	unmeasured: list[str]
	all_measured_targets_met: bool
	by_family: dict[str, int] = Field(default_factory=dict)


class EvaluationLevel(str, Enum):
	"""§22.8's five evaluation levels, in the order the table lists them.

	The order is the ladder: process asks whether the thing ran, outcome whether it changed
	behaviour, impact whether it mattered, and the last two are the checks that keep the first
	three honest. A report that reached impact without process evidence has skipped the rung that
	would have shown the mechanism.
	"""

	process = 'process'
	outcome = 'outcome'
	impact = 'impact'
	equity = 'equity'
	privacy = 'privacy'


class EvaluationMethod(BaseModel):
	"""One §22.8 row: the level, the method, and how often it is done.

	`cadence_days` is derived from the section's Frequency column rather than restated — monthly is
	30, quarterly 91, semi-annually 182, annually 365 — and the derivation is why the row can be
	late-checked at all. A cadence of "Quarterly" as a string is a duty nobody can be late for,
	which is the state §24's `Obligation` model already refuses for the same reason.

	`families` is which §22 metric families the level reads. That mapping is the part §22.8 leaves
	implicit: "Early detection rates" is not a family name, and an evaluation level with no metrics
	behind it is a review meeting with nothing to review.
	"""

	model_config = MODEL_CONFIG
	level: EvaluationLevel
	method: str = Field(min_length=1)
	frequency: str = Field(min_length=1)
	cadence_days: int = Field(gt=0)
	families: list[MetricFamily] = Field(min_length=1)

	def at_least_quarterly(self) -> bool:
		"""Whether this level is reviewed at least quarterly. Three of §22.8's five are — Process
		(monthly), Outcome and Equity (both quarterly) — and those are the ones a funder asks about
		between annual reports, which is why the predicate is the cadence rather than the label."""
		return self.cadence_days <= 91


class EvaluationFramework(BaseModel):
	"""§22.8 as one answer: the five levels, their cadences, and the two things a reader needs.

	`uncovered_families` is the finding. §22 has seven metric families and §22.8 names five
	evaluation levels; if a family is read by no level, the metrics under it are collected and
	never looked at, which is the same shape as a §7.3 feature outside the tier map. `levels_by_
	cadence` is the review calendar in order, because the frequency column is what turns a
	framework into a schedule.
	"""

	model_config = MODEL_CONFIG
	levels: list[EvaluationMethod]
	families: list[str]
	uncovered_families: list[str]
	levels_by_cadence: list[str]
	note: str


class EquityGap(BaseModel):
	"""An equity axis §22.7 names that no measurement covers, or a metric reported with no cut."""

	model_config = MODEL_CONFIG
	kpi_id: str
	axis: str
	reason: str


class EquityReport(BaseModel):
	"""§22.7 disaggregation, reported as coverage rather than asserted.

	`covered_axes` and `gaps` together answer the only question an equity report has to answer: for
	which of the four cuts do we actually have a number, and which are we claiming without one.
	"""

	model_config = MODEL_CONFIG
	axes: list[str]
	covered_axes: list[str]
	gaps: list[EquityGap]
	complete: bool
	note: str
