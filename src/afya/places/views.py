"""Unified POI model (OSM-normalised) + direction guidance — 'how do I get there?'
Map UI opens the platform maps app (Apple/Google) via deep link; no embedded SDK dependency.
"""
from enum import Enum

from afya.facilities.service import haversine_km

from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class PlaceKind(str, Enum):
	pharmacy = 'pharmacy'
	clinic = 'clinic'
	hospital = 'hospital'
	school = 'school'
	treatment_unit = 'treatment_unit'
	testing_site = 'testing_site'
	vaccination_point = 'vaccination_point'
	water_point = 'water_point'


class TestType(str, Enum):
	"""§FND-003's seven "Test types (context-dependent)", closed.

	The section prints seven and `TestOffering.name` was free text, so the filter matched a
	substring and the seven the section names had no vocabulary behind them: a deployment that wrote
	"RDT" or "malaria rapid test" was offering a test the finder could not recognise, and the
	screen's filter chips could not be generated from the spec at all. A closed set makes the seven
	the section prints the seven the filter offers.

	`general_lab` is the seventh and is deliberately broad — the section's own wording is "General
	laboratory panels", which is what a facility offers when it does not specialise.
	"""

	malaria_rdt_microscopy = 'malaria_rdt_microscopy'
	typhoid = 'typhoid'
	hiv = 'hiv'
	tb = 'tb'
	covid19 = 'covid19'
	ebola = 'ebola'
	general_lab = 'general_lab'


class TestOffering(BaseModel):
	"""One test a facility does, and the three things §FND-003 asks a person to filter on.

	The section's Features are "Filter by test, cost, hours, results turnaround". A filter needs a
	field to filter on, and `Place` carried none of the three: it is an OSM-normalised POI, and OSM
	knows a clinic's name and position, not what it tests for or what it charges. These are facts a
	county health office publishes, so they are a list a deployment posts rather than something
	inferred from `opening_hours`.

	`cost_kes` and `turnaround_hours` are `int | None` rather than defaulted to 0, for the reason
	`EmergencyCard.organ_donor` is tri-state: "this test is free" and "nobody has told us what it
	costs" are different answers, and a `0` default answers the second as the first on the screen
	someone uses to decide whether they can afford to get tested.

	`test_type` is §FND-003's own vocabulary and `name` stays free text for what the facility calls
	it: the type is what the filter matches and the name is what the screen shows.
	"""

	model_config = MODEL_CONFIG
	# pytest collects any class whose name starts with `Test`, and this one is a model: without this
	# the import is a PytestCollectionWarning on every run of the suite that touches `places`.
	__test__ = False
	name: str = Field(min_length=1)
	test_type: TestType | None = None
	cost_kes: int | None = Field(default=None, ge=0, le=1_000_000)
	turnaround_hours: int | None = Field(default=None, ge=0, le=8760)


class VaccineOffering(BaseModel):
	"""One vaccine a point offers, with §FND-005's four filters.

	"Filter by vaccine, age eligibility, cost (usually free), hours, whether walk-in or appointment."
	`walk_in` is `bool | None` for the same tri-state reason: "appointment only" and "we were not
	told" send a person to a clinic on different days, and a defaulted `False` collapses them.

	Age bounds are in months so one pair covers both the infant schedule and school-age campaigns;
	`min_age_months=None` means no lower bound is published, which is not the same as zero.
	"""

	model_config = MODEL_CONFIG
	name: str = Field(min_length=1)
	cost_kes: int | None = Field(default=None, ge=0, le=1_000_000)
	min_age_months: int | None = Field(default=None, ge=0, le=1200)
	max_age_months: int | None = Field(default=None, ge=0, le=1200)
	walk_in: bool | None = None

	def model_post_init(self, _context: object) -> None:
		assert self.min_age_months is None or self.max_age_months is None \
			or self.min_age_months <= self.max_age_months, \
			f'{self.name}: an age band that excludes everyone is not a band'


class Place(BaseModel):
	model_config = MODEL_CONFIG
	osm_id: str = Field(pattern=r'^(N|W|R)\d+$')
	kind: PlaceKind
	name: str
	lat: float = Field(ge=-5, le=6)
	lon: float = Field(ge=33, le=43)
	county: str | None = None
	opening_hours: str | None = None
	phone: str | None = None
	website: str | None = None
	# §FND-004's "Whether they accept SHA". Tri-state, for the reason §FND-001's identical field is:
	# "this chemist takes my insurance" and "nobody has filed it" are different answers, and a
	# defaulted `False` would tell a person their cover is refused when the row is simply empty.
	accepts_sha: bool | None = None
	# §FND-003's and §FND-005's filter dimensions. Empty means "nothing published", which is what a
	# freshly imported OSM row is — the finder then reports no filter rather than pretending the
	# facility does no tests, and a deployment fills these from the county's own service list.
	tests: list[TestOffering] = []
	vaccines: list[VaccineOffering] = []


class Directions(BaseModel):
	model_config = MODEL_CONFIG
	place_id: str
	place_name: str
	distance_km: float
	bearing_deg: int
	walk_minutes: int
	guidance: str
	apple_maps_url: str
	google_maps_url: str


class PlacesService:
	def __init__(self) -> None:
		self._places: dict[str, Place] = {}
		assert self._places == {}

	async def upsert(self, p: Place) -> int:
		assert p.osm_id, 'osm id required'
		self._places[p.osm_id] = p
		return len(self._places)

	def nearest(self, lat: float, lon: float, kinds: set[PlaceKind] | None = None, limit: int = 5) -> list[tuple[Place, float]]:
		from afya.facilities.service import haversine_km
		pool = [p for p in self._places.values() if not kinds or p.kind in kinds]
		assert pool, 'no places imported yet'
		return sorted(((p, haversine_km(lat, lon, p.lat, p.lon)) for p in pool), key=lambda x: x[1])[:limit]

	def find(
		self, lat: float, lon: float, kinds: set[PlaceKind] | None = None, limit: int = 5,
		test: str | None = None, vaccine: str | None = None, max_cost_kes: int | None = None,
		age_months: int | None = None, walk_in_only: bool = False, max_turnaround_hours: int | None = None,
		test_type: TestType | None = None, accepts_sha: bool | None = None,
	) -> tuple[list[tuple[Place, float]], list[str]]:
		"""§FND-003's and §FND-005's finders, with their own filter dimensions applied.

		Both sections' Features cells are filter lists, and a filter that is not applied is a screen
		that shows every facility and calls the list filtered. Each argument here is one of those
		dimensions; `test`/`test_type`/`max_turnaround_hours` are §FND-003's, `vaccine`/`age_months`/
		`walk_in_only` are §FND-005's, and `accepts_sha` is §FND-004's — they compose because all
		three are the same search over the same pool.

		`test` matches the free-text `name` and `test_type` matches the closed vocabulary the section
		prints; both exist because a person searching "RDT" and a filter chip generated from the spec
		are different queries over the same offering.

		The second return value is the finding rather than a nicety: `unanswered` names the dimensions
		the *data* cannot answer — a facility with no `tests` published is not one that does no tests,
		and filtering it out would turn "nobody has filled this in" into "this clinic does not test for
		HIV". The filter is applied only over the places that published the dimension, and the
		dimensions nothing published are reported so the screen can say "cost unknown" rather than
		showing a shorter list that reads as an answer.

		A `max_cost_kes` filter keeps a place whose offering has `cost_kes is None`: unknown cost is
		not a cost above the ceiling, and dropping it would hide the free public clinic whose row
		nobody has priced. `walk_in_only` is the one filter that *does* exclude on absence, because
		§FND-005 asks whether a point takes walk-ins and a person turning up without an appointment
		needs a yes, not a maybe.
		"""
		found, had_pool = self._nearest_or_empty(lat, lon, kinds, len(self._places) or 1)
		if not had_pool:
			# No places at all is not a dimension the data failed to answer — there is no data, and
			# "we have nothing imported" is a different sentence from "nobody has published a test
			# list for these facilities". Reporting `unanswered` here would put a filter defect on the
			# screen of a deployment whose import simply has not run.
			return [], []
		unanswered: list[str] = []
		if test is not None:
			if not any(p.tests for p, _ in found):
				unanswered.append('test')
			else:
				wanted = test.strip().lower()
				found = [(p, km) for p, km in found
					if any(wanted in t.name.lower() for t in p.tests)]
		if test_type is not None:
			if not any(t.test_type is not None for p, _ in found for t in p.tests):
				unanswered.append('test type')
			else:
				found = [(p, km) for p, km in found
					if any(t.test_type is test_type for t in p.tests)]
		if accepts_sha is not None:
			if not any(p.accepts_sha is not None for p, _ in found):
				unanswered.append('SHA acceptance')
			else:
				# An unpublished row stays: "nobody filed it" is not "they refuse your cover".
				found = [(p, km) for p, km in found
					if p.accepts_sha is None or p.accepts_sha is accepts_sha]
		if max_turnaround_hours is not None:
			if not any(t.turnaround_hours is not None for p, _ in found for t in p.tests):
				unanswered.append('results turnaround')
			else:
				found = [(p, km) for p, km in found if any(
					t.turnaround_hours is not None and t.turnaround_hours <= max_turnaround_hours
					for t in p.tests)]
		if vaccine is not None:
			if not any(p.vaccines for p, _ in found):
				unanswered.append('vaccine')
			else:
				wanted = vaccine.strip().lower()
				found = [(p, km) for p, km in found
					if any(wanted in v.name.lower() for v in p.vaccines)]
		if age_months is not None:
			if not any(v.min_age_months is not None or v.max_age_months is not None
					for p, _ in found for v in p.vaccines):
				unanswered.append('age eligibility')
			else:
				found = [(p, km) for p, km in found if any(
					(v.min_age_months is None or age_months >= v.min_age_months)
					and (v.max_age_months is None or age_months <= v.max_age_months)
					for v in p.vaccines)]
		if max_cost_kes is not None:
			offerings = [(t.cost_kes, None) for p, _ in found for t in p.tests]
			offerings += [(v.cost_kes, None) for p, _ in found for v in p.vaccines]
			if not any(c is not None for c, _ in offerings):
				unanswered.append('cost')
			else:
				def _affordable(p: Place) -> bool:
					"""A place with nothing priced stays in the list. It has not said it is expensive —
					it has said nothing, and a cost ceiling that dropped every unpriced facility would
					hide the public clinic whose row nobody has filled in, which is the one a person
					looking for the cheapest option most needs to see."""
					costs = [t.cost_kes for t in p.tests] + [v.cost_kes for v in p.vaccines]
					return not costs or any(c is None or c <= max_cost_kes for c in costs)
				found = [(p, km) for p, km in found if _affordable(p)]
		if walk_in_only:
			if not any(v.walk_in is not None for p, _ in found for v in p.vaccines):
				unanswered.append('whether walk-in or appointment')
			else:
				found = [(p, km) for p, km in found if any(v.walk_in is True for v in p.vaccines)]
		return found[:limit], unanswered

	def _nearest_or_empty(
		self, lat: float, lon: float, kinds: set[PlaceKind] | None, limit: int,
	) -> tuple[list[tuple[Place, float]], bool]:
		"""`nearest` with the empty pool answered as an empty list. A locator whose import has not run
		has no answer, and `nearest`'s assert would surface as a 500 on the screen a person opens when
		they are unwell."""
		try:
			return self.nearest(lat, lon, kinds, limit), True
		except AssertionError:
			return [], False

	def count(self) -> int:
		return len(self._places)

	@staticmethod
	def directions(place: Place, lat: float, lon: float) -> Directions:
		import math
		dist = haversine_km(lat, lon, place.lat, place.lon)
		dy = 110_574.0 * (place.lat - lat)
		dx = 111_320.0 * (place.lon - lon) * math.cos(math.radians(lat))
		bearing = int(((math.degrees(math.atan2(dx, dy)) % 360) // 5) * 5)
		cardinal = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][min(7, (bearing + 22) // 45 % 8)]
		walk = int(dist * 12)  # ~12 min per km average
		return Directions(
			place_id=place.osm_id, place_name=place.name,
			distance_km=round(dist, 2), bearing_deg=bearing, walk_minutes=walk,
			guidance=f'{place.name} is {dist:.1f} km {cardinal} of you (~{walk} min walk). Follow the map link for step-by-step navigation.',
			apple_maps_url=f'https://maps.apple.com/?daddr={place.lat},{place.lon}&dirflg=w',
			google_maps_url=f'https://www.google.com/maps/dir/?api=1&destination={place.lat},{place.lon}',
		)
