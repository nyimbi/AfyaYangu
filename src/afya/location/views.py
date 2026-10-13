"""Location & proximity models (spec §11.5 LOC-002..005, §8.6 LOC-001).

Everything here is Tier 4 except LOC-001's static advisory zones. Raw location never crosses
this boundary: LOC-003 accepts geohashes, never coordinates.
"""
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

EBID_ROTATION_MINUTES = 15
LOCATION_WINDOW_DAYS = 21
LOCATION_WINDOW_MAX_DAYS = 28

# §COM-102's geofenced alert zones — "500 m, 1 km, 5 km — configurable by county" — and §8.6
# LOC-001's alert radii, which are the same three numbers. Kept here rather than in the location
# *service* because the peer-alert model validates against the set: a zone the section does not
# offer is a radius no county can configure, and a model that imported the service would make a
# views module depend on a service module for a constant that is a fact about the spec.
ALERT_ZONE_RADII_M: tuple[int, ...] = (500, 1000, 5000)


# --- LOC-002 BLE proximity ---------------------------------------------------------------

class EphemeralId(BaseModel):
	model_config = MODEL_CONFIG
	ebid: str = Field(pattern=r'^[0-9a-f]{32}$')
	rotated_at_ms: int
	rotates_every_minutes: int = EBID_ROTATION_MINUTES


class EncounterToken(BaseModel):
	"""Private Encounter Token — identifies an encounter without identifying a person."""
	model_config = MODEL_CONFIG
	pet: str = Field(min_length=32, max_length=64)
	seen_at_ms: int
	rssi_dbm: int = Field(ge=-120, le=0)
	county: str


class ExposureDeclaration(BaseModel):
	model_config = MODEL_CONFIG
	declaration_id: str
	pet: str = Field(min_length=32, max_length=64)
	declared_at_ms: int
	proxied: bool = True


class ExposureMatch(BaseModel):
	model_config = MODEL_CONFIG
	matched: bool
	encounters: int = Field(ge=0)
	window_days: int = Field(ge=1, le=28)
	message: str


# --- LOC-003 location history ------------------------------------------------------------

class LocationPoint(BaseModel):
	model_config = MODEL_CONFIG
	geohash: str = Field(pattern=r'^[0-9a-z]{5,9}$')
	at_iso: str
	place_label: str | None = Field(default=None, max_length=80)


class LocationHistory(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	points: list[LocationPoint] = Field(default_factory=list)
	consent_granted: bool = False
	window_days: int = Field(default=LOCATION_WINDOW_DAYS, ge=1, le=LOCATION_WINDOW_MAX_DAYS)


class LocationReport(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	points: int = Field(ge=0)
	places: list[str]
	window_days: int = Field(ge=1, le=28)
	shared_with: str | None
	message: str


# --- LOC-004 QR / NFC check-in -----------------------------------------------------------

class CheckInPoint(BaseModel):
	model_config = MODEL_CONFIG
	point_id: str
	kind: str = Field(pattern=r'^(border_post|health_facility|isolation_unit|vaccination_point|school|workplace|event)$')
	label: str
	county: str
	token: str = Field(pattern=r'^[A-Z0-9]{6,16}$')


class CheckIn(BaseModel):
	model_config = MODEL_CONFIG
	checkin_id: str = Field(pattern=r'^CHK-[A-Z0-9]{8,}$')
	point_token: str = Field(pattern=r'^[A-Z0-9]{6,16}$')
	subject_ref: str
	method: str = Field(pattern=r'^(qr|nfc|manual)$')
	at_iso: str
	share_with_authority: bool = False


class CheckInReceipt(BaseModel):
	model_config = MODEL_CONFIG
	checkin_id: str
	point_label: str
	guidance: str
	logged_locally: bool
	shared: bool


# --- LOC-005 border and point-of-entry ---------------------------------------------------

class BorderPost(BaseModel):
	model_config = MODEL_CONFIG
	post_id: str
	name: str
	county: str
	country_pair: str
	queue_minutes: int = Field(ge=0, le=1440)
	screening_required: bool
	# §LOC-005's "integration with mobile laboratory results at border points". A mobile lab is a
	# *capability of the post*, not a result: a post either has one on site or sends its samples
	# onward, and a screen that could not say which is a traveller sent to a post that cannot test
	# them. Absent means the post does not report a lab, which is not the same as reporting none.
	mobile_lab: bool = False
	lab_turnaround_hours: int | None = Field(default=None, ge=1, le=168)
	lab_tests: list[str] = Field(default_factory=list)

	@model_validator(mode='after')
	def _a_lab_is_described_or_absent(self) -> Self:
		"""A turnaround with no lab behind it is a promise from a post that cannot keep it, and a
		test list with no lab is a menu for a service that is not there. The three fields move
		together or none of them is set."""
		assert self.mobile_lab == (self.lab_turnaround_hours is not None), (
			'a lab turnaround was stated for a post that reports no lab, or a lab with no turnaround'
		)
		assert self.mobile_lab == bool(self.lab_tests), (
			'a post reports a lab but names no test, or names tests with no lab behind them'
		)
		return self


class TravelerDeclaration(BaseModel):
	model_config = MODEL_CONFIG
	declaration_id: str = Field(pattern=r'^TD-[A-Z0-9]{8,}$')
	subject_ref: str
	destination: str
	arrival_iso: str
	origin_country: str
	symptoms: list[str] = Field(default_factory=list)
	# §LOC-005's "multi-language support for cross-border travellers". The declaration already carried
	# this and nothing read it, so the field was a claim: every acknowledgement went out in English
	# whatever the traveller said they read.
	lang: str = 'en'


class PostArrivalReport(BaseModel):
	"""§LOC-005's "post-arrival symptom reporting": what a traveller sends on one of the 21 days.

	The enrolment stated a schedule — days 1, 3, 7, 14 and 21 — and no route accepted a report
	against it, so the schedule was a notification plan with nothing on the other end. `day` is the
	day of the window and not a date, because that is what the schedule names and what the traveller
	is being asked about.
	"""
	model_config = MODEL_CONFIG
	subject_ref: str
	day: int = Field(ge=1, le=28)
	symptoms: list[str] = Field(default_factory=list)
	temperature_c: float | None = Field(default=None, ge=30.0, le=45.0)


class PostArrivalVerdict(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	day: int
	days_remaining: int
	escalate: bool
	notify_border_health: bool
	message: str
	lang: str


class TravellerEnrolment(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	monitoring_days: int = Field(default=21, ge=1, le=28)
	enrolled: bool
	report_schedule: list[int]
	message: str
	lang: str = 'en'
	# §INF-005's fifth Feature is "21-day self-monitoring enrolment for travellers (**links to
	# MON-009**)", and the link was a sentence: the acknowledgement said the traveller was enrolled
	# for 21 days while `MonitoringService` had never heard of them, so the diary route answered an
	# empty list. The field is what makes the link checkable from the payload rather than inferred
	# from a message string — `False` means this deployment has no monitoring service wired, which
	# a client can act on instead of showing a schedule nothing will ask about.
	diary_linked: bool = False


# --- §INF-005 travel advisories ------------------------------------------------------------
#
# "Country and county advisories" is two halves and the repo had neither: `advisory()` interpolated
# the caller's two arguments into one fixed paragraph, so the country half was a constant and the
# county half had no carrier at all. `PlaceAdvisory` is the shape both halves are served in.

class PlaceAdvisory(BaseModel):
	"""One place — a country or a Kenyan county — with the band the authority gives it.

	`kind` is load-bearing and not decoration: the two halves read from **different vocabularies**.
	A country carries WHO's `very_high|high|low|not_assessed`, a county carries §INF-001's dashboard
	`low|moderate|high`, and a client that rendered the union as one scale would put a Kenyan county
	assessed "high" beside the Democratic Republic of the Congo assessed "very high" and let a reader
	rank them. `band` accepts the union so one model serves both; `kind` says which table it came
	from, and `source` names the table.

	`unknown` is a third verdict and it is not `low`. A city, a misspelling and a country WHO did not
	name all resolve here, because from the table's side they are one fact: nothing in the source
	addresses it. §INF-005 is asked "is it safe to travel", and the only answer that may never be
	invented is the reassuring one.
	"""
	model_config = MODEL_CONFIG
	place: str
	kind: str = Field(pattern=r'^(country|county|unknown)$')
	name: str = ''
	band: str = Field(pattern=r'^(very_high|high|moderate|low|not_assessed|unknown)$')
	stated: str = ''
	# §8.5's "Last updated timestamp" and "Data source attribution", on both halves. A country's is
	# the date of the assessment it came from; a county's is the dashboard's own stamp, which is
	# `UNDATED_MS` for a county nobody has assessed — the same distinction `CountyRisk` draws, and
	# the reason a defaulted low-risk county cannot read as an assessment made today.
	assessed_on_iso: str = ''
	source: str = ''


class RiskBand(BaseModel):
	"""One row of WHO's own four-row risk table, as the source prints it.

	Served because it is the frame every country row is read in, and because two of its rows are bands
	for *groups* — "Rest of the African Region", "Global" — which cannot be resolved to a country and
	would otherwise be invisible to a traveller who is in neither the DRC nor a land-border state.
	"""
	model_config = MODEL_CONFIG
	label: str
	band: str = Field(pattern=r'^(very_high|high|low)$')
	printed: str
	confidence: str = Field(pattern=r'^(low|moderate|high)$')


class PostTravelStep(BaseModel):
	"""§INF-005's fourth Feature, "What to do if you feel unwell after travel", as steps.

	The row's note called the guidance "one fixed sentence", and it was: `advisory` ended "if you
	feel unwell after arrival, call 719 and say where you travelled", which is one of five things
	the sources say and the only one a Kenyan reader already knows.

	`source` travels on every step because the five are **not one authority's**. Three are quoted
	from WHO or CDC and two are this deployment's operating rule, and a traveller is owed the
	difference — the same reason `sources/INDEX.md` records what a source does *not* support.
	"""
	model_config = MODEL_CONFIG
	step_id: str
	instruction: str
	source: str


class TravelAdvisoryReport(BaseModel):
	"""§INF-005's first and fourth Features, whole: both places, the paragraph, and the steps.

	`advisory` stays a single string because §5.4 puts this answer on WhatsApp, USSD and SMS, and a
	structured payload is not renderable on two of the three. It is no longer a constant: it is
	composed from `destination`'s row, so the same question about two countries returns two answers.
	"""
	model_config = MODEL_CONFIG
	destination: PlaceAdvisory
	origin: PlaceAdvisory
	advisory: str
	steps: list[PostTravelStep]
	risk_table: list[RiskBand]
	who_travel_advice: str
	border_note: str
	traveller_risk_note: str
	not_assessed_caveat: str
	lang: str = 'en'
	source: str
