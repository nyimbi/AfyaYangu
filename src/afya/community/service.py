"""Community services (spec §10.4 COM-005, §11.4 COM-101..104).

COM-101 case reports are server-authoritative (§16.3) and mirror AVADAR: submission fires an
automatic alert to the disease surveillance officer, and the report moves through
reported -> investigated -> lab_result -> closed.
"""
import json

from typing import Any, Protocol

from afya.auth.views import now_ms
from afya.channels.views import PushPayload
from afya.community.protocol import PROTOCOL, ResponseClock, coverage, response_clock
from afya.community.views import (
	ALERT_WINDOW_DAYS, FOLLOWUP_DAYS, ISSUE_ROUTING, CaseReport, CaseReportView, CaseStatus,
	ClaimAnswer, CommunityIssue, ContactEntry, ContactList, ContactShare, ContactShareReceipt,
	ContactTracingSummary, CorrectionNotice, IssueReceipt, IssueStatus, MisinfoCluster,
	MisinfoSubmission, PeerAlert, PeerAlertAck, PeerAlertGuidance, PeerAlertReceipt,
)
from afya.crypto.service import CryptoService
from afya.identity.service import IdentityService
from afya.ids import uuid7str
from afya.info.myths import (
	DRAFTED_ON_ISO, FALLBACK_CORRECTION, FALLBACK_TOPIC, classify, correction_library, myth_for,
)
from afya.info.principles import Subject, judge
from afya.logmixin import LogMixin
from afya.strings import answerable
from afya.sync.views import SyncOp, SyncQueue

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


class HealthAuthorityPort(Protocol):
	"""§COM-103's "secure, encrypted channel", as the community service sees it.

	The service seals the list and hands the envelope over; what carries it is the deployment's
	business, because the channel that exists differs by county — ADaM where the national platform is
	reachable, a county health team's own endpoint where it is not, and in a unit test a port that
	records what it was handed. The service is therefore testable without a network and the transport
	is replaceable without touching the consent logic.

	Structural rather than an import of `AdamClient` for the same reason `SyncQueue` is: the
	dependency then runs one way, and no cycle can form through the module that carries the bytes.
	"""

	async def share_contact_list(self, envelope: dict[str, Any]) -> str: ...


class NotificationPort(Protocol):
	"""§11.4's last arrow — "flagger notified" — as the community service sees it.

	One method and no state: the service composes the notice and hands it over, and what delivers it
	(native push, SMS, a WhatsApp template) is the deployment's business for the same reason
	`HealthAuthorityPort`'s transport is. §ALT-003's own preference vocabulary travels with the
	payload as its `category`, so the subscription check happens in the layer that holds the
	subscriptions rather than being re-derived here from a second copy of the toggle list.

	The payload type is `PushPayload` rather than a dict, and that is deliberate: the first version
	passed a dict and `ChannelService.push` — which takes the model — raised `'dict' object has no
	attribute 'title'` inside the transport's own `except Exception`, so every notice was recorded as
	unsent with no reason a reader could act on. A structural port whose payload is `Any` moves the
	mismatch from the type checker to the one place it is invisible.
	"""

	async def push(self, payload: PushPayload) -> PushPayload: ...


# §COM-103's data handling: "Deleted after the contact-tracing window closes." The window is the
# same 21 days §COM-102's follow-up prompts and §MON-009's diary run on, and it is read from the
# constant rather than typed again — three features that each wrote their own 21 would be three
# answers to one question.
CONTACT_SHARE_WINDOW_DAYS: int = ALERT_WINDOW_DAYS

# The recipient §COM-103's bullet names. An office rather than a person: a share addressed to an
# individual is unreadable the day that individual transfers, and the contact list is the county's
# to act on rather than theirs to keep.
CONTACT_SHARE_RECIPIENT = 'County Disease Surveillance Team'

CONTACT_SHARE_MESSAGE = (
	'Encrypted and sent to the county disease surveillance team. It is kept for 21 days — the '
	'tracing window — and then deleted. You can withdraw it sooner by deleting your contact list.'
)

# §11.4's "Push notification with corrections when a rumour the user flagged is addressed". The
# category is §ALT-003's own "Community alerts" — the option a person switches off when they do not
# want to hear about what is circulating where they live. A new toggle for this would be a twelfth
# switch §ALT-003 never listed, and a category outside `TOGGLEABLE` is one nobody can decline.
CORRECTION_NOTICE_CATEGORY = 'community_alerts'

# Why a notice that exists was not handed to a delivery path. Both are answers rather than errors,
# because a notice dropped in silence reads exactly like a person who was never told.
NOTICE_WITHHELD_NO_FLAGGER = (
	'This report named nobody to tell. A report can carry the phone number or reference of the '
	'person who heard the rumour, and the correction goes to them when it is ready.'
)
NOTICE_WITHHELD_UNSUBSCRIBED = (
	'You have community alerts switched off, so this was not pushed to your phone. It is here for '
	'you to read, and you can turn them back on in your alert settings.'
)
NOTICE_WITHHELD_UNDRAFTED = (
	'This rumour is still being verified, so there is no correction to send yet. You will be told '
	'when there is one.'
)
NOTICE_WITHHELD_NO_TRANSPORT = (
	'No notification channel is configured on this deployment, so nothing was pushed. The correction '
	'is here for you to read.'
)
NOTICE_WITHHELD_TRANSPORT_FAILED = (
	'Your phone could not be reached when this was ready. The correction is here for you to read, and '
	'it is the same one that would have been pushed.'
)

CORRECTION_NOTICE_TITLE = 'That rumour you reported — here is the answer'


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
	def __init__(self, identity: IdentityService | None = None, sync: SyncQueue | None = None,
	             crypto: CryptoService | None = None,
	             authority: HealthAuthorityPort | None = None,
	             notifier: NotificationPort | None = None,
	             alerts: Any | None = None) -> None:
		"""`identity` is §5.4's single identity model, injected rather than constructed here because the
		index it holds is shared with the channel layer — two instances would resolve the same phone to
		two subjects and the deduplication would find nothing. Optional only so a unit test can build
		the community service alone; `_dedup_key` refuses rather than falling back to the raw number,
		because a key built on the MSISDN alone silently fails to match a report the same person filed
		from the app, which is the cross-channel case §5.4 is about.

		`sync` is §COM-101's "Offline report queue". A CHW in the field is the one user this section
		describes whose reports are most likely to be filed with no bars, and §16.3 already carries a
		`case_reports` rule with nothing queueing a report through it — a rule for a dataset nothing
		writes. Optional for the same reason `identity` is: a unit test that only wants the dedup must
		not have to stand up a queue.

		`crypto` and `authority` are §COM-103's "share with health authorities through a secure,
		encrypted channel", and they are two parameters rather than one because they fail
		independently. `crypto` supplies the seal — and the share is *refused* rather than sent in the
		clear when it is absent or when the deployment holds no application-layer key, because a
		contact list is the one dataset §SEC-003 names for the second layer and a plaintext share
		would be the audit row's "a flag and nothing transmits" replaced by something worse.
		`authority` supplies the transport; with none, a consented share is sealed, stored and
		reported as held rather than silently reported as delivered.

		`notifier` and `alerts` are §11.4's last bullet, and they are two parameters because they
		answer two different questions. `notifier` is the delivery path — the `ChannelService`, typed
		loosely for the reason every cross-module port here is. `alerts` is §ALT-003's subscription
		ledger, and it decides whether the notice is *owed* to this person before any transport is
		consulted. A deployment with neither still composes the notice and says it was withheld, which
		is the honest state: the audit row's defect was a correction drafted for a flagger nobody
		could identify, and a notice reported as sent with nothing wired would be the same defect
		wearing §COM-103's ending.
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
		# §COM-101's offline report queue. Absent when the service is built without one, and a report
		# is then recorded locally and not queued — the same two-state shape §MON-004's tracker has.
		self._sync: SyncQueue | None = sync
		# §COM-103's encrypted share. `_shares` is the outbox: a sealed envelope is kept whether or
		# not a transport took it, so a deployment with no authority yet still has the list sealed and
		# ready, and the person is told which of the two happened rather than the flattering one.
		self._crypto = crypto
		self._authority: HealthAuthorityPort | None = authority
		self._shares: dict[str, ContactShare] = {}
		# §11.4's flagger notification. `_notices` is keyed on `(topic, subject_ref)` rather than on
		# the topic alone, because a rumour twenty people reported owes twenty notices and one entry
		# per topic would tell exactly one of them. Keyed on the pair so a second call for the same
		# person and rumour is one notice, which is what makes the publish step idempotent.
		self._notifier: NotificationPort | None = notifier
		self._alerts = alerts
		self._notices: dict[tuple[str, str], CorrectionNotice] = {}
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
		# §COM-101's "Offline report queue". Queued here, with the *recording*, rather than with the
		# alert below — both paths record the report and only one of them alerts, and a duplicate
		# that arrived offline is still a report the server does not have. Queueing it beside the
		# alert would drop exactly the second report the dedup docstring promises is kept.
		#
		# Gated on the CHW's own declaration rather than queued unconditionally, and that gate is the
		# difference between a queue and a duplicate factory: a report that arrived over a network is
		# one the server already holds, and §5.4's dedup cannot catch a replayed copy because the CHW
		# logging offline carries no MSISDN for the key to be built on. `reported_offline` says which
		# of the two happened, and it was a field nothing read until now.
		if report.reported_offline and self._sync is not None:
			await self._queue_case(report)
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

	async def _queue_case(self, report: CaseReport) -> None:
		"""Hand an offline report to the sync queue, under §16.3's own `case_reports` rule.

		The dataset name is the one `CONFLICT_RULES` already carries for this data, so the strategy
		applied on replay is the spec's own — server-authoritative, "clinical accuracy critical" —
		rather than one chosen here. A rule with no producer is a rule for a dataset nothing writes.

		**The whole report travels, not a reference to it.** §COM-101's bullet is that the report is
		*stored locally* until there is a signal, and the store this deployment has is the queue: a
		payload carrying only an id would leave the fields on a handset that crashed, and the officer
		would receive a case with no symptoms, no village and no temperature. Every field is encoded,
		`None` included, because §16.4's delta is computed field by field — an omitted key reads as
		"unchanged" and a key that went from a value to `null` is a change, so the two must be
		distinguishable on the wire. JSON per value rather than one blob for the same reason: a
		single serialised string would make every edit resend every field and §16.4's delta sync a
		claim rather than a behaviour.
		"""
		assert self._sync is not None, 'a queue is required to queue a report'
		# The *tail* of the id, not the head. A UUID7's leading bytes are its millisecond timestamp,
		# so a prefix collides for two reports filed in the same millisecond and the queue — keyed on
		# `op_id` — keeps the last and drops the first. A CHW replaying a day of reports after an
		# outage files them in a burst, which is exactly when a collision costs the most; §MON-004's
		# dose queue takes its suffix for the same reason.
		op = SyncOp(
			op_id='OP-' + uuid7str().replace('-', '').upper()[-8:],
			dataset='case_reports',
			client_ts=now_ms(),
			payload={name: json.dumps(value) for name, value in report.model_dump(mode='json').items()},
		)
		await self._sync.enqueue(op)
		self._log_info('offline case report queued for sync', report=report.report_id)

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
		# `shared` reports whether a share has actually *left*, not whether consent was given. The
		# flag alone was the audit row: the summary read `share_consent` and the person was told
		# "Shared with the health team." while nothing had been sent anywhere. Consent and delivery
		# are different facts and the second is the one a person needs.
		delivered = any(s.subject_ref == subject_ref for s in self._shares.values())
		return ContactTracingSummary(
			subject_ref=subject_ref, by_setting=by_setting, total=total, shared=delivered,
			progress_pct=progress,
			message=(
				'Thank you — this is hard, and it protects people you care about. '
				+ ('Shared with the health team.' if delivered
				   else 'Ready to share with the health team.' if bucket.share_consent
				   else 'Held on your phone until you choose to share.')
			),
		)

	async def share_contacts(self, subject_ref: str, with_who: str | None = None,
	                         at_ms: int | None = None) -> ContactShareReceipt:
		"""§COM-103's "share with health authorities through a secure, encrypted channel".

		Three gates, and each is a different refusal:

		1. **Consent.** `share_consent` must be true. §COM-103's data handling says the list is
		   "transmitted only with explicit consent", and a route that shared on request would make
		   the flag decorative — the same shape as the audit row this closes.
		2. **Something to share.** An empty list is refused rather than sent: an empty contact list
		   arriving at the county reads as "this person had no contacts", which is a claim about the
		   outbreak that the person never made.
		3. **A key.** The list is sealed under the *application-layer* key and the share is refused
		   when that key is absent. Falling back to the at-rest key would put the contacts under the
		   key the operator already holds, which is the one layer §SEC-003 says is not enough here.

		The envelope is built before the transport is consulted, so a deployment with no authority
		still seals and keeps the list; `receipt.message` then says it is held rather than delivered.
		A share that reported success with nothing behind it would be the audit row again.
		"""
		bucket = self._contacts.get(subject_ref)
		assert bucket is not None, 'no contact list is held for this person'
		assert bucket.share_consent, (
			'sharing a contact list needs the person\'s explicit consent (§COM-103); the list is '
			'held on the phone until they give it')
		assert bucket.entries, 'there is nothing to share — an empty list is not a statement about contacts'
		assert self._crypto is not None and self._crypto.has_app_layer, (
			'the deployment holds no application-layer key, so a contact list cannot be sealed; '
			'refusing rather than sharing it under the at-rest key alone')
		recipient = with_who or CONTACT_SHARE_RECIPIENT
		shared_at = at_ms if at_ms is not None else now_ms()
		# A second share to the same recipient reuses the envelope already held rather than sealing
		# a fresh one. That is what makes the held-then-sent path work: a person with no bars taps
		# share, the envelope is sealed and kept, and when signal returns the *same* ciphertext goes
		# out. Sealing again would leave the first envelope in the outbox forever, so the dashboard
		# would show two shares where the person made one.
		held = self._shares.get(f'{subject_ref}:{recipient}')
		if held is not None and held.expires_at_ms > shared_at:
			envelope = held
		else:
			payload = json.dumps({
				'subject_ref': subject_ref,
				'entries': [e.model_dump(mode='json') for e in bucket.entries],
			}).encode('utf-8')
			sealed = self._crypto.seal(payload, app_layer=True)
			envelope = ContactShare(
				subject_ref=subject_ref, with_who=recipient, sealed=sealed.to_blob(),
				entries=len(bucket.entries), shared_at_ms=shared_at,
				expires_at_ms=shared_at + CONTACT_SHARE_WINDOW_DAYS * 86_400_000,
				receipt='',
			)
			# Kept before it is sent, so a transport that fails does not lose the sealed list.
			self._shares[f'{subject_ref}:{recipient}'] = envelope
		delivered = False
		if self._authority is not None:
			# A transport that exists but is unreachable is this section's *normal* case, not an edge
			# one: the person sharing a contact list is the person who has been told they are a case
			# or a contact, and that is not a moment to depend on the county's endpoint being up. The
			# envelope is already sealed and kept, so a failure here degrades to held — the same
			# answer as a deployment with no transport — rather than raising and losing the fact that
			# the person made the decision. §16.1 principle 5: nothing is lost.
			try:
				await self._authority.share_contact_list(envelope.model_dump(mode='json'))
				delivered = True
			except Exception as exc:  # noqa: BLE001 — any transport failure means the same thing here
				self._log_warn('contact list share could not be delivered', subject=subject_ref,
					error=str(exc)[:120])
		self._log_info('contact list share', subject=subject_ref, entries=envelope.entries,
			delivered=delivered, recipient=recipient)
		return ContactShareReceipt(
			share_id=envelope.share_id, with_who=recipient, entries=envelope.entries,
			shared_at_ms=shared_at, expires_at_ms=envelope.expires_at_ms,
			algorithm=envelope.algorithm,
			message=CONTACT_SHARE_MESSAGE if delivered else
				'Encrypted and kept on this device. It will be sent as soon as the health team\'s '
				'channel is reachable.',
		)

	def shared_contacts(self, subject_ref: str) -> list[ContactShare]:
		"""The envelopes this person has shared, newest last. §SEC-006's dashboard reads it."""
		return [s for s in self._shares.values() if s.subject_ref == subject_ref]

	def withdraw_shares(self, subject_ref: str) -> int:
		"""§COM-103's "deleted after the contact-tracing window closes", on the person's own demand.

		Returns the count removed. §SEC-005 gives a person the right to delete their own data at any
		time, and a share the person cannot take back would be a retention rule with no lever.
		"""
		gone = [k for k, s in self._shares.items() if s.subject_ref == subject_ref]
		for k in gone:
			del self._shares[k]
		if gone:
			self._log_info('contact shares withdrawn', subject=subject_ref, count=len(gone))
		return len(gone)

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

	# --- §11.4's last arrow: the flagger is told -----------------------------------------------

	def flaggers_for(self, topic: str) -> list[str]:
		"""Everyone who reported this rumour and left a way to reach them.

		`flagger_ref` was written on every submission and read nowhere, which is why the section's
		flow ended at "published on all channels" with no arrow back to the person who started it.
		Deduplicated in order of first report, because one person who reported the same rumour three
		times is one person owed one correction.
		"""
		out: list[str] = []
		for s in self._misinfo:
			if (s.topic or 'unknown') != topic or not s.flagger_ref:
				continue
			if s.flagger_ref not in out:
				out.append(s.flagger_ref)
		return out

	async def notify_flaggers(self, topic: str, lang: str = 'en',
	                          at_ms: int | None = None) -> list[CorrectionNotice]:
		"""§11.4's "Push notification with corrections when a rumour the user flagged is addressed".

		One notice per person who reported the rumour, composed from the correction the protocol has
		already drafted, addressed through `flagger_ref`. Three things are checked before anything
		leaves, and each failure is *reported* rather than dropped:

		* a topic with no correction drafted yet is not addressed at all. The flow's own order is
		  "verified → correction drafted → published → flagger notified", and notifying before the
		  correction exists would push "under verification" to someone who already knows it is under
		  verification — they are the one who reported it.
		* a report with no `flagger_ref` cannot be addressed, and says so. §COM-103's lesson applies
		  here: a notification reported as sent to nobody is worse than one reported as unsendable.
		* a person who switched §ALT-003's community alerts off is not pushed to, and the notice is
		  kept for them to read. `should_deliver` is the ledger's own answer, so the toggle decides
		  rather than a second copy of the rule.

		Keyed on `(topic, subject_ref)` in `_notices`, so calling this after every new report — which
		is what the flag route does — re-notifies nobody who has already been told.
		"""
		assert topic, 'a notice needs the rumour it is about'
		assert topic in self._detected, f'no rumour detected for {topic!r}'
		issued = at_ms if at_ms is not None else now_ms()
		text = self.correction_for(topic, lang)
		served = answerable(lang)
		myth = myth_for(topic, served)
		source = myth.source if myth else ''
		# The correction, not the fallback: `correction_for` answers an undrafted topic with "under
		# verification", and pushing that to the person who reported the rumour tells them nothing
		# they did not already know. The notice is owed only once there is something to say. The
		# fallback topic is excluded for the same reason and it is the case that matters most — a
		# report filed with no topic resolves to `unknown`, which *has* a library entry, so without
		# this the person who reported a rumour the tracker could not classify would be pushed the
		# one answer the tracker gives when it has nothing to say.
		drafted = topic in CORRECTION_LIBRARY and topic != FALLBACK_TOPIC
		out: list[CorrectionNotice] = []
		for flagger in self.flaggers_for(topic):
			if not drafted:
				out.append(CorrectionNotice(
					topic=topic, subject_ref=flagger, title=CORRECTION_NOTICE_TITLE,
					body=self.correction_for(topic, lang), correction=text, source=source,
					sent=False, withheld=NOTICE_WITHHELD_UNDRAFTED,
					category=CORRECTION_NOTICE_CATEGORY, issued_at_ms=issued))
				continue
			notice = self._notices.get((topic, flagger))
			if notice is not None:
				out.append(notice)
				continue
			subscribed = True
			if self._alerts is not None:
				subscribed = bool(self._alerts.should_deliver(flagger, CORRECTION_NOTICE_CATEGORY))
			notice = CorrectionNotice(
				topic=topic, subject_ref=flagger, title=CORRECTION_NOTICE_TITLE,
				body=f'{text} Source: {source}.' if source else text,
				correction=text, source=source, sent=False,
				withheld=(None if (subscribed and self._notifier is not None)
				          else NOTICE_WITHHELD_UNSUBSCRIBED if not subscribed
				          else NOTICE_WITHHELD_NO_TRANSPORT),
				category=CORRECTION_NOTICE_CATEGORY, issued_at_ms=issued)
			if subscribed and self._notifier is not None:
				try:
					await self._notifier.push(PushPayload(
						subject_ref=flagger, title=notice.title, body=notice.body,
						category=CORRECTION_NOTICE_CATEGORY,
						# The section this notice comes from, so a client can resolve the control
						# that owns it without matching on the title.
						tier_feature='COM-104'))
					notice.sent = True
				except Exception as exc:  # noqa: BLE001
					# A transport that fails is this section's normal case, not its edge case: the
					# correction is composed and kept either way, and the person is told it is here.
					# `withheld` says the transport failed rather than that none is configured —
					# the two are different facts and a reader acting on the wrong one chases the
					# wrong fault.
					notice.withheld = NOTICE_WITHHELD_TRANSPORT_FAILED
					self._log_warn('correction notice could not be pushed', subject=flagger,
					               topic=topic, error=str(exc)[:120])
			self._notices[(topic, flagger)] = notice
			out.append(notice)
		if out:
			self._log_info('correction notices for flaggers', topic=topic,
			               flaggers=len(out), sent=sum(1 for n in out if n.sent))
		return out

	def notices_for(self, subject_ref: str) -> list[CorrectionNotice]:
		"""§SEC-001's "audit log visible to the user", for this section: what this person was told.

		Readable whether or not the push went out, because the notice a person can open in the app is
		the same correction the push carried — and the one that was withheld says why.
		"""
		return [n for n in self._notices.values() if n.subject_ref == subject_ref]

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
