"""§20 distribution and growth, §21 rollout phasing.

§20 and §21 read as marketing, and two of §20.2's six levers make claims about *this repository*:
"open-source client" and "Under 15 MB". Neither was checkable, and a claim about the artefact that
nobody checks stays true by nobody looking. `readiness` answers both from the artefacts.

§21.1 is a gate as well as a calendar: each phase carries a tier ceiling, so a deployment running
Tier 4 while its plan says Phase 2 has skipped its own gate. `status` crosses the two.
"""
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from typing import Any

from afya.privacy.views import RBACRole
from afya.registry.service import FeatureRegistry
from afya.rollout.service import APK_BUDGET_MB, PHASES, RETENTION, RolloutService
from afya.rollout.views import GrowthLever, Phase, PhaseSpec, RetentionMechanism
from afya.service import build_services, create_app


def _svc(apk: float | None = None, root: Path | None = None) -> RolloutService:
	return RolloutService(FeatureRegistry(), apk_size_mb=apk, repo_root=root)


def _auditor_app() -> tuple[Any, dict[str, str]]:
	svc = build_services()
	auth: Any = svc['auth']
	tok = auth.provision_staff('ops-aud', RBACRole.auditor, registrar='MoH ops').access_token
	return create_app(svc), {'authorization': f'Bearer {tok}'}


# --- §21.1 the phases ------------------------------------------------------------------------

def test_the_phase_table_matches_the_spec() -> None:
	"""§21.1's seven rows, with the tier ceiling each authorises. The ceilings are the gate: they
	are what a deployment is checked against, so a phase that quietly gained Tier 4 would authorise
	an outbreak module twelve months early."""
	assert len(PHASES) == 7
	ceilings = {p.phase: p.max_tier for p in PHASES}
	assert ceilings[Phase.phase_0_foundation] is None, 'phase 0 delivers nothing to a user'
	assert ceilings[Phase.phase_1_information] == 1
	assert ceilings[Phase.phase_2_utility] == 1
	assert ceilings[Phase.phase_3_retention] == 2
	assert ceilings[Phase.phase_4_daily_habit] == 3
	assert ceilings[Phase.phase_5_outbreak_ready] == 4
	assert ceilings[Phase.phase_6_scale] == 4
	assert [p.phase.order for p in PHASES] == list(range(7)), 'phases must be in spec order'


def test_a_phase_authorising_a_tier_over_no_channel_is_refused() -> None:
	"""Canary at the model: §21.1's Channels column is empty only for Phase 0, because a phase that
	promises a tier with no way to reach a person is a capability nobody can use."""
	with pytest.raises(ValidationError, match='over no channel'):
		PhaseSpec(phase=Phase.phase_1_information, timeline='x', objective='y', channels=[],
		          max_tier=1, weeks_start=0, weeks_end=4)


def test_a_tier_above_the_phase_ceiling_is_a_mismatch() -> None:
	"""The gate. §11.1 puts three keys on Tier 4; §21.1 puts it at Phase 5. A deployment at Phase 2
	with Tier 4 on has skipped the phases that build up to it."""
	svc = _svc()
	early = svc.status(Phase.phase_2_utility, 4)
	assert early.phase_mismatch is True and early.max_tier == 1
	assert 'tier 4' in early.note and 'tier 1' in early.note, 'the finding names both numbers'
	late = svc.status(Phase.phase_5_outbreak_ready, 4)
	assert late.phase_mismatch is False and late.max_tier == 4
	inside = svc.status(Phase.phase_3_retention, 2)
	assert inside.phase_mismatch is False, 'at the ceiling is inside it'
	with pytest.raises(AssertionError, match='tiers run 1 to 4'):
		svc.status(Phase.phase_1_information, 5)


# --- §20.2 the growth levers -----------------------------------------------------------------

def test_every_lever_is_present_and_only_the_repo_claims_are_checkable() -> None:
	"""Six levers in §20.2, of which exactly two make a claim about this repository. Marking all
	six checkable would be the dodge this module exists to avoid — four of them are partnership and
	design commitments with nothing to inspect."""
	svc = _svc()
	levers = svc.growth_levers()
	assert [le.number for le in levers] == [1, 2, 3, 4, 5, 6]
	checkable = {le.number: le.check for le in levers if le.checkable}
	assert set(checkable) == {3, 5}, 'only trust (open source) and friction (size) name an artefact'
	assert 'licence' in (checkable[3] or '')
	assert 'APK' in (checkable[5] or '') or 'size' in (checkable[5] or '')


def test_a_checkable_lever_with_no_check_is_refused() -> None:
	with pytest.raises(ValidationError, match='checkable but names no check'):
		GrowthLever(number=1, lever='x', why='y', action='z', checkable=True)


def test_the_apk_budget_comes_from_the_metric_not_a_second_copy() -> None:
	"""§20.2 lever 5 says "Under 15 MB" and §22.5 sets the same number. Two copies of one number is
	the drift this repo keeps finding, so the rollout reads §22.5's table."""
	from afya.metrics.service import KPIS
	assert APK_BUDGET_MB == next(row[3] for row in KPIS if row[0] == 'apk_base_size') == 15.0


def test_an_unweighed_build_is_not_reported_as_small() -> None:
	"""The rule §15.4 and §22 already apply: silence is not a pass. A build nobody weighed gets
	`apk_within_budget=None`, not True."""
	unweighed = _svc(apk=None).readiness()
	assert unweighed.apk_within_budget is None and unweighed.apk_base_size_mb is None
	assert 'unmeasured' in unweighed.note
	assert _svc(apk=12.0).readiness().apk_within_budget is True
	assert _svc(apk=60.0).readiness().apk_within_budget is False


def test_the_open_source_claim_is_answered_from_the_repository() -> None:
	"""§20.2 lever 3 and §23.5 both rest on the client being open source. The spec names no licence,
	so this checks that *a* licence was chosen — picking one is the product owner's call."""
	svc = _svc()
	licence = svc.licence()
	readiness = svc.readiness()
	assert readiness.open_source is (licence is not None)
	assert readiness.license == licence
	if licence is None:
		assert 'no licence file' in readiness.note, 'an unbacked claim must say so'
	else:
		assert licence.strip(), 'a licence file with no text is not a licence'


def test_the_licence_lookup_can_actually_find_one(tmp_path: Path) -> None:
	"""Canary for the lookup: a check that has only ever been seen return None is not evidence that
	it can find a file."""
	empty = _svc(root=tmp_path)
	assert empty.licence() is None, 'an empty directory carries no licence'
	(tmp_path / 'LICENSE').write_text('MIT License\n\nCopyright (c) 2026\n', encoding='utf-8')
	found = _svc(root=tmp_path)
	assert found.licence() == 'MIT License' and found.readiness().open_source is True


# --- §20.6 the retention engine --------------------------------------------------------------

def test_every_retention_mechanism_resolves_to_a_registered_feature() -> None:
	"""§20.6 is the argument that the product outlives the outbreak: nine mechanisms, each carried
	by a named feature. A mechanism on an unregistered feature is an argument with nothing under it."""
	svc = _svc()
	assert len(RETENTION) == 9
	assert svc.unregistered_retention_features() == []
	assert all(m.registered for m in svc.retention_mechanisms())
	assert svc.is_registered('MON-001') is True and svc.is_registered('ZZZ-999') is False, \
		'the cross-check must be able to say no'


def test_a_mechanism_on_an_unbuilt_feature_is_reported() -> None:
	"""The negative direction of the cross-check, reachable because the table is injectable. With
	the real §20.6 table every feature resolves, so a check that could never report a gap would be
	indistinguishable from one that works — the reason this path exists as a test at all."""
	orphan = RetentionMechanism(mechanism='A mechanism on nothing', feature_id='MON-099',
	                            frequency='Weekly', cadence_days=7)
	svc = RolloutService(FeatureRegistry(), mechanisms=(*RETENTION, orphan))
	assert svc.unregistered_retention_features() == ['MON-099']
	assert 'MON-099' in svc.readiness().note, 'the readiness note must name the unbacked mechanism'


def test_only_the_scheduled_mechanisms_carry_a_cadence() -> None:
	"""§20.6's frequency column: five mechanisms name a period and four say "as needed". Giving a
	facility finder a cadence would invent a return visit it does not cause."""
	by_id = {m.feature_id: m for m in RETENTION}
	assert by_id['MON-004'].cadence_days == 1, 'medication reminders are daily'
	assert by_id['MON-001'].cadence_days == 30
	assert by_id['ALT-001'].cadence_days == 7
	for fid in ('FND-001', 'MED-001', 'REC-002', 'MED-004'):
		assert by_id[fid].cadence_days is None and by_id[fid].returns_regularly() is False, fid


def test_the_antipatterns_are_named_and_the_checkable_ones_say_what_checks_them() -> None:
	"""§20.2's "What does not work" list. Four of the five are properties someone could ship by
	accident — a login wall, a 60 MB app, a name with the disease in it, unrequested push — and
	naming them is what makes them refusable in review."""
	patterns = {p.antipattern: p for p in _svc().readiness().antipatterns}
	assert len(patterns) == 5
	assert 'A login wall' in patterns and 'A name with "Ebola" in it' in patterns
	assert patterns['A login wall'].checkable is True
	assert 'anonymous' in (patterns['A login wall'].check or ''), \
		'§20.2 requires Tier 1 without an account, which is what the anonymous token provides'
	assert patterns['Fear'].checkable is False, 'fear is not a property of the artefact'


def test_the_launch_sequence_is_in_order_and_covers_the_three_windows() -> None:
	svc = _svc()
	steps = svc.launch_sequence()
	assert len(steps) == 18, '§20.5 lists 6 pre-launch, 7 launch-week and 5 weeks-2-4 steps'
	assert [s.sequence for s in steps[:6]] == ['Phase 0'] * 6
	assert {s.sequence for s in steps} == {'Phase 0', 'Launch week', 'Weeks 2-4'}
	assert any('719' in s.step for s in steps), 'the hotline integration is a pre-launch step'


# --- routes ----------------------------------------------------------------------------------

async def test_the_routes_are_scoped_and_the_plan_is_public() -> None:
	app, h = _auditor_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
		# §21.1 names no person and no number about one, so the plan is readable by anyone.
		plan = (await c.get('/rollout/phases')).json()
		assert len(plan['phases']) == 7 and plan['current']['phase'] == 'phase_1_information'
		# The readiness report is evidence and takes the auditor's scope.
		assert (await c.get('/rollout/readiness')).status_code in (401, 403)
		report = (await c.get('/rollout/readiness', headers=h)).json()
		assert report['unregistered_retention_features'] == []
		assert report['apk_within_budget'] is None, 'the build has not been weighed in this deployment'


async def test_the_status_route_reports_the_live_tier_against_the_phase() -> None:
	app, h = _auditor_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
		out = (await c.get('/rollout/status', params={'phase': 'phase_3_retention'}, headers=h)).json()
		assert out['phase'] == 'phase_3_retention' and out['max_tier'] == 2
		assert out['active_tier'] == 3, 'Tier 4 is dormant, so the deployment runs at Tier 3'
		assert out['phase_mismatch'] is True, 'tier 3 over a tier-2 ceiling is the finding'
		assert (await c.get('/rollout/status', params={'phase': 'nope'}, headers=h)).status_code == 422
