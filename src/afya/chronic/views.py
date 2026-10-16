"""Chronic disease: BP/glucose logging, refill tracking (hypertension & diabetes, Kenya NCD burden)."""
from enum import Enum

from afya.ids import ref8
from afya.sensors.views import MeasurementSource
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class BPReading(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	systolic: int = Field(ge=60, le=260)
	diastolic: int = Field(ge=30, le=160)
	pulse: int = Field(default=70, ge=30, le=220)
	# §14.9: a paired cuff reports this, or a person typed it. The two are not the same reading and
	# triage on them should not be the same decision.
	source: MeasurementSource = MeasurementSource.manual
	clinical_grade: bool = False

	@property
	def stage(self) -> str:
		if self.systolic >= 140 or self.diastolic >= 90:
			return 'high'
		if self.systolic >= 130 or self.diastolic >= 85:
			return 'elevated'
		return 'normal'


class GlucoseReading(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	mmol_l: float = Field(gt=0, le=40)
	fasting: bool = True
	source: MeasurementSource = MeasurementSource.manual
	clinical_grade: bool = False

	@property
	def level(self) -> str:
		if self.fasting:
			return 'high' if self.mmol_l >= 7.0 else ('impaired' if self.mmol_l >= 6.1 else 'normal')
		return 'high' if self.mmol_l >= 11.1 else ('impaired' if self.mmol_l >= 7.8 else 'normal')


class RefillTracker(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	drug: str
	days_remaining: int = Field(ge=0, le=180)
	facility_id: str | None = None


# --- §MON-003's conditions with no reading behind them ------------------------------------------

class KidneyFunction(BaseModel):
	"""A kidney reading: creatinine with the age and sex the CKD-EPI equation needs.

	The equation is not a function of creatinine alone, so the model carries the three inputs
	together rather than taking them from a profile at the call site — a formula that silently reads
	the wrong age produces a plausible eGFR, which is the worst kind of wrong.

	`prior_egfr_iso` and `prior_egfr` are the second reading KDIGO requires. Without them the staging
	reports a stage and says it is not yet a diagnosis, which is the honest answer to one creatinine.
	"""

	model_config = MODEL_CONFIG
	subject_ref: str
	creatinine_mg_dl: float = Field(gt=0.1, le=30)
	age_years: int = Field(ge=18, le=120)
	sex: str = Field(pattern=r'^(male|female)$')
	acr_mg_g: float | None = Field(default=None, ge=0, le=10000)
	prior_egfr: float | None = Field(default=None, gt=0, le=250)
	prior_egfr_iso: str | None = None


class SeizureEvent(BaseModel):
	"""A seizure, timed. The duration is the whole clinical content of the escalation.

	`cluster` is a second seizure before recovery from the first, which ILAE treats as continuous
	rather than as two events, so it escalates at any duration.
	"""

	model_config = MODEL_CONFIG
	subject_ref: str
	duration_seconds: int = Field(ge=0, le=7200)
	cluster: bool = False
	pregnant: bool = False
	at_iso: str


class SickleCrisis(BaseModel):
	"""A painful vaso-occlusive crisis, with the signs that make it more than one.

	`signs` is a closed vocabulary rather than free text: the escalation keys on the sign, and a
	string a person types is a sign nothing matches.
	"""

	model_config = MODEL_CONFIG
	subject_ref: str
	pain_score: int = Field(ge=0, le=10)
	temperature_c: float = Field(ge=30, le=45)
	signs: list[str] = Field(default_factory=list)
	at_iso: str


class ConditionReading(BaseModel):
	"""One condition's assessment: the verdict, the measure behind it, and what to do.

	The measure travels with the verdict for the same reason the growth z-scores do — "stage G4" and
	"eGFR 22" are the same fact and only the number tells a clinician how urgent it is.
	"""

	model_config = MODEL_CONFIG
	condition: str = Field(pattern=r'^(epilepsy|sickle_cell|chronic_kidney)$')
	escalate: bool
	summary: str
	measure: dict[str, object] = {}
	danger_signs: list[str] = []


class TrendPoint(BaseModel):
	"""One point on §MON-003's "Trend charts"."""

	model_config = MODEL_CONFIG
	at_iso: str
	value: float
	label: str


class TrendChart(BaseModel):
	"""§MON-003's "Trend charts": the series, its direction, and the threshold lines it crosses.

	`thresholds` travels because a chart without them is a shape: a rising blood pressure is
	reassuring or alarming depending on where the line sits, and the reader of the chart is the
	person, not a clinician who knows the numbers.
	"""

	model_config = MODEL_CONFIG
	subject_ref: str
	metric: str = Field(pattern=r'^(bp_systolic|bp_diastolic|glucose|peak_flow|weight)$')
	points: list[TrendPoint]
	direction: str = Field(pattern=r'^(rising|falling|stable|insufficient)$')
	change: float
	unit: str
	thresholds: list[dict[str, object]] = []
	note: str


class AppointmentKind(str, Enum):
	"""What a scheduled appointment is for.

	Was a bare `str` with a pattern, which is a vocabulary with no name: the mobile form offered
	`clinic`/`home`/`telehealth` — a *mode* of visit, a different question — against a route accepting
	`review`/`test`/`refill`/`vaccination`. Every option the form drew was refused, so the action could
	not be submitted at all, and the name-only reachability gate could not see it because the field
	name matched. Naming the enum is what lets a form be a view of it.
	"""

	review = 'review'
	test = 'test'
	refill = 'refill'
	vaccination = 'vaccination'


class ChronicAppointment(BaseModel):
	"""§MON-003's "Appointment tracking": a scheduled review, and what it is for."""

	model_config = MODEL_CONFIG
	# Server-minted for the same reason `WalletMember.member_ref` now is: the catalogue carries it
	# as `_auto` and no form draws it, so a required field with no default was a submission the
	# person could not complete. `AppointmentStatus` below keeps it required — that is a read, and a
	# read of an appointment that names none is meaningless.
	appointment_id: str = Field(default_factory=lambda: 'APPT-' + ref8())
	subject_ref: str
	condition: str
	due_iso: str
	interval_days: int = Field(ge=1, le=730)
	kind: AppointmentKind
	facility_id: str | None = None


class AppointmentStatus(BaseModel):
	model_config = MODEL_CONFIG
	appointment_id: str
	subject_ref: str
	condition: str
	due_iso: str
	kind: str
	days_until: int
	overdue: bool
	remind: bool
	message: str


class LifestyleGuidance(BaseModel):
	"""§MON-003's "Lifestyle guidance", keyed on the condition rather than on the age.

	The existing guidance is `nutrition_guidance`, which bands by the child's age — right for a
	well-child visit and wrong here, because what a person with hypertension eats and what a person
	with sickle cell disease must avoid are different lists at the same age.
	"""

	model_config = MODEL_CONFIG
	condition: str
	subject_ref: str | None = None
	guidance: list[str]
	avoid: list[str]
	note: str