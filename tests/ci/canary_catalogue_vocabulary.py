"""Canaries for tests/ci/test_catalogue_vocabulary.py — each gate pointed at a planted defect.

Every mutation is **disjoint** from what its predicate reads:

* the Android picker canary changes the *accept reader* while leaving the catalogue's `accept`
  values alone;
* the iOS picker canary changes the *Swift branch* while leaving the Android one alone;
* the array canaries change one client's encoder each — a single mutation could not test both;
* the catalogue canaries change the *served document* while leaving both client sources alone;
* the population canary removes a flag no other mutation touches.

A canary that passes is a bug in the canary. Backups are read back before the mutation and the
restore is verified byte-for-byte, because a mutation and the real change live in one uncommitted
tree and `git checkout --` would take the real work with it.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
KOTLIN = ROOT / 'android/app/src/main/java/ke/go/health/afyayangu/ActionsActivity.kt'
SWIFT = ROOT / 'ios/AfyaYangu/Features.swift'
SWIFT_WIRE = ROOT / 'ios/AfyaYangu/Endpoints.swift'
ACT = ROOT / 'src/afya/mobile/actions.py'

GATE = 'tests/ci/test_catalogue_vocabulary.py'

CANARIES = [
	# 1. Android's picker stops reading the route's accepted type. The catalogue still carries
	#    `accept` on all four file fields, so this is the *client* half alone.
	('Android offers every file type again', KOTLIN,
	 '		a.fields.firstOrNull { it.type == "file" }?.accept ?: "*/*"',
	 '		"*/*"',
	 'test_a_file_is_a_picker_with_an_accepted_type_in_a_multipart_body'),

	# 2. iOS goes back to the photo library for every file field, which is how the voice note and
	#    the cough recording could not be selected at all. Android untouched.
	('iOS offers photos for an audio part', SWIFT,
	 '			if (field.accept ?? "").hasPrefix("image") {',
	 '			if true {',
	 'test_a_file_is_a_picker_with_an_accepted_type_in_a_multipart_body'),

	# 3. iOS sends a list as the raw comma text. The route's model is `list[str]`, so this is a 422
	#    on every list field — and the Android encoder is still correct, which is why the gate reads
	#    both.
	('iOS sends a list as text', SWIFT_WIRE,
	 '		case "list": return trimmed.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }',
	 '		case "list": return trimmed',
	 'test_a_list_is_sent_as_an_array_by_both_clients'),

	# 4. Android sends a list as text. Disjoint from #3 by file and by language.
	('Android sends a list as text', KOTLIN,
	 '		"list" -> JSONArray(raw.split(",").map { it.trim() }.filter { it.isNotEmpty() })',
	 '		"list" -> raw',
	 'test_a_list_is_sent_as_an_array_by_both_clients'),

	# 5. A closed vocabulary returns to a text box: the outbreak slugs move back from the
	#    placeholder to `options` on a `path`. This is the shipped defect, restored. `_a()` refuses
	#    the combination through `crossings()`, so the canary disables that one call in the same
	#    mutation — otherwise it would be testing the constructor rather than the gate.
	('a path field carries a closed set nobody can select', ACT,
	 ("_f('condition', 'What is happening?', 'path', ph='isolation_distress, grief, worker_burnout')",
	  "	assert not (found := crossings(act)), f'{id}: unfillable vocabulary: {found}'"),
	 ("_f('condition', 'What is happening?', 'path', options=['isolation_distress', 'grief', 'worker_burnout'])",
	  "	found = []"),
	 'test_options_are_only_where_a_client_offers_a_set'),

	# 6. A hint returns to a toggle, with the constructor's refusal disabled in the same mutation so
	#    the served-document predicate is what fires.
	('a placeholder returns to a toggle', ACT,
	 ("_f('walk_in_only', 'Walk-in only', 'bool')",
	  "	assert not (found := crossings(act)), f'{id}: unfillable vocabulary: {found}'"),
	 ("_f('walk_in_only', 'Walk-in only', 'bool', ph='yes if you cannot book ahead')",
	  "	found = []"),
	 'test_a_placeholder_is_only_where_a_client_draws_it'),

	# 7. A condition fires on an answer its trigger cannot produce. `decision` offers approve and
	#    decline; `rejected` is neither, so the condition is dead.
	('a condition names an answer no control offers', ACT,
	 ("when='decision', equals_any=['decline']",
	  "	assert not (found := crossings(act)), f'{id}: unfillable vocabulary: {found}'"),
	 ("when='decision', equals_any=['rejected']",
	  "	found = []"),
	 'test_a_condition_names_a_field_the_form_draws_and_an_answer_a_control_can_produce'),

	# 8. A condition names a field the action lacks — the same predicate, a different crossing.
	('a condition names a field that is not there', ACT,
	 ("when='decision', equals_any=['decline']",
	  "	assert not (found := crossings(act)), f'{id}: unfillable vocabulary: {found}'"),
	 ("when='verdict', equals_any=['decline']",
	  "	found = []"),
	 'test_a_condition_names_a_field_the_form_draws_and_an_answer_a_control_can_produce'),

	# 9. The marking makes every server-minted reference required. `_auto()` has no `required` to
	#    set, so the defect lives in `marked()` — a mutation of the marking, disjoint from the
	#    catalogue entries every other canary touches.
	('a server-minted reference is marked required', ACT,
	 "fields.append(f.model_copy(update={'required': f.name in needed and not conditional}))",
	 "fields.append(f.model_copy(update={'required': (f.name in needed or f.server_assigned) and not conditional}))",
	 'test_a_server_assigned_value_is_never_one_the_route_requires'),
]

failures = []
for name, path, old, new, node in CANARIES:
	# A canary may carry two edits: the planted defect and, where the constructor refuses that same
	# defect, the assertion it would trip. Both are applied as one mutation and both must be unique.
	edits = old if isinstance(old, tuple) else (old,)
	replacements = new if isinstance(new, tuple) else (new,)
	assert len(edits) == len(replacements), f'{name}: mismatched mutation pairs'
	backup = pathlib.Path(f'/tmp/canary_vocabulary.{path.name}.bak')
	shutil.copy2(path, backup)
	original = path.read_text()
	assert original == backup.read_text(), f'{name}: the backup is not this file'
	s = original
	for edit, replacement in zip(edits, replacements):
		count = s.count(edit)
		assert count == 1, f'{name}: target not unique/found ({count}): {edit[:70]!r}'
		s = s.replace(edit, replacement)
	path.write_text(s)
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', f'{GATE}::{node}'],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
	finally:
		shutil.copy2(backup, path)
		# Against the *pre-mutation* text, which is what the backup was taken from. Comparing to `s`
		# here would compare the restore to the mutation and always pass.
		assert path.read_text() == original, f'{name}: revert did not restore'
	print(f'{"CAUGHT " if caught else "MISSED "} {name}')
	if not caught:
		failures.append(name)
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
