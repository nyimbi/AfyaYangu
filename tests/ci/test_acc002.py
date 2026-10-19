"""§ACC-002 Multilingual Voice Interface — the three bullets that were not carried.

The section lists five Features. Two were already carried (`LANGUAGE_MATRIX`'s `tts` flag, and the
offline intent map), and this module holds the closure of two more:

* **"Voice-to-text for CHW notes and case descriptions"** — the route took a `VoiceRequest`, which
  is a *transcript*, and returned an `intent`. A CHW dictating "the patient's house is behind the
  market, three children, one with a rash" got `intent=unknown` and their words discarded, because
  a note is not a symptom report and running it through the intent map answers a question nobody
  asked. `purpose='note'` makes the transcript the result.
* **"Voice note triage on WhatsApp"** — a WhatsApp voice note arrives as *media*. The router read
  the media reference as the message body, found no symptom word in it, and answered at the low
  risk level. `/channels/whatsapp/voice` transcribes first and then triages through the same engine.

The third — **"Voice-guided symptom reporting in Swahili, Dholuo, Luhya, Kalenjin, Kikuyu, and
English"** — stays `missing`, and `test_the_six_language_bullet_stays_open` is the test that says
why. Four of its six named languages have no string table and no recognition, and inventing either
would report the gap as closed. What the voice path does instead is serve English on §ACC-002's own
`answerable` rule and *say which language it served*.

The recogniser is real: `WhisperSpeechEngine` runs whisper-tiny int8 through `onnxruntime` with a
numpy log-mel front end, and the audio fixtures in `tests/ci/fixtures/` are real speech. A test
that asserted a transcript against a stub would prove the plumbing and nothing about the words.
"""
import io
import wave
from pathlib import Path

import numpy as np
import pytest
from conftest import sign, sign_multipart
from fastapi.testclient import TestClient
from pydantic import ValidationError

from afya.access.service import VOICE_UNRECOGNISED, AccessService
from afya.access.views import LANGUAGE_MATRIX, VoiceAudioRequest, VoiceRequest
from afya.channels.service import AfricaTalkingSmsPort, ChannelService
from afya.channels.views import WhatsAppIn
from afya.ml.speech import N_FFT, N_MELS, SR, WhisperSpeechEngine, log_mel, periodic_hann

FIXTURES = Path(__file__).resolve().parent / 'fixtures'
SPEECH_EN = FIXTURES / 'speech_en.wav'
SPEECH_LONG = FIXTURES / 'speech_en_long.wav'


def _engine() -> WhisperSpeechEngine:
	"""The real recogniser, or a skip. The assets are 41 MB and not every checkout has them."""
	try:
		return WhisperSpeechEngine()
	except (FileNotFoundError, AssertionError) as exc:  # pragma: no cover - deployment dependent
		pytest.skip(f'models/speech is not deployed: {exc}')


def _token(c: TestClient, subject: str = 'U-1') -> dict[str, str]:
	r = c.post('/auth/anonymous', json={'subject_ref': subject})
	assert r.status_code == 200, r.text
	return {'authorization': f'Bearer {r.json()["token"]}'}


def _wav_bytes(path: Path) -> bytes:
	return path.read_bytes()


# --- the recogniser itself ----------------------------------------------------------------

async def test_the_front_end_matches_the_published_constants() -> None:
	"""OpenAI's own numbers, asserted rather than trusted. A front end that is *nearly* right is
	the failure this module is written around: whisper decodes a wrong spectrogram into fluent
	text, so nothing downstream can catch it."""
	features = log_mel(np.zeros(SR * 3, dtype=np.float32))
	assert features.shape == (N_MELS, 3000), '30 s of audio must yield 3000 frames'
	assert features.dtype == np.float32
	assert N_FFT == 400 and N_MELS == 80 and SR == 16_000


async def test_the_window_is_periodic_not_symmetric() -> None:
	"""`np.hanning` is the *symmetric* window and is wrong here. The two differ by one sample of
	phase; with the symmetric one every transcription comes back plausible and wrong."""
	periodic = periodic_hann(400)
	assert periodic[0] == 0.0, 'a periodic window starts at zero'
	assert periodic[1] > 0.0, 'a periodic window rises immediately'
	assert not np.allclose(periodic, np.hanning(400)), 'the symmetric window is the wrong one'


async def test_real_speech_is_transcribed_to_the_words_that_were_said() -> None:
	"""The fixture is a recording of a known sentence, and the assertion is on the *words*.

	This is the test that would catch a broken front end, a wrong prompt, or the merged decoder's
	cache branch (which produces "After early morning, the" for this audio — fluent, confident and
	wrong).
	"""
	engine = _engine()
	result = engine.transcribe_wav(SPEECH_EN, 'en')
	assert result.lang == 'en' and result.on_device is True and result.tokens > 10
	words = result.transcript.lower()
	assert 'after early nightfall' in words, result.transcript
	assert 'yellow lamps' in words, result.transcript
	assert 'brothels' in words, result.transcript


async def test_a_longer_recording_keeps_its_ending() -> None:
	"""The 30 s window is not a truncation hazard, but the token budget is. A cap that cut the
	utterance short would be a note that loses its last clause — and the last clause of a case
	description is usually the finding."""
	engine = _engine()
	result = engine.transcribe_wav(SPEECH_LONG, 'en')
	words = result.transcript.lower()
	assert 'god' in words and words.startswith('god'), result.transcript
	assert 'blessed soul in heaven' in words, result.transcript


async def test_the_recogniser_reports_the_languages_it_was_trained_on() -> None:
	"""Read off the weights, not written here. The comparison that matters is against §ACC-002's
	`LANGUAGE_MATRIX`, and `test_the_six_language_bullet_stays_open` is where that lands."""
	engine = _engine()
	langs = engine.languages()
	assert 'en' in langs and 'sw' in langs, 'the model is multilingual and must carry both'
	assert 'luo' not in langs, 'Dholuo is not a whisper language and must not be claimed as one'


async def test_audio_is_refused_in_a_language_the_recogniser_does_not_know() -> None:
	engine = _engine()
	wave_samples = np.zeros(SR, dtype=np.float32)
	with pytest.raises(AssertionError, match='not a language this recogniser'):
		engine.transcribe(wave_samples, 'luo')


async def test_the_engine_refuses_samples_it_cannot_be_trusted_with() -> None:
	engine = _engine()
	with pytest.raises(AssertionError, match='float32'):
		engine.transcribe(np.zeros(SR, dtype=np.int16), 'en')
	with pytest.raises(AssertionError, match='half a second'):
		engine.transcribe(np.zeros(SR // 4, dtype=np.float32), 'en')
	with pytest.raises(AssertionError, match='normalised'):
		engine.transcribe(np.full(SR, 4.0, dtype=np.float32), 'en')


async def test_the_wav_reader_refuses_the_wrong_shape_of_file() -> None:
	"""16 kHz mono 16-bit, the same contract §SENS-002's cough engine takes. A stereo or 8 kHz
	file read as if it were mono 16 kHz is a transcript of the wrong thing."""
	engine = _engine()
	stereo = io.BytesIO()
	with wave.open(stereo, 'wb') as fh:
		fh.setnchannels(2)
		fh.setsampwidth(2)
		fh.setframerate(SR)
		fh.writeframes(np.zeros(2 * SR, dtype=np.int16).tobytes())
	bad = FIXTURES / '_stereo_tmp.wav'
	bad.write_bytes(stereo.getvalue())
	try:
		with pytest.raises(AssertionError, match='mono'):
			engine.transcribe_wav(bad, 'en')
	finally:
		bad.unlink(missing_ok=True)


# --- the text path: symptoms read out of an utterance -------------------------------------

async def test_a_note_is_kept_as_text_and_not_triaged() -> None:
	"""The bullet that was missing. A note has no intent and no recommendation, and running it
	through the intent map discarded the dictation and answered `intent=unknown`."""
	svc = AccessService()
	out = svc.transcribe(VoiceRequest(
		subject_ref='CHW-1', lang='en', purpose='note',
		utterance="the patient's house is behind the market, three children, one with a rash",
	))
	assert out.transcript == "the patient's house is behind the market, three children, one with a rash"
	assert out.intent == 'note', 'a note is not a triage'
	assert out.symptoms == [], 'a note is not read for symptoms either'
	assert out.confidence == 1.0
	assert out.recogniser is None, 'no recognition ran on a transcript that was already text'


async def test_a_symptom_named_in_free_text_is_read_out_of_it() -> None:
	"""§ACC-002's first bullet is a *report*, not a menu. The predecessor matched six keyword
	intents and dropped everything else, so "fever and headache since Tuesday" was answered at the
	fever intent and the headache was lost."""
	svc = AccessService()
	out = svc.transcribe(VoiceRequest(
		subject_ref='U-1', lang='en', utterance='I have had fever and headache since Tuesday'))
	assert out.intent == 'triage'
	assert set(out.symptoms) == {'fever', 'headache'}, out.symptoms


async def test_a_symptom_with_no_intent_keyword_still_enters_the_engine() -> None:
	"""The sharpest case: "I have been vomiting" names no intent keyword at all, and the
	predecessor returned `intent=unknown` — the words were heard and the finding was lost."""
	svc = AccessService()
	out = svc.transcribe(VoiceRequest(subject_ref='U-1', lang='en', utterance='I have been vomiting'))
	assert out.intent == 'triage'
	assert out.symptoms == ['vomiting']


async def test_an_utterance_naming_nothing_is_answered_as_unrecognised() -> None:
	svc = AccessService()
	out = svc.transcribe(VoiceRequest(subject_ref='U-1', lang='en', utterance='the weather is fine'))
	assert out.intent == 'unknown' and out.symptoms == [] and out.confidence < 0.5


async def test_the_answer_says_which_language_it_was_served_in() -> None:
	"""§ACC-002 lists six languages for this bullet and two have tables. The gap is served, not
	hidden: `lang` is what the caller asked for and `served_in` is what they got.

	The assertion that can actually fail is the Dholuo one. `en` and `sw` both have tables, so
	`served_in` equals `lang` for either of them and a test built from those two passes against a
	route that ignores `answerable` entirely. `luo` is in `LANGUAGE_MATRIX` — the section names it
	first after Kiswahili — and has no table, which is what makes the fallback visible.
	"""
	svc = AccessService()
	sw = svc.transcribe(VoiceRequest(subject_ref='U-1', lang='sw', utterance='nina homa'))
	assert sw.lang == 'sw' and sw.served_in == 'sw'
	en = svc.transcribe(VoiceRequest(subject_ref='U-1', lang='en', utterance='I have fever'))
	assert en.served_in == 'en'
	luo = svc.transcribe(VoiceRequest(subject_ref='U-1', lang='luo', utterance='an gi penjo'))
	assert luo.lang == 'luo', 'the caller asked for Dholuo and that is what they asked for'
	assert luo.served_in == 'en', 'and this is the language they actually got'
	assert luo.spoken_reply == VOICE_UNRECOGNISED['en'], 'the reply is the English one, not a guess'
	assert luo.spoken_reply != VOICE_UNRECOGNISED['sw'], 'and specifically not the Kiswahili one'


async def test_a_language_the_matrix_does_not_list_is_refused() -> None:
	svc = AccessService()
	with pytest.raises(AssertionError, match='unsupported language'):
		svc.transcribe(VoiceRequest(subject_ref='U-1', lang='xx', utterance='hello'))


async def test_the_audio_path_returns_a_transcript_and_the_same_verdict() -> None:
	"""Both halves in one call: the recogniser produces the words, and `transcribe` — the *same*
	method the typed path uses — answers them. Two paths that could diverge would be two answers
	to one recording."""
	engine = _engine()
	svc = AccessService(engine)
	note = svc.transcribe_audio(
		VoiceAudioRequest(subject_ref='U-1', lang='en', purpose='note'), SPEECH_EN)
	assert 'nightfall' in note.transcript.lower()
	assert note.intent == 'note' and note.recogniser == 'whisper-tiny/en'
	assert note.on_device is True
	# The same audio asked as a symptom report must NOT come back as a note: `purpose` has to
	# survive the transcription, or every recording is filed as an observation and none is triaged.
	symptoms = svc.transcribe_audio(
		VoiceAudioRequest(subject_ref='U-1', lang='en', purpose='symptoms'), SPEECH_EN)
	assert symptoms.intent != 'note', 'a symptom report was filed as a note'
	assert symptoms.transcript == note.transcript, 'one recording, one transcript'


async def test_the_audio_path_refuses_when_no_recogniser_is_deployed() -> None:
	"""A transcript nobody produced is the one failure a voice path may not have, so an unwired
	service refuses by name rather than answering from a stub."""
	svc = AccessService()
	with pytest.raises(AssertionError, match='not deployed'):
		svc.transcribe_audio(VoiceAudioRequest(subject_ref='U-1', lang='en'), SPEECH_EN)


# --- the WhatsApp voice note --------------------------------------------------------------

def _channel_service(access: AccessService | None = None) -> ChannelService:
	return ChannelService(AfricaTalkingSmsPort('https://api.africastalking.com', 'k'), None, None, None, None, access)


async def test_a_whatsapp_voice_note_is_transcribed_then_triaged() -> None:
	"""The bullet, end to end. The note is audio; the answer is the recogniser's transcript run
	through §5.4's engine, and `recogniser` records which model produced the words."""
	engine = _engine()
	svc = _channel_service(AccessService(engine))
	msg = WhatsAppIn(from_msisdn='+254711222333', body='media-ref', kind='voice', voice_note_lang='en')
	out = svc.route_whatsapp_voice(msg, SPEECH_EN)
	assert 'nightfall' in out.transcript.lower()
	assert out.recogniser == 'whisper-tiny/en'
	assert out.spoken_reply, 'a voice note must be answered out loud'


async def test_a_text_message_is_not_routed_through_the_voice_path() -> None:
	svc = _channel_service(AccessService(_engine()))
	with pytest.raises(AssertionError, match='not a text message'):
		svc.route_whatsapp_voice(
			WhatsAppIn(from_msisdn='+254711222333', body='fever'), SPEECH_EN)


async def test_a_voice_note_is_not_read_as_text() -> None:
	"""The defect itself. Before this, the media reference went through the keyword map and a
	voice note was answered at the low risk level because a media id contains no symptom word."""
	svc = _channel_service(AccessService(_engine()))
	msg = WhatsAppIn(from_msisdn='+254711222333', body='media-ref-9f2a', kind='voice', voice_note_lang='en')
	with pytest.raises(AssertionError, match='no body to read'):
		svc.route_whatsapp(msg)


async def test_a_voice_note_with_no_language_is_refused_at_the_model() -> None:
	"""Recognition ships per language. A note that declares none is a note no recogniser can be
	pointed at, and guessing is guessing which language to mis-hear the person in."""
	with pytest.raises(ValidationError, match='recognition ships per language'):
		WhatsAppIn(from_msisdn='+254711222333', body='media-ref', kind='voice')


async def test_a_language_on_a_text_message_is_refused() -> None:
	with pytest.raises(ValidationError, match='not a voice note'):
		WhatsAppIn(from_msisdn='+254711222333', body='fever', voice_note_lang='en')


async def test_the_channel_layer_refuses_a_note_when_no_recogniser_is_wired() -> None:
	svc = _channel_service(None)
	msg = WhatsAppIn(from_msisdn='+254711222333', body='media-ref', kind='voice', voice_note_lang='en')
	with pytest.raises(AssertionError, match='not wired'):
		svc.route_whatsapp_voice(msg, SPEECH_EN)


async def test_a_text_message_still_routes_exactly_as_before() -> None:
	svc = _channel_service(AccessService(_engine()))
	out = svc.route_whatsapp(WhatsAppIn(from_msisdn='+254711222333', body='find facility'))
	assert 'facility' in out.reply.lower() or 'clinic' in out.reply.lower()


# --- the CHW note on a case report --------------------------------------------------------

async def test_a_case_report_keeps_the_note_and_the_language_it_was_said_in() -> None:
	"""§COM-101's "voice-to-text notes in local languages" and §ACC-002's third bullet are the
	same field seen from two sections. `voice_note_lang` named a language and nothing recorded a
	note; now the transcript and the language move together."""
	from afya.community.views import CaseReport
	report = CaseReport(
		chw_ref='CHW-1', county='Busia', community='Bumala', symptoms=['fever'],
		voice_note='Three children in the house, one with a rash behind the market.',
		voice_note_lang='sw',
	)
	assert report.voice_note and report.voice_note_lang == 'sw'


async def test_a_note_without_its_language_is_refused() -> None:
	from afya.community.views import CaseReport
	with pytest.raises(ValidationError, match='no transcript, or a transcript with no language'):
		CaseReport(chw_ref='CHW-1', county='Busia', community='Bumala', symptoms=['fever'],
			voice_note='a note')


async def test_a_language_without_a_note_is_refused() -> None:
	"""This is exactly how the field came to look implemented while nothing recorded a note: a
	language could be set on its own."""
	from afya.community.views import CaseReport
	with pytest.raises(ValidationError, match='no transcript, or a transcript with no language'):
		CaseReport(chw_ref='CHW-1', county='Busia', community='Bumala', symptoms=['fever'],
			voice_note_lang='sw')


# --- the routes ---------------------------------------------------------------------------

def _client() -> TestClient:
	from afya.service import create_app
	return TestClient(create_app())


async def test_the_audio_route_serves_a_transcript_and_refuses_an_empty_recording() -> None:
	c = _client()
	headers = _token(c, 'U-1')
	# Form parts, not query parameters: the catalogue marks this route's fields `form` and both
	# clients write them into the multipart body, so a test that sent them in the query would be
	# proving a spelling no client uses — and the route reads them as `Form(...)`.
	r = c.post('/access/voice/audio', data={'subject_ref': 'U-1', 'lang': 'en'},
		files={'file': ('note.wav', _wav_bytes(SPEECH_EN), 'audio/wav')}, headers=headers)
	assert r.status_code == 200, r.text
	body = r.json()
	assert 'nightfall' in body['transcript'].lower(), body
	assert body['recogniser'] == 'whisper-tiny/en'
	empty = c.post('/access/voice/audio', data={'subject_ref': 'U-1'},
		files={'file': ('note.wav', b'', 'audio/wav')}, headers=headers)
	assert empty.status_code == 422


async def test_the_audio_route_refuses_a_file_that_is_not_a_wav() -> None:
	c = _client()
	headers = _token(c, 'U-1')
	r = c.post('/access/voice/audio', data={'subject_ref': 'U-1'},
		files={'file': ('note.wav', b'this is not a recording', 'audio/wav')}, headers=headers)
	assert r.status_code == 422, r.text


# A WAV header that declares a `data` chunk with zero bytes and a RIFF size that promises more.
# `wave` seeks past the end of the file and raises `RuntimeError`, which is *not* `wave.Error` —
# the exception a dropped connection leaves behind when it truncates a recording in transit.
TRUNCATED_WAV = (b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00'
	b'\x80>\x00\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00')


async def test_a_truncated_recording_is_the_callers_422_and_not_the_servers_500(webhook_secret: str) -> None:
	"""A half-sent recording is the network's doing, and the route answers for it.

	`wave` raises `RuntimeError` — not its own `Error` — when a frame read seeks past EOF, so the
	routes' `except (wave.Error, EOFError)` missed the one malformed upload a dropped connection
	actually produces. Both voice routes answered 500, which reads as a server fault and tells the
	person to retry a request that will fail identically.
	"""
	c = _client()
	headers = _token(c, 'U-1')
	r = c.post('/access/voice/audio', data={'subject_ref': 'U-1'},
		files={'file': ('note.wav', TRUNCATED_WAV, 'audio/wav')}, headers=headers)
	assert r.status_code == 422, f'a truncated upload is the caller\'s 422, not {r.status_code}'
	# Which of the two refusals answers depends on where the truncation is noticed — a `data` chunk
	# that declares nothing fails the duration check, a seek past EOF raises `RuntimeError` — and
	# both are the caller's 422. The status is the claim; the message is not.
	assert 'detail' in r.json(), r.text
	raw, signed = sign_multipart({'from_msisdn': '+254711222333'},
		{'file': ('note.wav', TRUNCATED_WAV, 'audio/wav')}, webhook_secret)
	wa = c.post('/channels/whatsapp/voice', content=raw, headers=signed)
	assert wa.status_code == 422, f'the WhatsApp voice route answers {wa.status_code}'


async def test_the_audio_route_will_not_transcribe_for_someone_else() -> None:
	c = _client()
	headers = _token(c, 'U-1')
	r = c.post('/access/voice/audio', data={'subject_ref': 'U-2'},
		files={'file': ('note.wav', _wav_bytes(SPEECH_EN), 'audio/wav')}, headers=headers)
	assert r.status_code == 403


async def test_the_text_route_still_takes_a_transcript() -> None:
	c = _client()
	headers = _token(c, 'U-1')
	r = c.post('/access/voice', json={'subject_ref': 'U-1', 'lang': 'en',
		'utterance': 'I have fever and headache', 'purpose': 'symptoms'}, headers=headers)
	assert r.status_code == 200, r.text
	assert set(r.json()['symptoms']) == {'fever', 'headache'}


async def test_the_text_route_refuses_a_purpose_it_does_not_have() -> None:
	c = _client()
	headers = _token(c, 'U-1')
	r = c.post('/access/voice', json={'subject_ref': 'U-1', 'lang': 'en',
		'utterance': 'hello', 'purpose': 'gossip'}, headers=headers)
	assert r.status_code == 422


async def test_the_whatsapp_voice_webhook_transcribes_and_answers(webhook_secret: str) -> None:
	c = _client()
	raw, headers = sign_multipart(
		{'from_msisdn': '+254711222333', 'voice_note_lang': 'en'},
		{'file': ('note.wav', _wav_bytes(SPEECH_EN), 'audio/wav')}, webhook_secret)
	r = c.post('/channels/whatsapp/voice', content=raw, headers=headers)
	assert r.status_code == 200, r.text
	body = r.json()
	assert 'nightfall' in body['transcript'].lower(), body
	assert body['channel'] == 'whatsapp' and body['reply']


async def test_the_whatsapp_text_webhook_refuses_a_voice_note(webhook_secret: str) -> None:
	"""Refused rather than answered, which is the fix: answering is what the defect did."""
	c = _client()
	raw, headers = sign({'from_msisdn': '+254711222333', 'body': 'media-ref', 'kind': 'voice',
		'voice_note_lang': 'en'}, webhook_secret)
	r = c.post('/channels/whatsapp', content=raw, headers=headers)
	assert r.status_code == 422, r.text


async def test_the_whatsapp_text_webhook_still_answers_text(webhook_secret: str) -> None:
	c = _client()
	raw, headers = sign({'from_msisdn': '+254711222333', 'body': 'I have fever'}, webhook_secret)
	r = c.post('/channels/whatsapp', content=raw, headers=headers)
	assert r.status_code == 200 and r.json()['reply']


# --- the gap that stays open --------------------------------------------------------------

async def test_the_six_language_bullet_stays_open() -> None:
	"""§ACC-002's first bullet names six languages. `LANGUAGE_MATRIX` lists them and the product
	has string tables and recognition for two.

	This test exists so the gap cannot be closed by widening a list. `SUPPORTED_LANGS` is
	`{'en', 'sw'}` on purpose and `tests/ci/test_personas.py` pins the same absence from the other
	side; adding a fourth, fifth and sixth entry to make a count look better would report an
	untranslated table as a shipped feature. What the voice path does instead is serve English on
	`answerable` and carry `served_in` so the caller knows which language they got.
	"""
	from afya.strings import SUPPORTED_LANGS
	named = {'sw', 'luo', 'bxk', 'kln', 'ki', 'en'}
	assert named <= {str(meta['code']) for meta in LANGUAGE_MATRIX.values()}, \
		'the six the section names must all be in the matrix'
	unserved = named - SUPPORTED_LANGS
	assert unserved == {'luo', 'bxk', 'kln', 'ki'}, \
		'four of the six have no string table, and that is the open gap'
	engine_langs = set(_engine().languages())
	assert unserved & engine_langs == set(), \
		'and the recogniser was not trained on them either, so audio cannot close it'


async def test_the_voice_langs_offered_are_the_ones_recognition_ships_for() -> None:
	"""The mobile dropdown must not offer a language the recogniser was never trained on: a
	Dholuo recording sent to an English model is a fluent transcript of words nobody said."""
	from afya.mobile.actions import VOICE_LANGS, VOICE_PURPOSES
	assert VOICE_LANGS == ['en', 'sw'], VOICE_LANGS
	assert VOICE_PURPOSES == ['symptoms', 'note']


async def test_the_tts_flag_says_whether_a_voice_exists_not_which_tier_a_language_is() -> None:
	"""`tts` was `tier == 1` restated and read by nothing, and it is served on `/access/languages`.

	Every tier-1 language carried `True`, so the route told a client that Dholuo, Luhya (Bukusu) and
	Kikuyu had text-to-speech — while `transcribe` composes `spoken_reply` in `answerable(lang)`,
	which is English for all three. A client that believed the flag would offer a read-aloud button
	in a language the server will not speak. The flag now agrees with what the server actually does,
	which is the only thing it can be checked against, and the check is run against the *served*
	reply rather than against a second list.

	The inequality with `tier` is asserted rather than the count, because the defect was precisely
	that the two were equal: a future edit that collapses them again fails here whatever the rows are.
	"""
	from afya.access.service import AccessService
	from afya.access.views import VoiceRequest
	from afya.strings import SUPPORTED_LANGS

	svc = AccessService()
	tiers = {meta['tier'] for meta in LANGUAGE_MATRIX.values()}
	assert tiers == {1, 2}, 'the matrix must still carry both tiers, or this test proves nothing'
	assert any(meta['tier'] == 1 and meta['tts'] is False for meta in LANGUAGE_MATRIX.values()), (
		'a tier-1 language with no voice must exist, or `tts` has collapsed back into `tier == 1`'
	)
	for name, meta in LANGUAGE_MATRIX.items():
		code = str(meta['code'])
		result = svc.transcribe(VoiceRequest(
			subject_ref='U-1', lang=code, utterance='I have fever', purpose='symptoms'))
		# A language has a voice exactly when the reply comes back *in that language*. Checking
		# membership of `SUPPORTED_LANGS` would be wrong and did fail here first: Dholuo is answered
		# in `en`, and `en` is of course in the set, so the weaker predicate called a Dholuo reply
		# English-spoken — which is true of the text and false of the claim the flag makes.
		spoken = result.served_in == code
		assert meta['tts'] is spoken, (
			f'{name} ({code}) reports tts={meta["tts"]} and the server answers in '
			f'{result.served_in!r}, which has {"a" if spoken else "no"} table'
		)
		assert result.served_in == (code if code in SUPPORTED_LANGS else 'en'), result.served_in
