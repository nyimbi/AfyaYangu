"""Mental health service: validated screens, mood log, outbreak support and referral.

`MentalHealthService` carried WHO-5 and the counselling-line directory. §REC-005 asks for six
things; `instruments.py` supplies the first (PHQ-9 and GAD-7 with item text, scale and the
publisher's cut-points) and `support.py` supplies the coping, outbreak and referral content. This
module is the behaviour: it administers a screen, keeps the mood series, and builds a referral that
names services and reports what it could not reach.
"""
import statistics

from afya.ids import uuid7str
from afya.logmixin import LogMixin
from afya.mental.instruments import (
	AVAILABLE_LANGS, GAD7_FURTHER_EVALUATION_AT, ITEM_BANKS, PHQ9_IMPAIRMENT_QUESTION, RESPONSE_OPTIONS,
	SUICIDE_RISK_ITEM, TIMEFRAME, band_of, bands_for, max_total,
)
from afya.mental.support import (
	COPING_STRATEGIES, OUTBREAK_CONDITIONS, OUTBREAK_SUPPORT, CopingStrategy, MoodEntry, MoodTrend,
	OutbreakGuidance, ServiceReferral,
)
from afya.mental.views import COUNSELLING_LINES, Screening, ScreeningResult, WHO5, WellbeingVerdict

__all__ = [
	'COPING_STRATEGIES', 'COUNSELLING_LINES', 'OUTBREAK_CONDITIONS', 'OUTBREAK_SUPPORT', 'MoodEntry',
	'MoodTrend', 'Screening', 'ScreeningResult', 'ServiceReferral', 'WHO5', 'WellbeingVerdict',
	'MentalHealthService', 'guidance_for', 'screening_advice',
]

# A mood trend needs readings before it has a direction. Three is the smallest number that can show
# a direction at all rather than a difference between two points, and `too_few` is a named answer
# rather than a flat line over a gap.
MIN_TREND_ENTRIES = 3

# The band -> advice table. The manual's Table 4 proposes treatment actions per PHQ-9 band, and those
# are a clinician's options; what a self-check can honestly say is what to do next, so these say
# that. `self_harm` overrides every band, because item 9 above zero is not a severity level.
SCREENING_ADVICE: dict[str, str] = {
	'none_minimal': 'Nothing here suggests you need treatment. Keep your routines and check again if things change.',
	'minimal': 'A low score. Keep your routines and check again if things change.',
	'mild': 'Some symptoms. Watch and repeat the check in a few weeks; talk to someone you trust.',
	'moderate': 'Talk to a health worker about this. Counselling or further assessment may help.',
	'moderately_severe': 'Please see a health worker soon about treatment and support.',
	'severe': 'Please contact a health worker or one of the lines below today.',
}

# Names what the person endorsed without quoting the instrument back at them. The item's own words
# ("better off dead") are a clinical phrasing written to be answerable on a form, and repeating them
# verbatim to someone who just ticked the box is blunter than saying the same thing plainly.
SELF_HARM_ADVICE = ('You said you have had thoughts of ending your life or of hurting yourself. '
                    'Please contact a counselling line or 719 today, and tell someone near you. '
                    'This is not something to carry alone.')

SELF_HARM_REFERRAL_REASON = 'a positive answer to the self-harm item'


def guidance_for(condition: str, lang: str = 'en') -> OutbreakGuidance:
	"""One of §REC-005's three outbreak-specific conditions, in the language asked for.

	The three are named conditions rather than bands because "your score is 14" does not tell a
	person in isolation that what they are feeling has a name and a route. The slugs are the section's
	own three — isolation distress, grief support, healthcare worker burnout.
	"""
	assert condition in OUTBREAK_CONDITIONS, f'unknown outbreak condition {condition}'
	assert lang in ('en', 'sw'), f'no content in {lang}'
	row = next(g for g in OUTBREAK_SUPPORT if g['slug'] == condition)
	text = row[lang]
	assert isinstance(text, dict), 'content shape'
	return OutbreakGuidance(slug=condition, title=text['title'], body=text['body'],
	                        signs=list(text['signs']))


def coping_strategies(lang: str = 'en') -> list[CopingStrategy]:
	"""The coping and psychoeducation list, from WHO PFA, in the source's own translation.

	The Kiswahili is the archived Kiswahili edition's wording and register, not a machine rendering
	of the English: `sources/who-pfa/` holds both editions, so the two languages are two published
	texts rather than one text and a translation of it.
	"""
	assert lang in ('en', 'sw'), f'no content in {lang}'
	out: list[CopingStrategy] = []
	for row in COPING_STRATEGIES:
		text = row[lang]
		assert isinstance(text, dict), 'content shape'
		out.append(CopingStrategy(slug=str(row['slug']), title=text['title'], body=text['body']))
	return out


def screening_advice(result_band: str, self_harm: bool) -> str:
	"""What to say after a screen. Item 9 outranks the band, always.

	A total in `none_minimal` with a positive self-harm item is a person at risk in the lowest band,
	so the check is ordered the way the risk is: the item first, the band only if the item is clear.
	"""
	assert result_band in SCREENING_ADVICE, f'unknown band {result_band}'
	if self_harm:
		return SELF_HARM_ADVICE
	return SCREENING_ADVICE[result_band]


class MentalHealthService(LogMixin):
	def __init__(self) -> None:
		self._moods: list[MoodEntry] = []
		self._referrals: list[ServiceReferral] = []

	def assess(self, who5: WHO5) -> WellbeingVerdict:
		assert all(0 <= s <= 5 for s in who5.scores), 'item bounds'
		raw = who5.raw
		if raw < 29:
			verdict_band, advise = 'very_low', 'Likely depression range. Please contact a counselling line today; consider 719 for referral. You are not alone.'
		elif raw < 50:
			verdict_band, advise = 'low', 'Well-being is low: talk to someone you trust; use the counselling lines listed; book a facility visit.'
		else:
			verdict_band, advise = 'good', 'Well-being within normal range. Keep strong routines: sleep, movement, people.'
		return WellbeingVerdict(raw=raw, band=verdict_band, advise=advise)

	def lines(self) -> list[dict[str, str]]:
		return list(COUNSELLING_LINES)

	def screen(self, req: Screening) -> ScreeningResult:
		"""Administer PHQ-9 or GAD-7 and score it against the publisher's cut-points.

		The answer count is checked against the instrument's own item bank rather than against a
		number written here, so a seven-answer PHQ-9 is refused instead of scored as a shorter
		questionnaire — which is the failure mode of positional answers, and the reason `WHO5.scores`
		being positional with no item text was a gap rather than a shorthand.

		When the instrument has no form in the requested language the English items are served and the
		substitution is named in the result. Serving beats refusing — a person who reads some English
		gets a screen — but a caller that does not know it happened holds a score from questions the
		person may not have understood, and that is a number nobody should act on unknowingly.
		"""
		assert req.instrument in ITEM_BANKS, f'unknown instrument {req.instrument}'
		bank = ITEM_BANKS[req.instrument]['en']
		assert len(req.answers) == len(bank), (
			f'{req.instrument} has {len(bank)} items, {len(req.answers)} answers given')
		assert all(0 <= a <= len(RESPONSE_OPTIONS['en']) - 1 for a in req.answers), 'answer out of range'

		served_in_english = req.lang not in AVAILABLE_LANGS[req.instrument]
		served_lang = 'en' if served_in_english else req.lang
		items = list(ITEM_BANKS[req.instrument][served_lang])
		total = sum(req.answers)
		result_band = band_of(req.instrument, total)

		# Item 9 is PHQ-9's self-harm item and it is read on its own as well as summed. GAD-7 has no
		# equivalent item, so the flag is False there rather than absent — a client should not have to
		# know which instrument carries the item to decide whether to render a crisis route.
		self_harm = req.instrument == 'phq9' and req.answers[SUICIDE_RISK_ITEM - 1] > 0
		further = None
		if req.instrument == 'gad7':
			further = total >= GAD7_FURTHER_EVALUATION_AT
		advise = screening_advice(result_band, self_harm)
		if further and not self_harm:
			advise = f'{advise} A score of {total} is at or above the level where further evaluation is recommended.'
		if served_in_english and req.lang != 'en':
			advise = f'{advise} (These items are in English: this questionnaire has no {req.lang} version.)'

		return ScreeningResult(
			instrument=req.instrument, lang=served_lang, items=items,
			options=list(RESPONSE_OPTIONS[served_lang]), timeframe=TIMEFRAME[served_lang],
			answers=list(req.answers), total=total, band=result_band,
			severity_note=f'{total} of {max_total(req.instrument)} ({result_band.replace("_", " ")})',
			self_harm_item_positive=self_harm, advise=advise,
			served_in_english_instead=served_in_english, further_evaluation=further)

	def log_mood(self, entry: MoodEntry) -> MoodEntry:
		"""Record one day's own reading. Returns what was stored, so a client sees the same row."""
		assert 0 <= entry.score <= 10, 'mood score out of range'
		self._moods.append(entry)
		return entry

	def mood_trend(self, subject_ref: str, window_days: int = 14) -> MoodTrend:
		"""The person's own trend over a window, or a named reason there is not one.

		`too_few` is a distinct answer and not a flat line: two readings with the same score are not
		a steady mood, they are two readings. A window that excludes every entry is also `too_few`
		rather than a mean of nothing.
		"""
		assert window_days >= 1, 'window must be at least a day'
		entries = [e for e in self._moods if e.subject_ref == subject_ref]
		ordered = sorted(entries, key=lambda e: e.logged_at_iso)
		if len(ordered) < MIN_TREND_ENTRIES:
			return MoodTrend(entries=len(ordered), mean=0.0, direction='too_few', window_days=window_days,
			                 advise='Log how you feel for a few more days and a direction will appear.')
		scores = [float(e.score) for e in ordered[-window_days:]]
		if len(scores) < MIN_TREND_ENTRIES:
			return MoodTrend(entries=len(ordered), mean=0.0, direction='too_few', window_days=window_days,
			                 advise='Log how you feel for a few more days and a direction will appear.')
		mean = statistics.fmean(scores)
		# The first and last readings decide the direction, not a fitted slope: over a fortnight of
		# a 0–10 self-rating a slope reads noise as trend, and a person comparing "where I started"
		# with "where I am" is doing the arithmetic the chart is drawing.
		delta = scores[-1] - scores[0]
		direction = 'rising' if delta > 1 else ('falling' if delta < -1 else 'flat')
		advise = {
			'rising': 'Your own scores have been moving up. Keep what you are doing.',
			'falling': 'Your own scores have been moving down. Consider talking to someone or using a line below.',
			'flat': 'Your own scores have been steady.',
		}[direction]
		return MoodTrend(entries=len(ordered), mean=round(mean, 2), direction=direction,
		                 window_days=window_days, advise=advise)

	def coping(self, lang: str = 'en') -> list[CopingStrategy]:
		return coping_strategies(lang)

	def outbreak_support(self, condition: str, lang: str = 'en') -> OutbreakGuidance:
		return guidance_for(condition, lang)

	def refer(self, subject_ref: str, reason: str, urgency: str = 'routine') -> ServiceReferral:
		"""Build a referral that names services, or names what it could not reach.

		A referral to a service that does not exist is worse than none, because the person stops
		looking. So the lines are read from the directory the app actually serves and each is marked
		with whether it is verified; the unverified ones are listed in `unreachable` by name, which is
		what `COUNSELLING_LINES` has carried as `verified: 'False'` since before this method existed.
		"""
		assert urgency in ('routine', 'soon', 'urgent'), f'unknown urgency {urgency}'
		assert reason, 'a referral without a reason is a record nobody can act on'
		services: list[dict[str, str]] = []
		unreachable: list[str] = []
		for line in COUNSELLING_LINES:
			row = dict(line)
			services.append(row)
			if row.get('verified') != 'True':
				unreachable.append(f'{row["name"]} ({row["number"]}) — number not verified against the provider')
		referral = ServiceReferral(
			referral_id=f'MH-{uuid7str()[:12].upper()}', subject_ref=subject_ref, reason=reason,
			urgency=urgency, services=services, unreachable=unreachable,
			advise='Contact one of these services. If the number does not answer, use 719.')
		self._referrals.append(referral)
		self._log_info('mental referral recorded', referral_id=referral.referral_id, urgency=urgency)
		return referral

	def impairment_question(self, lang: str = 'en') -> str:
		"""PHQ-9's unnumbered functional-impairment question. Never scored, so never in the item bank."""
		assert lang in PHQ9_IMPAIRMENT_QUESTION, f'no content in {lang}'
		return PHQ9_IMPAIRMENT_QUESTION[lang]

	def cutpoints(self, instrument: str) -> list[dict[str, object]]:
		"""The publisher's cut-points for one instrument, so a client renders the same bands we score."""
		return [{'up_to': ceiling, 'band': name} for ceiling, name in bands_for(instrument)]
