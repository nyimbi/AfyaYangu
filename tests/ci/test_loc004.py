"""§LOC-004's fourth Behaviour bullet, held open.

The section's four Behaviour bullets had three carriers and one gap: the scan is the device's, the
guidance is `LocationService.GUIDANCE`, the check-in is `check_in` — and "Used for attendance
tracking, follow-up scheduling, and exposure window determination" was a sentence about a record
nothing read. The same shape as §COM-103 and §COM-104: every visible part present, the join absent.

Three joins were missing, and they are three because the bullet names three uses:

* **Attendance.** `CheckIn` carries a `point_token`; `CheckInPoint` carries the label, the kind and
  the county. `check_in` joins them once to build a receipt and the receipt is thrown away, so
  "which place was this person at on the 3rd" could not be asked of the stored record at all.
* **Follow-up scheduling.** The 21-day window's ask days exist in the repo — §LOC-005's enrolment
  states `[1, 3, 7, 14, 21]`, §COM-102's peer alert carries `(3, 7, 14, 21)` — and neither was
  reachable from a check-in.
* **Exposure window.** `CheckIn.at_iso` is the timestamp such a derivation would read, and no code
  did arithmetic on it.

So the tests come in three halves plus the refusals. The refusals are the half worth reading: a
person with no check-ins, a check-in at a point that opens no watch, and a window that has closed
all have to say *which* they are, because an empty list and a clean record read identically on a
screen and only one of them is true.
"""
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from afya.location.service import LocationService
from afya.location.views import (
	EXPOSURE_FOLLOWUP_DAYS,
	LOCATION_WINDOW_DAYS,
	WATCH_KINDS,
	CheckIn,
	CheckInPoint,
)
from afya.strings import CHECKIN_STRINGS, checkin

FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')

# 2026-10-01T09:00:00Z as an instant, so the arithmetic in these tests is checkable by hand.
DAY1_MS = 1_790_845_200_000
DAY_MS = 86_400_000


def _point(kind: str, token: str = 'BORDER01', point_id: str = 'P-1',
           label: str = 'Busia border post', county: str = 'Busia') -> CheckInPoint:
	return CheckInPoint(point_id=point_id, kind=kind, label=label, county=county, token=token)


def _checkin(token: str = 'BORDER01', at_iso: str = '2026-10-01T09:00:00Z',
             subject: str = 'U-1', n: int = 1, **kw: Any) -> CheckIn:
	return CheckIn(checkin_id=f'CHK-BORDER{n:02d}', point_token=token, subject_ref=subject,
	               method='qr', at_iso=at_iso, **kw)


async def _svc_with(*points: CheckInPoint, checkins: list[CheckIn] | None = None) -> LocationService:
	svc = LocationService()
	for p in points:
		await svc.register_point(p)
	for c in checkins or []:
		await svc.check_in(c)
	return svc


# --- attendance: the join that was never made -------------------------------------------------

async def test_a_check_in_resolves_to_the_point_it_names() -> None:
	"""The audit row's own gap: `point_token` is stored, `CheckInPoint` is stored, nothing joined
	them. A receipt carries the label once and is not kept, so the stored record could not name the
	place at all."""
	svc = await _svc_with(_point('border_post'), checkins=[_checkin()])
	report = svc.follow_up('U-1', DAY1_MS)
	assert report.attendance is not None and len(report.attendance) == 1
	row = report.attendance[0]
	assert row.point_id == 'P-1' and row.point_label == 'Busia border post'
	assert row.kind == 'border_post' and row.county == 'Busia'
	assert row.checkin_id == 'CHK-BORDER01' and row.day == '2026-10-01'
	assert row.method == 'qr' and row.shared is False


async def test_attendance_is_numbered_per_point_not_globally() -> None:
	"""Three scans at one screening point are one place attended three times. A global counter would
	report three places, which is the reading a county would act on."""
	svc = await _svc_with(
		_point('school', 'SCHOOL01', 'P-S', 'Kisumu Primary'),
		_point('health_facility', 'CLINIC01', 'P-C', 'Kisumu clinic'),
		checkins=[_checkin('SCHOOL01', '2026-10-01T07:00:00Z', n=1),
		          _checkin('CLINIC01', '2026-10-02T07:00:00Z', n=2),
		          _checkin('SCHOOL01', '2026-10-03T07:00:00Z', n=3)],
	)
	report = svc.follow_up('U-1', DAY1_MS)
	assert report.attendance is not None
	assert [r.visit_no for r in report.attendance] == [1, 1, 2], (
		'the second visit to the school is the school\'s second, not the record\'s third')
	assert report.points_attended == 2 and report.checkins == 3


async def test_attendance_is_in_time_order_and_per_subject() -> None:
	"""Two people check in at one gate. The join is per subject, and the order is the record's, not
	the order the calls arrived in — a person's own history read out of order is a different history."""
	svc = await _svc_with(
		_point('border_post'),
		checkins=[_checkin(at_iso='2026-10-05T09:00:00Z', n=2),
		          _checkin(at_iso='2026-10-01T09:00:00Z', n=1),
		          _checkin(at_iso='2026-10-02T09:00:00Z', subject='U-2', n=3)],
	)
	report = svc.follow_up('U-1', DAY1_MS)
	assert report.attendance is not None
	assert [r.day for r in report.attendance] == ['2026-10-01', '2026-10-05']
	assert report.checkins == 2, 'the other person is not this person\'s attendance'


# --- follow-up scheduling ---------------------------------------------------------------------

async def test_the_schedule_falls_on_the_window_days_from_the_check_in() -> None:
	"""The ask days are §MON-009's, counted from the check-in instant — day 1 is the day of the scan,
	the same counting §COM-102's `_alert_day` uses."""
	svc = await _svc_with(_point('border_post'), checkins=[_checkin()])
	report = svc.follow_up('U-1', DAY1_MS)
	assert [s.day for s in report.schedule] == list(EXPOSURE_FOLLOWUP_DAYS)
	assert [s.due_iso for s in report.schedule] == [
		'2026-10-01', '2026-10-03', '2026-10-07', '2026-10-14', '2026-10-21',
	]


async def test_a_step_is_due_on_its_day_and_past_after_it() -> None:
	"""Three-valued, and the three are different facts. A step that is neither due nor past has no
	prompt behind it; reporting it as incomplete would tell a person they had missed something that
	has not happened."""
	svc = await _svc_with(_point('border_post'), checkins=[_checkin()])
	day3 = svc.follow_up('U-1', DAY1_MS + 2 * DAY_MS)
	assert day3.schedule[0].past and not day3.schedule[0].due
	assert day3.schedule[1].due and not day3.schedule[1].past
	assert not day3.schedule[2].due and not day3.schedule[2].past
	assert day3.next_due_iso == '2026-10-03', (
		'the next ask is the first not behind the clock, and today\'s own ask is not behind it')


async def test_every_step_carries_the_question_it_asks() -> None:
	"""A schedule of dates with nothing to say on them is a notification plan, which is the shape
	§LOC-005's third bullet had. The question is the string the person reads."""
	svc = await _svc_with(_point('border_post'), checkins=[_checkin()])
	report = svc.follow_up('U-1', DAY1_MS)
	assert all(s.question for s in report.schedule)
	assert len({s.question for s in report.schedule}) == len(EXPOSURE_FOLLOWUP_DAYS), (
		'each day asks the day, or five steps carry one sentence between them')
	assert 'Day 3 of 21' in report.schedule[1].question


async def test_the_question_is_served_in_the_language_asked_for() -> None:
	"""The follow-up is prose, and prose is where the language has to be honoured. §ACC-002's rule
	is `answerable`: a language with no table is served English and told so, never served a string
	that pretends to be Dholuo."""
	svc = await _svc_with(_point('border_post'), checkins=[_checkin()])
	sw = svc.follow_up('U-1', DAY1_MS, 'sw')
	assert sw.schedule[1].question == checkin('sw', 'prompt', day=3)
	assert sw.schedule[1].question != svc.follow_up('U-1', DAY1_MS, 'en').schedule[1].question
	assert checkin('luo', 'prompt', day=3) == checkin('en', 'prompt', day=3), 'the documented fallback'


async def test_a_language_with_no_table_is_served_english_and_says_so() -> None:
	"""The fallback is not silent. `answerable` accepts every language §ACC-002 lists and serves
	English where there is no table; a caller not told which it got reads English believing it is
	Dholuo, which is the failure the field exists to prevent."""
	svc = await _svc_with(_point('border_post'), checkins=[_checkin()])
	assert svc.follow_up('U-1', DAY1_MS, 'sw').served_in == 'sw'
	luo = svc.follow_up('U-1', DAY1_MS, 'luo')
	assert luo.served_in == 'en' and luo.schedule[0].question.startswith('Day 1 of 21')
	assert svc.follow_up('U-1', DAY1_MS, 'sw').window is not None


def test_an_unknown_checkin_string_is_refused() -> None:
	"""A missing string is a screen that renders blank where a question should be, so it raises at
	the call rather than at the reader."""
	with pytest.raises(AssertionError, match='unknown check-in string'):
		checkin('en', 'not_a_key')


def test_the_swahili_table_covers_every_key_and_keeps_every_placeholder() -> None:
	"""A translated string that dropped a placeholder prints a sentence with a hole in it, and the
	key set is asserted so a new English string cannot ship untranslated."""
	assert set(CHECKIN_STRINGS['sw']) == set(CHECKIN_STRINGS['en'])
	for key, text in CHECKIN_STRINGS['en'].items():
		assert CHECKIN_STRINGS['sw'][key].strip(), f'{key} is empty in sw'
		for field in re.findall(r'\{(\w+)\}', text):
			assert f'{{{field}}}' in CHECKIN_STRINGS['sw'][key], f'{key} lost {{{field}}} in sw'


# --- exposure window --------------------------------------------------------------------------

async def test_the_window_is_21_days_from_the_check_in() -> None:
	"""`CheckIn.at_iso` is the timestamp, and this is the arithmetic on it. Derived and never stored:
	a stored end date is wrong the day after it is written."""
	svc = await _svc_with(_point('border_post'), checkins=[_checkin()])
	window = svc.follow_up('U-1', DAY1_MS).window
	assert window is not None
	assert window.window_days == LOCATION_WINDOW_DAYS == 21
	assert window.opened_iso == '2026-10-01T09:00:00Z'
	assert window.closes_iso == '2026-10-22'
	assert window.elapsed_days == 0 and window.remaining_days == 21 and window.open


async def test_the_window_closes_on_the_22nd() -> None:
	"""Day 21 of a window that opened on the 1st is the 21st; the window is closed from the 22nd.
	The boundary is asserted on both sides because an off-by-one here is a person told to keep
	watching for a day that is not in the window, or told they are clear a day early."""
	svc = await _svc_with(_point('border_post'), checkins=[_checkin()])
	last = svc.follow_up('U-1', DAY1_MS + 20 * DAY_MS).window
	assert last is not None and last.open and last.remaining_days == 1
	after = svc.follow_up('U-1', DAY1_MS + 21 * DAY_MS).window
	assert after is not None and not after.open and after.remaining_days == 0
	assert after.elapsed_days == 21, 'the elapsed count is clamped to the window'


async def test_a_closed_window_is_reported_as_closed_not_dropped() -> None:
	"""A person checking their record eight months on is owed the fact that the watch is over, in
	words. A `window: null` here would be indistinguishable from never having checked in."""
	svc = await _svc_with(_point('border_post'), checkins=[_checkin()])
	late = svc.follow_up('U-1', DAY1_MS + 240 * DAY_MS)
	assert late.window is not None and not late.window.open
	assert late.window.elapsed_days == 21 and late.window.remaining_days == 0
	assert 'ended' in late.window.note and late.window.note != ''
	assert late.attendance, 'the attendance is not lost when the window closes'


async def test_the_latest_watch_opening_check_in_opens_the_window() -> None:
	"""A later scan reopens nothing and a later scan at a gate does move it. Two border crossings are
	two windows, and the one that governs today is the most recent."""
	svc = await _svc_with(
		_point('border_post'),
		checkins=[_checkin(at_iso='2026-10-01T09:00:00Z', n=1),
		          _checkin(at_iso='2026-10-10T09:00:00Z', n=2)],
	)
	window = svc.follow_up('U-1', DAY1_MS + 9 * DAY_MS).window
	assert window is not None and window.opened_iso == '2026-10-10T09:00:00Z'
	assert window.remaining_days == 21


# --- the refusals, which are the half worth reading -------------------------------------------

async def test_a_subject_with_no_check_ins_is_told_so() -> None:
	"""`attendance: null` and a note, not `[]`. An empty list and "nothing is being followed up"
	read identically on a screen, and only one of them is true."""
	svc = await _svc_with(_point('border_post'))
	report = svc.follow_up('U-nobody', DAY1_MS)
	assert report.attendance is None and report.window is None and report.schedule == []
	assert report.checkins == 0 and report.points_attended == 0 and report.next_due_iso is None
	assert report.note == checkin('en', 'no_checkins') and report.note != ''


async def test_a_point_that_opens_no_watch_starts_no_window() -> None:
	"""A workplace check-in logs a visit and starts no 21-day clock: §LOC-004's own guidance for it
	says "logged for follow-up scheduling" and says nothing about symptoms. Deriving a window from
	every check-in would be this code inventing a watch the app never told the person about."""
	svc = await _svc_with(_point('workplace', 'WORK0001', label='Kisumu office'),
	                      checkins=[_checkin('WORK0001')])
	report = svc.follow_up('U-1', DAY1_MS)
	assert report.attendance is not None and len(report.attendance) == 1
	assert report.window is None and report.schedule == []
	assert report.note == checkin('en', 'no_watch'), (
		'a person with a record and no watch is not told nothing is on file')
	assert report.note != checkin('en', 'no_checkins')


async def test_the_kinds_that_open_a_watch_are_the_kinds_whose_guidance_says_so() -> None:
	"""The guard against the silent-watch failure: `WATCH_KINDS` and `GUIDANCE` are one claim, and a
	kind added to one without the other is the app starting a clock nobody was told about."""
	named = {k for k, text in LocationService.GUIDANCE.items() if '21 days' in text}
	assert named == set(WATCH_KINDS), named
	assert 'border_post' in WATCH_KINDS and 'event' in WATCH_KINDS
	assert not ({'school', 'workplace', 'vaccination_point'} & set(WATCH_KINDS)), (
		'guidance for these names no window, so none may open')


async def test_an_unregistered_point_is_refused_rather_than_dropped() -> None:
	"""`check_in` refuses an unknown token, so a stored check-in always resolves. The derivation
	asserts it instead of skipping: a `continue` would drop a visit from the count and report the
	person had attended fewer places than they had."""
	svc = LocationService()
	# The only way this state arises: `check_in` refuses an unknown token, so a registry lost to a
	# restart leaves records that resolve to nothing. It is exactly the state a `continue` hides.
	svc._checkins.append(_checkin())
	with pytest.raises(AssertionError, match='names an unregistered point'):
		svc.follow_up('U-1', DAY1_MS)


async def test_the_derivation_does_not_write() -> None:
	"""A read that mutates is a read whose second call answers differently. The schedule and the
	window are recomputed, never stored, so asking twice is asking the same question."""
	svc = await _svc_with(_point('border_post'), checkins=[_checkin()])
	before = len(svc.checkins_for('U-1'))
	first = svc.follow_up('U-1', DAY1_MS).model_dump(mode='json')
	second = svc.follow_up('U-1', DAY1_MS).model_dump(mode='json')
	assert first == second
	assert len(svc.checkins_for('U-1')) == before


async def test_no_spec_feature_code_reaches_a_served_follow_up() -> None:
	"""The standing constraint: feature ids are traceability handles, never user-facing copy."""
	svc = await _svc_with(_point('border_post'), checkins=[_checkin()])
	blob = repr(svc.follow_up('U-1', DAY1_MS).model_dump(mode='json'))
	assert not FEATURE_CODE.search(blob), blob


# --- the route --------------------------------------------------------------------------------

def _client() -> TestClient:
	from afya.service import build_services, create_app
	return TestClient(create_app(build_services()))


def _citizen(c: TestClient, subject: str) -> dict[str, str]:
	"""A citizen token for `subject`. The follow-up route is `require_self`-guarded, so a read
	without one is a 401 rather than someone else's record."""
	r = c.post('/auth/anonymous', json={'subject_ref': subject})
	assert r.status_code == 200, r.text
	return {'authorization': f'Bearer {r.json()["token"]}'}


def test_the_route_serves_the_three_uses() -> None:
	"""A green unit test says nothing about what the front door serves. The point is registered, the
	check-in posted, and the follow-up read back through the same guards a client goes through."""
	c = _client()
	h = _citizen(c, 'probe-1')
	point = c.post('/location/checkin/point', json={
		'point_id': 'P-ROUTE', 'kind': 'border_post', 'label': 'Busia border post',
		'county': 'Busia', 'token': 'ROUTEP1',
	})
	assert point.status_code == 200, point.text
	checked = c.post('/location/checkin', headers=h, json={
		'checkin_id': 'CHK-ROUTE001', 'point_token': 'ROUTEP1', 'subject_ref': 'probe-1',
		'method': 'qr', 'at_iso': '2026-10-01T09:00:00Z',
	})
	assert checked.status_code == 200, checked.text
	served = c.get('/location/checkin/probe-1/follow-up', headers=h,
	               params={'now_ms': DAY1_MS})
	assert served.status_code == 200, served.text
	body = served.json()
	assert body['attendance'][0]['point_label'] == 'Busia border post'
	assert [s['day'] for s in body['schedule']] == list(EXPOSURE_FOLLOWUP_DAYS)
	assert body['window']['closes_iso'] == '2026-10-22'
	assert body['window']['elapsed_days'] == 0 and body['window']['remaining_days'] == 21, (
		'the window is arithmetic against the clock the caller sent, not the wall clock')
	assert body['served_in'] == 'en', 'the language the answer was built in travels with it'
	assert not FEATURE_CODE.search(served.text), served.text


def test_the_route_is_self_scoped() -> None:
	"""A check-in is where one person was on one day — the most identifying row this module holds.
	Naming someone else is refused rather than served."""
	h = _citizen(c := _client(), 'probe-1')
	r = c.get('/location/checkin/probe-2/follow-up', headers=h)
	assert r.status_code == 403, r.text


def test_the_route_refuses_a_caller_with_no_token() -> None:
	r = _client().get('/location/checkin/probe-1/follow-up')
	assert r.status_code in (401, 403), r.text


def test_the_audit_row_is_carried_and_its_ref_resolves() -> None:
	"""The row this unit closes. `afya.refs.resolves` walks dotted attributes, so a ref that does not
	import fails here rather than in an audit run."""
	from afya.content_audit.service import FEATURE_CONTENT
	from afya.refs import resolves

	rows = [r for r in FEATURE_CONTENT if r[0] == 'LOC-004']
	assert not [r for r in rows if r[3] == 'missing'], rows
	row = [r for r in rows if r[2].startswith('Used for')][0]
	assert row[3] == 'carried' and resolves(row[4]), row
