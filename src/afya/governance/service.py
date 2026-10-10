"""Data residency enforcement, sharing agreements, capacity reporting (spec §15.3, §15.4, §17.7).

The three sections this module covers were prose in the spec and nothing in the code. §15.3 said
"no data transfer outside African jurisdictions without explicit legal review" and every outbound
client posted wherever it was configured; §17.7 listed seven agreements that had to exist and no
code knew whether any did; §15.4 gave thirteen targets and nothing measured any of them.

Each is now a decision the process makes and can be asked about, not a paragraph a reader has to
trust.
"""
from afya.governance.views import (
	RESIDENCY_RULES, HOST_JURISDICTIONS, LEGAL_REVIEW_EXCEPTION, AgreementParty, CapacityCheck,
	CapacityReport, DataClass, DataSharingAgreement, Jurisdiction, ResidencyDecision, ScaleTarget,
)
from afya.logmixin import LogMixin

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
