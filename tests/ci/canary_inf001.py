"""Canaries for tests/ci/test_inf001.py and tests/ci/test_county_adjacency.py.

§INF-001's three missing Displays are each a *shape* of defect that renders as working code, which
is why each is canaried rather than argued:

* The trend was the word nobody could compute, and the cheap fix — a `trend: str` field the caller
  sets — passes every test that reads the payload. Canary #2 makes the word settable.
* "Affected sub-counties" was missing because nothing carried a sub-county. The cheap fix is a list
  of names with no case behind them, which puts a place on a life-safety screen that has nothing to
  report. Canary #6 removes the refusal.
* "Service status" was a *read with no producer*, and this unit's job was the join. Canary #10 drops
  the statuses from the assembled dashboard, which is the §INF-007 defect restored one level up: the
  producer runs, the route works, and the screen that was supposed to show it is empty.

The canaries worth reading as a set are #1, #4 and #11. #1 makes the previous period the caller's
memory rather than the earlier row, which is how a trend becomes a transcription. #4 shifts a
correction into `previous_*`, which invents an outbreak event caused by someone fixing a typo. #11
breaks the border table by one pair, which is what a hand edit does.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary that
passes is a bug in the canary, so a MISSED line is a failure of this script.

**The `__pycache__` purge below is load-bearing, and it was found by watching this script disagree
with itself.** Canaries #7 and #8 mutate different methods — the sub-county read and the case-count
read — and the two edits happen to be the *same byte length*, because both remove a
`X_county == county and (` of exactly 24 characters. CPython validates a `.pyc` on (source mtime,
source size), both of which are recorded to a coarse granularity, so when the two writes landed in
the same second the second canary's pytest run reused the *first* canary's bytecode: `case_counts`
was never mutated, the test passed, and the script reported a gate it had never pointed anywhere.
It fired 19/19 on most runs and 18/19 on others, which is the signature — a canary that is
sometimes blind is blind. Deleting the module's bytecode cache before each run makes the run read
the source it was given.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
V = ROOT / 'src/afya/info/views.py'
S = ROOT / 'src/afya/info/service.py'
C = ROOT / 'src/afya/info/counties.py'
G = ROOT / 'src/afya/service.py'

CANARIES = [
	# 1. The previous period stops being carried forward, so the trend is computed against whatever
	#    the caller remembered rather than against the row already on file. Every later report reads
	#    "new" and a rising outbreak is reported as a first report, forever.
	('the previous period is not carried forward', S,
	 "		if counts.previous_confirmed is None and stored is not None and stored.as_of_iso != counts.as_of_iso:\n			updates = {'previous_confirmed': stored.confirmed, 'previous_suspected': stored.suspected}",
	 "		if False:\n			updates = {}",
	 'test_the_trend_is_derived_and_cannot_be_typed'),

	# 2. The trend stops being a computed field, so it is neither served nor dropped from an incoming
	#    mapping — the API's own output becomes a 422 against the API's own input, which is the exact
	#    failure `DerivedFields` exists to prevent.
	('the trend stops being a computed field', V,
	 "	@computed_field  # type: ignore[prop-decorator]\n	@property\n	def trend(self) -> str:",
	 "	@property\n	def trend(self) -> str:",
	 'test_the_trend_is_derived_and_cannot_be_typed'),

	# 3. `suspected` is dropped out of the trend, so a week where the suspected count tripled and the
	#    confirmed count held still is reported as steady — the one distinction a reader of an
	#    outbreak dashboard is making, erased from the word at the top of it.
	('the trend ignores suspected cases', V,
	 "		delta = (self.confirmed + self.suspected) - (previous_confirmed + previous_suspected)",
	 "		delta = self.confirmed - previous_confirmed",
	 'test_the_trend_is_derived_and_cannot_be_typed'),

	# 4. A correction to the period on file is treated as a new period, so re-posting the same date
	#    with a fixed figure makes the dashboard report an epidemiological event that did not happen.
	('a correction becomes a new period', S,
	 "		if counts.previous_confirmed is None and stored is not None and stored.as_of_iso != counts.as_of_iso:",
	 "		if counts.previous_confirmed is None and stored is not None:",
	 'test_a_correction_to_the_period_on_file_does_not_become_a_change_in_the_outbreak'),

	# 5. A half-supplied comparison is accepted, so a trend is computed from a period whose other
	#    count nobody gave — the word then rests on a number that does not exist.
	('half a comparison period is accepted', V,
	 "		assert (self.previous_confirmed is None) == (self.previous_suspected is None), \\",
	 "		assert True, \\",
	 'test_a_previous_period_is_known_for_both_counts_or_neither'),

	# 6. The "affected" refusal goes, so a sub-county with no case and no location can be listed —
	#    a place name on a life-safety screen with nothing behind it.
	('an empty sub-county is accepted', V,
	 "		assert self.confirmed or self.suspected or self.locations, (",
	 "		assert True or self.confirmed or self.suspected or self.locations, (",
	 'test_an_affected_sub_county_with_nothing_to_report_is_refused'),

	# 7. The sub-county read stops filtering by county, so Busia's dashboard lists Kisumu's areas —
	#    the reader is told the outbreak is somewhere it is not.
	('the sub-county read ignores the county', S,
	 "		        if s_county == county and (disease is None or s.disease == disease)]",
	 "		        if (disease is None or s.disease == disease)]",
	 'test_the_sub_counties_are_the_countys_own_and_ordered_by_how_affected_they_are'),

	# 8. The case-count read stops filtering by county, the same defect one Display up.
	('the case-count read ignores the county', S,
	 "		        if c_county == county and (disease is None or c.disease == disease)]",
	 "		        if (disease is None or c.disease == disease)]",
	 'test_the_counts_are_per_disease_because_the_section_says_other_diseases'),

	# 9. The sub-county read stops filtering by disease, so an Ebola dashboard lists cholera areas as
	#    Ebola-affected — the section's first Display is multi-disease and this is where it matters.
	('the sub-county read ignores the disease', S,
	 "		        if s_county == county and (disease is None or s.disease == disease)]",
	 "		        if s_county == county]",
	 'test_the_sub_counties_are_the_countys_own_and_ordered_by_how_affected_they_are'),

	# 10. The dashboard stops carrying §INF-007's service statuses, which is the "read with no
	#     producer" defect one level up: the producer runs, the route answers, and the screen that was
	#     supposed to show the fact is empty.
	('the dashboard drops the service statuses', G,
	 "			[s.model_dump(mode='json') for s in alerts.service_status(county)],",
	 "			[],",
	 'test_the_dashboard_is_served_end_to_end_with_the_service_status_the_other_feed_produces'),

	# 11. The border table loses one *side* of a pair, which is what a hand edit does — and every
	#     count and total still passes, because the row is a list of names and nothing adds them up.
	#     This is the shape the whole test file exists for: an asymmetric row puts Bungoma on Busia's
	#     dashboard while Busia is missing from Bungoma's, and both screens look right alone.
	('the border table loses one side of a pair', C,
	 "	'Busia': ('Bungoma', 'Kakamega', 'Siaya',),",
	 "	'Busia': ('Bungoma', 'Siaya',),",
	 'test_the_derivation_reproduces_the_module'),

	# 12. The neighbouring counties are dropped from the dashboard, so the section's Description —
	#     "in the user's county **and neighbouring counties**" — is answered with the narrower question.
	('the neighbouring counties are dropped', S,
	 "			neighbouring=[self.dashboard(n) for n in neighbours(county)],",
	 "			neighbouring=[],",
	 'test_the_dashboard_carries_all_seven_displays_and_stays_flat'),

	# 13. A neighbouring county is served with the *caller's* risk level, which looks exactly like a
	#     correct answer on a screen and tells a reader the outbreak is the same next door.
	('a neighbour wears the caller risk', S,
	 "			neighbouring=[self.dashboard(n) for n in neighbours(county)],",
	 "			neighbouring=[self.dashboard(n).model_copy(update={'risk_level': self.dashboard(county).risk_level, 'active_signals': self.dashboard(county).active_signals}) for n in neighbours(county)],",
	 'test_a_neighbouring_county_is_served_with_its_own_risk_and_its_own_stamp'),

	# 14. The path/body county agreement goes, so a caller can file Bungoma's counts against Busia and
	#     the dashboard contradicts the report it was built from with nothing to point at in between.
	('the route stops checking the county agrees', G,
	 "		if counts.county != county:\n			raise HTTPException(\n				status_code=422,\n				detail=f'body names county {counts.county!r}, path names {county!r}')",
	 "		pass",
	 'test_recording_counts_and_areas_is_guarded_and_the_two_counties_must_agree'),

	# 15. The write loses its guard, so anyone can put a number on a public outbreak dashboard.
	('recording counts loses its guard', G,
	 "	async def info_record_case_counts(county: str, counts: CaseCounts,\n			_subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, object]:",
	 "	async def info_record_case_counts(county: str, counts: CaseCounts) -> dict[str, object]:",
	 'test_recording_counts_and_areas_is_guarded_and_the_two_counties_must_agree'),

	# 16. Re-reporting a sub-county appends instead of superseding, so a place that had two cases and
	#     now has five is listed twice and the reader has to work out which is today's.
	('a sub-county is appended, not superseded', S,
	 "		self._sub_counties[(status.county, status.sub_county, status.disease)] = status",
	 "		self._sub_counties[(status.county, status.sub_county, status.disease, status.as_of_iso)] = status",
	 'test_re_reporting_a_sub_county_supersedes_it_rather_than_listing_it_twice'),

	# 17. The sub-county list stops being ordered by how affected a place is, so the reader scanning
	#     for the worst area gets whatever order the dict happened to hold.
	('the sub-county order stops meaning anything', S,
	 "		return sorted(rows, key=lambda s: (-(s.confirmed + s.suspected), s.sub_county))",
	 "		return sorted(rows, key=lambda s: s.sub_county)",
	 'test_the_sub_counties_are_the_countys_own_and_ordered_by_how_affected_they_are'),

	# 18. The served payload nests the risk row instead of flattening it, so every existing client
	#     reads `risk_level` as absent and draws an unassessed county.
	('the served payload nests the risk row', V,
	 "			**self.risk.model_dump(mode='json'),\n			'updated_line': updated_line,",
	 "			'risk': self.risk.model_dump(mode='json'),\n			'updated_line': updated_line,",
	 'test_the_dashboard_carries_all_seven_displays_and_stays_flat'),

	# 19. An unknown county raises instead of answering with an empty neighbour list, so the dashboard
	#     500s on the one input the risk read it replaces handles.
	('an unknown county raises', C,
	 "	return ADJACENCY.get(county, ())",
	 "	return ADJACENCY[county]",
	 'test_an_unknown_county_answers_with_nothing_rather_than_raising'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_inf001.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	# See the module docstring: a same-second write of the same size reuses the previous canary's
	# bytecode, and the canary then tests code it never mutated. Purged for the file just written.
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	if node.startswith('tests/'):
		target = node
	elif 'adjacency' in node or node.startswith('test_the_derivation') or node.startswith('test_an_unknown_county_answers'):
		target = f'tests/ci/test_county_adjacency.py::{node}'
	else:
		target = f'tests/ci/test_inf001.py::{node}'
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
