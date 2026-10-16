"""§10.2 MON-005: Water Quality Alerts.

The section's five Features are one household decision — is the water safe, how do I make it safe,
how do I keep it safe, and when do I do it again — and three of the five had no carrier at all. The
advisory string existed and said "do not drink without boiling", which is a *warning* and not
guidance: it names no method the household can perform, says nothing about the container the water
goes back into, and schedules nothing.

The readings below are the two the sources distinguish, and the tests are arranged around that
distinction because it is the one that decides which methods may be offered.
"""
import pydantic
import pytest
from fastapi.testclient import TestClient

from afya.alerts.service import REMINDER_INTERVAL_HOURS, AlertsService
from afya.alerts.views import (
	CHLORINE_TURBIDITY_LIMIT_NTU, TREATMENT_CAVEATS, TREATMENT_STEPS, StorageGuidance,
	TreatmentGuidance, TreatmentMethod, WaterQuality, WaterSafety,
)


def _svc() -> AlertsService:
	return AlertsService()


def _clear(ecoli: bool = True) -> WaterQuality:
	return WaterQuality(county='Homa Bay', ecoli_detected=ecoli, turbidity_ntu=1.0)


def _cloudy() -> WaterQuality:
	"""Above the limit the sources state for chemical disinfection, and below the one at which WHO
	says pretreatment is required regardless of the product. The band where the choice matters."""
	return WaterQuality(county='Homa Bay', ecoli_detected=True, turbidity_ntu=20.0)


# --- "treatment guidance" ------------------------------------------------------------------------

def test_boiling_is_always_offered_and_offered_first() -> None:
	"""WHO's brief is why: boiling is "highly efficacious, killing human pathogens even in turbid
	water and at high altitude". It is the one method with no condition attached, which is why the
	advisory can name it on any reading and the others cannot be named without one."""
	for w in (_clear(), _cloudy()):
		g = _svc().treatment_guidance(w)
		assert g.methods[0] is TreatmentMethod.boil, f'boiling was not led with on {w.turbidity_ntu} NTU'


def test_chlorine_is_withheld_from_water_it_was_not_evaluated_in() -> None:
	"""WHO's Round II evaluation states the tested products "should only be used in nonturbid water
	(<5 NTU)". Recommending chlorine above that is recommending it outside the conditions it was
	evaluated in, and the failure is silent: the household doses the water, waits half an hour, and
	drinks water that was never disinfected because the turbidity consumed the chlorine."""
	svc = _svc()
	assert TreatmentMethod.chlorinate in svc.treatment_guidance(_clear()).methods
	assert TreatmentMethod.chlorinate not in svc.treatment_guidance(_cloudy()).methods, (
		'chlorine was offered for water above the turbidity its own evaluation allows'
	)


def test_the_turbidity_limit_is_the_products_own_and_not_the_pretreatment_one() -> None:
	"""Two figures sit in the source and they mean different things: 5 NTU is the limit the products
	are evaluated to, and 30 NTU is where WHO says pretreatment is required whatever the product.
	Using the higher number as the offer threshold would recommend a method 25 NTU outside its own
	condition."""
	assert CHLORINE_TURBIDITY_LIMIT_NTU == 5.0, 'the limit moved off the products’ own figure'
	svc = _svc()
	at_limit = WaterQuality(county='Kisumu', ecoli_detected=True, turbidity_ntu=5.0)
	over_limit = WaterQuality(county='Kisumu', ecoli_detected=True, turbidity_ntu=5.01)
	assert TreatmentMethod.chlorinate in svc.treatment_guidance(at_limit).methods
	assert TreatmentMethod.chlorinate not in svc.treatment_guidance(over_limit).methods


def test_every_offered_method_carries_its_steps_and_its_limit() -> None:
	"""A method named without its limit is the one a household follows into water that is still
	infectious — chlorine does not touch Cryptosporidium, and boiling leaves no residual protection
	behind at all. So the caveats are asserted to be as long as the method list, and each to name
	something."""
	g = _svc().treatment_guidance(_clear())
	assert len(g.caveats) == len(g.methods), 'a method was offered with no limit attached'
	assert all(caveat.strip() for caveat in g.caveats)
	assert any('cryptosporidiosis' in c for c in g.caveats), 'the chlorine caveat is missing'


def test_the_steps_belong_to_the_methods_that_are_offered() -> None:
	"""The refusal that makes the field a fact rather than a claim: a notice naming boiling and
	describing chlorination is the shape this catches."""
	with pytest.raises(pydantic.ValidationError, match='do not belong'):
		TreatmentGuidance(county='Homa Bay', methods=[TreatmentMethod.boil],
			steps=list(TREATMENT_STEPS[TreatmentMethod.chlorinate]))


def test_a_guidance_with_no_methods_is_refused() -> None:
	"""`methods` is the field every other part of the answer is built from, and an empty list would
	be a notice that says "make it safe" and names nothing."""
	with pytest.raises(pydantic.ValidationError):
		TreatmentGuidance(county='Homa Bay', methods=[], steps=[])


# --- "safe storage guidance" ---------------------------------------------------------------------

def test_storage_guidance_is_served_for_every_reading() -> None:
	"""WHO's Round II evaluation cites a meta-analysis finding "filtration and integrated safe
	storage can reduce the risk of diarrhoeal disease by 61% compared to 51% from filtration only" —
	so this is not a lesser bullet than treatment, and water that is safe and poured back into the
	dirty container is untreated water again."""
	svc = _svc()
	for w in (_clear(), _cloudy()):
		s = svc.storage_guidance(w, TreatmentMethod.boil)
		assert s.steps, 'a reading with no storage guidance'
		assert any('lid' in step.lower() for step in s.steps), 'nothing about covering the container'


def test_the_residual_is_carried_only_for_chlorinated_water() -> None:
	"""WHO's brief states the residual that protects *stored* water — ">=0.5 mg/L after 30 minutes
	of contact time, or >=0.2 mg/L in stored household water" — and it is a figure only chlorine can
	produce. Boiled water has no such number, and a field holding one for it is a figure a reader
	cannot act on."""
	svc = _svc()
	chlorinated = svc.storage_guidance(_clear(), TreatmentMethod.chlorinate)
	boiled = svc.storage_guidance(_clear(), TreatmentMethod.boil)
	assert chlorinated.residual_chlorine_mg_l == 0.2
	assert boiled.residual_chlorine_mg_l is None, 'boiled water was given a chlorine residual'
	assert any('chlorine' in step.lower() for step in chlorinated.steps), (
		'the residual figure is carried with no step telling a household what to do with it'
	)


def test_storage_guidance_refuses_an_empty_step_list() -> None:
	with pytest.raises(pydantic.ValidationError):
		StorageGuidance(county='Homa Bay', steps=[])


# --- "point-of-use treatment reminders" ----------------------------------------------------------

def test_the_reminder_follows_the_time_the_household_treats_water() -> None:
	"""A household that boils in the morning and one that boils at night need different reminders,
	so the service is told when rather than picking. The interval is the storage guidance's own "drink
	it within a day": a reminder on a longer one would remind a household to drink water that has
	stood too long."""
	svc = _svc()
	r = svc.treatment_reminder(_clear(), TreatmentMethod.boil, '2026-10-20T07:00+03:00')
	assert r.due_iso == '2026-10-21T07:00:00+03:00'
	assert REMINDER_INTERVAL_HOURS == 24, 'the reminder interval no longer matches the storage advice'
	assert r.method is TreatmentMethod.boil and r.message


def test_a_reminder_with_no_usable_time_is_refused() -> None:
	"""An unparseable instant is not a reminder, and silently returning one would put a device's
	schedule on a time nobody chose."""
	with pytest.raises(AssertionError, match='not an instant'):
		_svc().treatment_reminder(_clear(), TreatmentMethod.boil, 'sometime tomorrow')


def test_no_reminder_is_served_when_the_household_has_not_said_when() -> None:
	"""The honest answer. The server does not know when this person treats water, and a reminder
	invented from a default would fire at a time nobody chose — the same defect §FND-006's reminder
	is derived to avoid."""
	ws = _svc().water_safety(_clear())
	assert ws.reminder is None
	assert _svc().water_safety(_clear(), '2026-10-20T07:00+03:00').reminder is not None


# --- the whole answer ----------------------------------------------------------------------------

def test_the_water_safety_answer_carries_all_five_features() -> None:
	"""The section's five bullets in one payload, because they are one decision for the household.
	Serving the advisory alone was the state that left three of them with no carrier."""
	ws = _svc().water_safety(_cloudy(), '2026-10-20T07:00+03:00')
	assert ws.unsafe and 'boiling' in ws.advisory.lower(), 'the advisory is no longer the reading’s'
	assert ws.treatment.methods and ws.reminder is not None
	assert len(ws.storage) == len(ws.treatment.methods), (
		'a method was offered with no storage advice behind it'
	)
	assert all(sg.steps for sg in ws.storage)


def test_the_advisory_is_the_existing_one_and_not_a_second_wording() -> None:
	"""One fact on two surfaces. A second string would be the copy that drifts, and it would drift
	away from the route the mobile catalogue already points at."""
	svc = _svc()
	w = _cloudy()
	assert svc.water_safety(w).advisory == svc.water_alert(w)


def test_a_clear_reading_offers_chlorine_with_its_own_residual() -> None:
	"""The residual is reachable only when chlorine is actually offered, which is why the storage
	blocks are per method: one block could only ever be the lead method's, and the lead is always
	boiling — so the figure WHO states for stored chlorinated water would be a field nothing could
	populate."""
	ws = _svc().water_safety(_clear())
	assert TreatmentMethod.chlorinate in ws.treatment.methods
	by_method = dict(zip(ws.treatment.methods, ws.storage, strict=True))
	assert by_method[TreatmentMethod.chlorinate].residual_chlorine_mg_l == 0.2
	assert by_method[TreatmentMethod.boil].residual_chlorine_mg_l is None


def test_the_reminder_is_bound_to_the_method_the_notice_leads_with() -> None:
	"""A notice that recommends boiling and schedules a chlorination is the defect the single
	`method` binding exists to prevent. Cloudy water permits no chlorination at all, so no storage
	block may carry a residual and the reminder must be a boiling one."""
	ws = _svc().water_safety(_cloudy(), '2026-10-20T07:00+03:00')
	assert all(sg.residual_chlorine_mg_l is None for sg in ws.storage), (
		'a reading that permits no chlorination carried a chlorine residual'
	)
	assert ws.reminder is not None and ws.reminder.method is TreatmentMethod.boil


def test_a_safe_reading_still_carries_guidance() -> None:
	"""The day the water is safe is the day a household has time to read how to keep it that way,
	and a screen that went blank would be one they stop opening."""
	ws = _svc().water_safety(WaterQuality(county='Nairobi', ecoli_detected=False, turbidity_ntu=0.5))
	assert ws.unsafe is False and ws.treatment.methods
	assert all(sg.steps for sg in ws.storage)


def test_a_storage_block_with_no_method_behind_it_is_refused() -> None:
	"""The count is what tells a reader which block goes with which method."""
	guidance = _svc().treatment_guidance(_clear())
	with pytest.raises(pydantic.ValidationError, match='storage'):
		WaterSafety(county='Homa Bay', unsafe=True, advisory='x', treatment=guidance, storage=[])


def test_a_storage_block_naming_another_county_is_refused() -> None:
	"""The count has to be right for this to be the check under test, which is the point: a block
	naming a clinic's neighbour is a notice served for one county carrying another's advice."""
	svc = _svc()
	guidance = svc.treatment_guidance(_clear())
	blocks = [svc.storage_guidance(_clear(), m) for m in guidance.methods]
	blocks[0] = StorageGuidance(county='Kisumu', steps=list(blocks[0].steps))
	with pytest.raises(pydantic.ValidationError, match='another county'):
		WaterSafety(county='Homa Bay', unsafe=True, advisory='x', treatment=guidance, storage=blocks)


# --- the route -----------------------------------------------------------------------------------

def test_the_water_route_serves_the_whole_answer() -> None:
	"""The mobile catalogue points at this route, so what it returns is what a person sees. The
	route is public on the same reasoning as the advisory it already served: asking whether the
	water is safe is a question asked before deciding to tell anyone who you are."""
	from afya.service import build_services, create_app
	c = TestClient(create_app(build_services()))
	body = {'county': 'Homa Bay', 'ecoli_detected': True, 'turbidity_ntu': 1.0}
	r = c.post('/environment/water', json={**body, 'treated_at_iso': '2026-10-20T07:00+03:00'})
	assert r.status_code == 200, r.text
	out = r.json()
	assert out['unsafe'] is True
	assert out['treatment']['methods'][0] == 'boil'
	assert len(out['storage']) == len(out['treatment']['methods'])
	assert out['reminder']['method'] == 'boil'
	assert out['reminder']['due_iso'] == '2026-10-21T07:00:00+03:00'


def test_the_route_serves_no_reminder_without_a_time() -> None:
	from afya.service import build_services, create_app
	c = TestClient(create_app(build_services()))
	r = c.post('/environment/water', json={'county': 'Kisumu', 'ecoli_detected': False,
		'turbidity_ntu': 0.5})
	assert r.status_code == 200, r.text
	assert r.json()['reminder'] is None


def test_the_route_refuses_a_time_it_cannot_read() -> None:
	"""The refusal is on the route and not only in the service, because a client that sent a date
	instead of an instant would otherwise be served a notice with no reminder and no reason — and a
	500 would tell the caller the server broke when their input is what was wrong."""
	from afya.service import build_services, create_app
	c = TestClient(create_app(build_services()))
	r = c.post('/environment/water', json={'county': 'Kisumu', 'ecoli_detected': False,
		'turbidity_ntu': 0.5, 'treated_at_iso': 'yesterday'})
	assert r.status_code == 422, r.text
	assert 'not an instant' in r.json()['detail']


# --- the guidance strings themselves -------------------------------------------------------------

def test_every_method_has_steps_and_a_caveat() -> None:
	"""Read from the tables rather than the service, so a method added to the enum and not to the
	guidance fails here rather than the first time somebody is advised with it."""
	for method in TreatmentMethod:
		assert method in TREATMENT_STEPS, f'{method.value} has no steps'
		assert method in TREATMENT_CAVEATS, f'{method.value} has no stated limit'
		assert TREATMENT_STEPS[method], f'{method.value} has an empty step list'
