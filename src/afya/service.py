"""App assembly — FastAPI front door (spec §15.5)."""
from afya.surveillance.service import SurveillanceService, estimate_breath_rate
from afya.surveillance.views import CountySignal, Geofence, ProximityToken

from fastapi import Body, Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from httpx import AsyncClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError

import json
import os
from typing import cast

from afya.brand.service import BRAND, NON_GOALS, PRINCIPLES, VISION, brand_is_clean, brand_violations
from afya.problem.service import gap_report, lesson_report
from afya.content_audit.service import content_report
from afya.config import ServiceConfig
from afya.persistence.service import SqliteStore
from afya.channels.cost import ZeroRatingRule, parse_rules, zero_rating_gaps
from afya.channels.attention import attention_report
from afya.channels.service import AfricaTalkingSmsPort, ChannelService
from afya.channels.views import ChwTask, SmsOut, UssdRequest, WhatsAppIn
from afya.emergency.service import EmergencyService, Inline719Port
from afya.identity.service import IdentityService
from afya.identity.views import IdentityLink, PhoneConsent
from afya.emergency.views import EmergencyCard, IMUSample, SOSEvent
from afya.evidence.service import EvidenceService, FileSystemEvidenceStore
from afya.integrations.gateways import AtSmsRestSend, AtUssdCallback
from afya.integrations.overpass import OverpassClient
from afya.places.service import Place, PlaceKind, PlacesService
from afya.evidence.views import EvidenceSubmission, EvidenceKind
from afya.insurance.service import InlineSHAPort, InsuranceService, SHACheckRequest, PriceItem
from afya.maternal.service import MaternalService
from afya.maternal.views import ANCRecord, Pregnancy
from afya.mental.service import MentalHealthService, WHO5
from afya.women.service import WomenService
from afya.women.views import CycleLog
from afya.alerts.service import AlertsService
from afya.alerts.views import AirQuality, CommunityAlert, FloodReport, WaterQuality
from afya.blood.service import BloodRequest, BloodService, Donor
from afya.chronic.service import ChronicService
from afya.chronic.views import BPReading, GlucoseReading, RefillTracker
from afya.integrations.adam import AdamClient
from afya.integrations.feeds import FEED_CADENCE, FEED_GRANULARITY, MIN_CELL, build as build_feed
from afya.integrations.service import InlineJaliPort, JaliClient, JaliPort, MoHFFacilityClient, PPBClient, PheocClient, SHAClient, TelcoGatewayClient
from afya.medicine.service import MedicineService
from afya.medicine.views import DoseRequest, StockReport, VerifyRequest
from afya.facilities.service import FacilityService
from afya.facilities.views import Booking, Facility, NearestRequest
from afya.info.escalation import CORRECTION_FEED_CATEGORY, ContentError
from afya.info import health_education
from afya.info.localisation import BackTranslation, CommunityValidation, workflow_for
from afya.info.recency import instant_iso
from afya.info.service import InfoService
from afya.info.views import WORKFLOW, ContentItem, CountyRisk
from afya.privacy.service import PrivacyService
from afya.privacy.views import _SCOPE, ConsentCategory, ConsentRecord, DPIAInput, RBACRole
from afya.privacy.service import BLOCKING_TOPICS, DPIA_TOPICS
from afya.privacy import rbac
from afya.records.service import RecordsService
from afya.records.views import GrowthRecord, ImmunisationRecord, LabResult, WalletMember
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
from afya.sensors.views import SenseKind
from afya.sensors.views import SenseIngest
from afya.sync.service import SyncService, apply_delta, delta_payload
from afya.sync.views import ConnectionClass, SyncOp
from afya.triage.service import TriageService
from afya.triage.views import DiaryEntry, TriageInput, TriageResult

# spec-coverage domains (§9.1, §9.6, §10.2-10.4, §11.4-11.5, §12, §17, §19)
from afya.access.service import AccessService
from afya.access.views import AccessProfile, VoiceRequest
from afya.ai.service import AIService
from afya.analytics.service import AnalyticsService
from afya.analytics.views import DASHBOARDS, DashboardId
from afya.metrics.service import MetricsService
from afya.metrics.views import MetricFamily
from afya.ai.views import AggregateCell, FairnessAudit, RedressRequest, RiskInputs, WarningSignal
from afya.alerting.service import AlertingService
from afya.alerting.views import ExposureAck, FeedItem, FeedPage, FamilyStatus
from afya.auth.service import AuthService
from afya.auth.views import PKCEStart, PKCETokenRequest, StaffProvision, TokenRequest
from afya.auth.views import now_ms as clock_ms
from afya.chw.service import ChwService
from afya.intermediaries.service import IntermediaryService
from afya.chw.views import ActivityLogEntry, ChwCase, ChwProfile
from afya.intermediaries.views import Incentive, Intermediary, Referral
from afya.community.service import CommunityService
from afya.community.views import (
	CaseReport, CaseStatus, CommunityIssue, ContactEntry, ContactList, MisinfoSubmission, PeerAlert,
)
from afya.location.service import LocationService
from afya.location.views import (
	BorderPost, CheckIn, CheckInPoint, EncounterToken, ExposureDeclaration, LocationPoint,
	TravelerDeclaration,
)
from afya.monitoring.service import MonitoringService
from afya.monitoring.views import (
	AdherenceEvent, ConditionProfile, FoodSafetyAlert, MedSchedule, MonitoringDay, PeakFlowReading,
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
	model_config = MODEL_CONFIG
	drugs: list[str]


class DPIAReviewRequest(BaseModel):
	"""§17.3's review as a thing that happened: which processing, when, and by whom. The `reviewed_by`
	and `reviewed_at_iso` are required rather than defaulted, because a review with no reviewer and no
	date is the boolean this replaced wearing two extra fields."""
	model_config = MODEL_CONFIG
	processing: DPIAInput
	reviewed_at_iso: str
	reviewed_by: str


def build_services(http: AsyncClient | None = None, db_path: str | None = None) -> dict[str, object]:
	client = http or AsyncClient(timeout=10)
	cfg = ServiceConfig.from_env()
	registry = FeatureRegistry()
	sms_port = AtSmsRestSend(cfg.at_base_url, cfg.at_api_key, cfg.at_username, client) if cfg.at_api_key else AfricaTalkingSmsPort(cfg.at_base_url, cfg.at_api_key or 'dev-key')
	store = SqliteStore(db_path) if db_path else None
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
	triage_svc = TriageService(registry)

	async def telco_rules() -> list[ZeroRatingRule] | None:
		"""The carrier's zero-rating rules, as rules. Failure is the channel service's to report.

		No try/except here: an unconfigured deployment and an unreachable carrier are both "the
		rules were not pulled", which `ChannelService.zero_rating_rules` already turns into None and
		logs. Swallowing it here as well would be a second place that decides what a failure means.
		"""
		return parse_rules(await telco.zero_rating_rules())

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
		'surveillance': SurveillanceService(registry, privacy_svc),
		'sensors': SensorService(registry),
		'medicine': MedicineService(PPBClient(cfg.ppb_url, client, '')),
		'facilities': FacilityService(),
		# §5.3 CHAN-1's zero-rating is an agreement with the carrier, so the channel service is
		# handed the telco client's rules rather than a boolean. A deployment with no telco
		# configured passes nothing and reports every free claim as unverified.
		'channels': ChannelService(sms_port, telco_rules, triage_svc, identity_svc, privacy_svc),
		'emergency': EmergencyService(Inline719Port()),
		'info': InfoService(),
		'records': RecordsService(),
		'women': WomenService(),
		'maternal': MaternalService(),
		'chronic': ChronicService(),
		'mental': MentalHealthService(),
		'blood': BloodService(),
		'alerts': AlertsService(),
		'insurance': InsuranceService(InlineSHAPort()),
		'places': PlacesService(),
		'evidence': EvidenceService(registry, FileSystemEvidenceStore('var/evidence')),
		'sync': SyncService(store),
		'monitoring': MonitoringService(),
		'identity': identity_svc,
		'community': CommunityService(identity_svc),
		'alerting': AlertingService(),
		'realtime': RealtimeService(),
		'location': LocationService(),
		'ai': AIService(),
		'analytics': AnalyticsService(),
		'metrics': MetricsService(),
		'access': AccessService(),
		'retention': RetentionService(),
		'governance': GovernanceService(),
		'operations': OperationsService(),
		# §20/§21: the rollout reads the registry (§20.6's retention table crossed against it) and
		# the APK budget §22.5 sets, so it is constructed with the registry rather than beside it.
		'rollout': RolloutService(registry),
		# §4: who the launch is for. Constructed beside the rollout because §4.3's priorities are the
		# ordering the rollout is a schedule for, and §22.7's equity targets need a population.
		'personas': PersonaService(),
		'security': SecurityService(),
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
		'adam': AdamClient(cfg.adam_url, client, cfg.adam_api_key, cfg.adam_cert()),
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
	governance: GovernanceService = svc['governance']  # type: ignore[assignment]
	operations: OperationsService = svc['operations']  # type: ignore[assignment]
	rollout: RolloutService = svc['rollout']  # type: ignore[assignment]
	personas: PersonaService = svc['personas']  # type: ignore[assignment]
	security: SecurityService = svc['security']  # type: ignore[assignment]
	chw: ChwService = svc['chw']  # type: ignore[assignment]
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

	def require_scope(dataset: str):  # type: ignore[no-untyped-def]
		"""Route guard: the token's role must cover the dataset it is asking for (§17 RBAC)."""
		async def guard(authorization: str | None = Header(default=None)) -> str:
			subject, role = require_token(authorization)
			from afya.privacy.views import AccessRequest
			# The logged variant, so every guarded route writes the durable §17.4 entry rather
			# than only the in-memory list.
			if not await privacy.check_access_logged(AccessRequest(role=role, dataset=dataset)):
				raise HTTPException(status_code=403, detail=f'role {role.value} may not read {dataset}')
			return subject
		return guard

	def require_any_scope(datasets: tuple[str, ...]):  # type: ignore[no-untyped-def]
		"""Route guard for a route §17.4 lets more than one role read, each through its own scope.

		§19.4 names PHEOC, county health teams and MoH as the readers of the public-health
		dashboards, and §17.4 gives those three different scopes: `county_aggregate` to the county
		officer, `national_aggregate` to the PHEOC analyst. Guarding the dashboard on either one
		alone locks out two thirds of the audience the spec names — so the guard takes the set, and
		still requires the token's role to hold *one of* them through the same `_SCOPE` map rather
		than widening any role. Each attempt is logged with the dataset that was actually tried.
		"""
		async def guard(authorization: str | None = Header(default=None)) -> str:
			subject, role = require_token(authorization)
			from afya.privacy.views import AccessRequest
			for dataset in datasets:
				if await privacy.check_access_logged(AccessRequest(role=role, dataset=dataset)):
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
			if not named:
				raise HTTPException(status_code=422, detail='this request must name the family member it acts for')
			if not may_create and not records.owns(subject, str(named)):
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
	async def auth_anonymous(req: TokenRequest) -> dict[str, object]:
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

	# --- triage ---
	@app.post('/triage/preliminary', response_model=TriageResult)
	async def triage_preliminary(inp: TriageInput, lang: str = 'en') -> TriageResult:
		return triage.assess(inp, lang)

	@app.post('/triage/evd', response_model=TriageResult)
	async def triage_evd(inp: TriageInput) -> TriageResult:
		try:
			return triage.assess_evd(inp)
		except PermissionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc

	@app.post('/triage/diary')
	async def triage_diary(entry: DiaryEntry, _subject: str = Depends(require_self())) -> dict[str, bool]:
		await triage.diary_append(entry)
		return {'accepted': True}

	@app.get('/triage/{ref}/diary')
	async def triage_diary_list(ref: str, _subject: str = Depends(require_self(lambda r: r.path_params['ref']))) -> list[dict[str, object]]:
		return [e.model_dump(mode='json') for e in triage.diary(ref)]

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

	@app.post('/facilities/{facility_id}/wait')
	async def facility_wait(facility_id: str, minutes: int) -> dict[str, int]:
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

	@app.post('/facilities/{facility_id}/booking')
	async def facility_book(facility_id: str, booking: Booking) -> Booking:
		if not any(f.facility_id == facility_id for f in facilities.all_facilities()):
			raise HTTPException(status_code=404, detail='unknown facility')
		return await facilities.book(facility_id, booking.slot_iso, booking.booking_id)

	# --- medicine ---
	@app.post('/medicine/verify')
	async def medicine_verify(req: VerifyRequest) -> dict[str, object]:
		return (await medicine.verify(req)).model_dump(mode='json')

	@app.post('/medicine/interactions')
	async def medicine_interactions(req: InteractionsRequest) -> list[str]:
		return medicine.check_interactions(req.drugs)

	@app.post('/medicine/stock')
	async def medicine_stock(report: StockReport) -> dict[str, bool]:
		await medicine.report_stock(report)
		return {'ok': True}

	@app.post('/medicine/dose')
	async def medicine_dose(req: DoseRequest) -> dict[str, object]:
		return medicine.dose(req).model_dump(mode='json')

	# --- emergency ---
	@app.post('/emergency/sos')
	async def emergency_sos(event: SOSEvent) -> dict[str, object]:
		return (await emergency.sos(event)).model_dump(mode='json')

	@app.post('/emergency/fall')
	async def emergency_fall(samples: list[IMUSample]) -> dict[str, object]:
		return EmergencyService.fall(samples).model_dump(mode='json')

	@app.post('/emergency/card/qr')
	async def emergency_card(card: EmergencyCard) -> dict[str, str]:
		return {'qr': EmergencyService.card_qr(card)}

	# --- info & records ---
	@app.get('/info/hotlines')
	async def info_hotlines(lang: str = 'en', now_ms: int | None = None) -> list[dict[str, object]]:
		"""§INF-006's directory, with §6.2.3's stamp on each entry.

		`verified` is an assertion about a number, and one nobody can act on without knowing when it
		was last checked — so the age travels with it. `updated_line` is None for an entry that has
		never been verified, which is a fact a client should render rather than infer from silence.
		"""
		return [
			{**h.model_dump(mode='json'), 'updated_line': info.hotline_freshness(h, now_ms, lang)}
			for h in info.hotlines()
		]

	@app.get('/info/dashboard/{county}')
	async def info_dashboard(county: str, lang: str = 'en', now_ms: int | None = None) -> dict[str, object]:
		"""§INF-001's county dashboard, with §8.5's "Last updated timestamp".

		`updated_line` is None when the county has never been assessed. `dashboard()` answers an
		unknown county with a defaulted low-risk row so a client always has something to draw, and
		without the stamp that default is indistinguishable from an assessment someone made today —
		which is exactly the undated content §6.2.3 calls destructive.
		"""
		risk = info.dashboard(county)
		return {**risk.model_dump(mode='json'), 'updated_line': info.dashboard_freshness(county, now_ms, lang)}

	@app.post('/info/dashboard/{county}')
	async def info_set_dashboard(county: str, risk_level: str, active_signals: int, bulletin: str,
			source: str = '', at_ms: int | None = None,
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
	async def info_library(lang: str = 'en', now_ms: int | None = None) -> list[dict[str, object]]:
		"""§6.2 content library (INF-003/004/008/009/010/015), served by language.

		Served as {slug,title,body,harmony_tag} — never `item_id`, whose seed values embed spec codes
		(`INF-003-en`) that must not reach a screen. The slug is what a client keys on.

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
		"""
		return [
			{'slug': c.slug, 'title': c.title, 'body': c.body, 'harmony_tag': c.harmony_tag or '',
			 'lang': c.lang, 'answers_rank': c.answers_rank,
			 **info.item_freshness(c, now_ms, lang).model_dump(mode='json')}
			for c in info.library(lang)
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
	async def info_content_advance(item_id: str, to: str, _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
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
		"""§10.5's three features — the topics each names, and which the corpus has an item for.

		Auditor-scoped like the other evidence views: it reports what the corpus is missing, which is
		a content owner's business rather than a client's. `gaps` is the finding — "first-aid items are
		in the health library corpus" is true of the one item that exists and says nothing about the
		other ten topics §INF-009 names.
		"""
		items = info.all_items()
		return {
			'coverage': health_education.report(items),
			'health_tip_topics': list(health_education.HEALTH_TIP_TOPICS),
			'first_aid_topics': list(health_education.FIRST_AID_TOPICS),
			'burial_content': list(health_education.BURIAL_CONTENT),
			'sensitivity_reviewers': list(health_education.SENSITIVITY_REVIEWERS),
			'first_aid_offline': health_education.first_aid_is_offline(),
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

	@app.get('/info/decision-tree')
	async def info_decision_tree(answers: str = '') -> dict[str, object]:
		"""§INF-002 "What Should I Do" decision tree.

		Without `answers` it returns the root question; each subsequent call passes the answers so
		far, comma-separated as `y`/`n`, and returns either the next question or the leaf
		recommendation. The answers are the caller's own symptoms, so no subject is named or needed.
		"""
		parsed: list[bool] = []
		for token in [t.strip().lower() for t in answers.split(',') if t.strip()]:
			if token not in ('y', 'n', 'yes', 'no', 'true', 'false'):
				raise HTTPException(status_code=422, detail=f'answer must be yes or no, not {token!r}')
			parsed.append(token in ('y', 'yes', 'true'))
		if not parsed:
			return {'question': info.TREE['root'].question, 'done': False, 'recommendation': None}
		try:
			recommendation = info.decide('', parsed)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		# Re-walk to find the node the answers reached, so a client can ask the next question.
		node = info.TREE['root']
		for ans in parsed:
			node = info.TREE[node.yes_next if ans else node.no_next]  # type: ignore[index]
		next_question = None if node.leaf_recommendation else node.question
		return {'question': next_question, 'done': node.leaf_recommendation is not None, 'recommendation': recommendation}

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
	async def records_growth(rec: GrowthRecord, _subject: str = Depends(require_self_or_guardian(_body_member))) -> dict[str, str]:
		try:
			records.assert_owns(_subject, rec.member_ref)
		except AssertionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc
		return records.growth_flag(rec).model_dump(mode='json')

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
		try:
			records.assert_owns(_subject, ref)
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc
		return [l.model_dump(mode='json') for l in records.labs(ref)]

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

		The section lists eight documents a family wallet holds. Seven have a model and one —
		discharge summaries — does not, which is reported rather than padded: a wallet payload that
		says "wallet" while holding seven of the section's eight items is the shape this surface
		exists to make visible.
		"""
		return records.wallet_contents().model_dump(mode='json')

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

	@app.post('/channels/sms')
	async def channels_sms(to_msisdn: str, body: str) -> dict[str, object]:
		try:
			return (await channels.send_sms(to_msisdn, body)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/channels/ussd')
	async def channels_ussd(req: UssdRequest, lang: str = 'en') -> dict[str, object]:
		"""`lang` is a query parameter because USSD carries no headers: the carrier's gateway passes
		the subscriber's language out of band, and the menu it returns is the whole user interface.
		Without it the route was English-only and Swahili — the language §ACC-002 puts first — was
		unreachable on the one channel §4.1's feature-phone persona can use."""
		return channels.ussd(req, lang).model_dump(mode='json')

	@app.post('/channels/whatsapp')
	async def channels_whatsapp(msg: WhatsAppIn, lang: str = 'en') -> dict[str, object]:
		"""`lang` is a query parameter for the same reason the USSD route takes one: WhatsApp
		Business carries no locale header we can trust, and §5.4 puts the same engine behind it."""
		return channels.route_whatsapp(msg, lang).model_dump(mode='json')

	@app.post('/channels/ussd/callback')
	async def channels_ussd_callback(cb: AtUssdCallback, lang: str = 'en', _body: bytes = Depends(require_webhook())) -> dict[str, str]:
		"""Carrier webhook. Signature-guarded: unsigned, it is anyone driving the USSD menus."""
		return channels.ussd_carrier_callback(cb, lang)

	@app.post('/channels/chw/tasks')
	async def chw_assign(task: ChwTask, _subject: str = Depends(require_scope('assigned'))) -> dict[str, bool]:
		await channels.assign_chw_task(task)
		return {'ok': True}

	@app.get('/channels/chw/tasks/{chw_ref}')
	async def chw_open(chw_ref: str, _subject: str = Depends(require_scope('assigned'))) -> list[dict[str, object]]:
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
		_subject: str = Depends(require_self()),
	) -> dict[str, object]:
		blob = await file.read()
		import hashlib
		from uuid6 import uuid7
		try:
			# Built inside the try: the model's size and mime contracts are part of the request
			# validation, so a violation is the caller's 422, not an unhandled 500.
			submission = EvidenceSubmission(
				submission_id='EV-' + str(uuid7()).replace('-', '').upper()[:12],
				kind=kind, subject_ref=subject_ref, county=county,
				# No fallback mime: the model's `image/(jpeg|webp|png)` contract is the check, and a
				# default of `image/jpeg` would let any content type through under a false label.
				image_sha256=hashlib.sha256(blob).hexdigest(), mime=file.content_type or '',
				size_bytes=len(blob), note=note,
			)
			receipt = await evidence.submit(submission, blob)
		except PermissionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc
		except (AssertionError, ValidationError) as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return receipt.model_dump(mode='json')

	@app.post('/ml/cough/analyze')
	async def ml_cough_analyze(file: UploadFile = File(...)) -> dict[str, object]:
		"""16 kHz mono WAV -> YAMNet AudioSet -> cough verdict (SENS-002, tier4 gated)."""
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
			return engine.analyze(wave, tier4_active=registry.tier4_active()).model_dump(mode='json')
		except PermissionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc

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

	@app.post('/maternal/pregnancy')
	async def maternal_register(p: Pregnancy, _subject: str = Depends(require_self())) -> dict[str, bool]:
		await maternal.register(p)
		return {'ok': True}

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
	async def maternal_danger(signs: list[str]) -> dict[str, object]:
		try:
			return maternal.assess_danger(signs).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/chronic/bp')
	async def chronic_bp(r: BPReading, _subject: str = Depends(require_self())) -> dict[str, str]:
		out = await chronic.bp(r)
		return {'stage': out.stage}

	@app.post('/chronic/glucose')
	async def chronic_glucose(r: GlucoseReading, _subject: str = Depends(require_self())) -> dict[str, str]:
		out = await chronic.glucose(r)
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

	@app.post('/mental/who5')
	async def mental_who5(w: WHO5, _subject: str = Depends(require_self())) -> dict[str, object]:
		return mental.assess(w).model_dump(mode='json')

	@app.get('/mental/lines')
	async def mental_lines() -> list[dict[str, str]]:
		return mental.lines()

	@app.post('/blood/donors')
	async def blood_register(d: Donor) -> dict[str, bool]:
		await blood.register(d)
		return {'ok': True}

	@app.post('/blood/match')
	async def blood_match(req: BloodRequest, today_iso: str = '2026-10-08') -> list[dict[str, object]]:
		return [m.model_dump(mode='json') for m in blood.match(req, today_iso)]

	# A community alert reaches every phone in the county. §17.4's `assigned` is the CHW's scope —
	# the role that carries a worker's report up — so issuing one is a worker action, not a
	# citizen's. Without this guard an anonymous caller could publish "Ebola confirmed" to a county.
	@app.post('/alerts')
	async def alerts_issue(a: CommunityAlert, _subject: str = Depends(require_scope('assigned'))) -> dict[str, bool]:
		try:
			await alerts.issue(a)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'ok': True}

	@app.get('/alerts/{county}')
	async def alerts_county(county: str) -> list[dict[str, object]]:
		return [a.model_dump(mode='json') for a in alerts.by_county(county)]

	@app.post('/environment/water')
	async def environment_water(w: WaterQuality) -> dict[str, str]:
		return {'advisory': alerts.water_alert(w)}

	@app.post('/environment/air')
	async def environment_air(a: AirQuality) -> dict[str, str]:
		return {'advisory': alerts.air_alert(a)}

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
	async def sync_flush(connection: str = 'wifi') -> dict[str, object]:
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
		"""
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
			'toggles': [t.model_dump(mode='json') for t in privacy.consent_toggles(granted, sensor_grants)],
			'sensors': privacy.sensor_consents(),
		}

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
	async def tier4_activate(auth: Tier4Activation, _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:
		"""§11.1: all three keys or nothing. The response names what is missing and what the
		activation unlocks, so a refusal is diagnosable instead of a bare false.

		The `dpia_review` key is not taken on the caller's word and is not even a field the caller
		sends: the DPIA is assessed from the deployment described in the request, and the key is held
		only by a recorded §17.3 review that still covers that processing. Before this, a request
		carrying `dpia_reviewed: true` and nothing else held the key — the DPIA was assessed only if
		`dpia_input` happened to be present, so the one input the gate exists for was optional.
		"""
		report = surveillance.assess_tier4(auth.dpia_input) if auth.dpia_input is not None else None
		review = surveillance.dpia_review_for(auth.dpia_input)
		active = await surveillance.activate_tier4(
			auth.authorized_by_pheoc, auth.flag_enabled, auth.bulletin_text,
			dpia=report, review=review, dpia_input=auth.dpia_input,
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
	async def surveillance_geofences_at(lat: float, lon: float) -> list[dict[str, object]]:
		"""LOC-001: the advisory zones covering a point. Read-only and open, like every other
		location-agnostic information route — the coordinates are where the *caller* is, and nothing
		about the caller is recorded. The alert text is what the client shows on entry; whether the
		entry is logged is a separate opt-in (§LOC-001 privacy).
		"""
		return [
			{'geofence_id': f.geofence_id, 'risk_type': f.risk_type, 'alert_level': f.alert_level,
			 'radius_m': f.radius_m, 'lat': f.lat, 'lon': f.lon,
			 'advice': ('You have entered an area where a case was reported. Avoid the named location, '
			            'monitor for symptoms for 21 days, and call 719 if you feel unwell.')}
			for f in surveillance.geofences_at(lat, lon)
		]

	@app.get('/mobile/features')
	async def mobile_features() -> list[dict[str, object]]:
		from afya.mobile.actions import FRIENDLY_COPY
		return [
			{'id': fid, 'title': t, 'description': d}
			for fid, (t, d) in FRIENDLY_COPY.items()
		]

	@app.get('/mobile/actions')
	async def mobile_actions(county: str | None = None, authorization: str | None = Header(default=None)) -> list[dict[str, object]]:
		"""What this caller may actually do.

		Two filters, both against showing a control that would refuse. An outbreak capability is shown
		only if §11.1 activates it for this caller — asked of the activation model per feature, not of
		the PHEOC declaration alone, because rows 3 and 5 activate the contact diary for *one person*
		and a person who asked for monitoring would otherwise be shown no diary while the route behind
		it would have served them. And an operator control is withheld from a caller whose role does
		not hold the dataset its route checks: a health-information form offered to a citizen token is
		a 403 waiting to happen, which is the same failure.

		No token means a citizen: the app's own screens work unauthenticated, so the citizen set is
		the default rather than a refusal.
		"""
		from afya.mobile.actions import available
		scopes: frozenset[str] = frozenset()
		subject_ref: str | None = None
		if authorization:
			try:
				subject_ref, role = require_token(authorization)
				scopes = frozenset(_SCOPE.get(role, set()))
			except HTTPException:
				scopes = frozenset()
		state = activation.state(county=county, subject_ref=subject_ref)
		return [
			act.model_dump(mode='json')
			for act in available(
				registry.tier4_active(), scopes,
				feature_available=lambda fid: activation.feature_available(fid, state),
			)
		]

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
	async def places_testing_sites(lat: float, lon: float, limit: int = 5) -> list[dict[str, object]]:
		"""FND-003. The kinds are fixed by the route rather than passed by the client, so a client
		cannot ask the testing-site endpoint for pharmacies and render the answer as test locations."""
		return await places_nearest(lat, lon, kinds=[PlaceKind.testing_site.value], limit=limit)

	@app.get('/places/vaccination-points')
	async def places_vaccination_points(lat: float, lon: float, limit: int = 5) -> list[dict[str, object]]:
		"""FND-005. Routine and campaign vaccination points, fixed to their own kind for the same reason."""
		return await places_nearest(lat, lon, kinds=[PlaceKind.vaccination_point.value], limit=limit)

	@app.post('/places/import-osm')
	async def places_import_osm(county_lat: float, county_lon: float, _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, int]:
		client = OverpassClient()
		rows = await client.fetch_places(county_lat, county_lon)
		for p in rows:
			await places.upsert(p)
		return {'imported': len(rows), 'total': places.count()}

	# --- monitoring & reminders (§9.1 MON-001..004, §10.2 MON-005..008, §11.3 MON-009) ---
	@app.post('/monitoring/child')
	async def monitoring_child(member_ref: str, dob_iso: str, _subject: str = Depends(require_self_or_guardian(lambda r: r.query_params.get('member_ref')))) -> dict[str, bool]:
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

	@app.post('/monitoring/child/{member_ref}/dose')
	async def monitoring_dose(member_ref: str, vaccine: str, dose_no: int, given_iso: str, _subject: str = Depends(require_self_or_guardian(lambda r: r.path_params['member_ref']))) -> dict[str, bool]:
		try:
			records.assert_owns(_subject, member_ref)
			await monitoring.record_dose(member_ref, vaccine, dose_no, given_iso)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'ok': True}

	@app.post('/monitoring/medication')
	async def monitoring_medication(sched: MedSchedule, _subject: str = Depends(require_self_or_guardian(_body_member))) -> dict[str, str]:
		# A medication schedule is bound to a member of the caller's own wallet, so a schedule
		# cannot be filed against a stranger's child.
		try:
			records.assert_owns(_subject, sched.member_ref)
		except AssertionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc
		out = await monitoring.add_schedule(sched)
		return {'schedule_id': out.schedule_id}

	@app.post('/monitoring/medication/adherence')
	async def monitoring_adherence(event: AdherenceEvent) -> dict[str, object]:
		try:
			return (await monitoring.record_adherence(event)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/monitoring/chronic/peak-flow')
	async def monitoring_peak_flow(r: PeakFlowReading, _subject: str = Depends(require_self())) -> dict[str, object]:
		return await monitoring.log_peak_flow(r)

	@app.post('/monitoring/chronic/weight')
	async def monitoring_weight(r: WeightReading, _subject: str = Depends(require_self())) -> dict[str, object]:
		return await monitoring.log_weight(r)

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
	async def monitoring_vector_risk(county: str, rainfall_mm_72h: float, livestock_adjacent: bool = False) -> dict[str, object]:
		return monitoring.vector_risk(county, rainfall_mm_72h, livestock_adjacent).model_dump(mode='json')

	@app.post('/monitoring/breeding-site')
	async def monitoring_breeding_site(county: str, lat: float, lon: float, description: str) -> dict[str, object]:
		return await monitoring.report_breeding_site(county, lat, lon, description)

	# A food-safety alert is a public warning about a named product; the county issues it.
	@app.post('/monitoring/food-alert')
	async def monitoring_food_alert(alert: FoodSafetyAlert, _subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, object]:
		return (await monitoring.issue_food_alert(alert)).model_dump(mode='json')

	@app.get('/monitoring/food-alerts/{county}')
	async def monitoring_food_alerts(county: str) -> list[dict[str, object]]:
		return [a.model_dump(mode='json') for a in monitoring.food_alerts(county)]

	@app.get('/monitoring/nutrition/{age_months}')
	async def monitoring_nutrition(age_months: int) -> dict[str, object]:
		try:
			return monitoring.nutrition_guidance(age_months).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/monitoring/contact/enrol')
	async def monitoring_enrol(subject_ref: str, officer: str | None = None, county: str | None = None, _subject: str = Depends(require_self())) -> dict[str, object]:
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
		return monitoring.enrol(subject_ref, officer).model_dump(mode='json')

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
	async def community_resolve(issue_id: str, _subject: str = Depends(require_scope('assigned'))) -> dict[str, str]:
		try:
			return {'status': (await community.resolve_issue(issue_id)).value}
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.post('/community/cases')
	async def community_case(report: CaseReport, _subject: str = Depends(require_scope('assigned'))) -> dict[str, object]:
		try:
			return (await community.submit_case(report)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/community/cases/{report_id}/advance')
	async def community_advance(report_id: str, status: CaseStatus, _subject: str = Depends(require_scope('assigned'))) -> dict[str, str]:
		try:
			return {'status': (await community.advance_case(report_id, status)).value}
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/community/ppe-reminder')
	async def community_ppe() -> dict[str, str]:
		return {'reminder': community.ppe_reminder()}

	@app.post('/community/peer-alert')
	async def community_peer_alert(alert: PeerAlert, _subject: str = Depends(require_scope('assigned'))) -> dict[str, object]:
		try:
			return (await community.send_peer_alert(alert)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/community/tracing-prompts')
	async def community_prompts() -> list[str]:
		return community.tracing_prompts()

	@app.post('/community/contacts')
	async def community_contacts(contacts: ContactList, _subject: str = Depends(require_self())) -> dict[str, object]:
		return (await community.save_contacts(contacts)).model_dump(mode='json')

	@app.post('/community/contacts/{subject_ref}/entry')
	async def community_contact_entry(subject_ref: str, entry: ContactEntry, _subject: str = Depends(require_self())) -> dict[str, object]:
		return community.add_contact(subject_ref, entry).model_dump(mode='json')

	@app.post('/community/misinformation')
	async def community_misinfo(submission: MisinfoSubmission) -> dict[str, object]:
		return (await community.flag_misinfo(submission)).model_dump(mode='json')

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
	async def alerting_publish(item: FeedItem, _subject: str = Depends(require_scope('assigned'))) -> dict[str, object]:
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
		"""
		items = [i for i in alerting.feed(county) if i.category == 'service']
		return {
			'county': county,
			'count': len(items),
			'items': [i.model_dump(mode='json') for i in items],
			'note': 'Statuses come from county and national sources; check the source line before travelling.',
		}

	@app.post('/alerting/preferences')
	async def alerting_preference(subject_ref: str, category: str, enabled: bool, _subject: str = Depends(require_self())) -> dict[str, object]:
		try:
			return alerting.set_preference(subject_ref, category, enabled).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/alerting/preferences/{subject_ref}')
	async def alerting_preferences(subject_ref: str, _subject: str = Depends(require_self())) -> dict[str, object]:
		return alerting.preferences(subject_ref).model_dump(mode='json')

	@app.post('/alerting/family/link')
	async def alerting_family_link(family_ref: str, members: list[str], _subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:
		# A group is built around the person creating it: without this a caller could link a
		# stranger's subject into a group and then read the board that names them.
		if _subject not in members:
			raise HTTPException(status_code=403, detail='a family group must include the person creating it')
		return alerting.link_family(family_ref, members).model_dump(mode='json')

	@app.post('/alerting/family/check-in')
	async def alerting_check_in(subject_ref: str, family_ref: str, at_iso: str, _subject: str = Depends(require_self())) -> dict[str, object]:
		try:
			return (await alerting.check_in(subject_ref, family_ref, at_iso)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

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
	async def alerting_exposure(subject_ref: str, case_ref: str | None = None, county: str | None = None, _subject: str = Depends(require_scope('assigned'))) -> dict[str, object]:
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
	async def location_ebid(seed: str, now_ms: int) -> dict[str, object]:
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
		return {'ok': True}

	@app.post('/tier4/activation/request')
	async def tier4_activation_request(county: str | None = None, _subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:
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
	async def location_check(own_pets: list[str], window_days: int = 21, now_ms: int | None = None) -> dict[str, object]:
		return location.check_exposure(own_pets, window_days, now_ms).model_dump(mode='json')

	@app.post('/location/history/enable')
	async def location_enable(subject_ref: str, window_days: int = 21, _subject: str = Depends(require_self())) -> dict[str, object]:
		try:
			return location.enable_history(subject_ref, window_days).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/location/history/point')
	async def location_point(subject_ref: str, point: LocationPoint, _subject: str = Depends(require_self())) -> dict[str, int]:
		try:
			return {'points': location.log_location(subject_ref, point)}
		except AssertionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc

	@app.get('/location/history/{subject_ref}/report')
	async def location_report(subject_ref: str, share: bool = False, _subject: str = Depends(require_self())) -> dict[str, object]:
		try:
			return location.build_report(subject_ref, share).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.delete('/location/history/{subject_ref}')
	async def location_purge(subject_ref: str, _subject: str = Depends(require_self())) -> dict[str, int]:
		return {'purged': location.purge_history(subject_ref)}

	@app.post('/location/checkin/point')
	async def location_checkin_point(point: CheckInPoint) -> dict[str, str]:
		await location.register_point(point)
		return {'token': point.token}

	@app.post('/location/checkin')
	async def location_checkin(checkin: CheckIn, _subject: str = Depends(require_self())) -> dict[str, object]:
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
	async def location_advisory(destination: str, origin_country: str) -> dict[str, str]:
		return {'advisory': location.advisory(destination, origin_country)}

	@app.post('/location/traveller/declare')
	async def location_declare_traveller(decl: TravelerDeclaration, _subject: str = Depends(require_self())) -> dict[str, object]:
		return (await location.self_declare(decl)).model_dump(mode='json')

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
	async def ai_hotspots(cells: list[AggregateCell], _subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, object]:
		try:
			return ai.hotspots(cells).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/ai/risk-score')
	async def ai_risk(inp: RiskInputs) -> dict[str, object]:
		return ai.personal_risk(inp).model_dump(mode='json')

	@app.post('/ai/early-warning')
	async def ai_warning(county: str, disease: str, signals: list[WarningSignal], _subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, object]:
		try:
			return ai.assess_warning(county, disease, signals).model_dump(mode='json')
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
	async def ai_audit(audit: FairnessAudit) -> dict[str, object]:
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
		try:
			return access.transcribe(req).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/access/battery')
	async def access_battery(subject_ref: str = 'U1', intensity: str = 'balanced', battery_saver: bool = False, _subject: str = Depends(require_self())) -> dict[str, object]:
		try:
			return access.battery_profile(subject_ref, intensity, battery_saver).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/access/compatibility/{platform}')
	async def access_compat(platform: str) -> dict[str, object]:
		try:
			return access.compatibility(platform).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	# --- retention, encryption, transparency (§17, SEC-003/005/006) ---
	@app.get('/retention/policy')
	async def retention_policy() -> list[dict[str, object]]:
		return [p.model_dump(mode='json') for p in retention.retention_table()]

	@app.post('/retention/holding')
	async def retention_holding(subject_ref: str, data_type: str, count: int, _subject: str = Depends(require_self())) -> dict[str, int]:
		try:
			return {'count': retention.record_holding(subject_ref, data_type, count)}
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/retention/share')
	async def retention_share(subject_ref: str, with_who: str, what: str, when_iso: str, _subject: str = Depends(require_self())) -> dict[str, bool]:
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
	async def retention_purge(subject_ref: str, age_days: dict[str, int], _subject: str = Depends(require_self())) -> dict[str, object]:
		try:
			return {'expired': retention.purge_expired(subject_ref, age_days)}
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/retention/encryption')
	async def retention_encryption() -> dict[str, object]:
		return retention.encryption_posture().model_dump(mode='json')

	@app.post('/retention/correct')
	async def retention_correct(req: CorrectionRequest, at_iso: str,
	                            _subject: str = Depends(require_self())) -> dict[str, object]:
		"""§17.2 accuracy: "user data editable; correction workflows".

		The subject is the token's own, not a parameter: a correction is an act a person performs on
		their own record, and a route that took a `subject_ref` would let anyone edit anyone's
		demographics by typing a reference. A correction made on someone's behalf is the DPO's, and
		that is a different route with a different guard.
		"""
		req = req.model_copy(update={'subject_ref': _subject, 'corrected_by': _subject})
		try:
			return (await retention.correct(req, at_iso)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.get('/retention/corrections')
	async def retention_corrections(_subject: str = Depends(require_self())) -> list[dict[str, object]]:
		"""The correction history §17.2's "workflow" implies: what was changed, to what, and by whom.

		A right to correct that left no trace would be indistinguishable from a right to overwrite.
		"""
		return retention.corrections(_subject)

	@app.get('/retention/transparency')
	async def retention_transparency(period: str, subject_ref: str | None = None, _subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		return retention.transparency_report(period, subject_ref).model_dump(mode='json')

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
		"""
		store = svc['store']
		if store is None:
			# No durable store configured (no AFYA_DB_PATH): say so rather than return an empty
			# list that would read as "nothing was ever accessed".
			return {'durable': False, 'entries': [], 'note': 'no durable store configured; access is logged in memory only'}
		rows = await store.audit_entries(limit)  # type: ignore[union-attr]
		return {
			'durable': True,
			'entries': [{'role': r, 'dataset': d, 'allowed': a, 'at_ms': t} for r, d, a, t in rows],
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
			rec = await privacy.record_consent_for_phone(grant.msisdn, category)
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

	@app.get('/chw/ppe-reminder')
	async def chw_ppe() -> dict[str, str]:
		return {'reminder': chw.ppe_reminder()}

	@app.get('/chw/{chw_ref}')
	async def chw_get(chw_ref: str, _subject: str = Depends(require_scope('assigned'))) -> dict[str, object]:
		try:
			return chw.profile(chw_ref).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.get('/chw/{chw_ref}/case-load')
	async def chw_case_load(chw_ref: str, _subject: str = Depends(require_scope('assigned'))) -> dict[str, int]:
		return {'open_cases': chw.case_load(chw_ref)}

	@app.post('/chw/{chw_ref}/cases')
	async def chw_case(chw_ref: str, case: ChwCase, _subject: str = Depends(require_scope('assigned'))) -> dict[str, object]:
		try:
			return (await chw.assign_case(chw_ref, case)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.get('/chw/{chw_ref}/cases')
	async def chw_cases(chw_ref: str, _subject: str = Depends(require_scope('assigned'))) -> list[dict[str, object]]:
		return [c.model_dump(mode='json') for c in chw.cases(chw_ref)]

	@app.post('/chw/activity')
	async def chw_activity(entry: ActivityLogEntry, _subject: str = Depends(require_scope('assigned'))) -> dict[str, bool]:
		try:
			await chw.log_activity(entry)
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc
		return {'ok': True}

	@app.get('/chw/{chw_ref}/activity')
	async def chw_activity_summary(chw_ref: str, period: str = '2026-W41', _subject: str = Depends(require_scope('assigned'))) -> dict[str, object]:
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
		the programme's own description and names no person — the same shape as `/personas`."""
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
	async def intermediaries_referral(referral: Referral, _subject: str = Depends(require_scope('assigned'))) -> dict[str, object]:
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
	async def intermediaries_attribution(code: str, _subject: str = Depends(require_scope('assigned'))) -> dict[str, object]:
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
		return {
			'wired': sorted(['adam', 'jali', 'pheoc', 'mohf', 'ppb', 'sha', 'telco']),
			'configured': cfg.live_vendors(),
			'adam_mutual_tls': adam.mutual_tls_configured,
			'jali_offline': jali.__class__.__name__ == 'InlineJaliPort',
			'pheoc_feeds': sorted(FEED_GRANULARITY),
		}

	# §18.1 ADaM — case reports out, status/assignments/definitions in.
	@app.post('/integrations/adam/cases')
	async def adam_push_case(report: dict[str, object], _subject: str = Depends(require_scope('assigned'))) -> dict[str, object]:
		try:
			ref = await adam.push_case_report(dict(report))
		except (AssertionError, ValueError) as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		except Exception as exc:
			raise HTTPException(status_code=502, detail='ADaM did not accept the case report') from exc
		return {'adam_case_ref': ref}

	@app.post('/integrations/adam/monitoring')
	async def adam_push_monitoring(summary: dict[str, object], _subject: str = Depends(require_scope('assigned'))) -> dict[str, bool]:
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
	async def adam_case_status(report_id: str, _subject: str = Depends(require_scope('assigned'))) -> dict[str, object]:
		try:
			return await adam.pull_case_status(report_id)
		except Exception as exc:
			raise HTTPException(status_code=502, detail='ADaM is unreachable') from exc

	@app.get('/integrations/adam/contacts')
	async def adam_contacts(chw_ref: str, _subject: str = Depends(require_scope('assigned'))) -> list[dict[str, object]]:
		try:
			return await adam.pull_contact_assignments(chw_ref)
		except Exception as exc:
			raise HTTPException(status_code=502, detail='ADaM is unreachable') from exc

	@app.get('/integrations/adam/case-definitions')
	async def adam_case_definitions(_subject: str = Depends(require_scope('assigned'))) -> list[dict[str, object]]:
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
	async def jali_share_assessment(summary: dict[str, object], _subject: str = Depends(require_scope('assigned'))) -> dict[str, bool]:
		try:
			await jali.share_assessment(dict(summary))
		except AssertionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc
		return {'ok': True}

	@app.get('/integrations/jali/assessments/{assessment_id}/review')
	async def jali_review(assessment_id: str) -> dict[str, object]:
		out = await jali.clinician_response(assessment_id)
		# `None` is "a human has not answered yet", which is a state, not an error — so it is a 200
		# with a null body rather than a 404 the client would read as "no such assessment".
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
		still says a named person called an outbreak hotline."""
		if payload.get('consented') is not True:
			return {'recorded': False, 'reason': 'outcome is recorded only with consent'}
		code = str(payload.get('outcome_code', '')).strip()
		if not code:
			raise HTTPException(status_code=422, detail='an outcome needs a code')
		return {'recorded': True, 'outcome_code': code}

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

	@app.post('/facilities/{facility_id}/correction')
	async def facility_correction(facility_id: str, correction: dict[str, object]) -> dict[str, object]:
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
	async def medicine_suspicious(report: dict[str, object], _subject: str = Depends(require_scope('self'))) -> dict[str, object]:
		"""Report a suspected falsified medicine. Guarded so the PPB report is attributable and the
		egress is not an open relay to the regulator's intake."""
		try:
			ref = await ppb.report_suspicious(dict(report))
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
		out = channels.route_whatsapp(WhatsAppIn(from_msisdn=msisdn, body=body), lang)
		return {'reply': out.reply, 'source': 'sms', 'linked': identity.is_linked(subject)}

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
		names no person and no number about one."""
		from afya.rollout.views import Phase
		return {
			'phases': [p.model_dump(mode='json') for p in rollout.phases()],
			'current': rollout.status(Phase.phase_1_information, 1 if not registry.tier4_active() else 4).model_dump(mode='json'),
		}

	@app.get('/rollout/app-size')
	async def rollout_app_size() -> dict[str, object]:
		"""§16.5's delivery table summed by where each row lands — base install against the §20.2
		lever 5 budget, on-demand modules reported beside it rather than folded in.

		Open like `/rollout/phases`: it is a plan a partner or a telco reads, and it names no person."""
		return rollout.app_size().model_dump(mode='json')

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