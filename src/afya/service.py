"""App assembly — FastAPI front door (spec §15.5)."""
from fastapi import FastAPI, HTTPException
from httpx import AsyncClient
from pydantic import BaseModel, ConfigDict

from afya.integrations.service import PPBClient
from afya.medicine.service import MedicineService
from afya.registry.service import FeatureRegistry, Tier4Activation, Tier
from afya.surveillance.service import SurveillanceService
from afya.triage.service import TriageService
from afya.triage.views import TriageInput, TriageResult

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

APP_VERSION = '2.0.0'


class HealthResponse(BaseModel):
	model_config = MODEL_CONFIG
	status: str
	version: str = APP_VERSION
	tier4: bool = False


def build_services(http: AsyncClient | None = None) -> dict[str, object]:
	client = http or AsyncClient(timeout=10)
	registry = FeatureRegistry()
	return {
		'registry': registry,
		'medicine': MedicineService(PPBClient('https://ppb.health.go.ke/api', client)),
		'triage': TriageService(registry),
		'surveillance': SurveillanceService(registry),
	}


def create_app(services: dict[str, object] | None = None) -> FastAPI:
	svc = services or build_services()
	assert {'registry', 'triage', 'surveillance', 'medicine'} <= svc.keys(), 'core services required'
	registry: FeatureRegistry = svc['registry']  # type: ignore[assignment]
	triage: TriageService = svc['triage']  # type: ignore[assignment]
	surveillance: SurveillanceService = svc['surveillance']  # type: ignore[assignment]
	app = FastAPI(title='Afya Yangu / Mlinzi', version=APP_VERSION)

	@app.get('/health', response_model=HealthResponse)
	async def health() -> HealthResponse:
		assert registry.available(), 'registry must respond'
		return HealthResponse(status='ok', tier4=registry.tier4_active())

	@app.get('/features')
	async def features() -> list[dict[str, object]]:
		return [f.model_dump(mode='json') for f in registry.available()]

	@app.post('/triage/preliminary', response_model=TriageResult)
	async def triage_preliminary(inp: TriageInput) -> TriageResult:
		return triage.assess(inp)

	@app.post('/triage/evd', response_model=TriageResult)
	async def triage_evd(inp: TriageInput) -> TriageResult:
		try:
			return triage.assess_evd(inp)
		except PermissionError as exc:
			raise HTTPException(status_code=403, detail=str(exc)) from exc

	@app.post('/tier4/activate')
	async def tier4_activate(auth: Tier4Activation) -> dict[str, bool]:
		return {'activated': await surveillance.activate_tier4(
			auth.authorized_by_pheoc, auth.dpia_reviewed, auth.flag_enabled, auth.bulletin_text,
		)}

	return app