"""CHW / human-intermediary models (spec §5 CHAN-005, §11.4 COM-101).

The CHW module is the trust layer: AVADAR's lesson is that the tool works only when it is
simple and the alerting is automatic. These models keep the form short and the escalation
out of the CHW's hands.
"""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# §5.3 COM-101 job aids — reference material a CHW can open offline.
JOB_AIDS: dict[str, str] = {
	'idsr_case_definition': 'IDSR case definition: sudden onset of fever with bleeding, or fever with three or more of headache, vomiting, diarrhoea, muscle pain, sore throat, rash, plus an epidemiological link.',
	'ppe_donning': 'PPE: wash hands, gown, mask, goggles, gloves — in that order. Check every seal before entering.',
	'ppe_doffing': 'Doffing: gloves, gown, goggles, mask — then wash hands immediately. Never touch the front of the mask.',
	'isolation_basics': 'Isolate the patient in a single room with its own latrine where possible. One trained caregiver only. No visitors.',
	'safe_burial': 'Call the burial team. Do not wash, touch or kiss the body. The team conducts a safe and dignified burial.',
	'reporting_flow': 'Report on the app. The surveillance officer is alerted automatically. Track the case until it is closed.',
}

TRAINING_MODULES: tuple[dict[str, object], ...] = (
	{'module': 'orientation', 'minutes': 120, 'required': True},
	{'module': 'case_report_form', 'minutes': 20, 'required': True},
	{'module': 'ppe_refresher', 'minutes': 15, 'required': False},
	{'module': 'supervised_first_three_reports', 'minutes': 0, 'required': True},
)


class ChwProfile(BaseModel):
	model_config = MODEL_CONFIG
	chw_ref: str
	name: str
	county: str
	community: str
	registry_verified: bool
	provisioned_by: str
	trained_iso: str | None = None


class ChwCase(BaseModel):
	"""The CHW-facing case record. Mirrors COM-101's report without exposing the pipeline internals."""
	model_config = MODEL_CONFIG
	report_id: str
	status: str = Field(pattern=r'^(reported|investigated|lab_result|closed)$')
	suspected_disease: str
	reported_iso: str
	surveillance_officer: str
	ppe_reminder_due: bool
	next_action: str


class ActivityLogEntry(BaseModel):
	model_config = MODEL_CONFIG
	chw_ref: str
	at_iso: str
	activity: str = Field(pattern=r'^(report|followup|sensitisation|referral|training|supervision)$')
	community: str
	notes: str | None = Field(default=None, max_length=300)


class ActivitySummary(BaseModel):
	model_config = MODEL_CONFIG
	chw_ref: str
	period: str
	by_activity: dict[str, int]
	total: int = Field(ge=0)
	supervision_note: str
