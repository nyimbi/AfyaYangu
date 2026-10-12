"""§AI-003 outbreak early warning: the six signals, collected from the app's own events.

§11.7 lists six observable patterns and says signals above threshold "trigger a review by PHEOC
epidemiologists. Never automatic public alerts." The scorer for that existed and was tested; the
collector did not, so the section was a detector nothing fed. These tests cover the half that was
missing — the counting, the period, the baseline, and the refusals — and then the routes that feed it.

The recurring theme is that a zero and a suppression are different facts. A signal nobody produced
and a signal too small to publish both read as "nothing happened" if the collector drops them
silently, and an epidemiologist cannot tell an outbreak response that is working from one that is
not collecting.
"""
from datetime import date, timedelta
from typing import Any

import httpx
import pytest

from afya.ai.service import MIN_CELL_SIZE, WARNING_Z, AIService, _iso_week, _prior_periods
from afya.ai.views import SIGNAL_CARRYING_FIELDS, SIGNAL_SOURCES, SignalEvent


def _svc() -> AIService:
	return AIService()


def _client() -> tuple[httpx.AsyncClient, dict[str, object]]:
	"""A real app over a real service set, so each test's events do not leak into the next."""
	from afya.service import build_services, create_app
	services = build_services()
	return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(services)),
	                         base_url='http://t'), services


def _monday(week_isoyear: int, week: int) -> date:
	return date.fromisocalendar(week_isoyear, week, 1)


async def _fill(ai: AIService, county: str, signal: str, week_isoyear: int, week: int,
                count: int) -> None:
	"""`count` events of `signal` in `county`, all inside one ISO period."""
	day = _monday(week_isoyear, week).isoformat()
	for i in range(count):
		await ai.record_signal_event(SignalEvent(county=county, at_iso=day, signal=signal, event_ref=f'r{i}'))


async def _county_officer(c: httpx.AsyncClient) -> str:
	"""A county health team token through the app's own PKCE flow — §17.4's `county_aggregate`."""
	from afya.auth.views import s256
	verifier = 'v' * 64
	authz = (await c.post('/auth/pkce/authorize', json={
		'client_id': 'app', 'redirect_uri': 'afya://cb', 'code_challenge': s256(verifier),
		'state': 'state-1234'})).json()
	return (await c.post('/auth/pkce/token', params={'role': 'county_officer'}, json={
		'authorization_code': authz['authorization_code'], 'client_id': 'app',
		'redirect_uri': 'afya://cb', 'code_verifier': verifier})).json()['access_token']


# --- the period ---------------------------------------------------------------------------------

def test_an_event_is_placed_in_the_iso_week_it_happened_in() -> None:
	"""The period is ISO, and ISO is not the calendar month or a rolling seven days.

	A rolling window would move with the query, so two runs of the same question would disagree about
	which events belong to the baseline.
	"""
	assert _iso_week('2026-05-11T08:00:00+00:00') == (2026, 20)
	assert _iso_week('2026-05-17T23:59:59+00:00') == (2026, 20)
	assert _iso_week('2026-05-18T00:00:00+00:00') == (2026, 21)
	# The date alone is enough — a ledger row carries a timestamp and only the day is read.
	assert _iso_week('2026-05-11') == (2026, 20)


def test_week_one_can_belong_to_the_previous_iso_year() -> None:
	"""The year comes back with the week, because taking it from the date is wrong for one week a year.

	2025-12-29 is a Monday and it is week 1 of ISO year **2026**. A collector that read the year off
	the date string would file these events under 2025-W01, which is a period eleven months earlier —
	the events would still be in the ledger and would never be counted again.
	"""
	assert date(2025, 12, 29).isocalendar()[:2] == (2026, 1)
	assert _iso_week('2025-12-29') == (2026, 1)
	assert _iso_week('2026-01-04') == (2026, 1)
	assert _iso_week('2026-01-05') == (2026, 2)


def test_the_prior_periods_cross_the_year_boundary_and_are_distinct() -> None:
	"""Week arithmetic by hand is wrong at the year end: 2026-W02 minus 4 is not 2026-W-2.

	Anchoring on the period's Monday and stepping back seven days lets the calendar answer. The
	distinctness assertion is the one that matters — a window that repeated a period would double
	weight it in the baseline.
	"""
	assert _prior_periods(2026, 2, 4) == [(2025, 50), (2025, 51), (2025, 52), (2026, 1)]
	assert _prior_periods(2026, 10, 3) == [(2026, 7), (2026, 8), (2026, 9)]
	assert _prior_periods(2025, 1, 3) == [(2024, 50), (2024, 51), (2024, 52)]
	# Oldest first, so the history reads in the order it happened.
	for year, week in ((2026, 1), (2026, 2), (2026, 30), (2025, 1)):
		periods = _prior_periods(year, week, 12)
		assert len(set(periods)) == 12, f'{year}-W{week} window repeats a period'
		assert periods == sorted(periods), f'{year}-W{week} window is not oldest-first'
		assert (year, week) not in periods, 'the window is prior periods, not the period itself'


def test_a_period_before_the_deployment_is_refused() -> None:
	"""A baseline has to be read from periods the ledger could have covered."""
	ai = _svc()
	with pytest.raises(AssertionError):
		ai.collect_signals('Nairobi', 2023, 10)


# --- collection: the six signals, counted --------------------------------------------------------

def test_the_six_signals_are_the_sections_six_bullets() -> None:
	"""§11.7 lists six; the collector produces six and does not pad the set.

	`WarningSignal.signal` also accepts `triage_volume` and `hotline_calls` — §11.7's neighbours in
	the surveillance module — but they are not among the six bullets AI-003 names. A collector that
	emitted them would report seven signals against a section that lists six, and nobody would be
	able to say which one was invented.
	"""
	assert set(SIGNAL_SOURCES) == {'fever_triage', 'cough_events', 'facility_search',
	                               'medicine_search', 'unwell_checkin', 'encounter_density'}
	assert 'triage_volume' not in SIGNAL_SOURCES and 'hotline_calls' not in SIGNAL_SOURCES
	assert set(SIGNAL_CARRYING_FIELDS) == set(SIGNAL_SOURCES), 'every bullet names its source field'


def test_the_source_fields_the_signals_are_read_from_still_exist() -> None:
	"""A collector keyed on a renamed field stops collecting and keeps returning zero.

	That reads as "no outbreak" — the one failure a detection layer may not have — and it is
	invisible, because a count of zero is a legal answer. Naming the model and field here makes the
	test fail when the source moves rather than when someone notices the silence.
	"""
	import afya.facilities.views as facilities_views
	import afya.location.views as location_views
	import afya.medicine.views as medicine_views
	import afya.mental.views as mental_views
	import afya.ml.views as ml_views
	import afya.triage.views as triage_views

	modules = {'TriageInput': triage_views, 'CoughVerdict': ml_views, 'NearestRequest': facilities_views,
	           'DoseRequest': medicine_views, 'WHO5': mental_views, 'EncounterToken': location_views}
	for signal, (model_name, field) in SIGNAL_CARRYING_FIELDS.items():
		model = getattr(modules[model_name], model_name, None)
		assert model is not None, f'{model_name} is gone, so {signal} has no source'
		assert field in model.model_fields, f'{model_name}.{field} is gone, so {signal} reads nothing'


async def test_the_signals_are_counted_by_period_and_not_in_total() -> None:
	"""Ten events this week and ten last week is not twenty this week.

	A tally kept at each route cannot answer "how does this week compare" at all, which is the only
	question the section asks.
	"""
	ai = _svc()
	await _fill(ai, 'Nairobi', 'fever_triage', 2026, 20, MIN_CELL_SIZE)
	await _fill(ai, 'Nairobi', 'fever_triage', 2026, 19, MIN_CELL_SIZE * 2)
	collection = ai.collect_signals('Nairobi', 2026, 20)
	counts = {o.signal: o.count for o in collection.observations}
	assert counts == {'fever_triage': MIN_CELL_SIZE}, 'the prior period is not counted into this one'
	assert {o.week_isoyear for o in collection.observations} == {2026}
	assert {o.week for o in collection.observations} == {20}


async def test_another_county_is_not_counted_into_this_one() -> None:
	"""The bullet is a rise *in a locality*; a national number against a county baseline means nothing."""
	ai = _svc()
	await _fill(ai, 'Nairobi', 'fever_triage', 2026, 20, MIN_CELL_SIZE * 2)
	await _fill(ai, 'Kisumu', 'fever_triage', 2026, 20, MIN_CELL_SIZE * 2)
	counts = {o.signal: o.count for o in ai.collect_signals('Nairobi', 2026, 20).observations}
	assert counts['fever_triage'] == MIN_CELL_SIZE * 2


async def test_a_signal_under_the_minimum_cell_size_is_withheld_by_name() -> None:
	"""§19.3's min-cell rule applies to a signal too: four people's fevers identify four people.

	The refusal is reported with the signal's name and its count. A signal dropped silently and a
	signal that did not occur are different facts, and the whole point of the rule is that the first
	one is a gap an epidemiologist can see.
	"""
	ai = _svc()
	await _fill(ai, 'Nairobi', 'fever_triage', 2026, 20, MIN_CELL_SIZE - 1)
	collection = ai.collect_signals('Nairobi', 2026, 20)
	assert collection.observations == []
	# The five signals nobody produced are withheld too, and each is named with its zero — which is
	# the point: the one signal that almost happened is legible beside the five that did not.
	assert len(collection.withheld) == len(SIGNAL_SOURCES)
	held = [w for w in collection.withheld if w.startswith('fever_triage')]
	assert len(held) == 1
	assert str(MIN_CELL_SIZE - 1) in held[0] and str(MIN_CELL_SIZE) in held[0], \
		'the count and the threshold are both stated, so the gap is legible'
	assert sum(1 for w in collection.withheld if '(0 event(s)' in w) == len(SIGNAL_SOURCES) - 1


async def test_a_signal_at_the_minimum_cell_size_is_published() -> None:
	"""The rule is a floor, not a margin: exactly the minimum is publishable."""
	ai = _svc()
	await _fill(ai, 'Nairobi', 'fever_triage', 2026, 20, MIN_CELL_SIZE)
	collection = ai.collect_signals('Nairobi', 2026, 20)
	assert [o.signal for o in collection.observations] == ['fever_triage']
	assert not any(w.startswith('fever_triage') for w in collection.withheld)


async def test_the_canary_catches_a_min_cell_rule_that_is_off_by_one() -> None:
	"""The shipped threshold, pointed at the count just under it.

	The canary runs `collect_signals` itself and reads its own verdict, rather than a copy of the
	comparison. It confirms the boundary is load-bearing in both directions: one event fewer is
	withheld and the same count at the floor is published, so a `<` that drifted to `<=` fails here.
	"""
	ai = _svc()
	await _fill(ai, 'Nairobi', 'fever_triage', 2026, 20, MIN_CELL_SIZE - 1)
	under = ai.collect_signals('Nairobi', 2026, 20)
	assert under.observations == [] and under.withheld, 'the canary target must be present'
	await _fill(ai, 'Nairobi', 'fever_triage', 2026, 20, 1)
	at = ai.collect_signals('Nairobi', 2026, 20)
	assert [o.count for o in at.observations] == [MIN_CELL_SIZE]


async def test_a_signal_never_seen_is_a_zero_and_not_a_missing_key() -> None:
	"""Every bullet of §11.7 is counted every period, including the ones nobody produced.

	A missing key would make "we do not collect that" and "it did not happen" the same answer.
	"""
	ai = _svc()
	collection = ai.collect_signals('Nairobi', 2026, 20)
	assert collection.observations == []
	assert len(collection.withheld) == len(SIGNAL_SOURCES), 'every quiet signal is named'
	for signal in SIGNAL_SOURCES:
		assert any(w.startswith(f'{signal} (0 event(s)') for w in collection.withheld), signal


# --- the baseline --------------------------------------------------------------------------------

async def test_the_baseline_counts_quiet_periods_as_zero() -> None:
	"""A quiet week is an observation. Dropping it raises the mean and narrows the spread.

	Both effects point the same way: the next genuine rise measures as smaller, exactly when the
	measurement matters most. This is the test that pins the zero-fill.
	"""
	ai = _svc()
	await _fill(ai, 'Nairobi', 'fever_triage', 2026, 19, 20)
	history = ai._history('Nairobi', 'fever_triage', 2026, 20, 4)
	assert history == [0.0, 0.0, 0.0, 20.0], 'the three quiet periods are present as zeros'
	assert len(history) == 4


async def test_the_canary_catches_a_baseline_that_skips_quiet_periods() -> None:
	"""The shipped history, against the same history with the zeros dropped.

	The mutant is the obvious spelling — collect the periods that had events — and it is wrong in a
	way that is invisible on a busy signal. Here it changes the mean from 5.0 to 20.0 and the spread
	from 8.66 to 0.0, which is the difference between "an increase" and "no variation at all".
	"""
	ai = _svc()
	await _fill(ai, 'Nairobi', 'fever_triage', 2026, 19, 20)
	shipped = ai._history('Nairobi', 'fever_triage', 2026, 20, 4)
	without_quiet = [v for v in shipped if v]
	assert shipped != without_quiet, 'the canary target must be present before it is trusted'
	assert len(shipped) == 4 and len(without_quiet) == 1
	assert sum(shipped) / len(shipped) == 5.0
	assert sum(without_quiet) / len(without_quiet) == 20.0


async def test_a_baseline_needs_at_least_two_periods() -> None:
	"""A standard deviation over one observation is zero, and `z_score` refuses a zero denominator."""
	ai = _svc()
	with pytest.raises(AssertionError):
		ai._history('Nairobi', 'fever_triage', 2026, 20, 1)


# --- the scan ------------------------------------------------------------------------------------

async def test_a_rise_is_scored_against_the_countys_own_history_and_routed_for_review() -> None:
	"""§AI-003 end to end: eight quiet-ish weeks, then a week that is far above them."""
	ai = _svc()
	for week in range(12, 20):
		await _fill(ai, 'Nairobi', 'fever_triage', 2026, week, 10 + (week % 2))
	await _fill(ai, 'Nairobi', 'fever_triage', 2026, 20, 60)
	scan = ai.scan('Nairobi', 'evd', 2026, 20, baseline_weeks=8)
	assert scan.assessment.review_required is True
	raised = {r.signal: r for r in scan.assessment.raised}
	assert 'fever_triage' in raised
	assert raised['fever_triage'].observed == 60.0
	assert raised['fever_triage'].z_score >= WARNING_Z
	assert 10 <= raised['fever_triage'].baseline <= 11
	assert scan.assessment.routed_to == 'PHEOC epidemiologist on duty'


async def test_a_flat_signal_is_not_raised() -> None:
	"""The negative control for the test above: same volume, no rise, no review."""
	ai = _svc()
	for week in range(12, 21):
		await _fill(ai, 'Nairobi', 'fever_triage', 2026, week, 12)
	scan = ai.scan('Nairobi', 'evd', 2026, 20, baseline_weeks=8)
	assert scan.assessment.raised == []
	assert scan.assessment.review_required is False
	assert scan.assessment.routed_to == 'routine weekly review'


def test_the_scan_never_issues_a_public_alert_on_any_path() -> None:
	"""§11.7: "trigger a review by PHEOC epidemiologists. Never automatic public alerts."

	Asserted over the model rather than over one call: `EarlyWarningScan` and `WarningAssessment`
	carry no field that can set `public_alert`, so there is no path — scored, unscored, raised or
	quiet — on which it is True. A boolean the caller passes in would be a promise, not a control.
	"""
	from afya.ai.views import EarlyWarningScan, WarningAssessment
	assert 'public_alert' in WarningAssessment.model_fields, 'the assessment states it'
	assert WarningAssessment.model_fields['public_alert'].is_required(), \
		'a defaulted public_alert is a value nobody has to decide'
	# And `EarlyWarningScan` does not carry it at all: there is one place it could be set, and that
	# place is a field whose value `assess_warning` writes and no caller supplies.
	assert 'public_alert' not in EarlyWarningScan.model_fields, \
		'a second place to set it is a second thing to get wrong'
	assert not any(f.annotation is bool and f.default is True
	               for f in WarningAssessment.model_fields.values()), \
		'no boolean on the assessment defaults to True'


async def test_a_raised_scan_still_carries_no_public_alert() -> None:
	"""The same guarantee on the path where it would be tempting: a genuine above-threshold signal."""
	ai = _svc()
	for week in range(12, 20):
		await _fill(ai, 'Nairobi', 'fever_triage', 2026, week, 10 + (week % 2))
	await _fill(ai, 'Nairobi', 'fever_triage', 2026, 20, 90)
	scan = ai.scan('Nairobi', 'evd', 2026, 20, baseline_weeks=8)
	assert scan.assessment.review_required is True
	assert scan.assessment.public_alert is False
	assert scan.assessment.message.endswith('no public alert is issued automatically.')


async def test_a_signal_with_no_history_at_all_is_named_rather_than_scored() -> None:
	"""A first-ever signal has nothing to be an increase against, and it says so in those words.

	The reachable refusal here is not "the baseline is too short" — `_history` zero-fills, so it
	always returns the requested number of periods. It is a history that is *entirely* zeros, which
	means this county has never produced this signal. That is different from a signal that runs at a
	constant rate, and reporting both as "no variation across eight prior periods" would describe a
	first-ever signal as eight weeks of quiet observation.
	"""
	ai = _svc()
	await _fill(ai, 'Nairobi', 'fever_triage', 2026, 20, 40)
	scan = ai.scan('Nairobi', 'evd', 2026, 20, baseline_weeks=4)
	assert scan.assessment.raised == []
	assert 'no events in any of the 4 prior periods' in scan.assessment.message
	assert 'no variation' not in scan.assessment.message


async def test_a_constant_signal_is_named_as_flat_rather_than_as_unobserved() -> None:
	"""The other half of the pair: real events every week, no variation to measure a rise against."""
	ai = _svc()
	for week in range(16, 20):
		await _fill(ai, 'Nairobi', 'fever_triage', 2026, week, 25)
	await _fill(ai, 'Nairobi', 'fever_triage', 2026, 20, 40)
	scan = ai.scan('Nairobi', 'evd', 2026, 20, baseline_weeks=4)
	assert 'no variation across 4 prior periods' in scan.assessment.message
	assert 'no events in any of the' not in scan.assessment.message


async def test_the_scan_says_which_signals_it_could_not_score() -> None:
	"""One signal with a baseline and one without: the first is scored, the second is reported."""
	ai = _svc()
	for week in range(12, 20):
		await _fill(ai, 'Nairobi', 'fever_triage', 2026, week, 10 + (week % 3))
	await _fill(ai, 'Nairobi', 'fever_triage', 2026, 20, 60)
	await _fill(ai, 'Nairobi', 'medicine_search', 2026, 20, 30)
	scan = ai.scan('Nairobi', 'evd', 2026, 20, baseline_weeks=8)
	assert 'medicine_search' in scan.assessment.message
	assert 'fever_triage' not in scan.assessment.message.split('Not scored:')[-1]


async def test_a_signal_below_the_cell_size_is_withheld_and_never_scored() -> None:
	"""The min-cell rule sits upstream of the scorer, so a suppressed signal cannot raise a review."""
	ai = _svc()
	for week in range(12, 20):
		await _fill(ai, 'Nairobi', 'fever_triage', 2026, week, 10)
	await _fill(ai, 'Nairobi', 'fever_triage', 2026, 20, MIN_CELL_SIZE - 1)
	scan = ai.scan('Nairobi', 'evd', 2026, 20, baseline_weeks=8)
	assert scan.assessment.raised == []
	assert any(w.startswith('fever_triage') for w in scan.collection.withheld)


async def test_the_ledger_is_bounded() -> None:
	"""Every store in this service is bounded; an unbounded one is a leak with a nice name."""
	ai = _svc()
	await ai.record_signal_event(SignalEvent(county='Nairobi', at_iso='2026-05-11',
	                                         signal='fever_triage'))
	assert len(ai._signal_events) == 1


async def test_an_unknown_signal_is_refused_at_the_ledger() -> None:
	"""The ledger is the one door, so the guard belongs there and not only on the route."""
	ai = _svc()
	with pytest.raises(Exception):
		await ai.record_signal_event(SignalEvent(county='Nairobi', at_iso='2026-05-11',
		                                         signal='made_up_signal'))


# --- the routes ----------------------------------------------------------------------------------

async def test_a_fever_triage_in_a_county_records_a_signal() -> None:
	"""§AI-003's first bullet, through the route a client actually calls."""
	client, services = _client()
	ai: AIService = services['ai']  # type: ignore[assignment]
	async with client:
		await client.post('/triage/preliminary', json={
			'symptoms': ['fever'], 'temperature_c': 38.8, 'county': 'Nairobi'})
	recorded = [e for e in ai._signal_events if e.signal == 'fever_triage']
	assert len(recorded) == 1 and recorded[0].county == 'Nairobi'


async def test_a_triage_without_fever_or_without_a_county_records_nothing() -> None:
	"""The count is of *fever* triages in a *locality*. Both halves are load-bearing.

	A rash triage during a fever outbreak is a different observation, and mixing them would let any
	cough campaign raise a fever signal.
	"""
	client, services = _client()
	ai: AIService = services['ai']  # type: ignore[assignment]
	async with client:
		await client.post('/triage/preliminary', json={
			'symptoms': ['rash'], 'temperature_c': 38.8, 'county': 'Nairobi'})
		await client.post('/triage/preliminary', json={'symptoms': ['fever'], 'temperature_c': 38.8})
	assert ai._signal_events == []


async def test_a_finder_search_that_names_a_symptom_records_a_signal_and_a_plain_one_does_not() -> None:
	"""§11.7's third bullet is searches for a *specific symptom*, not searches.

	"nearest clinic" is the commonest query there is and it is not a surveillance signal; "nearest
	clinic for a fever" is. The vocabulary is the triage symptom list, so the finder and the triage
	cannot disagree about what a symptom is.
	"""
	client, services = _client()
	ai: AIService = services['ai']  # type: ignore[assignment]
	body: dict[str, Any] = {'lat': -1.29, 'lon': 36.82, 'county': 'Nairobi'}
	async with client:
		await client.post('/facilities/find', json={**body, 'query': 'nearest clinic'})
		await client.post('/facilities/find', json={**body, 'query': 'KNH'})
		assert ai._signal_events == []
		await client.post('/facilities/find', json={**body, 'query': 'clinic for a fever'})
		await client.post('/facilities/find', json={**body, 'query': 'Fever'})
	assert [e.signal for e in ai._signal_events] == ['facility_search', 'facility_search']
	assert all(e.county == 'Nairobi' for e in ai._signal_events)


async def test_a_medicine_lookup_records_the_drug_it_was_for() -> None:
	"""§11.7's fourth bullet: a rise in medicine searches. The drug is the ref, and the detector
	never reads it — it is what makes a count traceable back to its events."""
	client, services = _client()
	ai: AIService = services['ai']  # type: ignore[assignment]
	async with client:
		await client.post('/medicine/dose', json={
			'drug': 'paracetamol', 'weight_kg': 20, 'mg_per_kg': 15, 'county': 'Kisumu'})
	recorded = [e for e in ai._signal_events if e.signal == 'medicine_search']
	assert len(recorded) == 1
	assert recorded[0].event_ref == 'paracetamol' and recorded[0].county == 'Kisumu'


async def test_a_low_wellbeing_checkin_records_a_signal_and_a_good_one_does_not() -> None:
	"""§11.7's fifth bullet. A good score is not "I feel unwell" — only the lower bands count.

	No subject reaches the ledger: the event carries the locality and nothing else, which is why the
	route can be guarded on the person and the event still be unlinkable to them.
	"""
	client, services = _client()
	ai: AIService = services['ai']  # type: ignore[assignment]
	async with client:
		token = (await client.post('/auth/anonymous', json={'subject_ref': 'AI003'})).json()['token']
		head = {'authorization': f'Bearer {token}'}
		good = await client.post('/mental/who5', headers=head, json={
			'subject_ref': 'AI003', 'scores': [5, 5, 5, 5, 5], 'county': 'Nairobi'})
		assert good.json()['band'] == 'good'
		assert ai._signal_events == []
		low = await client.post('/mental/who5', headers=head, json={
			'subject_ref': 'AI003', 'scores': [0, 1, 0, 1, 0], 'county': 'Nairobi'})
		assert low.json()['band'] in ('low', 'very_low')
	recorded = [e for e in ai._signal_events if e.signal == 'unwell_checkin']
	assert len(recorded) == 1 and recorded[0].county == 'Nairobi'
	assert not hasattr(recorded[0], 'subject_ref'), 'the ledger carries no subject'


async def test_a_proximity_encounter_records_a_density_event(tmp_path: Any) -> None:
	"""§11.7's sixth bullet, and the PET is carried as an opaque ref rather than a person.

	The route is dormant until §11.1 row 1 is declared, which is the section's own rule and not
	something to route around: an encounter logged while the response is off is a contact record
	nobody asked for. So the row is fired first and the emission is asserted on the live path.
	"""
	from afya.location.views import EncounterToken
	from afya.privacy.views import RBACRole
	from afya.registry.service import Tier4Activation as Keys
	from afya.service import build_services, create_app

	services = build_services(db_path=str(tmp_path / 'afya.db'))
	ai: AIService = services['ai']  # type: ignore[assignment]
	services['registry'].activate(Keys(  # type: ignore[attr-defined]
		authorized_by_pheoc=True, dpia_review_id='r1', flag_enabled=True))
	token = EncounterToken(pet='pet-abcdef1234567890abcdef1234567890', county='Nairobi',
	                       seen_at_ms=1_777_000_000_000, rssi_dbm=-60)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(services)),
	                             base_url='http://t') as client:
		sysadmin = services['auth'].provision_staff(  # type: ignore[attr-defined]
			'ops-0', RBACRole.sysadmin, registrar='MoH ops').access_token
		fired = await client.post('/tier4/activation/fire',
		                          headers={'authorization': f'Bearer {sysadmin}'},
		                          json={'firing_id': 'TF-00000001', 'trigger_number': 1,
		                                'scope': 'national_or_county',
		                                'evidence': 'PHEOC bulletin 2026-41',
		                                'fired_by': 'PHEOC duty officer',
		                                'fired_at_iso': '2026-10-11T09:00:00+00:00'})
		assert fired.status_code == 200, fired.text
		r = await client.post('/location/proximity/encounter', json=token.model_dump(mode='json'))
	assert r.status_code == 200, r.text
	recorded = [e for e in ai._signal_events if e.signal == 'encounter_density']
	assert len(recorded) == 1
	assert recorded[0].county == 'Nairobi'
	assert recorded[0].event_ref == token.pet[:8], 'the event_ref is a truncation, not the whole PET'
	assert len(recorded[0].event_ref) < len(token.pet), 'the ledger holds no usable identifier'


async def test_the_ingest_route_accepts_an_event_and_the_scan_route_reads_it_back() -> None:
	"""The two halves over HTTP: a client can post an event and a county officer can see the week."""
	client, _ = _client()
	async with client:
		officer = await _county_officer(client)
		head = {'authorization': f'Bearer {officer}'}
		posted = await client.post('/ai/signals', headers=head, json={
			'county': 'Nairobi', 'at_iso': '2026-05-11T09:00:00+00:00', 'signal': 'fever_triage'})
		assert posted.status_code == 200, posted.text
		assert posted.json()['signal'] == 'fever_triage'
		scan = await client.get('/ai/early-warning/Nairobi/scan',
		                        params={'week_isoyear': 2026, 'week': 20, 'baseline_weeks': 4},
		                        headers=head)
	assert scan.status_code == 200, scan.text
	body = scan.json()
	assert body['county'] == 'Nairobi' and body['week'] == 20
	assert body['assessment']['public_alert'] is False
	assert body['collection']['observations'] == [], 'one event is below the minimum cell size'
	assert any(w.startswith('fever_triage (1 event(s)') for w in body['collection']['withheld'])


async def test_the_scan_route_refuses_a_caller_without_the_county_scope() -> None:
	"""§17.4: a county's own signal counts are the county health team's, not any citizen's."""
	client, _ = _client()
	async with client:
		assert (await client.get('/ai/early-warning/Nairobi/scan')).status_code == 401
		anon = (await client.post('/auth/anonymous', json={})).json()['token']
		denied = await client.get('/ai/early-warning/Nairobi/scan',
		                          headers={'authorization': f'Bearer {anon}'})
	assert denied.status_code == 403


async def test_the_scan_route_defaults_to_the_current_week() -> None:
	"""Leaving the period out must not mean "some week" — it means the week the deployment is in.

	The default is computed from the clock rather than stored, so a scan cannot be pointed at a stale
	week by omitting a parameter.
	"""
	client, _ = _client()
	today = date.today().isocalendar()
	async with client:
		officer = await _county_officer(client)
		body = (await client.get('/ai/early-warning/Nairobi/scan',
		                         headers={'authorization': f'Bearer {officer}'})).json()
	assert (body['week_isoyear'], body['week']) == (today[0], today[1])


async def test_the_scan_route_refuses_an_event_that_is_not_one_of_the_six() -> None:
	"""The ingest route validates the signal name, so a typo is a 422 rather than a silent no-op."""
	client, _ = _client()
	async with client:
		officer = await _county_officer(client)
		head = {'authorization': f'Bearer {officer}'}
		assert (await client.post('/ai/signals', json={
			'county': 'Nairobi', 'at_iso': '2026-05-11', 'signal': 'fever'})).status_code == 401
		bad = await client.post('/ai/signals', headers=head, json={
			'county': 'Nairobi', 'at_iso': '2026-05-11', 'signal': 'fever'})
	assert bad.status_code == 422


def test_the_iso_week_helper_rejects_a_timestamp_with_no_date() -> None:
	"""The ledger guard states the reason: an event with no date cannot be placed in a period."""
	with pytest.raises(ValueError):
		_iso_week('not-a-date')


def test_the_period_window_is_the_same_every_time_it_is_asked() -> None:
	"""Determinism, because the baseline is compared against a county's own history.

	A window that moved with the query would make two runs of the same question disagree about what
	the county's normal is, and neither answer would be checkable.
	"""
	first = _prior_periods(2026, 20, 8)
	for _ in range(5):
		assert _prior_periods(2026, 20, 8) == first
	# And the window's own length is the calendar's, not a modulus: stepping back over a 53-week year.
	long_year = _prior_periods(2026, 5, 10)
	assert long_year == sorted(long_year)
	assert all(isinstance(y, int) and isinstance(w, int) for y, w in long_year)
	assert _monday(2026, 20) - _monday(2026, 19) == timedelta(weeks=1)
