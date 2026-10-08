"""Feature registry & tier model (spec §7, Appendix B). Tier 4 is dormant behind activation gates."""
from enum import IntEnum

from pydantic import BaseModel, ConfigDict, Field

from afya.ids import uuid7str

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class Tier(IntEnum):
	tier1 = 1
	tier2 = 2
	tier3 = 3
	tier4 = 4


CHANNELS: tuple[str, ...] = ('radio', 'sms', 'ussd', 'whatsapp', 'social', 'chw', 'native')


class FeatureSpec(BaseModel):
	model_config = MODEL_CONFIG
	id: str = Field(pattern=r'^(CHAN|INF|TRI|FND|MED|EMG|REC|SENS|LOC)-\d{3}$')
	name: str
	tier: Tier
	channels: list[str]


class Tier4Activation(BaseModel):
	model_config = MODEL_CONFIG
	activation_id: str = Field(default_factory=uuid7str)
	authorized_by_pheoc: bool
	dpia_reviewed: bool
	flag_enabled: bool
	bulletin_text: str | None = None

	def is_active(self) -> bool:
		return self.authorized_by_pheoc and self.dpia_reviewed and self.flag_enabled


class FeatureRegistry:
	FEATURES: tuple[FeatureSpec, ...] = (
		FeatureSpec(id='INF-001', name='County Risk Dashboard', tier=Tier.tier1, channels=['native']),
		FeatureSpec(id='INF-002', name='What Should I Do Decision Tree', tier=Tier.tier1, channels=['native', 'whatsapp', 'ussd']),
		FeatureSpec(id='TRI-001', name='Broad Febrile-Illness Triage', tier=Tier.tier1, channels=['native', 'whatsapp', 'ussd', 'sms']),
		FeatureSpec(id='TRI-002', name='Symptom Diary and Follow-Up', tier=Tier.tier1, channels=['native']),
		FeatureSpec(id='FND-001', name='Facility Finder', tier=Tier.tier1, channels=['native', 'whatsapp', 'ussd']),
		FeatureSpec(id='MED-001', name='Medicine Verifier', tier=Tier.tier1, channels=['native', 'ussd']),
		FeatureSpec(id='EMG-001', name='Emergency SOS', tier=Tier.tier1, channels=['native']),
		FeatureSpec(id='EMG-003', name='Offline Emergency Card', tier=Tier.tier1, channels=['native']),
		FeatureSpec(id='TRI-003', name='Ebola-Specific Triage', tier=Tier.tier4, channels=['native', 'ussd']),
		FeatureSpec(id='LOC-001', name='Geofenced Risk Alerts', tier=Tier.tier4, channels=['native', 'sms']),
	)

	def __init__(self, activation: Tier4Activation | None = None) -> None:
		self._activation = activation or Tier4Activation(authorized_by_pheoc=False, dpia_reviewed=False, flag_enabled=False)
		assert self._activation is not None

	def tier4_active(self) -> bool:
		return self._activation.is_active()

	def available(self) -> list[FeatureSpec]:
		return [f for f in self.FEATURES if f.tier is not Tier.tier4 or self.tier4_active()]

	def get(self, feature_id: str) -> FeatureSpec:
		for f in self.FEATURES:
			if f.id == feature_id:
				return f
		raise KeyError(feature_id)