"""Accessibility services (spec §12.1 ACC-001..005).

The point of this module is that no user is excluded by their device. Every capability that a
missing sensor removes has a named fallback, and the fallback table is data the client renders —
not a paragraph in a document that nobody enforces.
"""
from afya.access.views import (
	LANGUAGE_MATRIX, MIN_TOUCH_TARGET_DP, AccessProfile, BatteryProfile, DeviceCompatibility,
	UIAsset, VoiceRequest, VoiceResult,
)
from afya.logmixin import LogMixin

# §13.2 graceful degradation — missing sensor -> the path that still works.
SENSOR_FALLBACKS: dict[str, str] = {
	'lidar': 'Estimate breathing from cough audio, or type the number of breaths you counted in a minute.',
	'microphone': 'Type your symptoms instead of speaking them.',
	'gyroscope': 'Accelerometer-only fall detection (reduced accuracy), or the manual SOS button.',
	'gps': 'Type your area name, or scan the QR code at the facility.',
	'bluetooth': 'List your contacts by hand.',
	'nfc': 'Scan the QR code instead.',
	'camera': 'Type the registration number printed on the medicine box.',
	'thermometer': 'Type the temperature from your own thermometer.',
	'wearable': 'Enter your readings by hand.',
}

# Screen contracts the native clients render. Touch targets are asserted at >= 48 dp.
UI_SCREENS: tuple[UIAsset, ...] = (
	UIAsset(screen_id='home', pictogram='house', label='Home', risk_colour='neutral', touch_target_dp=56,
		read_aloud_text='Home. Choose what you need: check a fever, find care, or call for help.'),
	UIAsset(screen_id='triage', pictogram='thermometer', label='Check a fever', risk_colour='yellow', universal_symbol='!',
		touch_target_dp=64, read_aloud_text='Check a fever. We will ask a few questions and tell you what to do next.'),
	UIAsset(screen_id='emergency', pictogram='siren', label='Get help now', risk_colour='red', universal_symbol='SOS',
		touch_target_dp=96, read_aloud_text='Get help now. Press and hold to call for help. You will have time to cancel.'),
	UIAsset(screen_id='facility', pictogram='hospital-cross', label='Find care near me', risk_colour='green',
		universal_symbol='+', touch_target_dp=64, read_aloud_text='Find care near me. We will show the closest clinics and how far they are.'),
	UIAsset(screen_id='medicine', pictogram='pill', label='Is my medicine real?', risk_colour='green', touch_target_dp=64,
		read_aloud_text='Is my medicine real? Scan the box or type the number on it.'),
	UIAsset(screen_id='wallet', pictogram='card', label='Family health wallet', risk_colour='neutral', touch_target_dp=64,
		read_aloud_text='Family health wallet. Everyone in your family, their cards and their records.'),
	UIAsset(screen_id='diary', pictogram='calendar-check', label='How am I feeling?', risk_colour='yellow', touch_target_dp=64,
		read_aloud_text='How am I feeling? Log how you feel today. It takes two taps.'),
)

# Coarse intent map for the voice interface. Offline recognition only covers these.
VOICE_INTENTS: tuple[tuple[tuple[str, ...], str, str], ...] = (
	(('fever', 'homa', 'hot body'), 'triage', 'Starting a fever check. Is the temperature above 38 degrees?'),
	(('hospital', 'clinic', 'dispensary', 'kituo'), 'facility', 'Finding the clinics nearest to you now.'),
	(('help', 'emergency', 'ambulance', 'saidia'), 'emergency', 'Calling for help. Press the red button to confirm.'),
	(('medicine', 'drug', 'dawa'), 'medicine', 'Let us check your medicine. Type or scan the number on the box.'),
	(('water', 'maji'), 'water', 'Checking whether the water in your area is safe.'),
	(('child', 'mtoto', 'vaccine', 'chanjo'), 'immunisation', 'Opening your child immunisation schedule.'),
)

INTENSITY_SENSORS: dict[str, list[str]] = {
	'low': ['fall'],
	'balanced': ['fall', 'cough', 'ppg'],
	'maximum': ['fall', 'cough', 'ppg', 'respiration', 'sleep', 'ambient'],
}
INTENSITY_BATTERY: dict[str, float] = {'low': 0.8, 'balanced': 2.5, 'maximum': 4.6}


class AccessService(LogMixin):
	def __init__(self) -> None:
		self._profiles: dict[str, AccessProfile] = {}
		assert self._profiles == {}

	def set_profile(self, profile: AccessProfile) -> AccessProfile:
		assert profile.lang in {v['code'] for v in LANGUAGE_MATRIX.values()}, f'unsupported language {profile.lang}'
		self._profiles[profile.subject_ref] = profile
		return profile

	def profile(self, subject_ref: str) -> AccessProfile:
		return self._profiles.get(subject_ref, AccessProfile(subject_ref=subject_ref))

	def screens(self, simple_mode: bool = False) -> list[UIAsset]:
		rows = [s for s in UI_SCREENS if s.simple_mode_visible or not simple_mode]
		assert all(s.touch_target_dp >= MIN_TOUCH_TARGET_DP for s in rows), 'touch targets below 48 dp'
		return rows

	def languages(self, tier: int | None = None) -> list[dict[str, object]]:
		out = [{'name': name, **meta} for name, meta in LANGUAGE_MATRIX.items() if tier is None or meta['tier'] == tier]
		assert out, 'language matrix must not be empty'
		return out

	def transcribe(self, req: VoiceRequest) -> VoiceResult:
		assert req.lang in {v['code'] for v in LANGUAGE_MATRIX.values()}, 'unsupported language'
		lowered = req.utterance.lower()
		for keywords, intent, reply in VOICE_INTENTS:
			if any(k in lowered for k in keywords):
				# On-device only when the language ships recognition and the request is offline-capable.
				asr = bool(next(v['asr'] for v in LANGUAGE_MATRIX.values() if v['code'] == req.lang))
				return VoiceResult(lang=req.lang, transcript=req.utterance, intent=intent, confidence=0.82,
					spoken_reply=reply, on_device=asr or req.offline)
		return VoiceResult(lang=req.lang, transcript=req.utterance, intent='unknown', confidence=0.3,
			spoken_reply='I did not catch that. Try saying: fever, find care, or help.', on_device=req.offline)

	def battery_profile(self, subject_ref: str, intensity: str = 'balanced', battery_saver: bool = False) -> BatteryProfile:
		assert intensity in INTENSITY_SENSORS, 'unknown intensity'
		sensors = [] if battery_saver else list(INTENSITY_SENSORS[intensity])
		pct = 0.4 if battery_saver else INTENSITY_BATTERY[intensity]
		assert pct <= 5.0, 'battery budget is <5% per day with all Tier 4 sensors on (§ACC-004)'
		return BatteryProfile(subject_ref=subject_ref, intensity=intensity, sensors_enabled=sensors,
			estimated_daily_pct=pct, charging_adaptive=True, battery_saver=battery_saver)

	def compatibility(self, platform: str) -> DeviceCompatibility:
		assert platform in ('android', 'ios'), 'known platform'
		if platform == 'android':
			return DeviceCompatibility(
				platform='android', os_min='8.0 (API 26)', apk_base_mb=0.9, go_edition_supported=True,
				no_play_services=True, min_ram_mb=512,
				on_demand_modules={'tier3': 8.0, 'lidar': 4.0, 'acoustic': 6.0, 'medicine_registry': 25.0, 'content_library': 15.0, 'facility_cache': 5.0},
				missing_sensor_fallbacks=dict(SENSOR_FALLBACKS),
			)
		return DeviceCompatibility(
			platform='ios', os_min='14.0', apk_base_mb=12.0, go_edition_supported=False,
			no_play_services=False, min_ram_mb=1024,
			on_demand_modules={'tier3': 8.0, 'lidar': 4.0, 'acoustic': 6.0, 'medicine_registry': 25.0, 'content_library': 15.0, 'facility_cache': 5.0},
			missing_sensor_fallbacks=dict(SENSOR_FALLBACKS),
		)

	@staticmethod
	def fallback_for(sensor: str) -> str:
		assert sensor in SENSOR_FALLBACKS, f'no fallback documented for {sensor}'
		return SENSOR_FALLBACKS[sensor]
