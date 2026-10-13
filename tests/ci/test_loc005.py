"""§11.5 LOC-005: the border and point-of-entry module.

Seven Features; four were carried and three were bullets with no carrier at all. The three share a
shape — the module described a *plan* and had no other end of it:

* the enrolment stated a schedule of days 1, 3, 7, 14 and 21 and **no route accepted a report**
  against it, so the schedule was a notification plan with nothing behind it;
* `TravelerDeclaration.lang` was accepted and **never read**, so every acknowledgement went out in
  English whatever the traveller said they read;
* `BorderPost` described a queue and a screening flag and **nothing about testing**, so a screen
  could not tell a traveller whether the post could run their sample or send it onward.

The language tests are the ones worth reading. §ACC-002 names six languages for *voice-guided
symptom reporting* and §LOC-005 asks for multi-language support for *cross-border travellers*, and
those are different requirements with different honest answers: this path has strings for the two
languages the repo carries a table for, serves English for the rest, and offers only the two in its
own catalogue rather than a dropdown that promises Dholuo and delivers English.
"""
import pydantic
import pytest
from fastapi.testclient import TestClient

from afya.location.service import LocationService
from afya.location.views import (
	BorderPost, PostArrivalReport, TravellerEnrolment, TravelerDeclaration,
)
from afya.strings import SUPPORTED_LANGS, TRAVELLER_STRINGS, answerable, traveller


def _svc() -> LocationService:
	return LocationService()


async def _enrolled(svc: LocationService, lang: str = 'en', subject: str = 'U-1') -> TravellerEnrolment:
	return await svc.self_declare(TravelerDeclaration(
		declaration_id='TD-ABCDEFGH', subject_ref=subject, destination='Nairobi',
		arrival_iso='2026-10-01T00:00:00Z', origin_country='UG', lang=lang,
	))


# --- "post-arrival symptom reporting" ------------------------------------------------------------

async def test_a_report_on_a_scheduled_day_is_accepted_and_answered() -> None:
	"""The schedule the enrolment states is a promise that someone will read a report on those days.
	Without this route the promise had nothing behind it."""
	svc = _svc()
	await _enrolled(svc)
	v = await svc.report_arrival_day(PostArrivalReport(subject_ref='U-1', day=3))
	assert v.day == 3 and v.days_remaining == 18
	assert v.escalate is False and v.notify_border_health is False
	assert 'no warning signs' in v.message


async def test_a_report_on_a_day_nobody_asks_about_is_refused() -> None:
	"""Day 5 is not in [1, 3, 7, 14, 21]. Accepting it would tell a traveller they had been checked
	on a day the schedule does not cover, which is a false reassurance at the end of a 21-day
	window — the one place a missed report matters most."""
	svc = _svc()
	await _enrolled(svc)
	with pytest.raises(AssertionError, match='not one of the days'):
		await svc.report_arrival_day(PostArrivalReport(subject_ref='U-1', day=5))


async def test_a_report_from_someone_who_never_declared_is_refused() -> None:
	"""The enrolment is what makes a 21-day window exist. A report accepted from a person with no
	enrolment would create one by the back door, with a schedule nobody recorded and a language
	nobody declared."""
	with pytest.raises(AssertionError, match='not enrolled'):
		await _svc().report_arrival_day(PostArrivalReport(subject_ref='U-9', day=1))


async def test_a_fever_on_a_scheduled_day_escalates() -> None:
	"""§MON-009's own rule, read off `MONITORING_ALERT_SYMPTOMS` rather than written again: a
	traveller and a contact are the same person under the same criteria, and two lists would drift
	on the day one of them was edited."""
	svc = _svc()
	await _enrolled(svc)
	v = await svc.report_arrival_day(PostArrivalReport(subject_ref='U-1', day=1, temperature_c=38.4))
	assert v.escalate is True and v.notify_border_health is True
	assert 'fever' in v.message and '719' in v.message
	assert 'public transport' in v.message


async def test_a_warning_sign_without_fever_escalates_too() -> None:
	"""A thermometer is not the only way into this: the alert symptom set is the other, and it is
	the one a traveller with no thermometer has."""
	svc = _svc()
	await _enrolled(svc)
	v = await svc.report_arrival_day(PostArrivalReport(subject_ref='U-1', day=7, symptoms=['bleeding']))
	assert v.escalate is True and 'bleeding' in v.message


async def test_a_report_on_the_last_day_leaves_nothing_remaining() -> None:
	"""Day 21 is the end of the window and the arithmetic has to say so rather than leaving a
	traveller waiting for a day 22 that will never be asked about."""
	svc = _svc()
	await _enrolled(svc)
	assert (await svc.report_arrival_day(PostArrivalReport(subject_ref='U-1', day=21))).days_remaining == 0


async def test_reports_are_kept_per_traveller() -> None:
	svc = _svc()
	await _enrolled(svc, subject='U-1')
	await _enrolled(svc, subject='U-2')
	await svc.report_arrival_day(PostArrivalReport(subject_ref='U-1', day=1))
	await svc.report_arrival_day(PostArrivalReport(subject_ref='U-2', day=1))
	await svc.report_arrival_day(PostArrivalReport(subject_ref='U-2', day=3))
	assert len(svc.reports_for('U-1')) == 1
	assert len(svc.reports_for('U-2')) == 2


# --- "multi-language support for cross-border travellers" ----------------------------------------

async def test_the_advisory_is_served_in_the_language_the_traveller_asks_for() -> None:
	"""The string was an English literal and the route took no language, so a traveller crossing at
	Busia who reads Kiswahili was served English on the one screen where getting it wrong means
	arriving unwell and not knowing to call 719."""
	svc = _svc()
	en = svc.advisory('Kampala', 'Kenya', 'en')
	sw = svc.advisory('Kampala', 'Kenya', 'sw')
	assert en != sw and 'Safari kwenda' in sw and 'Travel to' in en
	assert 'Kampala' in sw and 'Kenya' in sw, 'the Kiswahili string lost its placeholders'
	assert '719' in sw and '719' in en


async def test_the_enrolment_acknowledgement_is_in_the_declared_language() -> None:
	"""The declaration carried `lang` and `self_declare` never read it, so the field was a claim.
	This is the message that tells a traveller when they will next be asked anything."""
	svc = _svc()
	en = await _enrolled(svc, 'en', subject='U-1')
	sw = await _enrolled(svc, 'sw', subject='U-2')
	assert sw.lang == 'sw' and sw.message != en.message
	assert 'Umeandikishwa' in sw.message and 'days 1, 3, 7, 14 and 21' in en.message


async def test_a_language_with_no_table_is_served_english_and_says_so() -> None:
	"""§ACC-002's `answerable` rule, not a second one: a wrong instruction at a point of entry is
	worse than an honest English one, and the payload names the language it actually got so a
	Dholuo speaker is not left reading English believing it is Dholuo."""
	svc = _svc()
	enrolment = await _enrolled(svc, 'luo')
	assert enrolment.lang == 'luo', 'the payload lost the language the traveller declared in'
	assert enrolment.message == TRAVELLER_STRINGS['en']['enrolled']
	assert answerable('luo') == 'en'
	assert 'luo' not in SUPPORTED_LANGS, 'the point of this test is that Dholuo has no table here'


async def test_every_traveller_string_exists_in_every_table() -> None:
	"""Read from the tables rather than the service, so a key added to one language and not the
	other fails here rather than the first time a Kiswahili speaker reaches that screen."""
	assert set(TRAVELLER_STRINGS['sw']) == set(TRAVELLER_STRINGS['en'])
	for key, text in TRAVELLER_STRINGS['en'].items():
		assert text.strip(), f'{key} is empty in en'
		assert TRAVELLER_STRINGS['sw'][key].strip(), f'{key} is empty in sw'


def test_an_unknown_traveller_string_is_refused() -> None:
	"""A missing key raises rather than returning a placeholder: a silent empty string is a screen
	that renders blank where an instruction should be."""
	with pytest.raises(AssertionError, match='unknown traveller string'):
		traveller('en', 'no_such_string')


async def test_the_daily_prompt_is_served_in_the_declared_language() -> None:
	"""The client has no other source for the question. A prompt written on the handset is one that
	never gets the traveller's language, which is the defect this whole bullet is about."""
	svc = _svc()
	await _enrolled(svc, 'sw')
	prompt = svc.arrival_prompt('U-1', 3)
	assert 'Siku 3 kati ya 21' in prompt
	assert svc.arrival_prompt('U-1', 21)
	with pytest.raises(AssertionError, match='not a scheduled report day'):
		svc.arrival_prompt('U-1', 4)


# --- "integration with mobile laboratory results at border points" -------------------------------

def test_a_post_with_a_mobile_lab_describes_it() -> None:
	"""A post either has a lab on site or sends its samples onward, and a screen that cannot say
	which is a traveller sent to a post that cannot test them."""
	post = BorderPost(post_id='BP-1', name='Busia', county='Busia', country_pair='KE-UG',
		queue_minutes=25, screening_required=True, mobile_lab=True, lab_turnaround_hours=4,
		lab_tests=['mRDT', 'Ebola PCR'])
	assert post.mobile_lab and post.lab_turnaround_hours == 4 and len(post.lab_tests) == 2


def test_a_post_without_a_lab_is_the_default_and_carries_no_promise() -> None:
	post = BorderPost(post_id='BP-2', name='Namanga', county='Kajiado', country_pair='KE-TZ',
		queue_minutes=10, screening_required=False)
	assert post.mobile_lab is False
	assert post.lab_turnaround_hours is None and post.lab_tests == []


def test_a_lab_turnaround_with_no_lab_behind_it_is_refused() -> None:
	"""A turnaround stated by a post that reports no lab is a promise from a post that cannot keep
	it."""
	with pytest.raises(pydantic.ValidationError, match='reports no lab'):
		BorderPost(post_id='BP-3', name='X', county='Y', country_pair='KE-UG', queue_minutes=5,
			screening_required=False, lab_turnaround_hours=6)


def test_tests_named_with_no_lab_behind_them_are_refused() -> None:
	"""A test list with no lab is a menu for a service that is not there."""
	with pytest.raises(pydantic.ValidationError, match='names tests with no lab'):
		BorderPost(post_id='BP-4', name='X', county='Y', country_pair='KE-UG', queue_minutes=5,
			screening_required=False, lab_tests=['mRDT'])


def test_a_lab_with_no_turnaround_is_refused() -> None:
	with pytest.raises(pydantic.ValidationError, match='lab with no turnaround'):
		BorderPost(post_id='BP-5', name='X', county='Y', country_pair='KE-UG', queue_minutes=5,
			screening_required=False, mobile_lab=True, lab_tests=['mRDT'])


# --- the routes ----------------------------------------------------------------------------------

def _client() -> TestClient:
	from afya.service import build_services, create_app
	return TestClient(create_app(build_services()))


def _token(c: TestClient, subject: str = 'U-1') -> dict[str, str]:
	"""A citizen token for `subject`. The traveller routes are `require_self`-guarded, so a report
	filed without one is a 401 rather than a silent write."""
	r = c.post('/auth/anonymous', json={'subject_ref': subject})
	assert r.status_code == 200, r.text
	return {'authorization': f'Bearer {r.json()["token"]}'}


def test_the_advisory_route_takes_a_language() -> None:
	r = _client().get('/location/travel-advisory',
		params={'destination': 'Kampala', 'origin_country': 'Kenya', 'lang': 'sw'})
	assert r.status_code == 200, r.text
	assert 'Safari kwenda' in r.json()['advisory']


def test_the_advisory_route_still_works_without_one() -> None:
	r = _client().get('/location/travel-advisory',
		params={'destination': 'Kampala', 'origin_country': 'Kenya'})
	assert r.status_code == 200 and 'Travel to' in r.json()['advisory']


def test_the_declaration_route_records_the_language_it_was_given() -> None:
	c = _client()
	r = c.post('/location/traveller/declare', headers=_token(c), json={
		'declaration_id': 'TD-ABCDEFGH', 'subject_ref': 'U-1', 'destination': 'Nairobi',
		'arrival_iso': '2026-10-01T00:00:00Z', 'origin_country': 'UG', 'lang': 'sw'})
	assert r.status_code == 200, r.text
	assert r.json()['lang'] == 'sw' and 'Umeandikishwa' in r.json()['message']


def test_the_prompt_route_serves_the_question_for_a_scheduled_day() -> None:
	c = _client()
	h = _token(c)
	c.post('/location/traveller/declare', headers=h, json={
		'declaration_id': 'TD-ABCDEFGH', 'subject_ref': 'U-1', 'destination': 'Nairobi',
		'arrival_iso': '2026-10-01T00:00:00Z', 'origin_country': 'UG', 'lang': 'sw'})
	r = c.get('/location/traveller/U-1/prompt', headers=h, params={'day': 7})
	assert r.status_code == 200, r.text
	assert r.json()['lang'] == 'sw' and 'Siku 7' in r.json()['prompt']


def test_the_prompt_route_refuses_a_day_outside_the_schedule() -> None:
	"""422 and not 500: the caller sent the day, and the server can say which days it accepts."""
	c = _client()
	h = _token(c)
	c.post('/location/traveller/declare', headers=h, json={
		'declaration_id': 'TD-ABCDEFGH', 'subject_ref': 'U-1', 'destination': 'Nairobi',
		'arrival_iso': '2026-10-01T00:00:00Z', 'origin_country': 'UG'})
	r = c.get('/location/traveller/U-1/prompt', headers=h, params={'day': 4})
	assert r.status_code == 422, r.text
	assert 'not a scheduled report day' in r.json()['detail']


def test_the_report_route_serves_the_verdict_and_the_language() -> None:
	c = _client()
	h = _token(c)
	c.post('/location/traveller/declare', headers=h, json={
		'declaration_id': 'TD-ABCDEFGH', 'subject_ref': 'U-1', 'destination': 'Nairobi',
		'arrival_iso': '2026-10-01T00:00:00Z', 'origin_country': 'UG', 'lang': 'sw'})
	r = c.post('/location/traveller/report', headers=h, json={
		'subject_ref': 'U-1', 'day': 3, 'symptoms': ['fever'], 'temperature_c': 38.5})
	assert r.status_code == 200, r.text
	out = r.json()
	assert out['escalate'] is True and out['lang'] == 'sw'
	assert 'Siku 3' in out['message'] and '719' in out['message']


def test_the_report_route_refuses_a_day_outside_the_schedule() -> None:
	c = _client()
	h = _token(c)
	c.post('/location/traveller/declare', headers=h, json={
		'declaration_id': 'TD-ABCDEFGH', 'subject_ref': 'U-1', 'destination': 'Nairobi',
		'arrival_iso': '2026-10-01T00:00:00Z', 'origin_country': 'UG'})
	r = c.post('/location/traveller/report', headers=h, json={'subject_ref': 'U-1', 'day': 5})
	assert r.status_code == 422, r.text
	assert 'not one of the days' in r.json()['detail']


def test_a_traveller_cannot_file_a_report_for_someone_else() -> None:
	"""The route is guarded because a report is a person's own symptoms. Without `require_self` the
	`subject_ref` in the body would be whoever the caller typed, and the verdict — including
	whether a county team is notified — would be about a stranger."""
	c = _client()
	h = _token(c, 'U-1')
	r = c.post('/location/traveller/report', headers=h, json={'subject_ref': 'U-2', 'day': 1})
	assert r.status_code == 403, r.text
	assert 'own subject' in r.json()['detail']


def test_the_border_route_records_a_post_with_a_lab() -> None:
	c = _client()
	r = c.post('/location/border', json={
		'post_id': 'BP-1', 'name': 'Busia', 'county': 'Busia', 'country_pair': 'KE-UG',
		'queue_minutes': 25, 'screening_required': True, 'mobile_lab': True,
		'lab_turnaround_hours': 4, 'lab_tests': ['mRDT']})
	assert r.status_code == 200, r.text
	s = c.get('/location/border/BP-1')
	assert s.status_code == 200, s.text
	assert s.json()['mobile_lab'] is True and s.json()['lab_tests'] == ['mRDT']
