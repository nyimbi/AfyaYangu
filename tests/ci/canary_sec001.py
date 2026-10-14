"""Canaries for tests/ci/test_sec001_history.py.

§SEC-001's "consent audit log visible to the user" was absent because the ledger held *state* and not
*history*: `ConsentRecord.withdrawn` is a boolean, so a grant later revoked and a grant that never
happened were one object with a different flag. The canaries are the cheap ways to make a log that
looks like a history without being one.

The four worth reading as a set:

* **#2** writes the withdrawal over the grant instead of beside it. This is the defect the unit was
  about, reproduced exactly — the person sees that something was withdrawn and cannot see what they
  had agreed to. A dict keyed by consent id does this without anyone intending it.
* **#4** drops the purge line. The log then ends in the middle: the last thing a person did to their
  consent is the one thing missing from it, and it disappears at the moment they go looking.
* **#7** resolves the catalogue words at read time instead of copying them onto the event. Reword the
  catalogue and every historical line silently changes, so the person's own history is rewritten
  under them.
* **#9** gives `live` its own predicate instead of reading `has_category_consent`. Two surfaces
  answering "is this on" from two rules is how a person withdraws something and still sees the
  switch on — and the log is the screen they opened to check.

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
V = ROOT / 'src/afya/privacy/views.py'
G = ROOT / 'src/afya/service.py'
T = ROOT / 'src/afya/strings.py'
M = ROOT / 'src/afya/mobile/actions.py'

CANARIES = [
	# 1. A grant writes no event at all, so the log begins with whatever happened second and the
	#    first thing a person agreed to is absent from their own history.
	('a grant is not logged', S,
	 "		self._consent_events.append(self._event(\n			record, action='granted', category=record.purpose, channel=record.channel,",
	 "		self._consent_events.extend([]) or self._event(\n			record, action='granted', category=record.purpose, channel=record.channel,",
	 'test_a_grant_is_logged'),

	# 2. The withdrawal is written over the grant instead of beside it — the exact defect the unit was
	#    about, reproduced. A dict keyed by consent id does this without anyone intending it.
	('the withdrawal overwrites the grant', S,
	 "		self._consent_events.append(self._event(\n			rec, action='withdrawn', category=rec.purpose, channel=rec.channel,",
	 "		self._consent_events = [self._event(\n			rec, action='withdrawn', category=rec.purpose, channel=rec.channel,",
	 'test_a_grant_and_its_withdrawal_are_two_events'),

	# 3. The log is sorted oldest first, so the entry a person just made is the last one on the
	#    screen — and the history reads as a different history.
	('the log is oldest first', S,
	 "			key=lambda e: (e.at_ms, e.event_id), reverse=True,",
	 "			key=lambda e: (e.at_ms, e.event_id), reverse=False,",
	 'test_the_log_is_newest_first'),

	# 4. The purge writes no event, so the log ends in the middle: the last thing a person did to
	#    their consent is the one line missing from it.
	('a purge is not logged', S,
	 "			self._consent_events.append(self._event(\n				c, action='purged', category=c.purpose, channel=c.channel,",
	 "			self._consent_events.extend([]) or self._event(\n				c, action='purged', category=c.purpose, channel=c.channel,",
	 'test_a_purge_is_logged_and_survives_the_record_it_was_about'),

	# 5. The log is not filtered by subject, so one person's screen shows another's consent history —
	#    a dump rather than a history, and the most direct §17 failure this route could have.
	('the log is not filtered to the subject', S,
	 "			(e for e in self._consent_events if e.subject_ref == subject_ref),",
	 "			(e for e in self._consent_events),",
	 'test_another_subjects_purge_does_not_enter_this_log'),

	# 6. The event stops carrying the catalogue's label, so a log line renders blank where the person
	#    should read what they agreed to.
	('the event loses the catalogue label', S,
	 "			record, action='granted', category=record.purpose, channel=record.channel,\n			label=self._label(record.purpose), consequence=self._consequence(record.purpose),",
	 "			record, action='granted', category=record.purpose, channel=record.channel,\n			label='', consequence=self._consequence(record.purpose),",
	 'test_every_catalogue_category_produces_a_usable_log_line'),

	# 7. The catalogue words are resolved at read time instead of copied onto the event, so rewording
	#    the catalogue rewrites every historical line and the person's own history changes under them.
	('the label is looked up at read time', S,
	 "			(e for e in self._consent_events if e.subject_ref == subject_ref),\n			key=lambda e: (e.at_ms, e.event_id), reverse=True,\n		)",
	 "			(e.model_copy(update={'label': self._label(e.category) + ' (updated)'})\n			 for e in self._consent_events if e.subject_ref == subject_ref),\n			key=lambda e: (e.at_ms, e.event_id), reverse=True,\n		)",
	 'test_the_event_carries_the_catalogue_words_not_a_reference'),

	# 8. A per-sensor grant is logged under its parent category, so a gps grant and a microphone grant
	#    read identically and the person cannot tell which one they switched on.
	('a sensor grant is logged as its parent category', S,
	 "		scope = _CATALOGUE_BY_CATEGORY.get(category)\n		if scope is None or ':' in purpose:\n			return purpose\n		return scope.label",
	 "		scope = _CATALOGUE_BY_CATEGORY.get(category)\n		if scope is None:\n			return purpose\n		return scope.label",
	 'test_a_sensor_grant_is_logged_as_that_sensor'),

	# 9. `live` reads every record rather than the live ones, so a category the person withdrew is
	#    still listed as standing — and the log contradicts the withdrawal it just recorded.
	('live ignores withdrawal', S,
	 "		live = sorted({c.purpose for c in self._consents.values()\n		               if c.subject_ref == subject_ref and not c.withdrawn})",
	 "		live = sorted({c.purpose for c in self._consents.values()\n		               if c.subject_ref == subject_ref})",
	 'test_live_is_the_same_predicate_the_toggles_use'),

	# 10. `live` is not filtered to the subject, so one person's log claims consents granted by
	#     another — the same leak as #5 through the other field. Only `test_a_subject_with_nothing_is_told_so`
	#     holds a second subject, so it is the only node that can catch it: with one subject,
	#     filtered and unfiltered are the same list and the mutation is invisible.
	('live is not filtered to the subject', S,
	 "		live = sorted({c.purpose for c in self._consents.values()\n		               if c.subject_ref == subject_ref and not c.withdrawn})",
	 "		live = sorted({c.purpose for c in self._consents.values() if not c.withdrawn})",
	 'test_a_subject_with_nothing_is_told_so'),

	# 11. The note collapses to one sentence, so "nothing has ever happened" and "everything was
	#     withdrawn" read the same on the screen where a person checks whether the withdrawal took.
	('every state gets the same note', T,
	 "	if not has_events:\n		return table['none']\n	return table['live'] if has_live else table['all_off']",
	 "	return table['live']",
	 'test_a_subject_with_nothing_is_told_so'),

	# 12. The note stops going through `answerable`, so a language with no table raises instead of
	#     serving English — the route 500s where a person asked for their own log.
	('the note stops falling back through answerable', T,
	 "	table = CONSENT_HISTORY_STRINGS[answerable(lang)]",
	 "	table = CONSENT_HISTORY_STRINGS[lang]",
	 'test_the_note_is_served_in_the_language_asked_for'),

	# 13. The event's `action` becomes an open string, so a new code path can write an event nobody
	#     wrote a sentence for and the log renders a state the app never described.
	('the event action is an open string', V,
	 "	action: str = Field(pattern='^(granted|withdrawn|sensor_granted|sensor_withdrawn|purged)$')",
	 "	action: str = Field(min_length=1)",
	 'test_an_unknown_action_is_refused_by_the_model'),

	# 14. The route loses its guard, so the consent history of whoever the caller names is served to
	#     anyone holding a token — a log of what a person agreed to and when.
	('the history route loses its guard', G,
	 "	async def privacy_consent_history(lang: str = 'en',\n	                                  _subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:",
	 "	async def privacy_consent_history(lang: str = 'en') -> dict[str, object]:",
	 'test_the_route_refuses_a_caller_with_no_token'),

	# 15. The route stops reading the caller's subject and answers about a fixed one, so every caller
	#     reads the same person's history.
	('the route answers about the wrong subject', G,
	 "		return privacy.consent_history(_subject, lang).model_dump(mode='json')",
	 "		return privacy.consent_history('someone-else', lang).model_dump(mode='json')",
	 'test_the_route_serves_the_callers_own_log'),

	# 16. The route ignores the language it is given, so a Kiswahili reader is served the English note
	#     on the one screen where the wording is the point.
	('the route ignores the language', G,
	 "		return privacy.consent_history(_subject, lang).model_dump(mode='json')",
	 "		return privacy.consent_history(_subject, 'en').model_dump(mode='json')",
	 'test_the_route_takes_a_language'),

	# 17. The catalogue offers a `subject_ref` field for a route that binds the subject to the token,
	#     so a form draws a control the server refuses — and names a stranger.
	('the catalogue draws a subject field', M,
	 "		_a('consent_history', 'What have I agreed to?', 'Privacy', 'GET', '/privacy/consent/history', [_f('lang', 'Which language?', 'select', TRAVELLER_LANGS)]),",
	 "		_a('consent_history', 'What have I agreed to?', 'Privacy', 'GET', '/privacy/consent/history', [_s(), _f('lang', 'Which language?', 'select', TRAVELLER_LANGS)]),",
	 'test_the_route_names_no_subject_and_so_the_catalogue_offers_no_field'),

	# 18. A channel-default of `app` instead of `unknown` on the carrier door, so a grant whose channel
	#     the caller did not state is logged as one made in the app — a session the person has no
	#     memory of. Only `test_a_grant_made_on_a_channel_is_logged_as_that_channel` calls the door
	#     *without* a channel and reads what came back, so it is the only node that can catch it.
	('a carrier grant is logged as an app grant', S,
	 "	                                   channel: str = 'unknown') -> ConsentRecord:",
	 "	                                   channel: str = 'app') -> ConsentRecord:",
	 'test_a_grant_made_on_a_channel_is_logged_as_that_channel'),

	# 19. The revocation door checks nothing, so a stranger holding a guessed consent id switches off
	#     a grant they are not party to — a denial of care wearing §SEC-001's label, and the reason
	#     `records.revoke_share` looks the grant up before it withdraws it.
	('the withdrawal does not check the owner', S,
	 "		if subject_ref is not None:\n			assert rec.subject_ref == subject_ref, 'a token may withdraw only its own consent'",
	 "		if subject_ref is not None:\n			assert True, 'a token may withdraw only its own consent'",
	 'test_the_route_refuses_a_consent_id_that_is_not_the_callers'),

	# 20. The revocation door answers 200 for an id it never held, so a person is told their consent
	#     was taken back when nothing was touched — the one lie a revocation screen must not tell.
	('an unknown consent id answers ok', G,
	 "		except (KeyError, AssertionError) as exc:\n			raise HTTPException(status_code=404, detail=f'no consent {consent_id!r}') from exc",
	 "		except (KeyError, AssertionError):\n			return {'consent_id': consent_id, 'withdrawn': True}",
	 'test_an_unknown_consent_id_is_not_found'),

	# 20b. The two 404s become tellable apart — a real id that is not the caller's answers with the
	#      ownership message and an id that names nothing answers with "no consent". The guard then
	#      *is* the oracle it was written to close: a stranger walks ids and learns whose exist. This
	#      is the defect the first draft shipped, caught by a live probe and not by a unit test.
	('the two not-found answers differ', G,
	 "		except (KeyError, AssertionError) as exc:\n			raise HTTPException(status_code=404, detail=f'no consent {consent_id!r}') from exc",
	 "		except KeyError as exc:\n			raise HTTPException(status_code=404, detail=f'no consent {consent_id!r}') from exc\n		except AssertionError as exc:\n			raise HTTPException(status_code=404, detail=str(exc)) from exc",
	 'test_the_route_refuses_a_consent_id_that_is_not_the_callers'),

	# 21. The revocation writes no event, so the person revokes and their own log does not record it —
	#     the screen they opened to confirm the revocation is the one that hides it.
	('a revocation writes no event', S,
	 "		self._consent_events.append(self._event(\n			rec, action='withdrawn', category=rec.purpose, channel=rec.channel,",
	 "		self._consent_events.extend([]) or self._event(\n			rec, action='withdrawn', category=rec.purpose, channel=rec.channel,",
	 'test_the_route_withdraws_the_callers_own_consent'),
]


def _node(canary_node: str) -> str:
	return canary_node if '/' in canary_node else f'tests/ci/test_sec001_history.py::{canary_node}'


_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only',
	'tests/ci/test_sec001_history.py'],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_sec001.{path.name}.bak')
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
