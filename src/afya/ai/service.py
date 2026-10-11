"""AI & analytics services (spec §19, §11.7, §19.3).

The governance rules of §19.3 are enforced as preconditions rather than documented:
  * aggregation suppresses any cell below MIN_CELL_SIZE, so a cell cannot be re-identified;
  * personal risk scoring runs on-device and returns its reasons, never a bare number;
  * an early-warning signal routes to a human epidemiologist and never fires a public alert;
  * every model has a named owner and published limitations, or it cannot be registered.
"""
import statistics

from afya.ai.views import (
	MIN_CELL_SIZE, AggregateCell, FairnessAudit, Hotspot, HotspotMap, ModelCard, ModelFootprint,
	RaisedSignal, RedressOutcome, RedressRequest, RiskInputs, RiskScore, WarningAssessment,
	WarningSignal,
)
from afya.logmixin import LogMixin

# §19.1's seven-row table, verbatim and in the section's order. `size_mb` is the section's own bound
# — it writes "<1 MB", "<2 MB", "<20 MB" — and `framework` its fourth column.
#
# Two of the seven were absent until now: the speech model and the cough *classifier*. Both are
# load-bearing rather than decorative. §ACC-002 lists "offline speech recognition for core commands"
# among its features and `LANGUAGE_MATRIX` records which languages ship recognition, so the model
# that recognition runs on is the thing that makes a transcript on-device; §14.2 lists "cough type
# distribution" among its outputs, which is a classifier and not the detector. Their absence was not
# visible as a missing route — it was visible as a footprint of 8 MB against §19.1's stated 30.
ON_DEVICE_MODELS: tuple[ModelCard, ...] = (
	ModelCard(model_id='triage-classifier', purpose='Symptom -> risk classification', owner='Mlinzi clinical lead',
		inputs=['symptoms', 'temperature_c', 'exposure_flags'], outputs=['risk_level'], on_device=True, size_mb=1.0,
		framework='TFLite',
		limitations=['Not a diagnosis; the malaria trap is a base-rate prior, not a test', 'Requires the rule engine as the authoritative path'],
		review_board_required=True),
	ModelCard(model_id='cough-detection', purpose='Audio -> cough event', owner='Mlinzi ML lead',
		inputs=['derived_acoustic_features'], outputs=['cough_count'], on_device=True, size_mb=2.0,
		framework='TFLite',
		limitations=['Audio never leaves the handset', 'Background noise degrades recall'], review_board_required=False),
	ModelCard(model_id='cough-classification', purpose='Cough -> type', owner='Mlinzi ML lead',
		inputs=['cough_segment'], outputs=['cough_type'], on_device=True, size_mb=1.0,
		framework='TFLite',
		limitations=[
			'§14.2 is explicit that it cannot distinguish a dangerous cough from any other one, so the type is a trend, not a verdict',
			'Runs on the segment the detector isolated; a missed cough is never classified',
		], review_board_required=False),
	ModelCard(model_id='fall-detection', purpose='IMU -> fall event', owner='Mlinzi ML lead',
		inputs=['accelerometer', 'gyroscope'], outputs=['fall_verdict'], on_device=True, size_mb=1.0,
		framework='TFLite',
		limitations=['Reduced accuracy without a gyroscope'], review_board_required=False),
	ModelCard(model_id='respiration-estimation', purpose='LiDAR -> respiratory rate', owner='Mlinzi ML lead',
		inputs=['derived_motion_series'], outputs=['breaths_per_minute'], on_device=True, size_mb=3.0,
		framework='TFLite',
		limitations=['Depth frames are discarded on-device', 'Accuracy falls with large subject motion'], review_board_required=True),
	ModelCard(model_id='speech-recognition', purpose='Voice -> text (local languages)', owner='Mlinzi ML lead',
		inputs=['utterance'], outputs=['transcript'], on_device=True, size_mb=20.0,
		framework='TFLite / Whisper-tiny',
		limitations=[
			'Recognition ships per language; `LANGUAGE_MATRIX` records which, and a language without it is answered online',
			'§ACC-002 names six report languages and only two ship recognition today',
			'Recognition is on-device; the transcript is what leaves the handset, never the audio',
		], review_board_required=True),
	ModelCard(model_id='image-quality', purpose='Photo -> quality score', owner='Mlinzi ML lead',
		inputs=['photo'], outputs=['quality_score'], on_device=True, size_mb=1.0,
		framework='TFLite',
		limitations=['No dermatology verdict is produced — deliberately (§14.4)'], review_board_required=False),
)

SERVER_MODELS: tuple[ModelCard, ...] = (
	ModelCard(model_id='outbreak-early-warning', purpose='Detect anomalous aggregated patterns', owner='PHEOC epidemiology',
		inputs=['aggregated_symptom_reports', 'search_signals', 'encounter_density'], outputs=['signal', 'confidence'],
		on_device=False, size_mb=0.0, limitations=['Never fires a public alert; routes to a human reviewer'],
		review_board_required=True),
	ModelCard(model_id='hotspot-prediction', purpose='Predict next-case locations', owner='PHEOC epidemiology',
		inputs=['aggregated_cases', 'mobility'], outputs=['probability_map'], on_device=False, size_mb=0.0,
		limitations=['Minimum cell size 10', 'Suppressed cells are reported as a count, never mapped'],
		review_board_required=True),
	ModelCard(model_id='misinformation-detection', purpose='Cluster emerging rumours', owner='MoH risk communication',
		inputs=['text_and_voice_submissions'], outputs=['topic_cluster', 'velocity'], on_device=False, size_mb=0.0,
		limitations=['Corrections require human drafting and source attribution'], review_board_required=False),
	ModelCard(model_id='content-recommendation', purpose='Personalise health education', owner='MoH health promotion',
		inputs=['engagement_history'], outputs=['content_items'], on_device=False, size_mb=0.0,
		limitations=[
			'Ranks the existing library; it does not write content, so it cannot outrun §6.5 governance',
			'§6.1 order is a demand prior and outranks personalisation for a life-safety item',
			'Personalisation reads engagement history, which is health-adjacent — §SEC-004 keeps it from naming a person',
		], review_board_required=False),
	ModelCard(model_id='stockout-prediction', purpose='Predict medicine stockouts', owner='County supply chain',
		inputs=['crowdsourced_reports', 'facility_data'], outputs=['probability_by_facility'], on_device=False, size_mb=0.0,
		limitations=['Crowdsourced reports are proximity-gated and reliability-weighted'], review_board_required=False),
)

# §19.1's closing line, verbatim as a number. The section writes "~30 MB"; the cards carry the
# per-row bounds it states ("<1 MB", "<2 MB", "<20 MB"), so the sum is an upper bound rather than a
# measurement — which is why `footprint()` compares against it instead of claiming to weigh a build.
STATED_FOOTPRINT_MB = 30.0

# §19.3 fairness axes — a model is not deployable until each has been audited.
FAIRNESS_AXES: tuple[str, ...] = ('gender', 'age_band', 'region', 'skin_tone')

WARNING_Z = 2.5


class AIService(LogMixin):
	def __init__(self) -> None:
		self._audits: dict[str, FairnessAudit] = {}
		self._redress: dict[str, RedressOutcome] = {}
		assert self._audits == {} and self._redress == {}

	# --- AI-001 hotspots ------------------------------------------------------------------

	def hotspots(self, cells: list[AggregateCell]) -> HotspotMap:
		assert cells, 'no cells supplied'
		eligible = [c for c in cells if c.population >= MIN_CELL_SIZE]
		suppressed = len(cells) - len(eligible)
		if not eligible:
			return HotspotMap(hotspots=[], suppressed_cells=suppressed, consumers=['county health teams', 'PHEOC'],
				explanation='Every cell is below the minimum cell size of 10; nothing may be published.')
		rates = [c.fever_reports / c.population for c in eligible]
		mean = statistics.fmean(rates)
		stdev = statistics.pstdev(rates) or 1.0
		out: list[Hotspot] = []
		for cell, rate in zip(eligible, rates):
			z = (rate - mean) / stdev
			prob = round(min(0.99, max(0.01, 0.5 + z * 0.15)), 2)
			if z < 0.5:
				continue
			reason = (
				f'{cell.fever_reports} fever reports in a population of {cell.population} '
				f'({rate * 1000:.1f} per 1,000) against a mean of {mean * 1000:.1f} per 1,000; '
				f'{cell.encounter_density:.1f} encounters per person.'
			)
			out.append(Hotspot(cell_id=cell.cell_id, county=cell.county, probability=prob, reason=reason,
				recommended_action='Send a rapid response team to verify and test; increase local surveillance.'))
		self._log_info('hotspot map built', hotspots=len(out), suppressed=suppressed)
		return HotspotMap(
			hotspots=sorted(out, key=lambda h: -h.probability), suppressed_cells=suppressed,
			consumers=['county health teams', 'PHEOC'],
			explanation=f'{len(out)} cell(s) above baseline; {suppressed} suppressed for size. Aggregated data only — no individual record informed this map.',
		)

	# --- AI-002 personal risk -------------------------------------------------------------

	@staticmethod
	def personal_risk(inp: RiskInputs) -> RiskScore:
		"""On-device scoring (§AI-002). Returns the reasons, because an unexplained score is not actionable."""
		score = 0.0
		reasons: list[str] = []
		if inp.exposure_contact:
			score += 0.45
			reasons.append('You reported contact with a known or suspected case.')
		if inp.travel_affected_area:
			score += 0.25
			reasons.append('You travelled to an affected area within the last 21 days.')
		febrile = {'fever', 'headache', 'muscle_pain', 'sore_throat', 'vomiting', 'diarrhoea'} & set(inp.symptoms)
		if febrile:
			score += min(0.3, 0.1 * len(febrile))
			reasons.append(f'You reported {", ".join(sorted(febrile))}.')
		if inp.geofence_entry:
			score += 0.1
			reasons.append('You entered an area with a reported case.')
		if inp.proximity_encounters:
			score += min(0.15, 0.05 * inp.proximity_encounters)
			reasons.append(f'{inp.proximity_encounters} proximity encounter(s) logged.')
		if inp.vaccinated:
			score *= 0.7
			reasons.append('Vaccination recorded, which lowers your risk.')
		score = round(min(1.0, score), 2)
		band = 'high' if score >= 0.6 else ('moderate' if score >= 0.25 else 'low')
		guidance = {
			'high': 'Call 719 now and follow the isolation guidance. Do not travel by public transport.',
			'moderate': 'Monitor your temperature twice a day for 21 days; call 719 if you develop fever.',
			'low': 'No specific action. Keep up hand hygiene and test any fever for malaria first.',
		}[band]
		if not reasons:
			reasons.append('No risk factors were reported.')
		return RiskScore(band=band, score=score, reasons=reasons, guidance=guidance, computed_on_device=True)

	# --- AI-003 early warning -------------------------------------------------------------

	def assess_warning(self, county: str, disease: str, signals: list[WarningSignal]) -> WarningAssessment:
		assert all(s.county == county for s in signals), 'single-county assessment'
		# The z-score is computed from the observed counts, never taken from the caller: an
		# alert gate that trusts a supplied z can be tripped or silenced by whoever posts to it.
		scored = [(s, self.z_score(s.observed, s.baseline, s.baseline_stdev)) for s in signals]
		raised = [RaisedSignal(**s.model_dump(), z_score=z) for s, z in scored if z >= WARNING_Z]
		review = bool(raised)
		if review:
			self._log_warn('early warning signal above threshold', county=county, disease=disease, n=len(raised))
		return WarningAssessment(
			county=county, raised=raised, review_required=review,
			routed_to='PHEOC epidemiologist on duty' if review else 'routine weekly review',
			public_alert=False,
			message=(
				f'{len(raised)} signal(s) above {WARNING_Z} SD for {disease} in {county}. Routed for human review — no public alert is issued automatically.'
				if review else f'All signals within normal range for {disease} in {county}.'
			),
		)

	@staticmethod
	def z_score(observed: float, baseline: float, stdev: float) -> float:
		assert stdev > 0, 'baseline stdev must be positive'
		return round((observed - baseline) / stdev, 2)

	# --- AI-004 governance ----------------------------------------------------------------

	def model_cards(self) -> list[ModelCard]:
		return [*ON_DEVICE_MODELS, *SERVER_MODELS]

	def register_model(self, card: ModelCard) -> ModelCard:
		assert card.owner, 'every model needs a named owner (§19.3 accountability)'
		assert card.limitations, 'limitations must be disclosed (§19.3 transparency)'
		assert card.purpose, 'model card needs a stated purpose'
		# §19.1 states a framework for every one of its seven rows, so a *device* model without one is
		# a row nobody transcribed from the section. §19.2 has no framework column at all, so the
		# refusal is scoped to on-device cards rather than to the field.
		assert not card.on_device or card.framework, f'{card.model_id} ships on device and names no §19.1 framework'
		return card

	def footprint(self) -> ModelFootprint:
		"""§19.1's "~30 MB" against the on-device cards this module carries.

		The comparison is the finding rather than a formality: with the speech model and the cough
		classifier absent the cards summed to 8 MB, and a client that reported 8 MB against a stated
		30 would have been describing a device carrying neither of the two models §ACC-002's offline
		recognition and §14.2's cough-type output depend on. Both halves are reported — the sum and the
		frameworks §19.1 names for every row — because either can drift on its own.
		"""
		device = [m for m in self.model_cards() if m.on_device]
		summed = round(sum(m.size_mb for m in device), 2)
		missing = [m.model_id for m in device if not m.framework]
		within = summed <= STATED_FOOTPRINT_MB
		notes: list[str] = []
		if not within:
			notes.append(f'{summed:g} MB exceeds §19.1\'s stated {STATED_FOOTPRINT_MB:g} MB')
		if missing:
			notes.append(f'§19.1 names a framework for every row; missing on: {", ".join(missing)}')
		self._log_info('on-device footprint', models=len(device), summed_mb=summed, within=within)
		return ModelFootprint(
			models=len(device), stated_total_mb=STATED_FOOTPRINT_MB, summed_mb=summed,
			within_statement=within, missing_frameworks=missing,
			note='; '.join(notes) if notes else
				f'{len(device)} device models, {summed:g} MB of §19.1\'s stated {STATED_FOOTPRINT_MB:g} MB, every framework named',
		)

	def audit_fairness(self, model_id: str, tested_axes: list[str], failures: list[str]) -> FairnessAudit:
		assert model_id in {m.model_id for m in self.model_cards()}, 'unknown model'
		unmet = sorted(set(FAIRNESS_AXES) - set(tested_axes))
		passed = not failures and not unmet
		audit = FairnessAudit(
			model_id=model_id, axes=list(FAIRNESS_AXES), unmet_axes=unmet, passed=passed,
			action='Deployable.' if passed else 'NOT deployable: complete the outstanding axes and remediate failures before release.',
		)
		self._audits[model_id] = audit
		self._log_info('fairness audit recorded', model=model_id, passed=passed)
		return audit

	# --- AI-005 redress -------------------------------------------------------------------

	def file_redress(self, req: RedressRequest) -> RedressOutcome:
		outcome = RedressOutcome(
			request_id=req.request_id, status='under_review', reviewer='Mlinzi clinical review panel',
			human_reviewed=True,
			explanation=(
				f'You challenged a {req.output_kind.replace("_", " ")} outcome. A named human reviewer will read '
				'the reasons that produced it and respond. The original output is not treated as final.'
			),
			remedy='If the challenge is upheld, the outcome is corrected, the correction is sent to you, and the model is re-audited.',
		)
		self._redress[req.request_id] = outcome
		self._log_info('redress filed', kind=req.output_kind, subject=req.subject_ref)
		return outcome

	def redress_outcome(self, request_id: str) -> RedressOutcome:
		assert request_id in self._redress, 'unknown redress request'
		return self._redress[request_id]
