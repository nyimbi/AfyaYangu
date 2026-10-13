"""Canaries for tests/ci/test_loc005.py.

§LOC-005's three missing bullets are each a *plan with no other end of it*, and that shape is why
each is canaried rather than argued:

* **"post-arrival symptom reporting"** was missing because the enrolment stated a schedule and no
  route accepted a report. The cheap fix is a route that accepts any day, which is canary #2: the
  traveller reports on day 5, is told they have been checked on, and the schedule's days go unread.
* **"multi-language support for cross-border travellers"** was missing because `lang` was accepted
  and never read. The cheap fix is a route that takes the parameter and ignores it — canaries #4
  and #5 — which passes any test that reads the payload and never compares two languages.
* **"integration with mobile laboratory results at border points"** was missing because a post
  described no testing. The cheap fix is a lab field that can be set on its own, which is canary #8:
  a turnaround promised by a post that reports no lab.

The canaries worth reading as a set are #2, #5 and #8. #2 is a false reassurance at the end of a
21-day window. #5 is the language parameter that is taken and discarded. #8 is a promise from a post
that cannot keep it.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary that
passes is a bug in the canary, so a MISSED line is a failure of this script. The `__pycache__` purge
after each write is load-bearing for the reason `canary_inf001.py` documents: two canaries mutating
two files with same-length edits in the same second make CPython reuse the previous canary's
bytecode, and the gate then reports a mutation it never made.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
V = ROOT / 'src/afya/location/views.py'
S = ROOT / 'src/afya/location/service.py'
G = ROOT / 'src/afya/service.py'
T = ROOT / 'src/afya/strings.py'

CANARIES = [
	# 1. The schedule stops being enforced, so a report on day 5 is accepted and the traveller is told
	#    they have been checked on a day nobody reads. The whole point of the enrolment naming days.
	('any day is accepted as a scheduled day', S,
	 "		assert report.day in enrolment.report_schedule, (",
	 "		assert True or report.day in enrolment.report_schedule, (",
	 'test_a_report_on_a_day_nobody_asks_about_is_refused'),

	# 2. A report from someone who never declared is accepted, so the window is created by the back
	#    door with a schedule nobody recorded and a language nobody declared.
	('a report from an unenrolled person is accepted', S,
	 "		assert enrolment is not None, f'{subject_ref} is not enrolled for post-arrival monitoring'",
	 "		enrolment = enrolment or TravellerEnrolment(subject_ref=subject_ref, enrolled=True, report_schedule=[1, 3, 7, 14, 21], message='x')",
	 'test_a_report_from_someone_who_never_declared_is_refused'),

	# 3. The escalation rule stops reading the alert symptom set, so a traveller reporting bleeding on
	#    day 7 is told they are fine. The one path where a missed escalation leaves Ebola in a market.
	('a warning sign stops escalating', S,
	 "		flagged = sorted(set(report.symptoms) & MONITORING_ALERT_SYMPTOMS)",
	 "		flagged = []",
	 'test_a_warning_sign_without_fever_escalates_too'),

	# 4. The advisory stops taking a language, so a Kiswahili-reading traveller is served English on
	#    the one screen where getting it wrong means arriving unwell and not knowing to call 719.
	('the advisory ignores the language it is given', S,
	 "		return traveller(lang, 'advisory', destination=destination, origin_country=origin_country)",
	 "		return traveller('en', 'advisory', destination=destination, origin_country=origin_country)",
	 'test_the_advisory_is_served_in_the_language_the_traveller_asks_for'),

	# 5. The enrolment acknowledgement is served in English whatever the traveller declared in — the
	#    exact defect the field existed for and nothing read.
	('the enrolment ignores the declared language', S,
	 "			message=traveller(decl.lang, 'enrolled'), lang=decl.lang,",
	 "			message=traveller('en', 'enrolled'), lang=decl.lang,",
	 'test_the_enrolment_acknowledgement_is_in_the_declared_language'),

	# 6. The daily prompt stops being localised, so the question a traveller is asked comes back in a
	#    language they may not read — and it is the question the whole 21-day window turns on.
	('the daily prompt ignores the declared language', S,
	 "		return traveller(enrolment.lang, 'prompt', day=day)",
	 "		return traveller('en', 'prompt', day=day)",
	 'test_the_daily_prompt_is_served_in_the_declared_language'),

	# 7. The prompt stops checking the day is scheduled, so a client asking about day 4 gets a
	#    question for a day that is not in the window.
	('the prompt answers for any day', S,
	 "		assert day in enrolment.report_schedule, f'day {day} is not a scheduled report day'",
	 "		assert True or day in enrolment.report_schedule, f'day {day} is not a scheduled report day'",
	 'test_the_prompt_route_refuses_a_day_outside_the_schedule'),

	# 8. A lab turnaround can be stated by a post that reports no lab, so the screen promises results
	#    in four hours from a post that cannot test. The promise is the whole defect.
	('a lab turnaround is allowed with no lab', V,
	 "		assert self.mobile_lab == (self.lab_turnaround_hours is not None), (",
	 "		assert True or self.mobile_lab == (self.lab_turnaround_hours is not None), (",
	 'test_a_lab_turnaround_with_no_lab_behind_it_is_refused'),

	# 9. Tests can be named with no lab behind them, so the post advertises a service that is not
	#    there and a traveller is sent to it.
	('tests are allowed with no lab', V,
	 "		assert self.mobile_lab == bool(self.lab_tests), (",
	 "		assert True or self.mobile_lab == bool(self.lab_tests), (",
	 'test_tests_named_with_no_lab_behind_them_are_refused'),

	# 10. The report route loses its guard, so the `subject_ref` in the body is whoever the caller
	#     typed and a verdict about a stranger — including whether a county team is notified.
	('the report route loses its guard', G,
	 "	async def location_traveller_report(report: PostArrivalReport, _subject: str = Depends(require_self())) -> dict[str, object]:",
	 "	async def location_traveller_report(report: PostArrivalReport) -> dict[str, object]:",
	 'test_a_traveller_cannot_file_a_report_for_someone_else'),

	# 11. A report route that raises 500 for a day outside the schedule, so the caller is told the
	#     server broke when their own input is what was wrong.
	('the report route stops refusing a bad day', G,
	 "		try:\n			return (await location.report_arrival_day(report)).model_dump(mode='json')\n		except AssertionError as exc:\n			raise HTTPException(status_code=422, detail=str(exc)) from exc",
	 "		return (await location.report_arrival_day(report)).model_dump(mode='json')",
	 'test_the_report_route_refuses_a_day_outside_the_schedule'),

	# 12. A Kiswahili string loses its placeholders, so the advisory names no destination and the
	#     traveller cannot tell which country's rules they are being told about.
	('a Kiswahili string loses its placeholders', T,
	 "			'Safari kwenda {destination} kutoka {origin_country}: angalia tangazo la sasa la Wizara '",
	 "			'Safari: angalia tangazo la sasa la Wizara '",
	 'test_the_advisory_is_served_in_the_language_the_traveller_asks_for'),

	# 13. An unknown key returns a placeholder instead of raising, so a screen renders blank where an
	#     instruction should be and nothing reports the missing string.
	('an unknown traveller string returns a placeholder', T,
	 "	assert key in TRAVELLER_STRINGS['en'], f'unknown traveller string {key}'",
	 "	assert True or key in TRAVELLER_STRINGS['en'], f'unknown traveller string {key}'",
	 'test_an_unknown_traveller_string_is_refused'),

	# 14. The traveller path stops falling back through `answerable`, so a language with no table is
	#     answered by indexing the table directly and the route raises instead of serving English.
	('the fallback stops going through answerable', T,
	 "	return TRAVELLER_STRINGS[answerable(lang)][key].format(**fields)",
	 "	return TRAVELLER_STRINGS[lang][key].format(**fields)",
	 'test_a_language_with_no_table_is_served_english_and_says_so'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_loc005.{path.name}.bak')
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
			f'tests/ci/test_loc005.py::{node}'], cwd=ROOT, capture_output=True, text=True)
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
