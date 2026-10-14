"""Canaries for tests/ci/test_loc004.py.

§LOC-004's fourth Behaviour bullet was "every visible part exists and the join does not": the
check-in is stored, the point is stored, the guidance is served — and "used for attendance tracking,
follow-up scheduling, and exposure window determination" was a sentence about a record nothing read.
The canaries are the cheap ways to make that sentence *look* carried, which is the failure this unit
exists to close.

The four worth reading as a set:

* **#1** opens the window for every kind. It passes every test that checks a border post opens one,
  and it is the app starting a 21-day symptom watch after a school screening — a clock nobody was
  told about, on the strength of guidance that says nothing about symptoms.
* **#4** drops an unreadable point from the attendance count instead of asserting. The person is
  told they attended four places when they attended five, and nothing anywhere says a row went
  missing. Silent undercount is the failure mode of every join.
* **#8** lets a closed window report itself as open with nothing left in it. The person keeps
  watching past the day the source's own upper bound ends.
* **#11** serves the no-check-ins string to someone who *has* check-ins but no watch. Two facts,
  one sentence — the screen contradicts the record it is describing.

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
S = ROOT / 'src/afya/location/service.py'
V = ROOT / 'src/afya/location/views.py'
G = ROOT / 'src/afya/service.py'
T = ROOT / 'src/afya/strings.py'

CANARIES = [
	# 1. Every kind opens a watch, so a school screening starts a 21-day symptom clock the school's
	#    own guidance never mentioned. The silent-watch failure the import-time assert exists for.
	('a point that names no watch opens one anyway', S,
	 "		return point is not None and point.kind in WATCH_KINDS",
	 "		return point is not None",
	 'test_a_point_that_opens_no_watch_starts_no_window'),

	# 3. `visit_no` becomes a global counter instead of a per-point one, so three scans at one
	#    screening point read as three places attended. The reading a county would act on.
	('visits are numbered globally instead of per point', S,
	 "			seen[point.point_id] = seen.get(point.point_id, 0) + 1\n			rows.append(CheckInAttendance(",
	 "			seen[point.point_id] = len(rows) + 1\n			rows.append(CheckInAttendance(",
	 'test_attendance_is_numbered_per_point_not_globally'),

	# 4. An unresolvable point is skipped instead of asserted, so a visit vanishes from the count and
	#    the person is told they attended fewer places than they did. Nothing reports the row.
	('an unresolvable point is dropped from the count', S,
	 "			assert point is not None, f'check-in {c.checkin_id} names an unregistered point'",
	 "			if point is None:\n				continue",
	 'test_an_unregistered_point_is_refused_rather_than_dropped'),

	# 5. The window is computed from the oldest watch-opening check-in instead of the newest, so a
	#    person who crossed a border twice is followed up on the crossing that is already over.
	('the window runs from the oldest check-in, not the newest', S,
	 "		window = self._window(max(watching, key=lambda c: c.at_iso), now, lang) if watching else None",
	 "		window = self._window(min(watching, key=lambda c: c.at_iso), now, lang) if watching else None",
	 'test_the_latest_watch_opening_check_in_opens_the_window'),

	# 6. `elapsed_days` stops being clamped, so a check-in eight months old reports 240 days into a
	#    21-day window. The field's own docstring is the claim this breaks.
	('elapsed days are not clamped to the window', S,
	 "			window_days=LOCATION_WINDOW_DAYS, elapsed_days=min(elapsed, LOCATION_WINDOW_DAYS),",
	 "			window_days=LOCATION_WINDOW_DAYS, elapsed_days=elapsed,",
	 'test_a_closed_window_is_reported_as_closed_not_dropped'),

	# 7. `remaining_days` loses its floor, so a window eight months closed reports a negative number
	#    of days left and the field's `ge=0` refuses the model — a 500 where a record should be.
	('remaining days can go negative', S,
	 "		remaining = max(0, LOCATION_WINDOW_DAYS - elapsed)",
	 "		remaining = LOCATION_WINDOW_DAYS - elapsed",
	 'test_a_closed_window_is_reported_as_closed_not_dropped'),

	# 8. A closed window reports itself open. The person keeps watching past the day the source's own
	#    upper bound ends — and the source gives a range, so the note must not imply they are clear.
	('a closed window reports itself open', S,
	 "		open_ = now_ms < closes_ms",
	 "		open_ = True",
	 'test_a_closed_window_is_reported_as_closed_not_dropped'),

	# 9. The schedule loses `due`, so the day a prompt falls on is indistinguishable from a day that
	#    has not arrived. Every step reads as "not yet", including today's.
	('no step is ever due', S,
	 "				day=day, due_iso=due, due=due == today, past=due < today,",
	 "				day=day, due_iso=due, due=False, past=due < today,",
	 'test_a_step_is_due_on_its_day_and_past_after_it'),

	# 10. The schedule's day arithmetic shifts by one, so the day-3 ask falls on the 4th and the whole
	#     window is off against §MON-009's counting.
	('the schedule days are off by one', S,
	 "			due = iso_add_days(start, day - 1)",
	 "			due = iso_add_days(start, day)",
	 'test_the_schedule_falls_on_the_window_days_from_the_check_in'),

	# 11. A person with check-ins and no watch is served the *no check-ins* string, so the screen
	#     tells them nothing is on file while the record beside it says otherwise.
	('a watched-out subject is told nothing is on file', S,
	 "			note=window.note if window is not None else checkin(lang, 'no_watch'),",
	 "			note=window.note if window is not None else checkin(lang, 'no_checkins'),",
	 'test_a_point_that_opens_no_watch_starts_no_window'),

	# 12. A subject with no check-ins is answered with an empty list instead of a refusal, so "we
	#     hold nothing about you" and "we hold a clean record" render identically.
	('no check-ins is answered with an empty list', S,
	 "			return CheckInFollowUp(\n				subject_ref=subject_ref, attendance=None, schedule=[], window=None,",
	 "			return CheckInFollowUp(\n				subject_ref=subject_ref, attendance=[], schedule=[], window=None,",
	 'test_a_subject_with_no_check_ins_is_told_so'),

	# 13. The check-in string path stops falling back through `answerable`, so a Dholuo reader is
	#     served English without being told — the one thing §ACC-002 refuses to allow.
	('the check-in fallback stops going through answerable', T,
	 "	return CHECKIN_STRINGS[answerable(lang)][key].format(**fields)",
	 "	return CHECKIN_STRINGS[lang][key].format(**fields)",
	 'test_the_question_is_served_in_the_language_asked_for'),

	# 14. An unknown key returns a placeholder instead of raising, so a screen renders a literal
	#     `{day}` where the question should be and nothing reports the missing string.
	('an unknown check-in string returns a placeholder', T,
	 "	assert key in CHECKIN_STRINGS['en'], f'unknown check-in string {key}'",
	 "	assert True or key in CHECKIN_STRINGS['en'], f'unknown check-in string {key}'",
	 'test_an_unknown_checkin_string_is_refused'),

	# 15. The follow-up route loses its guard, so the `subject_ref` in the path is whoever the caller
	#     typed — the most identifying row this module holds, readable by anyone with a token.
	('the follow-up route loses its guard', G,
	 "	async def location_checkin_follow_up(subject_ref: str, lang: str = 'en', now_ms: int | None = None,\n	                                     _subject: str = Depends(require_self())) -> dict[str, object]:",
	 "	async def location_checkin_follow_up(subject_ref: str, lang: str = 'en', now_ms: int | None = None) -> dict[str, object]:",
	 'test_the_route_is_self_scoped'),

	# 16. The route ignores the `now_ms` it is given, so the window's arithmetic runs against the wall
	#     clock and the record a person's prompt fell due on cannot be asked for at all.
	('the route ignores the clock it is given', G,
	 "		return location.follow_up(subject_ref, now_ms, lang).model_dump(mode='json')",
	 "		return location.follow_up(subject_ref, None, lang).model_dump(mode='json')",
	 'test_the_route_serves_the_three_uses'),

	# 17. The question stops being day-specific, so five scheduled asks carry one sentence between
	#     them and the person is asked the same thing on day 1 and day 21.
	('every scheduled day asks the same question', S,
	 "				question=checkin(lang, 'prompt', day=day),",
	 "				question=checkin(lang, 'prompt', day=1),",
	 'test_every_step_carries_the_question_it_asks'),

	# 18b. The language the answer was built in stops being reported, so a Dholuo reader is served
	#      English and told nothing — the silent fallback `answerable` exists to make impossible.
	('the served language stops being reported', S,
	 "			next_due_iso=next_due, served_in=answerable(lang),",
	 "			next_due_iso=next_due, served_in=lang,",
	 'test_a_language_with_no_table_is_served_english_and_says_so'),

	# 18. A kind is dropped from `WATCH_KINDS` while its guidance still promises 21 days, so a border
	#     post is logged and no window opens — the app breaking a promise it printed on the screen.
	#     The import-time assert is the gate, so this one fails at collection.
	('a watched kind is dropped from WATCH_KINDS', V,
	 "WATCH_KINDS: tuple[str, ...] = ('border_post', 'event')",
	 "WATCH_KINDS: tuple[str, ...] = ('border_post',)",
	 'test_the_kinds_that_open_a_watch_are_the_kinds_whose_guidance_says_so'),

	# 19. The drift runs the other way: a guidance line gains a 21-day promise for a kind that opens
	#     no window, so the app prints a clock it will not run. This is the same guard as #18 from the
	#     other side, and the reason the assert compares sets rather than one direction of them.
	('a guidance line promises a window no kind opens', S,
	 "		'school': 'School screening point. Report fever before entering.',",
	 "		'school': 'School screening point. Report fever before entering. Watch for 21 days.',",
	 'test_the_kinds_that_open_a_watch_are_the_kinds_whose_guidance_says_so'),
]


def _node(canary_node: str) -> str:
	return canary_node if '/' in canary_node else f'tests/ci/test_loc004.py::{canary_node}'


_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only',
	'tests/ci/test_loc004.py'],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_loc004.{path.name}.bak')
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
