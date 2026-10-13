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
	MIN_CELL_SIZE, SIGNAL_SOURCES, AggregateCell, ClusterLink, EarlyWarningScan, FairnessAudit,
	Hotspot, HotspotMap, ModelCard, ModelFootprint, RaisedSignal, RedressOutcome, RedressRequest,
	ResourceRecommendation, RiskInputs, RiskScore, SignalCollection, SignalEvent, SignalObservation,
	TransmissionCluster, WarningAssessment, WarningSignal,
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

	# §AI-001 says "uses anonymised, aggregated data"; it states no weights. These are the model's
	# own, and they are here rather than inline so the one place that decides what a hotspot is can
	# be read as a whole. `_WEIGHT_FEVER` dominates because fever is the signal the product actually
	# collects at scale; the other four shift the cell, they do not carry it.
	_WEIGHT_FEVER = 1.0
	_WEIGHT_COUGH = 0.5
	_WEIGHT_FACILITY = 0.4
	_WEIGHT_GEOFENCE = 0.3
	_WEIGHT_SEARCH = 0.3
	# Two cells are in one cluster when they are within this of each other. The section states no
	# distance, so it is a named constant with the reasoning attached rather than a literal: 5 km is
	# the radius §COM-102's own alert zones top out at, so a cluster is the same order of
	# neighbourhood as the alert a response team would raise over it.
	CLUSTER_RADIUS_KM = 5.0

	def cells_from_signals(self, county: str, cell_id: str, population: int,
			at_iso: str | None = None, facility_reports: int = 0, geofence_entries: int = 0,
			lat: float | None = None, lon: float | None = None) -> AggregateCell:
		"""Build one `AggregateCell` from the signals this service already holds (§AI-001's Inputs).

		This is the bridge the section's second and fifth Inputs were missing. The tree had both
		quantities and neither reached the model: the search signals live in this service's own
		`_signal_events` ledger under `facility_search` and `medicine_search`, and geofence entries
		live in `integrations.feeds.build_geofence_feed`'s aggregation — distinct subjects per cell,
		already floored at 10 — which the caller passes in because that aggregation is the module that
		owns the floor and this service must not keep a second copy of it. A signal the product
		records and does not feed to the prediction it makes is an Input the section asks for and
		nobody wired.

		`facility_reports` is likewise the caller's: §AI-001's fourth Input is *crowdsourced* reports
		about facilities, which live in `afya.facilities`, and reading the search ledger into that
		field would make two of the section's five Inputs the same number wearing two names.

		The window is one day, because the ledger's own baseline is a distribution over periods and a
		day is the smallest period the section's other consumers read. The cell is built whatever its
		population and left for `hotspots` to suppress and count — that is the one place that decides
		what may be published, and a bridge that pre-filtered would hide the suppression from the
		report that exists to state it.
		"""
		assert county and cell_id, 'a cell needs a county and an id'
		window = (at_iso or date.today().isoformat())[:10]
		today = [e for e in self._signal_events if e.county == county and e.at_iso[:10] == window]

		def _count(*signals: str) -> int:
			return sum(1 for e in today if e.signal in signals)

		return AggregateCell(
			cell_id=cell_id, county=county, population=population,
			fever_reports=_count('fever_triage', 'triage_volume'),
			cough_events=_count('cough_events'),
			# The ledger's `encounter_density` signal is a count of proximity encounters and the cell
			# wants a density, so the count is the numerator over the population the caller gave. The
			# `unwell_checkin` signal is the closest thing the ledger holds to an encounter and is
			# what §AI-003 names as its sixth monitored pattern; both are folded here for the same
			# reason and the cell's `reason` names the density rather than either count.
			encounter_density=round(_count('encounter_density', 'unwell_checkin') / population, 4) if population else 0.0,
			facility_reports=facility_reports, geofence_entries=geofence_entries,
			search_signals=_count('facility_search', 'medicine_search'),
			lat=lat, lon=lon,
		)

	def _signal_score(self, cell: AggregateCell) -> float:
		"""The cell's combined signal per person, in the section's five Inputs.

		Every term is a *rate*, not a count: a cell of 40,000 and a cell of 200 with the same count
		are not the same event, and a model that added raw counts would rank the big cell first every
		time and call it epidemiology.
		"""
		pop = cell.population
		return (
			self._WEIGHT_FEVER * cell.fever_reports / pop
			+ self._WEIGHT_COUGH * cell.cough_events / pop
			+ self._WEIGHT_FACILITY * cell.facility_reports / pop
			+ self._WEIGHT_GEOFENCE * cell.geofence_entries / pop
			+ self._WEIGHT_SEARCH * cell.search_signals / pop
			# Encounter density is already per person, so it enters unscaled by population.
			+ cell.encounter_density
		)

	def _cluster(self, cells: list[AggregateCell]) -> list[TransmissionCluster]:
		"""§AI-001's "transmission cluster identification": connected cells, by proximity.

		Single-linkage over the cells that carry a position, and only over cells that already cleared
		the baseline — clustering the whole map would produce one cluster spanning the country
		whenever the map is dense, which names every cell and therefore identifies none.

		A cell with no `lat`/`lon` cannot be linked and is reported in the `reason` rather than
		dropped silently: "we could not tell whether this cell touches the others" is a fact PHEOC
		can act on, and a cluster that quietly omitted it would read as complete.
		"""
		from afya.facilities.service import haversine_km
		located = [c for c in cells if c.lat is not None and c.lon is not None]
		unlocated = len(cells) - len(located)
		# Bound to tuples so the `None` narrowing survives into the loop: a cell that reached this
		# list has both coordinates, and the assertion says so once rather than at every use.
		points: list[tuple[AggregateCell, float, float]] = []
		for c in located:
			assert c.lat is not None and c.lon is not None, 'located cells carry both coordinates'
			points.append((c, c.lat, c.lon))
		# Union-find over indices, so a chain of cells 4 km apart is one cluster however long it is.
		parent = list(range(len(points)))

		def find(i: int) -> int:
			while parent[i] != i:
				parent[i] = parent[parent[i]]
				i = parent[i]
			return i

		links: list[ClusterLink] = []
		for i, (a, alat, alon) in enumerate(points):
			for j in range(i + 1, len(points)):
				b, blat, blon = points[j]
				km = haversine_km(alat, alon, blat, blon)
				if km <= self.CLUSTER_RADIUS_KM:
					parent[find(i)] = find(j)
					links.append(ClusterLink(
						from_cell=a.cell_id, to_cell=b.cell_id, km=round(km, 2),
						shared_signal='adjacent cells within the cluster radius',
					))
		groups: dict[int, list[int]] = {}
		for i in range(len(points)):
			groups.setdefault(find(i), []).append(i)
		out: list[TransmissionCluster] = []
		for members in groups.values():
			if len(members) < 2:
				continue  # one cell is a hotspot, which the map already carries
			cells_in = [points[i][0] for i in members]
			ids = sorted(c.cell_id for c in cells_in)
			edge = [link for link in links if link.from_cell in ids and link.to_cell in ids]
			counties = sorted({c.county for c in cells_in})
			total_pop = sum(c.population for c in cells_in)
			combined = round(min(0.99, sum(self._signal_score(c) * c.population for c in cells_in) / total_pop), 4)
			out.append(TransmissionCluster(
				cluster_id='TC-' + '-'.join(ids[:3]), counties=counties, cell_ids=ids, links=edge,
				combined_probability=combined,
				reason=(
					f'{len(cells_in)} adjacent cells ({", ".join(ids)}) within '
					f'{self.CLUSTER_RADIUS_KM:g} km of one another, combined signal '
					f'{combined:.3f} per person across a population of {total_pop}.'
					+ (f' {unlocated} further cell(s) carried no position and could not be linked.' if unlocated else '')
				),
			))
		return sorted(out, key=lambda c: -c.combined_probability)

	def _recommend(self, clusters: list[TransmissionCluster], hotspots: list[Hotspot]) -> list[ResourceRecommendation]:
		"""§AI-001's "resource deployment recommendations", derived from what the map found.

		Only from clusters and hotspots, never from the raw cells: a recommendation is the section's
		third Output and it has to trace to its first two, or it is a number with no finding behind
		it. A cluster gets a team and test kits — the two things that verify a cluster — and a lone
		hotspot gets risk communication, because one cell above baseline is a signal to check, not a
		finding to deploy against.

		`quantity` is `None` where the section's own arithmetic does not determine one. A rapid
		response team is one per cluster and that is a decision the map can make; how many ORS kits a
		county needs depends on a stock position this service does not hold, and inventing a figure
		would be a modelled number wearing the authority of a recommendation.
		"""
		per_county: dict[str, list[str]] = {}
		for cluster in clusters:
			for county in cluster.counties:
				per_county.setdefault(county, []).append(cluster.cluster_id)
		out: list[ResourceRecommendation] = []
		for county, cluster_ids in sorted(per_county.items()):
			out.append(ResourceRecommendation(
				county=county, resource='rapid_response_team', quantity=len(cluster_ids),
				unit='team(s)', rationale=(
					f'{len(cluster_ids)} transmission cluster(s) in {county} '
					f'({", ".join(cluster_ids)}); a cluster is verified by sampling, which is what a '
					'rapid response team does.'
				),
			))
			out.append(ResourceRecommendation(
				county=county, resource='test_kits', quantity=None, unit='kits', rationale=(
					f'One or more transmission clusters in {county}. The quantity depends on the '
					'cluster population and the county\'s current stock, neither of which this service '
					'holds — it is left for the county team to size rather than modelled here.'
				),
			))
		lone = [h for h in hotspots if not any(h.county in c.counties for c in clusters)]
		for county in sorted({h.county for h in lone}):
			out.append(ResourceRecommendation(
				county=county, resource='risk_communication', quantity=None, unit='campaign',
				rationale=(
					f'{sum(1 for h in lone if h.county == county)} cell(s) above baseline in {county} '
					'with no adjacent cell above it. One elevated cell is a signal to check, so this is '
					'a communication recommendation and not a deployment.'
				),
			))
		return out

	def hotspots(self, cells: list[AggregateCell]) -> HotspotMap:
		"""§AI-001's map: hotspots, the clusters they form, and what that implies for resources.

		The suppression rule is applied once, to the cells that go in, so a cluster can only ever be
		built from cells that already cleared `MIN_CELL_SIZE`. That ordering is the privacy control:
		a cluster whose `reason` named a cell of four people would re-identify exactly what the floor
		exists to prevent, and a cluster built before suppression would do it through the back door.
		"""
		assert cells, 'no cells supplied'
		eligible = [c for c in cells if c.population >= MIN_CELL_SIZE]
		suppressed = len(cells) - len(eligible)
		if not eligible:
			return HotspotMap(hotspots=[], suppressed_cells=suppressed, consumers=['county health teams', 'PHEOC'],
				explanation='Every cell is below the minimum cell size of 10; nothing may be published.')
		scores = [self._signal_score(c) for c in eligible]
		mean = statistics.fmean(scores)
		stdev = statistics.pstdev(scores) or 1.0
		out: list[Hotspot] = []
		for cell, score in zip(eligible, scores):
			z = (score - mean) / stdev
			prob = round(min(0.99, max(0.01, 0.5 + z * 0.15)), 2)
			if z < 0.5:
				continue
			rate = cell.fever_reports / cell.population
			# The reason names every input and its value, including the zero ones: a reader has to be
			# able to tell "this cell reported no geofence entries" from "this deployment has no
			# geofence feed", and a reason that omitted the zeros cannot say which.
			reason = (
				f'{cell.fever_reports} fever reports in a population of {cell.population} '
				f'({rate * 1000:.1f} per 1,000) against a mean of {mean * 1000:.1f} per 1,000; '
				f'{cell.cough_events} cough, {cell.facility_reports} facility report(s), '
				f'{cell.geofence_entries} geofence entr(ies), {cell.search_signals} search signal(s), '
				f'{cell.encounter_density:.1f} encounters per person.'
			)
			out.append(Hotspot(cell_id=cell.cell_id, county=cell.county, probability=prob, reason=reason,
				recommended_action='Send a rapid response team to verify and test; increase local surveillance.'))
		hotspots = sorted(out, key=lambda h: -h.probability)
		clusters = self._cluster([c for c in eligible if any(h.cell_id == c.cell_id for h in hotspots)])
		recommendations = self._recommend(clusters, hotspots)
		self._log_info('hotspot map built', hotspots=len(hotspots), clusters=len(clusters),
		               recommendations=len(recommendations), suppressed=suppressed)
		return HotspotMap(
			hotspots=hotspots, suppressed_cells=suppressed,
			consumers=['county health teams', 'PHEOC'],
			explanation=f'{len(hotspots)} cell(s) above baseline; {len(clusters)} cluster(s) among them; '
				f'{suppressed} suppressed for size. Aggregated data only — no individual record informed this map.',
			clusters=clusters, recommendations=recommendations,
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
