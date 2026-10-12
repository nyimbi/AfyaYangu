"""Behavioural tests for the accessibility module (spec §12.1 ACC-001..005).

These cover the guarantees the module exists to carry: a language matrix with declared
recognition and synthesis, touch targets of at least 48 dp, a per-intensity battery
budget under 5% a day, a named fallback for every sensor that can be absent, an offline
voice path, and device compatibility that includes the go edition and no-Play-Services.
"""
import pytest
from pydantic import ValidationError

from afya.access.service import (
	INTENSITY_BATTERY, INTENSITY_SENSORS, SENSOR_FALLBACKS, UI_SCREENS, AccessService,
)
from afya.access.views import (
	LANGUAGE_MATRIX, MIN_TOUCH_TARGET_DP, AccessProfile, BatteryProfile, DeviceCompatibility, UIAsset,
	VoiceRequest, VoiceResult,
)


# --- language matrix ----------------------------------------------------------------------

async def test_language_matrix_priority_tiers() -> None:
	tier1 = {name for name, meta in LANGUAGE_MATRIX.items() if meta['tier'] == 1}
	tier2 = {name for name, meta in LANGUAGE_MATRIX.items() if meta['tier'] == 2}
	assert tier1 == {'Kiswahili', 'English', 'Dholuo', 'Luhya (Bukusu)', 'Kikuyu'}
	assert tier2 == {'Luhya (Maragoli)', 'Kalenjin', 'Kamba', 'Somali', 'Maasai', 'Kisii', 'Meru', 'Taita'}
	assert len(tier1) == 5 and len(tier2) == 8


async def test_every_language_entry_declares_code_asr_tts() -> None:
	for name, meta in LANGUAGE_MATRIX.items():
		assert set(meta) == {'code', 'tier', 'asr', 'tts'}, f'{name} must declare code/tier/asr/tts'
		assert isinstance(meta['code'], str) and len(meta['code']) >= 2
		assert isinstance(meta['asr'], bool) and isinstance(meta['tts'], bool)


async def test_languages_service_filters_by_tier() -> None:
	svc = AccessService()
	all_rows = svc.languages()
	assert len(all_rows) == 13
	assert len(svc.languages(tier=1)) == 5
	assert len(svc.languages(tier=2)) == 8
	assert {r['name'] for r in svc.languages(tier=1)} == {'Kiswahili', 'English', 'Dholuo', 'Luhya (Bukusu)', 'Kikuyu'}


# --- touch targets ------------------------------------------------------------------------

async def test_min_touch_target_is_48dp() -> None:
	assert MIN_TOUCH_TARGET_DP == 48


async def test_every_ui_screen_meets_touch_target() -> None:
	svc = AccessService()
	rows = svc.screens()
	assert len(rows) == len(UI_SCREENS)
	for screen in rows:
		assert screen.touch_target_dp >= MIN_TOUCH_TARGET_DP, f'{screen.screen_id} below 48 dp'
		assert screen.read_aloud_text and screen.pictogram and screen.label
		assert screen.risk_colour in ('green', 'yellow', 'red', 'neutral')


async def test_ui_asset_refuses_touch_target_below_48dp() -> None:
	with pytest.raises(ValidationError):
		UIAsset(screen_id='tiny', pictogram='dot', label='Tiny', risk_colour='neutral',
			touch_target_dp=44, read_aloud_text='too small to tap')


# --- battery ------------------------------------------------------------------------------

async def test_battery_budget_under_five_percent_per_intensity() -> None:
	svc = AccessService()
	expected = {'low': 0.8, 'balanced': 2.5, 'maximum': 4.6}
	assert INTENSITY_BATTERY == expected
	for intensity, pct in expected.items():
		profile = svc.battery_profile('sub-1', intensity=intensity)
		assert isinstance(profile, BatteryProfile)
		assert profile.estimated_daily_pct == pct
		assert profile.estimated_daily_pct <= 5.0, f'{intensity} exceeds the 5%/day budget'
		assert profile.charging_adaptive is True
		assert profile.sensors_enabled == INTENSITY_SENSORS[intensity]


async def test_battery_saver_drops_sensors_and_budget() -> None:
	svc = AccessService()
	profile = svc.battery_profile('sub-1', intensity='maximum', battery_saver=True)
	assert profile.battery_saver is True
	assert profile.sensors_enabled == []
	assert profile.estimated_daily_pct == 0.4


async def test_battery_profile_refuses_unknown_intensity() -> None:
	svc = AccessService()
	with pytest.raises(AssertionError):
		svc.battery_profile('sub-1', intensity='turbo')


# --- sensor fallbacks ---------------------------------------------------------------------

async def test_fallbacks_exist_for_absence_prone_sensors() -> None:
	svc = AccessService()
	for sensor in ('lidar', 'microphone', 'gyroscope', 'gps', 'bluetooth', 'nfc', 'camera', 'thermometer', 'wearable'):
		assert sensor in SENSOR_FALLBACKS, f'{sensor} has no documented fallback'
		assert svc.fallback_for(sensor)


async def test_fallback_refuses_unknown_sensor() -> None:
	svc = AccessService()
	with pytest.raises(AssertionError):
		svc.fallback_for('teleporter')


async def test_compatibility_exposes_fallbacks_for_all_sensors() -> None:
	svc = AccessService()
	android = svc.compatibility('android')
	assert android.missing_sensor_fallbacks == SENSOR_FALLBACKS


# --- voice --------------------------------------------------------------------------------

async def test_voice_request_returns_intent_and_spoken_reply() -> None:
	svc = AccessService()
	out = svc.transcribe(VoiceRequest(subject_ref='sub-1', lang='en', utterance='I have a fever and a headache'))
	assert isinstance(out, VoiceResult)
	assert out.intent == 'triage'
	assert out.confidence == 0.82
	assert out.spoken_reply == 'Starting a fever check. Is the temperature above 38 degrees?'
	assert out.transcript == 'I have a fever and a headache'


async def test_voice_matches_a_kiswahili_keyword() -> None:
	svc = AccessService()
	out = svc.transcribe(VoiceRequest(subject_ref='sub-1', lang='sw', utterance='Nina homa'))
	assert out.intent == 'triage'
	assert out.on_device is True, 'Kiswahili ships on-device recognition'


async def test_a_language_without_recognition_is_not_reported_on_device() -> None:
	"""§12.1 ACC-002's "offline speech recognition for core commands" is a claim about which languages
	ship a recogniser, and `LANGUAGE_MATRIX` is where that is recorded.

	This test previously asserted the opposite — that an offline request on Dholuo ran on-device —
	because `on_device` was computed as `asr or req.offline`. That made the flag unfalsifiable: every
	offline request was on-device by construction, including one in a language with no recogniser, so
	§SEC-002's "raw sensor data never leaves the device" would have read as satisfied for a transcript
	the handset cannot produce. The flag now answers the only question it can: does recognition ship
	for this language.
	"""
	svc = AccessService()
	online = svc.transcribe(VoiceRequest(subject_ref='sub-1', lang='luo', utterance='an a dhier'))
	offline = svc.transcribe(VoiceRequest(subject_ref='sub-1', lang='luo', utterance='an a dhier', offline=True))
	assert online.on_device is False
	assert offline.on_device is False, 'offline does not conjure a recogniser Dholuo does not ship'
	# The intent is still served — the gap is in recognition, not in the response.
	assert offline.spoken_reply


async def test_the_matrix_is_what_decides_on_device_not_the_request() -> None:
	"""The flag must agree with `LANGUAGE_MATRIX` for every language, in both directions: a language
	that ships recognition is on-device whether or not the caller said it was offline."""
	svc = AccessService()
	for name, meta in LANGUAGE_MATRIX.items():
		code, asr = str(meta['code']), bool(meta['asr'])
		out = svc.transcribe(VoiceRequest(subject_ref='sub-1', lang=code, utterance='homa', offline=False))
		assert out.on_device is asr, f'{name}: on_device disagrees with the matrix'


async def test_voice_unknown_utterance_falls_back_gracefully() -> None:
	svc = AccessService()
	out = svc.transcribe(VoiceRequest(subject_ref='sub-1', lang='en', utterance='zzz qqq'))
	assert out.intent == 'unknown'
	assert out.confidence == 0.3
	assert 'I did not catch that' in out.spoken_reply


async def test_voice_refuses_unsupported_language() -> None:
	svc = AccessService()
	with pytest.raises(AssertionError):
		svc.transcribe(VoiceRequest(subject_ref='sub-1', lang='xx', utterance='hello'))


# --- profiles -----------------------------------------------------------------------------

async def test_set_profile_accepts_supported_language() -> None:
	svc = AccessService()
	profile = svc.set_profile(AccessProfile(subject_ref='sub-1', lang='sw', simple_mode=True))
	assert profile.lang == 'sw'
	assert svc.profile('sub-1').simple_mode is True


async def test_profile_defaults_for_unknown_subject() -> None:
	svc = AccessService()
	profile = svc.profile('nobody')
	assert profile.subject_ref == 'nobody'
	assert profile.lang == 'en'
	assert profile.read_aloud is True


async def test_set_profile_refuses_unsupported_language() -> None:
	svc = AccessService()
	with pytest.raises(AssertionError):
		svc.set_profile(AccessProfile(subject_ref='sub-1', lang='fr'))


# --- device compatibility -----------------------------------------------------------------

async def test_android_compatibility_reports_go_edition_and_no_play_services() -> None:
	svc = AccessService()
	android = svc.compatibility('android')
	assert isinstance(android, DeviceCompatibility)
	assert android.go_edition_supported is True
	assert android.no_play_services is True
	assert android.os_min == '8.0 (API 26)'
	assert android.apk_base_mb == 0.9
	assert android.min_ram_mb == 512
	assert 'medicine_registry' in android.on_demand_modules


async def test_ios_compatibility_has_no_go_edition() -> None:
	svc = AccessService()
	ios = svc.compatibility('ios')
	assert ios.platform == 'ios'
	assert ios.go_edition_supported is False
	assert ios.no_play_services is False
	assert ios.apk_base_mb == 12.0


async def test_compatibility_refuses_unknown_platform() -> None:
	svc = AccessService()
	with pytest.raises(AssertionError):
		svc.compatibility('windows')


# --- §13.2 against the spec's own table ------------------------------------------------------

def _spec_13_2_rows() -> list[list[str]]:
	"""§13.2's degradation table, read out of the spec so a revision fails here rather than passing."""
	from pathlib import Path
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	section = text.split('### 13.2 Graceful Degradation Strategy', 1)[1].split('**Principle:**', 1)[0]
	rows: list[list[str]] = []
	for line in section.splitlines():
		if not line.startswith('|') or set(line) <= set('|-: '):
			continue
		cells = [c.strip().replace('**', '') for c in line.strip('|').split('|')]
		if len(cells) != 2 or cells[0] == 'Missing sensor':
			continue
		rows.append(cells)
	return rows


def test_the_fallback_table_is_the_sections_rows() -> None:
	"""§13.2 is nine rows and every one is carried. The section keys its rows on the sensor it names
	("No LiDAR"), the table keys them on a slug, and the two vocabularies differ in three places —
	which is how a row can be dropped without anything noticing."""
	from afya.access.service import SPEC_FALLBACK_ROWS
	spec = _spec_13_2_rows()
	assert len(spec) == 9, f'the section names {len(spec)} missing-sensor rows'
	assert [label for _, label, _ in SPEC_FALLBACK_ROWS] == [r[0] for r in spec]
	assert [text for _, _, text in SPEC_FALLBACK_ROWS] == [r[1] for r in spec]


def test_the_rendered_fallback_is_a_rewrite_not_a_transcription() -> None:
	"""The table a client renders is plain language with the spec ids dropped, so its text is
	deliberately not the section's — but the row *set* must be exactly the section's, or a sensor
	the section names has no fallback and a sensor it does not has one."""
	from afya.access.service import SPEC_FALLBACK_ROWS
	spec_slugs = {slug for slug, _, _ in SPEC_FALLBACK_ROWS}
	assert set(SENSOR_FALLBACKS) == spec_slugs, 'the table and the section must key the same rows'
	for slug, _, spec_text in SPEC_FALLBACK_ROWS:
		rendered = SENSOR_FALLBACKS[slug]
		assert rendered and rendered != spec_text, f'{slug}: the rendered copy is the section verbatim'
		# The ids the section prints may not reach a screen (tests/ci/test_ui_vocabulary.py).
		import re
		assert not re.search(r'\b[A-Z]{2,4}-\d{3}\b', rendered), f'{slug} leaks a spec id to a client'


def test_the_sections_vocabulary_differs_from_the_tables_and_that_is_recorded() -> None:
	"""The three mismatches, named: §13.2 says `camera` where §13.1 splits rear from front, and
	`wearable` where §13.1 has no sensor row at all (a wearable is a §14.6 integration). A check
	that assumed the two vocabularies were the same would have silently dropped the camera row."""
	from afya.access.service import SPEC_FALLBACK_ROWS
	from afya.sensors.service import SENSORS
	sensor_slugs = {s.slug for s in SENSORS}
	section_slugs = {slug for slug, _, _ in SPEC_FALLBACK_ROWS}
	assert section_slugs - sensor_slugs == {'camera', 'wearable'}, 'the two rows §13.1 has no sensor for'
	# `camera` covers both §13.1 rows, which is why the sensors module aliases them onto it.
	assert {'camera_rear', 'camera_front'} <= sensor_slugs and 'camera' not in sensor_slugs
	assert 'wearable' not in sensor_slugs, 'a wearable is an integration, not a handset sensor'
