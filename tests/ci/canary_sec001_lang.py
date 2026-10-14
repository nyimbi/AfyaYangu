"""Canaries for tests/ci/test_sec001_consent_language.py.

§SEC-001's "Plain-language explanations in local languages" was the section's last `missing` row, and
the reason it was missing is the shape this repo keeps finding: every visible part existed and the
join did not. There was a catalogue, a sentence beside each toggle, a route serving it and a log
copying it — and no way for the sentence to be in any language but English.

These are the cheap ways to make a screen *look* multilingual without being it. The four worth
reading as a set:

* **#2** leaves one Swahili field holding the English string. The screen renders Swahili, the count
  of "languages we serve" is unchanged, and the person reads English believing it is her language —
  which on this screen is the difference between consent that was informed and consent that merely
  looks like it.
* **#4** stops the fallback going through `answerable`, so a language with no table raises instead of
  serving English and the toggle screen 500s for exactly the people the bullet is about.
* **#6** resolves the log's sentences in the *reader's* language rather than the record's, so a grant
  made in Swahili is displayed in English to anyone who opens the history — and the log's whole
  design is that it says what the person was told at the time.
* **#8** removes the catalogue action. The route keeps serving the explanation and no client can
  reach the screen for the question §SEC-001's first bullet is about: the second defect this unit
  found, and the one a green service test cannot see.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary that
passes is a bug in the canary, so a MISSED line is a failure of this script. The `__pycache__` purge
after each write is load-bearing for the reason `canary_inf001.py` documents: two canaries mutating
two files with same-length edits in the same second make CPython reuse the previous canary's
bytecode, and the gate then reports a mutation it never made.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
S = ROOT / 'src/afya/privacy/service.py'
T = ROOT / 'src/afya/strings.py'
G = ROOT / 'src/afya/service.py'
M = ROOT / 'src/afya/mobile/actions.py'

CANARIES = [
	# 1. The catalogue stops taking its label from the table and carries its own, so the sentence a
	#    toggle serves and the sentence the log copies are two facts that agree only until one is
	#    edited. The row was found in exactly this state — English literals in the service with no
	#    table behind them — and the fix was to build the catalogue *from* the table.
	('the catalogue carries its own label instead of the table', S,
	 "		**consent_scope_text(category.value),",
	 "		**{**consent_scope_text(category.value), 'label': 'Consent'},",
	 'test_the_catalogue_is_built_from_the_string_table_rather_than_restating_it'),

	# 2. One Swahili field holds the English string. The table still has two languages, every count
	#    still says two, and the person reads English under a Swahili heading. This is the mutation
	#    that makes the row *look* closed while leaving it exactly as open as it was.
	('a Swahili sentence is the English one', T,
	 "			'explains': 'Tunahifadhi dalili unazoandika ili wewe na mhudumu wako wa afya muone jinsi umekuwa.',",
	 "			'explains': 'We store the symptoms you log so you and your health worker can see how you have been.',",
	 'test_the_swahili_is_not_the_english_under_a_swahili_key'),

	# 3. A category is translated in English and not in Swahili, so the two key sets diverge. The
	#    import-time assertion turns this into a refusal to start rather than a KeyError on one
	#    screen — which is why the harness reports it as `collect` and not as a test failure: the
	#    module never loads, and a collection error that reads as CAUGHT is the trap this script
	#    names in its docstring. Reported distinctly so a reader can see which one fired.
	('a category is translated in one language only', T,
	 "		'research': {\n			'label': 'Ruhusu matumizi ya utafiti',\n			'explains': 'Taarifa zisizotambulisha mtu zinaweza kutumika kuchunguza jinsi ugonjwa huenea. Hili halihitajiki kamwe.',\n			'on_withdrawal': 'Taarifa zako hazitatumika katika utafiti. Hakuna kingine kinachobadilika.',\n		},\n	},\n}",
	 "	},\n}",
	 'test_every_category_the_section_names_is_translated_in_every_language'),

	# 4. The fallback stops going through `answerable`, so a language with no table raises KeyError
	#    instead of serving English — the toggle screen 500s for exactly the speakers the bullet is
	#    about, and the client cannot even tell them it has no table.
	('the fallback stops going through answerable', T,
	 "	return CONSENT_SCOPE_STRINGS[answerable(lang)][slug]",
	 "	return CONSENT_SCOPE_STRINGS[lang][slug]",
	 'test_a_language_with_no_table_is_served_english_and_told_so'),

	# 5. `served_in` reports the language that was *asked for* rather than the one served, so a
	#    Dholuo speaker is shown English and told it is Dholuo. The fallback exists to be visible; a
	#    fallback reported as a success is worse than no report at all.
	('served_in reports the language asked for', S,
	 "				served_in=served, language_fallback=served != lang,",
	 "				served_in=lang, language_fallback=False,",
	 'test_a_language_with_no_table_is_served_english_and_told_so'),

	# 6. The log resolves its sentences in the reader's language instead of the record's. A grant made
	#    in Swahili then reads in English to anyone who opens the history — and the log's entire
	#    design is that it carries what the person was told at the time, not what the catalogue says
	#    now or what the reader would prefer.
	('the log renders in the reader language not the record', S,
	 "		self._consent_events.append(self._event(\n			record, action='granted', category=record.purpose, channel=record.channel,\n			label=self._label(record.purpose, record.lang),\n			consequence=self._consequence(record.purpose, record.lang), lang=record.lang,",
	 "		self._consent_events.append(self._event(\n			record, action='granted', category=record.purpose, channel=record.channel,\n			label=self._label(record.purpose, 'en'),\n			consequence=self._consequence(record.purpose, 'en'), lang='en',",
	 'test_the_grant_records_the_language_it_was_made_in'),

	# 7. The phone door stops writing the session's language onto the record, so a USSD grant read
	#    back in the app says English whatever menu the person actually read — the record claiming an
	#    explanation was given in a language it was not, on the one screen where that must not happen.
	('the record does not carry the language', S,
	 "			retention_days=retention_days, legal_basis=LegalBasis.consent, channel=channel,\n			lang=lang,\n		))",
	 "			retention_days=retention_days, legal_basis=LegalBasis.consent, channel=channel,\n			lang='en',\n		))",
	 'test_the_phone_door_carries_the_sessions_language'),

	# 8. The catalogue action is removed. The route goes on serving the explanation and no client can
	#    reach it: a client could record a grant and withdraw one, and had no screen for the question
	#    §SEC-001's first bullet is about. This is the join the section was missing twice over, and
	#    no service-level test can see it.
	('the toggle screen has no catalogue action', M,
	 "	_a('consent_choices', 'What am I agreeing to?', 'Privacy', 'GET', '/privacy/consent', [_f('lang', 'Which language?', 'select', TRAVELLER_LANGS)]),",
	 "",
	 'test_the_toggle_screen_has_a_catalogue_action'),

	# 9. The route ignores the language it is given, so a Kiswahili reader is served the English
	#    catalogue — the service is correct and the front door is where the parameter is dropped.
	#    A green service test says nothing about what the route serves, which is why this node curls it.
	('the route ignores the language it is given', G,
	 "		return {\n			'toggles': [t.model_dump(mode='json')\n			            for t in privacy.consent_toggles(granted, sensor_grants, lang)],\n			'sensors': privacy.sensor_consents(),\n			'lang': answerable(lang),\n			'language_fallback': answerable(lang) != lang,\n		}",
	 "		return {\n			'toggles': [t.model_dump(mode='json')\n			            for t in privacy.consent_toggles(granted, sensor_grants, 'en')],\n			'sensors': privacy.sensor_consents(),\n			'lang': 'en',\n			'language_fallback': False,\n		}",
	 'test_the_catalogue_route_serves_the_language_it_was_asked_for'),

	# 10. A sentence renders its own slug, so a person deciding whether to trust the product with her
	#     health data reads `symptom_storage` where the explanation should be.
	('a sentence renders its own slug', T,
	 "			'label': 'Keep my symptom history',",
	 "			'label': 'symptom_storage',",
	 'test_no_spec_code_or_internal_slug_reaches_a_sentence_a_person_reads'),
]


def _node(canary_node: str) -> str:
	return canary_node if '/' in canary_node else f'tests/ci/test_sec001_consent_language.py::{canary_node}'


_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only',
	'tests/ci/test_sec001_consent_language.py'],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_sec001_lang.{path.name}.bak')
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
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', _node(node)],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
		# A module that refuses to import fails collection, not the test. That is still the gate
		# working — the import-time assertion is the gate for a diverged table — but it is a different
		# failure from an assertion in the named node, and a reader should not have to guess which.
		mode = 'collect' if 'ERROR' in proc.stdout or 'errors' in proc.stdout else 'test'
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
	print(f'{"CAUGHT" if caught else "MISSED"} [{mode}] {name}')
	if not caught:
		failures.append(name)
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
