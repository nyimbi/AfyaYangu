"""Canaries for tests/ci/test_chan000.py, test_live.py, test_submissions.py and test_explainers.py.

§CHAN-000's call-in and §CHAN-004's clinician Q&A were one absence printed on two channels: a live
programme needs a schedule, a queue and a record of a call answered, and this tree had none of the
three. The unit that closed them added `afya.live` and `RadioVignette`, and the cheap wrong versions
are what these canaries are for.

*A queue is a place two records are made in the same breath.* A clinician working down a queue mints
one question after another, and the first version of `live/views.py` built both ids from
`uuid7str()[:10]` — the top 40 bits of a millisecond timestamp, constant across a 256 ms window. The
second question silently replaced the first in the store. **#1** is that defect as a truncation of
the id source `afya.ids` ships to prevent it.

*A sink that is walked has no memory.* The three channel routes walk the whole report sink after every
session, so an absorb with no dedup queues a person's question once per later session they open —
a subscription to their own report. **#2** is that, and it is the one that would ship.

*A published record is the one place a handle must not travel.* `TranscriptEntry` has no field for
`asked_by`, which is the difference between a model that cannot carry a person and one trusted not to.
**#3** is the cheap version: build the entry from the queue row and filter the field at the route.

*Judging an answer is not refusing one.* `answer()` records §6.2's findings rather than raising on
them, because the section's rules would refuse ordinary clinical speech — "it is likely a viral
infection" contains no action, and an em dash is outside GSM-7. The rule that *must* bite is the
stigmatising one, and **#4** removes the judge entirely: a queue row that calls someone "an Ebola
victim" then reaches a supervisor with nothing on it.

*The vignette's three themes are the section's closed list.* **#5** renames one, which is the change
that reads as harmless and turns a closed list into an open one. **#6** drops the cast check, which is
the only thing that stops a script with a voice and no character behind it.

*Consent is a record, not a moment.* §SEC-001 revokes by setting `withdrawn` rather than deleting the
row, so a check that reads the record's existence and not its state publishes a story after its
subject took the permission back — **#7**, the branch that disappears when four `if consent.` guards
are tidied into one. **#8** collapses §CHAN-004's moderation into §6.5's workflow by publishing on
approval: a moderator's yes then reaches a reader with no clinical review and no harmony tag.

*An explainer is a sequence, and the bar is the second statement of it.* **#9** moves the progress
bar's animation to a property nothing keys to, leaving scenes that animate in place with nothing
saying the order advances. **#10** drifts the committed SVG by one byte, which is the only input that
distinguishes the equality check from an existence check.

*A `deferred` row is a decision, and reverting it is the drift the pin exists for.* **#11** puts
§CHAN-003's "Zero user education required" back in the missing list, which is a property of the
audience re-entering a defect register.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary that
passes is a bug in the canary, so a MISSED line fails this script. The `__pycache__` purge after each
write is load-bearing for the reason `canary_inf001.py` documents: a same-second write of the same
size reuses the previous canary's bytecode and the canary then tests code it never mutated.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
LS = ROOT / 'src/afya/live/service.py'
LV = ROOT / 'src/afya/live/views.py'
CV = ROOT / 'src/afya/channels/views.py'
SB = ROOT / 'src/afya/info/submissions.py'
EX = ROOT / 'src/afya/info/explainers.py'
AU = ROOT / 'src/afya/content_audit/service.py'

CANARIES = [
	# 1. The id is a truncation again. One hex character is sixteen values, so 200 questions asked in
	#    one burst collapse into a handful of rows and the queue answers one person per sixteen. This
	#    is the class `afya.ids` exists for: the first version of this module used `uuid7str()[:10]`,
	#    which is constant across a 256 ms window rather than merely narrow.
	('the question id is a truncation again', LV,
		"	question_id: str = Field(default_factory=lambda: 'LQ-' + ref8())",
		"	question_id: str = Field(default_factory=lambda: 'LQ-' + ref8()[0])",
		'test_live.py::test_a_burst_of_questions_gets_a_burst_of_distinct_ids'),

	# 2. The absorb forgets what it already absorbed. The channel routes walk the whole report sink
	#    after every session, so a person who texted a question once gets it queued again on every
	#    later programme they open — a queue the clinician answers twice.
	('the absorb forgets the report it already took', LS,
		"		if report_id is not None and report_id in self._absorbed:\n			return None",
		"		if False:\n			return None",
		'test_live.py::test_the_absorb_is_idempotent_on_the_report_id'),

	# 3. The transcript entry is built from the queue row. `SessionQuestion` carries `asked_by`, so
	#    the published record then names the asker — the field is in the payload, and filtering it at
	#    the route is what a response model would have to remember on every future field.
	('the transcript is built from the queue row and carries the handle', LS,
		"			TranscriptEntry(question=q.text, answer=q.answer or '', answered_by=q.answered_by or '',",
		"			TranscriptEntry(question=q.text, answer=q.answer or '', answered_by=q.asked_by or '',",
		'test_live.py::test_the_transcript_names_no_person_and_counts_what_was_not_answered'),

	# 4. The answer is not judged. The stigmatising rule is the one §6.2 clause that must bite on live
	#    speech, and with the judge gone a queue row reading "He is an Ebola victim" reaches a
	#    supervisor with an empty verdict list — the record saying the answer was clean.
	('the answer is stored without judging it', LS,
		"		finding: Finding = judge(f'live:{question_id}', answer, Subject.answer)",
		"		finding: Finding = Finding(surface=f'live:{question_id}', subject=Subject.answer, "
		"verdicts=[])",
		'test_live.py::test_a_stigmatising_answer_is_recorded_with_its_verdict_rather_than_refused'),

	# 5. A theme is renamed. §CHAN-000 prints three and only three, and the rename is the change that
	#    reads as harmless while turning a closed list into an open one — a segment nobody asked for
	#    arriving under this feature's name.
	('a vignette theme is renamed out of the section list', CV,
		"	care_seeking = 'care-seeking'",
		"	care_seeking = 'care_seeking'",
		'test_chan000.py::test_the_theme_list_is_the_sections_three_and_only_three'),

	# 6. The cast check is dropped. A line attributed to a character who is not in `roles` is a script
	#    that cannot be recorded as written — somebody at the station would have to invent a voice —
	#    and that check is the whole reason the vignette model exists.
	('a line may be spoken by somebody outside the cast', CV,
		"		unknown = speakers - self.roles",
		"		unknown = set()",
		'test_chan000.py::test_a_line_spoken_by_somebody_outside_the_cast_is_refused'),

	# 7. A withdrawn consent is read as a live one. §SEC-001's one-tap revocation is the whole reason
	#    the ledger records `withdrawn` rather than deleting the row, and a submission filed against a
	#    revoked record is publishing a person's story after they took the permission back. This is the
	#    check that would be dropped by anyone tidying four `if consent.` branches into one.
	('a withdrawn consent is accepted as a live one', SB,
		"		if consent.withdrawn:",
		"		if False:",
		'test_submissions.py::test_submit_refuses_a_withdrawn_consent'),

	# 8. Approval publishes instead of drafting. §CHAN-004's moderation and §6.5's workflow are two
	#    gates, and collapsing them is the cheap move: a moderator's yes would put a person's
	#    testimonial in front of a reader with no clinical review, no translation and no harmony tag.
	('approval publishes the story instead of drafting it', SB,
		"			stage=ContentStage.draft,",
		"			stage=ContentStage.published,",
		'test_submissions.py::test_approve_leaves_the_item_at_draft_and_out_of_the_library'),

	# 9. The generator emits a still. The progress bar's `keyTimes`/`values` are the second, independent
	#    statement of the scene timeline, and a version that drops the bar animates each scene in place
	#    with nothing saying the sequence advances. Caught on a fresh render, because the committed
	#    assets would still carry the old bar and a check against them alone would not see it.
	('the explainer generator drops the progress timeline', EX,
		'<animate attributeName="width" begin="0.0s"',
		'<animate attributeName="height" begin="0.0s"',
		'test_explainers.py::test_the_scenes_are_the_parents_own_sentences_and_its_timeline'),

	# 10. The committed asset is stale. `test_the_committed_asset_equals_a_fresh_render` is worth having
	#     only if it bites on a file that has drifted, so the mutation is a byte in the committed SVG
	#     rather than in the check: an existence assertion would pass on this file and the equality
	#     assertion is the one that fails.
	('the committed explainer drifts from the generator', ROOT / 'media/explainers/ebola-basics.svg',
		'font-size="30" font-weight="600"',
		'font-size="31" font-weight="600"',
		'test_explainers.py::test_the_committed_asset_equals_a_fresh_render[ebola-basics.svg]'),

	# 11. A §CHAN-003 bullet goes back to `missing`. The two rows were moved to `deferred` because each
	#     is a fact about the world rather than an absence in this tree, and reverting one puts a
	#     property of the audience back in the defect list — the exact drift the pinned missing set
	#     exists to catch.
	('a fact about the world goes back into the missing list', AU,
		"'Zero user education required', 'deferred', None,",
		"'Zero user education required', 'missing', None,",
		'test_chan000.py::test_the_three_rows_that_stay_open_are_the_ones_this_unit_does_not_change'),
]


def _node(canary_node: str) -> str:
	# Two files are canaried, so a bare test name has no file to attach to. The `.py::` form is what
	# the list uses to name the other one — keying on `/` alone, as `canary_chan001.py` does, sends
	# `test_live.py::x` to `tests/ci/test_chan000.py::test_live.py::x`, which collects nothing and
	# reads as a canary that fired.
	if canary_node.startswith('tests/'):
		return canary_node
	if '.py::' in canary_node:
		return f'tests/ci/{canary_node}'
	return f'tests/ci/test_chan000.py::{canary_node}'


_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only',
	'tests/ci/test_chan000.py', 'tests/ci/test_live.py', 'tests/ci/test_submissions.py',
	'tests/ci/test_explainers.py'],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_chan000.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', _node(node)],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	print(f'{"CAUGHT " if caught else "MISSED "} {name}')
	if not caught:
		failures.append(name)
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
