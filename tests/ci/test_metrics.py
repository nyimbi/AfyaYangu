"""§22 success metrics: the targets as data, the measurement rule, and the equity disaggregation.

Two failures this exists to prevent. A report that counts an unmeasured target as met, which is the
green-dashboard-from-silence §15.4's capacity report already refuses. And an equity metric printed
as one percentage, which cannot show the disparity §22.7 exists to surface.
"""
import httpx

from afya.auth.service import OPERATIONAL_ROLES, AuthService
from afya.governance.service import SCALE_TARGETS
from afya.metrics.service import EQUITY_CUTS, EVALUATION, KPIS, MetricsService, capacity_agreement
from afya.metrics.views import MetricFamily, Measurement
from afya.service import build_services, create_app


async def _staff(c: httpx.AsyncClient, auth: AuthService, role: str) -> str:
	"""A staff token. §17.4 splits issuance: `auditor` is operational and is provisioned directly;
	every other staff role goes through the app's PKCE flow, which `provision_staff` refuses."""
	from afya.auth.views import s256
	from afya.privacy.views import RBACRole
	if RBACRole(role) in OPERATIONAL_ROLES:
		return auth.provision_staff(f'ops-{role}', RBACRole(role), registrar='MoH ops').access_token
	verifier = 'v' * 64
	authz = (await c.post('/auth/pkce/authorize', json={
		'client_id': 'app', 'redirect_uri': 'afya://cb', 'code_challenge': s256(verifier), 'state': 'state-1234',
	})).json()
	return (await c.post('/auth/pkce/token', params={'role': role}, json={
		'authorization_code': authz['authorization_code'], 'client_id': 'app',
		'redirect_uri': 'afya://cb', 'code_verifier': verifier,
	})).json()['access_token']


def test_every_spec_section_22_subsection_is_represented() -> None:
	"""§22.1–§22.7 each contribute rows; a subsection that vanishes means the table was dropped."""
	sources = {r[7] for r in KPIS}
	assert sources >= {f'§22.{n}' for n in range(1, 8)}, f'missing subsections: {sources}'
	families = {r[5] for r in KPIS}
	assert families == set(MetricFamily), 'every §22 family must have at least one KPI'


def test_lives_saved_is_modelled_not_given_an_invented_target() -> None:
	"""§22.1 says lives saved is "measured via modelling" and gives no number. Inventing one would
	be the fabrication this file exists to avoid, so it is flagged `modelled` instead."""
	saved = next(r for r in KPIS if r[0] == 'lives_saved')
	assert saved[8] is True, 'lives_saved must be marked modelled'
	assert saved[3] == 0.0, 'no target may be invented for a modelled metric'


def test_the_technical_rows_agree_with_section_15_4() -> None:
	"""§22.5 and §15.4 state the same numbers. A report that said p95 <300 ms in one view and
	something else in another is the self-contradiction this asserts against."""
	pairs = capacity_agreement()
	assert len(pairs) == 2, 'both shared rows must be checked'
	for kpi_id, ours, capacity in pairs:
		assert ours == capacity, f'{kpi_id}: §22.5 says {ours}, §15.4 says {capacity}'
	assert {row[0] for row in SCALE_TARGETS} >= {'api_latency_p95_ms', 'uptime_pct'}


def test_an_unmeasured_target_is_not_counted_as_met() -> None:
	"""The rule. With nothing measured the report is empty, not green."""
	svc = MetricsService()
	report = svc.report('2026-10-10')
	assert len(report.unmeasured) == len(KPIS)
	assert report.all_measured_targets_met is False, 'a report that measured nothing is not a pass'
	assert report.by_family['technical'] >= 7


def test_direction_is_respected_per_kpi() -> None:
	"""Latency, care-seeking time, battery drain and complaint rates pass by being *under* target.
	A report that got the direction backwards would pass a 40-hour delay as comfortably under 24."""
	svc = MetricsService()
	svc.record(Measurement(kpi_id='api_latency_p95_ms', observed=250.0, as_at_iso='2026-10-10'))
	svc.record(Measurement(kpi_id='symptom_to_care', observed=40.0, as_at_iso='2026-10-10'))
	svc.record(Measurement(kpi_id='uptime_pct', observed=99.95, as_at_iso='2026-10-10'))
	results = {r.kpi_id: r for r in svc.report('2026-10-10').results}
	assert results['api_latency_p95_ms'].within_target is True, '250 ms meets a 300 ms cap'
	assert results['symptom_to_care'].within_target is False, '40 hours does not meet a 24-hour cap'
	assert results['uptime_pct'].within_target is True, 'higher is better here'


def test_an_equity_metric_with_no_cut_is_a_gap() -> None:
	"""§22.7 and §22.8: the equity family must be disaggregated by gender, geography, age, device.
	A single percentage cannot show a disparity, so reporting one is reported as a gap."""
	svc = MetricsService()
	svc.record(Measurement(kpi_id='female_users', observed=52.0, as_at_iso='2026-10-10'))
	eq = svc.equity()
	assert eq.complete is False
	assert any(g.kpi_id == 'female_users' and g.axis == 'any' for g in eq.gaps), \
		'a metric with no disaggregation at all must be flagged'
	# With all four cuts recorded it is complete.
	svc.record(Measurement(kpi_id='female_users', observed=52.0, as_at_iso='2026-10-10',
		cuts={'gender': 'female', 'geography': 'county', 'age': 'over_50', 'device': 'android_go'}))
	partial = svc.equity()
	assert 'gender' in partial.covered_axes
	assert all(a.value in partial.axes for a in EQUITY_CUTS)


def test_the_canary_watches_the_silence_rule_fail() -> None:
	"""Canary. If an unmeasured target were counted as met, the report would be green with nothing
	behind it — the exact failure. Assert the flag flips on a single measurement."""
	svc = MetricsService()
	assert svc.report('2026-10-10').all_measured_targets_met is False
	svc.record(Measurement(kpi_id='uptime_pct', observed=99.99, as_at_iso='2026-10-10'))
	after = svc.report('2026-10-10')
	assert after.all_measured_targets_met is True and 'uptime_pct' not in after.unmeasured
	assert len(after.unmeasured) == len(KPIS) - 1, 'only the measured one left the unmeasured list'


async def test_the_routes_are_scoped_and_refuse_an_unknown_kpi() -> None:
	services = build_services()
	auth: AuthService = services['auth']  # type: ignore[assignment]
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		anon = (await c.post('/auth/anonymous', json={'subject_ref': 'U1'})).json()['token']
		assert (await c.get('/metrics/report', headers={'authorization': f'Bearer {anon}'})).status_code == 403
		assert (await c.get('/metrics/report')).status_code in (401, 403)
		auditor = await _staff(c, auth, 'auditor')
		h = {'authorization': f'Bearer {auditor}'}
		rep = (await c.get('/metrics/report', headers=h)).json()
		assert rep['all_measured_targets_met'] is False and len(rep['unmeasured']) == len(KPIS)
		assert (await c.get('/metrics/kpis?family=technical', headers=h)).json()['kpis'][0]['source'] == '§22.5'
		assert (await c.get('/metrics/kpis?family=nonsense', headers=h)).status_code == 422
		assert (await c.get('/metrics/equity', headers=h)).json()['axes'] == [a.value for a in EQUITY_CUTS]


# --- §22.8 the five-level evaluation framework ---

def _spec_evaluation() -> list[tuple[str, str, str]]:
	"""§22.8's five rows as (level, method, frequency), read out of the spec rather than restated."""
	import re
	from pathlib import Path
	text = Path('docs/spec.md').read_text()
	section = text.split('### 22.8 Evaluation Framework', 1)[1].split('\n---', 1)[0]
	rows: list[tuple[str, str, str]] = []
	for line in section.splitlines():
		cells = [c.strip() for c in line.strip().strip('|').split('|')]
		if len(cells) != 3 or cells[0] in ('Level', '') or set(cells[0]) <= {'-', ' '}:
			continue
		rows.append((re.sub(r'\*\*', '', cells[0]).lower(), cells[1], cells[2]))
	return rows


def test_the_evaluation_levels_are_the_section_rows() -> None:
	"""§22.8's five rows, cell for cell. A level that vanished from the code is an evaluation the
	programme no longer runs, and a method or cadence that drifted is a review on a different clock."""
	from afya.metrics.service import EVALUATION
	rows = _spec_evaluation()
	assert len(rows) == 5, f'§22.8 must have five levels, parsed {len(rows)}'
	assert [(e.level.value, e.method, e.frequency) for e in EVALUATION] == rows
	# The cadence string is a duty nobody can be late for; `cadence_days` is what makes it checkable.
	months = {'monthly': 30, 'quarterly': 91, 'semi-annually': 182, 'annually': 365}
	for e in EVALUATION:
		assert e.cadence_days == months[e.frequency.lower()], f'{e.level.value} cadence'
		assert e.at_least_quarterly() == (e.cadence_days <= 91)
	assert sum(e.at_least_quarterly() for e in EVALUATION) == 3, 'monthly + the two quarterlies'


def test_every_metric_family_is_read_by_an_evaluation_level() -> None:
	"""The finding. §22 has seven families and §22.8 names five levels; a family no level reads is
	collected and never looked at — the same shape as a §7.3 feature outside the tier map."""
	framework = MetricsService().evaluation()
	assert framework.families == [f.value for f in MetricFamily]
	assert framework.uncovered_families == [], (
		f'no §22.8 level reads: {framework.uncovered_families}')
	assert set(framework.levels_by_cadence) == {e.level.value for e in EVALUATION}
	assert framework.levels_by_cadence[0] == 'process', 'the monthly level runs first'
	assert framework.levels_by_cadence[-1] == 'impact', 'the annual level runs last'
	# A level with no family behind it is a review meeting with nothing to review.
	for e in EVALUATION:
		assert e.families, f'{e.level.value} reads no metric family'
		assert all(isinstance(f, MetricFamily) for f in e.families)


def test_the_canary_watches_the_uncovered_family_check_fire() -> None:
	"""Canary. Drop the level that reads the equity family and the coverage check must name it — if
	this passes, the check is comparing the family list against itself."""
	from afya.metrics import service as ms
	original = ms.EVALUATION
	try:
		ms.EVALUATION = tuple(e for e in original if e.level is not ms.EvaluationLevel.equity)
		uncovered = ms.MetricsService().evaluation().uncovered_families
		assert uncovered == ['equity'], f'the dropped level went unnoticed: {uncovered}'
	finally:
		ms.EVALUATION = original
	assert ms.MetricsService().evaluation().uncovered_families == [], 'canary left the module mutated'


def test_the_privacy_level_has_a_duty_behind_it_and_the_two_clocks_are_different() -> None:
	"""§22.8 puts "DPIA review" on a semi-annual clock; §24.7 schedules the DPIA update *before each
	Tier-4 activation*. Both are real and they are not the same duty, so the review level must name a
	§24 obligation that exists — a review level with no duty behind it is a meeting nobody scheduled.
	"""
	from afya.operations.service import OBLIGATIONS
	from afya.metrics.service import EVALUATION
	privacy = next(e for e in EVALUATION if e.level.value == 'privacy')
	assert privacy.frequency == 'Semi-annually' and privacy.cadence_days == 182
	dpia = next(o for o in OBLIGATIONS if o.duty == 'DPIA update')
	assert dpia.section == '§24.7' and dpia.trigger is not None, '§24.7 triggers the DPIA, it does not schedule it'
	assert dpia.cadence_days is None, 'a triggered duty given a cadence reads as perpetually overdue'
	# The two clocks differ, and that is the finding: the semi-annual review cannot stand in for the
	# per-activation update, so neither may be dropped as a duplicate of the other.
	assert 'DPIA' in privacy.method


async def test_the_evaluation_route_is_scoped_and_serves_the_framework() -> None:
	services = build_services()
	auth: AuthService = services['auth']  # type: ignore[assignment]
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		anon = (await c.post('/auth/anonymous', json={'subject_ref': 'U2'})).json()['token']
		assert (await c.get('/metrics/evaluation', headers={'authorization': f'Bearer {anon}'})).status_code == 403
		assert (await c.get('/metrics/evaluation')).status_code in (401, 403)
		h = {'authorization': f'Bearer {await _staff(c, auth, "auditor")}'}
		body = (await c.get('/metrics/evaluation', headers=h)).json()
		assert [lvl['level'] for lvl in body['levels']] == [e.level.value for e in EVALUATION]
		assert body['uncovered_families'] == []
