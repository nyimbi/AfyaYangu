"""Facility domain models (spec §8.2 FND-001..006, §18.5 MoHF)."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, computed_field

from afya.derived import DerivedFields
from afya.ids import ref8

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# §FND-006's "Reminder notifications": how long before an appointment the reminder is due.
#
# A constant rather than a field, and in this module rather than the service, because the reminder
# time is *derived from the slot* and the derivation lives on `Booking`. A lead carried per booking
# would be a second copy of a policy the facility sets, and the copy that drifts is the one already
# written into somebody's appointment.
REMINDER_LEAD_HOURS = 24


class FacilityKind(str, Enum):
	treatment_unit = 'treatment_unit'
	ed = 'ed'
	testing_site = 'testing_site'
	pharmacy = 'pharmacy'
	vaccination_point = 'vaccination_point'
	# §MON-008's "therapeutic feeding programme locations". The kind is here rather than in
	# `ServiceOffered` because that enum's docstring is §FND-001's own printed list of seven, closed,
	# and a nutrition programme is not one of the seven — widening it would make the filter offer a
	# service the section never printed. `PlaceKind` was the audit row's other candidate and could
	# not take it: OpenStreetMap has no tag for a therapeutic feeding centre, so a place vocabulary
	# could not be sourced (see `sources/kenya-imam-guidelines/`).
	therapeutic_feeding = 'therapeutic_feeding'


class FacilityLevel(str, Enum):
	"""§FND-001's five-rung ladder, printed in the order the section prints it.

	`FacilityKind` answers *what service* a facility offers and is orthogonal to this: a dispensary
	and a national referral hospital are both `treatment_unit`, so the kind cannot render the
	"Name and level" line the section asks for and cannot rank a referral chain. The ladder is
	ordered because §FND-002's escalation ("nearest facility with ICU") is a question about going
	*up* it, and an unordered set of five strings cannot answer that.
	"""

	dispensary = 'dispensary'
	health_centre = 'health_centre'
	sub_county_hospital = 'sub_county_hospital'
	county_referral = 'county_referral'
	national_referral = 'national_referral'


class ServiceOffered(str, Enum):
	"""§FND-001's services list, closed.

	The section prints seven in a parenthetical — "maternal, child, HIV, TB, malaria, emergency,
	isolation capacity" — and the filter is "Filter by service". A filter needs a closed vocabulary:
	an open string means the screen offers a text box and every deployment spells "HIV" differently.
	"""

	maternal = 'maternal'
	child = 'child'
	hiv = 'hiv'
	tb = 'tb'
	malaria = 'malaria'
	emergency = 'emergency'
	isolation_capacity = 'isolation_capacity'


class CostBand(str, Enum):
	"""§FND-001's "Approximate cost band" and §FND-004's pricing signal.

	A band rather than a figure: the section says *approximate*, and a facility that publishes
	"KES 500–1000" has not published a price. `free` is its own member because the public clinic a
	person is looking for is the one whose band is `free`, and folding it into `low` would hide it.
	"""

	free = 'free'
	low = 'low'
	medium = 'medium'
	high = 'high'


class Facility(BaseModel):
	"""One facility, carrying §FND-001's "Data displayed per facility" list.

	Every field the section prints is here, and each is optional because a row imported from the
	Kenya Master Health Facility List carries a name, a level and a position and nothing else —
	"nobody has published this" and "this facility does not offer it" are different answers, and a
	defaulted `False` on `accepts_sha` would tell a person that a facility refuses their insurance
	when the truth is that the county has not filed the row yet.
	"""

	model_config = MODEL_CONFIG
	facility_id: str
	name: str
	kind: FacilityKind
	county: str
	lat: float = Field(ge=-5, le=6)
	lon: float = Field(ge=33, le=43)
	open_now: bool = True
	hours24: bool = False
	wait_minutes: int | None = Field(default=None, ge=0, le=600)
	ed_status: str | None = None
	crowdload: int = Field(default=0, ge=0, le=100)
	# §FND-001 "Name and level". `None` is a row whose level nobody filed.
	level: FacilityLevel | None = None
	# §FND-001 "Services offered". Empty is "nothing published", not "offers nothing".
	services: list[ServiceOffered] = []
	# §FND-001 "SHA/NHIF acceptance — critical for cost anxiety" and §FND-004 "Whether they accept
	# SHA". Tri-state for the reason the section gives: a person deciding whether they can afford
	# care is misled by either default.
	accepts_sha: bool | None = None
	# §FND-001 "Approximate cost band".
	cost_band: CostBand | None = None
	# §FND-001 "Whether it is a designated Ebola screening or isolation facility (Tier 4)".
	ebola_screening: bool = False
	isolation_beds: int | None = Field(default=None, ge=0, le=2000)
	# §FND-002's emergency capacity, which is what the ED screen reads.
	icu_beds: int | None = Field(default=None, ge=0, le=2000)
	ambulances: int | None = Field(default=None, ge=0, le=500)
	trauma_capable: bool | None = None
	# §FND-002's "Offline: Cached, with timestamp visible" — the stamp is the field, not a log line.
	reported_at_iso: str | None = None

	def has_service(self, service: ServiceOffered) -> bool:
		return service in self.services


class NearestRequest(BaseModel):
	"""§FND-001's finder: the search box and the four filters, on one request.

	`query` is "Search by area name or code" — a free-text box that matches a facility name, a
	county, or the MoHF code, because the section offers one box and a person types whichever of the
	three they know. The four filters are the section's own list and they compose, so a request can
	ask for "a county referral hospital that takes SHA and offers maternity".
	"""

	model_config = MODEL_CONFIG
	lat: float = Field(ge=-5, le=6)
	lon: float = Field(ge=33, le=43)
	kind: FacilityKind | None = None
	limit: int = Field(default=3, ge=1, le=20)
	# §FND-001 "Search by area name or code".
	query: str | None = None
	# §AI-003's "facility-finder searches for a specific symptom", counted by locality. `query` is
	# the symptom text the bullet names; this is the locality it is counted in.
	county: str | None = None
	# §FND-001 "Filter by service, level, cost, SHA acceptance".
	service: ServiceOffered | None = None
	level: FacilityLevel | None = None
	max_cost_band: CostBand | None = None
	accepts_sha: bool | None = None
	# §FND-002's filters, which are the same finder over the same pool.
	min_icu_beds: int | None = Field(default=None, ge=1, le=2000)
	needs_ambulance: bool = False
	needs_trauma: bool = False
	needs_isolation: bool = False
	# §FND-001 "Offline mode: caches facilities within 50 km of the user's home area". The radius is
	# a parameter rather than a constant so the offline bundle and the live finder can differ.
	within_km: float | None = Field(default=None, gt=0, le=500)


class OfflineFacility(BaseModel):
	"""One row of §FND-001's offline bundle: the facility and how far it is from home.

	A model rather than a dict because the bundle is what the client caches, and a dict is a shape
	nothing validates — the `km` a screen sorts on and the `facility` it renders are both fields a
	reader has to guess the names of.
	"""

	model_config = MODEL_CONFIG
	facility: Facility
	km: float = Field(ge=0)


class FacilityReportRequest(BaseModel):
	"""What a client posts to the report route. The facility id is in the path, so it is not repeated
	in the body — a body that could carry a different id from the path is a mismatch nothing checks.

	**There is no `reporter_ref` field, and its absence is the fix.** It was here as an optional
	string, so the route published whatever the caller typed on a public feed — including somebody
	else's subject reference, which keys every personal route in the app. The reporter is now the
	caller's own token, read by the route; a body field for it could only ever be ignored or
	believed, and believing it is the defect.
	"""

	model_config = MODEL_CONFIG
	text: str = Field(min_length=1, max_length=280)


class FacilityReport(BaseModel):
	"""§FND-001's "Recent user reports ('no malaria tests today,' 'long queue')".

	The section's own two examples are stock and queue facts, so this is deliberately free text
	rather than an enum: a crowdsourced field that only accepts the two shapes the spec happened to
	print would reject the third thing a person needs to say.

	`reporter_ref` is a §SEC-004 pseudonymous *handle* (`Tembo-a1b2`), not the subject reference it
	was named after. The field name is kept because it is a served payload a client already reads,
	but what it carries changed: the subject reference is the lookup key for a person's records, and
	this feed is on a screen anyone can open. A report from a caller with no token carries `None` —
	anonymous rather than absent, which is §FND-001's ordinary case.
	"""

	model_config = MODEL_CONFIG
	facility_id: str
	text: str = Field(min_length=1, max_length=280)
	reporter_ref: str | None = None


class BookingRequest(BaseModel):
	"""What a caller asks for: which facility, and when.

	`queue_position` is not here. It is the answer to the question "where am I in the queue", and it
	was a required field on the request — so a client had to state its own place before being told
	it. `booking_id` is minted by the model when the caller omits it, so a form that does not offer
	one is complete.
	"""

	model_config = MODEL_CONFIG
	booking_id: str = Field(default_factory=lambda: 'BOOK-' + ref8())
	slot_iso: str
	# The route takes the facility in its path, so a body copy would be a second spelling of one
	# fact. Optional and echoed into the result, which is where a client reads it back.
	facility_id: str | None = None


class Booking(BaseModel):
	"""The booking as it stands: the reference, the slot, and the place in the queue."""

	model_config = MODEL_CONFIG
	booking_id: str = Field(default_factory=lambda: 'BOOK-' + ref8())
	facility_id: str
	slot_iso: str
	queue_position: int = Field(ge=1, le=500)
	# §FND-006's "Book, reschedule, cancel" needs somebody the booking belongs to: without it a
	# cancel is a delete keyed on a short, guessable reference, and a reschedule is the same with a
	# new time on it. The owner is taken from the token on the route, never from the body, so the
	# field is `None` only for a booking filed before an owner was recorded.
	subject_ref: str | None = None
	# `cancelled` is a state rather than a deletion because §FND-006's queue is a *position*: a
	# booking that vanished would silently move everyone behind it, and "where did my place go" is
	# not a question a clinic can answer after the row is gone.
	cancelled: bool = False

	@computed_field  # type: ignore[prop-decorator]
	@property
	def reminder_due_iso(self) -> str:
		"""§FND-006's "Reminder notifications", as the instant the device schedules one for.

		Derived from the slot rather than stored, so the lead cannot drift from the appointment it
		belongs to and a reschedule cannot leave a reminder pointing at the old time. Not a
		notification queue: on §ACC-004's reasoning — the same shape as §MON-001's missed-dose alert
		and §REC-004's contraception reminder — the server states when the reminder is due and the
		device holds it, so the reminder fires with no network and §ACC-001's offline mode keeps
		working.

		A cancelled booking carries no reminder, because a notification for an appointment the person
		has already released is worse than none: it sends them to a clinic for nothing.
		"""
		if self.cancelled:
			return ''
		from datetime import datetime, timedelta
		try:
			at = datetime.fromisoformat(self.slot_iso)
		except ValueError:
			return ''
		return (at - timedelta(hours=REMINDER_LEAD_HOURS)).isoformat()


class FacilitySlot(BaseModel):
	"""One of §FND-006's available slots.

	`capacity` and `booked` rather than a boolean `taken`: a screen that offered only free times
	would tell a person nothing about whether the clinic is full today or closed, and "nothing
	available" is the answer they most need before they travel. A facility that runs a queue rather
	than appointments publishes eight places at nine o'clock instead of eight rows.
	"""

	model_config = MODEL_CONFIG
	facility_id: str
	slot_iso: str
	capacity: int = Field(default=1, ge=1, le=200)
	booked: int = Field(default=0, ge=0, le=200)

	def model_post_init(self, _context: object) -> None:
		assert self.booked <= self.capacity, (
			f'{self.slot_iso} at {self.facility_id} reports {self.booked} booked into a slot of '
			f'{self.capacity} — a clinic cannot have filled more places than it offers'
		)

	@computed_field  # type: ignore[prop-decorator]
	@property
	def free(self) -> int:
		"""Places left. Derived, so a slot cannot advertise places its bookings have taken."""
		return self.capacity - self.booked

	@property
	def open(self) -> bool:
		return self.free > 0


class SlotOffer(BaseModel):
	"""§FND-006's "participating facilities", as what one of them publishes.

	One slot per request rather than a whole day at once. A day is not a formula — a clinic that runs
	a queue at nine and appointments in the afternoon cannot be expressed as a start, an interval and
	a count — and a body carrying a list of *objects* is a shape the generic mobile form cannot
	render: its `list` field is comma-separated text. Publishing one slot per call is the shape a
	form can fill and the shape a facility actually decides in.
	"""

	model_config = MODEL_CONFIG
	facility_id: str | None = None
	slot_iso: str
	capacity: int = Field(default=1, ge=1, le=200)


class SlotSchedule(BaseModel):
	"""§FND-006's "View available slots": one facility's day, as the screen reads it.

	The day is echoed back because the answer is *about* a day — a client that asked for Tuesday and
	received a bare list cannot tell an empty Tuesday from a request that was answered with the wrong
	day's rows.
	"""

	model_config = MODEL_CONFIG
	facility_id: str
	day_iso: str
	slots: list[FacilitySlot] = []

	def model_post_init(self, _context: object) -> None:
		assert all(s.facility_id == self.facility_id for s in self.slots), (
			'a schedule carries one facility\'s day; a slot naming another clinic would be served '
			'under the wrong one'
		)
		assert all(s.slot_iso.startswith(self.day_iso) for s in self.slots), (
			'the schedule names a day and carries slots from another one'
		)

	@property
	def open_count(self) -> int:
		return sum(1 for s in self.slots if s.open)


class BookingChange(BaseModel):
	"""§FND-006's reschedule: the booking is in the path, the new slot is the body."""

	model_config = MODEL_CONFIG
	slot_iso: str