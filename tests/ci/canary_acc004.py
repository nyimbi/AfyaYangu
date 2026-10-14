"""Canaries for tests/ci/test_acc004.py.

§ACC-004's "Adaptive sensor sampling rates based on context (charging, stationary, time of day)" was
absent in a way two other units had already been: every visible part present and the join absent.
`charging_adaptive` was a hardcoded `True` with no referent, and `INTENSITY_SENSORS` held reading
kinds under a field named `sensors_enabled` — not one of which was a §13.1 sensor.

The canaries are the cheap ways to make an adaptive rate that is not one:

* **#1** puts the reading kinds back under `sensors_enabled`. This is the defect exactly as it was
  found, and it is worth reading because it *looked* right: the six names were plausible sensors,
  they were simply not the app's.
* **#4** derives the sensors from the wrong table, so the join exists and points somewhere else.
* **#6** drops the person's own "do not monitor" out of first place, so a setting they made is
  overridden by the phone's charging state.
* **#9** clamps the served figure at the section's budget. This is the failure that looks like
  compliance: the settings screen shows 5% while the profile is costing 9.2%.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script. The `__pycache__`
purge after each write is load-bearing for the reason `canary_inf001.py` documents.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
S = ROOT / 'src/afya/access/service.py'
V = ROOT / 'src/afya/access/views.py'
G = ROOT / 'src/afya/service.py'
M = ROOT / 'src/afya/mobile/actions.py'

CANARIES = [
	# 1. The reading kinds go back under `sensors_enabled` — the defect as found. The screen then
	#    lists six names that are not §13.1 sensors and the client switches on nothing. Caught by the
	#    profile test rather than the table test: the table is still correct, it is the profile that
	#    serves the wrong list.
	('the reading kinds are served as sensors', S,
	 "		sensors = [] if battery_saver else list(INTENSITY_SENSORS[intensity])",
	 "		sensors = [] if battery_saver else list(INTENSITY_READINGS[intensity])",
	 'test_the_profile_carries_the_readings_as_well_as_the_sensors'),

	# 2. The join is keyed on one kind instead of the level's kinds, so every level enables the same
	#    sensors — the level and the hardware become two independent things again, which is the shape
	#    the whole unit was about.
	('the join ignores the level it is for', S,
	 "	wanted = {_INGEST_FEATURE[SenseKind(kind)] for kind in kinds}",
	 "	wanted = {_INGEST_FEATURE[SenseKind('fall')] for kind in kinds}",
	 'test_the_sensors_are_the_ones_that_carry_the_reading_kinds'),

	# 3. The profile stops carrying what it collects, so a client can say which hardware is on and
	#    not what comes back from it. The mutation is in the service, not the model: a `= []` default
	#    on the field changes nothing while the service still passes it, which is a no-op canary.
	('the profile loses the reading kinds', S,
	 "			readings_enabled=readings, estimated_daily_pct=scaled,",
	 "			readings_enabled=[], estimated_daily_pct=scaled,",
	 'test_the_profile_carries_the_readings_as_well_as_the_sensors'),

	# 4. The join returns a sensor per kind rather than per feature, so a level's sensor list grows
	#    duplicates and stops matching §13.1's own order.
	('the join returns a sensor per kind', S,
	 "	slugs = [spec.slug for spec in SENSORS if wanted & set(spec.primary_features)]",
	 "	slugs = [spec.slug for spec in SENSORS for _ in kinds if wanted & set(spec.primary_features)]",
	 'test_the_sensors_are_the_ones_that_carry_the_reading_kinds'),

	# 5. The join answers an empty list instead of refusing, so an intensity that maps to no sensor
	#    serves "nothing is on" — the silent zero.
	('a kind with no sensor yields an empty list', S,
	 "	assert slugs, f'no §13.1 sensor carries {kinds}'",
	 "	assert True, f'no §13.1 sensor carries {kinds}'",
	 'test_a_reading_kind_that_names_no_sensor_is_refused_rather_than_served_empty'),

	# 6. The person's own "do not monitor" drops out of first place, so the phone's charging state
	#    overrides a setting they made — the app arguing with its user about their own phone.
	('do not monitor is not checked first', S,
	 "	'do_not_monitor', 'on_call', 'charging', 'stationary', 'night', 'day',",
	 "	'charging', 'on_call', 'do_not_monitor', 'stationary', 'night', 'day',",
	 'test_the_context_order_puts_the_persons_own_choice_first'),

	# 7. The context is computed and never applied, so the rate never moves — which is exactly what
	#    the hardcoded `charging_adaptive = True` did.
	('the rate does not move with the context', S,
	 "		duty, reason = CONTEXT_DUTY[key]",
	 "		duty, reason = CONTEXT_DUTY['day']",
	 'test_the_rate_moves_with_the_context'),

	# 8. Night is a window the module recognises and does not act on: the hours fall through to the
	#    day rate and the person is told nothing changed.
	('the night window is not applied', S,
	 "			'night': ctx.hour in NIGHT_HOURS,",
	 "			'night': False,",
	 'test_the_night_window_is_the_hours_it_claims'),

	# 9. The served figure is clamped at the section's budget, so the settings screen reports 5%
	#    while the profile costs 9.2% — a lie in the reassuring direction, and the one that looks
	#    like compliance.
	('the daily cost is reported clamped', S,
	 "		scaled = pct if battery_saver else round(pct * duty, 2)",
	 "		scaled = min(pct if battery_saver else round(pct * duty, 2), 5.0)",
	 'test_the_daily_budget_is_not_reported_clamped'),

	# 10. The saver is overridden by the phone's own state, so plugging in re-enables sensors the
	#     person switched off.
	('battery saver loses to the charger', S,
	 "		readings = [] if battery_saver else list(INTENSITY_READINGS[intensity])",
	 "		readings = [] if battery_saver and duty == 0.0 else list(INTENSITY_READINGS[intensity])",
	 'test_battery_saver_still_wins_over_a_charging_context'),

	# 11. A context with no sentence renders blank in the settings screen the section asks for.
	('a context has no sentence', S,
	 "	'charging': (2.0, 'Sampling runs faster while the phone is charging, because the battery is not the constraint.'),",
	 "	'charging': (2.0, ''),",
	 'test_every_context_has_a_rate_and_a_sentence'),

	# 12. A client that sends nothing is served a rate chosen for a context it never reported.
	('no context is served an adaptive rate', S,
	 "		if ctx is None:\n			return 'day'",
	 "		if ctx is None:\n			return 'charging'",
	 'test_no_context_at_all_is_the_sections_plain_target'),

	# 13. The route ignores the state the handset reports, so the behaviour exists and no client can
	#     reach it.
	('the route ignores the context it is given', G,
	 "		ctx = SamplingContext(charging=charging, stationary=stationary, hour=hour,\n		                      on_call=on_call, do_not_monitor=do_not_monitor)",
	 "		ctx = None",
	 'test_the_route_serves_the_context_it_was_given'),

	# 14. The catalogue stops offering the context fields, so no form can fill what the route reads.
	('the catalogue drops the context fields', M,
	 "_f('charging', 'On charge?', 'bool'), _f('stationary', 'Phone still?', 'bool'), _f('hour', 'Hour of the day', 'int'), _f('on_call', 'On a call?', 'bool'), _f('do_not_monitor', 'Pause monitoring?', 'bool')",
	 "_f('charging', 'On charge?', 'bool')",
	 'test_the_catalogue_offers_the_context_fields_and_reaches_the_route'),

	# 15. The two §ACC-004 budgets collapse into one, so a reader cannot see that §14.2's <2% and the
	#     section's <5% are different claims about different sets of sensors.
	('the two budgets collapse into one', S,
	 "ACOUSTIC_DAILY_PCT = 2.0",
	 "ACOUSTIC_DAILY_PCT = 5.0",
	 'test_the_acoustic_budget_is_kept_as_the_section_prints_it'),
]


def _node(canary_node: str) -> str:
	return canary_node if '/' in canary_node else f'tests/ci/test_acc004.py::{canary_node}'


_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only',
	'tests/ci/test_acc004.py'],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_acc004.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	# See the module docstring: a same-second write of the same size reuses the previous canary's
	# bytecode, and the canary then tests code it never mutated. Purged for the file just written.
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', _node(node)],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
	print(f'{"CAUGHT " if caught else "MISSED "} {name}')
	if not caught:
		failures.append(name)
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
