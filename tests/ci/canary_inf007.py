"""Canaries for §INF-007's status feed and §INF-006's directory rows — each gate pointed at a
planted defect and watched to fail.

Two sections share this file because their defects share a shape: §INF-007 was a *read with no
producer* (the route filtered the feed's `service` category and nothing ever wrote one), and
§INF-006's second and sixth Contents were *rows about the caller* (a county office, a CHW) that the
directory could not compose because `ChwProfile` carried no phone number at all. Both are failures
where the screen renders and answers nothing.

The canaries worth reading as a set are #4, #5 and #12. #4 stores a status without publishing it,
which is the original defect restored — the screen goes back to being permanently empty while the
status service looks like it is working. #5 lets an unverified status into the feed by writing the
flag rather than passing it, which is how a rule that lives in one place gets a second copy.
#12 drops the "no number, no row" gate, so the directory lists a CHW nobody can dial.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
V = ROOT / 'src/afya/alerts/views.py'
S = ROOT / 'src/afya/alerts/service.py'
G = ROOT / 'src/afya/service.py'
I = ROOT / 'src/afya/info/service.py'
C = ROOT / 'src/afya/chw/service.py'
W = ROOT / 'src/afya/chw/views.py'

CANARIES = [
	# 1. One state vocabulary for every kind, so a school can be "interrupted" and a market
	#    "restored". A status whose reader cannot map it onto a decision is a status that does not
	#    answer "can I go there today".
	('every kind accepts every state', V,
	 "		states = STATES_FOR[self.kind]\n		assert self.state in states, (",
	 "		states = tuple({s for v in STATES_FOR.values() for s in v})\n		assert self.state in states, (",
	 'test_a_state_the_kind_cannot_be_in_is_refused'),

	# 2. The section's own qualifier comes off, so a road closure that does not affect reaching care
	#    is carried by a feed whose whole purpose is answering whether the reader can reach care.
	('the road qualifier is dropped', V,
	 "		assert self.kind != 'road_closure' or self.affects_facility_access, (",
	 "		assert True or self.kind != 'road_closure' or self.affects_facility_access, (",
	 'test_the_road_qualifier_is_the_sections_and_is_enforced'),

	# 3. The headline stops naming the place, so the feed says "market closure — closed" and the
	#    reader cannot tell whether it is *their* market — the question they opened the screen for.
	('the headline loses the place', V,
	 "		return f'{self.name}: {self.kind.replace(\"_\", \" \")} — {self.state}'",
	 "		return f'{self.kind.replace(\"_\", \" \")} — {self.state}'",
	 'test_the_headline_names_the_place_and_the_state'),

	# 4. The producer stores and does not publish. This is the original defect exactly: the status
	#    service looks like it works, `service_status` answers, and the screen the route serves stays
	#    empty because nothing ever wrote a `service` feed item.
	('the status is stored without being published', S,
	 "		publish = getattr(feed, 'publish', None)",
	 "		publish = None",
	 'test_publishing_a_status_writes_the_feed_the_screen_reads'),

	# 5. The verification flag is written rather than passed, so an unverified status reaches the
	#    feed. §ALT-001's rule lives in the feed; a second copy of it here is a copy that can differ.
	('an unverified status reaches the feed', S,
	 "				verified=status.verified, published_iso=status.effective_iso))",
	 "				verified=True, published_iso=status.effective_iso))",
	 'test_an_unverified_status_never_reaches_the_feed'),

	# 6. A place that closed and reopened has two statuses instead of one, so the screen makes the
	#    reader work out which is current from two dates.
	('the status screen becomes a log', S,
	 "				latest[(s.kind, s.name)] = s",
	 "				latest[(s.kind, s.name + s.status_id)] = s",
	 'test_a_place_that_reopened_has_one_current_status_not_two'),

	# 7. The county filter stops filtering, so a caller asking about Busia is shown a Kisumu market
	#    as though it were near them.
	('the county filter stops filtering', S,
	 "			if county is None or s.county == county:",
	 "			if county is None or True:",
	 'test_the_county_filter_scopes_the_status_list'),

	# 8. The coverage report names one of the six, so the other five read as carried by a deployment
	#    that has no feed for them — a gap list that hides the gaps.
	('the coverage report names one kind', S,
	 "		counts = {k: 0 for k in SERVICE_STATUS_KINDS}",
	 "		counts = {k: 0 for k in ('market_closure',)}",
	 'test_the_coverage_report_names_all_six_and_counts_what_is_published'),

	# 9. The publish route loses its guard, so any caller can put a market closure in front of every
	#    phone in the county.
	('the publish route loses its guard', G,
	 "	async def alerting_publish_status(status: ServiceStatus,\n			_subject: str = Depends(require_scope('assigned'))) -> dict[str, object]:",
	 "	async def alerting_publish_status(status: ServiceStatus,\n			_subject: str | None = None) -> dict[str, object]:",
	 'test_the_route_publishes_and_the_same_route_reads_it_back'),

	# 10. The route stops passing the caller's county, so §INF-006's second Content is never
	#     composed however many offices the deployment has on file.
	('the route stops passing the county', G,
	 "		directory = info.hotline_directory(now_ms, lang, lat, lon, places, county, chw)",
	 "		directory = info.hotline_directory(now_ms, lang, lat, lon, places, None, chw)",
	 'test_registering_a_county_office_is_guarded_and_a_citizen_cannot_file_one'),

	# 11. Another county's office is served to a caller who named their own — the directory becomes
	#     a list of offices rather than an answer about the caller's.
	('another countys office is served', I,
	 "		number = self._county_offices.get(county)",
	 "		number = next(iter(self._county_offices.values()), None)",
	 'test_the_county_health_office_is_a_number_per_county_and_absent_without_one'),

	# 12. A CHW with no number on file is listed anyway. The row exists so a person can reach their
	#     worker; a name that cannot be dialled spends a screen slot on a life-safety page.
	('an unreachable CHW is listed', I,
	 "		if worker is None or not getattr(worker, 'phone', None):",
	 "		if worker is None:",
	 'test_the_chw_row_comes_from_the_provisioned_profile_and_is_absent_without_one'),

	# 13. `register_county_office` accepts an empty number, which `_county_office_rows` then reads as
	#     "not on file" — an operator believes they filed a number and the screen disagrees.
	('an empty county office number is stored', I,
	 "		assert county and number, 'a county office needs a county and a number'",
	 "		assert county is not None and number is not None, 'a county office needs a county and a number'",
	 'test_a_county_office_with_no_number_is_refused_rather_than_stored'),

	# 14. The profile loses the field that made the sixth Content answerable at all — the finding
	#     this section was: a CHW row was unanswerable even for a fully provisioned deployment.
	('the CHW profile loses its phone number', W,
	 "	phone: str | None = None",
	 "	# phone: str | None = None",
	 'test_the_chw_row_comes_from_the_provisioned_profile_and_is_absent_without_one'),

	# 15. `serving` asserts instead of answering, so a county with no worker is a 500 on a
	#     life-safety screen rather than a gap the directory can report.
	('a county with no CHW is an error', C,
	 "		return workers[0] if workers else None",
	 "		assert workers, 'no CHW provisioned for this county'\n		return workers[0]",
	 'test_the_chw_row_comes_from_the_provisioned_profile_and_is_absent_without_one'),

	# 16. The pick is no longer the lowest `chw_ref`, so a caller is shown a different worker on each
	#     refresh and the number they saved stops being the number they reach.
	('the CHW pick is not stable', C,
	 "		workers = sorted((w for w in self._chws.values() if w.county == county), key=lambda w: w.chw_ref)",
	 "		workers = sorted((w for w in self._chws.values() if w.county == county), key=lambda w: w.chw_ref, reverse=True)",
	 'test_the_chw_row_comes_from_the_provisioned_profile_and_is_absent_without_one'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_inf007.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	target = node if node.startswith('tests/') else f'tests/ci/test_inf007.py::{node}'
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
