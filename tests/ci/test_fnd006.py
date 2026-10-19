"""§FND-006 — appointment booking and queue management, five bullets end to end.

The section asks for five things and two of them were carried by a `book()` that took a time the
caller supplied and returned a queue position. The other three had nothing behind them, and the
shape of what was missing is worth stating because it is the reason this file is long:

* **"View available slots"** did not exist, so a client had no way to learn a time except from a
  person. A slot is a facility publishing a time it will see people — a claim, not a computation.
* **"reschedule, cancel"** did not exist, and *could not* have existed safely: `Booking` had no
  owner, so the only key to a booking was its six-character reference, and a cancel keyed on that
  is an IDOR with a delete key. The owner is therefore part of this unit rather than a separate
  one — the two verbs are unimplementable without it.
* **"Reminder notifications"** did not exist. It is derived from the slot rather than stored, on
  §ACC-004's reasoning: the server states when the reminder is due and the device holds it, which
  is the same shape as §MON-001's missed-dose alert.

The queue is the fifth and was already there. It is tested here anyway, because two of the four
new verbs move it and a queue that renumbers on a reschedule is the defect this unit most easily
introduces.
"""
import httpx
import pydantic
import pytest

from afya.facilities.service import FacilityService
from afya.facilities.views import (
	Booking, BookingRequest, Facility, FacilityKind, FacilitySlot, SlotOffer,
)
from afya.service import build_services, create_app


def _svc() -> FacilityService:
	svc = FacilityService()
	svc._facilities['F1'] = Facility(facility_id='F1', name='Busia Clinic',
		kind=FacilityKind.treatment_unit, county='Busia', lat=0.46, lon=34.11)
	return svc


# --- "View available slots at participating facilities" ------------------------------------------

async def test_a_published_slot_is_what_the_screen_reads() -> None:
	"""The first missing bullet: a facility says when it will see people, and how many."""
	svc = _svc()
	slot = await svc.publish_slot(SlotOffer(facility_id='F1', slot_iso='2026-10-20T09:00+03:00', capacity=8))
	assert (slot.capacity, slot.booked, slot.free) == (8, 0, 8)
	assert slot.open
	day = svc.slots('F1', '2026-10-20')
	assert [s.slot_iso for s in day.slots] == ['2026-10-20T09:00+03:00']
	assert day.open_count == 1


async def test_a_full_slot_stays_in_the_answer() -> None:
	"""A taken slot is served with no places left rather than dropped.

	A screen that showed only free times would tell a person nothing about whether the clinic is
	full this morning or closed — and "nothing available" is the answer they most need before they
	travel. This is the one place the list is *not* a filter, and it is deliberate.
	"""
	svc = _svc()
	await svc.publish_slot(SlotOffer(facility_id='F1', slot_iso='2026-10-20T09:00+03:00'))
	await svc.book('F1', '2026-10-20T09:00+03:00', 'BOOK-AAAA1111')
	day = svc.slots('F1', '2026-10-20')
	assert len(day.slots) == 1, 'a full slot was dropped from the day'
	assert day.slots[0].free == 0 and not day.slots[0].open
	assert day.open_count == 0


async def test_booking_a_full_slot_is_refused() -> None:
	"""Oversubscribing a slot sends a person to a clinic that cannot see them."""
	svc = _svc()
	await svc.publish_slot(SlotOffer(facility_id='F1', slot_iso='2026-10-20T09:00+03:00', capacity=1))
	await svc.book('F1', '2026-10-20T09:00+03:00', 'BOOK-AAAA1111')
	with pytest.raises(AssertionError, match='no places left'):
		await svc.book('F1', '2026-10-20T09:00+03:00', 'BOOK-BBBB2222')


async def test_a_facility_with_no_published_schedule_still_takes_a_booking() -> None:
	"""Most of the registry publishes no slots, and that is not the same answer as "that time is
	taken". A refusal here would make the whole feature depend on a facility having filed a
	schedule, which is the opposite of how a queue works."""
	svc = _svc()
	booking = await svc.book('F1', '2026-10-20T09:00+03:00', 'BOOK-AAAA1111')
	assert booking.queue_position == 1


async def test_re_publishing_a_slot_keeps_the_places_already_taken() -> None:
	"""The facility is saying "this time still exists, with this many places". Resetting the count
	would silently reopen places people hold."""
	svc = _svc()
	await svc.publish_slot(SlotOffer(facility_id='F1', slot_iso='2026-10-20T09:00+03:00', capacity=3))
	await svc.book('F1', '2026-10-20T09:00+03:00', 'BOOK-AAAA1111')
	again = await svc.publish_slot(SlotOffer(facility_id='F1', slot_iso='2026-10-20T09:00+03:00', capacity=3))
	assert again.booked == 1, 'a re-published slot forgot the booking it already had'
	assert again.free == 2


async def test_shrinking_a_slot_below_what_is_booked_is_refused() -> None:
	"""The facility has to cancel someone first, and that is a decision with a person at the end of
	it rather than a number the model may quietly clamp."""
	svc = _svc()
	await svc.publish_slot(SlotOffer(facility_id='F1', slot_iso='2026-10-20T09:00+03:00', capacity=4))
	await svc.book('F1', '2026-10-20T09:00+03:00', 'BOOK-AAAA1111')
	await svc.book('F1', '2026-10-20T09:00+03:00', 'BOOK-BBBB2222')
	with pytest.raises(pydantic.ValidationError, match='more places than it offers'):
		await svc.publish_slot(SlotOffer(facility_id='F1', slot_iso='2026-10-20T09:00+03:00', capacity=1))


async def test_a_slot_cannot_claim_more_booked_than_it_offers() -> None:
	"""The refusal above, at the model, so it holds wherever a slot is built and not only on the
	one route that publishes them."""
	with pytest.raises(pydantic.ValidationError, match='more places than it offers'):
		FacilitySlot(facility_id='F1', slot_iso='2026-10-20T09:00+03:00', capacity=2, booked=3)


async def test_a_schedule_carries_one_facility_and_one_day() -> None:
	"""Both, because the day is echoed back: a client that asked for Tuesday and received a bare
	list cannot tell an empty Tuesday from a request answered with another day's rows."""
	from afya.facilities.views import SlotSchedule
	with pytest.raises(pydantic.ValidationError, match="one facility's day"):
		SlotSchedule(facility_id='F1', day_iso='2026-10-20',
			slots=[FacilitySlot(facility_id='F2', slot_iso='2026-10-20T09:00+03:00')])
	with pytest.raises(pydantic.ValidationError, match='slots from another one'):
		SlotSchedule(facility_id='F1', day_iso='2026-10-20',
			slots=[FacilitySlot(facility_id='F1', slot_iso='2026-10-21T09:00+03:00')])


# --- "Book, reschedule, cancel" ------------------------------------------------------------------

async def test_a_reschedule_keeps_the_place_in_the_queue() -> None:
	"""The point of the verb. A person who booked in March and moves to April has not joined the
	back of a new line, and renumbering them punishes the one behaviour a clinic most wants."""
	svc = _svc()
	await svc.book('F1', '2026-10-20T09:00+03:00', 'BOOK-AAAA1111', 'U1')
	await svc.book('F1', '2026-10-20T09:30+03:00', 'BOOK-BBBB2222', 'U2')
	moved = await svc.reschedule('BOOK-AAAA1111', '2026-10-22T14:00+03:00')
	assert moved.slot_iso == '2026-10-22T14:00+03:00'
	# Read back through the service, not through `moved`/`first`: those are the *same object* the
	# mutation would have written to, so a self-comparison would hold whatever the code did.
	assert svc.booking('BOOK-AAAA1111').queue_position == 1, 'a reschedule renumbered the queue'
	assert svc.booking('BOOK-BBBB2222').queue_position == 2


async def test_a_reschedule_moves_the_place_between_slots() -> None:
	"""The old slot releases its place and the new one takes it, so a facility's booked count is
	never briefly wrong in the direction that oversells it."""
	svc = _svc()
	await svc.publish_slot(SlotOffer(facility_id='F1', slot_iso='2026-10-20T09:00+03:00'))
	await svc.publish_slot(SlotOffer(facility_id='F1', slot_iso='2026-10-22T14:00+03:00'))
	await svc.book('F1', '2026-10-20T09:00+03:00', 'BOOK-AAAA1111', 'U1')
	await svc.reschedule('BOOK-AAAA1111', '2026-10-22T14:00+03:00')
	assert svc.slots('F1', '2026-10-20').slots[0].free == 1, 'the old slot kept a place nobody holds'
	assert svc.slots('F1', '2026-10-22').slots[0].free == 0, 'the new slot did not take the place'


async def test_a_reschedule_into_a_full_slot_is_refused() -> None:
	svc = _svc()
	await svc.publish_slot(SlotOffer(facility_id='F1', slot_iso='2026-10-22T14:00+03:00', capacity=1))
	await svc.book('F1', '2026-10-22T14:00+03:00', 'BOOK-BBBB2222', 'U2')
	await svc.book('F1', '2026-10-20T09:00+03:00', 'BOOK-AAAA1111', 'U1')
	with pytest.raises(AssertionError, match='no places left'):
		await svc.reschedule('BOOK-AAAA1111', '2026-10-22T14:00+03:00')


async def test_a_cancel_releases_the_place_and_keeps_the_row() -> None:
	"""A state rather than a deletion, because the queue behind it was numbered against this row.
	Removing it would renumber people who did nothing."""
	svc = _svc()
	await svc.publish_slot(SlotOffer(facility_id='F1', slot_iso='2026-10-20T09:00+03:00'))
	await svc.book('F1', '2026-10-20T09:00+03:00', 'BOOK-AAAA1111', 'U1')
	await svc.book('F1', '2026-10-20T09:30+03:00', 'BOOK-BBBB2222', 'U2')
	cancelled = await svc.cancel('BOOK-AAAA1111')
	assert cancelled.cancelled
	assert svc.booking('BOOK-AAAA1111') is cancelled, 'the row was removed rather than marked'
	assert svc.booking('BOOK-BBBB2222').queue_position == 2
	assert svc.slots('F1', '2026-10-20').slots[0].free == 1


async def test_cancelling_twice_is_refused() -> None:
	"""The second cancel would release a place that is already free, and the count is what a
	facility reads."""
	svc = _svc()
	await svc.publish_slot(SlotOffer(facility_id='F1', slot_iso='2026-10-20T09:00+03:00'))
	await svc.book('F1', '2026-10-20T09:00+03:00', 'BOOK-AAAA1111', 'U1')
	await svc.cancel('BOOK-AAAA1111')
	with pytest.raises(AssertionError, match='already cancelled'):
		await svc.cancel('BOOK-AAAA1111')


async def test_a_cancelled_booking_cannot_be_moved() -> None:
	"""Moving it would take a place in a slot for an appointment that is not happening."""
	svc = _svc()
	await svc.book('F1', '2026-10-20T09:00+03:00', 'BOOK-AAAA1111', 'U1')
	await svc.cancel('BOOK-AAAA1111')
	with pytest.raises(AssertionError, match='was cancelled'):
		await svc.reschedule('BOOK-AAAA1111', '2026-10-22T14:00+03:00')


async def test_a_booking_belongs_to_whoever_filed_it() -> None:
	"""The relation the two verbs rest on, in one place.

	`owns` is the only implementation of it: a second copy in a route would be a second rule, and
	the one that drifts is the one an attacker reads.
	"""
	svc = _svc()
	await svc.book('F1', '2026-10-20T09:00+03:00', 'BOOK-AAAA1111', 'U1')
	assert svc.owns('BOOK-AAAA1111', 'U1')
	assert not svc.owns('BOOK-AAAA1111', 'U2')
	assert not svc.owns('BOOK-AAAA1111', None), 'no subject owns nothing'
	assert not svc.owns('BOOK-NOSUCH01', 'U1'), 'an unknown booking is not owned'


async def test_a_booking_with_no_owner_belongs_to_nobody() -> None:
	"""The deliberate half of the rule, and the one that is easy to get backwards.

	A booking filed without a token cannot be shown to belong to whoever presents its reference.
	Treating an unowned row as anyone's would make the six-character id a key to every anonymous
	booking in the system — which is exactly the IDOR the owner field exists to close. The cost is
	real and named: an anonymous booking can be neither moved nor cancelled, and the person has to
	book again.
	"""
	svc = _svc()
	await svc.book('F1', '2026-10-20T09:00+03:00', 'BOOK-AAAA1111')
	assert svc.booking('BOOK-AAAA1111').subject_ref is None
	assert not svc.owns('BOOK-AAAA1111', 'U1')
	assert not svc.owns('BOOK-AAAA1111', None)


async def test_the_queue_still_numbers_from_one_and_never_goes_backwards() -> None:
	"""§FND-006's third bullet, kept whole. Two of the four new verbs touch the queue, so the
	property is re-asserted here rather than assumed from `test_facilities.py`."""
	svc = _svc()
	positions = []
	for i in range(5):
		b = await svc.book('F1', f'2026-10-20T09:{i * 10:02d}+03:00', f'BOOK-AAAA{i:04d}', f'U{i}')
		positions.append(b.queue_position)
	assert positions == [1, 2, 3, 4, 5]
	await svc.cancel('BOOK-AAAA0002')
	after = await svc.book('F1', '2026-10-20T10:00+03:00', 'BOOK-CCCC3333', 'U9')
	assert after.queue_position == 6, 'a cancellation renumbered the queue'


# --- "Reminder notifications" --------------------------------------------------------------------

async def test_the_reminder_is_derived_from_the_slot() -> None:
	"""§FND-006's fifth bullet, as data the device schedules.

	The server states *when* the reminder is due and the device holds it, on §ACC-004's reasoning —
	the same shape as §MON-001's missed-dose alert. A stored reminder would be a second copy of the
	appointment time, and the copy that drifts is the one already in somebody's phone.
	"""
	booking = Booking(facility_id='F1', slot_iso='2026-10-20T09:00+03:00', queue_position=1)
	assert booking.reminder_due_iso.startswith('2026-10-19T09:00'), booking.reminder_due_iso


async def test_a_reschedule_moves_the_reminder_with_it() -> None:
	"""The property that makes deriving it worth doing: there is no reminder left pointing at the
	old time, because there is no stored reminder."""
	svc = _svc()
	b = await svc.book('F1', '2026-10-20T09:00+03:00', 'BOOK-AAAA1111', 'U1')
	before = b.reminder_due_iso
	await svc.reschedule('BOOK-AAAA1111', '2026-10-22T14:00+03:00')
	after = svc.booking('BOOK-AAAA1111').reminder_due_iso
	assert before.startswith('2026-10-19') and after.startswith('2026-10-21'), (before, after)


async def test_a_cancelled_booking_carries_no_reminder() -> None:
	"""A notification for an appointment the person has released is worse than none: it sends them
	to a clinic for nothing. The empty string rather than a date, because a client that scheduled a
	notification for `None` would still fire it."""
	svc = _svc()
	await svc.book('F1', '2026-10-20T09:00+03:00', 'BOOK-AAAA1111', 'U1')
	await svc.cancel('BOOK-AAAA1111')
	assert svc.booking('BOOK-AAAA1111').reminder_due_iso == ''


async def test_the_reminder_is_a_computed_field_and_survives_a_round_trip() -> None:
	"""§3.3 principle 10's reasoning and `DerivedFields`' one, on this model: the field is served,
	so a client reading a booking back into `BookingRequest`-shaped code must not be refused for
	echoing it. `Booking` is not a request body, so nothing posts it — but the property is asserted
	rather than assumed, because a booking is exactly what a client caches and replays."""
	assert set(Booking.model_computed_fields) == {'reminder_due_iso'}
	dumped = Booking(facility_id='F1', slot_iso='2026-10-20T09:00+03:00', queue_position=1).model_dump(mode='json')
	assert 'reminder_due_iso' in dumped
	# A time nobody can parse yields no reminder rather than a wrong one or an exception: a booking
	# is a record of a real appointment and a model that raised here would take the record down.
	assert Booking(facility_id='F1', slot_iso='sometime tuesday', queue_position=1).reminder_due_iso == ''


# --- over HTTP: the routes, their guards and the ownership rule ----------------------------------

async def _anon(c: httpx.AsyncClient, subject: str = 'U1') -> str:
	return str((await c.post('/auth/anonymous', json={'subject_ref': subject})).json()['token'])


async def _county_officer(c: httpx.AsyncClient) -> str:
	from afya.auth.views import s256
	verifier = 'v' * 64
	authz = (await c.post('/auth/pkce/authorize', json={
		'client_id': 'app', 'redirect_uri': 'afya://cb', 'code_challenge': s256(verifier), 'state': 'state-1234', 'role': 'county_officer',
	})).json()
	return str((await c.post('/auth/pkce/token', params={'role': 'county_officer'}, json={
		'authorization_code': authz['authorization_code'], 'client_id': 'app',
		'redirect_uri': 'afya://cb', 'code_verifier': verifier,
	})).json()['access_token'])


async def test_the_slot_screen_is_public_and_publishing_is_not() -> None:
	"""A person choosing a clinic has not decided to tell anyone who they are; a facility saying it
	will see people is the county health team's claim, the same scope as its registry row."""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		officer = {'authorization': f'Bearer {await _county_officer(c)}'}
		await c.post('/facilities', headers=officer, json={
			'facility_id': 'F1', 'name': 'Busia Clinic', 'kind': 'treatment_unit',
			'county': 'Busia', 'lat': 0.46, 'lon': 34.11})
		body = {'slot_iso': '2026-10-20T09:00+03:00', 'capacity': 4}
		assert (await c.post('/facilities/F1/slots', json=body)).status_code in (401, 403), 'published anonymously'
		anon = {'authorization': f'Bearer {await _anon(c)}'}
		assert (await c.post('/facilities/F1/slots', headers=anon, json=body)).status_code == 403
		assert (await c.post('/facilities/F1/slots', headers=officer, json=body)).status_code == 200
		# The read needs no token at all, and carries the day it was asked about.
		day = (await c.get('/facilities/F1/slots', params={'day_iso': '2026-10-20'})).json()
		assert day['day_iso'] == '2026-10-20' and len(day['slots']) == 1
		assert day['slots'][0]['free'] == 4


async def test_the_path_and_the_body_must_name_the_same_facility() -> None:
	"""A slot filed under one clinic and read from another is a time nobody can find."""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		officer = {'authorization': f'Bearer {await _county_officer(c)}'}
		await c.post('/facilities', headers=officer, json={
			'facility_id': 'F1', 'name': 'A', 'kind': 'treatment_unit', 'county': 'Busia', 'lat': 0.46, 'lon': 34.11})
		await c.post('/facilities', headers=officer, json={
			'facility_id': 'F2', 'name': 'B', 'kind': 'treatment_unit', 'county': 'Busia', 'lat': 0.47, 'lon': 34.12})
		out = await c.post('/facilities/F1/slots', headers=officer, json={
			'facility_id': 'F2', 'slot_iso': '2026-10-20T09:00+03:00'})
		assert out.status_code == 422 and 'F2' in out.json()['detail']


async def test_a_citizen_books_moves_and_cancels_their_own_appointment() -> None:
	"""The three verbs, end to end, on a token — which is the whole shape of §FND-006."""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		officer = {'authorization': f'Bearer {await _county_officer(c)}'}
		await c.post('/facilities', headers=officer, json={
			'facility_id': 'F1', 'name': 'A', 'kind': 'treatment_unit', 'county': 'Busia', 'lat': 0.46, 'lon': 34.11})
		await c.post('/facilities/F1/slots', headers=officer, json={'slot_iso': '2026-10-20T09:00+03:00', 'capacity': 2})
		me = {'authorization': f'Bearer {await _anon(c, "U1")}'}
		booked = (await c.post('/facilities/F1/booking', headers=me,
			json={'slot_iso': '2026-10-20T09:00+03:00'})).json()
		assert booked['subject_ref'] == 'U1', 'the owner is the token, not a body field'
		assert booked['queue_position'] == 1 and booked['reminder_due_iso'].startswith('2026-10-19')
		moved = (await c.post(f'/facilities/booking/{booked["booking_id"]}/reschedule', headers=me,
			json={'slot_iso': '2026-10-22T14:00+03:00'})).json()
		assert moved['slot_iso'] == '2026-10-22T14:00+03:00' and moved['queue_position'] == 1
		assert moved['reminder_due_iso'].startswith('2026-10-21')
		done = (await c.post(f'/facilities/booking/{booked["booking_id"]}/cancel', headers=me)).json()
		assert done['cancelled'] and done['reminder_due_iso'] == ''


async def test_another_person_cannot_move_or_cancel_your_appointment() -> None:
	"""The IDOR this unit exists to close. The booking id is six characters off a screen, so
	guessing one must not be enough to take somebody's place at a clinic."""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		officer = {'authorization': f'Bearer {await _county_officer(c)}'}
		await c.post('/facilities', headers=officer, json={
			'facility_id': 'F1', 'name': 'A', 'kind': 'treatment_unit', 'county': 'Busia', 'lat': 0.46, 'lon': 34.11})
		mine = {'authorization': f'Bearer {await _anon(c, "U1")}'}
		theirs = {'authorization': f'Bearer {await _anon(c, "U2")}'}
		booked = (await c.post('/facilities/F1/booking', headers=mine,
			json={'slot_iso': '2026-10-20T09:00+03:00'})).json()
		path = f'/facilities/booking/{booked["booking_id"]}'
		assert (await c.post(f'{path}/reschedule', headers=theirs,
			json={'slot_iso': '2026-10-22T14:00+03:00'})).status_code == 403
		assert (await c.post(f'{path}/cancel', headers=theirs)).status_code == 403
		# And it really is untouched: a refusal that still wrote would be the same defect with a
		# nicer status code.
		assert (await c.post(f'{path}/cancel', headers=mine)).json()['cancelled'] is True
		assert (await c.post(f'{path}/reschedule', headers=mine,
			json={'slot_iso': '2026-10-22T14:00+03:00'})).status_code == 409


async def test_an_anonymous_booking_cannot_be_moved_or_cancelled_at_all() -> None:
	"""The cost of the rule, asserted rather than left to be discovered: a booking filed with no
	token has no owner, so presenting its reference is not enough — for anybody, including the
	person who made it. 403 rather than 404, because the caller named something that exists."""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		officer = {'authorization': f'Bearer {await _county_officer(c)}'}
		await c.post('/facilities', headers=officer, json={
			'facility_id': 'F1', 'name': 'A', 'kind': 'treatment_unit', 'county': 'Busia', 'lat': 0.46, 'lon': 34.11})
		booked = (await c.post('/facilities/F1/booking',
			json={'slot_iso': '2026-10-20T09:00+03:00'})).json()
		assert booked['subject_ref'] is None
		path = f'/facilities/booking/{booked["booking_id"]}'
		me = {'authorization': f'Bearer {await _anon(c, "U1")}'}
		assert (await c.post(f'{path}/cancel', headers=me)).status_code == 403
		assert (await c.post(f'{path}/cancel')).status_code == 403


async def test_an_unknown_booking_answers_exactly_as_someone_elses_does() -> None:
	"""A guess must not be distinguishable from a near miss.

	Answering 404 for a reference that names nothing and 403 for one that exists but is not the
	caller's turns this route into an oracle: six characters is a search space a script walks in
	minutes, and the 404 tells it which of its guesses named a real appointment. Both cases get the
	same 403 for that reason, and the *only* place a booking's existence is admitted is a route the
	owner has already passed.
	"""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		officer = {'authorization': f'Bearer {await _county_officer(c)}'}
		await c.post('/facilities', headers=officer, json={
			'facility_id': 'F1', 'name': 'A', 'kind': 'treatment_unit', 'county': 'Busia', 'lat': 0.46, 'lon': 34.11})
		real = (await c.post('/facilities/F1/booking', json={'slot_iso': '2026-10-20T09:00+03:00'})).json()
		me = {'authorization': f'Bearer {await _anon(c, "U1")}'}
		unknown = await c.post('/facilities/booking/BOOK-NOSUCH01/cancel', headers=me)
		not_mine = await c.post(f'/facilities/booking/{real["booking_id"]}/cancel', headers=me)
		assert unknown.status_code == not_mine.status_code == 403
		assert unknown.json()['detail'] == not_mine.json()['detail'], (
			'the two answers differ, so a caller can tell which references name a real appointment'
		)


async def test_the_service_refuses_an_unknown_booking_rather_than_inventing_one() -> None:
	"""The guard under the route. `owns` already refuses an unknown id, so this is the second line —
	and it is asserted directly because a caller reaching the service without the route (the gRPC
	surface, a test, an offline replay) must not get a booking minted out of nothing."""
	svc = _svc()
	with pytest.raises(AssertionError, match='unknown booking'):
		await svc.reschedule('BOOK-NOSUCH01', '2026-10-22T14:00+03:00')
	with pytest.raises(AssertionError, match='unknown booking'):
		await svc.cancel('BOOK-NOSUCH01')


async def test_an_unknown_facility_is_refused_before_a_booking_is_written() -> None:
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		out = await c.post('/facilities/NOPE/booking', json={'slot_iso': '2026-10-20T09:00+03:00'})
		assert out.status_code == 404


async def test_the_booking_form_can_fill_its_own_route() -> None:
	"""`BookingRequest`'s required fields, against the catalogue's field list.

	`subject_ref` is deliberately *not* on the form: the owner is the token's, and a form offering
	to type one would be offering a control the route ignores. `test_every_action_can_fill_the_body
	_its_route_requires` covers the general case; this pins the one this unit changed.
	"""
	from afya.mobile.actions import catalogue
	act = next(a for a in catalogue() if a.id == 'book_appointment')
	offered = {f.name for f in act.fields}
	assert {'slot_iso'} <= offered
	assert 'subject_ref' not in offered, 'the owner comes from the token; a form must not offer one'
	assert set(BookingRequest(facility_id='F1', slot_iso='x').model_dump()) >= {'booking_id', 'slot_iso'}
