"""Canaries for tests/ci/test_acc002.py.

§ACC-002's two closable bullets are both *a step that was skipped*, and a skipped step is the
easiest kind of defect to ship because the payload still looks right:

* **"voice-to-text for CHW notes"** was missing because the route took a transcript and returned an
  `intent`. The cheap fix is to keep doing that and call the note a note — canary #3 — which passes
  any test that reads `transcript` and never asks whether the words were *classified*.
* **"voice note triage on WhatsApp"** was missing because a note's media reference was read as the
  message body. The cheap fix is a branch that transcribes and then answers from the transcript
  without triaging it — canary #5 — and the note is heard, written down, and acted on by nobody.

The canaries worth reading as a set are #1, #5 and #9. #1 is the front end that is *nearly* right:
whisper decodes a wrong spectrogram into fluent, confident text, so nothing downstream can catch
it. #5 is a transcript with no verdict. #9 is the six-language bullet closed by widening a list,
which is the failure `test_personas.py` was written to prevent and this module inherits.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script. The `__pycache__`
purge after each write is load-bearing for the reason `canary_inf001.py` documents: two canaries
mutating two files with same-length edits in the same second make CPython reuse the previous
canary's bytecode, and the gate then reports a mutation it never made.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
SP = ROOT / 'src/afya/ml/speech.py'
AS = ROOT / 'src/afya/access/service.py'
AV = ROOT / 'src/afya/access/views.py'
CS = ROOT / 'src/afya/channels/service.py'
CV = ROOT / 'src/afya/channels/views.py'
CM = ROOT / 'src/afya/community/views.py'
MO = ROOT / 'src/afya/mobile/actions.py'
ST = ROOT / 'src/afya/strings.py'

CANARIES = [
	# 1. The symmetric Hann window, where whisper uses the periodic one. The two differ by one
	#    sample of phase, and the structural assertion in `test_the_window_is_periodic_not_symmetric`
	#    is what catches it — `periodic[1] > 0.0` fails for `np.hanning`, whose second sample is
	#    still zero.
	#
	#    Pointed here and NOT at the transcript test, because the transcript test cannot see this:
	#    measured, both windows produce the identical, correct sentence for `speech_en.wav`. An
	#    earlier version of this canary claimed the symmetric window yields "After early morning,"
	#    and that claim was wrong — it was a real bug (a truncated prompt), but not this one. A
	#    canary whose stated mechanism does not hold is a canary nobody can trust when it passes.
	('the window is the symmetric one', SP,
	 "	return (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / n)).astype(np.float32)",
	 "	return np.hanning(n).astype(np.float32)",
	 'test_the_window_is_periodic_not_symmetric'),

	# 2. The language prompt token is dropped, so the model auto-detects from a three-word report.
	#    Auto-detection on an utterance that short is a coin toss, and a wrong toss is a fluent
	#    transcript of the wrong words.
	('the language is no longer prompted', SP,
	 "		prompt = [SOT, self._tok.lang_ids[lang], TRANSCRIBE, NO_TIMESTAMPS]",
	 "		prompt = [SOT, TRANSCRIBE, NO_TIMESTAMPS]",
	 'test_real_speech_is_transcribed_to_the_words_that_were_said'),

	# 3. A note is classified as a symptom report. This is the predecessor's behaviour and the
	#    defect the bullet names: the dictation is discarded and `intent=unknown` comes back.
	('a note is triaged as a symptom report', AS,
	 "		if req.purpose == 'note':",
	 "		if False:",
	 'test_a_note_is_kept_as_text_and_not_triaged'),

	# 4. The symptoms stop being read out of free text, so "fever and headache" is answered at the
	#    fever intent and the headache is lost — §ACC-002's first bullet as a menu rather than a
	#    report.
	('symptoms stop being read out of the utterance', AS,
	 "		symptoms = [s for s in VOICE_SYMPTOM_WORDS if s in lowered]",
	 "		symptoms: list[str] = []",
	 'test_a_symptom_named_in_free_text_is_read_out_of_it'),

	# 5. The audio path transcribes and never triages. The note is heard and written down, and no
	#    verdict follows it — the WhatsApp bullet with the triage half removed.
	('the audio path transcribes but does not triage', AS,
	 "		return served.model_copy(update={",
	 "		return served.model_copy(update={'intent': 'note',",
	 'test_the_audio_path_returns_a_transcript_and_the_same_verdict'),

	# 6. `served_in` claims the requested language. A Dholuo speaker then reads English believing
	#    it is Dholuo, which is the one outcome the field exists to prevent.
	('served_in claims the language that was asked for', AS,
	 "		served = answerable(req.lang)",
	 "		served = req.lang",
	 'test_the_answer_says_which_language_it_was_served_in'),

	# 7. An audio request is answered from a stub when no recogniser is deployed, so a transcript
	#    nobody produced is served as if a model had made it.
	('audio is answered with no recogniser deployed', AS,
	 "		assert self._speech is not None, (\n			'the speech model is not deployed (models/speech); audio cannot be transcribed without it')",
	 "		assert True, (\n			'the speech model is not deployed (models/speech); audio cannot be transcribed without it')",
	 'test_the_audio_path_refuses_when_no_recogniser_is_deployed'),

	# 8. The recogniser stops refusing a language it was never trained on, so a Dholuo recording is
	#    fed to an English model and comes back as fluent text of words nobody said.
	('the recogniser accepts a language it does not know', SP,
	 "		assert lang in self._tok.lang_ids, f'{lang} is not a language this recogniser was trained on'",
	 "		assert True, f'{lang} is not a language this recogniser was trained on'",
	 'test_audio_is_refused_in_a_language_the_recogniser_does_not_know'),

	# 9. The six-language bullet is closed by widening `SUPPORTED_LANGS`. This is the exact failure
	#    the whole test module guards: an untranslated table reported as a shipped feature.
	#
	#    The target is the *definition*, not a literal: `SUPPORTED_LANGS` is `frozenset(TRIAGE_RECS)`,
	#    and an earlier version of this canary looked for `frozenset({'en', 'sw'})` — a string that
	#    appears nowhere. Its `assert count == 1` fired, and because this script asserts rather than
	#    continuing, canaries #10-#16 never ran at all. A canary that crashes the runner is a canary
	#    that silently deletes every canary after it.
	('the open language gap is closed by widening the table list', ST,
	 "SUPPORTED_LANGS: frozenset[str] = frozenset(TRIAGE_RECS)",
	 "SUPPORTED_LANGS: frozenset[str] = frozenset(TRIAGE_RECS | {'luo', 'bxk', 'kln', 'ki'})",
	 'test_the_six_language_bullet_stays_open'),

	# 10. The mobile dropdown offers a language the recogniser was not trained on, so the app
	#     promises a transcript of words nobody said.
	('the voice dropdown offers a language recognition does not ship for', MO,
	 "VOICE_LANGS = sorted(code for code in TRAVELLER_LANGS if LANGUAGE_MATRIX_ASR.get(code))",
	 "VOICE_LANGS = sorted(code for code in LANGUAGE_MATRIX_ASR)",
	 'test_the_voice_langs_offered_are_the_ones_recognition_ships_for'),

	# 11. A WhatsApp voice note is read as text again — the original defect, where the media
	#     reference goes through the keyword map and a note is answered at the low risk level.
	('a voice note is read as a text body', CS,
	 "		assert msg.kind == 'text', (\n			'a voice note has no body to read; route it through `route_whatsapp_voice`, which '\n			'transcribes it first'\n		)",
	 "		assert True, (\n			'a voice note has no body to read; route it through `route_whatsapp_voice`, which '\n			'transcribes it first'\n		)",
	 'test_a_voice_note_is_not_read_as_text'),

	# 12. The voice-note branch stops checking it was handed a note, so a text message routed at the
	#     voice path is transcribed as if it were audio.
	('the voice branch accepts a text message', CS,
	 "		assert msg.kind == 'voice', 'this path transcribes a voice note and not a text message'",
	 "		assert True, 'this path transcribes a voice note and not a text message'",
	 'test_a_text_message_is_not_routed_through_the_voice_path'),

	# 13. The channel layer answers a note with no recogniser wired, so a stub transcript reaches a
	#     triage verdict.
	('the channel layer answers a note with no recogniser', CS,
	 "		assert self._access is not None, (\n			'the accessibility service is not wired into the channel layer; a voice note cannot be '\n			'transcribed without it'\n		)",
	 "		assert True, (\n			'the accessibility service is not wired into the channel layer; a voice note cannot be '\n			'transcribed without it'\n		)",
	 'test_the_channel_layer_refuses_a_note_when_no_recogniser_is_wired'),

	# 14. A voice note with no declared language is accepted, and the recogniser is pointed at
	#     whatever the default is — which is guessing which language to mis-hear the person in.
	('a voice note may declare no language', CV,
	 "		assert self.kind != 'voice' or self.voice_note_lang is not None, (\n			'a voice note arrived with no language declared, and recognition ships per language'\n		)",
	 "		assert True, (\n			'a voice note arrived with no language declared, and recognition ships per language'\n		)",
	 'test_a_voice_note_with_no_language_is_refused_at_the_model'),

	# 15. A case report keeps a transcript with no language, or a language with no transcript —
	#     which is exactly how the field looked implemented while nothing recorded a note.
	('a case report carries half a voice note', CM,
	 "		assert (self.voice_note is None) == (self.voice_note_lang is None), (",
	 "		assert True or (self.voice_note is None) == (self.voice_note_lang is None), (",
	 'test_a_note_without_its_language_is_refused'),

	# 16. The audio route loses its guard, so the `subject_ref` in the query is whoever the caller
	#     typed and a recording is transcribed for a stranger.
	('the audio route loses its guard', ROOT / 'src/afya/service.py',
	 "		file: UploadFile = File(...), subject_ref: str = '', lang: str = 'en', purpose: str = 'symptoms',\n		_subject: str = Depends(require_self()),",
	 "		file: UploadFile = File(...), subject_ref: str = '', lang: str = 'en', purpose: str = 'symptoms',",
	 'test_the_audio_route_will_not_transcribe_for_someone_else'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_acc002.{path.name}.bak')
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
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly',
			f'tests/ci/test_acc002.py::{node}'], cwd=ROOT, capture_output=True, text=True)
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
