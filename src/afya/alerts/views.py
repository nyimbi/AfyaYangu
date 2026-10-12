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