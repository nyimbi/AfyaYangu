"""Canaries for tests/ci/test_ai001.py — each gate pointed at a planted defect and watched to fail.

§AI-001 had three carriers missing and two of them were the *same* failure wearing opposite coats.
`geofence_entries` and `search_signals` were quantities the product already recorded and never passed
to the model (a signal with no consumer). `build_resource_feed` rendered §18.3's
`resource_deployment` feed and nothing produced its recommendations (a consumer with no signal).
Both render as working code, which is why each is canaried rather than argued.

The canaries worth reading as a set are #1, #4 and #9. #1 drops an Input from the score while
leaving it on the model, which is the exact shape of the defect this unit closed — a field that
exists and is never read. #4 builds a cluster from cells that have not cleared the min-cell floor,
which re-identifies through the back door exactly what the floor exists to prevent. #9 makes a
recommendation action itself, which is the system deploying teams.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary that
passes is a bug in the canary, so a MISSED line is a failure of this script.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
V = ROOT / 'src/afya/ai/views.py'
S = ROOT / 'src/afya/ai/service.py'
G = ROOT / 'src/afya/service.py'

CANARIES = [
	# 1. `search_signals` stays on the model and comes out of the score. This is the defect the unit
	#    closed, restored: a field the section names, the cell carries, and nothing reads.
	('an input is on the cell and not in the score', S,
	 "			+ self._WEIGHT_SEARCH * cell.search_signals / pop",
	 "			+ 0.0 * cell.search_signals / pop",
	 'test_every_input_moves_the_score_and_fever_dominates'),

	# 2. The geofence term comes out of the score, so §AI-001's second Input is carried and unread.
	('geofence entries stop moving the score', S,
	 "			+ self._WEIGHT_GEOFENCE * cell.geofence_entries / pop",
	 "			+ 0.0 * cell.geofence_entries / pop",
	 'test_every_input_moves_the_score_and_fever_dominates'),

	# 3. The score adds raw counts instead of rates, so the biggest cell ranks first every time and
	#    the model is measuring population, not epidemiology.
	('the score counts instead of rating', S,
	 "			self._WEIGHT_FEVER * cell.fever_reports / pop",
	 "			self._WEIGHT_FEVER * cell.fever_reports",
	 'test_every_input_moves_the_score_and_fever_dominates'),

	# 4. Clustering runs over every eligible cell rather than the ones above baseline, so a dense map
	#    becomes one country-spanning cluster that names every cell and therefore identifies none.
	('every cell is clustered, not the hotspots', S,
	 "		clusters = self._cluster([c for c in eligible if any(h.cell_id == c.cell_id for h in hotspots)])",
	 "		clusters = self._cluster(eligible)",
	 'test_one_cell_above_baseline_is_a_hotspot_and_not_a_cluster'),

	# 5. The cluster radius is widened to the whole planet, so two cells at opposite ends of the
	#    country are joined into a cluster no response team could surround.
	('the cluster radius covers everything', S,
	 "	CLUSTER_RADIUS_KM = 5.0",
	 "	CLUSTER_RADIUS_KM = 20_000.0",
	 'test_cells_further_apart_than_the_radius_are_not_one_cluster'),

	# 6. A cell with no position is dropped rather than reported, so a cluster reads as complete when
	#    it could not tell whether one of its cells touched the others.
	('an unlinkable cell is silently dropped', S,
	 "					+ (f' {unlocated} further cell(s) carried no position and could not be linked.' if unlocated else '')",
	 "					+ ''",
	 'test_a_cell_with_no_position_is_reported_as_unlinkable_not_dropped'),

	# 7. A cluster of one is emitted, so the count a county reads as "how many events" is inflated by
	#    the cells that are already listed as hotspots.
	('a lone cell becomes a cluster', S,
	 "			if len(members) < 2:\n				continue  # one cell is a hotspot, which the map already carries",
	 "			if len(members) < 1:\n				continue  # one cell is a hotspot, which the map already carries",
	 'test_one_cell_above_baseline_is_a_hotspot_and_not_a_cluster'),

	# 8. Every hotspot county is treated as a cluster county, so a county whose cells are isolated is
	#    told to send a rapid response team — advice with no cluster behind it. The patch lands on the
	#    loop that builds `per_county`, not on the `lone` line below it: mutating the later line only
	#    changes the communication rows, and the team rows are already emitted by then.
	('a lone hotspot gets a team', S,
	 "		for cluster in clusters:\n			for county in cluster.counties:\n				per_county.setdefault(county, []).append(cluster.cluster_id)",
	 "		for cluster in clusters:\n			for county in cluster.counties:\n				per_county.setdefault(county, []).append(cluster.cluster_id)\n		for h in hotspots:\n			per_county.setdefault(h.county, []).append('TC-' + h.cell_id)",
	 'test_a_lone_hotspot_gets_communication_and_not_a_deployment'),

	# 9. A recommendation may action itself, so the system deploys teams — the one thing §19.3's
	#    human-in-the-loop rule forbids.
	('a recommendation can action itself', V,
	 "		assert not self.auto_actioned, (",
	 "		assert True or not self.auto_actioned, (",
	 'test_a_recommendation_cannot_action_itself'),

	# 10. `quantity` is invented where the section's arithmetic does not determine one, so a modelled
	#     number wears the authority of a recommendation.
	('a quantity is invented for the kits', S,
	 "				county=county, resource='test_kits', quantity=None, unit='kits', rationale=(",
	 "				county=county, resource='test_kits', quantity=500, unit='kits', rationale=(",
	 'test_a_cluster_recommends_a_team_and_a_quantity_is_not_invented'),

	# 11. The deploy route fabricates a recommendation instead of deriving it from the finding, so a
	#     caller can put a rapid-response team on the wire with nothing behind it.
	('the deploy route invents a recommendation', G,
	 "			recommendations = [r.model_dump(mode='json') for r in ai.hotspots(cells).recommendations]",
	 "			recommendations = [{'county': cells[0].county, 'resource': 'rapid_response_team', 'quantity': 9, 'unit': 'team(s)', 'rationale': 'requested'}]\n			_ = ai.hotspots(cells)",
	 'test_the_deploy_route_answers_a_map_with_nothing_to_recommend'),

	# 12. The bridge reads the search ledger into `facility_reports`, so two of the section's five
	#     Inputs become one number wearing two names and the reason reports it twice.
	('search signals are counted as facility reports', S,
	 "			facility_reports=facility_reports, geofence_entries=geofence_entries,",
	 "			facility_reports=_count('facility_search', 'medicine_search'), geofence_entries=geofence_entries,",
	 'test_the_bridge_keeps_facility_reports_and_search_signals_apart'),

	# 13. The bridge pre-filters below the floor, so the suppression report under-counts and a screen
	#     says a deployment carries nothing when it withheld a cell.
	('the bridge pre-filters the floor', S,
	 "		assert county and cell_id, 'a cell needs a county and an id'",
	 "		assert population >= MIN_CELL_SIZE, 'below the floor'\n		assert county and cell_id, 'a cell needs a county and an id'",
	 'test_the_bridge_reads_the_signal_ledger_the_product_already_writes'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_ai001.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	target = node if node.startswith('tests/') else f'tests/ci/test_ai001.py::{node}'
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
