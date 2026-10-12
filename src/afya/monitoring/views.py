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

class ReminderSlot(str, Enum):
	"""§MON-009's "twice-daily reminders", as the two slots a day actually has.

	A reminder is not a message the app sends into nothing: it is a time the person is asked to log,
	and the check-in surface has to know whether the day's two are done. Morning and evening rather
	than arbitrary times, because a temperature read at bedtime and one read at dawn are the two the
	21-day window is built from, and a third would be a schedule nobody keeps.
	"""
	morning = 'morning'
	evening = 'evening'


# Both slots are required for a day to be complete, and the escalation ladder is §11.3's own
# adherence design — "reminders escalate in urgency if missed".
REMINDER_SLOTS: tuple[ReminderSlot, ...] = (ReminderSlot.morning, ReminderSlot.evening)


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
	# §MON-009's twice-daily cadence, carried on the entry rather than inferred from how many were
	# filed. Optional because a client that does not send it must still be able to log — but when it
	# is absent the service can only count entries, and two readings taken the same morning look
	# exactly like one morning and one evening.
	slot: ReminderSlot | None = None


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
	# §MON-009's "psychological support resources". A 21-day diary is a frightening place to be —
	# the person is watching themselves for a disease that kills — so the support is attached to the
	# verdict rather than left in another section of the app for them to find. Carried on every
	# verdict including the clear ones, because the day someone most needs it is not always a
	# flagged day, and it escalates with the verdict when it is.
	support: list[dict[str, str]] = Field(default_factory=list)


class MonitoringReminder(BaseModel):
	"""One day's reminder state, derived from what was logged rather than from what was sent.

	`missing` is what makes this a control rather than a notification: a reminder surface that
	cannot name the missed slots cannot escalate, and §MON-009 says the reminders escalate.
	"""
	model_config = MODEL_CONFIG
	subject_ref: str
	day: int = Field(ge=1, le=21)
	due: list[str]
	logged: list[str]
	missing: list[str]
	complete: bool
	escalation: str = Field(pattern=r'^(none|gentle|firm|urgent)$')
	message: str


class HouseholdMonitor(BaseModel):
	"""One contact's 21-day household. The members are monitored in the same interface, not beside it.

	§MON-009 asks for "household member monitoring in the same interface", and the predecessor had
	`members: list[str]` with nothing that read it — so a household was a list of names on a record
	and no member had a diary. `MonitoringDay.household_member` existed too and was never read, which
	is the same gap from the other side: a day could be filed *for* a member and counted *as* the
	contact's.
	"""
	model_config = MODEL_CONFIG
	subject_ref: str
	monitoring_officer: str | None = None
	# §MON-009 asks for a *direct line* to the officer. A name alone is not dialable — the predecessor
	# had exactly that and the audit row said so — so the number travels with the name or neither is
	# recorded, and the route serves `tel:` only when there is a number behind it.
	monitoring_officer_number: str | None = None
	members: list[str] = Field(default_factory=list)
	# Consent for contact-tracing location, recorded as a decision with a time rather than as the
	# `location_logged` boolean a client could simply set true. A monitored person is under
	# surveillance by definition; making their location opt-in and revocable is the difference
	# between contact tracing and tracking.
	location_consent: bool = False
	location_consent_at_iso: str | None = None


class LocationConsentDecision(BaseModel):
	"""§MON-009's consent, as a decision the contact makes rather than a field a client sets.

	`granted` is two-valued on purpose: withdrawal has to be expressible, and a model that only
	carries "consent given" cannot record the moment somebody changed their mind.
	"""
	model_config = MODEL_CONFIG
	granted: bool
	at_iso: str = Field(min_length=10)


class HouseholdMemberRequest(BaseModel):
	model_config = MODEL_CONFIG
	member_ref: str = Field(min_length=1, max_length=64)
