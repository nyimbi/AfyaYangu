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


# --- §MON-007 "larviciding campaign notifications" ---------------------------------------
#
# The vocabulary and the figures below are the WHO operational manual's, archived at
# `sources/who-larval-source-management/`. Two of its statements are load-bearing and are carried
# as constants rather than paraphrased into the notice text, because a notice that dropped either
# would be telling people something the source does not:
#
#   "larviciding measures should normally be used only as a supplement to the core interventions
#    (ITNs or IRS); larviciding should never be seen as a substitute for ITNs or IRS in areas with
#    significant malaria risk"
#
#   "larviciding will generally be most effective in areas where larval habitats are few, fixed and
#    findable ... most likely to be cost-effective in urban areas ... in rural settings, larviciding
#    is not recommended unless there are particular circumstances limiting the larval habitats"
#
# A notice is therefore never served without `SUPPLEMENT_RULE`, and a rural county is served the
# source's own condition rather than a round that reads as routine.
SUPPLEMENT_RULE = (
	'Larviciding supplements treated nets and indoor spraying; it does not replace them. '
	'Keep using your net every night.'
)

# What the manual calls the "few, fixed and findable" condition, as the question the county answers.
LSM_FEASIBILITY = (
	'Larviciding works best where the breeding sites are few, fixed and easy to find — '
	'most often in towns and cities. In rural areas WHO does not recommend it unless the '
	'breeding sites are limited and the county can show it reduces malaria here.'
)

# The larvicide classes the manual names, as (slug, label, typical interval in days). The interval
# is the manual's own: "Frequency of re-treatment with bacterial larvicides can range from 1 to 4
# weeks for Anopheles ... Typical re-treatment intervals with Bti are 7–10 days"; surface films
# "Re-treatment is needed weekly"; IGR briquettes "slowly release methoprene for up to four
# months". `None` is a class whose interval the manual states as a range rather than a figure.
LARVICIDE_CLASSES: dict[str, tuple[str, int | None]] = {
	'bacterial': ('Bacterial larvicide (Bti, Bs)', 10),
	'surface_film': ('Surface film or oil', 7),
	'growth_regulator': ('Insect growth regulator', 28),
	'organophosphate': ('Organophosphate (temephos)', 42),
}

# The shortest interval any class above carries, derived rather than typed. §MON-007's household
# container reminder uses it so a family is asked to clear standing water at least as often as a
# county would re-treat the same water; a second hand-typed 7 here would be a second definition of
# "the most frequent interval", and the two would part company the moment a class is added.
LARVICIDE_INTERVAL_FLOOR_DAYS: int = min(
	interval for _label, interval in LARVICIDE_CLASSES.values() if interval is not None
)

# §MON-007's "personal protection reminders": the hour the net reminder is anchored to. The manual
# puts anopheline biting "between dusk and dawn", so the reminder belongs at dusk rather than at an
# arbitrary hour — a reminder to sleep under a net is worth nothing at noon.
DUSK_HOUR = 18


class LarvicidingNotice(BaseModel):
	"""§MON-007's "larviciding campaign notifications" — a round, and who it reaches.

	`campaign_id` and the county list make this the same shape as §MON-001's `CampaignNotice` in the
	one respect that matters — a notice is addressed to a place — and deliberately *not* the same
	shape in the other: a campaign notice carries `target_age_months` because it is aimed at
	children in a band, and a larviciding round has no age band at all. Sharing the model would have
	meant a required `target_age_months` on a notice that has none, which is how a field that means
	nothing gets invented.

	`habitats` is the manual's own unit of work: larviciding is applied to *water bodies*, and the
	person reading the notice is deciding whether the drain outside their gate is being treated.
	`larvicide` is a `LARVICIDE_CLASSES` key so the label and the re-treatment interval cannot
	drift apart, and `next_round_iso` is derived from that interval rather than typed in.
	"""

	model_config = MODEL_CONFIG
	campaign_id: str = Field(default_factory=lambda: 'LSM-' + uuid7str().replace('-', '')[-8:].upper())
	counties: list[str]
	larvicide: str
	habitats: list[str]
	first_round_iso: str
	issued_by: str = Field(pattern=r'^(MoH|PHEOC|County)$')
	headline: str = Field(max_length=120)
	body: str = Field(max_length=600)

	@model_validator(mode='after')
	def _the_vocabulary_is_the_sources(self) -> Self:
		assert self.counties, 'a larviciding round with no county reaches nobody'
		assert self.habitats, 'a larviciding round with no habitat treats nothing'
		assert self.larvicide in LARVICIDE_CLASSES, (
			f'{self.larvicide!r} is not a larvicide class: {sorted(LARVICIDE_CLASSES)}')
		return self


class ProtectionReminder(BaseModel):
	"""§MON-007's "personal protection reminders", as the two instants the device schedules.

	The section's own `VectorRisk.advise` already says "drain containers, use nets every night" — as
	text, on the screen, once. What the bullet asks for is the reminder, and a reminder needs a time.

	`net_due_iso` is the one figure the source fixes: the manual puts anopheline biting "between
	dusk and dawn (and especially during the early hours of the morning)" and names `An. gambiae`
	and `An. funestus` peak biting "an hour before dawn", so the net reminder is placed against
	dusk and the message says why it is an evening reminder rather than a morning one.
	`container_due_iso` is a *recurrent* activity in the manual's own sense — habitat manipulation
	is "a recurrent activity including water level manipulation ... keeping drains clear" — and its
	interval is the shortest re-treatment interval any larvicide class carries, so a household is
	asked to clear standing water at least as often as a county would re-treat it.
	"""

	model_config = MODEL_CONFIG
	county: str
	rainfall_band: str = Field(pattern=r'^(dry|normal|wet|flood)$')
	net_due_iso: str
	container_due_iso: str
	message: str


class FoodSafetyAlert(BaseModel):
	model_config = MODEL_CONFIG
	county: str
	kind: str = Field(pattern=r'^(aflatoxin|recall|cholera_food|other)$')
	detail: str = Field(min_length=3, max_length=300)
	source: str


class NutritionGuidance(BaseModel):
	"""§MON-008's "infant feeding guidance" and "Seasonal food availability", in one answer.

	Two lists, deliberately not merged. `seasonal_foods` is the age band's own list — the foods a
	child of this age can eat — and `in_season` is what is being harvested this month. A parent is
	making both decisions at once and they are not the same decision, so a merged list would lose
	which entry was which. `in_season` is empty when the caller named no month, and `calendar_source`
	says where the harvest months came from, because a seasonal claim with no provenance is a claim
	a reader cannot check.
	"""

	model_config = MODEL_CONFIG
	age_months: int = Field(ge=0, le=60)
	guidance: str
	seasonal_foods: list[str]
	month: int | None = Field(default=None, ge=1, le=12)
	in_season: list[str] = []
	calendar_source: str | None = None


# --- §MON-008 "Seasonal food availability" ------------------------------------------------
#
# Harvest windows per crop, from the FAO Crop Calendar for Kenya, archived at
# `sources/fao-crop-calendar-kenya/`. Generated from the source's own JSON rather than typed by
# hand: each crop's months are the union of its early- and late-harvest months across all 22
# agro-ecological zones the source disaggregates by. `_allyear` is the source's own `all_year`
# flag, set for the five crops it marks as harvestable throughout the year in at least one zone.
#
# Two honest limits, both the source's:
#
#  * The FAO data is **disaggregated by agro-ecological zone** and there is no national month. A
#    month in this table therefore means "harvested in this month somewhere in Kenya", which is the
#    right granularity for a *national* app and the wrong one for a county advisor. The table is
#    used to answer "what is in season", not "what is in season in Siaya".
#  * The source covers 30 crops and the local list below maps only the ones it has. **Avocado,
#    mango, banana, amaranth (terere) and fish are absent from the FAO data** and are therefore
#    absent here rather than given invented months — `NUTRITION_BY_AGE` names avocado and small
#    fish, and this table does not pretend to know when they are harvested.
SEASONAL_CALENDAR_SOURCE = 'FAO Crop Calendar for Kenya (harvest windows, all agro-ecological zones)'

# (label served, the source's own crop name, harvest months, the source's all-year flag). The
# source's crop names are French — it is FAO's French-language rendering of the Kenyan crop list —
# so the served label is an English rendering and the source name is kept beside it. Without the
# source name the translation would be unverifiable: a reader checking this table against the JSON
# needs to know that `Fève, vert` is what became `Broad bean`, and a mapping asserted only by
# position is a mapping nobody can check.
SEASONAL_FOODS: tuple[tuple[str, str, tuple[int, ...], bool], ...] = (
	('Bok choy', 'Bok choy', (4, 5, 6, 10, 12), False),
	('Broad bean', 'Fève, vert', (1, 2, 3, 6, 7, 8, 9, 10, 11, 12), False),
	('Cabbage', 'Chou, commun', (1, 2, 5, 6, 7, 10, 11, 12), False),
	('Carrot', 'Carotte', (1, 2, 5, 6, 7, 10, 11), False),
	('Cashew nut', 'Noix de cajou', (1, 12), True),
	('Cassava', 'Manioc', (1, 12), True),
	('Chickpea', 'Pois chiche', (1, 2, 6, 7, 8, 11, 12), False),
	('Coconut', 'Noix de coco', (7, 8, 9, 12), True),
	('Cowpea', 'Niébé', (1, 2, 5, 6, 7, 8, 9, 10, 11, 12), False),
	('Dolichos (lablab)', 'Dolicos lablab', (1, 3, 6, 8), False),
	('Dry pea', 'Petit pois, sec', (2, 3, 4, 5, 7, 8, 9, 10, 12), False),
	('Finger millet', 'Millet, sabac', (1, 2, 3, 5, 6, 7, 8, 11), False),
	('Green gram', 'Pigeon', (1, 2, 4, 7, 8, 9, 10), False),
	('Groundnut', 'Cacahuète', (1, 2, 3, 6, 7, 8, 11, 12), False),
	('Kales (sukuma wiki)', 'Kales', (1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12), False),
	('Maize (sweet corn)', 'Maïs, sucré', (1, 2, 3, 5, 6, 7, 8, 9, 12), False),
	('Onion', 'Oignon', (1, 2, 3, 4, 7, 8, 9, 10), False),
	('Potato', 'Pomme de terre', (1, 2, 3, 4, 6, 7, 8, 9, 10, 11), False),
	('Pumpkin', 'Citrouille', (1, 3, 6, 8), False),
	('Rice', 'Riz', (8, 9), True),
	('Sesame', 'Sésame', (1, 2, 3, 6, 7, 8, 9, 11), False),
	('Sorghum', 'Sorgho', (1, 2, 3, 4, 6, 7, 8, 9, 11, 12), False),
	('Soybean', 'Soja', (1, 3, 6, 7, 8, 9, 11, 12), False),
	('Sugar cane', 'Canne à sucre', (1, 2, 3, 4, 5, 6, 12), True),
	('Sunflower', 'Tournesol', (1, 2, 3, 6, 7, 8, 9, 11, 12), False),
	('Sweet potato', 'Patate douce', (1, 2, 3, 5, 6, 7, 8, 9, 11, 12), False),
	('Tomato', 'Tomate', (1, 2, 4, 5, 6, 7, 8, 10, 11, 12), False),
	('Watermelon', 'Pastèque', (1, 3, 6, 7, 8), False),
	('Wheat (bread)', 'Pain de blé', (1, 3, 8, 9, 10, 11), False),
)

# The Kenya IMAM programme types, as (slug, label, the guideline's own definition). These are the
# three programmes a therapeutic feeding *site* runs, and they are not interchangeable: the
# guideline's abbreviation list prints `OTP: Out-patient Therapeutic Programme`, `SC: Stabilization
# Center` and `SFP: Supplementary Feeding Programme`, and its body text says a child with severe
# acute malnutrition and no complications is treated at an OTP while one with complications — or an
# infant under six months — is admitted to an SC. A parent sent to the wrong one is turned away.
#
# They are served as the national vocabulary, not as a claim about any one site: the facility
# registry records *that* a facility is a therapeutic feeding site (`FacilityKind.therapeutic_feeding`)
# and does not record which of the three it runs, and inventing that per row would be the registry
# telling a parent something nobody filed.
IMAM_PROGRAMMES: tuple[tuple[str, str, str], ...] = (
	('otp', 'Out-patient therapeutic programme',
	 'A child with severe acute malnutrition and no medical complications is treated here and '
	 'goes home the same day, returning for follow-up.'),
	('sc', 'Stabilisation centre',
	 'A child with severe acute malnutrition and medical complications, or an infant under six '
	 'months, is admitted here as an in-patient.'),
	('sfp', 'Supplementary feeding programme',
	 'A child with moderate acute malnutrition — not yet severe — is treated here, at a health '
	 'facility or an outreach site.'),
)

# §MON-008's "therapeutic feeding programme locations" is the one bullet in the section that could
# not be sourced from OpenStreetMap: there is no OSM tag for a therapeutic feeding centre or a
# malnutrition treatment site (the `healthcare` key's 31 values include none, the `amenity` key's
# feeding values are all animal feeding, and a live taginfo search for `malnutrition` returns no
# structured keys). The vocabulary is therefore Kenya's national guideline, archived at
# `sources/kenya-imam-guidelines/`.
THERAPEUTIC_FEEDING_LABEL = (
	'A health facility running a therapeutic feeding programme for acute malnutrition, under '
	"Kenya's Integrated Management of Acute Malnutrition guidelines"
)
THERAPEUTIC_FEEDING_SOURCE = (
	'Kenya National Guideline for Integrated Management of Acute Malnutrition (IMAM)'
)


class TherapeuticFeedingSite(BaseModel):
	"""§MON-008's "therapeutic feeding programme locations" — a site, and what it is for.

	`kind` is `FacilityKind`'s slug and `label` the IMAM description of what such a site does, so
	the screen never holds a second copy of the vocabulary — the same reasoning §REC-006's
	`DonationCentre` follows for its two OpenStreetMap kinds.

	`programmes` is the national vocabulary of the three programme types, served with every result
	so a parent can see which door is which. It is deliberately *not* a per-site claim: the registry
	records that a facility is a therapeutic feeding site and not which programme it runs, and a
	field asserted per row from nothing would send a child with complications to an out-patient
	queue.
	"""

	model_config = MODEL_CONFIG
	facility_id: str
	name: str
	county: str
	kind: str
	label: str
	distance_km: float = Field(ge=0)
	level: str | None = None
	phone: str | None = None
	walk_in: bool = True
	programmes: list[dict[str, str]] = Field(
		default_factory=lambda: [{'slug': s, 'label': lab, 'definition': d} for s, lab, d in IMAM_PROGRAMMES])
	source: str = THERAPEUTIC_FEEDING_SOURCE


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
