"""Environment & community-alert layer: water quality, air quality, flood→cholera risk, school closures, multi-disease outbreak alerts."""
from enum import Enum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from afya.ids import uuid7str

from afya.registry.diseases import DISEASES

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class AlertKind(str, Enum):
	"""§11.1's community alert kinds, with one `outbreak_*` member per §3.3 principle 12 disease.

	`outbreak_measles` and `outbreak_other` are new. Principle 12 names measles among the diseases
	Tier 4 activates for and ends "and the next unknown" — and this enum had neither, so the two
	diseases the section is most explicit about were the two an outbreak alert could not be raised
	for. `outbreak_other` is principle 12's own slot: the sixth outbreak is the one nobody has named
	yet, and an enum that cannot carry it can only ever alert on the five that already happened.

	The members are asserted against `registry.diseases` below, so a disease added there and not
	here fails at import rather than at the moment someone tries to alert on it.
	"""
	outbreak_evd = 'outbreak_evd'
	outbreak_cholera = 'outbreak_cholera'
	outbreak_rvf = 'outbreak_rvf'
	outbreak_mpox = 'outbreak_mpox'
	outbreak_measles = 'outbreak_measles'
	outbreak_malaria = 'outbreak_malaria'
	outbreak_dengue = 'outbreak_dengue'
	outbreak_other = 'outbreak_other'
	flood = 'flood'
	water_quality = 'water_quality'
	school_closure = 'school_closure'
	public_health_notice = 'public_health_notice'


# The `outbreak_*` members as wire kinds, and the disease each one is about. `outbreak_other` maps to
# the `other` slug, which is the slot principle 12 leaves for the next unknown — so the mapping is
# onto the whole vocabulary and not onto a subset of it.
OUTBREAK_KINDS: tuple[AlertKind, ...] = tuple(k for k in AlertKind if k.value.startswith('outbreak_'))
assert tuple(k.value.removeprefix('outbreak_') for k in OUTBREAK_KINDS) == DISEASES, \
	'every §3.3 principle 12 disease needs an outbreak alert kind, and no kind without a disease'


class CommunityAlert(BaseModel):
	model_config = MODEL_CONFIG
	alert_id: str = Field(default_factory=lambda: 'AL-' + uuid7str().replace('-', '').upper()[:8])
	kind: AlertKind
	county: str
	headline: str = Field(max_length=80)
	body: str = Field(max_length=400)
	issued_by: str = Field(pattern=r'^(MoH|PHEOC|County|KMD)$')
	multi_disease: bool = False

	@classmethod
	def outbreak(cls, alert_id: str, disease: AlertKind, county: str, headline: str, body: str) -> 'CommunityAlert':
		return cls(alert_id=alert_id, kind=disease, county=county, headline=headline, body=body, issued_by='PHEOC', multi_disease=disease is not AlertKind.outbreak_evd)


class WaterQuality(BaseModel):
	model_config = MODEL_CONFIG
	county: str
	ecoli_detected: bool
	turbidity_ntu: float = Field(ge=0, le=400)

	@property
	def unsafe(self) -> bool:
		return self.ecoli_detected or self.turbidity_ntu > 5.0


# --- §MON-005: treatment and safe storage ------------------------------------------------

class TreatmentMethod(str, Enum):
	"""The methods WHO's household-water-treatment brief names, as the closed set a notice offers.

	Boiling is the one the section's own bullet is about, and it is the one WHO calls "highly
	efficacious, killing human pathogens even in turbid water and at high altitude". The other three
	are the brief's own list — "chemical disinfection, filtration, flocculation/disinfection and
	heat" — because a notice that offered only boiling would send a household with no fuel to a
	method it cannot perform, and the brief's first limitation of boiling is exactly that: "high-cost
	use of carbon-based fuel sources".
	"""
	boil = 'boil'
	chlorinate = 'chlorinate'
	filter = 'filter'
	solar = 'solar'


# What each method requires, and what it does not achieve. The caveats are not decoration: WHO's
# brief states that boiling "does not provide any residual protection", and its Round II evaluation
# states that chlorine is "ineffective against most protozoan cysts including Cryptosporidium" and
# that chlorine disinfection needs an FRC of ">=0.5 mg/L after 30 minutes of contact time". A
# guidance string that named a method without its limit is the one a household follows into a
# treated-water supply that is still infectious.
TREATMENT_STEPS: dict[TreatmentMethod, tuple[str, ...]] = {
	TreatmentMethod.boil: (
		'Bring the water to a rolling boil — bubbling vigorously, not merely steaming.',
		'Take it off the heat and let it cool on its own; do not add ice.',
		'Pour it into a clean container with a lid and keep it covered.',
	),
	TreatmentMethod.chlorinate: (
		'Let the water settle, then pour off the clear water; chlorine works poorly in cloudy water.',
		'Add the dose your product states and stir.',
		'Wait 30 minutes before drinking.',
		'If the water is still cloudy after 30 minutes, the dose was not enough — treat it again.',
	),
	TreatmentMethod.filter: (
		'Pour the water through the filter and collect what comes out.',
		'Clean the filter on the schedule its maker states; a clogged filter stops working.',
	),
	TreatmentMethod.solar: (
		'Fill clear plastic bottles and lay them in full sun.',
		'Leave them for at least six hours in bright sun, or two days if the sky is overcast.',
	),
}

# What each method leaves behind. Read by the advisory rather than restated there, so a method
# cannot be recommended in one place and limited in another.
TREATMENT_CAVEATS: dict[TreatmentMethod, str] = {
	TreatmentMethod.boil: 'Boiling leaves no protection behind: water that is boiled and then stored badly is unsafe again.',
	TreatmentMethod.chlorinate: 'Chlorine does not kill the parasite that causes cryptosporidiosis. If diarrhoea is going round, boil as well.',
	TreatmentMethod.filter: 'A filter that is not cleaned stops working, and a cracked ceramic filter lets everything through.',
	TreatmentMethod.solar: 'Sunlight only works in clear bottles and clear weather, and it works slowly.',
}

# The turbidity above which a disinfectant needs the water clarifying first. WHO's Round II
# evaluation states the tested products "should only be used in nonturbid water (<5 NTU)" and that
# waters of higher turbidity need pretreatment "e.g. > 30 NTU ... by filtration or flocculation".
# Five rather than thirty: the products' own limit is 5, and the higher figure is the point at which
# WHO says pretreatment is required regardless of the product. The lower number is the one that
# keeps a notice from recommending a method outside the conditions it was tested in.
CHLORINE_TURBIDITY_LIMIT_NTU = 5.0


class TreatmentGuidance(BaseModel):
	"""§MON-005's "treatment guidance": how to make this water safe, given what is in it.

	Guidance and not a method name, because the choice is not free: chlorine is the wrong advice for
	cloudy water (WHO's Round II evaluation: products "should only be used in nonturbid water
	(<5 NTU)"), and it is the wrong advice where diarrhoea is going round, because it does not touch
	Cryptosporidium. So the model computes which methods the reading permits and returns those with
	their steps, rather than leaving a client to pick from a list of four.
	"""
	model_config = MODEL_CONFIG
	county: str
	methods: list[TreatmentMethod] = Field(min_length=1)
	steps: list[str] = Field(min_length=1)
	caveats: list[str] = Field(default_factory=list)

	@model_validator(mode='after')
	def _steps_match_the_methods(self) -> Self:
		"""The steps are the methods', in the methods' order, and a mismatch is a notice that names
		one method and describes another."""
		expected = [step for m in self.methods for step in TREATMENT_STEPS[m]]
		assert self.steps == expected, 'the steps do not belong to the methods being offered'
		return self


class StorageGuidance(BaseModel):
	"""§MON-005's "safe storage guidance": what to do with treated water before it is drunk.

	WHO's Round II evaluation is explicit that this is not a lesser bullet than treatment: a
	meta-analysis it cites found "filtration and integrated safe storage can reduce the risk of
	diarrhoeal disease by 61% compared to 51% from filtration only". Treated water that is poured
	back into the dirty container is untreated water, and the last step of the boiling brief is
	"protected from post-treatment recontamination during storage".
	"""
	model_config = MODEL_CONFIG
	county: str
	steps: list[str] = Field(min_length=1)
	# WHO's brief states the residual that protects stored household water: "an FRC concentration of
	# >=0.5 mg/L after 30 minutes of contact time, or >=0.2 mg/L in stored household water". It is
	# carried as the figure the notice is built from, and it is `None` when the notice is not about
	# chlorinated water — a number with no method behind it is a number a reader cannot act on.
	residual_chlorine_mg_l: float | None = Field(default=None, ge=0, le=5)


class TreatmentReminder(BaseModel):
	"""§MON-005's "point-of-use treatment reminders", as the instant the device schedules one for.

	The same shape as §MON-001's missed-dose alert and §FND-006's appointment reminder, on §ACC-004's
	reasoning: the server states *when* and the device holds it, so the reminder fires with no
	network. A reminder the server had to send would stop arriving exactly when the water went bad,
	which is during a flood.
	"""
	model_config = MODEL_CONFIG
	county: str
	due_iso: str
	method: TreatmentMethod
	message: str


class WaterSafety(BaseModel):
	"""§MON-005's reading, its advisory, and the three things to do about it — in one answer.

	The section's five Features are one decision for the household: is the water safe, and if not,
	how do I make it safe, how do I keep it safe, and when do I do it again. Serving the advisory
	alone was the state that left three of the five bullets with no carrier — a person was told the
	water was unsafe and given nothing to do next.
	"""
	model_config = MODEL_CONFIG
	county: str
	unsafe: bool
	advisory: str
	treatment: TreatmentGuidance
	# One per permitted method, in the same order as `treatment.methods`. A single storage block
	# would have to be the lead method's, and then the chlorine residual — the one figure only a
	# chlorinated supply can have — would be unreachable in every served payload, because the lead
	# method is always boiling. A field nothing can populate is not a feature.
	storage: list[StorageGuidance] = Field(min_length=1)
	# The reminder is about what *this household* does, so it is bound to one method: the lead. The
	# others are offered, not scheduled.
	reminder: TreatmentReminder | None = None

	@model_validator(mode='after')
	def _storage_matches_the_methods(self) -> Self:
		"""A storage block with no method behind it is advice a household cannot place, and the
		order is what tells a reader which block goes with which method."""
		assert len(self.storage) == len(self.treatment.methods), (
			f'{len(self.treatment.methods)} methods were offered with {len(self.storage)} storage '
			'blocks — a reader cannot tell which belongs to which'
		)
		assert all(sg.county == self.county for sg in self.storage), (
			'a storage block names another county'
		)
		return self


class AirQuality(BaseModel):
	model_config = MODEL_CONFIG
	county: str
	pm25: float = Field(ge=0, le=500)

	@property
	def band(self) -> str:
		"""The three responses the advisory has, read off the index rather than off the reading.

		The cuts used to be 35 and 55 µg/m³, which are the index's own category boundaries arrived at
		by a different route and *not quite* the same ones: the index crosses 100 at 35.5 and 150 at
		55.5, so a reading of 35.2 or 55.2 was served an "AIR ALERT" beside an index that said
		otherwise. Two answers to one question in one payload is the shape this removes.
		"""
		index = self.aqi
		return 'alert' if index > 150 else ('watch' if index > 100 else 'normal')

	@property
	def aqi(self) -> int:
		"""§MON-006's "AQI for user's location": the index a person reads, from the reading.

		The section names an *index*, and the tree had a raw PM2.5 figure with three ad-hoc band
		cuts at 35 and 55. Those cuts are the index's own category boundaries arrived at by a
		different route — 35.5 µg/m³ is where the index crosses 100 and 55.5 where it crosses 150 —
		so the bands were right and the number a person could compare against a news bulletin was
		missing. `aqi` is derived from the breakpoint table rather than the band being derived from
		the index, because the band is what the advisory already branched on and changing its
		arithmetic would change which advisory a reading gets.
		"""
		return pm25_aqi(self.pm25)


# --- §MON-006: the air quality index ---------------------------------------------------------

# The PM2.5 breakpoints, as `(concentration_low, concentration_high, aqi_low, aqi_high)` in µg/m³.
# Truncated to one decimal place on the way in, because the source's own worked example truncates
# before it looks the value up — a reading of 35.49 is in the 12.1-35.4 band, not the one above it,
# and interpolating on the untruncated figure puts it in the wrong category.
#
# The `(250.5, 500.4)` row carries the source's own footnote: it applies "if a different SHL for
# PM2.5 is promulgated", and the figure is not one of the four interim targets WHO sets. It is here
# because the index runs to 500 and a reading above 250.4 still needs an answer, and the code says
# so rather than leaving a hole a caller falls through.
PM25_BREAKPOINTS: tuple[tuple[float, float, int, int], ...] = (
	(0.0, 12.0, 0, 50),
	(12.1, 35.4, 51, 100),
	(35.5, 55.4, 101, 150),
	(55.5, 150.4, 151, 200),
	(150.5, 250.4, 201, 300),
	(250.5, 350.4, 301, 400),
	(350.5, 500.4, 401, 500),
)

# The index's own category names, as the ranges they cover. Separate from `AirQuality.band`, which
# is the three-way cut the advisory branches on: the index has six categories and the advisory has
# three responses, and collapsing them would lose the category a screen wants to print.
AQI_CATEGORIES: tuple[tuple[int, int, str], ...] = (
	(0, 50, 'good'),
	(51, 100, 'moderate'),
	(101, 150, 'unhealthy_for_sensitive_groups'),
	(151, 200, 'unhealthy'),
	(201, 300, 'very_unhealthy'),
	(301, 500, 'hazardous'),
)


def pm25_aqi(pm25: float) -> int:
	"""The index for a PM2.5 reading, by the source's own linear interpolation.

	Truncation before lookup is the source's, not a rounding convenience: its worked example
	truncates 0.07853333 to 0.078 before choosing a band, and the band boundaries are inclusive at
	the top — 35.4 is in one band and 35.5 in the next, with nothing between them. Interpolating on
	an untruncated value would put 35.45 in the band above the one it belongs to.
	"""
	value = int(pm25 * 10) / 10
	for low, high, aqi_low, aqi_high in PM25_BREAKPOINTS:
		if low <= value <= high:
			return round((aqi_high - aqi_low) / (high - low) * (value - low) + aqi_low)
	# Above the table's top. The index is capped at 500, and a reading past 500.4 is beyond what the
	# scale expresses — served as 500 rather than extrapolated, because an index of 900 is a number
	# no screen is designed for and no guidance is written against.
	return 500


class AirQualityReading(BaseModel):
	"""§MON-006's "AQI for user's location": the index, the category, and which groups it is about.

	`location` is carried because the section says "for user's location" and the reading had only a
	county: a county is tens of thousands of people, and a person deciding whether to walk to school
	this morning is asking about their own street. It is a place *name* and not a coordinate — §LOC-002
	keeps a person's position on their own device, and a server that resolved one would be holding it.
	"""
	model_config = MODEL_CONFIG
	county: str
	location: str
	pm25: float = Field(ge=0, le=500)
	aqi: int = Field(ge=0, le=500)
	category: str

	@model_validator(mode='after')
	def _category_matches_the_index(self) -> Self:
		"""A reading whose index says 180 and whose category says "moderate" is a screen that tells a
		person the air is fine while the number beside it says otherwise."""
		expected = next((name for low, high, name in AQI_CATEGORIES if low <= self.aqi <= high), None)
		assert expected == self.category, (
			f'an index of {self.aqi} is {expected}, not {self.category}'
		)
		return self

	@model_validator(mode='after')
	def _index_matches_the_reading(self) -> Self:
		"""The index is derived from the reading and not asserted alongside it, so a caller cannot
		post a PM2.5 of 200 with an index of 40."""
		assert self.aqi == pm25_aqi(self.pm25), (
			f'PM2.5 {self.pm25} is index {pm25_aqi(self.pm25)}, not {self.aqi}'
		)
		return self


class OutdoorWindow(BaseModel):
	"""§MON-006's "best times for outdoor activity": the hours of a day, and why they are the best.

	WHO's guidelines give the reason a time of day is the right unit here: exposure "is a product of
	the pollutant concentration and the time over which a person is in contact with that pollutant",
	and concentrations follow "the temporal pattern of operation of outdoor sources (e.g. traffic)
	but also on indoor sources (e.g. the daily cycle of cooking)". So the answer is not a number, it
	is *when* — and the model takes the day's readings and returns the hours a person can go out.

	`hours` is empty when no hour is better than another, which is a real answer and not a failure:
	on a uniformly bad day there is no window, and a screen that invented one would send somebody
	outdoors.
	"""
	model_config = MODEL_CONFIG
	county: str
	location: str
	hours: list[int] = []
	best_aqi: int | None = Field(default=None, ge=0, le=500)
	advise: str

	@model_validator(mode='after')
	def _hours_are_hours(self) -> Self:
		assert all(0 <= h <= 23 for h in self.hours), 'an hour of the day is 0-23'
		assert self.hours == sorted(self.hours), 'the windows are not in the order a day runs'
		assert (self.best_aqi is None) == (not self.hours), (
			'a window was offered with no index behind it, or an index with no window'
		)
		return self


class PollutionSource(BaseModel):
	"""§MON-006's "pollution source information": what is likely to be putting it there.

	The categories are WHO's own, from the guidelines' sources-of-emissions section — "land, air and
	water transportation; industry and power generation; and biomass burning, which includes
	controlled and uncontrolled forest and savannah fires and agricultural waste burning, as well as
	waste burning in urban areas" — plus household fuel combustion, which the same document defines
	separately because in Kenya it is the one a person can act on.

	`likely` is a word and not a certainty, and the field is named for it: a monitor reads a
	concentration and cannot read a source. What the model does is exclude what the evidence rules
	out — a source whose own signature is absent — rather than assert what remains.
	"""
	model_config = MODEL_CONFIG
	county: str
	location: str
	likely: list[str] = []
	evidence: str
	advise: str

	@model_validator(mode='after')
	def _a_source_list_is_named_or_empty(self) -> Self:
		assert all(s.strip() for s in self.likely), 'an unnamed source in the list'
		assert self.likely or self.evidence, (
			'a source report with nothing likely and nothing said about why'
		)
		return self


class AirQualityGuidance(BaseModel):
	"""§MON-006's five Features as one answer, on §MON-005's reasoning: they are one decision.

	The section lists an index, an advisory, mask guidance, a time to go out and a source, and a
	person reading a screen acts on all five together or on none of them.
	"""
	model_config = MODEL_CONFIG
	county: str
	location: str
	reading: AirQualityReading
	advisory: str
	mask_guidance: str
	outdoor: OutdoorWindow
	source: PollutionSource


class FloodReport(BaseModel):
	model_config = MODEL_CONFIG
	county: str
	rainfall_mm_72h: float = Field(ge=0, le=500)
	population_at_risk: int = Field(default=0, ge=0)

	@property
	def cholera_risk(self) -> str:
		return 'high' if self.rainfall_mm_72h >= 100 else ('moderate' if self.rainfall_mm_72h >= 50 else 'low')


# --- §9.5 INF-007 service status feed -----------------------------------------------------

# The section's six Contents, as slugs. A closed set rather than free text because the feed's
# question is "which of the six does this deployment carry" — the same question §INF-006's
# `SPEC_CONTENTS` answers for the directory — and an open string cannot be counted.
#
# `school_closure` is the one kind that already existed, as an `AlertKind` member. It stays there:
# §ALT-001's community alert feed carries school closures as *alerts* to residents, and this carries
# the same fact as a *status* on a screen. They are two surfaces over one fact, which is why the
# status publishes into the alert feed rather than beside it.
SERVICE_STATUS_KINDS: tuple[str, ...] = (
	'school_closure',
	'border_post',
	'market_closure',
	'water_interruption',
	'road_closure',
	'transport_disruption',
)

# Which states each kind can be in. A school is open or closed; a water supply is interrupted or
# restored; a border post can be *restricted*, which is neither. One shared vocabulary would let a
# school be "interrupted", and a status a reader cannot map onto a decision is a status that does
# not answer "can I go there today".
STATES_FOR: dict[str, tuple[str, ...]] = {
	'school_closure': ('open', 'closed'),
	'border_post': ('open', 'restricted', 'closed'),
	'market_closure': ('open', 'closed'),
	'water_interruption': ('interrupted', 'restored'),
	'road_closure': ('open', 'restricted', 'closed'),
	'transport_disruption': ('normal', 'disrupted'),
}


class ServiceStatus(BaseModel):
	"""§INF-007's "real-time status of public services relevant to health".

	The section's Contents were five `missing` rows and one carried one, and the shape of the gap was
	the same for all five: the alert feed's `service` category existed and *nothing produced one*, so
	`/alerting/service-status` filtered an empty set and reported zero statuses however many closures
	the county had published. A read with no producer is not a feature with a gap, it is a screen
	that is always empty.

	`name` is the specific place — the school, the market, the road, the border post. The section
	says "market closures", and a status that names no market is a rumour: the reader cannot tell
	whether it is their market, which is the whole question they opened the screen to answer.
	"""

	model_config = MODEL_CONFIG
	status_id: str
	kind: str = Field(pattern=r'^(' + '|'.join(SERVICE_STATUS_KINDS) + r')$')
	county: str
	name: str = Field(min_length=2, max_length=120)
	state: str
	detail: str = Field(max_length=400)
	# §INF-007 qualifies one Content — "road closures **affecting facility access**" — and does not
	# qualify the others. A road closure that does not affect reaching care is a road closure, and
	# this feed is about reaching care, so the qualifier is carried as a fact rather than left in
	# the section's prose.
	affects_facility_access: bool
	source: str = Field(min_length=2)
	# §ALT-001's Verification clause governs the feed this publishes into, so an unverified status
	# is refused by the same rule rather than by a second one written here.
	verified: bool
	effective_iso: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2}))?$')

	def model_post_init(self, _context: object) -> None:
		states = STATES_FOR[self.kind]
		assert self.state in states, (
			f'a {self.kind.replace("_", " ")} is {"/".join(states)}, not {self.state!r}'
		)
		# The section's own qualifier, enforced where it can be: this feed exists to answer whether
		# the reader can reach care, and a road closure filed under a kind the section scopes to
		# facility access but flagged as not affecting it is a row the feed should not be carrying.
		assert self.kind != 'road_closure' or self.affects_facility_access, (
			'§INF-007 carries "road closures affecting facility access" — a closure that does not '
			'affect reaching care belongs in a traffic feed, not this one'
		)

	@property
	def headline(self) -> str:
		"""The one line the feed carries. Derived, so the alert text cannot drift from the status."""
		return f'{self.name}: {self.kind.replace("_", " ")} — {self.state}'

	@property
	def body(self) -> str:
		"""The detail, with the place named again. Not redundancy: §3.3 principle 10 requires every
		output be shareable, and a body forwarded without its headline — which is what happens to a
		body — that says "Closed after flooding" names nothing and cannot be acted on."""
		access = 'Reaching a health facility is affected.' if self.affects_facility_access else ''
		return f'{self.name} is {self.state}. {self.detail} {access}'.strip()
