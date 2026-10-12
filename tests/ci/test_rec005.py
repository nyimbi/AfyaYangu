"""§REC-005: PHQ-9 and GAD-7, mood tracking, coping and psychoeducation, referral, outbreak support.

The section asks for six things. Five were `missing` and one — the crisis-line directory — was
carried. What is under test here is not "does a route exist" but whether each bullet is discharged
against the thing that makes it true:

* **The instruments are the published instruments.** Item text, response scale and cut-points come
  from the archived sources, so the tests read them back against the source's own numbers rather
  than against a constant this repo chose. The canary for this is a *wrong* cut-point: a band table
  that scores 10 as `mild` would pass any test written from the same table.
* **Localisation is real or it is named.** A Kiswahili PHQ-9 exists and is served; a Kiswahili GAD-7
  does not, and the service serves English *and says so*. The failure this guards against is the one
  that looks best: English items under a `sw` label, returning a score from someone who could not
  read the questions.
* **Item 9 outranks the band.** A total of 2 is `none_minimal`, and with item 9 positive it is still
  a person at risk. Any test that only checks totals passes a scorer that folds item 9 into the sum.
* **Referral routes somebody.** The predecessor was a prose sentence. A referral that lists a
  service whose number was never verified, and does not say so, is the same failure in a new shape.
"""
import re

import httpx
import pytest

from afya.mental.instruments import (
	AVAILABLE_LANGS, GAD7_FURTHER_EVALUATION_AT, ITEM_BANKS, PHQ9_ITEMS, RESPONSE_OPTIONS,
	SUICIDE_RISK_ITEM, TIMEFRAME, band_of, bands_for, max_total,
)
from afya.mental.service import (
	MIN_TREND_ENTRIES, SELF_HARM_ADVICE, MentalHealthService, MoodEntry, Screening, guidance_for,
)
from afya.mental.support import COPING_STRATEGIES, OUTBREAK_CONDITIONS, OUTBREAK_SUPPORT, ReferralRequest
from afya.service import build_services, create_app

# §3.3 principle 9 and §6.2.1: a section number must not reach anything a person reads. The new
# surfaces serve item text, guidance and advice, so the pattern is checked against every one.
FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')


def _service() -> MentalHealthService:
	return MentalHealthService()


def _screen(instrument: str, answers: list[int], **kw: object) -> Screening:
	body: dict[str, object] = {'subject_ref': 'U1', 'instrument': instrument, 'answers': answers,
	                           'administered_at_iso': '2026-10-12T09:00'}
	return Screening(**{**body, **kw})  # type: ignore[arg-type]


async def _client() -> httpx.AsyncClient:
	return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(build_services())),
	                         base_url='http://t')


async def _citizen(c: httpx.AsyncClient) -> tuple[dict[str, str], str]:
	"""An anonymous citizen token — the app's own citizen path, and the subject it carries."""
	tok = (await c.post('/auth/anonymous', json={})).json()
	return {'Authorization': f'Bearer {tok["token"]}'}, str(tok['subject_ref'])


# --- The instruments are the published instruments ------------------------------------------------

def test_the_item_banks_are_the_published_lengths() -> None:
	"""Nine and seven, from the forms themselves. A shortened bank scores a different instrument."""
	assert len(PHQ9_ITEMS['en']) == 9 and len(PHQ9_ITEMS['sw']) == 9
	assert len(ITEM_BANKS['gad7']['en']) == 7
	assert len(PHQ9_ITEMS['en']) == len(PHQ9_ITEMS['sw']), 'the two PHQ-9 forms are one instrument'


def test_the_response_scale_is_four_options_scoring_zero_to_three() -> None:
	assert len(RESPONSE_OPTIONS['en']) == 4 and len(RESPONSE_OPTIONS['sw']) == 4
	assert RESPONSE_OPTIONS['en'][0] == 'Not at all' and RESPONSE_OPTIONS['en'][3] == 'Nearly every day'
	assert max_total('phq9') == 27 and max_total('gad7') == 21


def test_the_item_text_matches_the_archived_forms() -> None:
	"""Spot-checks against `sources/phq9-gad7/PHQ-9_English.txt`, including the item that matters most.

	Item 9 is the self-harm item and its wording is load-bearing: a paraphrase of "thoughts that you
	would be better off dead or of hurting yourself in some way" is a different question, and a
	paraphrase that softens it under-detects the one item that must not under-detect.
	"""
	assert PHQ9_ITEMS['en'][0] == 'Little interest or pleasure in doing things'
	assert PHQ9_ITEMS['en'][2].startswith('Trouble falling or staying asleep')
	assert PHQ9_ITEMS['en'][SUICIDE_RISK_ITEM - 1].startswith('Thoughts that you would be better off dead')
	assert 'hurting yourself' in PHQ9_ITEMS['en'][SUICIDE_RISK_ITEM - 1]
	assert ITEM_BANKS['gad7']['en'][0] == 'Feeling nervous, anxious or on edge'
	assert 'Over the last 2 weeks' in TIMEFRAME['en']


def test_the_kiswahili_items_are_the_archived_translation() -> None:
	"""From `PHQ-9_Kiswahili.txt`, which carries the publisher's own Kiswahili edition.

	The licence sentence is translated there too ("Hakuna kibali kinachohitajika…"), which is what
	makes serving this form an act the publisher asked for.
	"""
	assert PHQ9_ITEMS['sw'][0] == 'Kutokuwa na hamu au raha ya kufanya kitu'
	assert PHQ9_ITEMS['sw'][SUICIDE_RISK_ITEM - 1].startswith('Mawazo kuwa ni afadhali zaidi ufe')
	assert RESPONSE_OPTIONS['sw'][0] == 'Haijatoke kabisa'
	assert 'wiki mbili zilizopita' in TIMEFRAME['sw']


def test_the_cut_points_are_the_manuals_own() -> None:
	"""PHQ-9's Table 4, p. 6, and GAD-7's stated cut-points, pp. 6–7.

	Asserted by boundary rather than by reading the table back: the table is the thing under test,
	so a test that derives its expectations from it proves only that the table equals itself. These
	are the numbers the manual prints, typed out here from `instructions.txt`.
	"""
	# The ceilings, so 5 opens `mild` rather than closing `none_minimal`. Table 4 prints the bands as
	# intervals — 0–4 None-minimal, 5–9 Mild, 10–14 Moderate, 15–19 Moderately Severe, 20–27 Severe —
	# and the cut-points 5/10/15/20 are where each band starts.
	assert bands_for('phq9') == ((4, 'none_minimal'), (9, 'mild'), (14, 'moderate'),
	                             (19, 'moderately_severe'), (27, 'severe'))
	assert bands_for('gad7') == ((4, 'minimal'), (9, 'mild'), (14, 'moderate'), (21, 'severe'))
	assert GAD7_FURTHER_EVALUATION_AT == 10, 'the manual recommends further evaluation at 10'
	# A cut-point belongs to the band it opens: 10 is moderate, not mild.
	assert band_of('phq9', 4) == 'none_minimal' and band_of('phq9', 5) == 'mild'
	assert band_of('phq9', 9) == 'mild' and band_of('phq9', 10) == 'moderate'
	assert band_of('phq9', 20) == 'severe' and band_of('phq9', 27) == 'severe'
	assert band_of('gad7', 21) == 'severe'


def test_scoring_a_full_scale_phq9() -> None:
	s = _service()
	out = s.screen(_screen('phq9', [3] * 9))
	assert out.total == 27 and out.band == 'severe'
	assert out.items == list(PHQ9_ITEMS['en']) and len(out.items) == 9


def test_an_answer_count_that_does_not_match_the_instrument_is_refused() -> None:
	"""Positional answers are only safe if the length is checked, and this is that check."""
	s = _service()
	with pytest.raises(AssertionError, match='9 items'):
		s.screen(_screen('phq9', [1, 2, 3]))
	with pytest.raises(AssertionError, match='7 items'):
		s.screen(_screen('gad7', [1] * 9))


def test_an_out_of_range_answer_is_refused() -> None:
	s = _service()
	with pytest.raises(AssertionError, match='out of range'):
		s.screen(_screen('phq9', [0, 0, 0, 0, 0, 0, 0, 0, 4]))


# --- Item 9 outranks the band ---------------------------------------------------------------------

def test_a_low_total_with_item_nine_positive_is_not_waved_through() -> None:
	"""The failure this guards: a band alone clears a person at risk.

	A total of 2 is `none_minimal`, whose advice is "nothing here suggests you need treatment". With
	item 9 answered `Several days` the person has said they have had thoughts of being better off
	dead, and the band must not be what they are told.
	"""
	s = _service()
	answers = [0, 0, 0, 0, 0, 0, 0, 0, 1]
	out = s.screen(_screen('phq9', answers))
	assert out.total == 1 and out.band == 'none_minimal'
	assert out.self_harm_item_positive is True
	assert out.advise == SELF_HARM_ADVICE
	assert 'better off dead' not in out.advise  # it does not echo the item back at a distressed person
	assert 'today' in out.advise
	# And the band's own advice is not what was served.
	assert 'Nothing here suggests' not in out.advise


def test_item_nine_at_zero_leaves_the_band_in_charge() -> None:
	s = _service()
	out = s.screen(_screen('phq9', [1, 0, 0, 0, 0, 0, 0, 0, 0]))
	assert out.self_harm_item_positive is False and out.total == 1
	assert 'Nothing here suggests' in out.advise


def test_gad7_carries_no_self_harm_item_and_says_false_rather_than_nothing() -> None:
	"""GAD-7 has no item 9. The flag is False, not absent, so a client need not know which
	instrument carries the item before deciding whether to render a crisis route."""
	s = _service()
	out = s.screen(_screen('gad7', [3] * 7))
	assert out.self_harm_item_positive is False and out.total == 21 and out.band == 'severe'


def test_gad7_reports_further_evaluation_at_its_own_threshold_not_its_band() -> None:
	"""7 is `mild` and below the further-evaluation threshold; 10 is both. The two are different
	numbers and the manual keeps them apart."""
	s = _service()
	below = s.screen(_screen('gad7', [1] * 7))
	assert below.total == 7 and below.band == 'mild' and below.further_evaluation is False
	at = s.screen(_screen('gad7', [1, 1, 1, 2, 2, 2, 1]))
	assert at.total == 10 and at.further_evaluation is True
	assert 'further evaluation' in at.advise
	# PHQ-9 has no such field: its bands are its thresholds, and a second one would be a second rule.
	assert s.screen(_screen('phq9', [1] * 9)).further_evaluation is None


# --- Localisation is real or it is named ----------------------------------------------------------

def test_kiswahili_phq9_is_served_in_kiswahili() -> None:
	s = _service()
	out = s.screen(_screen('phq9', [1] * 9, lang='sw'))
	assert out.lang == 'sw' and out.served_in_english_instead is False
	assert out.items == list(PHQ9_ITEMS['sw']) and out.options == list(RESPONSE_OPTIONS['sw'])
	assert out.timeframe == TIMEFRAME['sw']


def test_gad7_in_kiswahili_serves_english_and_says_so() -> None:
	"""The publisher ships no Kiswahili GAD-7 — the language list has Afrikaans through Urdu and no
	Swahili — so the honest answer is English items plus a statement that they are English. The
	failure mode being refused here is English items labelled `sw`."""
	s = _service()
	out = s.screen(_screen('gad7', [1] * 7, lang='sw'))
	assert out.served_in_english_instead is True
	assert out.lang == 'en', 'the language reported is the one the person was shown'
	assert out.items == list(ITEM_BANKS['gad7']['en'])
	assert 'no sw version' in out.advise
	assert AVAILABLE_LANGS['gad7'] == ('en',), 'GAD-7 has one form and it is English'
	assert AVAILABLE_LANGS['phq9'] == ('en', 'sw')


def test_the_served_items_never_claim_a_language_the_instrument_lacks() -> None:
	"""A sweep over every instrument/language pair, so a third instrument cannot be added with a
	translation claim the bank does not have."""
	s = _service()
	for instrument, langs in AVAILABLE_LANGS.items():
		for lang in ('en', 'sw'):
			out = s.screen(_screen(instrument, [0] * len(ITEM_BANKS[instrument]['en']), lang=lang))
			if lang in langs:
				assert out.served_in_english_instead is False and out.lang == lang
			else:
				assert out.served_in_english_instead is True and out.lang == 'en'


# --- Mood tracking --------------------------------------------------------------------------------

def test_mood_trend_needs_readings_before_it_has_a_direction() -> None:
	"""`too_few` is a named answer, not a flat line. Two readings with the same score are two
	readings, and drawing a steady line over them is a claim nobody made."""
	s = _service()
	assert s.mood_trend('U1').direction == 'too_few'
	for day in (1, 2):
		s.log_mood(MoodEntry(subject_ref='U1', score=5, logged_at_iso=f'2026-10-0{day}T09:00'))
	assert s.mood_trend('U1').direction == 'too_few'
	assert s.mood_trend('U1').entries == 2


def test_mood_trend_reads_the_persons_own_series() -> None:
	s = _service()
	for day, score in ((1, 3), (2, 4), (3, 7)):
		s.log_mood(MoodEntry(subject_ref='U1', score=score, logged_at_iso=f'2026-10-0{day}T09:00'))
	out = s.mood_trend('U1')
	assert out.direction == 'rising' and out.entries == 3 and out.advise
	assert s.mood_trend('SOMEONE-ELSE').entries == 0, 'a series is one person\'s'


def test_a_falling_mood_series_is_named_falling() -> None:
	s = _service()
	for day, score in ((1, 8), (2, 5), (3, 2)):
		s.log_mood(MoodEntry(subject_ref='U1', score=score, logged_at_iso=f'2026-10-0{day}T09:00'))
	assert s.mood_trend('U1').direction == 'falling'
	assert MIN_TREND_ENTRIES == 3


def test_the_mood_log_is_not_the_instrument_scale() -> None:
	"""A mood score is 0–10 and PHQ-9 is 0–27. Averaging them produces a number with neither a
	person's trend nor a validated instrument's cut-points, so the scales stay apart."""
	s = _service()
	with pytest.raises(Exception):
		s.log_mood(MoodEntry(subject_ref='U1', score=11, logged_at_iso='2026-10-12T09:00'))


# --- Coping strategies and psychoeducation --------------------------------------------------------

def test_the_coping_list_is_served_in_both_languages_from_the_source() -> None:
	"""WHO PFA's three action principles — look, listen, link, rendered in the Kiswahili edition as
	Tazama, Sikiliza, Unganisha — are the spine of the list."""
	s = _service()
	for lang in ('en', 'sw'):
		rows = s.coping(lang)
		assert len(rows) == len(COPING_STRATEGIES) == 6
		assert all(r.title and r.body for r in rows)
		assert len({r.slug for r in rows}) == len(rows), 'slugs are what a client routes on'
	en = {r.slug for r in s.coping('en')}
	sw = {r.slug for r in s.coping('sw')}
	assert en == sw, 'the two languages are the same list, not two lists'


def test_the_coping_text_does_not_press_anyone_to_recount_the_event() -> None:
	"""WHO PFA states PFA "is not 'psychological debriefing'" and "is not about pressuring people to
	tell you their feelings". A wellness feature's commonest error is the opposite, so the content
	is checked against the source's own line rather than trusted to have respected it."""
	s = _service()
	no_pressure = next(r for r in s.coping('en') if r.slug == 'no-pressure-to-talk')
	assert 'does not help' in no_pressure.body
	for row in s.coping('en') + s.coping('sw'):
		assert 'debrief' not in row.body.lower(), 'the source rules debriefing out'


def test_the_kiswahili_coping_text_is_kiswahili() -> None:
	s = _service()
	rows = s.coping('sw')
	assert rows[0].title == 'Tulia kwanza'
	assert any('Vuta pumzi' in r.body for r in rows)
	en_titles = {r.title for r in s.coping('en')}
	assert not ({r.title for r in rows} & en_titles), 'the Kiswahili list is not the English one'


def test_an_unknown_language_is_refused_rather_than_served_in_english() -> None:
	"""Unlike a screening, content has no clinical cost to refusing: serving English coping advice
	to a French speaker is not better than saying there is none."""
	s = _service()
	with pytest.raises(AssertionError, match='no content in fr'):
		s.coping('fr')
	with pytest.raises(AssertionError, match='no content in fr'):
		s.outbreak_support('grief', 'fr')


# --- Outbreak-specific: the three §REC-005 names --------------------------------------------------

def test_the_three_outbreak_conditions_are_the_sections_own() -> None:
	assert OUTBREAK_CONDITIONS == ('isolation_distress', 'grief', 'worker_burnout')
	assert {g['slug'] for g in OUTBREAK_SUPPORT} == set(OUTBREAK_CONDITIONS)


def test_each_outbreak_condition_is_served_in_both_languages_with_signs() -> None:
	s = _service()
	for condition in OUTBREAK_CONDITIONS:
		for lang in ('en', 'sw'):
			out = s.outbreak_support(condition, lang)
			assert out.slug == condition and out.title and out.body
			assert out.signs, 'a named condition with nothing to recognise is a label, not support'
			assert not FEATURE_CODE.search(out.title + out.body + ' '.join(out.signs))


def test_an_unknown_outbreak_condition_is_refused() -> None:
	s = _service()
	with pytest.raises(AssertionError, match='unknown outbreak condition'):
		s.outbreak_support('burnout')  # the slug is `worker_burnout`; a near miss must not pass


def test_grief_support_does_not_medicalise_grief() -> None:
	"""The source lists "crying, sadness, depressed mood, grief" among expected distress reactions.
	A self-check that calls grief an illness sends bereaved people to a clinic for being bereaved."""
	out = guidance_for('grief', 'en')
	assert 'not an illness' in out.body
	assert 'Grief has no schedule' in out.body


def test_worker_burnout_speaks_to_the_worker_and_points_them_at_the_lines() -> None:
	out = guidance_for('worker_burnout', 'en')
	assert 'not a lack of commitment' in out.body
	assert 'the same lines you send others to' in out.body


def test_isolation_support_is_clear_that_isolation_is_a_measure_not_a_punishment() -> None:
	out = guidance_for('isolation_distress', 'en')
	assert 'not a punishment' in out.body
	assert 'asking for help does not break it' in out.body


# --- Referral to services -------------------------------------------------------------------------

def test_a_referral_names_services_and_names_the_unverified_ones() -> None:
	"""Every line in `COUNSELLING_LINES` is marked `verified: 'False'`. A referral that presented
	them as reachable would send someone to a number nobody has checked, which is worse than no
	referral because they stop looking."""
	s = _service()
	out = s.refer('U1', 'a positive answer to the self-harm item', 'urgent')
	assert out.referral_id.startswith('MH-')
	assert out.urgency == 'urgent' and out.subject_ref == 'U1'
	assert len(out.services) == 3
	assert len(out.unreachable) == 3, 'all three are unverified, so all three are named'
	assert all('not verified' in u for u in out.unreachable)


def test_a_referral_keeps_the_persons_own_reason() -> None:
	s = _service()
	out = s.refer('U1', 'cannot sleep since the funeral')
	assert 'funeral' in out.reason


def test_a_referral_without_a_reason_is_refused() -> None:
	s = _service()
	with pytest.raises(AssertionError, match='without a reason'):
		s.refer('U1', '')
	with pytest.raises(AssertionError, match='unknown urgency'):
		s.refer('U1', 'grief', 'whenever')


def test_the_referral_request_cannot_supply_the_services_or_the_id() -> None:
	"""The service list and the unreachable list are the app's statements about what it can reach.
	A client that could set them could claim a referral to a service nobody checked."""
	with pytest.raises(Exception):
		ReferralRequest(subject_ref='U1', reason='grief', referral_id='MH-FAKE')  # type: ignore[call-arg]
	with pytest.raises(Exception):
		ReferralRequest(subject_ref='U1', reason='grief', services=[{'name': 'x'}])  # type: ignore[call-arg]
	with pytest.raises(Exception):
		ReferralRequest(subject_ref='U1', reason='grief', unreachable=[])  # type: ignore[call-arg]


# --- The routes -----------------------------------------------------------------------------------

async def test_the_instrument_endpoint_serves_the_item_banks_and_cut_points() -> None:
	c = await _client()
	body = (await c.get('/mental/instruments')).json()
	assert len(body['phq9']['items']) == 9 and len(body['phq9']['sw_items']) == 9
	assert len(body['gad7']['items']) == 7
	assert body['gad7']['langs'] == ['en'] and body['phq9']['langs'] == ['en', 'sw']
	assert body['gad7']['further_evaluation_at'] == 10
	assert body['phq9']['max_total'] == 27 and body['gad7']['max_total'] == 21
	assert body['phq9']['cutpoints'][1] == {'up_to': 9, 'band': 'mild'}


async def test_a_screen_over_http_is_self_scoped() -> None:
	c = await _client()
	h, subject = await _citizen(c)
	ok = await c.post('/mental/screen', headers=h, json={
		'subject_ref': subject, 'instrument': 'phq9', 'answers': [1] * 9,
		'administered_at_iso': '2026-10-12T09:00'})
	assert ok.status_code == 200 and ok.json()['total'] == 9
	# The IDOR the guard exists for: a token filing a screen against somebody else.
	bad = await c.post('/mental/screen', headers=h, json={
		'subject_ref': 'someone-else', 'instrument': 'phq9', 'answers': [1] * 9,
		'administered_at_iso': '2026-10-12T09:00'})
	assert bad.status_code == 403


async def test_a_malformed_screen_is_a_422_and_not_a_500() -> None:
	c = await _client()
	h, subject = await _citizen(c)
	r = await c.post('/mental/screen', headers=h, json={
		'subject_ref': subject, 'instrument': 'phq9', 'answers': [1, 2],
		'administered_at_iso': '2026-10-12T09:00'})
	assert r.status_code == 422 and '9 items' in str(r.json()['detail'])


async def test_a_screen_requires_a_token() -> None:
	c = await _client()
	r = await c.post('/mental/screen', json={
		'subject_ref': 'U1', 'instrument': 'phq9', 'answers': [0] * 9,
		'administered_at_iso': '2026-10-12T09:00'})
	assert r.status_code == 401


async def test_mood_logging_and_the_trend_over_http() -> None:
	c = await _client()
	h, subject = await _citizen(c)
	assert (await c.get('/mental/mood/trend', headers=h,
	                    params={'subject_ref': subject})).json()['direction'] == 'too_few'
	for day, score in ((1, 3), (2, 5), (3, 8)):
		r = await c.post('/mental/mood', headers=h, json={
			'subject_ref': subject, 'score': score, 'logged_at_iso': f'2026-10-0{day}T09:00'})
		assert r.status_code == 200
	trend = (await c.get('/mental/mood/trend', headers=h, params={'subject_ref': subject})).json()
	assert trend['direction'] == 'rising' and trend['entries'] == 3
	# And the trend is the token's own subject.
	assert (await c.get('/mental/mood/trend', headers=h,
	                    params={'subject_ref': 'someone-else'})).status_code == 403


async def test_the_content_routes_are_open_and_serve_both_languages() -> None:
	"""Content is identical for everyone and carries no subject, so it needs no token — the same
	shape as `/mental/lines`."""
	c = await _client()
	coping = await c.get('/mental/coping', params={'lang': 'sw'})
	assert coping.status_code == 200 and len(coping.json()) == 6
	assert coping.json()[0]['title'] == 'Tulia kwanza'
	out = await c.get('/mental/outbreak-support/grief', params={'lang': 'sw'})
	assert out.status_code == 200 and out.json()['slug'] == 'grief'
	assert out.json()['signs']


async def test_the_content_routes_refuse_an_unknown_condition_and_language() -> None:
	c = await _client()
	assert (await c.get('/mental/outbreak-support/nonsense')).status_code == 422
	assert (await c.get('/mental/coping', params={'lang': 'fr'})).status_code == 422


async def test_a_referral_over_http_is_self_scoped_and_returns_the_unreachable_list() -> None:
	c = await _client()
	h, subject = await _citizen(c)
	ok = await c.post('/mental/referral', headers=h, json={
		'subject_ref': subject, 'reason': 'a positive answer to the self-harm item', 'urgency': 'urgent'})
	assert ok.status_code == 200
	body = ok.json()
	assert body['referral_id'].startswith('MH-') and len(body['unreachable']) == 3
	bad = await c.post('/mental/referral', headers=h, json={
		'subject_ref': 'someone-else', 'reason': 'grief'})
	assert bad.status_code == 403


# --- Nothing a person reads carries a feature code -------------------------------------------------

def test_no_served_mental_health_text_carries_a_spec_code() -> None:
	"""The user's own constraint, applied to every string this unit serves."""
	s = _service()
	texts: list[str] = []
	for lang in ('en', 'sw'):
		texts += [r.title + r.body for r in s.coping(lang)]
		texts += [g.title + g.body + ' '.join(g.signs) for g in
		          (s.outbreak_support(c, lang) for c in OUTBREAK_CONDITIONS)]
	texts += [r['name'] + r['number'] for r in s.lines()]
	texts.append(s.screen(_screen('phq9', [0] * 9)).advise)
	texts.append(s.screen(_screen('phq9', [1] * 9)).advise)
	texts.append(s.screen(_screen('phq9', [0, 0, 0, 0, 0, 0, 0, 0, 1])).advise)
	texts.append(s.refer('U1', 'grief').advise)
	for text in texts:
		assert not FEATURE_CODE.search(text), text
