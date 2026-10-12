"""Data residency enforcement, sharing agreements, capacity reporting (spec §15.3, §15.4, §17.7).

The three sections this module covers were prose in the spec and nothing in the code. §15.3 said
"no data transfer outside African jurisdictions without explicit legal review" and every outbound
client posted wherever it was configured; §17.7 listed seven agreements that had to exist and no
code knew whether any did; §15.4 gave thirteen targets and nothing measured any of them.

Each is now a decision the process makes and can be asked about, not a paragraph a reader has to
trust.
"""
from afya.governance.views import (
	RESIDENCY_RULES, HOST_JURISDICTIONS, LEGAL_REVIEW_EXCEPTION, AgreementParty, ArchitectureComponent,
	CapacityCheck, CapacityReport, DataClass, DataSharingAgreement, Jurisdiction, OpenQuestion,
	ResidencyDecision, ScaleTarget, StackLayer, StackReport, StackStatus,
)
from afya.logmixin import LogMixin
from afya.refs import resolves

# §15.4 table, verbatim. `higher_is_better` is False for latency and the recovery times, where
# being under the target is the pass — a report that got this backwards would pass a 3-second p95.
SCALE_TARGETS: tuple[tuple[str, float, str, str, bool], ...] = (
	('registered_users', 10_000_000, 'users', '§15.4', True),
	('daily_active_users_outbreak', 2_000_000, 'users', '§15.4', True),
	('daily_active_users_steady', 500_000, 'users', '§15.4', True),
	('concurrent_api_requests', 50_000, 'requests', '§15.4', True),
	('triage_requests_per_second', 500, 'requests/s', '§15.4', True),
	('push_notifications_per_hour', 5_000_000, 'notifications/h', '§15.4', True),
	('sms_per_day', 10_000_000, 'messages/day', '§15.4', True),
	('whatsapp_per_day', 2_000_000, 'messages/day', '§15.4', True),
	('sensor_ingest_per_day', 100_000_000, 'events/day', '§15.4', True),
	('api_latency_p95_ms', 300, 'ms', '§15.4', False),
	('uptime_pct', 99.9, 'percent', '§15.4', True),
	('recovery_time_hours', 1, 'hours', '§15.4', False),
	('recovery_point_minutes', 15, 'minutes', '§15.4', False),
)


class GovernanceService(LogMixin):
	def __init__(self, agreements: list[DataSharingAgreement] | None = None) -> None:
		self._agreements: dict[AgreementParty, DataSharingAgreement] = {a.party: a for a in (agreements or [])}
		self._log_info('governance initialised', agreements=len(self._agreements))

	# --- Appendix D: the open questions ------------------------------------------------------
	# The last block of the spec nothing carried. Its seven rows were cited in prose three times
	# (`rollout/service.py`, `registry/gate.py`, `test_activation.py`) and held as data nowhere, so
	# the list of decisions the spec says are *required* was itself a thing a reader had to
	# remember. Two of the seven are not open in the tree at all: question 4's provider choice has
	# already been made in the negative — `HOST_JURISDICTIONS` classifies every AWS and Azure host
	# as outside Africa, so §15.3's own example option is refused for the classes §15.3 protects —
	# and question 7's cap is a literal 730 at `privacy/service.py:257` whose provenance the spec
	# states and the code did not. Carrying the rows makes both visible; neither is repaired here,
	# because both are the owner's call and this module reports rather than decides.
	OPEN_QUESTIONS: tuple[OpenQuestion, ...] = (
		OpenQuestion(number=1,
			question='Product owner entity (MoH Digital Health Agency vs implementing partner) — listed TBD',
			blocks='governance, contracting', live_at=None, assumed=None),
		OpenQuestion(number=2,
			question='Official hotline codes/platform names/case counts require MoH/PHEOC validation '
				'(see Verification Note)',
			blocks='content, USSD menus, INF-006', live_at='afya.info.service:HOTLINES',
			assumed='719, unverified — `HotlineInfo.verified` is False on both rows and the age of '
				'the last check travels with the number'),
		OpenQuestion(number=3,
			question='Tier-4 activation protocol: who holds PHEOC authorization + flag authority + '
				'DPIA sign-off?',
			blocks='surveillance gate', live_at='afya.registry.service:Tier4Activation',
			assumed='three keys held by whoever calls the gate — the model records that they were '
				'held, not by whom, so the protocol the row asks for is the one thing the gate '
				'cannot state'),
		OpenQuestion(number=4,
			question='Cloud provider + data residency final selection (AWS Africa vs Azure South '
				'Africa vs on-prem)',
			blocks='§15.3, DPIA', live_at='afya.governance.views:HOST_JURISDICTIONS',
			assumed='none — every AWS and Azure host is classified outside_africa, so §15.3\'s own '
				'option is refused for case management, contact tracing and citizen personal data; '
				'no host in the table is classified african_union'),
		OpenQuestion(number=5,
			question='Unleash instance vs internal feature flags for Tier-4 control',
			blocks='§15.2', live_at='afya.registry.service:FeatureRegistry',
			assumed="internal — the three-key gate; §15.2's stack row records the divergence"),
		OpenQuestion(number=6,
			question='Telco zero-rating agreements for CHAN-001', blocks='distribution',
			live_at='afya.channels.cost:zero_rating_gaps',
			assumed='unagreed — with no rules pulled the two zero-rating channels report unverified, '
				'not free; the check exists so the claim cannot be made without the agreement'),
		OpenQuestion(number=7,
			question='Retention policy per data type needs ODPC sign-off (24-month cap assumed in code)',
			blocks='privacy service', live_at='afya.privacy.service:RETENTION_CAP_DAYS',
			assumed='730 days for consent-based records — the cap the row names, enforced against '
				'every consent record whose basis is not a mandatory notification'),
	)

	def open_questions(self) -> list[OpenQuestion]:
		"""Appendix D's seven rows, each with whether the place it bites resolves.

		Nothing here is a verdict on the decision. The list answers "what is still open and where
		does it land", which is the question a reader of the appendix is actually asking — and
		`unresolved` is the finding, because a row naming a place that no longer exists is a
		blocker someone will believe is tracked when the code it names is gone.
		"""
		return list(self.OPEN_QUESTIONS)

	@staticmethod
	def unresolved_questions() -> list[int]:
		return [q.number for q in GovernanceService.OPEN_QUESTIONS
		        if q.live_at is not None and not resolves(q.live_at)]

	# --- §15.3 residency ---------------------------------------------------------------------

	@staticmethod
	def jurisdiction_of(host: str) -> Jurisdiction:
		"""Where a host sits. An unrecognised host is *not* assumed safe: it is outside Africa until
		someone adds the rule, because the default that fails open is the one that ships a transfer
		nobody reviewed."""
		bare = host.split('//')[-1].split('/')[0].split(':')[0].lower()
		best: tuple[int, Jurisdiction] | None = None
		for suffix, juris in HOST_JURISDICTIONS:
			if bare.endswith(suffix) and (best is None or len(suffix) > best[0]):
				best = (len(suffix), juris)
		return best[1] if best else Jurisdiction.outside_africa

	def residency_decision(self, party: str, host: str, data_class: DataClass) -> ResidencyDecision:
		assert party and host, 'a residency decision needs a party and a host'
		juris = self.jurisdiction_of(host)
		if juris in RESIDENCY_RULES[data_class]:
			return ResidencyDecision(party=party, host=host, jurisdiction=juris, data_class=data_class,
				allowed=True, reason=f'{data_class.value} may be processed in {juris.value} (§15.3)')
		# §15.3's exception: outside-Africa is allowed for a class under legal review when the
		# §17.7 agreement with this party is signed. The agreement *is* the legal review.
		if data_class in LEGAL_REVIEW_EXCEPTION and self._party_cleared(party):
			self._log_warn('residency exception invoked', party=party, host=host, data_class=data_class.value)
			return ResidencyDecision(party=party, host=host, jurisdiction=juris, data_class=data_class,
				allowed=True,
				reason=f'{data_class.value} to {juris.value} allowed under the signed §17.7 agreement with {party}')
		self._log_warn('residency refusal', party=party, host=host, data_class=data_class.value)
		return ResidencyDecision(party=party, host=host, jurisdiction=juris, data_class=data_class,
			allowed=False,
			reason=f'{data_class.value} may not leave {sorted(j.value for j in RESIDENCY_RULES[data_class])}')

	def _party_cleared(self, party: str) -> bool:
		"""Whether a party string names a §17.7 party with a signed agreement. A party we have no
		agreement with is not cleared, and a free-text party name clears nothing."""
		try:
			return self.may_share(AgreementParty(party))
		except ValueError:
			return False

	# Each outbound wire, the party it goes to, and the class of data it carries. Kept beside the
	# clients rather than inside them: a client that asserted its own residency could be constructed
	# with the check skipped, whereas this table is audited against the deployment's real config.
	EGRESS_WIRES: tuple[tuple[str, AgreementParty, DataClass], ...] = (
		('adam', AgreementParty.ministry_of_health, DataClass.case_management),
		('pheoc', AgreementParty.ministry_of_health, DataClass.anonymised_analytics),
		('jali', AgreementParty.ministry_of_health, DataClass.citizen_personal),
		('sha', AgreementParty.ministry_of_health, DataClass.citizen_personal),
		('mohf', AgreementParty.ministry_of_health, DataClass.anonymised_analytics),
		('ppb', AgreementParty.ministry_of_health, DataClass.anonymised_analytics),
		('sms', AgreementParty.telco, DataClass.citizen_personal),
		('whatsapp', AgreementParty.meta_whatsapp, DataClass.citizen_personal),
	)

	def audit_egress(self, urls: dict[str, str]) -> list[ResidencyDecision]:
		"""Classify every configured outbound wire against §15.3.

		`urls` maps a wire name to the host its client will actually post to. A wire with no URL is
		not configured and produces no decision — but a wire with a URL pointing somewhere the class
		may not go is a refusal, which is the whole point: the deployment's env, not this file's
		defaults, decides.
		"""
		out: list[ResidencyDecision] = []
		for wire, party, data_class in self.EGRESS_WIRES:
			url = urls.get(wire, '')
			if not url:
				continue
			out.append(self.residency_decision(party.value, url, data_class))
		return out

	def egress_violations(self, urls: dict[str, str]) -> list[ResidencyDecision]:
		return [d for d in self.audit_egress(urls) if not d.allowed]

	def assert_egress_allowed(self, party: str, host: str, data_class: DataClass) -> ResidencyDecision:
		"""Raise on a transfer §15.3 forbids. The route layer calls this so the refusal happens here,
		before a request is built, rather than being discovered in a log after it was sent."""
		decision = self.residency_decision(party, host, data_class)
		assert decision.allowed, decision.reason
		return decision

	# --- §17.7 agreements --------------------------------------------------------------------

	def register(self, agreement: DataSharingAgreement) -> DataSharingAgreement:
		"""Record an agreement. The model refuses a missing §17.7 clause at construction, so reaching
		here means the purpose, scope, retention, security and audit-rights fields are all present;
		this asserts the party is one of the seven the spec names."""
		assert agreement.party in AgreementParty, f'{agreement.party} is not a §17.7 party'
		self._agreements[agreement.party] = agreement
		return agreement

	def agreement(self, party: AgreementParty) -> DataSharingAgreement | None:
		return self._agreements.get(party)

	def may_share(self, party: AgreementParty) -> bool:
		"""Whether data may be shared with a party. A missing agreement is a refusal, and an
		unsigned one is a refusal: absence and "not yet signed" are the same answer to the caller."""
		agreement = self._agreements.get(party)
		return bool(agreement and agreement.may_share())

	def unsigned(self) -> list[str]:
		return sorted(p.value for p in AgreementParty if not self.may_share(p))

	def sharing_posture(self) -> dict[str, object]:
		return {
			'parties': [p.value for p in AgreementParty],
			'registered': sorted(p.value for p in self._agreements),
			'cleared_to_share': sorted(p.value for p in AgreementParty if self.may_share(p)),
			'unsigned': self.unsigned(),
		}

	# --- §15.4 capacity ----------------------------------------------------------------------

	# --- §15.2 the stack, and §15.1 the architecture ------------------------------------------

	# §15.2's table, verbatim on the first three columns, with what the build actually runs. This is
	# the section that overstates what exists — it names Flutter, Node.js and a list of datastores,
	# and the repo ships two native clients, no Node at all, and one Postgres-protocol store — so the
	# honest form of the table is a comparison rather than a copy. `evidence` is a `module:attr`
	# reference for a layer that is code and a repo path for a layer that is configuration, and both
	# are walked: a `deferred` layer names nothing and is reported as deferred rather than unbacked.
	STACK: tuple[tuple[str, str, str, StackStatus, str | None, str | None, str | None], ...] = (
		('Mobile framework', 'Flutter', 'Single codebase for Android and iOS; strong offline support; small binary',
			StackStatus.diverged, 'SwiftUI + Kotlin', 'ios/', 'two native clients, so every string exists twice'),
		# §15.2 names an ACID offline-first store and §15.1 draws the local data layer as one; the
		# clients cache the last good response in SharedPreferences and UserDefaults, which is a
		# cache rather than a database and has neither transactions nor a schema. Reporting this as
		# shipped would be the stack table making exactly the claim it exists to check.
		('Local DB', 'SQLite + Room (Android), Core Data (iOS)', 'Proven, ACID-compliant, offline-first',
			StackStatus.diverged, 'SharedPreferences + UserDefaults',
			'android/app/src/main/java/ke/go/health/afyayangu/BackendClient.kt',
			'last-good-response cache, not an ACID store'),
		('On-device ML', 'TensorFlow Lite, ONNX Runtime Mobile', 'Lightweight, mature, supports the required models',
			StackStatus.shipped, 'ONNX Runtime', 'afya.ml.cough:YamnetCoughEngine', None),
		('Backend runtime', 'Node.js (Fastify) + Python (FastAPI)', 'Node for APIs, Python for ML and data pipelines',
			StackStatus.diverged, 'Python (FastAPI) only', 'afya.service:create_app', 'no Node process runs'),
		('Primary DB', 'PostgreSQL 16', 'Robust, open-source, mature ecosystem',
			StackStatus.shipped, 'PostgreSQL via asyncpg', 'afya.persistence.postgres_store:PostgresStore', None),
		('Geospatial', 'PostGIS', 'Geofencing, geohashing, spatial queries',
			StackStatus.diverged, 'application-level haversine', 'afya.surveillance.service:SurveillanceService.geofences_at',
			'no PostGIS extension is required by any migration'),
		('Time-series', 'TimescaleDB', 'Sensor metrics, monitoring diaries',
			StackStatus.deferred, None, None, 'sensor rows land in the primary store'),
		('Cache / queue', 'Redis', 'Sessions, rate limiting, job queues',
			StackStatus.deferred, None, None, None),
		('Object storage', 'S3-compatible (MinIO on-prem option)', 'Photos, documents, exports',
			StackStatus.shipped, 'local filesystem port', 'afya.evidence.service:EvidenceService', 'S3/MinIO is a port swap'),
		('Search', 'OpenSearch', 'Content search, facility search, misinformation tracking',
			StackStatus.deferred, None, None, None),
		('Message queue', 'RabbitMQ or Kafka', 'Async processing, alert fan-out',
			StackStatus.deferred, None, None, None),
		('WhatsApp', 'Meta WhatsApp Business API', 'Official channel',
			StackStatus.shipped, 'WhatsApp Business API', 'afya.integrations.gateways:WhatsAppBusinessClient', None),
		('SMS / USSD', "Africa's Talking or Telco direct", 'Proven in Kenya',
			StackStatus.shipped, "Africa's Talking REST", 'afya.integrations.gateways:AtSmsRestSend', None),
		('Cloud', 'AWS Africa (Cape Town) or Azure South Africa', 'Data residency, low latency',
			StackStatus.shipped, 'configured per deployment', 'afya.governance.views:HOST_JURISDICTIONS',
			'residency is enforced against the deployment\'s own hosts'),
		('On-prem option', 'Kubernetes on MoH infrastructure', 'Data sovereignty option for sensitive components',
			StackStatus.shipped, 'same image, on-prem host', 'afya.governance.views:RESIDENCY_RULES',
			'case management and contact tracing may not leave Kenya'),
		('CI/CD', 'GitHub Actions + Fastlane', 'Standard, cost-effective',
			StackStatus.shipped, 'GitHub Actions', '.github/workflows/ci.yml', None),
		('Monitoring', 'Prometheus + Grafana + Sentry', 'Standard observability',
			StackStatus.deferred, None, None, None),
		('Feature flags', 'Unleash', 'Tier 4 activation control',
			StackStatus.diverged, 'in-process three-key gate', 'afya.registry.service:FeatureRegistry',
			'§11.1\'s gate is the flag system; Unleash is not deployed'),
	)

	# §15.1's diagram boxes. The diagram is a picture, so the checkable part is not the picture but
	# whether each box has a module behind it: a box drawn and not built is an architecture claim with
	# nothing under it, which is the same failure as an unbacked mitigation in a different medium.
	ARCHITECTURE: tuple[tuple[str, str, str | None, str | None], ...] = (
		('API Gateway (rate limiting, auth, routing, audit)', 'backend', 'afya.service:create_app', None),
		('Triage Service', 'backend', 'afya.triage.service:TriageService', None),
		('Case Mgmt Service', 'backend', 'afya.surveillance.service:SurveillanceService', None),
		('Exposure Notify', 'backend', 'afya.surveillance.service:ProximityToken', None),
		('Content Service', 'backend', 'afya.info.service:InfoService', None),
		('Facility Service', 'backend', 'afya.facilities.service:FacilityService', None),
		('Medicine Registry', 'backend', 'afya.medicine.service:MedicineService', None),
		('Records Service', 'backend', 'afya.records.service:RecordsService', None),
		('Alerting Service', 'backend', 'afya.alerting.service:AlertingService', None),
		('AI/ML Engine', 'backend', 'afya.ai.service:AIService', None),
		('Consent Registry', 'backend', 'afya.privacy.service:PrivacyService', None),
		('ADaM Platform', 'integration', 'afya.integrations.adam:AdamClient', None),
		('JALI Chatbot', 'integration', 'afya.integrations.service:JaliClient', None),
		('PHEOC Dashboards', 'integration', 'afya.integrations.service:PheocClient', None),
		('719 Hotline', 'integration', 'afya.emergency.service:Inline719Port', None),
		('PPB Registry', 'integration', 'afya.integrations.service:PPBClient', None),
		('MoHF Facility', 'integration', 'afya.integrations.service:MoHFFacilityClient', None),
		('SHA/NHIF', 'integration', 'afya.integrations.service:SHAClient', None),
		('EPI Schedule', 'integration', 'afya.records.views:EPI_SCHEDULE', None),
		('Lab Results', 'integration', 'afya.records.views:LabResult', None),
		('Telco Gateways', 'integration', 'afya.integrations.service:TelcoGatewayClient', None),
		('HTTPS/TLS REST API', 'sync', 'afya.service:create_app', None),
		('BLE Proximity', 'sync', 'afya.surveillance.views:ProximityToken', None),
		('SMS / USSD Gateway', 'sync', 'afya.integrations.gateways:AtSmsRestSend', None),
		('WhatsApp Business API', 'sync', 'afya.integrations.gateways:WhatsAppBusinessClient', None),
		('Hardware-Backed Keystore', 'local', None, 'the keystore is the OS\'s, reached from the clients'),
		('SQLite / Room / Core Data', 'local', None, 'client-side store, not in this repo'),
	)

	def stack_report(self) -> StackReport:
		"""§15.2's stack table and §15.1's diagram, each crossed against what the build contains.

		Three findings, and they are different questions. `unbacked_layers` is a layer claiming to
		ship with nothing in the repo pointing at it — the sharper failure, because the claim reads
		as true. `deferred_layers` is a layer the spec names and the programme has not stood up,
		which is honest and worth counting. `diverged_layers` is a layer running something else,
		which the §23.3 fragmentation mitigation and every "we run the spec's stack" sentence
		depends on being visible rather than buried.
		"""
		layers = [
			StackLayer(layer=layer, specified=specified, rationale=rationale, status=status,
				actual=actual, evidence=evidence, resolves=bool(evidence) and self._evidence_resolves(evidence),
				note=note)
			for layer, specified, rationale, status, actual, evidence, note in self.STACK
		]
		components = [
			ArchitectureComponent(name=name, band=band, module=module,
				resolves=module is not None and resolves(module), note=note)
			for name, band, module, note in self.ARCHITECTURE
		]
		return StackReport(
			layers=layers, components=components,
			unbacked_layers=[l.layer for l in layers if l.status is StackStatus.shipped and not l.resolves],
			unresolved_components=[c.name for c in components if c.module is not None and not c.resolves],
			deferred_layers=[l.layer for l in layers if l.status is StackStatus.deferred],
			diverged_layers=[l.layer for l in layers if l.status is StackStatus.diverged],
		)

	@staticmethod
	def _evidence_resolves(evidence: str) -> bool:
		"""Whether a layer's evidence points at something real.

		A `module:attr` reference is walked the way §23's mitigations are; anything else is a repo
		path and is checked against the filesystem. Both spellings are checked because the table uses
		both — a stack layer can be code or it can be configuration, and a checker that knew only the
		import form would pass every configuration layer for free.
		"""
		from pathlib import Path
		if ':' in evidence:
			return resolves(evidence)
		return (Path(__file__).resolve().parents[3] / evidence).exists()

	@staticmethod
	def targets() -> list[ScaleTarget]:
		return [ScaleTarget(metric=m, target=t, unit=u, source=s) for m, t, u, s, _ in SCALE_TARGETS]

	def capacity_report(self, observed: dict[str, float] | None = None) -> CapacityReport:
		"""Compare measured values against §15.4. A metric with no measurement is reported
		unmeasured and does not count as met — the alternative is a green dashboard built from
		nothing having been checked."""
		seen = observed or {}
		checks: list[CapacityCheck] = []
		for metric, target, unit, _source, higher_is_better in SCALE_TARGETS:
			value = seen.get(metric)
			within = None if value is None else (value >= target if higher_is_better else value <= target)
			checks.append(CapacityCheck(metric=metric, target=target, observed=value, unit=unit, within_target=within))
		unmeasured = [c.metric for c in checks if c.observed is None]
		measured = [c for c in checks if c.observed is not None]
		return CapacityReport(
			checks=checks,
			unmeasured=unmeasured,
			all_measured_targets_met=bool(measured) and all(c.met() for c in measured),
		)
