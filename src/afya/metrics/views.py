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


class Measurement(BaseModel):
	"""One observed value, optionally cut by the equity axes it is broken down along."""

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
