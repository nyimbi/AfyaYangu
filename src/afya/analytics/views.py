"""Public-health analytics models (spec §19.4).

§19.4 names nine dashboards for PHEOC, county health teams and MoH, and sets three rules for all
of them: the access is role-based, it is audit logged, and — from §19.3 and §11.7 — every number is
aggregated with a minimum cell size of 10 so no row can be read back to a person.

`MetricRow` is the shape all nine share, and it carries the two things that make the aggregation
rule checkable rather than asserted: the `population` it was drawn from, and a `suppressed` flag
for a cell the service refused to report. A row that is suppressed carries its counts as None, so a
consumer cannot render a number the rule withheld.
"""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from afya.ai.views import MIN_CELL_SIZE

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class DashboardId(str, Enum):
	"""§19.4's nine dashboards, as ids rather than prose headings."""

	symptom_surveillance = 'symptom_surveillance'
	triage_volume = 'triage_volume'
	case_pipeline = 'case_pipeline'
	contact_monitoring = 'contact_monitoring'
	encounter_density = 'encounter_density'
	content_engagement = 'content_engagement'
	misinformation_velocity = 'misinformation_velocity'
	facility_availability = 'facility_availability'
	alert_reach = 'alert_reach'


# The spec's own list, in its own order, with the granularity each is reported at. Kept beside the
# enum so a dashboard that is named but not built (or built but not named) fails the coverage test.
DASHBOARDS: tuple[tuple[DashboardId, str, str], ...] = (
	(DashboardId.symptom_surveillance, 'Real-time symptom surveillance by county', 'county'),
	(DashboardId.triage_volume, 'Triage volume and risk distribution', 'county'),
	(DashboardId.case_pipeline, 'Case report pipeline and status', 'county'),
	(DashboardId.contact_monitoring, 'Contact monitoring adherence', 'county'),
	(DashboardId.encounter_density, 'Proximity encounter density', 'county'),
	(DashboardId.content_engagement, 'Content engagement', 'item'),
	(DashboardId.misinformation_velocity, 'Misinformation velocity', 'topic'),
	(DashboardId.facility_availability, 'Facility and drug availability', 'facility'),
	(DashboardId.alert_reach, 'Alert reach and response', 'county'),
)


class MetricRow(BaseModel):
	"""One aggregated row. `suppressed` is the min-cell verdict, not a rendering hint.

	A suppressed row carries `value` and `denominator` as None because there is no number the rule
	permits reporting — leaving a small count in place and flagging it would put the count on the
	wire, which is the thing §11.7 forbids.
	"""

	model_config = MODEL_CONFIG
	key: str
	label: str
	value: float | None = None
	denominator: int | None = None
	suppressed: bool = False
	breakdown: dict[str, float] = Field(default_factory=dict)
	note: str | None = None


class Dashboard(BaseModel):
	"""One §19.4 dashboard: its rows, how many cells the min-cell rule withheld, and the caveat.

	`suppressed_cells` is reported rather than hidden. A dashboard that silently drops small cells
	reads as complete when it is not, and the reader has no way to tell coverage from emptiness.
	"""

	model_config = MODEL_CONFIG
	dashboard: DashboardId
	title: str
	granularity: str
	rows: list[MetricRow]
	suppressed_cells: int = Field(ge=0)
	min_cell_size: int = Field(ge=1)
	as_at_iso: str
	caveat: str


class AnalyticsAccess(BaseModel):
	"""The §19.4 access rule, reported so a reader can check it instead of assuming it."""

	model_config = MODEL_CONFIG
	dashboards: list[str]
	roles_allowed: list[str]
	audit_logged: bool
	individual_level_data: bool
