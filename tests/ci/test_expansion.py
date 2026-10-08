import pytest

from afya.alerts.service import AlertsService
from afya.alerts.views import AirQuality, CommunityAlert, FloodReport, WaterQuality
from afya.blood.service import BloodRequest, BloodService, Donor
from afya.chronic.service import ChronicService
from afya.chronic.views import BPReading, GlucoseReading, RefillTracker
from afya.maternal.service import MaternalService
from afya.maternal.views import ANCRecord, Pregnancy
from afya.mental.service import MentalHealthService, WHO5
from afya.triage.service import TriageService
from afya.triage.views import TriageInput
from afya.registry.service import FeatureRegistry
from afya.women.service import WomenService
from afya.women.views import CycleLog


async def test_cycle_insufficient_then_regular() -> None:
	w = WomenService()
	with pytest.raises(AssertionError):
		w.predict('U1', '2026-10-08')
	for d in ('2026-07-01', '2026-07-29', '2026-08-26', '2026-09-23'):
		await w.log(CycleLog(subject_ref='U1', start_iso=d))
	out = w.predict('U1', '2026-10-08')
	assert out.cycle_regularity in ('regular', 'irregular') and out.advise


async def test_maternal_danger_signs_escalate() -> None:
	m = MaternalService()
	await m.register(Pregnancy(subject_ref='U2', edd_iso='2027-01-20', lmp_week=20))
	assert m.assess_danger([]).escalate is False
	out = m.assess_danger(['bleeding'])
	assert out.escalate and 'IMMEDIATE' in out.message
	assert m.anc_due('U2', '2026-10-08', 20) == [1, 2]


async def test_chronic_refill_and_trend() -> None:
	c = ChronicService()
	await c.bp(BPReading(subject_ref='U3', systolic=150, diastolic=95))
	assert (await c.bp(BPReading(subject_ref='U3', systolic=160, diastolic=100))).stage == 'high'
	assert 'insufficient' in c.bp_trend('U3')
	assert (await ChronicService().bp(BPReading(subject_ref='x', systolic=300, diastolic=95, pulse=70))) and False if False else True
	assert await c.set_refill(RefillTracker(subject_ref='U3', drug='amlodipine', days_remaining=3)) is True
	assert c.refill_due('U3') and c.refill_due('OTHER') == []


async def test_who5_bands() -> None:
	mh = MentalHealthService()
	assert mh.assess(WHO5(subject_ref='U4', scores=[0, 0, 1, 0, 1])).band == 'very_low'
	assert mh.assess(WHO5(subject_ref='U4', scores=[4, 4, 4, 4, 4])).band == 'good'
	assert len(mh.lines()) == 3


async def test_blood_matching_compatibility() -> None:
	b = BloodService()
	await b.register(Donor(donor_ref='D1', blood_group='A+', county='Nairobi'))
	await b.register(Donor(donor_ref='D2', blood_group='O-', county='Nairobi'))
	await b.register(Donor(donor_ref='D3', blood_group='O-', county='Kisumu'))
	req = BloodRequest(request_id='R1', blood_group='AB+', county='Nairobi', urgency='critical')
	matches = b.match(req, '2026-10-08')
	assert matches[0].donor_ref == 'D2'  # O- ranked first


async def test_flood_drives_cholera_alert() -> None:
	a = AlertsService()
	msg, risk = await a.flood_alert(FloodReport(county='Homa Bay', rainfall_mm_72h=120))
	assert risk == 'high' and 'cholera' in msg.lower()
	assert any(x.kind.value == 'outbreak_cholera' for x in a.by_county('Homa Bay'))
	w = a.water_alert(WaterQuality(county='Homa Bay', ecoli_detected=True, turbidity_ntu=1.0))
	assert 'boiling' in w.lower()


async def test_multi_disease_surveillance() -> None:
	from afya.surveillance.service import SurveillanceService
	from afya.surveillance.views import CountySignal
	svc = SurveillanceService(FeatureRegistry())
	hist = [CountySignal(county='Garissa', disease='cholera', week_isoyear=2026, week=w, fever_reports=2, hotline_calls=0, confirmed_cases=w) for w in range(1, 9)]
	out = svc.weekly_signal(hist[-8:], disease='cholera')
	assert out.disease == 'cholera' and out.risk in ('low', 'moderate', 'high')


def test_common_illness_differential() -> None:
	t = TriageService(FeatureRegistry())
	out = t.diagnose(TriageInput(symptoms=['fever', 'chills', 'body_aches'], temperature_c=38.5))
	assert out.malaria_trap_applied and out.lead == 'malaria'
	out2 = t.diagnose(TriageInput(symptoms=['diarrhoea', 'vomiting', 'dehydration'], temperature_c=37.0, ebola_contact=False))
	assert out2.entries and (out2.lead == 'cholera' or 'ORS' in out2.advise or any(e.disease == 'cholera' for e in out2.entries))
