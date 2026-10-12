"""§TRI-002's five Features, four of which the diary did not have.

`diary_append` stored an entry and `diary` returned the list, so "log symptoms" worked and the
other four — the daily prompt, the escalation, the trend view and the export — were absent. The
section is a follow-up tool; without them the module is a log, which is the half of it that needs
no product decisions.

The escalation test is the one worth reading: §TRI-002 says "automatic escalation if *new* red flags
are logged", and a version that escalated on any entry carrying a flag would re-fire every day until
the person stopped reading it.
"""
import httpx

from afya.registry.service import FeatureRegistry
from afya.triage.service import TriageService
from afya.triage.views import DiaryEntry, RiskLevel, TrendDirection

SUBJECT = 'U1'


def _svc() -> TriageService:
	return TriageService(FeatureRegistry())


def _entry(day: int, symptoms: list[str], temp: float, red_flags: list[str] | None = None) -> DiaryEntry:
	return DiaryEntry(entry_id=f'DIARY-DAY{day:02d}ABC123', subject_ref=SUBJECT, day=day,
		symptoms=symptoms, temperature_c=temp, red_flags=red_flags or [])


async def _seed(svc: TriageService, entries: list[DiaryEntry]) -> None:
	for e in entries:
		await svc.diary_append(e)


async def test_the_trend_reads_the_entries_rather_than_asking() -> None:
	"""§TRI-002's "trend view: is this getting better or worse?" — a self-report of "worse" and a
	diary showing a rising temperature are two different facts, and the section wants the second."""
	svc = _svc()
	await _seed(svc, [_entry(1, ['fever'], 38.2), _entry(2, ['fever'], 38.9), _entry(3, ['fever'], 39.4)])
	trend = svc.diary_trend(SUBJECT)
	assert trend.direction is TrendDirection.worsening
	assert any('temperature' in c for c in trend.changed), 'what moved is named, not just the verdict'
	assert trend.days_logged == 3

	svc = _svc()
	await _seed(svc, [_entry(1, ['fever', 'headache'], 39.0), _entry(2, ['fever'], 38.0)])
	trend = svc.diary_trend(SUBJECT)
	assert trend.direction is TrendDirection.improving
	assert any('gone' in c for c in trend.changed)


async def test_one_entry_has_no_trend_and_says_so() -> None:
	"""`unknown` is a member because a first entry has no trend, and "no change yet" is a different
	answer from "stable over four days" — a two-member enum forces the first entry to claim one."""
	svc = _svc()
	assert svc.diary_trend(SUBJECT).direction is TrendDirection.unknown
	await _seed(svc, [_entry(1, ['fever'], 38.2)])
	trend = svc.diary_trend(SUBJECT)
	assert trend.direction is TrendDirection.unknown and trend.days_logged == 1
	assert 'at least two days' in trend.note


async def test_escalation_fires_once_on_a_new_red_flag() -> None:
	"""§TRI-002: "automatic escalation if *new* red flags are logged". A flag already escalated on
	day 2 must not escalate again on day 4, or the person gets the same ambulance message daily."""
	svc = _svc()
	await _seed(svc, [_entry(1, ['fever'], 38.0), _entry(2, ['fever'], 38.2, ['convulsions'])])
	first = svc.diary_escalation(SUBJECT)
	assert first is not None and first.risk_level is RiskLevel.emergency
	# The same flag repeated on a later entry is not new, so the second call is silent.
	await _seed(svc, [_entry(3, ['fever'], 38.1, ['convulsions'])])
	assert svc.diary_escalation(SUBJECT) is None, 'a repeated flag is not a new one'
	# A different flag is new.
	await _seed(svc, [_entry(4, ['fever'], 38.1, ['convulsions', 'inability_to_drink'])])
	assert svc.diary_escalation(SUBJECT) is not None


async def test_nothing_to_escalate_returns_nothing_not_a_low_risk_result() -> None:
	"""A client that renders the return value would show a triage answer where the section asks for
	silence, so `None` is the answer and it is the only honest one."""
	svc = _svc()
	assert svc.diary_escalation(SUBJECT) is None
	await _seed(svc, [_entry(1, ['fever'], 38.0)])
	assert svc.diary_escalation(SUBJECT) is None, 'a fever with no red flag is not an escalation'


async def test_the_export_is_text_a_clinician_can_read() -> None:
	"""§TRI-002's "exportable summary for a clinician". What the section asks for is an export the
	person hands over; a clinician reading JSON is not the use case."""
	svc = _svc()
	await _seed(svc, [_entry(1, ['fever', 'headache'], 38.2), _entry(2, ['fever'], 39.0, ['confusion'])])
	export = svc.diary_export(SUBJECT)
	assert export.days_logged == 2
	assert 'day 1' in export.text and '38.2' in export.text and 'headache' in export.text
	assert 'red flags: confusion' in export.text
	assert 'worsening' in export.text
	assert export.entries == svc.diary(SUBJECT), 'the entries stay available for the app\'s own view'


async def test_the_prompt_needs_the_opt_in_the_feature_names() -> None:
	"""§TRI-002 writes the opt-in into the Feature — "daily 'how are you feeling?' prompt (opt-in)" —
	so a declined prompt is not a prompt. Returning one with a flag would put it on the screen of
	someone who said no, in any client that renders what it is handed."""
	svc = _svc()
	assert svc.diary_prompt(SUBJECT, day=1, opted_in=False) is None
	prompt = svc.diary_prompt(SUBJECT, day=1, opted_in=True)
	assert prompt is not None and prompt.due, 'nothing logged today, so it is due'
	assert 'feeling' in prompt.question
	await _seed(svc, [_entry(1, ['fever'], 38.2)])
	today = svc.diary_prompt(SUBJECT, day=1, opted_in=True)
	tomorrow = svc.diary_prompt(SUBJECT, day=2, opted_in=True)
	assert today is not None and tomorrow is not None
	assert not today.due, 'answered today'
	assert tomorrow.due, 'day 2 is unanswered'


async def test_the_routes_serve_all_four_diary_features() -> None:
	"""The routes are where the absence was: `/triage/diary` accepted an entry and
	`/triage/{ref}/diary` returned the list, so a client had the log and none of the four features.

	The subject is taken from the token rather than written into the URL, because the four routes
	are `require_self`-guarded: a citizen may act only on their own diary, and a test that typed a
	subject in would be testing a route the guard refuses.
	"""
	from afya.service import build_services, create_app
	services = build_services()
	app = create_app(services)
	svc: TriageService = services['triage']  # type: ignore[assignment]
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		token = (await c.post('/auth/anonymous', json={})).json()
		auth = {'Authorization': f'Bearer {token["token"]}'}
		subject = str(token['subject_ref'])
		for e in (_entry(1, ['fever'], 38.2), _entry(2, ['fever'], 38.9, ['convulsions'])):
			e.subject_ref = subject
			await svc.diary_append(e)
		trend = (await c.get(f'/triage/{subject}/diary/trend', headers=auth)).json()
		assert trend['direction'] == 'worsening' and trend['days_logged'] == 2
		export = (await c.get(f'/triage/{subject}/diary/export', headers=auth)).json()
		assert 'day 1' in export['text']
		escalation = (await c.get(f'/triage/{subject}/diary/escalation', headers=auth)).json()
		assert escalation['risk_level'] == 'emergency'
		# No opt-in is a null body, not a prompt with a flag.
		assert (await c.get(f'/triage/{subject}/diary/prompt?day=3', headers=auth)).json() is None
		prompt = (await c.get(f'/triage/{subject}/diary/prompt?day=3&opted_in=true', headers=auth)).json()
		assert prompt['due'] is True
		# Another subject's diary is not reachable with this token.
		assert (await c.get('/triage/someone-else/diary/trend', headers=auth)).status_code == 403
