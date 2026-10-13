"""Canaries for tests/ci/test_mon005.py.

§MON-005's three missing bullets are each a shape that renders as working code, which is why each is
canaried rather than argued:

* **"treatment guidance"** was missing because the advisory named no method. The cheap fix is a
  fixed list of four methods served for every reading, which passes any test that reads the payload
  — so canary #2 offers chlorine on water it was never evaluated in, and #3 moves the threshold onto
  the *pretreatment* figure so the offer looks justified by the source it is not.
* **"safe storage guidance"** was missing because no string existed. The cheap fix is a single block
  served for every method, which is canary #6: it puts a chlorine residual on boiled water, which is
  a figure a reader cannot act on and the one number in the answer that has to belong to a method.
* **"point-of-use treatment reminders"** was missing because nothing scheduled one. The cheap fix is
  a reminder at a fixed hour, which fires at a time nobody chose — canary #8 — and #7 removes the
  binding between the reminder and the method the notice leads with.

The canaries worth reading as a set are #2, #6 and #9. #2 is the silent one: the household doses
cloudy water, waits half an hour, and drinks water that was never disinfected. #6 is the figure that
belongs to the wrong method. #9 is the whole answer losing a bullet while every field still reads
correctly alone.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary that
passes is a bug in the canary, so a MISSED line is a failure of this script. The `__pycache__` purge
after each write is load-bearing for the reason `canary_inf001.py` documents: two canaries mutating
two methods with same-length edits in the same second make CPython reuse the previous canary's
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
	# 1. Boiling stops being led with, so the method the advisory names is not the method the
	#    guidance starts from — and the storage block and reminder are built from a method the
	#    household was never told to use.
	('boiling is no longer led with', S,
	 "		methods = [TreatmentMethod.boil]",
	 "		methods = [TreatmentMethod.solar]",
	 'test_boiling_is_always_offered_and_offered_first'),

	# 2. Chlorine is offered on water it was never evaluated in. The silent one: the household doses
	#    the water, waits half an hour, and drinks water the turbidity never let the chlorine reach.
	('chlorine is offered on turbid water', S,
	 "		if w.turbidity_ntu <= CHLORINE_TURBIDITY_LIMIT_NTU:\n			methods.append(TreatmentMethod.chlorinate)",
	 "		methods.append(TreatmentMethod.chlorinate)",
	 'test_chlorine_is_withheld_from_water_it_was_not_evaluated_in'),

	# 3. The threshold moves onto the *pretreatment* figure — the 30 NTU at which WHO says any
	#    product needs the water clarified first. The offer then looks justified by the source and is
	#    25 NTU outside the condition the products are actually evaluated to.
	('the threshold moves onto the pretreatment figure', V,
	 "CHLORINE_TURBIDITY_LIMIT_NTU = 5.0",
	 "CHLORINE_TURBIDITY_LIMIT_NTU = 30.0",
	 'test_the_turbidity_limit_is_the_products_own_and_not_the_pretreatment_one'),

	# 4. A method is offered with no limit stated. The caveats are the half that stops a household
	#    following a method into water that is still infectious — chlorine does not touch
	#    Cryptosporidium — so a method list longer than the caveat list is the defect.
	('a method is offered with no stated limit', S,
	 "			caveats=[TREATMENT_CAVEATS[m] for m in methods],",
	 "			caveats=[TREATMENT_CAVEATS[m] for m in methods][:1],",
	 'test_every_offered_method_carries_its_steps_and_its_limit'),

	# 5. The steps stop belonging to the methods being offered, so the notice names boiling and
	#    describes chlorination.
	('the steps stop belonging to the methods', V,
	 "		assert self.steps == expected, 'the steps do not belong to the methods being offered'",
	 "		assert True or self.steps == expected, 'the steps do not belong to the methods being offered'",
	 'test_the_steps_belong_to_the_methods_that_are_offered'),

	# 6. The residual is carried for every method, so boiled water is served a chlorine figure. This
	#    is the one number in the answer that has to belong to a method, and a reader who cannot act
	#    on it is a reader being told to check for a smell that will never be there.
	('the residual is carried for every method', S,
	 "			residual_chlorine_mg_l=0.2 if method is TreatmentMethod.chlorinate else None,",
	 "			residual_chlorine_mg_l=0.2,",
	 'test_the_residual_is_carried_only_for_chlorinated_water'),

	# 7. The reminder stops being bound to the method the notice leads with, so a notice recommending
	#    boiling schedules a chlorination.
	('the reminder loses its method', S,
	 "			reminder=self.treatment_reminder(w, method, treated_at_iso) if treated_at_iso else None,",
	 "			reminder=self.treatment_reminder(w, TreatmentMethod.solar, treated_at_iso) if treated_at_iso else None,",
	 'test_the_reminder_is_bound_to_the_method_the_notice_leads_with'),

	# 8. A reminder is invented when the household never said when it treats water, so a device
	#    schedules a notification at an hour nobody chose.
	('a reminder is invented from a default', S,
	 "			reminder=self.treatment_reminder(w, method, treated_at_iso) if treated_at_iso else None,",
	 "			reminder=self.treatment_reminder(w, method, treated_at_iso or '2026-01-01T08:00+03:00'),",
	 'test_no_reminder_is_served_when_the_household_has_not_said_when'),

	# 9. The storage blocks stop being one per method, so a method is offered with nothing behind it
	#    — the bullet the section lists separately and the one WHO's own meta-analysis shows carries
	#    most of the effect.
	('a method is offered with no storage advice', S,
	 "			storage=[self.storage_guidance(w, m) for m in guidance.methods],",
	 "			storage=[self.storage_guidance(w, guidance.methods[0])],",
	 'test_the_water_safety_answer_carries_all_five_features'),

	# 10. The advisory stops being the existing string, so the same reading is described two ways on
	#     two surfaces and the mobile catalogue's copy drifts from the route's.
	('the advisory becomes a second wording', S,
	 "			county=w.county, unsafe=w.unsafe, advisory=self.water_alert(w),",
	 "			county=w.county, unsafe=w.unsafe, advisory=f'Water for {w.county} needs treating.',",
	 'test_the_advisory_is_the_existing_one_and_not_a_second_wording'),

	# 11. An unreadable time is accepted rather than refused, so a client that sent a date gets a
	#     notice with no reminder and no reason.
	('an unreadable time is accepted', S,
	 "			raise AssertionError(f'{at_iso!r} is not an instant a reminder can be scheduled for') from None",
	 "			return TreatmentReminder(county=w.county, due_iso=at_iso, method=method, message='treat water')",
	 'test_a_reminder_with_no_usable_time_is_refused'),

	# 12. The route stops answering 422 for a time it cannot read, so the caller is told the server
	#     broke when their own input is what was wrong.
	('the route stops refusing an unreadable time', G,
	 "		try:\n			return alerts.water_safety(w, treated_at_iso).model_dump(mode='json')\n		except AssertionError as exc:\n			raise HTTPException(status_code=422, detail=str(exc)) from exc",
	 "		return alerts.water_safety(w, treated_at_iso).model_dump(mode='json')",
	 'test_the_route_refuses_a_time_it_cannot_read'),

	# 13. A storage block may name another county, so a notice served for one county carries a
	#     neighbour's advice.
	('a storage block may name another county', V,
	 "		assert all(sg.county == self.county for sg in self.storage), (",
	 "		assert True or all(sg.county == self.county for sg in self.storage), (",
	 'test_a_storage_block_naming_another_county_is_refused'),

	# 14. A method stays in the enum with an empty step list, so a household advised with it is told
	#     to use a method and given nothing to do.
	('a method has no steps', V,
	 "	TreatmentMethod.solar: (\n		'Fill clear plastic bottles and lay them in full sun.',\n		'Leave them for at least six hours in bright sun, or two days if the sky is overcast.',\n	),",
	 "	TreatmentMethod.solar: (),",
	 'test_every_method_has_steps_and_a_caveat'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_mon005.{path.name}.bak')
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
			f'tests/ci/test_mon005.py::{node}'], cwd=ROOT, capture_output=True, text=True)
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
