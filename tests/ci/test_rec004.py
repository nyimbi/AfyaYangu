"""§REC-004 — a cycle tracker whose every date was wrong, and four Features that were absent.

The section prints six Features. Two were implemented and four were not, and the two that were had
three defects that made the output unusable:

- **Every date was wrong.** `predict` computed the next period with `int(month) * 30 + int(day)` — a
  30-day month for every month — so a 28-day cycle starting 2026-01-20 predicted 2026-02-20 where
  the calendar says 2026-02-17. Both branches were wrong; the "fast" branch (`day_ <= 28`) was wrong
  because it never carried the month at all.
- **The anchor was the last *logged* period, not the latest.** `logs[-1]` on an unsorted list means a
  person who backfills a missed earlier period moves their own anchor backwards. January–March
  entries plus a backfilled December log produced a next-period date in January, for a person
  standing in March.
- **`fertile_window_days` was declared and set to `None` on every path.** The window existed only
  inside the `advise` prose, so no client could read it as a value — a field that is a promise the
  code did not keep.

Each gate below is canaried against a planted defect in `canary_rec004.py`: a check that has never
been watched to fail is a check nobody has read.
"""
import httpx
import pytest

from afya.service import build_services, create_app
from afya.women import content
from afya.women.service import WomenService, _add_days, _days_between, _months_between
from afya.women.views import ContraceptionRequest, CycleLog


def _svc(*starts: str, subject: str = 's') -> WomenService:
	"""A service with `starts` logged in the order given — the order a person actually logs in."""
	svc = WomenService()
	for start in starts:
		svc._logs.setdefault(subject, []).append(CycleLog(subject_ref=subject, start_iso=start))
	return svc


async def _token(c: httpx.AsyncClient, subject: str = 's') -> dict[str, str]:
	"""A citizen token for `subject`, minted the way every other test in the tree mints one."""
	tok = (await c.post('/auth/anonymous', json={'subject_ref': subject})).json()['token']
	return {'Authorization': f'Bearer {tok}'}


# --- the date arithmetic, which was wrong on every path -------------------------------------------

def test_a_predicted_date_is_the_date_the_calendar_gives() -> None:
	"""The defect: `int(month) * 30 + int(day)` treats every month as 30 days, so a 28-day cycle from
	2026-01-20 gave 2026-02-20 instead of 2026-02-17. Three days out is a date a person plans around."""
	assert _add_days('2026-01-20', 28) == '2026-02-17'
	assert _add_days('2026-01-25', 30) == '2026-02-24'
	assert _add_days('2026-01-31', 28) == '2026-02-28', 'January has 31 days'
	assert _add_days('2026-03-15', 30) == '2026-04-14'
	assert _add_days('2026-02-28', 1) == '2026-03-01', '2026 is not a leap year'
	assert _add_days('2024-02-28', 1) == '2024-02-29', '2024 is a leap year'
	assert _add_days('2026-12-20', 20) == '2027-01-09', 'across a year boundary'


def test_a_cycle_span_is_measured_on_the_calendar_not_in_thirty_day_months() -> None:
	"""The same defect on the input side: the span between two logs was computed with the same 30-day
	month, so a real 31-day cycle (Jan 1 to Feb 1) was read as 30 and every `md` was compressed."""
	assert _days_between('2026-01-01', '2026-02-01') == 31
	assert _days_between('2026-01-08', '2026-02-05') == 28
	assert _days_between('2026-02-05', '2026-01-08') == -28, 'signed, so an out-of-order pair is visible'
	assert _months_between('2026-01-15', '2027-01-15') == 12
	assert _months_between('2026-01-15', '2027-01-14') == 11, 'a day short of the month is not the month'
	assert _months_between('2026-01-15', '2026-01-14') == -1


def test_the_prediction_is_anchored_to_the_latest_period_not_the_last_one_logged() -> None:
	"""The defect: `logs[-1]` on an unsorted list. Backfilling a missed earlier period — the ordinary
	way a tracker is used — moved the anchor backwards and the prediction followed it, producing a
	next-period date in the past for a person standing today."""
	svc = _svc('2026-01-05', '2026-02-02', '2026-03-02', '2025-12-08')
	out = svc.predict('s', '2026-03-10')
	assert out.next_period_iso == '2026-03-30', out.next_period_iso
	assert out.next_period_iso > '2026-03-10', 'a next period in the past is not a next period'


# --- §REC-004's fertility awareness --------------------------------------------------------------

def test_the_fertile_window_is_a_value_with_dates_and_a_pair_of_cycle_days() -> None:
	"""The defect: `fertile_window_days` was declared and set to `None` on every path, so the window
	existed only inside the `advise` string and no client could read it as a value. A field that is
	always `None` is a promise the code does not keep."""
	out = _svc('2026-01-08', '2026-02-05', '2026-03-05').predict('s', '2026-03-10')
	assert out.fertile_window_days == (7, 15), out.fertile_window_days
	assert out.next_period_iso == '2026-04-02'
	assert out.ovulation_iso == '2026-03-19', 'ovulation is 14 days before the next period'
	assert out.fertile_from_iso == '2026-03-12', 'the window opens 7 days earlier: sperm survival'
	assert out.fertile_to_iso == '2026-03-20'
	assert out.fertility_note, 'a window with no caveat reads as a schedule'


def test_the_window_says_it_is_an_estimate_and_not_a_contraceptive_method() -> None:
	"""The source states that fertility-awareness methods are "less reliable" than the others. A
	tracker that presented its own window as a green light would be causing the pregnancy it exists
	to help avoid, so the note travels with the window."""
	out = _svc('2026-01-08', '2026-02-05', '2026-03-05').predict('s', '2026-03-10')
	assert 'less reliable' in out.fertility_note
	assert 'not a contraceptive method' in out.fertility_note
	assert '10 to 16 days' in out.fertility_note, 'the source spread the estimate moves within'


def test_an_overdue_prediction_says_so_rather_than_naming_a_date_in_the_past() -> None:
	"""`ref_date` was an unused parameter. Its job is the one thing the anchor cannot say: a person
	who has not logged for three months gets a confident date in the past."""
	out = _svc('2026-01-05', '2026-02-02', '2026-03-02').predict('s', '2026-06-01')
	assert out.next_period_iso == '2026-03-30', 'the anchor is still the last logged period'
	assert 'ago' in out.advise and '2026-03-30' in out.advise
	assert 'pregnant' in out.advise, 'an overdue period is the one case where that is worth naming'


# --- §REC-004's contraception reminders -----------------------------------------------------------

def test_the_methods_are_whos_groups_with_no_invented_percentage() -> None:
	"""WHO groups methods into "highly effective and long-lasting", "works well when taken correctly"
	and "less reliable", and states no efficacy figure for any of them. A percentage invented here
	would read as one WHO publishes."""
	groups = {row['reliability'] for row in content.CONTRACEPTIVE_METHODS}
	assert groups == {content.Reliability.HIGHLY_EFFECTIVE, content.Reliability.WHEN_TAKEN_CORRECTLY,
	                  content.Reliability.LESS_RELIABLE}
	assert all('%' not in str(row) for row in content.CONTRACEPTIVE_METHODS)
	condoms = content.METHODS_BY_SLUG['condom']
	assert condoms['prevents_sti'] is True
	assert content.METHODS_BY_SLUG['implant']['prevents_sti'] is False
	assert content.METHODS_BY_SLUG['fertility_awareness']['reliability'] == content.Reliability.LESS_RELIABLE


def test_a_recorded_method_takes_its_reliability_from_who_not_from_the_caller() -> None:
	"""A client that could label withdrawal "highly effective" would be writing WHO's own grouping."""
	plan = _svc().set_contraception(ContraceptionRequest(
		subject_ref='s', method='withdrawal', started_iso='2026-03-01'))
	assert plan.label == 'Withdrawal'
	assert plan.reliability == content.Reliability.LESS_RELIABLE
	assert plan.prevents_sti is False
	assert content.FERTILITY_AWARENESS_NOTE in plan.notes


def test_a_repeating_method_gets_a_due_date_and_a_long_acting_one_does_not() -> None:
	"""A reminder for an implant would be a reminder to do something that is not done on a schedule."""
	pill = _svc().set_contraception(ContraceptionRequest(
		subject_ref='s', method='pill', started_iso='2026-03-01', repeat_days=28))
	assert pill.next_due_iso == '2026-03-29'
	assert pill.repeat_days == 28
	implant = _svc().set_contraception(ContraceptionRequest(subject_ref='s', method='implant', started_iso='2026-03-01'))
	assert implant.next_due_iso is None and implant.repeat_days is None
	with pytest.raises(AssertionError, match='repeating schedule'):
		_svc().set_contraception(ContraceptionRequest(
			subject_ref='s', method='iud', started_iso='2026-03-01', repeat_days=30))
	with pytest.raises(AssertionError, match='unknown contraceptive method'):
		_svc().set_contraception(ContraceptionRequest(subject_ref='s', method='herbal', started_iso='2026-03-01'))


def test_a_non_sti_method_says_it_does_not_protect_against_stis() -> None:
	"""The fact sheet draws exactly one distinction between methods: condoms are the only ones that
	prevent both pregnancy and STI transmission including HIV. A method's own note has to say so."""
	pill = _svc().set_contraception(ContraceptionRequest(
		subject_ref='s', method='pill', started_iso='2026-03-01'))
	assert any('HIV' in note for note in pill.notes)
	assert content.NO_INFERTILITY_NOTE in pill.notes, 'the misconception the source names outright'


def test_the_reminder_is_the_methods_that_are_due_by_the_day_asked_about() -> None:
	svc = _svc()
	svc.set_contraception(ContraceptionRequest(
		subject_ref='s', method='pill', started_iso='2026-03-01', repeat_days=28))
	assert svc.contraception_due('s', '2026-03-28') == [], 'not due yet'
	due = svc.contraception_due('s', '2026-03-29')
	assert len(due) == 1 and due[0].next_due_iso == '2026-03-29'
	assert svc.contraception_due('other', '2026-06-01') == [], 'another subject has none'


# --- §REC-004's menopause support -----------------------------------------------------------------

def test_the_twelve_month_rule_is_whos_and_it_comes_from_the_persons_own_logs() -> None:
	"""The fact sheet: "Pregnancy is still possible during perimenopause. Contraception is
	recommended to avoid unintended pregnancy until after 12 consecutive months without
	menstruation." Twelve months is the whole state machine, and it counts from the person's last
	logged period — never from their age, which the source gives as a population figure ("most
	women", 45–55) and not a test to apply to one."""
	svc = _svc('2026-01-05', '2026-02-02', '2026-03-02')
	early = svc.menopause('s', '2026-08-02')
	assert early.state == 'perimenopausal'
	assert early.months_since_last_period == 5
	assert early.contraception_still_recommended is True
	assert 'still possible' in early.advise
	after = svc.menopause('s', '2027-03-02')
	assert after.state == 'postmenopausal' and after.months_since_last_period == 12
	assert after.contraception_still_recommended is False, 'the twelve months have passed'
	assert after.months_required == content.PERIMENOPAUSE_MONTHS == 12
	# One day short of the twelfth month is still perimenopausal — the rule is the month, not the day.
	assert svc.menopause('s', '2027-03-01').state == 'perimenopausal'


def test_the_menopause_output_carries_the_sources_own_symptoms_and_no_verdict_on_age() -> None:
	"""The symptoms are the fact sheet's list verbatim; the advice is its own sentence, because the
	source states no threshold at which a symptom needs review."""
	svc = _svc('2026-01-05', '2026-02-02', '2026-03-02')
	out = svc.menopause('s', '2026-08-02')
	slugs = {row['slug'] for row in out.symptoms}
	assert {'hot_flushes', 'vaginal_dryness', 'sleep', 'mood', 'bone_density'} <= slugs
	assert 'health-care provider' in out.advise
	assert '45' not in out.advise, 'the age range is a population figure, not a verdict on a person'
	empty = WomenService().menopause('nobody', '2026-08-02')
	assert empty.state == 'insufficient_data' and empty.contraception_still_recommended is True


# --- §REC-004's referral to services --------------------------------------------------------------

def test_a_referral_names_services_and_the_numbers_nobody_verified() -> None:
	"""A referral to a service that does not exist is worse than none, because the person stops
	looking — the same reasoning §REC-005's `refer` is built on. The counselling rows come from
	`mental.COUNSELLING_LINES`, the table §INF-006's directory also reads, so a number cannot drift
	between the two screens that show it."""
	from afya.mental.views import COUNSELLING_LINES
	out = _svc().refer('s', 'Irregular cycles')
	assert out.reason == 'Irregular cycles'
	slugs = {row['slug'] for row in out.services}
	assert {'family_planning', 'antenatal', 'counselling'} <= slugs
	assert len(out.unreachable) == len([r for r in COUNSELLING_LINES if r.get('verified') != 'True'])
	assert all('not verified' in u for u in out.unreachable)
	with pytest.raises(AssertionError, match='reason'):
		_svc().refer('s', '')


def test_a_referral_to_services_does_not_carry_a_spec_code() -> None:
	"""The codes are backend identifiers. A person reads `services`, not `§REC-004`."""
	import json
	out = _svc().refer('s', 'Irregular cycles')
	blob = json.dumps(out.model_dump(mode='json'))
	assert 'REC-004' not in blob and '§' not in blob


# --- the wire -------------------------------------------------------------------------------------

async def test_the_routes_serve_the_window_the_reminder_and_the_state() -> None:
	"""End to end through the real app: the Features are wired in `create_app` and a test that
	constructed its own service would not notice a route going missing."""
	app = create_app(build_services())
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		head = await _token(c, 's')
		for start in ('2026-01-08', '2026-02-05', '2026-03-05'):
			posted = await c.post('/women/cycle', json={'subject_ref': 's', 'start_iso': start},
			                      headers=head)
			assert posted.status_code == 200, posted.text
		pred = await c.get('/women/cycle/s/predict?ref_date=2026-03-10', headers=head)
		assert pred.status_code == 200, pred.text
		body = pred.json()
		assert body['fertile_window_days'] == [7, 15]
		assert body['fertile_from_iso'] == '2026-03-12'
		methods = await c.get('/women/contraception/methods', headers=head)
		assert len(methods.json()['methods']) == len(content.CONTRACEPTIVE_METHODS)
		plan = await c.post('/women/contraception', headers=head, json={
			'subject_ref': 's', 'method': 'pill',
			'started_iso': '2026-03-01', 'repeat_days': 28})
		assert plan.status_code == 200, plan.text
		assert plan.json()['next_due_iso'] == '2026-03-29'
		due = await c.get('/women/contraception/s/due?on_iso=2026-03-30', headers=head)
		assert len(due.json()['due']) == 1
		meno = await c.get('/women/menopause/s?today_iso=2026-08-05', headers=head)
		assert meno.json()['state'] == 'perimenopausal'
		ref = await c.post('/women/referral', headers=head, json={'reason': 'Irregular cycles'})
		assert ref.status_code == 200 and ref.json()['services']


async def test_another_persons_cycle_is_refused() -> None:
	"""§17.6 and the IDOR rule: the subject named in the path must be the token's own. A tracker of
	someone's periods read by whoever asks is the worst version of this module's failure."""
	app = create_app(build_services())
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		refused = await c.get('/women/cycle/someone-else/predict?ref_date=2026-03-10',
		                      headers=await _token(c, 's'))
		assert refused.status_code == 403, refused.text
