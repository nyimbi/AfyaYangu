"""YAMNet ONNX cough engine (SENS-002 acoustic cough, §14.2) — on-device parity target for mobile; server reference impl."""
import time

import numpy as np

from afya.logmixin import LogMixin
from afya.ml.views import MODELS_DIR, CoughVerdict, class_map

SR = 16_000


class YamnetCoughEngine(LogMixin):
	FRAME_S = 0.96  # YAMNet window is 0.96 s of 16 kHz audio

	def __init__(self, model_dir=None) -> None:
		import onnxruntime as ort
		d = model_dir or MODELS_DIR
		self._session = ort.InferenceSession(str(d / 'yamnet.onnx'), providers=['CPUExecutionProvider'])
		self._labels = class_map(d / 'yamnet_class_map.csv')
		self._cough_idx = [i for i, name in enumerate(self._labels) if 'cough' in name.lower()]
		assert self._cough_idx, 'class map must contain cough class'
		assert len(self._labels) == 521, 'AudioSet class count'

	def analyze(self, wave: np.ndarray, sr: int = SR, tier4_active: bool = True) -> CoughVerdict:
		assert wave.dtype == np.float32, 'float32 mono samples required'
		assert sr == SR, f'must be {SR} Hz mono'
		if not tier4_active:
			raise PermissionError('SENS-002 acoustic cough is Tier 4 dormant')
		n = int(np.asarray(wave).size)
		assert n >= SR, 'need >= 1 s of audio'
		assert n <= SR * 60, 'one-minute analysis bound'
		raw = self._session.run(None, {'waveform': np.asarray(wave, dtype=np.float32)})
		scores = np.asarray(raw[0])
		assert scores.shape[1] == 521, 'scores shape per frame'
		cough_scores = np.asarray(scores[:, self._cough_idx]).max(axis=1)
		frames = cough_scores > 0.30
		events = int(np.sum(frames & ~np.roll(frames, 1, axis=0)))
		mean_scores = scores.mean(axis=0)
		dominant = self._labels[int(np.asarray(mean_scores).argmax())]
		rate = frames.sum() * self.FRAME_S / max(1e-6, n / sr)
		band = 'alert' if rate >= 30 else ('watch' if rate >= 15 else 'normal')
		out = CoughVerdict(cough_frames=int(frames.sum()), cough_events=events, dominant_class=dominant, band=band)
		self._log_info('cough analyzed', band=band, dominant=dominant)
		assert out.band in ('normal', 'watch', 'alert')
		return out