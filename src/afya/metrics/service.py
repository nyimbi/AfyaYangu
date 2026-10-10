"""Success metrics — §22's eight tables as data, with the measurement rule §15.4 already applies.

§22.5's technical table overlaps §15.4's capacity targets, and the overlap is deliberate: the same
number appears in both sections, so this module asserts the two agree rather than keeping a second
copy that can drift. A report that said "API p95 <300 ms" in one view and "p95 500 ms" in another
would be the self-contradiction this repo keeps finding.

The rule throughout: a target with no measurement is unmeasured and does not count as met. §22 is
what a funder reads, and a green report assembled from silence is the failure the section invites.
"""
from afya.governance.service import SCALE_TARGETS
from afya.logmixin import LogMixin
from afya.metrics.views import (
	EquityAxis, EquityGap, EquityReport, Kpi, KpiResult, Measurement, MetricFamily, MetricReport,
)

# §22, one row per KPI. (kpi_id, name, definition, target, unit, family, higher_is_better, source).
# "Lives saved" carries target 0.0 and `modelled=True` in the table below: §22.1 gives it no fixed
# number ("Measured via modelling"), so inventing one would be the fabrication this file avoids.
KPIS: tuple[tuple[str, str, str, float, str, MetricFamily, bool, str, bool], ...] = (
	# §22.1 north star
	('people_reached', 'People reached', 'Unique individuals receiving health information through any channel', 15_000_000, 'people', MetricFamily.north_star, True, '§22.1', False),
	('people_protected', 'People protected', 'Individuals who completed a triage and received actionable guidance', 3_000_000, 'people', MetricFamily.north_star, True, '§22.1', False),
	('lives_saved', 'Lives saved (estimated)', 'Cases detected earlier than they would have been otherwise', 0.0, 'lives', MetricFamily.north_star, True, '§22.1', True),
	('retention_dau_mau', 'Retention', 'DAU/MAU ratio', 35.0, 'percent', MetricFamily.north_star, True, '§22.1', False),
	# §22.2 reach
	('app_downloads', 'App downloads', 'App store downloads', 2_000_000, 'downloads', MetricFamily.reach, True, '§22.2', False),
	('whatsapp_users', 'WhatsApp bot users', 'Users of the WhatsApp bot', 2_000_000, 'users', MetricFamily.reach, True, '§22.2', False),
	('sms_optins', 'SMS opt-ins', 'SMS subscribers', 3_000_000, 'opt-ins', MetricFamily.reach, True, '§22.2', False),
	('ussd_sessions_monthly', 'USSD sessions per month', 'USSD sessions in a month', 500_000, 'sessions/month', MetricFamily.reach, True, '§22.2', False),
	('radio_reach_weekly', 'Radio reach (weekly)', 'Weekly radio audience', 10_000_000, 'people', MetricFamily.reach, True, '§22.2', False),
	('social_reach', 'Social media reach', 'Social media audience', 20_000_000, 'people', MetricFamily.reach, True, '§22.2', False),
	('chws_onboarded', 'CHWs onboarded', 'Community health workers in the registry', 5_000, 'CHWs', MetricFamily.reach, True, '§22.2', False),
	# §22.3 engagement
	('dau', 'DAU', 'Daily active users', 500_000, 'users', MetricFamily.engagement, True, '§22.3', False),
	('mau', 'MAU', 'Monthly active users', 1_500_000, 'users', MetricFamily.engagement, True, '§22.3', False),
	('triages_monthly', 'Triages per month', 'Triage assessments in a month', 200_000, 'triages/month', MetricFamily.engagement, True, '§22.3', False),
	('assessment_completion', 'Symptom assessments completed', 'Share of started assessments completed', 85.0, 'percent', MetricFamily.engagement, True, '§22.3', False),
	('session_duration', 'Average session duration', 'Mean session length', 2.0, 'minutes', MetricFamily.engagement, True, '§22.3', False),
	('push_optin', 'Push notification opt-in', 'Share of users who opted into push', 60.0, 'percent', MetricFamily.engagement, True, '§22.3', False),
	# §22.4 health outcome
	('contacts_monitored', 'Contacts monitored to completion', 'Share of contacts monitored to completion', 90.0, 'percent', MetricFamily.health_outcome, True, '§22.4', False),
	('symptom_to_care', 'Median time from symptom to care-seeking', 'Median hours from symptom onset to care', 24.0, 'hours', MetricFamily.health_outcome, False, '§22.4', False),
	('exposure_notified_24h', 'Exposure notifications delivered <24h', 'Share of exposure notifications delivered within 24 hours', 95.0, 'percent', MetricFamily.health_outcome, True, '§22.4', False),
	('corrections_24h', 'Misinformation corrections published <24h', 'Share of corrections published within 24 hours', 90.0, 'percent', MetricFamily.health_outcome, True, '§22.4', False),
	('malaria_tests', 'Malaria tests prompted', 'Malaria test referrals prompted', 100_000, 'tests', MetricFamily.health_outcome, True, '§22.4', False),
	('immunisation_onschedule', 'Immunisation doses on schedule', 'Tracked children whose doses are on schedule', 80.0, 'percent', MetricFamily.health_outcome, True, '§22.4', False),
	('medication_adherence', 'Medication adherence', 'Share of doses taken as scheduled', 70.0, 'percent', MetricFamily.health_outcome, True, '§22.4', False),
	# §22.5 technical — these must agree with §15.4, which the test asserts.
	('api_latency_p95_ms', 'API p95 latency', '95th percentile API latency', 300.0, 'ms', MetricFamily.technical, False, '§22.5', False),
	('uptime_pct', 'Uptime', 'Service availability', 99.9, 'percent', MetricFamily.technical, True, '§22.5', False),
	('crash_free_sessions', 'Crash-free sessions', 'Share of sessions with no crash', 99.5, 'percent', MetricFamily.technical, True, '§22.5', False),
	('sync_success', 'Sync success rate', 'Share of sync operations that succeed', 98.0, 'percent', MetricFamily.technical, True, '§22.5', False),
	('offline_availability', 'Offline feature availability', 'Core features usable offline', 100.0, 'percent', MetricFamily.technical, True, '§22.5', False),
	('battery_impact', 'Battery impact (all sensors)', 'Daily battery drain with all sensors on', 5.0, 'percent/day', MetricFamily.technical, False, '§22.5', False),
	('apk_base_size', 'APK base size', 'Base download size', 15.0, 'MB', MetricFamily.technical, False, '§22.5', False),
	# §22.6 privacy and trust
	('privacy_dashboard_review', 'Users who review privacy dashboard', 'Share of users who opened the privacy dashboard', 30.0, 'percent', MetricFamily.privacy_trust, True, '§22.6', False),
	('consent_revocation', 'Consent revocation rate', 'Share of consents withdrawn', 2.0, 'percent', MetricFamily.privacy_trust, False, '§22.6', False),
	('dsar_fulfilled_30d', 'Data subject access requests fulfilled <30 days', 'Share of access requests answered within 30 days', 100.0, 'percent', MetricFamily.privacy_trust, True, '§22.6', False),
	('security_incidents', 'Security incidents', 'Major security incidents', 0.0, 'incidents', MetricFamily.privacy_trust, False, '§22.6', False),
	('privacy_complaints', 'Privacy complaints', 'Privacy complaints as a share of users', 0.01, 'percent', MetricFamily.privacy_trust, False, '§22.6', False),
	('audit_findings_closed', 'Independent audit findings closed', 'Share of audit findings closed', 100.0, 'percent', MetricFamily.privacy_trust, True, '§22.6', False),
	# §22.7 equity
	('female_users', 'Female users', 'Share of users who are female', 50.0, 'percent', MetricFamily.equity, True, '§22.7', False),
	('outside_nairobi', 'Users outside Nairobi', 'Share of users outside Nairobi', 70.0, 'percent', MetricFamily.equity, True, '§22.7', False),
	('android_go', 'Users on Android Go devices', 'Share of users on Android Go', 30.0, 'percent', MetricFamily.equity, True, '§22.7', False),
	('feature_phone_reached', 'Users on feature phones reached', 'Feature-phone users reached', 5_000_000, 'people', MetricFamily.equity, True, '§22.7', False),
	('local_language', 'Local language usage', 'Share of sessions in a local language', 60.0, 'percent', MetricFamily.equity, True, '§22.7', False),
	('users_over_50', 'Users over 50', 'Share of users aged over 50', 15.0, 'percent', MetricFamily.equity, True, '§22.7', False),
)

# §22.8: "Disaggregated analysis by gender, geography, age, device." The four cuts an equity
# metric must carry. Named here so a report can say which it is missing rather than implying it has
# all four because it printed a percentage.
EQUITY_CUTS: tuple[EquityAxis, ...] = (EquityAxis.gender, EquityAxis.geography, EquityAxis.age, EquityAxis.device)

# §22's technical rows that repeat a §15.4 target. The numbers must be equal in both sections; this
# map is what the test walks to assert they are, rather than the equality being a coincidence
# nobody checks.
SHARED_WITH_CAPACITY: dict[str, str] = {'api_latency_p95_ms': 'api_latency_p95_ms', 'uptime_pct': 'uptime_pct'}


def _kpi(row: tuple[str, str, str, float, str, MetricFamily, bool, str, bool]) -> Kpi:
	kpi_id, name, definition, target, unit, family, higher, source, modelled = row
	return Kpi(kpi_id=kpi_id, name=name, definition=definition, target=target, unit=unit,
		family=family, higher_is_better=higher, source=source, modelled=modelled)


class MetricsService(LogMixin):
	def __init__(self) -> None:
		self._measured: dict[str, Measurement] = {}
		self._cuts: dict[str, set[str]] = {}
		assert len({r[0] for r in KPIS}) == len(KPIS), 'KPI ids must be unique'

	def kpis(self, family: MetricFamily | None = None) -> list[Kpi]:
		return [_kpi(r) for r in KPIS if family is None or r[5] is family]

	def record(self, m: Measurement) -> Measurement:
		assert any(r[0] == m.kpi_id for r in KPIS), f'{m.kpi_id} is not a §22 KPI'
		self._measured[m.kpi_id] = m
		if m.cuts:
			self._cuts.setdefault(m.kpi_id, set()).update(m.cuts)
		return m

	def result(self, kpi: Kpi) -> KpiResult:
		m = self._measured.get(kpi.kpi_id)
		if m is None:
			return KpiResult(kpi_id=kpi.kpi_id, name=kpi.name, family=kpi.family, target=kpi.target,
				observed=None, unit=kpi.unit, within_target=None, gap=None)
		within = m.observed >= kpi.target if kpi.higher_is_better else m.observed <= kpi.target
		return KpiResult(kpi_id=kpi.kpi_id, name=kpi.name, family=kpi.family, target=kpi.target,
			observed=m.observed, unit=kpi.unit, within_target=within,
			gap=round(m.observed - kpi.target, 4))

	def report(self, as_at_iso: str) -> MetricReport:
		"""Every §22 target beside its measurement. A target nobody measured is unmeasured, and
		`all_measured_targets_met` ignores it rather than counting it as a pass — a report that
		measured nothing is an empty report, not a green one."""
		results = [self.result(_kpi(r)) for r in KPIS]
		unmeasured = [r.kpi_id for r in results if r.observed is None]
		measured = [r for r in results if r.observed is not None]
		by_family: dict[str, int] = {}
		for r in results:
			by_family[r.family.value] = by_family.get(r.family.value, 0) + 1
		return MetricReport(
			as_at_iso=as_at_iso, results=results, unmeasured=unmeasured,
			all_measured_targets_met=bool(measured) and all(r.met() for r in measured),
			by_family=by_family,
		)

	def equity(self) -> EquityReport:
		"""§22.7 disaggregation coverage. An equity metric reported with no cut is a gap: the whole
		point of the family is a disparity, and a single percentage cannot show one."""
		gaps: list[EquityGap] = []
		covered: set[str] = set()
		for r in KPIS:
			if r[5] is not MetricFamily.equity:
				continue
			kpi_id = r[0]
			present = self._cuts.get(kpi_id, set())
			if not present:
				gaps.append(EquityGap(kpi_id=kpi_id, axis='any',
					reason='reported as a single figure with no disaggregation'))
				continue
			for axis in EQUITY_CUTS:
				if axis.value in present:
					covered.add(axis.value)
				else:
					gaps.append(EquityGap(kpi_id=kpi_id, axis=axis.value,
						reason=f'no {axis.value} cut recorded for this metric'))
		return EquityReport(
			axes=[a.value for a in EQUITY_CUTS], covered_axes=sorted(covered), gaps=gaps,
			complete=not gaps,
			note='§22.7 metrics are disaggregated by gender, geography, age and device (§22.8).',
		)


def capacity_agreement() -> list[tuple[str, float, float]]:
	"""The §22.5 rows that repeat a §15.4 target, as (kpi_id, §22 target, §15.4 target). A caller
	can assert every pair is equal; the test does, so the two sections cannot drift apart."""
	capacity = {metric: target for metric, target, _unit, _source, _higher in SCALE_TARGETS}
	out: list[tuple[str, float, float]] = []
	for kpi_id, capacity_id in SHARED_WITH_CAPACITY.items():
		ours = next(target for r in KPIS if r[0] == kpi_id for target in [r[3]])
		out.append((kpi_id, ours, capacity[capacity_id]))
	return out
