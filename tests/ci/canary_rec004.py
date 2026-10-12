"""Canaries for tests/ci/test_rec004.py — each gate pointed at a planted defect and watched to fail.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
S = ROOT / 'src/afya/women/service.py'
V = ROOT / 'src/afya/women/views.py'
C = ROOT / 'src/afya/women/content.py'

CANARIES = [
	# 1. The 30-day month returns. This is the defect the module shipped with, and it must fail the
	#    arithmetic gate on every branch — including the leap-year and year-boundary rows.
	('the 30-day month returns', S,
	 "	return (date(y, m, d) + timedelta(days=days)).isoformat()",
	 "	return f'{y + (m * 30 + d + days - 1) // 360}-{m:02d}-{d:02d}'",
	 'test_a_predicted_date_is_the_date_the_calendar_gives'),

	# 2. The span goes back to 30-day months: a real 31-day cycle reads as 30.
	('the span is measured in 30-day months', S,
	 "	return (date(y2, m2, d2) - date(y, m, d)).days",
	 "	return (y2 - y) * 360 + (m2 - m) * 30 + (d2 - d)",
	 'test_a_cycle_span_is_measured_on_the_calendar_not_in_thirty_day_months'),

	# 3. The anchor goes back to the last *logged* entry. A backfilled earlier period must move the
	#    prediction into the past.
	('the anchor is the last logged period again', S,
	 "		return sorted(self._logs.get(subject_ref, []), key=lambda entry: entry.start_iso)",
	 "		return list(self._logs.get(subject_ref, []))",
	 'test_the_prediction_is_anchored_to_the_latest_period_not_the_last_one_logged'),

	# 4. The fertile window is declared and dropped again — the field that was always None.
	('the fertile window is dropped from the value', S,
	 "			fertile_window_days=window,",
	 "			fertile_window_days=None,",
	 'test_the_fertile_window_is_a_value_with_dates_and_a_pair_of_cycle_days'),

	# 5. The window's dates stop travelling, so only the cycle-day pair survives.
	('the window dates stop travelling', S,
	 "			fertile_from_iso=_add_days(ovulation, -content.SPERM_SURVIVAL_DAYS),",
	 "			fertile_from_iso=None,",
	 'test_the_fertile_window_is_a_value_with_dates_and_a_pair_of_cycle_days'),

	# 6. The "not a contraceptive method" note goes: the window reads as a schedule.
	('the estimate caveat is dropped', S,
	 "			fertility_note=f'{content.FERTILE_WINDOW_CAVEAT} {content.FERTILITY_AWARENESS_NOTE}',",
	 "			fertility_note='',",
	 'test_the_window_says_it_is_an_estimate_and_not_a_contraceptive_method'),

	# 7. The overdue branch goes, so an unlogged-for-three-months person gets a date in the past.
	('an overdue prediction names a past date', S,
	 "		elif overdue_days > 0:",
	 "		elif False:",
	 'test_an_overdue_prediction_says_so_rather_than_naming_a_date_in_the_past'),

	# 8. The reliability stops coming from WHO's table, so the recorded band is the caller's string.
	('the reliability stops coming from the table', S,
	 "			repeat_days=req.repeat_days, label=str(row['label']),\n			reliability=str(row['reliability']), prevents_sti=bool(row['prevents_sti']),",
	 "			repeat_days=req.repeat_days, label=str(row['label']),\n			reliability='highly effective', prevents_sti=True,",
	 'test_a_recorded_method_takes_its_reliability_from_who_not_from_the_caller'),

	# 9. A long-acting method is given a repeating schedule it does not have.
	('a long-acting method gets a schedule', S,
	 "		assert req.repeat_days is None or req.method in ('pill', 'injection', 'patch', 'vaginal_ring'), (\n			'a long-acting method is not taken on a repeating schedule')",
	 "		pass",
	 'test_a_repeating_method_gets_a_due_date_and_a_long_acting_one_does_not'),

	# 10. An unknown method is accepted, so a client can record one WHO does not list.
	('an unknown method is accepted', S,
	 "		assert row is not None, f'unknown contraceptive method {req.method!r}'",
	 "		assert row is not None or True, f'unknown contraceptive method {req.method!r}'",
	 'test_a_repeating_method_gets_a_due_date_and_a_long_acting_one_does_not'),

	# 11. The STI note goes: a pill user is not told it does not protect against HIV.
	('the STI note is dropped', S,
	 "		if not plan.prevents_sti:",
	 "		if False:",
	 'test_a_non_sti_method_says_it_does_not_protect_against_stis'),

	# 12. The due filter is loosened, so a method that is not due yet is reported as due.
	('a method is due before its date', S,
	 "		       if p.subject_ref == subject_ref and p.next_due_iso and p.next_due_iso <= on_iso]",
	 "		       if p.subject_ref == subject_ref]",
	 'test_the_reminder_is_the_methods_that_are_due_by_the_day_asked_about'),

	# 13. The twelve-month rule is shortened, so perimenopause ends early.
	('the twelve-month rule is shortened', C,
	 "PERIMENOPAUSE_MONTHS = 12",
	 "PERIMENOPAUSE_MONTHS = 6",
	 'test_the_twelve_month_rule_is_whos_and_it_comes_from_the_persons_own_logs'),

	# 14. Contraception stops being recommended during perimenopause — the source says the opposite.
	('contraception stops being recommended', S,
	 "			contraception_still_recommended=state == 'perimenopausal',",
	 "			contraception_still_recommended=False,",
	 'test_the_twelve_month_rule_is_whos_and_it_comes_from_the_persons_own_logs'),

	# 15. A symptom the source does not name is invented, or the source's own list is cut.
	('the symptom list is cut', C,
	 "{'slug': 'bone_density', 'label': 'Bone density loss',",
	 "{'slug': 'bones_removed', 'label': 'Bone density loss',",
	 'test_the_menopause_output_carries_the_sources_own_symptoms_and_no_verdict_on_age'),

	# 16. The unverified numbers stop being reported, so an unchecked number looks checked.
	('unverified numbers stop being reported', S,
	 "		unverified = [f\"{row['name']} ({row['number']}) — number not verified against the provider\"\n\t\t              for row in COUNSELLING_LINES if row.get('verified') != 'True']",
	 "		unverified = []",
	 'test_a_referral_names_services_and_the_numbers_nobody_verified'),

	# 17. A spec code leaks into the referral a person reads.
	('a spec code leaks into the referral', C,
	 "	{'slug': 'family_planning', 'label': 'Family planning and contraception',",
	 "	{'slug': 'family_planning', 'label': '§REC-004 family planning',",
	 'test_a_referral_to_services_does_not_carry_a_spec_code'),

	# 18. The IDOR guard is loosened: another person's cycle becomes readable.
	('another persons cycle is readable', ROOT / 'src/afya/service.py',
	 "	async def women_predict(ref: str, ref_date: str = '2026-10-08', _subject: str = Depends(require_self(lambda r: r.path_params['ref']))) -> dict[str, object]:",
	 "	async def women_predict(ref: str, ref_date: str = '2026-10-08', _subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:",
	 'test_another_persons_cycle_is_refused'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_rec.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly',
			f'tests/ci/test_rec004.py::{node}'],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
	print(f'{"CAUGHT " if caught else "MISSED "} {name}')
	if not caught:
		failures.append(name)
		print(proc.stdout[-1200:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
