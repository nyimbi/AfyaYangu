"""Accessibility services (spec §12.1 ACC-001..005).

The point of this module is that no user is excluded by their device. Every capability that a
missing sensor removes has a named fallback, and the fallback table is data the client renders —
not a paragraph in a document that nobody enforces.
"""
from pathlib import Path

from afya.access.views import (
	LANGUAGE_MATRIX, MIN_TOUCH_TARGET_DP, NARROW_WIDTH_DP, SCREEN_BUCKETS, TABLET_WIDTH_DP,
	AccessProfile, BatteryProfile, DeviceCompatibility, SamplingContext, ScreenLayout, UIAsset,
	VoiceAudioRequest, VoiceRequest, VoiceResult,
)
from afya.logmixin import LogMixin
from afya.sensors.views import SenseKind
from afya.strings import SYMPTOM_WORDS, answerable

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

# §13.2's nine rows, verbatim: the sensor the section names as missing, and the path it says still
# works. The section keys its rows on the sensor ("No LiDAR"), while `SENSOR_FALLBACKS` keys them on
# a slug — and the two vocabularies differ in three places, which is exactly how the tables drift:
# §13.2 says `camera` where §13.1 splits rear from front, and `wearable` where §13.1 has no row at
# all. Carrying the section's own labels here lets the two be compared instead of assumed equal.
#
# The fallback text is deliberately not the section's: `SENSOR_FALLBACKS` is what a client renders,
# so it is a plain-language rewrite with the spec ids dropped. Only the row *set* is compared.
SPEC_FALLBACK_ROWS: tuple[tuple[str, str, str], ...] = (
	('lidar', 'No LiDAR', 'Acoustic respiration estimation (SENS-002) or manual entry'),
	('microphone', 'No microphone access', 'Manual symptom entry'),
	('gyroscope', 'No gyroscope', 'Accelerometer-only fall detection (reduced accuracy)'),
	('gps', 'No GPS', 'Manual location entry, cell-tower triangulation, QR check-in'),
	('bluetooth', 'No Bluetooth', 'Manual contact listing'),
	('nfc', 'No NFC', 'QR code scan'),
	('camera', 'No camera', 'Manual medicine registration number entry'),
	('thermometer', 'No biometric sensor', 'Manual temperature entry'),
	('wearable', 'No wearable', 'Manual health data entry'),
)

# §ACC-005's "support for low-resolution screens", as the layout each bucket gets. The narrow row is
# not a smaller copy of the regular one: it is one column instead of two, a smaller pictogram, and
# the label reserved over more lines. The touch target is 56 against 64 — still above §ACC-001's
# 48 dp floor, because a screen that is small is exactly the screen where a thumb misses, and
# shrinking the control to make room is the move that looks like an answer and is not.
SCREEN_LAYOUTS: tuple[ScreenLayout, ...] = (
	ScreenLayout(bucket='narrow', smallest_width_dp=NARROW_WIDTH_DP, columns=1, scrolls=True,
	             pictogram_dp=32, touch_target_dp=56, label_lines=2, degrades=''),
	ScreenLayout(bucket='regular', smallest_width_dp=TABLET_WIDTH_DP, columns=2, scrolls=True,
	             pictogram_dp=48, touch_target_dp=64, label_lines=1, degrades=''),
)
# Above the tablet bucket nothing degrades and nothing is claimed: a device wider than the layout
# needs gets the regular layout, because inventing a "wide" row would be a commitment §ACC-005 does
# not make.
assert {row.bucket for row in SCREEN_LAYOUTS} == {b for b, _ in SCREEN_BUCKETS}, \
	'every bucket needs a layout'
assert all(row.touch_target_dp >= MIN_TOUCH_TARGET_DP for row in SCREEN_LAYOUTS), \
	'a screen bucket may not shrink a control below the §ACC-001 floor'


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

# §ACC-002's first bullet asks for *symptom reporting*, and the predecessor read six intent
# keywords and returned a canned reply — a person who said "fever and headache since Tuesday" was
# answered at the fever intent and the headache was dropped. These are the symptoms the voice path
# hears in free text, read from §5.4's own vocabulary rather than written again so a symptom the
# triage engine knows cannot be invisible to the voice path.
VOICE_SYMPTOM_WORDS: tuple[str, ...] = SYMPTOM_WORDS

VOICE_TRIAGE_FOLLOWUP: dict[str, str] = {
	'en': 'I heard symptoms. Starting a check — is the temperature above 38 degrees?',
	'sw': 'Nimesikia dalili. Tunaanza ukaguzi — je, joto ni zaidi ya digrii 38?',
}

VOICE_UNRECOGNISED: dict[str, str] = {
	'en': 'I did not catch that. Try saying: fever, find care, or help.',
	'sw': 'Sikusikia vizuri. Jaribu kusema: homa, tafuta matibabu, au msaada.',
}

# §ACC-004's Low / Balanced / Maximum, as the *reading kinds* each level collects. These are
# `SenseKind` members, not §13.1 sensor slugs — the predecessor held them under a field called
# `sensors_enabled` and not one resolved to a sensor the app has, so the screen listing "sensors
# on" named six things nothing measures with. `INTENSITY_SENSORS` below is the join.
INTENSITY_READINGS: dict[str, list[str]] = {
	'low': ['fall'],
	'balanced': ['fall', 'cough', 'ppg'],
	'maximum': ['fall', 'cough', 'ppg', 'respiration', 'sleep', 'ambient'],
}
INTENSITY_BATTERY: dict[str, float] = {'low': 0.8, 'balanced': 2.5, 'maximum': 4.6}

# §14.2's "target: <2% per day" for acoustic monitoring alone, against §ACC-004's <5% for
# everything. Kept as the section prints them so a reader can see the two budgets are different
# claims about different sets of sensors.
ACOUSTIC_DAILY_PCT = 2.0


def _sensors_for(kinds: list[str]) -> list[str]:
	"""The §13.1 sensors that carry a set of reading kinds, in §13.1's own order.

	The join the module was missing. `SenseIngest` classifies each reading as a `SenseKind` and
	`_INGEST_FEATURE` maps each kind to the sensor feature that produces it; §13.1 maps that feature
	to the sensor rows. Three tables already existed and nothing crossed them, so the intensity
	level and the hardware were two independent lists that happened to be spelled similarly.
	"""
	from afya.sensors.service import _INGEST_FEATURE, SENSORS
	wanted = {_INGEST_FEATURE[SenseKind(kind)] for kind in kinds}
	slugs = [spec.slug for spec in SENSORS if wanted & set(spec.primary_features)]
	assert slugs, f'no §13.1 sensor carries {kinds}'
	return slugs


INTENSITY_SENSORS: dict[str, list[str]] = {
	level: _sensors_for(kinds) for level, kinds in INTENSITY_READINGS.items()
}

# §ACC-004's context axis. The section names three ("charging, stationary, time of day") and §14.2
# names two more in its own words ("disabled when on a call, in a meeting, or when the user sets
# 'do not monitor'"). The values are multipliers on the device's sampling baseline: the spec prints
# no rate, so a context choosing an absolute Hz would be inventing a figure. Every entry carries
# the sentence a person reads in settings.
CONTEXT_DUTY: dict[str, tuple[float, str]] = {
	'do_not_monitor': (0.0, 'Monitoring is off because you asked it to stay off.'),
	'on_call': (0.0, 'Monitoring pauses while you are on a call, so the microphone stays free.'),
	'charging': (2.0, 'Sampling runs faster while the phone is charging, because the battery is not the constraint.'),
	'stationary': (1.5, 'Sampling runs faster while the phone is still, because movement is not confusing the reading.'),
	'night': (0.5, 'Sampling runs slower at night to save battery while you sleep.'),
	'day': (1.0, 'Sampling runs at the normal rate.'),
}
# The order the contexts are tested in, most specific first: a person who asked for no monitoring
# gets no monitoring whatever else is true, and a call outranks a charger.
CONTEXT_ORDER: tuple[str, ...] = (
	'do_not_monitor', 'on_call', 'charging', 'stationary', 'night', 'day',
)
NIGHT_HOURS = (22, 23, 0, 1, 2, 3, 4, 5)
assert set(CONTEXT_ORDER) == set(CONTEXT_DUTY), 'every context needs a rate and a reason'


class AccessService(LogMixin):
	def __init__(self, speech: object | None = None) -> None:
		"""`speech` is §ACC-002's recogniser, injected rather than imported for §SENS-002's reason.

		`WhisperSpeechEngine` loads 41 MB of ONNX and needs `onnxruntime`, so a deployment that has
		not shipped the assets — and every unit test that only wants the text path — must be able to
		build this service without it. When it is absent, an *audio* request is refused by name
		rather than answered from a stub, because a transcript nobody produced is the one failure a
		voice path may not have.
		"""
		self._profiles: dict[str, AccessProfile] = {}
		self._speech = speech
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
		"""§ACC-002's voice path, answering two different questions with one entry point.

		`purpose='symptoms'` is §ACC-002's *first* bullet: the caller's own words are read for the
		symptoms they name and the intent map decides what to do about them. Reading the symptoms out
		of the utterance is what makes this a *report* rather than a menu — the predecessor matched
		six keyword intents and returned a canned reply, so a person who said "I have had fever and
		headache since Tuesday" was answered at the fever intent and the headache was dropped.

		`purpose='note'` is the third bullet, and it is not a triage: a CHW's note or case
		description has no intent and no recommendation, and running it through the intent map
		discarded the dictation and answered `intent=unknown`. The transcript *is* the result, and
		`intent` says so rather than pretending to a classification that was never attempted.

		`served_in` reports the language the answer is actually in. §ACC-002 lists six languages for
		this bullet and only `en`/`sw` have tables, so the gap is served rather than hidden: the
		caller is told which language they got, on the same `answerable` rule the triage route uses.
		"""
		assert req.lang in {v['code'] for v in LANGUAGE_MATRIX.values()}, 'unsupported language'
		served = answerable(req.lang)
		asr = bool(next(v['asr'] for v in LANGUAGE_MATRIX.values() if v['code'] == req.lang))
		lowered = req.utterance.lower()
		if req.purpose == 'note':
			# §ACC-002's "voice-to-text for CHW notes and case descriptions". The words are the
			# output; nothing is classified and nothing is recommended, because a note is not a
			# symptom report and answering it as one would put a triage verdict on a field
			# observation.
			return VoiceResult(
				lang=req.lang, transcript=req.utterance, intent='note', confidence=1.0,
				spoken_reply='Note saved as text.', on_device=asr, served_in=served, symptoms=[],
			)
		symptoms = [s for s in VOICE_SYMPTOM_WORDS if s in lowered]
		for keywords, intent, reply in VOICE_INTENTS:
			if any(k in lowered for k in keywords):
				return VoiceResult(lang=req.lang, transcript=req.utterance, intent=intent, confidence=0.82,
					spoken_reply=reply, on_device=asr, served_in=served, symptoms=symptoms)
		if symptoms:
			# A symptom named with no intent keyword is still a symptom report. The predecessor
			# returned `intent=unknown` and dropped the symptom, so "I have been vomiting" entered
			# nothing at all — the words were heard and the finding was lost.
			return VoiceResult(lang=req.lang, transcript=req.utterance, intent='triage', confidence=0.6,
				spoken_reply=VOICE_TRIAGE_FOLLOWUP[served], on_device=asr, served_in=served,
				symptoms=symptoms)
		return VoiceResult(lang=req.lang, transcript=req.utterance, intent='unknown', confidence=0.3,
			spoken_reply=VOICE_UNRECOGNISED[served], on_device=asr, served_in=served, symptoms=[])

	@property
	def speech(self) -> object:
		assert self._speech is not None, (
			'the speech model is not deployed (models/speech); audio cannot be transcribed without it')
		return self._speech

	def transcribe_audio(self, req: VoiceAudioRequest, path: Path) -> VoiceResult:
		"""§ACC-002's audio path: a recording in, the same answer the text path gives.

		This is where the three voice bullets meet. The audio is transcribed by the on-device
		recogniser, the transcript is then put through `transcribe` — the *same* method the typed
		path uses — so a spoken symptom report and a typed one cannot diverge into two sets of
		rules. `recogniser` records which model produced the words, and `on_device` is the engine's
		own claim rather than this method's.

		The language is not detected. §ACC-002 ships recognition per language, and a three-word
		utterance is too short to detect from: a wrong guess produces a fluent transcript of the
		wrong words, which is worse than a refusal because it reads like a successful recording.
		"""
		assert req.lang in {v['code'] for v in LANGUAGE_MATRIX.values()}, 'unsupported language'
		engine = self.speech
		recognised = engine.transcribe_wav(path, req.lang)  # type: ignore[attr-defined]
		served = self.transcribe(VoiceRequest(
			subject_ref=req.subject_ref, lang=req.lang, utterance=recognised.transcript,
			purpose=req.purpose,
		))
		return served.model_copy(update={
			'on_device': bool(recognised.on_device),
			'recogniser': f'whisper-tiny/{req.lang}',
		})

	@staticmethod
	def _context_key(ctx: SamplingContext | None) -> str:
		"""Which of §ACC-004's contexts applies, most specific first.

		A person who set "do not monitor" gets no monitoring whatever else is true, and a call
		outranks a charger — the order is the rule, and it is data (`CONTEXT_ORDER`) rather than a
		chain of `if`s so a context added to the table without a place in the order fails the import
		assert rather than being silently unreachable.
		"""
		if ctx is None:
			return 'day'
		state = {
			'do_not_monitor': ctx.do_not_monitor,
			'on_call': ctx.on_call,
			'charging': ctx.charging,
			'stationary': ctx.stationary,
			'night': ctx.hour in NIGHT_HOURS,
		}
		for key in CONTEXT_ORDER:
			if state.get(key):
				return key
		return 'day'

	def battery_profile(self, subject_ref: str, intensity: str = 'balanced', battery_saver: bool = False,
	                    context: SamplingContext | None = None) -> BatteryProfile:
		"""§ACC-004's intensity level, its battery saver, and the *context* the section names.

		The context is the part that was absent. `charging_adaptive` was hardcoded `True` and nothing
		read a charging state, a motion state or the hour, so "adaptive sensor sampling rates based on
		context" described a field with no referent — the rate never moved.

		The rate is a **duty multiplier** on the handset's own baseline rather than an absolute Hz:
		§ACC-004 prints no sampling rate, and a figure invented here would be a commitment the spec
		never made. What the server owns is which context applies, by how much it scales, and the
		sentence the person reads.
		"""
		assert intensity in INTENSITY_READINGS, 'unknown intensity'
		key = self._context_key(context)
		duty, reason = CONTEXT_DUTY[key]
		readings = [] if battery_saver else list(INTENSITY_READINGS[intensity])
		sensors = [] if battery_saver else list(INTENSITY_SENSORS[intensity])
		pct = 0.4 if battery_saver else INTENSITY_BATTERY[intensity]
		if battery_saver:
			# Battery saver is the person switching the sensors off, so there is no sampling rate for
			# a context to adapt. A saver that let a charger scale the rate back up would be the phone
			# overriding the person who asked for it.
			duty = 0.0
			reason = 'Battery saver is on, so the sensors are off and nothing is being sampled.'
		# §ACC-004's budget, named in the comment rather than in the message: a refusal is read by a
		# person, and a spec id is an internal traceability handle.
		assert pct <= 5.0, 'the sensors would use more than the daily battery budget'
		# The context scales the drain as well as the rate: a profile that ran sampling at 2x while
		# reporting the un-scaled figure would be the settings screen lying about the cost of the
		# setting it just applied. The scaled figure is reported **unclamped** — §ACC-004's <5% is a
		# *daily* budget, and sampling faster while charging is precisely the case where exceeding it
		# costs nothing, so capping the number at 5 would be a lie in the reassuring direction. The
		# assert is on the base intensity, which is the figure the section's target is about.
		# The saver's residual figure is the app's own cost, not sensor sampling, so the duty must not
		# scale it: a saver reporting 0.0% would say the app costs nothing to run.
		scaled = pct if battery_saver else round(pct * duty, 2)
		assert INTENSITY_BATTERY[intensity] <= 5.0, 'this intensity would exceed the daily battery budget'
		return BatteryProfile(
			subject_ref=subject_ref, intensity=intensity, sensors_enabled=sensors,
			readings_enabled=readings, estimated_daily_pct=scaled,
			charging_adaptive=True, battery_saver=battery_saver,
			context=key, context_reason=reason, sampling_duty=duty,
		)

	@staticmethod
	def screen_bucket(smallest_width_dp: int) -> str:
		"""Which bucket a device's shorter side falls in, read off `SCREEN_BUCKETS`.

		Keyed on `smallestWidth` rather than on width because the shorter side is the same number in
		portrait and landscape: a phone that fits in a pocket does not become a tablet when it is
		turned, and a layout that changed columns on rotation for that reason would be answering a
		question nobody asked.
		"""
		assert smallest_width_dp >= 1, 'a screen has a positive width'
		chosen = SCREEN_BUCKETS[0][0]
		for bucket, floor in SCREEN_BUCKETS:
			if smallest_width_dp >= floor:
				chosen = bucket
		assert chosen in {row.bucket for row in SCREEN_LAYOUTS}, 'every bucket has a layout'
		return chosen

	def layout_for(self, smallest_width_dp: int) -> ScreenLayout:
		"""§ACC-005's "support for low-resolution screens", as the layout that device gets.

		The width the caller reported is carried back with the bucket's row rather than the row's own
		floor, so a client can tell 360dp from 320dp within the same layout instead of reading the
		answer as "you are exactly on the boundary".
		"""
		bucket = self.screen_bucket(smallest_width_dp)
		row = next(r for r in SCREEN_LAYOUTS if r.bucket == bucket)
		# §ACC-001's floor, in the comment rather than the message for the reason above.
		assert row.touch_target_dp >= MIN_TOUCH_TARGET_DP, 'the layout shrinks its controls below the touch-target floor'
		return row.model_copy(update={'smallest_width_dp': smallest_width_dp})

	@staticmethod
	def screen_layouts() -> list[ScreenLayout]:
		"""Every bucket, so a client can lay out for a phone it is not running on.

		§ACC-001's screen contracts are rendered by the *native* clients, and a designer building for
		the 320dp handset is usually holding something larger. Serving the narrow row rather than
		describing it in a document is the same rule the fallback table follows.
		"""
		rows = list(SCREEN_LAYOUTS)
		assert len(rows) == len(SCREEN_BUCKETS), 'one layout per bucket'
		return rows

	def compatibility(self, platform: str, smallest_width_dp: int = NARROW_WIDTH_DP) -> DeviceCompatibility:
		"""What this device gets. `smallest_width_dp` defaults to the reference handset, not to the
		tablet: a caller who does not say what they are holding is assumed to be on the smaller
		device, because the narrow layout renders correctly on a large screen and the reverse is not
		true.
		"""
		assert platform in ('android', 'ios'), 'known platform'
		if platform == 'android':
			return DeviceCompatibility(
				platform='android', os_min='8.0 (API 26)', apk_base_mb=0.9, go_edition_supported=True,
				no_play_services=True, min_ram_mb=512,
				on_demand_modules={'tier3': 8.0, 'lidar': 4.0, 'acoustic': 6.0, 'medicine_registry': 25.0, 'content_library': 15.0, 'facility_cache': 5.0},
				missing_sensor_fallbacks=dict(SENSOR_FALLBACKS),
				smallest_width_dp=smallest_width_dp, screen_layouts=self.screen_layouts(),
			)
		return DeviceCompatibility(
			platform='ios', os_min='14.0', apk_base_mb=12.0, go_edition_supported=False,
			no_play_services=False, min_ram_mb=1024,
			on_demand_modules={'tier3': 8.0, 'lidar': 4.0, 'acoustic': 6.0, 'medicine_registry': 25.0, 'content_library': 15.0, 'facility_cache': 5.0},
			missing_sensor_fallbacks=dict(SENSOR_FALLBACKS),
			smallest_width_dp=smallest_width_dp, screen_layouts=self.screen_layouts(),
		)

	@staticmethod
	def fallback_for(sensor: str) -> str:
		assert sensor in SENSOR_FALLBACKS, f'no fallback documented for {sensor}'
		return SENSOR_FALLBACKS[sensor]
