"""Feature registry & tier model (spec §7, Appendix B). Tier 4 is dormant behind activation gates."""
from enum import IntEnum

from afya.logmixin import LogMixin
from pydantic import BaseModel, ConfigDict, Field

from afya.ids import uuid7str
from afya.privacy.views import DPIAInput

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class Tier(IntEnum):
	"""§7.3 tier model. cross_cutting (0) is always-on and never dormant."""
	cross_cutting = 0
	tier1 = 1
	tier2 = 2
	tier3 = 3
	tier4 = 4


CHANNELS: tuple[str, ...] = ('radio', 'sms', 'ussd', 'whatsapp', 'social', 'chw', 'native')


class FeatureSpec(BaseModel):
	model_config = MODEL_CONFIG
	id: str = Field(pattern=r'^(CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}$')
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
	# §24.7: the DPIA precedes each Tier-4 activation. Carried here rather than in a second model
	# so the gate and the assessment of what it turns on cannot be described separately.
	dpia_input: DPIAInput | None = None

	def is_active(self) -> bool:
		return self.authorized_by_pheoc and self.dpia_reviewed and self.flag_enabled

	def unmet_keys(self) -> list[str]:
		"""The three-key gate (§11.1) as data, so a refusal can say which key is missing
		rather than reporting a bare boolean a caller has to guess at."""
		keys = (
			('pheoc_authorization', self.authorized_by_pheoc),
			('dpia_review', self.dpia_reviewed),
			('feature_flag', self.flag_enabled),
		)
		return [name for name, held in keys if not held]


# Spec-ID divergence, recorded rather than papered over. §10.1 assigns REC-004 menstrual,
# REC-005 mental health, REC-006 blood donors. The shipped wire ids (frozen by the mobile
# action catalogue and the native clients) put blood at REC-004, mental at REC-005, chronic
# at REC-006, labs at REC-007, maternal at REC-008, menstrual at REC-009. Only REC-005 agrees.
# Spec ids resolve to shipped ids here so callers may use either spelling; the reverse is not
# offered because two spec ids (REC-006 blood, REC-006 chronic) would collide.
SPEC_ID_ALIASES: dict[str, str] = {
	'REC-004': 'REC-009',  # spec menstrual tracker -> shipped cycle tracker
	'REC-006': 'REC-004',  # spec blood donor matching -> shipped donor matcher
}


class FeatureRegistry(LogMixin):
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
		FeatureSpec(id='INF-011', name='Water Quality Alerts', tier=Tier.tier3, channels=['native', 'sms']),
		FeatureSpec(id='INF-012', name='Air Quality Index', tier=Tier.tier3, channels=['native']),
		FeatureSpec(id='INF-013', name='Flood and Weather Alerts', tier=Tier.tier2, channels=['native', 'sms']),
		FeatureSpec(id='INF-014', name='School Closures and Public Notices', tier=Tier.tier1, channels=['native', 'sms', 'radio']),
		FeatureSpec(id='INF-015', name='Traditional and Herbal Safety', tier=Tier.tier1, channels=['native', 'whatsapp']),
		FeatureSpec(id='INF-016', name='Price Transparency', tier=Tier.tier2, channels=['native']),
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
		FeatureSpec(id='REC-003', name='Growth and Development Tracker', tier=Tier.tier3, channels=['native']),
		FeatureSpec(id='REC-004', name='Blood Donor Matching', tier=Tier.tier3, channels=['native']),
		FeatureSpec(id='REC-005', name='Mental Health Self-Check and Support', tier=Tier.tier3, channels=['native', 'sms']),
		FeatureSpec(id='REC-006', name='Chronic Disease Companion', tier=Tier.tier3, channels=['native']),
		FeatureSpec(id='REC-007', name='Lab Results and Prescriptions Wallet', tier=Tier.tier3, channels=['native']),
		FeatureSpec(id='REC-008', name='Maternal ANC Tracker', tier=Tier.tier3, channels=['native', 'sms']),
		FeatureSpec(id='REC-009', name='Menstrual and Reproductive Health Tracker', tier=Tier.tier3, channels=['native']),
		FeatureSpec(id='MON-001', name='Child Immunisation Tracker', tier=Tier.tier2, channels=['native', 'sms']),
		FeatureSpec(id='MON-002', name='Pregnancy and Antenatal Care Tracker', tier=Tier.tier2, channels=['native', 'sms']),
		FeatureSpec(id='MON-003', name='Chronic Disease Log', tier=Tier.tier2, channels=['native']),
		FeatureSpec(id='MON-004', name='Medication Reminders', tier=Tier.tier2, channels=['native', 'sms']),
		FeatureSpec(id='MON-005', name='Water Quality Alerts', tier=Tier.tier3, channels=['native', 'sms']),
		FeatureSpec(id='MON-006', name='Air Quality Index', tier=Tier.tier3, channels=['native']),
		FeatureSpec(id='MON-007', name='Vector and Environmental Risk', tier=Tier.tier3, channels=['native', 'sms']),
		FeatureSpec(id='MON-008', name='Nutrition and Food Safety', tier=Tier.tier3, channels=['native', 'sms']),
		FeatureSpec(id='MON-009', name='21-Day Contact Monitoring Diary', tier=Tier.tier4, channels=['native', 'sms', 'chw']),
		FeatureSpec(id='SENS-001', name='LiDAR Respiration Monitoring', tier=Tier.tier4, channels=['native']),
		FeatureSpec(id='SENS-002', name='Acoustic Cough and Respiratory Monitoring', tier=Tier.tier4, channels=['native']),
		FeatureSpec(id='SENS-003', name='Fall Detection', tier=Tier.tier1, channels=['native']),
		FeatureSpec(id='SENS-004', name='Camera-Based Symptom Capture', tier=Tier.tier4, channels=['native']),
		FeatureSpec(id='SENS-005', name='Screen and Camera PPG Health Monitoring', tier=Tier.tier2, channels=['native']),
		FeatureSpec(id='SENS-006', name='Wearable Integration', tier=Tier.tier2, channels=['native']),
		FeatureSpec(id='SENS-007', name='Sleep and Activity Monitoring', tier=Tier.tier2, channels=['native']),
		FeatureSpec(id='SENS-008', name='Environmental and Ambient Sensing', tier=Tier.tier4, channels=['native']),
		FeatureSpec(id='SENS-009', name='External Device Integration', tier=Tier.tier2, channels=['native']),
		FeatureSpec(id='SENS-010', name='NFC Tag-Based Workflows', tier=Tier.tier2, channels=['native']),
		FeatureSpec(id='LOC-001', name='Geofenced Risk Alerts', tier=Tier.tier1, channels=['native', 'sms']),
		FeatureSpec(id='LOC-002', name='Bluetooth Proximity Logging', tier=Tier.tier4, channels=['native']),
		FeatureSpec(id='LOC-003', name='GPS Location History for Contact Tracing', tier=Tier.tier4, channels=['native']),
		FeatureSpec(id='LOC-004', name='QR Code and NFC Check-In', tier=Tier.tier4, channels=['native']),
		FeatureSpec(id='LOC-005', name='Border and Point-of-Entry Module', tier=Tier.tier4, channels=['native', 'sms', 'whatsapp']),
		FeatureSpec(id='COM-005', name='Community Reporting', tier=Tier.tier3, channels=['native', 'sms']),
		FeatureSpec(id='COM-101', name='Community Health Worker Reporting Module', tier=Tier.tier4, channels=['chw', 'native']),
		FeatureSpec(id='COM-102', name='Peer-to-Peer Community Alert Network', tier=Tier.tier4, channels=['native', 'sms']),
		FeatureSpec(id='COM-103', name='Contact-Tracing Assistance for Individuals', tier=Tier.tier4, channels=['native']),
		FeatureSpec(id='COM-104', name='Community Misinformation Tracker', tier=Tier.tier4, channels=['native', 'whatsapp']),
		FeatureSpec(id='ALT-001', name='Community Alert Feed', tier=Tier.tier3, channels=['native', 'sms']),
		FeatureSpec(id='ALT-002', name='Family Safety Check-In', tier=Tier.tier3, channels=['native', 'sms']),
		FeatureSpec(id='ALT-003', name='Personalised Alert Preferences', tier=Tier.tier2, channels=['native']),
		FeatureSpec(id='ALT-004', name='Exposure Notification', tier=Tier.tier4, channels=['native', 'sms', 'whatsapp']),
		FeatureSpec(id='AI-001', name='Community-Level Risk Prediction', tier=Tier.tier4, channels=['native']),
		FeatureSpec(id='AI-002', name='Personal Risk Scoring', tier=Tier.tier4, channels=['native']),
		FeatureSpec(id='AI-003', name='Outbreak Early Warning Signal', tier=Tier.tier4, channels=['native']),
		FeatureSpec(id='AI-004', name='Model Governance and Fairness Audit', tier=Tier.cross_cutting, channels=['native']),
		FeatureSpec(id='AI-005', name='Explainability and Redress', tier=Tier.cross_cutting, channels=['native']),
		FeatureSpec(id='ACC-001', name='Low-Literacy Interface', tier=Tier.cross_cutting, channels=['native']),
		FeatureSpec(id='ACC-002', name='Multilingual Voice Interface', tier=Tier.cross_cutting, channels=['native', 'whatsapp']),
		FeatureSpec(id='ACC-003', name='Offline-First Architecture', tier=Tier.cross_cutting, channels=['native']),
		FeatureSpec(id='ACC-004', name='Battery Efficiency', tier=Tier.cross_cutting, channels=['native']),
		FeatureSpec(id='ACC-005', name='Device Compatibility', tier=Tier.cross_cutting, channels=['native']),
		FeatureSpec(id='SEC-001', name='Consent Management', tier=Tier.cross_cutting, channels=['native']),
		FeatureSpec(id='SEC-002', name='On-Device Processing', tier=Tier.cross_cutting, channels=['native']),
		FeatureSpec(id='SEC-003', name='Encryption', tier=Tier.cross_cutting, channels=['native']),
		FeatureSpec(id='SEC-004', name='Anonymity and Pseudonymity', tier=Tier.cross_cutting, channels=['native']),
		FeatureSpec(id='SEC-005', name='Data Retention and Deletion', tier=Tier.cross_cutting, channels=['native', 'sms', 'ussd', 'whatsapp']),
		FeatureSpec(id='SEC-006', name='Transparency and Audit', tier=Tier.cross_cutting, channels=['native']),
	)

	def __init__(self, activation: Tier4Activation | None = None) -> None:
		self._activation = activation or Tier4Activation(authorized_by_pheoc=False, dpia_reviewed=False, flag_enabled=False)
		assert self._activation is not None

	def activate(self, activation: Tier4Activation) -> None:
		"""Evaluate a fresh three-key attempt. Replaces reaching into __init__ to mutate state."""
		self._activation = activation
		self._log_info('tier4 gate evaluated', active=activation.is_active(), unmet=activation.unmet_keys())

	@property
	def activation(self) -> Tier4Activation:
		return self._activation

	def tier4_active(self) -> bool:
		return self._activation.is_active()

	def available(self) -> list[FeatureSpec]:
		return [f for f in self.FEATURES if f.tier is not Tier.tier4 or self.tier4_active()]

	def dormant(self) -> list[FeatureSpec]:
		"""Tier-4 features currently dark behind the three-key gate (§11.1)."""
		return [f for f in self.FEATURES if f.tier is Tier.tier4 and not self.tier4_active()]

	def get(self, feature_id: str) -> FeatureSpec:
		wanted = SPEC_ID_ALIASES.get(feature_id, feature_id)
		for f in self.FEATURES:
			if f.id == wanted:
				return f
		raise KeyError(feature_id)

	def by_tier(self, tier: Tier) -> list[FeatureSpec]:
		return [f for f in self.FEATURES if f.tier is tier]
