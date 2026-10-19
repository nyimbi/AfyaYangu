"""Canaries for tests/ci/test_chan001.py.

§CHAN-1's two outbound bullets were `missing` for two different reasons, and the canaries are split
the same way.

*The follow-up.* §5.3 CHAN-1's Outbound list ends "Follow-up after a USSD report" and nothing sent
one. The cheap wrong versions are the ones a plausible fix produces: sent from the walk (which is
synchronous, so it cannot), sent for every channel (§CHAN-3's WhatsApp router already answers in the
thread — an SMS on top is two messages for one report), and sent once per session rather than once
per report (the routes emit by walking the whole sink, so a send with no memory is a subscription to
a person's own report). **#1** is the last of those and the one that would ship.

*The bound.* "plain language" was a claim in a comment. The cheap wrong versions are a bound set to
fit the widest sentence already written — which is a description of the status quo wearing a
ceiling's clothes, and the reason the §SEC-004 caveat was split instead — and a walker that handles
one nesting shape. **#5** is that walker: the flat-only version reports 15 tables and 30 strings
while silently skipping the fifteen nested tables carrying the clinical advice, which is a gate
losing 15 of its 30 tables and 161 of its 191 strings without failing.

**Three of these went MISSED on the first run, and two of those were bugs in the tests.** #4's test
computed its input as `MAX_SENTENCE_WORDS + 3`, so loosening the ceiling loosened the test with it —
a tautology wearing an assertion. #7's test asserted `plain is True` on a body already known to be
plain, which a hardcoded reading satisfies; it now exercises both sides of the line. #5's *mutation*
was wrong rather than its gate: disabling the list branch still recurses every dict, and every table
the test names is dict-nested. A canary that passes is a bug in the canary, and a canary whose
mutation is not disjoint from what the predicate looks for is a canary that never ran.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line fails this script. The `__pycache__` purge
after each write is load-bearing for the reason `canary_inf001.py` documents: a same-second write of
the same size reuses the previous canary's bytecode and the canary then tests code it never mutated.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
OB = ROOT / 'src/afya/channels/outbound.py'
CS = ROOT / 'src/afya/channels/service.py'
CV = ROOT / 'src/afya/channels/views.py'

CANARIES = [
	# 1. The send forgets it already sent. The routes walk the whole report sink after every session,
	#    so this texts the person again on every later USSD session — a subscription to their own
	#    report rather than a follow-up. This is the defect a follow-up actually has.
	('the follow-up is re-sent on every walk', CS,
	 "		if body is None or report.report_id in self._followed_up:",
	 "		if body is None:",
	 'test_the_follow_up_is_sent_once_however_many_sessions_follow'),

	# 2. The follow-up is composed for every channel. §CHAN-3's WhatsApp router replies inside the
	#    thread the person is already in, so this is a second message for one report — and it is the
	#    shape a fix written against "the report" rather than against the bullet produces.
	('the follow-up is composed for every channel', CS,
	 "		if channel == 'ussd':\n			self._follow_ups[report.report_id] = follow_up_message(",
	 "		if True:\n			self._follow_ups[report.report_id] = follow_up_message(",
	 'test_a_report_from_another_channel_gets_no_follow_up'),

	# 3. The callback promise is folded into the record sentence. A person who was told a health
	#    worker would ring is then texted a receipt that says nothing about it — the follow-up
	#    contradicting the screen they just read, which is the failure `USSD_CLOSE` splits to avoid.
	('the callback promise is dropped from the follow-up', OB,
	 "	key = 'callback' if callback_requested else 'plain'",
	 "	key = 'plain'",
	 'test_the_follow_up_says_whether_a_callback_was_promised'),

	# 4. The bound is loosened to fit the widest sentence the tree already wrote, instead of the
	#    sentence being fixed. §SEC-004's caveat was 31 words in one sentence and is three now; a
	#    ceiling of 40 is a description of the status quo wearing a bound's clothes, and it would let
	#    the next 31-word screen-reader paragraph through. The node is the *both-directions* test:
	#    the report test pins its input as a literal, so it cannot move with the constant, but only
	#    this one asserts the ceiling sits below the caveat that was split.
	('the bound is loosened to fit rather than the string fixed', OB,
	 "MAX_SENTENCE_WORDS = 25",
	 "MAX_SENTENCE_WORDS = 40",
	 'test_the_bound_is_a_bound_and_not_a_description_of_the_status_quo'),

	# 5. The walker handles one nesting shape. `afya.strings` carries three — flat, `{lang: {key}}`,
	#    `{lang: {int}}` — so this reports 15 tables and 30 strings while silently skipping the
	#    fifteen that carry the clinical advice, against 30 and 191. A gate that loses 15 of its 30
	#    tables and 161 of its 191 strings without failing. Note the mutation has to remove the
	#    recursion *and* the dispatch into it: deleting only the list branch still recurses every
	#    dict, and every table the test names is dict-nested — which is how the first version of
	#    this canary went MISSED.
	('the walker stops recursing into the nested tables', OB,
	 """		if isinstance(obj, dict):
			for key, value in obj.items():
				collect(value, f'{path}.{key}', out)
			return
		if isinstance(obj, (list, tuple, frozenset, set)):
			for i, value in enumerate(obj):
				collect(value, f'{path}[{i}]', out)""",
	 """		if isinstance(obj, dict):
			for key, value in obj.items():
				if isinstance(value, str) and ' ' in value:
					out[f'{path}.{key}'] = value""",
	 'test_the_walker_sees_the_nested_tables_and_not_only_the_flat_ones'),

	# 6. `NOT_A_MESSAGE` grows to hide a real table. The list is asserted in both directions, so a
	#    name that does not belong is a table quietly exempted from the bound — the filter nobody
	#    re-reads, which is exactly what the both-directions assertion exists to prevent.
	('a real message table is exempted as not-a-message', OB,
	 "	'LANGUAGE_NAME_FOR',",
	 "	'LANGUAGE_NAME_FOR',\n	'TRIAGE_RECS',",
	 'test_a_language_code_is_not_measured_as_a_message'),

	# 7. The reading is dropped from the message. "plain language" then lives in a report beside the
	#    message instead of travelling with it, which is the comment this unit replaced — and a
	#    sender can no longer see what the body it is about to send reads like.
	('the plain-language reading leaves the message', CV,
	 "	@computed_field  # type: ignore[prop-decorator]\n	@property\n	def plain(self) -> PlainLanguageReading:\n		return plain_language(self.body)",
	 "	@computed_field  # type: ignore[prop-decorator]\n	@property\n	def plain(self) -> PlainLanguageReading:\n		return plain_language('Call 719.')",
	 'test_an_sms_carries_its_own_reading_and_still_round_trips'),

	# 8. The body size is folded into `plain`, so a two-segment message is called illegible. §LOC-005's
	#    traveller advisory is two segments and the tree's clearest writing, and §CHAN-1's 160 is a
	#    size while "plain language" is a property — collapsing them refuses correct content.
	('the body size is read as illegibility', OB,
	 "		plain=longest_sentence <= MAX_SENTENCE_WORDS and len(longest_word) <= MAX_WORD_CHARS,",
	 "		plain=longest_sentence <= MAX_SENTENCE_WORDS and len(body) <= MESSAGE_CHARS,",
	 'test_the_body_size_is_reported_separately_from_readability'),
]


def _node(canary_node: str) -> str:
	return canary_node if '/' in canary_node else f'tests/ci/test_chan001.py::{canary_node}'


_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only',
	'tests/ci/test_chan001.py'],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_chan001.{path.name}.bak')
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
	print(f'{"CAUGHT " if caught else "MISSED "} {name}')
	if not caught:
		failures.append(name)
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
