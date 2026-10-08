from afya.medicine.service import MedicineService, PPBStubClient
from afya.medicine.views import DoseRequest, VerifyRequest


async def test_stub_client_marks_unverified() -> None:
	svc = MedicineService(PPBStubClient())
	out = await svc.verify(VerifyRequest(batch_number='B1234', gtin='0123456789012'))
	assert out.genuine is False and out.source == 'offline_stub'


async def test_dose_calculator() -> None:
	svc = MedicineService(PPBStubClient())
	out = svc.dose(DoseRequest(drug='paracetamol', weight_kg=20.0, mg_per_kg=15.0))
	assert out.total_mg == 300.0 and out.warns == []


async def test_dose_warnings() -> None:
	svc = MedicineService(PPBStubClient())
	out = svc.dose(DoseRequest(drug='x', weight_kg=3.0, mg_per_kg=65.0))
	assert any('paediatric' in w for w in out.warns) and any('high' in w for w in out.warns)


def test_interaction_table() -> None:
	svc = MedicineService(PPBStubClient())
	hits = svc.check_interactions(['warfarin', 'aspirin', 'metformin'])
	assert len(hits) == 1 and 'MAJOR' in hits[0]
	assert svc.check_interactions(['metformin']) == []