"""Monitoring & reminder models (spec §9.1 MON-001..004, §10.2 MON-005..008, §11.3 MON-009)."""
from enum import Enum

from typing import Self

from afya.sensors.views import MeasurementSource
from pydantic import BaseModel, ConfigDict, Field, model_validator

from afya.ids import uuid7str
from afya.records.views import EPI_SCHEDULE

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


# --- MON-001: child immunisation tracker -------------------------------------------------

# The schedule is `records.views.EPI_SCHEDULE`, re-exported rather than restated. The tracker is a
# *view* over the doses the wallet holds — it decides what is due and what is overdue — and a
# schedule kept beside the record would be the second copy of one fact. The two disagreed until
# this change: `RV`/`Measles-Rubella` here against `RV1`/`MMR` there, and IPV at dose 1 against dose
# 2, so a dose recorded through the tracker was invisible to the wallet's gap check.
EPI_DUE_WEEKS: dict[str, list[tuple[int, int]]] = EPI_SCHEDULE

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


class ImmunisationAlert(BaseModel):
	"""§MON-001's "Missed-dose alerts", as the alert a client acts on rather than a status string.

	`schedule` has always been able to say a dose is `overdue`; what was missing is anything that
	*raises* one. The alert is served as data on the same reasoning as §REC-004's contraception
	reminder and §EMG-001's countdown — §ACC-004 wants no background polling, so the server states
	the alert and the device schedules it. `kind` separates the two the section names apart: a dose
	the child is behind on (`overdue`) and a dose that is coming (`due_soon`), which are different
	messages to a parent and were the same string before.
	"""

	model_config = MODEL_CONFIG
	member_ref: str
	vaccine: str
	dose_no: int = Field(ge=0, le=4)
	kind: str = Field(pattern=r'^(overdue|due_soon)$')
	days_overdue: int = Field(ge=0)
	due_iso: str
	message: str


class CampaignNotice(BaseModel):
	"""§MON-001's "Campaign notifications (polio, measles)" — the notice, and who issued it.

	A campaign is not a §11.1 community alert: it is not a hazard in a county, it is a service
	being offered to an age group, and its audience is the parents of children in that band rather
	than everyone within a boundary. So it carries its own shape and is published into the feed
	under the immunisation category, where a parent who asked for immunisation reminders is the
	person who receives it.

	`disease` is a `registry.diseases` slug, which is what makes "polio" expressible: polio is a
	campaign and not one of §3.3 principle 12's outbreak diseases, so it is a campaign target and
	never an `AlertKind`. `target_age_months` is the band the campaign is for, because a measles
	campaign for nine-month-olds and one for school entrants are different notices to the same
	parent.
	"""

	model_config = MODEL_CONFIG
	campaign_id: str = Field(default_factory=lambda: 'CMP-' + uuid7str().replace('-', '')[-8:].upper())
	disease: str
	counties: list[str]
	target_age_months: tuple[int, int]
	starts_iso: str
	ends_iso: str
	headline: str = Field(max_length=120)
	body: str = Field(max_length=600)
	issued_by: str = Field(pattern=r'^(MoH|PHEOC|County)$')

	@model_validator(mode='after')
	def _band_is_ordered(self) -> Self:
		"""`(59, 9)` is a tuple of two ints and an age band of nobody.

		A validator rather than an assertion in the service, because the service's assert is only
		reached by callers that go through the service — a client posting the notice is checked by
		the model, and a band that reads backwards would otherwise publish a campaign addressed to
		no child. The upper bound is 216 months: eighteen years, past which a person is an adult and
		not the subject of a child vaccination campaign.
		"""
		low, high = self.target_age_months
		assert 0 <= low < high <= 216, f'{low}-{high} months is not an age band a campaign can have'
		return self


# --- MON-004: medication reminders -------------------------------------------------------

# §MON-004's "Multiple daily reminders". A day has the times a person actually takes medicine at,
# and the section's count is not one of them: `times_per_day=2` cannot be notified at. These are
# the instants a reminder fires, on a 24-hour clock, chosen so that a twice-daily course lands on
# morning and evening rather than on two arbitrary hours.
REMINDER_CLOCK: dict[int, tuple[str, ...]] = {
	1: ('08:00',),
	2: ('08:00', '20:00'),
	3: ('08:00', '14:00', '20:00'),
	4: ('06:00', '12:00', '18:00', '22:00'),
	5: ('06:00', '10:00', '14:00', '18:00', '22:00'),
	6: ('06:00', '10:00', '14:00', '18:00', '22:00', '02:00'),
}


def reminder_times(times_per_day: int) -> list[str]:
	"""The instants to wake somebody for a course of `times_per_day` doses.

	Every schedule has times rather than a count, because a count is not a time. The mapping is a
	table rather than arithmetic — an even division of 24 hours by 6 gives 04:00 as the first dose,
	which is a time nobody chose.
	"""
	assert 1 <= times_per_day <= 6, f'{times_per_day} doses a day is outside the table'
	return list(REMINDER_CLOCK[times_per_day])


class MedSchedule(BaseModel):
	model_config = MODEL_CONFIG
	schedule_id: str = Field(default_factory=lambda: 'MED-' + uuid7str().replace('-', '').upper()[:6])
	member_ref: str
	drug: str
	dose: str
	times_per_day: int = Field(ge=1, le=6)
	start_iso: str
	duration_days: int = Field(ge=1, le=365)
	refill_at_days_left: int = Field(default=7, ge=1, le=60)
	# Derived from `times_per_day` by the service, never supplied by a caller — the same reason
	# `RegistrationOutcome.genuine` is derived: two clients computing their own reminder instants
	# would eventually disagree about when to wake somebody, and the one that disagrees is the one
	# that is wrong. Empty until `add_schedule` fills it.
	reminder_times: list[str] = Field(default_factory=list)


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
	entry_id: str = Field(default_factory=lambda: 'MON-' + uuid7str().replace('-', '').upper()[:8])
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
