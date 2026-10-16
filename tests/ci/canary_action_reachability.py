"""Canaries for tests/ci/test_action_reachability.py — each gate pointed at a planted defect and watched to fail.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script.

Each mutation is **disjoint** from what its predicate looks for: the first three move a field to a
place no client writes to rather than renaming it, because a name-only comparison would let a
renamed-but-still-query field through. The fourth plants an open map, which the gate's comparison
is blind to by construction — that is the reason the open-map check is separate, and it must fail
when the map is planted.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
SVC = ROOT / 'src/afya/service.py'
ACT = ROOT / 'src/afya/mobile/actions.py'
CH = ROOT / 'src/afya/channels/views.py'
ALERTS_V = ROOT / 'src/afya/alerts/views.py'
ALERTS_S = ROOT / 'src/afya/alerts/service.py'
TEST = ROOT / 'tests/ci/test_action_reachability.py'

GATE = 'tests/ci/test_action_reachability.py'

CANARIES = [
	# 1. A scalar body field goes back to a plain parameter, which FastAPI reads from the *query
	#    string* — and both clients send no query string on a write. The value the catalogue offers
	#    becomes one no form can deliver, which is the defect class this gate exists for.
	('a write field moves back to the query string', SVC,
	 "	async def facility_wait(facility_id: str, minutes: int = Body(..., embed=True)) -> dict[str, int]:",
	 "	async def facility_wait(facility_id: str, minutes: int) -> dict[str, int]:",
	 'test_every_field_a_form_offers_is_one_the_route_accepts'),

	# 2. The same, on a route whose body is a bare list: `embed=True` is what makes the list a named
	#    property instead of the whole body, and dropping it makes `signs` unreadable.
	('a list body field loses its name', SVC,
	 "	async def maternal_danger(signs: list[str] = Body(..., embed=True)) -> dict[str, object]:",
	 "	async def maternal_danger(signs: list[str] = Body(...)) -> dict[str, object]:",
	 'test_every_field_a_form_offers_is_one_the_route_accepts'),

	# 3. A composed body loses its extra field, so the model's own properties are all the route
	#    takes and the catalogue's control for it has nowhere to go.
	('a composed body drops a field', SVC,
	 "	async def environment_water(w: WaterAdvisoryRequest) -> dict[str, object]:",
	 "	async def environment_water(w: WaterQuality) -> dict[str, object]:",
	 'test_every_field_a_form_offers_is_one_the_route_accepts'),

	# 4. An open map returns to a route the catalogue reaches. `dict[str, str]` accepts any key, so
	#    the comparison above is blind to it — which is exactly why the separate check must fail.
	('a route takes an open map body again', SVC,
	 "	async def women_referral(body: ReproductiveReferralRequest, _subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:",
	 "	async def women_referral(body: dict[str, str], _subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:",
	 'test_a_write_route_takes_no_open_map_body'),

	# 5. A catalogue action offers a field the route genuinely never reads — not one spelled
	#    differently. This is the mutation the gate's own synthetic canary cannot make, because that
	#    one is driven against a fake action and proves the comparison rather than the wiring.
	('the catalogue offers a field the route does not read', ACT,
	 "		_a('request_activation', 'Ask us to switch this on for me', 'Outbreak', 'POST', '/tier4/activation/request', [_f('county', 'Where you are', ph='optional')]),",
	 "		_a('request_activation', 'Ask us to switch this on for me', 'Outbreak', 'POST', '/tier4/activation/request', [_f('county', 'Where you are', ph='optional'), _f('nowhere_to_go', 'Nowhere')]),",
	 'test_every_field_a_form_offers_is_one_the_route_accepts'),

	# 6. A route whose guard binds the subject from the token goes back to the default, which reads a
	#    `subject_ref` out of the path, query or body — and the catalogue's `my_corrections` action
	#    offers no such field, because a person typing one here would be asking to read somebody
	#    else's correction log. The form 422s on a control the person was never shown. The mutation
	#    *removes* the binding rather than renaming anything, so a name-only comparison cannot help.
	('a token-bound route starts demanding a named subject', SVC,
	 "	async def retention_corrections(_subject: str = Depends(require_self(names_subject=False))) -> list[dict[str, object]]:",
	 "	async def retention_corrections(_subject: str = Depends(require_self())) -> list[dict[str, object]]:",
	 'test_every_action_can_name_the_subject_its_guard_requires'),

	# 7. The same defect reached from the other side: the form stops offering the subject its guard
	#    reads. `submit_evidence`'s route takes `subject_ref` with a default and the guard demands it,
	#    so dropping the field leaves a form whose only submittable value is a 422.
	('a form stops offering the subject its guard reads', ACT,
	 "		_a('submit_evidence', 'Send a photo for review', 'Sensors', 'POST', '/evidence', [_s(), _f('file', 'Photo', 'file'),",
	 "		_a('submit_evidence', 'Send a photo for review', 'Sensors', 'POST', '/evidence', [_f('file', 'Photo', 'file'),",
	 'test_every_action_can_name_the_subject_its_guard_requires'),

	# --- the select-options crossing -------------------------------------------------------------

	# 8. A value the route accepts leaves the form. `AlertKind.outbreak_measles` is §3.3 principle
	#    12's own disease and the enum's docstring says it was added for it; dropping it from the
	#    vocabulary the form reads is the *shipped* defect (the list was hand-typed and stopped at
	#    ten), and it has no symptom on either side — the form submits, the route answers 200, and
	#    measles simply cannot be alerted on. Disjoint from #9, which moves the other direction.
	('a value the route accepts leaves the form', ACT,
	 "ALERT_KINDS = [k.value for k in AlertKind]",
	 "ALERT_KINDS = [k.value for k in AlertKind if k.value != 'outbreak_measles']",
	 'test_every_select_offers_exactly_the_vocabulary_its_route_accepts'),

	# 9. An option the route *refuses* returns to the form — `schedule_review.kind` exactly as it
	#    shipped: `clinic`/`home`/`telehealth` against a route accepting `review`/`test`/`refill`/
	#    `vaccination`. Every option the form drew was a 422, and the name-only reachability gate
	#    above is blind to it because the field name matches. This is the direction that proves the
	#    comparison reads *values* and not only membership.
	('an option the route refuses returns to the form', ACT,
	 "_f('kind', 'What kind of review?', 'select', [k.value for k in AppointmentKind])",
	 "_f('kind', 'What kind of review?', 'select', ['clinic', 'home', 'telehealth'])",
	 'test_every_select_offers_exactly_the_vocabulary_its_route_accepts'),

	# 10. The reader stops seeing one of the two spellings of a closed vocabulary. FastAPI writes an
	#     `Enum` annotation as `enum` and a `str` with a pattern as `pattern`, and a reader that knew
	#     only the first reports clean on every field written the second way — which is 50 of the 63
	#     rows. The `len(checked)` floor is what catches the coverage loss; the per-row comparison
	#     cannot, because the rows are gone.
	('the reader stops reading pattern alternations', TEST,
	 "		pat = branch.get('pattern')",
	 "		pat = None",
	 'test_every_select_offers_exactly_the_vocabulary_its_route_accepts'),

	# 11. A required body property with a closed vocabulary that no form draws. `WhatsAppIn.kind` is
	#     optional today and the form is right to omit it; making it required is a question with a
	#     known answer set that the form never asks, so every caller has to type the token blind.
	#     Disjoint from #8–#10, which all move the catalogue or the reader, not a route's model.
	('a required closed vocabulary has no control', CH,
	 "	kind: str = Field(default='text', pattern=r'^(text|voice)$')",
	 "	kind: str = Field(pattern=r'^(text|voice)$')",
	 'test_every_closed_vocabulary_a_route_declares_is_offered_as_a_select'),

	# --- the assert-enforced-vocabulary crossing ---------------------------------------------------

	# 12. The KMD defect, restored exactly: the model's pattern admits a fourth member while the
	#     handler assert keeps its own narrower set. The two schema-reading gates above both pass on
	#     this — the form matched the model and the model matched the form — and only the model-vs-
	#     assert crossing sees it. This is the mutation the gate exists for, and it is what the
	#     `KMD` in `ALERT_ISSUERS` was before this unit: a value the document promises and the route
	#     refuses.
	('a model vocabulary is wider than the assert that guards it', ALERTS_V,
	 "	issued_by: str = Field(pattern=ALERT_ISSUER_PATTERN)",
	 "	issued_by: str = Field(pattern=r'^(MoH|PHEOC|County|KMD)$')",
	 'test_a_models_vocabulary_is_no_wider_than_the_assert_that_guards_it'),

	# 13. The same field, from the other layer: the handler stops naming the vocabulary at all and
	#     admits anything, which is how the field was *before* the set was declared on the model.
	#     Disjoint from #12, which widens the document; this one widens the assert.
	('an assert stops naming a vocabulary', ALERTS_S,
	 "		assert alert.issued_by in ALERT_ISSUERS, 'alerts are issued by an authority'",
	 "		assert alert.issued_by, 'alerts are issued by an authority'",
	 'test_a_models_vocabulary_is_no_wider_than_the_assert_that_guards_it'),

	# 14. The reader stops resolving the model through the parameter annotation, so the whole
	#     crossing goes blind: `_asserted_vocabularies()` returns nothing and every comparison passes
	#     vacuously. The `len(asserted)` floor is what catches it — the per-row comparison cannot,
	#     because the rows are gone. Same shape as canary #10.
	('the assert reader stops resolving the model', TEST,
	 "					if field in models.get(model, {}):",
	 "					if False:",
	 'test_a_models_vocabulary_is_no_wider_than_the_assert_that_guards_it'),

	# 15. The form offers an option the handler refuses — the same defect one layer up, where the
	#     model and the assert agree and the *form* is the stale copy. `KMD` goes back into the
	#     spinner only, so the document stays honest and the control is still a 422.
	('the form offers a value the handler refuses', ACT,
	 "_f('provisioned_by', 'Registered by', 'select', list(PROVISIONERS))]),",
	 "_f('provisioned_by', 'Registered by', 'select', [*PROVISIONERS, 'Self'])]),",
	 'test_a_form_offers_no_value_the_assert_that_guards_it_refuses'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_reach.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', f'{GATE}::{node}'],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
	print(f'{"CAUGHT " if caught else "MISSED "} {name}')
	if not caught:
		failures.append(name)
		print(proc.stdout[-1200:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
