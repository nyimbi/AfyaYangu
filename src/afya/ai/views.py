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
	"""One aggregated geography cell. `population` is the denominator the min-cell rule tests.

	The five Inputs §AI-001 names are the five fields above `encounter_density`. Two were missing
	until now — `geofence_entries` and `search_signals` — and the shape of that gap is worth naming:
	the tree *had* both quantities, in `integrations.feeds.build_geofence_feed` (distinct subjects
	entering a cell, already floored at 10) and in §AI-003's `facility_search` / `medicine_search`
	signals, and neither reached the model. A signal that exists in the product and is not an input
	to the prediction the product makes is an input the section asks for and nobody wired.

	Both are counts of *distinct people* in the cell and not events: the same rule
	`build_geofence_feed` states, for the same reason — ten visits by four people is a cell of four,
	and counting events clears the floor with a cell that describes those four.

	The defaults are 0 rather than required so a caller that has no geofence feed and no search
	signal sends a cell rather than omitting one: an absent input is a zero, and the `reason` on the
	hotspot says which inputs were zero so a reader can tell "no signal" from "no data".
	"""
	model_config = MODEL_CONFIG
	cell_id: str
	county: str
	population: int = Field(ge=0)
	fever_reports: int = Field(ge=0)
	cough_events: int = Field(ge=0)
	encounter_density: float = Field(ge=0)
	facility_reports: int = Field(ge=0)
	# §AI-001's second Input, "geofence entries": distinct subjects whose entry events landed in this
	# cell. Carried as a count, because the individual events are what `build_geofence_feed` exists
	# to refuse to emit.
	geofence_entries: int = Field(default=0, ge=0)
	# §AI-001's fifth Input, "search and content-engagement signals": facility-finder and
	# medicine-search queries that resolved to this cell, plus content engagement. One count rather
	# than three because the section names one signal, and splitting it would invent two thresholds
	# it does not state.
	search_signals: int = Field(default=0, ge=0)
	# Where the cell is, when the caller knows. Optional because a cell that arrived from a
	# sub-county rollup has no centroid, and required for clustering: adjacency is a spatial claim
	# and a cell with no position is not adjacent to anything. `None` means "cannot be linked",
	# which the cluster list reports rather than silently dropping.
	lat: float | None = Field(default=None, ge=-90, le=90)
	lon: float | None = Field(default=None, ge=-180, le=180)


class ClusterLink(BaseModel):
	"""One edge of a transmission cluster (§AI-001's second Output).

	An edge and not a group: a cluster is a connected set of cells, and a model that returned only
	the set would lose *which* cells touch, which is the part a response team acts on — you
	surround a cluster, and you surround it along the links.
	"""
	model_config = MODEL_CONFIG
	from_cell: str
	to_cell: str
	km: float = Field(ge=0)
	shared_signal: str


class TransmissionCluster(BaseModel):
	"""§AI-001's "transmission cluster identification".

	Distinct from a hotspot. A hotspot is one cell above its own baseline; a cluster is a set of
	adjacent cells whose *combined* signal is above baseline — two cells each at 1.2σ and touching
	are one event a response team should treat as one, and the map that lists them as two hotspots
	tells PHEOC to send two teams. The `links` are what makes it a cluster rather than a list.
	"""
	model_config = MODEL_CONFIG
	cluster_id: str
	counties: list[str]
	cell_ids: list[str]
	links: list[ClusterLink]
	combined_probability: float = Field(ge=0, le=1)
	reason: str


class ResourceRecommendation(BaseModel):
	"""§AI-001's "resource deployment recommendations".

	Advice to a human, which is why nothing here is actioned by this system and why `rationale`
	names the quantity it was derived from. `quantity` is `None` when the section's own arithmetic
	does not determine one — a modelled number presented as a decision is worse than an absent one.
	"""
	model_config = MODEL_CONFIG
	county: str
	resource: str = Field(pattern=r'^(rapid_response_team|ors_kits|test_kits|vaccine_doses|vector_control|risk_communication)$')
	quantity: int | None = Field(default=None, ge=0)
	unit: str
	rationale: str
	auto_actioned: bool = False

	def model_post_init(self, _context: object) -> None:
		assert not self.auto_actioned, (
			'§19.3 keeps a human in the loop: a resource recommendation is advice, and a row that '
			'actioned itself would be the system deploying teams'
		)


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
	# §AI-001's other two Outputs. Defaulted so the suppression-only path — every cell below the
	# floor, nothing may be published — does not have to invent an empty cluster list, and so the
	# map a caller already reads keeps its shape.
	clusters: list[TransmissionCluster] = Field(default_factory=list)
	recommendations: list[ResourceRecommendation] = Field(default_factory=list)


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


# --- AI-003's six signals, as the app's own events --------------------------------------------------

# The six bullets §11.7 lists, keyed to the signal names `WarningSignal.signal` accepts. The mapping
# lives here because it is a fact about the spec's wording and the app's surfaces, and both ends of
# it are in this module's import graph.
SIGNAL_SOURCES: dict[str, str] = {
	'fever_triage': 'a triage completed with fever among the reported symptoms',
	'cough_events': 'a cough detection event — the on-device classifier returning a positive',
	'facility_search': 'a facility-finder search that names a symptom',
	'medicine_search': 'a medicine lookup that names a drug',
	'unwell_checkin': 'an "I feel unwell" check-in',
	'encounter_density': 'a proximity encounter between two devices',
}
"""§11.7's six bullets and the app event each one is counted from.

`triage_volume` and `hotline_calls` are also accepted by `WarningSignal.signal` — they are §11.7's
neighbours in the surveillance module — but they are not among the six bullets this section lists,
so the collector does not produce them and says so rather than padding the set.
"""

SIGNAL_CARRYING_FIELDS: dict[str, tuple[str, str]] = {
	# signal -> (model, field): the request field the event is read from, where the route records one
	'fever_triage': ('TriageInput', 'symptoms'),
	'cough_events': ('CoughVerdict', 'cough_events'),
	'facility_search': ('NearestRequest', 'query'),
	'medicine_search': ('DoseRequest', 'drug'),
	'unwell_checkin': ('WHO5', 'scores'),
	'encounter_density': ('EncounterToken', 'pet'),
}
"""Where each signal is read from, named so a test can assert the field still exists.

A collector keyed on a field that was renamed stops collecting and keeps returning zero, which reads
as "no outbreak" — the one failure mode a detection layer may not have. Naming the model and field
here lets a test fail when the source moves rather than when someone notices the silence.
"""


class SignalEvent(BaseModel):
	"""One occurrence, as the route that owns the surface recorded it.

	This is the ingestion row and it is deliberately not the count. A count kept by incrementing an
	integer at each route loses the period it happened in, and a baseline is a distribution over
	periods — so the events are kept and the counting happens at read time, where the window is
	explicit. `event_ref` is the opaque identifier of whatever the route has (a triage id, a PET,
	a drug name); it is never read by the detector, and it is what makes a count auditable back to its
	events. It is not called `ref`, because a route that names a *person* uses `ref` for the subject
	(§17) and the gate that walks subject-carrying routes reads the name, not the intent.
	"""

	model_config = MODEL_CONFIG
	county: str
	at_iso: str
	signal: str = Field(pattern=r'^(fever_triage|cough_events|facility_search|medicine_search|unwell_checkin|encounter_density)$')
	event_ref: str = ''


class SignalObservation(BaseModel):
	"""One period's count of one signal in one locality — a row of the history a baseline is read from.

	`week_isoyear` and `week` are the period, because a baseline is a distribution over periods: a
	z-score against a mean whose window is unknown is a number that cannot be checked. The collector
	groups by these and nothing else.
	"""

	model_config = MODEL_CONFIG
	county: str
	week_isoyear: int = Field(ge=2024, le=2100)
	week: int = Field(ge=1, le=53)
	signal: str = Field(pattern=r'^(fever_triage|cough_events|facility_search|medicine_search|unwell_checkin|encounter_density)$')
	count: int = Field(ge=0)


class SignalCollection(BaseModel):
	"""What one collection pass produced, and what it refused to produce.

	`withheld` is the finding and not a warning: a signal whose source produced fewer than
	`MIN_CELL_SIZE` events in the period is not a small signal, it is a signal that cannot be told
	from noise without re-identifying the people in it. The name is reported so an epidemiologist can
	see the gap rather than the absence.
	"""

	model_config = MODEL_CONFIG
	county: str
	observations: list[SignalObservation]
	withheld: list[str]
	note: str


class EarlyWarningScan(BaseModel):
	"""§AI-003 end to end: the signals collected, the assessment they produced, and the refusal.

	`public_alert` is False on every path and there is no field that can set it. §11.7: signals above
	threshold "trigger a review by PHEOC epidemiologists. Never automatic public alerts." A model
	whose only way to express that is a boolean the caller passes in is a promise, not a control.
	"""

	model_config = MODEL_CONFIG
	county: str
	disease: str
	week_isoyear: int
	week: int
	collection: SignalCollection
	assessment: WarningAssessment
	message: str


# --- AI-004 governance ------------------------------------------------------------------

class ModelCard(BaseModel):
	"""One model, as §19.1 or §19.2 states it.

	`framework` is §19.1's fourth column and §19.2 has no equivalent — the server table is Model,
	Purpose, Inputs, Outputs — so the field is empty exactly where the spec is silent. `footprint()`
	refuses a *device* model that leaves it blank, because §19.1 states a framework for all seven of
	its rows: a blank one is a row nobody transcribed.
	"""

	model_config = MODEL_CONFIG
	model_id: str
	purpose: str
	owner: str
	inputs: list[str]
	outputs: list[str]
	on_device: bool
	size_mb: float = Field(ge=0)
	framework: str = ''
	limitations: list[str]
	review_board_required: bool


class ModelFootprint(BaseModel):
	"""§19.1's closing line — "Total on-device model footprint: ~30 MB (loaded as needed, not all at
	once)" — against the cards the module actually carries.

	`within_statement` is the finding. The five cards that existed summed to 8 MB against a stated 30,
	which is not a rounding difference: the two absent rows are the speech model and the cough
	classifier, 21 of the 29 MB, and both are load-bearing. The speech model is what §ACC-002's
	"offline speech recognition" needs and what makes a transcript on-device at all; the cough
	classifier is what §14.2's "cough type distribution" output comes from. A footprint report that
	read 8 MB would have described a client that carries neither.

	`missing_frameworks` is the second half: §19.1 names a framework for every one of its rows, so a
	device model without one is a row that was not transcribed from the section.
	"""

	model_config = MODEL_CONFIG
	models: int = Field(ge=0)
	stated_total_mb: float = Field(ge=0)
	summed_mb: float = Field(ge=0)
	within_statement: bool
	missing_frameworks: list[str]
	note: str


class FairnessAuditRequest(BaseModel):
	"""What a caller submits to start an audit: the model and the axes they tested.

	`passed` and `action` are not here. Both are `audit_fairness`'s own conclusion, and requiring
	them of a caller asked the person running the audit to hand in its verdict — a control that
	returns what it was given. They live on `FairnessAudit`, which is what the audit answers.
	"""

	model_config = MODEL_CONFIG
	model_id: str
	axes: list[str]
	unmet_axes: list[str] = Field(default_factory=list)


class FairnessAudit(BaseModel):
	"""The audit's result: the axes, the ones left unmet, and whether the model may ship."""

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
