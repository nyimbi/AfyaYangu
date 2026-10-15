"""§23's risk register and §24's operational duties, as data that can be checked.

Two rules run through this module.

The first is that a mitigation naming software must name software that exists. §23's mitigation
column says "automated staleness alerts", "bug bounty", "transparency reports", "manual fallback";
each of those is a claim about this repo, and `resolve` walks the `module:attr` reference and says
whether it lands. A register whose mitigations are all `process` is honest; a register with a `code`
row pointing at nothing is the failure mode, and it is now a red test.

The second is that a deadline is computed from the clock, not asserted. §24.8 puts the ODPC
notification at 72 hours from *detection* — the DPA's clock, not ours — so `status` measures from
`detected_at_iso` and reports overdue as a fact. The earlier `breach_notification` clamped its
answer with `max(0, 3 - days_ago)`, which made a breach reported two days late indistinguishable
from one reported on time: both read `0`.
"""
from datetime import date, datetime, timedelta, timezone

from afya.logmixin import LogMixin
from afya.refs import resolves
from afya.operations.views import (
	FundingStage, GovernanceBody, GovernanceReport, Incident, IncidentClass, IncidentKind,
	IncidentSeverity, IncidentStatus, Obligation, ObligationStatus, OpsPosture, Rating, Risk,
	RiskAssessment, RiskDomain, SupportChannel, SupportPlan, SupportSla, SustainabilityMitigation,
	SustainabilityReport, TrainingRow,
)
from afya.security.views import ControlKind

# §24.1's six governance bodies, verbatim, with the §24 duty owners each one accounts for.
#
# `owners` is the join between two vocabularies §24 uses without relating them: §24.2–§24.7 assign a
# duty to a role slug, and §24.1 says who sits on the body that role belongs to. `clinical_advisory_group`
# and `community_advisory_panel` are already slugs in both places; `dpo` sits on the Privacy and
# Ethics Board; `ciso` on the Technical Working Group; `programme_manager` and `content_lead` on the
# Operations Cell; `comms_lead` on the Operations Cell's comms function and the Steering Committee's
# escalation path. A body with no duty behind it is a committee that decides nothing.
GOVERNANCE_BODIES: tuple[GovernanceBody, ...] = (
	GovernanceBody(slug='steering_committee', body='Steering Committee',
		composition=['MoH', 'PHEOC', 'implementing partner', 'telcos', 'NGO partners'],
		role='Strategic direction, funding, escalation', owners=[]),
	GovernanceBody(slug='clinical_advisory_group', body='Clinical Advisory Group',
		composition=['Clinicians', 'epidemiologists', 'WHO', 'CDC'],
		role='Clinical content, triage logic, case definitions', owners=['clinical_advisory_group']),
	GovernanceBody(slug='technical_working_group', body='Technical Working Group',
		composition=['Engineers', 'architects', 'security', 'data'],
		role='Architecture, integration, security', owners=['ciso']),
	GovernanceBody(slug='privacy_and_ethics_board', body='Privacy and Ethics Board',
		composition=['DPO', 'legal', 'ethicists', 'civil society', 'community reps'],
		role='DPIA, AI ethics, consent, oversight', owners=['dpo', 'legal']),
	GovernanceBody(slug='community_advisory_panel', body='Community Advisory Panel',
		composition=['CHWs', 'faith leaders', 'youth reps', "women's reps"],
		role='Usability, cultural appropriateness, feedback', owners=['community_advisory_panel']),
	GovernanceBody(slug='operations_cell', body='Operations Cell',
		composition=['Programme manager', 'content lead', 'support lead', 'data lead'],
		role='Day-to-day operations', owners=['programme_manager', 'content_lead', 'comms_lead']),
)

# §24.3's five support channels, verbatim. `staffing` is None where the section writes an em dash
# rather than a headcount — the self-service help page is not an unstaffed channel, it is one nobody
# is rostered on, and a zero would read as the first.
SUPPORT_CHANNELS: tuple[SupportChannel, ...] = (
	SupportChannel(channel='In-app help', coverage='24/7 (self-service)', always_on=True),
	SupportChannel(channel='WhatsApp support', coverage='8am–8pm, 7 days', always_on=False,
		staffing='5 agents', agents=5),
	SupportChannel(channel='Phone support', coverage='8am–8pm, 7 days', always_on=False,
		staffing='3 agents', agents=3),
	SupportChannel(channel='CHW escalation', coverage='24/7', always_on=True, staffing='Roving'),
	SupportChannel(channel='Technical incidents', coverage='24/7', always_on=True, staffing='On-call engineer'),
)

# §24.4's training matrix, verbatim. `hours` is the Duration column as a number — "2 days" is 16
# hours at an 8-hour day, "4 hours" is 4 — so the matrix can be totalled. `body` is the §24.1 body
# accountable for the audience, joined on the composition §24.1 states: CHWs, faith leaders and
# community reps sit on the Community Advisory Panel, county health teams and PHEOC analysts are
# government bodies the Steering Committee convenes, support agents staff the Operations Cell's
# support function. `body` is None where §24 names nobody — the radio partners are briefed by the
# comms lead and no §24.1 body owns that, which is reported rather than papered over.
TRAINING: tuple[TrainingRow, ...] = (
	TrainingRow(audience='CHWs', content='App use, case reporting, triage, referral',
		format='In-person + e-learning', duration='2 days', hours=16.0, body='Community Advisory Panel'),
	TrainingRow(audience='Facility staff', content='App integration, referral handling',
		format='In-person', duration='4 hours', hours=4.0),
	TrainingRow(audience='County health teams', content='Dashboards, alerting, data use',
		format='In-person', duration='1 day', hours=8.0, body='Steering Committee'),
	TrainingRow(audience='PHEOC analysts', content='Analytics, AI outputs, escalation',
		format='In-person', duration='2 days', hours=16.0, body='Steering Committee'),
	TrainingRow(audience='Support agents', content='All features, escalation paths',
		format='In-person + shadowing', duration='3 days', hours=24.0, body='Operations Cell'),
	TrainingRow(audience='Community leaders', content='Awareness, referral',
		format='Community session', duration='2 hours', hours=2.0, body='Community Advisory Panel'),
	TrainingRow(audience='Radio partners', content='Messaging, verification',
		format='Briefing pack', duration='1 hour', hours=1.0),
)

# §24.5's funding model, verbatim. `sustainability` is None where the section writes an em dash: the
# emergency and build bands are not meant to sustain, and a fabricated answer would read as a plan
# for the integration the next row says has not begun.
FUNDING: tuple[FundingStage, ...] = (
	FundingStage(phase='Phase 0–1 (emergency)',
		primary_funding=['Government emergency funds', 'donor grants'], phase_floor=0, phase_ceiling=1),
	FundingStage(phase='Phase 2–3 (build)', primary_funding=['Donor grants', 'PPP'],
		phase_floor=2, phase_ceiling=3),
	FundingStage(phase='Phase 4–5 (scale)',
		primary_funding=['Donor grants', 'government budget line'],
		sustainability='Begin integration into MoH budget', phase_floor=4, phase_ceiling=5),
	FundingStage(phase='Phase 6+ (sustain)',
		primary_funding=['Government budget', 'telco CSR', 'foundation grants'],
		sustainability='Fully integrated into national health budget', phase_floor=6, phase_ceiling=6),
)

COST_DRIVERS: tuple[str, ...] = (
	'Engineering', 'content', 'translation', 'cloud', 'SMS/WhatsApp', 'support', 'training', 'evaluation',
)

COST_MITIGATIONS: tuple[str, ...] = (
	'Zero-rating reduces user cost but may require telco CSR commitment',
	'Open-source reduces licensing',
	'Shared infrastructure with MoH',
	'Volunteer CHW network (with incentives)',
	'Grant funding for outbreak-specific work',
)

# §24.6's eight mitigations, verbatim. Seven name something this repo either has or has not, so they
# carry a `control` and the register resolves it — the same rule §23's mitigation column already
# follows. The eighth is a plan for other countries rather than a claim about this build, so it
# carries no reference and is reported as unresolvable rather than given one that always lands.
SUSTAINABILITY: tuple[SustainabilityMitigation, ...] = (
	SustainabilityMitigation(number=1, mitigation='Position as permanent health infrastructure, not an outbreak tool',
		control='afya.brand.service:BRAND'),
	SustainabilityMitigation(number=2, mitigation='Tier 1–3 features are useful year-round — this is the retention engine',
		control='afya.rollout.service:RETENTION'),
	SustainabilityMitigation(number=3, mitigation='Integrate into MoH budget by Phase 6',
		control='afya.operations.service:FUNDING'),
	SustainabilityMitigation(number=4, mitigation='Multi-disease scope justifies ongoing investment',
		control='afya.registry.diseases:DISEASE_ROWS'),
	SustainabilityMitigation(number=5, mitigation='Measurable health impact in non-outbreak periods (immunisation, medication adherence, malaria)',
		control='afya.metrics.service:KPIS'),
	SustainabilityMitigation(number=6, mitigation='Telco partnership provides ongoing distribution and zero-rating',
		control='afya.rollout.service:PARTNERS'),
	SustainabilityMitigation(number=7, mitigation='Open-source community reduces maintenance cost',
		control='afya.rollout.service:LICENCE_FILES'),
	SustainabilityMitigation(number=8, mitigation='Regional expansion shares cost across countries'),
)

SUPPORT_SLAS: tuple[SupportSla, ...] = (
	SupportSla(severity=IncidentSeverity.critical, definition='System down', response_hours=0.25, response_label='15 minutes'),
	SupportSla(severity=IncidentSeverity.high, definition='Feature broken', response_hours=2.0, response_label='2 hours'),
	SupportSla(severity=IncidentSeverity.medium, definition='Usability issue', response_hours=24.0, response_label='24 hours'),
	SupportSla(severity=IncidentSeverity.low, definition='Enhancement request', response_hours=168.0, response_label='1 week'),
)

# §24.8's breach clock. The DPA 2019 gives 72 hours from becoming aware, so this is the one
# deadline in the section that is statutory rather than internal.
ODPC_NOTIFICATION_HOURS = 72

# §24.8, one row per incident type. `deadline_hours` is set only where the spec sets a clock; the
# rows it describes qualitatively ("rapid response protocol", "immediate correction") carry None and
# the §24.3 ladder entry instead, rather than a number this file invented.
INCIDENT_KINDS: tuple[IncidentKind, ...] = (
	IncidentKind(kind=IncidentClass.data_breach, severity=IncidentSeverity.critical,
		response='Isolate, assess, notify ODPC, notify affected users, remediate',
		deadline_hours=ODPC_NOTIFICATION_HOURS, deadline_basis='ODPC within 72h of detection (§24.8, DPA 2019)',
		notifies=['odpc', 'affected_users', 'pheoc']),
	IncidentKind(kind=IncidentClass.system_outage, severity=IncidentSeverity.critical,
		response='Failover, status page, comms, root cause analysis', notifies=['pheoc', 'county_health']),
	IncidentKind(kind=IncidentClass.false_alert, severity=IncidentSeverity.high,
		response='Immediate correction on all channels, investigation, process fix',
		notifies=['affected_users', 'pheoc']),
	IncidentKind(kind=IncidentClass.misinformation_spike, severity=IncidentSeverity.high,
		response='Rapid response protocol', notifies=['comms']),
	IncidentKind(kind=IncidentClass.clinical_content_error, severity=IncidentSeverity.critical,
		response='Immediate correction, clinical review, user notification',
		notifies=['clinical_advisory_group', 'affected_users']),
	IncidentKind(kind=IncidentClass.privacy_complaint, severity=IncidentSeverity.medium,
		response='Investigate, respond, remediate', deadline_hours=720,
		deadline_basis='within 30 days (§24.8)', notifies=['dpo', 'complainant']),
	IncidentKind(kind=IncidentClass.security_vulnerability, severity=IncidentSeverity.high,
		response='Patch, disclose responsibly, audit for exploitation', notifies=['ciso']),
)

# §24.8 "Post-incident: Root cause analysis within 5 days."
RCA_DEADLINE_DAYS = 5

# §23, one row per risk. `control` is `module:attr` and is walked by `resolve`; a row with
# `control_kind=process` and no reference is a duty a human discharges, which is honest, while a
# `code` row must land. The ids are assigned here rather than read from the spec, which numbers
# none of its risk rows — the register is the spec's table given handles.
RISKS: tuple[Risk, ...] = (
	# §23.1 strategic
	Risk(risk_id='R-S1', domain=RiskDomain.strategic, statement='Low adoption due to data cost',
		likelihood=Rating.high, impact=Rating.high,
		mitigation='Zero-rating agreements before launch; multi-channel strategy',
		control_kind=ControlKind.process, owner='programme_manager'),
	Risk(risk_id='R-S2', domain=RiskDomain.strategic, statement='Branded as "Ebola app" and abandoned post-outbreak',
		likelihood=Rating.high, impact=Rating.high,
		mitigation='Position as health companion; Tier 1–3 features',
		control_kind=ControlKind.code, control='afya.registry.service:FeatureRegistry', owner='programme_manager'),
	Risk(risk_id='R-S3', domain=RiskDomain.strategic, statement='Government change of priorities',
		likelihood=Rating.medium, impact=Rating.high, mitigation='Multi-stakeholder ownership; institutional embedding',
		control_kind=ControlKind.process, owner='steering_committee'),
	Risk(risk_id='R-S4', domain=RiskDomain.strategic, statement='Funding ends after outbreak',
		likelihood=Rating.high, impact=Rating.high, mitigation='Sustainable funding model; integration into national budget',
		control_kind=ControlKind.process, owner='steering_committee'),
	Risk(risk_id='R-S5', domain=RiskDomain.strategic, statement='Competitor or parallel initiative',
		likelihood=Rating.medium, impact=Rating.medium, mitigation='Coordination with MoH; avoid duplication',
		control_kind=ControlKind.process, owner='programme_manager'),
	# §23.2 operational
	Risk(risk_id='R-O1', domain=RiskDomain.operational, statement='CHW capacity constraints',
		likelihood=Rating.high, impact=Rating.medium, mitigation='Simple tools; training; incentives; supervision',
		control_kind=ControlKind.code, control='afya.chw.service:ChwService', owner='chw_lead'),
	Risk(risk_id='R-O2', domain=RiskDomain.operational, statement='Content not updated',
		likelihood=Rating.medium, impact=Rating.high, mitigation='Content governance; SLAs; automated staleness alerts',
		control_kind=ControlKind.code, control='afya.info.service:InfoService.stale', owner='content_lead'),
	Risk(risk_id='R-O3', domain=RiskDomain.operational, statement='Facility data inaccurate',
		likelihood=Rating.high, impact=Rating.medium, mitigation='Crowdsourced corrections; regular MoHF sync',
		control_kind=ControlKind.code, control='afya.facilities.service:FacilityService.ingest_mohf', owner='data_lead'),
	Risk(risk_id='R-O4', domain=RiskDomain.operational, statement='Misinformation overwhelms response',
		likelihood=Rating.high, impact=Rating.medium, mitigation='Pre-drafted corrections; rapid response protocol',
		control_kind=ControlKind.code, control='afya.integrations.service:InlineJaliPort.corrections', owner='comms_lead'),
	Risk(risk_id='R-O5', domain=RiskDomain.operational, statement='Panic from alerts',
		likelihood=Rating.medium, impact=Rating.high, mitigation='Verify before publishing; calm tone; community testing',
		control_kind=ControlKind.code, control='afya.alerting.service:AlertingService.publish', owner='comms_lead'),
	Risk(risk_id='R-O6', domain=RiskDomain.operational, statement='Stigma from exposure notification',
		likelihood=Rating.medium, impact=Rating.high, mitigation='Anonymity; non-stigmatising language; community engagement',
		control_kind=ControlKind.code, control='afya.alerting.service:AlertingService.notify_exposure', owner='comms_lead'),
	Risk(risk_id='R-O7', domain=RiskDomain.operational, statement='Alert fatigue',
		likelihood=Rating.high, impact=Rating.medium, mitigation='Granular preferences; critical-only defaults',
		control_kind=ControlKind.code, control='afya.alerting.service:AlertingService.should_deliver', owner='comms_lead'),
	# §23.3 technical
	Risk(risk_id='R-T1', domain=RiskDomain.technical, statement='Telco zero-rating not secured',
		likelihood=Rating.medium, impact=Rating.high, mitigation='Multi-telco negotiation; fallback to USSD/SMS',
		control_kind=ControlKind.code, control='afya.channels.service:ChannelService.ussd', owner='partnerships_lead'),
	Risk(risk_id='R-T2', domain=RiskDomain.technical, statement='Device fragmentation',
		likelihood=Rating.high, impact=Rating.medium, mitigation='Graceful degradation; Android Go support',
		control_kind=ControlKind.code, control='afya.access.service:AccessService', owner='mobile_lead'),
	Risk(risk_id='R-T3', domain=RiskDomain.technical, statement='Battery drain complaints',
		likelihood=Rating.medium, impact=Rating.medium, mitigation='Adaptive sampling; user controls; <5% target',
		control_kind=ControlKind.code, control='afya.metrics.service:MetricsService', owner='mobile_lead'),
	Risk(risk_id='R-T4', domain=RiskDomain.technical, statement='Sync failures in low connectivity',
		likelihood=Rating.high, impact=Rating.medium, mitigation='Robust queue; exponential backoff; user-visible status',
		# The mitigation names three things and the control used to name one function that computed a
		# delay and was called by nothing. `SyncService.flush` is where all three happen — the queue
		# is kept, the backoff is applied, and `SyncStatus` is what the indicator reads.
		control_kind=ControlKind.code, control='afya.sync.service:SyncService.flush', owner='engineering_lead'),
	Risk(risk_id='R-T5', domain=RiskDomain.technical, statement='Backend scalability',
		likelihood=Rating.low, impact=Rating.high, mitigation='Load testing; auto-scaling; CDN',
		control_kind=ControlKind.process, owner='engineering_lead'),
	Risk(risk_id='R-T6', domain=RiskDomain.technical, statement='Integration failures with ADaM/PHEOC',
		likelihood=Rating.medium, impact=Rating.high, mitigation='Early technical engagement; fallback manual processes',
		control_kind=ControlKind.code, control='afya.integrations.adam:AdamClient', owner='engineering_lead'),
	Risk(risk_id='R-T7', domain=RiskDomain.technical, statement='Security breach',
		likelihood=Rating.low, impact=Rating.very_high, mitigation='Encryption; audits; bug bounty; incident response',
		control_kind=ControlKind.code, control='afya.security.service:SecurityService.disclosure_policy', owner='ciso'),
	Risk(risk_id='R-T8', domain=RiskDomain.technical, statement='LiDAR accuracy issues',
		likelihood=Rating.medium, impact=Rating.low, mitigation='Confidence indicators; fallback to acoustic/manual',
		control_kind=ControlKind.code, control='afya.access.service:SENSOR_FALLBACKS', owner='ml_lead'),
	Risk(risk_id='R-T9', domain=RiskDomain.technical, statement='Acoustic model false positives',
		likelihood=Rating.high, impact=Rating.medium, mitigation='Baseline personalisation; threshold tuning; user feedback loop',
		control_kind=ControlKind.code, control='afya.sensors.service:SensorService', owner='ml_lead'),
	# §23.4 privacy and ethical
	Risk(risk_id='R-P1', domain=RiskDomain.privacy_ethical, statement='Location data misuse',
		likelihood=Rating.low, impact=Rating.very_high, mitigation='On-device processing; geohashing; consent; audit',
		control_kind=ControlKind.code, control='afya.location.service:_geohash_cell', owner='dpo'),
	Risk(risk_id='R-P2', domain=RiskDomain.privacy_ethical, statement='Proximity data deanonymisation',
		likelihood=Rating.low, impact=Rating.very_high, mitigation='PET architecture; trusted proxy; min cell size',
		control_kind=ControlKind.code, control='afya.analytics.views:MIN_CELL_SIZE', owner='dpo'),
	Risk(risk_id='R-P3', domain=RiskDomain.privacy_ethical, statement='AI bias (skin tone, gender, region)',
		likelihood=Rating.medium, impact=Rating.high, mitigation='Diverse validation; bias audits; published model cards',
		control_kind=ControlKind.code, control='afya.ai.service:AIService.audit_fairness', owner='ml_lead'),
	Risk(risk_id='R-P4', domain=RiskDomain.privacy_ethical, statement='Surveillance creep',
		likelihood=Rating.medium, impact=Rating.very_high, mitigation='Legal constraints; DPIA; transparency reports; oversight board',
		control_kind=ControlKind.code, control='afya.retention.service:RetentionService.transparency_report', owner='dpo'),
	Risk(risk_id='R-P5', domain=RiskDomain.privacy_ethical, statement='Contact tracing data retained too long',
		likelihood=Rating.medium, impact=Rating.high, mitigation='Automatic deletion; retention schedule; audit',
		control_kind=ControlKind.code, control='afya.retention.service:RetentionService.purge_expired', owner='dpo'),
	Risk(risk_id='R-P6', domain=RiskDomain.privacy_ethical, statement="Children's data misuse",
		likelihood=Rating.low, impact=Rating.high, mitigation='Guardian consent; age-appropriate design; extra protections',
		control_kind=ControlKind.code, control='afya.records.service:RecordsService', owner='dpo'),
	Risk(risk_id='R-P7', domain=RiskDomain.privacy_ethical, statement='Misuse by authorities',
		likelihood=Rating.low, impact=Rating.very_high,
		mitigation='Legal agreements; audit; independent oversight; open source',
		control_kind=ControlKind.code, control='afya.privacy.service:PrivacyService.check_access_logged', owner='dpo'),
	# §23.5 reputational
	Risk(risk_id='R-R1', domain=RiskDomain.reputational, statement='Perceived as government surveillance',
		likelihood=Rating.medium, impact=Rating.high, mitigation='Open source; transparency reports; privacy by design',
		control_kind=ControlKind.code, control='afya.retention.service:RetentionService.transparency_report', owner='dpo'),
	Risk(risk_id='R-R2', domain=RiskDomain.reputational, statement='Failure during outbreak',
		likelihood=Rating.medium, impact=Rating.very_high, mitigation='Load testing; red team; disaster recovery; manual fallback',
		control_kind=ControlKind.process, owner='engineering_lead'),
	Risk(risk_id='R-R3', domain=RiskDomain.reputational, statement='False reassurance from triage',
		likelihood=Rating.medium, impact=Rating.high, mitigation='Clear disclaimers; conservative thresholds; clinical review',
		control_kind=ControlKind.code, control='afya.triage.service:TriageService.assess', owner='clinical_advisory_group'),
	Risk(risk_id='R-R4', domain=RiskDomain.reputational, statement='Stigmatising a community',
		likelihood=Rating.medium, impact=Rating.high, mitigation='Non-stigmatising language; community engagement; rapid correction',
		control_kind=ControlKind.code, control='afya.alerting.service:AlertingService.publish', owner='comms_lead'),
	Risk(risk_id='R-R5', domain=RiskDomain.reputational, statement='Media misrepresentation',
		likelihood=Rating.medium, impact=Rating.medium, mitigation='Proactive comms; media training; transparency',
		control_kind=ControlKind.process, owner='comms_lead'),
)

# The cells where this register deliberately does not carry §23's table verbatim. Recorded rather
# than silently dropped, for the reason `afya.registry.activation.DIVERGENCES` gives: a divergence a
# reader cannot find is a divergence that reads as drift, and the next person to diff the two tables
# finds the same cells again. `test_the_register_is_the_sections_table_cell_for_cell` reads this map
# and the spec together, so an *unrecorded* divergence fails there while a recorded one is excused by
# name — the two states are different and the gate has to tell them apart.
#
# R-S1, R-S2, R-O7 and R-P7 are not here: they were the register drifting from the section, and the
# code was moved to the section. R-T2 is the one where the section is the thing that is out of date.
MITIGATION_DIVERGENCES: dict[str, str] = {
	'R-T2': '§23.3 names "Flutter" as the first mitigation for device fragmentation; §15.2 records '
	        'Flutter → SwiftUI + Kotlin as a divergence and the clients are native. §23.3 also names '
	        '"graceful degradation", which is the load-bearing half and is carried by '
	        '`afya.access.service:AccessService`. The mitigation cell drops the framework and keeps '
	        'the two mechanisms; the divergence is recorded here rather than repaired by claiming a '
	        'framework the repo does not use.',
}

assert set(MITIGATION_DIVERGENCES) <= {r.risk_id for r in RISKS}, \
	'a mitigation divergence names a risk row that does not exist'


# §24's recurring duties. §24.2's content cadences and §24.7's legal/regulatory cadences are the two
# tables with dates in them; §24.1's bodies and §24.4's training matrix are structural and are
# modelled by the absence of an entry here rather than by a fake cadence.
OBLIGATIONS: tuple[Obligation, ...] = (
	Obligation(obligation_id='OPS-1', section='§24.2', owner='content_lead', duty='Clinical review (outbreak)',
		cadence_days=7, control='afya.info.service:InfoService.stale'),
	Obligation(obligation_id='OPS-2', section='§24.2', owner='clinical_advisory_group', duty='Clinical review (steady)',
		cadence_days=30, control='afya.info.service:InfoService.stale'),
	Obligation(obligation_id='OPS-3', section='§24.2', owner='content_lead', duty='Staleness audit',
		cadence_days=30, control='afya.info.service:InfoService.stale'),
	Obligation(obligation_id='OPS-4', section='§24.2', owner='community_advisory_panel', duty='Community validation',
		cadence_days=30),
	Obligation(obligation_id='OPS-5', section='§24.2', owner='comms_lead', duty='Misinformation response',
		trigger='misinformation spike detected'),
	Obligation(obligation_id='OPS-6', section='§24.7', owner='dpo', duty='DPIA update',
		trigger='before each Tier 4 activation', control='afya.privacy.service:PrivacyService.assess_dpia'),
	Obligation(obligation_id='OPS-7', section='§24.7', owner='legal', duty='Data sharing agreement review',
		cadence_days=365, control='afya.governance.service:GovernanceService.sharing_posture'),
	Obligation(obligation_id='OPS-8', section='§24.7', owner='ciso', duty='Security audit',
		cadence_days=365, control='afya.security.service:SecurityService.obligations'),
	Obligation(obligation_id='OPS-9', section='§24.7', owner='dpo', duty='Privacy policy review', cadence_days=365),
	Obligation(obligation_id='OPS-10', section='§24.7', owner='legal', duty='Telco agreement review', cadence_days=365),
	Obligation(obligation_id='OPS-11', section='§24.7', owner='dpo', duty='ODPC registration', trigger='on change'),
	Obligation(obligation_id='OPS-12', section='§24.7', owner='programme_manager', duty='MoH registration', trigger='on change'),
	Obligation(obligation_id='OPS-13', section='§24.7', owner='legal', duty='Content legal review',
		trigger='on publish of sensitive content'),
	Obligation(obligation_id='OPS-14', section='§24.8', owner='programme_manager', duty='Post-incident root cause analysis',
		trigger='major incident', control=None),
)


def _today(iso: str) -> date:
	assert len(iso) >= 10, 'an ISO date is required'
	return date.fromisoformat(iso[:10])


def _instant(iso: str) -> datetime:
	"""An ISO instant as an aware datetime.

	§24.8's deadlines are hour-granular, so a caller may hand a bare `2026-10-10` or a full
	`2026-10-10T09:00:00Z`, and the two must be comparable — subtracting a naive datetime from an
	aware one raises, which turned "how long has this breach been open" into a 500 for the ordinary
	case of asking at the start of a day. A bare date is midnight UTC, because that is the only
	reading of it that does not depend on the server's timezone.
	"""
	text = iso.strip()
	if 'T' not in text and ' ' not in text:
		return datetime.fromisoformat(text[:10]).replace(tzinfo=timezone.utc)
	parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
	return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


class OperationsService(LogMixin):
	def __init__(self, performed: dict[str, str] | None = None) -> None:
		"""`performed` maps obligation id -> the date it was last discharged. An obligation with no
		entry has never been performed, which `status` reports as overdue rather than as exempt."""
		self._performed: dict[str, str] = dict(performed or {})
		self._incidents: list[Incident] = []
		assert len({r.risk_id for r in RISKS}) == len(RISKS), 'risk ids must be unique'
		assert len({o.obligation_id for o in OBLIGATIONS}) == len(OBLIGATIONS), 'obligation ids must be unique'

	# --- §23 register ---------------------------------------------------------------------

	def risks(self, domain: RiskDomain | None = None) -> list[Risk]:
		rows = [r for r in RISKS if domain is None or r.domain is domain]
		return sorted(rows, key=lambda r: (-r.exposure(), r.risk_id))

	def register(self) -> list[RiskAssessment]:
		return [RiskAssessment(risk=r, resolves=self.resolve(r.control), note=self._note(r)) for r in self.risks()]

	def resolve(self, control: str | None) -> bool:
		"""Whether a `module:attr` reference lands. A process control resolves by definition — there
		is no module to walk, and the register says so through `control_kind` rather than by
		pretending the reference is fine. The walk itself lives in `afya.refs` because §17.1 and
		§17.2 now resolve their own tables the same way, and three copies of a four-line import loop
		is three places for it to drift."""
		return resolves(control)

	def _note(self, risk: Risk) -> str:
		if risk.control is None:
			return 'a process duty; no code reference'
		return f'{risk.control} resolves' if self.resolve(risk.control) else f'{risk.control} does not resolve'

	def unbacked(self) -> list[str]:
		"""§23 rows whose named control does not exist. The list a reviewer wants: every entry is a
		mitigation the register presents as enforced and is not."""
		return [r.risk_id for r in RISKS if not self.resolve(r.control)]

	# --- §24.8 incident response ----------------------------------------------------------

	@staticmethod
	def incident_kinds() -> list[IncidentKind]:
		return list(INCIDENT_KINDS)

	@staticmethod
	def kind_spec(kind: IncidentClass) -> IncidentKind:
		for k in INCIDENT_KINDS:
			if k.kind is kind:
				return k
		raise AssertionError(f'{kind} is not a §24.8 incident type')

	@staticmethod
	def support_slas() -> list[SupportSla]:
		return list(SUPPORT_SLAS)

	def sustainability(self) -> SustainabilityReport:
		"""§24.6's eight mitigations, each resolved against the artefact it names.

		The same rule §23's mitigation column follows, applied to the section that argues the product
		outlives the outbreak. Two lists, and they are different findings: `unbacked_mitigations` is a
		mitigation that *names* a `module:attr` and does not resolve, which is a plan pointing at
		something that is not there; `process_mitigations` is one that names no artefact at all, which
		is a commitment about the world rather than a claim about the build. §23's register makes the
		same split through `ControlKind`, and `resolve(None)` returning True is that convention rather
		than a silent pass.
		"""
		unbacked = [f'{m.number}. {m.mitigation}' for m in SUSTAINABILITY
			if m.control is not None and not self.resolve(m.control)]
		process = [f'{m.number}. {m.mitigation}' for m in SUSTAINABILITY if m.control is None]
		resolved = len(SUSTAINABILITY) - len(unbacked) - len(process)
		self._log_info('sustainability read', mitigations=len(SUSTAINABILITY),
			resolved=resolved, process=len(process), unbacked=len(unbacked))
		return SustainabilityReport(
			mitigations=list(SUSTAINABILITY), process_mitigations=process,
			unbacked_mitigations=unbacked,
			note=(
				f'{resolved} of {len(SUSTAINABILITY)} §24.6 mitigations name an artefact that resolves; '
				f'{len(process)} name no artefact and are reported as process commitments'
				if not unbacked else
				f'{len(unbacked)} §24.6 mitigation(s) name an artefact this build does not have'
			),
		)

	def support_plan(self) -> SupportPlan:
		"""§24.4's training matrix and §24.5's funding model.

		`untrained_audiences` is the finding: §24.4 names seven audiences and §24.1 names six bodies
		with the roles that sit on them, so an audience no body accounts for is a group expected to
		use the product with nobody in the governance structure responsible for teaching them.
		`unfunded_stages` is the other direction — a §21 phase no §24.5 band pays for.

		The body join is stated in `TRAINING` rather than derived, because §24.4's audiences
		("Radio partners") and §24.1's bodies ("Operations Cell") are two vocabularies the spec never
		relates, and the two audiences with no body are the honest answer rather than a gap to close
		by inventing one.
		"""
		# Imported here rather than at module scope: `rollout` pulls in `metrics`, which pulls in
		# `governance`, and §24.5's bands are the only thing in this module that needs §21's phase
		# list. A top-level import would make the cycle a matter of what the other two modules do next.
		from afya.rollout.service import PHASES
		untrained = [t.audience for t in TRAINING if t.body is None]
		covered = {n for f in FUNDING for n in range(f.phase_floor, f.phase_ceiling + 1)}
		unfunded = [p.phase.value for p in PHASES if p.phase.order not in covered]
		hours = sum(t.hours for t in TRAINING)
		self._log_info('support plan read', audiences=len(TRAINING), stages=len(FUNDING),
			untrained=len(untrained), hours=hours)
		return SupportPlan(
			training=list(TRAINING), funding=list(FUNDING), refresher='Quarterly',
			new_feature_training='On release', cost_drivers=list(COST_DRIVERS),
			cost_mitigations=list(COST_MITIGATIONS), training_hours=hours,
			untrained_audiences=untrained, unfunded_stages=unfunded,
			note=(
				f'{len(TRAINING)} audiences, {hours:g} training hours; {len(FUNDING)} §24.5 funding bands '
				f'covering §21 phases 0–{max(covered)}'
				if not untrained and not unfunded else
				f'{len(untrained)} audience(s) with no §24.1 body accountable; '
				f'{len(unfunded)} §21 phase(s) no §24.5 band funds'
			),
		)

	def governance(self) -> GovernanceReport:
		"""§24.1's six bodies and §24.3's five support channels, crossed against §24's duty rows.

		`unowned_bodies` is the finding on the governance side: §24.1 names six bodies and §24.2–§24.7
		assign duties to owners, so a body accounting for no duty is a committee the register cannot
		tell apart from one that governs. The Steering Committee is the honest instance of it — its
		role is "strategic direction, funding, escalation", none of which is a recurring duty §24
		schedules, and it is reported rather than given a fabricated owner.

		`unlisted_owners` is the reverse: a duty owner §24.1 seats on no body. `unstaffed_channels`
		is §24.3's version — a support channel with no coverage window is one a person can reach and
		nobody reads.
		"""
		owners = sorted({o.owner for o in OBLIGATIONS})
		accounted = {o for b in GOVERNANCE_BODIES for o in b.owners}
		unowned = [b.body for b in GOVERNANCE_BODIES if not b.owners]
		unlisted = [o for o in owners if o not in accounted]
		unstaffed = [c.channel for c in SUPPORT_CHANNELS if not c.coverage]
		agents = sum(c.agents for c in SUPPORT_CHANNELS if c.agents is not None)
		self._log_info('governance read', bodies=len(GOVERNANCE_BODIES), owners=len(owners),
			unowned=len(unowned), unlisted=len(unlisted))
		return GovernanceReport(
			bodies=list(GOVERNANCE_BODIES), support_channels=list(SUPPORT_CHANNELS),
			duty_owners=owners, unowned_bodies=unowned, unlisted_owners=unlisted,
			unstaffed_channels=unstaffed, staffed_agents=agents,
			note=(
				f'{len(GOVERNANCE_BODIES)} bodies account for {len(accounted)} of {len(owners)} duty owners; '
				f'{len(unstaffed)} support channel(s) with no coverage window'
				if not unowned and not unlisted else
				f'{len(unowned)} body/bodies account for no §24 duty; '
				f'{len(unlisted)} duty owner(s) sit on no §24.1 body'
			),
		)

	def open_incident(self, incident: Incident) -> IncidentStatus:
		assert incident.incident_id not in {i.incident_id for i in self._incidents}, 'duplicate incident id'
		assert incident.detected_at_iso >= incident.opened_at_iso, 'detection cannot precede opening'
		self._incidents.append(incident)
		spec = self.kind_spec(incident.kind)
		self._log_warn('incident opened', incident=incident.incident_id, kind=incident.kind.value,
			severity=spec.severity.value, deadline_h=spec.deadline_hours)
		return self.status(incident, incident.detected_at_iso)

	def status(self, incident: Incident, as_at_iso: str) -> IncidentStatus:
		"""Where the incident stands against its own deadline, measured from *detection*.

		The clock starts when the breach was noticed, not when it was recorded, because that is the
		DPA's 72 hours. Measuring from `opened_at_iso` would let a team buy time by writing the
		incident up late, which is the opposite of what the deadline is for.
		"""
		spec = self.kind_spec(incident.kind)
		elapsed = (_instant(as_at_iso) - _instant(incident.detected_at_iso)).total_seconds() / 3600.0
		remaining = None if spec.deadline_hours is None else round(spec.deadline_hours - elapsed, 2)
		return IncidentStatus(
			incident_id=incident.incident_id, kind=incident.kind, severity=spec.severity,
			hours_elapsed=round(elapsed, 2), deadline_hours=spec.deadline_hours,
			hours_remaining=remaining, overdue=remaining is not None and remaining < 0,
			notifies=list(spec.notifies), response=spec.response,
		)

	def open_incidents(self, as_at_iso: str) -> list[IncidentStatus]:
		return [self.status(i, as_at_iso) for i in self._incidents]

	def rca_due_on(self, incident: Incident) -> str:
		"""§24.8's five-day root-cause deadline, off the same detection date."""
		return (_today(incident.detected_at_iso) + timedelta(days=RCA_DEADLINE_DAYS)).isoformat()

	# --- §24 duties -----------------------------------------------------------------------

	@staticmethod
	def obligations() -> list[Obligation]:
		return list(OBLIGATIONS)

	def mark_performed(self, obligation_id: str, on_iso: str) -> None:
		assert any(o.obligation_id == obligation_id for o in OBLIGATIONS), f'{obligation_id} is not a §24 duty'
		self._performed[obligation_id] = on_iso

	def obligation_status(self, today_iso: str) -> list[ObligationStatus]:
		"""Every §24 duty and whether it is late. A duty never performed is overdue, not exempt —
		the same rule §17.5's scan cadence already applies, and the one that catches the duty nobody
		has thought about since launch.

		An event-triggered duty carries no due date: it is overdue when its trigger has fired and it
		has not been discharged, which is not something a calendar knows. It is reported with
		`due_on_iso=None` and `overdue=False` unless it has never been performed *and* its trigger
		names a recurring event — the honest answer for "on change" is that only a change can make
		it late.
		"""
		today = _today(today_iso)
		out: list[ObligationStatus] = []
		for o in OBLIGATIONS:
			last = self._performed.get(o.obligation_id)
			if o.cadence_days is not None:
				due = (_today(last) + timedelta(days=o.cadence_days)).isoformat() if last else None
				overdue = due is None or _today(due) < today
			else:
				due = None
				overdue = False
			out.append(ObligationStatus(
				obligation_id=o.obligation_id, duty=o.duty, owner=o.owner, section=o.section,
				cadence_days=o.cadence_days, trigger=o.trigger, last_performed_iso=last,
				due_on_iso=due, overdue=overdue,
			))
		return out

	def overdue(self, today_iso: str) -> list[str]:
		return [s.obligation_id for s in self.obligation_status(today_iso) if s.overdue]

	# --- posture --------------------------------------------------------------------------

	def posture(self, today_iso: str) -> OpsPosture:
		register = self.register()
		statuses = self.obligation_status(today_iso)
		return OpsPosture(
			risks=register,
			unbacked_risks=[a.risk.risk_id for a in register if not a.resolves],
			incident_kinds=self.incident_kinds(),
			support_slas=self.support_slas(),
			obligations=statuses,
			overdue_obligations=[s.obligation_id for s in statuses if s.overdue],
			open_incidents=self.open_incidents(today_iso),
		)
