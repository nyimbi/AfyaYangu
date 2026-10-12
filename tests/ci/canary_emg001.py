"""Canaries for tests/ci/test_emg001.py — each gate pointed at a planted defect and watched to fail.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
V = ROOT / 'src/afya/emergency/views.py'
S = ROOT / 'src/afya/emergency/service.py'

CANARIES = [
	# 1. The contacts leg disappears: the fan-out stops reaching anyone. This is the section's own
	#    bullet, and the gate that reads `contacts_notified` must see the empty list.
	('the contacts leg is dropped', S,
	 "\t\tif not event.contacts:\n\t\t\treturn [], [], 0",
	 "\t\tif True:\n\t\t\treturn [], [], 0",
	 'test_the_alert_reaches_the_contacts_the_section_names'),

	# 2. The cap is raised: a fourth contact is accepted and silently dropped by the SMS loop. The
	#    section says "up to three", and the gate asserts the fourth is refused.
	('the three-contact cap is raised', V,
	 "contacts: list[EmergencyContact] = Field(default=[], max_length=3)",
	 "contacts: list[EmergencyContact] = Field(default=[], max_length=10)",
	 'test_the_contacts_cap_is_three_and_a_fourth_is_refused_not_dropped'),

	# 3. The reachability test is loosened to "any Kenyan number": a landline is counted as
	#    delivered, which is the "3 contacts" for two deliveries failure.
	('the SMS reachability test accepts landlines', S,
	 r"_KE_MOBILE = re.compile(r'^\+254[17]\d{8}$')",
	 r"_KE_MOBILE = re.compile(r'^\+254\d{9}$')",
	 'test_a_number_that_cannot_receive_an_sms_is_reported_not_counted'),

	# 3b. And the same for the local spelling, so the unit gate on `_sms_dialable` fires too.
	('the local spelling accepts a landline', S,
	 r"_KE_LOCAL = re.compile(r'^0([17]\d{8})$')",
	 r"_KE_LOCAL = re.compile(r'^0(\d{9})$')",
	 'test_the_local_spelling_is_dialled_in_the_form_a_gateway_takes'),

	# 4. A non-GSM7 character enters the message — the em dash a person writing "someone — hurt"
	#    would use. Zero-rating and segmentation both turn on GSM7, so this is a message the
	#    gateway refuses on the one route that must not fail.
	('a non-GSM7 character enters the preset message', S,
	 "bits = ['AFYA SOS: someone needs help.', f'Where: {event.lat},{event.lon}', link]",
	 "bits = ['AFYA SOS: someone needs help \\u2014 now.', f'Where: {event.lat},{event.lon}', link]",
	 'test_the_preset_message_is_gsm7_so_it_can_be_zero_rated_and_segmented'),

	# 5. The ambulance leg stops reading the registry and returns a base for any call — the
	#    "where integrated" clause ignored.
	('the ambulance leg invents a dispatch', S,
	 "\t\tif self._ambulance is None:\n\t\t\treturn None",
	 "\t\tif self._ambulance is None:\n\t\t\treturn 'ambulance:nearest'",
	 'test_a_registry_with_no_ambulance_reports_the_leg_absent_rather_than_inventing_one'),

	# 6. The countdown deadline stops travelling: the client has nothing to count to and the
	#    server's window is unenforceable.
	('the cancel deadline stops being computed', S,
	 "armed_at_ms=now, cancel_deadline_ms=now + self._countdown_s * 1000, event=event,",
	 "armed_at_ms=now, cancel_deadline_ms=now, event=event,",
	 'test_the_countdown_is_a_window_the_server_owns_and_the_deadline_travels'),

	# 7. A cancel stops stopping the alert: the guard is removed and a cancelled alert fires
	#    anyway, which is worse than no cancel at all.
	('a cancel no longer stops the alert', S,
	 "\t\tassert not alert.cancelled, 'this alert was cancelled before it went out'",
	 "\t\tpass",
	 'test_cancelling_before_the_deadline_stops_the_alert_going_out'),

	# 8. A late cancel is accepted: the person is told nobody was alerted while the alert is with
	#    their contacts.
	('a late cancel is accepted', S,
	 "\t\tassert now <= alert.cancel_deadline_ms, 'the countdown has closed'",
	 "\t\tpass",
	 'test_a_cancel_after_the_deadline_is_refused'),

	# 9. The replay guard goes: firing twice sends twice, texting the same three people again for
	#    one emergency.
	('firing twice sends twice', S,
	 "\t\tif alert.fired:\n\t\t\treturn self._fired[sos_id]",
	 "\t\tif False:\n\t\t\treturn self._fired[sos_id]",
	 'test_firing_twice_sends_once'),

	# 10. The profile is always attached, so an empty one reads as "attached and blank".
	('an empty profile is attached rather than omitted', S,
	 "profile=None if profile.is_empty() else profile, actions=actions,",
	 "profile=profile, actions=actions,",
	 'test_the_profile_is_attached_when_given_and_absent_when_not'),

	# 11. The state route stops reporting the dispatch, so a person cannot see whether their alert
	#     went out.
	('the state route hides the dispatch', ROOT / 'src/afya/service.py',
	 "\t\tbody['dispatch'] = fired.model_dump(mode='json') if fired else None",
	 "\t\tbody['dispatch'] = None",
	 'test_the_routes_serve_the_fan_out_the_countdown_and_the_state'),

	# 12. A cancelled alert is handed a receipt instead of a conflict: the client believes an
	#     alert went out that never did. Anchored on `emergency.fire(` so the patch lands on the
	#     *fire* route — patching the cancel route's identical except-block leaves this test green
	#     and is how this canary passed the first time it was run.
	('a cancelled alert is handed a receipt', ROOT / 'src/afya/service.py',
	 "\t\ttry:\n\t\t\treturn (await emergency.fire(sos_id)).model_dump(mode='json')\n\t\texcept AssertionError as exc:\n\t\t\traise HTTPException(status_code=409, detail=str(exc)) from exc",
	 "\t\ttry:\n\t\t\treturn (await emergency.fire(sos_id)).model_dump(mode='json')\n\t\texcept AssertionError as exc:\n\t\t\traise HTTPException(status_code=200, detail=str(exc)) from exc",
	 'test_a_cancelled_alert_fires_a_conflict_not_a_receipt'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_emg.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly',
			f'tests/ci/test_emg001.py::{node}'],
			cwd=ROOT, capture_output=True, text=True)
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
