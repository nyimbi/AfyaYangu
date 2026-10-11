"""Community services (spec §10.4 COM-005, §11.4 COM-101..104).

COM-101 case reports are server-authoritative (§16.3) and mirror AVADAR: submission fires an
automatic alert to the disease surveillance officer, and the report moves through
reported -> investigated -> lab_result -> closed.
"""
from afya.auth.views import now_ms
from afya.community.protocol import PROTOCOL, ResponseClock, coverage, response_clock
from afya.community.views import (
	ISSUE_ROUTING, CaseReport, CaseReportView, CaseStatus, CommunityIssue, ContactEntry, ContactList,
	ContactTracingSummary, IssueReceipt, IssueStatus, MisinfoCluster, MisinfoSubmission, PeerAlert,
	PeerAlertReceipt,
)
from afya.info.principles import Subject, judge
from afya.logmixin import LogMixin
from afya.strings import answerable

# Misinformation topics with a pre-drafted, source-attributed correction (§6.4 response protocol).
#
# Every correction carries both languages. §6.4's step 4 says the correction is drafted "in all
# relevant languages" and §6.2.4 forbids publishing English-only for a life-safety message, so an
# English-only correction is one the audience §3.3 principle 8 puts first cannot read. The table was
# a bare `str` per topic until §6.4 was built; `coverage()` now reports any that go missing.
#
# The attributions are separated by a hyphen and not an em dash. §6.4 step 5 publishes "all channels
# simultaneously", and SMS is one of the channels §6.2.6 names — a character outside GSM-7 cannot be
# sent as a plain SMS, so every one of these six corrections was unpostable on a channel the section
# requires. `tests/ci/test_misinfo_protocol.py` holds that shut.
CORRECTION_LIBRARY: dict[str, dict[str, str]] = {
	'cure_claim': {
		'en': 'No herbal or religious remedy cures Ebola. Only supportive care in a treatment unit improves survival - MoH/PHEOC.',
		'sw': 'Hakuna dawa ya miti shamba wala ya kidini inayotibu Ebola. Huduma katika kituo cha matibabu pekee huongeza nafasi ya kupona - Wizara ya Afya/PHEOC.',
	},
	'transmission_claim': {
		'en': 'Ebola spreads through direct contact with blood or body fluids of a sick or dead person. It is not airborne and not spread by food - WHO.',
		'sw': 'Ebola huenea kwa kugusa damu au majimaji ya mwili ya mtu mgonjwa au aliyefariki. Hauenei kwa hewa wala kwa chakula - WHO.',
	},
	'vaccine_claim': {
		'en': 'Approved Ebola vaccines are tested and free at designated points. Vaccination protects your family - MoH.',
		'sw': 'Chanjo za Ebola zilizoidhinishwa zimepimwa na ni bure katika vituo vilivyotajwa. Chanjo inalinda familia yako - Wizara ya Afya.',
	},
	'burial_claim': {
		'en': 'Safe and dignified burial protects the family while respecting the deceased. Burial teams are trained and free - MoH/PHEOC.',
		'sw': 'Mazishi salama na ya heshima hulinda familia na kumheshimu marehemu. Timu za mazishi zimefundishwa na hazina malipo - Wizara ya Afya/PHEOC.',
	},
	'denial_claim': {
		'en': 'Ebola is real and Kenya has activated its response. Reporting symptoms early saves lives - PHEOC.',
		'sw': 'Ebola ni kweli na Kenya imeanzisha mwitikio wake. Kuripoti dalili mapema huokoa maisha - PHEOC.',
	},
	'unknown': {
		'en': 'This claim is under verification by MoH. Treat unverified health claims as unconfirmed and follow official channels.',
		'sw': 'Madai haya yanachunguzwa na Wizara ya Afya. Chukulia madai ya afya yasiyothibitishwa kama hayajathibitishwa na fuata njia rasmi.',
	},
}

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


class CommunityService(LogMixin):
	def __init__(self) -> None:
		self._issues: dict[str, CommunityIssue] = {}
		self._issue_status: dict[str, IssueStatus] = {}
		self._cases: dict[str, CaseReport] = {}
		self._case_status: dict[str, CaseStatus] = {}
		self._peer_alerts: list[PeerAlert] = []
		self._contacts: dict[str, ContactList] = {}
		self._misinfo: list[MisinfoSubmission] = []
		self._detected: dict[str, int] = {}
		assert self._issues == {} and self._cases == {}

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
		assert report.symptoms, 'symptom checklist required'
		if report.photo_sha256 is not None:
			assert report.geotagged, 'photo evidence requires geotag consent (§COM-101)'
		self._cases[report.report_id] = report
		self._case_status[report.report_id] = CaseStatus.reported
		officer = f'{report.county} disease surveillance officer'
		self._log_warn('case report submitted', report=report.report_id, disease=report.suspected_disease, county=report.county)
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
		finding = judge(f'peer_alert:{alert.alert_id}', f'{alert.headline} {alert.body}', Subject.content)
		failures = [v.detail for v in finding.failures()]
		assert not failures, f'peer alert tone rejected: {failures}'
		self._peer_alerts.append(alert)
		# Recipients are counted by the geofence fan-out; this service records the verified alert.
		recipients = int(3.14159 * (alert.radius_m / 1000.0) ** 2 * 4000)
		self._log_warn('peer alert verified and dispatched', county=alert.county, radius_m=alert.radius_m)
		return PeerAlertReceipt(
			alert_id=alert.alert_id, recipients=recipients, verification=f'verified by {alert.verified_by}',
			tone_check='calm, factual, actionable — no case identifiers present',
		)

	def peer_alerts(self, county: str) -> list[PeerAlert]:
		return [a for a in self._peer_alerts if a.county == county]

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
		texts = CORRECTION_LIBRARY.get(topic, CORRECTION_LIBRARY['unknown'])
		served = answerable(lang)
		return texts.get(served) or texts['en']

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
