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
		FeatureSpec(id='CHAN-000', name='Community Radio', tier=Tier.tier1, channels=['radio']),
		FeatureSpec(id='CHAN-001', name='SMS Zero-Rated', tier=Tier.tier1, channels=['sms']),
		FeatureSpec(id='CHAN-002', name='USSD', tier=Tier.tier1, channels=['ussd']),
		FeatureSpec(id='CHAN-003', name='WhatsApp Bot', tier=Tier.tier1, channels=['whatsapp']),
		FeatureSpec(id='CHAN-004', name='Social Media', tier=Tier.tier1, channels=['social']),
		FeatureSpec(id='CHAN-005', name='Human Intermediaries', tier=Tier.tier2, channels=['chw']),
		FeatureSpec(id='CHAN-006', name='Native Application', tier=Tier.tier1, channels=['native']),
		FeatureSpec(id='INF-001', name='County Risk Dashboard', tier=Tier.tier1, channels=['native']),
		FeatureSpec(id='INF-002', name='What Should I Do Decision Tree', tier=Tier.tier1, channels=['native', 'whatsapp', 'ussd']),
		FeatureSpec(id='INF-003', name='Ebola Information Library', tier=Tier.tier1, channels=['native', 'whatsapp']),
		FeatureSpec(id='INF-004', name='Myth-Busting Library', tier=Tier.tier1, channels=['native', 'whatsapp', 'social']),
		FeatureSpec(id='INF-005', name='Travel Advisory', tier=Tier.tier1, channels=['native', 'whatsapp']),
		FeatureSpec(id='INF-006', name='Hotline and Contact Directory', tier=Tier.tier1, channels=['native', 'sms', 'ussd']),
		FeatureSpec(id='INF-007', name='Service Status Feed', tier=Tier.tier2, channels=['native']),
		FeatureSpec(id='INF-008', name='Health Tips and Education', tier=Tier.tier3, channels=['native', 'sms']),
		FeatureSpec(id='INF-009', name='First Aid Guide', tier=Tier.tier3, channels=['native']),
		FeatureSpec(id='INF-010', name='Safe and Dignified Burial Guidance', tier=Tier.tier3, channels=['native', 'chw']),
		FeatureSpec(id='TRI-001', name='Broad Febrile-Illness Triage', tier=Tier.tier1, channels=['native', 'whatsapp', 'ussd', 'sms']),
		FeatureSpec(id='TRI-002', name='Symptom Diary and Follow-Up', tier=Tier.tier1, channels=['native']),
		FeatureSpec(id='TRI-003', name='Ebola-Specific Triage', tier=Tier.tier4, channels=['native', 'ussd']),
		FeatureSpec(id='FND-001', name='Facility Finder', tier=Tier.tier1, channels=['native', 'whatsapp', 'ussd']),
		FeatureSpec(id='FND-002', name='Emergency Department Status', tier=Tier.tier1, channels=['native', 'sms']),
		FeatureSpec(id='FND-003', name='Testing Site Locator', tier=Tier.tier1, channels=['native', 'whatsapp', 'ussd']),
		FeatureSpec(id='FND-004', name='Pharmacy and Chemist Finder', tier=Tier.tier1, channels=['native']),
		FeatureSpec(id='FND-005', name='Vaccination Point Finder', tier=Tier.tier1, channels=['native']),
		FeatureSpec(id='FND-006', name='Appointment Booking and Queue Management', tier=Tier.tier2, channels=['native']),
		FeatureSpec(id='MED-001', name='Medicine Verifier', tier=Tier.tier1, channels=['native', 'ussd']),
		FeatureSpec(id='MED-002', name='Drug Interaction and Safety Checker', tier=Tier.tier1, channels=['native', 'chw']),
		FeatureSpec(id='MED-003', name='Dosage Calculator', tier=Tier.tier1, channels=['native', 'chw']),
		FeatureSpec(id='MED-004', name='Drug Stock Crowdsourcing', tier=Tier.tier2, channels=['native', 'sms']),
		FeatureSpec(id='EMG-001', name='Emergency SOS', tier=Tier.tier1, channels=['native']),
		FeatureSpec(id='EMG-002', name='Fall Detection and Auto-Alert', tier=Tier.tier1, channels=['native']),
		FeatureSpec(id='EMG-003', name='Offline Emergency Card', tier=Tier.tier1, channels=['native']),
		FeatureSpec(id='REC-001', name='Family Health Wallet Basic', tier=Tier.tier2, channels=['native']),
		FeatureSpec(id='REC-002', name='Family Health Wallet Full', tier=Tier.tier3, channels=['native']),
		FeatureSpec(id='REC-003', name='Growth Monitoring Chart', tier=Tier.tier3, channels=['native']),
		FeatureSpec(id='LOC-001', name='Geofenced Risk Alerts', tier=Tier.tier4, channels=['native', 'sms']),
		FeatureSpec(id='SENS-001', name='LiDAR Respiration Monitoring', tier=Tier.tier4, channels=['native']),
		FeatureSpec(id='SENS-002', name='Acoustic Cough Monitoring', tier=Tier.tier4, channels=['native']),
		FeatureSpec(id='SENS-003', name='Fall Detection', tier=Tier.tier1, channels=['native']),
		FeatureSpec(id='SENS-004', name='Camera Symptom Capture', tier=Tier.tier4, channels=['native']),
		FeatureSpec(id='SENS-005', name='PPG Health Monitoring', tier=Tier.tier2, channels=['native']),
		FeatureSpec(id='SENS-006', name='Wearable Integration', tier=Tier.tier2, channels=['native']),
		FeatureSpec(id='SENS-007', name='Sleep and Activity Monitoring', tier=Tier.tier2, channels=['native']),
		FeatureSpec(id='SENS-008', name='Environmental Ambient Sensing', tier=Tier.tier4, channels=['native']),
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