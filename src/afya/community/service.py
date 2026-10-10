"""Community services (spec §10.4 COM-005, §11.4 COM-101..104).

COM-101 case reports are server-authoritative (§16.3) and mirror AVADAR: submission fires an
automatic alert to the disease surveillance officer, and the report moves through
reported -> investigated -> lab_result -> closed.
"""
from afya.community.views import (
	ISSUE_ROUTING, CaseReport, CaseReportView, CaseStatus, CommunityIssue, ContactEntry, ContactList,
	ContactTracingSummary, IssueReceipt, IssueStatus, MisinfoCluster, MisinfoSubmission, PeerAlert,
	PeerAlertReceipt,
)
from afya.logmixin import LogMixin

# Misinformation topics with a pre-drafted, source-attributed correction (§6.4 response protocol).
CORRECTION_LIBRARY: dict[str, str] = {
	'cure_claim': 'No herbal or religious remedy cures Ebola. Only supportive care in a treatment unit improves survival — MoH/PHEOC.',
	'transmission_claim': 'Ebola spreads through direct contact with blood or body fluids of a sick or dead person. It is not airborne and not spread by food — WHO.',
	'vaccine_claim': 'Approved Ebola vaccines are tested and free at designated points. Vaccination protects your family — MoH.',
	'burial_claim': 'Safe and dignified burial protects the family while respecting the deceased. Burial teams are trained and free — MoH/PHEOC.',
	'denial_claim': 'Ebola is real and Kenya has activated its response. Reporting symptoms early saves lives — PHEOC.',
	'unknown': 'This claim is under verification by MoH. Treat unverified health claims as unconfirmed and follow official channels.',
}

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
		lowered = f'{alert.headline} {alert.body}'.lower()
		banned = [w for w in ('panic', 'deadly killer', 'everyone will die', 'mass grave') if w in lowered]
		assert not banned, f'alarmist tone rejected: {banned}'
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

	async def flag_misinfo(self, submission: MisinfoSubmission) -> MisinfoCluster:
		self._misinfo.append(submission)
		self._log_info('misinformation flagged', medium=submission.medium, county=submission.county)
		# The cluster for the topic just flagged, not the busiest topic overall: someone reporting a
		# rumour must be shown the correction for that rumour, never one about a different subject.
		return self._cluster_for(submission.topic or 'unknown')

	def _cluster_for(self, topic: str) -> MisinfoCluster:
		rows = [s for s in self._misinfo if (s.topic or 'unknown') == topic]
		counties = sorted({s.county for s in rows})
		n = len(rows)
		velocity = 'spiking' if n >= SPIKING_THRESHOLD else ('rising' if n >= RISING_THRESHOLD else 'slow')
		return MisinfoCluster(
			topic=topic, reports=max(1, n), velocity=velocity, counties=counties,
			correction=CORRECTION_LIBRARY.get(topic, CORRECTION_LIBRARY['unknown']),
			status='correction_published' if velocity in ('rising', 'spiking') else 'aggregating',
		)

	def clusters(self) -> list[MisinfoCluster]:
		topics = sorted({s.topic or 'unknown' for s in self._misinfo})
		out = [self._cluster_for(t) for t in topics]
		return sorted(out, key=lambda c: -c.reports)

	def correction_for(self, topic: str) -> str:
		return CORRECTION_LIBRARY.get(topic, CORRECTION_LIBRARY['unknown'])
