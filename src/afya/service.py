"""App assembly — FastAPI front door (spec §15.5)."""
from afya.surveillance.service import SurveillanceService, estimate_breath_rate
from afya.surveillance.views import CountySignal, Geofence, ProximityToken

from fastapi import FastAPI, File, HTTPException, UploadFile
from httpx import AsyncClient
from pydantic import BaseModel, ConfigDict, Field

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
from afya.integrations.service import PPBClient
from afya.medicine.service import MedicineService
from afya.medicine.views import DoseRequest, StockReport, VerifyRequest
from afya.facilities.service import FacilityService
from afya.facilities.views import Booking, Facility, NearestRequest
from afya.info.service import InfoService
from afya.info.views import CountyRisk
from afya.privacy.service import PrivacyService
from afya.privacy.views import ConsentRecord, DPIAInput
from afya.records.service import RecordsService
from afya.records.views import GrowthRecord, ImmunisationRecord, LabResult, WalletMember
from afya.ml.cough import SR as WAV_SR, YamnetCoughEngine
from afya.registry.service import FeatureRegistry, Tier4Activation, Tier
from afya.surveillance.service import SurveillanceService
from afya.surveillance.views import CountySignal, Geofence
from afya.sensors.service import SensorService
from afya.sensors.views import SenseKind
from afya.sensors.views import SenseIngest
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
		'cough_engine': cough_engine,
		'triage': TriageService(registry),
		'surveillance': SurveillanceService(registry),
		'sensors': SensorService(registry),
		'medicine': MedicineService(PPBClient(cfg.ppb_url, client)),
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
	async def triage_preliminary(inp: TriageInput, lang: str = 'en') -> TriageResult:
		return triage.assess(inp, lang)

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

	@app.get('/triage/{ref}/diary')
	async def triage_diary_list(ref: str) -> list[dict[str, object]]:
		return [e.model_dump(mode='json') for e in triage.diary(ref)]

	# --- sensors (derived metrics only; tier4 gated) ---
	@app.post('/sensors/breath/estimate')
	async def sensors_breath(req: BreathEstimateRequest) -> dict[str, object]:
		rate = estimate_breath_rate(req.series, req.fps)
		verdict = await sensors.ingest(SenseIngest(kind=SenseKind.respiration, subject_ref='U1', value=rate, county='Nairobi'))
		return {'rate_bpm': rate, **verdict.model_dump(mode='json')}

	@app.post('/sensors/ingest')
	async def sensors_ingest(inp: SenseIngest) -> dict[str, object]:
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
	async def channels_ussd_callback(cb: AtUssdCallback, lang: str = 'en') -> dict[str, str]:
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

	# --- photo + textual evidence (SENS-004) ---
	@app.post('/evidence')
	async def evidence_upload(file: UploadFile = File(...), kind: str = 'scene_photo', subject_ref: str = 'U1', county: str = 'Nairobi', note: str = '') -> dict[str, object]:
		blob = await file.read()
		import hashlib
		from uuid6 import uuid7
		submission = EvidenceSubmission(
			submission_id='EV-' + str(uuid7()).replace('-', '').upper()[:12],
			kind=EvidenceKind(kind), subject_ref=subject_ref, county=county,
			image_sha256=hashlib.sha256(blob).hexdigest(), mime=file.content_type or 'image/jpeg',
			size_bytes=len(blob), note=note,
		)
		try:
			receipt = await evidence.submit(submission, blob)
		except PermissionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc
		except AssertionError as exc:
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
	async def women_cycle(entry: CycleLog) -> dict[str, int]:
		return {'logs': await women.log(entry)}

	@app.get('/women/cycle/{ref}/predict')
	async def women_predict(ref: str, ref_date: str = '2026-10-08') -> dict[str, object]:
		try:
			return women.predict(ref, ref_date).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/maternal/pregnancy')
	async def maternal_register(p: Pregnancy) -> dict[str, bool]:
		await maternal.register(p)
		return {'ok': True}

	@app.get('/maternal/{ref}/anc-due')
	async def maternal_anc(ref: str, today_iso: str = '2026-10-08', gest_week: int = 12) -> list[int]:
		try:
			return maternal.anc_due(ref, today_iso, gest_week)
		except AssertionError as exc:
			raise HTTPException(status_code=404, detail=str(exc)) from exc

	@app.post('/maternal/anc')
	async def maternal_anc_record(rec: ANCRecord) -> dict[str, bool]:
		await maternal.record_anc(rec)
		return {'ok': True}

	@app.post('/maternal/danger')
	async def maternal_danger(signs: list[str]) -> dict[str, object]:
		try:
			return maternal.assess_danger(signs).model_dump(mode='json')
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/chronic/bp')
	async def chronic_bp(r: BPReading):
		out = await chronic.bp(r)
		return {'stage': out.stage}

	@app.post('/chronic/glucose')
	async def chronic_glucose(r: GlucoseReading):
		out = await chronic.glucose(r)
		return {'level': out.level}

	@app.get('/chronic/{ref}/bp-trend')
	async def chronic_trend(ref: str) -> dict[str, str]:
		try:
			return {'trend': chronic.bp_trend(ref)}
		except AssertionError as exc:
			raise HTTPException(status_code=422, detail=str(exc)) from exc

	@app.post('/chronic/refill')
	async def chronic_refill(t: RefillTracker) -> dict[str, bool]:
		return {'due': await chronic.set_refill(t)}

	@app.post('/mental/who5')
	async def mental_who5(w: WHO5) -> dict[str, object]:
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

	@app.get('/mobile/actions')
	async def mobile_actions() -> list[dict[str, object]]:
		from afya.mobile.actions import catalogue
		return [act.model_dump(mode='json') for act in catalogue()]

	@app.post('/places/nearest')
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

	return app