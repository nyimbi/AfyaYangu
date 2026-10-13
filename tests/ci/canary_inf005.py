"""Canaries for tests/ci/test_inf005.py.

§INF-005's four rows were the same shape — *a claim with no table behind it* — so every canary here
removes a table and leaves the claim standing, which is what the defect looked like the first time:

* **The country half was a constant.** Canary #1 puts the paragraph back the way it was: one string
  with no band in it, identical for every destination. Any test that reads a single destination
  passes against it.
* **`not_assessed` was the dangerous direction.** Kenya sits inside WHO's "rest of the African
  Region" band, so reading its row off that band answers `low` about the country the advisory is
  served in. Canary #4 is that flip, and it is the single most consequential mutation in this file.
* **The county half had no carrier.** Canary #7 gives it its own band source, which is the copy that
  goes stale the first time a county office publishes a risk level.
* **The MON-009 link was a message.** Canary #9 leaves the acknowledgement promising days 1, 3, 7,
  14 and 21 while nothing is enrolled, so the diary route answers an empty list — the defect
  exactly, and the one a unit test that reads the payload cannot see.

The canaries worth reading as a set are #4, #7 and #9. #4 invents the reassuring answer. #7 makes a
second source of truth for a figure that already has one. #9 is a promise with nothing behind it.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary that
passes is a bug in the canary, so a MISSED line is a failure of this script. The `__pycache__` purge
after each write is load-bearing for the reason `canary_loc005.py` documents: two canaries mutating
two files with same-length edits in the same second make CPython reuse the previous canary's
bytecode, and the gate then reports a mutation it never made.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
S = ROOT / 'src/afya/location/service.py'
A = ROOT / 'src/afya/location/advisories.py'
V = ROOT / 'src/afya/location/views.py'

CANARIES = [
	# 1. The paragraph goes back to being a constant: no band, no source's words, the same sentence
	#    for every destination. This is the original defect, and it is why the test compares two.
	('the advisory paragraph stops carrying the destination band', S,
		"		                 band=BAND_LABELS[row.band], stated=row.stated)",
		"		                 band=BAND_LABELS[row.band], stated='')",
		'test_the_country_half_is_a_table_and_not_a_constant'),

	# 2. Kenya's row is read off the regional band it sits inside. `not_assessed` becomes `low` for
	#    the country this advisory is served in — the reassuring answer, invented.
	('Kenya is served as low instead of not assessed', A,
		"	CountryRow('KE', 'KEN', 'Kenya', NOT_ASSESSED,",
		"	CountryRow('KE', 'KEN', 'Kenya', LOW,",
		'test_kenya_is_not_assessed_and_never_low'),

	# 3. The band label for a refusal becomes reassurance. `unknown` and `not_assessed` are verdicts,
	#    not bands, and the label is where a client reads which one it got.
	('an unassessed place is labelled as low risk', A,
		"	NOT_ASSESSED: 'not assessed', UNKNOWN: 'not assessed',",
		"	NOT_ASSESSED: 'not assessed', UNKNOWN: 'low',",
		'test_the_unknown_verdict_is_never_rendered_as_reassurance'),

	# 4. WHO's own caveat is dropped from the report. An absent row then reads as an assessment that
	#    was made, which is the failure the sentence exists to prevent.
	('the not-assessed caveat is dropped', S,
		"			not_assessed_caveat=NOT_ASSESSED_CAVEAT,",
		"			not_assessed_caveat='',",
		'test_the_unknown_verdict_is_never_rendered_as_reassurance'),

	# 5. An unrecognised place resolves to a band instead of to a refusal, so a city is answered with
	#    the regional band and "Kampala" reads as safe.
	('an unknown place resolves to a band', A,
		"	code = canonical(place)\n	if code is None:\n		return None",
		"	code = canonical(place)\n	if code is None:\n		return COUNTRIES[2]",
		'test_an_unrecognised_place_is_unknown_and_not_a_band'),

	# 6. The county half keeps its own risk table instead of reading §INF-001's dashboard, which is
	#    the second source of truth for a figure that already has one.
	('the county half stops reading the dashboard', S,
		"		if self._county_risk is None or county not in COUNTIES:",
		"		if True or self._county_risk is None or county not in COUNTIES:",
		'test_the_county_half_reads_the_dashboard_and_not_a_second_table'),

	# 7. The county's own stamp is replaced by WHO's assessment date, so a county reading taken this
	#    morning is served as a 14 August assessment — §6.2.3's "a risk level with no date is
	#    indistinguishable from today's", in the other direction.
	('the county row is stamped with WHO assessment date', S,
		"			stated=risk.bulletin, assessed_on_iso=_assessed_on_iso(risk.updated_at_ms),",
		"			stated=risk.bulletin, assessed_on_iso=ASSESSED_ON_ISO,",
		'test_a_county_offices_published_risk_reaches_the_traveller_screen'),

	# 8. WHO's travel advice is dropped, leaving the bands with no statement of what the authority
	#    actually advises — the half of the answer a traveller acts on.
	('the WHO travel advice is dropped', S,
		"			who_travel_advice=WHO_TRAVEL_ADVICE,",
		"			who_travel_advice='',",
		'test_whos_travel_advice_is_carried_verbatim_and_is_the_whole_answer'),

	# 9. The deployment's own two steps are relabelled as the sources', so an operating rule this
	#    product invented reads as a WHO or CDC instruction. The whole reason `source` travels.
	('a deployment rule is relabelled as a source instruction', A,
		"	'deployment': 'This deployment’s operating rule (not stated by either source)',",
		"	'deployment': 'CDC, About Ebola Disease',",
		'test_every_step_carries_its_own_source_because_they_are_not_one_authoritys'),

	# 10. The source's own counterweight is dropped, so a reader who sees the bands and nothing else
	#     concludes that Ebola is a general hazard.
	('the traveller risk note is dropped', S,
		"			traveller_risk_note=TRAVELLER_RISK_NOTE,",
		"			traveller_risk_note='',",
		'test_the_sources_own_counterweight_is_served_with_the_bands'),

	# 11. The MON-009 link goes back to being a message: the acknowledgement still names days 1, 3, 7,
	#     14 and 21 and nothing is enrolled, so the diary route answers an empty list. This is the
	#     defect the row named, and a payload-reading test cannot see it.
	('the enrolment stops reaching the monitoring service', S,
		"		if self._monitoring is not None:\n			self._monitoring.enrol(decl.subject_ref)\n			linked = True\n",
		"		if self._monitoring is not None:\n			linked = True\n",
		'test_the_enrolment_reaches_the_monitoring_service'),

	# 12. `diary_linked` reports True whatever happened, so a deployment with no monitoring service
	#     wired promises a schedule nothing will ask about — the honest refusal turned into a claim.
	('diary_linked is reported true with nothing enrolled', S,
		"			message=traveller(decl.lang, 'enrolled'), lang=decl.lang, diary_linked=linked,",
		"			message=traveller(decl.lang, 'enrolled'), lang=decl.lang, diary_linked=True,",
		'test_a_deployment_with_no_monitoring_wired_says_so'),

	# 13. `PlaceAdvisory.band` widens to any string, so a third vocabulary can be introduced by a
	#     caller and the one place the two tables are allowed to meet stops being a gate.
	('a band from neither table is accepted', V,
		"	band: str = Field(pattern=r'^(very_high|high|moderate|low|not_assessed|unknown)$')",
		"	band: str = Field(pattern=r'^.*$')",
		'test_a_place_advisory_refuses_a_band_from_neither_table'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_inf005.{path.name}.bak')
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
			f'tests/ci/test_inf005.py::{node}'], cwd=ROOT, capture_output=True, text=True)
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
