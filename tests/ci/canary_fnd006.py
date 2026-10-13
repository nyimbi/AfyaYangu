"""Canaries for tests/ci/test_fnd006.py.

§FND-006's three missing bullets are each a shape that renders as working code, which is why each
is canaried rather than argued:

* **"View available slots"** was missing because nothing carried one. The cheap fix is a list of
  times the client invents, which passes any test that reads the payload — so canary #1 makes the
  booking ignore the published slot entirely, which is the defect of a schedule that is *served*
  and never *consulted*. #2 is the same one level down: a full slot silently dropped from the day,
  which reads on a screen as "the clinic is closed".
* **"reschedule, cancel"** could not exist because a booking had no owner. Canary #4 removes the
  ownership check, which is the IDOR the whole unit turns on — and it is the one that matters most,
  because the booking id is six characters a person reads off a screen. #5 makes an unowned booking
  anyone's, which is the same hole reached through the one booking that has no token behind it.
* **"Reminder notifications"** did not exist. Canary #7 stops the reminder moving with a
  reschedule, which is what a *stored* reminder would do and the reason this one is derived.

The canaries worth reading as a set are #3, #4 and #8. #3 renumbers the queue on a reschedule,
which punishes the one behaviour a clinic wants. #4 is the IDOR. #8 lets a cancelled booking keep
its reminder, which sends a person to a clinic for an appointment they released.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script. The `__pycache__`
purge after each write is load-bearing for the reason `canary_inf001.py` documents: two canaries
mutating two methods with same-length edits in the same second make CPython reuse the previous
canary's bytecode, and the gate then reports a mutation it never made.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
V = ROOT / 'src/afya/facilities/views.py'
S = ROOT / 'src/afya/facilities/service.py'
G = ROOT / 'src/afya/service.py'

CANARIES = [
	# 1. Booking stops consulting the published schedule, so a facility's slots are served and never
	#    enforced: every time is bookable, and the screen that said "full" is a decoration.
	('a booking ignores the published slot', S,
	 "		offered = self._slots.get((facility_id, slot_iso))\n		if offered is not None:\n			assert offered.open, f'{slot_iso} at {facility_id} has no places left'\n			offered.booked += 1",
	 "		offered = None",
	 'test_booking_a_full_slot_is_refused'),

	# 2. A full slot is dropped from the day instead of served with no places left, so a clinic that
	#    is full this morning looks like a clinic with no morning at all.
	('a full slot is dropped from the day', S,
	 "		rows = [s for (f, iso), s in self._slots.items() if f == facility_id and iso.startswith(day_iso)]",
	 "		rows = [s for (f, iso), s in self._slots.items() if f == facility_id and iso.startswith(day_iso) and s.open]",
	 'test_a_full_slot_stays_in_the_answer'),

	# 3. A reschedule takes a new queue position, so moving an appointment to a later date puts the
	#    person at the back of a line they were already in — punishing the one behaviour a clinic
	#    most wants, which is being told in advance.
	('a reschedule renumbers the queue', S,
	 "		booking.slot_iso = slot_iso\n		self._log_info('booking rescheduled', booking=booking_id, slot=slot_iso)",
	 "		self._queue_counts[booking.facility_id] = self._queue_counts.get(booking.facility_id, 0) + 1\n		booking.queue_position = self._queue_counts[booking.facility_id]\n		booking.slot_iso = slot_iso\n		self._log_info('booking rescheduled', booking=booking_id, slot=slot_iso)",
	 'test_a_reschedule_keeps_the_place_in_the_queue'),

	# 4. The ownership check goes, and the six-character booking id becomes a key to anybody's
	#    appointment: guess one off a screen and take their place at a clinic.
	('the reschedule loses its ownership check', G,
	 "		if not facilities.owns(booking_id, subject):\n			raise HTTPException(status_code=403, detail='this appointment belongs to someone else')\n		try:\n			return await facilities.reschedule(booking_id, change.slot_iso)",
	 "		try:\n			return await facilities.reschedule(booking_id, change.slot_iso)",
	 'test_another_person_cannot_move_or_cancel_your_appointment'),

	# 5. The same hole through the one booking with no token behind it: an unowned row treated as
	#    anyone's, which is exactly the reading `owns` exists to refuse.
	('an unowned booking becomes anyone\'s', S,
	 "		if subject_ref is None or booking_id not in self._bookings:\n			return False\n		return self._bookings[booking_id].subject_ref == subject_ref",
	 "		if subject_ref is None or booking_id not in self._bookings:\n			return False\n		return self._bookings[booking_id].subject_ref in (None, subject_ref)",
	 'test_a_booking_with_no_owner_belongs_to_nobody'),

	# 6. A cancel deletes the row instead of marking it, so the queue behind it renumbers and the
	#    person who did nothing loses their place. This is the defect `Booking.cancelled` documents.
	('a cancel deletes the row', S,
	 "		booking.cancelled = True\n		held = self._slots.get((booking.facility_id, booking.slot_iso))",
	 "		del self._bookings[booking_id]\n		held = None",
	 'test_a_cancel_releases_the_place_and_keeps_the_row'),

	# 7. The reminder stops following the slot and becomes the fixed instant a *stored* reminder
	#    would be: the appointment moves and the notification still fires for the old time. The
	#    mutation is a constant rather than a shifted offset so it survives the first assertion in
	#    the file and is caught only where the derivation is the point — which is the reschedule.
	('the reminder stops following the slot', V,
	 "		return (at - timedelta(hours=REMINDER_LEAD_HOURS)).isoformat()",
	 "		return '2026-10-19T09:00:00+03:00'",
	 'test_a_reschedule_moves_the_reminder_with_it'),

	# 8. A cancelled booking keeps a reminder, so a person is notified to travel to a clinic for an
	#    appointment they have already given up.
	('a cancelled booking keeps its reminder', V,
	 "		if self.cancelled:\n			return ''",
	 "		if False:\n			return ''",
	 'test_a_cancelled_booking_carries_no_reminder'),

	# 9. A reschedule into a full slot is accepted, so two people hold the last place and one of them
	#    travels for nothing.
	('a reschedule may oversubscribe a slot', S,
	 "			if wanted is not None:\n				assert wanted.open, f'{slot_iso} at {booking.facility_id} has no places left'\n				wanted.booked += 1",
	 "			if wanted is not None:\n				wanted.booked += 1",
	 'test_a_reschedule_into_a_full_slot_is_refused'),

	# 10. A reschedule stops releasing the old slot's place, so a facility counts a seat for a person
	#     who has moved to another day.
	('a reschedule leaks the old slot', S,
	 "			if held is not None:\n				held.booked = max(0, held.booked - 1)\n			wanted = self._slots.get((booking.facility_id, slot_iso))",
	 "			wanted = self._slots.get((booking.facility_id, slot_iso))",
	 'test_a_reschedule_moves_the_place_between_slots'),

	# 11. Publishing a slot stops carrying the count forward, so re-publishing a time reopens places
	#     that people already hold.
	('re-publishing forgets the bookings', S,
	 "		booked = existing.booked if existing is not None else 0",
	 "		booked = 0",
	 'test_re_publishing_a_slot_keeps_the_places_already_taken'),

	# 12. The path/body facility agreement goes, so a slot is published under one clinic and read
	#     from another — a time nobody can find, with both screens looking right alone.
	('the slot route stops checking the facility agrees', G,
	 "		if offer.facility_id is not None and offer.facility_id != facility_id:\n			raise HTTPException(status_code=422,\n				detail=f'body names facility {offer.facility_id!r}, path names {facility_id!r}')",
	 "		pass",
	 'test_the_path_and_the_body_must_name_the_same_facility'),

	# 13. The publish route loses its guard, so anyone can put appointment times on a public screen —
	#     and a person travels to a clinic that never offered the slot.
	('publishing a slot loses its guard', G,
	 "	async def facility_publish_slot(facility_id: str, offer: SlotOffer,\n			_subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, object]:",
	 "	async def facility_publish_slot(facility_id: str, offer: SlotOffer) -> dict[str, object]:",
	 'test_the_slot_screen_is_public_and_publishing_is_not'),

	# 14. The owner stops being taken from the token, so the field a client may set decides whose
	#     appointment this is — and the ownership check becomes a check the caller performs.
	('the owner comes from the caller', G,
	 "			return await facilities.book(facility_id, booking.slot_iso, booking.booking_id, subject)",
	 "			return await facilities.book(facility_id, booking.slot_iso, booking.booking_id, 'U-SOMEONE-ELSE')",
	 'test_a_citizen_books_moves_and_cancels_their_own_appointment'),

	# 15. The slot model stops refusing more booked than offered, so a facility can publish a full
	#     slot with places left in it and the screen offers a time that does not exist.
	('a slot may claim more booked than it offers', V,
	 "		assert self.booked <= self.capacity, (",
	 "		assert True or self.booked <= self.capacity, (",
	 'test_a_slot_cannot_claim_more_booked_than_it_offers'),

	# 16. A schedule stops agreeing with its own day, so a client that asked for Tuesday is served
	#     Monday's rows and cannot tell an empty day from the wrong one.
	('a schedule may carry another day', V,
	 "		assert all(s.slot_iso.startswith(self.day_iso) for s in self.slots), (",
	 "		assert True or all(s.slot_iso.startswith(self.day_iso) for s in self.slots), (",
	 'test_a_schedule_carries_one_facility_and_one_day'),

	# 17. A cancelled booking may be moved, so a place in a slot is taken for an appointment that is
	#     not happening.
	('a cancelled booking may be moved', S,
	 "		assert not booking.cancelled, f'{booking_id} was cancelled; book a new appointment'",
	 "		assert True or not booking.cancelled, f'{booking_id} was cancelled; book a new appointment'",
	 'test_a_cancelled_booking_cannot_be_moved'),

	# 18. The service mints a booking for a reference that names nothing instead of refusing it, so
	#     the second line under the route is gone. The route's `owns` refuses an unknown id, but the
	#     gRPC surface, an offline replay and a test all reach the service without passing it, and
	#     each would get an appointment invented out of six guessed characters.
	('an unknown booking is invented', S,
	 "		assert booking_id in self._bookings, f'unknown booking {booking_id}'",
	 "		return self._bookings.setdefault(booking_id, Booking(booking_id=booking_id, facility_id='F1', slot_iso='2026-10-20T09:00+03:00', queue_position=1))",
	 'test_the_service_refuses_an_unknown_booking_rather_than_inventing_one'),
]
failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_fnd006.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	# See the module docstring: a same-second write of the same size reuses the previous canary's
	# bytecode, and the canary then tests code it never mutated. Purged for the file just written.
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly',
			f'tests/ci/test_fnd006.py::{node}'], cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
	print(f'{"CAUGHT " if caught else "MISSED "} {name}')
	if not caught:
		failures.append(name)
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
