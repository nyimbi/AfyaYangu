"""Location & proximity models (spec §11.5 LOC-002..005, §8.6 LOC-001).

Everything here is Tier 4 except LOC-001's static advisory zones. Raw location never crosses
this boundary: LOC-003 accepts geohashes, never coordinates.
"""
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from afya.ids import uuid7str

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

EBID_ROTATION_MINUTES = 15
LOCATION_WINDOW_DAYS = 21
LOCATION_WINDOW_MAX_DAYS = 28

# The days a person is asked about symptoms after something put them on watch. Day 1 is the event
# day itself — the same counting §COM-102's `_alert_day` uses (`(seen - issued).days + 1`) — so a
# check-in on the 1st is followed up on the 1st, 3rd, 7th, 15th and 22nd.
#
# One tuple for both §LOC-004's check-in and §LOC-005's traveller arrival, because they are the same
# fact: a border post check-in and an arrival declaration are one event seen twice, and the section
# that schedules the follow-up is §MON-009's 21-day window either way. Two tuples would be two
# answers to "which days do we ask", and the second would be the one nobody re-read.
EXPOSURE_FOLLOWUP_DAYS: tuple[int, ...] = (1, 3, 7, 14, 21)

# §LOC-004's six Deployment points plus the screening point, which the section names in
# "Health facilities and screening points". One tuple, because the client's picker and the model's
# pattern are the same fact: `afya.mobile.actions` carried a hand-typed second copy of this list,
# which is the copy that goes stale the first time a point kind is added.
CHECKIN_KINDS: tuple[str, ...] = (
	'border_post', 'health_facility', 'isolation_unit', 'vaccination_point', 'school', 'workplace',
	'event',
)

# Which check-in points open a 21-day symptom watch. The set is not a clinical taxonomy invented
# here: it is the set §LOC-004's own guidance already speaks a 21-day sentence about, and a point
# that opens a window the app never mentioned would be the app following something up in silence.
# `LocationService` asserts this set and its `GUIDANCE` agree at import, so the two cannot drift.
WATCH_KINDS: tuple[str, ...] = ('border_post', 'event')

assert set(WATCH_KINDS) <= set(CHECKIN_KINDS), 'a watched kind must be a kind a point can be'
# The model's pattern is built from the tuple rather than written out beside it: a second hand-typed
# alternation is the copy that keeps validating a kind the picker no longer offers.
CHECKIN_KIND_PATTERN = '^(' + '|'.join(CHECKIN_KINDS) + ')$'

# How the code was read. The client reports it and the server records it; §LOC-004's own first
# Behaviour bullet is the scan, and §SENS-010's coverage gate is where the reading itself lives.
CHECKIN_METHODS: tuple[str, ...] = ('qr', 'nfc', 'manual')
CHECKIN_METHOD_PATTERN = '^(' + '|'.join(CHECKIN_METHODS) + ')$'

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


class LocationShare(BaseModel):
	"""§LOC-003's "report shared with health authorities through a secure channel": the envelope.

	`sealed` is a `Sealed.to_blob()` string, so the geohashed report is ciphertext before it leaves
	the process. It is sealed under the *application-layer* key, which `CryptoService.has_app_layer`
	describes as the layer contact lists **and location history** get — the same standard §COM-103's
	contact list meets, and the same reason: the at-rest key is the one an operator holds, so a share
	sealed under it is one the operator could read without being the recipient.

	`places` is the count of geohashed places, not the places. The report's own `places` list is what
	a person reads on their screen; what leaves is the cell set, and the count is the only thing the
	receipt can say without repeating it.
	"""
	model_config = MODEL_CONFIG
	share_id: str = Field(default_factory=lambda: 'LSH-' + uuid7str().replace('-', '').upper()[:8])
	subject_ref: str
	with_who: str = Field(min_length=2, max_length=120)
	sealed: str = Field(min_length=1)
	places: int = Field(ge=0)
	shared_at_ms: int
	algorithm: str = 'AES-256-GCM'


class LocationShareReceipt(BaseModel):
	"""What actually happened to the report: sent, or sealed and held for when the channel is up.

	`delivered` is read off the transport rather than off the request. The route used to take a
	`share` flag and compose "Report generated and shared as coarse locations only." from it, with a
	log line behind it and nothing on the wire — so the sentence asserted a disclosure that had not
	happened and the §SEC-006 dashboard, which reads the share ledger, would answer "nothing shared"
	about a report the person believed the county held.
	"""
	model_config = MODEL_CONFIG
	share_id: str
	with_who: str
	places: int
	shared_at_ms: int
	algorithm: str
	delivered: bool
	message: str


# --- LOC-004 QR / NFC check-in -----------------------------------------------------------

class CheckInPoint(BaseModel):
	model_config = MODEL_CONFIG
	point_id: str
	kind: str = Field(pattern=CHECKIN_KIND_PATTERN)
	label: str
	county: str
	token: str = Field(pattern=r'^[A-Z0-9]{6,16}$')


class CheckIn(BaseModel):
	"""One scan. `share_with_authority` is the person's *request* at the moment of the scan.

	It is not the answer to whether anything was sent, and reading it as one is the defect this
	unit closes: `CheckInReceipt.shared` was set from this field, so a check-in that was refused a
	standing consent still reported `shared: true`, and `CheckInAttendance.shared` read it back off
	the stored record months later. `synced` is the service's own outcome and is written by
	`check_in`; a caller that sets it has the value discarded, exactly as `SyncService.enqueue`
	discards a caller's `synced` on a `SyncOp`.
	"""

	model_config = MODEL_CONFIG
	checkin_id: str = Field(pattern=r'^CHK-[A-Z0-9]{8,}$')
	point_token: str = Field(pattern=r'^[A-Z0-9]{6,16}$')
	subject_ref: str
	method: str = Field(pattern=CHECKIN_METHOD_PATTERN)
	at_iso: str
	share_with_authority: bool = False
	synced: bool = False
	# The language the guidance and the receipt's sentence are served in. §ACC-002's rule applies to
	# a person standing at a gate as much as to a triage answer, and a receipt built with no `lang`
	# was English guidance on a screen the person may not read.
	lang: str = 'en'


class CheckInReceipt(BaseModel):
	"""What the scan did, as two facts that are not the same fact.

	`logged_locally` is §16.1 principle 1 — the local write always succeeds, and it is the whole of
	the feature when the person has not asked to share. `synced` is the second half of §LOC-004's
	third Behaviour bullet, "synced with consent", and it is read off the sync queue rather than off
	the request. The three ways it can be False are three different things a person should be told
	apart, which is what `message` carries: not asked, asked and no standing consent, and no queue
	to hand it to. `synced_with` names the dataset it went out under, so a client can tell a
	check-in that left from one that did not without parsing prose.
	"""

	model_config = MODEL_CONFIG
	checkin_id: str
	point_label: str
	guidance: str
	logged_locally: bool
	synced: bool
	synced_with: str | None = None
	message: str = Field(min_length=1)
	served_in: str = 'en'


class CheckInAttendance(BaseModel):
	"""One check-in, joined to the point it names and counted against the person's own record.

	`CheckIn` carries a `point_token` and nothing else about the place: a receipt names the label
	once, at the moment of the scan, and after that the token is a string that resolves to nothing a
	reader can act on. §LOC-004's fourth Behaviour bullet is that check-ins are *used* — attendance
	is the join this record is, and it is a join nobody could make from the stored shape.

	`visit_no` is 1-based over the person's own check-ins *at this point*, in time order, so three
	scans at one school screening point are one place attended three times rather than three places.
	`day` is the date half of `at_iso`, which is the field the window arithmetic reads; the instant
	is carried too, because a check-in is a moment and the day is a reading of it.
	"""

	model_config = MODEL_CONFIG
	checkin_id: str
	point_id: str
	point_label: str
	kind: str
	county: str
	at_iso: str
	day: str
	visit_no: int = Field(ge=1)
	method: str
	synced: bool


class FollowUpStep(BaseModel):
	"""One scheduled ask, and whether it is behind the clock, on it, or still ahead.

	`due` and `past` are two booleans rather than one tri-state string because "today" is the case
	the screen acts on and both neighbours are different from it: a step that is `due and not past`
	is the one being asked now. Neither reads an answer — no answer is stored on this path. The
	answer lives on §LOC-005's traveller route, where `PostArrivalReport` is filed against a day;
	reporting a check-in step as "missed" would be this code inventing a prompt nobody sent.
	"""

	model_config = MODEL_CONFIG
	day: int = Field(ge=1)
	due_iso: str
	due: bool
	past: bool
	question: str


class ExposureWindow(BaseModel):
	"""The 21-day window a check-in opens, and how far into it the caller's clock is.

	The window is derived from `CheckIn.at_iso` and not stored: a stored end date is wrong the day
	after it is written, and §LOC-004's whole point is that the check-in is the timestamp.

	`elapsed_days` is clamped to the window, so a check-in eight months old reports `21` and not
	`240`. The clamp is the window's own arithmetic — a day past the end is not a day of it — and
	`remaining_days` is `0` for every one of them, which is the fact that matters.
	"""

	model_config = MODEL_CONFIG
	opened_iso: str
	closes_iso: str
	window_days: int = Field(ge=1, le=LOCATION_WINDOW_MAX_DAYS)
	elapsed_days: int = Field(ge=0)
	remaining_days: int = Field(ge=0)
	open: bool
	note: str


class CheckInFollowUp(BaseModel):
	"""What §LOC-004's fourth bullet asks for, derived from the check-ins on file.

	Three answers, and they are three because the bullet names three uses: which points the person
	attended and when (`attendance`), which symptom questions are owed (`schedule`), and whether the
	21-day exposure window from the most recent check-in is still open (`window`).

	`attendance: null` and `window: null` are not "nothing happened" — they are "there is no
	check-in to derive from", and `note` says so in words. A person with no check-ins is owed the
	fact that the app is not following anything up, not an empty list that reads like a clean
	record, which is the same distinction `DoseResult.unknown` draws.

	`served_in` is the language the strings were actually built in, and it is the same rule
	`TriageResult.served_in` follows: `answerable` accepts every language §ACC-002 lists and falls
	back to English where there is no table, and a fallback nobody is told about is a Dholuo speaker
	reading English believing it is Dholuo. `lang` is the request; this is the answer.
	"""

	model_config = MODEL_CONFIG
	subject_ref: str
	attendance: list[CheckInAttendance] | None
	schedule: list[FollowUpStep]
	window: ExposureWindow | None
	points_attended: int = Field(ge=0)
	checkins: int = Field(ge=0)
	next_due_iso: str | None
	served_in: str
	note: str


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


# --- §8.6 LOC-001 zone entry/exit, and the privacy switch over it -------------------------
#
# §LOC-001's Tier 1 behaviour is "static advisory zones ... with opt-in alerts", its Tier 4 behaviour
# is "alert on entry **and exit**", and its Privacy line is "Location processed on-device. Only
# entry/exit events logged, and only with consent." Three facts, and the repo carried one of them:
# `Geofence` existed and nothing derived an entry or an exit from a position, so the "dynamic
# geofences ... alert on entry and exit" half of the section had no carrier at all.
#
# The switch is a *stored decision* and not a request parameter, for §MON-009's reason: a client that
# sent `log_entries=true` would be asserting the person's consent on their behalf, and the one thing
# a consent flag may never be is a value the caller chooses. `alerts_enabled` is what a person set,
# and `log_entries` is what the code may therefore do — derived, never accepted.

class ZoneWatch(BaseModel):
	"""One person's geofence state: whether alerts are on, and the zones they were last seen inside.

	`inside` is what makes an entry an *event* rather than a reading. Without it every position inside
	a zone is an entry, so a person walking across a 5 km zone is alerted on every GPS fix — which is
	how an alert becomes something people turn off.
	"""
	model_config = MODEL_CONFIG
	subject_ref: str
	alerts_enabled: bool = False
	# The zones the last check found this person inside. Coordinates are not kept: §LOC-001's Privacy
	# line is that location is processed on-device, so what is stored is *which zones* were crossed
	# and not where the person was when they crossed them.
	inside: list[str] = Field(default_factory=list)


class ZoneEvent(BaseModel):
	"""An entry or an exit, and the sentence the client shows for it.

	§LOC-001's Alert content is served as `alert` — the section's own sentence with the specific
	location named — and `message` is the entry/exit frame around it. Both are strings rather than a
	structured alert for §5.4's reason: this answer reaches USSD and SMS as well as the app, and two
	of the three cannot render a structure.

	`logged` is the Privacy line made checkable. `False` means nothing about the crossing was written
	down, which is what a person who turned alerts off is owed; a client that showed "your entry was
	recorded" on a `False` would be telling them the opposite of what the code did.
	"""
	model_config = MODEL_CONFIG
	event: str = Field(pattern=r'^(entry|exit)$')
	geofence_id: str
	place_label: str = ''
	county: str = ''
	risk_type: str = Field(pattern=r'^(general|outbreak)$')
	alert_level: str = Field(pattern=r'^(low|medium|high)$')
	alert: str
	message: str
	# §LOC-001's Privacy line said to the person. `logged` is the fact and this is the sentence: a
	# client that only had the boolean would write the explanation itself, and the explanation is the
	# part a person reads.
	privacy_note: str
	logged: bool
	lang: str = 'en'
	# §LOC-001's 21-day window, named on the exit as well as the entry: the sentence the spec prints
	# asks for 21 days of symptom monitoring, and leaving the zone is not the end of that window.
	symptom_watch_days: int = Field(default=21, ge=1, le=28)
