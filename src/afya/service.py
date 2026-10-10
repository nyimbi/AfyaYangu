"""App assembly — FastAPI front door (spec §15.5)."""
from afya.surveillance.service import SurveillanceService, estimate_breath_rate
from afya.surveillance.views import CountySignal, Geofence, ProximityToken

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from httpx import AsyncClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError

import json
import os

from afya.config import ServiceConfig
from afya.persistence.service import SqliteStore
from afya.channels.service import AfricaTalkingSmsPort, ChannelService
from afya.channels.views import ChwTask, SmsOut, UssdRequest, WhatsAppIn
from afya.emergency.service import EmergencyService, Inline719Port
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
from afya.info.service import InfoService
from afya.info.views import ContentItem, CountyRisk
from afya.privacy.service import PrivacyService
from afya.privacy.views import ConsentRecord, DPIAInput, RBACRole
from afya.records.service import RecordsService
from afya.records.views import GrowthRecord, ImmunisationRecord, LabResult, WalletMember
from afya.ml.cough import SR as WAV_SR, YamnetCoughEngine
from afya.registry.service import FeatureRegistry, Tier4Activation, Tier
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
from afya.ai.views import AggregateCell, FairnessAudit, RedressRequest, RiskInputs, WarningSignal
from afya.alerting.service import AlertingService
from afya.alerting.views import ExposureAck, FeedItem, FeedPage, FamilyStatus
from afya.auth.service import AuthService
from afya.auth.views import PKCEStart, PKCETokenRequest, StaffProvision, TokenRequest
from afya.chw.service import ChwService
from afya.chw.views import ActivityLogEntry, ChwCase, ChwProfile
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
from afya.retention.views import DeletionRequest
from afya.governance.service import GovernanceService

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
	series: list[float]
	fps: float = Field(default=30.0, ge=0.5, le=120)


class InteractionsRequest(BaseModel):
	model_config = MODEL_CONFIG
	drugs: list[str]


def build_services(http: AsyncClient | None = None, db_path: str | None = None) -> dict[str, object]:
	client = http or AsyncClient(timeout=10)
	cfg = ServiceConfig.from_env()
	registry = FeatureRegistry()
	sms_port = AtSmsRestSend(cfg.at_base_url, cfg.at_api_key, cfg.at_username, client) if cfg.at_api_key else AfricaTalkingSmsPort(cfg.at_base_url, cfg.at_api_key or 'dev-key')
	store = SqliteStore(db_path) if db_path else None
	try:
		from afya.ml.cough import YamnetCoughEngine as YCE
		cough_engine: object = YCE()
	except (FileNotFoundError, AssertionError):
		cough_engine = None
	return {
		'registry': registry,
		'store': store,
		'cough_engine': cough_engine,
		'triage': TriageService(registry),
		'surveillance': SurveillanceService(registry),
		'sensors': SensorService(registry),
		'medicine': MedicineService(PPBClient(cfg.ppb_url, client, '')),
		'facilities': FacilityService(),
		'channels': ChannelService(sms_port),
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
		'privacy': PrivacyService(store),
		'sync': SyncService(store),
		'monitoring': MonitoringService(),
		'community': CommunityService(),
		'alerting': AlertingService(),
		'realtime': RealtimeService(),
		'location': LocationService(),
		'ai': AIService(),
		'access': AccessService(),
		'retention': RetentionService(),
		'governance': GovernanceService(),
		'chw': ChwService(),
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
		'telco': TelcoGatewayClient(cfg.telco_zero_rating_url, cfg.telco_airtime_url, cfg.telco_api_key or 'unconfigured', client),
	}


def create_app(services: dict[str, object] | None = None) -> FastAPI:
	svc = services or build_services(db_path=os.environ.get('AFYA_DB_PATH'))
	assert {'registry', 'triage', 'surveillance', 'facilities', 'channels', 'sync', 'privacy', 'evidence'} <= svc.keys(), 'core services required'
	registry: FeatureRegistry = svc['registry']  # type: ignore[assignment]
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
	alerting: AlertingService = svc['alerting']  # type: ignore[assignment]
	realtime: RealtimeService = svc['realtime']  # type: ignore[assignment]
	location: LocationService = svc['location']  # type: ignore[assignment]
	ai: AIService = svc['ai']  # type: ignore[assignment]
	access: AccessService = svc['access']  # type: ignore[assignment]
	retention: RetentionService = svc['retention']  # type: ignore[assignment]
	governance: GovernanceService = svc['governance']  # type: ignore[assignment]
	chw: ChwService = svc['chw']  # type: ignore[assignment]
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
	async def sensors_breath(req: BreathEstimateRequest) -> dict[str, object]:
		rate = estimate_breath_rate(req.series, req.fps)
		verdict = await sensors.ingest(SenseIngest(kind=SenseKind.respiration, subject_ref='U1', value=rate, county='Nairobi'))
		return {'rate_bpm': rate, **verdict.model_dump(mode='json')}

	@app.post('/sensors/ingest')
	async def sensors_ingest(inp: SenseIngest, _subject: str = Depends(require_self())) -> dict[str, object]:
		try:
			return (await sensors.ingest(inp)).model_dump(mode='json')
		except PermissionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc

	# --- facilities ---
	@app.post('/facilities')
	async def facility_upsert(fac: Facility) -> dict[str, bool]:
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
	async def info_hotlines() -> list[dict[str, str]]:
		return [h.model_dump(mode='json') for h in info.hotlines()]

	@app.get('/info/dashboard/{county}')
	async def info_dashboard(county: str) -> dict[str, str]:
		return info.dashboard(county).model_dump(mode='json')

	@app.get('/info/library')
	async def info_library(lang: str = 'en') -> list[dict[str, str]]:
		"""§6.2 content library (INF-003/004/008/009/010/015), served by language.

		Served as {slug,title,body,harmony_tag} — never `item_id`, whose seed values embed spec codes
		(`INF-003-en`) that must not reach a screen. The slug is what a client keys on.
		"""
		return [
			{'slug': c.slug, 'title': c.title, 'body': c.body, 'harmony_tag': c.harmony_tag or '', 'lang': c.lang}
			for c in info.library(lang)
		]

	@app.post('/info/content')
	async def info_upsert_content(item: ContentItem) -> dict[str, bool]:
		"""Publish or correct a library item. The `harmony_tag` is required — §6.2 serves nothing
		that has not been harmonised against the official source."""
		if not item.harmony_tag:
			raise HTTPException(status_code=422, detail='content must carry a harmony tag before it is served')
		try:
			await info.upsert_content(item)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'ok': True}

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
	async def records_member(member: WalletMember) -> dict[str, bool]:
		try:
			await records.add_member(member)
		except AssertionError as exc:
			raise HTTPException(status_code=400, detail=str(exc)) from exc
		return {'ok': True}

	@app.get('/records/{member_ref}/immunisation-gaps')
	async def records_gaps(member_ref: str) -> list[str]:
		try:
			return records.immunisation_gaps(member_ref)
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.post('/records/growth')
	async def records_growth(rec: GrowthRecord) -> dict[str, str]:
		return records.growth_flag(rec).model_dump(mode='json')

	@app.post('/records/labs')
	async def records_add_lab(res: LabResult) -> dict[str, bool]:
		await records.add_lab(res)
		return {'ok': True}

	@app.get('/records/{ref}/labs')
	async def records_labs(ref: str) -> list[dict[str, object]]:
		return [l.model_dump(mode='json') for l in records.labs(ref)]

	@app.get('/records/{guardian_ref}/wallet')
	async def records_wallet(guardian_ref: str) -> dict[str, object]:
		try:
			return records.wallet(guardian_ref)
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	# --- channels ---
	@app.post('/channels/sms')
	async def channels_sms(to_msisdn: str, body: str) -> dict[str, object]:
		try:
			return (await channels.send_sms(to_msisdn, body)).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/channels/ussd')
	async def channels_ussd(req: UssdRequest) -> dict[str, object]:
		return channels.ussd(req).model_dump(mode='json')

	@app.post('/channels/whatsapp')
	async def channels_whatsapp(msg: WhatsAppIn) -> dict[str, object]:
		return channels.route_whatsapp(msg).model_dump(mode='json')

	@app.post('/channels/ussd/callback')
	async def channels_ussd_callback(cb: AtUssdCallback, lang: str = 'en', _body: bytes = Depends(require_webhook())) -> dict[str, str]:
		"""Carrier webhook. Signature-guarded: unsigned, it is anyone driving the USSD menus."""
		return channels.ussd_carrier_callback(cb, lang)

	@app.post('/channels/chw/tasks')
	async def chw_assign(task: ChwTask) -> dict[str, bool]:
		await channels.assign_chw_task(task)
		return {'ok': True}

	@app.get('/channels/chw/tasks/{chw_ref}')
	async def chw_open(chw_ref: str) -> list[dict[str, object]]:
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
	async def women_predict(ref: str, ref_date: str = '2026-10-08') -> dict[str, object]:
		try:
			return women.predict(ref, ref_date).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/maternal/pregnancy')
	async def maternal_register(p: Pregnancy, _subject: str = Depends(require_self())) -> dict[str, bool]:
		await maternal.register(p)
		return {'ok': True}

	@app.get('/maternal/{ref}/anc-due')
	async def maternal_anc(ref: str, today_iso: str = '2026-10-08', gest_week: int = 12) -> list[int]:
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

	@app.post('/alerts')
	async def alerts_issue(a: CommunityAlert) -> dict[str, bool]:
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
	async def sync_flush() -> dict[str, int]:
		return (await sync.flush(0)).model_dump(mode='json')

	# --- privacy ---
	@app.post('/privacy/consent')
	async def privacy_consent(rec: ConsentRecord, _subject: str = Depends(require_self())) -> dict[str, str]:
		try:
			out = await privacy.record_consent(rec)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'consent_id': out.consent_id}

	@app.post('/privacy/dpia')
	async def privacy_dpia(inp: DPIAInput) -> dict[str, object]:
		return privacy.assess_dpia(inp).model_dump(mode='json')

	# --- tier4 + surveillance ---
	@app.post('/tier4/activate')
	async def tier4_activate(auth: Tier4Activation) -> dict[str, object]:
		"""§11.1: all three keys or nothing. The response names what is missing and what the
		activation unlocks, so a refusal is diagnosable instead of a bare false."""
		active = await surveillance.activate_tier4(
			auth.authorized_by_pheoc, auth.dpia_reviewed, auth.flag_enabled, auth.bulletin_text,
		)
		return {
			'activated': active,
			'unmet_keys': auth.unmet_keys(),
			'unlocked_features': [s.id for s in registry.by_tier(Tier.tier4)] if active else [],
			'message': (
				'Outbreak capabilities are live for this event.'
				if active else 'Outbreak capabilities stay dark until all three keys are held.'
			),
		}

	@app.post('/surveillance/geofence')
	async def surveillance_geofence(fence: Geofence) -> dict[str, bool]:
		try:
			await surveillance.set_geofence(fence)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'ok': True}

	@app.post('/surveillance/signal')
	async def surveillance_signal(history: list[CountySignal]) -> dict[str, object]:
		return surveillance.weekly_signal(history).model_dump(mode='json')

	@app.get('/mobile/features')
	async def mobile_features() -> list[dict[str, object]]:
		from afya.mobile.actions import FRIENDLY_COPY
		return [
			{'id': fid, 'title': t, 'description': d}
			for fid, (t, d) in FRIENDLY_COPY.items()
		]

	@app.get('/mobile/actions')
	async def mobile_actions() -> list[dict[str, object]]:
		"""Dormant outbreak capabilities are withheld until PHEOC activates the event, so a person
		never sees a control that would refuse them (§11.1)."""
		from afya.mobile.actions import available
		return [act.model_dump(mode='json') for act in available(registry.tier4_active())]

	@app.get('/places/nearest')
	async def places_nearest(lat: float, lon: float, kinds: list[str] | None = None, limit: int = 5) -> list[dict[str, object]]:
		wanted = {PlaceKind(k) for k in (kinds or [])} or None
		return [
			{'place': p.model_dump(mode='json'), 'km': round(km, 2), 'directions': places.directions(p, lat, lon).model_dump(mode='json')}
			for p, km in places.nearest(lat, lon, wanted, limit)
		]

	@app.post('/places/import-osm')
	async def places_import_osm(county_lat: float, county_lon: float) -> dict[str, int]:
		client = OverpassClient()
		rows = await client.fetch_places(county_lat, county_lon)
		for p in rows:
			await places.upsert(p)
		return {'imported': len(rows), 'total': places.count()}

	# --- monitoring & reminders (§9.1 MON-001..004, §10.2 MON-005..008, §11.3 MON-009) ---
	@app.post('/monitoring/child')
	async def monitoring_child(member_ref: str, dob_iso: str) -> dict[str, bool]:
		await monitoring.register_child(member_ref, dob_iso)
		return {'ok': True}

	@app.get('/monitoring/child/{member_ref}/schedule')
	async def monitoring_schedule(member_ref: str, today_iso: str = '2026-10-10') -> list[dict[str, object]]:
		try:
			return [r.model_dump(mode='json') for r in monitoring.schedule(member_ref, today_iso)]
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.get('/monitoring/child/{member_ref}/catch-up')
	async def monitoring_catch_up(member_ref: str, today_iso: str = '2026-10-10') -> dict[str, object]:
		try:
			return monitoring.catch_up(member_ref, today_iso).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.post('/monitoring/child/{member_ref}/dose')
	async def monitoring_dose(member_ref: str, vaccine: str, dose_no: int, given_iso: str) -> dict[str, bool]:
		try:
			await monitoring.record_dose(member_ref, vaccine, dose_no, given_iso)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'ok': True}

	@app.post('/monitoring/medication')
	async def monitoring_medication(sched: MedSchedule) -> dict[str, str]:
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

	@app.post('/monitoring/food-alert')
	async def monitoring_food_alert(alert: FoodSafetyAlert) -> dict[str, object]:
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
	async def monitoring_enrol(subject_ref: str, officer: str | None = None, _subject: str = Depends(require_self())) -> dict[str, object]:
		try:
			registry.get('MON-009')
		except KeyError as exc:
			raise HTTPException(status_code=404, detail='unknown feature') from exc
		if not registry.tier4_active():
			raise HTTPException(status_code=403, detail='contact monitoring is dormant until PHEOC activates the outbreak event')
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

	@app.post('/community/issues/{issue_id}/resolve')
	async def community_resolve(issue_id: str) -> dict[str, str]:
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
	async def community_clusters() -> list[dict[str, object]]:
		return [c.model_dump(mode='json') for c in community.clusters()]

	# --- alerting (§9.6 ALT-003, §10.3 ALT-001/002, §11.8 ALT-004) ---
	@app.post('/alerting/feed')
	async def alerting_publish(item: FeedItem) -> dict[str, object]:
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
	async def alerting_exposure(subject_ref: str, case_ref: str | None = None, _subject: str = Depends(require_scope('assigned'))) -> dict[str, object]:
		if not registry.tier4_active():
			raise HTTPException(status_code=403, detail='exposure notification is dormant until PHEOC activates the event')
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
		if not registry.tier4_active():
			raise HTTPException(status_code=403, detail='proximity logging is dormant until PHEOC activates the event')
		await location.log_encounter(token)
		return {'ok': True}

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

	@app.get('/retention/transparency')
	async def retention_transparency(period: str, subject_ref: str | None = None, _subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:
		return retention.transparency_report(period, subject_ref).model_dump(mode='json')

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
	async def chw_case_load(chw_ref: str) -> dict[str, int]:
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

	@app.post('/integrations/jali/assessments')
	async def jali_share_assessment(summary: dict[str, object]) -> dict[str, bool]:
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
	async def telco_sms_inbound(payload: dict[str, object], _body: bytes = Depends(require_webhook())) -> dict[str, object]:
		"""Telco → App: an inbound SMS, routed through the same service the app's own messaging uses.

		Routed via `route_whatsapp`'s keyword intent path rather than the USSD menu: an SMS body is
		free text ("fever", "facility", "719"), not a menu selection, and feeding it to the USSD
		parser would refuse every real message with `USSD selections numeric`. The msisdn is
		normalised to the E.164 form the channel models require, because carriers deliver it bare.
		"""
		body = str(payload.get('text', '')).strip()
		if not body:
			raise HTTPException(status_code=422, detail='an inbound SMS needs text')
		raw = str(payload.get('from', '')).strip()
		msisdn = raw if raw.startswith('+') else ('+' + raw.lstrip('0') if raw.startswith('0') else '+' + raw)
		out = channels.route_whatsapp(WhatsAppIn(from_msisdn=msisdn, body=body))
		return {'reply': out.reply, 'source': 'sms'}

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