"""Community models (spec §10.4 COM-005, §11.4 COM-101..104)."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

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
	suspected_disease: str = Field(default='evd', pattern=r'^(evd|cholera|malaria|dengue|mpox|rvf|measles|other)$')
	reported_offline: bool = False


class CaseReportView(BaseModel):
	model_config = MODEL_CONFIG
	report_id: str
	status: CaseStatus
	surveillance_officer: str
	alerts_sent: int = Field(ge=0)
	next_step: str


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
