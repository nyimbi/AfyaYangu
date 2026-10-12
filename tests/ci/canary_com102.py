"""Canaries for tests/ci/test_com102.py — each gate pointed at a planted defect and watched to fail.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script.

The three shapes worth reading as a set are #3, #7 and #12. #3 restores the free-text body — the
defect the audit found, where a CHW could write any sentence into a whole village. #7 makes the
follow-up prompt fire on every day of the window, which is the same defect as #3 in the other
direction: too much sent rather than the wrong thing sent. #12 drops the route's count, so the
receipt a CHW reads says nobody answered an alert people did answer — a control that reports a
number it did not measure.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
V = ROOT / 'src/afya/community/views.py'
S = ROOT / 'src/afya/community/service.py'
G = ROOT / 'src/afya/service.py'
M = ROOT / 'src/afya/mobile/actions.py'

CANARIES = [
	# 1. The body becomes a field a caller writes again. This is the audit's finding exactly: a
	#    free-text body is a body that can be alarmist and that no reviewer sees before dispatch.
	('the body becomes caller-supplied', V,
	 "	@computed_field\n	@property\n	def body(self) -> str:\n		\"\"\"The section's sentence, with the location in it. Derived, so there is no free-text body.\"\"\"\n		return ALERT_TEMPLATE.format(location=self.location)",
	 "	body: str = ''",
	 'test_the_body_is_the_sections_sentence_and_the_location_is_the_only_slot'),

	# 2. `DerivedFields` comes off, so the request that carries back the body it was served is
	#    refused with a 422 — the shape that makes a client drop a field it cannot round-trip.
	('the model stops tolerating its own derived field', V,
	 "class PeerAlert(DerivedFields, BaseModel):",
	 "class PeerAlert(BaseModel):",
	 'test_the_body_is_the_sections_sentence_and_the_location_is_the_only_slot'),

	# 3. The sentence loses the symptom window, so the alert tells someone to avoid a market and
	#    never says for how long — §COM-102 prints "for 21 days" and the number is the section's.
	('the alert loses its 21-day window', V,
	 "	'Monitor for symptoms for 21 days. Call 719 if you feel unwell.'",
	 "	'Call 719 if you feel unwell.'",
	 'test_the_body_is_the_sections_sentence_and_the_location_is_the_only_slot'),

	# 4. The location rule is removed, so "House 14, next to Mama Otieno's" reaches the geofence.
	('the location rule is removed', V,
	 "		assert not leaked, (",
	 "		assert True or not leaked, (",
	 'test_the_alert_body_has_nowhere_to_put_a_case_identifier'),

	# 5. The rule is widened to the section's own anonymised phrasing, so "The Case Hotel" is
	#    refused — the shape of rule people route around rather than use.
	('the rule refuses the sections own phrasing', V,
	 "	'the patient', 'the victim', 'the deceased', 'the body',",
	 "	'the case', 'the patient', 'the victim', 'the deceased', 'the body',",
	 'test_the_alert_body_has_nowhere_to_put_a_case_identifier'),

	# 6. The zone check is loosened back to a range, so 3000 m — a radius no county can configure —
	#    is accepted as a zone.
	('the zone set becomes a range', V,
	 "		assert self.radius_m in ALERT_ZONE_RADII_M, (",
	 "		assert 500 <= self.radius_m <= 5000, (",
	 'test_a_radius_outside_the_sections_zones_is_refused'),

	# 7. `followup_days` stops being pinned, so a caller sends [1..21] and every recipient gets a
	#    prompt a day — the daily nag the section avoids precisely by naming four.
	('the follow-up days become a callers choice', V,
	 "		assert self.followup_days == list(FOLLOWUP_DAYS), (",
	 "		assert True or self.followup_days == list(FOLLOWUP_DAYS), (",
	 'test_the_followup_days_are_the_sections_four_and_not_a_callers_choice'),

	# 8. The prompt fires on every day of the window rather than the four.
	('a prompt goes on every day', S,
	 "		if day not in FOLLOWUP_DAYS:\n			return None",
	 "		if day > ALERT_WINDOW_DAYS:\n			return None",
	 'test_a_prompt_goes_on_the_four_days_and_on_no_other'),

	# 9. The prompt fires on no day — the fourth Feature with a carrier that returns nothing, which
	#    is the state the audit found it in.
	('a prompt goes on no day', S,
	 "		if day not in FOLLOWUP_DAYS:\n			return None",
	 "		return None\n		if day not in FOLLOWUP_DAYS:\n			return None",
	 'test_a_prompt_goes_on_the_four_days_and_on_no_other'),

	# 10. An unknown alert answers instead of refusing, so the scheduler's typo looks like a day
	#     with no prompt.
	('an unknown alert answers', S,
	 "		self.alert(alert_id)\n		if day not in FOLLOWUP_DAYS:",
	 "		if day not in FOLLOWUP_DAYS:",
	 'test_a_prompt_goes_on_the_four_days_and_on_no_other'),

	# 11. The acknowledgement stops being recorded, so the count stays 0 however many people answer.
	('the acknowledgement is not recorded', S,
	 "		self._peer_acks[key] = ack",
	 "		pass  #",
	 'test_one_person_acknowledging_twice_is_one_acknowledgement'),

	# 12. The ledger becomes append-only, so three taps are three people — the number a CHW reads as
	#     "how many heard this" becomes a count of taps. The gate is the *key*, not the set in
	#     `acknowledged_count`: the dict already dedupes on `(alert_id, subject_ref)`, so mutating the
	#     set alone is caught by nothing and a canary written against it passes for the wrong reason.
	('a double tap counts twice', S,
	 "		self._peer_acks[key] = ack",
	 "		self._peer_acks[(ack.alert_id, str(len(self._peer_acks)))] = ack",
	 'test_one_person_acknowledging_twice_is_one_acknowledgement'),

	# 13. The day is read from the acknowledgement alone, so a person who reads a day-1 alert on
	#     day 21 is told they are on day 1 — the client's clock decides what they are told.
	('the day ignores when the alert was issued', S,
	 "	day = (seen - issued).days + 1",
	 "	day = 1",
	 'test_the_day_is_derived_from_the_alert_not_from_the_client'),

	# 14. A late acknowledgement is refused rather than clamped, so the fact that the person
	#     answered at all is lost.
	('a late acknowledgement is refused', S,
	 "	return max(1, min(ALERT_WINDOW_DAYS, day))",
	 "	assert day <= ALERT_WINDOW_DAYS, 'past the window'\n	return max(1, day)",
	 'test_the_day_is_derived_from_the_alert_not_from_the_client'),

	# 15. The guidance loses the action that resolves a concern, so an acknowledgement returns the
	#     alert and no next step — §COM-102's third bullet with half a carrier.
	('the acknowledgement returns no guidance', S,
	 "		guidance = list(ALERT_GUIDANCE)",
	 "		guidance = []",
	 'test_an_acknowledgement_returns_guidance_and_names_the_next_prompt'),

	# 16. A worried person gets no extra line, so "concerned" is a field nothing reads.
	('a worried person gets nothing extra', S,
	 "		if ack.concerned:",
	 "		if False:",
	 'test_an_acknowledgement_returns_guidance_and_names_the_next_prompt'),

	# 17. The receipt stops carrying the sentence it dispatched, so the sender's review surface
	#     shows a body the recipients did not get.
	('the receipt carries a different body', S,
	 "			body=alert.body, followup_days=list(alert.followup_days),",
	 "			body=alert.headline, followup_days=list(alert.followup_days),",
	 'test_the_receipt_carries_the_body_it_sent_and_the_days_it_will_prompt'),

	# 18. The route stops reading the ledger, so the receipt says nobody answered an alert people
	#     did answer — a number reported rather than measured.
	('the receipt stops counting acknowledgements', G,
	 "		return receipt.model_copy(update={'acknowledged': community.acknowledged_count(alert.alert_id)}).model_dump(mode='json')",
	 "		return receipt.model_dump(mode='json')",
	 'test_the_route_refuses_a_body_and_the_acknowledgement_binds_the_token'),

	# 19. The ack route stops binding the body to the token, so a caller can acknowledge as someone
	#     else and inflate the count.
	('the ack route stops binding the token', G,
	 "	async def community_peer_ack(ack: PeerAlertAck, _subject: str = Depends(require_self())) -> dict[str, object]:",
	 "	async def community_peer_ack(ack: PeerAlertAck, _subject: str | None = None) -> dict[str, object]:",
	 'test_the_route_refuses_a_body_and_the_acknowledgement_binds_the_token'),

	# 20. The two new actions go live, so a Tier-4 feature ships a control §11.1 says stays dark.
	#     The gate that catches this lives with the other tier gates, not in this module's file.
	('the peer-alert actions go live', M,
	 "	'peer_alert', 'peer_alert_followup', 'ack_peer_alert',",
	 "	'peer_alert',",
	 'tests/ci/test_ui_vocabulary.py::test_every_tier4_action_is_dormant'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_com102.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	target = node if node.startswith('tests/') else f'tests/ci/test_com102.py::{node}'
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', target],
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
