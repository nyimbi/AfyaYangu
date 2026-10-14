"""§ACC-004's "Adaptive sensor sampling rates based on context (charging, stationary, time of day)".

The row was `missing` for one reason and it was not the rate: `BatteryProfile.charging_adaptive` was
a hardcoded `True` and nothing in the tree read a charging state, a motion state or the hour. The
field described a behaviour the module did not have.

Writing the test found the second half. `INTENSITY_SENSORS` held `['fall', 'cough', 'ppg', …]` under
a field called `sensors_enabled`, and those are `SenseKind` *reading* kinds — not one resolved to any
of §13.1's eighteen sensor rows. A screen titled "sensors on" listed six things the app cannot
measure with, and a client switching hardware on by those names switched on nothing.

Both halves are the same defect §COM-103 and §LOC-004 were: every visible part present, the join
absent. Here the join is three tables that already existed — `SenseIngest.kind` → `_INGEST_FEATURE`
→ §13.1's `SensorSpec.primary_features` — and nothing crossed them.
"""
import re

from afya.access.service import (
	ACOUSTIC_DAILY_PCT, CONTEXT_DUTY, CONTEXT_ORDER, INTENSITY_BATTERY, INTENSITY_READINGS,
	INTENSITY_SENSORS, NIGHT_HOURS, AccessService,
)
from afya.access.views import BatteryProfile, SamplingContext
from afya.sensors.service import _INGEST_FEATURE, SENSORS
from afya.sensors.views import SenseKind

FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')


def _svc() -> AccessService:
	return AccessService()


# --- the join the module was missing ------------------------------------------------------

async def test_every_intensity_sensor_is_a_sensor_the_app_has() -> None:
	"""The defect in one assertion. Every entry under `sensors_enabled` must be a §13.1 slug.

	Before this the six entries were `fall`, `cough`, `ppg`, `respiration`, `sleep`, `ambient` and
	none of them was a sensor — so the client that switched hardware on by these names switched on
	nothing, and the settings screen named six measurements the app cannot take.
	"""
	slugs = {spec.slug for spec in SENSORS}
	for level, sensors in INTENSITY_SENSORS.items():
		assert sensors, level
		assert set(sensors) <= slugs, f'{level}: not §13.1 sensors: {sorted(set(sensors) - slugs)}'


async def test_the_sensors_are_the_ones_that_carry_the_reading_kinds() -> None:
	"""The join is derived, not a second list. A sensor is enabled at a level exactly when it carries
	one of that level's reading kinds — so a sensor added to §13.1 for a kind the level collects
	appears here without anyone editing this table."""
	for level, kinds in INTENSITY_READINGS.items():
		wanted = {_INGEST_FEATURE[SenseKind(kind)] for kind in kinds}
		expected = [spec.slug for spec in SENSORS if wanted & set(spec.primary_features)]
		assert INTENSITY_SENSORS[level] == expected, level


async def test_the_profile_carries_the_readings_as_well_as_the_sensors() -> None:
	"""Two lists because they answer different questions: which hardware is on, and what comes back
	from it. A profile carrying only the sensors leaves the client unable to say what it collects."""
	profile = _svc().battery_profile('U1', intensity='maximum')
	assert profile.readings_enabled == INTENSITY_READINGS['maximum']
	assert profile.sensors_enabled == INTENSITY_SENSORS['maximum']
	assert set(profile.readings_enabled) == {k.value for k in SenseKind}


async def test_a_reading_kind_that_names_no_sensor_is_refused_rather_than_served_empty() -> None:
	"""The join asserts it found a sensor. A kind whose feature maps to no §13.1 row would otherwise
	serve an empty list, which reads as "nothing is on" — the silent-zero failure the assert exists
	to prevent. `SenseKind` is a closed enum, so the reachable case is a *known* kind whose feature
	no sensor claims; that is the one exercised here."""
	import afya.access.service as mod
	import afya.sensors.service as sensors

	original = sensors._INGEST_FEATURE[SenseKind.respiration]
	try:
		sensors._INGEST_FEATURE[SenseKind.respiration] = 'SENS-999'
		raised = False
		try:
			mod._sensors_for(['respiration'])
		except AssertionError:
			raised = True
		assert raised, 'a kind that maps to no sensor must not silently yield an empty list'
	finally:
		sensors._INGEST_FEATURE[SenseKind.respiration] = original


# --- the context axis ---------------------------------------------------------------------

async def test_the_rate_moves_with_the_context() -> None:
	"""The whole point of the bullet. `charging_adaptive` was hardcoded `True` while nothing read a
	charging state, so the rate never moved; it moves now, and in the direction the section names."""
	svc = _svc()
	day = svc.battery_profile('U1', intensity='maximum')
	charging = svc.battery_profile('U1', intensity='maximum', context=SamplingContext(charging=True))
	assert charging.sampling_duty > day.sampling_duty, 'charging must raise the rate, not lower it'
	assert charging.estimated_daily_pct > day.estimated_daily_pct


async def test_the_context_order_puts_the_persons_own_choice_first() -> None:
	"""A person who set "do not monitor" gets no monitoring whatever else is true, and a call
	outranks a charger. The order is data, so a context added without a place in it fails the import
	assert rather than being unreachable."""
	assert CONTEXT_ORDER[0] == 'do_not_monitor' and CONTEXT_ORDER[1] == 'on_call'
	assert CONTEXT_ORDER.index('charging') < CONTEXT_ORDER.index('stationary')
	svc = _svc()
	both = svc.battery_profile('U1', context=SamplingContext(do_not_monitor=True, charging=True, on_call=True))
	assert both.context == 'do_not_monitor' and both.sampling_duty == 0.0
	call = svc.battery_profile('U1', context=SamplingContext(on_call=True, charging=True))
	assert call.context == 'on_call' and call.sampling_duty == 0.0


async def test_every_context_has_a_rate_and_a_sentence() -> None:
	"""A context with no sentence renders blank in the settings screen the section asks for; a
	context with no rate is a state the module recognises and does not act on."""
	assert set(CONTEXT_ORDER) == set(CONTEXT_DUTY)
	for key, (duty, reason) in CONTEXT_DUTY.items():
		assert duty >= 0, key
		assert reason and reason.endswith('.'), key
	profile = _svc().battery_profile('U1', context=SamplingContext(hour=3))
	assert profile.context == 'night' and profile.context_reason == CONTEXT_DUTY['night'][1]


async def test_the_night_window_is_the_hours_it_claims() -> None:
	svc = _svc()
	for hour in range(24):
		got = svc.battery_profile('U1', context=SamplingContext(hour=hour)).context
		assert got == ('night' if hour in NIGHT_HOURS else 'day'), hour
	assert 22 in NIGHT_HOURS and 5 in NIGHT_HOURS and 6 not in NIGHT_HOURS


async def test_no_context_at_all_is_the_sections_plain_target() -> None:
	"""A client that sends nothing must get the profile §ACC-004's own <5% target describes — not a
	night rate chosen because the server guessed the hour."""
	svc = _svc()
	plain = svc.battery_profile('U1', intensity='balanced')
	assert plain.context == 'day' and plain.sampling_duty == 1.0
	assert plain.estimated_daily_pct == INTENSITY_BATTERY['balanced']
	assert plain.charging_adaptive is True


async def test_the_daily_budget_is_not_reported_clamped() -> None:
	"""§ACC-004's <5% is a *daily* budget, and sampling faster while charging is exactly the case
	where exceeding it costs nothing. Capping the served figure at 5 would be a lie in the
	reassuring direction: the settings screen would show the budget instead of the drain."""
	svc = _svc()
	hot = svc.battery_profile('U1', intensity='maximum', context=SamplingContext(charging=True))
	assert hot.estimated_daily_pct > 5.0, 'the true cost of charging-adaptive maximum is over budget'
	assert hot.estimated_daily_pct == round(INTENSITY_BATTERY['maximum'] * CONTEXT_DUTY['charging'][0], 2)
	# The base figure — the one the section's target is about — stays under it.
	for intensity, pct in INTENSITY_BATTERY.items():
		assert pct <= 5.0, intensity


async def test_battery_saver_still_wins_over_a_charging_context() -> None:
	"""Battery saver is the person switching things off; charging is the phone's own state. A saver
	that re-enabled sensors because the phone was plugged in would be the app overriding the person."""
	svc = _svc()
	profile = svc.battery_profile('U1', intensity='maximum', battery_saver=True,
	                              context=SamplingContext(charging=True))
	assert profile.sensors_enabled == [] and profile.readings_enabled == []
	assert profile.estimated_daily_pct == 0.4
	# Nothing is sampling, so there is no rate for the charger to scale: a duty of 2.0 here would
	# report 0.8% for a profile with every sensor off.
	assert profile.sampling_duty == 0.0
	assert profile.context_reason == CONTEXT_DUTY['do_not_monitor'][1] or 'Battery saver' in profile.context_reason


async def test_the_acoustic_budget_is_kept_as_the_section_prints_it() -> None:
	"""§14.2's "<2% per day" is a budget for acoustic monitoring alone and §ACC-004's <5% is for
	everything. Both are kept so a reader can see they are different claims about different sets."""
	assert ACOUSTIC_DAILY_PCT == 2.0 < INTENSITY_BATTERY['maximum']


async def test_the_profile_carries_no_spec_feature_code() -> None:
	payload = _svc().battery_profile('U1', context=SamplingContext(charging=True)).model_dump_json()
	assert FEATURE_CODE.search(payload) is None, payload


# --- the front door -----------------------------------------------------------------------

def _client():  # type: ignore[no-untyped-def]
	from fastapi.testclient import TestClient
	from afya.service import build_services, create_app
	return TestClient(create_app(build_services()))


def _citizen(c, subject: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
	r = c.post('/auth/anonymous', json={'subject_ref': subject})
	assert r.status_code == 200, r.text
	return {'authorization': f'Bearer {r.json()["token"]}'}


def test_the_route_serves_the_context_it_was_given() -> None:
	"""The device knows whether it is charging; the server does not. The route takes the state the
	handset reports and answers with the rate that follows — a green unit test says nothing about
	whether a client can reach the behaviour."""
	c = _client()
	h = _citizen(c, 'probe-1')
	plain = c.get('/access/battery', headers=h, params={'subject_ref': 'probe-1', 'intensity': 'maximum'})
	assert plain.status_code == 200, plain.text
	hot = c.get('/access/battery', headers=h,
	            params={'subject_ref': 'probe-1', 'intensity': 'maximum', 'charging': 'true'})
	assert hot.status_code == 200, hot.text
	assert hot.json()['context'] == 'charging'
	assert hot.json()['sampling_duty'] > plain.json()['sampling_duty']
	assert hot.json()['sensors_enabled'] and hot.json()['readings_enabled']
	assert FEATURE_CODE.search(hot.text) is None, hot.text


def test_the_route_defaults_to_the_unadaptive_profile() -> None:
	c = _client()
	h = _citizen(c, 'probe-1')
	body = c.get('/access/battery', headers=h, params={'subject_ref': 'probe-1'}).json()
	assert body['context'] == 'day' and body['sampling_duty'] == 1.0


def test_the_route_refuses_an_unknown_intensity() -> None:
	c = _client()
	h = _citizen(c, 'probe-1')
	r = c.get('/access/battery', headers=h, params={'subject_ref': 'probe-1', 'intensity': 'turbo'})
	assert r.status_code == 422, r.text


def test_the_route_refuses_a_caller_with_no_token() -> None:
	assert _client().get('/access/battery').status_code in (401, 403)


def test_the_catalogue_offers_the_context_fields_and_reaches_the_route() -> None:
	"""A context the catalogue cannot fill is a context no client can send — the behaviour would
	exist and be unreachable, which is how this row stayed missing."""
	from afya.mobile.actions import catalogue
	act = next(a for a in catalogue() if a.id == 'battery_profile')
	assert act.method == 'GET' and act.path == '/access/battery'
	names = {f.name for f in act.fields}
	assert {'charging', 'stationary', 'hour', 'on_call', 'do_not_monitor'} <= names, names
	assert FEATURE_CODE.search(act.model_dump_json()) is None, act.model_dump(mode='json')


def test_the_audit_row_is_carried_and_its_ref_resolves() -> None:
	from afya.content_audit.service import FEATURE_CONTENT
	from afya.refs import resolves

	rows = [r for r in FEATURE_CONTENT if r[0] == 'ACC-004' and r[2].startswith('Adaptive sensor sampling')]
	assert len(rows) == 1
	assert rows[0][3] == 'carried' and resolves(rows[0][4]), rows[0]
