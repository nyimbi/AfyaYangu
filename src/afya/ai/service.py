"""AI & analytics services (spec §19, §11.7, §19.3).

The governance rules of §19.3 are enforced as preconditions rather than documented:
  * aggregation suppresses any cell below MIN_CELL_SIZE, so a cell cannot be re-identified;
  * personal risk scoring runs on-device and returns its reasons, never a bare number;
  * an early-warning signal routes to a human epidemiologist and never fires a public alert;
  * every model has a named owner and published limitations, or it cannot be registered.
"""
import statistics
from datetime import date, timedelta

from afya.ai.views import (
	MIN_CELL_SIZE, SIGNAL_SOURCES, AggregateCell, EarlyWarningScan, FairnessAudit, Hotspot,
	HotspotMap, ModelCard, ModelFootprint, RaisedSignal, RedressOutcome, RedressRequest, RiskInputs,
	RiskScore, SignalCollection, SignalEvent, SignalObservation, WarningAssessment, WarningSignal,
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


def _iso_week(at_iso: str) -> tuple[int, int]:
	"""The ISO year and week a timestamp falls in — the period a baseline is a distribution over.

	ISO weeks are used rather than a rolling seven-day window because the ledger is compared against
	the county's own history and a boundary that moves with the query makes two runs of the same
	question disagree. Week 1 can belong to the previous ISO year, which is why the year comes back
	with the week rather than being taken from the date.
	"""
	iso_year, iso_week, _ = date(*(int(p) for p in at_iso[:10].split('-'))).isocalendar()
	return iso_year, iso_week


def _prior_periods(week_isoyear: int, week: int, count: int) -> list[tuple[int, int]]:
	"""The `count` ISO periods before this one, oldest first, crossing the year boundary correctly.

	Arithmetic on the week number alone is wrong at the year end — week 52 minus 3 is week 49 in the
	same year, but week 2 minus 3 is week 51 of the *previous* ISO year, which has either 52 or 53
	weeks. Anchoring on the Monday of the period and stepping back seven days at a time lets the
	calendar answer instead of a modulus.
	"""
	monday = date.fromisocalendar(week_isoyear, week, 1)
	periods: list[tuple[int, int]] = []
	for step in range(count, 0, -1):
		y, w, _ = (monday - timedelta(weeks=step)).isocalendar()
		periods.append((y, w))
	assert len(periods) == count and len(set(periods)) == count, 'the window is distinct periods'
	return periods


class AIService(LogMixin):
	def __init__(self) -> None:
		self._audits: dict[str, FairnessAudit] = {}
		self._redress: dict[str, RedressOutcome] = {}
		# §AI-003's signal ledger: one row per occurrence, because a count loses the period and a
		# baseline is a distribution over periods.
		self._signal_events: list[SignalEvent] = []
		assert self._audits == {} and self._redress == {} and self._signal_events == []

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

	# --- AI-003's six signals, collected from the app's own events ---------------------------------

	async def record_signal_event(self, event: SignalEvent) -> SignalEvent:
		"""Ingest one occurrence of one of §11.7's six signals.

		This is the half of AI-003 that did not exist. `assess_warning` scores a `WarningSignal` and
		refuses to take a z-score from the caller, but nothing produced the signals: the section lists
		six observable patterns and the app recorded the events behind all six without ever counting
		them together. A detection layer with no collector is a scorer nothing feeds, and it is
		invisible in review because the scorer's own tests pass.

		The event is kept, not tallied. A count incremented at each route loses the period it happened
		in, and a baseline is a distribution over periods, so the window has to be explicit at read
		time. The ledger is bounded like every other store here.
		"""
		assert event.signal in SIGNAL_SOURCES, f'{event.signal} is not one of §11.7\'s six bullets'
		assert len(event.at_iso) >= 10, 'an event with no date cannot be placed in a period'
		self._signal_events.append(event)
		self._signal_events = self._signal_events[-500_000:]
		assert len(self._signal_events) <= 500_000, 'signal ledger bounded'
		return event

	def collect_signals(self, county: str, week_isoyear: int, week: int) -> SignalCollection:
		"""Count §11.7's six signals for one locality and one period, from the events ingested.

		**The min-cell rule applies here too.** §19.3 sets it for published aggregates, and a signal
		counted from four people is a signal that identifies them to whoever reads it. A source under
		`MIN_CELL_SIZE` in the period is withheld by name, and withheld is *reported*: a signal absent
		because it is small and a signal absent because nothing happened are different facts, and an
		epidemiologist has to be able to tell them apart. A collector that dropped both would report a
		quiet week and a suppressed one identically.

		The min-cell rule is applied to the *period's count* and not to the baseline. The baseline is
		what the count is compared against, and it is a mean over periods — withholding it would leave
		the count with nothing to be measured against, which is the failure the rule exists to avoid.
		"""
		assert week_isoyear >= 2024, 'a period before this deployment has no baseline'
		counts = self._count_events(county, week_isoyear, week)
		observations: list[SignalObservation] = []
		withheld: list[str] = []
		for signal in SIGNAL_SOURCES:
			count = counts[signal]
			if count < MIN_CELL_SIZE:
				withheld.append(f'{signal} ({count} event(s), below the minimum cell size of {MIN_CELL_SIZE})')
				continue
			observations.append(SignalObservation(county=county, week_isoyear=week_isoyear, week=week,
			                                      signal=signal, count=count))
		self._log_info('signals collected', county=county, week=week, collected=len(observations),
		               withheld=len(withheld))
		return SignalCollection(
			county=county, observations=observations, withheld=withheld,
			note=(f'{len(observations)} of {len(SIGNAL_SOURCES)} signals collected for {county} week '
			      f'{week}. A withheld signal is one the source produced too few events for, not one '
			      f'that did not occur — the name and the count are given so the two can be told apart.'),
		)

	def _count_events(self, county: str, week_isoyear: int, week: int) -> dict[str, int]:
		"""The six counts for one period, each from the ledger.

		Separate from `collect_signals` so the counting is one thing and the thresholding another: the
		min-cell rule is a publication rule, and a source returning a count below it is still a source
		that answered. Every signal in `SIGNAL_SOURCES` gets an entry even at zero, so a signal that
		was never ingested is a zero here and a withholding there, never a missing key.
		"""
		counts = {signal: 0 for signal in SIGNAL_SOURCES}
		for event in self._signal_events:
			if event.county != county:
				continue
			year, week_no = _iso_week(event.at_iso)
			if (year, week_no) != (week_isoyear, week):
				continue
			counts[event.signal] += 1
		assert set(counts) == set(SIGNAL_SOURCES), 'every bullet of §11.7 is counted'
		assert all(c >= 0 for c in counts.values()), 'a count is not negative'
		return counts

	def scan(self, county: str, disease: str, week_isoyear: int, week: int,
	         baseline_weeks: int = 8) -> EarlyWarningScan:
		"""§AI-003 end to end: collect the signals, score them, and route the result for review.

		The baseline is the preceding `baseline_weeks` periods of the same signal in the same county,
		which is the only window the ledger can justify — a mean taken over an unstated period is a
		number nobody can check. A signal whose history is shorter than two periods is not scored at
		all: a standard deviation needs two observations, and `assess_warning` refuses a non-positive
		one rather than dividing by zero.

		The result never carries a public alert. §11.7 says signals above threshold "trigger a review
		by PHEOC epidemiologists. Never automatic public alerts", and `public_alert` is False on every
		path with no field that can set it.
		"""
		collection = self.collect_signals(county, week_isoyear, week)
		signals: list[WarningSignal] = []
		unscored: list[str] = []
		for obs in collection.observations:
			history = self._history(county, obs.signal, week_isoyear, week, baseline_weeks)
			# A history of all zeros and a history that is flat and non-zero are different facts and
			# they get different refusals. The first means this county has never produced this signal
			# — there is nothing to measure an increase against, and it is the one case an
			# epidemiologist most wants named rather than silently dropped. The second means the
			# signal runs at a constant rate, so a rise cannot be told from its own noise. Reporting
			# both as "no variation" would describe a first-ever signal as four weeks of quiet.
			if not any(history):
				unscored.append(f'{obs.signal} (no events in any of the {len(history)} prior periods, so '
				                f'there is no baseline to measure an increase against)')
				continue
			baseline = statistics.fmean(history)
			stdev = statistics.pstdev(history)
			if stdev <= 0:
				unscored.append(f'{obs.signal} (no variation across {len(history)} prior periods)')
				continue
			signals.append(WarningSignal(county=county, disease=disease, signal=obs.signal,
			                             observed=float(obs.count), baseline=baseline,
			                             baseline_stdev=stdev))
		assessment = self.assess_warning(county, disease, signals) if signals else WarningAssessment(
			county=county, raised=[], review_required=False, routed_to='routine weekly review',
			public_alert=False,
			message=f'No signal in {county} week {week} had a baseline to be measured against.',
		)
		if unscored:
			assessment = assessment.model_copy(update={
				'message': assessment.message + ' Not scored: ' + '; '.join(unscored) + '.',
			})
		return EarlyWarningScan(
			county=county, disease=disease, week_isoyear=week_isoyear, week=week,
			collection=collection, assessment=assessment,
			message=('Signals are counted from app events and scored against the county\'s own recent '
			         'history. Anything above threshold is routed to an epidemiologist for review; this '
			         'system never issues a public alert on its own.'),
		)

	def _history(self, county: str, signal: str, week_isoyear: int, week: int,
	             baseline_weeks: int) -> list[float]:
		"""The counts for the `baseline_weeks` periods before this one, oldest first.

		Periods with no events are included as zero rather than skipped. A quiet week is an
		observation, and dropping it would raise the mean and narrow the spread — which makes the
		next genuine rise look smaller, exactly when it matters most.
		"""
		assert baseline_weeks >= 2, 'a baseline needs at least two periods'
		periods = _prior_periods(week_isoyear, week, baseline_weeks)
		by_period = {p: 0 for p in periods}
		for event in self._signal_events:
			if event.county != county or event.signal != signal:
				continue
			key = _iso_week(event.at_iso)
			if key in by_period:
				by_period[key] += 1
		return [float(by_period[p]) for p in periods]

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
