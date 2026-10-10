"""Behavioural tests for the AI & analytics module (spec §19, §19.3).

These cover the guarantees the module exists to carry: minimum-cell suppression, the
human-in-the-loop early warning, on-device explainable risk scoring, model-card
accountability, all-axis fairness audits, and human-reviewed redress.
"""
import pytest
from pydantic import ValidationError

from afya.ai.service import (
	FAIRNESS_AXES, MIN_CELL_SIZE, ON_DEVICE_MODELS, SERVER_MODELS, WARNING_Z, AIService,
)
from afya.ai.views import (
	AggregateCell, FairnessAudit, HotspotMap, ModelCard, RedressOutcome, RedressRequest, RiskInputs,
	RiskScore, WarningAssessment, WarningSignal,
)


def _cell(cell_id: str, county: str, population: int, fever_reports: int = 0) -> AggregateCell:
	return AggregateCell(cell_id=cell_id, county=county, population=population, fever_reports=fever_reports,
		cough_events=0, encounter_density=0.2, facility_reports=0)


def _signal(z: float, county: str = 'Nairobi', disease: str = 'cholera') -> WarningSignal:
	"""A signal whose observed count sits `z` standard deviations above its baseline. The z-score is
	derived by the service, never supplied, so the helper expresses the same thing in raw counts."""
	stdev = 4.0
	return WarningSignal(county=county, disease=disease, signal='fever_triage',
		observed=100.0 + stdev * z, baseline=100.0, baseline_stdev=stdev)


# --- AI-001 hotspots: minimum cell size ---------------------------------------------------

async def test_min_cell_size_constant_is_ten() -> None:
	assert MIN_CELL_SIZE == 10


async def test_hotspots_suppresses_cells_below_min_size() -> None:
	svc = AIService()
	cells = [
		_cell('c1', 'Nairobi', 1000, 5),
		_cell('c2', 'Nairobi', 500, 2),
		_cell('c3', 'Kisumu', 800, 1),
		_cell('s1', 'Nairobi', 9, 9),
		_cell('s2', 'Kisumu', 4, 4),
	]
	out = svc.hotspots(cells)
	assert isinstance(out, HotspotMap)
	assert out.suppressed_cells == 2, 'the two cells under population 10 must be suppressed'
	named = {h.cell_id for h in out.hotspots}
	assert 's1' not in named and 's2' not in named, 'a suppressed cell must never be named in a hotspot'
	assert named == {'c1'}, 'only the above-baseline eligible cell should surface'
	hotspot = out.hotspots[0]
	assert hotspot.county == 'Nairobi'
	assert hotspot.probability == 0.65
	assert 'per 1,000' in hotspot.reason and hotspot.recommended_action


async def test_hotspots_all_below_min_size_publishes_nothing() -> None:
	svc = AIService()
	out = svc.hotspots([_cell('s1', 'Nairobi', 9, 9), _cell('s2', 'Kisumu', 4, 4)])
	assert out.hotspots == []
	assert out.suppressed_cells == 2
	assert 'nothing may be published' in out.explanation


async def test_hotspots_refuses_empty_input() -> None:
	svc = AIService()
	with pytest.raises(AssertionError):
		svc.hotspots([])


# --- AI-002 personal risk scoring ---------------------------------------------------------

async def test_personal_risk_returns_reasons_guidance_on_device() -> None:
	svc = AIService()
	out = svc.personal_risk(RiskInputs(exposure_contact=True, symptoms=['fever', 'headache']))
	assert isinstance(out, RiskScore)
	assert out.score == 0.65, '0.45 contact + 0.2 for two febrile symptoms'
	assert out.band == 'high'
	assert out.computed_on_device is True
	assert out.reasons == [
		'You reported contact with a known or suspected case.',
		'You reported fever, headache.',
	]
	assert out.guidance == 'Call 719 now and follow the isolation guidance. Do not travel by public transport.'


async def test_personal_risk_vaccination_lowers_score() -> None:
	svc = AIService()
	base = RiskInputs(exposure_contact=True, symptoms=['fever', 'headache'])
	vaccinated = RiskInputs(exposure_contact=True, symptoms=['fever', 'headache'], vaccinated=True)
	plain = svc.personal_risk(base)
	lowered = svc.personal_risk(vaccinated)
	assert lowered.score < plain.score
	assert lowered.score == 0.45
	assert lowered.band == 'moderate'
	assert 'Vaccination recorded, which lowers your risk.' in lowered.reasons


async def test_personal_risk_no_factors_is_low_and_explained() -> None:
	svc = AIService()
	out = svc.personal_risk(RiskInputs())
	assert out.score == 0.0
	assert out.band == 'low'
	assert out.reasons == ['No risk factors were reported.']
	assert out.guidance == 'No specific action. Keep up hand hygiene and test any fever for malaria first.'


# --- AI-003 early warning: never a public alert -------------------------------------------

async def test_z_score_threshold_is_two_point_five() -> None:
	assert WARNING_Z == 2.5


async def test_signal_above_threshold_raises_and_routes_to_human() -> None:
	svc = AIService()
	out = svc.assess_warning('Nairobi', 'cholera', [_signal(2.6)])
	assert isinstance(out, WarningAssessment)
	assert len(out.raised) == 1 and out.raised[0].z_score == 2.6, 'the service derives the z-score' 
	assert out.review_required is True
	assert out.routed_to == 'PHEOC epidemiologist on duty'
	assert 'human review' in out.message


async def test_signal_below_threshold_does_not_raise() -> None:
	svc = AIService()
	out = svc.assess_warning('Nairobi', 'cholera', [_signal(2.4)])
	assert out.raised == []
	assert out.review_required is False
	assert out.routed_to == 'routine weekly review'
	assert 'normal range' in out.message


async def test_threshold_boundary_is_inclusive() -> None:
	svc = AIService()
	out = svc.assess_warning('Nairobi', 'cholera', [_signal(WARNING_Z)])
	assert len(out.raised) == 1, 'z == WARNING_Z counts as raised'


async def test_early_warning_never_sets_public_alert() -> None:
	svc = AIService()
	for z in (-1.0, 0.0, 2.4, WARNING_Z, 3.1, 9.0):
		out = svc.assess_warning('Nairobi', 'cholera', [_signal(z)])
		assert out.public_alert is False, 'an assessment must never fire a public alert automatically'


async def test_early_warning_refuses_cross_county_signals() -> None:
	svc = AIService()
	with pytest.raises(AssertionError):
		svc.assess_warning('Nairobi', 'cholera', [_signal(3.0, county='Kisumu')])


async def test_z_score_refuses_zero_stdev() -> None:
	with pytest.raises(AssertionError):
		AIService.z_score(observed=10.0, baseline=5.0, stdev=0.0)


async def test_z_score_computes_standard_deviations() -> None:
	assert AIService.z_score(observed=12.0, baseline=10.0, stdev=2.0) == 1.0


# --- AI-004 governance: model cards -------------------------------------------------------

async def test_every_registered_model_card_names_owner_and_limitation() -> None:
	svc = AIService()
	cards = svc.model_cards()
	assert len(cards) == len(ON_DEVICE_MODELS) + len(SERVER_MODELS)
	for card in cards:
		assert card.owner, f'{card.model_id} must name an owner'
		assert card.limitations, f'{card.model_id} must disclose at least one limitation'
		assert card.purpose, f'{card.model_id} must state a purpose'
		assert svc.register_model(card) is card


async def test_register_model_refuses_missing_owner() -> None:
	svc = AIService()
	card = ModelCard(model_id='x', purpose='p', owner='', inputs=['a'], outputs=['b'], on_device=True,
		size_mb=1.0, limitations=['l'], review_board_required=False)
	with pytest.raises(AssertionError):
		svc.register_model(card)


async def test_register_model_refuses_missing_limitations() -> None:
	svc = AIService()
	card = ModelCard(model_id='x', purpose='p', owner='Someone', inputs=['a'], outputs=['b'], on_device=True,
		size_mb=1.0, limitations=[], review_board_required=False)
	with pytest.raises(AssertionError):
		svc.register_model(card)


# --- AI-004 governance: fairness audit ----------------------------------------------------

async def test_fairness_axes_are_the_four_required() -> None:
	assert FAIRNESS_AXES == ('gender', 'age_band', 'region', 'skin_tone')


async def test_fairness_audit_all_four_axes_passes() -> None:
	svc = AIService()
	audit = svc.audit_fairness('hotspot-prediction', list(FAIRNESS_AXES), [])
	assert isinstance(audit, FairnessAudit)
	assert audit.axes == list(FAIRNESS_AXES)
	assert audit.unmet_axes == []
	assert audit.passed is True
	assert audit.action == 'Deployable.'


async def test_fairness_audit_missing_axis_is_not_deployable() -> None:
	svc = AIService()
	audit = svc.audit_fairness('hotspot-prediction', ['gender', 'age_band', 'region'], [])
	assert audit.unmet_axes == ['skin_tone']
	assert audit.passed is False
	assert audit.action.startswith('NOT deployable')


async def test_fairness_audit_failure_blocks_deployment() -> None:
	svc = AIService()
	audit = svc.audit_fairness('hotspot-prediction', list(FAIRNESS_AXES), ['region'])
	assert audit.unmet_axes == []
	assert audit.passed is False
	assert audit.action.startswith('NOT deployable')


async def test_fairness_audit_refuses_unknown_model() -> None:
	svc = AIService()
	with pytest.raises(AssertionError):
		svc.audit_fairness('does-not-exist', list(FAIRNESS_AXES), [])


# --- AI-005 explainability and redress ----------------------------------------------------

async def test_redress_request_is_always_human_reviewed() -> None:
	svc = AIService()
	req = RedressRequest(request_id='RDR-ABCD1234', subject_ref='sub-1', output_kind='risk_score',
		output_ref='rs-1', challenge='My score ignored my vaccination record.')
	out = svc.file_redress(req)
	assert isinstance(out, RedressOutcome)
	assert out.human_reviewed is True
	assert out.status == 'under_review'
	assert out.reviewer == 'Mlinzi clinical review panel'
	assert 'risk score' in out.explanation
	assert out.remedy
	assert svc.redress_outcome('RDR-ABCD1234') is out


async def test_redress_outcome_refuses_unknown_request() -> None:
	svc = AIService()
	with pytest.raises(AssertionError):
		svc.redress_outcome('RDR-NOPE0000')


async def test_redress_request_rejects_bad_id() -> None:
	with pytest.raises(ValidationError):
		RedressRequest(request_id='nope', subject_ref='s', output_kind='triage', output_ref='o',
			challenge='this is a long enough challenge')


async def test_caller_cannot_supply_its_own_z_score() -> None:
	"""Regression: the alert gate must derive the z-score from the counts. A caller that can set its
	own z can raise or silence an outbreak alert at will."""
	import pytest
	from pydantic import ValidationError

	with pytest.raises(ValidationError):
		WarningSignal(county='Nairobi', disease='cholera', signal='fever_triage',
			observed=100.0, baseline=100.0, baseline_stdev=4.0, z_score=99.0)  # type: ignore[call-arg]

	# And the same counts produce the same verdict whatever the caller claims about severity:
	# a flat signal stays unraised.
	svc = AIService()
	out = svc.assess_warning('Nairobi', 'cholera', [_signal(0.0)])
	assert out.review_required is False
	assert out.raised == []
