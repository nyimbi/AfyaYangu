"""Community models (spec §10.4 COM-005, §11.4 COM-101..104)."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from afya.registry.diseases import DISEASE_PATTERN

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


# --- COM-005 community reporting ---------------------------------------------------------

class IssueKind(str, Enum):
	broken_water_point = 'broken_water_point'
	open_sewage = 'open_sewage'
	illegal_dumping = 'illegal_dumping'
	mosquito_breeding = 'mosquito_breeding'
	dead_animal = 'dead_animal'
	unsafe_food_vendor = 'unsafe_food_vendor'
	counterfeit_medicine = 'counterfeit_medicine'
	facility_stockout = 'facility_stockout'
	facility_staff_absence = 'facility_staff_absence'


# county authority routing table — who actually fixes this (§10.4 "routed to relevant authority")
ISSUE_ROUTING: dict[IssueKind, str] = {
	IssueKind.broken_water_point: 'County Water Services',
	IssueKind.open_sewage: 'County Public Health Office',
	IssueKind.illegal_dumping: 'County Environment Office',
	IssueKind.mosquito_breeding: 'County Public Health Office',
	IssueKind.dead_animal: 'County Veterinary Services',
	IssueKind.unsafe_food_vendor: 'County Public Health Office',
	IssueKind.counterfeit_medicine: 'Pharmacy and Poisons Board',
	IssueKind.facility_stockout: 'County Health Management Team',
	IssueKind.facility_staff_absence: 'County Health Management Team',
}


class CommunityIssue(BaseModel):
	model_config = MODEL_CONFIG
	issue_id: str = Field(pattern=r'^CIS-[A-Z0-9]{8,}$')
	kind: IssueKind
	county: str
	description: str = Field(min_length=5, max_length=300)
	lat: float | None = Field(default=None, ge=-5, le=6)
	lon: float | None = Field(default=None, ge=33, le=43)


class IssueStatus(str, Enum):
	reported = 'reported'
	routed = 'routed'
	in_progress = 'in_progress'
	resolved = 'resolved'


class IssueReceipt(BaseModel):
	model_config = MODEL_CONFIG
	issue_id: str
	routed_to: str
	status: IssueStatus
	message: str


# --- COM-101 CHW case reporting ----------------------------------------------------------

class CaseStatus(str, Enum):
	reported = 'reported'
	investigated = 'investigated'
	lab_result = 'lab_result'
	closed = 'closed'


class CaseReport(BaseModel):
	"""WHO IDSR / Kenya MoH structured report. Patient name optional — anonymous is a first-class path."""
	model_config = MODEL_CONFIG
	report_id: str = Field(pattern=r'^CR-[A-Z0-9]{8,}$')
	chw_ref: str
	county: str
	community: str
	patient_ref: str | None = None
	age_years: int | None = Field(default=None, ge=0, le=120)
	sex: str | None = Field(default=None, pattern=r'^(male|female|other)$')
	symptoms: list[str] = Field(min_length=1)
	exposure_history: str | None = Field(default=None, max_length=500)
	temperature_c: float | None = Field(default=None, ge=30, le=45)
	geotagged: bool = False
	photo_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
	voice_note_lang: str | None = None
	suspected_disease: str = Field(default='evd', pattern=DISEASE_PATTERN)
	reported_offline: bool = False
	# §5.4's "deduplicated by phone number" needs the number the report came from, and the model had
	# no field for it — so a case filed over USSD and the same case filed in the app were two cases
	# and the count PHEOC reads was inflated by exactly the duplicates the section promises are gone.
	# Optional because a CHW logging offline carries no MSISDN: the phone is a channel's identity, and
	# a report that did not come over a channel has none. Absent means "cannot be deduplicated", which
	# `CommunityService.submit_case` reports rather than treats as "no duplicate".
	reporter_msisdn: str | None = Field(default=None, pattern=r'^\+[1-9]\d{6,14}$')


class CaseReportView(BaseModel):
	model_config = MODEL_CONFIG
	report_id: str
	status: CaseStatus
	surveillance_officer: str
	alerts_sent: int = Field(ge=0)
	next_step: str
	# True when §5.4's dedup recognised this report as one already open. The caller is told rather
	# than silently given the first report's id: a person who reports twice because the first
	# acknowledgement never arrived must not be left believing a second case was opened.
	deduplicated: bool = False


# --- COM-102 peer alert network ----------------------------------------------------------

class PeerAlert(BaseModel):
	model_config = MODEL_CONFIG
	alert_id: str
	county: str
	lat: float = Field(ge=-5, le=6)
	lon: float = Field(ge=33, le=43)
	radius_m: int = Field(ge=500, le=5000)
	headline: str = Field(max_length=120)
	body: str = Field(max_length=400)
	verified_by: str
	followup_days: list[int] = [3, 7, 14, 21]


class PeerAlertReceipt(BaseModel):
	model_config = MODEL_CONFIG
	alert_id: str
	recipients: int = Field(ge=0)
	verification: str
	tone_check: str


# --- COM-103 contact tracing assistance --------------------------------------------------

class ContactEntry(BaseModel):
	model_config = MODEL_CONFIG
	description: str = Field(min_length=2, max_length=200)
	contact_ref: str | None = None
	setting: str = Field(pattern=r'^(home|work|transport|worship|market|social|other)$')
	approx_location: str | None = None
	name_unknown: bool = False


class ContactList(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	entries: list[ContactEntry] = Field(default_factory=list)
	share_consent: bool = False


class ContactTracingSummary(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	by_setting: dict[str, int]
	total: int = Field(ge=0)
	shared: bool
	progress_pct: float = Field(ge=0, le=100)
	message: str


# --- COM-104 misinformation tracker ------------------------------------------------------

class MisinfoSubmission(BaseModel):
	model_config = MODEL_CONFIG
	submission_id: str = Field(pattern=r'^MIS-[A-Z0-9]{8,}$')
	claim: str = Field(min_length=5, max_length=500)
	county: str
	medium: str = Field(pattern=r'^(text|voice|screenshot|whatsapp_forward)$')
	topic: str | None = None
	flagger_ref: str | None = None


class MisinfoCluster(BaseModel):
	model_config = MODEL_CONFIG
	topic: str
	reports: int = Field(ge=1)
	velocity: str = Field(pattern=r'^(slow|rising|spiking)$')
	counties: list[str]
	correction: str | None = None
	status: str = Field(pattern=r'^(aggregating|verified|correction_published)$')
	# §6.4's clock, on the cluster rather than beside it. `reports` and `velocity` say how loud a
	# rumour is; neither says how long the response has been running, so a cluster could read
	# `spiking` for a week with nothing anywhere showing that the four-hour triage was never done.
	detected_at_ms: int | None = None
	next_due_at_ms: int | None = None
	response_overdue: bool = False


class ClaimAnswer(BaseModel):
	"""§INF-004's "Ask about a rumour", answered to the person who asked.

	`MisinfoCluster` is the wrong shape for this and the difference is the feature. A cluster is
	PHEOC's view of a rumour — how many reports, which counties, how fast it is moving — and it is
	what a *flagger* gets, because a flagger reports something they saw someone else spread. Someone
	who asks "is it true that salt water cures Ebola" is not flagging anything: they want the
	correction, and handing them a surveillance row instead answers a question they did not ask.

	So the correction travels with the claim it corrects and the authority behind it, which is
	§INF-004's Format — "Rumour: [claim]. Fact: [correction]. Source: [authority]." — as fields rather
	than as one rendered string. `recognised` is what makes the fallback honest: a claim matching no
	drafted rumour is answered "under verification" and says so, rather than being attached to the
	nearest correction with the confidence of a match.
	"""
	model_config = MODEL_CONFIG
	claim: str = Field(min_length=5)
	# None when no drafted rumour matched. The topic, not the category: a category is a pre-drafting
	# grouping for §6.4's brief and several topics answer one, so naming the category here would lose
	# which rumour was actually recognised.
	topic: str | None = None
	# The words that decided the match, so a reader can argue with the classification rather than
	# being told an answer with no evidence behind it.
	matched: list[str] = []
	correction: str = Field(min_length=1)
	fact: str = Field(min_length=1)
	source: str = ''
	# The library item this correction is, so a client can open the full myth card rather than
	# rendering the correction as a dead end. Empty when nothing matched — there is no card for a
	# claim the library has not drafted.
	slug: str = ''
	# The language the answer is actually in, which is not always the one asked for: `answerable()`
	# resolves a language with no table to English rather than refusing, and a person told which
	# language they got is not left reading English believing it is Dholuo.
	answered_in: str = Field(pattern=r'^(en|sw)$')
	recognised: bool
	# §6.2.3: an undated correction about a live rumour is one nobody can weigh.
	drafted_on_iso: str = Field(min_length=10)
