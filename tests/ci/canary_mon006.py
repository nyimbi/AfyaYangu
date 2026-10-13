"""Canaries for tests/ci/test_mon006.py.

§MON-006's three missing bullets are each a shape that renders as working code:

* **"AQI for user's location"** was missing because nothing computed an index. The cheap fix is a
  number derived from the reading by *some* arithmetic, which passes any test that only reads the
  payload — so canary #1 drops the truncation the source requires, #2 extrapolates past the top of
  the scale, #3 keeps the reading and the index free to disagree, and #4 keeps the index and the
  category free to disagree. #1 is the quiet one: it changes an answer only at values just under a
  band boundary, which is exactly where a category changes.
* **"best times for outdoor activity"** was missing because nothing named an hour. The cheap fix is
  a window named from the daily figure, which is canary #6 — an hour nobody measured. #5 names one
  hour instead of all of them at the best level, and #7 lets the hours keep the order they arrived
  in, which on an evening-first series is a day that runs backwards.
* **"pollution source information"** was missing because nothing named a source. The cheap fix is a
  source asserted with no evidence, which is canary #8, and it is the one with a health consequence:
  a person told the smoke is from traffic does not think to stop burning rubbish in the yard.

The canaries worth reading as a set are #1, #6 and #8. #1 is the boundary. #6 is the invented hour.
#8 is the guess that reads like an answer.

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
V = ROOT / 'src/afya/alerts/views.py'
S = ROOT / 'src/afya/alerts/service.py'
G = ROOT / 'src/afya/service.py'

CANARIES = [
	# 1. The truncation goes, so the band is chosen from an untruncated value. Quiet by construction:
	#    it changes nothing at a whole or half decimal, and changes the *category* at 35.45 — the
	#    value the source's own boundaries put in the band below.
	('the index is computed from the untruncated reading', V,
	 "	value = int(pm25 * 10) / 10",
	 "	value = pm25",
	 'test_truncation_happens_before_the_lookup'),

	# 2. The top of the scale is extrapolated instead of capped, so a reading of 600 is served an
	#    index no category defines and no guidance is written against.
	('the top of the scale is extrapolated', V,
	 "	return 500",
	 "	low, high, aqi_low, aqi_high = PM25_BREAKPOINTS[-1]\n	return round((aqi_high - aqi_low) / (high - low) * (value - low) + aqi_low)",
	 'test_a_reading_above_the_table_is_capped_rather_than_extrapolated'),

	# 3. The reading and the index stop being checked against each other, so a caller can post a
	#    PM2.5 of 120 with an index of 40 and the payload carries two answers to one question.
	('the index stops agreeing with the reading', V,
	 "		assert self.aqi == pm25_aqi(self.pm25), (",
	 "		assert True or self.aqi == pm25_aqi(self.pm25), (",
	 'test_the_index_cannot_be_asserted_against_the_reading'),

	# 4. The category stops agreeing with the index, so a screen prints "moderate" beside a number
	#    that says 184.
	('the category stops agreeing with the index', V,
	 "		assert expected == self.category, (",
	 "		assert True or expected == self.category, (",
	 'test_the_category_agrees_with_the_index'),

	# 5. The window names a single hour rather than every hour at the best level, so a person with an
	#    appointment at nine is told about six and left to guess.
	('the window names one hour instead of all of them', S,
	 "		hours = sorted(h for h, pm25 in hourly if pm25_aqi(pm25) == best)",
	 "		hours = [min(h for h, pm25 in hourly if pm25_aqi(pm25) == best)]",
	 'test_every_hour_at_the_best_level_is_offered_and_not_just_one'),

	# 6. The window is invented from the daily figure when no hourly series exists. The hour named is
	#    an hour nobody measured — the fabrication §MON-006's own Data sources clause is about.
	('the window is invented when no hourly series exists', S,
	 "			self.outdoor_window(a, location, hourly) if hourly\n			else OutdoorWindow(\n				county=a.county, location=location, hours=[], best_aqi=None,\n				advise='No hourly readings for today, so no time of day can be called better than another.',\n			)",
	 "			self.outdoor_window(a, location, hourly) if hourly\n			else OutdoorWindow(\n				county=a.county, location=location, hours=[6, 7, 8], best_aqi=a.aqi,\n				advise='Early morning is usually the cleanest time to be outside.',\n			)",
	 'test_a_day_with_no_hourly_readings_gets_an_empty_window_that_says_so'),

	# 7. The hours keep the order the readings arrived in, so an evening-first series produces a day
	#    that runs backwards.
	('the hours keep the order they arrived in', S,
	 "		hours = sorted(h for h, pm25 in hourly if pm25_aqi(pm25) == best)",
	 "		hours = [h for h, pm25 in hourly if pm25_aqi(pm25) == best]",
	 'test_the_window_is_ordered_even_when_the_readings_arrive_unordered'),

	# 8. A source is named with no evidence for it. The one with a health consequence: a person told
	#    the smoke is traffic does not think to stop burning rubbish in the yard, and the source they
	#    could have acted on is the one the screen ruled out.
	('a source is named with no evidence', S,
	 "		if traffic_nearby:\n			likely.append('road traffic')",
	 "		likely.append('road traffic')",
	 'test_a_reported_source_is_named_and_an_unreported_one_is_not'),

	# 9. The mask guidance drops what a mask does not do, so a person in a cloth mask reads that they
	#    are protected. WHO's guidelines deliberately do not make this recommendation, so the honesty
	#    of the sentence is the whole of what the repo adds to it.
	('the mask guidance drops what a mask does not do', S,
	 "				'A cloth or surgical mask helps much less. A mask is not a substitute for staying '\n				'out of the smoke — the best protection is not being in it.'",
	 "				'A cloth or surgical mask helps much less.'",
	 'test_mask_guidance_says_what_a_mask_does_not_do'),

	# 10. The advisory stops being the existing string, so the same reading is described two ways on
	#     two surfaces and the mobile catalogue's copy drifts from the route's.
	('the advisory becomes a second wording', S,
	 "			advisory=self.air_alert(a), mask_guidance=self.mask_guidance(a),",
	 "			advisory=f'Air quality index {self.air_reading(a, location).aqi} for {location}.', mask_guidance=self.mask_guidance(a),",
	 'test_the_advisory_is_the_existing_one_and_not_a_second_wording'),

	# 11. The window stops saying when no hour is clean, so a person on a uniformly bad day is sent
	#     outdoors by advice that reads like a window worth taking.
	('the window stops saying no hour is clean', S,
	 "			advise = (\n				'No hour today is clean. These are the least bad — keep it short and avoid exertion.'\n			)",
	 "			advise = 'Go out in these hours; they are the cleanest of the day.'",
	 'test_the_advice_says_when_no_hour_is_actually_clean'),

	# 12. The route stops requiring a location, so the section's "AQI for user's location" is served
	#     for a place nobody named.
	('the route stops requiring a location', G,
	 "	async def environment_air(a: AirQuality, location: str, hourly: str | None = None) -> dict[str, object]:",
	 "	async def environment_air(a: AirQuality, location: str = 'unspecified', hourly: str | None = None) -> dict[str, object]:",
	 'test_the_air_route_requires_a_location'),

	# 13. The route drops the hourly series, so the window is empty however many readings the caller
	#     sent — the feature silently gone from the served payload while the service still has it.
	('the route drops the hourly series', G,
	 "		return alerts.air_quality_guidance(a, location, series or None).model_dump(mode='json')",
	 "		return alerts.air_quality_guidance(a, location).model_dump(mode='json')",
	 'test_the_air_route_serves_the_whole_answer'),

	# 14. A window is served with an index and no hours behind it, so a screen renders a number that
	#     belongs to no time.
	('a window carries an index with no hours', V,
	 "		assert (self.best_aqi is None) == (not self.hours), (",
	 "		assert True or (self.best_aqi is None) == (not self.hours), (",
	 'test_a_window_with_hours_and_no_index_is_refused'),

	# 15. A source list carries an unnamed entry, so a screen renders a blank where a source should
	#     be and a person reads a row they cannot act on.
	('an unnamed source passes the list check', V,
	 "		assert all(s.strip() for s in self.likely), 'an unnamed source in the list'",
	 "		assert True or all(s.strip() for s in self.likely), 'an unnamed source in the list'",
	 'test_an_unnamed_source_in_the_list_is_refused'),

	# 16. The empty-window path asserts nothing, so a caller that meant to send readings and sent none
	#     gets a window instead of a refusal.
	('a day with no readings gets a window', S,
	 "		assert hourly, 'a day with no hourly readings has no window to name'",
	 "		hourly = hourly or [(6, a.pm25)]",
	 'test_a_day_with_no_readings_at_all_is_refused'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_mon006.{path.name}.bak')
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
			f'tests/ci/test_mon006.py::{node}'], cwd=ROOT, capture_output=True, text=True)
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
