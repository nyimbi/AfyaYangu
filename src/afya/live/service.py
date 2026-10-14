"""§CHAN-000's call-in and §CHAN-004's clinician Q&A, as a service.

The two sections print a live session as a content format and both rows were `missing` for the same
stated reason: "there is no queue, no schedule and no record of a call answered". This module is
those three things, and two decisions in it are what make it more than a table of rows.

**The queue is fed from the channels that already exist.** §CHAN-2's Integration clause puts every
channel's report into one backend, and `ChannelService.record_report` is that backend's single
writer. A message arriving while a session is open is therefore *absorbed* into the queue rather
than filed into a second inbox — which is the mechanism that makes a radio call-in a queue and not
a telephone, and the reason the row closes with a service rather than with a form. The absorb is
idempotent on the report id, because the channel routes walk the whole report sink after every
session: without that a person who texted one question would have it queued again every time they
opened the USSD menu afterwards.

**An answer is judged and the verdicts are carried, not raised on.** §6.2's rules would refuse
ordinary clinical speech — probed live against `judge`: "It is likely a viral infection." fails
§6.2.1 with `no_action`, and "Take paracetamol — 500mg." fails §6.2.6 with `not_forwardable`,
because an em dash is outside GSM-7. A gate that rejected on either would refuse correct medicine
from a clinician answering live, which is the failure mode that gets a gate switched off. So this
follows the codebase's own precedent — `InfoService.content_verdicts` returns rather than raises "so
the drafting screen can show what to fix" — and records the finding on the question so a supervisor
sees it. The rule that must bite still bites: `judge`'s stigmatising check governs any text a person
reads, and "He is an Ebola victim" is a failure whatever else is on the row.

`judge` asserts non-empty text, so `decline` does not call it at all. A declined question has no
answer to judge, and calling the judge with the empty string to "check" it would raise rather than
return — a refusal dressed as a validation.
"""
from collections.abc import Iterable

from afya.info.principles import Finding, Subject, judge
from afya.live.views import (
	LivePlatform, LiveSession, LiveStatus, QuestionStatus, SessionQuestion, SessionTranscript,
	TranscriptEntry,
)
from afya.logmixin import LogMixin


class LiveService(LogMixin):
	def __init__(self) -> None:
		"""No identity model, deliberately: a handle is derived, not looked up.

		The queue names askers by §SEC-004 handle, and `handle_for` reaches `IdentityService.
		derive_handle` as a classmethod because the derivation is a pure function of the subject and
		the window. Holding an `IdentityService` here would be an instance that is never read — and
		the shape that invites a second derivation from it, which is how one asker ends up in the
		queue under two names.
		"""
		self._sessions: dict[str, LiveSession] = {}
		self._questions: dict[str, SessionQuestion] = {}
		# The report ids already in the queue, and they start at *every report the sink holds* rather
		# than empty. The routes that carry a question in walk the whole sink after every session, so
		# a report filed while no programme was on air would otherwise be queued the moment one
		# opened — a question nobody asked in the session it appears in, which is worse than a lost
		# one because it is attributed to a person who has stopped waiting. Marking the sink at
		# construction makes "already seen" mean *seen*, not *seen while live*.
		self._absorbed: set[str] = set()
		assert self._sessions == {} and self._questions == {} and self._absorbed == set()

	def mark_absorbed(self, report_ids: Iterable[str]) -> int:
		"""Record reports as already read, so opening a programme cannot resurrect an old question.

		Called once at wiring time with the ids the sink already holds. Returns how many were newly
		marked, so a caller can log the backlog it skipped rather than inferring it.
		"""
		before = len(self._absorbed)
		self._absorbed.update(report_ids)
		added = len(self._absorbed) - before
		if added:
			self._log_info('live absorb backlog marked', reports=added)
		return added

	# --- the schedule --------------------------------------------------------------------------

	async def schedule(self, session: LiveSession) -> LiveSession:
		"""Put a programme on the schedule. §CHAN-000's and §CHAN-004's absent half.

		Refuses a session that ends before it starts, and refuses a duplicate id: two programmes under
		one id would put two clinicians' queues in one transcript, which is the failure a schedule
		exists to prevent.
		"""
		assert session.session_id not in self._sessions, f'{session.session_id} is already scheduled'
		assert session.ends_at_iso > session.starts_at_iso, (
			f'{session.session_id} ends at {session.ends_at_iso} and starts at {session.starts_at_iso}'
		)
		assert session.status is LiveStatus.scheduled, 'a session is scheduled before it is opened'
		self._sessions[session.session_id] = session
		self._log_info('live session scheduled', session=session.session_id, platform=session.platform.value)
		return session

	def session(self, session_id: str) -> LiveSession:
		assert session_id in self._sessions, f'no live session {session_id}'
		return self._sessions[session_id]

	def sessions(self, platform: LivePlatform | None = None, status: LiveStatus | None = None) -> list[LiveSession]:
		"""The schedule as a caller reads it, filtered the two ways a reader asks."""
		return sorted(
			(s for s in self._sessions.values()
			 if (platform is None or s.platform is platform) and (status is None or s.status is status)),
			key=lambda s: (s.starts_at_iso, s.session_id),
		)

	async def open(self, session_id: str) -> LiveSession:
		"""Start the programme. Only a scheduled session opens; a second open is a no-op-shaped bug.

		This is the instant the queue becomes writable, which is why it is a state change rather than
		a comparison against `starts_at_iso`: the deployment running a programme decides when the
		lines open, and a session whose clock says 10:00 but whose host is not in the studio is not
		one to take questions on.
		"""
		session = self.session(session_id)
		assert session.status is LiveStatus.scheduled, f'{session_id} is {session.status.value}, not scheduled'
		opened = session.model_copy(update={'status': LiveStatus.live})
		self._sessions[session_id] = opened
		self._log_info('live session open', session=session_id, clinician=opened.clinician)
		return opened

	async def close(self, session_id: str) -> LiveSession:
		"""End the programme. A question asked after this is refused rather than queued into nothing."""
		session = self.session(session_id)
		assert session.status is LiveStatus.live, f'{session_id} is {session.status.value}, not live'
		closed = session.model_copy(update={'status': LiveStatus.ended})
		self._sessions[session_id] = closed
		queued = [q for q in self._questions.values()
		          if q.session_id == session_id and q.status is QuestionStatus.queued]
		self._log_info('live session closed', session=session_id, left_unanswered=len(queued))
		return closed

	# --- the queue -----------------------------------------------------------------------------

	@staticmethod
	def handle_for(subject_ref: str, now_ms: int) -> str:
		"""The §SEC-004 handle a queue row carries instead of the person.

		`derive_handle` is a classmethod on `IdentityService` and is reached that way rather than
		through the instance this service may not have: the derivation is a pure function of the
		subject and the window, so a caller with no identity model wired can still name an asker
		without minting one. The two callers that must agree are the route (which holds a token) and
		the channel absorb (which holds only a phone), and a second derivation here would put one
		person's question in the transcript under two names.
		"""
		assert subject_ref, 'a handle is derived from a subject'
		from afya.identity.service import IdentityService
		return IdentityService.derive_handle(subject_ref, now_ms).handle

	async def ask(self, session_id: str, asked_by: str, text: str, at_ms: int, lang: str = 'en',
	              source_report_id: str | None = None) -> SessionQuestion:
		"""Put one question in the queue of an open programme.

		Refuses a question asked when the session is not live. That refusal is the whole difference
		between §CHAN-000's call-in — a programme a person listens to and rings — and a mailbox, and
		it is stated as a refusal rather than as a silent drop because a person who texted a question
		and got nothing back has been told nothing.
		"""
		session = self.session(session_id)
		assert session.status is LiveStatus.live, (
			f'{session_id} is {session.status.value}: §CHAN-000\'s call-in takes questions while the '
			'programme is on air, and a question queued into a session nobody is hosting is answered '
			'by nobody'
		)
		assert text.strip(), 'a question is text'
		assert asked_by, 'a question names the handle that asked it'
		if source_report_id is not None:
			assert source_report_id not in self._absorbed, (
				f'{source_report_id} is already in the queue; the channel routes walk the whole report '
				'sink, so an absorb with no memory queues one question once per later session'
			)
		question = SessionQuestion(
			session_id=session_id, asked_by=asked_by, text=text.strip(), lang=lang,
			asked_at_ms=at_ms, source_report_id=source_report_id,
		)
		self._questions[question.question_id] = question
		if source_report_id is not None:
			self._absorbed.add(source_report_id)
		self._log_info('live question queued', session=session_id, question=question.question_id)
		return question

	def question(self, question_id: str) -> SessionQuestion:
		assert question_id in self._questions, f'no question {question_id}'
		return self._questions[question_id]

	def queue(self, session_id: str, pending_only: bool = False) -> list[SessionQuestion]:
		"""The queue as the clinician running the programme reads it, oldest first.

		Holds the asker's words and their handle, which is why the route over it is guarded: this is
		the one read of a live session that is not publishable, and the handle is what makes it a
		weaker disclosure than a name rather than no disclosure at all.
		"""
		return sorted(
			(q for q in self._questions.values()
			 if q.session_id == session_id and (not pending_only or q.status is QuestionStatus.queued)),
			key=lambda q: (q.asked_at_ms, q.question_id),
		)

	async def answer(self, question_id: str, answer: str, answered_by: str, at_ms: int) -> SessionQuestion:
		"""Answer one queued question, carrying §6.2's verdicts rather than refusing on them.

		The verdicts are recorded on the row so a supervisor sees the sentence that needs a word with
		the clinician. The *only* rule this method enforces is that there is an answer and a person
		behind it — everything else about the sentence is the section's, reported.
		"""
		question = self.question(question_id)
		assert question.status is QuestionStatus.queued, (
			f'{question_id} is {question.status.value}; a question is answered once'
		)
		assert answer.strip(), 'an answer is text'
		assert answered_by, 'an answer names who gave it'
		session = self.session(question.session_id)
		assert session.status is LiveStatus.live, (
			f'{question.session_id} is {session.status.value}; an answer given after the programme '
			'ended is a question answered by nobody'
		)
		finding: Finding = judge(f'live:{question_id}', answer, Subject.answer)
		answered = question.model_copy(update={
			'status': QuestionStatus.answered, 'answer': answer.strip(), 'answered_by': answered_by,
			'answered_at_ms': at_ms,
			'verdicts': [f'{v.rule}: {v.detail}' for v in finding.failures()],
		})
		self._questions[question_id] = answered
		self._log_info('live question answered', question=question_id,
		               principles=len(answered.verdicts))
		return answered

	async def decline(self, question_id: str, reason: str, at_ms: int) -> SessionQuestion:
		"""Decline a question, with the reason recorded.

		`judge` is not called: there is no answer to judge, and the function asserts non-empty text.
		The reason is required rather than optional because a queue row that goes quiet is the one a
		clinician cannot account for later — and §CHAN-000's format is a programme whose record is
		published, so "not taken" has to be a thing the record can say.
		"""
		question = self.question(question_id)
		assert question.status is QuestionStatus.queued, f'{question_id} is {question.status.value}'
		assert reason.strip(), 'a declined question says why it was not taken'
		declined = question.model_copy(update={
			'status': QuestionStatus.declined, 'declined_reason': reason.strip(), 'answered_at_ms': at_ms,
		})
		self._questions[question_id] = declined
		self._log_info('live question declined', question=question_id)
		return declined

	# --- absorbing §5.4's report sink ------------------------------------------------------------

	def open_session_for(self, channel: str) -> LiveSession | None:
		"""The programme currently on air that this channel's messages belong to, or None.

		`channel` is a §5.4 channel name. A radio call-in takes questions from the phone channels —
		USSD, SMS and WhatsApp are what a listener with a feature phone has — and a social live
		session takes them from WhatsApp, which is §CHAN-003's primary product. The mapping is stated
		rather than derived from `platform`, because `radio_callin` and `social_live` are where the
		programme is *broadcast* and the question arrives on a different wire entirely.
		"""
		wanted = LivePlatform.radio_callin if channel in ('ussd', 'sms') else LivePlatform.social_live
		live = [s for s in self._sessions.values()
		        if s.status is LiveStatus.live and s.platform is wanted]
		return sorted(live, key=lambda s: (s.starts_at_iso, s.session_id))[-1] if live else None

	async def absorb_report(self, report: object, at_ms: int) -> SessionQuestion | None:
		"""Put a channel report into the queue of the programme on air, or file nothing.

		The bridge between §5.4's single backend and §CHAN-000's call-in, and the reason the bullet
		closes with a service rather than with a route. A report is absorbed only when a programme is
		live on that channel, and only when the report carries words — a menu-keypress report names a
		symptom and is not a question, and queueing one would fill the clinician's screen with the
		output of a menu.

		The asker is the report's own dedup key, which is the spelling §5.4 already decided for this
		phone, run through the handle derivation: one person who texts twice asks under one handle
		within a window, and a reader of the queue can tell a repeated asker from two people.

		**A report already absorbed returns None rather than raising.** The channel routes walk the
		whole sink on every request, so this is called again for every report on every later message —
		and the idempotency guard inside `ask` is an assert, which would make the second USSD request
		after any report a 500. The short circuit here is what keeps "already seen" a no-op; the
		assert stays where it is, as the guard for a caller reaching `ask` directly with a stale id.
		"""
		channel = getattr(report, 'channel', None)
		session = self.open_session_for(channel) if channel else None
		if session is None:
			return None
		text = getattr(report, 'symptom_label', None)
		if not text:
			return None
		report_id = getattr(report, 'report_id', None)
		if report_id is not None and report_id in self._absorbed:
			return None
		asked_by = self.handle_for(getattr(report, 'dedup_key', ''), at_ms)
		return await self.ask(
			session.session_id, asked_by, text, at_ms=at_ms, lang=getattr(report, 'lang', 'en'),
			source_report_id=report_id,
		)

	# --- the record -----------------------------------------------------------------------------

	def transcript(self, session_id: str) -> SessionTranscript:
		"""§CHAN-000's "record of a call answered", with no person in it.

		Built from `TranscriptEntry` rather than by filtering `SessionQuestion`, so the model itself
		cannot carry a handle into a published document. `questions_asked` counts the queue rather
		than the entries, because the gap between the two is what the record exists to make visible.
		"""
		session = self.session(session_id)
		queue = self.queue(session_id)
		entries = [
			TranscriptEntry(question=q.text, answer=q.answer or '', answered_by=q.answered_by or '',
			                lang=q.lang)
			for q in queue if q.status is QuestionStatus.answered and q.answer
		]
		return SessionTranscript(
			session_id=session.session_id, topic=session.topic, clinician=session.clinician,
			platform=session.platform, lang=session.lang, status=session.status,
			entries=entries, questions_asked=len(queue), questions_answered=len(entries),
		)
