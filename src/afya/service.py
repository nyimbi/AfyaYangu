"""App assembly — FastAPI front door (spec §15.5)."""
from afya.surveillance.service import SurveillanceService, estimate_breath_rate
from afya.surveillance.views import CountySignal, Geofence, ProximityToken

from fastapi import Body, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from httpx import AsyncClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError

import json
import os
import tempfile
import wave as wavmod
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, cast

from afya.brand.service import BRAND, NON_GOALS, PRINCIPLES, VISION, brand_is_clean, brand_violations
from afya.problem.service import gap_report, lesson_report
from afya.content_audit.service import claim_report, content_report
from afya.config import ServiceConfig
from afya.crypto.service import KEY_BYTES, CryptoService
from afya.persistence.service import SqliteStore
from afya.channels.cost import ZeroRatingRule, parse_rules, zero_rating_gaps
from afya.channels.attention import attention_report
from afya.channels.outbound import MAX_SENTENCE_WORDS, MAX_WORD_CHARS, MESSAGE_CHARS, plain_language_report
from afya.channels.service import AfricaTalkingSmsPort, ChannelService
from afya.channels.views import ChwTask, SmsOut, UssdRequest, WhatsAppIn
from afya.emergency.service import EmergencyService, FacilityAmbulancePort, Inline719Port, _sms_dialable
from afya.identity.service import IdentityService
from afya.identity.views import IdentityLink, PhoneConsent, PseudonymChoice
from afya.emergency.views import EmergencyCard, IMUSample, SOSAlert, SOSEvent
from afya.evidence.service import EvidenceService, FileSystemEvidenceStore
from afya.integrations.gateways import AtSmsRestSend, AtUssdCallback
from afya.integrations.overpass import OverpassClient
from afya.places.service import Place, PlaceKind, PlacesService
from afya.places.views import TestType
from afya.evidence.views import EvidenceSubmission, EvidenceKind, UploadChunk, UploadOpen
from afya.insurance.service import InlineSHAPort, InsuranceService, SHACheckRequest, PriceItem
from afya.maternal.service import MaternalService
from afya.maternal.views import ANCRecord, BirthPlan, Pregnancy
from afya.mental.instruments import (
	AVAILABLE_LANGS, GAD7_FURTHER_EVALUATION_AT, ITEM_BANKS, RESPONSE_OPTIONS, TIMEFRAME, max_total,
)
from afya.mental.service import MentalHealthService, MoodEntry, Screening, WHO5
from afya.mental.support import ReferralRequest
from afya.women.service import WomenService
from afya.women.views import ContraceptionRequest, CycleLog, ReproductiveReferralRequest
from afya.alerts.service import AlertsService
from afya.alerts.views import (
	AirAdvisoryRequest, AirQuality, CommunityAlert, FloodReport, ServiceStatus,
	WaterAdvisoryRequest, WaterQuality,
)
from afya.blood.service import BloodRequest, BloodService, Donor
from afya.chronic.service import ChronicService
from afya.chronic.views import (
	BPReading, ChronicAppointment, GlucoseReading, KidneyFunction, RefillTracker, SeizureEvent,
	SickleCrisis,
)
from afya.integrations.adam import AdamClient
from afya.integrations.feeds import FEED_CADENCE, FEED_GRANULARITY, MIN_CELL, build as build_feed
from afya.integrations.service import InlineJaliPort, JaliClient, JaliPort, MoHFFacilityClient, PPBClient, PheocClient, SHAClient, TelcoGatewayClient
from afya.medicine.service import STOCK_REPORT_MAX_KM, MedicineService
from afya.medicine.views import (
	ESSENTIAL_MEDICINES, DoseRequest, InteractionReport, StockReport, SuspiciousReport,
	VerifyRequest,
)
from afya.facilities.service import FacilityService
from afya.facilities.views import (
	Booking, BookingChange, BookingRequest, Facility, FacilityLevel, FacilityReportRequest, NearestRequest,
	OfflineFacility, ServiceOffered, SlotOffer,
)
from afya.info.escalation import CORRECTION_FEED_CATEGORY, ContentError
from afya.info import health_education
from afya.info import counties
from afya.info.localisation import BackTranslation, CommunityValidation, workflow_for
from afya.info.myths import categories_of, topic_for_slug
from afya.info.recency import instant_iso
from afya.info.service import InfoService
from afya.info.views import CaseCounts, SubCountyStatus
from afya.info.views import WORKFLOW, ContentItem, CountyRisk
from afya.privacy.service import PrivacyService
from afya.privacy.views import _SCOPE, ConsentCategory, ConsentRecord, DPIAInput, RBACRole, Tier4ActivationRequest
from afya.privacy.service import BLOCKING_TOPICS, DPIA_TOPICS
from afya.privacy import rbac
from afya.records.service import RecordsService
from afya.records.views import GrowthRecord, ImmunisationRecord, LabResult, MilestoneCheck, ShareGrant, WalletDocument, WalletMember
from afya.ml.cough import SR as WAV_SR, YamnetCoughEngine
from afya.registry.activation import TriggerFiring, TriggerScope
from afya.registry.gate import ActivationService
from afya.registry.service import FeatureRegistry, Tier4Activation, Tier
from afya.registry.taxonomy import (
	DIVERGENCES as TIER_DIVERGENCES, PREFIXES, STRATEGIC_LOGIC, TIER_MAP, TIERS,
)
from afya.surveillance.service import SurveillanceService
from afya.surveillance.views import CountySignal, Geofence
from afya.sensors.service import SensorService
from afya.sensors.tags import Tag, TagReading, TagService, TagTarget
from afya.sensors.views import SenseKind
from afya.sensors.views import SenseIngest
from afya.sync.service import SyncService, apply_delta, delta_payload
from afya.sync.views import ConnectionClass, SyncOp
from afya.triage.service import TriageService
from afya.triage.views import EBOLA_SYMPTOMS, DiaryEntry, RiskLevel, TriageInput, TriageResult

# spec-coverage domains (§9.1, §9.6, §10.2-10.4, §11.4-11.5, §12, §17, §19)
from afya.access.service import AccessService
from afya.access.views import AccessProfile, SamplingContext, VoiceAudioRequest, VoiceRequest
from afya.ai.service import AIService
from afya.analytics.service import AnalyticsService
from afya.analytics.views import DASHBOARDS, DashboardId
from afya.metrics.service import MetricsService
from afya.metrics.views import MetricFamily
from afya.ai.views import AggregateCell, FairnessAuditRequest, RedressRequest, RiskInputs, SignalEvent, WarningSignal
from afya.alerting.service import AlertingService, safe_intent
from afya.alerting.views import ExposureAck, FeedItem, FeedPage, FamilyStatus
from afya.auth.service import AuthService
from afya.auth.views import PKCEStart, PKCETokenRequest, StaffProvision, TokenRequest
from afya.auth.views import now_ms as clock_ms
from afya.chw.service import ChwService
from afya.live.service import LiveService
from afya.live.views import AnswerIn, DeclineIn, LivePlatform, LiveSession, LiveStatus, QuestionIn
from afya.intermediaries.service import IntermediaryService
from afya.info.submissions import StoryIn, StoryModerationIn, StoryService
from afya.chw.views import ActivityLogEntry, ChwCase, ChwProfile
from afya.intermediaries.views import Incentive, Intermediary, Referral
from afya.community.service import CommunityService
from afya.community.views import (
	CaseReport, CaseStatus, CommunityIssue, ContactEntry, ContactList, MisinfoSubmission, PeerAlert,
	PeerAlertAck,
)
from afya.location.service import LocationService
from afya.location.views import (
	BorderPost, CheckIn, CheckInPoint, EncounterToken, ExposureDeclaration, LocationPoint,
	LocationPointWithSubject, PostArrivalReport, TravelerDeclaration,
)
from afya.monitoring.service import MonitoringService
from afya.monitoring.views import (
	AdherenceEvent, CampaignNotice, ConditionProfile, FoodSafetyAlert, HouseholdMemberRequest,
	LarvicidingNotice, LocationConsentDecision, MedSchedule, MonitoringDay, PeakFlowReading,
	WeightReading,
)
from afya.realtime.service import RealtimeService
from afya.realtime.views import KNOWN_CATEGORIES, SocketSubscription, now_iso
from afya.retention.service import RetentionService
from afya.retention.views import CorrectionRequest, DeletionRequest
from afya.governance.service import GovernanceService
from afya.operations.service import OperationsService
from afya.personas.service import PersonaService
from afya.rollout.service import RolloutService
from afya.security.service import SecurityService

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

APP_VERSION = '2.0.0'

# §15.5 versioning. `v1` is the current and only version, so the unversioned paths remain
# canonical — a client written against the bare path keeps working, and one that pins a version
# gets the same routes. A future `v2` mounts beside it and this tuple grows.
API_VERSIONS: tuple[str, ...] = ('v1',)
CURRENT_API_VERSION = 'v1'

# §FND-004's finder scans a wider pool than it returns before ranking on distance *and* whether a
# chemist is open: a pharmacy two hundred metres away that closed an hour ago is not the nearest
# answer to "where can I go now", so the ordering has to see past the first few by distance alone.
_PHARMACY_SCAN_LIMIT = 50


def _names_a_symptom(query: str | None) -> bool:
	"""Whether a free-text search names a symptom, for §AI-003's third signal.

	The bullet is "facility-finder searches for a *specific symptom*", and a finder search is mostly
	not that: "nearest hospital" and "KNH" are the commonest queries and neither is a surveillance
	signal. Matching against the triage symptom vocabulary is what separates the two, and it is the
	same list the triage flow uses so the finder and the triage cannot disagree about what a symptom
	is. Case-folded, because a person types "Fever" as often as "fever".
	"""
	if not query:
		return False
	text = query.lower()
	return any(symptom.replace('_', ' ') in text or symptom in text for symptom in EBOLA_SYMPTOMS)


async def _record_signal(ai: AIService, county: str | None, signal: str, event_ref: str = '') -> None:
	"""Record one §AI-003 signal event, if the surface named a locality at all.

	One door, because the six routes that emit are six chances to forget the locality check or to
	stamp a different clock. A signal with no county is not recorded: the bullet is a rise *in a
	locality*, and a national count against a county baseline is a number that cannot mean anything.
	The clock is read here rather than at each call site so every event in the ledger is dated the
	same way.
	"""
	if not county:
		return
	await ai.record_signal_event(SignalEvent(county=county, at_iso=now_iso(), signal=signal,
	                                           event_ref=event_ref))


class HealthResponse(BaseModel):
	model_config = MODEL_CONFIG
	status: str
	version: str = APP_VERSION
	tier4: bool = False


class BreathEstimateRequest(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	series: list[float]
	fps: float = Field(default=30.0, ge=0.5, le=120)


class InteractionsRequest(BaseModel):
	"""§MED-002's question, with the patient the section's third bullet asks about.

	The three patient fields are optional and each selects one axis of the answer: `pregnant` the
	Appendix 2 list, `age_months` the age floor in each monograph's own contraindication line, and
	`conditions` the condition families the monographs name. Omitted, the answer is the drug-pair
	check alone — which is what it was before, minus the four rows typed into the service.
	"""

	model_config = MODEL_CONFIG
	drugs: list[str] = Field(min_length=2, max_length=50)
	pregnant: bool | None = None
	age_months: int | None = Field(default=None, ge=0, le=1200)
	conditions: list[str] = Field(default_factory=list)


class DPIAReviewRequest(BaseModel):
	"""§17.3's review as a thing that happened: which processing, when, and by whom. The `reviewed_by`
	and `reviewed_at_iso` are required rather than defaulted, because a review with no reviewer and no
	date is the boolean this replaced wearing two extra fields."""
	model_config = MODEL_CONFIG
	processing: DPIAInput
	reviewed_at_iso: str
	reviewed_by: str


def _key_from_env(name: str) -> bytes | None:
	"""Read a 256-bit key from a hex environment variable, or None when it is unset.

	A key of the wrong length is refused rather than padded. Padding a short key to 32 bytes is how
	a deployment ends up with 8 bytes of entropy and a 256-bit label on it — the same class of
	failure as a control named in a table and absent from the code.
	"""
	raw = os.environ.get(name)
	if raw is None or raw == '':
		return None
	key = bytes.fromhex(raw)
	assert len(key) == KEY_BYTES, f'{name} must be {KEY_BYTES} bytes of hex ({KEY_BYTES * 2} characters)'
	return key


def _at_rest_key_for(db_path: str | None) -> bytes:
	"""The at-rest key for a deployment: a 0600 sidecar beside the database, created on first use.

	What this protects: a copy of the database file that does not include the sidecar — a dump, a
	backup bucket holding only `.db`, a snapshot of one file. What it does not protect: a reader with
	access to the whole directory, who has the key beside the ciphertext.

	That limitation is stated rather than papered over, because the honest control here is the
	platform keystore §SEC-003 names — Android Keystore, iOS Secure Enclave — which this server-side
	build cannot reach and which stays `deferred` in the audit. A sidecar key is a real improvement
	on plaintext and is not the standard the section asks for, and the posture reports the difference
	rather than claiming AES-256 has closed it.
	"""
	assert db_path is None or db_path, 'a path is either absent or a real path'
	# An in-memory database has no file to protect and no directory to hold a sidecar. Without this,
	# `db_path=':memory:'` — which every test fixture passes — writes a persistent 0600 file literally
	# named `:memory:.key` into the working directory, one per run, and reads it back on the next, so
	# the "ephemeral" database is keyed by whatever is lying in the CWD.
	if db_path is None or db_path == ':memory:' or db_path.startswith('file::memory:'):
		return os.urandom(KEY_BYTES)
	sidecar = Path(f'{db_path}.key')
	if sidecar.exists():
		key = bytes.fromhex(sidecar.read_text().strip())
		assert len(key) == KEY_BYTES, f'{sidecar} does not hold a {KEY_BYTES}-byte key'
		return key
	key = os.urandom(KEY_BYTES)
	sidecar.parent.mkdir(parents=True, exist_ok=True)
	# Opened 0600 at creation rather than chmod-ed afterwards: between a default-mode write and a
	# later chmod the key is world-readable, and that window is the whole attack.
	fd = os.open(str(sidecar), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
	try:
		os.write(fd, key.hex().encode())
	finally:
		os.close(fd)
	return key


def _app_layer_sealer(crypto: Any) -> Any:
	"""§SEC-003's application-layer key as the one operation §LOC-003's share performs with it.

	Returned rather than the crypto service itself so `afya.location` depends on a single operation.
	The refusal for a missing key lives in the returned object and not here, because the crypto
	service is built before a deployment knows whether it has an application-layer key, and a build
	that raised would make an unconfigured deployment unable to start rather than unable to share.

	`available` is a property rather than a value latched at build time, so a deployment that
	installs its second key without a restart gets a working share — and, more to the point here, so
	the flag cannot disagree with what `seal` will do.
	"""
	class _Sealer:
		@property
		def available(self) -> bool:
			return bool(crypto.has_app_layer)

		def __call__(self, plaintext: bytes) -> str:
			assert crypto.has_app_layer, (
				'no application-layer key is configured, so a location report cannot be sealed; '
				'refusing rather than sharing it under the at-rest key alone')
			return str(crypto.seal(plaintext, app_layer=True).to_blob())
	return _Sealer()


def _share_authority_consent(privacy: Any) -> Any:
	"""§SEC-001's `share_health_authorities` category as the one question §LOC-003's share asks.

	Returned rather than the privacy service itself so `afya.location` depends on a single question
	and keeps no import edge to `afya.privacy` — the same shape as `_app_layer_sealer` above, and
	for the same reason.

	The category is passed in as a string rather than read off `ConsentCategory` here, because the
	coupling this keeps is one predicate. `test_loc003_share.py` asserts the string the location
	module holds is the enum's own value, so the two cannot drift.
	"""
	def holds(subject_ref: str, category: str) -> bool:
		return bool(privacy.has_consent(subject_ref, category))
	return holds


def build_services(http: AsyncClient | None = None, db_path: str | None = None) -> dict[str, object]:
	client = http or AsyncClient(timeout=10)
	cfg = ServiceConfig.from_env()
	registry = FeatureRegistry()
	sms_port = AtSmsRestSend(cfg.at_base_url, cfg.at_api_key, cfg.at_username, client) if cfg.at_api_key else AfricaTalkingSmsPort(cfg.at_base_url, cfg.at_api_key or 'dev-key')
	# §SEC-003's encryption. The at-rest key is generated at boot when the deployment has not
	# supplied one, so a fresh install is encrypted rather than depending on an operator to
	# remember; `AFYA_AT_REST_KEY` and `AFYA_APP_LAYER_KEY` are read when set, and the two must
	# differ or the application layer adds nothing. Both are hex, so a key survives a config file.
	at_rest_key = _key_from_env('AFYA_AT_REST_KEY')
	app_layer_key = _key_from_env('AFYA_APP_LAYER_KEY')
	if app_layer_key is not None and at_rest_key == app_layer_key:
		raise ValueError(
			'AFYA_APP_LAYER_KEY must differ from AFYA_AT_REST_KEY; the application layer §SEC-003 '
			'asks for is a second key, not the same one used twice')
	# A generated key must survive a restart or the store it encrypts becomes unreadable — a random
	# per-boot key turns "encrypted" into "lost". With a database path the key is persisted in a
	# sidecar beside it, mode 0600; without one there is nothing to persist and the key is ephemeral,
	# which is correct for the in-memory store a test builds.
	crypto_svc = CryptoService(
		at_rest_key if at_rest_key is not None else _at_rest_key_for(db_path), app_layer_key)
	store = SqliteStore(db_path, crypto_svc) if db_path else None
	# §5.4's single identity model, built before the two services that must share it — the case-report
	# backend (dedup by phone) and the consent registry (a grant on one channel visible on another).
	# Built here rather than inside either one because a second instance resolves the same phone to a
	# different subject, and both claims then fail silently while reporting themselves as working.
	identity_svc = IdentityService()
	privacy_svc = PrivacyService(store, identity_svc)
	try:
		from afya.ml.cough import YamnetCoughEngine as YCE
		cough_engine: object = YCE()
	except (FileNotFoundError, AssertionError):
		cough_engine = None
	# §18.8's billing rules are constructed before the dict because the channel service is built
	# from them — the SMS zero-rating claim is only checkable against the carrier's own rules, so
	# the two cannot be wired independently. The rules are read lazily on each send: §18.8's
	# frequency is "on change", and a rule cached at startup is a rule that goes stale silently.
	telco = TelcoGatewayClient(cfg.telco_zero_rating_url, cfg.telco_airtime_url, cfg.telco_api_key or 'unconfigured', client)
	# §5.4's first bullet — "a single triage engine, same clinical logic regardless of entry point" —
	# needs one instance behind both the API routes and the channel handlers, so it is built here
	# rather than inside the return dict. Two constructions would be two engines and the claim would
	# be false the moment they diverged.
	triage_svc = TriageService(registry, privacy_svc)
	# §SEC-004's optional pseudonymous profile is wired here rather than inside the facility service:
	# the finder is built before the identity model in the return dict, and a second `IdentityService`
	# would derive handles from a different map than the one the routes read.
	facilities_svc = FacilityService(identity_svc)
	# §ACC-002's recogniser, built before both consumers for §SENS-002's reason: `AccessService`
	# answers a voice request and `ChannelService` transcribes a WhatsApp voice note, and two
	# engines would be two answers to one recording. Absent assets leave it None and every audio
	# path refuses by name rather than answering from a stub.
	try:
		from afya.ml.speech import WhisperSpeechEngine as WSE
		speech_engine: object | None = WSE()
	except (FileNotFoundError, AssertionError, ImportError):
		speech_engine = None
	access_svc = AccessService(speech_engine)
	# §SEC-006's quarterly publication draws its tables from §19.4's dashboards and §17.5's scan
	# record rather than recomputing either. Built as locals and handed over below, because the
	# services dict is constructed in one expression and a service that read `services['analytics']`
	# from inside would depend on the order the dict happened to be written in.
	analytics_svc = AnalyticsService()
	security_svc = SecurityService()
	retention_svc = RetentionService()
	# §AI-003's detector, built here rather than inline in the services dict because the channel
	# service is constructed above it and needs the same instance the six app surfaces record into.
	# Two `AIService`s would be two ledgers, and a signal counted into the one nobody reads is
	# indistinguishable from a signal that was never counted.
	ai_svc = AIService()
	retention_svc.register_sources({'dashboards': analytics_svc, 'scans': security_svc})

	async def telco_rules() -> list[ZeroRatingRule] | None:
		"""The carrier's zero-rating rules, as rules. Failure is the channel service's to report.

		No try/except here: an unconfigured deployment and an unreachable carrier are both "the
		rules were not pulled", which `ChannelService.zero_rating_rules` already turns into None and
		logs. Swallowing it here as well would be a second place that decides what a failure means.
		"""
		return parse_rules(await telco.zero_rating_rules())

	# §EMG-001's fan-out needs three legs and only one of them is the app. The contacts go out
	# through §5.3's channel service so the zero-rating claim is resolved where every other message's
	# is; the ambulance leg is §FND-001's own registry rather than a second list of bases; and the
	# countdown is a parameter the section does not state, so it is passed rather than inlined.
	def _dialable(number: str | None) -> str | None:
		return _sms_dialable(number) if number else None

	channels_svc = ChannelService(sms_port, telco_rules, triage_svc, identity_svc, privacy_svc, access_svc,
		# §AI-003's ledger, handed over as a callable for the reason §ALT-002's legs are: the channel
		# layer must not import the detection layer, and a report filed by a channel is counted by the
		# same `_record_signal` door the six app surfaces use — one clock, one locality check. Built
		# as a local above the dict so the channel service can be handed it at construction; without
		# this the ledger saw the app and neither of the two channels built for feature phones.
		record_signal=lambda county, signal, ref: _record_signal(ai_svc, county, signal, ref))
	# §ALT-002's two legs, wired here because they point in opposite directions and neither service
	# may import the other: the check-in texts the family through §5.3's channel service, which is
	# where §18.8's zero-rating is resolved — so a check-in message is free by the same rule as every
	# other message — and the inbound SMS resolves a number to a subject through §5.4's identity
	# model. Both are passed as callables rather than as services, so `afya.alerting` holds no import
	# of either and the cycle cannot form.
	# The identity model hands back whatever spelling the link recorded, and a landline is a number
	# that cannot receive a text at all. §EMG-001's fan-out refuses those through `_sms_dialable`, and
	# §ALT-002's goes to the same families, so it refuses them the same way rather than sending to a
	# number the gateway will drop — which would report a family told that never was.
	alerting_svc = AlertingService(
		channels_svc.send_sms, lambda ref: _dialable(identity_svc.msisdn_for(ref)))
	emergency_svc = EmergencyService(
		Inline719Port(), channels_svc, FacilityAmbulancePort(facilities_svc))
	# §MON-001's tracker reads and writes the wallet's dose log, so the wallet is built first and
	# handed to it — the same shape as §EMG-001's ambulance leg wrapping §FND-001's registry.
	records_svc = RecordsService()
	# §MON-004's "Works with no data connection" needs one queue that both the sync routes and the
	# medication tracker enqueue into, so it is built here and shared rather than constructed twice.
	sync_svc = SyncService(store)
	# §INF-005's first and fifth Features both reach a service this module already builds: the county
	# half of "Country and county advisories" reads §INF-001's risk rows, and the traveller enrolment
	# has to reach §MON-009's diary. Built as locals and handed to `LocationService` rather than
	# looked up later, because the dict is constructed in one expression and a service that read
	# `services['info']` from inside would depend on the order the dict happened to be written in.
	info_svc = InfoService()
	monitoring_svc = MonitoringService(records_svc, sync_svc)
	# §LOC-001's third collaborator: the entry/exit half reads §11.1's zone registry. A local for the
	# same reason as the two above — the dict is one expression, so `location` cannot reach the
	# `surveillance` entry beside it.
	surveillance_svc = SurveillanceService(registry, privacy_svc)
	# §18's ADaM client, built as a local because two entries need the same object: the integrations
	# dict below and §COM-103's encrypted contact-list share, which travels the ADaM wire. Two
	# constructions would be two clients with two connection pools, and a share sent through one
	# would be invisible to the health check reading the other.
	adam_svc = AdamClient(cfg.adam_url, client, cfg.adam_api_key, cfg.adam_cert())
	# §CHAN-000's call-in and §CHAN-004's clinician Q&A. Built here rather than inline in the dict
	# because the channel service has to be handed it: the queue is fed from §5.4's one report sink,
	# and a second reader of that sink would be a second inbox. The backlog is marked before the
	# routes exist, so a report filed before any programme was scheduled is not resurrected as a
	# question in the first session that opens.
	live_svc = LiveService()
	live_svc.mark_absorbed(r.report_id for r in channels_svc.channel_reports())
	channels_svc.attach_live(live_svc)
	# §CHAN-004's submissions. It needs both collaborators as locals for the same reason the two
	# above do: the dict is one expression, and a story is refused against §SEC-001's consent ledger
	# and approved into §6.5's content workflow.
	story_svc = StoryService(privacy_svc, info_svc)

	return {
		'registry': registry,
		# §11.1's activation model: the registry's three-key gate answers "is the event on", and this
		# answers the three scopes the table also has. Built from the registry rather than beside it,
		# so a declared event and the keys that permit it stay one fact.
		'activation': ActivationService(registry),
		'store': store,
		'cough_engine': cough_engine,
		# §24.7: the Tier-4 gate reads the DPO's DPIA, so the two services are wired, not independent.
		'privacy': privacy_svc,
		'triage': triage_svc,
		'surveillance': surveillance_svc,
		'sensors': SensorService(registry),
		# §SENS-010's tag workflows. Built here rather than inside `SensorService` because the tag
		# register is not a sensor: it is the binding between a tag and the object it names, and
		# §13.1's `nfc` row is about the radio, not about what a tap means.
		'tags': TagService(),
		'medicine': MedicineService(PPBClient(cfg.ppb_url, client, '')),
		'facilities': facilities_svc,
		# §5.3 CHAN-1's zero-rating is an agreement with the carrier, so the channel service is
		# handed the telco client's rules rather than a boolean. A deployment with no telco
		# configured passes nothing and reports every free claim as unverified.
		'channels': channels_svc,
		# §CHAN-000's call-in queue and §CHAN-004's clinician Q&A. Its own entry rather than a
		# collaborator of `channels` because the two read the same report sink in opposite
		# directions: the channel service files a report, and a programme on air reads it back as a
		# question. `channels_svc` holds the same object so the absorb happens on the routes that
		# already walk the sink.
		'live': live_svc,
		'crypto': crypto_svc,
		'emergency': emergency_svc,
		'info': info_svc,
		'stories': story_svc,
		'records': records_svc,
		'women': WomenService(),
		'maternal': MaternalService(),
		'chronic': ChronicService(),
		'mental': MentalHealthService(),
		'blood': BloodService(),
		'alerts': AlertsService(),
		'insurance': InsuranceService(InlineSHAPort()),
		'places': PlacesService(),
		# §SEC-002's "photos encrypted": the pipeline is handed the deployment's key, so a photo is
		# sealed before it reaches the object store. Wired here rather than inside the evidence
		# module for the reason every other service takes its crypto this way — one key, one place
		# it is read, and a deployment with no key refuses to store rather than storing in the clear.
		'evidence': EvidenceService(registry, FileSystemEvidenceStore('var/evidence'), crypto_svc),
		'sync': sync_svc,
		# §MON-001's child tracker is a view over the wallet's doses, not a second store: a dose
		# recorded on the tracker screen has to reach the record that outlives the paper card, or the
		# certificate and the gap list describe a child the parent has been vaccinating.
		# §MON-004's "Works with no data connection": a dose taken with no signal has to reach the
		# sync queue, so the tracker is handed the queue rather than the route doing it separately —
		# a caller that forgot would lose the dose while the screen said it was recorded.
		# §MON-004's "Works with no data connection" and §COM-101's "Offline report queue" both need a
		# queue the sync routes and the feature's own service enqueue into, so it is built here and
		# shared rather than constructed twice. §COM-101's CHW is the field user the section describes,
		# and §16.3 already carried a `case_reports` rule with nothing writing to it.
		'monitoring': monitoring_svc,
		'identity': identity_svc,
		# §11.4's last bullet needs both halves of the join: `channels_svc` carries the notice and
		# `alerting_svc` holds §ALT-003's subscriptions, which decide whether the notice is owed. They
		# are separate parameters because a deployment with the transport and no ledger must not push
		# to someone who switched community alerts off, and a deployment with neither must still be
		# able to say which of the two is missing rather than reporting a notice sent to nobody.
		'community': CommunityService(identity_svc, sync_svc, crypto_svc, adam_svc, channels_svc, alerting_svc),
		'alerting': alerting_svc,
		'realtime': RealtimeService(),
		# §INF-005's two collaborators. `info_svc.dashboard` is the county risk read and
		# `monitoring_svc` is the diary the traveller enrolment has to reach — the audit row's
		# "the link is a message string, so the enrolment does not reach `MonitoringService.enrol`
		# and the diary stays empty". §LOC-001's third is the zone registry: `geofences_at` is one
		# method of the surveillance service, handed over as a callable so this module depends on a
		# read and not on a service.
		# §LOC-003's share seals under §SEC-003's application-layer key, which is the layer the crypto
		# service's own docstring assigns to location history. The transport is the deployment's, so
		# it is left unwired here: a share with no endpoint still seals and holds, and the receipt
		# says held rather than delivered. Sealing is passed as a callable so the location module
		# depends on one operation and not on the crypto service.
		# The share's consent is §SEC-001's `share_health_authorities` category read off the one
		# ledger, not the location diary's own `consent_granted` flag: those are two toggles, and a
		# person who allowed a diary and refused the Ministry must keep the diary on the phone.
		'location': LocationService(info_svc.dashboard, monitoring_svc, surveillance_svc.geofences_at,
		                            sealer=_app_layer_sealer(crypto_svc),
		                            share_consent=_share_authority_consent(privacy_svc),
		                            sync=sync_svc),
		'ai': ai_svc,
		'analytics': analytics_svc,
		'metrics': MetricsService(),
		'access': access_svc,
		# §SEC-006's quarterly publication reads §19.4's dashboards and §17.5's scan record rather
		# than recomputing either, so the min-cell rule and the scan cadence each live in one place.
		# Wired here, after both services exist, for the reason the audit egress table is handed its
		# wires: a publication that applied its own threshold would be a second copy of the rule.
		'retention': retention_svc,
		'governance': GovernanceService(),
		'operations': OperationsService(),
		# §20/§21: the rollout reads the registry (§20.6's retention table crossed against it) and
		# the APK budget §22.5 sets, so it is constructed with the registry rather than beside it.
		'rollout': RolloutService(registry),
		# §4: who the launch is for. Constructed beside the rollout because §4.3's priorities are the
		# ordering the rollout is a schedule for, and §22.7's equity targets need a population.
		'personas': PersonaService(),
		'security': security_svc,
		'chw': ChwService(),
		# §CHAN-5: the intermediary programme. Separate from `chw` because §4.2 and §CHAN-5 are two
		# lists — pharmacy staff, faith leaders and teachers read the product *and* distribute it,
		# and an intermediary holds a code, not a session.
		'intermediaries': IntermediaryService(),
		'auth': AuthService(),
		# §18: the national systems. Every client is constructed whether or not its vendor is
		# configured, because a client that only exists when configured makes "not configured" and
		# "not wired" indistinguishable from the outside — which is exactly the failure the routes
		# below have to be able to report.
		'jali': JaliClient(cfg.jali_url, cfg.jali_api_key, client) if cfg.jali_api_key else InlineJaliPort(),
		'pheoc': PheocClient(cfg.pheoc_url, client, cfg.pheoc_api_key),
		'mohf': MoHFFacilityClient(cfg.mohf_url, client),
		'ppb': PPBClient(cfg.ppb_url, client, cfg.ppb_api_key),
		'adam': adam_svc,
		'sha': SHAClient(cfg.sha_url, client, cfg.sha_api_key),
		'telco': telco,
	}


def create_app(services: dict[str, object] | None = None) -> FastAPI:
	svc = services or build_services(db_path=os.environ.get('AFYA_DB_PATH'))
	assert {'registry', 'triage', 'surveillance', 'facilities', 'channels', 'sync', 'privacy', 'evidence'} <= svc.keys(), 'core services required'
	registry: FeatureRegistry = svc['registry']  # type: ignore[assignment]
	# §11.1's activation model: five triggers over three scopes, where `registry.tier4_active()` is
	# one boolean. Bound here rather than reached through the dict so every route resolves through the
	# same object, and so a firing recorded by one route is visible to the next.
	activation: ActivationService = svc['activation']  # type: ignore[assignment]
	triage: TriageService = svc['triage']  # type: ignore[assignment]
	sensors: SensorService = svc['sensors']  # type: ignore[assignment]
	tags: TagService = svc['tags']  # type: ignore[assignment]
	surveillance: SurveillanceService = svc['surveillance']  # type: ignore[assignment]
	facilities: FacilityService = svc['facilities']  # type: ignore[assignment]
	channels: ChannelService = svc['channels']  # type: ignore[assignment]
	emergency: EmergencyService = svc['emergency']  # type: ignore[assignment]
	info: InfoService = svc['info']  # type: ignore[assignment]
	records: RecordsService = svc['records']  # type: ignore[assignment]
	evidence: EvidenceService = svc['evidence']  # type: ignore[assignment]
	women: WomenService = svc['women']  # type: ignore[assignment]
	maternal: MaternalService = svc['maternal']  # type: ignore[assignment]
	chronic: ChronicService = svc['chronic']  # type: ignore[assignment]
	mental: MentalHealthService = svc['mental']  # type: ignore[assignment]
	blood: BloodService = svc['blood']  # type: ignore[assignment]
	alerts: AlertsService = svc['alerts']  # type: ignore[assignment]
	insurance: InsuranceService = svc['insurance']  # type: ignore[assignment]
	places: PlacesService = svc['places']  # type: ignore[assignment]
	cough_engine = svc.get('cough_engine')
	privacy: PrivacyService = svc['privacy']  # type: ignore[assignment]
	sync: SyncService = svc['sync']  # type: ignore[assignment]
	medicine: MedicineService = svc['medicine']  # type: ignore[assignment]
	monitoring: MonitoringService = svc['monitoring']  # type: ignore[assignment]
	community: CommunityService = svc['community']  # type: ignore[assignment]
	identity: IdentityService = svc['identity']  # type: ignore[assignment]
	alerting: AlertingService = svc['alerting']  # type: ignore[assignment]
	realtime: RealtimeService = svc['realtime']  # type: ignore[assignment]
	location: LocationService = svc['location']  # type: ignore[assignment]
	ai: AIService = svc['ai']  # type: ignore[assignment]
	analytics: AnalyticsService = svc['analytics']  # type: ignore[assignment]
	metrics: MetricsService = svc['metrics']  # type: ignore[assignment]
	access: AccessService = svc['access']  # type: ignore[assignment]
	retention: RetentionService = svc['retention']  # type: ignore[assignment]
	# §SEC-003's encryption, bound here so the posture route and the backup route read the same
	# object. Reaching into the dict per route would let two of them resolve different services.
	crypto = svc['crypto']
	governance: GovernanceService = svc['governance']  # type: ignore[assignment]
	operations: OperationsService = svc['operations']  # type: ignore[assignment]
	rollout: RolloutService = svc['rollout']  # type: ignore[assignment]
	personas: PersonaService = svc['personas']  # type: ignore[assignment]
	security: SecurityService = svc['security']  # type: ignore[assignment]
	chw: ChwService = svc['chw']  # type: ignore[assignment]
	live: LiveService = svc['live']  # type: ignore[assignment]
	stories: StoryService = svc['stories']  # type: ignore[assignment]
	intermediaries: IntermediaryService = svc['intermediaries']  # type: ignore[assignment]
	auth: AuthService = svc['auth']  # type: ignore[assignment]
	# §18: the national systems. `jali` may be the offline port, which is why it is typed as the
	# protocol rather than the concrete client — the routes must work on a deployment with no vendor.
	adam: AdamClient = svc['adam']  # type: ignore[assignment]
	jali: JaliPort = svc['jali']  # type: ignore[assignment]
	pheoc: PheocClient = svc['pheoc']  # type: ignore[assignment]
	mohf: MoHFFacilityClient = svc['mohf']  # type: ignore[assignment]
	sha: SHAClient = svc['sha']  # type: ignore[assignment]
	ppb: PPBClient = svc['ppb']  # type: ignore[assignment]
	telco: TelcoGatewayClient = svc['telco']  # type: ignore[assignment]
	app = FastAPI(title='Afya Yangu / Mlinzi', version=APP_VERSION)

	# --- §15.5 request integrity: rate limiting and idempotency ------------------------------
	# Applied as middleware rather than per-route so a new endpoint cannot be added without them.
	@app.middleware('http')
	async def request_integrity(request: Request, call_next):  # type: ignore[no-untyped-def]
		device = request.headers.get('x-device-id') or (request.client.host if request.client else 'unknown')
		decision = auth.check_rate(device)
		if not decision.allowed:
			return JSONResponse(
				status_code=429, content={'detail': decision.message, 'retry_after_seconds': decision.retry_after_seconds},
				headers={'Retry-After': str(decision.retry_after_seconds)},
			)
		key = request.headers.get('idempotency-key')
		if key and request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
			body = (await request.body()).decode('utf-8', 'replace')
			try:
				prior = auth.replay(key, body)
			except AssertionError as exc:
				return JSONResponse(status_code=409, content={'detail': str(exc)})
			if prior is not None:
				return JSONResponse(status_code=prior.status_code, content=prior.response)
			response = await call_next(request)
			if response.status_code < 400:
				chunks = [chunk async for chunk in response.body_iterator]  # type: ignore[attr-defined]
				raw = b''.join(chunks)
				try:
					payload = json.loads(raw)
				except ValueError:
					# A non-JSON success body cannot be replayed; the write itself still stands, and
					# the response is passed through untouched rather than re-parsed outside the try.
					return Response(content=raw, status_code=response.status_code, headers=dict(response.headers))
				auth.store(key, body, payload, response.status_code)
				return JSONResponse(status_code=response.status_code, content=payload, headers=dict(response.headers))
			return response
		return await call_next(request)

	def require_token(authorization: str | None) -> tuple[str, RBACRole]:
		"""Resolve a bearer token to (subject, role). Absent or unknown token is a 401, not a 500."""
		if not authorization or not authorization.lower().startswith('bearer '):
			raise HTTPException(status_code=401, detail='Bearer token required')
		presented = authorization.split(' ', 1)[1].strip()
		try:
			return auth.resolve_anonymous(presented).subject_ref, RBACRole.citizen_anonymous
		except AssertionError:
			pass
		try:
			worker = auth.resolve_worker(presented)
			return worker.subject_ref, RBACRole(worker.role)
		except (AssertionError, ValueError) as exc:
			raise HTTPException(status_code=401, detail='Invalid or expired token') from exc

	def optional_subject():  # type: ignore[no-untyped-def]
		"""The token's subject when one was presented, and `None` when none was.

		For a route that must work without a token and does something extra when there is one.
		`/triage/evd` is the case: §8.1's triage is Tier 1 with anonymous mode, so refusing a caller
		with no token would break the feature — but §11.2's Escalation needs a subject, because
		consent is held per person in §SEC-001's ledger. A guard would make the escalation mandatory
		with the identity; this makes the identity optional and the *consent* the thing that
		decides, which is what the section actually conditions the notification on.

		A malformed token is treated as no token rather than as a 401. The triage is still owed to
		the caller, and an expired token must not turn a clinical answer into an error page — the
		escalation is the part that is lost, and the result says so.
		"""
		async def dependency(authorization: str | None = Header(default=None)) -> str | None:
			if not authorization or not authorization.lower().startswith('bearer '):
				return None
			presented = authorization.split(' ', 1)[1].strip()
			try:
				return auth.resolve_anonymous(presented).subject_ref
			except AssertionError:
				pass
			try:
				return auth.resolve_worker(presented).subject_ref
			except (AssertionError, ValueError):
				return None
		return dependency

	def require_scope(dataset: str, *, purpose: str | None = None):  # type: ignore[no-untyped-def]
		"""Route guard: the token's role must cover the dataset it is asking for (§17 RBAC).

		`purpose` is §17.4's "Access to personal data requires a documented purpose", declared by the
		route rather than sent by the caller: the route's jurisdiction *is* the purpose it serves, and
		a caller-supplied purpose is a value the caller attests about itself — the failure
		`DPIARecord` names for §17.3. It is required on the scopes that reach another person's data
		and absent on the ones that do not; `rbac.undocumented_access()` reads the routes and names
		any that should declare one and do not.

		It is typed `str` and converted here rather than typed `AccessPurpose`, so a route declares
		it in the same spelling `rbac.route_purposes` reads — one spelling, read from the source.
		`rbac.unknown_purposes()` is the gate that a declared string is a member, so a typo fails a
		test rather than reaching a request; the conversion below makes it fail loudly if one ever
		does.
		"""
		async def guard(authorization: str | None = Header(default=None)) -> str:
			subject, role = require_token(authorization)
			from afya.privacy.views import AccessPurpose, AccessRequest
			# The logged variant, so every guarded route writes the durable §17.4 entry rather
			# than only the in-memory list.
			declared = AccessPurpose(purpose) if purpose is not None else None
			if not await privacy.check_access_logged(AccessRequest(role=role, dataset=dataset, purpose=declared)):
				raise HTTPException(status_code=403, detail=f'role {role.value} may not read {dataset}')
			return subject
		return guard

	def require_any_scope(datasets: tuple[str, ...], *, purpose: str | None = None):  # type: ignore[no-untyped-def]
		"""Route guard for a route §17.4 lets more than one role read, each through its own scope.

		§19.4 names PHEOC, county health teams and MoH as the readers of the public-health
		dashboards, and §17.4 gives those three different scopes: `county_aggregate` to the county
		officer, `national_aggregate` to the PHEOC analyst. Guarding the dashboard on either one
		alone locks out two thirds of the audience the spec names — so the guard takes the set, and
		still requires the token's role to hold *one of* them through the same `_SCOPE` map rather
		than widening any role. Each attempt is logged with the dataset that was actually tried.

		`purpose` is carried for the same reason `require_scope` carries it. No current call site
		declares one — the only set in use is `('infrastructure', 'audit_logs')`, neither of which
		reaches another person's data — but the argument exists so a future multi-role personal-data
		route is not forced to reach for a second guard.
		"""
		async def guard(authorization: str | None = Header(default=None)) -> str:
			subject, role = require_token(authorization)
			from afya.privacy.views import AccessPurpose, AccessRequest
			declared = AccessPurpose(purpose) if purpose is not None else None
			for dataset in datasets:
				if await privacy.check_access_logged(AccessRequest(role=role, dataset=dataset, purpose=declared)):
					return subject
			raise HTTPException(status_code=403, detail=f'role {role.value} may read none of {list(datasets)}')
		return guard

	def require_self(subject_from_request=None, *, names_subject: bool = True):  # type: ignore[no-untyped-def]
		"""Route guard for a personal-data route: the named subject must be the token's own.

		A `self`-scoped route that reads a `subject_ref` out of the path or body without comparing
		it to the token is an IDOR — the scope check passes for *every* citizen while the subject
		is whatever the caller typed. This binds the two: a citizen may act only on their own
		subject, and a worker role (which reaches people through its own scoped routes) is refused
		outright rather than allowed to name anyone.

		`subject_from_request` extracts the subject when it is not a path parameter; the default
		reads path, then query, then a JSON body, then form fields. When `names_subject` is False
		the route is one that binds the subject itself (a group the caller joins), so only the token
		and the citizen role are required.
		"""
		async def guard(request: Request, authorization: str | None = Header(default=None)) -> str:
			import inspect
			subject, role = require_token(authorization)
			from afya.privacy.views import CITIZEN_ROLES, AccessRequest
			if not await privacy.check_access_logged(AccessRequest(role=role, dataset='self')):
				raise HTTPException(status_code=403, detail=f'role {role.value} may not act for a citizen subject')
			if role not in CITIZEN_ROLES:
				raise HTTPException(status_code=403, detail='this route acts only for the token holder')
			if not names_subject:
				return subject
			named: object = None
			if subject_from_request is not None:
				named = subject_from_request(request)
				if inspect.isawaitable(named):
					named = await named
			else:
				named = request.path_params.get('subject_ref') or request.query_params.get('subject_ref')
				if named is None and request.method in ('POST', 'PUT', 'PATCH'):
					ctype = request.headers.get('content-type', '')
					try:
						if 'json' in ctype:
							body = json.loads(await request.body())
							named = body.get('subject_ref') if isinstance(body, dict) else None
						elif 'form' in ctype:
							named = (await request.form()).get('subject_ref')
					except ValueError:
						named = None
			if named is None:
				raise HTTPException(status_code=422, detail='this request must name the subject it acts for')
			if named != subject:
				raise HTTPException(status_code=403, detail='a token may act only for its own subject')
			return subject
		return guard

	def require_self_or_guardian(member_from_request, *, may_create: bool = False):  # type: ignore[no-untyped-def]
		"""Route guard for a family-record route: the named member must be the token's own subject
		or a minor in the token's wallet (§17.6).

		`require_self` compares for equality, which is right for a route where a person names
		themselves and wrong here: a guardian names their child, never themselves, so equality would
		refuse every legitimate read. The relation that authorises these routes is ownership —
		`records.owns` — and this guard is the only place that relation is applied, so a family route
		cannot invent a looser one.

		`may_create` is for the one route that enrols a member: nothing owns a member that does not
		exist yet, so there is no relation to check and the route binds the write itself by forcing
		the recorded guardian to be the caller. It is a flag rather than a second guard so the two
		remain visibly the same rule with one exemption, not two rules that can drift.

		`may_create` waives the *ownership* check, never the *taken-ref* one. Without that second
		check a caller could name a `member_ref` another wallet already holds and the write would
		land on it: the enrolment map is keyed by the ref, so a stranger's child is re-enrolled under
		the caller's guardianship and the original guardian loses the record. The route's own
		`guardian_ref` binding cannot catch it, because a client that omits `guardian_ref` is the
		normal path and the binding then fills in the caller.

		A create that names no ref is allowed through rather than refused: `WalletMember.member_ref`
		has a `default_factory`, so the model mints one and there is nothing to collide with. The
		catalogue marks the field `server_assigned` for exactly that reason — no form draws it — so
		requiring it here would 422 the one action the route exists for.
		"""
		async def guard(request: Request, authorization: str | None = Header(default=None)) -> str:
			import inspect
			subject, role = require_token(authorization)
			from afya.privacy.views import CITIZEN_ROLES, AccessRequest
			if not await privacy.check_access_logged(AccessRequest(role=role, dataset='self')):
				raise HTTPException(status_code=403, detail=f'role {role.value} may not act for a citizen subject')
			if role not in CITIZEN_ROLES:
				raise HTTPException(status_code=403, detail='this route acts only for the token holder')
			named: object = member_from_request(request)
			if inspect.isawaitable(named):
				named = await named
			if may_create:
				if named and str(named) in records.member_refs() and not records.owns(subject, str(named)):
					raise HTTPException(status_code=403, detail='that reference belongs to another wallet')
				return subject
			if not named:
				raise HTTPException(status_code=422, detail='this request must name the family member it acts for')
			if not records.owns(subject, str(named)):
				raise HTTPException(status_code=403, detail='these records belong to someone else')
			return subject
		return guard

	async def _body_member(request: Request) -> str | None:
		"""The `member_ref` a write names in its JSON body.

		`require_self`'s default extractor looks for `subject_ref`; a records write names its
		subject `member_ref` instead, so a route that only took the default would compare nothing
		and fall through to the 422. Reading the body here is safe — Starlette caches it, so the
		route's own model parsing sees the same bytes.
		"""
		try:
			body = json.loads(await request.body())
		except ValueError:
			return None
		return body.get('member_ref') if isinstance(body, dict) else None

	def require_webhook(header_name: str = 'x-afya-signature'):  # type: ignore[no-untyped-def]
		"""Guard for an inbound webhook: a carrier or a peer system has no app token.

		An unauthenticated webhook is an open write into the system — anyone who learns the URL can
		inject a hotline follow-up or a call outcome, and every one of those is attributed to a real
		person. The body is HMAC-signed with the shared secret and the signature compared in constant
		time; the body is read here, so a route using this guard must take the raw bytes it needs
		from the request rather than re-reading a consumed stream.

		No secret configured means the deployment cannot authenticate, and the honest answer is to
		refuse: a dev box with an open webhook is how an open webhook ships to production.
		"""
		from afya.config import ServiceConfig
		import hashlib
		import hmac

		async def guard(request: Request, signature: str | None = Header(default=None, alias=header_name)) -> bytes:
			secret = ServiceConfig.from_env().webhook_secret
			if not secret:
				raise HTTPException(status_code=503, detail='inbound webhooks are not configured on this deployment')
			if not signature:
				raise HTTPException(status_code=401, detail='webhook signature required')
			body = await request.body()
			expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
			if not hmac.compare_digest(expected, signature.strip().lower()):
				raise HTTPException(status_code=401, detail='webhook signature does not match')
			return body
		return guard

	# --- §15.5 authentication ---
	@app.post('/auth/anonymous')
	async def auth_anonymous(req: TokenRequest,
			authorization: str | None = Header(default=None)) -> dict[str, object]:
		"""Mint a citizen token, or re-issue one for a subject this service has issued before.

		§SEC-004 asks for no account, and the subject an anonymous token carries is the *only* thing
		the citizen routes check — `require_self` compares the subject a request names to the subject
		the token holds. A route that mints a token for any name in the body is therefore a way to
		ask for a key to anyone's record: `{"subject_ref": "someone"}` used to return a token for
		`someone`, and every `require_self` route then read and wrote that person's diary, wallet,
		cycles and antenatal notes.

		So a subject is honoured only when it is one this service has issued before — either because
		the request carries that subject's live token (what a restart does), or because the name is
		already in the issued set. A device that loses its token still owns its subject, which is
		what makes a reinstall survivable; a caller naming somebody else's subject has neither the
		token nor the prior issue, and is refused rather than quietly given a fresh identity under a
		name it chose.

		Reissue revokes the old token, so a stolen one does not outlive its replacement.
		"""
		if req.subject_ref is None:
			token = await auth.issue_anonymous()
			return token.model_dump(mode='json')
		presented = (authorization or '')
		presented = presented.split(' ', 1)[1].strip() if presented.lower().startswith('bearer ') else ''
		holder: str | None = None
		if presented:
			try:
				holder = auth.resolve_anonymous(presented).subject_ref
			except AssertionError:
				holder = None
		if holder is None and not auth.claim_subject(req.subject_ref):
			raise HTTPException(
				status_code=403,
				detail='an anonymous subject may be reclaimed only with the token that subject holds')
		if holder is not None and holder != req.subject_ref:
			raise HTTPException(
				status_code=403,
				detail='the token presented names a different subject')
		if presented:
			await auth.revoke(presented)
		token = await auth.issue_anonymous(req.subject_ref)
		return token.model_dump(mode='json')

	@app.post('/auth/pkce/authorize')
	async def auth_pkce_authorize(req: PKCEStart) -> dict[str, str]:
		try:
			authz = auth.start_pkce(req)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'authorization_code': authz.authorization_code, 'state': authz.state, 'redirect_uri': authz.redirect_uri}

	@app.post('/auth/pkce/token')
	async def auth_pkce_token(req: PKCETokenRequest, role: RBACRole) -> dict[str, object]:
		try:
			token = auth.exchange_pkce(req, role)
		except AssertionError as exc:
			raise HTTPException(status_code=401, detail=str(exc)) from exc
		return token.model_dump(mode='json')

	@app.post('/auth/revoke')
	async def auth_revoke(authorization: str | None = Header(default=None)) -> dict[str, int]:
		if not authorization or not authorization.lower().startswith('bearer '):
			raise HTTPException(status_code=401, detail='Bearer token required')
		return {'revoked': await auth.revoke(authorization.split(' ', 1)[1].strip())}

	@app.get('/auth/whoami')
	async def auth_whoami(authorization: str | None = Header(default=None)) -> dict[str, str]:
		subject, role = require_token(authorization)
		return {'subject_ref': subject, 'role': role.value}

	@app.post('/auth/staff/provision')
	async def auth_provision_staff(req: StaffProvision, _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""Issue a token for a role the app flow deliberately refuses (§17.5, §17.4).

		Guarded by the infrastructure scope, so only a sysadmin can mint a sysadmin or auditor.
		Without this the audit log had no reader: `auditor` is the only role scoped to
		`audit_logs`, and it could not be issued by any path.
		"""
		try:
			token = auth.provision_staff(req.operator_ref, RBACRole(req.role), req.registrar)
		except (AssertionError, ValueError) as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'access_token': token.access_token, 'role': token.role, 'scopes': token.scopes}

	@app.get('/health', response_model=HealthResponse)
	async def health() -> HealthResponse:
		assert registry.available(), 'registry must respond'
		return HealthResponse(status='ok', tier4=registry.tier4_active())

	@app.get('/features')
	async def features() -> list[dict[str, object]]:
		return [f.model_dump(mode='json') for f in registry.available()]

	@app.get('/features/taxonomy')
	async def features_taxonomy() -> dict[str, object]:
		"""§7.1's four tiers, §7.2's sixteen prefixes, and §7.3's map — the scheme the ids are drawn
		from, which nothing served.

		Open: it names no person and no number about one, and it is what a client reads to know why a
		feature id begins the way it does. The three crossings travel with it, because a taxonomy
		served without the places the spec's own tables disagree is a second document rather than a
		check."""
		return {
			'tiers': [t.model_dump(mode='json') for t in TIERS],
			'prefixes': [{'prefix': p, 'domain': d} for p, d in PREFIXES],
			'tier_map': [{'tier': tier, 'features': list(ids)} for tier, ids in TIER_MAP],
			'strategic_logic': STRATEGIC_LOGIC,
			'unmapped_features': registry.unmapped_features(),
			'spec_tier_mismatches': registry.spec_tier_mismatches(),
			'ebola_specific_mismatches': registry.ebola_specific_mismatches(),
			'divergences': TIER_DIVERGENCES,
		}

	@app.get('/brand')
	async def brand_section() -> dict[str, object]:
		"""§3: the vision, the two names, the twelve principles, the five non-goals, and the verdict
		of the brand check §20.2 declares.

		The check travels with the section rather than staying a function a caller has to know to
		import — §3.2's "It is not 'the Ebola app'" had a check named in `rollout.ANTIPATTERNS` and
		nothing running it, which is how a control that exists comes to look applied. It is open: it
		names no person and no number about one, and the principles are what a reviewer cites when
		refusing a feature."""
		return {
			'vision': VISION,
			'brand': BRAND.model_dump(mode='json'),
			'principles': [p.model_dump(mode='json') for p in PRINCIPLES],
			'non_goals': [g.value for g in NON_GOALS],
			# The anti-pattern's own check, run against the name this build serves. A rename that
			# puts a disease in the product name shows up here and at import, not in a review.
			'name_check': {
				'name': BRAND.public_name,
				'violations': brand_violations(BRAND.public_name),
				'clean': brand_is_clean(BRAND.public_name),
			},
		}

	@app.get('/problem')
	async def problem_statement(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§2: the seven citizen-layer gaps the product claims to close, and the five conditioned
		lessons it takes from comparable systems.

		Auditor-scoped, like the other build-evidence surfaces, because the answer is a statement about
		this repo — which gaps resolve, and which lesson's condition nothing honours. §2.3 lesson 3 is
		the finding: §SEC-001 carries `proximity_logging` with a scope and a revocation consequence,
		and no proximity path reads it, so the opt-in the lesson requires is not enforced anywhere.
		"""
		return {
			'gaps': gap_report().model_dump(mode='json'),
			'lessons': lesson_report().model_dump(mode='json'),
		}

	@app.get('/features/content')
	async def features_content(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§8–§12's labelled content lists, crossed against what the repo does.

		The registry gate asks whether a feature is *reachable*; this asks whether it does what its
		section says. Four sections are audited — the ones the section-number survey found named
		nowhere in the source — and the report carries the thirty-two it has not read, so a list of
		fifteen gaps cannot be mistaken for a complete audit.
		"""
		return content_report().model_dump(mode='json')

	@app.get('/features/claims')
	async def features_claims(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""The other half of the same audit: the sentences the sections print about their features.

		`/features/content` reads the labels whose body is a list. This reads the ones whose body is
		a claim, which had no gate at all until it did — and the two claims that were unread there are
		why §CHAN-2's single-report-backend sentence described a flow that did not exist and §AI-003's
		early-warning ledger had no channel feeding it.
		"""
		return claim_report().model_dump(mode='json')

	# --- triage ---
	@app.post('/triage/preliminary', response_model=TriageResult)
	async def triage_preliminary(inp: TriageInput, lang: str = 'en') -> TriageResult:
		# §AI-003's first bullet. The count is of fever triages, not of triages: a triage for a rash
		# in a fever outbreak is a different observation, and mixing them would let a cough campaign
		# raise a fever signal.
		if 'fever' in inp.symptoms:
			await _record_signal(ai, inp.county, 'fever_triage')
		return triage.assess(inp, lang)

	@app.post('/triage/evd', response_model=TriageResult)
	async def triage_evd(inp: TriageInput, subject: str | None = Depends(optional_subject())) -> TriageResult:
		"""§11.2's Ebola branch, including its Escalation.

		The notification is attempted only when the branch produced an Ebola suspicion, and the
		consent is read from §SEC-001's ledger rather than taken from the body — a caller cannot
		consent on the person's behalf by posting a boolean. When it does not go, the result says
		which of the two reasons it was, because "you declined to share" and "you are not a
		suspected case" are different things to be told and a client cannot tell them apart from a
		false.
		"""
		try:
			result = triage.assess_evd(inp)
		except PermissionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc
		if result.risk_level in (RiskLevel.high_ebola_suspicion, RiskLevel.emergency):
			notification = (triage.notify_county_rrt(inp, result, subject)
			                if subject is not None else None)
			if notification is not None:
				result.county_rrt_notified = True
				result.county_rrt_note = (
					'The county rapid response team has been told, because you agreed to share '
					'your health information with health authorities.'
				)
			else:
				result.county_rrt_note = (
					'Your result was not shared with the county team. You have not agreed to '
					'share your health information with health authorities, or no county was given. '
					'You can change that in your privacy settings, or call 719 yourself.'
				)
		return result

	@app.get('/triage/rrt/{county}')
	async def triage_rrt(county: str, _subject: str = Depends(require_scope('assigned', purpose='outbreak_surveillance'))) -> list[dict[str, object]]:
		"""What the county rapid response team reads — §11.2's Escalation, from their side."""
		return [n.model_dump(mode='json') for n in triage.rrt_notifications(county)]

	@app.post('/triage/diary')
	async def triage_diary(entry: DiaryEntry, _subject: str = Depends(require_self())) -> dict[str, bool]:
		await triage.diary_append(entry)
		return {'accepted': True}

	@app.get('/triage/{ref}/diary')
	async def triage_diary_list(ref: str, _subject: str = Depends(require_self(lambda r: r.path_params['ref']))) -> list[dict[str, object]]:
		return [e.model_dump(mode='json') for e in triage.diary(ref)]

	@app.get('/triage/{ref}/diary/trend')
	async def triage_diary_trend(ref: str, _subject: str = Depends(require_self(lambda r: r.path_params['ref']))) -> dict[str, object]:
		"""§TRI-002's "trend view: is this getting better or worse?" — read from the entries, not asked."""
		return triage.diary_trend(ref).model_dump(mode='json')

	@app.get('/triage/{ref}/diary/escalation')
	async def triage_diary_escalation(ref: str, _subject: str = Depends(require_self(lambda r: r.path_params['ref']))) -> dict[str, object] | None:
		"""§TRI-002's "automatic escalation if new red flags are logged".

		A `null` body is the answer when nothing is new, and it is a deliberate one: the client
		renders an escalation only when there is one, and returning a low-risk triage result here
		would put a triage answer on the screen where the section asks for silence.
		"""
		result = triage.diary_escalation(ref)
		return result.model_dump(mode='json') if result else None

	@app.get('/triage/{ref}/diary/export')
	async def triage_diary_export(ref: str, _subject: str = Depends(require_self(lambda r: r.path_params['ref']))) -> dict[str, object]:
		"""§TRI-002's "exportable summary for a clinician" — the text a person hands over."""
		return triage.diary_export(ref).model_dump(mode='json')

	@app.get('/triage/{ref}/diary/prompt')
	async def triage_diary_prompt(ref: str, day: int, opted_in: bool = False,
			_subject: str = Depends(require_self(lambda r: r.path_params['ref']))) -> dict[str, object] | None:
		"""§TRI-002's daily prompt. `null` when the person did not opt in — the section writes the
		opt-in into the Feature, so a declined prompt is not a prompt."""
		prompt = triage.diary_prompt(ref, day, opted_in)
		return prompt.model_dump(mode='json') if prompt else None

	# --- sensors (derived metrics only; tier4 gated) ---
	@app.post('/sensors/breath/estimate')
	async def sensors_breath(req: BreathEstimateRequest, _subject: str = Depends(require_self())) -> dict[str, object]:
		"""Estimate a respiration rate from a motion series and store the derived value.

		The reading is a personal metric, so it is bound to the caller's own subject and the tier-4
		gate applies exactly as it does to `/sensors/ingest` — this route previously wrote to a
		hardcoded `'U1'` with no token, which both misattributed the reading and let an unguarded
		caller turn respiration sensing on while the outbreak response was dormant.
		"""
		rate = estimate_breath_rate(req.series, req.fps)
		try:
			verdict = await sensors.ingest(SenseIngest(kind=SenseKind.respiration, subject_ref=req.subject_ref, value=rate, county='Nairobi'))
		except PermissionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc
		return {'rate_bpm': rate, **verdict.model_dump(mode='json')}

	@app.post('/sensors/ingest')
	async def sensors_ingest(inp: SenseIngest, _subject: str = Depends(require_self())) -> dict[str, object]:
		"""Take a derived reading and return the verdict §14 obliges the app to show beside it.

		The verdict alone would be a number presented as a measurement. §14.5 requires the known
		accuracy limitations be disclosed, so the response carries the disclosure, the limitations
		and a confidence that reflects the reading's signal quality — "where signal quality permits"
		is §14.5's own hedge, and it is enforced here rather than assumed of the client.
		"""
		try:
			return (await sensors.qualified_verdict(inp)).model_dump(mode='json')
		except PermissionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc

	@app.get('/sensors/accuracy')
	async def sensors_accuracy() -> dict[str, object]:
		"""§14's accuracy statements and the disclosures they oblige, for the client to show.

		Public: it names no person and no reading. It is the text a person needs *before* trusting
		a number, which is the point §14.5 makes about disclosure being an ethical requirement.
		"""
		return {
			'claims': [a.model_dump(mode='json') for a in sensors.accuracy_claims()],
			'undisclosed_limitations': sensors.undisclosed_limitations(),
		}

	# §13.1's capability matrix. The rows name no person and no reading, so the matrix is public —
	# a prospective user deciding whether the app suits their handset is exactly who it is for. The
	# audit view is evidence about the build, so it takes the auditor's scope like its siblings.
	@app.get('/sensors/capabilities')
	async def sensors_capabilities() -> dict[str, object]:
		return {'sensors': sensors.capabilities(), 'platforms': {
			p: sensors.absent_on(p) for p in ('android', 'ios')
		}}

	@app.get('/sensors/coverage')
	async def sensors_coverage(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""Whether §13.1 and §13.2 agree, and whether every sensor row cites a feature that exists.

		Two ways the tables can disagree, both silent without this: a sensor that can be absent with
		no fallback excludes a user, and a sensor row citing an unbuilt feature describes hardware
		acquired for a capability nobody shipped. A third is reported rather than repaired:
		`sensor_feature_disagreements` crosses §11.6's feature→sensor table against §13.1's and names
		the places the two sections contradict each other, which is a spec question and not one the
		code may answer by choosing.
		"""
		return {
			'missing_fallbacks': sensors.missing_fallbacks(),
			'unregistered_sensor_features': sensors.unregistered_sensor_features(),
			'sensor_feature_disagreements': sensors.sensor_feature_disagreements(),
			'raw_streams_retained': sensors.raw_streams_retained(),
			'sensor_count': len(sensors.sensors()),
			'external_device': sensors.external_device_gap().model_dump(mode='json'),
		}

	# --- §SENS-010 tag-based workflows ---
	# One binding, four targets, plus §LOC-004's check-in which owns its own tap. A tag holds the
	# target's id and never the person's, so a wristband that is lost leaks a bed number rather than
	# a patient.
	@app.post('/sensors/tags')
	async def tag_bind(tag: Tag, _subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, object]:
		"""Bind a tag to the thing it names. Registering hardware is a county-team action, the same
		scope §LOC-004's `register_checkin_point` takes, because a tag bound by anyone is a tag an
		attacker binds to a medicine package."""
		try:
			return tags.bind(tag).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=409, detail=str(exc)) from exc

	@app.delete('/sensors/tags/{tag_id}')
	async def tag_unbind(tag_id: str, _subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, bool]:
		tags.unbind(tag_id)
		return {'unbound': True}

	@app.get('/sensors/tags/{tag_id}')
	async def tag_resolve(tag_id: str) -> dict[str, object]:
		"""What one tap answers. Open, because a person holding a phone at a bedside is the caller and
		a tap that needs an account is a tap nobody makes — the answer carries the target's label and
		its opaque id, and nothing about any person."""
		return tags.resolve(tag_id).model_dump(mode='json')

	@app.post('/sensors/tags/{tag_id}/tap')
	async def tag_tap(tag_id: str, at_iso: str = Body(...), worker_ref: str | None = Body(None),
	                  _subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:
		"""Record a tap. A PPE station log names the worker because §COM-101 states it as
		occupational; every other target is about the object, and `tap` asserts the distinction
		rather than trusting the caller to keep it.

		`names_subject=False`: the tap is about the *tag*, not about a person, and the subject the
		reading is filed under is the token's own. With the default the guard demanded a
		`subject_ref` the catalogue does not offer — no form draws it, because there is nothing for a
		person to type — so the action 422'd on a field the client was never given.
		"""
		try:
			reading: TagReading = tags.tap(tag_id, at_iso, worker_ref)
		except AssertionError as exc:
			raise HTTPException(status_code=400, detail=str(exc)) from exc
		return reading.model_dump(mode='json')

	@app.get('/sensors/tags/{tag_id}/readings')
	async def tag_readings(tag_id: str, _subject: str = Depends(require_scope('audit_logs'))) -> list[dict[str, object]]:
		return [r.model_dump(mode='json') for r in tags.readings() if r.tag_id == tag_id]

	@app.get('/sensors/tag-coverage')
	async def tag_coverage(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§SENS-010's five applications and which module carries each, so the section's coverage is
		read off the running object rather than asserted in a table."""
		return tags.coverage()

	@app.post('/sensors/equipment')
	async def equipment_add(asset_ref: str = Body(...), label: str = Body(...), status: str = Body('in_service'),
	                        _subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, bool]:
		try:
			tags.equipment.add(asset_ref, label, status)
		except AssertionError as exc:
			raise HTTPException(status_code=400, detail=str(exc)) from exc
		return {'ok': True}

	@app.post('/sensors/equipment/{asset_ref}/move')
	async def equipment_move(asset_ref: str, station: str = Body(..., embed=True),
	                         _subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, bool]:
		try:
			tags.equipment.move(asset_ref, station)
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc
		return {'ok': True}

	# The asset list is the deployment's inventory, not a bedside answer: a citizen tapping a tag
	# learns what that tag is from `GET /sensors/tags/{tag_id}`, while the whole register is the
	# county health team's — the same scope the two writes above take. Serving it openly would hand
	# anyone the layout of every ventilator and station in the county.
	@app.get('/sensors/equipment')
	async def equipment_list(status: str | None = None,
	                         _subject: str = Depends(require_scope('county_aggregate'))) -> list[dict[str, str]]:
		return tags.equipment.assets(status)

	# --- facilities ---
	# The facility registry is what every locator screen reads. An anonymous caller could add a
	# facility to it, and the nearest-facility answer changed for everyone. §17.4's
	# `county_aggregate` is the county health team's scope, which is who maintains the registry.
	@app.post('/facilities')
	async def facility_upsert(fac: Facility, _subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, bool]:
		await facilities.upsert(fac)
		return {'ok': True}

	@app.post('/facilities/nearest')
	async def facility_nearest(req: NearestRequest) -> list[dict[str, object]]:
		return [{'facility': f.model_dump(mode='json'), 'km': round(km, 2)} for f, km in facilities.nearest(req)]

	@app.post('/facilities/find')
	async def facility_find(req: NearestRequest) -> dict[str, object]:
		"""§FND-001's finder and §FND-002's capacity screen.

		`unanswered` is served alongside the results, the same contract `/places/find` keeps: a
		filter whose dimension nothing published is named rather than applied, so the screen can say
		"cost unknown" instead of showing a shorter list that reads as an answer.
		"""
		found, unanswered = facilities.find(req)
		# §AI-003's third bullet: a finder search that names a symptom. The bullet is about searches
		# for a *symptom* — "nearest clinic" is not a signal and "nearest clinic for a fever" is — so
		# the query is matched against the same vocabulary the triage symptom list uses.
		if _names_a_symptom(req.query):
			await _record_signal(ai, req.county, 'facility_search')
		return {
			'results': [{'facility': f.model_dump(mode='json'), 'km': round(km, 2)} for f, km in found],
			'unanswered': unanswered,
		}

	@app.get('/facilities/offline-bundle')
	async def facility_offline_bundle(
		lat: float, lon: float, county: str | None = None,
	) -> list[OfflineFacility]:
		"""§FND-001's offline cache: the facilities within 50 km of the home area, plus the home
		county's own. Public because the client fetches it before it has any use for the network."""
		return facilities.offline_bundle(lat, lon, county)

	@app.post('/facilities/{facility_id}/reports')
	async def facility_report(facility_id: str, report: FacilityReportRequest,
	                          reporter: str | None = Depends(optional_subject())) -> dict[str, object]:
		"""§FND-001's "Recent user reports". The reporter is the authenticated subject when there is
		one and is never a name — the feed is on a public screen.

		The subject comes from the token and not from the body. It used to come from the body, which
		meant the feed published whatever reference the caller typed — including a stranger's, since
		nothing checked it against the token. §SEC-004's optional pseudonymous profile is what turns
		that reference into a rotating handle before it reaches the screen; a caller with no token is
		published anonymously rather than refused, which is §FND-001's ordinary case.
		"""
		try:
			created = await facilities.report(facility_id, report.text, reporter)
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc
		return created.model_dump(mode='json')

	@app.get('/facilities/{facility_id}/reports')
	async def facility_reports(facility_id: str, limit: int = 5) -> list[dict[str, object]]:
		return [r.model_dump(mode='json') for r in facilities.recent_reports(facility_id, limit)]

	@app.post('/facilities/{facility_id}/wait')
	async def facility_wait(facility_id: str, minutes: int = Body(..., embed=True)) -> dict[str, int]:
		try:
			return {'median_wait': await facilities.report_wait(facility_id, minutes)}
		except (AssertionError, KeyError) as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/facilities/{facility_id}/ed-status')
	async def facility_ed(facility_id: str) -> dict[str, str]:
		try:
			return {'status': facilities.ed_status(facility_id)}
		except AssertionError as exc:
			raise HTTPException(status_code=400, detail=str(exc)) from exc

	@app.get('/facilities/{facility_id}/slots')
	async def facility_slots(facility_id: str, day_iso: str) -> dict[str, object]:
		"""§FND-006's "View available slots at participating facilities". Public: choosing a clinic
		is something a person does before they have decided to tell anyone who they are."""
		return facilities.slots(facility_id, day_iso).model_dump(mode='json')

	@app.post('/facilities/{facility_id}/slots')
	async def facility_publish_slot(facility_id: str, offer: SlotOffer,
			_subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, object]:
		"""What a participating facility publishes. The county health team's scope, because a slot
		on the public screen is the facility saying it will see people — the same class of claim as
		§FND-001's registry row, and the same scope that maintains it."""
		if offer.facility_id is not None and offer.facility_id != facility_id:
			raise HTTPException(status_code=422,
				detail=f'body names facility {offer.facility_id!r}, path names {facility_id!r}')
		try:
			return (await facilities.publish_slot(
				offer.model_copy(update={'facility_id': facility_id}))).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/facilities/{facility_id}/booking')
	async def facility_book(facility_id: str, booking: BookingRequest,
			subject: str | None = Depends(optional_subject())) -> Booking:
		"""§FND-006's "Book". The owner is the token's subject, never the body's.

		`optional_subject` rather than a guard, because booking an appointment is §FND-006's Tier-2
		feature and the whole point of it is that it works — requiring a token would put a login
		between a person and a clinic slot. But a booking filed *with* a token records the owner, and
		that is what makes the cancel below safe: the reference is short enough to read off a screen,
		so the token is the difference between an appointment that can be moved only by its owner and
		one anyone holding six characters can take.
		"""
		if not any(f.facility_id == facility_id for f in facilities.all_facilities()):
			raise HTTPException(status_code=404, detail='unknown facility')
		try:
			return await facilities.book(facility_id, booking.slot_iso, booking.booking_id, subject)
		except AssertionError as exc:
			raise HTTPException(status_code=409, detail=str(exc)) from exc

	@app.post('/facilities/booking/{booking_id}/reschedule')
	async def facility_reschedule(booking_id: str, change: BookingChange,
			subject: str | None = Depends(optional_subject())) -> Booking:
		"""§FND-006's "reschedule", owned by the token's subject (§17).

		A booking filed without a token has no owner and cannot be moved by presenting its reference:
		the route answers 403, not 404. The *same* 403 covers a reference that names nothing, and
		that is deliberate — a 404 for the unknown id and a 403 for the known-but-not-yours turns
		this route into an oracle for which six-character references exist, and the reference is
		short enough to read off a screen. The check is `owns`, which is the one place the relation
		is applied; a second implementation here would be a second rule.
		"""
		if not facilities.owns(booking_id, subject):
			raise HTTPException(status_code=403, detail='this appointment belongs to someone else')
		try:
			return await facilities.reschedule(booking_id, change.slot_iso)
		except AssertionError as exc:
			raise HTTPException(status_code=409, detail=str(exc)) from exc

	@app.post('/facilities/booking/{booking_id}/cancel')
	async def facility_cancel(booking_id: str,
			subject: str | None = Depends(optional_subject())) -> Booking:
		"""§FND-006's "cancel", on the same ownership rule and the same uniform 403 as the reschedule.

		A POST rather than a DELETE because the row survives: the queue behind it was numbered
		against it, and removing it would renumber people who did nothing. §17.1's "deletable at any
		time" is about a person's *data*, and this is a state a clinic reads — the appointment is
		released, which is what the person asked for.
		"""
		if not facilities.owns(booking_id, subject):
			raise HTTPException(status_code=403, detail='this appointment belongs to someone else')
		try:
			return await facilities.cancel(booking_id)
		except AssertionError as exc:
			raise HTTPException(status_code=409, detail=str(exc)) from exc

	# --- medicine ---
	@app.post('/medicine/verify')
	async def medicine_verify(req: VerifyRequest) -> dict[str, object]:
		return (await medicine.verify(req)).model_dump(mode='json')

	@app.post('/medicine/interactions')
	async def medicine_interactions(req: InteractionsRequest) -> dict[str, object]:
		return medicine.check_interactions(
			req.drugs, pregnant=req.pregnant, age_months=req.age_months,
			conditions=req.conditions).model_dump(mode='json')

	@app.post('/medicine/stock')
	async def medicine_stock(report: StockReport,
		authorization: str | None = Header(default=None)) -> dict[str, object]:
		"""§MED-004's one-tap availability report, with its Anti-gaming controls applied here.

		The clause names three: "Require location proximity to report. Weight reports by reporter
		reliability. Show report age clearly." Proximity is checked against the facility the report
		names when the client could place itself, and the refusal is a 422 rather than a silent
		drop — a report that vanished would look like a network fault to the person who filed it.
		A report with no geohash is accepted and recorded unweighted rather than refused: §13.2's
		`gps` fallback exists so a phone without a fix can still report, and refusing it would be
		the accessibility failure §ACC-001 is about.

		The reporter is taken from the token when the caller presents one, and the body's own
		`reported_by` is used only when it does not. The route is ungated — an emergency-adjacent
		write that must not fail for want of a token — so without this the identity behind
		"Weight reports by reporter reliability" would be whatever the client typed, and a reporter
		with a bad record could file the next report under a fresh name and start at the middle
		again. The weight is only a weight if the history it reads belongs to one reporter.
		"""
		if authorization:
			try:
				report = report.model_copy(update={'reported_by': require_token(authorization)[0]})
			except HTTPException:
				# An unreadable token is not a reason to refuse a stock report; it is a reason not
				# to believe the name attached to it.
				pass
		if not report.reported_by:
			raise HTTPException(status_code=422, detail='a stock report needs a reporter: sign in, or name one')
		if report.reporter_geohash:
			facility = next((f for f in facilities.all_facilities() if f.facility_id == report.facility_id), None)
			if facility is None:
				raise HTTPException(status_code=404, detail='unknown facility')
			if not medicine.within_proximity(report, facility, STOCK_REPORT_MAX_KM):
				raise HTTPException(status_code=422, detail='report from too far away to be about this facility')
		alert = await medicine.report_stock(report)
		out: dict[str, object] = {'ok': True}
		# §MED-004's "Alert when a previously out-of-stock medicine becomes available": the caller
		# learns about the transition in the same response, because it is the one thing that makes
		# a report worth filing.
		if alert is not None:
			out['restock_alert'] = alert.model_dump(mode='json')
		return out

	@app.get('/medicine/stock/search')
	async def medicine_stock_search(q: str, limit: int = 20, _subject: str = Depends(require_scope('self'))) -> list[dict[str, object]]:
		"""§MED-004's "Search for a medicine" — where a drug is, across facilities."""
		rows = medicine.search_stock(q, limit=max(1, min(limit, 100)))
		names = {f.facility_id: f.name for f in facilities.all_facilities()}
		return [{**a.model_dump(mode='json'), 'facility_name': names.get(a.facility_id)} for a in rows]

	@app.get('/medicine/stock/availability')
	async def medicine_stock_availability(drug: str, facility_id: str, _subject: str = Depends(require_scope('self'))) -> dict[str, object]:
		"""§MED-004's own example, renderable: "available at [pharmacy], 2 hours ago"."""
		row = medicine.availability_for(drug, facility_id)
		if row is None:
			raise HTTPException(status_code=404, detail='no reports for that medicine at that facility')
		facility = next((f for f in facilities.all_facilities() if f.facility_id == facility_id), None)
		return {**row.model_dump(mode='json'), 'facility_name': facility.name if facility else None}

	@app.get('/medicine/stock/alerts')
	async def medicine_stock_alerts(facility_id: str | None = None, _subject: str = Depends(require_scope('self'))) -> list[dict[str, object]]:
		"""§MED-004's restock alerts — the transition, not the state."""
		return [a.model_dump(mode='json') for a in medicine.restock_alerts(facility_id)]

	@app.get('/medicine/essential')
	async def medicine_essential() -> list[dict[str, object]]:
		"""§MED-004's essential-medicines list, as the section names it.

		Public and unguarded: it is a constant the section prints, and a client needs it before it
		can render "prioritised" — the ordering is the feature.
		"""
		return [m.model_dump(mode='json') for m in ESSENTIAL_MEDICINES]

	@app.post('/medicine/dose')
	async def medicine_dose(req: DoseRequest) -> dict[str, object]:
		# §AI-003's fourth bullet. A dose lookup names a drug by construction, so every one of these
		# is a medicine search; the locality is what makes it a signal rather than a total.
		await _record_signal(ai, req.county, 'medicine_search', req.drug)
		return medicine.dose(req).model_dump(mode='json')

	# --- emergency ---
	@app.post('/emergency/sos')
	async def emergency_sos(event: SOSEvent) -> dict[str, object]:
		return (await emergency.sos(event)).model_dump(mode='json')

	@app.post('/emergency/sos/arm')
	async def emergency_sos_arm(event: SOSEvent) -> dict[str, object]:
		"""§EMG-001's countdown, started. Ungated with `/emergency/sos` and for the same reason: an
		emergency must not wait for a token, and the arming call is the one a person makes while
		they can still cancel."""
		return emergency.arm(event).model_dump(mode='json')

	@app.post('/emergency/sos/{sos_id}/cancel')
	async def emergency_sos_cancel(sos_id: str) -> dict[str, object]:
		try:
			return emergency.cancel(sos_id).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=409, detail=str(exc)) from exc

	@app.post('/emergency/sos/{sos_id}/fire')
	async def emergency_sos_fire(sos_id: str) -> dict[str, object]:
		"""The countdown ran out. 409 when it was cancelled or never armed, so a client that fires a
		stale timer is told the alert did not go out rather than handed a receipt for one."""
		try:
			return (await emergency.fire(sos_id)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=409, detail=str(exc)) from exc

	@app.post('/emergency/fall')
	async def emergency_fall(samples: list[IMUSample]) -> dict[str, object]:
		return EmergencyService.fall(samples).model_dump(mode='json')

	@app.post('/emergency/card/qr')
	async def emergency_card(card: EmergencyCard) -> dict[str, str]:
		return {'qr': EmergencyService.card_qr(card)}

	# --- §EMG-001 emergency, continued -----------------------------------------------------------
	@app.get('/emergency/alert/{sos_id}')
	async def emergency_sos_state(sos_id: str) -> dict[str, object]:
		"""What became of one alert: armed, cancelled, or sent — and who it reached.

		Public and unguarded, like the rest of the emergency path. The identifier is a random one the
		server minted and only the caller's own device holds it, and a person who has just cancelled
		an alert must be able to see that they did. Serving it behind a token would put a login in
		front of the one screen where a person is checking whether help is coming.
		"""
		alert = emergency.armed(sos_id)
		if alert is None:
			raise HTTPException(status_code=404, detail='no such alert')
		body = alert.model_dump(mode='json')
		fired = emergency.fired(sos_id)
		body['dispatch'] = fired.model_dump(mode='json') if fired else None
		return body

	# --- info & records ---
	@app.get('/info/hotlines')
	async def info_hotlines(
		lang: str = 'en', now_ms: int | None = None, lat: float | None = None, lon: float | None = None,
		county: str | None = None,
	) -> dict[str, object]:
		"""§INF-006's directory, with §6.2.3's stamp on each entry and the ones this deployment lacks.

		`verified` is an assertion about a number, and one nobody can act on without knowing when it
		was last checked — so the age travels with it. `updated_line` is None for an entry that has
		never been verified, which is a fact a client should render rather than infer from silence.

		The section's fourth Content is "nearest facility", which is not a row but an answer about the
		caller's position, so it is composed only when `lat`/`lon` are given. The second and sixth —
		"county health office" and "CHW" — are answers about the caller's *county*, and are composed
		the same way from `county`. The four Features are served as `actions` on each row, rendered
		here rather than left to each client.
		"""
		directory = info.hotline_directory(now_ms, lang, lat, lon, places, county, chw)
		return directory.model_dump(mode='json')

	@app.post('/info/county-office')
	async def info_register_county_office(county: str, number: str,
			_subject: str = Depends(require_scope('infrastructure'))) -> dict[str, str]:
		"""Register a county health office's number (§INF-006's second Content).

		Infrastructure-scoped, matching `POST /info/dashboard/{county}`: a county office's published
		number is the county authority's fact, and the row it fills is one a caller may dial in an
		emergency. A citizen-scoped write here would let anyone put a number on a life-safety screen.
		"""
		try:
			return {'county': county, 'number': await info.register_county_office(county, number)}
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/info/dashboard/{county}')
	async def info_dashboard(county: str, lang: str = 'en', now_ms: int | None = None) -> dict[str, object]:
		"""§INF-001's county dashboard: all seven Displays, assembled, with §6.2.3's stamp.

		`updated_line` is None when the county has never been assessed. `dashboard()` answers an
		unknown county with a defaulted low-risk row so a client always has something to draw, and
		without the stamp that default is indistinguishable from an assessment someone made today —
		which is exactly the undated content §6.2.3 calls destructive.

		The section's fourth and fifth Displays — "active alerts and advisories" and "service status"
		— are §ALT-001's alert feed and §INF-007's status feed. They are read from those services
		rather than restated here, because they are the same facts on two screens and a second copy
		would be the one that goes stale. Both are county-filtered; the alerts are the *current* alert
		per kind, which is what `by_county` returns, not the feed's whole history.
		"""
		assembled = info.county_dashboard(
			county,
			[a.model_dump(mode='json') for a in alerts.by_county(county)],
			[s.model_dump(mode='json') for s in alerts.service_status(county)],
		)
		return assembled.served(info.dashboard_freshness(county, now_ms, lang))

	@app.post('/info/dashboard/{county}/cases')
	async def info_record_case_counts(county: str, counts: CaseCounts,
			_subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, object]:
		"""Record a county's case counts (§INF-001's second Display).

		`county_aggregate` rather than `infrastructure`: a case count is the county health team's own
		epidemiological report — the same scope that already guards `POST /surveillance/signal` and
		`POST /ai/hotspots` — whereas a risk *level* is what the authority publishes to the public and
		stays with the infrastructure scope that guards it.

		The path's `county` must match the body's. A route that took the county from the path and the
		rest from the body could file Bungoma's counts against Busia with nothing to catch it, and the
		mismatch would surface as a dashboard that contradicts the report it was built from.
		"""
		if counts.county != county:
			raise HTTPException(
				status_code=422,
				detail=f'body names county {counts.county!r}, path names {county!r}')
		try:
			row = await info.record_case_counts(counts)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {**row.model_dump(mode='json'), 'trend': row.trend}

	@app.post('/info/dashboard/{county}/sub-counties')
	async def info_record_sub_county(county: str, status: SubCountyStatus,
			_subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, object]:
		"""Record an affected sub-county (§INF-001's third Display).

		Same scope and same path/body agreement as the case counts, for the same reasons. The model
		refuses an "affected" sub-county carrying neither a case nor a named location, so a place with
		nothing to report cannot be put on the dashboard by a caller who is filling a table.
		"""
		if status.county != county:
			raise HTTPException(
				status_code=422,
				detail=f'body names county {status.county!r}, path names {county!r}')
		try:
			row = await info.record_sub_county(status)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return row.model_dump(mode='json')

	@app.post('/info/dashboard/{county}')
	async def info_set_dashboard(county: str, risk_level: str = Body(...), active_signals: int = Body(...),
			bulletin: str = Body(...), source: str = Body(''), at_ms: int | None = Body(None),
			_subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""Record a county's risk level (§INF-001).

		Without this the dashboard route could only ever answer its default, so §8.5's "Current
		outbreak status by county" and §6.2.3's "Last updated timestamp" were both unreachable — a
		served surface with no way to put a fact behind it. Operator-scoped: a risk level is what the
		county health authority publishes, not something a citizen asserts.

		`at_ms` is the caller's clock, matching every other stamp in this codebase.
		"""
		if risk_level not in ('low', 'moderate', 'high'):
			raise HTTPException(status_code=422, detail=f'unknown risk level {risk_level!r}')
		risk = await info.set_county_risk(
			CountyRisk(county=county, risk_level=risk_level, active_signals=active_signals,
			           bulletin=bulletin, source=source), at_ms)
		return {**risk.model_dump(mode='json'),
		        'updated_line': info.dashboard_freshness(county, at_ms, 'en')}

	@app.get('/info/library')
	async def info_library(lang: str = 'en', now_ms: int | None = None, tag: str | None = None,
			q: str | None = None) -> list[dict[str, object]]:
		"""§6.2 content library (INF-003/004/008/009/010/015), served by language.

		Served as {slug,title,body,harmony_tag} — never `item_id`, whose seed values embed spec codes
		(`INF-003-en`) that must not reach a screen. The slug is what a client keys on.

		`tag` narrows to one harmony tag, which is what §INF-002's fourth and fifth Entry questions
		open: "I want to protect my family" is the Ebola library and "I heard something — is it true?"
		is the myth-busting corpus. Without the filter those entries would open the whole library and
		leave the reader to find the section themselves, which is not what an entry question is for.

		`q` is §INF-004's Search. It matches over the claim as well as the title and body, which is
		the half that needed the corpus to carry a claim at all: a person typing "salt water" is
		searching for a rumour, and while the rumour lived as prose inside `body` it was findable by
		accident rather than on purpose. `claim` and `source` travel on every row that has them, so a
		client renders §INF-004's "Rumour: … Fact: … Source: …" from fields rather than by parsing
		the body. Both are null on a non-myth row, which is the honest shape: a first-aid card has no
		rumour to refute.

		§INF-004's "Shareable as a card" travels as `share_card` and `share_url`, rendered here for
		the reason §INF-003's renditions are: §5.4's single content repository puts this answer on
		WhatsApp, USSD and SMS, and only one of those can compose a forwardable message. The card is
		§INF-004's own three-line Format for a myth and the title plus body for anything else.

		§6.2.4 withholds a life-safety item whose other required language is missing, in *both*
		languages — publishing it English-only is the act the section forbids, and `library()` is
		where publishing happens. `answers_rank` is served so a client can lead with §6.1's own
		demand order rather than listing the corpus alphabetically.

		§6.2.3's `updated_line` is "Updated 2 hours ago", built here rather than stored and rather
		than left to the client: §5.4's single content repository puts this same answer on WhatsApp,
		USSD and SMS, and only one of those can do date arithmetic. `updated_iso` travels beside it
		because a relative age is unreadable the moment the page is cached offline (§16.4) and an
		instant is unreadable at a glance. `now_ms` is the caller's clock, for the reason `/location/check`
		takes one — a clock nobody can move is a clock nobody can test.

		§INF-003's and §INF-008's Format cells travel as `renditions` on the item they are renditions
		of: a list of `{format, media_ref, title}`. They are not separate list entries — a rendition
		has no prose of its own, so an entry for one would be a blank card beside the article it
		illustrates — and they are not a route of their own either, because a client that had to ask
		twice would render the article before knowing it had an audio version. `media_ref` is the file;
		the client fetches it, which is why no bytes are in this payload.
		"""
		items = info.search(q, lang, tag=tag) if q else info.library(lang)
		if q is None and tag is not None:
			items = [c for c in items if c.harmony_tag == tag]
		return [
			{'slug': c.slug, 'title': c.title, 'body': c.body, 'harmony_tag': c.harmony_tag or '',
			 'lang': c.lang, 'answers_rank': c.answers_rank, 'format': c.format.value,
			 'claim': c.claim, 'source': c.source,
			 'share_card': c.share_card, 'share_url': c.share_url,
			 'renditions': [
				 {'format': r.format.value, 'media_ref': r.media_ref, 'title': r.title}
				 for r in info.renditions_of(c.slug)
			 ],
			 **info.item_freshness(c, now_ms, lang).model_dump(mode='json')}
			for c in items
		]

	@app.get('/info/library/categories')
	async def info_library_categories(lang: str = 'en') -> list[dict[str, object]]:
		"""§INF-004's "Browse by category": the tags the library can be browsed by, with counts.

		A route of its own rather than a key on `/info/library`, because a browse screen and a list
		screen are different requests: a client opening the library wants the items, and one drawing
		a category chooser wants the categories, and folding the facets into every library response
		would make every list request carry a count it does not render.

		Counts are of served items — read through `library()`, not off the store — so a category is
		offered only when something is behind it. A browse screen that opens onto an empty list
		because the facet counted a draft is the failure the count exists to prevent.
		"""
		return info.facets(lang)

	@app.get('/info/myths')
	async def info_myths(lang: str = 'en', q: str | None = None) -> list[dict[str, object]]:
		"""§INF-004's myth library: the rumour, the correction and the authority, as three fields.

		Every row carries all three, which is the section's Format. Served as its own route rather
		than as a `tag=mythbusting` filter on `/info/library` because the shape is different: a
		library row is prose and a myth row is a claim with a correction beside it, and a client that
		had to branch on whether `claim` is null to decide which to render is a client doing the
		server's job. `q` searches the same corpus `/info/library?q=` does, through the same
		implementation, so the two cannot disagree about what matches.

		No `now_ms`: a myth is not a feed item and the section prints no freshness line for it. The
		correction's own `drafted_on` travels instead, which is what makes it weighable.
		"""
		return [
			{'slug': c.slug, 'title': c.title, 'claim': c.claim, 'fact': c.body, 'source': c.source,
			 'lang': c.lang, 'answers_rank': c.answers_rank, 'harmony_tag': c.harmony_tag or '',
			 'share_card': c.share_card, 'share_url': c.share_url,
			 'category': (categories_of(topic_for_slug(c.slug, c.lang) or '') or [None])[0]}
			for c in info.myths(lang, q)
		]


	@app.get('/info/questions')
	async def info_questions() -> list[dict[str, object]]:
		"""§6.1's ten questions in the section's own order.

		§6.1 is explicit that the order is "by real demand, not by what health authorities want to
		publish", so the ordering is the section's contribution and is served rather than left to a
		client to guess. `life_safety` is what §6.2.4's language rule applies to.
		"""
		return [q.model_dump(mode='json') for q in info.ranked_questions()]

	@app.post('/info/content')
	async def info_upsert_content(item: ContentItem, _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, bool]:
		"""Draft or correct a library item (§6.2 harmonisation, §6.5 governance).

		The `harmony_tag` is required here because §6.2 serves nothing un-harmonised, and the §6.5
		governance fields — owner, reviewer, review date, version — are required by the model itself,
		so an item with nobody accountable for it cannot be constructed at all. Writing an item does
		not publish it: an item lands at the stage the body names, and only `published` is served.

		§17.4 defines eight data-access roles and none of them owns content, so this rides the
		operations scope rather than inventing a ninth role the spec's table does not have.

		§6.2 is enforced here rather than left to the reviewer: an item that stigmatises the person
		it describes, carries a spec section reference, or cannot be sent as a plain SMS is refused
		with the verdicts, so the drafting screen can say what to fix. The long-sentence flag is a
		`review` verdict and does not block — §6.2.10 is a design intent, and a burial protocol may
		legitimately run long.
		"""
		if not item.harmony_tag:
			raise HTTPException(status_code=422, detail='content must carry a harmony tag before it is served')
		failures = [v.model_dump(mode='json') for v in info.content_verdicts(item)]
		if failures:
			raise HTTPException(status_code=422, detail={'content_principles': failures})
		# §6.2.4: a life-safety message may not be published in one language alone. Refused at the
		# moment of publishing, which is the only point where the missing translation can still be
		# written — and refused with the reason the section gives, so the author knows why this item
		# and not the last one.
		untranslated = info.life_safety_refusal(item)
		if untranslated:
			raise HTTPException(status_code=422, detail={'content_language': untranslated})
		try:
			await info.upsert_content(item)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'ok': True}

	@app.post('/info/content/{item_id}/advance')
	async def info_content_advance(item_id: str, to: str = Body(..., embed=True),
			_subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""Move an item one step along §6.5's workflow, or retire it to `archived`.

		One step, so a draft cannot be marked published without the clinical review, translation,
		back-translation and community validation the section puts before it. `archived` is reachable
		from any stage: retiring something wrong should not require walking it forward first.
		"""
		from afya.info.views import ContentStage
		try:
			stage = ContentStage(to)
		except ValueError as exc:
			raise HTTPException(status_code=422, detail=f'unknown content stage {to!r}') from exc
		# §6.2.4 bites at the step that publishes, not only at the write. An item drafted in English
		# and walked through §6.5's workflow reaches `published` here, so a check on the POST alone
		# would be a gate on the door beside the one everybody uses.
		if stage is ContentStage.published:
			current = next((c for c in info.all_items() if c.item_id == item_id), None)
			if current is None:
				raise HTTPException(status_code=422, detail=f'no content item {item_id}')
			untranslated = info.life_safety_refusal(current.model_copy(update={'stage': stage}))
			if untranslated:
				raise HTTPException(status_code=422, detail={'content_language': untranslated})
		try:
			item = info.advance(item_id, stage)
		except (AssertionError, KeyError) as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'item_id': item.item_id, 'stage': item.stage.value, 'version': item.version}

	@app.post('/info/content/back-translation')
	async def info_record_back_translation(record: BackTranslation, at_ms: int | None = None,
			_subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""§6.5's back-translation step: record the rendered text and who produced it.

		The step is a check only if it leaves evidence, and the evidence is two things: the text
		someone who had not seen the source produced from the translation, and their name. Recording
		it does not move the item — the stage is moved by `/advance`, which refuses to enter
		`back_translation` without this record. Writing and moving are separate so the record can be
		corrected without walking the item back, and so the gate reads a fact rather than a parameter.
		"""
		try:
			state = info.record_back_translation(record, at_ms)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return state.model_dump(mode='json')

	@app.post('/info/content/community-validation')
	async def info_record_community_validation(record: CommunityValidation, at_ms: int | None = None,
			_subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""§6.5's community validation step: who took the text to the community, and what they said.

		Refused when no back-translation is on file, because the community is shown the text the
		back-translation produced — validating before it exists is validating nothing. The validator
		may be neither the translator nor the back-translator: a step authored by the person whose work
		it checks is the step's name without the step.
		"""
		try:
			state = info.record_community_validation(record, at_ms)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return state.model_dump(mode='json')

	@app.get('/info/content/localisation')
	async def info_content_localisation(_subject: str = Depends(require_scope('audit_logs'))) -> list[dict[str, object]]:
		"""§6.5's localisation workflow as it stands, item by item.

		Auditor-scoped for the same reason the escalation log is: the person who walked an item
		through the workflow is not the person who checks it was walked, and a reviewer who can move
		the item can make their own evidence look complete.
		"""
		return [s.model_dump(mode='json') for s in info.localisation_review()]

	@app.post('/info/content/errors')
	async def info_report_error(error: ContentError, at_ms: int | None = None,
			_subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""§6.5's escalation: report a published item as wrong, and broadcast the correction.

		Two things happen and both are required by the section's own sentence. The item is **retired**
		— every published item sharing its slug, so the Swahili translation goes with the English —
		and, when the item is life-safety, the correction is **broadcast**: it is published to the
		alert feed §6.4's own corrections use, which the socket fans out from.

		`affects_safety` is not a parameter. §6.5 says "any content error affecting safety", and the
		only honest reading of that is §6.1's life-safety set, the same one §6.2.4 keys on — the
		person retiring content under pressure is the last one to mark their own item as
		safety-affecting. A non-safety item is archived and escalates nothing.

		The correction is refused if it is missing a language §6.2.4 requires, for the same reason
		`/info/content` refuses an English-only life-safety item: publishing it *is* the act the
		section forbids, and a correction half the audience cannot read is not a correction.
		"""
		from afya.alerting.views import FeedItem
		try:
			escalated = await info.report_error(error, at_ms)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		out = escalated.model_dump(mode='json')
		if not escalated.broadcast_required:
			out['broadcast'] = False
			return out
		if escalated.missing_langs:
			raise HTTPException(status_code=422, detail={
				'content_language': (
					f'§6.2.4: this is a life-safety correction, so it cannot go out in '
					f'{", ".join(escalated.correction_langs)} alone. Missing: '
					f'{", ".join(escalated.missing_langs)}.'
				),
				'escalation': out,
			})
		# §6.4 step 5: "All channels simultaneously". The durable feed is written first and the
		# socket fans out from it, so a client offline when the correction fired still finds it.
		# The headline is the retired item's own title: a correction to "Boil drinking water" that
		# arrives headlined by a slug is a correction to nothing a reader can recognise.
		item = info.by_slug(escalated.slug)
		feed_item = FeedItem(
			item_id=f'COR-{escalated.error_id}', category=CORRECTION_FEED_CATEGORY,
			headline=(item.title if item else escalated.slug)[:120],
			body=error.correction['en'][:600],
			source='MoH Health Promotion Unit', verified=True,
			published_iso=instant_iso(clock_ms()),
		)
		stored = await alerting.publish(feed_item)
		out['broadcast'] = True
		out['feed_item_id'] = stored.item_id
		out['delivered_realtime'] = realtime.publish(stored)
		return out

	@app.get('/info/content/errors')
	async def info_content_errors(now_ms: int | None = None,
			_subject: str = Depends(require_scope('audit_logs'))) -> list[dict[str, object]]:
		"""§6.5's escalation log: every content error found, and where each one stands.

		Auditor-scoped like the rest of the governance views. Each row is recomputed against the
		clock it is asked at, so `review_overdue` is a fact about now rather than about when the row
		was written — the same discipline §24.8's breach deadline follows.
		"""
		stamp = now_ms if now_ms is not None else clock_ms()
		return [info.escalation(e.error_id, stamp).model_dump(mode='json') for e in info.errors()]

	@app.get('/info/health-education')
	async def info_health_education(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§8.5's library and §10.5's three features — the topics and formats each names, and which the
		corpus answers.

		Auditor-scoped like the other evidence views: it reports what the corpus is missing, which is
		a content owner's business rather than a client's. `gaps` and `missing_formats` are the
		finding — "first-aid items are in the health library corpus" is true of the one item that
		exists and says nothing about the other ten topics §INF-009 names, and a library of articles
		delivers none of the audio and video versions §INF-003 asks for.
		"""
		items = info.all_items()
		return {
			'coverage': health_education.report(items),
			'ebola_topics': list(health_education.EBOLA_TOPICS),
			'ebola_formats': list(health_education.EBOLA_FORMATS),
			'health_tip_topics': list(health_education.HEALTH_TIP_TOPICS),
			'first_aid_topics': list(health_education.FIRST_AID_TOPICS),
			'burial_content': list(health_education.BURIAL_CONTENT),
			'sensitivity_reviewers': list(health_education.SENSITIVITY_REVIEWERS),
			'first_aid_offline': health_education.first_aid_is_offline(),
			'first_aid_illustrations': health_education.illustrated(items),
			'over_length': health_education.over_length(items),
		}

	@app.get('/info/content/governance')
	async def info_content_governance(today_iso: str = '2026-10-10', regime: str = 'steady',
			_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§6.5 content governance: who owns and reviewed each item, at what version and stage, and
		which published items are past their review cycle.

		Auditor-scoped, like the other evidence views. `stale` is the §6.5 staleness audit as a
		date rather than a monthly intention — the item served longest ago is the one nobody has
		looked at since, which is exactly what the section exists to catch. `content_principles` is
		§6.2's own audit over the same corpus, so a stigmatising sentence is visible to the reviewer
		whether it was caught at drafting time or predates the check."""
		if regime not in ('outbreak', 'steady'):
			raise HTTPException(status_code=422, detail=f'unknown review regime {regime!r}')
		items = [
			{
				'item_id': c.item_id, 'slug': c.slug, 'lang': c.lang, 'stage': c.stage.value,
				'owner': c.owner, 'reviewer': c.reviewer, 'reviewed_on_iso': c.reviewed_on_iso,
				'version': c.version, 'updated_at_ms': c.updated_at_ms,
			}
			for c in sorted(info.all_items(), key=lambda c: c.item_id)
		]
		return {
			'workflow': [s.value for s in WORKFLOW],
			# §6.5's arrow is one sequence read across the two rows of a slug, so the governance view
			# names both walks. A reader who sees only the flat list cannot tell why the English row
			# has no translation step — and the flat list alone is what made `advance` walk every row
			# through a translation of itself.
			'workflow_by_lang': {
				lang: [s.value for s in workflow_for(lang)]
				for lang in dict.fromkeys(c.lang for c in info.all_items())
			},
			'items': items,
			'stale': info.stale(today_iso, regime),
			'regime': regime,
			'cadence_days': info.cadence_days(regime),
			# §6.2.4's audit: published life-safety items held back for a missing language. Named by
			# slug, because a gate that withheld content silently would be worse than the English-only
			# message it prevents — the audience sees nothing and nobody is told why.
			'untranslated_life_safety': info.untranslated(),
			# §6.2.3's audit, the same shape for the same reason: an item held back for carrying no
			# timestamp is a gap the reviewer has to be able to see, or the withholding is silent.
			'undated': info.undated(),
			'content_principles': [
				{'surface': f.surface, 'verdicts': [v.model_dump(mode='json') for v in f.verdicts]}
				for f in info.library_audit() + info.tree_audit()
			],
		}

	@app.get('/info/entry-answers')
	async def info_entry_answers() -> list[dict[str, object]]:
		"""§INF-002's six Entry questions, as the menu the app opens on.

		Served rather than left to each client, for the same reason §INF-006's directory actions are:
		six screens that each decide for themselves what "I have a fever" opens is six places for the
		six to drift from the section. Ungated — the entries are a menu, and the walk behind three of
		them names no subject.
		"""
		return [e.model_dump(mode='json') for e in info.entry_answers()]

	@app.get('/info/decision-tree')
	async def info_decision_tree(answers: str = '', entry: str = 'root') -> dict[str, object]:
		"""§INF-002 "What Should I Do" decision tree.

		Without `answers` it returns the first question of the chosen entry; each subsequent call
		passes the answers so far, comma-separated as `y`/`n`, and returns either the next question or
		the leaf recommendation with the facility and hotline links the section's Output names. The
		answers are the caller's own symptoms, so no subject is named or needed.

		`entry` selects which of the section's Entry questions the walk started from. It defaults to
		the fever root, which is the walk that existed before the six entries were modelled; the
		household entry is a second root because it asks about a different person and a caller
		answering it against the fever tree would be told no action was needed.
		"""
		parsed: list[bool] = []
		for token in [t.strip().lower() for t in answers.split(',') if t.strip()]:
			if token not in ('y', 'n', 'yes', 'no', 'true', 'false'):
				raise HTTPException(status_code=422, detail=f'answer must be yes or no, not {token!r}')
			parsed.append(token in ('y', 'yes', 'true'))
		try:
			step = info.step(parsed, entry)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return step.model_dump(mode='json')

	@app.post('/records/member')
	async def records_member(member: WalletMember, _subject: str = Depends(require_self_or_guardian(_body_member, may_create=True))) -> dict[str, bool]:
		# A wallet write is bound to the token: the guardian recorded on the member must be the
		# caller, so one person cannot enrol a child into a wallet they do not own. Nothing owns a
		# member that does not exist yet, so the guard's ownership check is waived (`may_create`)
		# and the binding below is what makes the write safe.
		if member.guardian_ref is not None and member.guardian_ref != _subject:
			raise HTTPException(status_code=403, detail='a wallet member may only be added to your own wallet')
		if member.guardian_ref is None:
			member = member.model_copy(update={'guardian_ref': _subject})
		try:
			await records.add_member(member)
		except AssertionError as exc:
			raise HTTPException(status_code=400, detail=str(exc)) from exc
		return {'ok': True}

	@app.get('/records/{member_ref}/immunisation-gaps')
	async def records_gaps(member_ref: str, _subject: str = Depends(require_self_or_guardian(lambda r: r.path_params['member_ref']))) -> list[str]:
		try:
			records.assert_owns(_subject, member_ref)
			return records.immunisation_gaps(member_ref)
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.post('/records/growth')
	async def records_growth(rec: GrowthRecord, _subject: str = Depends(require_self_or_guardian(_body_member))) -> dict[str, object]:
		"""§REC-003's verdict, recorded and returned.

		This returned `growth_flag`, the one-word summary, which could not carry the two measurements
		the section names — head circumference and MUAC — nor the alert a MUAC category raises. The
		flag is still served inside the assessment's statuses, so a caller holding the word keeps it.
		"""
		try:
			records.assert_owns(_subject, rec.member_ref)
		except AssertionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc
		return (await records.record_growth(rec)).model_dump(mode='json')

	@app.post('/records/milestones')
	async def records_milestones(check: MilestoneCheck, _subject: str = Depends(require_self_or_guardian(_body_member))) -> dict[str, object]:
		"""§REC-003's milestone checklist, classified by Annex 9's ASSESS/CLASSIFY rules."""
		try:
			records.assert_owns(_subject, check.member_ref)
			return records.milestone_check(check).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=400, detail=str(exc)) from exc

	@app.get('/records/{member_ref}/milestones')
	async def records_milestones_for(member_ref: str, age_months: int = 0,
	                                 _subject: str = Depends(require_self_or_guardian(lambda r: r.path_params['member_ref']))) -> dict[str, object]:
		"""The checklist itself, for a caregiver to read before answering — nothing is recorded.

		Guarded like every other family route rather than left open: the checklist names the skills a
		child of a given age should have, and an unauthenticated route keyed on an age is a way to
		ask after a specific child's development without naming them.
		"""
		try:
			records.assert_owns(_subject, member_ref)
			return records.milestones_for(age_months).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/records/labs')
	async def records_add_lab(res: LabResult, _subject: str = Depends(require_self_or_guardian(_body_member))) -> dict[str, bool]:
		try:
			records.assert_owns(_subject, res.member_ref)
		except AssertionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc
		await records.add_lab(res)
		return {'ok': True}

	@app.get('/records/{ref}/labs')
	async def records_labs(ref: str, _subject: str = Depends(require_self_or_guardian(lambda r: r.path_params['ref']))) -> list[dict[str, object]]:
		# Lab results are personal data; the ref is a member of the caller's own wallet, not anyone's.
		# `reader=_subject` carries §17.6's last line to this second door: a lab result is also filed
		# as a wallet document, so filtering the document route alone would withhold a pregnancy test
		# there and serve it here.
		try:
			records.assert_owns(_subject, ref)
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc
		return [l.model_dump(mode='json') for l in records.labs(ref, reader=_subject)]

	@app.get('/records/{guardian_ref}/wallet')
	async def records_wallet(guardian_ref: str, _subject: str = Depends(require_self_or_guardian(lambda r: r.path_params['guardian_ref']))) -> dict[str, object]:
		try:
			records.assert_owns(_subject, guardian_ref)
			return records.wallet(guardian_ref)
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	# §9.2 REC-001's contents, as evidence rather than as a claim. Auditor-scoped: the report names
	# `module:attr` references and the one item nothing models, which is a fact about the build.
	@app.get('/records/wallet/contents')
	async def records_wallet_contents(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""Whether §9.2's eight wallet contents are carried, and whether the ten-profile cap is kept.

		The section lists eight documents a family wallet holds. All eight are carried now: seven had
		a model and the eighth, discharge summaries, is the `discharge` kind of `WalletDocument` —
		which is where the paper a facility hands a person gets filed. The report is still served
		auditor-scoped and still names each item's carrier, because the question it answers is what
		the build holds on the day it is asked, and a report that only ever agreed with itself would
		be worth nothing the next time a section gains an item.
		"""
		return records.wallet_contents().model_dump(mode='json')

	# --- §9.2/§10.1: the wallet's documents and the operations over them -------------------------

	@app.post('/records/documents')
	async def records_add_document(doc: WalletDocument, _subject: str = Depends(require_self_or_guardian(_body_member))) -> dict[str, object]:
		"""File a document in the wallet — §9.2's eight kinds, one envelope.

		This is where "photo capture and storage" lands: the client uploads the photograph through
		the existing evidence route, receives a reference, and files the document here with that
		reference as `media_ref`. The wallet stores the reference and the capture metadata and never
		the bytes, which is the same split `ContentItem.media_ref` uses for audio and video.
		"""
		try:
			await records.add_document(doc)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'ok': True, 'doc_id': doc.doc_id}

	@app.get('/records/{member_ref}/documents')
	async def records_documents(member_ref: str, kind: str | None = None,
	                            _subject: str = Depends(require_self_or_guardian(lambda r: r.path_params['member_ref']))) -> list[dict[str, object]]:
		"""One member's wallet documents, newest first, optionally narrowed to one of §9.2's kinds.

		`reader=_subject` is §17.6's last line at the door: a guardian reading an adolescent's record
		gets everything except her reproductive health documents. The filter is applied in
		`RecordsService.documents` rather than here, so this route and the timeline, search, export
		and backup cannot disagree about what a guardian may read.
		"""
		try:
			records.assert_owns(_subject, member_ref)
			kinds = [kind] if kind else None
			return [d.model_dump(mode='json')
			        for d in records.documents(member_ref, kinds, reader=_subject)]
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.get('/records/timeline')
	async def records_timeline(_subject: str = Depends(require_self(names_subject=False))) -> list[dict[str, object]]:
		"""§10.1's "Timeline view of all health events", across everyone the caller may read.

		Self-scoped rather than member-scoped: the timeline's whole content is the union across the
		wallet, and a caller who had to name a member to see their own family's history would not be
		looking at a timeline. Which members are included is decided by `owns`, per member.

		`names_subject=False` because there is no subject to name: the wallet is the caller's own, so
		a guard demanding `?subject_ref=` would be asking for a value that decides nothing and
		refusing every client that did not send one.
		"""
		return [e.model_dump(mode='json') for e in records.timeline(_subject)]

	@app.get('/records/search')
	async def records_search(q: str, _subject: str = Depends(require_self(names_subject=False))) -> list[dict[str, object]]:
		"""§REC-001's "Search", over every document the caller may read."""
		try:
			return [d.model_dump(mode='json') for d in records.search(_subject, q)]
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/records/share')
	async def records_share(grant: ShareGrant, _subject: str = Depends(require_self_or_guardian(_body_member))) -> dict[str, object]:
		"""§REC-001's secure link and §10.1's time-limited provider share, as one grant.

		The caller is recorded as the issuer rather than trusted to name themselves: a grant that
		said someone else issued it would attribute a disclosure to the wrong person, and §17.1's
		accountability is about who disclosed, not who typed.
		"""
		grant = grant.model_copy(update={'issued_by': _subject})
		try:
			await records.grant_share(grant)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'ok': True, 'grant_id': grant.grant_id, 'expires_iso': grant.expires_iso}

	@app.get('/records/{member_ref}/shares')
	async def records_shares(member_ref: str, _subject: str = Depends(require_self_or_guardian(lambda r: r.path_params['member_ref']))) -> list[dict[str, object]]:
		"""Every share issued over this member, live and expired — "who has seen my record"."""
		try:
			records.assert_owns(_subject, member_ref)
			return [g.model_dump(mode='json') for g in records.grants_for(member_ref)]
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.post('/records/share/{grant_id}/revoke')
	async def records_revoke_share(grant_id: str, _subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:
		"""Withdraw a share. §17.1: consent that cannot be taken back is not consent.

		The grant is looked up and checked against the caller before it is withdrawn, because a
		revocation that only needed a grant id would let anyone who guessed one switch off a share
		they are not party to — a denial of care with a §17.1 label on it.
		"""
		try:
			grant = records.grants_for_member(grant_id)
			records.assert_owns(_subject, grant.member_ref)
			grant = await records.revoke_share(grant_id)
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc
		return grant.model_dump(mode='json')

	@app.get('/records/share/{grant_id}/view')
	async def records_share_view(grant_id: str, at_iso: str,
	                             _subject: str = Depends(require_scope('consented_patient', purpose='consented_care'))) -> dict[str, object]:
		"""§10.1's provider-side view: what a clinician reads through a grant, refused past its end.

		Guarded on `consented_patient`, which is §17.4's clinician row — "Patients who have consented
		to share". The share *is* the consent that makes the row reachable, which is why this route
		is what closes the `unreachable_scopes` finding for that scope rather than a route invented to
		give a scope a caller. The expiry is enforced by the service, not by this route, so the same
		refusal applies wherever the view is read from.
		"""
		try:
			return records.share_view(grant_id, at_iso).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc

	@app.get('/records/{member_ref}/export')
	async def records_export(member_ref: str, fmt: str = 'pdf', at_iso: str = '',
	                         _subject: str = Depends(require_self_or_guardian(lambda r: r.path_params['member_ref']))) -> dict[str, object]:
		"""§REC-001's PDF export and §10.1's export for school, travel or employment.

		`at_iso` is a parameter rather than a call to the clock so the rendered document's own
		timestamp is the one the caller asked for; a default of '' is filled from the clock here.
		"""
		stamp = at_iso or datetime.now(timezone.utc).isoformat(timespec='seconds')
		try:
			return records.export(_subject, member_ref, fmt, stamp).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/records/{member_ref}/backup')
	async def records_backup(member_ref: str, at_iso: str = Body(''), passphrase: str = Body(''),
	                         _subject: str = Depends(require_self_or_guardian(lambda r: r.path_params['member_ref']))) -> dict[str, object]:
		"""§REC-001/§10.1's encrypted cloud backup, refused without the `cloud_backup` consent.

		The consent is read from the privacy service rather than taken as a request field: a caller
		who could assert their own consent in the body would be the label with nothing enforcing it.

		A `passphrase` makes the backup end-to-end. It is taken as a query parameter rather than a
		body because the route has no body, and it is never logged, never stored, and never sent to
		the crypto service except to derive a key. §SEC-003's "user-held key" is only true when one
		was supplied, which is why the envelope reports which case it is.
		"""
		from afya.privacy.views import ConsentCategory
		stamp = at_iso or datetime.now(timezone.utc).isoformat(timespec='seconds')
		consented = privacy.has_category_consent(_subject, ConsentCategory.cloud_backup)
		try:
			envelope = await records.backup(
				_subject, member_ref, stamp, consented,
				passphrase=passphrase or None, crypto=crypto,
			)
		except AssertionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc
		return envelope.model_dump(mode='json')

	@app.get('/records/{member_ref}/growth-chart')
	async def records_growth_chart(member_ref: str, sex: str = 'boy',
	                               _subject: str = Depends(require_self_or_guardian(lambda r: r.path_params['member_ref']))) -> dict[str, object]:
		"""§REC-003's percentile chart: the child's series against the WHO reference lines."""
		try:
			records.assert_owns(_subject, member_ref)
			return records.growth_chart(member_ref, sex).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.get('/records/{member_ref}/vaccination-certificate')
	async def records_vaccination_certificate(member_ref: str, purpose: str = 'travel', at_iso: str = '',
	                                          _subject: str = Depends(require_self_or_guardian(lambda r: r.path_params['member_ref']))) -> dict[str, object]:
		"""§10.1's vaccination certificate for travel, school or employment, sealed by the deployment."""
		from afya.config import ServiceConfig
		stamp = at_iso or datetime.now(timezone.utc).isoformat(timespec='seconds')
		secret = ServiceConfig.from_env().webhook_secret or 'afya-dev-seal'
		try:
			cert = records.vaccination_certificate(_subject, member_ref, purpose, stamp, secret)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return cert.model_dump(mode='json')

	# --- channels ---
	@app.get('/channels/cost')
	async def channels_cost() -> dict[str, object]:
		"""§5.2's cost-to-user column and §3.3 principle 3, resolved against the carrier's rules.

		Public, because it is the answer to a question every user has — will this cost me airtime —
		and it names no person. `zero_rating_gaps` is served beside the rows so a deployment whose
		carrier stopped covering SMS says so, rather than the app continuing to tell people alerts
		are free.
		"""
		rows = await channels.cost_report()
		rules = await channels.zero_rating_rules()
		gaps = zero_rating_gaps(rules)
		return {
			'channels': [r.model_dump(mode='json') for r in rows],
			'zero_rating_gaps': [g.channel for g in gaps],
			# Whether the carrier's rules were pulled at all. `rules is None` is the deployment-level
			# answer; a row's own `verified` is only about that row, and every row that needs no rule
			# is verified by construction — so reading it off the first row would report a
			# deployment with no carrier agreement as verified.
			'rules_pulled': rules is not None,
		}

	@app.get('/channels/attention')
	async def channels_attention() -> dict[str, object]:
		"""§5.1's rationale and the ordering it states: where attention is, in the section's own words.

		Served beside `/channels/cost` because the two are read together and they disagree on purpose —
		§5.2's Reach column ranks radio first and §5.1 ranks it third. A client placing an alert needs
		§5.1's order, which is about where a person's attention is, not about how many people a channel
		can eventually reach. It is open: it names no person and no number about one.
		"""
		return attention_report()

	@app.get('/channels/plain-language')
	async def channels_plain_language(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§CHAN-1's Format bullet — "plain language" — measured over every outbound string table.

		Scoped `audit_logs`, which is the scope §17.4 gives the content team and the one every other
		content-governance read takes. The rows name the strings and the sentences that overran the
		ceiling, which is editorial state rather than anything about a person, so it is a governance
		read and not a citizen one — the same reading `content_errors` takes.
		"""
		rows = plain_language_report()
		return {
			'surfaces': [r.model_dump(mode='json') for r in rows],
			'measured': sum(r.strings for r in rows),
			'over_the_ceiling': sum(len(r.over_the_ceiling) for r in rows),
			'ceiling': {'sentence_words': MAX_SENTENCE_WORDS, 'word_chars': MAX_WORD_CHARS,
			            'message_chars': MESSAGE_CHARS},
		}

	@app.post('/channels/sms')
	async def channels_sms(to_msisdn: str = Body(...), body: str = Body(...)) -> dict[str, object]:
		try:
			return (await channels.send_sms(to_msisdn, body)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/channels/ussd')
	async def channels_ussd(req: UssdRequest, lang: str = 'en') -> dict[str, object]:
		"""`lang` is a query parameter because USSD carries no headers: the carrier's gateway passes
		the subscriber's language out of band, and the menu it returns is the whole user interface.
		Without it the route was English-only and Swahili — the language §ACC-002 puts first — was
		unreachable on the one channel §4.1's feature-phone persona can use.

		The signal emit is here for the reason it is on the carrier callback: the walk is synchronous
		and the ledger write is not. A completed report is counted on the request that completed it,
		which for this route is the one carrying the final `*` answer.

		§CHAN-1's "Follow-up after a USSD report" is sent on the same walk and for the same reason —
		the walk composes the sentence and a send is I/O. It is the route that sends it rather than the
		walk, and `send_follow_up` is idempotent per report, so the whole-sink walk below texts a
		person once for the report they made rather than once per session they open afterwards.
		"""
		out = channels.ussd(req, lang).model_dump(mode='json')
		for report in channels.channel_reports():
			await channels.emit_report_signal(report)
			await channels.send_follow_up(report)
			await channels.absorb_into_live(report)
		return out

	@app.post('/channels/whatsapp')
	async def channels_whatsapp(msg: WhatsAppIn, lang: str = 'en') -> dict[str, object]:
		"""`lang` is a query parameter for the same reason the USSD route takes one: WhatsApp
		Business carries no locale header we can trust, and §5.4 puts the same engine behind it.

		A voice note is refused here rather than answered, and that is the fix to §ACC-002's fourth
		bullet rather than a regression: the note's `body` is a media reference, and routing it
		through the text keyword map answered "a media id contains no symptom word" at the low risk
		level. `/channels/whatsapp/voice` is where a note goes, and it transcribes first.

		The router files §5.4's channel report and this counts it into §AI-003's ledger, which is the
		one leg of the report the router cannot do: `route_whatsapp` is synchronous and the ledger
		write is I/O.
		"""
		try:
			out = channels.route_whatsapp(msg, lang).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		for report in channels.channel_reports():
			await channels.emit_report_signal(report)
			await channels.absorb_into_live(report)
		return out

	@app.post('/channels/whatsapp/voice')
	async def channels_whatsapp_voice(
		file: UploadFile = File(...), from_msisdn: str = Form(...), voice_note_lang: str = Form('en'),
	) -> dict[str, object]:
		"""§ACC-002's "voice note triage on WhatsApp": audio in, the same answer the app gives.

		Form fields rather than a JSON body, because this is the shape a webhook delivers — Meta
		posts the media reference alongside the message metadata, and the audio arrives as a
		download. The note is transcribed and then triaged through §5.4's one engine, so a person
		speaking into WhatsApp and the same person speaking into the app cannot get two answers.
		"""
		try:
			msg = WhatsAppIn(from_msisdn=from_msisdn, body='voice-note', kind='voice',
				voice_note_lang=voice_note_lang)
		except ValidationError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		blob = await file.read()
		if not blob:
			raise HTTPException(status_code=422, detail='an empty recording cannot be transcribed')
		with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as fh:
			fh.write(blob)
			path = Path(fh.name)
		try:
			result = channels.route_whatsapp_voice(msg, path)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		except (wavmod.Error, EOFError, RuntimeError) as exc:
			# `RuntimeError` is `wave`'s answer when a frame read seeks past the end of the file: a
			# recording truncated in transit, which is the shape a dropped connection leaves. It is
			# not a `wave.Error`, so catching only that turned a malformed upload into a 500 and
			# blamed the server for the network's truncation.
			raise HTTPException(status_code=422, detail=f'not a readable WAV file: {exc}') from exc
		finally:
			path.unlink(missing_ok=True)
		return {'reply': result.spoken_reply, 'channel': 'whatsapp', **result.model_dump(mode='json')}

	@app.post('/channels/ussd/callback')
	async def channels_ussd_callback(cb: AtUssdCallback, lang: str = 'en', _body: bytes = Depends(require_webhook())) -> dict[str, str]:
		"""Carrier webhook. Signature-guarded: unsigned, it is anyone driving the USSD menus.

		The signal emit sits here rather than inside `ussd()` because the walk is synchronous — it is
		a pure function of the accumulated input — and §AI-003's ledger write is I/O. This is the one
		place the USSD leg becomes awaitable, so it is the one place the count can be made.

		The carrier envelope is returned unchanged. A report that could not be placed in a locality is
		held and *not* counted, which is `emit_report_signal`'s own answer rather than a failure here:
		§AI-003's signal is a rise in a locality, and a USSD session carries none.
		"""
		envelope = channels.ussd_carrier_callback(cb, lang)
		for report in channels.channel_reports():
			await channels.emit_report_signal(report)
			await channels.send_follow_up(report)
			await channels.absorb_into_live(report)
		return envelope

	@app.get('/channels/reports')
	async def channels_reports(_subject: str = Depends(require_scope('assigned', purpose='outbreak_surveillance')),
	                           channel: str | None = None,
	                           unhandled_only: bool = False) -> dict[str, object]:
		"""§5.4's "single case-report backend" as the deployment reads it, with what the detector sees.

		Scoped `assigned` for the reason the callback queue is: this is a list of phone numbers and
		the symptoms each one reported, which is the dataset §SEC-003 exists for. The two counts are
		served together because the interesting fact is the *difference* between them — how many
		reports the product holds and how many of them its early-warning detector can actually count.
		"""
		reports = channels.channel_reports(channel=channel, unhandled_only=unhandled_only)
		return {
			'reports': [r.model_dump(mode='json') for r in reports],
			'held': len(reports),
			'countable_into_a_locality': len([r for r in reports if r.county is not None]),
		}

	@app.post('/channels/reports/{report_id}/handled')
	async def channels_report_handled(report_id: str, _subject: str = Depends(require_scope('assigned', purpose='outbreak_surveillance'))) -> dict[str, bool]:
		"""Mark one report read. The record is kept, so a report looked at twice is one report."""
		try:
			channels.handle_report(report_id)
		except KeyError as exc:
			raise HTTPException(status_code=404, detail='no such channel report') from exc
		return {'handled': True}

	@app.get('/channels/callbacks')
	async def channels_callbacks(_subject: str = Depends(require_scope('assigned', purpose='outbreak_surveillance')),
	                             unhandled_only: bool = True) -> list[dict[str, object]]:
		"""§CHAN-1's `CALLBACK` queue, for the deployment that rings people back.

		Scoped `assigned` rather than opened to anyone: this is a list of phone numbers and the
		symptom each caller reported, which is the one dataset on this route that is a person's
		health. `unhandled_only` defaults True so the default read is the work remaining.
		"""
		return [c.model_dump(mode='json') for c in channels.callback_requests(unhandled_only=unhandled_only)]

	@app.post('/channels/callbacks/{request_id}/handled')
	async def channels_callback_handled(request_id: str, _subject: str = Depends(require_scope('assigned', purpose='outbreak_surveillance'))) -> dict[str, bool]:
		"""Mark one request rung back, so a second reader sees it was already answered."""
		try:
			channels.handle_callback(request_id)
		except KeyError as exc:
			raise HTTPException(status_code=404, detail='no such callback request') from exc
		return {'handled': True}

	@app.post('/channels/chw/tasks')
	async def chw_assign(task: ChwTask, _subject: str = Depends(require_scope('assigned', purpose='case_management'))) -> dict[str, bool]:
		await channels.assign_chw_task(task)
		return {'ok': True}

	@app.get('/channels/chw/tasks/{chw_ref}')
	async def chw_open(chw_ref: str, _subject: str = Depends(require_scope('assigned', purpose='case_management'))) -> list[dict[str, object]]:
		return [t.model_dump(mode='json') for t in channels.open_tasks(chw_ref)]

	@app.post('/channels/chw/tasks/{task_id}/done')
	async def chw_done(task_id: str) -> dict[str, bool]:
		try:
			await channels.complete_task(task_id)
		except KeyError as exc:
			raise HTTPException(status_code=404, detail='unknown task') from exc
		return {'ok': True}

	# --- photo + textual evidence (SENS-004 symptom capture, COM-005 community reporting) ---
	@app.post('/evidence')
	async def evidence_upload(
		file: UploadFile = File(...),
		# Declared as Form, not query: a multipart body that carries these fields would otherwise
		# leave FastAPI's plain parameters at their defaults, so a client sending `kind=rash` in
		# the body would silently submit `scene_photo` — a different feature, a different gate.
		# Android's upload writes exactly that body, so the symptom-photo gate was bypassable.
		kind: EvidenceKind = Form(...),
		subject_ref: str = Form('U1'),
		county: str = Form('Nairobi'),
		note: str = Form(''),
		# §SEC-002's "explicit per-item consent", as a form field because the client that uploads a
		# photo writes a multipart body — the same reason `kind` is a `Form` and not a query
		# parameter. Defaults False, and the model refuses a submission without it: a photo that
		# arrives with nothing said about consent is not stored.
		consent: bool = Form(False),
		_subject: str = Depends(require_self()),
	) -> dict[str, object]:
		blob = await file.read()
		import hashlib
		from uuid6 import uuid7
		try:
			# The feature gate runs before the submission is built, so a symptom photo sent while
			# the response is dormant is refused as dormant rather than as a consent problem the
			# person could fix and which would fix nothing. The kind is the caller's own claim, so
			# this consults exactly what the body says and the model below re-checks the rest.
			evidence.gate(kind)
			# Built inside the try: the model's size and mime contracts are part of the request
			# validation, so a violation is the caller's 422, not an unhandled 500.
			submission = EvidenceSubmission(
				submission_id='EV-' + str(uuid7()).replace('-', '').upper()[:12],
				kind=kind, subject_ref=subject_ref, county=county,
				# No fallback mime: the model's `image/(jpeg|webp|png)` contract is the check, and a
				# default of `image/jpeg` would let any content type through under a false label.
				image_sha256=hashlib.sha256(blob).hexdigest(), mime=file.content_type or '',
				size_bytes=len(blob), note=note, consent=consent,
			)
			receipt = await evidence.submit(submission, blob)
		except PermissionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc
		except RuntimeError as exc:
			# The deployment holds no key. A 503 rather than a 422: nothing the caller sends would
			# succeed, and answering "your request was bad" would put the operator's omission on
			# the person holding the phone.
			raise HTTPException(status_code=503, detail=str(exc)) from exc
		except (AssertionError, ValidationError) as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return receipt.model_dump(mode='json')

	# --- §16.4 resumable upload, for the photos that are too big to send in one request ---
	# The three steps are separate routes rather than one streaming endpoint because the failure they
	# exist for is a dropped connection: a client that has to re-establish a stream to ask "what do
	# you have" cannot recover from the drop it is recovering from.
	def _upload_owner():  # type: ignore[no-untyped-def]
		"""Route guard for the chunk routes: the session's subject must be the token's own.

		`require_self` cannot do this job. It reads `subject_ref` from the path, the query or the
		body, and the chunk routes carry none of the three — their body is an offset and some bytes.
		The subject lives on the *session*, so the guard has to resolve the session first and compare
		the two. Without that, a session id derived from a submission id is the only thing between
		any token and any other person's in-flight photo, and appending bytes to a session is enough
		to make the finished picture hash wrong for its owner.

		It runs before the handler, so a caller who does not own the session never reaches the
		append — the same ordering `require_self` gives every other personal-data route.
		"""
		async def guard(session_id: str, authorization: str | None = Header(default=None)) -> str:
			subject, role = require_token(authorization)
			from afya.privacy.views import CITIZEN_ROLES
			if role not in CITIZEN_ROLES:
				raise HTTPException(status_code=403, detail='this route acts only for the token holder')
			try:
				owner = evidence.upload_session(session_id).subject_ref
			except KeyError as exc:
				raise HTTPException(status_code=404, detail=str(exc)) from exc
			if owner != subject:
				raise HTTPException(status_code=403, detail='this upload belongs to another person')
			return subject
		return guard

	@app.post('/evidence/upload')
	async def evidence_upload_open(
		body: UploadOpen, _subject: str = Depends(require_self()),
	) -> dict[str, object]:
		"""Open a resumable upload. Returns where the next chunk goes and when the session expires.

		JSON rather than a multipart form, unlike the single-shot route, and the difference is not
		cosmetic: the single-shot route carries the photo itself, so its fields travel in a multipart
		body beside the bytes. This request carries no bytes — only the claims about them — so there
		is nothing to put a boundary around, and a client that sent these as form fields to a route
		declaring them as a model would have every field left at its default.

		`chunk_bytes` is an offer, not a contract — chunks are addressed by byte offset, so a client
		that slices differently still resumes correctly.
		"""
		from uuid6 import uuid7
		try:
			# Built inside the try: the model's consent refusal and its mime/size contracts are part
			# of request validation, so a violation is the caller's 422 rather than an unhandled 500
			# — the same ordering the single-shot route uses for the same reason.
			submission = EvidenceSubmission(
				submission_id='EV-' + str(uuid7()).replace('-', '').upper()[:12],
				kind=body.kind, subject_ref=body.subject_ref, county=body.county,
				image_sha256=body.image_sha256, mime=body.mime, size_bytes=body.declared_bytes,
				note=body.note, consent=body.consent,
			)
			session = evidence.open_upload(submission, declared_bytes=body.declared_bytes,
			                               chunk_bytes=body.chunk_bytes)
		except PermissionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc
		except (AssertionError, ValidationError) as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return session.model_dump(mode='json')
	@app.get('/evidence/upload/{session_id}')
	async def evidence_upload_status(session_id: str, _subject: str = Depends(_upload_owner())) -> dict[str, object]:
		"""What the server holds for this upload. The question a resuming client asks after a drop."""
		try:
			return evidence.upload_session(session_id).model_dump(mode='json')
		except KeyError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.post('/evidence/upload/{session_id}/chunk')
	async def evidence_upload_chunk(
		session_id: str, chunk: UploadChunk, _subject: str = Depends(_upload_owner()),
	) -> dict[str, object]:
		"""Append one chunk. A 409 means the offset was wrong and the body says which one to send.

		A wrong offset is a conflict rather than a validation error because the client's next move is
		to read `next_offset` and continue — not to abandon an upload that is mostly on the server.
		"""
		try:
			return evidence.append_chunk(session_id, chunk).model_dump(mode='json')
		except KeyError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc
		except ValueError as exc:
			raise HTTPException(status_code=409, detail=str(exc)) from exc

	@app.post('/evidence/upload/{session_id}/finish')
	async def evidence_upload_finish(session_id: str, _subject: str = Depends(_upload_owner())) -> dict[str, object]:
		"""Store the assembled photo. Runs the same controls the single-shot route does."""
		try:
			receipt = await evidence.finish_upload(session_id)
		except KeyError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc
		except PermissionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc
		except RuntimeError as exc:
			raise HTTPException(status_code=503, detail=str(exc)) from exc
		except (AssertionError, ValueError, ValidationError) as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return receipt.model_dump(mode='json')

	@app.post('/ml/cough/analyze')
	async def ml_cough_analyze(file: UploadFile = File(...), county: str = '') -> dict[str, object]:
		"""16 kHz mono WAV -> YAMNet AudioSet -> cough verdict (SENS-002, tier4 gated).

		`county` is the locality §AI-003's second bullet counts cough events in. It is a query
		parameter and not part of the audio, because the recording is on-device and the file that
		reaches here carries no geography — the caller knows where the recording was taken and the
		waveform does not.
		"""
		if not cough_engine:
			raise HTTPException(status_code=503, detail='onnx model assets not deployed (models/cough)')
		import io
		import wave as wavmod
		import numpy as np
		blob = await file.read()
		try:
			with wavmod.open(io.BytesIO(blob), 'rb') as w:
				if w.getframerate() != WAV_SR or w.getnchannels() != 1:
					raise HTTPException(status_code=422, detail='requires 16 kHz mono WAV')
				frames = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2')
				wave = (frames.astype(np.float32) / 32768.0)
		except HTTPException:
			raise
		except Exception as exc:
			raise HTTPException(status_code=422, detail='invalid WAV') from exc
		engine: YamnetCoughEngine = cough_engine  # type: ignore[assignment]
		try:
			verdict = engine.analyze(wave, tier4_active=registry.tier4_active())
		except PermissionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc
		# One ledger row per positive detection, not per recording: §AI-003's bullet is cough
		# *detection events*, and a recording of five coughs is five events in the classifier's own
		# count. A recording with none is not a signal.
		for _ in range(verdict.cough_events):
			await _record_signal(ai, county, 'cough_events')
		return verdict.model_dump(mode='json')

	# --- women / maternal / chronic / mental / blood / alerts / insurance ---
	@app.post('/women/cycle')
	async def women_cycle(entry: CycleLog, _subject: str = Depends(require_self())) -> dict[str, int]:
		return {'logs': await women.log(entry)}

	@app.get('/women/cycle/{ref}/predict')
	async def women_predict(ref: str, ref_date: str = '2026-10-08', _subject: str = Depends(require_self(lambda r: r.path_params['ref']))) -> dict[str, object]:
		try:
			return women.predict(ref, ref_date).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	# --- §REC-004's other four Features ------------------------------------------------------------
	@app.get('/women/contraception/methods')
	async def women_methods() -> dict[str, object]:
		"""WHO's method table, so a client offers the methods the server records against."""
		return {'methods': women.contraception_methods()}

	@app.post('/women/contraception')
	async def women_contraception(req: ContraceptionRequest, _subject: str = Depends(require_self())) -> dict[str, object]:
		try:
			return women.set_contraception(req).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/women/contraception/{ref}/due')
	async def women_contraception_due(ref: str, on_iso: str, _subject: str = Depends(require_self(lambda r: r.path_params['ref']))) -> dict[str, object]:
		"""The reminders, as data: a client schedules them locally (§ACC-004 wants no polling)."""
		return {'due': [p.model_dump(mode='json') for p in women.contraception_due(ref, on_iso)]}

	@app.get('/women/menopause/{ref}')
	async def women_menopause(ref: str, today_iso: str, _subject: str = Depends(require_self(lambda r: r.path_params['ref']))) -> dict[str, object]:
		"""§REC-004's menopause support — the twelve-month rule applied to the person's own logs."""
		return women.menopause(ref, today_iso).model_dump(mode='json')

	@app.post('/women/referral')
	async def women_referral(body: ReproductiveReferralRequest, _subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:
		"""§REC-004's referral to services.

		`names_subject=False` because this route never reads a subject from the caller: it refers the
		token's own holder, so there is nothing to compare the token against and no way to name someone
		else. The guard still requires a citizen role and still writes the access log.
		"""
		reason = body.reason
		try:
			return women.refer(_subject, reason).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/maternal/pregnancy')
	async def maternal_register(p: Pregnancy, _subject: str = Depends(require_self())) -> dict[str, bool]:
		await maternal.register(p)
		return {'ok': True}

	@app.get('/maternal/due-date')
	async def maternal_due_date(lmp_iso: str) -> dict[str, str]:
		"""§MON-002's "Estimated due date calculator". No subject and nothing stored — a date in, a
		date out — so a person who has not registered can still get the answer, and a caller who has
		not decided to register is not made to."""
		try:
			return {'lmp_iso': lmp_iso, 'edd_iso': maternal.estimated_due_date(lmp_iso)}
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/maternal/birth')
	async def maternal_birth(subject_ref: str = Body(...), birth_iso: str = Body(...),
			_subject: str = Depends(require_self())) -> dict[str, str]:
		"""The birth date the postnatal contacts count from. Without it there are no postnatal visits."""
		try:
			return {'subject_ref': subject_ref, 'birth_iso': await maternal.record_birth(subject_ref, birth_iso)}
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/maternal/{ref}/visits')
	async def maternal_visits(ref: str, today_iso: str = '2026-10-08', _subject: str = Depends(require_self(lambda r: r.path_params['ref']))) -> list[dict[str, object]]:
		"""§MON-002's eight ANC contacts with their dates and reminder leads, which is what makes
		"Visit reminders" a reminder rather than a count of what is outstanding."""
		try:
			return [v.model_dump(mode='json') for v in maternal.visits(ref, today_iso)]
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.get('/maternal/{ref}/postnatal')
	async def maternal_postnatal(ref: str, _subject: str = Depends(require_self(lambda r: r.path_params['ref']))) -> list[dict[str, object]]:
		try:
			return [v.model_dump(mode='json') for v in maternal.postnatal_visits(ref)]
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.get('/maternal/guidance')
	async def maternal_guidance(gest_week: int) -> dict[str, object]:
		"""§MON-002's "Trimester-specific guidance". Keyed on the week, so the same call answers at
		week 12 and week 40 with the two different things the section asks for."""
		try:
			return maternal.trimester_guidance(gest_week)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/maternal/newborn-signs')
	async def maternal_newborn_signs() -> list[dict[str, str]]:
		"""§MON-002's "Newborn danger signs" — the baby's list, which is not the mother's."""
		return [s.model_dump(mode='json') for s in maternal.newborn_danger_signs()]

	@app.post('/maternal/birth-plan')
	async def maternal_birth_plan(plan: BirthPlan, _subject: str = Depends(require_self())) -> dict[str, object]:
		"""§MON-002's birth plan, with the fields still unanswered served alongside it.

		`gaps` is the answer to "is this plan finished" and is computed rather than left to the
		client: a screen that counted the filled fields itself would be a second implementation of
		the section's five, and the two would disagree the first time one changed.
		"""
		try:
			saved = await maternal.save_birth_plan(plan)
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc
		return {'plan': saved.model_dump(mode='json'), 'gaps': saved.gaps()}

	@app.get('/maternal/{ref}/birth-plan')
	async def maternal_birth_plan_get(ref: str, _subject: str = Depends(require_self(lambda r: r.path_params['ref']))) -> dict[str, object]:
		try:
			plan = maternal.birth_plan(ref)
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc
		return {'plan': plan.model_dump(mode='json'), 'gaps': plan.gaps()}

	@app.get('/maternal/facilities')
	async def maternal_facilities(
		lat: float, lon: float, limit: int = 5, level: FacilityLevel | None = None,
		accepts_sha: bool | None = None,
	) -> dict[str, object]:
		"""§MON-002's "Facility finder for maternity services", fixed to the maternal service.

		The same finder `/facilities/find` serves, with the service pinned — the reason `/places/pharmacies`
		pins its kind: a client that asked the general finder and rendered the answer as places that
		deliver babies would be showing a person a clinic that does not. `level` and `accepts_sha` are
		§FND-001's own filters and stay open, because "a health centre that takes SHA" is a maternity
		question too.

		`unanswered` travels for the reason it does on the general finder: a pool where no facility
		published a level must say so rather than return a shorter list that reads as the answer.
		"""
		found, unanswered = facilities.find(NearestRequest(
			lat=lat, lon=lon, limit=limit, service=ServiceOffered.maternal,
			level=level, accepts_sha=accepts_sha,
		))
		return {
			'results': [{'facility': f.model_dump(mode='json'), 'km': round(km, 2)} for f, km in found],
			'unanswered': unanswered,
		}

	@app.post('/maternal/pmtct-referral')
	async def maternal_pmtct(subject_ref: str = Body(...), hiv_positive: bool = Body(...),
			_subject: str = Depends(require_self())) -> dict[str, object]:
		"""§MON-002's "Referral to PMTCT where relevant". The HIV result is a boolean the caller
		derived at the point of care and is not stored — this module has no PIN on it."""
		return maternal.pmtct_referral(subject_ref, hiv_positive).model_dump(mode='json')

	@app.get('/maternal/{ref}/anc-due')
	async def maternal_anc(ref: str, today_iso: str = '2026-10-08', gest_week: int = 12, _subject: str = Depends(require_self(lambda r: r.path_params['ref']))) -> list[int]:
		try:
			return maternal.anc_due(ref, today_iso, gest_week)
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.post('/maternal/anc')
	async def maternal_anc_record(rec: ANCRecord, _subject: str = Depends(require_self())) -> dict[str, bool]:
		await maternal.record_anc(rec)
		return {'ok': True}

	@app.post('/maternal/danger')
	async def maternal_danger(signs: list[str] = Body(..., embed=True)) -> dict[str, object]:
		try:
			return maternal.assess_danger(signs).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/chronic/bp')
	async def chronic_bp(r: BPReading, at_iso: str = '',
	                     _subject: str = Depends(require_self())) -> dict[str, str]:
		"""Log a blood pressure. `at_iso` dates it for §MON-003's trend chart.

		A query parameter rather than a model field: the reading model forbids extras and the date is
		not part of the measurement, it is where the measurement goes on the chart. Omitted, the
		reading is scored and not charted — which is the honest outcome, since a chart that used the
		server's clock would put two readings taken a month apart on the same day.
		"""
		out = await chronic.bp(r, at_iso)
		return {'stage': out.stage}

	@app.post('/chronic/glucose')
	async def chronic_glucose(r: GlucoseReading, at_iso: str = '',
	                          _subject: str = Depends(require_self())) -> dict[str, str]:
		out = await chronic.glucose(r, at_iso)
		return {'level': out.level}

	@app.get('/chronic/{ref}/bp-trend')
	async def chronic_trend(ref: str, _subject: str = Depends(require_self(lambda r: r.path_params['ref']))) -> dict[str, str]:
		try:
			return {'trend': chronic.bp_trend(ref)}
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/chronic/refill')
	async def chronic_refill(t: RefillTracker, _subject: str = Depends(require_self())) -> dict[str, bool]:
		return {'due': await chronic.set_refill(t)}

	# --- §MON-003: the three conditions with no reading, and the three missing features ----------

	@app.post('/chronic/kidney')
	async def chronic_kidney(reading: KidneyFunction, at_iso: str = '',
	                         _subject: str = Depends(require_self())) -> dict[str, object]:
		"""§MON-003's chronic kidney disease: CKD-EPI 2021, staged by KDIGO.

		`at_iso` is the reading's date and is deliberately not filled from the clock. The KDIGO
		definition needs the abnormality sustained for three months, so a reading with no date is
		staged and never reported as chronic — stamping it "now" would compare a prior reading of
		unknown age against today and call the result a duration.
		"""
		return (await chronic.kidney(reading, at_iso or None)).model_dump(mode='json')

	@app.post('/chronic/seizure')
	async def chronic_seizure(event: SeizureEvent, _subject: str = Depends(require_self())) -> dict[str, object]:
		"""§MON-003's epilepsy: ILAE's 5-minute and 30-minute time points."""
		return (await chronic.seizure(event)).model_dump(mode='json')

	@app.post('/chronic/sickle-crisis')
	async def chronic_sickle(crisis: SickleCrisis, _subject: str = Depends(require_self())) -> dict[str, object]:
		"""§MON-003's sickle cell disease: a painful crisis and the signs that escalate it."""
		return (await chronic.sickle_crisis(crisis)).model_dump(mode='json')

	@app.get('/chronic/{ref}/chart')
	async def chronic_chart(ref: str, metric: str,
	                        _subject: str = Depends(require_self(lambda r: r.path_params['ref']))) -> dict[str, object]:
		"""§MON-003's "Trend charts" for the readings this service holds.

		The peak-flow and weight series live in the monitoring service, where those readings are
		logged, so they are read from there and charted here rather than copied into a second store.
		"""
		try:
			if metric == 'peak_flow':
				return chronic.chart_from_series(
					ref, metric, [(at, float(v)) for at, v in monitoring.peak_flow_series(ref)]
				).model_dump(mode='json')
			if metric == 'weight':
				return chronic.chart_from_series(
					ref, metric, [(at, float(v)) for at, v in monitoring.weight_series(ref)]
				).model_dump(mode='json')
			return chronic.chart(ref, metric).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/chronic/appointments')
	async def chronic_schedule_appointment(appt: ChronicAppointment,
	                                       _subject: str = Depends(require_self())) -> dict[str, object]:
		"""§MON-003's "Appointment tracking": record a review that is due."""
		try:
			return (await chronic.schedule_appointment(appt)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/chronic/{ref}/appointments')
	async def chronic_appointments(ref: str, today_iso: str = '',
	                               _subject: str = Depends(require_self(lambda r: r.path_params['ref']))) -> list[dict[str, object]]:
		"""Every appointment for a person, soonest first, with how long until each is due."""
		stamp = today_iso or datetime.now(timezone.utc).date().isoformat()
		return [s.model_dump(mode='json') for s in chronic.appointments_for(ref, stamp)]

	@app.get('/chronic/lifestyle')
	async def chronic_lifestyle(condition: str, subject_ref: str | None = None,
	                            _subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:
		"""§MON-003's "Lifestyle guidance", keyed on the condition rather than on the age.

		Self-scoped and not member-scoped: the guidance is a property of the condition and names no
		person, so the route serves it to any caller and takes a `subject_ref` only to echo it back.
		"""
		try:
			return chronic.lifestyle(condition, subject_ref).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/mental/who5')
	async def mental_who5(w: WHO5, _subject: str = Depends(require_self())) -> dict[str, object]:
		# §AI-003's fifth bullet, "increase in 'I feel unwell' check-ins". A low well-being score is
		# the person saying they feel unwell; a good one is not a signal, so only the lower bands
		# count. No subject reaches the ledger — the event carries the locality and nothing else.
		verdict = mental.assess(w)
		if verdict.band in ('very_low', 'low'):
			await _record_signal(ai, w.county, 'unwell_checkin')
		return verdict.model_dump(mode='json')

	@app.get('/mental/lines')
	async def mental_lines() -> list[dict[str, str]]:
		return mental.lines()

	@app.post('/mental/screen')
	async def mental_screen(req: Screening, _subject: str = Depends(require_self())) -> dict[str, object]:
		# §REC-005's first bullet. Self-scoped: a screen is a person's own answers about themselves,
		# and the guard binds `subject_ref` to the token so a caller cannot file one against somebody
		# else. A positive self-harm item is *not* turned into a §AI-003 signal — that ledger is
		# counts by county and nothing in it may point at a person.
		try:
			return mental.screen(req).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/mental/instruments')
	async def mental_instruments() -> dict[str, object]:
		# The item banks and cut-points a client renders. Served rather than duplicated in each
		# client, so a client cannot score an instrument the server scores differently. Not
		# self-scoped: it is a published instrument's text, with no subject in it.
		return {
			'phq9': {'items': list(ITEM_BANKS['phq9']['en']), 'sw_items': list(ITEM_BANKS['phq9']['sw']),
			         'options': list(RESPONSE_OPTIONS['en']), 'sw_options': list(RESPONSE_OPTIONS['sw']),
			         'langs': list(AVAILABLE_LANGS['phq9']), 'max_total': max_total('phq9'),
			         'cutpoints': mental.cutpoints('phq9'),
			         'impairment_question': mental.impairment_question('en'),
			         'sw_impairment_question': mental.impairment_question('sw'),
			         'timeframe': TIMEFRAME['en'], 'sw_timeframe': TIMEFRAME['sw']},
			'gad7': {'items': list(ITEM_BANKS['gad7']['en']), 'options': list(RESPONSE_OPTIONS['en']),
			         'langs': list(AVAILABLE_LANGS['gad7']), 'max_total': max_total('gad7'),
			         'cutpoints': mental.cutpoints('gad7'),
			         'further_evaluation_at': GAD7_FURTHER_EVALUATION_AT, 'timeframe': TIMEFRAME['en']},
			'who5': {'items': 5, 'scale': '0-5 each', 'raw': 'sum x 4, 0-100'},
		}

	@app.post('/mental/mood')
	async def mental_mood(entry: MoodEntry, _subject: str = Depends(require_self())) -> dict[str, object]:
		# §REC-005's "mood tracking". A person's own daily reading, kept apart from the instruments:
		# the mood log is a self-rating and PHQ-9 is a measurement with cut-points behind it.
		try:
			return mental.log_mood(entry).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/mental/mood/trend')
	async def mental_mood_trend(subject_ref: str, window_days: int = 14, _subject: str = Depends(require_self())) -> dict[str, object]:
		# `subject_ref` is a path/query param so `require_self` reads it and binds it to the token —
		# a person's own mood series is theirs, and a trend of somebody else's is an IDOR.
		return mental.mood_trend(subject_ref, window_days).model_dump(mode='json')

	@app.get('/mental/coping')
	async def mental_coping(lang: str = 'en') -> list[dict[str, object]]:
		# Psychoeducation from WHO's Psychological first aid guide, in the source's own two editions.
		# Not self-scoped: it is content, identical for everyone.
		try:
			return [c.model_dump(mode='json') for c in mental.coping(lang)]
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/mental/outbreak-support/{condition}')
	async def mental_outbreak_support(condition: str, lang: str = 'en') -> dict[str, object]:
		# §REC-005's sixth bullet: isolation distress, grief support and healthcare worker burnout,
		# each a named condition with a route rather than a band on a total.
		try:
			return mental.outbreak_support(condition, lang).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/mental/referral')
	async def mental_referral(req: ReferralRequest, _subject: str = Depends(require_self())) -> dict[str, object]:
		# §REC-005's "referral to services". Before this, referral existed only as a prose sentence
		# in `assess`; this records one, names the services, and names the ones whose numbers are
		# unverified rather than presenting every line as reachable.
		try:
			return mental.refer(req.subject_ref, req.reason, req.urgency).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/blood/donors')
	async def blood_register(d: Donor) -> dict[str, bool]:
		await blood.register(d)
		return {'ok': True}

	@app.post('/blood/match')
	async def blood_match(req: BloodRequest, today_iso: str = '2026-10-08') -> list[dict[str, object]]:
		return [m.model_dump(mode='json') for m in blood.match(req, today_iso)]

	@app.post('/blood/alerts')
	async def blood_alerts(req: BloodRequest, today_iso: str = '2026-10-08') -> list[dict[str, object]]:
		"""§REC-006's "Receive alerts when your blood type is urgently needed nearby".

		The donors who should be told, as data — the same shape §MON-001's missed-dose alerts and
		§EMG-001's countdown take, and for §ACC-004's reason: the server states the alert and the
		device schedules it, so nothing polls. `urgency` decides the reach, which is what the field
		was for; before this it was carried on the request and read by nobody.
		"""
		return [a.model_dump(mode='json') for a in blood.donor_alerts(req, today_iso, counties.ADJACENCY)]

	@app.get('/blood/donation-centres')
	async def blood_donation_centres(lat: float, lon: float, kind: str = 'blood_donation',
	                                 limit: int = 5) -> list[dict[str, object]]:
		"""§REC-006's "Find donation centres" — a public question with a public answer.

		`kind` defaults to `blood_donation` because that is the question a donor is asking; a caller
		that wants the storage sites names `blood_bank` explicitly, and the label on each result says
		which of the two it is.
		"""
		try:
			return [c.model_dump(mode='json')
			        for c in blood.donation_centres(places, lat, lon, limit, (kind,))]
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	# A community alert reaches every phone in the county. §17.4's `assigned` is the CHW's scope —
	# the role that carries a worker's report up — so issuing one is a worker action, not a
	# citizen's. Without this guard an anonymous caller could publish "Ebola confirmed" to a county.
	@app.post('/alerts')
	async def alerts_issue(a: CommunityAlert, _subject: str = Depends(require_scope('assigned', purpose='community_health_delivery'))) -> dict[str, bool]:
		try:
			await alerts.issue(a)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'ok': True}

	@app.get('/alerts/{county}')
	async def alerts_county(county: str) -> list[dict[str, object]]:
		return [a.model_dump(mode='json') for a in alerts.by_county(county)]

	@app.post('/environment/water')
	async def environment_water(w: WaterAdvisoryRequest) -> dict[str, object]:
		"""§MON-005's water safety, whole: the advisory and the three things to do about it.

		Public, and on the same reasoning as the advisory it already served: asking whether the water
		is safe is a question a person asks before they have decided to tell anyone who they are, and
		a reading that required a token would be unavailable during the flood it is about.

		`treated_at_iso` is when *this household* last treated water and not part of the county's
		reading, which is why `WaterAdvisoryRequest` carries it as its own field rather than folding
		it into `WaterQuality`. It was a query parameter, and both clients put every non-path field
		of a write into the JSON body and send no query string — so the field was one the form
		offered and no client could deliver, and the advisory came back with no reminder and no
		error. When it is absent there is no reminder, which is the honest answer: the server does
		not know when this person treats water.

		A time the server cannot read is answered 422 rather than left to the service's assertion: it
		is the caller's input that is wrong, and a 500 would tell them the server broke.
		"""
		try:
			return alerts.water_safety(w, w.treated_at_iso).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/environment/air')
	async def environment_air(a: AirAdvisoryRequest) -> dict[str, object]:
		"""§MON-006's air quality, whole: the index, the advisory, the mask, the window and the source.

		`location` is required and is a place name, not a coordinate. The section asks for the AQI
		"for user's location" and a county is tens of thousands of people; §LOC-002 keeps a person's
		position on their own device and §SEC-001's ledger governs what leaves it, so the caller
		names the place rather than the server resolving one.

		`hourly` is `hour=pm25` pairs — the same shape the catalogue's `list` field renders, and the
		reason it is a list of strings on `AirAdvisoryRequest` rather than a list of pairs: a generic
		form draws one text box per field, so a nested object would be a control no client renders.
		It was a comma-separated query parameter, which is the one place neither client puts a write
		field. Omitted, the window is empty and says so: an hour named from a single daily reading
		would be an hour nobody measured.
		"""
		series: list[tuple[int, float]] = []
		for pair in a.hourly:
			if not pair.strip():
				continue
			hour, _, value = pair.partition('=')
			series.append((int(hour), float(value)))
		return alerts.air_quality_guidance(a, a.location, series or None).model_dump(mode='json')

	@app.post('/environment/flood')
	async def environment_flood(f: FloodReport) -> dict[str, str]:
		msg, risk = await alerts.flood_alert(f)
		return {'advisory': msg, 'cholera_risk': risk}

	@app.post('/insurance/sha-check')
	async def insurance_check(req: SHACheckRequest) -> dict[str, object]:
		return (await insurance.check(req)).model_dump(mode='json')

	@app.post('/insurance/prices')
	async def insurance_prices(item: PriceItem) -> dict[str, bool]:
		await insurance.upsert_price(item)
		return {'ok': True}

	@app.get('/insurance/quote/{facility_id}/{procedure}')
	async def insurance_quote(facility_id: str, procedure: str, sha_active: bool = False) -> dict[str, object]:
		q = insurance.quote(procedure, facility_id, sha_active)
		if q is None:
			raise HTTPException(status_code=404, detail='no price on file')
		return q.model_dump(mode='json')

	@app.post('/triage/diagnose')
	async def triage_diagnose(inp: TriageInput) -> dict[str, object]:
		return triage.diagnose(inp).model_dump(mode='json')

	# --- sync ---
	@app.post('/sync/ops')
	async def sync_enqueue(op: SyncOp) -> dict[str, bool]:
		try:
			await sync.enqueue(op)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'queued': True}

	# --- §16.4 bandwidth minimisation ---
	@app.get('/sync/policy')
	async def sync_policy(connection: str = 'metered') -> dict[str, object]:
		"""What this connection class is allowed to spend, and how often it may ask.

		The client reads this rather than choosing its own numbers: a phone that could request the
		wifi batch size while on mobile data would spend the user's airtime to defeat the policy.
		"""
		try:
			policy = sync.policy_for(ConnectionClass(connection))
		except ValueError as exc:
			raise HTTPException(status_code=422, detail=f'unknown connection class {connection}') from exc
		return policy.model_dump(mode='json')

	@app.post('/sync/batch')
	async def sync_batch(connection: str = 'metered') -> dict[str, object]:
		"""Assemble the next request from the queue: delta payloads, batched, gzipped if it pays.

		Returns the encoding and byte counts as well as the ops, so a client can show the user what
		the sync is about to cost them before it happens.
		"""
		try:
			conn = ConnectionClass(connection)
		except ValueError as exc:
			raise HTTPException(status_code=422, detail=f'unknown connection class {connection}') from exc
		await sync.load()
		pending = [o for o in sync._queue.values() if not o.synced]  # noqa: SLF001 - the queue is the batch source
		batch = sync.encode(pending, conn)
		return batch.model_dump(mode='json')

	@app.post('/sync/delta')
	async def sync_delta(previous: dict[str, str], current: dict[str, str]) -> dict[str, object]:
		"""§16.4 delta sync, as a pure function so the client can compute what it will send.

		A removal travels as an explicit `-field` entry. Omitting it would mean "unchanged", so a
		deletion the user made would never reach the server and would return on the next pull.
		"""
		delta = delta_payload(previous, current)
		assert apply_delta(previous, delta) == current, 'a delta must reconstruct the current state exactly'
		return {'delta': delta, 'changed_fields': len(delta), 'full_fields': len(current)}

	@app.post('/sync/flush')
	async def sync_flush(connection: str = Body('wifi', embed=True)) -> dict[str, object]:
		"""§16.2's flow, run once: send what is due, schedule what failed, defer what cannot go.

		`connection` is the diagram's first diamond. A client that says `offline` has its ops deferred
		with no backoff earned — the phone was offline, not the op at fault — so they go out the
		moment the connection returns instead of waiting out a delay they did not cause.
		"""
		try:
			conn = ConnectionClass(connection)
		except ValueError as exc:
			raise HTTPException(status_code=422, detail=f'unknown connection class {connection}') from exc
		return (await sync.flush(clock_ms(), conn)).model_dump(mode='json')

	@app.get('/sync/state')
	async def sync_state(connection: str = 'offline') -> dict[str, object]:
		"""§16.1 principle 4 / ACC-003: what the offline indicator shows.

		Unscoped because it names no person — it is the state of *this* handset's queue, which the
		client reads to draw its own banner. `durable` is computed from whether the deployment has
		a store, so an indicator cannot claim a queued write survives a restart in a build where it
		does not.
		"""
		try:
			conn = ConnectionClass(connection)
		except ValueError as exc:
			raise HTTPException(status_code=422, detail=f'unknown connection class {connection}') from exc
		await sync.load()
		return sync.offline_state(conn).model_dump(mode='json')

	@app.get('/sync/conflicts')
	async def sync_conflicts(_subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:
		"""§16.3's appeal surface: the writes the server overruled, and whether each can be appealed.

		The queue is the device's, so the route binds the caller's own token rather than naming a
		subject — there is no subject parameter to get wrong. A conflict under a strategy the spec
		does not make appealable is returned too, marked, because "the server decided and that is
		the end of it" is a fact the user is entitled to see rather than infer from silence.
		"""
		rows = sync.conflicts()
		return {
			'conflicts': [c.model_dump(mode='json') for c in rows],
			'open': len([c for c in rows if not c.resolved()]),
			'appealable': [c.op_id for c in rows if c.appealable],
		}

	@app.post('/sync/conflicts/{op_id}/appeal')
	async def sync_appeal(op_id: str, note: str = Body(embed=True),
	                      _subject: str = Depends(require_self(names_subject=False))) -> dict[str, str]:
		try:
			rec = sync.appeal(op_id, note)
		except KeyError as exc:
			raise HTTPException(status_code=404, detail='no such conflict') from exc
		except PermissionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'op_id': rec.op_id, 'appeal': rec.appeal.value}

	# --- privacy ---
	@app.post('/privacy/consent')
	async def privacy_consent(rec: ConsentRecord, _subject: str = Depends(require_self())) -> dict[str, str]:
		try:
			out = await privacy.record_consent(rec)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'consent_id': out.consent_id}

	@app.get('/privacy/consent')
	async def privacy_consent_catalogue(
		lang: str = 'en',
		authorization: str | None = Header(default=None),
	) -> dict[str, object]:
		"""§SEC-001's categories as toggles, with the consequence each withdrawal carries.

		The catalogue names no person, so it is readable without a token — a prospective user
		deciding whether to use the app is who the plain-language sentences are for. The route takes
		no subject: when the caller presents a token their own live grants are resolved into the
		toggles, and otherwise every toggle reads off.

		A `subject_ref` parameter would have been the obvious shape and is the wrong one — the route
		has no guard, because the catalogue is public, so any subject parameter would be a reference
		a stranger could type. The token is the only subject this route reads.

		`lang` is §SEC-001's own first Feature bullet — "plain-language explanations in *local
		languages*" — and it is a parameter here rather than a header because the sentence is the
		whole content of the response. A language with no table is served English and every toggle
		says so through `served_in`, the rule `TriageResult` established: an explanation a person
		cannot read is not an explanation, and silently substituting English for Dholuo would make
		the consent look informed when it was not.
		"""
		from afya.strings import answerable
		caller: str | None = None
		if authorization:
			try:
				caller = require_token(authorization)[0]
			except HTTPException:
				caller = None
		granted = {c.category.value: True for c in privacy.consent_catalogue()
		           if caller is not None and privacy.has_category_consent(caller, c.category)}
		sensor_grants = {str(r['sensor']): True for r in privacy.sensor_consents()
		                 if caller is not None and privacy.sensor_consented(caller, str(r['sensor']))}
		return {
			'toggles': [t.model_dump(mode='json')
			            for t in privacy.consent_toggles(granted, sensor_grants, lang)],
			'sensors': privacy.sensor_consents(),
			'lang': answerable(lang),
			'language_fallback': answerable(lang) != lang,
		}

	@app.get('/privacy/consent/history')
	async def privacy_consent_history(lang: str = 'en',
	                                  _subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:
		"""§SEC-001's "consent audit log visible to the user".

		`names_subject=False` because there is no subject to name: the log is the caller's own, read
		from the token. A `subject_ref` parameter would be the obvious shape and the wrong one — the
		route has no way to tell a person asking about themselves from one asking about a stranger,
		and a consent history is a list of what someone agreed to and when.

		The catalogue route beside it (`GET /privacy/consent`) is public and serves the toggles
		without a token; this one is not, because a log is personal data and the toggles are not.
		"""
		return privacy.consent_history(_subject, lang).model_dump(mode='json')

	@app.post('/privacy/consent/{consent_id}/withdraw')
	async def privacy_consent_withdraw(consent_id: str,
	                                   _subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:
		"""§SEC-001's "One-tap revocation", as a door rather than a method.

		`PrivacyService.withdraw` was audited as carried and reached by nothing: consent could be
		granted at `POST /privacy/consent` and revoked only from inside the process. A person reading
		their own log could see every grant and no way to end one — and the log's `withdrawn` line was
		a state no door could produce.

		`names_subject=False` for the same reason the history route gives: the token is the subject,
		so there is nothing to name and no reference a stranger could type. The service asserts the
		record belongs to the caller, because a revocation that only needed a guessed id would let
		anyone switch off a grant they are not party to.

		A stranger's id and an id that names nothing both answer the *same* 404. The first draft let
		the ownership assertion's own message through, so "may withdraw only its own consent" and "no
		consent" were two distinguishable answers to the same request — an id oracle a stranger could
		walk, turning the guard into a way of learning whose grants exist. `records.revoke_share`
		keeps the message because a grant id there is already scoped to the caller's own records.
		"""
		try:
			rec = await privacy.withdraw(consent_id, _subject)
		except (KeyError, AssertionError) as exc:
			raise HTTPException(status_code=404, detail=f'no consent {consent_id!r}') from exc
		return {'consent_id': rec.consent_id, 'withdrawn': rec.withdrawn}

	@app.post('/privacy/dpia')
	async def privacy_dpia(inp: DPIAInput) -> dict[str, object]:
		"""Assess a proposed use against §17.3's eight topics. Stores nothing — this is the
		question "what would a DPIA say about this", which anyone may ask about their own plan."""
		report = privacy.assess_dpia(inp)
		return {**report.model_dump(mode='json'),
			'topics': [topic for topic, _field, _finding in DPIA_TOPICS],
			'raised': [topic for topic, field, _finding in DPIA_TOPICS if getattr(inp, field)]}

	@app.get('/privacy/dpia/topics')
	async def privacy_dpia_topics(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§17.3's eight bullets as the list the assessment walks, with the field that describes each.

		Auditor-scoped because it is a coverage claim about the assessment itself: the thing worth
		checking is that the topics the section names and the topics the code can find are the same
		eight, and that is not something a citizen endpoint should be asked to assert.
		"""
		return {
			'topics': [
				{'topic': topic, 'field': field, 'finding': finding, 'blocking': finding in BLOCKING_TOPICS}
				for topic, field, finding in DPIA_TOPICS
			],
			'reviews': [r.model_dump(mode='json') for r in privacy.dpia_reviews()],
		}

	@app.post('/privacy/dpia/review')
	async def privacy_dpia_review(review: DPIAReviewRequest, _subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""Record that §17.3's DPIA for this processing was conducted. The one way the Tier-4
		`dpia_review` key can be earned, and it takes a named reviewer and a timestamp rather than a
		boolean — a review is a thing that happened, at a time, by someone.

		A blocked assessment is refused here too, so the violation cannot be recorded away and then
		cited as reviewed at the gate.
		"""
		try:
			record = privacy.review_dpia(review.processing, review.reviewed_at_iso, review.reviewed_by)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return record.model_dump(mode='json')

	@app.get('/privacy/regulatory')
	async def privacy_regulatory(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§17.1's six instruments and §17.2's seven principles against what exists.

		Auditor-scoped, and the ids and `module:attr` references stay in the payload: this is the
		evidence surface, where the reference *is* the finding. What backs a registration or an
		agreement lives outside this repo, so the two sets are read from the records the deployment
		actually holds — an empty set is the honest answer for a deployment with none, and it is
		reported as unbacked rather than assumed.
		"""
		registrations = frozenset(s.duty.lower() for s in operations.obligation_status('2026-10-12')
			if s.last_performed_iso is not None)
		# `sharing_posture` is typed `dict[str, object]` because it carries four shapes of value, so
		# the key this route wants has to be narrowed at the read rather than trusted from the type.
		cleared = cast(list[str], governance.sharing_posture()['cleared_to_share'])
		agreements = frozenset(cleared)
		return privacy.regulatory_report(registrations=registrations,
			agreements=agreements).model_dump(mode='json')

	# --- tier4 + surveillance ---
	# Turning on the outbreak capabilities is an operations action, not something a client asks for.
	# §11.1's three keys are held by PHEOC (authorisation), the DPO (the DPIA) and the flag; §17.4
	# puts infrastructure in the sysadmin's hands, and the caller's role is checked against the same
	# `_SCOPE` map every other route uses rather than a second list that could drift.
	@app.post('/tier4/activate')
	async def tier4_activate(auth: Tier4ActivationRequest,
			_subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""§11.1: all three keys or nothing. The response names what is missing and what the
		activation unlocks, so a refusal is diagnosable instead of a bare false.

		The `dpia_review` key is not taken on the caller's word and is not even a field the caller
		sends: the DPIA is assessed from the deployment described in the request, and the key is held
		only by a recorded §17.3 review that still covers that processing. Before this, a request
		carrying `dpia_reviewed: true` and nothing else held the key — the DPIA was assessed only if
		`dpia_input` happened to be present, so the one input the gate exists for was optional.

		One flat body, because the operator's form offers one control per §17.3 topic and both
		clients put every non-path field of a write at the top level. The route used to take a nested
		`dpia_input` object beside a separate `auth` model, which no form could build: the operator
		set the ten switches and read a 422 naming a field they had set.
		"""
		processing = auth.processing()
		report = surveillance.assess_tier4(processing) if processing is not None else None
		review = surveillance.dpia_review_for(processing)
		active = await surveillance.activate_tier4(
			auth.authorized_by_pheoc, auth.flag_enabled, auth.bulletin_text,
			dpia=report, review=review, dpia_input=processing,
		)
		return {
			'activated': active,
			# Read off the activation that ran, not off the request: a DPIA the assessment blocked
			# changes which key is missing, and a refusal that named the caller's own claims would
			# report every key held while nothing turned on.
			'unmet_keys': registry.activation.unmet_keys(),
			'unlocked_features': [s.id for s in registry.by_tier(Tier.tier4)] if active else [],
			'dpia_risks': list(report.risks) if report is not None else [],
			'dpia_review_id': registry.activation.dpia_review_id,
			'message': (
				'Outbreak capabilities are live for this event.'
				if active else 'Outbreak capabilities stay dark until all three keys are held.'
			),
		}

	@app.get('/tier4/activation')
	async def tier4_activation_view(county: str | None = None, subject_ref: str | None = None, _subject: str = Depends(require_any_scope(('infrastructure', 'audit_logs')))) -> dict[str, object]:
		"""§11.1's table, what has fired, and which Tier-4 features no row turns on.

		Read by two roles through their own scopes: `infrastructure`, which fires the triggers and
		closes the event and therefore has to see what is firing, and `audit_logs`, which reviews the
		response afterwards. Guarding on either alone locks out one of the two — the shape
		`require_any_scope` exists for.

		`unassigned_features` is the finding: §11.1 names seven features and the registry has eighteen
		in Tier 4, and the twelve no row reaches are dormant by §7.3's tier model with no trigger that
		turns them on. Reported rather than resolved, because deciding which trigger governs SENS-001
		is a product question and inventing an assignment here would make the gap look closed.
		"""
		from afya.registry.activation import DIVERGENCES, TRIGGERS, unassigned
		state = activation.state(county=county, subject_ref=subject_ref)
		tier4 = frozenset(s.id for s in registry.by_tier(Tier.tier4))
		return {
			'triggers': [
				{'number': t.number, 'trigger': t.trigger, 'scope': t.scope.value,
				 'scope_label': t.scope_label, 'features': list(t.features),
				 'firing': state.scope_met(t)}
				for t in TRIGGERS
			],
			'pheoc_event_active': state.pheoc_event_active,
			'unassigned_features': list(unassigned(tier4)),
			'divergences': DIVERGENCES,
			'firings': [f.model_dump(mode='json') for f in activation.firings()],
		}

	@app.post('/tier4/activation/fire')
	async def tier4_activation_fire(firing: TriggerFiring, _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""Record a §11.1 trigger. Operator-scoped: a county finding or a tracing decision is not
		something a citizen asserts about themselves, and row 5's self-request is the one exception —
		it is fired through the person's own route, not here."""
		try:
			await activation.fire(firing)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'fired': firing.trigger_number, 'scope': firing.scope.value}

	@app.post('/tier4/deactivate')
	async def tier4_deactivate(at_iso: str, closed_by: str, _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""§11.1's closing clause: "Automatic when PHEOC closes the event. Users are notified. Data
		retention clocks begin." Closing also clears the three-key gate, because an event that is
		closed and a gate that is still open is the state the clause exists to prevent."""
		report = activation.deactivate(at_iso, closed_by)
		registry.activate(Tier4Activation(authorized_by_pheoc=False, flag_enabled=False))
		return report.model_dump(mode='json')

	# A geofence is a risk zone every device inside it is told about. An anonymous caller could
	# declare a high-alert outbreak zone over Nairobi and every phone there would read it.
	@app.post('/surveillance/geofence')
	async def surveillance_geofence(fence: Geofence, _subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, bool]:
		try:
			await surveillance.set_geofence(fence)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'ok': True}

	# The county's own fever and hotline counts. These are the numbers the early-warning z-score
	# is computed from, so an unguarded write is an outbreak signal anyone can fabricate.
	@app.post('/surveillance/signal')
	async def surveillance_signal(history: list[CountySignal], _subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, object]:
		return surveillance.weekly_signal(history).model_dump(mode='json')

	@app.get('/surveillance/geofences-at')
	async def surveillance_geofences_at(lat: float, lon: float, lang: str = 'en') -> list[dict[str, object]]:
		"""§LOC-001's zones at a point, for a caller who has not said who they are.

		Read-only and open, like every other location-agnostic information route: the coordinates are
		where the *caller* is, and nothing about the caller is recorded. An anonymous caller is treated
		as someone who never opted in — every zone reads as an entry and every event carries
		`logged=False` — which is the honest answer for a device that has not identified itself and the
		only one that cannot be turned into a movement record from an open route.

		A `subject_ref` is deliberately **not** a parameter here. It would have to be compared to the
		token to mean anything, and a route that took one without that comparison is an IDOR: the
		scope check passes for every citizen while the subject is whatever the caller typed. The
		opted-in path is `/location/zones/{subject_ref}`, which is guarded.
		"""
		return [e.model_dump(mode='json') for e in location.zones_at(lat, lon, None, lang)]

	@app.get('/location/zones/{subject_ref}')
	async def location_zones(subject_ref: str, lat: float, lon: float, lang: str = 'en',
	                          _subject: str = Depends(require_self())) -> list[dict[str, object]]:
		"""§LOC-001's entry and exit for a person, derived from the position and their own switch.

		Guarded because the answer depends on whether this person consented to have crossings
		recorded, and because `inside` is a record of where they have been. `require_self` binds the
		path's subject to the token, so the subject cannot be someone else's.

		`alert` is the section's own sentence with the place named, `message` is the entry or exit
		line, and the two differ: a client that rendered one sentence for both has told someone
		leaving a zone the same thing it told them entering, while the 21-day watch that started on
		entry is still running.
		"""
		return [e.model_dump(mode='json') for e in location.zones_at(lat, lon, subject_ref, lang)]

	@app.get('/location/zone-alerts/{subject_ref}')
	async def location_zone_alerts(subject_ref: str, _subject: str = Depends(require_self())) -> dict[str, object]:
		"""The person's own opt-in switch, and the zones they were last seen inside.

		Guarded by `require_self` because the switch is a consent decision: reading it is reading
		whether this person agreed to have their crossings recorded.
		"""
		return location.zone_watch(subject_ref).model_dump(mode='json')

	@app.post('/location/zone-alerts/{subject_ref}')
	async def location_set_zone_alerts(subject_ref: str, enabled: bool = Body(..., embed=True),
	                                   _subject: str = Depends(require_self())) -> dict[str, object]:
		"""§LOC-001's "Fully disableable" — the switch itself, stored against the subject.

		A stored decision rather than a per-request flag: a client that sent `enabled=true` with each
		position fix would be choosing on the person's behalf, and the section's Privacy line is that
		only entry/exit events are logged *and only with consent*. Turning it off does not forget the
		zones already crossed, so turning it back on does not re-announce the zone someone is
		standing in.
		"""
		return location.set_zone_alerts(subject_ref, enabled).model_dump(mode='json')

	@app.get('/mobile/features')
	async def mobile_features() -> list[dict[str, object]]:
		from afya.mobile.actions import FRIENDLY_COPY
		return [
			{'id': fid, 'title': t, 'description': d}
			for fid, (t, d) in FRIENDLY_COPY.items()
		]

	@app.get('/mobile/actions')
	async def mobile_actions(county: str | None = None, simple_mode: bool | None = None,
	                         authorization: str | None = Header(default=None)) -> list[dict[str, object]]:
		"""What this caller may actually do, and — if they use simple mode — how little they are asked.

		Three filters, all against showing a control that would refuse. An outbreak capability is
		shown only if §11.1 activates it for this caller — asked of the activation model per feature,
		not of the PHEOC declaration alone, because rows 3 and 5 activate the contact diary for *one
		person* and a person who asked for monitoring would otherwise be shown no diary while the
		route behind it would have served them. An operator control is withheld from a caller whose
		role does not hold the dataset its route checks: a health-information form offered to a
		citizen token is a 403 waiting to happen, which is the same failure. And a form is simplified
		for a caller who asked for simple mode, which is §ACC-001's other half.

		`simple_mode` is a *third* state, not a boolean: `None` means "whatever this caller's profile
		says", which is what makes the setting reach the forms without the client having to send it
		back. §ACC-001's simple mode is a stored `AccessProfile` field, and a client that had to pass
		it per request would be a second place for the same preference to live — the first place being
		the one `POST /access/profile` writes. `True`/`False` override it, for a preview or for a
		caller with no profile yet.

		No token means a citizen: the app's own screens work unauthenticated, so the citizen set is
		the default rather than a refusal.
		"""
		from afya.access.forms import required_fields, simplified
		from afya.mobile.actions import available, marked
		scopes: frozenset[str] = frozenset()
		subject_ref: str | None = None
		if authorization:
			try:
				subject_ref, role = require_token(authorization)
				scopes = frozenset(_SCOPE.get(role, set()))
			except HTTPException:
				scopes = frozenset()
		state = activation.state(county=county, subject_ref=subject_ref)
		acts = available(
			registry.tier4_active(), scopes,
			feature_available=lambda fid: activation.feature_available(fid, state),
		)
		# `required` is read off the routes once, here, and used for both things that need it: the
		# form's own asterisks and §ACC-001's drop list. Marking before simplifying is deliberate —
		# a simplified form must not drop a field the route requires, and `simplified` checks that
		# against the same reading, so the two cannot disagree about what a route needs.
		required = required_fields(app)
		acts = marked(acts, required)
		simple = simple_mode if simple_mode is not None else (
			subject_ref is not None and access.profile(subject_ref).simple_mode)
		if simple:
			acts = simplified(acts, required)
		return [act.model_dump(mode='json') for act in acts]

	@app.get('/places/nearest')
	async def places_nearest(lat: float, lon: float, kinds: list[str] | None = None, limit: int = 5) -> list[dict[str, object]]:
		"""FND-003/FND-005 (testing sites, vaccination points) plus pharmacies and water points.

		An empty registry is an empty list, not a 500: `PlacesService.nearest` asserts a non-empty
		pool, which would surface as a server error the first time a client asked a deployment whose
		OSM import had not run. A locator with nothing imported has no answer, and the honest one is
		"none found yet" rather than a crash.
		"""
		wanted = {PlaceKind(k) for k in (kinds or [])} or None
		try:
			found = places.nearest(lat, lon, wanted, limit)
		except AssertionError:
			return []
		return [
			{'place': p.model_dump(mode='json'), 'km': round(km, 2), 'directions': places.directions(p, lat, lon).model_dump(mode='json')}
			for p, km in found
		]

	@app.get('/places/testing-sites')
	async def places_testing_sites(
		lat: float, lon: float, limit: int = 5, test: str | None = None,
		max_cost_kes: int | None = None, max_turnaround_hours: int | None = None,
		test_type: TestType | None = None,
	) -> dict[str, object]:
		"""FND-003. The kinds are fixed by the route rather than passed by the client, so a client
		cannot ask the testing-site endpoint for pharmacies and render the answer as test locations.

		The three filter arguments are §FND-003's own Features cell — "Filter by test, cost, hours,
		results turnaround" — and `unanswered` names the ones this deployment's data cannot answer,
		so a screen can say "cost not published" instead of showing a shorter list that reads as one.

		`test_type` is the section's "Test types (context-dependent)" list as a closed vocabulary, so
		the seven it prints are the seven the filter offers; `test` stays for the free-text search a
		person types.
		"""
		found, unanswered = places.find(
			lat, lon, {PlaceKind.testing_site, PlaceKind.clinic, PlaceKind.hospital, PlaceKind.treatment_unit},
			limit, test=test, max_cost_kes=max_cost_kes, max_turnaround_hours=max_turnaround_hours,
			test_type=test_type)
		return {
			'places': [
				{'place': p.model_dump(mode='json'), 'km': round(km, 2),
					'directions': places.directions(p, lat, lon).model_dump(mode='json')}
				for p, km in found
			],
			'unanswered': unanswered,
		}

	@app.get('/places/pharmacies')
	async def places_pharmacies(
		lat: float, lon: float, limit: int = 5, accepts_sha: bool | None = None,
		open_now: bool = False,
	) -> dict[str, object]:
		"""FND-004. The pharmacy and chemist finder, fixed to the pharmacy kind for the same reason
		the testing-site route fixes its own — a client that asked this endpoint for hospitals and
		rendered them as chemists would be showing a person a shop that is not one.

		`accepts_sha` is the section's "Whether they accept SHA" and `open_now` its "Open now". The
		pharmacies are ordered by distance and then by whether they are open, because a chemist two
		hundred metres away that closed an hour ago is not the nearest answer to "where can I go now".
		"""
		found, unanswered = places.find(
			lat, lon, {PlaceKind.pharmacy}, _PHARMACY_SCAN_LIMIT, accepts_sha=accepts_sha)
		if open_now:
			found = [(p, km) for p, km in found if p.opening_hours is not None]
		found.sort(key=lambda pair: (pair[0].opening_hours is None, pair[1]))
		return {
			'places': [
				{'place': p.model_dump(mode='json'), 'km': round(km, 2),
					'directions': places.directions(p, lat, lon).model_dump(mode='json')}
				for p, km in found[:limit]
			],
			'unanswered': unanswered,
		}

	@app.get('/places/vaccination-points')
	async def places_vaccination_points(
		lat: float, lon: float, limit: int = 5, vaccine: str | None = None,
		age_months: int | None = None, max_cost_kes: int | None = None, walk_in_only: bool = False,
	) -> dict[str, object]:
		"""FND-005. Routine and campaign vaccination points, fixed to their own kind for the same
		reason, with the section's own filters — vaccine, age eligibility, cost, walk-in."""
		found, unanswered = places.find(
			lat, lon, {PlaceKind.vaccination_point, PlaceKind.clinic, PlaceKind.hospital}, limit,
			vaccine=vaccine, age_months=age_months, max_cost_kes=max_cost_kes, walk_in_only=walk_in_only)
		return {
			'places': [
				{'place': p.model_dump(mode='json'), 'km': round(km, 2),
					'directions': places.directions(p, lat, lon).model_dump(mode='json')}
				for p, km in found
			],
			'unanswered': unanswered,
		}

	@app.post('/places/import-osm')
	async def places_import_osm(county_lat: float, county_lon: float, _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, int]:
		client = OverpassClient()
		rows = await client.fetch_places(county_lat, county_lon)
		for p in rows:
			await places.upsert(p)
		return {'imported': len(rows), 'total': places.count()}

	# --- monitoring & reminders (§9.1 MON-001..004, §10.2 MON-005..008, §11.3 MON-009) ---
	@app.post('/monitoring/child')
	async def monitoring_child(member_ref: str = Body(...), dob_iso: str = Body(...),
			_subject: str = Depends(require_self_or_guardian(_body_member))) -> dict[str, bool]:
		# A child is registered into the caller's own wallet; a member_ref the caller does not own is
		# refused, so one person cannot enrol another's child into a monitoring schedule they control.
		try:
			records.assert_owns(_subject, member_ref)
		except AssertionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc
		await monitoring.register_child(member_ref, dob_iso)
		return {'ok': True}

	@app.get('/monitoring/child/{member_ref}/schedule')
	async def monitoring_schedule(member_ref: str, today_iso: str = '2026-10-10', _subject: str = Depends(require_self_or_guardian(lambda r: r.path_params['member_ref']))) -> list[dict[str, object]]:
		try:
			records.assert_owns(_subject, member_ref)
			return [r.model_dump(mode='json') for r in monitoring.schedule(member_ref, today_iso)]
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.get('/monitoring/child/{member_ref}/catch-up')
	async def monitoring_catch_up(member_ref: str, today_iso: str = '2026-10-10', _subject: str = Depends(require_self_or_guardian(lambda r: r.path_params['member_ref']))) -> dict[str, object]:
		try:
			records.assert_owns(_subject, member_ref)
			return monitoring.catch_up(member_ref, today_iso).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.post('/monitoring/child/dose')
	async def monitoring_dose(rec: ImmunisationRecord, _subject: str = Depends(require_self_or_guardian(_body_member))) -> dict[str, object]:
		"""§MON-001's "Record doses given (with photo of card)", into the wallet's dose log.

		The body carries the member rather than the path, because the record is the wallet's and it
		already names its member; the guard binds it the same way every other wallet write does.
		"""
		try:
			records.assert_owns(_subject, rec.member_ref)
			out = await monitoring.record_dose(rec)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return out.model_dump(mode='json')

	@app.get('/monitoring/child/{member_ref}/alerts')
	async def monitoring_alerts(member_ref: str, today_iso: str = '2026-10-10', _subject: str = Depends(require_self_or_guardian(lambda r: r.path_params['member_ref']))) -> list[dict[str, object]]:
		"""§MON-001's "Missed-dose alerts", as data: the device schedules them (§ACC-004)."""
		try:
			records.assert_owns(_subject, member_ref)
			return [a.model_dump(mode='json') for a in monitoring.missed_dose_alerts(member_ref, today_iso)]
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.post('/monitoring/campaign')
	async def monitoring_campaign(notice: CampaignNotice,
			_subject: str = Depends(require_scope('county_aggregate', purpose='community_health_delivery'))) -> dict[str, object]:
		"""§MON-001's campaign notification — issued by an authority, published into the feed.

		`county_aggregate`, which is the county health team's scope and the one every other public
		broadcast on this surface carries (`POST /alerting/feed` publishes the same class of notice
		under `assigned`). The route writes a notice that says `issued_by: MoH` into the immunisation
		feed every parent in a county receives, so the guard has to be about *who may speak for the
		authority* — and the scope is the only thing that answers that.

		It carried `require_self(names_subject=False)` until this was read against what the route
		does. `require_self` is the citizen's own-data guard: it admits `CITIZEN_ROLES` and refuses
		every staff role outright, so the guard did the *opposite* of what its comment claimed. An
		anonymous token posted a notice attributed to MoH and got a 200 — probed, not inferred — while
		the county officer the notice is from was refused. A route with a guard that admits the wrong
		population is the unguarded-write defect wearing a guard's clothes: the walker in
		`test_ui_vocabulary.py` counts any `Depends` as a guard, so this route was invisible to the
		check that exists to find exactly this.
		"""
		try:
			out = await monitoring.publish_campaign(notice, alerting)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return out.model_dump(mode='json')

	@app.get('/monitoring/campaigns')
	async def monitoring_campaigns(county: str, on_iso: str = '2026-10-10') -> list[dict[str, object]]:
		"""The campaigns running in a county on a day — a public question with a public answer."""
		return [c.model_dump(mode='json') for c in monitoring.campaigns(county, on_iso)]

	@app.post('/monitoring/medication')
	async def monitoring_medication(sched: MedSchedule, _subject: str = Depends(require_self_or_guardian(_body_member))) -> dict[str, object]:
		# A medication schedule is bound to a member of the caller's own wallet, so a schedule
		# cannot be filed against a stranger's child.
		try:
			records.assert_owns(_subject, sched.member_ref)
		except AssertionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc
		out = await monitoring.add_schedule(sched)
		# §MON-004's "Multiple daily reminders": the instants are served, not just stored. A schedule
		# acknowledged with its id alone leaves the client to invent the times, which is the count
		# this bullet replaced — and two clients would invent two different days.
		return {'schedule_id': out.schedule_id, 'reminder_times': out.reminder_times}

	@app.post('/monitoring/medication/adherence')
	async def monitoring_adherence(event: AdherenceEvent) -> dict[str, object]:
		try:
			return (await monitoring.record_adherence(event)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/monitoring/chronic/peak-flow')
	async def monitoring_peak_flow(r: PeakFlowReading, at_iso: str = '',
	                               _subject: str = Depends(require_self())) -> dict[str, object]:
		return await monitoring.log_peak_flow(r, at_iso)

	@app.post('/monitoring/chronic/weight')
	async def monitoring_weight(r: WeightReading, at_iso: str = '',
	                            _subject: str = Depends(require_self())) -> dict[str, object]:
		return await monitoring.log_weight(r, at_iso)

	@app.post('/monitoring/chronic/conditions')
	async def monitoring_conditions(p: ConditionProfile, _subject: str = Depends(require_self())) -> dict[str, bool]:
		try:
			await monitoring.set_conditions(p)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'ok': True}

	@app.get('/monitoring/chronic/{subject_ref}/report')
	async def monitoring_report(subject_ref: str, _subject: str = Depends(require_self())) -> dict[str, object]:
		return monitoring.shareable_report(subject_ref)

	@app.post('/monitoring/vector-risk')
	async def monitoring_vector_risk(county: str = Body(...), rainfall_mm_72h: float = Body(...),
			livestock_adjacent: bool = Body(False)) -> dict[str, object]:
		return monitoring.vector_risk(county, rainfall_mm_72h, livestock_adjacent).model_dump(mode='json')

	@app.post('/monitoring/breeding-site')
	async def monitoring_breeding_site(county: str = Body(...), lat: float = Body(...),
			lon: float = Body(...), description: str = Body(...)) -> dict[str, object]:
		return await monitoring.report_breeding_site(county, lat, lon, description)

	# §MON-007's larviciding campaign notice. A county issues it, on the same reasoning as the
	# food-safety alert below: it is a public statement about a place, not a personal record.
	@app.post('/monitoring/larviciding')
	async def monitoring_larviciding(notice: LarvicidingNotice, _subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, object]:
		try:
			return (await monitoring.publish_larviciding(notice, alerting)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/monitoring/larviciding/{county}')
	async def monitoring_larviciding_rounds(county: str, on_iso: str = '2026-10-10') -> list[dict[str, object]]:
		return [n.model_dump(mode='json') for n in monitoring.larviciding_rounds(county, on_iso)]

	# §MON-007's personal protection reminders. `at_iso` is supplied, not assumed — the household's
	# own evening is what the net reminder is anchored to, the same contract `/alerts/water-safety`
	# keeps for the treatment reminder.
	@app.get('/monitoring/protection-reminder')
	async def monitoring_protection_reminder(county: str, rainfall_mm_72h: float, at_iso: str) -> dict[str, object]:
		try:
			return monitoring.protection_reminder(county, rainfall_mm_72h, at_iso).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	# §MON-008's therapeutic feeding sites, over §FND-001's registry. A read expressed as a GET: a
	# county and a position in, a list out.
	@app.get('/monitoring/therapeutic-feeding')
	async def monitoring_therapeutic_feeding(county: str, lat: float, lon: float, limit: int = 5) -> list[dict[str, object]]:
		try:
			return [s.model_dump(mode='json')
			        for s in monitoring.therapeutic_feeding_centres(facilities, county, lat, lon, limit)]
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	# A food-safety alert is a public warning about a named product; the county issues it.
	@app.post('/monitoring/food-alert')
	async def monitoring_food_alert(alert: FoodSafetyAlert, _subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, object]:
		return (await monitoring.issue_food_alert(alert)).model_dump(mode='json')

	@app.get('/monitoring/food-alerts/{county}')
	async def monitoring_food_alerts(county: str) -> list[dict[str, object]]:
		return [a.model_dump(mode='json') for a in monitoring.food_alerts(county)]

	@app.get('/monitoring/nutrition/{age_months}')
	async def monitoring_nutrition(age_months: int, month: int | None = None) -> dict[str, object]:
		"""§MON-008's feeding guidance, and — when the caller names a month — what is in season.

		`month` is optional because a client with no calendar position can honestly be served the
		age band's own list and nothing else; inventing a month would answer a question nobody asked.
		"""
		try:
			return monitoring.nutrition_guidance(age_months, month).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/monitoring/contact/enrol')
	async def monitoring_enrol(subject_ref: str = Body(...), officer: str | None = Body(None),
			officer_number: str | None = Body(None), county: str | None = Body(None),
			_subject: str = Depends(require_self())) -> dict[str, object]:
		"""§11.1 rows 3 and 5: a contact gets the diary, or a person asks for it.

		This used to be `if not registry.tier4_active()`, one global gate, so the diary was
		unreachable until PHEOC declared a *national* event — while §11.1 activates MON-009 for an
		individual on two separate triggers and §11's own constraint says Tier 4 "activates
		automatically for users in affected areas". The person identified as a contact in a county
		with no declared event is exactly who the row is for.
		"""
		try:
			registry.get('MON-009')
		except KeyError as exc:
			raise HTTPException(status_code=404, detail='unknown feature') from exc
		state = activation.state(county=county, subject_ref=subject_ref)
		if not activation.feature_available('MON-009', state):
			raise HTTPException(status_code=403, detail=activation.reason('MON-009', state))
		return monitoring.enrol(subject_ref, officer, officer_number).model_dump(mode='json')

	@app.post('/monitoring/contact/day')
	async def monitoring_day(entry: MonitoringDay, _subject: str = Depends(require_self())) -> dict[str, object]:
		try:
			return (await monitoring.log_day(entry)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/monitoring/contact/{subject_ref}/diary')
	async def monitoring_diary(subject_ref: str, _subject: str = Depends(require_self())) -> dict[str, object]:
		return {
			'entries': [e.model_dump(mode='json') for e in monitoring.diary(subject_ref)],
			'missing_days': monitoring.adherence_reminder_days(subject_ref),
		}

	@app.get('/monitoring/contact/{subject_ref}/reminders/{day}')
	async def monitoring_reminders(subject_ref: str, day: int, _subject: str = Depends(require_self())) -> dict[str, object]:
		"""§MON-009's twice-daily reminders, as state rather than as a notification queue."""
		try:
			return monitoring.reminders(subject_ref, day).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/monitoring/contact/{subject_ref}/location-consent')
	async def monitoring_location_consent(subject_ref: str, decision: LocationConsentDecision, _subject: str = Depends(require_self())) -> dict[str, object]:
		"""Record the contact's own decision about contact-tracing location, granted or withdrawn."""
		try:
			return monitoring.record_location_consent(
				subject_ref, decision.granted, decision.at_iso).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/monitoring/contact/{subject_ref}/members')
	async def monitoring_add_member(subject_ref: str, request: HouseholdMemberRequest, _subject: str = Depends(require_self())) -> dict[str, object]:
		try:
			return monitoring.add_household_member(subject_ref, request.member_ref).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.delete('/monitoring/contact/{subject_ref}/members/{member_ref}')
	async def monitoring_remove_member(subject_ref: str, member_ref: str, _subject: str = Depends(require_self())) -> dict[str, object]:
		try:
			return monitoring.remove_household_member(subject_ref, member_ref).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/monitoring/contact/{subject_ref}/members/{member_ref}/diary')
	async def monitoring_member_diary(subject_ref: str, member_ref: str, _subject: str = Depends(require_self())) -> dict[str, object]:
		"""A household member's readings, out of the same 21-day window as the contact's own."""
		try:
			return {'member_ref': member_ref,
			        'entries': [e.model_dump(mode='json') for e in monitoring.member_diary(subject_ref, member_ref)]}
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/monitoring/contact/{subject_ref}/officer')
	async def monitoring_officer(subject_ref: str, _subject: str = Depends(require_self())) -> dict[str, str]:
		"""§MON-009's direct line to the assigned monitoring officer."""
		try:
			return monitoring.monitoring_officer_line(subject_ref)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	# --- community (§10.4 COM-005, §11.4 COM-101..104) ---
	@app.post('/community/issues')
	async def community_issue(issue: CommunityIssue) -> dict[str, object]:
		return (await community.report_issue(issue)).model_dump(mode='json')

	@app.get('/community/issues/{county}')
	async def community_issues(county: str) -> list[dict[str, object]]:
		return community.issues_by_county(county)

	# Marking a community problem fixed is the authority's act, not the reporter's: anyone who
	# could resolve an issue could close one they filed against their own facility.
	@app.post('/community/issues/{issue_id}/resolve')
	async def community_resolve(issue_id: str, _subject: str = Depends(require_scope('assigned', purpose='community_health_delivery'))) -> dict[str, str]:
		try:
			return {'status': (await community.resolve_issue(issue_id)).value}
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.post('/community/cases')
	async def community_case(report: CaseReport, _subject: str = Depends(require_scope('assigned', purpose='case_management'))) -> dict[str, object]:
		try:
			return (await community.submit_case(report)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/community/cases/{report_id}/advance')
	async def community_advance(report_id: str, status: CaseStatus = Body(..., embed=True),
			_subject: str = Depends(require_scope('assigned', purpose='case_management'))) -> dict[str, str]:
		try:
			return {'status': (await community.advance_case(report_id, status)).value}
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/community/ppe-reminder')
	async def community_ppe() -> dict[str, str]:
		return {'reminder': community.ppe_reminder()}

	@app.post('/community/peer-alert')
	async def community_peer_alert(alert: PeerAlert, _subject: str = Depends(require_scope('assigned', purpose='community_health_delivery'))) -> dict[str, object]:
		try:
			receipt = await community.send_peer_alert(alert)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		# §COM-102's fourth bullet from the sender's side: the receipt says how many people answered,
		# so a CHW who dispatched an alert can see whether anyone read it.
		return receipt.model_copy(update={'acknowledged': community.acknowledged_count(alert.alert_id)}).model_dump(mode='json')

	@app.get('/community/peer-alert/{alert_id}/followup/{day}')
	async def community_peer_followup(alert_id: str, day: int) -> dict[str, object]:
		"""§COM-102's follow-up prompt for one day of the window. `prompt` is `None` on a day the
		section does not name, which is an answer rather than an error — the scheduler asks for every
		day and sends only what comes back."""
		try:
			return {'alert_id': alert_id, 'day': day, 'prompt': community.followup_prompt(alert_id, day)}
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.post('/community/peer-alert/ack')
	async def community_peer_ack(ack: PeerAlertAck, _subject: str = Depends(require_self())) -> dict[str, object]:
		"""§COM-102's "Users acknowledge alerts and receive follow-up guidance", both halves.

		`require_self()` binds the body's `subject_ref` to the token, so a caller who names another
		person is refused rather than silently overwritten. That matters more here than on most
		self-bound routes: the acknowledgement is what §COM-102's receipt counts, so a caller who
		could acknowledge on someone else's behalf could inflate the number a CHW reads as "how many
		people heard this".
		"""
		try:
			guidance = await community.acknowledge_peer_alert(ack)
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc
		return guidance.model_dump(mode='json')

	@app.get('/community/tracing-prompts')
	async def community_prompts() -> list[str]:
		return community.tracing_prompts()

	@app.post('/community/contacts')
	async def community_contacts(contacts: ContactList, _subject: str = Depends(require_self())) -> dict[str, object]:
		return (await community.save_contacts(contacts)).model_dump(mode='json')

	@app.post('/community/contacts/{subject_ref}/entry')
	async def community_contact_entry(subject_ref: str, entry: ContactEntry, _subject: str = Depends(require_self())) -> dict[str, object]:
		return community.add_contact(subject_ref, entry).model_dump(mode='json')

	@app.post('/community/contacts/{subject_ref}/share')
	async def community_contact_share(subject_ref: str, with_who: str | None = Body(None, embed=True),
	                                  _subject: str = Depends(require_self())) -> dict[str, object]:
		"""§COM-103's "share with health authorities through a secure, encrypted channel".

		A POST rather than a field on `/community/contacts`, because the two are different acts at
		different moments: saving a list is a person writing down who they met, and sharing it is a
		decision they make afterwards and can take back. Folding the share into the save would make
		the consent flag the only gate, which is the shape the audit row named.
		"""
		try:
			receipt = await community.share_contacts(subject_ref, with_who)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		# §SEC-006's "what has been shared, with whom, when" reads `RetentionService.inventory`, and
		# a share that did not reach it would leave the dashboard §COM-103 exists to feed answering
		# "nothing shared" about a list the county now holds. Recorded here rather than inside the
		# community service so the two services stay unaware of each other.
		retention.record_share(
			subject_ref, receipt.with_who, f'contact list ({receipt.entries} people)',
			datetime.fromtimestamp(receipt.shared_at_ms / 1000, tz=timezone.utc).isoformat())
		return receipt.model_dump(mode='json')

	@app.get('/community/contacts/{subject_ref}/shares')
	async def community_contact_shares(subject_ref: str, _subject: str = Depends(require_self())) -> list[dict[str, object]]:
		"""The shares this person has made — §SEC-006's "what has been shared, with whom, when".

		The ciphertext is dropped from every row. A dashboard that echoed `sealed` would put the one
		value worth protecting into a response, a log and a client cache for no gain.
		"""
		return [
			{'share_id': s.share_id, 'with_who': s.with_who, 'entries': s.entries,
			 'shared_at_ms': s.shared_at_ms, 'expires_at_ms': s.expires_at_ms,
			 'algorithm': s.algorithm}
			for s in community.shared_contacts(subject_ref)
		]

	@app.delete('/community/contacts/{subject_ref}/shares')
	async def community_contact_shares_withdraw(subject_ref: str, _subject: str = Depends(require_self())) -> dict[str, int]:
		"""Take a share back before the tracing window closes. §SEC-005's right to delete."""
		return {'withdrawn': community.withdraw_shares(subject_ref)}

	@app.post('/community/misinformation')
	async def community_misinfo(submission: MisinfoSubmission) -> dict[str, object]:
		"""§COM-104's flag, and the flagger notification §11.4's flow ends on.

		The flag is recorded first and the notice is composed second, in that order, because the
		flow's own order is "aggregated → verified → correction drafted → published → flagger
		notified": a report that triggered a push before it was counted would tell the reporter
		something the deployment had not yet decided. `notices` carries what was sent and what was
		withheld with the reason, so a caller can tell "no correction drafted yet" from "you switched
		community alerts off" — two different facts the predecessor reported as neither, since it
		reported nothing at all.

		The notice does not fail the flag. A transport that is down is this route's normal case, and
		a 500 here would lose a report from someone who did the right thing.
		"""
		cluster = await community.flag_misinfo(submission)
		out = cluster.model_dump(mode='json')
		try:
			notices = await community.notify_flaggers(cluster.topic)
		except AssertionError:
			notices = []
		out['notices'] = [n.model_dump(mode='json') for n in notices]
		return out

	@app.get('/community/misinformation/notices/{subject_ref}')
	async def community_misinfo_notices(subject_ref: str,
	                                    _subject: str = Depends(require_self())) -> list[dict[str, object]]:
		"""What this person has been told about the rumours they reported, sent or withheld.

		`self`-scoped for the reason every personal-data route is: the notices name the rumour the
		person reported and the correction they were owed, which is a fact about them and not about
		the outbreak. A person whose push was withheld reads the same correction here, which is what
		makes switching community alerts off a preference rather than a way to lose an answer.
		"""
		return [n.model_dump(mode='json') for n in community.notices_for(subject_ref)]

	@app.post('/info/myths/ask')
	async def info_myths_ask(claim: str = Body(...), lang: str = Body('en')) -> dict[str, object]:
		"""§INF-004's "Ask about a rumour" — a claim submitted for verification, answered to the asker.

		Deliberately not `/community/misinformation`. That route is a *flag*: a person reports a rumour
		they saw someone else spread, and PHEOC gets a cluster — how many reports, which counties, how
		fast it is moving. Someone who asks "is it true that salt water cures Ebola" is not reporting
		anything; they want the correction, and answering them with a surveillance row is answering a
		question they did not ask. This returns the claim, the correction and the authority behind it,
		which is §INF-004's own Format.

		Unscoped and unauthenticated, like the rest of the myth library: §6.2.7's whole point is that
		the correction reaches the person who has the rumour, and requiring an account to ask whether
		something is true is how a correction stays unread.

		A claim matching nothing drafted is answered "under verification" with `recognised=false`,
		rather than being attached to the nearest rumour. A confident correction to the wrong question
		is worse than the honest one §6.2.8 asks for.

		`lang` is the asker's language and `answered_in` is the language they actually got, which
		differ when the language has no table — the same disclosure every channel route makes.
		"""
		return community.answer_claim(claim, lang).model_dump(mode='json')

	@app.get('/community/misinformation/clusters')
	async def community_clusters(now_ms: int | None = None) -> list[dict[str, object]]:
		"""`now_ms` is the caller's clock, for the same reason `/location/check` takes one: §6.4's
		deadlines are computed from the detection instant, and a view that can only read the wall
		clock cannot be asked what the response looked like at 5 hours."""
		return [c.model_dump(mode='json') for c in community.clusters(now_ms)]

	@app.get('/community/misinformation/protocol')
	async def community_protocol() -> dict[str, object]:
		"""§6.4's six steps with their owners and SLAs, and the readiness of the myth library.

		Served rather than documented because two of the six myth categories §6.4 names have no
		correction drafted, and a coverage report that exists only in a test is one an operator
		cannot read. The response is PHEOC's own working document, not citizen copy."""
		return {'steps': community.protocol_steps(), 'coverage': community.protocol_coverage()}

	# --- alerting (§9.6 ALT-003, §10.3 ALT-001/002, §11.8 ALT-004) ---
	# The feed is the durable broadcast behind the socket. Writing it is publishing to everyone.
	@app.post('/alerting/feed')
	async def alerting_publish(item: FeedItem, _subject: str = Depends(require_scope('assigned', purpose='community_health_delivery'))) -> dict[str, object]:
		try:
			stored = await alerting.publish(item)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		# The durable feed is written first, then the socket fans out. A socket is a transport, not
		# a second source of truth: a client that was offline when the alert fired still finds it
		# in the REST feed, which §16.1 requires to survive a restart.
		out = stored.model_dump(mode='json')
		out['delivered_realtime'] = realtime.publish(stored)
		return out

	@app.get('/alerting/feed')
	async def alerting_feed(
		county: str | None = None,
		since: str | None = None,
		known_revision: str | None = None,
	) -> dict[str, object]:
		"""§16.4 content caching: a client that already holds the current revision is told so, and
		`since` returns only items newer than what it last saw. Both are opt-in, so a first-time
		client still gets the whole feed."""
		revision = alerting.feed_revision(county)
		if known_revision is not None and known_revision == revision:
			return FeedPage(revision=revision, changed=False, items=[]).model_dump(mode='json')
		items = alerting.feed(county, since_iso=since)
		return FeedPage(revision=revision, changed=True, items=items).model_dump(mode='json')

	@app.get('/alerting/service-status')
	async def alerting_service_status(county: str | None = None) -> dict[str, object]:
		"""INF-007 service status feed: school and market closures, water interruptions, road and
		transport disruptions that affect reaching care.

		These are feed items in the `service` category, which the alerting feed already carries and
		the preference map already routes to `facility_alerts` — so this is a view over one category
		of the existing feed rather than a second store. Keeping it one store is what stops a closure
		being published twice and read as two events.

		`statuses` is the current state per place and `items` the announcements that produced it. The
		two differ deliberately: a market that closed and reopened has one current status and two feed
		items, and a screen that showed only the items would make a reader work out which is now.
		`coverage` names the section's six Contents and how many current statuses each carries, so a
		deployment with no road-closure feed says so rather than rendering an empty section.
		"""
		items = [i for i in alerting.feed(county) if i.category == 'service']
		statuses = alerts.service_status(county)
		return {
			'county': county,
			'count': len(statuses),
			'statuses': [s.model_dump(mode='json') for s in statuses],
			'coverage': alerts.status_coverage(),
			'items': [i.model_dump(mode='json') for i in items],
			'note': 'Statuses come from county and national sources; check the source line before travelling.',
		}

	@app.post('/alerting/service-status')
	async def alerting_publish_status(status: ServiceStatus,
			_subject: str = Depends(require_scope('assigned', purpose='community_health_delivery'))) -> dict[str, object]:
		"""Publish one §INF-007 status. This is the producer the read above was missing.

		`assigned` rather than a citizen scope: a market closure or a border-post restriction is what
		a county authority publishes, and the feed it lands in is the one that reaches every phone in
		the county. The same scope guards `POST /alerting/feed` for the same reason.
		"""
		stored = await alerts.publish_status(status, alerting)
		return stored.model_dump(mode='json')

	@app.post('/alerting/preferences')
	async def alerting_preference(subject_ref: str = Body(...), category: str = Body(...),
			enabled: bool = Body(...), _subject: str = Depends(require_self())) -> dict[str, object]:
		try:
			return alerting.set_preference(subject_ref, category, enabled).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/alerting/preferences/{subject_ref}')
	async def alerting_preferences(subject_ref: str, _subject: str = Depends(require_self())) -> dict[str, object]:
		return alerting.preferences(subject_ref).model_dump(mode='json')

	@app.post('/alerting/family/link')
	async def alerting_family_link(family_ref: str = Body(...), members: list[str] = Body(..., embed=True),
			_subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:
		# A group is built around the person creating it: without this a caller could link a
		# stranger's subject into a group and then read the board that names them.
		if _subject not in members:
			raise HTTPException(status_code=403, detail='a family group must include the person creating it')
		return alerting.link_family(family_ref, members).model_dump(mode='json')

	@app.post('/alerting/family/check-in')
	async def alerting_check_in(subject_ref: str = Body(...), family_ref: str = Body(...),
			at_iso: str | None = Body(None), channel: str = Body('native'), note: str | None = Body(None),
			_subject: str = Depends(require_self())) -> dict[str, object]:
		# `at_iso` is optional and defaults to the server clock, because the field exists so a queued
		# check-in can carry the instant it was actually made — not so every person has to have one.
		# The mobile catalogue marked it required, which meant a person pressing "I'm safe" had to be
		# asked *when*, and a question the server can answer itself is a question that loses a
		# check-in. §MON-004's offline queue still sends its own instant and is still honoured.
		try:
			return (await alerting.check_in(
				subject_ref, family_ref,
				at_iso or datetime.now(timezone.utc).isoformat(timespec='seconds'),
				channel=channel, note=note,
			)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/alerting/family/check-ins/{subject_ref}')
	async def alerting_checkins(subject_ref: str, _subject: str = Depends(require_self())) -> list[dict[str, object]]:
		"""The person's own check-ins, as §ALT-002's record of the feature working without data.

		Self-scoped and filtered to the caller: a check-in carries a subject and an instant, and a
		route that served every subject's would be a log of who is where for anyone who asked.
		"""
		return [c.model_dump(mode='json') for c in alerting.checkins() if c.subject_ref == subject_ref]

	@app.get('/alerting/family/{family_ref}')
	async def alerting_family(family_ref: str, _subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:
		# The board names which members are safe and which are unaccounted for, so it is readable
		# only by someone in the group — not by anyone who guesses the reference.
		if not alerting.is_member(family_ref, _subject):
			raise HTTPException(status_code=403, detail='this family board is not yours')
		return alerting.family_board(family_ref).model_dump(mode='json')

	# --- §15.5 WebSocket: real-time alert delivery -------------------------------------------
	@app.websocket('/alerts/socket')
	async def alerts_socket(ws: WebSocket, county: str | None = None, categories: str | None = None) -> None:
		"""A subscriber names a county and categories as query parameters; the server sends one
		frame per matching alert. Unnamed categories default to the toggleable set, and critical
		categories are delivered regardless — the same rule `AlertingService.should_deliver`
		applies, so a socket cannot mute an exposure notification that the REST path would send.
		"""
		await ws.accept()
		named = [c.strip() for c in (categories or '').split(',') if c.strip()]
		unknown = sorted(set(named) - KNOWN_CATEGORIES)
		if unknown:
			await ws.send_json({'kind': 'error', 'at_iso': now_iso(), 'message': f'unknown alert category: {unknown[0]}'})
			await ws.close(code=1008)
			return
		sub = realtime.subscribe(SocketSubscription(
			county=county, categories=named or sorted(KNOWN_CATEGORIES),
		))
		try:
			await ws.send_json(realtime.hello(sub).model_dump(mode='json'))
			while True:
				event = await sub.queue.get()
				await ws.send_json(event.model_dump(mode='json'))
		except WebSocketDisconnect:
			pass  # the client hung up; that is the normal way a socket ends
		finally:
			realtime.unsubscribe(sub)

	@app.get('/alerts/socket/stats')
	async def alerts_socket_stats() -> dict[str, object]:
		return realtime.stats().model_dump(mode='json')

	@app.post('/alerting/exposure')
	async def alerting_exposure(subject_ref: str = Body(...), case_ref: str | None = Body(None),
			county: str | None = Body(None),
			_subject: str = Depends(require_scope('assigned', purpose='contact_tracing'))) -> dict[str, object]:
		"""§11.1 rows 1, 2 and 4: ALT-004 is activated by a declared event, by a case in the county, or
		by the person entering a risk zone — three rows, so any one of them is enough."""
		state = activation.state(county=county, subject_ref=subject_ref)
		if not activation.feature_available('ALT-004', state):
			raise HTTPException(status_code=403, detail=activation.reason('ALT-004', state))
		return (await alerting.notify_exposure(subject_ref, case_ref)).model_dump(mode='json')

	@app.post('/alerting/exposure/ack')
	async def alerting_exposure_ack(ack: ExposureAck, _subject: str = Depends(require_self())) -> dict[str, object]:
		try:
			return (await alerting.acknowledge(ack)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	# --- location & proximity (§11.5 LOC-002..005) ---
	@app.post('/location/proximity/ebid')
	async def location_ebid(seed: str = Body(...), now_ms: int = Body(...)) -> dict[str, object]:
		return location.rotate_ebid(seed, now_ms).model_dump(mode='json')

	@app.post('/location/proximity/encounter')
	async def location_encounter(token: EncounterToken) -> dict[str, bool]:
		"""§11.1 row 1 activates LOC-002: an encounter is logged while the outbreak response is on.

		Rows 4 and 5 activate it too, and neither can be resolved here. `EncounterToken` is a Private
		Encounter Token — "identifies an encounter without identifying a person", §11.5 — so there is
		no subject on the request to match against a contact list or a risk-zone roster, and a
		`getattr(token, 'subject_ref', None)` would resolve to `None` on every call: a row that can
		never fire, dressed as one that can. The individual routes below are where those two fire,
		against the caller's own subject.
		"""
		state = activation.state(county=token.county)
		if not activation.feature_available('LOC-002', state):
			raise HTTPException(status_code=403, detail=activation.reason('LOC-002', state))
		await location.log_encounter(token)
		# §AI-003's sixth bullet. The PET is carried as the opaque ref and never read by the detector;
		# the county is what the density is measured in, and it is already on the token because the
		# feature gate above needs it.
		await _record_signal(ai, token.county, 'encounter_density', token.pet[:8])
		return {'ok': True}

	@app.post('/tier4/activation/request')
	async def tier4_activation_request(county: str | None = Body(None, embed=True),
			_subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:
		"""§11.1 row 5, "User requests activation" — the one trigger a person fires about themselves.

		It needs its own route because the operator route is `infrastructure`-scoped and a citizen does
		not hold it; and `names_subject=False` because the subject is the token's own and there is no
		`subject_ref` in the request to compare against — the guard would otherwise 422 every call for
		failing to name a subject that naming would only let a caller forge. The route then fires the
		trigger for the subject the token resolved to, so a person can turn this on for themselves and
		for nobody else.

		Firing it turns on the two features the row names for that person — the contact diary
		(MON-009) and proximity logging (LOC-002) — without a national declaration.
		"""
		await activation.fire(TriggerFiring(
			trigger_number=5, scope=TriggerScope.individual, subject_ref=_subject, county=county,
			evidence='the person asked for outbreak monitoring', fired_by=_subject,
			fired_at_iso=now_iso(),
		))
		from afya.registry.activation import TRIGGER
		state = activation.state(county=county, subject_ref=_subject)
		return {
			'activated': [f for f in TRIGGER[5].features if activation.feature_available(f, state)],
			'message': 'Outbreak monitoring is on for you. You can turn it off at any time.',
		}

	@app.post('/location/proximity/declare')
	async def location_declare(decl: ExposureDeclaration) -> dict[str, bool]:
		try:
			await location.declare_exposure(decl)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'ok': True}

	@app.post('/location/proximity/check')
	async def location_check(own_pets: list[str] = Body(..., embed=True), window_days: int = Body(21),
			now_ms: int | None = Body(None)) -> dict[str, object]:
		return location.check_exposure(own_pets, window_days, now_ms).model_dump(mode='json')

	@app.post('/location/history/enable')
	async def location_enable(subject_ref: str = Body(...), window_days: int = Body(21),
			_subject: str = Depends(require_self())) -> dict[str, object]:
		try:
			return location.enable_history(subject_ref, window_days).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/location/history/point')
	async def location_point(point: LocationPointWithSubject, _subject: str = Depends(require_self())) -> dict[str, int]:
		try:
			return {'points': location.log_location(point.subject_ref, point)}
		except AssertionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc

	@app.get('/location/history/{subject_ref}/report')
	async def location_report(subject_ref: str, _subject: str = Depends(require_self())) -> dict[str, object]:
		"""The report on the person's own screen. It shares nothing — see `/share` below."""
		try:
			return location.build_report(subject_ref).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.post('/location/history/{subject_ref}/share')
	async def location_report_share(subject_ref: str, with_who: str = Body('', embed=True),
	                                _subject: str = Depends(require_self())) -> dict[str, object]:
		"""§LOC-003's "report shared with health authorities through a secure channel".

		The report is sealed under §SEC-003's application-layer key and handed to the deployment's
		transport; a share that could not be delivered is held rather than lost. §SEC-006's "what has
		been shared, with whom, when" reads `RetentionService.inventory`, so a share that did not
		reach it would leave the dashboard answering "nothing shared" about a report the person
		believes the county holds — recorded here rather than inside the location service so the two
		services stay unaware of each other, exactly as the contact-list share does.
		"""
		try:
			receipt = await location.share_report(subject_ref, with_who)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		if receipt.delivered:
			retention.record_share(
				subject_ref, receipt.with_who,
				f'location report ({receipt.places} place{"" if receipt.places == 1 else "s"})',
				datetime.fromtimestamp(receipt.shared_at_ms / 1000, tz=timezone.utc).isoformat())
		return receipt.model_dump(mode='json')

	@app.get('/location/history/{subject_ref}/shares')
	async def location_report_shares(subject_ref: str, _subject: str = Depends(require_self())) -> list[dict[str, object]]:
		"""The sealed reports held for this person — what the receipt's held state points at.

		The ciphertext is dropped from every row, for the reason the contact-list listing drops it: a
		response that echoed `sealed` would put the one value worth protecting into a log, a cache and
		a client for no gain.
		"""
		return [
			{'share_id': s.share_id, 'with_who': s.with_who, 'places': s.places,
			 'shared_at_ms': s.shared_at_ms, 'algorithm': s.algorithm}
			for s in location.shared_reports(subject_ref)
		]

	@app.delete('/location/history/{subject_ref}')
	async def location_purge(subject_ref: str, _subject: str = Depends(require_self())) -> dict[str, int]:
		return {'purged': location.purge_history(subject_ref)}

	@app.post('/location/checkin/point')
	async def location_checkin_point(point: CheckInPoint) -> dict[str, str]:
		await location.register_point(point)
		return {'token': point.token}

	@app.post('/location/checkin')
	async def location_checkin(checkin: CheckIn, _subject: str = Depends(require_self())) -> dict[str, object]:
		"""§LOC-004's check-in. The receipt's `synced` is the queue's answer, not the request's.

		`share_with_authority` on the body is what the person asked for at the gate; whether anything
		left the phone is decided by `check_in`, which checks §SEC-001's sharing permission and hands
		the check-in to §16.2's queue. The two were one field, so a check-in that was refused still
		told the person it had been shared.
		"""
		try:
			return (await location.check_in(checkin)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/location/checkin/points')
	async def location_checkin_points(county: str | None = None) -> list[dict[str, object]]:
		return [
			p.model_dump(mode='json') for p in location.points()
			if county is None or p.county == county
		]

	@app.get('/location/checkin/{subject_ref}')
	async def location_checkins(subject_ref: str, _subject: str = Depends(require_self())) -> list[dict[str, object]]:
		return [c.model_dump(mode='json') for c in location.checkins_for(subject_ref)]

	@app.get('/location/checkin/{subject_ref}/follow-up')
	async def location_checkin_follow_up(subject_ref: str, lang: str = 'en', now_ms: int | None = None,
	                                     _subject: str = Depends(require_self())) -> dict[str, object]:
		"""§LOC-004's fourth Behaviour bullet: attendance, the follow-up schedule, the window.

		`now_ms` is the caller's clock for the same reason `/location/check` takes one — the window's
		elapsed days are arithmetic against an instant, and a view that can only read the wall clock
		cannot be asked what a person's record looked like on the day a prompt fell due.

		`self`-scoped, not an aggregate. A check-in is where one person was on one day, which is the
		most identifying row this module holds; a county-level reading of it would be an aggregate
		surface §LOC-004 does not ask for and §17.4 gives no role.
		"""
		return location.follow_up(subject_ref, now_ms, lang).model_dump(mode='json')

	@app.post('/location/border')
	async def location_border(post: BorderPost) -> dict[str, bool]:
		await location.register_border(post)
		return {'ok': True}

	@app.get('/location/border/{post_id}')
	async def location_border_status(post_id: str) -> dict[str, object]:
		try:
			return location.border_status(post_id).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.get('/location/travel-advisory')
	async def location_advisory(destination: str, origin_country: str, lang: str = 'en') -> dict[str, object]:
		"""§INF-005's travel advisory, whole: both places, the paragraph, and the post-travel steps.

		`lang` defaults to English and any language without a string table is served English and told
		so through `TravellerEnrolment.lang`/the advisory's own text — §ACC-002's `answerable` rule,
		not a second one. The route is public on the reasoning §INF-005 already used: a person asks
		whether it is safe to travel before deciding to tell anyone who they are.

		The response grew from `{advisory, lang}` to the resolved rows and the five steps, because
		§INF-005 asks for four things this one route answers and a client that had to call four
		routes to draw one screen is a client that can draw three of them. `advisory` stays a string
		for §5.4's USSD and SMS legs, which cannot render a structure.
		"""
		return location.travel_advisory(destination, origin_country, lang).model_dump(mode='json')

	@app.post('/location/traveller/declare')
	async def location_declare_traveller(decl: TravelerDeclaration, _subject: str = Depends(require_self())) -> dict[str, object]:
		return (await location.self_declare(decl)).model_dump(mode='json')

	@app.get('/location/traveller/{subject_ref}/prompt')
	async def location_traveller_prompt(subject_ref: str, day: int, _subject: str = Depends(require_self())) -> dict[str, object]:
		"""What the traveller is asked on a scheduled day, in the language they declared in.

		The enrolment names the schedule; without this the client would have to write the question
		itself, and a question written on the handset is one that never gets the traveller's language.
		"""
		try:
			enrolment = location.enrolment(subject_ref)
			return {'day': day, 'lang': enrolment.lang, 'prompt': location.arrival_prompt(subject_ref, day)}
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/location/traveller/report')
	async def location_traveller_report(report: PostArrivalReport, _subject: str = Depends(require_self())) -> dict[str, object]:
		"""§LOC-005's "post-arrival symptom reporting" — the other end of the 21-day schedule.

		Guarded because the report is a person's own symptoms: it is filed against their own subject
		and `require_self` is what makes the `subject_ref` in the body the token's and not whoever
		the caller typed. A 422 rather than a 500 for a day outside the schedule, because the caller
		sent the day and the server can say which days it accepts.
		"""
		try:
			return (await location.report_arrival_day(report)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	# --- §19.4 public-health dashboards --------------------------------------------------------
	# Nine dashboards the spec names for PHEOC, county health teams and MoH. Every row is a count
	# over a group with a min-cell-10 rule enforced at the boundary, and the read is audit logged
	# because §19.4 says so — "role-based, audit logged" is a property of the route, not a promise.

	# --- §22 success metrics and evaluation ----------------------------------------------------
	# §22 is what a funder reads: eight tables of targets and an evaluation framework. The rule is
	# §15.4's — a target with no measurement is unmeasured, not met — because a green report built
	# from silence is the failure these sections invite.

	@app.get('/metrics/kpis')
	async def metrics_kpis(family: str | None = None, _subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§22's targets, optionally filtered to one family. Auditor-scoped: this is the evidence
		half of the report, and it names no person."""
		from afya.metrics.views import MetricFamily as _F
		if family is None:
			return {'kpis': [k.model_dump(mode='json') for k in metrics.kpis()]}
		try:
			which = _F(family)
		except ValueError as exc:
			raise HTTPException(status_code=422, detail=f'unknown metric family {family!r}; one of {[f.value for f in _F]}') from exc
		return {'kpis': [k.model_dump(mode='json') for k in metrics.kpis(which)]}

	@app.get('/metrics/report')
	async def metrics_report(as_at_iso: str = '2026-10-10', _subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""Every §22 target beside its measurement. With nothing measured the report is empty, not
		green: `all_measured_targets_met` is false and `unmeasured` names each one."""
		return metrics.report(as_at_iso).model_dump(mode='json')

	@app.post('/metrics/measurement')
	async def metrics_record(measurement: dict[str, object], _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""Record a measurement against a §22 KPI. An unknown KPI is refused rather than stored and
		silently ignored, and the equity cuts travel with it so §22.7 coverage is measured too."""
		from afya.metrics.views import Measurement
		try:
			parsed = Measurement.model_validate(measurement)
			metrics.record(parsed)
		except (AssertionError, ValidationError) as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return metrics.result(next(k for k in metrics.kpis() if k.kpi_id == parsed.kpi_id)).model_dump(mode='json')

	@app.get('/metrics/equity')
	async def metrics_equity(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§22.7 disaggregation coverage: which of gender, geography, age and device we actually
		have a number for, and which we are claiming without one."""
		return metrics.equity().model_dump(mode='json')

	@app.get('/metrics/evaluation')
	async def metrics_evaluation(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§22.8's five evaluation levels, and the family coverage they add up to. A §22 metric family
		no level reads is collected and never looked at; the route names it rather than reporting a
		framework that looks complete because it has five rows."""
		return metrics.evaluation().model_dump(mode='json')

	# §19.4's readers span two §17.4 scopes: the county officer holds `county_aggregate` and the
	# PHEOC analyst `national_aggregate`. Guarding on either alone locks out a named audience.
	_ANALYTICS_SCOPES = ('county_aggregate', 'national_aggregate')

	@app.get('/analytics/dashboards')
	async def analytics_catalogue(_subject: str = Depends(require_any_scope(_ANALYTICS_SCOPES))) -> dict[str, object]:
		"""The nine §19.4 dashboards, their granularity, and who may read them."""
		return {
			'dashboards': [{'id': d.value, 'title': t, 'granularity': g} for d, t, g in DASHBOARDS],
			'access': analytics.access().model_dump(mode='json'),
		}

	@app.get('/analytics/dashboards/{dashboard}')
	async def analytics_dashboard(dashboard: str, as_at_iso: str = '2026-10-10',
			_subject: str = Depends(require_any_scope(_ANALYTICS_SCOPES))) -> dict[str, object]:
		"""One dashboard. `as_at_iso` is stamped on the report so a reader knows what day it is.

		An unknown dashboard is a 422 naming the ones that exist, rather than a 404 that leaves a
		caller guessing at the spelling."""
		try:
			which = DashboardId(dashboard)
		except ValueError as exc:
			raise HTTPException(status_code=422, detail=f'unknown dashboard {dashboard!r}; one of {[d.value for d in DashboardId]}') from exc
		return analytics.dashboard(which, as_at_iso).model_dump(mode='json')

	# --- AI & analytics (§19, §11.7) ---
	@app.post('/ai/hotspots')
	async def ai_hotspots(cells: list[AggregateCell] = Body(..., embed=True),
			_subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, object]:
		try:
			return ai.hotspots(cells).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/ai/hotspots/deploy')
	async def ai_hotspot_deploy(cells: list[AggregateCell],
			_subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, object]:
		"""§AI-001's third Output, shipped as §18.3's `resource_deployment` feed.

		The gap this closes is the one the audit found: `build_resource_feed` rendered a
		`resource_deployment` feed and **nothing produced its recommendations**. So the map answered
		with hotspots and the feed that is supposed to carry what to do about them was a builder with
		no caller — the same read-with-no-producer shape as §INF-007, on the write side.

		The recommendations come from `AIService.hotspots`, not from the request: a caller posting
		its own recommendation list could put a rapid-response team on the wire without the finding
		that justifies it. What this route adds is the transport, not the judgement.
		"""
		try:
			recommendations = [r.model_dump(mode='json') for r in ai.hotspots(cells).recommendations]
			if not recommendations:
				# A map with no cluster and no lone hotspot has nothing to deploy against, and an
				# empty push is refused by the transport on purpose (a quiet hour must not read as a
				# failed sync). Saying so here names the reason instead of surfacing the transport's
				# refusal as though the caller had sent something malformed.
				return {'feed': 'resource_deployment', 'cells_withheld': 0, 'recommendations': 0,
				        'accepted': 0, 'note': 'no cluster and no isolated hotspot; nothing to recommend.'}
			built, withheld = build_feed('resource_deployment', recommendations)
			accepted = await pheoc.push_feed('resource_deployment', built)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		except HTTPException:
			raise
		except Exception as exc:
			raise HTTPException(status_code=502, detail='PHEOC did not accept the feed') from exc
		return {'feed': 'resource_deployment', 'cells_withheld': withheld,
		        'recommendations': len(built), 'accepted': accepted}

	@app.post('/ai/risk-score')
	async def ai_risk(inp: RiskInputs) -> dict[str, object]:
		return ai.personal_risk(inp).model_dump(mode='json')

	@app.post('/ai/early-warning')
	async def ai_warning(county: str = Body(...), disease: str = Body(...),
			signals: list[str] = Body(..., embed=True),
			_subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, object]:
		"""`signals` is `name=observed=baseline=stdev` strings — the same shape §MON-006's `hourly`
		uses, and for the same reason: a generic form draws one text box per field, so a
		`list[WarningSignal]` is a control no client renders, and both clients send a `list` field as
		an array of strings. It was a list of objects, which meant the catalogue's own control
		produced a body the route refused — the section's only write action, unsubmittable.

		Four values rather than a nested object, and the *order* is fixed by the placeholder the
		catalogue prints. `z_score` is still not among them: it is derived here, and a caller that
		could set its own z-score could raise or silence an alert at will.
		"""
		parsed: list[WarningSignal] = []
		try:
			for spec in signals:
				if not spec.strip():
					continue
				name, _, rest = spec.partition('=')
				observed, _, rest = rest.partition('=')
				baseline, _, stdev = rest.partition('=')
				parsed.append(WarningSignal(county=county, disease=disease, signal=name.strip(),
					observed=float(observed), baseline=float(baseline), baseline_stdev=float(stdev)))
			return ai.assess_warning(county, disease, parsed).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		except (ValueError, ValidationError) as exc:
			# A signal name outside §11.7's six, or a count that is not a number. Refused as 422 with
			# the model's own message: a string the caller typed is their input being wrong, and a 500
			# would tell them the server broke. The six names are on the catalogue field's placeholder.
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/ai/signals')
	async def ai_record_signal(event: SignalEvent, _subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, object]:
		"""Ingest one occurrence of one of §11.7's six signals.

		Guarded on the county health team's scope, because this writes into a county's baseline and a
		baseline is what a review is triggered from: an unguarded ingest is a way for anyone to inflate
		a locality's count until an epidemiologist is paged about nothing. The app's own six surfaces
		do not come through here — they call the collector in-process, from routes that already carry
		their own guards — so this door is for a county system or a device reporting an event.

		The event carries no subject: it is a count of something that happened in a place, and nothing
		here identifies a person. The `ref` is the reporter's own opaque id for whatever it recorded,
		kept so a count can be traced back to its events and never read by the detector.
		"""
		try:
			return (await ai.record_signal_event(event)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/ai/early-warning/{county}/scan')
	async def ai_warning_scan(county: str, disease: str = 'evd', week_isoyear: int = 0, week: int = 0,
	                          baseline_weeks: int = 8,
	                          _subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, object]:
		"""§AI-003 end to end for one county and one week: the six signals, scored, routed for review.

		The period defaults to the week the deployment is running in, which is the week an
		epidemiologist means when they ask "how are we doing" — and it is computed from the clock
		rather than stored, so the scan cannot be pointed at a stale week by leaving a parameter out.
		"""
		if not week_isoyear or not week:
			iso_year, iso_week, _ = datetime.now(timezone.utc).date().isocalendar()
			week_isoyear, week = week_isoyear or iso_year, week or iso_week
		try:
			return ai.scan(county, disease, week_isoyear, week, baseline_weeks).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/ai/models')
	async def ai_models() -> list[dict[str, object]]:
		return [m.model_dump(mode='json') for m in ai.model_cards()]

	@app.get('/ai/footprint')
	async def ai_footprint() -> dict[str, object]:
		"""§19.1's "~30 MB (loaded as needed, not all at once)" against the on-device cards.

		The finding is the comparison, not the sum: five cards against a seven-row table read 8 MB
		where the section states 30, because the speech model and the cough classifier were absent —
		and `on_device` claimed on-device processing for languages that ship no recogniser. Open
		because it is a statement about what the client carries, not about a person."""
		return ai.footprint().model_dump(mode='json')

	@app.post('/ai/fairness-audit')
	async def ai_audit(audit: FairnessAuditRequest) -> dict[str, object]:
		try:
			return ai.audit_fairness(audit.model_id, audit.axes, audit.unmet_axes).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/ai/redress')
	async def ai_redress(req: RedressRequest, _subject: str = Depends(require_self())) -> dict[str, object]:
		return ai.file_redress(req).model_dump(mode='json')

	# --- accessibility (§12.1) ---
	@app.post('/access/profile')
	async def access_profile(profile: AccessProfile, _subject: str = Depends(require_self())) -> dict[str, bool]:
		try:
			access.set_profile(profile)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'ok': True}

	@app.get('/access/screens')
	async def access_screens(simple_mode: bool = False) -> list[dict[str, object]]:
		return [s.model_dump(mode='json') for s in access.screens(simple_mode)]

	@app.get('/access/languages')
	async def access_languages(tier: int | None = None) -> list[dict[str, object]]:
		return access.languages(tier)

	@app.post('/access/voice')
	async def access_voice(req: VoiceRequest, _subject: str = Depends(require_self())) -> dict[str, object]:
		"""Text in, answer out. The *audio* route is `/access/voice/audio`; this one takes a
		transcript, which is what a client that did its own on-device recognition already has."""
		try:
			return access.transcribe(req).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/access/voice/audio')
	async def access_voice_audio(
		file: UploadFile = File(...), subject_ref: str = Form(''), lang: str = Form('en'),
		purpose: str = Form('symptoms'),
		_subject: str = Depends(require_self()),
	) -> dict[str, object]:
		"""§ACC-002's actual entry point: a 16 kHz mono WAV recording, transcribed and answered.

		The recording is written to a temporary file, read by the engine and removed — §17.2's rule
		is that the waveform does not survive the request, and holding it in memory for the life of
		the process would be a recording kept. What leaves is the transcript and the answer to it.

		`subject_ref`, `lang` and `purpose` are `Form`, not plain parameters, because the body is
		multipart: a field a client writes into a multipart body leaves a plain parameter at its
		default, so the catalogue's language and purpose controls were silently ignored and every
		recording was transcribed as English symptoms. Both clients send the non-file fields as
		multipart parts (`Endpoints.multipart`, `BackendClient.uploadEvidence`), so the parts are
		where the values are.
		"""
		try:
			req = VoiceAudioRequest(subject_ref=subject_ref, lang=lang, purpose=purpose)
		except ValidationError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		blob = await file.read()
		if not blob:
			raise HTTPException(status_code=422, detail='an empty recording cannot be transcribed')
		with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as fh:
			fh.write(blob)
			path = Path(fh.name)
		try:
			return access.transcribe_audio(req, path).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		except (wavmod.Error, EOFError, RuntimeError) as exc:
			# A truncated recording is `wave`'s `RuntimeError` from a seek past EOF, not its own
			# `Error`; see the WhatsApp voice route for the same catch and the same reason.
			raise HTTPException(status_code=422, detail=f'not a readable WAV file: {exc}') from exc
		finally:
			path.unlink(missing_ok=True)

	@app.get('/access/battery')
	async def access_battery(subject_ref: str = 'U1', intensity: str = 'balanced', battery_saver: bool = False,
	                         charging: bool = False, stationary: bool = False, hour: int = 12,
	                         on_call: bool = False, do_not_monitor: bool = False,
	                         _subject: str = Depends(require_self())) -> dict[str, object]:
		"""§ACC-004's battery impact display, with the *context* the section names.

		The five context flags are query parameters because the device is what knows them — it is
		charging or it is not, the accelerometer says whether it is still, and the clock says the
		hour. §ACC-004 wants no background polling, so the handset reports its own state with the
		request rather than the server guessing it. Every default is the un-adaptive one, so a client
		that sends nothing gets exactly the profile the section's plain target describes.
		"""
		ctx = SamplingContext(charging=charging, stationary=stationary, hour=hour,
		                      on_call=on_call, do_not_monitor=do_not_monitor)
		try:
			return access.battery_profile(subject_ref, intensity, battery_saver, ctx).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/access/compatibility/{platform}')
	async def access_compat(platform: str, smallest_width_dp: int = Query(default=320, ge=1)) -> dict[str, object]:
		"""§ACC-005's device answer. `smallest_width_dp` is the caller's own shorter side, which is
		what selects the screen layout; it defaults to the 320dp reference handset because a narrow
		layout renders correctly on a large screen and the reverse is not true."""
		try:
			return access.compatibility(platform, smallest_width_dp).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.get('/access/screen-layouts')
	async def access_screen_layouts() -> list[dict[str, object]]:
		"""Every screen bucket, so a designer can lay out for the 320dp handset they are not holding."""
		return [s.model_dump(mode='json') for s in access.screen_layouts()]

	# --- retention, encryption, transparency (§17, SEC-003/005/006) ---
	@app.get('/retention/policy')
	async def retention_policy() -> list[dict[str, object]]:
		return [p.model_dump(mode='json') for p in retention.retention_table()]

	@app.post('/retention/holding')
	async def retention_holding(subject_ref: str = Body(...), data_type: str = Body(...),
			count: int = Body(...), _subject: str = Depends(require_self())) -> dict[str, int]:
		try:
			return {'count': retention.record_holding(subject_ref, data_type, count)}
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/retention/share')
	async def retention_share(subject_ref: str = Body(...), with_who: str = Body(...),
			what: str = Body(...), when_iso: str = Body(...),
			_subject: str = Depends(require_self())) -> dict[str, bool]:
		retention.record_share(subject_ref, with_who, what, when_iso)
		return {'ok': True}

	@app.get('/retention/inventory/{subject_ref}')
	async def retention_inventory(subject_ref: str, _subject: str = Depends(require_self())) -> dict[str, object]:
		return retention.inventory(subject_ref).model_dump(mode='json')

	@app.get('/retention/export/{subject_ref}')
	async def retention_export(subject_ref: str, at_iso: str, channel: str = 'native', _subject: str = Depends(require_self())) -> dict[str, object]:
		"""§SEC-005 "export all personal data at any time". A right with no route is not a right."""
		try:
			return retention.export(subject_ref, at_iso, channel).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/retention/delete')
	async def retention_delete(req: DeletionRequest, _subject: str = Depends(require_self())) -> dict[str, object]:
		return (await retention.delete(req)).model_dump(mode='json')

	@app.post('/retention/purge-expired')
	async def retention_purge(subject_ref: str = Body(...), age_days: list[str] = Body(default_factory=list),
			_subject: str = Depends(require_self())) -> dict[str, object]:
		"""`age_days` is `type=days` strings — the same shape §MON-006's `hourly` uses, and for the
		same reason: a generic form draws one text box per field, so a `dict[str, int]` is a control
		no client renders, and both clients send a `list` field as an array of strings. It was a
		JSON object, which meant the catalogue's own control produced a body the route refused.

		The parse is inside the `try` and a non-numeric age is a 422: `int(days)` on a string a person
		typed raises `ValueError`, and letting it escape answers a typo with a 500.
		"""
		try:
			ages: dict[str, int] = {}
			for pair in age_days:
				if not pair.strip():
					continue
				data_type, _, days = pair.partition('=')
				ages[data_type.strip()] = int(days)
			return {'expired': retention.purge_expired(subject_ref, ages)}
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		except ValueError as exc:
			raise HTTPException(status_code=422, detail=f'each entry is `type=days`: {exc}') from exc

	@app.get('/retention/encryption')
	async def retention_encryption() -> dict[str, object]:
		"""§SEC-003's posture, read off the crypto service this deployment actually built."""
		return retention.encryption_posture(crypto).model_dump(mode='json')

	@app.post('/retention/correct')
	async def retention_correct(req: CorrectionRequest,
	                            _subject: str = Depends(require_self())) -> dict[str, object]:
		"""§17.2 accuracy: "user data editable; correction workflows".

		The subject is the token's own, not a parameter: a correction is an act a person performs on
		their own record, and a route that took a `subject_ref` would let anyone edit anyone's
		demographics by typing a reference. A correction made on someone's behalf is the DPO's, and
		that is a different route with a different guard.
		"""
		req = req.model_copy(update={'subject_ref': _subject, 'corrected_by': _subject})
		# `at_iso` is optional on the form — a person correcting a field is not asked to state the
		# moment they did it — so an empty one is filled here rather than refused. It is still the
		# body's value, so a caller who does name a moment gets the one they named.
		at_iso = req.at_iso or datetime.now(timezone.utc).isoformat(timespec='seconds')
		try:
			return (await retention.correct(req, at_iso)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/retention/corrections')
	async def retention_corrections(_subject: str = Depends(require_self(names_subject=False))) -> list[dict[str, object]]:
		"""The correction history §17.2's "workflow" implies: what was changed, to what, and by whom.

		A right to correct that left no trace would be indistinguishable from a right to overwrite.

		`names_subject=False`: the history is the caller's own, read from the token, and the route
		names nobody. With the default the guard demanded a `subject_ref` the catalogue's
		`my_corrections` action does not offer — and must not, since a person typing a subject here
		would be asking to read somebody else's correction log.
		"""
		return retention.corrections(_subject)

	@app.get('/retention/transparency')
	async def retention_transparency(period: str, subject_ref: str | None = None, _subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§SEC-006's dashboard, for the person it is about: their own data, and who it went to.

		Guarded, unlike the publication below, because this one *is* about a person. The two are
		different documents and the section prints them as different Features.
		"""
		return retention.transparency_report(period, subject_ref).model_dump(mode='json')

	@app.get('/transparency/report')
	async def transparency_publication(period: str, as_at_iso: str) -> dict[str, object]:
		"""§SEC-006's "Public transparency reports (quarterly)": the aggregate document, served with
		no token at all — because a quarterly public report that required one would not be public.

		`/retention/transparency` is the *other* Feature of the same section: a subject's own view of
		their own data, guarded, and the two were one name apart while only the second existed. A
		document about a person is not a publication to the public.

		This route *reads* and does not record. Marking the quarter published is `POST
		/transparency/publish`, because a reader who could record a publication would let any caller
		mark a duty met — including a quarter that has not ended.

		Deliberately not under `/retention`: everything under that prefix is personal data with a
		subject, and a reader should not have to open a personal-data path to reach a document that
		names nobody.
		"""
		try:
			return retention.build_publication(period, as_at_iso).model_dump(mode='json')
		except ValueError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/transparency/publish')
	async def transparency_publish(period: str, as_at_iso: str,
	                               _subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""Record that a quarter's report was published. The operator's act, and the only write here.

		Separate from the read above so the schedule cannot be satisfied by being looked at: a duty
		that a reader discharges by reading is not a duty.
		"""
		try:
			return retention.publish(period, as_at_iso).model_dump(mode='json')
		except ValueError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/transparency/schedule')
	async def transparency_schedule(period: str) -> dict[str, object]:
		"""Whether the quarterly publication is done, late, or not yet owed — with no token.

		A cadence a reader cannot check is a cadence nobody can be late for. This is the read that
		makes §SEC-006's "quarterly" a claim about the deployment rather than a word in a document.
		"""
		try:
			return retention.publication_schedule(period, date.today()).model_dump(mode='json')
		except ValueError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/privacy/rbac')
	async def privacy_rbac(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§17.4's table against the routes and the token-issuing paths.

		Auditor-scoped, like the other evidence views: it reports which rows of the access table no
		implementation stands behind. Three scopes have no route and one role can never hold a token,
		which is the same class as a §7.3 feature outside the tier map — a capability the spec claims
		and no caller can reach. Reported rather than repaired here: adding a route so a scope has a
		caller would be this code inventing an endpoint, and issuing `citizen_identified` needs an
		identity-upgrade flow §15.5 does not specify.
		"""
		return rbac.report()

	@app.get('/privacy/access-log')
	async def privacy_access_log(limit: int = 100, _subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§17.4 "All access is logged" — readable by the auditor role, and only by it.

		Without a reader the log is write-only, which is not a control: nobody could answer "who
		looked at this record". The entry names the role and the dataset it asked for; it carries
		no subject reference, so reading the log does not itself disclose whose record was opened.

		`purpose` is the section's second sentence, and it is the difference between a ledger that
		records authorisation and one that records accountability: "the chw was allowed to read
		`assigned`" answers *whether*, and "for case management" answers *why* — which is the
		question a DPIA and the ODPC actually ask. A `null` means no purpose was declared, which is
		correct on a route that reaches no one else's data and is a finding on one that does; the
		auditor can tell the two apart because `GET /privacy/rbac` names the scopes that owe one.
		"""
		store = svc['store']
		if store is None:
			# No durable store configured (no AFYA_DB_PATH): say so rather than return an empty
			# list that would read as "nothing was ever accessed".
			return {'durable': False, 'entries': [], 'note': 'no durable store configured; access is logged in memory only'}
		rows = await store.audit_entries(limit)  # type: ignore[union-attr]
		return {
			'durable': True,
			'entries': [{'role': r, 'dataset': d, 'allowed': a, 'at_ms': t, 'purpose': p}
			            for r, d, a, t, p in rows],
		}

	# --- §5.4 identity model ---
	@app.get('/identity/model')
	async def identity_model(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§5.4's single identity model, and the deduplication finding it carries.

		Auditor-scoped like the other evidence views, and for the same reason §17.2 gives: the model
		holds an MSISDN-to-subject index, which is personal data, so "how many phones have resolved"
		is not a number a caller may read. The report carries the *shape* — the bases a link may have,
		whether the case-report dedup is performed, and the gap where it is not — and no phone and no
		subject.

		`can_deduplicate` is False and travels with its reason. The section promises the dedup; the
		identifier alone cannot perform it, because a person is not their phone (§4.1 has shared
		handsets, CHWs reporting for others, borrowed phones), so the finding is stated rather than
		papered over with a rule this code would have invented.
		"""
		return identity.report()

	@app.post('/identity/link')
	async def identity_link(link: IdentityLink, _subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:
		"""§5.4's "optional linkage to an app profile", as an act the person performs.

		`require_self` with no named subject: the link's `subject_ref` is forced to the caller's own
		token subject rather than taken from the body, so a caller cannot join someone else's profile
		to a phone. The body's `subject_ref` is therefore read only to reject a mismatch, which is a
		422 with a reason rather than a silent overwrite.

		The `consent_id` must be a live grant (§17.1), which `IdentityService.link` asserts — a link
		with no consent on record is the automatic merge §3.3 principle 6 forbids.
		"""
		caller = _subject
		if link.subject_ref != caller:
			raise HTTPException(status_code=422, detail='a link joins your own profile to a phone')
		if not privacy.has_consent(caller, 'identity_linkage') and not privacy.has_category_consent(caller, ConsentCategory.symptom_storage):
			raise HTTPException(status_code=422, detail='linkage needs a recorded consent (§17.1)')
		try:
			out = await identity.link(link)
		except (AssertionError, ValueError) as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		# The grants the phone made while it was anonymous move onto the profile. This is the one
		# place both services are in hand, so it is where the migration happens — a ledger that read
		# through to the old handle would leave two records for one grant and a withdrawal would then
		# stop being one tap. `moved` is reported so a client can tell the person what came across.
		moved = sum(privacy.reassign_subject(handle, out.subject_ref)
		            for handle in identity.absorbed_subjects(out.msisdn))
		return {'link_id': out.link_id, 'basis': out.basis.value, 'linked': True, 'consents_moved': moved}

	@app.get('/identity/links')
	async def identity_links(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""The links on record, without the phones. A link is what makes one person's channel
		activity join their app profile, so who holds one is an audit fact; the number itself is
		§17.2 personal data and stays out of the payload."""
		return {'count': len(identity.links()),
		        'links': [{'link_id': l.link_id, 'basis': l.basis.value} for l in identity.links()]}

	@app.get('/identity/pseudonym')
	async def identity_pseudonym(_subject: str = Depends(require_self(names_subject=False)),
	                             lang: str = 'en') -> dict[str, object]:
		"""§SEC-004's "optional pseudonymous profile": the handle that stands for the caller.

		`names_subject=False` because there is no subject to name: the handle is the caller's own, read
		from the token. A `subject_ref` parameter would be the obvious shape and the wrong one — the
		handle is the thing that makes a person's posts on a public feed unlinkable to their records,
		and a route that answered "what is this subject called" for any caller would undo that in one
		request. The guard is the same one §SEC-001's consent log uses, for the same reason.

		`chosen` says whether the person picked the handle or the app derived it, which is the
		difference the section's word "optional" turns on. `note` carries the sentence — and `caveat`
		carries the limit of what the handle protects, served rather than paraphrased: a handle that
		hides a name is not anonymity, and a screen that implied otherwise would change what a person
		is willing to write. An earlier cut had the caveat in the string table and no route reading
		it, which is the same absent-join defect the handle was added to close.
		"""
		from afya.strings import pseudonym_caveat, pseudonym_note
		policy = identity.pseudonym(_subject, clock_ms())
		return {**policy.model_dump(mode='json'),
		        'note': pseudonym_note(policy.chosen, policy.rotates_every_days, lang),
		        'caveat': pseudonym_caveat(lang)}

	@app.post('/identity/pseudonym')
	async def identity_pseudonym_choose(choice: PseudonymChoice,
	                                    _subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:
		"""A person naming themselves on the app's shared screens.

		A handle that is an identifier — a phone number or a subject reference — is refused by the
		service, because a person typing their own number into this box would be publishing the key
		§SEC-004 exists to keep off the screen, and the service would be the thing that let them.
		"""
		try:
			out = identity.choose_handle(_subject, choice.handle, clock_ms())
		except (AssertionError, ValueError) as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return out.model_dump(mode='json')

	@app.post('/privacy/consent/by-phone')
	async def privacy_consent_by_phone(grant: PhoneConsent,
	                                   _body: bytes = Depends(require_webhook())) -> dict[str, object]:
		"""A consent granted on a channel, written to the one registry the app reads.

		Webhook-guarded because the caller is a carrier-side integration holding a phone and no app
		token — the same shape as the inbound SMS and USSD callbacks. The subject is resolved through
		§5.4's identity model, so the grant is the same record the app's toggle reads: that is what
		makes "consent granted on one channel applies across channels" true rather than a slogan.
		"""
		try:
			category = ConsentCategory(grant.category)
		except ValueError as exc:
			raise HTTPException(status_code=422, detail=f'unknown consent category {grant.category!r}') from exc
		try:
			rec = await privacy.record_consent_for_phone(grant.msisdn, category,
			                                             channel=grant.channel, lang=grant.lang)
		except (AssertionError, RuntimeError, ValueError) as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'consent_id': rec.consent_id, 'category': rec.purpose}

	# --- CHW trust layer (§5 CHAN-005, §11.4 COM-101) ---
	@app.post('/chw/provision')
	async def chw_provision(profile: ChwProfile, _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, bool]:
		try:
			await chw.provision(profile)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'ok': True}

	# Static paths must precede /chw/{chw_ref}: FastAPI matches in declaration order, so a
	# parameterised route declared first swallows /chw/training and friends.
	@app.get('/chw/training')
	async def chw_training() -> list[dict[str, object]]:
		return chw.training()

	@app.get('/chw/job-aid/{topic}')
	async def chw_job_aid(topic: str) -> dict[str, str]:
		try:
			return {'job_aid': chw.job_aid(topic)}
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.get('/chw/job-aid/{topic}/print')
	async def chw_job_aid_print(topic: str) -> dict[str, object]:
		"""§CHAN-5's "Printed job aids" — the same aid as a printable PDF.

		Public like the aid itself: a job aid is reference material a CHW opens, not personal data,
		and the printed sheet carries the same words the screen already serves.
		"""
		try:
			return chw.job_aid_sheet(topic).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.get('/chw/ppe-reminder')
	async def chw_ppe() -> dict[str, str]:
		return {'reminder': chw.ppe_reminder()}

	@app.get('/chw/{chw_ref}')
	async def chw_get(chw_ref: str, _subject: str = Depends(require_scope('assigned', purpose='case_management'))) -> dict[str, object]:
		try:
			return chw.profile(chw_ref).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.get('/chw/{chw_ref}/case-load')
	async def chw_case_load(chw_ref: str, _subject: str = Depends(require_scope('assigned', purpose='case_management'))) -> dict[str, int]:
		return {'open_cases': chw.case_load(chw_ref)}

	@app.post('/chw/{chw_ref}/cases')
	async def chw_case(chw_ref: str, case: ChwCase, _subject: str = Depends(require_scope('assigned', purpose='case_management'))) -> dict[str, object]:
		try:
			return (await chw.assign_case(chw_ref, case)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.get('/chw/{chw_ref}/cases')
	async def chw_cases(chw_ref: str, _subject: str = Depends(require_scope('assigned', purpose='case_management'))) -> list[dict[str, object]]:
		return [c.model_dump(mode='json') for c in chw.cases(chw_ref)]

	@app.post('/chw/activity')
	async def chw_activity(entry: ActivityLogEntry, _subject: str = Depends(require_scope('assigned', purpose='case_management'))) -> dict[str, bool]:
		try:
			await chw.log_activity(entry)
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc
		return {'ok': True}

	@app.get('/chw/{chw_ref}/activity')
	async def chw_activity_summary(chw_ref: str, period: str | None = None, _subject: str = Depends(require_scope('assigned', purpose='case_management'))) -> dict[str, object]:
		"""One CHW's activity in a period, defaulting to the week the deployment is running in.

		The default used to be the **literal** `'2026-W41'`, so the catalogue's "My activity this week"
		read week 41 for the life of the deployment — a screen whose title is a week and whose number
		is a fixed one. The period is computed from the clock rather than stored, for the reason
		`/ai/early-warning` gives one route up: leaving the parameter out cannot then be pointed at a
		stale period, and the two routes that ask "how are we doing" answer about the same week.
		"""
		if not period:
			iso_year, iso_week, _ = datetime.now(timezone.utc).date().isocalendar()
			period = f'{iso_year}-W{iso_week:02d}'
		return chw.activity_summary(chw_ref, period).model_dump(mode='json')

	# --- §CHAN-5 the intermediary programme --------------------------------------------------
	# §4.1's Persona B arrives through "SOS feature recommended by his SACCO chairman", and §CHAN-5
	# names the SACCO chairmen as a target intermediary who gets a code. Until now the only thing
	# called `referral` in the tree was a CHW activity label, so the route a named persona takes into
	# the product did not exist. Enrolment and the code are the operator's; recording a referral and
	# reading an attribution are the intermediary's own.

	@app.get('/intermediaries/programme')
	async def intermediaries_programme() -> dict[str, object]:
		"""§CHAN-5's seven kinds and five tools, against what this repo carries. Open, because it is
		the programme's own description — the same shape as `/personas`.

		It names no person, and that is a claim about which fields are in the payload rather than a
		reader's impression: `untrained` carries attribution codes, which §CHAN-5 prints on a flip
		chart so a referral can be attributed to whoever made it, while `Intermediary.name`, its
		community and its enrolled date stay out. The test asserts the payload carries no name."""
		return intermediaries.programme().model_dump(mode='json')

	@app.get('/intermediaries/kinds')
	async def intermediaries_kinds() -> dict[str, object]:
		"""The seven target intermediaries, in §CHAN-5's order, with the code prefix each gets."""
		from afya.intermediaries.service import _KIND_PREFIX
		from afya.intermediaries.views import IntermediaryKind
		return {'kinds': [{'kind': k.value, 'name': k.name, 'prefix': _KIND_PREFIX[k]}
		                  for k in IntermediaryKind]}

	@app.post('/intermediaries/enrol')
	async def intermediaries_enrol(intermediary: Intermediary, _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""Enrol an intermediary under a code. `infrastructure`-scoped: issuing a code is what makes
		an incentive payable, so it is the operator's, not something a person can do for themselves.
		A duplicate code is refused — the second enrolment would silently reattribute the first one's
		referrals."""
		try:
			await intermediaries.enrol(intermediary)
		except AssertionError as exc:
			raise HTTPException(status_code=409, detail=str(exc)) from exc
		return intermediary.model_dump(mode='json')

	@app.post('/intermediaries/referrals')
	async def intermediaries_referral(referral: Referral, _subject: str = Depends(require_scope('assigned', purpose='case_management'))) -> dict[str, object]:
		"""Record a referral against a code. `assigned`-scoped like the CHW activity routes, because
		it is the same kind of write: a worker recording what they did. The referral names the person
		who arrived — §CHAN-5's "verified" is what makes the record checkable, and a referral with no
		person behind it is the intermediary's claim about their own activity."""
		try:
			await intermediaries.record_referral(referral)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return referral.model_dump(mode='json')

	@app.get('/intermediaries/{code}/attribution')
	async def intermediaries_attribution(code: str, _subject: str = Depends(require_scope('assigned', purpose='case_management'))) -> dict[str, object]:
		"""One intermediary's referrals, completions and payments."""
		try:
			return intermediaries.attribution(code).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.post('/intermediaries/incentives')
	async def intermediaries_incentive(incentive: Incentive, _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""Pay one §CHAN-5 airtime incentive for a verified referral, through §18.8's telco client.

		`infrastructure`-scoped: this spends money. The gate that refuses a second payment for the
		same referral is in the service rather than here, because the route sees an amount and a
		phone number and a caller that posted the same body twice would otherwise be paid twice.
		"""
		async def _disburse(msisdn: str, kes: int, reason: str) -> str:
			return await telco.disburse_airtime(msisdn, kes, reason)
		try:
			paid = await intermediaries.pay_incentive(incentive, _disburse)
		except AssertionError as exc:
			# The telco client's own refusals (unconfigured, over the 500 KES bound) arrive here too.
			# 422 for a bad request, 503 when the deployment has no carrier agreement — the two are
			# different facts and a caller can act on the first but not the second.
			detail = str(exc)
			status = 503 if 'not configured' in detail else 422
			raise HTTPException(status_code=status, detail=detail) from exc
		except Exception as exc:
			raise HTTPException(status_code=502, detail='the carrier is unreachable') from exc
		return paid.model_dump(mode='json')

	# --- §18 national system integrations ----------------------------------------------------
	# Every route below is a wire the spec names and that nothing called before: the clients existed
	# and no path reached them, so §18 was "implemented" in the sense that code existed. A route per
	# integration point is what makes the claim checkable from outside the process.

	@app.get('/integrations/status')
	async def integrations_status() -> dict[str, object]:
		"""What is wired and what the deployment actually configured. Read-only, no secret values.

		`configured` is about credentials; `wired` is about this process. They are reported apart
		because a deployment can be wired and unconfigured (dev), and reading one as the other is
		how "no API key" gets mistaken for "no integration".
		"""
		from afya.config import ServiceConfig
		cfg = ServiceConfig.from_env()
		from afya.integrations.frequencies import frequencies_for
		return {
			'wired': sorted(['adam', 'jali', 'pheoc', 'mohf', 'ppb', 'sha', 'telco']),
			'configured': cfg.live_vendors(),
			'adam_mutual_tls': adam.mutual_tls_configured,
			'jali_offline': jali.__class__.__name__ == 'InlineJaliPort',
			'pheoc_feeds': sorted(FEED_GRANULARITY),
			# §18's Frequency column per subsystem, with the route that carries each row. Served
			# because the cadence is an operating obligation — a duty desk asking "how often does
			# PHEOC get symptom reports" could previously only be answered by reading a docstring.
			'frequencies': {s: frequencies_for(s) for s in ('18.1', '18.2', '18.3', '18.4', '18.5', '18.6', '18.7', '18.8')},
		}

	# §18.1 ADaM — case reports out, status/assignments/definitions in.
	@app.post('/integrations/adam/cases')
	async def adam_push_case(report: dict[str, object], _subject: str = Depends(require_scope('assigned', purpose='outbreak_surveillance'))) -> dict[str, object]:
		try:
			ref = await adam.push_case_report(dict(report))
		except (AssertionError, ValueError) as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		except Exception as exc:
			raise HTTPException(status_code=502, detail='ADaM did not accept the case report') from exc
		return {'adam_case_ref': ref}

	@app.post('/integrations/adam/monitoring')
	async def adam_push_monitoring(summary: dict[str, object], _subject: str = Depends(require_scope('assigned', purpose='outbreak_surveillance'))) -> dict[str, bool]:
		"""Consented only. The refusal is the service's, so an unconsented summary cannot be pushed
		by leaving the flag off — the check is `is True`, not truthiness."""
		try:
			await adam.push_monitoring_summary(dict(summary))
		except AssertionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc
		except Exception as exc:
			raise HTTPException(status_code=502, detail='ADaM did not accept the monitoring summary') from exc
		return {'ok': True}

	@app.get('/integrations/adam/cases/{report_id}')
	async def adam_case_status(report_id: str, _subject: str = Depends(require_scope('assigned', purpose='outbreak_surveillance'))) -> dict[str, object]:
		try:
			return await adam.pull_case_status(report_id)
		except Exception as exc:
			raise HTTPException(status_code=502, detail='ADaM is unreachable') from exc

	@app.get('/integrations/adam/contacts')
	async def adam_contacts(chw_ref: str, _subject: str = Depends(require_scope('assigned', purpose='contact_tracing'))) -> list[dict[str, object]]:
		try:
			return await adam.pull_contact_assignments(chw_ref)
		except Exception as exc:
			raise HTTPException(status_code=502, detail='ADaM is unreachable') from exc

	@app.get('/integrations/adam/case-definitions')
	async def adam_case_definitions(_subject: str = Depends(require_scope('assigned', purpose='outbreak_surveillance'))) -> list[dict[str, object]]:
		try:
			return await adam.pull_case_definitions()
		except Exception as exc:
			raise HTTPException(status_code=502, detail='ADaM is unreachable') from exc

	# §18.2 JALI — a link out, corrections and clinician answers in.
	@app.post('/integrations/jali/link')
	async def jali_link(context: str, subject_ref: str, _subject: str = Depends(require_self())) -> dict[str, str]:
		"""No guard: this is the citizen's own launch, and the link carries a pseudonym the caller
		already holds. `jali` may be the offline port, in which case the link is empty — an empty
		link is the honest answer, not a fabricated URL that 404s on the phone."""
		return {'url': await jali.launch_link(context, subject_ref)}

	@app.get('/integrations/jali/corrections')
	async def jali_corrections(since: str = '1970-01-01T00:00:00Z') -> list[dict[str, object]]:
		"""Corrections are published health content. Read is open (they are meant to be shown to
		everyone); it is the *write* side, JALI's, that has to be authenticated, which it is."""
		return await jali.corrections(since)

	# The ADaM twin of this route carries `assigned`; a summary of one person's assessment
	# pushed to a national system without a guard is the same disclosure with the guard missing.
	@app.post('/integrations/jali/assessments')
	async def jali_share_assessment(summary: dict[str, object], _subject: str = Depends(require_scope('assigned', purpose='community_health_delivery'))) -> dict[str, str]:
		"""Push a consented assessment and return the reference the review is pulled by.

		The ref has to come back: the clinician's answer is §18.2's fourth row and it is read by id,
		so a push that returned only a boolean left the app with nothing to pull with.

		The consent check is made *here* as well as in the client, because the two ports are not
		equally guarded: `JaliClient.share_assessment` asserts it and `InlineJaliPort` does not, so
		with JALI unconfigured — which is the default, and what a deployment without a JALI key
		runs — an unconsented summary was accepted and answered 200. A control present in one of two
		implementations is a control at half the paths, and the route is the boundary both share.
		"""
		if summary.get('consented') is not True:
			raise HTTPException(status_code=403, detail='assessments are shared only with consent')
		try:
			ref = await jali.share_assessment(dict(summary))
		except AssertionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc
		except Exception as exc:
			raise HTTPException(status_code=502, detail='JALI did not accept the assessment') from exc
		return {'assessment_ref': ref}

	# §18.2's fourth row is a clinician's answer about one person's assessment. It carried no guard
	# at all — the only unguarded route on the §18 surface that serves a person's data — so anyone
	# could read any assessment by guessing an id. It carries the push route's scope, because the
	# same clinician relationship that may send an assessment out is the one that may read what came
	# back; a citizen route would be wrong, since a citizen never holds the assessment id.
	@app.get('/integrations/jali/assessments/{assessment_id}/review')
	async def jali_review(assessment_id: str, _subject: str = Depends(require_scope('assigned', purpose='case_management'))) -> dict[str, object]:
		"""The clinician's answer to an assessment this deployment pushed.

		`None` is "a human has not answered yet", which is a state, not an error — so it is a 200
		with a null body rather than a 404 the client would read as "no such assessment".
		"""
		try:
			out = await jali.clinician_response(assessment_id)
		except Exception as exc:
			raise HTTPException(status_code=502, detail='JALI is unreachable') from exc
		return {'review': out}

	# §18.3 PHEOC — the six dashboard feeds. Built by `feeds.py` (which enforces min-cell-10),
	# shipped here.
	@app.get('/integrations/pheoc/feeds')
	async def pheoc_feed_catalogue() -> dict[str, object]:
		return {
			'feeds': [{'name': n, 'granularity': FEED_GRANULARITY[n], 'cadence': FEED_CADENCE[n]} for n in sorted(FEED_GRANULARITY)],
			'min_cell': MIN_CELL,
		}

	@app.post('/integrations/pheoc/feeds/{feed}/preview')
	async def pheoc_feed_preview(feed: str, rows: list[dict[str, object]], _subject: str = Depends(require_scope('national_aggregate'))) -> dict[str, object]:
		"""Build a feed and show exactly what would leave. Suppression is applied here too, so the
		preview cannot show a row the push would drop — a preview that disagrees with the wire is
		worse than none. `cells_withheld` counts suppressed cells, not rows folded into an aggregate."""
		try:
			built, withheld = build_feed(feed, rows)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'feed': feed, 'granularity': FEED_GRANULARITY[feed], 'cells_withheld': withheld, 'rows': built}

	@app.post('/integrations/pheoc/feeds/{feed}')
	async def pheoc_feed_push(feed: str, rows: list[dict[str, object]], _subject: str = Depends(require_scope('national_aggregate'))) -> dict[str, object]:
		try:
			built, withheld = build_feed(feed, rows)
			accepted = await pheoc.push_feed(feed, built)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		except Exception as exc:
			raise HTTPException(status_code=502, detail='PHEOC did not accept the feed') from exc
		return {'feed': feed, 'offered': len(rows), 'cells_withheld': withheld, 'accepted': accepted}

	# §18.4 719 hotline — the app side of the callback and outcome wires. The outbound call is the
	# SOS path; what was missing was the inbound half, which is what closes the loop.
	@app.post('/integrations/hotline/follow-up')
	async def hotline_follow_up(payload: dict[str, object], _body: bytes = Depends(require_webhook())) -> dict[str, object]:
		"""719 → App: a follow-up message about a case. Recorded, and delivered into the alert feed so
		the person sees it where they see everything else.

		Signature-guarded: this writes into a feed a citizen reads, so an unsigned request here is
		someone else speaking as the national hotline.
		"""
		body = str(payload.get('message', '')).strip()
		if not body:
			# A bare assert here would surface as an unhandled 500: FastAPI does not translate
			# AssertionError into a 4xx, so request validation has to be an explicit refusal.
			raise HTTPException(status_code=422, detail='a follow-up needs a message')
		item = FeedItem(
			item_id='HF-' + str(payload.get('case_ref', 'unknown')), category='service',
			headline='Follow-up from the 719 hotline', body=body[:600], source='719 hotline', verified=True,
			published_iso=str(payload.get('at', '2026-01-01T00:00:00Z')), county=str(payload.get('county', 'national')),
		)
		await alerting.publish(item)
		return {'recorded': True, 'delivered': 'feed'}

	@app.post('/integrations/hotline/outcome')
	async def hotline_outcome(payload: dict[str, object], _body: bytes = Depends(require_webhook())) -> dict[str, object]:
		"""719 → App: the outcome code, where consented. No consent flag, no record — the code alone
		still says a named person called an outbreak hotline.

		The code is recorded as its own §18.4 row and, when the report names a number with an open
		callback request behind it, settles that request too. The route used to return
		`{'recorded': True}` and store nothing, so §18.4's fifth row was a wire that acknowledged a
		write it never made — and `outcome_code` was read nowhere in the tree, which is the tell: a
		field whose only occurrences are the line that reads it off the payload and the line that
		echoes it back is data the system collects and never uses.

		`msisdn` is *optional*, because the section's Data column for this row is the code alone.
		Requiring one refused the body the section describes — which the pre-existing webhook
		fixture (`{'outcome_code': 'transported', 'consented': True}`) caught — and it would also
		have made the row unreachable for two of the three calls it closes: a one-tap call and the
		auto-call on fall detection are dispatched from the SOS path and file no callback request,
		so an outcome that required a queue entry could only ever close the third.
		"""
		if payload.get('consented') is not True:
			return {'recorded': False, 'reason': 'outcome is recorded only with consent'}
		code = str(payload.get('outcome_code', '')).strip()
		if not code:
			raise HTTPException(status_code=422, detail='an outcome needs a code')
		msisdn = str(payload.get('msisdn', '')).strip() or None
		try:
			outcome = channels.record_call_outcome(code, msisdn)
		except (AssertionError, ValueError) as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'recorded': True, 'outcome_id': outcome.outcome_id, 'outcome_code': code,
		        'settled_request_id': outcome.call_ref}

	@app.get('/integrations/hotline/outcomes')
	async def hotline_outcomes(_subject: str = Depends(require_scope('assigned', purpose='outbreak_surveillance'))) -> list[dict[str, object]]:
		"""§18.4's outcomes, for the deployment that asked the hotline to ring someone.

		Scoped `assigned` and not opened, for the reason `/channels/callbacks` is: a row carries the
		number a call was about, which is a person's contact detail and, where it settled a request,
		the symptom behind it. The record has to be readable or the row is written and never used —
		the defect this wire was fixed from.
		"""
		return [o.model_dump(mode='json') for o in channels.call_outcomes()]

	# §18.5 MoHF — pull the facility list, and the two inbound wires (corrections out, verification in).
	@app.post('/facilities/import-mohf')
	async def facilities_import_mohf(county: str, _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""The bridge that was missing: `download_facilities` and `ingest_mohf` both existed and
		nothing joined them, so the facility list could be fetched and never entered the service."""
		try:
			rows = await mohf.download_facilities(county)
			accepted = await facilities.ingest_mohf([dict(r) for r in rows])
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		except Exception as exc:
			raise HTTPException(status_code=502, detail='the facility registry is unreachable') from exc
		return {'county': county, 'offered': len(rows), 'accepted': accepted}

	# The one MoHF wire that carried no guard, while its two siblings on the same block did. §18.5's
	# second row writes to the *national registry* under this deployment's credentials, so an open
	# route here is a proxy that spends our API key on someone else's behalf — the class
	# `sha_verify`'s own docstring already named it as ("the same class as the open facility proxy")
	# while the proxy itself stayed open. `infrastructure` is the scope both siblings carry, because
	# all three are the same wire to the same authority. §FND-001's citizen-facing crowdsourced half
	# is `POST /facilities/{facility_id}/reports`, which is free text published on a public feed;
	# this route forwards structured field corrections to MoHF's intake and is not that.
	@app.post('/facilities/{facility_id}/correction')
	async def facility_correction(facility_id: str, correction: dict[str, object],
	                              _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""App → MoHF, on report: a crowdsourced correction. A correction is not applied locally —
		the registry is the authority, and a local edit would diverge from it silently."""
		body = {'facility_id': facility_id, **correction}
		try:
			ticket = await mohf.report_correction(body)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		except Exception as exc:
			raise HTTPException(status_code=502, detail='the facility registry is unreachable') from exc
		return {'ticket': ticket, 'applied_locally': False}

	@app.get('/facilities/verification')
	async def facilities_verification(facility_ids: str, _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		ids = [f.strip() for f in facility_ids.split(',') if f.strip()]
		try:
			status = await mohf.verification_status(ids)
		except Exception as exc:
			raise HTTPException(status_code=502, detail='the facility registry is unreachable') from exc
		return {'status': status}

	# §18.6 SHA — cover, acceptance list, benefits.
	@app.post('/insurance/sha/verify')
	async def sha_verify(req: SHACheckRequest, _subject: str = Depends(require_scope('self'))) -> dict[str, object]:
		"""Cover verification against the real authority, not the offline stub. The service keeps the
		hash binding, so what is returned can only ever carry the hash of the number that was asked
		about. Guarded: an unguarded cover check is a member-number oracle spending our SHA
		credentials, the same class as the open facility proxy."""
		live = InsuranceService(sha)
		try:
			return (await live.check(req)).model_dump(mode='json')
		except Exception as exc:
			raise HTTPException(status_code=502, detail='SHA is unreachable') from exc

	@app.get('/insurance/sha/facilities')
	async def sha_facilities(county: str, _subject: str = Depends(require_scope('self'))) -> list[dict[str, object]]:
		try:
			return await sha.acceptance_list(county)
		except Exception as exc:
			raise HTTPException(status_code=502, detail='SHA is unreachable') from exc

	@app.get('/insurance/sha/benefits')
	async def sha_benefits(product: str = 'SHIF', _subject: str = Depends(require_scope('self'))) -> list[dict[str, object]]:
		try:
			return await sha.benefits(product)
		except Exception as exc:
			raise HTTPException(status_code=502, detail='SHA is unreachable') from exc

	# §18.7 PPB — registry and recalls in, suspicious reports out. `verify` is already at
	# /medicine/verify; these are the other three wires.
	@app.get('/medicine/registry')
	async def medicine_registry(since: str = '1970-01-01T00:00:00Z', _subject: str = Depends(require_scope('self'))) -> list[dict[str, object]]:
		try:
			return await ppb.registry(since)
		except Exception as exc:
			raise HTTPException(status_code=502, detail='the PPB registry is unreachable') from exc

	@app.get('/medicine/recalls')
	async def medicine_recalls(since: str = '1970-01-01T00:00:00Z', _subject: str = Depends(require_scope('self'))) -> list[dict[str, object]]:
		try:
			return await ppb.recalls(since)
		except Exception as exc:
			raise HTTPException(status_code=502, detail='the PPB registry is unreachable') from exc

	@app.post('/medicine/suspicious')
	async def medicine_suspicious(report: SuspiciousReport, _subject: str = Depends(require_scope('self'))) -> dict[str, object]:
		"""Report a suspected falsified medicine. Guarded so the PPB report is attributable and the
		egress is not an open relay to the regulator's intake."""
		try:
			ref = await ppb.report_suspicious(report)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		except Exception as exc:
			raise HTTPException(status_code=502, detail='the PPB registry is unreachable') from exc
		return {'ppb_case_ref': ref}

	# §18.8 Telco — zero-rating rules in, airtime out. SMS/USSD in and out already live in
	# /channels; the inbound SMS webhook is the piece that was missing.
	@app.get('/integrations/telco/zero-rating')
	async def telco_zero_rating() -> list[dict[str, object]]:
		try:
			return await telco.zero_rating_rules()
		except AssertionError as exc:
			raise HTTPException(status_code=503, detail=str(exc)) from exc
		except Exception as exc:
			raise HTTPException(status_code=502, detail='the carrier is unreachable') from exc

	@app.post('/integrations/telco/airtime')
	async def telco_airtime(msisdn: str, kes: int, reason: str, _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		try:
			ref = await telco.disburse_airtime(msisdn, kes, reason)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		except Exception as exc:
			raise HTTPException(status_code=502, detail='the carrier is unreachable') from exc
		return {'reference': ref}

	@app.post('/integrations/telco/sms/inbound')
	async def telco_sms_inbound(payload: dict[str, object], lang: str = 'en', _body: bytes = Depends(require_webhook())) -> dict[str, object]:
		"""Telco → App: an inbound SMS, routed through the same service the app's own messaging uses.

		Routed via `route_whatsapp`'s keyword intent path rather than the USSD menu: an SMS body is
		free text ("fever", "facility", "719"), not a menu selection, and feeding it to the USSD
		parser would refuse every real message with `USSD selections numeric`. The msisdn is
		normalised to the E.164 form the channel models require, because carriers deliver it bare.
		"""
		body = str(payload.get('text', '')).strip()
		if not body:
			raise HTTPException(status_code=422, detail='an inbound SMS needs text')
		# §CHAN-1's Format: "local language option via keyword (e.g., prefix `SW`, `LU`, `KY`)". The
		# prefix is read off the body the person actually sent, because `lang` above is a query
		# parameter and the sender of a text cannot set one — so the section's mechanism had no
		# implementation on the one channel it was written for. A body with no prefix is unchanged and
		# reads as English, which is what `answerable('en')` would have given anyway.
		from afya.strings import answerable, sms_language
		asked_lang, body = sms_language(body)
		if not body:
			raise HTTPException(status_code=422, detail='an inbound SMS needs text after its language prefix')
		# The asked-for language wins over the query parameter, and the response says which language
		# was served — the `served_in` rule §CHAN-1's own channel needs as much as the triage engine
		# does: a person who prefixed `LU` and is answered in English must be able to see that.
		lang = asked_lang
		# §5.4's one spelling of a phone number, from §5.4's one identity model. This route used to
		# strip a leading zero and the USSD callback prepend a `+`, so the same handset arrived as
		# `+254712345678` on one channel and `+0712345678` on the other — two identities for one
		# person, and a case-report dedup that could never match across the two.
		# Resolved through §5.4's identity model, which is also where the carrier's spelling is turned
		# into E.164 — the route does not normalise a second time. An earlier cut did, and the call was
		# dead: `subject_of` reaches `resolve`, which normalises, so the route's own call could not
		# change any answer. Two call sites for one rule is how a rule acquires two behaviours, so the
		# model's stands alone, and the canonical spelling is read back from the model rather than
		# recomputed here.
		try:
			subject = channels.subject_of(str(payload.get('from', '')).strip())
		except (AssertionError, ValueError) as exc:
			raise HTTPException(status_code=422, detail=f'an inbound SMS needs a Kenyan sender number: {exc}') from exc
		msisdn = identity.msisdn_for(subject)
		assert msisdn is not None, 'a resolved subject has a phone'
		# §ALT-002's "Works over SMS when data is unavailable": the family check-in has no app to
		# press a button in, so the message *is* the button and this is where it lands. Branching
		# here rather than inside `route_whatsapp` because that router is §CHAN-3's WhatsApp keyword
		# map and is synchronous — the check-in records a state and texts the family, which is I/O,
		# and a sync router cannot await it. A body that is not a safe word falls through to the
		# keyword map unchanged, so the triage and facility intents are reached exactly as before.
		if safe_intent(body) != 'none':
			reply = await alerting.check_in_by_msisdn(
				msisdn, body, datetime.now(timezone.utc).isoformat(timespec='seconds'), lang)
			# `intent` is named rather than left for the reply to imply: a carrier-side log and a
			# person reading the response both need to tell a check-in from a triage answer, and the
			# reply text alone does not say which branch produced it.
			return {'reply': reply, 'source': 'sms', 'intent': 'family-check-in',
			        'lang': answerable(lang), 'language_fallback': answerable(lang) != lang,
			        'linked': identity.is_linked(subject)}
		# §CHAN-1's Inbound use case "Callback requests (`CALLBACK`)" — the keyword form of the same
		# request §CHAN-2's second `→` prompt collects. Branching here rather than inside
		# `route_whatsapp` because that router returns a reply string and this records a request: a
		# keyword answered with a sentence and stored nowhere is the handler "ignoring" it in the
		# audit row's sense, however polite the sentence.
		#
		# Matched as a whole word, not as a substring: "callback" inside a longer message is a person
		# writing about a call, and treating every mention as a request would put a queue entry
		# against someone who asked for nothing.
		if body.strip().upper() == 'CALLBACK':
			from afya.strings import CALLBACK_ACK
			req = channels.record_callback(msisdn, session_id=f'sms:{subject}', symptom=None, lang=lang)
			return {'reply': CALLBACK_ACK[answerable(lang)], 'source': 'sms', 'intent': 'callback',
			        'request_id': req.request_id, 'lang': answerable(lang),
			        'language_fallback': answerable(lang) != lang, 'linked': identity.is_linked(subject)}
		out = channels.route_whatsapp(WhatsAppIn(from_msisdn=msisdn, body=body), lang)
		return {'reply': out.reply, 'source': 'sms',
		        'lang': answerable(lang), 'language_fallback': answerable(lang) != lang,
		        'linked': identity.is_linked(subject)}

	# --- §15.3 residency, §17.7 agreements, §15.4 capacity -----------------------------------
	# Three spec sections that were prose and nothing else. Residency is a decision made before a
	# request is built; the agreements are state the deployment must hold; the capacity report is
	# measured, and reports an unmeasured target as unmeasured rather than as met.

	@app.get('/governance/residency')
	async def governance_residency(_subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""Which data classes may reach which jurisdiction (§15.3). Read-only policy, but it names
		where case data is allowed to go, so it is infrastructure-scoped like the other config views."""
		from afya.governance.views import HOST_JURISDICTIONS, RESIDENCY_RULES
		return {
			'rules': {cls.value: sorted(j.value for j in allowed) for cls, allowed in RESIDENCY_RULES.items()},
			'hosts': sorted({host for host, _ in HOST_JURISDICTIONS}),
		}

	@app.get('/governance/residency/check')
	async def governance_residency_check(party: str, host: str, data_class: str,
			_subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""Answer, without sending anything, whether a transfer would be allowed. `data_class` is a
		query string rather than an enum so an unknown class is a 422 from the parser, not a 500."""
		from afya.governance.views import DataClass
		try:
			cls = DataClass(data_class)
		except ValueError as exc:
			raise HTTPException(status_code=422, detail=f'unknown data class {data_class!r}') from exc
		return governance.residency_decision(party, host, cls).model_dump(mode='json')

	@app.get('/governance/agreements')
	async def governance_agreements(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§17.7 sharing posture. Auditor-scoped: it says which parties we may lawfully share with,
		which is exactly the question an auditor asks."""
		return governance.sharing_posture()

	@app.post('/governance/agreements')
	async def governance_register_agreement(agreement: dict[str, object], _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""Record an agreement. Refused when a clause §17.7 names is missing, so an incomplete
		agreement cannot be registered and later read as one that permits sharing."""
		from afya.governance.views import DataSharingAgreement
		try:
			parsed = DataSharingAgreement.model_validate(agreement)
			governance.register(parsed)
		except (AssertionError, ValidationError) as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return governance.sharing_posture()

	@app.get('/governance/stack')
	async def governance_stack(_subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""§15.2's stack table and §15.1's diagram against what the build actually contains.

		Infrastructure-scoped: it names what runs and where, which is a deployment fact rather than
		something a citizen endpoint should be asked to assert. The three findings are separate
		questions — an unbacked layer is a claim reading as true, a deferred layer is one the
		programme has not stood up, and a diverged layer is one running something other than the
		spec's choice. Collapsing them would let a deferral read as compliance.
		"""
		return governance.stack_report().model_dump(mode='json')

	@app.get('/governance/capacity')
	async def governance_capacity(_subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""§15.4 targets and, where the deployment has measured them, the observed value. With no
		measurements supplied every target is unmeasured, and `all_measured_targets_met` is false —
		the honest report for a process that has not been load-tested."""
		return governance.capacity_report().model_dump(mode='json')

	@app.post('/governance/capacity')
	async def governance_capacity_measured(observed: dict[str, float], _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""Check a set of measurements against §15.4. A metric the spec names but the caller did not
		measure stays unmeasured; an unknown metric is refused rather than silently ignored."""
		known = {t.metric for t in governance.targets()}
		unknown = sorted(set(observed) - known)
		if unknown:
			raise HTTPException(status_code=422, detail=f'not §15.4 metrics: {unknown}')
		return governance.capacity_report(observed).model_dump(mode='json')

	@app.get('/governance/open-questions')
	async def governance_open_questions(_subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""Appendix D's seven decisions, each with the place it bites and the value the code carries
		while it is open.

		Infrastructure-scoped: it names the retention cap, the residency table and the activation
		gate as undecided, which is a deployment fact rather than something a citizen endpoint
		should be asked to assert. `unresolved` is the finding — a row naming a `module:attr` that
		no longer resolves is a blocker someone will believe is tracked after the code it names is
		gone. Nothing here is a verdict on the decision itself; the spec says these are the
		owner's, and this says only where each one lands.
		"""
		return {
			'questions': [q.model_dump(mode='json') for q in governance.open_questions()],
			'unresolved': governance.unresolved_questions(),
		}

	@app.get('/governance/egress')
	async def governance_egress(_subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""Every configured outbound wire classified against §15.3, with its party and data class.

		This reads the *deployment's* URLs, so a host set in the environment that a class may not
		reach is reported here rather than discovered on the wire. `violations` is the actionable
		list; an empty one means every configured wire is inside its jurisdiction."""
		from afya.config import ServiceConfig
		cfg = ServiceConfig.from_env()
		urls = {
			'adam': cfg.adam_url, 'pheoc': cfg.pheoc_url, 'jali': cfg.jali_url, 'sha': cfg.sha_url,
			'mohf': cfg.mohf_url, 'ppb': cfg.ppb_url, 'sms': cfg.at_base_url,
			'whatsapp': 'https://graph.facebook.com' if cfg.wa_token else '',
		}
		decisions = governance.audit_egress(urls)
		return {
			'decisions': [d.model_dump(mode='json') for d in decisions],
			'violations': [d.model_dump(mode='json') for d in decisions if not d.allowed],
		}

	# --- §17.5 security controls, scans and disclosure ----------------------------------------
	# §17.5 is a table of eleven controls; this makes each one name where it is enforced, and holds
	# the recurring scan obligations so "monthly" is a date rather than an intention.

	@app.get('/security/controls')
	async def security_controls(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""The §17.5 control table with each row's enforcement named. Auditor-scoped: this is the
		evidence a reviewer asks for, and it names no secret."""
		return {'controls': [c.model_dump(mode='json') for c in security.controls()]}

	@app.get('/security/posture')
	async def security_posture(today_iso: str = '2026-10-10', _subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""Control table, CI-enforced commands, scan obligations and open findings. An obligation
		never performed is overdue, not exempt."""
		from datetime import date as _date
		return security.posture(_date.fromisoformat(today_iso)).model_dump(mode='json')

	@app.post('/security/scans')
	async def security_record_scan(scan: dict[str, object], _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""Record a completed scan. The outcome is what makes the monthly cadence a fact rather than
		a schedule — a scan with critical findings is logged loudly."""
		from afya.security.views import VulnerabilityScan
		try:
			recorded = security.record_scan(VulnerabilityScan.model_validate(scan))
		except (AssertionError, ValidationError) as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return recorded.model_dump(mode='json')

	@app.get('/security/disclosure')
	async def security_disclosure() -> dict[str, object]:
		"""§17.5 bug bounty: the public programme and its responsible-disclosure terms. Open by
		design — a disclosure policy nobody can read is not a disclosure policy."""
		return security.disclosure_policy().model_dump(mode='json')

	@app.get('/security/licence')
	async def security_licence() -> dict[str, object]:
		"""§LOC-002's "Open-source client for independent verification" and §SEC-006's "Open-source
		client code", as the fact a reader can obtain rather than a claim about the repository.

		Open, like `/security/disclosure` and for the same reason: a licence that required a token
		would not be the licence the client is offered under. `offered` is read from the root
		`LICENSE` file rather than returned from a constant, so a tree that declares MIT and ships
		no terms answers `false` instead of asserting something it cannot show.
		"""
		from afya.licensing import licence_offer
		return licence_offer()

	# --- §23 risk register, §24 operational duties and incident response ----------------------

	@app.get('/operations/risks')
	async def operations_risks(domain: str | None = None,
	                           _subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§23's register, worst exposure first, with each row's mitigation checked against the code.

		Auditor-scoped like the other evidence views. The interesting field is `unbacked_risks`: a
		mitigation that names a module which does not exist is a risk the register presents as
		handled and is not, and that is the one thing this route exists to say out loud.
		"""
		from afya.operations.views import RiskDomain
		rows = operations.register() if domain is None else [
			a for a in operations.register() if a.risk.domain is RiskDomain(domain)
		]
		return {
			'risks': [a.model_dump(mode='json') for a in rows],
			'unbacked_risks': [a.risk.risk_id for a in rows if not a.resolves],
			'counts_by_domain': {d.value: len(operations.risks(d)) for d in RiskDomain},
		}

	@app.get('/operations/incidents')
	async def operations_incidents(today_iso: str = '2026-10-10',
	                               _subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§24.8's incident types, the §24.3 SLA each severity maps to, and every open incident's
		position against its own deadline. A breach's 72 hours run from detection."""
		return operations.posture(today_iso).model_dump(mode='json')

	@app.post('/operations/incidents')
	async def operations_open_incident(incident: dict[str, object],
	                                   _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""Open an incident. Operations scope: §24.8's team is the on-call engineer and the DPO,
		and opening a record that starts a statutory clock is not a citizen action."""
		from afya.operations.views import Incident
		try:
			parsed = Incident.model_validate(incident)
		except ValueError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		status = operations.open_incident(parsed)
		return {**status.model_dump(mode='json'), 'rca_due_on': operations.rca_due_on(parsed)}

	@app.get('/operations/duties')
	async def operations_duties(today_iso: str = '2026-10-10',
	                            _subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§24.2's and §24.7's recurring duties and whether each is late. A duty never performed is
		overdue rather than exempt — the rule §17.5's scan cadence already applies."""
		statuses = operations.obligation_status(today_iso)
		return {
			'duties': [s.model_dump(mode='json') for s in statuses],
			'overdue': [s.obligation_id for s in statuses if s.overdue],
			'event_triggered': [s.obligation_id for s in statuses if s.cadence_days is None],
		}

	@app.get('/operations/governance')
	async def operations_governance(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§24.1's six governance bodies and §24.3's five support channels, crossed against §24's duty
		rows. A body accounting for no duty is a committee the register cannot tell apart from one
		that governs; a support channel with no coverage window is one nobody reads.

		Auditor-scoped: it names roles and headcounts, not people."""
		return operations.governance().model_dump(mode='json')

	@app.get('/operations/support-plan')
	async def operations_support_plan(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§24.4's training matrix and §24.5's funding model, crossed against §24.1's bodies and §21's
		phases. An audience no body accounts for is one nobody in the governance structure is
		responsible for teaching; a §21 phase no funding band covers is one nothing pays for.

		Auditor-scoped: it is a staffing and funding plan, and it names roles rather than people."""
		return operations.support_plan().model_dump(mode='json')

	@app.get('/operations/sustainability')
	async def operations_sustainability(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§24.6's eight mitigations, each resolved against the artefact it names — the same rule §23's
		mitigation column follows, applied to the section that argues the product outlives the
		outbreak. A mitigation naming a capability the build does not have is a claim that reads as a
		plan and is not one.

		Auditor-scoped: it is a funding and continuity argument, and it names no person."""
		return operations.sustainability().model_dump(mode='json')

	@app.post('/operations/duties/{obligation_id}/performed')
	async def operations_mark_duty(obligation_id: str, on_iso: str,
	                               _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""Record that a duty was discharged. Without this every cadence obligation is overdue from
		the first day, which is true but not useful — the date is what makes the cadence a fact."""
		try:
			operations.mark_performed(obligation_id, on_iso)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'ok': True, 'overdue': operations.overdue(on_iso)}

	# --- §20 growth, §21 phasing --------------------------------------------------------------

	@app.get('/rollout/phases')
	async def rollout_phases() -> dict[str, object]:
		"""§21.1's seven phases with their tier ceilings and channel sets. Open by design: a rollout
		plan nobody outside the programme can read is not a plan a partner can align to, and it
		names no person and no number about one.

		The channel handles are resolved to §5.2's names before they travel. This route served
		`CHAN-000`–`CHAN-006` and §21.1's Channels cell verbatim on an anonymous surface, which is
		the one rollout read that broke the public/evidence split `public_plans` and
		`/rollout/acquisition` already keep. The ids stay on `/rollout/status`, which is scoped and
		where the id is the finding."""
		from afya.rollout.views import Phase
		current = rollout.status(Phase.phase_1_information, 1 if not registry.tier4_active() else 4)
		return {
			'phases': rollout.public_phases(),
			'current': {
				'phase': current.phase.value, 'objective': current.objective,
				'max_tier': current.max_tier, 'active_tier': current.active_tier,
				'phase_mismatch': current.phase_mismatch, 'note': current.note,
			},
		}

	@app.get('/rollout/app-size')
	async def rollout_app_size() -> dict[str, object]:
		"""§16.5's delivery table summed by where each row lands — base install against the §20.2
		lever 5 budget, on-demand modules reported beside it rather than folded in.

		Open like `/rollout/phases`: it is a plan a partner or a telco reads, and it names no person."""
		return rollout.app_size().model_dump(mode='json')

	@app.get('/rollout/launch')
	async def rollout_launch() -> dict[str, object]:
		"""§20.5's 18-step launch sequence, grouped by the three windows the section schedules them in.

		Open like `/rollout/phases`: it is the timeline a telco, an NGO or a county team reads to know
		what happens when, and it names no person and no number about one."""
		plan = rollout.launch_plan()
		return {
			'steps': [s.model_dump(mode='json') for s in plan.steps],
			'counts': plan.counts,
			'note': plan.note,
		}

	@app.get('/rollout/readiness')
	async def rollout_readiness(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§20.2's two claims about this repo — an open-source client and a sub-15 MB app — answered
		from the artefacts, plus §20.6's retention table crossed against the registry.

		Auditor-scoped: this is the evidence half, and it reports what is *not* measured rather than
		leaving a silent pass."""
		return rollout.readiness().model_dump(mode='json')

	@app.get('/rollout/acquisition')
	async def rollout_acquisition() -> dict[str, object]:
		"""§20.3's channel-by-channel acquisition plan and §20.4's partnership map, with §20.2's levers
		crossed against the partners they name.

		Open like `/rollout/phases`: it is the document a telco, an NGO or a county team reads to see
		what is being asked of them, and it names no person. The §20.3 rows carry their registry
		handles, so this is the one rollout surface that must not be served where a partner reads it
		— the handles are dropped below for the same reason `/rollout/plan` drops its own."""
		plan = rollout.acquisition()
		return {
			'channels': [{'channel': c.channel, 'label': c.label, 'role': c.role, 'tactics': c.tactics}
				for c in plan.channels],
			'partner_types': [p.model_dump(mode='json') for p in plan.partner_types],
			'partner_count': plan.partner_count,
			'lever_partners': plan.lever_partners,
			'note': plan.note,
		}

	@app.get('/rollout/acquisition/levers')
	async def rollout_levers() -> dict[str, object]:
		"""§20.2's six growth levers, with the two that claim something about this repository answered
		from the artefacts rather than restated.

		Open like `/rollout/phases` and `/rollout/acquisition`: it is the strategy a telco, an NGO or
		a county team reads to see what is being asked of them, and it names no person.

		`action_cell` is dropped from the payload, the way `/rollout/acquisition` drops `feature_id`:
		it is the section's Action column verbatim and §20.2 lever 4's carries the handle `CHAN-5`, so
		serving the model as-is would put a traceability handle on the one rollout surface a partner
		reads. `action` is that cell with the id resolved to the registry's name, which is what
		travels."""
		plan = rollout.lever_plan()
		return {
			'levers': [
				{'number': le.number, 'lever': le.lever, 'why': le.why, 'action': le.action,
				 'checkable': le.checkable, 'check': le.check}
				for le in plan.levers
			],
			'unbacked_claims': plan.unbacked_claims,
			'note': plan.note,
		}

	@app.get('/rollout/acquisition/coverage')
	async def rollout_acquisition_coverage(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""The evidence half: the §20.3 rows with their registry handles, the §5.2 channels §20.3
		leaves unmapped, and the §20.2 levers resting on a partner §20.4 does not list.

		Auditor-scoped for the same reason `/rollout/plan/readiness` is: here the id *is* the finding."""
		return rollout.acquisition().model_dump(mode='json')

	@app.get('/rollout/status')
	async def rollout_status(phase: str, _subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§21.1's tier ceiling for a phase against what is actually active. A deployment running
		Tier 4 while its plan says Phase 2 skipped its own gate, and that is the finding.

		Auditor-scoped like every other read in this family: the convention here is reads on
		`audit_logs` and writes on `infrastructure`, and this route changes nothing."""
		from afya.rollout.views import Phase
		# The ceiling the deployment is actually running at: Tier 4 when the §11.1 gate is open,
		# otherwise the highest tier among the features that are live. `Tier.cross_cutting` is 0 and
		# is always on, so it cannot be the answer to "which tier is this deployment at".
		active = 4 if registry.tier4_active() else max(
			(s.tier for s in registry.available() if s.tier is not Tier.cross_cutting), default=Tier.tier1
		)
		try:
			return rollout.status(Phase(phase), max(1, int(active))).model_dump(mode='json')
		except (ValueError, AssertionError) as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/rollout/plan')
	async def rollout_plan() -> dict[str, object]:
		"""§21.2–21.7's six phase sections: each phase's objective, deliverables and success
		criteria, with §21.6's testing.

		Open like `/rollout/phases` and for the same reason — it is the plan a county team or a
		partner aligns to, and it names no person. The deliverables are text and the criteria are
		the sections' own numbers; nothing here is about an individual."""
		return {'plans': rollout.public_plans()}

	@app.get('/rollout/plan/readiness')
	async def rollout_plan_readiness(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""Each phase's plan crossed against the registry and against §22, as the evidence half.

		Auditor-scoped like its siblings. Three findings a reader needs separately: a deliverable
		naming a feature the registry does not carry, a success criterion with no §22 KPI behind it
		so the phase's own exit cannot be computed, and §21 and §22 stating different numbers for
		the same measure. The drift is reported rather than resolved — both sections are the
		product owner's and this build does not get to pick a winner between them."""
		plans = rollout.rollout_plan()
		return {
			'plans': [p.model_dump(mode='json') for p in plans],
			'not_ready': [p.phase.value for p in plans if not p.ready],
			'criterion_drift': {p.phase.value: p.criterion_drift for p in plans if p.criterion_drift},
		}

	# --- §4: who the launch is for ------------------------------------------------------------
	# §4.1's personas, §4.2's audiences and §4.3's priorities. The catalogue is open — it is the
	# product's own description of its users, carries nothing about a person, and the channels are
	# already told who they are writing for. The coverage read is not: it is an audit of the build
	# against the section, in the same family as `/rollout/readiness`.
	@app.get('/personas')
	async def personas_catalogue() -> dict[str, object]:
		"""§4.1's seven personas with the §4.3 segments they belong to, and §4.2's audiences."""
		return {
			'personas': [p.model_dump(mode='json') for p in personas.personas()],
			'secondary': [s.model_dump(mode='json') for s in personas.secondary()],
		}

	@app.get('/personas/segments')
	async def personas_segments(priority: str | None = None) -> dict[str, object]:
		"""§4.3's eight rows in priority order, each with the §4.1 personas that carry it. The
		ordering is the section's, which is why `priority` filters rather than sorts."""
		from afya.personas.views import Priority
		try:
			wanted = Priority(priority) if priority is not None else None
		except ValueError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'segments': [s.model_dump(mode='json') for s in personas.segments(wanted)]}

	@app.get('/personas/coverage')
	async def personas_coverage(_subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		"""§4 crossed against the language matrix, the channel table and §17.4 — what the section
		names that the product does not carry. Scoped like `/rollout/readiness` because it is the
		same kind of answer: the build's own gaps, not a user-facing fact."""
		return personas.coverage().model_dump(mode='json')

	# --- §CHAN-000's call-in and §CHAN-004's clinician Q&A --------------------------------------
	# A live programme is the one §5 content format that is not a document: it has a schedule, a
	# queue and a record of what was answered, and this tree had none of the three. The routes below
	# are those three, and the guard on each follows the dataset it serves rather than the feature it
	# belongs to — the *queue* holds callers' words and their handles, so it is scoped like the
	# callback queue; the *transcript* is the published record and holds no person, so it is open.
	#
	# The queue is worked by a *health worker*, which is §CHAN-000's own wording — and §17.4 gives
	# that role `assigned`, "the people and tasks allocated to it". §CHAN-004's clinician is named
	# on the session (`LiveSession.clinician`) rather than holding a token of their own: `clinician`
	# in §17.4's table is scoped `consented_patient`, which is a read of *another person's record*
	# through a share, and hosting a broadcast is not that. Widening either role would put a
	# patient-record scope on a queue, so the guard is the one scope the section actually names.
	@app.post('/live/sessions')
	async def live_schedule(session: LiveSession, _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""Put a programme on the schedule. Scoped as content publishing is: §17.4's eight roles hold
		no "broadcaster", and putting a clinician on air is operations, not a ninth role."""
		try:
			scheduled = await live.schedule(session)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return scheduled.model_dump(mode='json')

	@app.get('/live/sessions')
	async def live_sessions(platform: str | None = None, status: str | None = None) -> dict[str, object]:
		"""The schedule as a listener reads it — what is on, and when. No token, no person in it.

		Open for the reason `/info/library` is: an announcement of a call-in programme is the thing
		that makes it a call-in programme, and one behind a token reaches nobody.
		"""
		try:
			wanted_platform = LivePlatform(platform) if platform else None
			wanted_status = LiveStatus(status) if status else None
		except ValueError as exc:
			raise HTTPException(status_code=422, detail=f'unknown session filter: {exc}') from exc
		rows = live.sessions(wanted_platform, wanted_status)
		return {'sessions': [s.model_dump(mode='json') for s in rows], 'count': len(rows)}

	@app.post('/live/sessions/{session_id}/open')
	async def live_open(session_id: str,
                    _subject: str = Depends(require_scope('assigned', purpose='community_health_delivery'))) -> dict[str, object]:
		"""Start the programme. This is the instant the queue becomes writable."""
		try:
			return (await live.open(session_id)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/live/sessions/{session_id}/close')
	async def live_close(session_id: str,
                     _subject: str = Depends(require_scope('assigned', purpose='community_health_delivery'))) -> dict[str, object]:
		"""End the programme, and report how many questions were left unanswered on it.

		The count is in the response rather than left to a later read because it is the number the
		clinician closing the session is the last person able to do anything about.
		"""
		try:
			closed = await live.close(session_id)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		left = [q for q in live.queue(session_id, pending_only=True)]
		return {**closed.model_dump(mode='json'), 'left_unanswered': len(left)}

	@app.get('/live/sessions/{session_id}/queue')
	async def live_queue(session_id: str, pending_only: bool = False,
	                     _subject: str = Depends(require_scope('assigned', purpose='community_health_delivery'))) -> dict[str, object]:
		"""The queue as the clinician running the programme reads it, oldest first.

		Scoped `assigned` for the reason `/channels/callbacks` is: this is the one read of a live
		session that holds what people said. The handle is a weaker disclosure than a name rather
		than no disclosure, and a weaker disclosure is still one that needs a role.
		"""
		try:
			rows = live.queue(session_id, pending_only=pending_only)
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc
		return {'questions': [q.model_dump(mode='json') for q in rows], 'count': len(rows)}

	@app.post('/live/sessions/{session_id}/questions')
	async def live_ask(session_id: str, body: QuestionIn,
	                   subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:
		"""Ask a question on a live programme. The asker is the token, and there is no field to lie in.

		`names_subject=False` because the body names no subject and there is nothing to compare — the
		route binds the asker to the token itself. The handle is then *derived* from that subject, so
		what the queue carries is a §SEC-004 rotating name rather than the person: the same asker
		carries a different handle next month, and a reader of the queue cannot assemble a question
		history out of it.
		"""
		try:
			asked = await live.ask(session_id, live.handle_for(subject, clock_ms()), body.text,
			                       at_ms=clock_ms(), lang=body.lang)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		# The handle is not in the response: the asker already knows who they are, and a response
		# body is the easiest place for an identifier to end up somewhere it was never meant to go.
		return {'question_id': asked.question_id, 'session_id': asked.session_id, 'status': asked.status.value}

	@app.post('/live/questions/{question_id}/answer')
	async def live_answer(question_id: str, body: AnswerIn,
                      subject: str = Depends(require_scope('assigned', purpose='community_health_delivery'))) -> dict[str, object]:
		"""Answer one queued question, with §6.2's finding on the answer carried rather than raised.

		The verdicts come back in the response so the screen the clinician is typing on can show
		them, which is the same reason `InfoService.content_verdicts` returns rather than raises. The
		answer is *recorded* either way: §6.2 would refuse ordinary clinical speech — "it is likely a
		viral infection" names no action, and an em dash is outside GSM-7 — so a gate that rejected on
		the finding would refuse correct medicine from a doctor answering live. What a supervisor can
		act on is the stigmatising sentence, and that is on the row it is on.
		"""
		try:
			answered = await live.answer(question_id, body.answer, subject, clock_ms())
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return answered.model_dump(mode='json')

	@app.post('/live/questions/{question_id}/decline')
	async def live_decline(question_id: str, body: DeclineIn,
                       _subject: str = Depends(require_scope('assigned', purpose='community_health_delivery'))) -> dict[str, object]:
		"""Decline a question, with the reason recorded. §6.2 is not consulted: there is no answer."""
		try:
			return (await live.decline(question_id, body.reason, clock_ms())).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/live/sessions/{session_id}/transcript')
	async def live_transcript(session_id: str) -> dict[str, object]:
		"""§CHAN-000's "record of a call answered", published.

		Open, and that is the point of the row: the audit note's absence was "no record of a call
		answered", and a record behind a token is a record of a call answered that the person who
		missed the programme cannot read. It holds no person — the entries are built from
		`TranscriptEntry`, which has no field for a handle — so there is nothing here for a scope to
		protect.
		"""
		try:
			return live.transcript(session_id).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	# --- §CHAN-004: user-generated content, with consent and moderation ------------------------
	# The section prints one bullet — "User-generated content from satisfied users (with consent)"
	# — and the two halves of it are two guards. A submission is filed *by* the person whose words
	# they are, so the route carries `subject_ref` and `require_self` binds it to the token: a story
	# filed against someone else's consent is the defect the guard exists to stop, and the model
	# compares the subject because a §SEC-004 handle is a different value derived from the subject
	# and a check written against the handle would silently never fire.
	#
	# Moderation is not publication. `approve` drafts a `ContentItem` and hands it to §6.5's
	# existing workflow, so a story still walks clinical review, translation, back-translation and
	# community validation — which is why the moderation queue is `infrastructure` (content ops, as
	# publishing is) rather than a scope of its own.
	@app.post('/info/stories')
	async def info_story_submit(body: StoryIn,
	                            subject: str = Depends(require_self())) -> dict[str, object]:
		"""File a story. Refused without a real consent record behind it, by `submit`.

		`require_self()` with `names_subject` at its default, because the body *does* name
		`subject_ref` and the guard compares it to the token: a story filed against someone else's
		consent is the defect the comparison exists to stop. The author handle is derived from the
		token's own subject rather than sent, so the queue cannot be filled under another name.
		"""
		story = body.as_submission(live.handle_for(subject, clock_ms()))
		try:
			filed = stories.submit(story, privacy.consent_record(story.consent_id))
		except PermissionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc
		except AssertionError as exc:
			raise HTTPException(status_code=409, detail=str(exc)) from exc
		return filed.model_dump(mode='json')

	@app.get('/info/stories/pending')
	async def info_stories_pending(
			_subject: str = Depends(require_scope('infrastructure'))) -> list[dict[str, object]]:
		"""The moderation queue. It holds people's own words, so it is content ops."""
		return [s.model_dump(mode='json') for s in stories.pending()]

	@app.post('/info/stories/{story_id}/moderate')
	async def info_story_moderate(story_id: str, body: StoryModerationIn,
	                              subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""Approve into §6.5's draft stage, or decline with a reason. Neither publishes.

		Approval returns the drafted item's id rather than the story, because the thing that changed
		is a `ContentItem` in the workflow and a caller told "approved" would reasonably think a
		reader can now see it. A story that is approved and not yet published is invisible to
		`library()`, and the response says which stage it is at. Who moderated is the token, so the
		record names an actor the caller could not have typed.
		"""
		try:
			if body.decision == 'approve':
				item = await stories.approve(story_id, subject, body.at_ms)
				return {'story_id': story_id, 'approved': True, 'content_id': item.item_id,
				        'stage': item.stage.value, 'published': False}
			declined = stories.decline(story_id, subject, body.note or '', body.at_ms)
			return declined.model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc
		except PermissionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc

	# --- §15.5 versioning: `/v1/` beside the bare paths --------------------------------------
	# Both spellings reach the same routes. `v1` is the only version, so pinning it changes
	# nothing today; it exists so that when a `v2` diverges, it mounts here and the bare paths can
	# stay on `v1` — which is what makes the pin mean something instead of being decoration.
	# The wrapper is a facade: it holds no routes of its own, so the OpenAPI spec it publishes is
	# the API's own, not an empty description of a mount table.
	root = FastAPI(title='Afya Yangu / Mlinzi', version=APP_VERSION, openapi_url=None, docs_url=None, redoc_url=None)
	# The facade holds no routes of its own, so its own spec would describe a mount table. Point it
	# at the API's, which is what `create_app().openapi()` is read for — the catalogue drift-lock
	# test and the published `/openapi.json` both depend on it returning real routes.
	root.openapi = app.openapi  # type: ignore[method-assign]

	@root.get('/')
	async def api_index() -> dict[str, object]:
		return {
			'service': 'Afya Yangu / Mlinzi', 'current_version': CURRENT_API_VERSION,
			'versions': list(API_VERSIONS), 'docs': f'/{CURRENT_API_VERSION}/docs',
		}

	@root.get('/openapi.json')
	async def openapi_spec() -> JSONResponse:
		return JSONResponse(app.openapi())

	for _version in API_VERSIONS:
		root.mount(f'/{_version}', app)
	root.mount('/', app)
	assert len(root.routes) >= len(API_VERSIONS) + 2, 'index, spec and every version must be mounted'
	return root
