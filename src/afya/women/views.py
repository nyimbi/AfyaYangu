"""Women's health: menstrual cycle tracking (period prediction, fertile window, §17.6 adolescent protections)."""
from pydantic import BaseModel, ConfigDict, Field

from afya.ids import ref8

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class CycleLog(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	start_iso: str  # period start date
	cycle_days: int = Field(default=28, ge=20, le=45)
	pain_level: int = Field(default=0, ge=0, le=10)


class CyclePrediction(BaseModel):
	model_config = MODEL_CONFIG
	next_period_iso: str | None
	fertile_window_days: tuple[int, int] | None = None
	cycle_regularity: str = Field(pattern=r'^(regular|irregular|insufficient_data)$')
	advise: str
	# §REC-004's "fertility awareness". The window above is a pair of *cycle days*, which is what a
	# person reading a calendar wants and what `advise` used to be the only carrier of — the field
	# was declared and set to None on every path, so no client could read it as a value. These two
	# are the same window in dates, because a person plans by date, plus the caveat the source
	# states and the note that a calendar estimate is not a contraceptive method.
	fertile_from_iso: str | None = None
	fertile_to_iso: str | None = None
	ovulation_iso: str | None = None
	fertility_note: str = ''


class ContraceptionRequest(BaseModel):
	"""What a caller may say about their contraception — and nothing about how well it works.

	A request and a result, not one model, for the reason the catalogue gate's own history records:
	`label`, `reliability` and `prevents_sti` are read from WHO's table by the service, so they are
	not inputs and a form cannot fill them. Leaving them on the input model made the route
	unfillable from the catalogue — the exact defect class that gate exists to find — and making them
	optional would have hidden it rather than fixed it. A caller that sends one is refused by
	`extra='forbid'`, which is a stronger statement than ignoring it.
	"""

	model_config = MODEL_CONFIG
	subject_ref: str
	method: str
	started_iso: str
	# Days between repeats, for the methods that repeat. None for a long-acting method and for one
	# that is used as needed: how often a pill is taken is a fact about the prescription, and an
	# implant is not taken on a schedule at all.
	repeat_days: int | None = Field(default=None, ge=1, le=366)


class ContraceptionPlan(BaseModel):
	"""§REC-004's "contraception reminders" — the method as recorded, and when it is next due.

	Not a notification queue: nothing here sends anything, and the reminder is the `next_due_iso`
	a client reads and schedules locally, on the same reasoning as §EMG-001's countdown (§ACC-004
	wants no background polling). The method's own reliability is carried as WHO's wording rather
	than a percentage, because the fact sheet states no percentage for any method.
	"""

	model_config = MODEL_CONFIG
	plan_id: str = Field(default_factory=lambda: 'CP-' + ref8())
	subject_ref: str
	method: str
	label: str
	reliability: str
	prevents_sti: bool
	started_iso: str
	repeat_days: int | None = Field(default=None, ge=1, le=366)
	next_due_iso: str | None = None
	notes: list[str] = []


class MenopauseStatus(BaseModel):
	"""§REC-004's "menopause support", as the state the person's own logs put them in.

	The state machine is the WHO fact sheet's twelve-month rule and nothing else: a person is
	`perimenopausal` — and the fact sheet says explicitly that pregnancy is still possible and
	contraception is still recommended — until twelve consecutive months have passed with no period.
	The tracker reports the count and never decides on its own that someone has reached menopause,
	because the source frames that as a clinical judgement and the age range it gives is a
	population figure ("most women", 45–55) and not a rule about a person.
	"""

	model_config = MODEL_CONFIG
	subject_ref: str
	state: str = Field(pattern=r'^(insufficient_data|cycling|perimenopausal|postmenopausal)$')
	months_since_last_period: int | None = None
	months_required: int
	last_period_iso: str | None = None
	contraception_still_recommended: bool
	symptoms: list[dict[str, str]] = []
	advise: str


class ReproductiveReferral(BaseModel):
	"""§REC-004's "referral to services" — the services, and what could not be reached.

	The same shape as §REC-005's `ServiceReferral`, and for the same reason: a referral to a service
	that does not exist is worse than none, because the person stops looking. Each row names where
	the service is; the ones whose number could not be verified are listed by name.
	"""

	model_config = MODEL_CONFIG
	referral_id: str = Field(default_factory=lambda: 'RH-' + ref8())
	subject_ref: str
	reason: str
	services: list[dict[str, str]]
	unreachable: list[str]
	advise: str