"""Canaries for tests/ci/test_alt002.py.

§ALT-002's SMS bullet was missing in a way that left every screen looking right: the check-in route
answered 200, `SafetyCheckIn.channel` already accepted `sms`, and nothing in the product ever sent
or received one. So every canary here is a plausible way to keep failing *while the feature appears
to work* — a board that reports a fan-out, a reply that arrives, a keyword that matches.

* **A member with no phone is counted as told** (#1) — the dangerous direction, and the one a
  `continue` in the loop produces: `sms_sent` goes up and `sms_unreachable` stays empty, so a
  family is told everyone knows when two people were reached.
* **A landline is texted** (#2) — the identity model hands back what the link recorded, and without
  `_sms_dialable` a Nairobi landline goes to the gateway, which drops it. Same false fan-out, one
  layer down.
* **One dead leg silences the rest** (#3) — an unguarded `await` inside the loop, so the first
  gateway refusal ends the fan-out and the members after it are never texted.
* **The check-in is lost when the text fails** (#4) — the fan-out written before the board, which is
  the button failing at the moment it matters: the person *is* safe whatever the carrier did.
* **`notify=False` becomes "nothing happened"** (#5) — the body composed only when something was
  sent, so a queued replay renders a blank line where the confirmation belongs.
* **The message names the members** (#6) — the subjects the board is keyed on, put into plain text
  on a handset that may be shared. §17.2's personal data, one SMS segment at a time.
* **The reply speaks the language that was asked for** (#7) — `luo` beside an English template, so
  a Dholuo speaker is told the English is Dholuo.
* **A negation reads as a check-in** (#8) — the one error worse than silence: "I am not safe" tells
  a family their relative is accounted for on the strength of the opposite.
* **A message about somebody else is filed as the sender's** (#9) — the same error one step removed.
* **An unlinked number is silently ignored** (#10) — an SMS with no answer is indistinguishable from
  a dropped network, so the refusal has to be a reply.
* **A group named that is not theirs is filed against their own** (#11) — two families told the
  wrong thing at once.
* **A person in two groups is guessed into one** (#12) — the check-in filed against whichever group
  sorted first, which is a coin toss with a family's answer on it.
* **A retried message becomes two check-ins** (#13) — the record appended blindly, so a carrier's
  retry reads as a second person accounted for on a board whose whole purpose is counting.
* **The SMS check-in stops reaching the fan-out** (#14) — the inbound path treated as a lesser
  version of the feature, so a family on feature phones is never told.
* **The route drops the check-in branch** (#15) — the feature gone at the carrier's own front door
  while every unit test over the service stays green, which is what the route did before.
* **The route claims the triage intents too** (#16) — a keyword test widened past the safe words, so
  the fever report is answered as a check-in. The outbreak response losing a symptom report is the
  cost of a router that is too eager.
* **The check-in record loses its channel** (#17) — `SafetyCheckIn.channel` back to the default, so
  the one field that makes the SMS leg auditable after the fact records nothing.
* **The check-in route stops binding the token** (#18) — `subject_ref` read from the query without
  comparison, so anyone can file a check-in as anyone.
* **The check-ins route stops binding the token** (#19) — a log of who is where, readable by anyone
  who types a subject. Caught by the route gate rather than by a test of this unit.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
L = ROOT / 'src/afya/alerting/service.py'
S = ROOT / 'src/afya/strings.py'
A = ROOT / 'src/afya/service.py'

CANARIES = [
	# 1. A member with no phone counted as told. The loop skips them and `sms_sent` still goes up, so
	#    the board reports a fan-out that reached two of three — the failure the split exists for.
	('a member who cannot be reached is counted as told', L,
	 "			if number is None:\n				unreachable.append(member)\n				# \"Cannot be reached\", not \"no phone on file\". The live probe printed the second for a",
	 "			if number is None:\n				sent += 1\n				# \"Cannot be reached\", not \"no phone on file\". The live probe printed the second for a",
	 'test_a_member_with_no_phone_is_reported_rather_than_counted_as_told'),

	# 2. The landline handed to the gateway. `identity_svc.msisdn_for` returns what the link recorded
	#    and `_sms_dialable` is what refuses a number that cannot receive a text; without it the
	#    gateway drops the message and the fan-out reports a family told that never was.
	('a landline is texted', A,
	 "		channels_svc.send_sms, lambda ref: _dialable(identity_svc.msisdn_for(ref)))",
	 "		channels_svc.send_sms, identity_svc.msisdn_for)",
	 'test_a_landline_is_not_a_phone_that_can_receive_a_text'),

	# 3. One dead leg ends the fan-out. The `try` goes away, so the first gateway refusal propagates
	#    out of `_notify_family` and the members after it are never texted.
	('one dead leg silences the rest', L,
	 "			try:\n				await self._sms(number, body)\n			except Exception as exc:  # one dead leg must not silence the others\n				unreachable.append(member)\n				self._log_error('family SMS failed', family=family_ref, error=str(exc))\n				continue",
	 "			await self._sms(number, body)",
	 'test_a_dead_gateway_leg_does_not_silence_the_others'),

	# 4. The check-in recorded after the fan-out, so a carrier that refuses everything loses the
	#    check-in itself. The person is safe whatever the gateway did with the text.
	('the check-in is lost when the text fails', L,
	 "		self._checkins.setdefault(family_ref, {})[subject_ref] = at_iso",
	 "		pass",
	 'test_the_check_in_is_recorded_even_when_no_message_goes_out'),

	# 5. `notify=False` leaves the body empty, so a queued replay renders a blank line where the
	#    person's own confirmation belongs — and the client has nothing to show.
	('notify false becomes nothing happened', L,
	 "		sent, unreachable = await self._notify_family(family_ref, board, lang) if notify else (0, [])",
	 "		if not notify:\n			return board\n		sent, unreachable = await self._notify_family(family_ref, board, lang)",
	 'test_a_notify_false_check_in_does_not_send'),

	# 6. The message names the members. The board is keyed on subjects, and putting them in the text
	#    sends §17.2's personal data to a handset the server has not verified belongs to the reader.
	('the message names the members', L,
	 "		return SMS_FAMILY_SAFE[served].format(board=summary)",
	 "		return SMS_FAMILY_SAFE[served].format(board=summary) + ' ' + ','.join(board.members_unknown)",
	 'test_no_members_subject_appears_in_the_message'),

	# 7. The reply reports the language asked for rather than the one it answered in, so a Dholuo
	#    speaker reads an English template believing it is Dholuo.
	('the reply speaks the asked-for language', L,
	 "		served = answerable(lang)\n		total = len(board.members_safe) + len(board.members_unknown)",
	 "		served = lang\n		total = len(board.members_safe) + len(board.members_unknown)",
	 'test_the_reply_is_answered_in_a_language_the_product_can_answer_in'),

	# 8. A negation read as a check-in — the audit's own defect class in the other direction. The
	#    word before the keyword stops being read, so "I am not safe" tells a family the opposite.
	('a negation reads as a check-in', L,
	 "			if i and words[i - 1] in _NEGATIONS:",
	 "			if False:",
	 'test_a_safe_word_is_a_check_in_and_a_negated_one_is_not'),

	# 8b. A negation answered with nothing rather than with 719 — the fall-through the live probe
	#     caught, where a person saying they are in danger was handed the welcome menu.
	('a negation falls through to the welcome menu', L,
	 "		if safe_intent(body) == 'negated':",
	 "		if False:",
	 'test_a_person_saying_they_are_not_safe_is_given_the_line_that_helps'),

	# 9. A message about somebody else filed as the sender's own. "My brother is safe" marks the
	#    *sender* safe, which is the same error one step removed.
	('a third-party message is filed as the sender', L,
	 "			if set(words[:i]) & _THIRD_PARTY:\n				return 'third-party'",
	 "			if False:\n				return 'third-party'",
	 'test_a_message_about_somebody_else_is_not_the_senders_check_in'),

	# 10. An unlinked number silently ignored. An SMS with no answer is indistinguishable from a
	#     dropped network, so the refusal has to be a reply rather than a `return ''`.
	('an unlinked number is silently ignored', L,
	 "		if subject is None:\n			self._log_info('inbound family SMS from an unlinked number')\n			return SMS_FAMILY_NO_GROUP[served]",
	 "		if subject is None:\n			return ''",
	 'test_an_unlinked_number_is_told_it_is_unlinked_rather_than_ignored'),

	# 11. A group named that is not the sender's, filed against their own — two families told the
	#     wrong thing at once.
	('a stranger group name is filed as their own', L,
	 "			if self._group_named_in(body, sorted(self._family)) is not None:\n				return SMS_FAMILY_UNKNOWN_GROUP[served]",
	 "			if False:\n				return SMS_FAMILY_UNKNOWN_GROUP[served]",
	 'test_a_group_name_that_is_not_one_of_theirs_is_refused_by_name'),

	# 12. A person in two groups guessed into one, which is a coin toss with a family's answer on it.
	('a two-group sender is guessed into one', L,
	 "			if len(groups) > 1:\n				return SMS_FAMILY_MANY_GROUPS[served]\n			named = groups[0]",
	 "			named = groups[0]",
	 'test_a_person_in_two_groups_is_asked_which_one_rather_than_guessed_into_one'),

	# 13. A retried message becomes two check-ins. The record appended blindly, so a carrier's retry
	#     reads as a second person accounted for.
	('a retried message becomes two check-ins', L,
	 "		if not any(c.checkin_id == checkin_id for c in self._checkins_log):",
	 "		if True:",
	 'test_a_retried_message_is_one_check_in_and_not_two'),

	# 14. The inbound path stops notifying the family, so a person who checks in over SMS is recorded
	#     and their family is never told — the SMS path as a lesser version of the feature.
	('the sms check-in stops reaching the fan-out', L,
	 "			board = await self.check_in(subject, named, at_iso, lang, notify=True, channel='sms')",
	 "			board = await self.check_in(subject, named, at_iso, lang, notify=False, channel='sms')",
	 'test_an_inbound_check_in_still_texts_the_members_who_have_not_answered'),

	# 15. The route drops the check-in branch entirely — what it did before this unit. Every service
	#     test stays green, which is why the canary names the front-door test.
	('the route drops the check-in branch', A,
	 "		if safe_intent(body) != 'none':",
	 "		if False:",
	 'test_the_inbound_sms_files_a_check_in_through_the_deployment'),

	# 16. The route claims the triage intents too. A router that answered every message as a check-in
	#     takes the fever report with it, and that is the report the outbreak response cannot lose.
	('the route claims the triage intents', A,
	 "		if safe_intent(body) != 'none':",
	 "		if True:",
	 'test_a_safe_word_does_not_displace_the_triage_intent'),

	# 17. The check-in record loses its channel, so the one field that makes §ALT-002's SMS leg
	#     auditable after the fact records the default for every arrival.
	('the check-in record loses its channel', L,
	 "				channel=channel, note=note,",
	 "				channel='native', note=note,",
	 'test_an_sms_check_in_is_recorded_as_having_come_over_sms'),

	# 18. The check-in route stops binding the token, so a citizen can file a check-in as anyone.
	('the check-in route stops binding the token', A,
	 "	async def alerting_check_in(subject_ref: str, family_ref: str, at_iso: str | None = None,\n			channel: str = 'native', note: str | None = None,\n			_subject: str = Depends(require_self())) -> dict[str, object]:",
	 "	async def alerting_check_in(subject_ref: str, family_ref: str, at_iso: str | None = None,\n			channel: str = 'native', note: str | None = None,\n			_subject: str = Depends(require_scope('self'))) -> dict[str, object]:",
	 'tests/ci/test_self_scope.py::test_every_subject_carrying_route_is_guarded'),

	# 19. The check-ins route stops binding the token: a log of who is where, readable by anyone who
	#     types a subject.
	('the check-ins route stops binding the token', A,
	 "	async def alerting_checkins(subject_ref: str, _subject: str = Depends(require_self())) -> list[dict[str, object]]:",
	 "	async def alerting_checkins(subject_ref: str, _subject: str = Depends(require_scope('self'))) -> list[dict[str, object]]:",
	 'test_a_token_may_not_read_another_persons_check_ins'),
]

failures = []

# A nonexistent node id makes pytest exit non-zero on a *collection* error, which reads as CAUGHT.
# So every node is collected first and asserted present, and a canary that names a test that is not
# there fails this script rather than passing it.
def _node(canary_node: str) -> str:
	return canary_node if '/' in canary_node else f'tests/ci/test_alt002.py::{canary_node}'

_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only',
	'tests/ci/test_alt002.py', 'tests/ci/test_self_scope.py'],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_alt002.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	# See canary_inf001.py's docstring: a same-second write of the same size reuses the previous
	# canary's bytecode, and the canary then tests code it never mutated.
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', _node(node)],
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
