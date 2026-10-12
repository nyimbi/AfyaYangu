"""Community services (spec §10.4 COM-005, §11.4 COM-101..104).

COM-101 case reports are server-authoritative (§16.3) and mirror AVADAR: submission fires an
automatic alert to the disease surveillance officer, and the report moves through
reported -> investigated -> lab_result -> closed.
"""
from afya.auth.views import now_ms
from afya.community.protocol import PROTOCOL, ResponseClock, coverage, response_clock
from afya.community.views import (
	ALERT_WINDOW_DAYS, FOLLOWUP_DAYS, ISSUE_ROUTING, CaseReport, CaseReportView, CaseStatus,
	ClaimAnswer, CommunityIssue, ContactEntry, ContactList, ContactTracingSummary, IssueReceipt,
	IssueStatus, MisinfoCluster, MisinfoSubmission, PeerAlert, PeerAlertAck, PeerAlertGuidance,
	PeerAlertReceipt,
)
from afya.identity.service import IdentityService
from afya.info.myths import (
	DRAFTED_ON_ISO, FALLBACK_CORRECTION, FALLBACK_TOPIC, classify, correction_library, myth_for,
)
from afya.info.principles import Subject, judge
from afya.logmixin import LogMixin
from afya.strings import answerable

# Misinformation topics with a pre-drafted, source-attributed correction (§6.4 response protocol).
#
# Derived from `afya.info.myths` rather than written here. The corrections were a table of their own
# until §INF-004 was built, and the myth library held the same facts again as prose — two authors,
# one subject, and nothing keeping them in step. The corpus now carries the claim, the correction and
# the named authority as three fields, `correction_text` renders the sentence §6.4 publishes, and this
# is that rendering. The correction the protocol publishes and the correction the library shows are
# therefore the same string by construction.
#
# Every correction carries both languages. §6.4's step 4 says the correction is drafted "in all
# relevant languages" and §6.2.4 forbids publishing English-only for a life-safety message, so an
# English-only correction is one the audience §3.3 principle 8 puts first cannot read. `coverage()`
# reports any that go missing.
#
# The attributions are separated by a hyphen and not an em dash. §6.4 step 5 publishes "all channels
# simultaneously", and SMS is one of the channels §6.2.6 names — a character outside GSM-7 cannot be
# sent as a plain SMS. `afya.info.myths` holds the corpus to the character set and
# `tests/ci/test_misinfo_protocol.py` holds this rendering of it shut.
CORRECTION_LIBRARY: dict[str, dict[str, str]] = correction_library()

# The clock starts when a rumour is first seen. A submission carries no timestamp of its own — the
# flagger is a member of the public and their phone's clock is not evidence — so detection is the
# server's receipt of the first report for that topic. Held per service instance rather than at
# module scope: two services in one process are two deployments, and a shared detection time would
# make one deployment's response look started by another's first report.
SPIKING_THRESHOLD = 25
RISING_THRESHOLD = 8

# Contact-tracing prompt categories (§COM-103: guided, humane, not a cold form)
TRACING_PROMPTS: tuple[str, ...] = (
	'Who did you share a home with during the exposure window?',
	'Who did you sit or work beside?',
	'Which matatus, buses or boda rides did you take, and with whom?',
	'Where did you worship, and who was near you?',
	'Who did you meet at the market or shops?',
	'Any funeral, wedding or gathering you attended?',
)

# §COM-102's "receive follow-up guidance" — what an acknowledgement returns. The four things a
# person inside an alert zone is told to do, in the order that resolves a concern fastest. The
# section's Tone clause is "calm, factual, actionable" and this is the actionable half: an alert
# that only said "monitor for symptoms" leaves a person watching and waiting with nothing to do.
ALERT_GUIDANCE: tuple[str, ...] = (
	'Watch yourself for fever, headache, muscle pain, vomiting or unusual bleeding for 21 days from the day the alert was issued.',
	'Wash your hands with soap and running water, and keep them away from your face.',
	'If a fever or any of those symptoms starts, call 719 and say you were in an alert zone. Do not go to a clinic unannounced.',
	'Do not touch anyone who is sick, and do not wash or touch a body if someone dies. Call 719 for a safe burial team.',
)


def _alert_day(alert: PeerAlert, acknowledged_iso: str) -> int:
	"""Which day of §COM-102's window an acknowledgement falls on, clamped into it.

	Derived from the alert's own issue date rather than from the acknowledgement alone: the window
	starts when the alert was issued, not when the person happened to read it, so someone who opens
	the app on day 5 is on day 5. Clamped to `[1, ALERT_WINDOW_DAYS]` rather than refused — an
	acknowledgement that arrives late is still an acknowledgement, and a 422 would lose the fact that
	the person answered at all.
	"""
	from datetime import date
	def _parse(text: str) -> date:
		return date.fromisoformat(text[:10])
	issued = _parse(alert.issued_iso)
	seen = _parse(acknowledged_iso)
	day = (seen - issued).days + 1
	return max(1, min(ALERT_WINDOW_DAYS, day))


class CommunityService(LogMixin):
	def __init__(self, identity: IdentityService | None = None) -> None:
		"""`identity` is §5.4's single identity model, injected rather than constructed here because the
		index it holds is shared with the channel layer — two instances would resolve the same phone to
		two subjects and the deduplication would find nothing. Optional only so a unit test can build
		the community service alone; `_dedup_key` refuses rather than falling back to the raw number,
		because a key built on the MSISDN alone silently fails to match a report the same person filed
		from the app, which is the cross-channel case §5.4 is about.
		"""
		self._issues: dict[str, CommunityIssue] = {}
		self._issue_status: dict[str, IssueStatus] = {}
		self._cases: dict[str, CaseReport] = {}
		self._case_status: dict[str, CaseStatus] = {}
		self._peer_alerts: list[PeerAlert] = []
		# (alert_id, subject_ref) -> the acknowledgement. Keyed by the pair so a person who taps the
		# button twice is one acknowledgement, which is what §COM-102's receipt counts.
		self._peer_acks: dict[tuple[str, str], PeerAlertAck] = {}
		self._contacts: dict[str, ContactList] = {}
		self._misinfo: list[MisinfoSubmission] = []
		self._detected: dict[str, int] = {}
		self._identity = identity
		# dedup key -> the report already open under it. §5.4 says reports are deduplicated, and the
		# key is the resolved subject rather than the raw number so a USSD report and an app report
		# by the same person collide.
		self._open_by_reporter: dict[str, str] = {}
		assert self._issues == {} and self._cases == {} and self._open_by_reporter == {}

	def _dedup_key(self, report: CaseReport) -> str | None:
		"""§5.4's dedup key for a report, or None when the report carries no phone.

		None is not "no duplicate": it means the report cannot be deduplicated, and the two are
		reported differently. A CHW logging offline has no MSISDN and never will, so treating the
		absence as a match would merge every offline report into one case.

		The key is the phone number in its one spelling, which is what §5.4 says the dedup is by. It
		goes through the identity model rather than being used raw, because the model is where the
		spelling is decided — a report filed from `0712345678` and the same case filed from
		`+254712345678` must collide, and only the shared normalisation makes them.
		"""
		if report.reporter_msisdn is None:
			return None
		if self._identity is None:
			raise RuntimeError('the community service has no identity model wired; §5.4 requires the shared one')
		return self._identity.dedup_key(report.reporter_msisdn)

	# --- COM-005 community reporting ------------------------------------------------------

	async def report_issue(self, issue: CommunityIssue) -> IssueReceipt:
		self._issues[issue.issue_id] = issue
		self._issue_status[issue.issue_id] = IssueStatus.routed
		routed_to = ISSUE_ROUTING[issue.kind]
		self._log_info('community issue routed', kind=issue.kind.value, to=routed_to)
		return IssueReceipt(
			issue_id=issue.issue_id, routed_to=routed_to, status=IssueStatus.routed,
			message=f'Sent to {routed_to}. You will be told when it is resolved.',
		)

	def issue_status(self, issue_id: str) -> IssueStatus:
		assert issue_id in self._issues, 'unknown issue'
		return self._issue_status[issue_id]

	async def resolve_issue(self, issue_id: str) -> IssueStatus:
		assert issue_id in self._issues, 'unknown issue'
		self._issue_status[issue_id] = IssueStatus.resolved
		self._log_info('community issue resolved', issue_id=issue_id)
		return IssueStatus.resolved

	def issues_by_county(self, county: str) -> list[dict[str, object]]:
		return [
			{'issue_id': i.issue_id, 'kind': i.kind.value, 'status': self._issue_status[i.issue_id].value, 'description': i.description}
			for i in self._issues.values() if i.county == county
		]

	# --- COM-101 CHW case reporting -------------------------------------------------------

	async def submit_case(self, report: CaseReport) -> CaseReportView:
		"""§5.4's "single case-report backend — deduplicated by phone number", performed.

		The dedup is over *open* cases, keyed on the identity model's resolved subject. A closed case
		is a completed episode and a second report from the same person after it is a new one, not a
		duplicate — the same reasoning that makes a re-infection a new case rather than an amendment.

		The duplicate is still stored. Dropping it would lose the channel it arrived on, which is what
		§5.4's cross-channel journeys are made of (WhatsApp → USSD → CHW is one person reporting twice
		on purpose), and it would make a person who reported twice unable to see that the second one
		landed. What the dedup changes is the *alert*: the officer is told once per open case, because
		an alert per duplicate is how a surveillance queue fills with the same patient.
		"""
		assert report.symptoms, 'symptom checklist required'
		if report.photo_sha256 is not None:
			assert report.geotagged, 'photo evidence requires geotag consent (§COM-101)'
		officer = f'{report.county} disease surveillance officer'
		key = self._dedup_key(report)
		existing = self._open_by_reporter.get(key) if key is not None else None
		if existing is not None and self._case_status[existing] is not CaseStatus.closed:
			self._cases[report.report_id] = report
			self._case_status[report.report_id] = CaseStatus.reported
			self._log_info('case report deduplicated onto an open case', report=report.report_id, open_case=existing)
			return CaseReportView(
				report_id=report.report_id, status=CaseStatus.reported, surveillance_officer=officer,
				alerts_sent=0, deduplicated=True,
				next_step=f'Already reported — this is the same case as {existing}. The officer was alerted once; no second alert was sent.',
			)
		self._cases[report.report_id] = report
		self._case_status[report.report_id] = CaseStatus.reported
		if key is not None:
			self._open_by_reporter[key] = report.report_id
		self._log_warn('case report submitted', report=report.report_id, disease=report.suspected_disease, county=report.county,
		               deduplicable=key is not None)
		# AVADAR lesson: alerting is automatic, never a second manual step.
		return CaseReportView(
			report_id=report.report_id, status=CaseStatus.reported, surveillance_officer=officer,
			alerts_sent=1,
			next_step='Officer alerted automatically. Keep the patient isolated; log PPE use; await investigation instructions.',
		)

	async def advance_case(self, report_id: str, status: CaseStatus) -> CaseStatus:
		assert report_id in self._cases, 'unknown case report'
		order = [CaseStatus.reported, CaseStatus.investigated, CaseStatus.lab_result, CaseStatus.closed]
		current = self._case_status[report_id]
		assert order.index(status) >= order.index(current), 'case status moves forward only'
		self._case_status[report_id] = status
		self._log_info('case advanced', report=report_id, status=status.value)
		return status

	def case_status(self, report_id: str) -> CaseStatus:
		assert report_id in self._cases, 'unknown case report'
		return self._case_status[report_id]

	def ppe_reminder(self) -> str:
		return 'PPE: gloves, gown, face shield and mask before any contact. Remove in order: gloves, gown, shield, mask — then wash hands.'

	# --- COM-102 peer alert network -------------------------------------------------------

	async def send_peer_alert(self, alert: PeerAlert) -> PeerAlertReceipt:
		assert alert.verified_by in ('County', 'PHEOC', 'MoH'), 'peer alerts require county verification (§COM-102)'
		# §6.2.5 and §6.2.9, through the one table that holds them. The peer alert carried its own
		# four-word alarmist list, which missed the stigmatising substitutions the section states and
		# would not have moved if the section did. It is instruction text — a peer alert tells someone
		# what to do — so the directive rule applies and the stigma rule does not: the sentence names
		# the reader, not a group.
		#
		# The judged string is `alert.body`, which is *derived* from `ALERT_TEMPLATE` and the location.
		# That is the point of the template: the section's own sentence is the calm one it says it
		# tested with community representatives, so a body that failed this judge would be a body the
		# template could not have produced. The judge still runs, because the location is free text
		# and a place name can carry a stigma ("the Somali quarter") even when the sentence around it
		# is the section's.
		finding = judge(f'peer_alert:{alert.alert_id}', f'{alert.headline} {alert.body}', Subject.content)
		failures = [v.detail for v in finding.failures()]
		assert not failures, f'peer alert tone rejected: {failures}'
		self._peer_alerts.append(alert)
		# Recipients are counted by the geofence fan-out; this service records the verified alert.
		# The figure below is a *modelling assumption*, not a sourced number: 4,000 people per km²
		# is a dense informal-settlement figure, and §COM-102 states no density. It is a receipt
		# field a CHW reads as an order of magnitude, and it is named here so nobody cites it as
		# census data.
		recipients = int(3.14159 * (alert.radius_m / 1000.0) ** 2 * 4000)
		self._log_warn('peer alert verified and dispatched', county=alert.county, radius_m=alert.radius_m)
		return PeerAlertReceipt(
			alert_id=alert.alert_id, recipients=recipients, verification=f'verified by {alert.verified_by}',
			tone_check='calm, factual, actionable — no case identifiers present',
			body=alert.body, followup_days=list(alert.followup_days),
		)

	def peer_alerts(self, county: str) -> list[PeerAlert]:
		return [a for a in self._peer_alerts if a.county == county]

	def alert(self, alert_id: str) -> PeerAlert:
		"""One alert by id. `assert` rather than a `None` return: an alert id a client holds and the
		server does not is a bug on one side, and a caller that has to handle `None` will render an
		empty screen instead of reporting it."""
		for a in self._peer_alerts:
			if a.alert_id == alert_id:
				return a
		raise AssertionError(f'unknown alert: {alert_id}')

	def followup_prompt(self, alert_id: str, day: int) -> str | None:
		"""§COM-102's fourth bullet: "Follow-up prompts on days 3, 7, 14, and 21".

		`None` on a day that is not one of the four, and `None` past the window. A prompt on every
		day would be the daily nag the section avoids by naming four; a prompt on day 22 would be a
		prompt about a window that has closed.

		The day is a parameter rather than read from a clock: the scheduler that calls this is the
		deployment's, and a service that read `date.today()` would make every test that exercises
		day 21 depend on when it ran.
		"""
		assert day >= 0, 'day must not be negative'
		self.alert(alert_id)
		if day not in FOLLOWUP_DAYS:
			return None
		# Day 21 is the last prompt, so there is nothing after it — and saying "we will check on you
		# on day 22" is a promise the section does not make.
		return (
			f'Day {day} of {ALERT_WINDOW_DAYS}. Are you well? Call 719 straight away if you have a '
			f'fever, a headache, muscle pain, vomiting or unusual bleeding.'
		)

	async def acknowledge_peer_alert(self, ack: PeerAlertAck) -> PeerAlertGuidance:
		"""§COM-102's third bullet, both halves: the acknowledgement, and the guidance it returns.

		The acknowledgement is recorded per person per alert, so acknowledging twice does not count
		twice — §COM-102's receipt reports how many people answered, and a person who taps the button
		twice is one person. The day is derived from when the alert was issued rather than sent by the
		client, because a client's clock decides which follow-up prompt the person reads, and a phone
		with a wrong clock would read them the day-21 prompt on day 1.
		"""
		alert = self.alert(ack.alert_id)
		assert ack.subject_ref, 'an acknowledgement names the person who read the alert'
		key = (ack.alert_id, ack.subject_ref)
		self._peer_acks[key] = ack
		day = _alert_day(alert, ack.acknowledged_iso)
		guidance = list(ALERT_GUIDANCE)
		if ack.concerned:
			# The section's Tone clause is "calm, factual, actionable", so a person who says they
			# are worried is given the one action that resolves it rather than reassurance.
			guidance.append('You said you are worried. Call 719 — it is staffed, and they will tell you what to do.')
		upcoming = [d for d in FOLLOWUP_DAYS if d > day]
		self._log_info('peer alert acknowledged', alert=ack.alert_id, day=day)
		return PeerAlertGuidance(
			alert_id=ack.alert_id, subject_ref=ack.subject_ref, day=day, guidance=guidance,
			next_followup_day=upcoming[0] if upcoming else None,
			message=f'Thank you. You are on day {day} of {ALERT_WINDOW_DAYS}.',
		)

	def acknowledged_count(self, alert_id: str) -> int:
		"""How many distinct people answered this alert. The receipt's `acknowledged` field."""
		self.alert(alert_id)
		return len({s for (a, s) in self._peer_acks if a == alert_id})

	# --- COM-103 contact tracing assistance ----------------------------------------------

	def tracing_prompts(self) -> list[str]:
		return list(TRACING_PROMPTS)

	async def save_contacts(self, contacts: ContactList) -> ContactTracingSummary:
		self._contacts[contacts.subject_ref] = contacts
		return self.summary(contacts.subject_ref)

	def add_contact(self, subject_ref: str, entry: ContactEntry) -> ContactTracingSummary:
		bucket = self._contacts.setdefault(subject_ref, ContactList(subject_ref=subject_ref))
		bucket.entries.append(entry)
		return self.summary(subject_ref)

	def summary(self, subject_ref: str) -> ContactTracingSummary:
		bucket = self._contacts.get(subject_ref, ContactList(subject_ref=subject_ref))
		by_setting: dict[str, int] = {}
		for e in bucket.entries:
			by_setting[e.setting] = by_setting.get(e.setting, 0) + 1
		total = len(bucket.entries)
		progress = min(100.0, round(100.0 * len(by_setting) / len(TRACING_PROMPTS), 1))
		return ContactTracingSummary(
			subject_ref=subject_ref, by_setting=by_setting, total=total, shared=bucket.share_consent,
			progress_pct=progress,
			message=(
				'Thank you — this is hard, and it protects people you care about. '
				+ ('Shared with the health team.' if bucket.share_consent else 'Held on your phone until you choose to share.')
			),
		)

	# --- COM-104 misinformation tracker ---------------------------------------------------

	async def flag_misinfo(self, submission: MisinfoSubmission, at_ms: int | None = None) -> MisinfoCluster:
		"""Record a rumour and return its cluster, with §6.4's clock attached.

		The first report for a topic starts the clock. `at_ms` is injectable for the same reason
		§24.8's breach deadline is computed from a supplied instant rather than read from the wall:
		a clock nobody can move is a clock nobody can test, and a deadline asserted is not a deadline
		measured.
		"""
		seen_at = at_ms if at_ms is not None else now_ms()
		self._misinfo.append(submission)
		self._log_info('misinformation flagged', medium=submission.medium, county=submission.county)
		# The cluster for the topic just flagged, not the busiest topic overall: someone reporting a
		# rumour must be shown the correction for that rumour, never one about a different subject.
		return self._cluster_for(submission.topic or 'unknown', seen_at, at_ms)

	def _cluster_for(self, topic: str, seen_at: int, at_ms: int | None = None) -> MisinfoCluster:
		rows = [s for s in self._misinfo if (s.topic or 'unknown') == topic]
		counties = sorted({s.county for s in rows})
		n = len(rows)
		velocity = 'spiking' if n >= SPIKING_THRESHOLD else ('rising' if n >= RISING_THRESHOLD else 'slow')
		detected = self._detected.setdefault(topic, seen_at)
		clock = response_clock(topic, detected, at_ms if at_ms is not None else seen_at)
		due = clock.next_due_ms
		return MisinfoCluster(
			topic=topic, reports=max(1, n), velocity=velocity, counties=counties,
			correction=self.correction_for(topic),
			status='correction_published' if velocity in ('rising', 'spiking') else 'aggregating',
			detected_at_ms=detected, next_due_at_ms=due, response_overdue=clock.breached,
		)

	def clusters(self, at_ms: int | None = None) -> list[MisinfoCluster]:
		now = at_ms if at_ms is not None else now_ms()
		topics = sorted({s.topic or 'unknown' for s in self._misinfo})
		out = [self._cluster_for(t, now, at_ms) for t in topics]
		return sorted(out, key=lambda c: -c.reports)

	def correction_for(self, topic: str, lang: str = 'en') -> str:
		"""The pre-drafted correction for a topic, in the reader's language.

		An unknown topic falls back to `unknown`, which is itself a correction — "under verification"
		is the honest answer §6.2.8 asks for, and it is better than silence. A topic known to the
		library but missing a language falls back to English and says so rather than returning a
		string that pretends to be Swahili; `coverage()` is what surfaces that gap to an operator.

		A language with no table at all is the same case one level up: `answerable` resolves it to
		English rather than asserting. Refusing here would mean a rumour correction cannot be sent
		to a Dholuo-speaking community — the audience §4.1's Persona F is, and the one §6.2.8's
		response clock is most likely to be running for.
		"""
		texts = CORRECTION_LIBRARY.get(topic, CORRECTION_LIBRARY[FALLBACK_TOPIC])
		served = answerable(lang)
		return texts.get(served) or texts['en']

	def answer_claim(self, claim: str, lang: str = 'en') -> ClaimAnswer:
		"""§INF-004's "Ask about a rumour" — a claim submitted for verification, answered to the asker.

		This is not `flag_misinfo`, and the difference is the whole feature. A flagger reports a rumour
		they saw *someone else* spread, and gets a cluster: how many reports, which counties, how fast
		it is moving. That is PHEOC's view of a rumour, and it is the wrong answer to give a person who
		has just asked whether something they heard is true — they are told their question started a
		surveillance row and handed no correction.

		So the answer carries the correction, the claim it corrects, and the authority behind it. The
		correction is served in the asker's own language and `answered_in` says which they got, so a
		Dholuo speaker is answered in English *and knows it* rather than reading English believing it is
		Dholuo — the discipline `answerable()` exists for.

		A claim matching nothing drafted is answered with the fallback rather than guessed at. Naming
		the wrong rumour would put a confident correction in front of someone asking about a different
		one, which is worse than the honest "under verification".
		"""
		assert claim.strip(), 'a claim is required'
		topic, matched = classify(claim)
		served = answerable(lang)
		myth = myth_for(topic, served) if topic else None
		text = self.correction_for(topic or FALLBACK_TOPIC, lang)
		return ClaimAnswer(
			claim=claim, topic=topic, matched=matched, correction=text,
			# The fallback is drafted in both languages too, so an unrecognised claim is answered in
			# the asker's own language rather than dropped to English: "under verification" is the
			# whole answer and it is no less useful to a Swahili reader than a correction is.
			fact=myth.fact if myth else FALLBACK_CORRECTION[served],
			source=myth.source if myth else '',
			slug=myth.slug if myth else '',
			# The language the correction is actually in, not the one asked for. `answerable()` resolves
			# a language with no table to English rather than refusing, and a person told which language
			# they got is not left reading English believing it is Dholuo.
			answered_in=served,
			recognised=myth is not None,
			# §6.2.3: the correction a person is shown carries when it was drafted, because an
			# undated correction about a live rumour is one nobody can weigh.
			drafted_on_iso=DRAFTED_ON_ISO,
		)

	# --- §6.4 the response protocol, as a clock and as coverage ---------------------------------

	def response_clock(self, topic: str, at_ms: int | None = None, completed_through: int = 0) -> ResponseClock:
		"""Where this topic's response stands. A topic never flagged has no clock, which is an
		assertion rather than a zero: a response that never started is not a response that is on time."""
		assert topic in self._detected, f'no rumour detected for {topic!r}'
		return response_clock(topic, self._detected[topic], at_ms if at_ms is not None else now_ms(),
		                      completed_through)

	def protocol_steps(self) -> list[dict[str, object]]:
		return [
			{'step': s.step, 'action': s.action, 'owner': s.owner, 'sla_label': s.sla_label,
			 'sla_hours': s.sla_hours}
			for s in PROTOCOL
		]

	def protocol_coverage(self) -> dict[str, object]:
		"""§6.4's readiness, as the served view of it. The gaps are named, not counted — an operator
		who reads "undrafted: conspiracy" knows what to draft, and one who reads a number does not."""
		return coverage(CORRECTION_LIBRARY).model_dump(mode='json')
