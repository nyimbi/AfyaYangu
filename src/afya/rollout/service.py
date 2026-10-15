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
from afya.registry.service import CHANNELS, FeatureRegistry
from afya.rollout.views import (
	AcquisitionChannel, AcquisitionPlan, AntiPattern, AppSizePlan, Deliverable, GrowthLever,
	LaunchStep, ModuleDelivery, PartnerType, Phase, PhasePlan, PhaseReadiness, PhaseSpec,
	ReadinessReport, RetentionMechanism, RolloutStatus, SuccessCriterion,
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
#
# `channels` is the Channels column *expanded and accumulated* and `channels_cell` is the column
# verbatim. §21.1 writes it three ways: `CHAN-0,1,2,3,4,5` (abbreviated), `+ CHAN-6` (cumulative —
# the `+` means in addition to the phase before) and `All` (a quantifier over §5.2's seven, not an
# id). The first cut carried the cell as-is, which put the literal string `'all'` on
# `/rollout/phases` — an anonymous route — where it read as a channel id beside `CHAN-006`.
ALL_CHANNELS: tuple[str, ...] = tuple(f'CHAN-{n:03d}' for n in range(7))

PHASES: tuple[PhaseSpec, ...] = (
	PhaseSpec(phase=Phase.phase_0_foundation, timeline='Weeks -8 to 0', objective='Build, partner, prepare',
		channels=[], channels_cell='—', max_tier=None, tiers_cell='—', weeks_start=-8, weeks_end=0),
	PhaseSpec(phase=Phase.phase_1_information, timeline='Weeks 0–4', objective='Maximum reach, minimum friction',
		channels=['CHAN-000', 'CHAN-001', 'CHAN-002', 'CHAN-003', 'CHAN-004', 'CHAN-005'],
		channels_cell='CHAN-0,1,2,3,4,5', max_tier=1, tiers_cell='Info only', weeks_start=0, weeks_end=4),
	# `+ CHAN-6`: phase 2 opens CHAN-006 *in addition to* phase 1's six, so the row's channel set is
	# cumulative and seven ids, not the one id the cell spells.
	PhaseSpec(phase=Phase.phase_2_utility, timeline='Weeks 2–8', objective='App launch with Tier 1',
		channels=['CHAN-000', 'CHAN-001', 'CHAN-002', 'CHAN-003', 'CHAN-004', 'CHAN-005', 'CHAN-006'],
		channels_cell='+ CHAN-6', max_tier=1, tiers_cell='Tier 1', weeks_start=2, weeks_end=8),
	PhaseSpec(phase=Phase.phase_3_retention, timeline='Months 2–6', objective='Tier 2 features, CHW scale',
		channels=list(ALL_CHANNELS), channels_cell='All', max_tier=2, tiers_cell='Tier 1–2', weeks_start=8, weeks_end=26),
	PhaseSpec(phase=Phase.phase_4_daily_habit, timeline='Months 4–12', objective='Tier 3 features',
		channels=list(ALL_CHANNELS), channels_cell='All', max_tier=3, tiers_cell='Tier 1–3', weeks_start=17, weeks_end=52),
	PhaseSpec(phase=Phase.phase_5_outbreak_ready, timeline='Months 6–12', objective='Tier 4 build and test',
		channels=list(ALL_CHANNELS), channels_cell='All', max_tier=4, tiers_cell='Tier 1–4', weeks_start=26, weeks_end=52),
	PhaseSpec(phase=Phase.phase_6_scale, timeline='Month 12+', objective='Multi-disease, national integration',
		channels=list(ALL_CHANNELS), channels_cell='All', max_tier=4, tiers_cell='All', weeks_start=52, weeks_end=None),
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

# §16.5's delivery table, verbatim and in the section's order. `delivery` is the section's own
# Delivery column collapsed to three slugs: "Initial download" is `initial`, "On-demand ..." is
# `on_demand` with the parenthetical kept as `condition`, and "Automatic per county" is `automatic`.
# The condition matters for the two rows whose on-demand-ness is a device fact rather than a choice —
# the LiDAR module only exists on a phone with a LiDAR sensor, and §13.2's fallback is what the rest
# of the fleet gets.
MODULES: tuple[ModuleDelivery, ...] = (
	ModuleDelivery(component='Base app', size_mb=15.0, delivery='initial'),
	ModuleDelivery(component='Tier 1 features', size_mb=0.0, delivery='initial'),
	ModuleDelivery(component='Tier 2 features', size_mb=0.0, delivery='initial'),
	ModuleDelivery(component='Tier 3 features', size_mb=8.0, delivery='on_demand'),
	ModuleDelivery(component='LiDAR module', size_mb=4.0, delivery='on_demand', condition='LiDAR devices only'),
	ModuleDelivery(component='Acoustic module', size_mb=6.0, delivery='on_demand'),
	ModuleDelivery(component='Medicine registry (offline)', size_mb=25.0, delivery='on_demand', condition='optional'),
	ModuleDelivery(component='Offline content library', size_mb=15.0, delivery='on_demand', condition='optional'),
	ModuleDelivery(component='Offline facility cache', size_mb=5.0, delivery='automatic', condition='per county'),
)

# §20.3, verbatim. `channel` is §5.2's slug and `label` the section's own word, because the two are
# not the same set — "App stores" is `native` here, and §20.3's row is the *discovery* act rather
# than the app. §5.2's seven channels are all seven rows, so nothing in the section is unmapped; the
# crossing is asserted rather than assumed, and it is what would fail if §5.2 gained an eighth.
ACQUISITION: tuple[AcquisitionChannel, ...] = (
	AcquisitionChannel(channel='radio', label='Radio', role='Mass awareness',
		tactics=['Daily segments', 'call-ins', 'drama vignettes'], feature_id='CHAN-000'),
	AcquisitionChannel(channel='sms', label='SMS', role='Opt-in list building',
		tactics=['Zero-rated alerts with opt-in keyword'], feature_id='CHAN-001'),
	AcquisitionChannel(channel='ussd', label='USSD', role='Non-smartphone reach',
		tactics=['Menu with "download app" option via SMS link'], feature_id='CHAN-002'),
	AcquisitionChannel(channel='whatsapp', label='WhatsApp', role='Primary conversion',
		tactics=['Forwardable cards with download links', 'bot → app handoff'], feature_id='CHAN-003'),
	AcquisitionChannel(channel='social', label='Social media', role='Youth reach',
		tactics=['TikTok myth-busting', 'Instagram explainers', 'X threads'], feature_id='CHAN-004'),
	AcquisitionChannel(channel='chw', label='Human intermediaries', role='Trust transfer',
		tactics=['CHWs', 'chemists', 'faith leaders', 'boda SACCOs'], feature_id='CHAN-005'),
	AcquisitionChannel(channel='native', label='App stores', role='Discovery',
		tactics=['ASO', 'ratings', 'reviews'], feature_id='CHAN-006'),
)

# §20.4, verbatim. `partners` is the Specific partners cell split on its commas — the cell is the
# section naming organisations, and a map whose partner count counted rows would read as ten
# organisations when the section names thirty-nine.
PARTNERS: tuple[PartnerType, ...] = (
	PartnerType(partner_type='Telcos', partners=['Safaricom', 'Airtel Kenya', 'Telkom Kenya'],
		role='Zero-rating, SMS/USSD gateway, airtime incentives, distribution'),
	PartnerType(partner_type='Health NGOs',
		partners=['Kenya Red Cross', 'AMREF Health Africa', 'Living Goods', 'Medic', 'Dimagi'],
		role='CHW networks, field validation, credibility'),
	PartnerType(partner_type='Government',
		partners=['MoH', 'PHEOC', 'county health teams', 'PPB', 'SHA'],
		role='Data, authority, integration'),
	PartnerType(partner_type='Faith networks',
		partners=['NCCK', 'SUPKEM', 'Catholic Secretariat', 'evangelical associations'],
		role='Trust, distribution, burial guidance'),
	PartnerType(partner_type='Transport',
		partners=['Boda boda SACCOs', 'matatu SACCOs', 'long-distance operators'],
		role='Mobility, distribution, trusted voices'),
	PartnerType(partner_type='Retail',
		partners=['Pharmacy chains', 'chemists', 'supermarkets', 'kiosks'],
		role='Medicine verification, distribution, stock reporting'),
	PartnerType(partner_type='Education', partners=['Universities', 'TVETs', 'secondary schools'],
		role='Student adoption, peer spread'),
	PartnerType(partner_type='Media',
		partners=['KBC', 'Royal Media', 'Radio Africa', 'Standard Group', 'Nation Media'],
		role='Awareness, credibility'),
	PartnerType(partner_type='International', partners=['WHO', 'UNICEF', 'CDC', 'Africa CDC'],
		role='Technical guidance, funding, legitimacy'),
	PartnerType(partner_type='Tech', partners=['Google', 'Meta', 'Safaricom Spark'],
		role='Platform support, zero-rating, technical resources'),
)

# The organisations §20.2's levers name as the thing the lever is waiting on, spelled as the
# partnership map spells them. This is the join §20.4 exists to satisfy: §20.2 lever 1 says
# "Negotiate with Safaricom, Airtel, Telkom before launch" and lever 3 says "Co-brand with Kenya Red
# Cross, AMREF, WHO, faith networks", and §20.4 is the section that says who is a partner.
#
# Only those two levers name an organisation. "faith networks" is a category rather than a body, so
# it is left out rather than mapped to a row: the lever names WHO and two NGOs by name, and a
# category given a row's worth of partners would be this code inventing the join.
LEVER_PARTNER_NAMES: dict[int, tuple[str, ...]] = {
	1: ('Safaricom', 'Airtel Kenya', 'Telkom Kenya'),
	3: ('Kenya Red Cross', 'AMREF Health Africa', 'WHO'),
}


# §21.2–21.7, the phase sections. §21.1's table gives each phase a ceiling and a channel set; the
# sections give the work, and until they were carried a rollout was seven gates describing nothing.
#
# `feature_id` is set only where the section's own words name a capability the registry holds.
# "Zero-rated app data", "Facility data loaded for all 47 counties" and "Full PHEOC integration" are
# operational acts or integration states, not features, and leaving them unmapped is the honest
# reading — marking them unbuilt would make the readiness report cry wolf on every phase.
#
# §21.3's "719 integration live" is the case worth naming: 719 is the hotline §8.5's contact
# directory carries and §5's hotline channel answers, so the deliverable is real and the registry
# has no feature id for it. That is a gap in the registry's coverage of §21, not an unbuilt feature,
# and it is why `unbuilt_deliverables` and `unregistered_features` are reported separately.
PHASE_PLANS: tuple[PhasePlan, ...] = (
	PhasePlan(
		phase=Phase.phase_1_information,
		objective='Reach millions without requiring a download',
		deliverables=[
			Deliverable(text='Community radio partnership live in 20+ stations', feature_id='CHAN-000'),
			Deliverable(text='Zero-rated SMS alerts operational', feature_id='CHAN-001'),
			Deliverable(text='USSD menu live', feature_id='CHAN-002'),
			Deliverable(text='WhatsApp bot live with triage, Q&A, myth-busting', feature_id='CHAN-003'),
			Deliverable(text='Social media campaign', feature_id='CHAN-004'),
			Deliverable(text='200 CHWs trained as information intermediaries', feature_id='CHAN-005'),
			Deliverable(text='Content in 6 languages minimum'),
		],
		criteria=[
			SuccessCriterion(text='500,000 SMS opt-ins', value=500_000, unit='opt-ins', kpi_id='sms_optins'),
			SuccessCriterion(text='100,000 WhatsApp users', value=100_000, unit='users', kpi_id='whatsapp_users'),
			SuccessCriterion(text='50 stations broadcasting', value=50, unit='stations'),
		],
		rationale='It delivers the mission — protecting people — without waiting for app development. '
			'It builds the audience the app will later convert.',
	),
	PhasePlan(
		phase=Phase.phase_2_utility,
		objective='Launch the app with features that earn a permanent place on the home screen',
		deliverables=[
			Deliverable(text='App live on Google Play and App Store', feature_id='CHAN-006'),
			Deliverable(text='Tier 1 features complete'),
			Deliverable(text='Zero-rated app data'),
			Deliverable(text='2,000 CHWs trained', feature_id='CHAN-005'),
			Deliverable(text='Facility data loaded for all 47 counties'),
			Deliverable(text='Medicine registry cached', feature_id='MED-001'),
			Deliverable(text='Emergency SOS live', feature_id='EMG-001'),
			Deliverable(text='719 integration live'),
		],
		criteria=[
			SuccessCriterion(text='300,000 installs', value=300_000, unit='installs', kpi_id='app_downloads'),
			SuccessCriterion(text='4.0+ rating', value=4.0, unit='stars'),
			SuccessCriterion(text='40% D30 retention', value=40.0, unit='percent'),
			SuccessCriterion(text='50,000 triages', value=50_000, unit='triages'),
		],
	),
	PhasePlan(
		phase=Phase.phase_3_retention,
		objective='Tier 2 features, CHW scale',
		deliverables=[
			Deliverable(text='Child immunisation tracker', feature_id='MON-001'),
			Deliverable(text='Pregnancy and ANC tracker', feature_id='MON-002'),
			Deliverable(text='Chronic disease log', feature_id='MON-003'),
			Deliverable(text='Medication reminders', feature_id='MON-004'),
			Deliverable(text='Family health wallet (basic)', feature_id='REC-001'),
			Deliverable(text='Drug stock crowdsourcing', feature_id='MED-004'),
			Deliverable(text='Appointment booking pilot', feature_id='FND-006'),
			Deliverable(text='Service status feed', feature_id='INF-007'),
		],
		criteria=[
			SuccessCriterion(text='1M installs', value=1_000_000, unit='installs', kpi_id='app_downloads'),
			SuccessCriterion(text='25% DAU/MAU', value=25.0, unit='percent', kpi_id='retention_dau_mau'),
			SuccessCriterion(text='100,000 children tracked', value=100_000, unit='children'),
			SuccessCriterion(text='200,000 medication reminders active', value=200_000, unit='reminders'),
		],
	),
	PhasePlan(
		phase=Phase.phase_4_daily_habit,
		objective='Tier 3 features',
		deliverables=[
			Deliverable(text='Full family health wallet with cloud backup', feature_id='REC-002'),
			Deliverable(text='Growth and development tracker', feature_id='REC-003'),
			Deliverable(text='Mental health support', feature_id='REC-005'),
			Deliverable(text='Blood donor matching', feature_id='REC-004'),
			Deliverable(text='Water quality alerts', feature_id='MON-005'),
			Deliverable(text='Air quality index', feature_id='MON-006'),
			Deliverable(text='Community reporting', feature_id='COM-005'),
			Deliverable(text='First aid guide', feature_id='INF-009'),
			Deliverable(text='Nutrition guidance', feature_id='MON-008'),
			Deliverable(text='Safe and dignified burial guidance', feature_id='INF-010'),
		],
		criteria=[
			SuccessCriterion(text='2M installs', value=2_000_000, unit='installs', kpi_id='app_downloads'),
			SuccessCriterion(text='35% DAU/MAU', value=35.0, unit='percent', kpi_id='retention_dau_mau'),
			SuccessCriterion(text='20% of users open the app daily', value=20.0, unit='percent'),
		],
	),
	PhasePlan(
		phase=Phase.phase_5_outbreak_ready,
		objective='Tier 4 build and test',
		deliverables=[
			Deliverable(text='21-day contact monitoring', feature_id='MON-009'),
			Deliverable(text='CHW case reporting module', feature_id='COM-101'),
			Deliverable(text='Bluetooth proximity logging', feature_id='LOC-002'),
			Deliverable(text='GPS location history for contact tracing', feature_id='LOC-003'),
			Deliverable(text='QR/NFC check-in', feature_id='LOC-004'),
			Deliverable(text='LiDAR respiration monitoring', feature_id='SENS-001'),
			Deliverable(text='Acoustic cough monitoring', feature_id='SENS-002'),
			Deliverable(text='Fall detection (enhanced)', feature_id='SENS-003'),
			Deliverable(text='Wearable integration', feature_id='SENS-006'),
			Deliverable(text='AI risk prediction', feature_id='AI-001'),
			Deliverable(text='Early warning signal', feature_id='AI-003'),
			Deliverable(text='Full PHEOC integration'),
		],
		criteria=[
			SuccessCriterion(text='Tier 4 activation in under 60 minutes', value=60.0, unit='minutes', operator='at_most'),
			SuccessCriterion(text='<5% daily battery impact', value=5.0, unit='percent/day', operator='at_most', kpi_id='battery_impact'),
			SuccessCriterion(text='full offline operation verified', value=100.0, unit='percent', kpi_id='offline_availability'),
		],
		testing=[
			'Tabletop exercises with PHEOC',
			'simulated outbreak activation',
			'red team review of privacy controls',
		],
	),
	PhasePlan(
		phase=Phase.phase_6_scale,
		objective='Multi-disease, national integration',
		deliverables=[
			Deliverable(text='Multi-disease support (cholera, Rift Valley fever, mpox, measles)'),
			Deliverable(text='Integration into national health information system'),
			Deliverable(text='Sustainable funding model'),
			Deliverable(text='Regional expansion (Uganda, Tanzania, DRC, South Sudan)'),
			Deliverable(text='Continuous improvement based on user feedback'),
		],
		criteria=[],
	),
)

# §21.2–21.7 by phase, for the readiness check. Built from the tuple rather than kept beside it, so
# a phase cannot be in one and missing from the other.
#
# The Channels column's expansion and accumulation are asserted in `tests/ci/test_rollout.py` rather
# than at import. They were module-level asserts for one revision, and the cost was concrete: a
# mutation to one phase's channel set tripped the assert, which turned the whole file into a
# *collection error* — every other test in it stopped running and the canary could not name the node
# it aimed at, which is the failure the canary harness exists to refuse. A guard that takes the file
# down with it is a guard that hides the thing it caught.
PLAN_BY_PHASE: dict[Phase, PhasePlan] = {p.phase: p for p in PHASE_PLANS}


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

	def app_size(self) -> AppSizePlan:
		"""§16.5's delivery table, summed by where each row lands.

		The split is the section's own argument. §16.5 lists a 20 MB speech model, a 25 MB medicine
		registry and a 15 MB content library and still closes "Base install under 15 MB", which is only
		true because the Delivery column makes them on-demand. Summing the table into one number would
		report ~60 MB and read as a budget breach the section does not have; summing only the initial
		rows would report 15 MB and hide everything the person may later carry.

		`within_budget` is therefore about the install, and the on-demand total is reported beside it
		rather than folded in. The budget is `APK_BUDGET_MB`, read from §22.5's KPI table, so §20.2
		lever 5, §16.5's closing line and §22.5's target stay one number instead of three.
		"""
		base = round(sum(m.size_mb for m in MODULES if m.delivery == 'initial'), 2)
		on_demand = round(sum(m.size_mb for m in MODULES if m.delivery == 'on_demand'), 2)
		full = round(base + on_demand + sum(m.size_mb for m in MODULES if m.delivery == 'automatic'), 2)
		within = base <= APK_BUDGET_MB
		self._log_info('app size plan', base_mb=base, on_demand_mb=on_demand, within=within)
		return AppSizePlan(
			components=list(MODULES), base_install_mb=base, on_demand_mb=on_demand, full_install_mb=full,
			budget_mb=APK_BUDGET_MB, within_budget=within,
			note=(
				f'base install {base:g} MB against the {APK_BUDGET_MB:g} MB budget; '
				f'{on_demand:g} MB more is available on demand and {full:g} MB with every module'
				if within else
				f'base install {base:g} MB exceeds the {APK_BUDGET_MB:g} MB budget §20.2 lever 5 and §22.5 set'
			),
		)

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

	# --- §21.2–21.7 phase plans --------------------------------------------------------------

	@staticmethod
	def phase_plans() -> list[PhasePlan]:
		"""§21.2–21.7's six sections, in phase order. Phase 0 has no section: it is the build."""
		return [PLAN_BY_PHASE[p.phase] for p in PHASES if p.phase in PLAN_BY_PHASE]

	@staticmethod
	def phase_plan(phase: Phase) -> PhasePlan:
		"""One phase's plan, or a refusal naming the phase. Phase 0 is the case that refuses, and it
		is not an error: §21.1 gives it no section because it delivers nothing to a user."""
		if phase not in PLAN_BY_PHASE:
			raise KeyError(f'{phase.value} has no §21 plan: it delivers nothing to a user')
		return PLAN_BY_PHASE[phase]

	def phase_readiness(self, phase: Phase) -> PhaseReadiness:
		"""A phase's plan crossed against the registry and against §22.

		Four findings, and they are genuinely different problems:

		* **A deliverable the registry does not carry.** §21.4 lists "Family health wallet (basic)"
		and the registry holds it; a phase listing a capability nobody built is a schedule for
		something that will not arrive. This is the §11.1 defect in the phase dimension — a plan
		naming a feature that does not exist reads identically to one that does.
		* **A criterion with no KPI behind it.** §21.2's "50 stations broadcasting" is a real target
		and §22 measures no such thing, so the phase's own exit cannot be computed from §22's
		report. Reported rather than invented.
		* **Criterion drift between §21 and §22.** Both sections state a number for the same measure
		and they disagree — §21.3's 300,000 installs against §22.2's 2,000,000, §21.4's 25% DAU/MAU
		against §22.1's 35%. Averaging them or picking one would be this code overruling the product
		owner; what it owes is the finding.
		* **A deliverable above the phase's own tier ceiling.** §21.1 gives each phase a ceiling and
		§21.2–§21.7 schedule features under it, so a plan that schedules a feature the ceiling does
		not authorise contradicts itself in two adjacent columns. See `_tier_over_ceiling` for why
		this is reported rather than resolved.

		`ready` is False when any of the first two holds. Drift does not make a phase unready — the
		phase can ship — it makes the *document* inconsistent, which is a different reader's problem.
		"""
		plan = self.phase_plan(phase)
		kpi_targets = {row[0]: row[3] for row in KPIS}
		unregistered: list[str] = []
		unbuilt: list[str] = []
		for d in plan.deliverables:
			if d.feature_id is None:
				continue
			if not self.is_registered(d.feature_id):
				unregistered.append(d.feature_id)
				unbuilt.append(d.text)
		drift: list[str] = []
		unmeasurable: list[str] = []
		for c in plan.criteria:
			if c.kpi_id is None or c.kpi_id not in kpi_targets:
				unmeasurable.append(c.text)
				continue
			target = kpi_targets[c.kpi_id]
			if not c.agrees_with(target):
				drift.append(
					f'{c.text} against §22\'s {c.kpi_id} target of {target:g} {c.unit}'
				)
		over_ceiling = self._tier_over_ceiling(phase)
		ready = not unregistered and not unmeasurable
		if unregistered:
			note = f'{len(unregistered)} deliverable(s) name a feature the registry does not carry'
		elif unmeasurable:
			note = f'{len(unmeasurable)} criterion/criteria have no §22 KPI to measure against'
		elif over_ceiling:
			note = f'{len(over_ceiling)} deliverable(s) sit above the phase\'s own tier ceiling'
		elif drift:
			note = f'plan ships; {len(drift)} criterion/criteria disagree with §22'
		else:
			note = 'every deliverable that names a feature resolves and every criterion maps to a §22 KPI'
		self._log_info('phase readiness', phase=phase.value, unbuilt=len(unregistered),
		               unmeasurable=len(unmeasurable), drift=len(drift), over_ceiling=len(over_ceiling))
		return PhaseReadiness(
			phase=phase, objective=plan.objective,
			deliverable_count=len(plan.deliverables),
			feature_deliverables=sum(1 for d in plan.deliverables if d.feature_id is not None),
			unbuilt_deliverables=unbuilt, unregistered_features=sorted(set(unregistered)),
			criteria=list(plan.criteria), criterion_drift=drift,
			unmeasurable_criteria=unmeasurable, testing=list(plan.testing),
			over_ceiling_deliverables=over_ceiling,
			ready=ready, note=note,
		)

	def _tier_over_ceiling(self, phase: Phase) -> list[str]:
		"""Deliverables whose feature tier is above the phase's own §21.1 ceiling.

		Two are live, both `CHAN-005` ("200 CHWs trained as information intermediaries" in §21.2 and
		"2,000 CHWs trained" in §21.3) against a ceiling of 1 in both phases. **Reported, not
		resolved**, and the reason is that the two columns disagree with no third authority to break
		the tie:

		* §21.1's Channels column opens `CHAN-0,1,2,3,4,5` in Phase 1, and its Tiers column says
		  `Info only`; Phase 2's says `+ CHAN-6` / `Tier 1`. So the section *schedules* the channel
		  in Phase 1 and *caps* the phase at Tier 1 in the same row.
		* §7.3's tier map names **no CHAN id at all** — `unmapped_features()` reports all seven — and
		  no CHAN section in §5.3 states a `**Tier:**` line. The registry's `CHAN-005 → Tier 2` is
		  therefore this repo's assignment with no section behind it, which is what
		  `test_registry.py` already says about the CHAN ids ("§7.3 names no CHAN id at all").

		So moving `CHAN-005` to Tier 1 or the ceilings to Tier 2 would each be this code overruling
		one §21 column on the strength of a registry value the spec does not state. What it owes is
		the finding, which is the same call §21/§22's criterion drift already makes.
		"""
		ceiling = self.phase_spec(phase).max_tier
		if ceiling is None:
			return []
		plan = self.phase_plan(phase)
		out: list[str] = []
		for d in plan.deliverables:
			if d.feature_id is None or not self.is_registered(d.feature_id):
				continue
			tier = int(self._registry.get(d.feature_id).tier)
			if tier > ceiling:
				out.append(f'{d.text} — Tier {tier}, above the phase ceiling of Tier {ceiling}')
		return out

	@staticmethod
	def public_plans() -> list[dict[str, object]]:
		"""§21.2–21.7 rendered for a reader who is not the auditor: the section's own words, with the
		registry handles dropped.

		The same split `/sensors/capabilities` and `/sensors/coverage` already make. A deliverable's
		`feature_id` is a traceability handle, and the plan is a document a county team and a partner
		align to — the text says what ships and the handle adds nothing a reader of the plan needs.
		The evidence half keeps the ids, because there the id *is* the finding.
		"""
		return [
			{
				'phase': plan.phase.value,
				'objective': plan.objective,
				'deliverables': [d.text for d in plan.deliverables],
				'criteria': [c.text for c in plan.criteria],
				'testing': list(plan.testing),
				'rationale': plan.rationale,
			}
			for plan in (PLAN_BY_PHASE[p.phase] for p in PHASES if p.phase in PLAN_BY_PHASE)
		]

	def rollout_plan(self) -> list[PhaseReadiness]:
		"""Every phase's plan and its findings, in phase order. The whole of §21 as one answer."""
		return [self.phase_readiness(p.phase) for p in PHASES if p.phase in PLAN_BY_PHASE]

	def acquisition(self) -> AcquisitionPlan:
		"""§20.3's channel plan and §20.4's partnership map, crossed against §5.2 and §20.2.

		Two findings. `unmapped_channels` is a §5.2 channel §20.3 gives no acquisition role for — a
		channel the product reaches someone through and no plan to reach them. `unsourced_levers` is
		the sharper one: a §20.2 lever whose named partner is not on the §20.4 map is a growth
		strategy waiting on an agreement with an organisation the partnership section does not know.
		"""
		known: dict[str, str] = {p: t.partner_type for t in PARTNERS for p in t.partners}
		lever_partners: dict[str, list[str]] = {}
		unsourced: list[str] = []
		for number, names in sorted(LEVER_PARTNER_NAMES.items()):
			lever_partners[str(number)] = list(names)
			missing = [n for n in names if n not in known]
			if missing:
				lever = next(lv for lv in GROWTH_LEVERS if lv.number == number)
				unsourced.append(f'lever {number} ({lever.lever}) names {", ".join(missing)}')
		planned = {c.channel for c in ACQUISITION}
		unmapped = [c for c in CHANNELS if c not in planned]
		total = sum(len(t.partners) for t in PARTNERS)
		self._log_info('acquisition plan read', channels=len(ACQUISITION), partners=total, unsourced=len(unsourced))
		return AcquisitionPlan(
			channels=list(ACQUISITION), partner_types=list(PARTNERS), partner_count=total,
			unmapped_channels=unmapped, lever_partners=lever_partners, unsourced_levers=unsourced,
			note=(
				f'{total} named partners across {len(PARTNERS)} partner types; '
				f'{len(unmapped)} §5.2 channel(s) with no §20.3 acquisition role'
				if not unsourced else
				f'{len(unsourced)} §20.2 lever(s) rest on a partner §20.4 does not list'
			),
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
			phase_mismatch=mismatch, channels_open=list(spec.channels),
			channels_cell=spec.channels_cell, note=note,
		)
