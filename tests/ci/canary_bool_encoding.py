"""Canaries for tests/ci/test_bool_encoding.py — each gate pointed at a planted defect.

Every mutation is **disjoint** from what the predicate reads:

* #1 changes the Kotlin encoding while leaving the answered-predicate alone;
* #2 changes the answered-predicate while leaving the encoding alone — the two are separate claims
  and a single mutation cannot test both;
* #3 changes the Swift check while leaving the Swift encoding alone;
* #4 adds a conditional bool to the catalogue, which the population gate must notice.

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
ACT = ROOT / 'src/afya/mobile/actions.py'

GATE = 'tests/ci/test_bool_encoding.py'

CANARIES = [
	# 1. Android goes back to the shipped encoding: a ticked box says yes and an unticked one says
	#    nothing. The predicate reads the encoding line, and the answered-predicate beside it still
	#    exists — so this is the "sends both states" claim alone.
	('Android omits an unticked checkbox again', KOTLIN,
	 '		is CheckBox -> if (v.isChecked) "true" else "false"',
	 '		is CheckBox -> if (v.isChecked) "true" else ""',
	 'test_a_toggle_sends_both_states_on_both_clients'),

	# 2. The answered-predicate treats any value as an answer. Encoding untouched, so a required bool
	#    is still submittable false — the *pre-request check* is what this canary tests, and it is the
	#    half the Swift fix was about.
	('the answered-predicate counts "false" as answered', KOTLIN,
	 '		if (f.type == "bool") raw == "true" else raw.isNotEmpty()',
	 '		raw.isNotEmpty()',
	 'test_an_unticked_toggle_is_unanswered_for_the_pre_request_check'),

	# 3. The same, on iOS — where the encoding was always correct and only the check was wrong. A
	#    canary on one client would have called the class fixed.
	('iOS counts "false" as answered', SWIFT,
	 '		if f.type == "bool" { return (values[f.name] ?? "") == "true" }',
	 '		if f.type == "bool" { return !(values[f.name] ?? "").isEmpty }',
	 'test_an_unticked_toggle_is_unanswered_for_the_pre_request_check'),

	# 4. A second conditional bool appears in the catalogue. The population gate pins the set, so it
	#    must fail: the point of that gate is to make a new conditional bool a decision, not a default.
	('a new conditional bool ships with no gate covering it', ACT,
	 "		_a('log_glucose', 'Log my blood sugar', 'Daily care', 'POST', '/chronic/glucose', [_s(), _f('mmol_l', 'mmol/L', 'decimal'), _f('fasting', 'Before eating?', 'bool')]),",
	 "		_a('log_glucose', 'Log my blood sugar', 'Daily care', 'POST', '/chronic/glucose', [_s(), _f('mmol_l', 'mmol/L', 'decimal'), _f('fasting', 'Before eating?', 'bool', when='mmol_l')]),",
	 'test_the_catalogue_still_demands_bools_a_toggle_has_to_answer'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_bool.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	assert s == backup.read_text(), f'{name}: the backup is not this file'
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
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
