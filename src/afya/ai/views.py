"""AI & analytics models (spec §19, §11.7 AI-001..003, §19.3 AI-004/005).

§19.3 sets the rules these models obey: every output carries a plain-language reason,
aggregation has a minimum cell size, clinical decisions keep a human in the loop, and a
user can challenge an outcome.
"""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# §11.7 / §19.3 / §SEC-004: "Minimum cell size of 10 to prevent re-identification." Defined here
# because this module is the lowest layer that needs it — `afya.analytics.views` and
# `afya.integrations.feeds` both import from it, so this is the single copy.
MIN_CELL_SIZE = 10


# --- AI-001 community-level risk prediction ----------------------------------------------

class AggregateCell(BaseModel):
	"""One aggregated geography cell. `population` is the denominator the min-cell rule tests."""
	model_config = MODEL_CONFIG
	cell_id: str
	county: str
	population: int = Field(ge=0)
	fever_reports: int = Field(ge=0)
	cough_events: int = Field(ge=0)
	encounter_density: float = Field(ge=0)
	facility_reports: int = Field(ge=0)


class Hotspot(BaseModel):
	model_config = MODEL_CONFIG
	cell_id: str
	county: str
	probability: float = Field(ge=0, le=1)
	reason: str
	recommended_action: str


class HotspotMap(BaseModel):
	model_config = MODEL_CONFIG
	hotspots: list[Hotspot]
	suppressed_cells: int = Field(ge=0)
	consumers: list[str]
	explanation: str


# --- AI-002 personal risk scoring --------------------------------------------------------

class RiskInputs(BaseModel):
	model_config = MODEL_CONFIG
	symptoms: list[str] = Field(default_factory=list)
	exposure_contact: bool = False
	travel_affected_area: bool = False
	geofence_entry: bool = False
	proximity_encounters: int = Field(default=0, ge=0, le=100)
	vaccinated: bool = False


class RiskScore(BaseModel):
	model_config = MODEL_CONFIG
	band: str = Field(pattern=r'^(low|moderate|high)$')
	score: float = Field(ge=0, le=1)
	reasons: list[str]
	guidance: str
	computed_on_device: bool


# --- AI-003 outbreak early warning -------------------------------------------------------

class WarningSignal(BaseModel):
	"""A raw signal as observed. The z-score is deliberately NOT an input field: a caller that can
	set its own z-score can raise or suppress an outbreak alert at will. It is derived from the
	counts by AIService.assess_warning, and returned on RaisedSignal."""
	model_config = MODEL_CONFIG
	county: str
	disease: str
	signal: str = Field(pattern=r'^(fever_triage|triage_volume|cough_events|facility_search|medicine_search|unwell_checkin|encounter_density|hotline_calls)$')
	observed: float = Field(ge=0)
	baseline: float = Field(ge=0)
	baseline_stdev: float = Field(gt=0, description='week-to-week standard deviation of the baseline')


class RaisedSignal(WarningSignal):
	"""A signal that cleared the threshold, carrying the z-score the service computed for it."""
	z_score: float


class WarningAssessment(BaseModel):
	model_config = MODEL_CONFIG
	county: str
	raised: list[RaisedSignal]
	review_required: bool
	routed_to: str
	public_alert: bool
	message: str


# --- AI-004 governance ------------------------------------------------------------------

class ModelCard(BaseModel):
	model_config = MODEL_CONFIG
	model_id: str
	purpose: str
	owner: str
	inputs: list[str]
	outputs: list[str]
	on_device: bool
	size_mb: float = Field(ge=0)
	limitations: list[str]
	review_board_required: bool


class FairnessAudit(BaseModel):
	model_config = MODEL_CONFIG
	model_id: str
	axes: list[str]
	unmet_axes: list[str]
	passed: bool
	action: str


# --- AI-005 explainability and redress ---------------------------------------------------

class RedressRequest(BaseModel):
	model_config = MODEL_CONFIG
	request_id: str = Field(pattern=r'^RDR-[A-Z0-9]{8,}$')
	subject_ref: str
	output_kind: str = Field(pattern=r'^(triage|risk_score|hotspot|exposure|tier4_activation)$')
	output_ref: str
	challenge: str = Field(min_length=5, max_length=500)


class RedressOutcome(BaseModel):
	model_config = MODEL_CONFIG
	request_id: str
	status: str = Field(pattern=r'^(received|under_review|upheld|overturned)$')
	reviewer: str
	human_reviewed: bool
	explanation: str
	remedy: str
