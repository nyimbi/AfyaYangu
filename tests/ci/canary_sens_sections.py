"""Canaries for the §14.1–§14.8 coverage repair in tests/ci/test_content_audit.py.

The defect this unit repaired was not a wrong verdict. It was a reader that could not see eight
sections — §14.1–§14.8 write `### 14.N SENS-00N:` where the other eighty-one write `#### FID:` —
and a partition test that derived its ground truth from *that same reader*, so the two agreed. One
instrument cannot refute itself, and no test in the module could see the gap; it was found by
crossing the feature registry's 97 ids against the 78 the audit claimed.

So the canaries here aim at the three things that made the gap invisible or that the repair
introduced, and each mutation is *disjoint* from what its predicate reads — a predicate changed in
reach, a classification moved across a partition, a filter deleted — rather than a reworded string
the gate was already comparing.

* **#1 narrows the reader's heading split back to `^#### `** — the defect as it shipped. §14.1–§14.8
  stop being sections at all and the audited count falls from 86 to 78. This is the canary that
  would have caught the original bug, aimed at the test that asserts how much of the spec was read.
* **#2 makes the pair-aware rule fall through to `claim` for a dual label** — §SENS-001's
  `Limitations`, a four-bullet list, is then filed as a claim. Both coverage gates fail, because a
  pair in the wrong vocabulary is a list with no rows under it *and* a verdict under a claim the
  section does not print. This is the canary for the rule the repair rests on.
* **#3 deletes the semicolon test's jurisdiction filter** — the loop then runs over claim-side pairs
  too and finds ten lists where the split can only ever reach two. The predicate would be broader
  than its jurisdiction, which is the failure the filter exists to prevent.
* **#4 moves a deferred sensor metric into `carried`** — §SENS-007's per-section count falls from
  seven to six. The pinned per-section count is the check that catches a capability moved out of
  `deferred` to make a gap disappear, and this is that move made with a real reference, so nothing
  else in the file objects.
* **#5 widens the ON_DEVICE predicate back to a substring** — `afya.ai.service:ON_DEVICE_MODELS` is
  a carrier reference, not a membership claim, and §SENS-004's "no facial recognition" note is
  pulled in and reported as one citing no member. The word boundary is the fix; this proves it is
  load-bearing rather than decorative.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the real change and the mutation live in the same uncommitted tree). `__pycache__`
is purged after each write, for the reason `canary_inf001.py` documents. A canary that passes is a
bug in the canary, so a MISSED line fails this script.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
T = ROOT / 'tests/ci/test_content_audit.py'
S = ROOT / 'src/afya/content_audit/service.py'

CANARIES = [
	# 1. The reader's heading split narrowed back to four hashes, which is the defect as it shipped:
	#    §14.1–§14.8 write three. The eight sections vanish and the audited count drops to 78.
	('the spec reader loses the three-hash headings', T,
	 "	headings = re.split(r'^#{3,4} (?=(?:\\d+\\.\\d+ )?[A-Za-z])', SPEC, flags=re.M)[1:]",
	 "	headings = re.split(r'^#{4} (?=(?:\\d+\\.\\d+ )?[A-Za-z])', SPEC, flags=re.M)[1:]",
	 'test_the_report_states_how_much_of_the_spec_it_read'),

	# 2. The pair-aware rule falls through to `claim` for a label in neither vocabulary, so a dual
	#    label's *list* is filed as a claim. §SENS-001's Limitations is the four-bullet one.
	('a dual label falls to the claim side regardless of shape', T,
	 "	if label in _CLAIM_LABELS:\n"
	 "		return 'content' if listy else 'claim'\n"
	 "	return 'content' if listy else 'claim'",
	 "	if label in _CLAIM_LABELS:\n"
	 "		return 'content' if listy else 'claim'\n"
	 "	return 'claim'",
	 'test_every_claim_label_a_section_prints_has_a_verdict_under_it'),

	# 3. The semicolon test's jurisdiction filter is deleted, so the loop reads claim-side pairs the
	#    split never runs for and reports ten lists where there are two.
	('the semicolon scan reads pairs the split cannot reach', T,
	 "			# Scoped to the pairs the split can reach: it lives in the prose branch of\n"
	 "			# `_spec_bullets`, which runs for a content-side pair only. A claim-side section that\n"
	 "			# writes a semicolon is not a section this parser reads as a list at all, so counting it\n"
	 "			# here would report a finding against a jurisdiction the split does not have — the\n"
	 "			# predicate-broader-than-its-jurisdiction failure, in the test that exists to prevent it.\n"
	 "			if _side_of(fid, label) != 'content':\n"
	 "				continue\n",
	 "",
	 'test_the_only_semicolon_list_in_the_spec_is_the_one_that_was_read'),

	# 4. A deferred metric becomes carried, with a reference that resolves, so every other test in the
	#    file accepts it and only the pinned per-section count sees the move.
	('a deferred sensor metric is filed as carried', S,
	 "	('SENS-007', 'Metrics', 'night wakings', 'deferred', None, 'a count of interruptions within the sleep window, which is the interval detail the single derived duration discards'),",
	 "	('SENS-007', 'Metrics', 'night wakings', 'carried', 'afya.sensors.service:sleep_band', 'a count of interruptions within the sleep window, which is the interval detail the single derived duration discards'),",
	 'test_the_deferred_bullets_are_the_ones_the_section_conditions_on_the_world'),

	# 5. The ON_DEVICE predicate back to a substring, so a note citing the model inventory
	#    `ON_DEVICE_MODELS` is read as a membership claim and §SENS-004's note names no member.
	('the ON_DEVICE predicate matches a carrier reference', T,
	 "	names_the_gate = re.compile(r'\\bON_DEVICE\\b')",
	 "	names_the_gate = re.compile(r'ON_DEVICE')",
	 'test_a_note_that_cites_the_on_device_gate_names_a_member_of_it'),
]

_F = 'tests/ci/test_content_audit.py'
_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only', _F],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_KNOWN = {line.strip().split('::')[-1] for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({c[4] for c in CANARIES if c[4] not in _KNOWN})
assert not _missing, f'canaries name tests that do not exist: {_missing}'


failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_sens_sections.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		# `-v`, not `-q`: a passing run under `-q` prints no node name, so `aimed` could not tell the
		# right test ran from a collection that picked up nothing.
		proc = subprocess.run(['uv', 'run', 'pytest', '-v', '-p', 'no:randomly', f'{_F}::{node}'],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
		aimed = node in proc.stdout
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
		for cache in path.parent.rglob('__pycache__'):
			shutil.rmtree(cache, ignore_errors=True)
	ok = caught and aimed
	print(f'{"CAUGHT " if ok else "MISSED "} {name}')
	if not ok:
		failures.append(name)
		print(f'  returncode={proc.returncode} aimed_at_node={aimed}')
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
