"""§MON-008 — Nutrition and Food Safety: the two bullets with a name and nothing behind them.

The section's six Features are all food. Four already had a carrier — `food_availability`,
`FoodSafetyAlert` for aflatoxin and recalls, `NUTRITION_BY_AGE` for infant feeding guidance, and
`NUTRITION_BY_AGE`'s local-food lists for the recipe bullet. The two that did not:

* **Seasonal food availability** — the audit row read "`NutritionGuidance.seasonal_foods` is the
  field, and `NUTRITION_BY_AGE` fills it with fixed food lists that do not vary by season, so the
  seasonal half is the name of a field with nothing behind it"
* **therapeutic feeding programme locations** — "neither `PlaceKind` (eight members) nor
  `FacilityKind` (five) has a therapeutic-feeding kind, so no route can list one"

Both are checked here against their archived sources rather than against a copy of their own
numbers: the harvest months against the FAO Crop Calendar for Kenya's own JSON, the programme
vocabulary against Kenya's IMAM guideline. The FAO JSON is *recomputed* below rather than compared
to a transcription of itself, which is the difference between a test and a restatement.
"""
import hashlib
import json
import pathlib

import httpx
import pytest

from afya.facilities.service import FacilityService
from afya.facilities.views import Facility, FacilityKind
from afya.monitoring.service import MonitoringService
from afya.monitoring.views import (
	IMAM_PROGRAMMES, SEASONAL_CALENDAR_SOURCE, SEASONAL_FOODS, THERAPEUTIC_FEEDING_LABEL,
)

SOURCES = pathlib.Path('sources')
INDEX = SOURCES / 'INDEX.md'
FAO = SOURCES / 'fao-crop-calendar-kenya' / 'crop-calendar-ke.json'
IMAM = SOURCES / 'kenya-imam-guidelines' / 'imam-guidelines-2020.txt'


def _svc() -> MonitoringService:
	return MonitoringService()


def _fao_rows() -> list[dict[str, object]]:
	return json.loads(FAO.read_text(encoding='utf-8'))


def _harvest_from_source() -> tuple[dict[str, set[int]], set[str]]:
	"""Recompute the harvest months from the source's own JSON, the way `SEASONAL_FOODS` was built.

	The source's shape: one record per (crop, agro-ecological zone), each carrying `sessions`, each
	session carrying `early_harvest` and `late_harvest` as `{month, day}` and an `all_year` flag.
	A crop's months are the union across every zone, which is why a month in the table means
	"harvested this month somewhere in Kenya".
	"""
	months: dict[str, set[int]] = {}
	all_year: set[str] = set()
	for row in _fao_rows():
		crop = row['crop']['name']  # type: ignore[index]
		for session in row.get('sessions') or []:  # type: ignore[union-attr]
			if str(session.get('all_year', 'no')).lower() == 'yes':
				all_year.add(crop)
			for key in ('early_harvest', 'late_harvest'):
				month = (session.get(key) or {}).get('month')
				if month:
					months.setdefault(crop, set()).add(int(month))
	return months, all_year


# --- the archived sources, and the gate every other check rests on -------------------------------

def test_the_archived_sources_are_present_and_match_their_recorded_checksums() -> None:
	"""Presence and identity are assertions of their own.

	`if FAO.exists():` around the harvest checks below is a gate that fails open — lose the archive
	and every one of them silently stops running, which is the exact failure this file exists to
	catch. The checksum is verified against `sources/INDEX.md` so a *changed* archive fails too.
	"""
	recorded = INDEX.read_text(encoding='utf-8')
	assert INDEX.exists(), 'sources/INDEX.md is missing'
	for path, marker in ((FAO, 'FAO Crop Calendar'), (IMAM, 'Integrated Management of Acute Malnutrition')):
		assert path.exists(), f'the archived source is missing: {path}'
		digest = hashlib.sha256(path.read_bytes()).hexdigest()
		assert digest[:16] in recorded, (
			f'{path.name} is {digest[:16]}, which sources/INDEX.md does not record — the archive '
			'changed, or the record did')
		assert marker in recorded, f'{marker} is not described in sources/INDEX.md'


# --- seasonal food availability, recomputed from the source ---------------------------------------

def test_the_table_is_the_sources_own_crops_and_months() -> None:
	"""The check the audit row asks for. `seasonal_foods` was a field with a fixed list behind it;
	this asserts that every month served is a month the source states, for the crop the source
	states it for, and that nothing the source states is missing from the table.

	The `Épinard` exclusion is asserted rather than left implicit: the source carries the crop and
	no harvest month anywhere, so there is nothing to serve — and a table that quietly gave it one
	would pass a spot-check on any other row.
	"""
	months, all_year = _harvest_from_source()
	served = {row[1]: (set(row[2]), row[3]) for row in SEASONAL_FOODS}

	assert set(served) == set(months), (
		f'served crops disagree with the source: only in table {sorted(set(served) - set(months))}, '
		f'only in source {sorted(set(months) - set(served))}')
	for crop, (row_months, row_all_year) in served.items():
		assert row_months == months[crop], f'{crop}: {sorted(row_months)} != {sorted(months[crop])}'
		assert row_all_year == (crop in all_year), f'{crop}: all-year flag disagrees with the source'

	assert 'Épinard' not in served, 'the source states no harvest month for spinach, so none may be served'
	assert len(SEASONAL_FOODS) == 29 and len(_fao_rows()) == 283


def test_every_served_label_is_distinct_and_carries_its_source_name() -> None:
	"""The label is an English rendering and the source's name is French; the mapping is kept in
	the table so it can be checked. A position-only mapping is a mapping nobody can verify — and
	two rows sharing a label would make `in_season` report the same food twice."""
	labels = [row[0] for row in SEASONAL_FOODS]
	assert len(set(labels)) == len(labels), 'two crops serve the same label'
	for row in SEASONAL_FOODS:
		label, source_name, months = row[0], row[1], row[2]
		assert label and source_name, 'a row with no label or no source name cannot be checked'
		assert months, f'{label} is served with no month at all'
		assert all(1 <= m <= 12 for m in months), f'{label} carries a month that is not a month'


def test_every_source_name_is_spelled_the_way_the_source_spells_it() -> None:
	"""The label is an English rendering and the source's name is French; carrying both is what
	makes the rendering checkable, and the pairing is what a reader checks.

	Two assertions, because they catch different defects. The first is that every source name is a
	crop the source actually carries — an invented one would be unverifiable by construction. The
	second is the mapping itself, pinned here as a second copy of the generator's table: a change
	to either side alone then fails, which is the only way a *swap* between two rows is caught.
	The label and the source name for the crops the source already names in English are equal, and
	that is asserted too rather than assumed.
	"""
	source_crops = {row['crop']['name'] for row in _fao_rows()}  # type: ignore[index]
	labels = {
		'Bok choy': 'Bok choy', 'Broad bean': 'Fève, vert', 'Cabbage': 'Chou, commun',
		'Carrot': 'Carotte', 'Cashew nut': 'Noix de cajou', 'Cassava': 'Manioc',
		'Chickpea': 'Pois chiche', 'Coconut': 'Noix de coco', 'Cowpea': 'Niébé',
		'Dolichos (lablab)': 'Dolicos lablab', 'Dry pea': 'Petit pois, sec',
		'Finger millet': 'Millet, sabac', 'Green gram': 'Pigeon', 'Groundnut': 'Cacahuète',
		'Kales (sukuma wiki)': 'Kales', 'Maize (sweet corn)': 'Maïs, sucré', 'Onion': 'Oignon',
		'Potato': 'Pomme de terre', 'Pumpkin': 'Citrouille', 'Rice': 'Riz', 'Sesame': 'Sésame',
		'Sorghum': 'Sorgho', 'Soybean': 'Soja', 'Sugar cane': 'Canne à sucre',
		'Sunflower': 'Tournesol', 'Sweet potato': 'Patate douce', 'Tomato': 'Tomate',
		'Watermelon': 'Pastèque', 'Wheat (bread)': 'Pain de blé',
	}
	assert {row[0]: row[1] for row in SEASONAL_FOODS} == labels, 'the label mapping drifted'
	assert set(labels.values()) <= source_crops, (
		f'not a crop the source carries: {sorted(set(labels.values()) - source_crops)}')
	assert labels['Kales (sukuma wiki)'] == 'Kales' and labels['Bok choy'] == 'Bok choy', (
		'a crop the source already names in English must not be re-rendered')


def test_the_all_year_crops_are_the_five_the_source_flags() -> None:
	"""`in_season` for any month must include exactly the crops the source marks `all_year: yes`.
	Reading the flag but ignoring it — or inverting it — is the canary this asserts against."""
	assert {row[1] for row in SEASONAL_FOODS if row[3]} == {
		'Canne à sucre', 'Manioc', 'Noix de cajou', 'Noix de coco', 'Riz'}


def test_a_month_serves_what_is_harvested_then() -> None:
	svc = _svc()
	january = svc.nutrition_guidance(24, month=1)
	assert january.month == 1
	assert january.calendar_source == SEASONAL_CALENDAR_SOURCE
	# Every all-year crop is in every month, by construction.
	assert {'Cassava', 'Cashew nut', 'Coconut', 'Rice', 'Sugar cane'} <= set(january.in_season)
	assert 'Maize (sweet corn)' in january.in_season and 'Kales (sukuma wiki)' in january.in_season

	august = svc.nutrition_guidance(24, month=8)
	assert 'Rice' in august.in_season
	assert 'Carrot' not in august.in_season, 'carrot is not harvested in August in the source'
	assert set(august.in_season) != set(january.in_season), 'the season does not vary with the month'


def test_no_month_serves_the_age_list_alone_and_claims_nothing_about_season() -> None:
	"""A caller with no calendar position gets the age band's own list and an empty season. Served
	a month, it would be answering a question nobody asked; served a season, it would be a claim
	with no date behind it."""
	g = _svc().nutrition_guidance(12)
	assert g.seasonal_foods == ['ugali', 'sukuma wiki', 'eggs', 'small fish']
	assert g.in_season == [] and g.month is None and g.calendar_source is None


def test_the_two_lists_are_not_merged() -> None:
	"""A parent is deciding two different things — what to feed this child, and what to buy this
	week — and a merged list cannot say which entry was which. The age list names avocado and small
	fish, which the FAO calendar does not cover at all, so a merge would also read as a seasonal
	claim about foods whose season nobody published."""
	g = _svc().nutrition_guidance(12, month=1)
	assert g.seasonal_foods == ['ugali', 'sukuma wiki', 'eggs', 'small fish']
	assert 'small fish' not in g.in_season and 'avocado' not in g.in_season


def test_a_month_that_is_not_a_month_is_refused() -> None:
	svc = _svc()
	for month in (0, 13, -1):
		with pytest.raises(AssertionError, match='is not a month'):
			svc.nutrition_guidance(24, month=month)
	with pytest.raises(AssertionError, match='paediatric nutrition range'):
		svc.nutrition_guidance(61)


# --- therapeutic feeding programme locations ------------------------------------------------------

def _facility(fid: str, name: str, kind: FacilityKind, county: str, lat: float, lon: float,
              **kw: object) -> Facility:
	return Facility(facility_id=fid, name=name, kind=kind, county=county, lat=lat, lon=lon, **kw)  # type: ignore[arg-type]


async def _registry() -> FacilityService:
	"""One therapeutic feeding site in Kisumu, one in Siaya, and two Kisumu facilities of other
	kinds — an ED and a pharmacy. The other kinds are the point: a finder that filtered on
	`county` alone, or that read the wrong enum member, would return them."""
	svc = FacilityService()
	await svc.upsert(_facility('TF1', 'Kisumu OTP site', FacilityKind.therapeutic_feeding,
	                           'Kisumu', -0.0917, 34.7680, level='health_centre'))
	await svc.upsert(_facility('TF2', 'Ahero feeding site', FacilityKind.therapeutic_feeding,
	                           'Kisumu', -0.1730, 34.9200))
	await svc.upsert(_facility('TF3', 'Siaya feeding site', FacilityKind.therapeutic_feeding,
	                           'Siaya', 0.0600, 34.2880))
	await svc.upsert(_facility('ED1', 'Kisumu ED', FacilityKind.ed, 'Kisumu', -0.0900, 34.7700))
	await svc.upsert(_facility('PH1', 'Kisumu pharmacy', FacilityKind.pharmacy, 'Kisumu',
	                           -0.0910, 34.7690))
	return svc


async def test_only_therapeutic_feeding_sites_are_returned_and_the_nearest_first() -> None:
	"""Both halves matter. A finder that returned the county's whole registry would send a parent
	to a pharmacy; one that did not order by distance would make the "nearest" claim in the field
	name untrue — and `distance_km` is served, so the order has to agree with the numbers."""
	registry = await _registry()
	rows = _svc().therapeutic_feeding_centres(registry, 'Kisumu', -0.0917, 34.7680)
	assert [r.facility_id for r in rows] == ['TF1', 'TF2']
	assert all(r.kind == 'therapeutic_feeding' for r in rows)
	assert rows[0].distance_km <= rows[1].distance_km
	assert rows[0].distance_km == 0.0
	assert rows[0].level == 'health_centre' and rows[1].level is None


async def test_a_site_in_another_county_is_not_served() -> None:
	"""A parent in Kisumu sent to Siaya is a wasted journey, and the county filter is the only
	thing that prevents it."""
	registry = await _registry()
	rows = _svc().therapeutic_feeding_centres(registry, 'Siaya', 0.06, 34.288)
	assert [r.facility_id for r in rows] == ['TF3']


async def test_a_county_with_nothing_filed_is_an_empty_list_not_a_refusal() -> None:
	"""An empty list is a real answer — "nothing is filed here" — and a different one from "there
	is no such programme". Raising would collapse the two and make the screen show an error where
	it should show a gap."""
	registry = await _registry()
	assert _svc().therapeutic_feeding_centres(registry, 'Turkana', 3.1, 35.6) == []


async def test_the_finder_returns_at_most_the_limit_asked_for() -> None:
	registry = await _registry()
	rows = _svc().therapeutic_feeding_centres(registry, 'Kisumu', -0.0917, 34.7680, limit=1)
	assert len(rows) == 1 and rows[0].facility_id == 'TF1'
	with pytest.raises(AssertionError, match='not a finder'):
		_svc().therapeutic_feeding_centres(registry, 'Kisumu', -0.0917, 34.7680, limit=0)


async def test_the_three_programmes_travel_with_every_site() -> None:
	"""The registry records *that* a facility is a therapeutic feeding site; it does not record
	which of the three programmes it runs. So the payload carries the national vocabulary — what
	each door is for — rather than a per-row claim invented from nothing. A parent who took an
	out-patient definition as this site's would bring a child with complications to a queue that
	cannot admit them."""
	registry = await _registry()
	site = _svc().therapeutic_feeding_centres(registry, 'Kisumu', -0.0917, 34.7680)[0]
	assert [p['slug'] for p in site.programmes] == ['otp', 'sc', 'sfp']
	assert site.label == THERAPEUTIC_FEEDING_LABEL
	assert 'Integrated Management of Acute Malnutrition' in site.source
	assert 'complications' in site.programmes[1]['definition']
	assert site.walk_in is True


def test_the_site_label_is_a_sentence_and_not_the_internal_slug() -> None:
	"""`label` is the one field on this model a parent actually reads, and `kind` is an enum member
	whose value is an internal handle.

	Asserting `label == THERAPEUTIC_FEEDING_LABEL` above is not enough: a constant and itself agree
	whatever the constant says, so a label emptied to the bare slug passes it. This pins the
	*content* — it must be a sentence, name the condition it treats, and not be the slug.
	"""
	assert site_kind_slug() not in THERAPEUTIC_FEEDING_LABEL, 'the label is the internal slug'
	assert THERAPEUTIC_FEEDING_LABEL.count(' ') >= 8, 'the label is not a sentence'
	assert 'therapeutic feeding programme' in THERAPEUTIC_FEEDING_LABEL
	assert 'acute malnutrition' in THERAPEUTIC_FEEDING_LABEL
	assert THERAPEUTIC_FEEDING_LABEL[0].isupper() and THERAPEUTIC_FEEDING_LABEL.endswith('guidelines')


def site_kind_slug() -> str:
	return FacilityKind.therapeutic_feeding.value


def test_the_programme_vocabulary_is_the_guidelines_own() -> None:
	"""`OTP`, `SC` and `SFP` are the guideline's abbreviation list, not an invented set. The source
	is read here rather than trusted: a vocabulary that drifted from the national guideline would be
	a screen naming a programme Kenya does not run."""
	text = IMAM.read_text(encoding='utf-8')
	for slug, label, definition in IMAM_PROGRAMMES:
		assert slug in {'otp', 'sc', 'sfp'}
		assert label, f'{slug} has no label'
		assert definition, f'{slug} has no definition'
	assert 'Out-patient Therapeutic Programme' in text
	assert 'Stabilization Center' in text
	assert 'Supplementary Feeding Programme' in text


def test_the_kind_is_a_facility_kind_and_not_a_service() -> None:
	"""The audit row named `FacilityKind`. `ServiceOffered` could not take it: that enum's own
	docstring is §FND-001's printed list of seven, closed, and a nutrition programme is not one of
	the seven — widening it would make the finder offer a service the section never printed."""
	from afya.facilities.views import ServiceOffered
	assert FacilityKind.therapeutic_feeding.value == 'therapeutic_feeding'
	assert 'therapeutic_feeding' not in {s.value for s in ServiceOffered}
	assert len(FacilityKind) == 6


# --- the front door ------------------------------------------------------------------------------

def _client() -> httpx.AsyncClient:
	from afya.service import build_services, create_app
	return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(build_services())),
	                         base_url='http://t')


async def test_the_nutrition_route_serves_the_season_when_a_month_is_given() -> None:
	"""The route served the age band alone. The month is the parameter that turns the seasonal half
	from a field name into an answer, so it is exercised through the app."""
	async with _client() as c:
		plain = await c.get('/monitoring/nutrition/12')
		assert plain.status_code == 200
		assert plain.json()['in_season'] == [] and plain.json()['month'] is None

		august = await c.get('/monitoring/nutrition/12', params={'month': 8})
		assert august.status_code == 200, august.text
		out = august.json()
		assert out['month'] == 8
		assert out['seasonal_foods'] == ['ugali', 'sukuma wiki', 'eggs', 'small fish']
		assert 'Rice' in out['in_season'] and 'Carrot' not in out['in_season']
		assert out['calendar_source'] == SEASONAL_CALENDAR_SOURCE

		assert (await c.get('/monitoring/nutrition/12', params={'month': 13})).status_code == 422


async def test_the_therapeutic_feeding_route_serves_the_sites_and_refuses_a_bad_limit() -> None:
	async with _client() as c:
		r = await c.get('/monitoring/therapeutic-feeding',
		                params={'county': 'Kisumu', 'lat': -0.0917, 'lon': 34.768})
		assert r.status_code == 200, r.text
		assert isinstance(r.json(), list)
		assert (await c.get('/monitoring/therapeutic-feeding',
		                    params={'county': 'Kisumu', 'lat': -0.0917, 'lon': 34.768,
		                            'limit': 0})).status_code == 422


async def test_no_spec_feature_code_appears_in_any_served_field() -> None:
	"""The standing constraint: §MON-008 is an internal identifier. A person reads "Nutrition and
	food safety", never "MON-008".

	The regex is the house one, not a substring search for this section's own code: a served field
	carrying some *other* section's id is the same defect, and the vacuousness guard matters more
	here than usual because a payload of numbers would pass every one of these assertions by
	carrying no strings at all.
	"""
	import re
	code = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')

	registry = await _registry()
	site = _svc().therapeutic_feeding_centres(registry, 'Kisumu', -0.0917, 34.7680)[0]
	guidance = _svc().nutrition_guidance(12, month=8)
	strings = [guidance.guidance, guidance.calendar_source or '', *guidance.seasonal_foods,
	           *guidance.in_season, site.name, site.label, site.source, *site.programmes[0].values()]
	assert strings, 'a vacuous check over nothing reads as a pass'
	for s in strings:
		assert not code.search(s), s
