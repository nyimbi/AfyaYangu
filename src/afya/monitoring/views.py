"""Monitoring & reminder models (spec §9.1 MON-001..004, §10.2 MON-005..008, §11.3 MON-009)."""
from enum import Enum

from afya.sensors.views import MeasurementSource
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


# --- MON-001: child immunisation tracker -------------------------------------------------

# Kenya EPI schedule: vaccine -> (dose_no, due_age_weeks). Ages are upper bounds; a dose is
# "due" once the child reaches the age and overdue after the catch-up grace window.
EPI_DUE_WEEKS: dict[str, list[tuple[int, int]]] = {
	'BCG': [(1, 0)],
	'OPV': [(0, 0), (1, 6), (2, 10), (3, 14)],
	'PCV10': [(1, 6), (2, 10), (3, 14)],
	'DPT-HepB-Hib': [(1, 6), (2, 10), (3, 14)],
	'RV': [(1, 6), (2, 10)],
	'IPV': [(1, 14)],
	'Measles-Rubella': [(1, 39), (2, 78)],
	'Yellow Fever': [(1, 39)],
	'HPV': [(1, 520), (2, 546)],
}

CATCH_UP_GRACE_WEEKS = 4
REMINDER_LEAD_DAYS = (3, 1)


class ImmunisationDue(BaseModel):
	model_config = MODEL_CONFIG
	member_ref: str
	vaccine: str
	dose_no: int = Field(ge=0)
	due_age_weeks: int = Field(ge=0)
	status: str = Field(pattern=r'^(due|overdue|upcoming|given)$')
	remind_days_before: list[int] = []


class ImmunisationCatchUp(BaseModel):
	model_config = MODEL_CONFIG
	member_ref: str
	defaulted: list[str]
	advise: str


# --- MON-004: medication reminders -------------------------------------------------------

class MedSchedule(BaseModel):
	model_config = MODEL_CONFIG
	schedule_id: str = Field(pattern=r'^MED-[A-Z0-9]{6,}$')
	member_ref: str
	drug: str
	dose: str
	times_per_day: int = Field(ge=1, le=6)
	start_iso: str
	duration_days: int = Field(ge=1, le=365)
	refill_at_days_left: int = Field(default=7, ge=1, le=60)


class AdherenceAction(str, Enum):
	taken = 'taken'
	skipped = 'skipped'
	snoozed = 'snoozed'


class AdherenceEvent(BaseModel):
	model_config = MODEL_CONFIG
	schedule_id: str
	at_iso: str
	action: AdherenceAction


class AdherenceReport(BaseModel):
	model_config = MODEL_CONFIG
	schedule_id: str
	expected_doses: int = Field(ge=0)
	taken: int = Field(ge=0)
	skipped: int = Field(ge=0)
	snoozed: int = Field(ge=0)
	adherence_pct: float = Field(ge=0, le=100)
	refill_due: bool


# --- MON-003: chronic disease log ---------------------------------------------------------

class PeakFlowReading(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	litres_per_min: int = Field(ge=50, le=900)
	personal_best: int | None = Field(default=None, ge=50, le=900)


class WeightReading(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	kg: float = Field(gt=1, le=400)


class ConditionProfile(BaseModel):
	"""MON-003 condition list. HIV status is separately gated (§9.1 privacy: separate PIN)."""
	model_config = MODEL_CONFIG
	subject_ref: str
	conditions: list[str] = Field(default_factory=list)
	hiv_pin_set: bool = False


# --- MON-005..008: environmental & nutrition --------------------------------------------

class VectorRisk(BaseModel):
	model_config = MODEL_CONFIG
	county: str
	rainfall_band: str = Field(pattern=r'^(dry|normal|wet|flood)$')
	malaria_season: bool
	rvf_alert: bool
	advise: str


class BreedingSiteReport(BaseModel):
	model_config = MODEL_CONFIG
	county: str
	lat: float = Field(ge=-5, le=6)
	lon: float = Field(ge=33, le=43)
	description: str = Field(min_length=3, max_length=200)


class FoodSafetyAlert(BaseModel):
	model_config = MODEL_CONFIG
	county: str
	kind: str = Field(pattern=r'^(aflatoxin|recall|cholera_food|other)$')
	detail: str = Field(min_length=3, max_length=300)
	source: str


class NutritionGuidance(BaseModel):
	model_config = MODEL_CONFIG
	age_months: int = Field(ge=0, le=60)
	guidance: str
	seasonal_foods: list[str]


# --- MON-009: 21-day contact monitoring diary --------------------------------------------

class MonitoringDay(BaseModel):
	model_config = MODEL_CONFIG
	entry_id: str = Field(pattern=r'^MON-[A-Z0-9]{8,}$')
	subject_ref: str
	day: int = Field(ge=1, le=21)
	temperature_c: float = Field(ge=30, le=45)
	# §14.9: a paired thermometer measures this; otherwise it is a number someone typed, and the
	# fever threshold below fires on it either way — which is why the source has to travel.
	source: MeasurementSource = MeasurementSource.manual
	symptoms: list[str] = Field(default_factory=list)
	household_member: str | None = None
	location_logged: bool = False


class MonitoringVerdict(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	day: int = Field(ge=1, le=21)
	days_remaining: int = Field(ge=0, le=20)
	escalate: bool
	notify_chw: bool
	message: str
	# §14.9: whether the temperature behind this verdict came from a paired device. A fever a
	# thermometer measured and a fever typed from memory produce the same escalation, so the
	# difference is only visible if the verdict carries it.
	clinical_grade: bool = False
	reading_source: MeasurementSource = MeasurementSource.manual


class HouseholdMonitor(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	monitoring_officer: str | None = None
	members: list[str] = Field(default_factory=list)
