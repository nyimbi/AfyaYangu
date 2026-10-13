"""§8.5 INF-005: the travel advisory, and the two things it was not.

Four of the section's five Features were `carried` and one was `missing`, but three of the four
carried rows disclosed a gap in their own note. All four were the same shape — **a claim with no
table behind it**:

* "Country and county advisories" was `missing` because `advisory(destination, origin_country)`
  interpolated its two arguments into one fixed paragraph. Kampala, Kinshasa and
  Kinshasa-from-Nairobi were answered identically, so the country half was a constant and the
  county half had no carrier in this module at all.
* "What to do if you feel unwell after travel" was one sentence — the 719 line — where the sources
  say five things.
* "21-day self-monitoring enrolment for travellers (**links to MON-009**)" linked by *saying so*:
  the acknowledgement promised a schedule while `MonitoringService` had never heard of the
  traveller, so the diary route answered an empty list.

The tests worth reading are the three about direction. `not_assessed` is not `low` (WHO had not
finished assessing Kenya when the notice went out, and serving the regional band would have been the
most consequential invention in the file). An unrecognised place is not a safe place. And a
deployment with no monitoring service wired says `diary_linked=False` rather than promising a
diary — the same rule as §MED-002's pregnancy caveat: **the only answer that may never be invented
is the reassuring one.**
"""
import ast
import pathlib
import re

import httpx
import pytest

from afya.info.service import InfoService
from afya.info.views import CountyRisk
from afya.location.advisories import (
	ASSESSED_ON_ISO, BANDS, COUNTRIES, NOT_ASSESSED, NOT_ASSESSED_CAVEAT, POST_TRAVEL_STEPS,
	STEP_SOURCES, TRAVELLER_RISK_NOTE, UNKNOWN, VERY_HIGH, WHO_BORDER_NOTE, WHO_RISK_TABLE,
	WHO_TRAVEL_ADVICE, row_for,
)
from afya.location.service import LocationService
from afya.location.views import TravelerDeclaration
from afya.monitoring.service import MonitoringService
from afya.service import build_services, create_app

FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _svc(county_risk: object = None, monitoring: object = None) -> LocationService:
	svc = LocationService(county_risk, monitoring)  # type: ignore[arg-type]
	return svc


def _declaration(subject: str = 'U-1', **kw: object) -> TravelerDeclaration:
	body: dict[str, object] = {
		'declaration_id': 'TD-ABCDEFGH', 'subject_ref': subject, 'destination': 'Nairobi',
		'arrival_iso': '2026-10-01T00:00:00Z', 'origin_country': 'UG',
	}
	return TravelerDeclaration(**{**body, **kw})  # type: ignore[arg-type]


async def _citizen(c: httpx.AsyncClient, subject: str | None = None) -> tuple[dict[str, str], str]:
	tok = (await c.post('/auth/anonymous', json={'subject_ref': subject} if subject else {})).json()
	return {'Authorization': f'Bearer {tok["token"]}'}, str(tok['subject_ref'])


# --- "Country and county advisories" --------------------------------------------------------------

def test_the_country_half_is_a_table_and_not_a_constant() -> None:
	"""The defect, stated as a test. Two destinations must not be answered with the same paragraph:
	that is what "the country half is a constant rather than a table" means, and a test that read
	only one destination could not tell the two apart.

	The **source's own sentence** has to reach the paragraph, not just the band — a paragraph that
	carried a band and dropped the sentence it came from would still differ between two countries
	while leaving a reader with a number nobody can check. Canary #1 is exactly that mutation and
	this test is why it fires."""
	svc = _svc()
	drc = svc.travel_advisory('Democratic Republic of the Congo', 'Kenya')
	uganda = svc.travel_advisory('Uganda', 'Kenya')
	assert drc.advisory != uganda.advisory
	assert drc.destination.band == VERY_HIGH and uganda.destination.band == 'high'
	assert 'very high' in drc.advisory and 'high' in uganda.advisory
	assert 'particular concern' in uganda.advisory, 'the band arrived without the sentence behind it'
	assert 'cross-border population movement' in uganda.advisory
	assert row_for('Uganda').stated in uganda.advisory  # type: ignore[union-attr]


def test_a_country_row_carries_the_sources_own_sentence_for_it() -> None:
	"""A band with no sentence behind it is a number a reader cannot check, and this outbreak's band
	moved twice in four months. `stated` is the source's words rather than a paraphrase."""
	row = row_for('Uganda')
	assert row is not None and row.band == 'high'
	assert 'particular concern' in row.stated, 'the band lost the sentence it came from'
	assert 'cross-border population movement' in row.stated


def test_kenya_is_not_assessed_and_never_low() -> None:
	"""The one row this whole section is for. WHO's notice says a detailed rapid risk assessment for
	Kenya "is currently ongoing ... and will be reported once available", so the honest verdict is
	that there is none. Kenya sits inside the "rest of the African Region" band, and reading it off
	that band would have answered "low" about the country the advisory is served in."""
	row = row_for('Kenya')
	assert row is not None and row.band == NOT_ASSESSED
	assert 'currently ongoing' in row.stated
	assert 'low' not in row.band


def test_an_unrecognised_place_is_unknown_and_not_a_band() -> None:
	"""A city, a misspelling and a country WHO did not name are one fact from the table's side:
	nothing in the source addresses it. The advisory is asked "is it safe to travel", and answering
	a city with a band would invent the one answer that may never be invented."""
	svc = _svc()
	for place in ('Kampala', 'Busialand', 'Atlantis'):
		row = svc.place_advisory(place)
		assert row.kind == 'unknown' and row.band == UNKNOWN, place
		assert row.name == '' and 'No country row matches' in row.stated


def test_the_unknown_verdict_is_never_rendered_as_reassurance() -> None:
	"""The band label for `unknown` is "not assessed", which is a refusal to answer — and the
	source's own caveat travels with it, because a traveller reading a paragraph that ends in a
	country name needs to know the name is the only thing that matched."""
	svc = _svc()
	report = svc.travel_advisory('Goma', 'Kenya')
	assert report.destination.kind == 'unknown'
	assert 'not assessed' in report.advisory
	assert report.not_assessed_caveat == NOT_ASSESSED_CAVEAT
	assert 'not the same as being assessed as low risk' in report.not_assessed_caveat


def test_the_county_half_reads_the_dashboard_and_not_a_second_table() -> None:
	"""The row said the county half "has no carrier at all". It had one the whole time, in another
	module: `CountyRisk` already holds a per-county band with a stamp and a source. A second table
	here would be the copy that goes stale the first time a county office publishes a risk level."""
	info = InfoService()
	svc = _svc(info.dashboard)
	row = svc.place_advisory('Busia')
	assert row.kind == 'county' and row.name == 'Busia'
	assert row.band in ('low', 'moderate', 'high'), 'a county must not carry a WHO band'
	assert row.source.startswith('County dashboard')


async def test_a_county_offices_published_risk_reaches_the_traveller_screen() -> None:
	"""The end-to-end claim: what §INF-001's dashboard records is what the advisory serves, with the
	stamp the county office set rather than today's date."""
	info = InfoService()
	svc = _svc(info.dashboard)
	await info.set_county_risk(CountyRisk(
		county='Busia', risk_level='high', active_signals=4, bulletin='Confirmed cases in the county.',
		source='Busia County Health Office'), at_ms=1_760_000_000_000)
	row = svc.place_advisory('Busia')
	assert row.band == 'high' and row.stated == 'Confirmed cases in the county.'
	assert row.source == 'Busia County Health Office'
	assert row.assessed_on_iso.startswith('2025-'), row.assessed_on_iso
	assert row.assessed_on_iso != ASSESSED_ON_ISO, 'a county row is not WHO\'s August assessment'


def test_a_county_never_assessed_is_served_with_no_date_rather_than_todays() -> None:
	"""`dashboard()` answers an unknown county with a defaulted low-risk row so a client always has
	something to draw. With no stamp that default reads as an assessment someone made — the same
	failure §6.2.3 names for the dashboard itself, and the reason the stamp is carried rather than
	the payload being stamped at serve time."""
	info = InfoService()
	row = _svc(info.dashboard).place_advisory('Busia')
	assert row.band == 'low' and row.assessed_on_iso == ''
	assert 'no source line published' in row.source


def test_the_county_half_falls_through_when_it_has_nothing() -> None:
	"""`None` from `_county_advisory` is what lets the caller reach the country table. A county
	resolver that answered for anything would make "Kenya" a county lookup miss and a country lookup
	that never runs."""
	svc = _svc()
	assert svc.place_advisory('Kenya').kind == 'country'
	assert svc.place_advisory('Uganda').kind == 'country'
	# The same service with no risk source wired still answers the country half.
	assert _svc(None).place_advisory('Kenya').kind == 'country'


def test_the_two_halves_keep_their_own_vocabularies() -> None:
	"""`PlaceAdvisory.band` accepts the union so one model serves both tables, and `kind` says which
	table a row came from. The two vocabularies **overlap on `high` and `low`**, and that overlap is
	the reason `kind` is not decoration: "high" for Uganda is WHO's land-border band and "high" for
	a Kenyan county is a dashboard reading, and a client that rendered the union as one scale would
	let a reader rank them against each other. The overlap is asserted rather than wished away — a
	test that expected the vocabularies to be disjoint would pass on a tree that had quietly renamed
	one of them, which is the drift this section is about."""
	assert set(BANDS) == {'very_high', 'high', 'moderate', 'low', 'not_assessed', 'unknown'}
	country_bands = {c.band for c in COUNTRIES}
	assert country_bands <= {'very_high', 'high', 'low', 'not_assessed'}
	assert country_bands & {'low', 'moderate', 'high'} == {'high', 'low'}, (
		'the vocabularies share `high` and `low`; if they stop sharing, one of them was renamed and '
		'the rename is the finding')
	# The two bands a county can carry that WHO's table has no row for, and the two WHO bands a
	# county cannot: the asymmetry is what makes the overlap a trap rather than a shared scale.
	assert {'moderate'} <= {'low', 'moderate', 'high'} - country_bands
	assert {'very_high', 'not_assessed'} <= country_bands - {'low', 'moderate', 'high'}


def test_the_source_does_not_enumerate_the_drcs_land_border() -> None:
	"""The table is short because the source is short, and this is the assertion that keeps it that
	way. WHO names three countries "of particular concern" and does not enumerate the rest; Burundi
	shares a land border with the DRC and has no row. Answering it "low" from the regional band is
	exactly the invented number `sources/INDEX.md` exists to prevent."""
	assert {c.iso2 for c in COUNTRIES} == {'CD', 'UG', 'CF', 'SS', 'KE', 'FR', 'DE'}
	assert row_for('Burundi') is None, 'Burundi has a land border with the DRC and no row in the source'
	assert row_for('Rwanda') is None and row_for('Tanzania') is None


def test_whos_own_risk_table_and_confidence_are_served() -> None:
	"""Two of the four rows are bands for *groups* — "Rest of the African Region", "Global" — which
	cannot be resolved to a country and would otherwise be invisible to a traveller in neither the
	DRC nor a land-border state. The confidence travels with them because the source does not claim
	certainty about the rows that matter most."""
	report = _svc().travel_advisory('Kenya', 'Uganda')
	assert [(b.label, b.band) for b in report.risk_table] == [(a, b) for a, b, _ in WHO_RISK_TABLE]
	assert all(b.confidence for b in report.risk_table)
	assert {b.confidence for b in report.risk_table if b.band == 'high'} == {'moderate'}


def test_whos_travel_advice_is_carried_verbatim_and_is_the_whole_answer() -> None:
	"""WHO does not say "do not travel to X"; it says countries should not close against each other.
	A product that turned this into a per-destination go/no-go would answer a question the authority
	deliberately declined to answer — so the sentence is served as it stands, beside the border note
	that stops it reading as a licence to ignore the outbreak."""
	report = _svc().travel_advisory('Democratic Republic of the Congo', 'Kenya')
	assert report.who_travel_advice == WHO_TRAVEL_ADVICE
	assert 'advises against any restriction of travel' in report.who_travel_advice
	assert report.border_note == WHO_BORDER_NOTE
	assert 'informal border crossing routes' in report.border_note


# --- "What to do if you feel unwell after travel" -------------------------------------------------

def test_the_post_travel_guidance_is_five_steps_and_not_one_sentence() -> None:
	"""The row called it "one fixed sentence", and it was: the advisory ended "if you feel unwell
	after arrival, call 719" — one of five things the sources say, and the only one a Kenyan reader
	already knows."""
	report = _svc().travel_advisory('Democratic Republic of the Congo', 'Kenya')
	assert [s.step_id for s in report.steps] == [sid for sid, _, _ in POST_TRAVEL_STEPS]
	assert len(report.steps) == 5
	joined = ' '.join(s.instruction for s in report.steps)
	assert '21 days' in joined and 'Seek medical care immediately' in joined
	assert '719' in joined and 'public transport' in joined


def test_every_step_carries_its_own_source_because_they_are_not_one_authoritys() -> None:
	"""Three of the five are quoted from WHO or CDC and two are this deployment's operating rule,
	and a traveller is owed the difference — the same reason `sources/INDEX.md` records what a
	source does *not* support."""
	report = _svc().travel_advisory('Kenya', 'Uganda')
	by_id = {s.step_id: s for s in report.steps}
	assert 'CDC' in by_id['monitor'].source and 'CDC' in by_id['seek_care'].source
	assert 'WHO' in by_id['symptoms'].source
	assert 'not stated by either source' in by_id['call'].source
	assert 'not stated by either source' in by_id['declare'].source
	assert len({s.source for s in report.steps}) > 1, 'all five read as one authority'


def test_the_sources_own_counterweight_is_served_with_the_bands() -> None:
	"""A reader who sees only the risk bands concludes that Ebola is a general hazard. The source
	says the opposite in its own words, and it travels on the report rather than in a footnote."""
	report = _svc().travel_advisory('Democratic Republic of the Congo', 'Kenya')
	assert report.traveller_risk_note == TRAVELLER_RISK_NOTE
	assert 'pose little risk to travelers or the general public' in report.traveller_risk_note


def test_the_steps_source_table_covers_every_step() -> None:
	"""Read from the tables rather than the service: a step added without a source would raise at
	serve time on the one screen a person reads while unwell."""
	assert {src for _, _, src in POST_TRAVEL_STEPS} == set(STEP_SOURCES)
	for _, _, src in POST_TRAVEL_STEPS:
		assert STEP_SOURCES[src].strip(), src


# --- "21-day self-monitoring enrolment for travellers (links to MON-009)" -------------------------

async def test_the_enrolment_reaches_the_monitoring_service() -> None:
	"""The link was a message string: the acknowledgement named days 1, 3, 7, 14 and 21 while
	`MonitoringService` had never heard of the traveller, so the diary answered an empty list and no
	day was ever logged."""
	monitoring = MonitoringService()
	svc = _svc(None, monitoring)
	enrolment = await svc.self_declare(_declaration())
	assert enrolment.diary_linked is True
	assert monitoring.diary('U-1') == [], 'enrolled, and nothing filed yet'
	assert 'U-1' in monitoring._households  # noqa: SLF001 — the window itself, not a proxy for it


async def test_a_deployment_with_no_monitoring_wired_says_so() -> None:
	"""`diary_linked=False` is the honest answer and the one a client can act on. Reporting True
	from a service that has nothing to enrol into is a schedule nothing will ask about."""
	enrolment = await _svc().self_declare(_declaration())
	assert enrolment.diary_linked is False
	assert enrolment.report_schedule == [1, 3, 7, 14, 21]


async def test_the_diary_route_has_a_window_to_file_against(tmp_path) -> None:
	"""The front door, not the unit. A declaration through `/location/traveller/declare` must leave
	a 21-day window that `/monitoring/contact/{ref}/diary` can be filed against — the two services
	are wired together in `build_services`, and a unit test that constructs them by hand proves the
	call while proving nothing about the deployment."""
	app = create_app(build_services(db_path=str(tmp_path / 'afya.db')))
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers, subject = await _citizen(c)
		declared = await c.post('/location/traveller/declare', headers=headers, json={
			'declaration_id': 'TD-ABCDEFGH', 'subject_ref': subject, 'destination': 'Nairobi',
			'arrival_iso': '2026-10-01T00:00:00Z', 'origin_country': 'UG'})
		assert declared.status_code == 200, declared.text
		assert declared.json()['diary_linked'] is True, 'the deployment did not wire the two services'
		# A day filed against the window the declaration created — the point of the link.
		logged = await c.post('/monitoring/contact/day', headers=headers, json={
			'entry_id': 'MON-ABCD1234', 'subject_ref': subject, 'day': 3, 'temperature_c': 36.8})
		assert logged.status_code == 200, logged.text
		diary = await c.get(f'/monitoring/contact/{subject}/diary', headers=headers)
		assert diary.status_code == 200, diary.text
		assert [e['day'] for e in diary.json()['entries']] == [3]


async def test_the_officer_is_not_invented_for_a_traveller() -> None:
	"""A traveller is not a contact of a named officer, and inventing one would put a stranger's
	name on a 21-day record. §MON-009's escalation falls back to 719, which the advisory already
	names."""
	monitoring = MonitoringService()
	await _svc(None, monitoring).self_declare(_declaration())
	household = monitoring._households['U-1']  # noqa: SLF001
	assert household.monitoring_officer is None and household.monitoring_officer_number is None


# --- layering, and what a person is allowed to read -----------------------------------------------

def test_the_location_module_may_read_info_without_a_cycle() -> None:
	"""`CountyRisk` is a plain runtime import in `location.service`, not a `TYPE_CHECKING` guard,
	because a Protocol method's annotation is evaluated when the class object is created. That is
	only safe while the edge runs one way, so the edge is asserted rather than assumed."""
	tree = ast.parse((ROOT / 'src/afya/info/service.py').read_text())
	imported: set[str] = set()
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			imported |= {a.name for a in node.names}
		elif isinstance(node, ast.ImportFrom) and node.module:
			imported.add(node.module)
	assert not [m for m in imported if m.startswith('afya.location')], (
		f'afya.info.service imports afya.location: {sorted(imported)}')


async def test_no_feature_code_reaches_anything_a_person_reads(tmp_path) -> None:
	"""§3.3 principle 9: a spec id is an internal handle. The advisory is a paragraph a person reads
	at a border and the steps are instructions they act on, so this is the surface where a code
	would do the most damage."""
	app = create_app(build_services(db_path=str(tmp_path / 'afya.db')))
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers, subject = await _citizen(c)
		bodies = [
			(await c.get('/location/travel-advisory',
			             params={'destination': 'Democratic Republic of the Congo',
			                     'origin_country': 'Kenya'})).text,
			(await c.get('/location/travel-advisory',
			             params={'destination': 'Goma', 'origin_country': 'Kenya'})).text,
			(await c.post('/location/traveller/declare', headers=headers, json={
				'declaration_id': 'TD-ABCDEFGH', 'subject_ref': subject, 'destination': 'Nairobi',
				'arrival_iso': '2026-10-01T00:00:00Z', 'origin_country': 'UG'})).text,
		]
		for body in bodies:
			assert not FEATURE_CODE.search(body), body


async def test_the_advisory_route_serves_both_places_and_the_steps() -> None:
	"""The response grew from `{advisory, lang}` to the resolved rows and the five steps, because
	§INF-005 asks for four things this one route answers and a client that had to call four routes
	to render one screen would compose the answer itself. `advisory` stays a string for §5.4's USSD
	and SMS legs, which cannot render a structure."""
	app = create_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		r = await c.get('/location/travel-advisory',
		                params={'destination': 'Uganda', 'origin_country': 'Kenya'})
		assert r.status_code == 200, r.text
		out = r.json()
	assert out['destination']['kind'] == 'country'
	assert out['destination']['band'] == 'high'
	assert out['origin']['name'] == 'Kenya'
	assert out['origin']['band'] == 'not_assessed'
	assert len(out['steps']) == 5
	assert isinstance(out['advisory'], str) and 'high' in out['advisory']
	assert out['source'] and out['lang'] == 'en'


def test_a_place_advisory_refuses_a_band_from_neither_table() -> None:
	"""`band` accepts the union of two vocabularies and nothing else, so a third one cannot be
	introduced by a caller — the model is the only place the two tables are allowed to meet."""
	from pydantic import ValidationError

	from afya.location.views import PlaceAdvisory

	with pytest.raises(ValidationError):
		PlaceAdvisory(place='X', kind='country', band='severe')
	with pytest.raises(ValidationError):
		PlaceAdvisory(place='X', kind='city', band='low')
	with pytest.raises(ValidationError):
		PlaceAdvisory.model_validate({'place': 'X', 'kind': 'unknown', 'band': 'low', 'extra': 1})
