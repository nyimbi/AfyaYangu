"""Canaries for tests/ci/test_conditional_required.py — each gate pointed at a planted defect.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary that
passes is a bug in the canary, so a MISSED line is a failure of this script.

Each mutation is **disjoint** from what its predicate reads. That matters more here than usual: the
first two gates compare the served document to the route's requirement set, so a mutation that
changed *both* sides would move the document and the reader together and prove nothing. #1 changes
the route and leaves the document alone; #2 changes the catalogue and leaves the route alone.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
SVC = ROOT / 'src/afya/service.py'
ACT = ROOT / 'src/afya/mobile/actions.py'
COMM = ROOT / 'src/afya/community/views.py'
FORMS = ROOT / 'src/afya/access/forms.py'
LOC = ROOT / 'src/afya/info/localisation.py'
SUB = ROOT / 'src/afya/info/submissions.py'
KOT = ROOT / 'android/app/src/main/java/ke/go/health/afyayangu/ActionsActivity.kt'

GATE = 'tests/ci/test_conditional_required.py'

CANARIES = [
	# 1. The marking is skipped entirely, which is the defect as it shipped: `required` goes back to
	#    being whatever the field carries, and 385 offered fields a route refuses without are drawn as
	#    optional again. The mutation is in `service.py` — the *route* — while the gate's other half
	#    reads `marked()` directly, so the endpoint-agreement gate is the one that must catch it. This
	#    is the canary for "the route applies the marking", which nothing else would notice.
	('the route stops marking the fields it serves', SVC,
	 "		acts = marked(acts, required)",
	 "		acts = acts",
	 'test_the_endpoint_serves_what_the_marking_produces'),

	# 2. The reader loses the marker branch — the defect exactly as it shipped, and the one this
	#    unit's own first version had. `claim: str = Body(...)` is required by the route and its
	#    default is a `Body` object, not `inspect.Parameter.empty`, so a reader testing `is empty`
	#    reports nothing and the catalogue marks the field optional. The mutation is on the *reader*,
	#    so the document still knows the route requires it — which is the whole point of having two
	#    readers, and why the gate must not compare the marking to the function the marking came from.
	('the reader loses the marker branch', FORMS,
	 "				marked_required = getattr(param.default, 'is_required', None)\n"
	 "				if marked_required is not None and marked_required():\n"
	 "					names.add(name)\n"
	 "				elif marked_required is None and param.default is inspect.Parameter.empty:\n"
	 "					names.add(name)",
	 "				if param.default is inspect.Parameter.empty:\n"
	 "					names.add(name)",
	 'test_the_requirement_reader_agrees_with_the_route_document'),

	# 3. A condition is dropped from the field that carries it. `lab_tests` is required exactly when
	#    the post reports a mobile lab, and without the condition it draws as an ordinary optional
	#    question — the `BorderPost` refusal with nothing on the form to warn about it. The gate reads
	#    the *condition*, which the mutation removes, and the mutation does not touch the route.
	('a conditional field loses its condition', ACT,
	 "_f('lab_tests', 'Which tests can it run?', 'list', ph='e.g. mRDT, Ebola PCR', when='mobile_lab', equals_any=['true'])",
	 "_f('lab_tests', 'Which tests can it run?', 'list', ph='e.g. mRDT, Ebola PCR')",
	 'test_a_conditional_field_states_the_answer_that_makes_it_required'),

	# 4. The condition is pointed at a field the action does not carry. A client evaluating it would
	#    look for an answer to a question that is not on the screen and read "" forever, so the field
	#    would never be asked for — the condition is present, well-formed, and inert. Disjoint from
	#    #3, which removes the condition rather than retargeting it.
	('a condition names a field the action does not carry', ACT,
	 "_f('lab_turnaround_hours', 'Results in how many hours?', 'int', when='mobile_lab', equals_any=['true'])",
	 "_f('lab_turnaround_hours', 'Results in how many hours?', 'int', when='has_lab', equals_any=['true'])",
	 'test_the_condition_names_a_field_the_form_actually_draws'),

	# 5. The or-group is dropped, leaving both members drawn as optional. This is the
	#    `SuspiciousReport` defect exactly as it shipped: "a suspicious-medicine report needs a gtin or
	#    a batch number" was stated in two placeholders and enforced by neither form. The gate reads
	#    `any_of`, which the mutation removes; the route is untouched, so the group's absence is the
	#    only signal.
	('an either/or group is dropped from the action', ACT,
	 "		_a('report_suspicious_medicine', 'Report a fake medicine', 'Medicine', 'POST', '/medicine/suspicious', [_f('gtin', 'Barcode number', ph='if you have it'), _f('batch_number', 'Batch number', ph='if you have it'), _f('note', 'What is wrong?', 'textarea'), _f('photo_sha256', 'Photo of the packaging', ph='from the camera upload')],\n			any_of=[FieldGroup(fields=['gtin', 'batch_number'])]),",
	 "		_a('report_suspicious_medicine', 'Report a fake medicine', 'Medicine', 'POST', '/medicine/suspicious', [_f('gtin', 'Barcode number', ph='if you have it'), _f('batch_number', 'Batch number', ph='if you have it'), _f('note', 'What is wrong?', 'textarea'), _f('photo_sha256', 'Photo of the packaging', ph='from the camera upload')]),",
	 'test_a_conditional_field_states_the_answer_that_makes_it_required'),

	# 6. The route stops refusing what the condition warns about. The medium condition is written on
	#    the *model* — the set of media that name a payload — and read by the catalogue to state the
	#    same rule on the form. Widening the model's set leaves the form warning about a refusal the
	#    server no longer makes, and narrowing it leaves the server refusing a submission the form
	#    presented as complete. The mutation is in the model, disjoint from the catalogue the condition
	#    is read from, and the front-door gate is what crosses the two.
	('the route stops refusing what the condition warns about', COMM,
	 "MISINFO_PAYLOAD_MEDIA: tuple[str, ...] = ('voice', 'screenshot', 'whatsapp_forward')",
	 "MISINFO_PAYLOAD_MEDIA: tuple[str, ...] = ('voice', 'screenshot', 'whatsapp_forward', 'text')",
	 'test_the_route_refuses_exactly_what_the_condition_warns_about'),

	# 7. A route requires a parameter its form never draws. `required` can only be marked on a field
	#    that exists, so a requirement with no field cannot be marked, cannot be warned about, and is
	#    refused at the front door with the form looking complete — the unit's own defect one step
	#    out. `correct_my_data` shipped exactly this way (`at_iso` as a required *query parameter*, no
	#    field for it) and the census found it.
	#
	#    The mutation is on the **route**, not the catalogue: the gate reads `required_fields(app)`
	#    and each action's drawn names, so planting the requirement where the gate looks for it is
	#    the only mutation that tests the crossing. Removing the field instead — which is what this
	#    canary did while the defect was live — would now plant nothing, because `at_iso` is a body
	#    field with a default and a form that omits it is correct.
	('a route requires a parameter its form never draws', SVC,
	 "	async def retention_correct(req: CorrectionRequest,\n"
	 "	                            _subject: str = Depends(require_self())) -> dict[str, object]:",
	 "	async def retention_correct(req: CorrectionRequest, witness: str,\n"
	 "	                            _subject: str = Depends(require_self())) -> dict[str, object]:",
	 'test_a_route_requires_nothing_its_form_does_not_draw'),

	# 8. A condition fires on a trigger its route always requires, so it can never fire — or, with an
	#    empty `equals_any`, fires always. `submit_case`'s transcript is required exactly when the
	#    language is present, and the language's condition is required exactly when the transcript is.
	#    If the route required the language outright, the trigger could never be blank and the rule
	#    would be a boolean wearing a condition's clothes. The mutation is on the **route**, disjoint
	#    from the catalogue the condition is read from.
	('a condition fires on a trigger its route always requires', SVC,
	 "	async def community_case(report: CaseReport, _subject: str = Depends(require_scope('assigned', purpose='case_management'))) -> dict[str, object]:",
	 "	async def community_case(report: CaseReport, voice_note_lang: str = Body(...), _subject: str = Depends(require_scope('assigned', purpose='case_management'))) -> dict[str, object]:",
	 'test_a_select_a_condition_keys_off_can_be_left_unanswered'),

	# 9. One direction of the biconditional is dropped from the catalogue. The model refuses a
	#    transcript with no language *and* a language with no transcript, so a form carrying one
	#    direction warns about half the rule and presents the other half as complete — the unit's
	#    defect surviving on the side nobody checked. The mutation removes the language's condition,
	#    which the front-door gate reads; the route is untouched.
	('a biconditional loses one direction', ACT,
	 "_f('voice_note_lang', 'Which language was it spoken in?', 'select', VOICE_LANGS, when='voice_note')]),",
	 "_f('voice_note_lang', 'Which language was it spoken in?', 'select', VOICE_LANGS)]),",
	 'test_a_biconditional_is_refused_from_both_sides_and_the_form_warns_on_both'),

	# 10. The distinctness rule is dropped from the catalogue. `BackTranslation` refuses a render by
	#     the translator, and without the flag the form draws both questions as ordinary text fields —
	#     the refusal arrives as a 422 after the person has filled everything. The mutation is on the
	#     catalogue; the route is untouched, so the population gate and the front-door gate must both
	#     notice that the carried rule and the enforced rule no longer agree.
	('a distinctness rule is dropped from the catalogue', ACT,
	 " _f('back_translated_by', 'Rendered back by', ph='someone who has not seen the source', distinct_from='translated_by')",
	 " _f('back_translated_by', 'Rendered back by', ph='someone who has not seen the source')",
	 'test_a_distinctness_rule_is_carried_on_exactly_the_fields_the_route_enforces'),

	# 11. The route stops enforcing what the flag states. Widening the model's guard leaves the form
	#     refusing a submission the server accepts — a control the person cannot get past — which is
	#     the mirror of the unit's defect and equally invisible without crossing the two sides.
	('the route stops refusing a render by the translator', LOC,
	 "		if self.back_translated_by == self.translated_by:",
	 "		if False and self.back_translated_by == self.translated_by:",
	 'test_the_distinctness_rule_is_the_routes_refusal'),

	# 12. A client goes back to decoding the flag and reading nothing — the state both were in. The
	#     mutation removes the comparison, not the field, so the gate's read-check is what must fire.
	('a client decodes the distinctness flag and never compares', KOT,
	 "			val other = f.distinctFrom ?: return@filter false\n			val mine = answers[f.name] ?: \"\"\n			mine.isNotEmpty() && mine == answers[other]",
	 "			val other = f.distinctFrom ?: return@filter false\n			false && answers[f.name] == answers[other]",
	 'test_both_clients_read_the_distinctness_flag'),
	# 13. The decline rule goes back to living in the service's `assert` alone, which the route
	#     catches as a 404: a moderator who left the note blank is told the story does not exist.
	#     The mutation removes the model's refusal, which is disjoint from the gate's read of it.
	('a decline stops being refused by the model', SUB,
	 "		assert self.decision != 'decline' or (self.note or '').strip(), (",
	 "		assert True, (",
	 'test_the_model_refuses_a_decline_with_no_reason_before_the_service_does',
	 'tests/ci/test_submissions.py'),
]

failures = []
for name, path, old, new, node, *rest in CANARIES:
	gate = rest[0] if rest else GATE
	backup = pathlib.Path(f'/tmp/canary_cond.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', f'{gate}::{node}'],
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
