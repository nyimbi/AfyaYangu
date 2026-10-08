"""App assembly — FastAPI front door (spec §15.5)."""
from fastapi import FastAPI, HTTPException
from httpx import AsyncClient
from pydantic import BaseModel, ConfigDict

from afya.channels.service import AfricaTalkingSmsPort, ChannelService
from afya.channels.views import SmsOut, UssdRequest, WhatsAppIn
from afya.emergency.service import EmergencyService, Inline719Port
from afya.emergency.views import EmergencyCard, IMUSample, SOSEvent
import os

from afya.integrations.service import PPBClient
from afya.persistence.service import SqliteStore
from afya.medicine.service import MedicineService
from afya.medicine.views import DoseRequest, VerifyRequest
from afya.facilities.service import FacilityService
from afya.facilities.views import Booking, Facility, NearestRequest
from afya.info.service import InfoService
from afya.info.views import CountyRisk
from afya.privacy.service import PrivacyService
from afya.privacy.views import ConsentRecord, DPIAInput
from afya.records.service import RecordsService
from afya.records.views import GrowthRecord, ImmunisationRecord, WalletMember
from afya.registry.service import FeatureRegistry, Tier4Activation, Tier
from afya.surveillance.service import SurveillanceService
from afya.surveillance.views import CountySignal, Geofence
from afya.sync.service import SyncService
from afya.sync.views import SyncOp
from afya.triage.service import TriageService
from afya.triage.views import DiaryEntry, TriageInput, TriageResult

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

APP_VERSION = '2.0.0'


class HealthResponse(BaseModel):
	model_config = MODEL_CONFIG
	status: str
	version: str = APP_VERSION
	tier4: bool = False


class InteractionsRequest(BaseModel):
	model_config = MODEL_CONFIG
	drugs: list[str]


def build_services(http: AsyncClient | None = None, db_path: str | None = None) -> dict[str, object]:
	client = http or AsyncClient(timeout=10)
	registry = FeatureRegistry()
	store = SqliteStore(db_path) if db_path else None
	return {
		'registry': registry,
		'triage': TriageService(registry),
		'surveillance': SurveillanceService(registry),
		'medicine': MedicineService(PPBClient('https://ppb.health.go.ke/api', client)),
		'facilities': FacilityService(),
		'channels': ChannelService(AfricaTalkingSmsPort('https://api.africastalking.com', 'env-key')),
		'emergency': EmergencyService(Inline719Port()),
		'info': InfoService(),
		'records': RecordsService(),
		'privacy': PrivacyService(store),
		'sync': SyncService(store),
	}


def create_app(services: dict[str, object] | None = None) -> FastAPI:
	svc = services or build_services(db_path=os.environ.get('AFYA_DB_PATH'))
	assert {'registry', 'triage', 'surveillance', 'facilities', 'channels', 'sync', 'privacy'} <= svc.keys(), 'core services required'
	registry: FeatureRegistry = svc['registry']  # type: ignore[assignment]
	triage: TriageService = svc['triage']  # type: ignore[assignment]
	surveillance: SurveillanceService = svc['surveillance']  # type: ignore[assignment]
	facilities: FacilityService = svc['facilities']  # type: ignore[assignment]
	channels: ChannelService = svc['channels']  # type: ignore[assignment]
	emergency: EmergencyService = svc['emergency']  # type: ignore[assignment]
	info: InfoService = svc['info']  # type: ignore[assignment]
	records: RecordsService = svc['records']  # type: ignore[assignment]
	privacy: PrivacyService = svc['privacy']  # type: ignore[assignment]
	sync: SyncService = svc['sync']  # type: ignore[assignment]
	medicine: MedicineService = svc['medicine']  # type: ignore[assignment]
	app = FastAPI(title='Afya Yangu / Mlinzi', version=APP_VERSION)

	@app.get('/health', response_model=HealthResponse)
	async def health() -> HealthResponse:
		assert registry.available(), 'registry must respond'
		return HealthResponse(status='ok', tier4=registry.tier4_active())

	@app.get('/features')
	async def features() -> list[dict[str, object]]:
		return [f.model_dump(mode='json') for f in registry.available()]

	# --- triage ---
	@app.post('/triage/preliminary', response_model=TriageResult)
	async def triage_preliminary(inp: TriageInput) -> TriageResult:
		return triage.assess(inp)

	@app.post('/triage/evd', response_model=TriageResult)
	async def triage_evd(inp: TriageInput) -> TriageResult:
		try:
			return triage.assess_evd(inp)
		except PermissionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc

	@app.post('/triage/diary')
	async def triage_diary(entry: DiaryEntry) -> dict[str, bool]:
		await triage.diary_append(entry)
		return {'accepted': True}

	# --- facilities ---
	@app.post('/facilities')
	async def facility_upsert(fac: Facility) -> dict[str, bool]:
		await facilities.upsert(fac)
		return {'ok': True}

	@app.post('/facilities/nearest')
	async def facility_nearest(req: NearestRequest) -> list[dict[str, object]]:
		return [{'facility': f.model_dump(mode='json'), 'km': round(km, 2)} for f, km in facilities.nearest(req)]

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

	# --- sync ---
	@app.post('/sync/ops')
	async def sync_enqueue(op: SyncOp) -> dict[str, bool]:
		try:
			await sync.enqueue(op)
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc
		return {'queued': True}

	@app.post('/sync/flush')
	async def sync_flush() -> dict[str, int]:
		return (await sync.flush(0)).model_dump(mode='json')

	# --- privacy ---
	@app.post('/privacy/consent')
	async def privacy_consent(rec: ConsentRecord) -> dict[str, str]:
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
	async def tier4_activate(auth: Tier4Activation) -> dict[str, bool]:
		return {'activated': await surveillance.activate_tier4(
			auth.authorized_by_pheoc, auth.dpia_reviewed, auth.flag_enabled, auth.bulletin_text,
		)}

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

	return app