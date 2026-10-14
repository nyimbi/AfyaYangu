"""Canaries for the widened content-audit reader — tests/ci/test_content_audit.py.

The unit these belong to is not a feature. It is the instrument, and the defect was that the
instrument could not see nine of the spec's feature sections while reporting "69 of 69" coverage.
The tests that were supposed to catch that derived their ground truth from the *same* reader, so
they could not disagree with it: a partition test whose two sides come from one instrument measures
the instrument, not the spec.

Which makes the canaries here different from every other file's. Most canaries break the code and
expect a test to notice. These break the *reader* and expect a test to notice, because the reader
is the thing that was wrong — and the first canary is the original defect restored byte for byte:
revert `_spec_feature_ids` to the heading-only regex and nine sections must vanish from the
report. If that canary ever passes, the gate has been scoped back to its own blind spot.

The rest are the ways a widened reader can be wrong in the other direction:

* #2 and #3 widen by *shape* rather than by the id the section declares — matching any heading that
  merely starts with `CHAN-` catches the seven channels but would also swallow `#### CHAN-2: USSD`'s
  own subheadings and, in a spec with a `SENS-01` heading, invent a section. A reader that finds
  sections by a prefix is a reader that finds sections the spec does not have.
* #4 makes the `**Feature ID:**` fallback match a *mentioned* id rather than the section's own, so
  §CHAN-0 — which names §CHAN-1 in its Integration clause — is read as CHAN-001 and the report
  audits one section twice and the other never.
* #5 stops the section body at the next `####` rather than at the next `---`, so a section absorbs
  its neighbours' labels and every list in §5 reads as belonging to the first channel.
* #6 and #7 are the label vocabulary. A widened reader without a widened vocabulary fails the
  partition test in the loud direction; the quiet direction is a vocabulary that grows by absorbing
  a *content* label into `_CLAIM_LABELS`, which is exactly how eight sections became invisible the
  first time (the miscategorised-label defect this file's sibling test names).
* #8 is the parenthetical split. §CHAN-1's Format is three items and a flat `re.split` makes six,
  three of them fragments — and the fragments are what a row would then be written against.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --`, because the mutation and the real change live in the same uncommitted tree.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
T = ROOT / 'tests/ci/test_content_audit.py'
S = ROOT / 'src/afya/content_audit/service.py'

CANARIES = [
	# 1. The original defect, restored. The reader goes back to matching the id in the heading only,
	#    which is what the module did when it reported 69 of 69. §5's seven channels spell their id
	#    with one digit and §14.9's two sensors carry theirs on a `**Feature ID:**` line, so nine
	#    sections leave the report — and the partition test must notice, or the gate is scoped to the
	#    blind spot it was written to remove.
	('the reader goes back to heading-only ids', T,
	 "		f = re.search(r'^\\*\\*Feature ID:\\*\\* ([A-Z]{2,4}-\\d{3})\\s*$', body, re.M)\n		if f:\n			ids.append(f.group(1))",
	 "		pass",
	 'test_the_report_states_how_much_of_the_spec_it_read'),

	# 2. Sections are found by a heading *prefix* rather than by the id the section declares. §5's
	#    seven channels are caught, and so is every heading that merely starts with the prefix — a
	#    reader that finds sections the spec does not have, which is the opposite failure to the one
	#    this unit fixed and just as wrong. `SENS-0` matches SENS-009's own heading here, so the
	#    section is counted twice and the count disagrees with the document.
	('sections are found by heading prefix', T,
	 "		if head.startswith(f'{feature_id}:') or re.search(",
	 "		if head.startswith(feature_id[:5]) or re.search(",
	 'test_every_content_label_a_section_prints_has_rows_under_it'),

	# 3. The `**Feature ID:**` fallback matches an id the section *mentions* rather than the one it
	#    declares. §CHAN-0's Integration clause names §CHAN-1, so CHAN-000's body answers a search for
	#    CHAN-001 and the report audits §CHAN-1 twice while §CHAN-0's own content goes unread — the
	#    original defect, one level down and harder to see because the total still looks right.
	('the id fallback matches a mentioned id', T,
	 "				rf'^\\*\\*Feature ID:\\*\\* {re.escape(feature_id)}\\s*$', body, re.M):",
	 "				rf'Feature ID.{0,40}{re.escape(feature_id)}', body, re.M):",
	 'test_every_content_label_a_section_prints_has_rows_under_it'),

	# 4. A section's body stops at the next `####` instead of at the next `---`, so §CHAN-0 absorbs
	#    §CHAN-1's lists and the report attributes one channel's content to another. Every label is
	#    still found, every count still adds up, and the rows are filed against the wrong section.
	('a section body runs past its own end', T,
	 "		return body.split('\\n---', 1)[0]",
	 "		return body.split('\\n####', 1)[0]",
	 'test_every_content_label_a_section_prints_has_rows_under_it'),

	# 5. A *content* label is filed as a claim label. This is the miscategorised-label defect that
	#    hid eight sections the first time, and it is canaried in this direction because the loud
	#    failure (a label in neither set) is caught by the partition test while this one — a label in
	#    the wrong set — is caught only by the shape rule.
	('a content label is filed as a claim label', S,
	 "	'Menu structure (illustrative)', 'Outbound use cases', 'Supported devices',",
	 "	'Outbound use cases', 'Supported devices',",
	 'test_a_label_declared_out_of_scope_has_no_list_under_it'),

	# 6. A claim label is filed as a content label, the same defect the other way. The vocabulary
	#    still partitions the spec exactly — same size, no overlap — so the partition test passes and
	#    the shape rule passes too, because `Capabilities` has left the set the shape rule reads. What
	#    fails is the pair coverage: §CHAN-3 prints a `Capabilities` table, `_LABELS` now claims it is
	#    a content list, and there is no row under it. This is the quiet direction, and the one that
	#    matters: a label in the wrong set is invisible to every test except the one that counts pairs.
	('a claim label is filed as a content label', S,
	 "	'Menu structure (illustrative)', 'Outbound use cases', 'Supported devices',",
	 "	'Menu structure (illustrative)', 'Outbound use cases', 'Supported devices', 'Capabilities',",
	 'test_every_content_label_a_section_prints_has_rows_under_it'),

	# 7. The depth tracking goes, so the split is flat and §CHAN-1's Format becomes six items — "160
	#    characters", "plain language", "local language option via keyword (e.g.", "prefix `SW`",
	#    "`LU`", "`KY`)". Three of the six are fragments of one item, and the rows are written against
	#    the three the section actually prints, so the section's own words stop matching the audit's.
	#    Note the earlier cut of this canary patched `depth == 0` to `depth <= 0`, which is a no-op —
	#    the branch is only reached for a character that is neither bracket, and `(` has already
	#    incremented the depth by then. A canary whose patch changes no behaviour is a canary that
	#    did not run, and it read as MISSED.
	('the split ignores parentheses', T,
	 "		if char in ';,' and depth == 0:",
	 "		if char in ';,' and True:",
	 'test_every_audited_bullet_is_the_sections_bullet_in_its_own_words'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_chan.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	# A same-second write of the same size reuses the previous canary's bytecode, and the canary then
	# tests code it never mutated. Purged for the file just written.
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	target = f'tests/ci/test_content_audit.py::{node}'
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', target],
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
