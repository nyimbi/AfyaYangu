"""§CHAN-000's call-in and §CHAN-004's clinician Q&A, as the queue and the record.

Both rows were `missing` for the same stated reason — "there is no queue, no schedule and no record
of a call answered" — and every test here asserts one of those three as a *behaviour*: a question
that arrives becomes a queue row, a question that arrives with nobody on air is refused rather than
filed into nothing, and an answered question reaches a published transcript with no person in it.

Two of the tests are about the failures that would make the feature worse than absent. The absorb
is idempotent because the channel routes walk the whole report sink on every request, so a person
who texted once would otherwise have their question queued again every time they opened the USSD
menu afterwards — a queue that grows with traffic rather than with questions. And `answer()` judges
the answer without refusing on it, because §6.2 would reject ordinary clinical speech; the test
that matters is the one where the answer stigmatises, which is the sentence a supervisor has to see.
"""
import asyncio

from afya.channels.service import ChannelService
from afya.identity.service import IdentityService
from afya.live.service import LiveService
from afya.live.views import LivePlatform, LiveSession, LiveStatus, QuestionStatus
from afya.privacy.views import RBACRole
from afya.registry.service import FeatureRegistry
from afya.triage.service import TriageService

MSISDN = '+254711222333'
SUBJECT = 'U1'
OTHER = 'U2'
OPEN = '2026-10-14T10:00:00Z'
CLOSE = '2026-10-14T11:00:00Z'
NOW = 1_760_000_000_000


class _NoSms:
	"""A port that does not send: these tests are about the queue, not about delivery."""

	async def send(self, msg: object) -> str:
		return 'at:queued'


def _session(session_id: str = 'LS-1', platform: LivePlatform = LivePlatform.radio_callin) -> LiveSession:
	return LiveSession(session_id=session_id, platform=platform, topic='Fever in an outbreak',
	                   clinician='Dr Achieng', starts_at_iso=OPEN, ends_at_iso=CLOSE)


def _channels(live: LiveService, identity: IdentityService) -> ChannelService:
	svc = ChannelService(_NoSms(), None, TriageService(FeatureRegistry()), identity, None, None)
	svc.attach_live(live)
	return svc


def test_a_question_asked_before_the_programme_opens_is_refused_not_filed() -> None:
	"""§CHAN-000's format is a programme on air, not a mailbox.

	A question queued into a session nobody is hosting is answered by nobody, and a person who sent
	it has been told nothing — which is why this is a refusal with a reason rather than a drop.
	"""
	async def run() -> None:
		live = LiveService()
		await live.schedule(_session())
		try:
			await live.ask('LS-1', 'fever-1234', 'Is a headache a sign?', at_ms=NOW)
		except AssertionError as exc:
			assert 'scheduled' in str(exc), str(exc)
			return
		raise AssertionError('a question was queued into a session that had not opened')
	asyncio.run(run())


def test_an_answer_given_after_the_programme_ends_is_refused() -> None:
	"""The other end of the same rule, and the one a clinician working late would hit."""
	async def run() -> None:
		live = LiveService()
		await live.schedule(_session())
		await live.open('LS-1')
		q = await live.ask('LS-1', 'fever-1234', 'Is a headache a sign?', at_ms=NOW)
		await live.close('LS-1')
		try:
			await live.answer(q.question_id, 'Drink water and rest.', 'Dr Achieng', NOW)
		except AssertionError as exc:
			assert 'ended' in str(exc), str(exc)
			return
		raise AssertionError('a question was answered after the programme ended')
	asyncio.run(run())


def test_a_question_asked_twice_is_answered_once() -> None:
	"""A question is answered once; a second answer is a second clinician over the first."""
	async def run() -> None:
		live = LiveService()
		await live.schedule(_session())
		await live.open('LS-1')
		q = await live.ask('LS-1', 'fever-1234', 'Is a headache a sign?', at_ms=NOW)
		await live.answer(q.question_id, 'Drink water and rest.', 'Dr Achieng', NOW)
		try:
			await live.answer(q.question_id, 'Take paracetamol.', 'Dr Otieno', NOW)
		except AssertionError as exc:
			assert 'answered' in str(exc), str(exc)
			return
		raise AssertionError('one question took two answers')
	asyncio.run(run())


def test_a_stigmatising_answer_is_recorded_with_its_verdict_rather_than_refused() -> None:
	"""The one §6.2 rule that must bite, carried on the row instead of raised at the clinician.

	An ordinary clinical answer is *not* refused — "it is likely a viral infection" names no action,
	and a gate that rejected on that would refuse correct medicine from a doctor answering live. The
	stigmatising sentence is the case a supervisor has to see, so it is the case asserted here.
	"""
	async def run() -> None:
		live = LiveService()
		await live.schedule(_session())
		await live.open('LS-1')
		ordinary = await live.ask('LS-1', 'fever-1234', 'Is a headache a sign?', at_ms=NOW)
		answered = await live.answer(ordinary.question_id, 'It is likely a viral infection.', 'Dr Achieng', NOW)
		assert answered.status is QuestionStatus.answered
		assert answered.answer == 'It is likely a viral infection.'
		bad = await live.ask('LS-1', 'fever-5678', 'What does it mean?', at_ms=NOW + 1)
		flagged = await live.answer(bad.question_id, 'He is an Ebola victim.', 'Dr Achieng', NOW + 2)
		assert flagged.status is QuestionStatus.answered, 'the answer is recorded, not refused'
		assert flagged.verdicts, 'a stigmatising answer carries its verdicts to the supervisor'
		assert any('stigmatis' in v or 'stigma' in v for v in flagged.verdicts), flagged.verdicts
	asyncio.run(run())


def test_a_declined_question_carries_a_reason_and_is_not_judged() -> None:
	"""`judge` asserts non-empty text, so the declined path must not call it at all.

	A declined question has no answer to judge; calling the judge with the empty string to "check"
	it would raise rather than return, which is a refusal dressed as a validation.
	"""
	async def run() -> None:
		live = LiveService()
		await live.schedule(_session())
		await live.open('LS-1')
		q = await live.ask('LS-1', 'fever-1234', 'Can you diagnose me?', at_ms=NOW)
		declined = await live.decline(q.question_id, 'needs a consultation, not a broadcast', NOW)
		assert declined.status is QuestionStatus.declined
		assert declined.declined_reason == 'needs a consultation, not a broadcast'
		assert declined.verdicts == [], 'there is no answer to have a verdict'
	asyncio.run(run())


def test_the_transcript_names_no_person_and_counts_what_was_not_answered() -> None:
	"""The record §CHAN-000's note says is absent, and the two properties that make it publishable.

	The entries are built from `TranscriptEntry`, which has no field for a handle — so a person
	reading the published record cannot learn who asked. `questions_asked` counts the queue rather
	than the entries, because a transcript showing only what was answered reads as a programme where
	every question was taken, which is a claim nobody made.
	"""
	async def run() -> None:
		live = LiveService()
		await live.schedule(_session())
		await live.open('LS-1')
		taken = await live.ask('LS-1', 'fever-1234', 'Is a headache a sign?', at_ms=NOW)
		await live.answer(taken.question_id, 'Drink water and rest.', 'Dr Achieng', NOW)
		await live.ask('LS-1', 'fever-5678', 'What about a rash?', at_ms=NOW + 1)
		await live.close('LS-1')
		record = live.transcript('LS-1')
		assert record.questions_asked == 2
		assert record.questions_answered == 1
		assert len(record.entries) == 1
		assert record.entries[0].answer == 'Drink water and rest.'
		body = record.model_dump(mode='json')
		assert 'fever-1234' not in str(body), 'the transcript must not carry the asker handle'
		assert 'asked_by' not in str(body), 'a transcript entry has no field for who asked'
	asyncio.run(run())


def test_a_burst_of_questions_gets_a_burst_of_distinct_ids() -> None:
	"""The defect a queue invites: two questions asked in the same breath must be two questions.

	A UUID7's leading bits are a millisecond timestamp, so an id built from a truncation of one is
	constant across a 256 ms window — and a clinician working down a queue asks for one question
	after another. The first version of this module used `uuid7str()[:10]` and the second question
	silently replaced the first in the store, which is a queue that answers one person and drops the
	next. `afya.ids` documents the failure; this is the assertion that it has not come back.
	"""
	async def run() -> None:
		live = LiveService()
		await live.schedule(_session())
		await live.open('LS-1')
		ids = [(await live.ask('LS-1', f'asker-{i}', f'Question {i}?', at_ms=NOW)).question_id
		       for i in range(200)]
		assert len(set(ids)) == 200, f'{200 - len(set(ids))} of 200 questions shared an id'
		assert len(live.queue('LS-1')) == 200
	asyncio.run(run())


def test_a_handle_is_derived_from_the_subject_and_is_not_the_subject() -> None:
	"""§SEC-004's rotating handle is the identifier a queue row carries, and it is not the person."""
	handle = LiveService.handle_for(SUBJECT, NOW)
	assert handle != SUBJECT
	assert SUBJECT not in handle
	# Derived, not stored: the same subject and window give the same handle, so the route and the
	# channel absorb cannot put one person in the queue under two names.
	assert LiveService.handle_for(SUBJECT, NOW) == handle
	assert LiveService.handle_for(OTHER, NOW) != handle


def test_a_report_becomes_a_queued_question_while_a_programme_is_on_air() -> None:
	"""§CHAN-2's Integration clause: the channel's one backend feeds the queue, so a radio call-in
	is a queue and not a telephone."""
	async def run() -> None:
		identity = IdentityService()
		live = LiveService()
		channels = _channels(live, identity)
		await live.schedule(_session())
		await live.open('LS-1')
		report = channels.record_report(MSISDN, 'ussd', ['fever'], symptom_label='Is a headache a sign?')
		question_id = await channels.absorb_into_live(report)
		assert question_id is not None, 'a report filed while the programme is on air must be queued'
		queue = live.queue('LS-1')
		assert len(queue) == 1
		assert queue[0].text == 'Is a headache a sign?'
		assert queue[0].asked_by == LiveService.handle_for(report.dedup_key, queue[0].asked_at_ms)
		assert queue[0].asked_by != report.msisdn, 'the queue carries a handle, never the phone'
	asyncio.run(run())


def test_the_absorb_is_idempotent_on_the_report_id() -> None:
	"""The failure the idempotency exists for: the routes walk the whole sink on every request.

	Without the guard, a person who texted one question has it queued again each time they open the
	USSD menu afterwards — a queue that grows with traffic rather than with questions.
	"""
	async def run() -> None:
		identity = IdentityService()
		live = LiveService()
		channels = _channels(live, identity)
		await live.schedule(_session())
		await live.open('LS-1')
		report = channels.record_report(MSISDN, 'ussd', ['fever'], symptom_label='Is a headache a sign?')
		first = await channels.absorb_into_live(report)
		second = await channels.absorb_into_live(report)
		assert first is not None
		assert second is None, 'the same report was queued twice'
		assert len(live.queue('LS-1')) == 1
	asyncio.run(run())


def test_a_report_filed_before_any_programme_is_never_resurrected_into_one() -> None:
	"""The backlog mark, and why it is taken at wiring time rather than when a session opens.

	A report filed while no programme was on air is a message about a fever, not a question asked of
	a clinician. Queueing it the moment a session opens attributes it to a person who has stopped
	waiting — worse than losing it, because it looks answered.
	"""
	async def run() -> None:
		identity = IdentityService()
		live = LiveService()
		channels = _channels(live, identity)
		old = channels.record_report(MSISDN, 'ussd', ['fever'], symptom_label='Fever since Tuesday')
		live.mark_absorbed([old.report_id])
		await live.schedule(_session())
		await live.open('LS-1')
		assert await channels.absorb_into_live(old) is None
		assert live.queue('LS-1') == []
	asyncio.run(run())


def test_a_menu_report_with_no_words_is_not_a_question() -> None:
	"""A keypress names a symptom; it is not something a clinician can answer."""
	async def run() -> None:
		identity = IdentityService()
		live = LiveService()
		channels = _channels(live, identity)
		await live.schedule(_session())
		await live.open('LS-1')
		report = channels.record_report(MSISDN, 'ussd', ['fever'])
		assert await channels.absorb_into_live(report) is None
		assert live.queue('LS-1') == []
	asyncio.run(run())


def test_a_report_with_no_programme_on_air_files_nothing() -> None:
	"""The ordinary case: most reports arrive with no call-in running, and that is not an error."""
	async def run() -> None:
		identity = IdentityService()
		live = LiveService()
		channels = _channels(live, identity)
		await live.schedule(_session())
		report = channels.record_report(MSISDN, 'ussd', ['fever'], symptom_label='Is a headache a sign?')
		assert await channels.absorb_into_live(report) is None
	asyncio.run(run())


def test_the_queue_is_attached_once() -> None:
	"""Two live services reading one sink queue every question twice, and the clinician answers the
	one nobody is looking at."""
	async def run() -> None:
		channels = _channels(LiveService(), IdentityService())
		try:
			channels.attach_live(LiveService())
		except AssertionError as exc:
			assert 'once' in str(exc), str(exc)
			return
		raise AssertionError('the call-in queue was attached twice')
	asyncio.run(run())


def test_the_social_platform_takes_whatsapp_and_the_radio_one_takes_the_phone() -> None:
	"""§CHAN-000 is Community Radio and §CHAN-004 is Social Media; the question arrives on a
	different wire from the one the programme is broadcast on."""
	async def run() -> None:
		live = LiveService()
		await live.schedule(_session('LS-RADIO', LivePlatform.radio_callin))
		await live.schedule(_session('LS-SOCIAL', LivePlatform.social_live))
		await live.open('LS-RADIO')
		await live.open('LS-SOCIAL')
		assert live.open_session_for('ussd').session_id == 'LS-RADIO'  # type: ignore[union-attr]
		assert live.open_session_for('sms').session_id == 'LS-RADIO'  # type: ignore[union-attr]
		assert live.open_session_for('whatsapp').session_id == 'LS-SOCIAL'  # type: ignore[union-attr]
	asyncio.run(run())


def test_a_session_that_ends_before_it_starts_is_refused() -> None:
	"""Two programmes under one id, or one that ends before it begins, are both schedules nobody can
	read — and a schedule is half of what the audit row said was absent."""
	async def run() -> None:
		live = LiveService()
		backwards = LiveSession(session_id='LS-X', platform=LivePlatform.radio_callin, topic='t',
		                        clinician='Dr Achieng', starts_at_iso=CLOSE, ends_at_iso=OPEN)
		try:
			await live.schedule(backwards)
		except AssertionError as exc:
			assert 'ends at' in str(exc), str(exc)
			return
		raise AssertionError('a session ending before it starts was scheduled')
	asyncio.run(run())


def test_a_second_programme_under_one_id_is_refused() -> None:
	"""Two clinicians' queues in one transcript, which is the failure a schedule exists to prevent."""
	async def run() -> None:
		live = LiveService()
		await live.schedule(_session())
		try:
			await live.schedule(_session())
		except AssertionError as exc:
			assert 'already scheduled' in str(exc), str(exc)
			return
		raise AssertionError('two sessions shared one id')
	asyncio.run(run())


def test_the_session_list_filters_the_two_ways_a_listener_asks() -> None:
	async def run() -> None:
		live = LiveService()
		await live.schedule(_session('LS-RADIO', LivePlatform.radio_callin))
		await live.schedule(_session('LS-SOCIAL', LivePlatform.social_live))
		assert [s.session_id for s in live.sessions(LivePlatform.radio_callin)] == ['LS-RADIO']
		assert len(live.sessions()) == 2
		await live.open('LS-RADIO')
		assert [s.session_id for s in live.sessions(status=LiveStatus.live)] == ['LS-RADIO']
		assert [s.session_id for s in live.sessions(status=LiveStatus.scheduled)] == ['LS-SOCIAL']
	asyncio.run(run())


def test_the_front_door_serves_the_schedule_the_ask_and_the_transcript() -> None:
	"""The routes exist and are reachable. A service with no route is a capability nobody can use.

	Both tokens are obtained through the app's own flows — a citizen by `/auth/anonymous` and a
	clinician by the PKCE exchange — because a token minted directly would not prove the route's
	guard admits the role the deployment actually has.
	"""
	import asyncio as _asyncio

	import httpx

	from afya.auth.views import s256
	from afya.service import build_services, create_app

	async def _worker(c: httpx.AsyncClient, role: str) -> dict[str, str]:
		"""A worker token through the app's own PKCE exchange, so the guard sees a real role."""
		verifier = 'v' * 64
		authz = (await c.post('/auth/pkce/authorize', json={
			'client_id': 'app', 'redirect_uri': 'afya://cb', 'code_challenge': s256(verifier),
			'state': 'state-1234'})).json()
		tok = (await c.post('/auth/pkce/token', params={'role': role}, json={
			'authorization_code': authz['authorization_code'], 'client_id': 'app',
			'redirect_uri': 'afya://cb', 'code_verifier': verifier})).json()
		return {'Authorization': f'Bearer {tok["access_token"]}'}

	async def run() -> None:
		svc = build_services()
		app = create_app(svc)
		# `sysadmin` is not issuable through the app flow — it is provisioned through
		# `/auth/staff/provision`, which itself needs an `infrastructure` token, so the first one is
		# bootstrapped from the service the way every other test that needs an operator does.
		admin = {'Authorization': 'Bearer ' + svc['auth'].provision_staff(  # type: ignore[union-attr]
			'live-ops', RBACRole.sysadmin, registrar='MoH ops').access_token}
		transport = httpx.ASGITransport(app=app)
		async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
			anon = (await c.post('/auth/anonymous', json={'subject_ref': SUBJECT})).json()
			citizen = {'Authorization': f'Bearer {anon["token"]}'}
			# One worker role, and §CHAN-000's own wording is why: the call-in is with a *health
			# worker*, and §17.4 gives that role `assigned`. §CHAN-004's clinician is named on the
			# session rather than holding a token — `clinician` in the table is scoped
			# `consented_patient`, which is a read of another person's record through a share.
			worker = await _worker(c, 'chw')

			created = await c.post('/live/sessions', json=_session().model_dump(mode='json'),
			                       headers=admin)
			assert created.status_code == 200, created.text
			opened = await c.post('/live/sessions/LS-1/open', headers=worker)
			assert opened.status_code == 200, opened.text
			assert (await c.get('/live/sessions')).json()['count'] == 1
			asked = await c.post('/live/sessions/LS-1/questions',
			                     json={'text': 'Is a headache a sign?', 'lang': 'en'}, headers=citizen)
			assert asked.status_code == 200, asked.text
			assert 'asked_by' not in asked.text, 'the response must not hand back the handle'
			queue = await c.get('/live/sessions/LS-1/queue', headers=worker)
			assert queue.status_code == 200, queue.text
			assert queue.json()['count'] == 1
			question_id = asked.json()['question_id']
			answered = await c.post(f'/live/questions/{question_id}/answer',
			                        json={'answer': 'Drink water and rest.'}, headers=worker)
			assert answered.status_code == 200, answered.text
			transcript = await c.get('/live/sessions/LS-1/transcript')
			assert transcript.status_code == 200, transcript.text
			body = transcript.json()
			assert body['questions_asked'] == 1 and body['questions_answered'] == 1
			assert 'asked_by' not in transcript.text, 'the published record names no person'
	_asyncio.run(run())


def test_a_citizen_may_not_read_the_queue() -> None:
	"""The refusal that makes the queue's guard mean something: it holds what people said."""
	import asyncio as _asyncio

	import httpx

	from afya.service import build_services, create_app

	async def run() -> None:
		app = create_app(build_services())
		transport = httpx.ASGITransport(app=app)
		async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
			anon = (await c.post('/auth/anonymous', json={'subject_ref': SUBJECT})).json()
			citizen = {'Authorization': f'Bearer {anon["token"]}'}
			refused = await c.get('/live/sessions/LS-1/queue', headers=citizen)
			assert refused.status_code == 403, refused.text
	_asyncio.run(run())
