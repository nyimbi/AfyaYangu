"""Canaries for tests/ci/test_rec006.py.

Both bullets of §REC-006 are the same shape the §MON-004 pair was — a fact the code already carried
and nothing that acted on it — and each canary below is a plausible implementation of the same
feature that answers the question wrongly. The two failure modes that matter most here are the ones
that produce a *plausible* wrong answer rather than an error:

* **Urgency read but not applied** (#1, #2, #9) — the field is on the request, so a filter that
  ignores it looks like working code and passes every test that only asks whether an alert was
  raised. #1 is the one that matters clinically: a routine need waking a donor at 3am spends the
  goodwill a donor list runs on. #2 is its mirror, a routine need reaching the compatible groups.
  #9 is the subtler shape — the walk implemented one hop deep, so `critical` and `urgent` reach the
  same counties and the table's top row is a value that decides nothing.
* **An ineligible donor invited to donate** (#3) — the alert is an invitation to break a safety
  interval that is about the donor, not about supply. `_eligible` is the shared rule, so a canary
  that bypasses it here reproduces the exact defect the audit row described: two callers of one rule
  disagreeing about the same donor.
* **An incompatible donor invited** (#4) — the dangerous direction. A donor brought to a facility to
  be turned away is worse than one not called, because it spends the one thing the list runs on.
* **The two OSM kinds collapsed** (#5, #6) — the source documents them as different things, so a
  finder that merges them puts a storage site at the top of a donor's distance-sorted list. #5
  collapses the finder's default, #6 collapses the enum the importer maps into.
* **The importer reads only the `amenity` key** (#7) — the shape the query would have had if the
  vocabulary had been assumed rather than read. The query finds the sites and the parser drops every
  one of them, which is a silent zero rather than an error.
* **The route forgets the adjacency table** (#8) — the wiring present in the service and absent from
  the front door, so "nearby" never means anything beyond the requesting county in production.

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
V = ROOT / 'src/afya/blood/views.py'
P = ROOT / 'src/afya/places/views.py'
O = ROOT / 'src/afya/integrations/overpass.py'
G = ROOT / 'src/afya/service.py'

CANARIES = [
	# 1. Urgency is read and then ignored: every request reaches the neighbours at full depth. A
	#    routine need wakes a donor in the next county for a unit the stock list already holds.
	('the urgency tables are flattened to full reach and depth', V,
	 "URGENCY_REACH: dict[str, int] = {'routine': 0, 'urgent': 1, 'critical': 2}",
	 "URGENCY_REACH: dict[str, int] = {'routine': 2, 'urgent': 1, 'critical': 2}",
	 'test_urgency_decides_the_reach_and_a_routine_request_does_not_wake_a_neighbour'),

	# 9. The walk is implemented one hop deep, so `critical` reaches exactly what `urgent` reaches.
	#    This is the defect the two-hop table exists to prevent and the one the first version of this
	#    work actually shipped: a reach value whose top row duplicates the middle one decides nothing.
	('the reach walk stops after one hop however far the table says', V,
	 "		for step in range(1, hops + 1):",
	 "		for step in range(1, min(hops, 1) + 1):",
	 'test_urgency_decides_the_reach_and_a_routine_request_does_not_wake_a_neighbour'),

	# 2. The depth is flattened instead: a routine request reaches the compatible groups, so the O-
	#    donor is woken for a B+ need that the exact group covers. The same test catches it from the
	#    other side, which is why one node names both tables.
	('the depth table is flattened so a routine request reaches every compatible group', V,
	 "URGENCY_DEPTH: dict[str, int] = {'routine': 0, 'urgent': 2, 'critical': 2}",
	 "URGENCY_DEPTH: dict[str, int] = {'routine': 2, 'urgent': 2, 'critical': 2}",
	 'test_urgency_decides_the_reach_and_a_routine_request_does_not_wake_a_neighbour'),

	# 3. The eligibility rule is bypassed. The donor who gave blood seven days ago is invited to give
	#    again, which is the one thing the 90-day interval exists to prevent and the one thing an
	#    alert must not do.
	('an ineligible donor is invited to donate', V,
	 "			if d.county not in counties or not self._eligible(d, now_iso):",
	 "			if d.county not in counties:",
	 'test_a_donor_inside_the_90_day_window_is_not_invited_to_donate'),

	# 4. Compatibility is dropped and everyone in the county is alerted. An A+ donor cannot be given
	#    to a B+ patient, so the alert brings a donor in to be turned away.
	('an incompatible donor is alerted', V,
	 "			rank = self._rank(d.blood_group, req.blood_group)\n			if rank is None or rank > depth:",
	 "			rank = self._rank(d.blood_group, req.blood_group)\n			if False:",
	 'test_a_donor_whose_group_cannot_be_given_to_the_patient_is_not_alerted'),

	# 5. The finder's default becomes both kinds. A blood bank is where the blood already is, not
	#    somewhere a donor can go, and it sorts to the top of a distance list for a donor who cannot
	#    use it.
	('the finder defaults to both kinds', V,
	 "	                     kinds: tuple[str, ...] = ('blood_donation',)) -> list[DonationCentre]:",
	 "	                     kinds: tuple[str, ...] = ('blood_donation', 'blood_bank')) -> list[DonationCentre]:",
	 'test_the_finder_defaults_to_where_a_person_can_give_blood'),

	# 6. The enum collapses the two kinds into one. The finder can no longer tell them apart and the
	#    importer maps a storage site to a donation site — the source's own distinction, erased.
	('the two place kinds are collapsed into one', P,
	 "	blood_bank = 'blood_bank'",
	 "	blood_bank = 'blood_donation'",
	 'test_the_two_kinds_are_the_sources_own_and_are_not_synonyms'),

	# 7. The importer reads only the `amenity` key. Every donation site the query returns is dropped
	#    silently — the import reports success and the finder has nothing to find.
	('the importer reads only the amenity key', O,
	 "		kind = _KIND_MAP.get(tags.get('amenity', '')) or _HEALTHCARE_KIND_MAP.get(tags.get('healthcare', ''))",
	 "		kind = _KIND_MAP.get(tags.get('amenity', ''))",
	 'test_the_importer_reads_the_healthcare_key_and_not_only_the_amenity_key'),

	# 8. The route forgets to pass the adjacency table. The service takes it as an argument, the unit
	#    test hands it a two-county world, and production passes none — so no neighbour is ever
	#    reached and "nearby" silently means "in your county".
	('the route forgets the adjacency table', G,
	 "		return [a.model_dump(mode='json') for a in blood.donor_alerts(req, today_iso, counties.ADJACENCY)]",
	 "		return [a.model_dump(mode='json') for a in blood.donor_alerts(req, today_iso)]",
	 'test_the_routes_serve_the_alerts_and_the_centres'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_rec006.{path.name}.bak')
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
			f'tests/ci/test_rec006.py::{node}'], cwd=ROOT, capture_output=True, text=True)
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
