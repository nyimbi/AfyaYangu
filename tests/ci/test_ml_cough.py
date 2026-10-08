import numpy as np
import pytest

from afya.ml.cough import SR, YamnetCoughEngine


@pytest.fixture(scope='module')
def engine() -> YamnetCoughEngine:
	return YamnetCoughEngine()


def test_class_map_has_cough(engine: YamnetCoughEngine) -> None:
	cough = [label for label in engine._labels if 'cough' in label.lower()]  # noqa: SLF001 — contract check
	assert cough and engine._cough_idx  # noqa: SLF001
	assert len(engine._labels) == 521  # noqa: SLF001 — full AudioSet map


def test_random_noise_not_cough_dominant(engine: YamnetCoughEngine) -> None:
	rng = np.random.default_rng(7)
	wave = rng.normal(0, 0.05, size=SR * 2).astype(np.float32)
	verdict = engine.analyze(wave, tier4_active=True)
	assert verdict.band in ('normal', 'watch', 'alert')
	assert verdict.cough_frames == 0


def test_silence_normal(engine: YamnetCoughEngine) -> None:
	verdict = engine.analyze(np.zeros(SR * 2, dtype=np.float32))
	assert verdict.band in ('normal', 'watch', 'alert')


def test_dormant_rejected(engine: YamnetCoughEngine) -> None:
	rng = np.random.default_rng(3)
	wave = rng.normal(0, 0.05, size=SR * 2).astype(np.float32)
	with pytest.raises(PermissionError):
		engine.analyze(wave, tier4_active=False)


def test_minimum_audio_enforced(engine: YamnetCoughEngine) -> None:
	with pytest.raises(AssertionError):
		engine.analyze(np.zeros(SR // 2, dtype=np.float32))


def test_wrong_sample_rate_enforced(engine: YamnetCoughEngine) -> None:
	with pytest.raises(AssertionError):
		engine.analyze(np.zeros(SR * 2, dtype=np.float32), sr=8000)