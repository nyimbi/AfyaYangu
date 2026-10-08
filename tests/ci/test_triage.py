import pytest

from afya.registry.service import FeatureRegistry, Tier4Activation
from afya.triage.service import TriageService
from afya.triage.views import DiaryEntry, RiskLevel, TriageInput


@pytest.fixture
def svc() -> TriageService:
	return TriageService(FeatureRegistry())


async def test_healthy_low(svc: TriageService) -> None:
	out = svc.assess(TriageInput(symptoms=[], temperature_c=37.0))
	assert out.risk_level is RiskLevel.low and not out.escalate_719


async def test_malaria_trap(svc: TriageService) -> None:
	out = svc.assess(TriageInput(symptoms=['fever'], temperature_c=38.6, ebola_contact=False))
	assert out.risk_level is RiskLevel.malaria_suspect
	assert out.treated_as_malaria_first and 'malaria' in out.recommendation.lower()


async def test_contact_history_escalates(svc: TriageService) -> None:
	out = svc.assess(TriageInput(symptoms=['fever', 'headache'], temperature_c=38.2, ebola_contact=True))
	assert out.risk_level is RiskLevel.high and out.escalate_719


async def test_bleeding_always_high(svc: TriageService) -> None:
	out = svc.assess(TriageInput(symptoms=['bleeding'], temperature_c=36.8))
	assert out.risk_level is RiskLevel.high


async def test_tri003_gated_when_dormant(svc: TriageService) -> None:
	with pytest.raises(PermissionError):
		svc.assess_evd(TriageInput(symptoms=['fever'], temperature_c=39.0, ebola_contact=True))


async def test_tri003_active_after_gate() -> None:
	registry = FeatureRegistry(Tier4Activation(authorized_by_pheoc=True, dpia_reviewed=True, flag_enabled=True))
	assert registry.tier4_active()
	out = TriageService(registry).assess_evd(TriageInput(symptoms=['fever'], temperature_c=39.0, ebola_contact=True))
	assert out.risk_level is RiskLevel.high


async def test_diary_21_day_window(svc: TriageService) -> None:
	from pydantic import ValidationError
	with pytest.raises(ValidationError):
		DiaryEntry(entry_id='DIARY-ABC123XY99', subject_ref='U1', day=22, symptoms=['fever'], temperature_c=37.0)