"""Canaries for §CHAN-1's callback request and §CHAN-2's two `→` prompts.

The unit these belong to closed three gaps that shared one shape: the product carried the *wording*
of a callback request and the *mechanism* in none. A constant existed and was never reached; a menu
item's own answer text was refused by the handler's assertion; a language prefix the section prints
was parsed nowhere. Every one of them passed whatever test read the tree rather than the walk.

So the canaries here break the *mechanism* and expect a test that exercises the walk to notice —
which is the only kind of test that could have caught any of the three:

* #1 puts the walk back the way it was: the symptom selection answers directly and the prompts are
  never served. The constant, the spec assertion and the audit row all still pass; the test that
  answers `1*1*1*1` must not.
* #2 stops recording the request while still serving the prompt. This is the quieter half of the
  same defect and the more dangerous one — a person is asked whether they want a call, says yes, and
  nothing is filed. A test that only checked the prompt's *text* would pass.
* #3 files a request on a *declined* prompt, which turns the queue into a list of everyone who
  reached the symptom path. The default is the whole point of the field.
* #4 makes the language reply digits-only again, restoring the 500 on the one item §CHAN-2 gives to
  change language.
* #5 accepts an unknown language reply by guessing the nearest match, which puts a person in a
  language nobody chose — the failure the re-served menu exists to avoid.
* #6 reads the language prefix as a substring rather than as a word, so `SWAHILI ni lugha` loses its
  first word and the report that follows is a report with a word missing and nothing saying so.
* #7 drops the Swahili symptom vocabulary, restoring the half-mechanism: the prefix is honoured, the
  answer comes back in Kiswahili, and the fever the person reported is answered with the welcome
  menu.
* #8 matches the Swahili vocabulary shortest-phrase-first, so "maumivu ya kichwa" counts a headache
  twice — a report the triage thresholds read wrong rather than a report that fails loudly.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --`, because the mutation and the real change live in the same uncommitted tree.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
C = ROOT / 'src/afya/channels/service.py'
S = ROOT / 'src/afya/strings.py'
R = ROOT / 'src/afya/service.py'
T = ROOT / 'tests/ci/test_chan_callbacks.py'
I = ROOT / 'tests/ci/test_integrations.py'

CANARIES = [
	# 1. The original defect: the walk answers the symptom selection directly and the two prompts are
	#    never reached. `USSD_YES_NO_PROMPTS` still exists, still matches the spec, and is still cited
	#    by an audit row — the tree is unchanged in every respect a reader of the tree can see.
	('the walk answers without asking the prompts', C,
	 "			answers = segments[2:]\n			if not answers:",
	 "			answers = segments[2:]\n			if not answers or True:",
	 'test_the_two_prompts_are_reached_and_the_spec_prints_them'),

	# 2. The prompt is served and the request is dropped. The walk looks right, the closing screen
	#    says a health worker will call, and no one is queued — worse than the defect above, because
	#    the person is told a call is coming.
	('the request is served but not recorded', C,
	 "			if callback:\n				self.record_callback(",
	 "			if callback and False:\n				self.record_callback(",
	 'test_a_callback_request_is_recorded_and_readable'),

	# 3. A declined prompt files a request, which fills the queue with everyone who reached the
	#    symptom path. The default `False` is load-bearing and this is what it is holding back.
	('a declined prompt files a request', C,
	 "			if callback:\n				self.record_callback(",
	 "			if True:\n				self.record_callback(",
	 'test_answering_no_requests_nothing'),

	# 4. The digits-only assertion comes back, and §CHAN-2's item 5 — whose own answer text says
	#    "Reply with the one you want" — is a 500 again on a feature phone.
	('the language reply is refused as non-numeric', C,
	 "		if req.text.strip() and req.text.strip()[0].isalpha():\n			return self._ussd_language_choice(req, req.text.strip())",
	 "		if False:\n			return self._ussd_language_choice(req, req.text.strip())",
	 'test_item_five_takes_a_word_rather_than_a_digit'),

	# 5. An unknown language reply is matched to *something* rather than re-serving the menu. A
	#    nearest-match is how a person ends up in a language nobody chose, and the reply would look
	#    like a success from every angle except the one that matters.
	('an unknown language reply is answered anyway', C,
	 "		if code is None:",
	 "		if code is None and False:",
	 'test_an_unknown_language_reply_reserves_the_menu'),

	# 6. The prefix is read as a substring, so `SWAHILI ni lugha` is stripped to `AHILI ni lugha` and
	#    the report silently loses its first word. This is the failure the word boundary is for, and
	#    it is invisible without a test that asserts the remainder.
	('the prefix is matched inside a word', S,
	 "	word = head.rstrip(':').upper()",
	 "	word = stripped[:2].upper()",
	 'test_a_body_with_no_prefix_is_unchanged'),

	# 7. The Swahili symptom vocabulary goes, restoring the half-mechanism: the prefix is honoured,
	#    the reply comes back in Kiswahili, and the fever is answered with the welcome menu. Every
	#    assertion about the *prefix* still passes; only the report is lost.
	('a Swahili report names no symptom', S,
	 "	words = SYMPTOM_WORDS_BY_LANG.get(served, {})",
	 "	words = {}",
	 'test_a_report_written_in_kiswahili_reaches_the_engine'),

	# 8. The duplicate guard goes, so "maumivu ya kichwa" counts a headache twice — once for the
	#    phrase and once for the inner "kichwa". A doubled symptom is not a loud failure: it is a
	#    report the triage thresholds read wrong, which is why the assertion is on the list itself.
	#    Note the earlier cut of this canary flipped the phrase *order* and was MISSED — the order
	#    only decides which position is recorded, and the `key in claimed` guard is what holds. A
	#    canary that passes is a claim about the code that the code does not make.
	('a symptom is counted twice', S,
	 "		if at < 0 or key in claimed:",
	 "		if at < 0:",
	 'test_a_report_written_in_kiswahili_reaches_the_engine'),

	# 9. The route stops reading the prefix off the body, which is where the mechanism had no
	#    implementation at all — the sender of a text cannot set a query parameter.
	('the inbound route ignores the prefix', R,
	 "		asked_lang, body = sms_language(body)",
	 "		asked_lang, body = 'en', body",
	 'test_inbound_sms_reads_the_language_prefix_off_the_body'),

	# 10. The `CALLBACK` keyword is matched as a substring, so a person writing *about* a call gets a
	#     queue entry against them. The whole-word match is what keeps a mention out of the queue.
	('the keyword matches inside a message', R,
	 "		if body.strip().upper() == 'CALLBACK':",
	 "		if 'CALLBACK' in body.strip().upper():",
	 'test_the_callback_keyword_files_a_request'),

	# 11. A prompt screen carries the submenu as well as the question. Every prompt is still served,
	#     every path still ends, and the caller is cut off mid-sentence on a feature phone — which is
	#     §CHAN-2's Session limits, a constraint on the walk rather than on any one string. A test
	#     that only checked the prompts' *text* would pass, and so would one that checked the menu
	#     alone: the budget is spent by the screens together.
	('a prompt screen carries the submenu too', C,
	 "		return f'CON {recommendation}\\n{ussd_label(prompt, served)}'",
	 "		return f'CON {recommendation}\\n{ussd_label(prompt, served)}\\n{USSD_MENU[served]}\\n{ussd_symptom_menu_text(served)}'",
	 'test_every_screen_the_walk_serves_fits_the_sections_budget'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_chan002.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	# A same-second write of the same size reuses the previous canary's bytecode, and the canary then
	# tests code it never mutated. Purged for the file just written.
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	# The node names its own file: a canary aimed at a nonexistent node makes pytest exit non-zero
	# on a *collection* error, which reads as CAUGHT.
	suite = I if node.startswith(('test_inbound_sms_reads', 'test_the_callback_keyword')) else T
	target = f'{suite.relative_to(ROOT)}::{node}'
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', target],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
		# A canary caught for the wrong reason is not a canary that fired. The node it names has to
		# appear in the output, or pytest exited non-zero on a collection error somewhere else.
		aimed = node in proc.stdout
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
	print(f'{"CAUGHT " if caught and aimed else "MISSED "} {name}')
	if not (caught and aimed):
		failures.append(name)
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
