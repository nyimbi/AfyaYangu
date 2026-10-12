"""Facility domain models (spec §8.2 FND-001..006, §18.5 MoHF)."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class FacilityKind(str, Enum):
	treatment_unit = 'treatment_unit'
	ed = 'ed'
	testing_site = 'testing_site'
	pharmacy = 'pharmacy'
	vaccination_point = 'vaccination_point'


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
	"""

	model_config = MODEL_CONFIG
	text: str = Field(min_length=1, max_length=280)
	reporter_ref: str | None = None


class FacilityReport(BaseModel):
	"""§FND-001's "Recent user reports ('no malaria tests today,' 'long queue')".

	The section's own two examples are stock and queue facts, so this is deliberately free text
	rather than an enum: a crowdsourced field that only accepts the two shapes the spec happened to
	print would reject the third thing a person needs to say. `reporter_ref` is a pseudonymous
	subject reference and never a name — the feed is shown on a screen anyone can open.
	"""

	model_config = MODEL_CONFIG
	facility_id: str
	text: str = Field(min_length=1, max_length=280)
	reporter_ref: str | None = None


class Booking(BaseModel):
	model_config = MODEL_CONFIG
	booking_id: str = Field(pattern=r'^BOOK-[A-Z0-9]{6,}$')
	facility_id: str
	slot_iso: str
	queue_position: int = Field(ge=1, le=500)