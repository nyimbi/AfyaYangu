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
		return 'alert' if self.pm25 > 55 else ('watch' if self.pm25 > 35 else 'normal')


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
