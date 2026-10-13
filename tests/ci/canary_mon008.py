"""Canaries for tests/ci/test_mon008.py.

§MON-008's two missing bullets were both closed by giving a name some data: `in_season` behind the
seasonal field, and a `FacilityKind` member behind the therapeutic-feeding bullet. Both are the
kind of change that renders as working code when it is wrong — a month still returns a list, a
finder still returns sites. Each canary below is a plausible implementation that answers
incorrectly:

* **The all-year flag ignored** (#1) — the five crops the source marks `all_year` drop out of every
  month, so the answer is a season with cassava missing from it.
* **The month filter inverted** (#2) — `not in`, so a month serves exactly the crops that are *not*
  harvested then. The list is the right length and every entry is wrong.
* **A month accepted with no bounds check** (#3) — month 13 serves the all-year crops and nothing
  else, which reads as a thin season rather than as a rejected input.
* **The two lists merged** (#4) — the age list and the season in one field, so a parent cannot tell
  which entry is the age recommendation and which is the harvest.
* **The finder filtering on the wrong `FacilityKind`** (#5) — a pharmacy served as a therapeutic
  feeding site, which is a wasted journey for a parent with a malnourished child.
* **The finder not ordering by distance** (#6) — `distance_km` is served, so an unordered list
  makes the field's own claim untrue.
* **The county filter dropped** (#7) — a parent in Kisumu sent to Siaya.
* **The limit ignored** (#8) — a finder that returns the whole registry, which is not a finder.
* **An empty county raising instead of answering** (#9) — "nothing is filed here" surfaced as an
  error, which collapses it with "there is no such programme".
* **The programme vocabulary collapsed to a per-site claim** (#10) — one programme asserted per
  row from a registry that does not record it, sending a child with complications to an
  out-patient queue.
* **The label replaced with the bare slug** (#11) — the vocabulary present in the code and gone
  from what the screen reads, which is the standing constraint on served strings.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script. The `__pycache__`
purge after each write is load-bearing for the reason `canary_inf001.py` documents: two canaries
mutating two files with same-length edits in the same second make CPython reuse the previous
canary's bytecode, and the gate then reports a mutation it never made.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
V = ROOT / 'src/afya/monitoring/views.py'
S = ROOT / 'src/afya/monitoring/service.py'
F = ROOT / 'src/afya/facilities/views.py'
G = ROOT / 'src/afya/service.py'

CANARIES = [
	# 1. The source's `all_year` flag is read and then ignored, so the five crops it marks
	#    harvestable throughout the year are absent from every month — a season with no cassava.
	('the all-year flag is ignored', S,
	 "			if month in months or all_year",
	 "			if month in months",
	 'test_a_month_serves_what_is_harvested_then'),

	# 2. The month test inverted. The list is the right length and every entry is a crop that is not
	#    in season — the failure a spot-check on length alone cannot see.
	('the month filter is inverted', S,
	 "			if month in months or all_year",
	 "			if month not in months or all_year",
	 'test_a_month_serves_what_is_harvested_then'),

	# 3. No bounds check, so month 13 is answered rather than refused. It returns the all-year crops
	#    and nothing else, which reads as a thin season.
	('a month outside the year is accepted', S,
	 "		assert 1 <= month <= 12, f'{month} is not a month'",
	 "		assert True or 1 <= month <= 12, f'{month} is not a month'",
	 'test_a_month_that_is_not_a_month_is_refused'),

	# 4. The two lists merged into one field. The parent reading it cannot tell which entry is the
	#    age recommendation and which is the harvest — and the age list names avocado and small
	#    fish, which the calendar does not cover at all.
	('the two lists are merged', S,
	 "			month=month, in_season=in_season, calendar_source=SEASONAL_CALENDAR_SOURCE,",
	 "			month=month, in_season=sorted(set(band[2]) | set(in_season)),\n			calendar_source=SEASONAL_CALENDAR_SOURCE,",
	 'test_the_two_lists_are_not_merged'),

	# 5. The finder reads the wrong kind, so a pharmacy is served as a therapeutic feeding site. The
	#    list is non-empty and plausible, which is why it renders as working code.
	('the finder filters on the wrong facility kind', S,
	 "		        if f.county == county and f.kind is FacilityKind.therapeutic_feeding]",
	 "		        if f.county == county and f.kind is FacilityKind.pharmacy]",
	 'test_only_therapeutic_feeding_sites_are_returned_and_the_nearest_first'),

	# 6. The distance ordering removed. `distance_km` is still served, so the payload claims a
	#    nearest-first order it does not have.
	('the finder does not order by distance', S,
	 "		ranked = sorted(((f, haversine_km(lat, lon, f.lat, f.lon)) for f in pool), key=lambda p: p[1])",
	 "		ranked = sorted(((f, haversine_km(lat, lon, f.lat, f.lon)) for f in pool), key=lambda p: p[0].facility_id, reverse=True)",
	 'test_only_therapeutic_feeding_sites_are_returned_and_the_nearest_first'),

	# 7. The county filter dropped, so a parent in Kisumu is sent to a site in Siaya.
	('the county filter is dropped', S,
	 "		        if f.county == county and f.kind is FacilityKind.therapeutic_feeding]",
	 "		        if f.kind is FacilityKind.therapeutic_feeding]",
	 'test_a_site_in_another_county_is_not_served'),

	# 8. The limit ignored, so the finder returns the whole registry — which is a list, not a
	#    finder, and on a real registry is a screen nobody can read.
	('the limit is ignored', S,
	 "			for f, km in ranked[:limit]",
	 "			for f, km in ranked",
	 'test_the_finder_returns_at_most_the_limit_asked_for'),

	# 9. An empty county raises. "Nothing is filed here" becomes an error the screen shows where it
	#    should show a gap, which collapses it with "there is no such programme".
	('an empty county raises instead of answering', S,
	 "		if not pool:\n			self._log_info('no therapeutic feeding site filed', county=county)\n			return []",
	 "		if not pool:\n			raise AssertionError(f'no therapeutic feeding site in {county}')",
	 'test_a_county_with_nothing_filed_is_an_empty_list_not_a_refusal'),

	# 10. The programme vocabulary collapsed to a single per-site claim. The registry records *that*
	#     a facility is a therapeutic feeding site and not which programme it runs, so a child with
	#     complications is sent to an out-patient queue.
	('the programme vocabulary becomes a per-site claim', V,
	 "	programmes: list[dict[str, str]] = Field(\n		default_factory=lambda: [{'slug': s, 'label': lab, 'definition': d} for s, lab, d in IMAM_PROGRAMMES])",
	 "	programmes: list[dict[str, str]] = Field(\n		default_factory=lambda: [{'slug': s, 'label': lab, 'definition': d} for s, lab, d in IMAM_PROGRAMMES[:1]])",
	 'test_the_three_programmes_travel_with_every_site'),

	# 11. The label emptied to the bare slug, so the screen reads "therapeutic_feeding" where the
	#     IMAM description belongs. This is the standing constraint on served strings: an internal
	#     handle reaching the UI/UX, in the one field a parent actually reads.
	('the site label is emptied to the bare slug', V,
	 "THERAPEUTIC_FEEDING_LABEL = (\n	'A health facility running a therapeutic feeding programme for acute malnutrition, under '\n	\"Kenya's Integrated Management of Acute Malnutrition guidelines\"\n)",
	 "THERAPEUTIC_FEEDING_LABEL = 'therapeutic_feeding'",
	 'test_the_site_label_is_a_sentence_and_not_the_internal_slug'),

	# 12. The route stops passing the month, so the season is present in the service and absent from
	#     the served answer — the feature gone at the front door while the unit test over the
	#     service stays green.
	('the nutrition route drops the month', G,
	 "		return monitoring.nutrition_guidance(age_months, month).model_dump(mode='json')",
	 "		return monitoring.nutrition_guidance(age_months).model_dump(mode='json')",
	 'test_the_nutrition_route_serves_the_season_when_a_month_is_given'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_mon008.{path.name}.bak')
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
			f'tests/ci/test_mon008.py::{node}'], cwd=ROOT, capture_output=True, text=True)
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
