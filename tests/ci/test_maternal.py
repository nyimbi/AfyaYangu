"""§MON-002's ten features, as served.

The module carried two of the ten: the ANC week list and a danger-sign classifier that wrote a
message. The other eight were in the registry and accounted for in the audit as "the maternal
module exists", which is true of a module and says nothing about a due-date calculator, a birth
plan with five named fields, trimester guidance, postnatal contacts, a newborn sign list, a
maternity finder or a PMTCT referral.

Two of these tests read the spec rather than a copy of it. §MON-002 prints its own feature list and
its own birth-plan parenthetical, and a hand-typed list in a test is a second source of truth that
drifts from the first — which is the failure this file's subject is made of.
"""
from pathlib import Path

import httpx

from afya.maternal.service import MaternalService
from afya.maternal.views import (
	ANC_CONTACTS_WEEKS, ANCRecord, DANGER_SIGN_EDUCATION, DANGER_SIGNS, GESTATION_DAYS, NEWBORN_DANGER_SIGNS,
	POSTNATAL_CONTACTS, TRIMESTER_GUIDANCE, BirthPlan, Pregnancy,
)
from afya.service import build_services, create_app

SPEC = Path(__file__).resolve().parents[2] / 'docs' / 'spec.md'


def _spec_section(heading: str) -> str:
	text = SPEC.read_text(encoding='utf-8')
	return text.split(heading, 1)[1].split('\n#### ', 1)[0]


def _spec_features(heading: str) -> list[str]:
	"""§MON-002's own feature bullets, read from the spec rather than retyped."""
	section = _spec_section(heading)
	start = section.index('**Features:**')
	out: list[str] = []
	for line in section[start:].splitlines()[1:]:
		if not line.startswith('- '):
			break
		out.append(line[2:].strip())
	return out


def _pregnant(**overrides: object) -> Pregnancy:
	body: dict[str, object] = {
		'subject_ref': 'U1', 'edd_iso': '2027-01-20', 'lmp_week': 20, 'lmp_iso': '2026-04-15',
	}
	return Pregnancy(**{**body, **overrides})  # type: ignore[arg-type]


def test_the_feature_list_is_the_sections_own_and_every_one_has_a_carrier() -> None:
	"""The ten the section prints, and the module's answer to each. Named rather than counted, so a
	revision that adds an eleventh feature cannot pass by matching the total."""
	features = _spec_features('#### MON-002')
	assert len(features) == 10, features
	assert 'Estimated due date calculator' in features
	assert 'Birth plan builder (facility, transport, birth companion, blood donor, funds)' in features
	assert 'Referral to PMTCT where relevant' in features
	# The one the section names that this test file has no separate assertion for is the schedule,
	# which predates the unit; the other nine each have one below or in `test_the_...` above it.
	carried = {
		'Estimated due date calculator', 'WHO/Kenya ANC visit schedule (8 contacts)',
		'Visit reminders', 'Danger sign education and one-tap escalation',
		'Birth plan builder (facility, transport, birth companion, blood donor, funds)',
		'Trimester-specific guidance', 'Postnatal visit reminders', 'Newborn danger signs',
		'Facility finder for maternity services', 'Referral to PMTCT where relevant',
	}
	assert set(features) == carried


async def test_the_due_date_calculator_is_naegeles_rule_and_not_an_input() -> None:
	"""§MON-002's first feature. `Pregnancy.edd_iso` was the only date the model had, so the
	arithmetic was the client's — an app that computed it differently, or not at all, registered a
	pregnancy against a date nobody derived."""
	assert GESTATION_DAYS == 280
	# 2026-01-01 + 280 days. The same date the existing tests register by hand, so the calculator
	# and the value the corpus was written against are one fact.
	assert MaternalService.estimated_due_date('2026-01-01') == '2026-10-08'
	assert MaternalService.estimated_due_date('2026-04-15') == '2027-01-20'
	# And the gestation week reads back off either date, and the two routes agree — which is the
	# point of having both: a woman who arrives with a clinic-card EDD and no LMP answers every
	# question the rest of the section asks, because the LMP is 280 days before the EDD by
	# construction. `2026-04-15 + 280 = 2027-01-20`, so the two registrations below are the same
	# pregnancy written two ways and must not disagree about how far along it is.
	m = MaternalService()
	await m.register(_pregnant(subject_ref='A', lmp_iso=None))
	with_lmp = MaternalService()
	await with_lmp.register(_pregnant(subject_ref='A'))
	assert m.gestation_week('A', '2026-10-07') == with_lmp.gestation_week('A', '2026-10-07') == 25
	# And it advances: a week later is a week further on, so the number is a computation and not a
	# constant that happens to match.
	assert m.gestation_week('A', '2026-10-14') == 26


async def test_the_eight_contacts_carry_dates_and_the_two_reminder_leads() -> None:
	"""§MON-002's "Visit reminders". `anc_due` returned contact *numbers* — a count of what is
	outstanding — and a reminder is a date, so there was nothing a client could put in a calendar."""
	m = MaternalService()
	await m.register(_pregnant(subject_ref='A', lmp_iso='2026-04-15', edd_iso='2027-01-20'))
	visits = m.visits('A', '2026-10-07')
	assert [v.gest_week for v in visits] == list(ANC_CONTACTS_WEEKS)
	assert all(v.due_iso.startswith('2026') or v.due_iso.startswith('2027') for v in visits)
	# The LMP is the anchor: contact 1 is at week 12, so 84 days after 2026-04-15.
	assert visits[0].due_iso == '2026-07-08'
	# A contact three days out carries the 3-day lead and not the 1-day one, which is the whole
	# point of having two.
	from afya.maternal.service import _iso_add_days
	today = _iso_add_days(visits[3].due_iso, -3)
	near = [v for v in m.visits('A', today) if v.remind_days_before]
	assert near and near[0].remind_days_before == [3], near
	# An attended contact carries no lead, or the person is reminded about a visit they went to.
	await m.record_anc(ANCRecord(subject_ref='A', contact_no=4, done_iso='2026-09-01'))
	assert [v for v in m.visits('A', today) if v.contact_no == 4][0].remind_days_before == []


def test_the_danger_sign_education_and_the_one_tap_are_both_served() -> None:
	"""§MON-002's fourth feature is two things joined by "and". `assess_danger` wrote a message and
	the escalation *was* that message, so a client had a sentence and no button."""
	assert set(DANGER_SIGN_EDUCATION) == set(DANGER_SIGNS), 'every sign the section prints, explained'
	m = MaternalService()
	out = m.assess_danger(['bleeding', 'fever'])
	assert out.escalate is True
	assert len(out.education) == 2 and {e.sign for e in out.education} == {'bleeding', 'fever'}
	assert out.action is not None and out.action.kind == 'call' and out.action.href == 'tel:719'
	# The order is the classification's: a headache is a clinic today, so the finder leads and the
	# call is not what the person is handed first.
	calm = m.assess_danger(['severe_headache'])
	assert calm.action is not None and calm.action.kind == 'find_maternity'
	assert calm.action.href.startswith('/facilities/find') and 'maternal' in calm.action.href
	# The education is per sign and not one paragraph for the list.
	assert m.education_for('water_breaks').means != m.education_for('fever').means


async def test_the_birth_plan_has_the_five_fields_the_section_names_and_names_its_gaps() -> None:
	"""§MON-002's "Birth plan builder (facility, transport, birth companion, blood donor, funds)".
	`delivery_plan` returned the facility and the EDD — one of the five — and a plan with one of
	five filled is not a plan."""
	section = _spec_section('#### MON-002')
	for field in ('facility', 'transport', 'birth companion', 'blood donor', 'funds'):
		assert field in section, field
	m = MaternalService()
	await m.register(_pregnant(subject_ref='A'))
	empty = m.birth_plan('A')
	assert empty.gaps() == ['facility_id', 'transport', 'birth_companion', 'blood_donor', 'funds_kes']
	partial = BirthPlan(subject_ref='A', facility_id='F1', transport='Matatu from the stage')
	await m.save_birth_plan(partial)
	assert m.birth_plan('A').gaps() == ['birth_companion', 'blood_donor', 'funds_kes']
	full = BirthPlan(subject_ref='A', facility_id='F1', transport='Matatu', birth_companion='Mama',
	                 blood_donor='Sister', funds_kes=5000)
	await m.save_birth_plan(full)
	assert m.birth_plan('A').gaps() == [], 'a complete plan names no gap'


def test_the_guidance_varies_by_trimester_which_is_what_the_feature_asks() -> None:
	"""§MON-002's "Trimester-specific guidance". Nothing in the module varied by week: the guidance
	was the same at week 12 and week 40, which is the feature's name with nothing behind it."""
	assert set(TRIMESTER_GUIDANCE) == {1, 2, 3}
	m = MaternalService()
	first, second, third = (m.trimester_guidance(w) for w in (8, 20, 36))
	assert [first['trimester'], second['trimester'], third['trimester']] == [1, 2, 3]
	# Three different answers, not one answer with a label on it.
	assert len({first['advise'], second['advise'], third['advise']}) == 3
	assert all(row['points'] for row in (first, second, third))
	assert first['gest_week'] == 8 and third['gest_week'] == 36


async def test_the_postnatal_contacts_start_at_the_recorded_birth() -> None:
	"""§MON-002's "Postnatal visit reminders". `Pregnancy` ended at the EDD and the ANC list stopped
	at week 40, so there was no contact after delivery to remind anyone about."""
	assert POSTNATAL_CONTACTS and POSTNATAL_CONTACTS[0][0] == 1
	m = MaternalService()
	await m.register(_pregnant(subject_ref='A'))
	# Before the birth there is nothing to remind about, and four dates derived from a delivery that
	# has not happened are four wrong dates.
	assert m.postnatal_visits('A') == []
	await m.record_birth('A', '2026-12-01')
	visits = m.postnatal_visits('A')
	assert len(visits) == len(POSTNATAL_CONTACTS)
	assert visits[0].due_iso == '2026-12-01' and visits[1].due_iso == '2026-12-03'
	assert visits[-1].due_iso == '2027-01-11', 'week 6 is 42 days after the birth'
	assert all(v.what for v in visits)


def test_the_newborn_signs_are_a_different_list_from_the_mothers() -> None:
	"""§MON-002's "Newborn danger signs". `DANGER_SIGNS` is nine signs of the mother and none of them
	is a newborn sign, so a parent with a sick baby was shown the wrong list."""
	assert len(NEWBORN_DANGER_SIGNS) >= 8
	mother = {s.replace('_', ' ') for s in DANGER_SIGNS}
	baby = {sign for sign, _ in NEWBORN_DANGER_SIGNS}
	assert not (baby & {s.replace(' ', '_') for s in mother}) or len(baby - {s.replace(' ', '_') for s in mother}) >= 6
	# The overlap that does exist is real — a convulsion is a convulsion in either list — but the
	# baby's list carries what the mother's cannot: feeding, the cord, jaundice.
	assert {'not_feeding', 'cord_infection', 'yellow_skin'} <= baby
	assert all(means for _, means in NEWBORN_DANGER_SIGNS)


def test_the_maternity_finder_is_the_same_finder_with_the_service_pinned() -> None:
	"""§MON-002's "Facility finder for maternity services". `FacilityKind` has five members and no
	maternity kind, so a route that filtered on kind could not answer this; `ServiceOffered.maternal`
	is §FND-001's own service and is what the finder filters on."""
	from afya.facilities.service import FacilityService
	from afya.facilities.views import CostBand, Facility, FacilityKind, FacilityLevel, NearestRequest, ServiceOffered
	svc = FacilityService()
	for f in (
		Facility(facility_id='F1', name='Delivers', kind=FacilityKind.treatment_unit, county='Nairobi',
			lat=-1.28, lon=36.90, level=FacilityLevel.health_centre, services=[ServiceOffered.maternal]),
		Facility(facility_id='F2', name='Does not', kind=FacilityKind.treatment_unit, county='Nairobi',
			lat=-1.29, lon=36.88, level=FacilityLevel.dispensary, services=[ServiceOffered.malaria],
			cost_band=CostBand.free),
	):
		svc._facilities[f.facility_id] = f
	found, unanswered = svc.find(NearestRequest(lat=-1.28, lon=36.9, service=ServiceOffered.maternal))
	assert [f.name for f, _ in found] == ['Delivers'], 'the filter is the section\'s own service'
	assert unanswered == []


def test_the_pmtct_referral_does_not_store_the_hiv_result() -> None:
	"""§MON-002's tenth feature, and §9.1's rule for the same fact one section down: HIV status is
	separately gated. The referral takes the boolean the caller derived at the point of care, so the
	result never reaches a module with no PIN on it."""
	from afya.maternal.service import MaternalService as M
	ref = M.pmtct_referral('U1', True)
	assert ref.relevant is True and ref.programme and 'PMTCT' in ref.advise
	no = M.pmtct_referral('U1', False)
	assert no.relevant is False and no.programme is None
	# Nothing in the module carries a status: the only HIV-shaped thing is the referral's own text.
	import afya.maternal.service as svc_mod
	source = Path(svc_mod.__file__).read_text(encoding='utf-8')
	assert 'hiv_positive: bool' in source, 'the result travels as a boolean, not as a status'
	assert 'hiv_status' not in source and 'HIV status' not in source.replace('HIV result', '')


async def test_every_maternal_route_is_served_and_bound_to_the_token() -> None:
	"""The routes, not just the service. A capability with no route is one nobody can use, and a
	personal-data route that names a subject without binding it is the §17 defect."""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		anon = (await c.post('/auth/anonymous', json={'subject_ref': 'U1'})).json()['token']
		h = {'authorization': f'Bearer {anon}'}
		other = (await c.post('/auth/anonymous', json={'subject_ref': 'U2'})).json()['token']
		# The calculator is public: a date in, a date out, nothing stored.
		r = await c.get('/maternal/due-date', params={'lmp_iso': '2026-01-01'})
		assert r.status_code == 200 and r.json()['edd_iso'] == '2026-10-08'
		assert (await c.get('/maternal/due-date', params={'lmp_iso': 'x'})).status_code == 422
		assert (await c.post('/maternal/pregnancy', json={
			'subject_ref': 'U1', 'edd_iso': '2027-01-20', 'lmp_week': 20, 'lmp_iso': '2026-04-15',
		}, headers=h)).status_code == 200
		assert len((await c.get('/maternal/U1/visits', params={'today_iso': '2026-10-07'}, headers=h)).json()) == 8
		# The newborn list and the guidance are reference content, not personal data.
		assert len((await c.get('/maternal/newborn-signs')).json()) >= 8
		assert (await c.get('/maternal/guidance', params={'gest_week': 30})).json()['trimester'] == 3
		assert (await c.get('/maternal/guidance', params={'gest_week': 99})).status_code == 422
		plan = await c.post('/maternal/birth-plan', json={'subject_ref': 'U1', 'transport': 'Matatu'}, headers=h)
		assert plan.status_code == 200 and len(plan.json()['gaps']) == 4
		assert len((await c.get('/maternal/U1/birth-plan', headers=h)).json()['gaps']) == 4
		assert (await c.post('/maternal/birth', json={'subject_ref': 'U1', 'birth_iso': '2026-12-01'}, headers=h)).status_code == 200
		assert len((await c.get('/maternal/U1/postnatal', headers=h)).json()) == len(POSTNATAL_CONTACTS)
		assert (await c.post('/maternal/pmtct-referral', json={'subject_ref': 'U1', 'hiv_positive': True}, headers=h)).json()['relevant'] is True
		# And the guard: a token for U2 naming U1 is refused on every subject-bearing route.
		h2 = {'authorization': f'Bearer {other}'}
		cross = [
			await c.get('/maternal/U1/visits', headers=h2),
			await c.get('/maternal/U1/postnatal', headers=h2),
			await c.get('/maternal/U1/birth-plan', headers=h2),
			await c.post('/maternal/birth-plan', json={'subject_ref': 'U1'}, headers=h2),
			await c.post('/maternal/birth', json={'subject_ref': 'U1', 'birth_iso': '2026-12-01'}, headers=h2),
			await c.post('/maternal/pmtct-referral', json={'subject_ref': 'U1', 'hiv_positive': True}, headers=h2),
		]
		assert all(r.status_code == 403 for r in cross), [(r.request.url.path, r.status_code) for r in cross]
		# A maternity finder is a read with no subject, so it stays open, and it answers the filter.
		assert (await c.get('/maternal/facilities', params={'lat': -1.28, 'lon': 36.9})).status_code == 200
