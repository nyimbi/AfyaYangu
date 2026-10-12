import pytest
from pydantic import ValidationError
from typing import Any

from afya.registry.service import FeatureRegistry, Tier4Activation
from afya.sensors.service import HANDLING, SENSORS, SensorService, cough_band, ppg_band, resp_band
from afya.sensors.views import (
	Availability, BatteryCost, SenseIngest, SenseKind, Sensitivity, SensorSpec,
)


@pytest.fixture
def svc() -> SensorService:
	return SensorService(FeatureRegistry())


def test_respiration_bands() -> None:
	assert resp_band(16).band == 'normal'
	out = resp_band(9.0)
	assert out.anomaly and out.band == 'alert' and '12-25' in out.detail


def test_cough_bands() -> None:
	assert cough_band(5).band == 'normal'
	assert cough_band(18).band == 'watch'
	assert cough_band(31).band == 'alert'


def test_ppg_bands() -> None:
	assert ppg_band(72).band == 'normal'
	assert ppg_band(50).band == 'watch'
	assert ppg_band(140).band == 'alert'


async def test_fall_not_tier4_gated(svc: SensorService) -> None:
	v = await svc.ingest(SenseIngest(kind=SenseKind.fall, subject_ref='U1', value=5.5, county='Nairobi'))
	assert v.anomaly


async def test_tier4_dormant_rejects_respiration(svc: SensorService) -> None:
	with pytest.raises(PermissionError):
		await svc.ingest(SenseIngest(kind=SenseKind.respiration, subject_ref='U1', value=30.0, county='Nairobi'))


async def test_tier4_active_accepts_respiration() -> None:
	reg = FeatureRegistry(Tier4Activation(authorized_by_pheoc=True, dpia_review_id='r1', flag_enabled=True))
	svc = SensorService(reg)
	v = await svc.ingest(SenseIngest(kind=SenseKind.respiration, subject_ref='U1', value=30.0, county='Nairobi'))
	assert v.anomaly and v.band == 'alert'
	assert len(svc.history()) == 1


def test_raw_fields_structurally_rejected() -> None:
	from pydantic import ValidationError
	with pytest.raises(ValidationError):
		SenseIngest.model_validate({'kind': 'respiration', 'subject_ref': 'U1', 'value': 16, 'county': 'N', 'depth': [1.0, 2.0]})

def test_breath_rate_estimation() -> None:
	import math as _m
	from afya.surveillance.service import estimate_breath_rate
	fps = 30.0
	# 16 bpm -> 3.75 s period over 8 s
	series = [1.0 * _m.sin(2 * 3.14159 * 16 / 60 * t / fps) for t in range(240)]
	rate = estimate_breath_rate(series, fps)
	assert 13 <= rate <= 19
	series_fast = [1.0 * _m.sin(2 * 3.14159 * 24 / 60 * t / fps) for t in range(240)]
	rate_fast = estimate_breath_rate(series_fast, fps)
	assert 20 <= rate_fast <= 28


# --- §13.1 the capability matrix ------------------------------------------------------------

def test_the_matrix_has_every_spec_row() -> None:
	"""§13.1 is eighteen rows. Each carries the availability §13.1 gives it on both platforms, so a
	row that gained a capability nobody can use would show up here."""
	assert len(SENSORS) == 18
	assert len({s.slug for s in SENSORS}) == 18, 'sensor slugs must be unique'
	by_slug = {s.slug: s for s in SENSORS}
	assert by_slug['gps'].android is Availability.all and by_slug['gps'].ios is Availability.all
	assert by_slug['lidar'].android is Availability.select, '§13.1: select Android flagships only'
	assert by_slug['lidar'].ios is Availability.some, '§13.1: iPhone Pro / iPad Pro'
	assert by_slug['thermometer'].ios is Availability.none, '§13.1 gives iOS no thermometer'
	assert by_slug['heart_rate'].ios is Availability.none


def test_the_sensitivity_column_is_carried_per_sensor() -> None:
	"""The column §17.2's minimisation rule is enforced from. §13.1 marks location, the microphone
	and the rear camera High; Bluetooth and the front camera Medium; the rest Low."""
	by_slug = {s.slug: s for s in SENSORS}
	high = sorted(s.slug for s in SENSORS if s.sensitivity is Sensitivity.high)
	assert high == ['camera_rear', 'gps', 'microphone']
	assert by_slug['bluetooth'].sensitivity is Sensitivity.medium
	assert by_slug['camera_front'].sensitivity is Sensitivity.medium
	assert by_slug['lidar'].sensitivity is Sensitivity.low and by_slug['lidar'].derived_only


def test_a_derived_only_sensor_cannot_be_high_sensitivity() -> None:
	"""Canary at the model. §13.1 writes LiDAR's class as "Low (derived only)" — if the raw stream is
	discarded immediately there is nothing left but the derived metric, so a row claiming both
	derived-only and High is describing two different things."""
	with pytest.raises(ValidationError, match='discards raw data'):
		SensorSpec(slug='x', name='X', android=Availability.all, ios=Availability.all, used_for='y',
		           sensitivity=Sensitivity.high, derived_only=True, battery=BatteryCost.low)


def test_a_retention_cap_on_a_low_sensitivity_sensor_is_refused() -> None:
	"""§14.1/LOC-003 gives location a 21-day rolling window because it is High. A cap on a sensor
	that carries nothing about a person would be a rule with nothing to protect."""
	with pytest.raises(ValidationError, match='carries a retention cap'):
		SensorSpec(slug='x', name='X', android=Availability.all, ios=Availability.all, used_for='y',
		           sensitivity=Sensitivity.low, battery=BatteryCost.low, retention_days=21)


def test_no_class_ever_permits_retaining_a_raw_stream() -> None:
	"""§17.2: "Raw sensor data is never retained." SEC-002: it never leaves the device. The rule is
	stated once per class so it is computed rather than restated, and every class must say never."""
	svc = SensorService(FeatureRegistry())
	assert svc.raw_streams_retained() == []
	assert all(h.raw_may_be_retained is False for h in HANDLING)
	assert len(HANDLING) == 3, 'one handling row per sensitivity class'


def test_high_sensitivity_capture_needs_consent_and_low_does_not() -> None:
	"""§17.4 consent: asking a user to consent to a barometer reading is consent theatre, and not
	asking about their location is the failure §23's privacy risks name."""
	svc = SensorService(FeatureRegistry())
	assert svc.handling(Sensitivity.high).capture_requires_consent is True
	assert svc.handling(Sensitivity.medium).capture_requires_consent is True
	assert svc.handling(Sensitivity.low).capture_requires_consent is False


def test_every_absence_prone_sensor_has_a_fallback() -> None:
	"""§13.1 and §13.2 are one promise: a sensor that can be absent and has no fallback excludes a
	user, which is the principle §13.2 states outright. The two tables live in different modules,
	which is exactly how they can drift."""
	svc = SensorService(FeatureRegistry())
	assert svc.absent_on('android') and svc.absent_on('ios')
	assert svc.missing_fallbacks() == [], 'a §13.1 sensor with no §13.2 fallback'


def test_the_fallback_cross_check_can_actually_report_a_gap() -> None:
	"""Canary for the cross-check: it is only ever seen returning [], which is what a check that
	cannot fail looks like. Drive it with a sensor that carries a feature, can be absent, and is
	named by neither §13.2 nor the alias table — the shape it is meant to catch."""
	from afya.access.service import SENSOR_FALLBACKS
	orphan = SensorSpec(slug='spectrometer', name='Spectrometer', android=Availability.rare,
	                    ios=Availability.none, primary_features=['SENS-099'], used_for='x',
	                    sensitivity=Sensitivity.medium, battery=BatteryCost.low)
	patched = SensorService(FeatureRegistry())
	import afya.sensors.service as mod
	original = mod.SENSORS
	mod.SENSORS = (*original, orphan)
	try:
		assert patched.missing_fallbacks() == ['spectrometer']
	finally:
		mod.SENSORS = original
	# And the real table is clean, so the canary above is what makes the [] meaningful.
	assert patched.missing_fallbacks() == [] and SENSOR_FALLBACKS


def test_an_enhancement_only_sensor_is_not_asked_for_a_fallback() -> None:
	"""§14.8 reaches SENS-008 through five sensors and names the thermometer "where available"; the
	magnetometer carries no feature at all. Losing either costs an enhancement, not a path, so
	§13.2's principle asks nothing of them — which is why they are marked rather than given a
	fabricated fallback."""
	by_slug = {s.slug: s for s in SENSORS}
	assert by_slug['magnetometer'].enhancement_only and by_slug['barometer'].enhancement_only
	assert by_slug['heart_rate'].enhancement_only and by_slug['usb_otg'].enhancement_only
	assert by_slug['magnetometer'].primary_features == [], 'the magnetometer carries no feature'
	# The carriers are not marked: losing one of these removes a path.
	for slug in ('lidar', 'microphone', 'gyroscope', 'gps', 'bluetooth', 'nfc', 'camera_rear', 'thermometer'):
		assert by_slug[slug].enhancement_only is False, f'{slug} is a carrier, not an enhancement'


def test_every_sensor_row_cites_a_registered_feature() -> None:
	"""A sensor row citing a feature the registry does not carry describes hardware bought for a
	capability nobody built."""
	svc = SensorService(FeatureRegistry())
	assert svc.unregistered_sensor_features() == []
	assert any(s.primary_features for s in SENSORS), 'most rows name the features they carry'
	# The negative direction, so the check is not merely a list that always comes back empty.
	with pytest.raises(AssertionError):
		svc.sensor('teleporter')


def test_capabilities_are_served_without_a_spec_code() -> None:
	"""A code may not reach a screen, and the capability list is a screen. The ids stay in
	`primary_features`, which is deliberately not serialised."""
	rows = SensorService(FeatureRegistry()).capabilities()
	assert len(rows) == 18
	assert all('SENS-001' not in str(r) and 'primary_features' not in r for r in rows)
	gps = next(r for r in rows if r['sensor'] == 'gps')
	assert gps['used_for'] == 'Finding care, risk alerts, emergency location'
	assert gps['raw_retained'] is False and gps['needs_consent'] is True
	assert gps['retention_days'] == 21
	assert all(r['raw_retained'] is False for r in rows), 'no sensor may report a retained raw stream'


def test_the_served_matrix_prints_the_sections_words_not_the_enum() -> None:
	"""A user deciding whether the app suits their handset reads this. The enum cannot tell "Very
	rare" from "Rare" or "Limited" from "Some", so serving it would answer "is my phone supported?"
	with a value that overstates or understates §13.1 in exactly the three places the section
	distinguishes. The normalised answer stays beside it, under a name that says what it is for."""
	from afya.sensors.service import SPEC_AVAILABILITY
	rows = {r['sensor']: r for r in SensorService(FeatureRegistry()).capabilities()}
	for slug, _, android, ios in SPEC_AVAILABILITY:
		assert rows[slug]['android'] == android, f'{slug} android cell'
		assert rows[slug]['ios'] == ios, f'{slug} ios cell'
	# The three that would have been lost, named on the wire.
	assert rows['thermometer']['android'] == 'Very rare'
	assert rows['usb_otg']['ios'] == 'Limited'
	assert rows['lidar']['ios'] == 'iPhone Pro / iPad Pro'
	# And the normalised form is still there, labelled for what it answers.
	assert rows['thermometer']['android_availability'] == 'rare'
	assert rows['thermometer']['absence_prone'] is True
	assert rows['accelerometer']['absence_prone'] is False, 'the accelerometer is on every device'


def test_a_raw_field_name_is_refused_by_name() -> None:
	"""The guard that replaced a dead one. `guard_raw` asserted `not RAW_FORBIDDEN` on a non-empty
	tuple — always false, so it raised whenever called, and nothing called it. `extra='forbid'`
	already rejects the key; this makes the refusal say why, which is the §17.2 reason."""
	with pytest.raises(ValidationError, match='raw sensor fields may not be ingested'):
		SenseIngest.model_validate({'kind': 'respiration', 'subject_ref': 'U1', 'value': 16,
		                            'county': 'N', 'audio': [0.1]})
	# And it does not fire on the legitimate payload.
	ok = SenseIngest(kind=SenseKind.respiration, subject_ref='U1', value=16.0, county='Nairobi')
	assert ok.value == 16.0


# --- routes ---------------------------------------------------------------------------------

def _auditor_app() -> tuple[Any, dict[str, str]]:
	from afya.privacy.views import RBACRole
	from afya.service import build_services, create_app
	svc = build_services()
	auth: Any = svc['auth']
	tok = auth.provision_staff('sens-aud', RBACRole.auditor, registrar='MoH ops').access_token
	return create_app(svc), {'authorization': f'Bearer {tok}'}


async def test_the_matrix_is_public_and_the_coverage_view_is_evidence() -> None:
	"""The matrix names no person, so it is readable by anyone deciding whether the app suits their
	handset. The coverage view is evidence about the build and takes the auditor's scope."""
	import httpx
	app, h = _auditor_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		matrix = (await c.get('/sensors/capabilities')).json()
		assert len(matrix['sensors']) == 18 and set(matrix['platforms']) == {'android', 'ios'}
		assert 'thermometer' in matrix['platforms']['ios'], 'iOS has no thermometer in §13.1'
		assert (await c.get('/sensors/coverage')).status_code in (401, 403)
		coverage = (await c.get('/sensors/coverage', headers=h)).json()
		assert coverage['missing_fallbacks'] == [] and coverage['raw_streams_retained'] == []
		assert coverage['sensor_count'] == 18


async def test_a_sysadmin_is_refused_the_evidence_view() -> None:
	"""§17.4 splits the operator scopes: a sysadmin reads `infrastructure`, an auditor reads
	`audit_logs`. Every read in this family is evidence, so the sysadmin is refused."""
	import httpx
	from afya.privacy.views import RBACRole
	from afya.service import build_services, create_app
	svc = build_services()
	auth: Any = svc['auth']
	sys_tok = auth.provision_staff('sens-sys', RBACRole.sysadmin, registrar='MoH ops').access_token
	app = create_app(svc)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		assert (await c.get('/sensors/coverage', headers={'authorization': f'Bearer {sys_tok}'})).status_code == 403


# --- §14.9 SENS-009 external device provenance -----------------------------------------------

async def test_a_paired_device_is_the_only_route_to_clinical_grade(svc: SensorService) -> None:
	"""§14.9's value is the pairing: a device "converts consumer measurements into clinical-grade
	data, improving triage accuracy". A class claiming clinical grade with no device behind it is
	exactly what the section exists to distinguish from a hand-entered number."""
	from afya.sensors.service import SOURCES, source_class
	from afya.sensors.views import MeasurementSource, SourceClass
	assert sorted(s.source.value for s in SOURCES if s.clinical_grade) == ['ble_device', 'facility', 'usb_otg']
	assert source_class(MeasurementSource.manual).clinical_grade is False
	assert source_class(MeasurementSource.manual).patient_entered is True
	with pytest.raises(ValidationError, match='clinical grade without a paired device'):
		SourceClass(source=MeasurementSource.manual, label='x', clinical_grade=True,
		            patient_entered=False, paired_device=False, note='y')
	assert svc.clinical_grade_sources() == ['ble_device', 'facility', 'usb_otg']  # sorted


async def test_a_reading_cannot_be_both_patient_entered_and_device_measured() -> None:
	from afya.sensors.views import MeasurementSource, SourceClass
	with pytest.raises(ValidationError, match='both patient-entered and device-measured'):
		SourceClass(source=MeasurementSource.manual, label='x', clinical_grade=False,
		            patient_entered=True, paired_device=True, note='y')


async def test_the_readings_section_14_9_names_carry_their_provenance(svc: SensorService) -> None:
	"""§14.9 says the data flows into the health wallet and the monitoring diary. Those are the
	readings a triage decision is made on, so those are the ones that must say where they came
	from — a checkable claim rather than a sentence about integration."""
	gap = svc.external_device_gap()
	assert gap.unprovenanced_readings == [], gap
	assert set(gap.readings_carrying_provenance) == {'BPReading', 'GlucoseReading', 'MonitoringDay'}
	assert all(gap.readings_carrying_provenance.values())


async def test_a_cuff_reading_and_a_typed_one_are_distinguishable() -> None:
	"""The whole point: before this both were the same row and §14.9's improvement had nowhere to
	appear. Default is manual — an unstated source is a person's number, not a device's."""
	from afya.chronic.views import BPReading, GlucoseReading
	from afya.monitoring.views import MonitoringDay
	from afya.sensors.views import MeasurementSource
	typed = BPReading(subject_ref='U1', systolic=150, diastolic=95)
	cuffed = BPReading(subject_ref='U1', systolic=150, diastolic=95, source=MeasurementSource.ble_device)
	assert typed.stage == cuffed.stage == 'high'
	assert typed.clinical_grade is False and cuffed.source.value == 'ble_device'
	assert GlucoseReading(subject_ref='U1', mmol_l=6.0).source.value == 'manual', 'default is a person'
	day = MonitoringDay(entry_id='MON-ABCD1234', subject_ref='U1', day=1, temperature_c=38.4)
	assert day.source is MeasurementSource.manual
	assert MonitoringDay(entry_id='MON-ABCD1234', subject_ref='U1', day=1, temperature_c=38.4,
	                     source=MeasurementSource.ble_device).source is MeasurementSource.ble_device


async def test_the_fever_verdict_says_whether_a_device_measured_it() -> None:
	"""The escalation fires on the number either way, so the difference is only visible if the
	verdict carries it. A reader deciding how much to trust a fever needs it there."""
	from afya.monitoring.service import MonitoringService
	from afya.monitoring.views import MonitoringDay
	from afya.sensors.views import MeasurementSource
	svc = MonitoringService()
	svc.enrol('U1')
	typed = await svc.log_day(MonitoringDay(entry_id='MON-AAAA1111', subject_ref='U1', day=1, temperature_c=38.5))
	paired = await svc.log_day(MonitoringDay(entry_id='MON-BBBB2222', subject_ref='U1', day=2,
	                                         temperature_c=38.5, source=MeasurementSource.ble_device))
	assert typed.escalate is paired.escalate is True
	assert typed.clinical_grade is False and paired.clinical_grade is True
	assert paired.reading_source.value == 'ble_device'


async def test_a_provenance_class_carries_no_spec_code(svc: SensorService) -> None:
	import re
	body = str(svc.external_device_gap())
	assert re.search(r'\b(?:SENS|SEC|ACC|REC|MON)-\d{3}\b', body) is None, 'a spec code reached a payload'


# --- §14 accuracy statements and the disclosure §14.5 makes an ethical requirement -----------

async def test_every_sense_kind_states_its_accuracy_and_its_limits() -> None:
	"""§14 states an accuracy figure and a limitation list for each capability. §14.5 is explicit
	that disclosing them is "an ethical requirement, not an optional refinement", so a capability
	with no stated limitation is the thing the section forbids."""
	from afya.sensors.service import ACCURACY
	from afya.sensors.views import SenseKind
	assert {a.kind for a in ACCURACY} == set(SenseKind)
	for a in ACCURACY:
		assert a.stated_accuracy and a.limitations and a.disclosure, a.kind
		assert a.disclosure.endswith('.'), a.kind


async def test_the_bias_disclosure_is_required_where_the_spec_requires_it(svc: SensorService) -> None:
	"""§14.5: "PPG accuracy varies with skin pigmentation … the app must disclose known accuracy
	limitations." The row must carry the limitation, not merely a flag saying one is owed."""
	from afya.sensors.service import ACCURACY
	from afya.sensors.views import AccuracyClaim, SenseKind
	ppg = next(a for a in ACCURACY if a.kind is SenseKind.ppg)
	assert ppg.bias_disclosure_required is True
	assert any('skin' in x.lower() for x in ppg.limitations)
	assert 'darker skin' in ppg.disclosure
	assert svc.undisclosed_limitations() == []
	with pytest.raises(ValidationError, match='states no skin-tone limitation'):
		AccuracyClaim(kind=SenseKind.ppg, capability='x', stated_accuracy='y',
		              limitations=['varies by device'], disclosure='z.', not_diagnostic=True,
		              bias_disclosure_required=True)


async def test_signal_quality_gates_the_reading() -> None:
	"""§14.5's own hedge is "blood oxygen saturation — where signal quality permits". Nothing read
	`SenseIngest.quality` before, so a reading taken through a bad signal was reported as a reading.
	Below the floor it is not reported as one at all."""
	from afya.registry.service import FeatureRegistry
	from afya.sensors.views import Confidence, SenseIngest, SenseKind
	svc = SensorService(FeatureRegistry())
	async def at(q: float):  # noqa: ANN202
		return await svc.qualified_verdict(SenseIngest(kind=SenseKind.ppg, subject_ref='U1', value=72,
		                                               quality=q, county='Nairobi'))
	assert (await at(0.9)).confidence is Confidence.good
	low = await at(0.6)
	assert low.confidence is Confidence.low_quality and 'rough guide' in low.disclosure
	unusable = await at(0.3)
	assert unusable.confidence is Confidence.not_available
	assert 'not clear enough to use' in unusable.disclosure
	assert 'An estimate only' not in unusable.disclosure, 'an unusable reading is not offered as an estimate'


async def test_an_anomaly_carries_the_clinician_prompt_and_the_limits() -> None:
	"""A band on its own is a number. An out-of-range reading on a not-diagnostic capability has to
	say both that it is not a diagnosis and that a clinician is the next step."""
	from afya.registry.service import FeatureRegistry, Tier4Activation
	from afya.sensors.views import SenseIngest, SenseKind
	# Cough sensing is Tier 4, so the outbreak event has to be open before it can be read at all.
	reg = FeatureRegistry(Tier4Activation(authorized_by_pheoc=True, dpia_review_id='r1', flag_enabled=True))
	svc = SensorService(reg)
	out = await svc.qualified_verdict(SenseIngest(kind=SenseKind.cough, subject_ref='U1', value=40,
	                                              quality=0.9, county='Nairobi'))
	assert out.verdict.anomaly is True and out.not_diagnostic is True and out.seek_clinician is True
	assert any('cannot distinguish' in x for x in out.limitations)
	calm = await svc.qualified_verdict(SenseIngest(kind=SenseKind.cough, subject_ref='U1', value=4,
	                                               quality=0.9, county='Nairobi'))
	assert calm.seek_clinician is False


async def test_the_accuracy_surface_serves_the_disclosure_without_a_spec_code() -> None:
	import httpx
	import re
	from afya.service import create_app
	app = create_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		out = (await c.get('/sensors/accuracy')).json()
		assert len(out['claims']) == 6 and out['undisclosed_limitations'] == []
		body = str(out)
		assert re.search(r'\b(?:SENS|SEC|ACC|REC|MON|LOC|COM|ALT|AI|CHAN|INF|TRI|FND|MED|EMG)-\d{3}\b', body) is None


async def test_the_ingest_route_returns_the_disclosure_not_just_the_band() -> None:
	import httpx
	from afya.service import build_services, create_app
	from afya.registry.service import Tier4Activation
	services = build_services()
	# Open the outbreak event so a Tier-4 capability can be read; the disclosure is the same
	# question either way, and this keeps the test about the disclosure.
	services["registry"].activate(Tier4Activation(  # type: ignore[attr-defined]
		authorized_by_pheoc=True, dpia_review_id='r1', flag_enabled=True))
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		token = (await c.post('/auth/anonymous', json={'subject_ref': 'U1'})).json()['token']
		r = await c.post('/sensors/ingest', headers={'authorization': f'Bearer {token}'}, json={
			'kind': 'cough', 'subject_ref': 'U1', 'value': 40, 'quality': 0.9, 'county': 'Nairobi'})
		out = r.json()
		assert r.status_code == 200, out
		assert out['verdict']['band'] == 'alert'
		assert out['disclosure'] and out['limitations'] and out['confidence'] == 'good'
		assert out['seek_clinician'] is True


# --- §13.1 against the spec's own table -----------------------------------------------------

def _spec_13_1_rows() -> list[list[str]]:
	"""§13.1's inventory, read out of the spec so a revision fails here rather than passing."""
	from pathlib import Path
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	section = text.split('### 13.1 Full Sensor Inventory', 1)[1].split('### 13.2', 1)[0]
	rows: list[list[str]] = []
	for line in section.splitlines():
		if not line.startswith('|') or set(line) <= set('|-: '):
			continue
		cells = [c.strip().replace('**', '') for c in line.strip('|').split('|')]
		if len(cells) != 6 or cells[0] == 'Sensor':
			continue
		rows.append(cells)
	return rows


def test_the_matrix_is_the_sections_rows_in_its_own_words() -> None:
	"""§13.1's row names and Android/iOS cells are carried verbatim, not merely normalised.

	The normalisation loses information the section carries — "Rare" and "Very rare" both become
	`rare`, "Some", "iPhone Pro / iPad Pro" and "Limited" all become `some` — so a check that read
	only the enum would pass a table whose cells had been rewritten to any of the synonyms."""
	from afya.sensors.service import AVAILABILITY_SPELLINGS, SPEC_AVAILABILITY
	spec = _spec_13_1_rows()
	assert len(spec) == 18, f'the section names {len(spec)} sensors'
	assert [name for _, name, _, _ in SPEC_AVAILABILITY] == [r[0] for r in spec]
	assert [(a, i) for _, _, a, i in SPEC_AVAILABILITY] == [(r[1], r[2]) for r in spec]
	# And every spelling the section uses is one the map knows, so a tenth fails rather than
	# normalising into a neighbour.
	for _, _, android, ios in SPEC_AVAILABILITY:
		assert android in AVAILABILITY_SPELLINGS and ios in AVAILABILITY_SPELLINGS


def test_the_normalised_availability_agrees_with_the_sections_words() -> None:
	"""The map is what turns the section's prose into the enum the fallback predicate reads. If the
	two disagree, §13.2's "every feature must degrade gracefully" is being applied to a different
	table than the one §13.1 prints."""
	from afya.sensors.service import AVAILABILITY_SPELLINGS, SPEC_AVAILABILITY
	by_slug = {s.slug: s for s in SENSORS}
	for slug, _, android, ios in SPEC_AVAILABILITY:
		assert by_slug[slug].android is AVAILABILITY_SPELLINGS[android], f'{slug} android'
		assert by_slug[slug].ios is AVAILABILITY_SPELLINGS[ios], f'{slug} ios'


def test_the_enum_cannot_hold_every_spelling_and_that_is_recorded() -> None:
	"""The finding this unit exists to make visible: §13.1 writes nine Android/iOS strings and the
	enum has six members, so three collapses happen. They are sound for `can_be_absent` — `all` is
	the only value that is not absence-prone, and no spelling collapses *onto* `all` — but a client
	printing the matrix must read `SPEC_AVAILABILITY`, not the enum, or it will tell a user their
	device is fine when the section said "Limited"."""
	from afya.sensors.service import AVAILABILITY_SPELLINGS, SPEC_AVAILABILITY
	spellings = {s for _, _, a, i in SPEC_AVAILABILITY for s in (a, i)}
	assert len(spellings) == 9, f'§13.1 uses {len(spellings)} spellings: {sorted(spellings)}'
	assert set(AVAILABILITY_SPELLINGS) == spellings, 'the map and the section must name the same strings'
	assert len(set(AVAILABILITY_SPELLINGS.values())) == 6, 'six enum members for nine spellings'
	# The three collapses, named rather than counted: three spellings for `some`, two for `rare`.
	assert sorted(sp for sp, v in AVAILABILITY_SPELLINGS.items()
	              if v is Availability.some) == ['Limited', 'Some', 'iPhone Pro / iPad Pro']
	assert sorted(sp for sp, v in AVAILABILITY_SPELLINGS.items()
	              if v is Availability.rare) == ['Rare', 'Very rare']
	# The collapse never crosses the absence boundary, which is what makes it safe for §13.2: `All`
	# is the only spelling that maps to `all`, so no absence-prone cell can read as universal.
	assert {sp for sp, v in AVAILABILITY_SPELLINGS.items() if v is Availability.all} == {'All'}
	# And the one that would mislead a person is named: USB/OTG's iOS cell is "Limited", not "Some".
	assert dict((s, (a, i)) for s, _, a, i in SPEC_AVAILABILITY)['usb_otg'] == ('Most', 'Limited')
	assert AVAILABILITY_SPELLINGS['Limited'] is Availability.some


def test_every_feature_id_the_section_prints_is_carried() -> None:
	"""§13.1's Primary Features column, ids only. A sensor row citing a feature the section does not
	name is a row that gained a capability on its own authority; one dropping an id loses a path.

	The comparison is exact in both directions, with the additions §13.1's cell cannot supply named
	in `SPEC_FEATURE_ADDITIONS` rather than tolerated by a superset test."""
	import re
	from afya.sensors.service import SPEC_AVAILABILITY, SPEC_FEATURE_ADDITIONS
	spec = _spec_13_1_rows()
	by_slug = {s.slug: s for s in SENSORS}
	for row, (slug, _, _, _) in zip(spec, SPEC_AVAILABILITY, strict=True):
		printed = re.findall(r'\b[A-Z]{2,4}-\d{3}\b', row[3])
		carried = sorted(by_slug[slug].primary_features)
		expected = sorted(set(printed) | set(SPEC_FEATURE_ADDITIONS.get(slug, ())))
		assert carried == expected, f'{slug}: section prints {printed}, code carries {carried}'
	assert set(SPEC_FEATURE_ADDITIONS) <= set(by_slug), 'an addition names a row that does not exist'


# --- §11.6 against §13.1 ---------------------------------------------------------------------

def _spec_11_6_rows() -> list[list[str]]:
	"""§11.6's feature→sensor table, read out of the spec so a revision fails here rather than passing."""
	from pathlib import Path
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	section = text.split('### 11.6 Sensor-Based Monitoring', 1)[1].split('\n---', 1)[0]
	rows: list[list[str]] = []
	for line in section.splitlines():
		if not line.startswith('|') or set(line) <= set('|-: '):
			continue
		cells = [c.strip().replace('**', '') for c in line.strip('|').split('|')]
		if len(cells) != 3 or cells[0] == 'ID':
			continue
		rows.append(cells)
	return rows


def test_the_feature_sensor_table_is_the_sections_rows() -> None:
	"""§11.6 is eight rows mapping a feature to the sensors that carry it. It is §13.1 read the other
	way round, and carrying it is what lets the two be crossed instead of a reader noticing by eye."""
	from afya.sensors.service import SPEC_SENSOR_FEATURES
	spec = _spec_11_6_rows()
	assert len(spec) == 8, f'the section names {len(spec)} features'
	assert [(f, n) for f, n, _ in SPEC_SENSOR_FEATURES] == [(r[0], r[1]) for r in spec]
	assert [c for _, _, c in SPEC_SENSOR_FEATURES] == [r[2] for r in spec]


def test_the_two_sections_disagree_in_five_named_places() -> None:
	"""The finding: §11.6 and §13.1 describe one mapping and do not agree. The report names each
	disagreement rather than reconciling it, because the code follows §13.1 — the section that
	classifies the sensors — and the disagreement is a defect in one of the *sections*, which is a
	question for whoever owns the spec, not something the code should paper over.

	Five, each a distinct fact: §11.6's single "Camera" row cannot say which of §13.1's two cameras
	it means (twice, on SENS-004 and SENS-005); §13.1 gives SENS-005 the optical heart-rate sensor
	and §11.6 omits it; and §11.6 reaches SENS-006 and SENS-007 through platform surfaces
	(HealthKit/Health Connect, wearables) that are not §13.1 sensor rows at all."""
	svc = SensorService(FeatureRegistry())
	findings = svc.sensor_feature_disagreements()
	assert len(findings) == 5, f'{len(findings)} findings: {findings}'
	joined = '\n'.join(findings)
	assert 'SENS-004' in joined and 'SENS-005' in joined and 'SENS-006' in joined and 'SENS-007' in joined
	assert sum('splits into' in f for f in findings) == 2, 'the camera ambiguity, once per row that has it'
	assert any('heart_rate' in f for f in findings), 'SENS-005 loses the optical sensor in §11.6'


def test_every_feature_section_11_6_names_is_one_the_registry_carries() -> None:
	"""A §11.6 row for a feature the registry does not hold describes a sensor path for a capability
	nobody built — the same finding as an unregistered §13.1 feature, from the other direction."""
	from afya.sensors.service import SPEC_SENSOR_FEATURES
	reg = FeatureRegistry()
	missing = []
	for feature_id, _, _ in SPEC_SENSOR_FEATURES:
		try:
			reg.get(feature_id)
		except KeyError:
			missing.append(feature_id)
	assert missing == [], f'§11.6 names features the registry does not carry: {missing}'


def test_a_sensor_name_the_alias_table_does_not_map_is_refused() -> None:
	"""The canary's target. §11.6's cell is read through an explicit alias table, because the two
	sections spell the same hardware differently ("gyroscope" vs "Gyroscope", "BLE" vs "Bluetooth
	LE") and a fuzzy matcher would read "flash" as matching nothing and report a false omission."""
	from afya.sensors.service import _sensor_slugs_in
	covered, unmapped, ambiguous = _sensor_slugs_in('Accelerometer, gyroscope')
	assert covered == {'accelerometer', 'gyroscope'} and not unmapped and not ambiguous
	with pytest.raises(AssertionError, match='alias table does not map'):
		_sensor_slugs_in('Accelerometer, magneto-optical trap')


async def test_the_coverage_view_reports_the_cross_section_disagreements() -> None:
	"""The disagreements ride on the auditor-scoped coverage view, not the public matrix: they name
	spec ids and section numbers, which is evidence about the build rather than something a person
	deciding whether the app suits their handset needs."""
	import httpx
	app, h = _auditor_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		coverage = (await c.get('/sensors/coverage', headers=h)).json()
		disagreements = coverage['sensor_feature_disagreements']
		assert len(disagreements) == 5, disagreements
		# And the public matrix carries none of them.
		matrix = (await c.get('/sensors/capabilities')).json()
		assert 'sensor_feature_disagreements' not in matrix
		assert not any('§11.6' in str(r) for r in matrix['sensors'])
