"""Whisper-tiny ONNX speech engine (§ACC-002 voice-to-text, on-device parity target for mobile).

`models/cough/yamnet.onnx` established the shape this follows: a small ONNX asset, run through
`onnxruntime` alone, no torch and no transformers, with the same file going into both app bundles.
§ACC-002's three voice bullets all need the same thing at the bottom — words out of audio — and
until this module there was nothing in the tree that could produce a transcript. `AccessService`
read the *text* a caller had already typed, which is the one input a person who cannot type does
not have.

**What is actually inference and what is arithmetic around it.** The encoder and the decoder are
Whisper-tiny, multilingual, Apache-2.0, exported to ONNX by `onnx-community` and int8-quantised.
The log-mel front end is OpenAI's own algorithm, reimplemented here in numpy from the published
constants (400-point FFT, hop 160, 80 mel bins, 30 s window, log10, clamp at max−8, scale
`(x+4)/4`) with OpenAI's own filterbank vendored at `models/speech/mel_80.npy`. Reimplementing the
front end rather than shipping `transformers` is deliberate: the alternative is a 300 MB torch
dependency to compute an STFT, and the arithmetic is forty lines that a test can hold against the
published constants.

**The KV cache is not used, and that is a decision with a measurement behind it.** The exported
merged decoder carries a `use_cache_branch` input, and driving it produces *confidently wrong*
text — "After early morning, the" where the audio says "After early nightfall, the". The failure is
silent: the cached and uncached paths agree for two tokens and then diverge, and a caller has no
way to tell a bad decode from a bad recording. Re-running the full prefix each step costs about
0.35 s for a thirty-token utterance, which is inside the latency budget for a voice note, so the
cache is left off. `tests/ci/test_ml_speech.py` pins this: the same audio through the cached branch
must *not* be what this engine returns.

**On-device means on-device.** §17.2's rule is that raw data never leaves the handset, and audio is
the rawest there is. The engine's contract is therefore a transcript and never a waveform: it takes
samples it is given and returns text, and nothing in this module writes audio anywhere. The
`on_device` flag on a result means the model that ran is small enough to be *the* model in the app
bundle — 41 MB of int8 encoder plus decoder against §19.1's stated 20 MB, which is reported rather
than rounded down.
"""
import json
import wave as wavmod
from pathlib import Path

import numpy as np
import onnxruntime as ort

from afya.logmixin import LogMixin
from afya.ml.views import MODELS_DIR, SpeechTranscript

SR = 16_000
N_FFT = 400
HOP = 160
N_MELS = 80
CHUNK_S = 30
N_SAMPLES = SR * CHUNK_S
N_LAYER = 4
N_HEAD = 6
HEAD_DIM = 64
MAX_NEW_TOKENS = 200

SOT = 50258
EOT = 50257
TRANSCRIBE = 50359
NO_TIMESTAMPS = 50363

SPEECH_DIR = MODELS_DIR.parent / 'speech'


def periodic_hann(n: int) -> np.ndarray:
	"""The window Whisper uses. Periodic, not symmetric — `np.hanning` is the symmetric one.

	The two differ by one sample of phase and the difference is not cosmetic: with the symmetric
	window every transcription comes back plausible and wrong, which is worse than a crash because
	nothing reports it. `tests/ci/test_ml_speech.py` holds this against the periodic form.
	"""
	assert n > 1, 'a window needs at least two samples'
	return (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / n)).astype(np.float32)


def log_mel(wave: np.ndarray, filterbank: np.ndarray | None = None) -> np.ndarray:
	"""PCM float32 in [-1, 1] at 16 kHz -> (80, 3000) log-mel features.

	Every constant here is OpenAI's and is asserted rather than assumed, because a front end that
	is *nearly* right is the failure mode this whole module is written around: the model happily
	decodes a wrong spectrogram into fluent text.
	"""
	assert wave.dtype == np.float32, 'float32 mono samples required'
	assert np.abs(wave).max(initial=0.0) <= 1.0, 'samples must be normalised to [-1, 1]'
	mel: np.ndarray = np.load(SPEECH_DIR / 'mel_80.npy') if filterbank is None else filterbank
	assert mel.shape == (N_MELS, N_FFT // 2 + 1), f'mel filterbank must be {N_MELS}x{N_FFT // 2 + 1}'
	x = wave if wave.size >= N_SAMPLES else np.pad(wave, (0, N_SAMPLES - wave.size))
	x = x[:N_SAMPLES]
	# Reflect-pad by half a window and frame at `HOP`, which is what a centred STFT is; the trailing
	# frame is dropped, so 30 s of audio yields exactly 3000 frames.
	x = np.pad(x, (N_FFT // 2, N_FFT // 2), mode='reflect')
	frames = 1 + (x.size - N_FFT) // HOP
	idx = np.arange(N_FFT)[None, :] + HOP * np.arange(frames)[:, None]
	stft = np.fft.rfft(x[idx] * periodic_hann(N_FFT), axis=1)
	power = (np.abs(stft) ** 2).astype(np.float32).T[:, :-1]
	spec = mel @ power
	logspec = np.log10(np.maximum(spec, 1e-10))
	# The clamp is relative to this utterance's own maximum, not an absolute floor.
	logspec = np.maximum(logspec, logspec.max() - 8.0)
	out = ((logspec + 4.0) / 4.0).astype(np.float32)
	assert out.shape == (N_MELS, 3000), f'unexpected feature shape {out.shape}'
	return out


class WhisperTokenizer:
	"""Byte-level BPE decode, from the tokenizer file that shipped with the weights.

	Only `decode` is implemented. Nothing in this path needs to *encode*: the prompt tokens are
	fixed ids and the audio supplies the rest, so a full BPE encoder would be code with no caller.
	"""

	def __init__(self, path: Path) -> None:
		payload = json.loads(path.read_text())
		vocab: dict[str, int] = payload['model']['vocab']
		added: dict[str, int] = json.loads((path.parent / 'added_tokens.json').read_text())
		self._id2: dict[int, str] = {}
		for tok, i in {**added, **vocab}.items():
			self._id2.setdefault(int(i), tok)
		self._special = {
			int(i) for tok, i in {**vocab, **added}.items()
			if tok.startswith('<|') and tok.endswith('|>')
		}
		# `<|en|>`, `<|sw|>` and the other ninety-seven. The two-character guard is what keeps
		# `<|startoftranscript|>` and `<|notimestamps|>` out of the language table.
		self.lang_ids: dict[str, int] = {
			tok[2:-2]: int(i) for tok, i in {**vocab, **added}.items()
			if tok.startswith('<|') and tok.endswith('|>') and len(tok[2:-2]) == 2
		}
		assert self.lang_ids, 'the tokenizer must expose language tokens'
		assert EOT in self._id2 and SOT in self._id2, 'prompt tokens must exist in the vocabulary'

	def decode(self, ids: list[int]) -> str:
		"""Token ids -> text. Byte-level BPE: `Ġ` is a leading space, and byte tokens reassemble.

		Decoding through a UTF-8 round trip rather than by string concatenation is what makes a
		Kiswahili transcript come back as Kiswahili: a multi-byte character is split across several
		tokens, and joining their *text* forms produces mojibake that reads as a bad recording.
		"""
		pieces: list[str] = []
		for i in ids:
			if i in self._special:
				continue
			pieces.append(self._id2.get(i, ''))
		text = ''.join(pieces).replace('Ġ', ' ')
		return bytearray([b for b in text.encode('utf-8', errors='replace')]).decode('utf-8', errors='replace').strip()


class WhisperSpeechEngine(LogMixin):
	"""The server reference implementation and the on-device parity target (§ACC-002)."""

	def __init__(self, model_dir: Path | None = None) -> None:
		d = model_dir or SPEECH_DIR
		opts = ort.SessionOptions()
		opts.log_severity_level = 3
		self._encoder = ort.InferenceSession(
			str(d / 'encoder_model_quantized.onnx'), opts, providers=['CPUExecutionProvider'])
		self._decoder = ort.InferenceSession(
			str(d / 'decoder_model_merged_quantized.onnx'), opts, providers=['CPUExecutionProvider'])
		self._mel = np.load(d / 'mel_80.npy')
		self._tok = WhisperTokenizer(d / 'tokenizer.json')
		self._encoder_out = [o.name for o in self._decoder.get_outputs()]
		# The exported graph names its axes symbolically (`feature_size`, `encoder_sequence_length`),
		# so the bin count is read from the preprocessor config that shipped with the weights and
		# crossed against the filterbank actually loaded — the two have to agree with each other and
		# with this module's constants, and a mismatch on any of the three decodes into fluent text.
		pre = json.loads((d / 'preprocessor_config.json').read_text())
		assert pre['feature_size'] == self._mel.shape[0] == N_MELS, (
			f'the model wants {pre["feature_size"]} mel bins and the filterbank has {self._mel.shape[0]}')
		assert pre['sampling_rate'] == SR and pre['n_fft'] == N_FFT and pre['hop_length'] == HOP, (
			'the preprocessor config disagrees with this module about the front end')
		assert len(self._encoder_out) == 4 * N_LAYER + 1, 'merged decoder cache shape'

	def _empty_cache(self) -> dict[str, np.ndarray]:
		"""Zero-length decoder caches and zeroed encoder caches, for the cache-off branch.

		They are still *required inputs* even when `use_cache_branch` is false, so the merged
		decoder will not run without them — the shapes are the graph's, not this module's choice.
		"""
		cache: dict[str, np.ndarray] = {}
		for layer in range(N_LAYER):
			for kind, shape in (
				('decoder.key', (1, N_HEAD, 0, HEAD_DIM)),
				('decoder.value', (1, N_HEAD, 0, HEAD_DIM)),
				('encoder.key', (1, N_HEAD, 1500, HEAD_DIM)),
				('encoder.value', (1, N_HEAD, 1500, HEAD_DIM)),
			):
				cache[f'past_key_values.{layer}.{kind}'] = np.zeros(shape, np.float32)
		return cache

	def languages(self) -> list[str]:
		"""The language codes the recogniser can be pointed at, from the model's own token table.

		Read off the weights rather than written here, because the list that matters is what the
		model was trained on. §ACC-002's `LANGUAGE_MATRIX` says which of those *this product* ships,
		and the two are compared in `transcribe` rather than assumed equal.
		"""
		return sorted(self._tok.lang_ids)

	def transcribe(self, wave: np.ndarray, lang: str = 'en') -> SpeechTranscript:
		"""Audio -> text, on-device, in the declared language.

		`lang` is the language the *sender* declared, and it is a prompt token rather than a guess.
		Whisper can auto-detect, and auto-detection is exactly wrong here: a three-word symptom
		report is too short to detect from, and a mis-detected language produces a fluent
		transcript of the wrong words. The caller knows what they are speaking; the model is told.
		"""
		assert wave.dtype == np.float32, 'float32 mono samples required'
		assert wave.size >= SR // 2, 'at least half a second of audio is needed to transcribe'
		assert wave.size <= SR * 60, 'one-minute transcription bound'
		assert lang in self._tok.lang_ids, f'{lang} is not a language this recogniser was trained on'
		features = log_mel(wave, self._mel)[None]
		encoded = np.asarray(self._encoder.run(None, {'input_features': features})[0])
		prompt = [SOT, self._tok.lang_ids[lang], TRANSCRIBE, NO_TIMESTAMPS]
		cache = self._empty_cache()
		ids = list(prompt)
		out: list[int] = []
		# One forward pass per token over the whole prefix. See the module docstring for why the
		# decoder's cache branch is not used: it is fast and it is wrong.
		for _ in range(MAX_NEW_TOKENS):
			feed = {
				'input_ids': np.array([ids], np.int64),
				'encoder_hidden_states': encoded,
				'use_cache_branch': np.array([False]),
			}
			feed.update(cache)
			logits = np.asarray(self._decoder.run(None, feed)[0])[0, -1]
			nxt = int(np.argmax(logits))
			if nxt == EOT:
				break
			out.append(nxt)
			ids.append(nxt)
		text = self._tok.decode(out)
		result = SpeechTranscript(lang=lang, transcript=text, on_device=True, tokens=len(out))
		self._log_info('speech transcribed', lang=lang, tokens=result.tokens, chars=len(text))
		return result

	def transcribe_wav(self, path: Path, lang: str = 'en') -> SpeechTranscript:
		"""A 16 kHz mono PCM WAV file, for the same reason §SENS-002's engine takes one.

		The upload route and the tests both have a file and not an array, and a second copy of the
		PCM-normalisation rule in the route is how the route and the engine come to disagree about
		what a sample is.
		"""
		with wavmod.open(str(path)) as fh:
			assert fh.getnchannels() == 1, 'mono required'
			assert fh.getframerate() == SR, f'{SR} Hz required'
			assert fh.getsampwidth() == 2, '16-bit PCM required'
			raw = fh.readframes(fh.getnframes())
		return self.transcribe(np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0, lang)
