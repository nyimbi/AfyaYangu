"""Environment & community-alert layer: water quality, air quality, flood→cholera risk, school closures, multi-disease outbreak alerts."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

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
