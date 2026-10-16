"""§20 distribution and growth, §21 rollout phasing.

§20 and §21 read as marketing, and two of §20.2's six levers make claims about *this repository*:
"open-source client" and "Under 15 MB". Neither was checkable, and a claim about the artefact that
nobody checks stays true by nobody looking. `readiness` answers both from the artefacts.

§21.1 is a gate as well as a calendar: each phase carries a tier ceiling, so a deployment running
Tier 4 while its plan says Phase 2 has skipped its own gate. `status` crosses the two.
"""
from pathlib import Path

import json
import re as _re

import httpx
import pytest
from pydantic import ValidationError
from typing import Any

from afya.privacy.views import RBACRole
from afya.registry.service import CHANNELS, FeatureRegistry
from afya.rollout.service import ALL_CHANNELS, APK_BUDGET_MB, PHASES, RETENTION, RolloutService
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


def _spec_phase_rows() -> list[list[str]]:
	"""§21.1's seven rows read out of `docs/spec.md`, so a revision to the section fails here.

	The Channels cell is the interesting one and it is carried verbatim: §21.1 writes it three ways
	(`CHAN-0,1,2,3,4,5`, `+ CHAN-6`, `All`) and none of them is a list of ids. Reading the cell is
	what lets the expansion below be checked against the section rather than against itself.
	"""
	from pathlib import Path
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	section = text.split('### 21.1 Phase Overview', 1)[1].split('\n---', 1)[0]
	rows: list[list[str]] = []
	for line in section.splitlines():
		if not line.startswith('|') or set(line) <= set('|-: '):
			continue
		cells = [c.strip().replace('**', '') for c in line.strip('|').split('|')]
		if len(cells) != 5 or cells[0] == 'Phase':
			continue
		rows.append(cells)
	return rows


def test_the_channels_column_is_expanded_and_accumulated() -> None:
	"""§21.1's Channels column, and the two ways carrying it as-is went wrong.

	The column is written in three shapes and the first cut carried the cell verbatim as `channels`.
	Two defects followed from that, and neither is visible to a check on the ceilings:

	* **`All` was served as a channel id.** `/rollout/phases` is open by design, and it answered
	  `"channels": ["all"]` for four of the seven phases — a quantifier sitting in a list of
	  `CHAN-` ids, on the one rollout surface a partner reads. `'all'` is not one of §5.2's seven
	  channels and the expansion is what makes it seven ids instead.
	* **`+ CHAN-6` was read as exclusive.** The `+` means *in addition to the phase before*, so
	  §21.1's Phase 2 row opens all seven channels and the cell names only the seventh. Carried
	  as-is, Phase 2's channel set **shrank** from six to one as the rollout advanced — a plan
	  reaching fewer people in its second month than its first.

	The accumulation is asserted across all rows rather than on Phase 2 alone, because the property
	is what the `+` means and a later row written the same way has to inherit it.
	"""
	spec = _spec_phase_rows()
	assert len(spec) == 7, f'§21.1 lists seven phases, found {len(spec)}'
	assert [p.channels_cell for p in PHASES] == [r[3] for r in spec], 'the Channels column verbatim'
	assert [p.timeline for p in PHASES] == [r[1] for r in spec], 'the Timeline column verbatim'
	assert [p.objective for p in PHASES] == [r[2] for r in spec], 'the Objective column'
	# The Tiers column, read the same way and carried verbatim. Without this a ceiling could be
	# raised to make a deliverable fit under it — the "resolve the contradiction by picking a
	# column" move the crossing check deliberately refuses — and the ceiling assertions in
	# `test_the_phase_table_matches_the_spec` would read the new number as self-consistent.
	assert [p.tiers_cell for p in PHASES] == [r[4] for r in spec], 'the Tiers column verbatim'

	# Every served channel is a §5.2 CHAN id, so the quantifier cannot come back.
	for spec_row, phase in zip(spec, PHASES):
		assert all(c.startswith('CHAN-') and len(c) == 8 for c in phase.channels), \
			f'{phase.phase.value} serves a non-id channel: {phase.channels}'
		if spec_row[3] == 'All':
			assert phase.channels == list(ALL_CHANNELS), f'{phase.phase.value} reads All as a channel'
		if spec_row[3] == '—':
			assert phase.channels == [], f'{phase.phase.value} is the empty row'

	# The accumulation, in both directions: the set grows or holds, and Phase 2 is the row that
	# proves it (`+ CHAN-6` is seven ids, not one).
	sets = [(p.phase.value, set(p.channels)) for p in PHASES if p.max_tier is not None]
	for (prev_name, prev), (cur_name, cur) in zip(sets, sets[1:]):
		assert prev <= cur, f'{cur_name} opens {sorted(prev - cur)} that {prev_name} already opened'
	assert sets[1] == ('phase_2_utility', set(ALL_CHANNELS)), '§21.1 row 2 writes `+ CHAN-6`'
	assert PHASES[2].channels_cell == '+ CHAN-6', 'and the cell is still the section\'s own words'


def test_a_phase_authorising_a_tier_over_no_channel_is_refused() -> None:
	"""Canary at the model: §21.1's Channels column is empty only for Phase 0, because a phase that
	promises a tier with no way to reach a person is a capability nobody can use."""
	with pytest.raises(ValidationError, match='over no channel'):
		PhaseSpec(phase=Phase.phase_1_information, timeline='x', objective='y', channels=[],
		          channels_cell='—', max_tier=1, tiers_cell='Tier 1', weeks_start=0, weeks_end=4)


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
	design commitments with nothing to inspect.

	This is the *count* half. `test_the_lever_table_is_the_sections_six_rows` is the other, and it
	exists because this one passed for a revision against a table with three drifted cells: a
	predicate over `[le.number]` and the checkable set is a strict subset of what §20.2 prints.
	"""
	svc = _svc()
	levers = svc.growth_levers()
	assert [le.number for le in levers] == [1, 2, 3, 4, 5, 6]
	checkable = {le.number: le.check for le in levers if le.checkable}
	assert set(checkable) == {3, 5}, 'only trust (open source) and friction (size) name an artefact'
	assert 'licence' in (checkable[3] or '')
	assert 'APK' in (checkable[5] or '') or 'size' in (checkable[5] or '')


def test_the_lever_table_is_the_sections_six_rows() -> None:
	"""§20.2, cell for cell, all four columns. Three cells had drifted and no test could see it:

	* **Lever 5's `why` and `action` were swapped.** The section's reason is the size/offline
	  constraint and its act is "Engineering requirements"; the code stored the reason as the act,
	  so the lever said *what* to do where it owed *why* and the section's action was absent.
	* **Lever 6's `why` was invented** — "A health profile nobody completes is not a profile" is a
	  sentence the spec does not contain anywhere.
	* **Lever 4's Action cell was normalised**, `CHAN-5` to `CHAN-005`, which is the §21.1
	  abbreviation defect in a second place.

	The swapped and invented cells read as plausible prose, which is why a row count and a
	checkable-set assertion passed over them for a revision. `action_cell` is the column verbatim
	and `action` the same column with any spec id resolved, so the resolution is compared against
	the section's own text rather than a name retyped here.
	"""
	from afya.rollout.service import LEVER_ID_RESOLUTIONS
	from afya.registry.service import FeatureRegistry
	spec = _spec_table('### 20.2 The Six Growth Levers', '\n**What does not work', 4)
	levers = _svc().growth_levers()
	assert len(spec) == 6, f'§20.2 lists six levers, found {len(spec)}'
	assert [le.number for le in levers] == [int(r[0]) for r in spec]
	assert [le.lever for le in levers] == [r[1].replace('**', '') for r in spec], 'the Lever column'
	assert [le.why for le in levers] == [r[2] for r in spec], 'the Why-it-matters column'
	assert [le.action_cell for le in levers] == [r[3] for r in spec], 'the Action column verbatim'
	# The resolution, checked against the cell it came from: substituting the cell's own id must
	# produce what the row serves, so a renamed feature fails here rather than serving a stale name.
	names = {f.id: f.name for f in FeatureRegistry().FEATURES}
	for number, (cell_id, feature_id) in LEVER_ID_RESOLUTIONS.items():
		row = next(le for le in levers if le.number == number)
		assert feature_id in names, f'lever {number} resolves {cell_id} to an id the registry lacks'
		assert row.action == row.action_cell.replace(cell_id, names[feature_id]), f'lever {number}'
	# And no cell may carry a spec handle onto a surface: §20.2 lever 4 is the only one that names
	# an id, and it is the only row whose two spellings differ.
	resolved = [le.number for le in levers if le.action != le.action_cell]
	assert resolved == [4], f'levers whose served action differs from the section: {resolved}'
	assert 'CHAN-5' in levers[3].action_cell and 'CHAN-5' not in levers[3].action


async def test_no_spec_handle_reaches_a_lever_surface() -> None:
	"""The standing constraint, on the wire. §20.2's Action column writes `CHAN-5`, and the gate
	every other surface uses matches `PREFIX-\\d{3}` — so an abbreviated handle is invisible to it.
	That is the "one of two spellings" failure: the checker enumerates one of the two ways to write
	an id and reports clean.

	The pattern here is deliberately loose (`\\d{1,3}`), because the defect this guards against is
	the *short* spelling. It is read off the served response, not the model, for the same reason
	`test_the_acquisition_plan_is_public_and_the_coverage_evidence_is_scoped` is: the failure is a
	served string.
	"""
	import re as _re
	handle = _re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{1,3}\b')
	from afya.rollout.service import GROWTH_LEVERS
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		body = (await c.get('/rollout/acquisition')).text
		resp = await c.get('/rollout/acquisition/levers')
		levers = resp.text
	assert resp.status_code == 200, levers
	assert not handle.findall(body), f'a spec handle on a partner-facing surface: {handle.findall(body)}'
	assert not handle.findall(levers), f'a spec handle on the lever surface: {handle.findall(levers)}'
	# The count and the served action, so the gate above cannot pass by serving an empty plan — a
	# `findall` over nothing is clean for the same reason a gate that never ran is green.
	served = resp.json()['levers']
	assert len(served) == 6, f'§20.2 prints six levers; the route serves {len(served)}'
	assert [le['number'] for le in served] == [1, 2, 3, 4, 5, 6]
	assert served[3]['action'] == 'Structured intermediary programme (Human Intermediaries)', \
		'the id resolved to a registry name, not to itself and not to nothing'
	assert 'action_cell' not in served[3], 'the verbatim cell carries the handle and must not travel'
	# The gate is not vacuous: the section's cell it is derived from *does* carry the handle, so a
	# build that served the cell verbatim would fail above.
	assert handle.findall(GROWTH_LEVERS[3].action_cell) == ['CHAN-5'], \
		'the gate would pass against a table that never had the defect'


def test_a_checkable_lever_with_no_check_is_refused() -> None:
	with pytest.raises(ValidationError, match='checkable but names no check'):
		GrowthLever(number=1, lever='x', why='y', action='z', action_cell='z', checkable=True)


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


def _spec_launch_windows() -> list[tuple[str, list[str]]]:
	"""§20.5's three window headings and the bullets under each, read out of the section.

	The heading test is `startswith('**')` and not `endswith(':')`: every heading in the section ends
	`:**`, so the narrower form finds no window at all and returns an empty plan — a clean-looking
	result from a predicate that matches nothing, which is the failure this repo keeps recording.
	"""
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	section = text.split('### 20.5 Launch Sequence', 1)[1].split('\n---', 1)[0]
	windows: list[tuple[str, list[str]]] = []
	for line in section.splitlines():
		line = line.strip()
		if line.startswith('**') and line.endswith(':**'):
			windows.append((line.strip('*').rstrip(':'), []))
		elif line.startswith('- ') and windows:
			windows[-1][1].append(line[2:])
	return windows


def test_the_launch_sequence_is_the_sections_three_windows_cell_for_cell() -> None:
	"""§20.5, bullet for bullet against the section's own text.

	The version this replaces asserted `{s.sequence for s in steps} == {'Phase 0', 'Launch week',
	'Weeks 2-4'}` — a set literal the test also wrote, so it compared the code to itself and was
	blind to the drift it existed to catch. §20.5 writes `Weeks 2–4` with an **en-dash**; the code
	carried an ASCII hyphen in all five of those rows *and* in the test, so both sides agreed and
	nothing compared either to the section. That is the same drift §21.1's Timeline column had, one
	subsection over, and the `window_cell`/`sequence` split is the same remedy.
	"""
	windows = _spec_launch_windows()
	assert [w for w, _ in windows] == [
		'Phase 0 — Pre-launch (2 weeks before)', 'Launch week', 'Weeks 2–4'], windows
	spec_steps = [(window, step) for window, steps in windows for step in steps]
	svc_steps = _svc().launch_sequence()
	assert len(spec_steps) == 18, f'§20.5 lists 18 bullets, found {len(spec_steps)}'
	assert len(svc_steps) == 18, f'§20.5 lists 18 bullets, code carries {len(svc_steps)}'
	assert [s.step for s in svc_steps] == [step for _, step in spec_steps], \
		'a launch step drifted from §20.5, or moved between windows'
	assert [s.window_cell for s in svc_steps] == [w for w, steps in windows for _ in steps], \
		'the window heading is not §20.5\'s verbatim'
	# The slug is the cell with its parenthetical dropped. Asserted per row, not as a set: a step
	# that moves window leaves the bullet order and the heading both unchanged, so a set comparison
	# (or the `counts` on the route) is the only thing that sees it.
	slug = {'Phase 0 — Pre-launch (2 weeks before)': 'Phase 0', 'Launch week': 'Launch week',
		'Weeks 2–4': 'Weeks 2–4'}
	assert [s.sequence for s in svc_steps] == [
		slug[w] for w, steps in windows for _ in steps], 'a step moved between §20.5 windows'
	assert slug['Weeks 2–4'] == 'Weeks 2–4', 'the slug carries the en-dash, not a hyphen'
	assert any('719' in s.step for s in svc_steps), 'the hotline integration is a pre-launch step'


# --- routes ----------------------------------------------------------------------------------

async def test_the_routes_are_scoped_and_the_plan_is_public() -> None:
	app, h = _auditor_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
		# §21.1 names no person and no number about one, so the plan is readable by anyone.
		plan = (await c.get('/rollout/phases')).json()
		assert len(plan['phases']) == 7 and plan['current']['phase'] == 'phase_1_information'
		# The front door, on the anonymous route: the channels are §5.2's names, and no traceability
		# handle reaches a partner. Asserted on the wire rather than on the model because the defect
		# this replaced was a *served* string — a unit test on `channels` would have passed against
		# the id-carrying version if it only asked whether the list was non-empty.
		code = _re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{1,3}\b')
		assert not code.findall(json.dumps(plan)), f'spec handle on the anonymous plan: {code.findall(json.dumps(plan))}'
		served = [p['channels'] for p in plan['phases']]
		assert all(isinstance(c, str) and not c.startswith('CHAN-') for row in served for c in row), served
		assert served[1] == ['radio', 'sms', 'ussd', 'whatsapp', 'social', 'chw'], served[1]
		assert served[3] == list(CHANNELS), 'phase 3 opens all seven §5.2 channels'
		assert 'channels_cell' not in plan['phases'][1], \
			'the cell is written in handles for phases 1 and 2 and must not travel'
		# The ids and the cell stay on the scoped route, where the id is the finding.
		scoped = (await c.get('/rollout/status', params={'phase': 'phase_1_information'}, headers=h)).json()
		assert scoped['channels_open'] == [
			'CHAN-000', 'CHAN-001', 'CHAN-002', 'CHAN-003', 'CHAN-004', 'CHAN-005']
		assert scoped['channels_cell'] == 'CHAN-0,1,2,3,4,5', 'the evidence half keeps the section\'s cell'
		# The readiness report is evidence and takes the auditor's scope.
		assert (await c.get('/rollout/readiness')).status_code in (401, 403)
		report = (await c.get('/rollout/readiness', headers=h)).json()
		assert report['unregistered_retention_features'] == []
		assert report['apk_within_budget'] is None, 'the build has not been weighed in this deployment'


async def test_the_launch_route_serves_the_sequence_and_no_handle() -> None:
	"""§20.5 on the wire. The sequence was carried in code and reachable by no route, so a partner
	reading the plan could not see it — the same shape as §20.2's levers one subsection over.

	Asserted at the front door because the failure being replaced is a *served* payload: a check on
	the model would pass against a route that dropped half the steps."""
	app, _ = _auditor_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
		# Open, like `/rollout/phases`: no headers, and it names no person.
		launch = (await c.get('/rollout/launch')).json()
		assert len(launch['steps']) == 18, launch.get('counts')
		assert launch['counts'] == {
			'Phase 0': 6, 'Launch week': 7, 'Weeks 2–4': 5}, launch['counts']
		# The window is §20.5's heading, en-dash and parenthetical included, so a reader sees the
		# section's own words rather than a slug the section never prints.
		windows = [s['window_cell'] for s in launch['steps']]
		assert windows[:1] == ['Phase 0 — Pre-launch (2 weeks before)'] and windows[-1] == 'Weeks 2–4', windows
		# No traceability handle reaches an anonymous surface. `findall` alone is clean over an empty
		# list, so the step count above is what makes this non-vacuous.
		code = _re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{1,3}\b')
		body = json.dumps(launch)
		assert not code.findall(body), f'spec handle on the launch route: {code.findall(body)}'


async def test_the_status_route_reports_the_live_tier_against_the_phase() -> None:
	app, h = _auditor_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
		out = (await c.get('/rollout/status', params={'phase': 'phase_3_retention'}, headers=h)).json()
		assert out['phase'] == 'phase_3_retention' and out['max_tier'] == 2
		assert out['active_tier'] == 3, 'Tier 4 is dormant, so the deployment runs at Tier 3'
		assert out['phase_mismatch'] is True, 'tier 3 over a tier-2 ceiling is the finding'
		assert (await c.get('/rollout/status', params={'phase': 'nope'}, headers=h)).status_code == 422


# --- §16.5 the app size plan ------------------------------------------------------------------

def _spec_module_table() -> list[tuple[str, float, str]]:
	"""§16.5's nine rows read out of `docs/spec.md`, so a revision to the section fails here."""
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	# Terminated by the next heading, not by a `---` rule: the table's own separator row contains
	# `---`, so splitting on that cuts the table at its first line and yields nothing.
	section = text.split('### 16.5 App Size Strategy', 1)[1].split('\n## ', 1)[0]
	rows: list[tuple[str, float, str]] = []
	for line in section.splitlines():
		if not line.startswith('|') or set(line) <= set('|-: '):
			continue
		cells = [c.strip() for c in line.strip('|').split('|')]
		if len(cells) < 3 or cells[0] == 'Component':
			continue
		# §16.5 writes "Included" for the two tier rows rather than a figure, which is 0 MB of its
		# own — they are part of the base app's 15 MB, not a separate download.
		raw = cells[1].replace('<', '').replace('~', '').replace(' MB', '').strip()
		size = 0.0 if raw == 'Included' else float(raw)
		rows.append((cells[0], size, cells[2]))
	return rows


def test_the_module_table_is_the_sections_nine_rows() -> None:
	"""§16.5's delivery table, transcribed. Nine rows, and the sizes are the section's own — the
	section writes "<15 MB" and "~8 MB", so the numbers are bounds rather than measurements, which is
	what `size_mb` carries."""
	from afya.rollout.service import MODULES
	spec = _spec_module_table()
	assert len(spec) == 9, f'§16.5 lists nine components, found {len(spec)}'
	assert [m.component for m in MODULES] == [name for name, _, _ in spec]
	assert [m.size_mb for m in MODULES] == [size for _, size, _ in spec]


async def test_the_base_install_is_under_budget_and_the_modules_are_not_folded_in() -> None:
	"""The section's own distinction. §16.5 lists 25 MB and 15 MB modules and still closes "Base
	install under 15 MB", which is only true because Delivery makes them on-demand. A plan that
	summed the table into one number would report 78 MB — the whole table, which no install carries
	— and read as a breach §16.5 does not have. (The section's *own* closing total, ~60 MB, is a
	different number and does not equal 78; that gap is the finding
	`test_the_sections_stated_total_is_carried_and_its_rows_do_not_reach_it` carries.)"""
	plan = _svc().app_size()
	assert plan.base_install_mb == 15.0, 'Base app is the only initial row with a size'
	assert plan.within_budget is True
	assert plan.on_demand_mb == 58.0, 'Tier 3 + LiDAR + acoustic + registry + library'
	assert plan.full_install_mb == 78.0, 'and the 5 MB automatic facility cache'
	assert plan.budget_mb == APK_BUDGET_MB


async def test_the_automatic_row_counts_toward_the_install_and_on_demand_does_not() -> None:
	"""`at_install` is the property the split rests on: the facility cache arrives without anyone
	asking, so its 5 MB is spent on every device; the 25 MB registry is spent only where a person
	chose it."""
	from afya.rollout.service import MODULES
	by_component = {m.component: m for m in MODULES}
	assert by_component['Offline facility cache'].at_install is True
	assert by_component['Offline facility cache'].delivery == 'automatic'
	assert by_component['Medicine registry (offline)'].at_install is False
	assert by_component['LiDAR module'].condition == 'LiDAR devices only'


async def test_the_app_size_route_is_open_and_reports_the_split() -> None:
	app, _ = _auditor_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
		out = (await c.get('/rollout/app-size')).json()
		assert out['base_install_mb'] == 15.0 and out['within_budget'] is True
		assert len(out['components']) == 9
		assert out['on_demand_mb'] > out['base_install_mb'], 'the modules a person may pull outweigh the base'


def _spec_stated_total_mb() -> float:
	"""§16.5's closing line read out of `docs/spec.md`, so the constant cannot drift from the section.

	The section writes "**Total with all modules:** ~60 MB. Base install under 15 MB." on one line,
	and the `~` is why the comparison in `app_size` is `<=` rather than `==`. Read rather than
	restated for the same reason `_spec_module_table` is: a second copy of the number in this file
	would be the two-sources-of-truth drift this test exists to catch.
	"""
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	section = text.split('### 16.5 App Size Strategy', 1)[1].split('\n## ', 1)[0]
	m = _re.search(r'Total with all modules:\*\* ~(\d+(?:\.\d+)?) MB', section)
	assert m, '§16.5 no longer prints a "Total with all modules" figure'
	return float(m.group(1))


def test_the_sections_stated_total_is_carried_and_its_rows_do_not_reach_it() -> None:
	"""§16.5 contradicts itself, and the contradiction is a finding rather than a rounding error.

	The section's nine rows sum to 78 MB — 15 base + 8 Tier 3 + 4 LiDAR + 6 acoustic + 25 registry +
	15 library + 5 facility cache — and its own closing line says "~60 MB". The gap is 18 MB, and it
	was invisible because the code carried neither number: `full_install_mb` existed and nothing
	compared it to anything, so a reader had to add the column up by hand to find it.

	**Reported, not resolved.** The three rows a reader might use to explain the gap (the registry,
	the library and the cache are each marked optional or per-county) do not sum to 18 on any
	reading, so rounding 78 down to 60 in code would invent a reconciliation the section does not
	state. `within_statement` is False and stays False until §16.5's arithmetic or its closing line
	changes — which is the point: a test asserting `within_statement is True` would be asserting the
	section is consistent, and it is not.

	Both directions are asserted. `stated_total_mb` is compared to the figure *read from the
	section*, so a constant that drifts fails here; and the sum is compared to the section's own
	rows, so a transcribed size that changes is caught rather than silently widening the gap.
	"""
	from afya.rollout.service import STATED_TOTAL_MB
	plan = _svc().app_size()
	assert STATED_TOTAL_MB == _spec_stated_total_mb() == 60.0, \
		'the carried total is the section\'s closing figure'
	assert plan.stated_total_mb == STATED_TOTAL_MB
	assert plan.full_install_mb == 78.0, 'the nine rows sum to 78, which is the finding'
	assert sum(m.size_mb for m in plan.components) == 78.0, \
		'every row counts toward the total, including the automatic facility cache'
	assert plan.within_statement is False
	assert '60' in plan.note and '78' in plan.note, 'the note names both figures rather than one'


async def test_the_app_size_route_serves_the_stated_total_and_the_disagreement() -> None:
	"""A finding a reader cannot reach is not a finding. The route carries both numbers, and the
	note says which way the gap runs — a served `within_statement: false` with no figures beside it
	reads as a budget breach, which is the opposite of what it is."""
	app, _ = _auditor_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
		out = (await c.get('/rollout/app-size')).json()
		assert out['stated_total_mb'] == 60.0 and out['within_statement'] is False
		assert out['within_budget'] is True, 'the install is under budget; only the module total is not'
		assert '60' in out['note'] and '78' in out['note']


# --- §21.2–21.7 the phase sections -----------------------------------------------------------

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / 'docs' / 'spec.md'


def _spec_phase_sections() -> dict[str, dict[str, list[str]]]:
	"""§21.2–21.7 read out of `docs/spec.md`, keyed by phase number.

	Read from the document rather than restated, so a spec revision fails here until the code moves
	with it. The deliverables are the `- ` bullets under **Deliverables:** and the criteria are the
	one **Success criteria:** line split on `;` — §21.7 has neither, which is the case the reader
	must not crash on.
	"""
	import re
	text = SPEC.read_text()
	out: dict[str, dict[str, list[str]]] = {}
	for n in '234567':
		m = re.search(rf'\n### 21\.{n} [^\n]*\n(.*?)(?=\n### 21\.|\n## 22\.)', text, re.S)
		assert m, f'§21.{n} not found in the spec'
		body = m.group(1)
		d = re.search(r'\*\*Deliverables:\*\*\n((?:- [^\n]*\n)+)', body)
		deliverables = [line[2:].strip() for line in d.group(1).strip().split('\n')] if d else []
		c = re.search(r'\*\*Success criteria:\*\* ([^\n]*)', body)
		criteria = [x.strip().rstrip('.') for x in c.group(1).split(';')] if c else []
		t = re.search(r'\*\*Testing:\*\* ([^\n]*)', body)
		# The section's paragraph ends with a full stop on its last clause; the criteria line does
		# too, and both are stripped the same way so a trailing period is not a spec revision.
		testing = [x.strip().rstrip('.') for x in t.group(1).split(';')] if t else []
		out[n] = {'deliverables': deliverables, 'criteria': criteria, 'testing': testing}
	return out


def test_the_phase_plans_are_the_sections_deliverables_and_criteria() -> None:
	"""Every §21.2–21.7 deliverable and success criterion, cell for cell.

	§21.1's table was carried and the six sections beneath it were not, so the rollout had seven
	gates and no description of the work behind any of them. This pins the work.
	"""
	spec = _spec_phase_sections()
	# The mapping is the phase enum's ordinal against the section number, and it is stated rather
	# than inferred: §21.1 calls the section after Phase 0 "Phase 1 — Information First", so the
	# section number is the phase number plus one. Taking `phase.value.split('_')[1]` as the
	# section number is the off-by-one this table exists to make impossible.
	SECTIONS: dict[Phase, str] = {
		Phase.phase_1_information: '2',
		Phase.phase_2_utility: '3',
		Phase.phase_3_retention: '4',
		Phase.phase_4_daily_habit: '5',
		Phase.phase_5_outbreak_ready: '6',
		Phase.phase_6_scale: '7',
	}
	plans = {p.phase: p for p in RolloutService.phase_plans()}
	assert set(plans) == set(SECTIONS), plans
	for phase, n in SECTIONS.items():
		plan = plans[phase]
		assert [d.text for d in plan.deliverables] == spec[n]['deliverables'], f'§21.{n} deliverables'
		assert [c.text for c in plan.criteria] == spec[n]['criteria'], f'§21.{n} criteria'
		assert list(plan.testing) == spec[n]['testing'], f'§21.{n} testing'
	# §21.6 is the only section with a Testing paragraph, so a plan carrying testing elsewhere is
	# a plan that gained one from the wrong section.
	assert [p.phase for p in plans.values() if p.testing] == [Phase.phase_5_outbreak_ready]


def test_a_deliverable_above_its_own_phases_ceiling_is_reported() -> None:
	"""The finding §21 has against itself, and the one a check on either column alone cannot see.

	§21.1 gives Phase 1 a ceiling of `Tier 1` and §21.2 schedules "200 CHWs trained as information
	intermediaries" under it; §21.1 gives Phase 2 the same ceiling and §21.3 schedules "2,000 CHWs
	trained". Both rows carry `CHAN-005`, which the registry holds at Tier 2.

	**Reported, not resolved**, because the two columns disagree with no third authority between
	them: §21.1's Channels column opens `CHAN-0,1,2,3,4,5` in Phase 1 *and* caps that row at Tier 1,
	while §7.3's tier map names no CHAN id at all (`unmapped_features()` reports all seven) and no
	CHAN section states a `**Tier:**` line. So the registry's Tier 2 is this repo's assignment with
	no section behind it, and moving either column would be this code overruling the spec on the
	strength of its own value — the same call the §21/§22 criterion drift already makes.
	"""
	svc = _svc()
	over = {p.phase.value: p.over_ceiling_deliverables for p in svc.rollout_plan() if p.over_ceiling_deliverables}
	assert set(over) == {'phase_1_information', 'phase_2_utility'}, f'the crossing is in two phases: {set(over)}'
	assert over['phase_1_information'] == [
		'200 CHWs trained as information intermediaries — Tier 2, above the phase ceiling of Tier 1'], over['phase_1_information']
	assert over['phase_2_utility'] == [
		'2,000 CHWs trained — Tier 2, above the phase ceiling of Tier 1'], over['phase_2_utility']
	# Phase 0 authorises no tier, so nothing can be above its ceiling — a `None` ceiling is not a
	# ceiling of zero, which would report every deliverable of every later phase.
	assert not any(p.over_ceiling_deliverables for p in svc.rollout_plan()
	               if p.phase is Phase.phase_3_retention), 'Tier 2 under a Tier 2 ceiling is inside it'
	# The finding travels on the readiness report, so an auditor reading `/rollout/plan/readiness`
	# sees it rather than having to cross §21.1 against §21.2 by eye.
	assert all(hasattr(p, 'over_ceiling_deliverables') for p in svc.rollout_plan())


def test_a_deliverable_naming_a_capability_that_does_not_exist_is_reported() -> None:
	"""The §11.1 defect in the phase dimension: a plan listing a capability nobody built reads
	exactly like one that lists a capability that shipped."""
	svc = _svc()
	unbuilt = {p.phase.value: p.unregistered_features for p in svc.rollout_plan() if p.unregistered_features}
	assert unbuilt == {}, f'a phase deliverable names a feature the registry does not carry: {unbuilt}'


def test_the_criterion_drift_between_section_21_and_section_22_is_reported() -> None:
	"""§21.3 says 300,000 installs and §22.2 sets `app_downloads` at 2,000,000; §21.4 says 25%
	DAU/MAU and §22.1 sets `retention_dau_mau` at 35%.

	Both sections are the product owner's, so neither is overruled here. The finding is that a
	phase's own exit criterion and the KPI that measures it disagree by an order of magnitude, and
	a rollout judged against one would pass while the other read as a failure.
	"""
	svc = _svc()
	drift = {p.phase.value: p.criterion_drift for p in svc.rollout_plan() if p.criterion_drift}
	assert 'phase_3_retention' in drift, 'the DAU/MAU disagreement between §21.4 and §22.1 is the one that matters'
	assert any('25' in d and '35' in d for d in drift['phase_3_retention']), drift['phase_3_retention']
	assert 'phase_2_utility' in drift, '§21.3 installs against §22.2 app_downloads'
	assert 'phase_1_information' in drift, '§21.2 SMS opt-ins and WhatsApp users against §22.2'


def test_a_criterion_with_no_kpi_behind_it_is_reported_not_invented() -> None:
	"""§21.2's "50 stations broadcasting" and §21.3's "4.0+ rating" are real targets §22 measures
	nothing about. A phase exit that cannot be computed is a phase exit nobody can call."""
	svc = _svc()
	unmeasurable = {p.phase.value: p.unmeasurable_criteria for p in svc.rollout_plan()}
	# Pinned exactly rather than checked non-empty. A criterion that acquires a KPI moves out of
	# this list and into `criterion_drift`, and both are reported — so an assertion that only asks
	# whether the list is non-empty cannot see the move, which a canary confirmed.
	assert unmeasurable['phase_2_utility'] == ['4.0+ rating', '40% D30 retention', '50,000 triages'], unmeasurable['phase_2_utility']
	assert unmeasurable['phase_1_information'] == ['50 stations broadcasting'], unmeasurable['phase_1_information']
	assert unmeasurable['phase_5_outbreak_ready'] == ['Tier 4 activation in under 60 minutes'], unmeasurable['phase_5_outbreak_ready']
	assert unmeasurable['phase_6_scale'] == [], '§21.7 states no success criteria at all'


def test_a_phase_is_not_ready_while_a_deliverable_or_a_criterion_is_missing() -> None:
	"""`ready` is about the plan being executable, not about the drift. A phase whose deliverable
	names nothing built cannot ship; a phase whose criterion disagrees with §22 can ship and the
	document is inconsistent, which is a different reader's problem."""
	svc = _svc()
	by_phase = {p.phase.value: p for p in svc.rollout_plan()}
	assert by_phase['phase_6_scale'].ready is True, '§21.7 is a strategy section: no features, no criteria'
	assert by_phase['phase_5_outbreak_ready'].ready is False, 'Tier 4 activation time has no §22 KPI'
	assert all(p.deliverable_count == len(p.unbuilt_deliverables) + p.feature_deliverables
	           or p.deliverable_count >= p.feature_deliverables for p in by_phase.values())


def test_phase_0_has_no_plan_and_that_is_not_an_error() -> None:
	"""§21.1 gives Phase 0 no section because it delivers nothing to a user. The refusal names it."""
	svc = _svc()
	assert Phase.phase_0_foundation not in {p.phase for p in svc.rollout_plan()}
	with pytest.raises(KeyError, match='delivers nothing to a user'):
		svc.phase_plan(Phase.phase_0_foundation)


def test_an_unregistered_feature_in_a_plan_is_caught_by_the_readiness_check() -> None:
	"""Canary. Point a deliverable at an id the registry does not carry and watch the check fail.

	Without this the check could pass for the wrong reason — a `feature_id` that never reaches
	`is_registered` would report every phase ready, which is the shape of a gate that enumerates
	one of the ways the thing it checks can be written.
	"""
	from afya.rollout import service as rollout_service
	from afya.rollout.views import Deliverable, PhasePlan

	target = rollout_service.PHASE_PLANS[0]
	original = target.deliverables
	patched = PhasePlan(
		phase=target.phase, objective=target.objective,
		deliverables=[*original, Deliverable(text='A capability nobody built', feature_id='TRI-999')],
		criteria=target.criteria, testing=target.testing,
	)
	try:
		rollout_service.PHASE_PLANS = (patched, *rollout_service.PHASE_PLANS[1:])
		rollout_service.PLAN_BY_PHASE = {p.phase: p for p in rollout_service.PHASE_PLANS}
		out = _svc().phase_readiness(target.phase)
		assert out.unregistered_features == ['TRI-999'], out.unregistered_features
		assert out.unbuilt_deliverables == ['A capability nobody built']
		assert out.ready is False
	finally:
		rollout_service.PHASE_PLANS = (target, *rollout_service.PHASE_PLANS[1:])
		rollout_service.PLAN_BY_PHASE = {p.phase: p for p in rollout_service.PHASE_PLANS}
	# And the revert is real, or the canary leaves the module mutated for every later test.
	assert _svc().phase_readiness(target.phase).unregistered_features == []


async def test_the_plan_is_public_and_the_readiness_evidence_is_scoped() -> None:
	"""`/rollout/plan` is the section a county team aligns to and names no person; the readiness
	half is evidence about the build, like every other read in this family."""
	app, headers = _auditor_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		anon = await c.get('/rollout/plan')
		assert anon.status_code == 200, anon.text
		assert len(anon.json()['plans']) == 6
		assert (await c.get('/rollout/plan/readiness')).status_code in (401, 403)
		ev = await c.get('/rollout/plan/readiness', headers=headers)
		assert ev.status_code == 200, ev.text
		body = ev.json()
		assert body['criterion_drift']['phase_3_retention'], 'the §21.4/§22.1 drift travels'


async def test_the_phase_plan_surfaces_carry_no_spec_code() -> None:
	"""The standing constraint: a deliverable's text is read by a programme manager, and a criterion
	is read by a funder. Neither is a place for a traceability handle."""
	import re as _re
	code = _re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		body = (await c.get('/rollout/plan')).text
		assert not code.findall(body), f'spec code on a served plan surface: {code.findall(body)}'
		# And the same for the evidence half, which is a served surface too.
		app2, headers = _auditor_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app2), base_url='http://t') as c2:
		ev = (await c2.get('/rollout/plan/readiness', headers=headers)).text
		assert not code.findall(ev), f'spec code on the readiness surface: {code.findall(ev)}' 


# --- §20.3 channel acquisition, §20.4 partnership map ----------------------------------------

def _spec_table(heading: str, stop: str, columns: int) -> list[list[str]]:
	"""A spec table's rows, read out of `docs/spec.md` so a revision to the section fails here.

	The header is skipped by its first cell, which each of the three tables spells differently:
	§20.2's is `#` (its first column is a number) and §20.3/§20.4 name a label. A skip list of one
	spelling would let the header through as a row and every count below would read one too high.
	"""
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	section = text.split(heading, 1)[1].split(stop, 1)[0]
	rows: list[list[str]] = []
	for line in section.splitlines():
		if not line.startswith('|') or set(line) <= set('|-: '):
			continue
		cells = [c.strip() for c in line.strip('|').split('|')]
		if len(cells) != columns or cells[0] in ('#', 'Channel', 'Partner type'):
			continue
		rows.append(cells)
	return rows


def test_the_acquisition_table_is_the_sections_seven_rows() -> None:
	"""§20.3, cell for cell. The tactics cell is the section's, split on its separators — "Daily
	segments, call-ins, drama vignettes" is three tactics and WhatsApp's "Forwardable cards with
	download links; bot → app handoff" is two, so the split is on both a comma and a semicolon. A row
	carrying one string would be a plan nobody can assign."""
	import re as _re
	spec = _spec_table('### 20.3 Channel-by-Channel Acquisition', '\n---', 3)
	from afya.rollout.service import ACQUISITION
	assert len(spec) == 7, f'§20.3 lists seven channels, found {len(spec)}'
	assert [c.label for c in ACQUISITION] == [r[0] for r in spec]
	assert [c.role for c in ACQUISITION] == [r[1] for r in spec]
	for row, (_, _, tactics) in zip(ACQUISITION, spec):
		assert row.tactics == [t.strip() for t in _re.split(r'[;,]', tactics)], f'{row.label} tactics'


def test_every_section_5_2_channel_has_an_acquisition_role() -> None:
	"""The finding. §20.3 is how a person is reached and §5.2 is the channel list; a channel with no
	row is one the product can reach someone through with no plan to reach them."""
	from afya.registry.service import CHANNELS
	from afya.rollout.service import ACQUISITION
	plan = _svc().acquisition()
	assert plan.unmapped_channels == [], f'no §20.3 acquisition role for: {plan.unmapped_channels}'
	assert {c.channel for c in ACQUISITION} == set(CHANNELS)
	# §20.3 says "App stores" where §5.2's channel is `native`. The two words are both kept: the app
	# store is how the app is found, the app is what is found, and collapsing the label would read
	# as the section naming a channel the registry does not carry.
	stores = next(c for c in ACQUISITION if c.label == 'App stores')
	assert stores.channel == 'native'
	assert all(c.feature_id is not None for c in ACQUISITION), 'every channel names its capability'


def test_the_partnership_map_is_the_sections_ten_rows_and_names_its_organisations() -> None:
	"""§20.4, cell for cell, with the partners cell split on its commas. A map whose partner count
	counted rows rather than names would say ten when the section names thirty-nine."""
	spec = _spec_table('### 20.4 Partnership Map', '\n---', 3)
	from afya.rollout.service import PARTNERS
	assert len(spec) == 10, f'§20.4 lists ten partner types, found {len(spec)}'
	assert [t.partner_type for t in PARTNERS] == [r[0].replace('**', '') for r in spec]
	assert [t.role for t in PARTNERS] == [r[2] for r in spec]
	for row, (_, named, _role) in zip(PARTNERS, spec):
		assert row.partners == [p.strip() for p in named.split(',')], f'{row.partner_type} partners'
	assert sum(len(t.partners) for t in PARTNERS) == 39


def test_a_lever_resting_on_a_partner_outside_the_map_is_reported() -> None:
	"""The sharper finding: §20.2 lever 1 says "Negotiate with Safaricom, Airtel, Telkom" and lever 3
	"Co-brand with Kenya Red Cross, AMREF, WHO", and §20.4 is the section that says who is a partner.
	A lever waiting on an organisation the map does not list is a strategy waiting on a signature
	nobody asked for."""
	plan = _svc().acquisition()
	assert plan.unsourced_levers == [], f'levers resting on an unlisted partner: {plan.unsourced_levers}'
	assert plan.lever_partners['1'] == ['Safaricom', 'Airtel Kenya', 'Telkom Kenya']
	assert plan.lever_partners['3'] == ['Kenya Red Cross', 'AMREF Health Africa', 'WHO']
	# Only the levers whose Action cell names an organisation are joined; the other four name a
	# design property or a category and have nothing in §20.4 to resolve against.
	assert set(plan.lever_partners) == {'1', '3'}


def test_the_canary_watches_the_partner_join_fire() -> None:
	"""Canary. Rename a partner the lever depends on and the join must name the lever. If this
	passes, the check is comparing the map against itself."""
	from afya.rollout import service as rs
	original = rs.PARTNERS
	try:
		rs.PARTNERS = tuple(
			t.model_copy(update={'partners': [p for p in t.partners if p != 'Safaricom']})
			if t.partner_type == 'Telcos' else t for t in original)
		unsourced = rs.RolloutService(FeatureRegistry()).acquisition().unsourced_levers
		assert len(unsourced) == 1 and 'Safaricom' in unsourced[0], f'rename went unnoticed: {unsourced}'
	finally:
		rs.PARTNERS = original
	assert rs.RolloutService(FeatureRegistry()).acquisition().unsourced_levers == [], 'canary left PARTNERS mutated'


def test_the_canary_watches_the_channel_coverage_check_fire() -> None:
	"""Canary. Drop §20.3's USSD row and the coverage check must name the channel — the same shape as
	a §7.3 feature outside the tier map."""
	from afya.rollout import service as rs
	original = rs.ACQUISITION
	try:
		rs.ACQUISITION = tuple(c for c in original if c.channel != 'ussd')
		unmapped = rs.RolloutService(FeatureRegistry()).acquisition().unmapped_channels
		assert unmapped == ['ussd'], f'the dropped row went unnoticed: {unmapped}'
	finally:
		rs.ACQUISITION = original
	assert rs.RolloutService(FeatureRegistry()).acquisition().unmapped_channels == [], 'canary left ACQUISITION mutated'


async def test_the_acquisition_plan_is_public_and_the_coverage_evidence_is_scoped() -> None:
	"""`/rollout/acquisition` is the document a telco or a county team reads to see what is being
	asked of them, and it carries no registry handle; the coverage half keeps them, because there
	the id is the finding — the same split `/rollout/plan` and `/sensors/capabilities` already make."""
	import re as _re
	code = _re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		public = await c.get('/rollout/acquisition')
		assert public.status_code == 200, public.text
		assert not code.findall(public.text), f'spec code served to a partner: {code.findall(public.text)}'
		body = public.json()
		assert body['partner_count'] == 39 and len(body['channels']) == 7
		assert body['channels'][0]['label'] == 'Radio'
		assert (await c.get('/rollout/acquisition/coverage')).status_code in (401, 403)
	app2, headers = _auditor_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app2), base_url='http://t') as c2:
		ev = await c2.get('/rollout/acquisition/coverage', headers=headers)
		assert ev.status_code == 200, ev.text
		assert ev.json()['channels'][0]['feature_id'] == 'CHAN-000', 'the handles stay on the evidence half'
