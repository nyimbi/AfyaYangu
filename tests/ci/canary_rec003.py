"""Canaries for tests/ci/test_rec003.py.

§REC-003's two missing rows were both "a field recorded and read by nothing", so every canary here
is a plausible way to read it wrongly — or to keep not reading it. Each one renders as working code:
a growth check still returns a verdict, a milestone check still returns a status.

* **The head circumference ignored** (#1) — the field is on the record and the assessment reports
  `None` for it, which is exactly the defect the row names, restored.
* **The MUAC read in millimetres** (#2) — the record carries `muac_mm` and the standard is in
  centimetres, so the child scores about ten times too large and reads as normal.
* **An unmeasured child scored as average** (#3) — `None` defaulted to 0.0, so "not measured" and
  "measured and fine" become the same answer.
* **A MUAC category below six months** (#4) — the IMAM admission rule applied where the guideline
  refers the infant to its inpatient section instead.
* **The IMAM band off by a tenth** (#5) — the moderate band closed at 12.5 rather than 12.4, so a
  child the guideline admits is served as merely at risk.
* **The severe alert softened** (#6) — the unconditional admission rule turned into advice to
  watch, which is the one direction a malnutrition alert may not fail in.
* **The WHO table swapped** (#7) — the head-circumference z-score computed from the arm table, so
  a plausible number comes from the wrong standard.
* **Arm circumference read with the normal form** (#8) — `L` forced to 1, which is the error the
  Box-Cox transform exists to avoid and is invisible at the median.
* **The milestone branch order collapsed** (#9) — every current-band gap read as a delay, so a
  child late on one skill is referred.
* **Regression dropped from the delay rule** (#10) — the criterion the guideline names in its own
  right, and the one a series of checklists cannot catch.
* **The earlier bands counted without being asked** (#11) — every child asked only about their own
  age group reads as delayed.
* **An unknown milestone counted as absent** (#12) — a client's typo becomes a developmental delay.
* **The guidance collapsed to one sentence** (#13) — the three classifications serve the same text,
  so a delay and a normal reading are indistinguishable to the person reading them.
* **The route reverted to the one-word flag** (#14) — the feature gone at the front door while the
  unit tests over the service stay green.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
G = ROOT / 'src/afya/records/growth.py'
S = ROOT / 'src/afya/records/service.py'
V = ROOT / 'src/afya/records/views.py'
A = ROOT / 'src/afya/service.py'
T = ROOT / 'tests/ci/test_content_audit.py'

CANARIES = [
	# 1. The head-circumference field present and read by nothing — the audit defect restored. The
	#    assessment still returns a complete-looking report with the new fields set to None.
	('the head circumference is not read', S,
	 "		head_z = (head_circumference_z(rec.sex, rec.age_months, rec.head_circumference_cm)\n		          if rec.head_circumference_cm is not None else None)",
	 "		head_z = None",
	 'test_the_recorded_measurements_reach_the_assessment'),

	# 2. The MUAC taken from the record's millimetres and compared to a standard in centimetres, so
	#    every child scores about ten times too high and reads as normal.
	('the MUAC is not converted from millimetres', S,
	 "		muac_cm = rec.muac_mm / 10 if rec.muac_mm is not None else None",
	 "		muac_cm = rec.muac_mm if rec.muac_mm is not None else None",
	 'test_the_recorded_measurements_reach_the_assessment'),

	# 3. An absent measurement defaulted to a z-score of 0, so "not measured" and "measured and
	#    exactly average" become one answer. The dangerous direction for a screening field.
	('an unmeasured child scores as average', S,
	 "		head_z = (head_circumference_z(rec.sex, rec.age_months, rec.head_circumference_cm)\n		          if rec.head_circumference_cm is not None else None)",
	 "		head_z = (head_circumference_z(rec.sex, rec.age_months, rec.head_circumference_cm)\n		          if rec.head_circumference_cm is not None else 0.0)",
	 'test_an_unmeasured_child_is_not_reported_as_average'),

	# 4. The IMAM admission category applied below six months, where the guideline refers the infant
	#    to its inpatient section on weight-for-length and clinical signs instead.
	('the MUAC category is applied below six months', S,
	 "		muac_category = (classify_muac(muac_cm)\n		                 if muac_cm is not None and rec.age_months >= MUAC_MIN_AGE_MONTHS else None)",
	 "		muac_category = classify_muac(muac_cm) if muac_cm is not None else None",
	 'test_a_muac_below_six_months_has_a_z_score_and_no_category'),

	# 5. The moderate band closed one tenth late, so a child the guideline admits to a feeding
	#    programme is served as merely at risk. The band is right at both of its other edges.
	('the moderate band is off by a tenth', G,
	 "	if muac_cm < MUAC_MAM_CM:\n		return 'mam'",
	 "	if muac_cm < MUAC_MAM_CM + 0.1:\n		return 'mam'",
	 'test_the_bands_are_the_guidelines_and_meet_at_their_edges'),

	# 6. The severe alert softened from "take the child now" to advice to watch. The guideline's rule
	#    is unconditional ("must be admitted"), and this is the one direction it may not fail in.
	('the severe alert is softened', G,
	 "	'This arm measurement is below the level at which a child needs treatment for severe acute '\n		'malnutrition. Take the child to a health facility now — do not wait for the next visit. A '\n		'health worker will check for swelling of both feet and start treatment.'",
	 "	'This arm measurement is low. Keep an eye on it and mention it at the next visit.'",
	 'test_the_severe_alert_says_what_the_guideline_says'),

	# 7. The head-circumference z-score computed from the arm table. A number is returned, it is
	#    plausible, and it comes from the wrong standard.
	('the head z-score is computed from the arm table', G,
	 "	l, m, s = lms(HEAD_CIRCUMFERENCE_FOR_AGE, sex, age_months)\n	return zscore(head_cm, l, m, s)",
	 "	l, m, s = lms(ARM_CIRCUMFERENCE_FOR_AGE, sex, age_months)\n	return zscore(head_cm, l, m, s)",
	 'test_the_median_measurement_scores_zero'),

	# 8. Arm circumference read with the normal form. `L` is never 1 in that table, and the error is
	#    invisible at the median — which is where a spot-check looks.
	('the arm z-score uses the normal form', G,
	 "	l, m, s = lms(ARM_CIRCUMFERENCE_FOR_AGE, sex, age_months)\n	return zscore(muac_cm, l, m, s)",
	 "	l, m, s = lms(ARM_CIRCUMFERENCE_FOR_AGE, sex, age_months)\n	return zscore(muac_cm, 1.0, m, s)",
	 'test_head_circumference_is_normal_and_arm_is_not'),

	# 9. Every current-band gap read as a delay. Annex 9 needs a gap in the current band *and* an
	#    earlier one, or a regression; this refers a child who is merely late on one skill.
	('every current-band gap is a delay', S,
	 "		elif (missing and missing_earlier) or lost:\n			status = 'delay'",
	 "		elif missing or missing_earlier or lost:\n			status = 'delay'",
	 'test_one_missing_milestone_in_the_current_band_alone_is_an_alert_not_a_delay'),

	# 10. Regression dropped from the delay rule — the criterion the guideline names in its own right,
	#     and the one a series of checklists cannot catch.
	('regression is not a delay', S,
	 "		elif (missing and missing_earlier) or lost:\n			status = 'delay'",
	 "		elif missing and missing_earlier:\n			status = 'delay'",
	 'test_a_lost_milestone_is_a_delay_on_its_own'),

	# 11. The earlier bands counted whether or not the caller said they were assessed, so every child
	#     asked only about their own age group reads as delayed.
	('the earlier bands are counted unasked', S,
	 "		missing_earlier = ([slug for slug, _lab in earlier_items if slug not in present]\n		                   if checked_earlier else [])",
	 "		missing_earlier = [slug for slug, _lab in earlier_items if slug not in present]",
	 'test_the_earlier_milestones_counted_are_served'),

	# 12. An unknown milestone counted as absent rather than refused, so a client's typo becomes a
	#     developmental delay.
	('an unknown milestone is counted as absent', S,
	 "		assert not unknown, f'{unknown} is not a milestone this checklist knows'",
	 "		assert True or not unknown, f'{unknown} is not a milestone this checklist knows'",
	 'test_a_milestone_the_checklist_does_not_know_is_refused'),

	# 13. The three classifications served the same sentence, so a delay and a normal reading read
	#     the same to the person the guidance is for.
	('the guidance is one sentence for every classification', S,
	 "			status=status, guidance=MILESTONE_GUIDANCE[status],",
	 "			status=status, guidance=MILESTONE_GUIDANCE['normal'],",
	 'test_the_guidance_covers_the_three_classifications_and_names_an_action'),

	# 14. The route reverted to the one-word flag, which cannot carry the two measurements or the
	#     MUAC alert. The service still returns the full assessment, so only the front door changes.
	('the growth route returns the one-word flag', A,
	 "		return (await records.record_growth(rec)).model_dump(mode='json')",
	 "		return records.growth_flag(rec).model_dump(mode='json')",
	 'test_the_growth_route_serves_the_two_measurements'),

	# 15. The parser reverted to the comma alone, so §REC-003's Features reads as five items and
	#     four of the eight things the section asks for sit inside one cell named "MUAC; percentile
	#     charts; …". The audit still reports the section as read.
	('the semicolon list reads as one bullet', T,
	 "	items = [item.strip() for item in re.split(r'[;,]', prose.rstrip('.'))]",
	 "	items = [item.strip() for item in prose.rstrip('.').split(',')]",
	 'tests/ci/test_content_audit.py::test_every_audited_bullet_is_the_sections_bullet_in_its_own_words'),

	# 16. The split widened past its jurisdiction, so the semicolon in §LOC-002's "Opt-in only; can
	#     be disabled at any time" — one privacy property and its rationale — becomes two bullets
	#     the section does not print. A separator that is right for one section's prose is wrong
	#     for another's bullets, which is why the split lives in the prose branch.
	('the semicolon split reaches the bullets', T,
	 "	bullets = [line[2:].strip() for line in segment.splitlines() if line.startswith('- ')]",
	 "	bullets = [i.strip() for line in segment.splitlines() if line.startswith('- ')\n\t\tfor i in re.split(r';', line[2:])]",
	 'tests/ci/test_content_audit.py::test_every_audited_bullet_is_the_sections_bullet_in_its_own_words'),

	# 17. The read half classified as if it had been answered, so a caregiver who has read nothing yet
	#     is shown "one or more skills for this age are not there yet" about a child nobody assessed.
	#     Annex 9's ALERT is the instruction to go and assess; served as a result it is a finding.
	('the unchecked checklist reads as an alert', S,
	 "		if not answered:\n			status = 'unanswered'",
	 "		if not answered:\n			status = 'alert'",
	 'test_the_checklist_can_be_read_before_it_is_answered'),

	# 18. The growth document keyed on the age alone, so a second measurement at the same age is an
	#     AssertionError and a 500 at the front door — with the first visit already stored. This was
	#     unreachable until the route started filing, which is why the live probe found it and no
	#     unit test had.
	('a reweigh at the same age is a duplicate document', S,
	 "			doc_id=f'growth-{rec.member_ref}-{rec.age_months}-{visit}', member_ref=rec.member_ref,",
	 "			doc_id=f'growth-{rec.member_ref}-{rec.age_months}', member_ref=rec.member_ref,",
	 'test_a_reweigh_at_the_same_age_is_two_visits_and_not_a_retry'),
]

failures = []

# A nonexistent node id makes pytest exit non-zero on a *collection* error, which reads as CAUGHT.
# So every node is collected first and asserted present, and a canary that names a test that is not
# there fails this script rather than passing it.
def _node(canary_node: str) -> str:
	return canary_node if '/' in canary_node else f'tests/ci/test_rec003.py::{canary_node}'

_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only',
	'tests/ci/test_rec003.py', 'tests/ci/test_content_audit.py'],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_rec003.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	# See canary_inf001.py's docstring: a same-second write of the same size reuses the previous
	# canary's bytecode, and the canary then tests code it never mutated.
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
