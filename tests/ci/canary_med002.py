"""Canaries for tests/ci/test_med002.py.

§MED-002's two missing bullets were both closed by adding a data axis, and a data axis is exactly
the kind of change that renders as working code when it is wrong. Each canary below is a *plausible*
implementation of the same feature that answers the question incorrectly:

* **The pair lookup made order-dependent** (#1) — the appendix lists each pair twice, once under
  each drug, so a table keyed on the ordered pair answers one ordering and silently misses the
  other. The test that catches it asks the same question twice in two orders.
* **A hazard disagreement resolved downward** (#2) — the appendix disagrees with itself on 7 pairs,
  and resolving toward "noted" instead of "hazardous" turns the warning into the reassurance. This
  is the one canary whose failure mode is a patient taking the combination.
* **An unmatched name silently dropped** (#3) — the dangerous direction, and the one the plan named:
  a name the reference cannot place becomes "no interaction" rather than "we did not check this".
* **The pregnancy caveat dropped** (#4) — the appendix says absence from its list does not imply
  safety; without the sentence, an absent row reads as a reassurance the source refuses to give.
* **The pregnancy caveat volunteered to a caller who never said they were pregnant** (#5) — the
  opposite error, and the one a careless "always include it" fix produces.
* **The age threshold off by one band** (#6) — `<=` where the source says "under", so an
  eight-year-old is told a medicine is not for them when the source's floor is eight years.
* **A condition firing for a condition the caller did not name** (#7) — an axis that ignores its
  own input.
* **The guidance line emptied** (#8) — the section's fourth bullet served as an empty string, which
  passes any test that only checks the field exists.
* **The route's patient fields dropped** (#9) — the feature present in the service and gone from the
  served payload, which is the shape a green unit test over the service cannot see.

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
I = ROOT / 'src/afya/medicine/interactions.py'
C = ROOT / 'src/afya/medicine/contraindications.py'
S = ROOT / 'src/afya/medicine/service.py'
G = ROOT / 'src/afya/service.py'

CANARIES = [
	# 1. The lookup is keyed on the ordered pair, so `['aspirin', 'warfarin']` finds nothing while
	#    `['warfarin', 'aspirin']` finds the interaction. The appendix lists the pair under both
	#    drugs; a table that reads only one of them answers half the questions asked of it.
	('the pair lookup is made order-dependent', I,
	 "			key = frozenset((left.lower(), right.lower()))",
	 "			key = (left.lower(), right.lower())  # type: ignore[assignment]",
	 'test_pair_lookup_is_order_independent'),

	# 2. The one pair the appendix marks two ways is resolved downward. Clomipramine + Warfarin is
	#    `noted` under clomipramine's section and `hazardous` under warfarin's; the table keeps the
	#    severe one, and flipping it turns the warning into the clearance. This is the canary whose
	#    failure mode is a patient taking the combination.
	('the hazard disagreement resolves downward', I,
	 "	('Clomipramine', 'Warfarin', 'hazardous', 'Enhanced or reduced anticoagulant effect'),",
	 "	('Clomipramine', 'Warfarin', 'noted', 'Enhanced or reduced anticoagulant effect'),",
	 'test_hazard_disagreement_resolves_toward_the_warning'),

	# 3. A name the table cannot place is dropped instead of reported. This is the dangerous
	#    direction: "we do not have this medicine" becomes "these medicines are safe together".
	('an unmatched name is silently dropped', I,
	 "			unmatched.append(raw)",
	 "			continue",
	 'test_unmatched_name_is_reported_not_read_as_safe'),

	# 4. The caveat is dropped, so "no flag" reads as reassurance for a drug the appendix simply
	#    does not list — a claim the source explicitly refuses to make.
	('the pregnancy caveat is dropped', S,
	 "			pregnancy_caveat=(\n				f'{contraindications.PREGNANCY_CAVEAT}. '\n				f'{contraindications.PREGNANCY_BENEFIT_CAVEAT}'\n			) if pregnant else None,",
	 "			pregnancy_caveat=None,",
	 'test_pregnancy_flag_carries_the_sources_own_caveat'),

	# 5. The caveat is served unconditionally. The opposite error: the sentence becomes an unprompted
	#    claim about a patient whose pregnancy nobody stated.
	('the pregnancy caveat is volunteered when nobody asked', S,
	 "			) if pregnant else None,",
	 "			),",
	 'test_pregnancy_flag_carries_the_sources_own_caveat'),

	# 6. The age floor is inclusive where the source says "under", so a child exactly at the floor is
	#    flagged. Doxycycline's line is "children under 8 years"; 8 years is not under 8.
	('the age floor is off by one band', C,
	 "			if hit_age and (hit_age[1] is None or age_months < hit_age[1]):",
	 "			if hit_age and (hit_age[1] is None or age_months <= hit_age[1]):",
	 'test_age_axis_fires_below_the_floor_the_source_states'),

	# 7. The condition axis fires for every condition the drug names rather than for the one the
	#    caller named, so an asthma question is answered with a porphyria warning.
	('a condition fires without being named', C,
	 "			if slug in wanted:",
	 "			if True or slug in wanted:",
	 'test_condition_axis_fires_only_for_a_condition_the_caller_names'),

	# 8. The guidance line is emptied. It still exists as a field, so a test that only reads for
	#    presence passes — which is why the test asserts its content and its identity.
	('the guidance line is emptied', S,
	 "	PHARMACIST_GUIDANCE = (\n		'Take this to a pharmacist or clinician before you act on it. A pharmacist can see your '\n		'other medicines, your allergies and your test results, and none of those are in this check.'\n	)",
	 "	PHARMACIST_GUIDANCE = ''",
	 'test_guidance_and_disclaimer_are_served_with_every_answer'),

	# 9. The route stops passing the patient fields, so the axes are present in the service and
	#    absent from the served answer — the feature gone at the front door while every unit test
	#    over the service stays green.
	('the route drops the patient fields', G,
	 "		return medicine.check_interactions(\n			req.drugs, pregnant=req.pregnant, age_months=req.age_months,\n			conditions=req.conditions).model_dump(mode='json')",
	 "		return medicine.check_interactions(req.drugs).model_dump(mode='json')",
	 'test_route_serves_the_report_and_refuses_a_single_drug'),

	# 10. A single medicine becomes an acceptable request, so the section's "two or more medicines"
	#     is served for a list of one — a check that looked at nothing and reports clean.
	('a single medicine is accepted as a pair', G,
	 "	drugs: list[str] = Field(min_length=2, max_length=50)",
	 "	drugs: list[str] = Field(min_length=1, max_length=50)",
	 'test_route_serves_the_report_and_refuses_a_single_drug'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_med002.{path.name}.bak')
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
			f'tests/ci/test_med002.py::{node}'], cwd=ROOT, capture_output=True, text=True)
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
