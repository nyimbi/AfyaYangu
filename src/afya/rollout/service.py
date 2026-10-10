"""§20's growth strategy and §21's phasing, as data with the two repo claims made checkable.

The phasing table is a gate, not a calendar. §21.1 assigns each phase a tier ceiling and §11.1
gives Tier 4 a three-key gate; `status` crosses the two, so a deployment running Tier 4 while its
own plan says Phase 2 is a finding rather than a number a reader has to compare by eye.

Two of §20.2's six levers are claims about this repository — "open-source client" and "Under 15 MB"
— and `readiness` answers them from the artefacts: whether a licence file exists, and whether the
APK budget §22.5 already sets is met. The other four levers are partnership and design commitments
with nothing to inspect, and they are marked uncheckable rather than given a check that always
passes, which is the failure this module exists to avoid.
"""
from pathlib import Path

from afya.logmixin import LogMixin
from afya.metrics.service import KPIS
from afya.registry.service import FeatureRegistry
from afya.rollout.views import (
	AntiPattern, GrowthLever, LaunchStep, Phase, PhaseSpec, ReadinessReport, RetentionMechanism,
	RolloutStatus,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

# §22.5's `apk_base_size` target, read from the KPI table rather than restated — §20.2 lever 5 says
# "Under 15 MB" and §22.5 sets the same number, so a second copy here is the drift this repo keeps
# finding.
APK_BUDGET_MB: float = next(row[3] for row in KPIS if row[0] == 'apk_base_size')

# The licence files a repository can carry. §20.2 says "open-source client" and §23.5 repeats it as
# the answer to "perceived as government surveillance" — but the spec names no licence, so this
# checks that *a* licence was chosen rather than asserting which one. Picking one is the product
# owner's call (Appendix D's open questions are all this shape).
LICENCE_FILES: tuple[str, ...] = ('LICENSE', 'LICENSE.md', 'LICENSE.txt', 'COPYING')

# §21.1, verbatim. `weeks_start`/`weeks_end` are the timeline column as numbers so a phase can be
# located on a clock rather than in a string; Phase 0 starts negative, which is the point — the
# eight weeks before launch are part of the plan.
PHASES: tuple[PhaseSpec, ...] = (
	PhaseSpec(phase=Phase.phase_0_foundation, timeline='Weeks -8 to 0', objective='Build, partner, prepare',
		channels=[], max_tier=None, weeks_start=-8, weeks_end=0),
	PhaseSpec(phase=Phase.phase_1_information, timeline='Weeks 0-4', objective='Maximum reach, minimum friction',
		channels=['CHAN-000', 'CHAN-001', 'CHAN-002', 'CHAN-003', 'CHAN-004', 'CHAN-005'],
		max_tier=1, weeks_start=0, weeks_end=4),
	PhaseSpec(phase=Phase.phase_2_utility, timeline='Weeks 2-8', objective='App launch with Tier 1',
		channels=['CHAN-006'], max_tier=1, weeks_start=2, weeks_end=8),
	PhaseSpec(phase=Phase.phase_3_retention, timeline='Months 2-6', objective='Tier 2 features, CHW scale',
		channels=['all'], max_tier=2, weeks_start=8, weeks_end=26),
	PhaseSpec(phase=Phase.phase_4_daily_habit, timeline='Months 4-12', objective='Tier 3 features',
		channels=['all'], max_tier=3, weeks_start=17, weeks_end=52),
	PhaseSpec(phase=Phase.phase_5_outbreak_ready, timeline='Months 6-12', objective='Tier 4 build and test',
		channels=['all'], max_tier=4, weeks_start=26, weeks_end=52),
	PhaseSpec(phase=Phase.phase_6_scale, timeline='Month 12+', objective='Multi-disease, national integration',
		channels=['all'], max_tier=4, weeks_start=52, weeks_end=None),
)

# §20.2's six levers. `checkable` is True only for the two that make a claim about this repo.
GROWTH_LEVERS: tuple[GrowthLever, ...] = (
	GrowthLever(number=1, lever='Zero-rated data',
		why='The single largest barrier to app use in Kenya',
		action='Negotiate with Safaricom, Airtel, Telkom before launch', checkable=False),
	GrowthLever(number=2, lever='Utility in 60 seconds', why='Value before commitment',
		action='Tier 1 designed for immediate payoff', checkable=False),
	GrowthLever(number=3, lever='Trust', why='Government-only branding limits adoption',
		action='Co-brand with Kenya Red Cross, AMREF, WHO, faith networks; open-source client',
		checkable=True, check='a licence file exists in the repository'),
	GrowthLever(number=4, lever='Social proof',
		why='CHWs, chemists, faith leaders drive adoption, not app stores',
		action='Structured intermediary programme (CHAN-005)', checkable=False),
	GrowthLever(number=5, lever='Friction removal',
		why='Adoption falls off with every step between intent and use',
		action='Under 15 MB; no account; Android Go; offline',
		checkable=True, check='the APK base-size budget is met'),
	GrowthLever(number=6, lever='Incentive', why='A health profile nobody completes is not a profile',
		action='Telco partnership; short-term boost', checkable=False),
)

# §20.2's closing list, verbatim. Two of the five are checkable against the shipped artefacts.
ANTIPATTERNS: tuple[AntiPattern, ...] = (
	AntiPattern(antipattern='Fear', why='Fear-based downloads churn when the news cycle moves on'),
	AntiPattern(antipattern='Unrequested push notifications',
		why='The fastest way to be uninstalled', checkable=True,
		check='every push category is opt-in and the default is off'),
	AntiPattern(antipattern='A 60 MB app', why='Data cost is the largest barrier',
		checkable=True, check='the APK base-size budget is met'),
	AntiPattern(antipattern='A login wall', why='Tier 1 must work without an account',
		checkable=True, check='an anonymous token is issued without a prior identity'),
	AntiPattern(antipattern='A name with "Ebola" in it',
		why='§23.1: branding the product as an outbreak tool is the risk it names first',
		checkable=True, check='the served product name contains no disease name'),
)

# §20.6's nine retention mechanisms. `cadence_days` is set only where the frequency column names a
# period; the "as needed" rows carry None.
RETENTION: tuple[RetentionMechanism, ...] = (
	RetentionMechanism(mechanism='Immunisation reminders', feature_id='MON-001', frequency='Monthly per child', cadence_days=30),
	RetentionMechanism(mechanism='Medication reminders', feature_id='MON-004', frequency='Daily', cadence_days=1),
	RetentionMechanism(mechanism='ANC reminders', feature_id='MON-002', frequency='Monthly', cadence_days=30),
	RetentionMechanism(mechanism='Community alerts', feature_id='ALT-001', frequency='Weekly', cadence_days=7),
	RetentionMechanism(mechanism='Health tips', feature_id='INF-008', frequency='Weekly', cadence_days=7),
	RetentionMechanism(mechanism='Facility finder', feature_id='FND-001', frequency='As needed'),
	RetentionMechanism(mechanism='Medicine verifier', feature_id='MED-001', frequency='As needed'),
	RetentionMechanism(mechanism='Family wallet', feature_id='REC-002', frequency='As needed'),
	RetentionMechanism(mechanism='Drug stock reports', feature_id='MED-004', frequency='As needed'),
)

# §20.5's launch sequence, flattened to steps in order.
LAUNCH_SEQUENCE: tuple[LaunchStep, ...] = (
	LaunchStep(sequence='Phase 0', step='Finalise telco zero-rating agreements'),
	LaunchStep(sequence='Phase 0', step='Brief county health teams and CHWs'),
	LaunchStep(sequence='Phase 0', step='Pre-load content in all languages'),
	LaunchStep(sequence='Phase 0', step='Set up 719 integration and referral pathways'),
	LaunchStep(sequence='Phase 0', step='Test with 500 pilot users in two counties'),
	LaunchStep(sequence='Phase 0', step='Train 200 CHWs as launch champions'),
	LaunchStep(sequence='Launch week', step='Radio blitz across partner stations'),
	LaunchStep(sequence='Launch week', step='WhatsApp bot goes live'),
	LaunchStep(sequence='Launch week', step='SMS opt-in campaign'),
	LaunchStep(sequence='Launch week', step='Social media campaign'),
	LaunchStep(sequence='Launch week', step='CHW door-to-door in high-risk areas'),
	LaunchStep(sequence='Launch week', step='App store launch'),
	LaunchStep(sequence='Launch week', step='Press conference with MoH and partners'),
	LaunchStep(sequence='Weeks 2-4', step='Scale CHW training to 2,000'),
	LaunchStep(sequence='Weeks 2-4', step='Expand radio to all counties'),
	LaunchStep(sequence='Weeks 2-4', step='First misinformation response cycle'),
	LaunchStep(sequence='Weeks 2-4', step='Weekly user feedback sessions'),
	LaunchStep(sequence='Weeks 2-4', step='Iterate on onboarding based on drop-off data'),
)


class RolloutService(LogMixin):
	def __init__(self, registry: FeatureRegistry, apk_size_mb: float | None = None,
	             repo_root: Path | None = None,
	             mechanisms: tuple[RetentionMechanism, ...] | None = None) -> None:
		"""`apk_size_mb` is a measurement, not a setting: None means nobody has weighed the build, and
		`readiness` reports that as unmeasured rather than as inside the budget — the same rule §15.4
		and §22 already apply.

		`mechanisms` defaults to §20.6's table. It is injectable so the *negative* direction of the
		registry cross-check is reachable: with the real table every feature is registered, so a
		check that could never report a gap would look identical to one that works.
		"""
		self._registry = registry
		self._apk = apk_size_mb
		self._root = repo_root or REPO_ROOT
		self._mechanisms = mechanisms if mechanisms is not None else RETENTION
		assert len({p.phase for p in PHASES}) == len(PHASES), 'phase ids must be unique'

	@staticmethod
	def phases() -> list[PhaseSpec]:
		return list(PHASES)

	@staticmethod
	def phase_spec(phase: Phase) -> PhaseSpec:
		for p in PHASES:
			if p.phase is phase:
				return p
		raise AssertionError(f'{phase} is not a §21.1 phase')

	@staticmethod
	def growth_levers() -> list[GrowthLever]:
		return list(GROWTH_LEVERS)

	@staticmethod
	def launch_sequence() -> list[LaunchStep]:
		return list(LAUNCH_SEQUENCE)

	def is_registered(self, feature_id: str) -> bool:
		"""Whether the registry knows a feature. Public so the negative direction is assertable: a
		check that has only ever been seen return True is not evidence that it can return False."""
		try:
			self._registry.get(feature_id)
		except KeyError:
			return False
		return True

	def retention_mechanisms(self) -> list[RetentionMechanism]:
		"""§20.6's table with each feature crossed against the registry. `registered` is the answer
		to "does the feature the retention engine rests on actually exist"."""
		return [
			m.model_copy(update={'registered': self.is_registered(m.feature_id)})
			for m in self._mechanisms
		]

	def unregistered_retention_features(self) -> list[str]:
		"""The §20.6 features with no registry entry. §20.6 is the argument that the product survives
		the outbreak; a mechanism resting on an unbuilt feature is an argument with nothing under it."""
		return sorted(m.feature_id for m in self.retention_mechanisms() if not m.registered)

	def licence(self) -> str | None:
		"""The licence file's first line, or None if the repository carries no licence.

		§20.2 lever 3 and §23.5 both rest on the client being open source, and the spec names no
		licence — so this reports which one was chosen, and None is a real answer that means the
		claim is currently unbacked.
		"""
		for name in LICENCE_FILES:
			path = self._root / name
			if path.is_file():
				text = path.read_text(encoding='utf-8', errors='replace').strip()
				return text.splitlines()[0][:120] if text else name
		return None

	def readiness(self) -> ReadinessReport:
		"""§20.2's two repo claims plus §20.6's registry coverage.

		`apk_within_budget` is None when no size was measured — an unweighed build is not a small
		one, and reporting True for it is the failure mode §15.4's capacity report already refuses.
		"""
		licence = self.licence()
		unregistered = self.unregistered_retention_features()
		within = None if self._apk is None else self._apk <= APK_BUDGET_MB
		notes: list[str] = []
		if licence is None:
			notes.append('no licence file: §20.2 lever 3 and §23.5 claim an open-source client')
		if within is None:
			notes.append(f'APK size unmeasured; §20.2 lever 5 and §22.5 set a {APK_BUDGET_MB:g} MB budget')
		if unregistered:
			notes.append(f'retention mechanisms on unregistered features: {", ".join(unregistered)}')
		self._log_info('rollout readiness', open_source=licence is not None, unregistered=len(unregistered))
		return ReadinessReport(
			open_source=licence is not None, license=licence,
			apk_base_size_mb=self._apk, apk_within_budget=within,
			retention_mechanisms=self.retention_mechanisms(),
			unregistered_retention_features=unregistered,
			antipatterns=list(ANTIPATTERNS),
			note='; '.join(notes) if notes else 'both §20.2 repo claims hold and every retention feature is registered',
		)

	def status(self, phase: Phase, active_tier: int) -> RolloutStatus:
		"""Where a deployment sits against §21.1's ceiling for its phase.

		A tier active above the ceiling means the rollout skipped its own gate. The mismatch is
		reported with both numbers rather than as a boolean, because the reader needs to know which
		phase claims to be current and what is actually on.
		"""
		assert 1 <= active_tier <= 4, 'tiers run 1 to 4'
		spec = self.phase_spec(phase)
		ceiling = spec.max_tier
		mismatch = ceiling is not None and active_tier > ceiling
		note = (
			f'tier {active_tier} is active but {phase.value} authorises at most tier {ceiling}'
			if mismatch else
			'phase 0 delivers nothing to a user' if ceiling is None else
			f'tier {active_tier} is within the {phase.value} ceiling of {ceiling}'
		)
		if mismatch:
			self._log_warn('rollout phase mismatch', phase=phase.value, active_tier=active_tier, ceiling=ceiling)
		return RolloutStatus(
			phase=phase, objective=spec.objective, max_tier=ceiling, active_tier=active_tier,
			phase_mismatch=mismatch, channels_open=list(spec.channels), note=note,
		)
