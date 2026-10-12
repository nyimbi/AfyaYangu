from afya.medicine.service import MedicineService, PPBStubClient
from afya.medicine.views import DoseRequest, VerifyRequest


async def test_stub_client_marks_unverified() -> None:
	svc = MedicineService(PPBStubClient())
	out = await svc.verify(VerifyRequest(batch_number='B1234', gtin='0123456789012'))
	assert out.genuine is False and out.source == 'offline_stub'


async def test_dose_calculator() -> None:
	svc = MedicineService(PPBStubClient())
	out = svc.dose(DoseRequest(drug='paracetamol', weight_kg=20.0))
	# §MED-003 asks for a range, and the source's own spread is 10–15 mg/kg, so 20 kg is 200–300 mg.
	assert out.matched == 'Paracetamol'
	assert out.mg_low == 200.0 and out.mg_high == 300.0
	assert out.mg_per_kg_low == 10.0 and out.mg_per_kg_high == 15.0


async def test_dose_is_refused_for_a_name_the_formulary_does_not_hold() -> None:
	svc = MedicineService(PPBStubClient())
	out = svc.dose(DoseRequest(drug='unobtainium', weight_kg=20.0))
	assert out.unknown is True and out.mg_low is None
	assert any('pharmacist' in w for w in out.warns)


async def test_dose_warns_below_the_reference_range() -> None:
	svc = MedicineService(PPBStubClient())
	out = svc.dose(DoseRequest(drug='paracetamol', weight_kg=2.0))
	assert any('start at' in w for w in out.warns)


async def test_zinc_is_dosed_by_age_and_refuses_without_one() -> None:
	svc = MedicineService(PPBStubClient())
	infant = svc.dose(DoseRequest(drug='zinc', weight_kg=7.0, age_months=3))
	assert infant.lines[0].amount_mg_low == 10.0
	child = svc.dose(DoseRequest(drug='zinc', weight_kg=12.0, age_months=18))
	assert child.lines[0].amount_mg_low == 20.0
	unknown_age = svc.dose(DoseRequest(drug='zinc', weight_kg=12.0))
	assert any('age' in w for w in unknown_age.warns) and unknown_age.lines == []


async def test_artemether_lumefantrine_is_dosed_by_weight_band() -> None:
	svc = MedicineService(PPBStubClient())
	# The source states tablet counts, not a milligram dose: 5–<15 kg is one tablet twice a day.
	out = svc.dose(DoseRequest(drug='coartem', weight_kg=10.0))
	assert out.lines[0].amount_low == 1 and out.lines[0].unit == 'tablet'
	assert out.lines[0].amount_mg_low is None
	assert out.days_low == 3 and out.days_high == 3


def test_interaction_table() -> None:
	svc = MedicineService(PPBStubClient())
	hits = svc.check_interactions(['warfarin', 'aspirin', 'metformin'])
	assert len(hits) == 1 and 'MAJOR' in hits[0]
	assert svc.check_interactions(['metformin']) == []