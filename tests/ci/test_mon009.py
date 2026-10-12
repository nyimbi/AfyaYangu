"""§11.3 MON-009: the five bullets the 21-day contact diary was missing.

What is under test is not "does a route exist" but whether each bullet is discharged against the
thing that makes it true:

* **Twice-daily reminders are state, not a queue.** §11.3's adherence design says reminders
  "escalate in urgency if missed", so the ladder has to be computable from what was logged. The
  canary for this is a person who logs every *morning* and forgets every *evening*: a ladder that
  only counts days with no entry at all never fires for them, and that is the commonest way a 21-day
  diary is lost.
* **Consent is a recorded decision, not a client boolean.** `MonitoringDay.location_logged` was a
  flag nothing set; making it settable is not consent, it is a client asserting consent on the
  person's behalf. The canary flips the assertion and confirms the location gate is not blind.
* **A household member has their own series.** The predecessor accepted `household_member` and read
  nothing, so a member's fever counted as the contact's. The canary files a member's day and checks
  it does *not* appear in the contact's diary.
* **Psychological support is attached to the verdict.** A crisis-line directory in another section
  is a directory; the bullet is that the support is on the screen the person is already looking at.
* **The officer line is dialable or it says it is not.** A name with no number behind it is a dead
  button, and the fallback has to be a line that is answered.
"""
import re

import httpx
import pytest

from afya.mental.views import COUNSELLING_LINES
from afya.monitoring.service import MONITORING_DAYS, MonitoringService, support_resources
from afya.monitoring.views import REMINDER_SLOTS, MonitoringDay, ReminderSlot
from afya.service import build_services, create_app

FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')


def _day(subject: str, day: int, temp: float = 36.8, **kw: object) -> MonitoringDay:
	body: dict[str, object] = {'entry_id': f'MON-ENTRY{day:04d}', 'subject_ref': subject, 'day': day,
	                           'temperature_c': temp}
	return MonitoringDay(**{**body, **kw})  # type: ignore[arg-type]


async def _citizen(c: httpx.AsyncClient, subject: str | None = None) -> tuple[dict[str, str], str]:
	tok = (await c.post('/auth/anonymous', json={'subject_ref': subject} if subject else {})).json()
	return {'Authorization': f'Bearer {tok["token"]}'}, str(tok['subject_ref'])


# --- twice-daily reminders ------------------------------------------------------------------

def test_a_day_has_exactly_two_slots() -> None:
	"""§MON-009's "twice-daily". Two, and the two are named, because a surface that cannot say which
	one is outstanding cannot tell the person what to do."""
	assert [s.value for s in REMINDER_SLOTS] == ['morning', 'evening']
	assert len(REMINDER_SLOTS) == 2


async def test_both_slots_logged_makes_the_day_complete() -> None:
	svc = MonitoringService()
	svc.enrol('s1')
	await svc.log_day(_day('s1', 1, slot=ReminderSlot.morning))
	await svc.log_day(_day('s1', 1, slot=ReminderSlot.evening))
	state = svc.reminders('s1', 1)
	assert state.complete is True
	assert state.missing == []
	assert state.escalation == 'none'
	assert sorted(state.logged) == ['evening', 'morning']


async def test_one_slot_logged_names_the_one_that_is_missing() -> None:
	svc = MonitoringService()
	svc.enrol('s1')
	await svc.log_day(_day('s1', 1, slot=ReminderSlot.morning))
	state = svc.reminders('s1', 1)
	assert state.complete is False
	assert state.missing == ['evening'], 'the missing slot is named, not merely counted'
	assert state.escalation == 'gentle'
	assert 'evening' in state.message


async def test_the_ladder_fires_for_the_person_who_forgets_every_evening() -> None:
	"""The canary's target. Four mornings logged and no evening: a ladder that counts only days with
	*no* entry sees a perfect record and stays silent. §11.3 says the reminders escalate if missed,
	and a half-kept day is missed."""
	svc = MonitoringService()
	svc.enrol('s1')
	for d in range(1, 5):
		await svc.log_day(_day('s1', d, slot=ReminderSlot.morning))
	state = svc.reminders('s1', 4)
	assert state.complete is False
	assert state.escalation == 'urgent', 'four half-days is four missed days'
	# Days 1–4 are not empty — and that is the point: an emptiness-only ladder sees a perfect record.
	assert all(d not in svc.adherence_reminder_days('s1') for d in range(1, 5))


async def test_the_ladder_is_gentle_at_one_missed_day_and_firm_at_two() -> None:
	svc = MonitoringService()
	svc.enrol('s1')
	# Day 1 complete, day 2 nothing, day 3 morning only.
	for slot in REMINDER_SLOTS:
		await svc.log_day(_day('s1', 1, slot=slot))
	await svc.log_day(_day('s1', 3, slot=ReminderSlot.morning))
	assert svc.reminders('s1', 3).escalation == 'firm', 'days 2 and 3 are both incomplete'
	assert svc.reminders('s1', 1).escalation == 'none'


def test_reminders_refuse_a_day_outside_the_window() -> None:
	svc = MonitoringService()
	svc.enrol('s1')
	with pytest.raises(AssertionError):
		svc.reminders('s1', 22)
	with pytest.raises(AssertionError):
		svc.reminders('s1', 0)


async def test_an_entry_without_a_slot_still_counts_towards_the_day() -> None:
	"""A client that predates the field must still be able to keep a diary. Two entries with no slot
	are read as the two slots, because counting is the best a service can do when it is not told."""
	svc = MonitoringService()
	svc.enrol('s1')
	await svc.log_day(_day('s1', 1))
	await svc.log_day(_day('s1', 1, temp=37.1))
	state = svc.reminders('s1', 1)
	assert state.complete is True
	assert state.missing == []


async def test_one_entry_without_a_slot_is_a_half_day_not_a_whole_one() -> None:
	"""The fallback's own boundary. Assigning entries to slots in order means *one* unslotted entry
	fills one slot — not both — and the canary for this is exactly the line that returns both slots
	whenever any entry exists: that passes a two-entry test and quietly completes every half-day."""
	svc = MonitoringService()
	svc.enrol('s1')
	await svc.log_day(_day('s1', 1))
	state = svc.reminders('s1', 1)
	assert state.complete is False
	assert state.missing == ['evening'], 'one reading is one slot'
	assert state.logged == ['morning']


# --- location logging with consent ----------------------------------------------------------

async def test_a_location_without_recorded_consent_is_refused() -> None:
	"""Consent is the household's recorded decision (§MON-009), not the entry's own boolean. The
	precedent is `location/service.py`: `assert history.consent_granted` before any point is taken."""
	svc = MonitoringService()
	svc.enrol('s1')
	with pytest.raises(AssertionError) as exc:
		await svc.log_day(_day('s1', 1, location_logged=True))
	assert 'consent' in str(exc.value)


async def test_granting_consent_lets_a_location_be_logged_and_withdrawal_stops_it() -> None:
	svc = MonitoringService()
	svc.enrol('s1')
	household = svc.record_location_consent('s1', True, '2026-10-12T08:00:00+00:00')
	assert household.location_consent is True
	assert household.location_consent_at_iso == '2026-10-12T08:00:00+00:00'
	await svc.log_day(_day('s1', 1, location_logged=True))

	svc.record_location_consent('s1', False, '2026-10-13T08:00:00+00:00')
	assert svc._households['s1'].location_consent is False
	with pytest.raises(AssertionError):
		await svc.log_day(_day('s1', 2, location_logged=True))


def test_a_consent_decision_is_dated() -> None:
	"""An undated consent is indistinguishable from an assumed one, and a withdrawal from never
	having agreed."""
	svc = MonitoringService()
	svc.enrol('s1')
	with pytest.raises(AssertionError):
		svc.record_location_consent('s1', True, '')


def test_consent_for_an_unenrolled_subject_is_refused() -> None:
	svc = MonitoringService()
	with pytest.raises(AssertionError):
		svc.record_location_consent('ghost', True, '2026-10-12T08:00:00+00:00')


# --- household members in the same interface -------------------------------------------------

async def test_a_member_is_added_and_has_their_own_diary() -> None:
	svc = MonitoringService()
	svc.enrol('s1')
	svc.add_household_member('s1', 'M1')
	await svc.log_day(_day('s1', 1, 36.8))
	await svc.log_day(_day('s1', 1, 39.2, household_member='M1'))
	assert [e.day for e in svc.member_diary('s1', 'M1')] == [1]
	assert svc.member_diary('s1', 'M1')[0].temperature_c == 39.2


async def test_a_members_day_is_not_the_contacts_day() -> None:
	"""The canary's target: the predecessor read `household_member` nowhere, so a member's fever sat
	in the contact's own series and the contact's adherence counted it."""
	svc = MonitoringService()
	svc.enrol('s1')
	svc.add_household_member('s1', 'M1')
	await svc.log_day(_day('s1', 1, 39.2, household_member='M1'))
	assert svc.diary('s1') == [], "a member's reading is not the contact's"
	assert svc.adherence_reminder_days('s1') == list(range(1, MONITORING_DAYS + 1)), \
		'the contact has still logged nothing'
	assert svc.reminders('s1', 1).complete is False, \
		"a member's morning does not discharge the contact's"


async def test_a_member_who_is_not_in_the_household_is_refused() -> None:
	svc = MonitoringService()
	svc.enrol('s1')
	with pytest.raises(AssertionError):
		await svc.log_day(_day('s1', 1, household_member='STRANGER'))
	with pytest.raises(AssertionError):
		svc.member_diary('s1', 'STRANGER')


def test_a_household_member_cannot_be_the_contact_themselves() -> None:
	svc = MonitoringService()
	svc.enrol('s1')
	with pytest.raises(AssertionError):
		svc.add_household_member('s1', 's1')


def test_a_member_is_added_once_and_can_be_removed() -> None:
	svc = MonitoringService()
	svc.enrol('s1')
	svc.add_household_member('s1', 'M1')
	svc.add_household_member('s1', 'M1')
	assert svc._households['s1'].members == ['M1'], 'a double tap does not make two members'
	svc.remove_household_member('s1', 'M1')
	assert svc._households['s1'].members == []
	with pytest.raises(AssertionError):
		svc.remove_household_member('s1', 'M1')


async def test_the_escalation_message_names_who_the_reading_is_for() -> None:
	"""One household, one diary. "A fever was recorded" without saying for whom is a message the
	contact has to decode at the moment they are least able to."""
	svc = MonitoringService()
	svc.enrol('s1', officer='chw-1', officer_number='0722000111')
	svc.add_household_member('s1', 'M1')
	mine = await svc.log_day(_day('s1', 1, 39.0))
	theirs = await svc.log_day(_day('s1', 2, 39.0, household_member='M1'))
	assert 'for you' in mine.message
	assert 'for M1' in theirs.message
	assert theirs.escalate is True


# --- psychological support resources ---------------------------------------------------------

async def test_support_is_on_every_verdict_including_the_clear_ones() -> None:
	"""The day someone most needs the support is not always a flagged day."""
	svc = MonitoringService()
	svc.enrol('s1')
	clear = await svc.log_day(_day('s1', 1, 36.6))
	assert clear.escalate is False
	kinds = {r['kind'] for r in clear.support}
	assert 'crisis_line' in kinds
	assert 'coping' in kinds
	assert 'outbreak_support' in kinds


async def test_a_flagged_verdict_says_why_the_lines_are_there() -> None:
	svc = MonitoringService()
	svc.enrol('s1')
	flagged = await svc.log_day(_day('s1', 1, 39.4))
	assert flagged.escalate is True
	assert flagged.support[0]['kind'] == 'escalation_note', 'the note leads when the verdict is flagged'
	clear = support_resources(False)
	assert all(r['kind'] != 'escalation_note' for r in clear)


def test_the_counselling_numbers_are_read_from_the_one_place_they_live() -> None:
	"""A second copy of the numbers is a second set to keep current — and the copy that goes stale is
	the one nobody is looking at."""
	resources = [r for r in support_resources(False) if r['kind'] == 'crisis_line']
	assert len(resources) == len(COUNSELLING_LINES)
	for resource, line in zip(resources, COUNSELLING_LINES, strict=True):
		assert resource['number'] == line['number']
		assert resource['title'] == line['name']
		assert resource['route'] == f'tel:{line["number"]}'


# --- direct line to the assigned monitoring officer ------------------------------------------

def test_an_assigned_officer_with_a_number_is_dialable() -> None:
	svc = MonitoringService()
	svc.enrol('s1', officer='chw-1', officer_number='0722000111')
	line = svc.monitoring_officer_line('s1')
	assert line['assigned'] == 'True'
	assert line['officer'] == 'chw-1'
	assert line['line'] == 'tel:0722000111'


def test_an_officer_with_no_number_falls_back_to_a_line_that_is_answered() -> None:
	"""The predecessor's defect in this bullet was exactly a free-text name with no number. Serving
	that name as a `tel:` target is a dead button, so the fallback names the officer *and* gives a
	line that is staffed."""
	svc = MonitoringService()
	svc.enrol('s1', officer='chw-1')
	line = svc.monitoring_officer_line('s1')
	assert line['officer'] == 'chw-1'
	assert line['line'] == 'tel:719'
	assert '719' in line['message']


def test_no_officer_at_all_says_so_rather_than_serving_an_empty_line() -> None:
	svc = MonitoringService()
	svc.enrol('s1')
	line = svc.monitoring_officer_line('s1')
	assert line['assigned'] == 'False'
	assert line['line'] == 'tel:719'


def test_the_officer_line_refuses_an_unenrolled_subject() -> None:
	svc = MonitoringService()
	with pytest.raises(AssertionError):
		svc.monitoring_officer_line('ghost')


# --- over HTTP --------------------------------------------------------------------------------

async def test_the_whole_diary_round_trip_over_http(tmp_path) -> None:
	"""The routes end to end: enrol with a dialable officer, consent, add a member, log both, read
	the reminder state, the two diaries and the officer line."""
	app = create_app(build_services(db_path=str(tmp_path / 'afya.db')))
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers, subject = await _citizen(c)
		await c.post('/tier4/activation/request', params={'county': 'Busia'}, headers=headers)

		enrolled = await c.post('/monitoring/contact/enrol', headers=headers,
		                        params={'subject_ref': subject, 'officer': 'chw-1',
		                                'officer_number': '0722000111'})
		assert enrolled.status_code == 200, enrolled.text

		consent = await c.post(f'/monitoring/contact/{subject}/location-consent', headers=headers,
		                       json={'granted': True, 'at_iso': '2026-10-12T08:00:00+00:00'})
		assert consent.status_code == 200, consent.text
		assert consent.json()['location_consent'] is True

		member = await c.post(f'/monitoring/contact/{subject}/members', headers=headers,
		                      json={'member_ref': 'M1'})
		assert member.status_code == 200, member.text
		assert member.json()['members'] == ['M1']

		logged = await c.post('/monitoring/contact/day', headers=headers, json={
			'entry_id': 'MON-ABCD1234', 'subject_ref': subject, 'day': 1, 'temperature_c': 36.7,
			'slot': 'morning', 'location_logged': True})
		assert logged.status_code == 200, logged.text
		verdict = logged.json()
		assert verdict['escalate'] is False
		assert verdict['support'], 'the support travels on the clear verdict too'

		state = await c.get(f'/monitoring/contact/{subject}/reminders/1', headers=headers)
		assert state.status_code == 200, state.text
		assert state.json()['missing'] == ['evening']

		member_day = await c.post('/monitoring/contact/day', headers=headers, json={
			'entry_id': 'MON-ABCD1235', 'subject_ref': subject, 'day': 1, 'temperature_c': 38.9,
			'household_member': 'M1', 'slot': 'morning'})
		assert member_day.status_code == 200, member_day.text
		assert member_day.json()['escalate'] is True
		assert 'for M1' in member_day.json()['message']

		mine = await c.get(f'/monitoring/contact/{subject}/diary', headers=headers)
		assert [e['entry_id'] for e in mine.json()['entries']] == ['MON-ABCD1234'], \
			"the member's day is not in the contact's diary"

		theirs = await c.get(f'/monitoring/contact/{subject}/members/M1/diary', headers=headers)
		assert [e['entry_id'] for e in theirs.json()['entries']] == ['MON-ABCD1235']

		officer = await c.get(f'/monitoring/contact/{subject}/officer', headers=headers)
		assert officer.status_code == 200, officer.text
		assert officer.json()['line'] == 'tel:0722000111'


async def test_a_location_without_consent_is_refused_over_http(tmp_path) -> None:
	app = create_app(build_services(db_path=str(tmp_path / 'afya.db')))
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers, subject = await _citizen(c)
		await c.post('/tier4/activation/request', params={'county': 'Busia'}, headers=headers)
		await c.post('/monitoring/contact/enrol', headers=headers, params={'subject_ref': subject})
		resp = await c.post('/monitoring/contact/day', headers=headers, json={
			'entry_id': 'MON-ABCD1234', 'subject_ref': subject, 'day': 1, 'temperature_c': 36.7,
			'location_logged': True})
		assert resp.status_code == 422, resp.text
		assert 'consent' in resp.json()['detail']


async def test_the_new_routes_refuse_an_absent_token(tmp_path) -> None:
	app = create_app(build_services(db_path=str(tmp_path / 'afya.db')))
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		anon = [
			await c.get('/monitoring/contact/U1/reminders/1'),
			await c.post('/monitoring/contact/U1/location-consent',
			             json={'granted': True, 'at_iso': '2026-10-12T08:00:00+00:00'}),
			await c.post('/monitoring/contact/U1/members', json={'member_ref': 'M1'}),
			await c.delete('/monitoring/contact/U1/members/M1'),
			await c.get('/monitoring/contact/U1/members/M1/diary'),
			await c.get('/monitoring/contact/U1/officer'),
		]
		assert all(r.status_code == 401 for r in anon), \
			[(r.request.url.path, r.status_code) for r in anon]


async def test_a_token_cannot_reach_another_persons_household(tmp_path) -> None:
	"""The guard binds `subject_ref` to the token, so a household lives inside the diary of the person
	who owns it. Without it these routes would be an IDOR over somebody's contact-tracing record."""
	app = create_app(build_services(db_path=str(tmp_path / 'afya.db')))
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		u1, _ = await _citizen(c, 'U1')
		u2, _ = await _citizen(c, 'U2')
		await c.post('/tier4/activation/request', params={'county': 'Busia'}, headers=u1)
		await c.post('/monitoring/contact/enrol', headers=u1, params={'subject_ref': 'U1'})
		await c.post('/monitoring/contact/U1/members', json={'member_ref': 'M1'}, headers=u1)
		cross = [
			await c.get('/monitoring/contact/U1/reminders/1', headers=u2),
			await c.post('/monitoring/contact/U1/location-consent', headers=u2,
			             json={'granted': True, 'at_iso': '2026-10-12T08:00:00+00:00'}),
			await c.post('/monitoring/contact/U1/members', headers=u2, json={'member_ref': 'M2'}),
			await c.delete('/monitoring/contact/U1/members/M1', headers=u2),
			await c.get('/monitoring/contact/U1/members/M1/diary', headers=u2),
			await c.get('/monitoring/contact/U1/officer', headers=u2),
		]
		assert all(r.status_code == 403 for r in cross), \
			[(r.request.url.path, r.status_code) for r in cross]


async def test_no_feature_code_reaches_anything_a_person_reads(tmp_path) -> None:
	"""§3.3 principle 9: a spec id is an internal handle and must not reach the UI/UX."""
	app = create_app(build_services(db_path=str(tmp_path / 'afya.db')))
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers, subject = await _citizen(c)
		await c.post('/tier4/activation/request', params={'county': 'Busia'}, headers=headers)
		await c.post('/monitoring/contact/enrol', headers=headers,
		             params={'subject_ref': subject, 'officer': 'chw-1',
		                     'officer_number': '0722000111'})
		await c.post(f'/monitoring/contact/{subject}/members', headers=headers,
		             json={'member_ref': 'M1'})
		await c.post('/monitoring/contact/day', headers=headers, json={
			'entry_id': 'MON-ABCD1234', 'subject_ref': subject, 'day': 1, 'temperature_c': 39.2})
		bodies = [
			(await c.post('/monitoring/contact/day', headers=headers, json={
				'entry_id': 'MON-ABCD1235', 'subject_ref': subject, 'day': 2,
				'temperature_c': 36.7})).text,
			(await c.get(f'/monitoring/contact/{subject}/reminders/2', headers=headers)).text,
			(await c.get(f'/monitoring/contact/{subject}/diary', headers=headers)).text,
			(await c.get(f'/monitoring/contact/{subject}/officer', headers=headers)).text,
		]
		for body in bodies:
			assert not FEATURE_CODE.search(body), body
