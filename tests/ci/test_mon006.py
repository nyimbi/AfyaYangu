"""§10.2 MON-006: Air Quality Index.

The section lists five Features and three had no carrier. What existed was `air_alert`, which reads
a raw PM2.5 figure the caller supplies and branches on two ad-hoc cuts at 35 and 55 µg/m³ — and the
section asks for an *index*, which is the number a person can compare against a bulletin, the
category a screen prints, and the six-way scale the bands were a three-way approximation of.

The two sources are why this is computable rather than invented: the breakpoint table and the
interpolation are the EPA's own, and the source categories and the reason a *time of day* is the
right unit are WHO's.
"""
import pydantic
import pytest
from fastapi.testclient import TestClient

from afya.alerts.service import AlertsService
from afya.alerts.views import (
	AQI_CATEGORIES, PM25_BREAKPOINTS, AirQuality, AirQualityReading, OutdoorWindow, PollutionSource,
	pm25_aqi,
)


def _svc() -> AlertsService:
	return AlertsService()


def _air(pm25: float = 120.0) -> AirQuality:
	return AirQuality(county='Nairobi', pm25=pm25)


# --- the index -----------------------------------------------------------------------------------

def test_the_index_reproduces_the_sources_own_worked_example() -> None:
	"""The EPA's document walks a value through the table: a PM2.5 of 35.9 µg/m³ is interpolated
	inside the 35.5-55.4 band and comes out at 102. If the arithmetic drifts, this is the row that
	says so — it is the only figure in either source that is both a specific input and a specific
	output."""
	assert pm25_aqi(35.9) == 102, 'the interpolation no longer reproduces the source’s own example'


def test_every_band_boundary_lands_on_its_own_index() -> None:
	"""Read off the table rather than asserted as a list: the low end of each band must produce that
	band's `aqi_low` and the high end its `aqi_high`, or the interpolation is off by a category
	boundary and a person is told the wrong thing at exactly the value the category changes."""
	for low, high, aqi_low, aqi_high in PM25_BREAKPOINTS:
		assert pm25_aqi(low) == aqi_low, f'{low} µg/m³ is not index {aqi_low}'
		assert pm25_aqi(high) == aqi_high, f'{high} µg/m³ is not index {aqi_high}'


def test_the_index_is_monotonic_and_stays_inside_the_scale() -> None:
	"""A reading that goes up must not make the index go down, and the scale ends at 500. The
	truncation is the source's, so the steps are coarse — the property is monotonicity, not
	strictness."""
	previous = -1
	for tenth in range(0, 5200):
		index = pm25_aqi(tenth / 10)
		assert index >= previous, f'the index fell at {tenth / 10} µg/m³'
		assert 0 <= index <= 500, f'the index left the scale at {tenth / 10} µg/m³'
		previous = index


def test_a_reading_above_the_table_is_capped_rather_than_extrapolated() -> None:
	"""Beyond 500.4 the scale has no answer. Serving 500 says "past the top of the scale", which is
	true; extrapolating gives an index no screen is designed for and no guidance is written
	against."""
	assert pm25_aqi(600.0) == 500


def test_truncation_happens_before_the_lookup() -> None:
	"""The source truncates to one decimal place before choosing a band, and the boundaries are
	inclusive at the top with nothing between them — 35.4 is in one band and 35.5 in the next. So
	35.49 is not "almost 35.5": it truncates down into the band below and is served index 100, where
	an untruncated lookup would have found no band below it and interpolated in the one above."""
	assert pm25_aqi(35.49) == 100, 'the reading was not truncated before the band was chosen'
	assert pm25_aqi(35.5) == 101
	assert pm25_aqi(12.09) == 50, 'a reading just under a boundary was rounded up into the next band'


# --- the reading ---------------------------------------------------------------------------------

def test_the_category_agrees_with_the_index() -> None:
	"""The refusal that makes the pair a fact: a reading whose index says 180 and whose category says
	"moderate" is a screen telling a person the air is fine while the number beside it says
	otherwise."""
	reading = _svc().air_reading(_air(120.0), 'Kibera')
	assert reading.aqi == 184 and reading.category == 'unhealthy'
	with pytest.raises(pydantic.ValidationError, match='not moderate'):
		AirQualityReading(county='Nairobi', location='Kibera', pm25=120.0, aqi=184,
			category='moderate')


def test_the_index_cannot_be_asserted_against_the_reading() -> None:
	"""A caller posting a PM2.5 of 120 with an index of 40 is refused, because the index is derived
	and not an independent field. The category has to be the one that *agrees with the wrong index*
	for this to be the check under test — with `moderate` the category validator fires first and the
	derivation is never reached."""
	with pytest.raises(pydantic.ValidationError, match='is index'):
		AirQualityReading(county='Nairobi', location='Kibera', pm25=120.0, aqi=40, category='good')


def test_the_three_way_band_now_agrees_with_the_index_it_is_read_off() -> None:
	"""The cuts were 35 and 55 µg/m³, which are the index's own boundaries arrived at by a different
	route and not quite the same ones: the index crosses 100 at 35.5 and 150 at 55.5. So 35.2 and
	55.2 were served an "AIR ALERT" beside an index that said otherwise — two answers to one question
	in one payload."""
	for pm25 in (35.2, 35.5, 55.2, 55.5, 100.0, 200.0):
		a = _air(pm25)
		if a.aqi > 150:
			assert a.band == 'alert'
		elif a.aqi > 100:
			assert a.band == 'watch'
		else:
			assert a.band == 'normal'
	assert _air(35.2).band == 'normal', 'a reading the index calls clean is served an alert'
	assert _air(55.2).band == 'watch'


def test_every_category_is_reachable_and_the_ranges_do_not_overlap() -> None:
	"""A category nothing can produce is a name on a screen that never appears, and overlapping
	ranges make the category a function of which row is checked first."""
	covered: set[int] = set()
	for low, high, _name in AQI_CATEGORIES:
		assert low == (max(covered) + 1 if covered else 0), f'the categories leave a gap at {low}'
		covered.update(range(low, high + 1))
	assert covered == set(range(0, 501))
	seen = {next(n for lo, hi, n in AQI_CATEGORIES if lo <= pm25_aqi(v) <= hi)
		for v in (5, 20, 45, 100, 200, 400)}
	assert len(seen) == 6, f'only {len(seen)} categories are reachable: {sorted(seen)}'


# --- "best times for outdoor activity" -----------------------------------------------------------

def test_the_window_is_the_cleanest_hours_of_the_day() -> None:
	"""WHO's guidelines are why this is a time of day: exposure "is a product of the pollutant
	concentration and the time over which a person is in contact with that pollutant", and
	concentrations follow "the temporal pattern of operation of outdoor sources (e.g. traffic)".
	Neither the rush hour nor the evening cooking is visible in a daily mean."""
	w = _svc().outdoor_window(_air(120.0), 'Kibera',
		[(6, 40.0), (12, 130.0), (18, 90.0), (21, 40.0)])
	assert w.hours == [6, 21], 'the window is not the cleanest hours'
	assert w.best_aqi == pm25_aqi(40.0)
	assert w.hours == sorted(w.hours)


def test_every_hour_at_the_best_level_is_offered_and_not_just_one() -> None:
	"""A person with a fixed appointment at nine needs to know whether nine is inside the window, and
	a single named hour answers a question they did not ask."""
	w = _svc().outdoor_window(_air(60.0), 'Kibera', [(6, 30.0), (9, 30.0), (15, 80.0)])
	assert w.hours == [6, 9]


def test_the_window_is_ordered_even_when_the_readings_arrive_unordered() -> None:
	"""The hours are a day in the order a day runs, and the series they come from is whatever order
	the caller sent. Left as they arrived, the window reads 21 then 6 — which is a person told to go
	out at nine in the evening and again at six in the morning."""
	w = _svc().outdoor_window(_air(60.0), 'Kibera', [(21, 30.0), (6, 30.0), (14, 90.0)])
	assert w.hours == [6, 21], 'the window followed the order the readings arrived in'


def test_the_advice_says_when_no_hour_is_actually_clean() -> None:
	"""A window offered on a uniformly bad day is a person sent outdoors. The hours are still served
	— the least bad is a real answer — but the advice has to say which it is."""
	bad = _svc().outdoor_window(_air(200.0), 'Kibera', [(6, 180.0), (14, 200.0)])
	assert 'No hour today is clean' in bad.advise
	clean = _svc().outdoor_window(_air(20.0), 'Kibera', [(6, 10.0), (14, 20.0)])
	assert 'fine all day' in clean.advise


def test_a_day_with_no_hourly_readings_gets_an_empty_window_that_says_so() -> None:
	"""An hour named from a single daily figure would be an hour nobody measured — the fabrication
	the section's own Data sources clause is about."""
	g = _svc().air_quality_guidance(_air(120.0), 'Kibera')
	assert g.outdoor.hours == [] and g.outdoor.best_aqi is None
	assert 'No hourly readings' in g.outdoor.advise


def test_a_window_with_hours_and_no_index_is_refused() -> None:
	pydantic = pytest.importorskip('pydantic')
	with pytest.raises(pydantic.ValidationError, match='no index behind it'):
		OutdoorWindow(county='Nairobi', location='Kibera', hours=[6], best_aqi=None, advise='x')


def test_an_out_of_order_window_is_refused() -> None:
	with pytest.raises(pydantic.ValidationError, match='order a day runs'):
		OutdoorWindow(county='Nairobi', location='Kibera', hours=[18, 6], best_aqi=40, advise='x')


def test_a_day_with_no_readings_at_all_is_refused() -> None:
	"""`outdoor_window` with an empty series has nothing to minimise, and returning an empty window
	from it would hide a caller that meant to send readings and sent none."""
	with pytest.raises(AssertionError, match='no hourly readings'):
		_svc().outdoor_window(_air(120.0), 'Kibera', [])


# --- "pollution source information" --------------------------------------------------------------

def test_a_reported_source_is_named_and_an_unreported_one_is_not() -> None:
	"""A monitor reads a concentration and cannot read a source, so the method is exclusion: the
	flags are evidence the caller supplies, and the service names only what it was told."""
	svc = _svc()
	some = svc.pollution_source(_air(), 'Kibera', traffic_nearby=True, household_fuel_use=True)
	assert some.likely == ['road traffic', 'household cooking and heating fuel']
	none = svc.pollution_source(_air(), 'Kibera')
	assert none.likely == [], 'a source was named with no evidence for it'
	assert 'not known' in none.evidence


def test_an_unknown_source_is_an_answer_and_carries_something_to_do() -> None:
	"""A guessed source on a health screen is worse than a blank, so the blank is served — but it is
	not a dead end: an unexplained high reading is the one worth reporting, and the advice says so
	rather than leaving a person with a number and no action."""
	s = _svc().pollution_source(_air(), 'Kibera')
	assert s.advise and 'report' in s.advise.lower()


def test_a_source_report_with_nothing_in_it_is_refused() -> None:
	with pytest.raises(pydantic.ValidationError, match='nothing likely'):
		PollutionSource(county='Nairobi', location='Kibera', likely=[], evidence='', advise='x')


def test_an_unnamed_source_in_the_list_is_refused() -> None:
	with pytest.raises(pydantic.ValidationError, match='unnamed source'):
		PollutionSource(county='Nairobi', location='Kibera', likely=['  '], evidence='x', advise='y')


# --- "mask guidance" -----------------------------------------------------------------------------

def test_mask_guidance_says_what_a_mask_does_not_do() -> None:
	"""WHO's guidelines deliberately do not make this recommendation — individual-level measures are
	"addressed in another document" — so the text is the repo's own, and it has to be honest: a
	cloth mask against PM2.5 is a partial reduction, and guidance implying otherwise has somebody
	standing in traffic smoke feeling safe."""
	alert = _svc().mask_guidance(_air(200.0))
	assert 'N95' in alert and 'cloth' in alert.lower()
	assert 'not a substitute' in alert, 'the mask guidance does not say what a mask does not do'
	assert 'No mask needed' in _svc().mask_guidance(_air(10.0))


# --- the whole answer ----------------------------------------------------------------------------

def test_the_guidance_carries_all_five_features() -> None:
	"""The section's five bullets in one payload, because a person reading the screen acts on all
	five together or on none of them."""
	g = _svc().air_quality_guidance(_air(120.0), 'Kibera', [(6, 40.0), (14, 130.0)],
		traffic_nearby=True)
	assert g.reading.aqi == 184 and g.reading.category == 'unhealthy'
	assert g.advisory and g.mask_guidance
	assert g.outdoor.hours == [6]
	assert g.source.likely == ['road traffic']


def test_the_advisory_is_the_existing_one_and_not_a_second_wording() -> None:
	"""One fact on two surfaces. A second string would be the copy that drifts, and it would drift
	away from the route the mobile catalogue already points at."""
	svc = _svc()
	a = _air(120.0)
	assert svc.air_quality_guidance(a, 'Kibera').advisory == svc.air_alert(a)


def test_the_guidance_carries_the_location_the_section_asks_about() -> None:
	"""The section says "AQI for user's location" and the reading had only a county — tens of
	thousands of people, when the question is about the street a person is standing on."""
	g = _svc().air_quality_guidance(_air(), 'Kibera')
	assert g.location == g.reading.location == g.outdoor.location == g.source.location == 'Kibera'
	assert g.county == 'Nairobi'


# --- the route -----------------------------------------------------------------------------------

def test_the_air_route_serves_the_whole_answer() -> None:
	from afya.service import build_services, create_app
	c = TestClient(create_app(build_services()))
	r = c.post('/environment/air', json={'county': 'Nairobi', 'pm25': 120.0,
		'location': 'Kibera', 'hourly': ['6=40.0', '12=130.0']})
	assert r.status_code == 200, r.text
	out = r.json()
	assert out['reading']['aqi'] == 184 and out['reading']['category'] == 'unhealthy'
	assert out['outdoor']['hours'] == [6]
	assert out['mask_guidance'] and out['source']['evidence']


def test_the_air_route_serves_an_empty_window_without_hourly_readings() -> None:
	from afya.service import build_services, create_app
	c = TestClient(create_app(build_services()))
	r = c.post('/environment/air', json={'county': 'Nairobi', 'pm25': 20.0, 'location': 'Karen'})
	assert r.status_code == 200, r.text
	assert r.json()['outdoor']['hours'] == []


def test_the_air_route_requires_a_location() -> None:
	"""The section asks for the AQI for the user's location and a county is not one. A default would
	serve a reading for a place nobody named."""
	from afya.service import build_services, create_app
	c = TestClient(create_app(build_services()))
	r = c.post('/environment/air', json={'county': 'Nairobi', 'pm25': 20.0})
	assert r.status_code == 422, r.text
