"""Canaries for tests/ci/test_tri003.py — each gate pointed at a planted defect and watched to fail.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script.

Two of these are worth reading as a pair. #5 empties the immediate-action list and #6 removes one
instruction from it: the first is the defect the audit found (the transport instruction was simply
absent) and the second is the same defect wearing a smaller coat, which a gate that only counted
the list would miss. #9 and #10 are the same shape for the consent check — one skips it, the other
inverts its unwired branch, and the second is the one that fails *open*.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
V = ROOT / 'src/afya/triage/views.py'
S = ROOT / 'src/afya/triage/service.py'
G = ROOT / 'src/afya/service.py'

CANARIES = [
	# 1. The four named exposures stop feeding the epidemiological criteria, so the section's
	#    Additional inputs become a form the person fills in and the classifier ignores.
	('the named exposures stop being contact history', V,
	 "			or bool(self.exposures))",
	 "			or False)",
	 'test_a_named_exposure_is_contact_history_without_the_boolean'),

	# 2. The exposure vocabulary stops being closed, so any string is an exposure.
	('the exposure list stops being closed', V,
	 "		assert all(e in EBOLA_EXPOSURES for e in self.exposures), \\",
	 "		pass  #",
	 'test_the_four_named_exposures_are_a_closed_vocabulary'),

	# 3. The notes stop being per-route, so a funeral and a bushmeat exposure read identically —
	#    the defect the audit found, moved from the input to the output.
	('every exposure gets the same sentence', V,
	 "		return [EXPOSURE_NOTE[e] for e in EBOLA_EXPOSURES if e in self.exposures]",
	 "		return [EXPOSURE_NOTE['case_contact'] for e in EBOLA_EXPOSURES if e in self.exposures]",
	 'test_each_exposure_says_what_it_means_in_its_own_words'),

	# 4. The notes reorder with the request, so two identical reports render differently.
	('the notes follow the request order', V,
	 "		return [EXPOSURE_NOTE[e] for e in EBOLA_EXPOSURES if e in self.exposures]",
	 "		return [EXPOSURE_NOTE[e] for e in self.exposures]",
	 'test_the_exposure_notes_do_not_reorder_with_the_request'),

	# 5. The whole immediate-action list disappears again — §11.2's second Output with no carrier.
	('the immediate actions disappear', S,
	 "			immediate_actions=_immediate_actions() if ebola_branch else [],",
	 "			immediate_actions=[],",
	 'test_the_three_immediate_actions_all_travel'),

	# 6. The transport instruction alone is dropped. This is the audit's finding exactly: the
	#    recommendation named 719 and isolation and said nothing about how not to arrive.
	('the transport instruction is dropped', V,
	 "	('do_not_travel', 'Do not travel by public transport',\n	 'Do not take a matatu, bus or boda. You would be sitting close to other people for the whole journey.'),",
	 "	('call', 'Call 719 now and say you may have Ebola', 'x'),",
	 'test_the_three_immediate_actions_all_travel'),

	# 7. The pair leaks onto every rung, so a person with a mild fever is told to await instructions.
	('the pair leaks onto every rung', S,
	 "			immediate_actions=_immediate_actions() if ebola_branch else [],",
	 "			immediate_actions=_immediate_actions(),",
	 'test_the_immediate_actions_are_absent_from_every_other_rung'),

	# 8. The model validator is loosened, so a hand-built result can carry the pair without the
	#    classification. The service assert would not be reached by such a caller.
	('the result accepts the pair on any rung', V,
	 "		assert (self.household_isolation is not None) is ebola, (",
	 "		assert True or (self.household_isolation is not None) is ebola, (",
	 'test_the_result_refuses_the_pair_without_the_classification'),

	# 9. The consent check is skipped entirely — the notification goes to whoever the branch finds.
	('consent is not consulted', S,
	 "		if self._privacy is None or not self._privacy.has_notification_consent(subject_ref):",
	 "		if False:",
	 'test_the_county_team_is_notified_only_with_consent'),

	# 10. The unwired branch notifies instead of refusing. This is the fail-open shape: a control
	#     that is correct at every wired path and absent at the one path nobody wired.
	('an unwired service notifies', S,
	 "		if self._privacy is None or not self._privacy.has_notification_consent(subject_ref):",
	 "		if self._privacy is not None and not self._privacy.has_notification_consent(subject_ref):",
	 'test_the_county_team_is_notified_only_with_consent'),

	# 11. The classification stops gating the escalation, so a malaria case is reported to the team.
	('every classification escalates', S,
	 "		if result.risk_level not in (RiskLevel.high_ebola_suspicion, RiskLevel.emergency):\n			return None",
	 "		if False:\n			return None",
	 'test_the_escalation_is_not_raised_for_another_classification'),

	# 12. A notification with no county is filed anyway, addressed to nobody.
	('a notification with no county is filed', S,
	 "		if not inp.county:\n			self._log_info('rrt notification withheld: no county', subject_ref=subject_ref)\n			return None",
	 "		if False:\n			return None",
	 'test_a_notification_with_no_county_goes_nowhere'),

	# 13. The county filter is dropped, so every county reads every other county's queue.
	('the county filter is dropped', S,
	 "		return [n for n in self._rrt if n.county == county]",
	 "		return list(self._rrt)",
	 'test_the_county_view_is_scoped_and_shows_what_was_sent'),

	# 14. The isolation status stops reaching the guidance, so "isolate now" reads the same to a
	#     person already in a separate room as to one who is not.
	('isolation status stops reaching the guidance', S,
	 "	isolating = inp.isolation in ('isolated_at_home', 'isolated_at_facility')",
	 "	isolating = False",
	 'test_the_guidance_says_whether_the_person_is_already_isolating'),

	# 15. The notification stops carrying the exposures, so the team's first question is one they
	#     have to open the app to answer.
	('the exposures stop travelling to the team', S,
	 "			exposures=list(inp.exposures),",
	 "			exposures=[],",
	 'test_the_county_view_is_scoped_and_shows_what_was_sent'),

	# 16. The case identifier is filled in from the subject, so a case identifier moves through a
	#     channel that has no need for one — §COM-102's rule from the other end.
	('the notification names a case', S,
	 "			case_ref=case_ref,",
	 "			case_ref=case_ref or subject_ref,",
	 'test_the_notification_names_no_person_and_no_case_unless_given_one'),

	# 17. §11.1's gate is removed from the Ebola branch, so the Ebola check is live year-round.
	('the Ebola branch opens without the declaration', S,
	 "		if not self._registry.tier4_active():\n			# Refusal text a person may read: no spec code, no tier number.\n			raise PermissionError('the Ebola check opens when the outbreak response is activated')",
	 "		if False:\n			raise PermissionError('x')",
	 'test_the_route_escalates_only_for_a_caller_who_consented'),

	# 18. The route stops reading the ledger and escalates on the branch alone — the failure
	#     §8.1's Privacy clause exists to prevent.
	('the route escalates without asking the ledger', G,
	 "		if result.risk_level in (RiskLevel.high_ebola_suspicion, RiskLevel.emergency):",
	 "		if False:",
	 'test_the_route_escalates_only_for_a_caller_who_consented'),

	# 19. The route reports a notification it did not make, so a person who declined is told a team
	#     was told about them.
	('the result claims a notification that did not go', G,
	 "			if notification is not None:\n				result.county_rrt_notified = True",
	 "			if True:\n				result.county_rrt_notified = True",
	 'test_the_route_escalates_only_for_a_caller_who_consented'),

	# 20. The county view stops being scoped, so a citizen reads the team's queue.
	('the county view stops being scoped', G,
	 "	async def triage_rrt(county: str, _subject: str = Depends(require_scope('assigned'))) -> list[dict[str, object]]:",
	 "	async def triage_rrt(county: str, _subject: str | None = None) -> list[dict[str, object]]:",
	 'test_the_county_view_is_scoped_and_shows_what_was_sent'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_tri003.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly',
			f'tests/ci/test_tri003.py::{node}'],
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
