"""§MED-003 — the dosage calculator, and the source every number in it comes from.

The section is a weight-based dosing calculator for common medicines, especially paediatric. The
route it had computed `weight_kg * mg_per_kg` and took `mg_per_kg` from the caller: the one constant
a person opens a dosing calculator to look up, supplied by the person looking it up. A caller who
knew the figure did not need the app.

Every figure in `afya.medicine.formulary` is checked here against the WHO Pocket Book of Hospital
Care for Children, second edition, archived at `sources/who-pocket-book/` with its checksums and page
references in `sources/INDEX.md`. Where the source states no maximum, the test asserts the code
carries none — a number invented to fill that column would be the most dangerous kind of wrong, a
limit a prescriber trusts that no guideline set.
"""
import pathlib

import httpx

from afya.medicine import formulary
from afya.medicine.service import MedicineService, PPBStubClient
from afya.medicine.views import DoseRequest

SOURCE = pathlib.Path('sources/who-pocket-book/who-pocket-book-2nd-ed.txt')
INDEX = pathlib.Path('sources/INDEX.md')


def _svc() -> MedicineService:
	return MedicineService(PPBStubClient())


def _dose(**kw: object) -> object:
	return _svc().dose(DoseRequest(**kw))  # type: ignore[arg-type]


def test_the_archived_source_is_present_and_matches_its_recorded_checksum() -> None:
	"""The gate every other check in this file rests on, and the reason none of them is guarded.

	`if SOURCE.exists():` around a figure assertion is a gate that fails open: lose the archive and
	every check below silently stops running, which is the one failure this file exists to prevent.
	Presence is therefore an assertion of its own, and the checksum is verified against the one
	`sources/INDEX.md` records so a *changed* archive fails too — a source that can change under a
	clinical calculation is not a source. The canary that proves this file's other gates are live
	points `SOURCE` at a path that does not exist and requires the suite to fail.
	"""
	import hashlib

	assert SOURCE.exists(), f'the archived source is missing: {SOURCE}'
	assert INDEX.exists(), 'sources/INDEX.md is missing'
	digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
	recorded = INDEX.read_text()
	assert digest[:16] in recorded, (
		f'{SOURCE.name} is {digest[:16]}, which sources/INDEX.md does not record — the archive '
		'changed, or the record did')
	assert 'WHO Pocket Book of Hospital Care for Children' in recorded


# --- the five formulations the section names ------------------------------------------------------

def test_the_formulary_is_exactly_the_five_the_section_names() -> None:
	"""§MED-003: "Common paediatric formulations (paracetamol, amoxicillin, ORS, zinc,
	artemether-lumefantrine)". Five named, five present — the section's list is the set."""
	assert {e.slug for e in formulary.PAEDIATRIC_FORMULARY} == {
		'paracetamol', 'amoxicillin', 'ors', 'zinc', 'artemether-lumefantrine',
	}


def test_every_entry_states_where_in_the_source_it_comes_from() -> None:
	"""A dose with no page reference is a dose nobody can check."""
	for entry in formulary.PAEDIATRIC_FORMULARY:
		assert entry.source_page, f'{entry.slug} names no source page'


def test_a_name_matches_on_whole_words_not_substrings() -> None:
	"""The failure `essential_slug` documents: "act" is inside "contact", and a substring test would
	dose an antibiotic for a malaria tablet."""
	assert formulary.match('paracetamol') is formulary.PARACETAMOL
	assert formulary.match('Panadol') is formulary.PARACETAMOL
	assert formulary.match('coartem') is formulary.ARTEMETHER_LUMEFANTRINE
	assert formulary.match('contact') is None
	assert formulary.match('insulinoma') is None


# --- the numbers, against the archived source -----------------------------------------------------

def test_the_paracetamol_figures_are_the_sources() -> None:
	"""Appendix 2, p. 367: "Paracetamol 10–15 mg/kg, up to six times a day"."""
	assert (formulary.PARACETAMOL.mg_per_kg_low, formulary.PARACETAMOL.mg_per_kg_high) == (10.0, 15.0)
	assert formulary.PARACETAMOL.doses_per_day_high == 6
	text = SOURCE.read_text(errors='replace')
	assert 'Paracetamol              10–15 mg/kg, up to six' in text


def test_the_amoxicillin_figures_are_the_sources() -> None:
	"""Appendix 2, p. 357: 25 mg/kg twice a day generally, 40 mg/kg twice a day for pneumonia."""
	assert (formulary.AMOXICILLIN.mg_per_kg_low, formulary.AMOXICILLIN.mg_per_kg_high) == (25.0, 40.0)
	assert formulary.AMOXICILLIN.doses_per_day_low == 2
	text = SOURCE.read_text(errors='replace')
	assert 'Amoxicillin               25 mg/kg twice a day' in text
	assert 'For pneumonia             40 mg/kg twice a day' in text


def test_the_zinc_rule_turns_on_six_months_and_nothing_else() -> None:
	"""p. 134: "≤ 6 months: half tablet (10 mg) per day for 10–14 days; ≥ 6 months: one tablet
	(20 mg) per day for 10–14 days". Age is a threshold here, not a dose axis."""
	assert formulary.ZINC_MONTHS_THRESHOLD == 6
	assert (formulary.ZINC_MG_UNDER, formulary.ZINC_MG_FROM) == (10.0, 20.0)
	assert (formulary.ZINC_DAYS_LOW, formulary.ZINC_DAYS_HIGH) == (10, 14)
	text = SOURCE.read_text(errors='replace')
	assert '≤ 6 months: half tablet (10 mg) per day for 10–14 days' in text
	assert '≥ 6 months: one tablet (20 mg) per day for 10–14 days' in text


def test_the_ors_volumes_are_the_sources() -> None:
	"""p. 136 for the per-stool volume, p. 135 for the 5 ml/kg per hour maintenance rate."""
	assert (formulary.ORS_ML_UNDER_2Y_LOW, formulary.ORS_ML_UNDER_2Y_HIGH) == (50.0, 100.0)
	assert (formulary.ORS_ML_FROM_2Y_LOW, formulary.ORS_ML_FROM_2Y_HIGH) == (100.0, 200.0)
	assert formulary.ORS_ML_PER_KG_MAINTENANCE == 5.0
	text = SOURCE.read_text(errors='replace')
	assert 'for children < 2 years, about 50–100 ml after each loose stool' in text
	assert 'for children ≥ 2 years, about 100–200 ml after each loose stool' in text
	assert 'about 5 ml/kg per h' in text


def test_the_artemether_lumefantrine_bands_are_the_sources() -> None:
	"""p. 164, stated as tablet counts for the 20 mg/120 mg combined tablet, not as a mg/kg dose."""
	bands = formulary.ARTEMETHER_LUMEFANTRINE.bands
	assert [(b.min_kg, b.max_kg, b.units_low) for b in bands] == [
		(5.0, 15.0, 1), (15.0, 24.0, 2), (25.0, 35.0, 3)]
	text = SOURCE.read_text(errors='replace')
	assert 'child weighing 5 – < 15 kg: one tablet twice a day for 3 days' in text
	assert 'child weighing 15–24 kg: 2 tablets twice a day for 3 days' in text


def test_no_maximum_is_stated_where_the_source_states_none() -> None:
	"""The most important assertion in this file.

	The Pocket Book gives paracetamol a *frequency* ceiling and no milligram total, and gives
	amoxicillin, ORS and zinc no maximum at all. Filling `max_mg_per_dose` for those would invent
	the number a prescriber is most likely to rely on, so the field stays `None` and the result says
	so in words rather than leaving an empty column that reads as "no limit".
	"""
	for entry in formulary.PAEDIATRIC_FORMULARY:
		assert entry.max_mg_per_dose is None, f'{entry.slug} claims a maximum the source does not state'
		assert entry.max_mg_per_day is None, f'{entry.slug} claims a daily maximum the source does not state'
	out = _dose(drug='paracetamol', weight_kg=20.0)
	assert any('no maximum dose' in w for w in out.warns)  # type: ignore[attr-defined]


# --- the calculator ------------------------------------------------------------------------------

async def test_the_route_takes_no_mg_per_kg() -> None:
	"""The defect this unit fixes, asserted on the wire rather than on the model.

	`extra='forbid'` means a client that still sends the old field is refused, so this also pins
	that no shipped client can keep computing the dose itself and have it silently accepted.
	"""
	from afya.service import build_services, create_app

	app = create_app(build_services())
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		ok = await c.post('/medicine/dose', json={'drug': 'paracetamol', 'weight_kg': 20.0})
		assert ok.status_code == 200
		body = ok.json()
		assert (body['mg_low'], body['mg_high']) == (200.0, 300.0)
		old = await c.post('/medicine/dose',
		                   json={'drug': 'paracetamol', 'weight_kg': 20.0, 'mg_per_kg': 15.0})
		assert old.status_code == 422


def test_the_answer_is_a_range_not_a_midpoint() -> None:
	"""§MED-003 says "Get dose range". A midpoint is a number no guideline states, and a prescriber
	reading one has no way to know which end of the range it came from."""
	out = _dose(drug='paracetamol', weight_kg=20.0)
	assert out.mg_low == 200.0 and out.mg_high == 300.0  # type: ignore[attr-defined]
	assert out.mg_low != out.mg_high  # type: ignore[attr-defined]


def test_a_syrup_is_measured_and_a_tablet_is_counted() -> None:
	"""A person holding a 5 ml spoon should not have to divide a milligram figure by the strength
	printed on the bottle. That division is the calculator's whole job."""
	out = _dose(drug='paracetamol', weight_kg=20.0)
	by_unit = {line.unit for line in out.lines}  # type: ignore[attr-defined]
	assert by_unit == {'ml', 'tablet'}
	ml = next(line for line in out.lines if line.unit == 'ml')  # type: ignore[attr-defined]
	# 200 mg at 120 mg/5 ml is 8.3 ml; 300 mg is 12.5 ml.
	assert (ml.amount_low, ml.amount_high) == (8.3, 12.5)
	assert (ml.amount_mg_low, ml.amount_mg_high) == (200.0, 300.0)


def test_an_unknown_name_is_an_answer_not_an_exception() -> None:
	"""A parent who mistyped a medicine name needs to be told so, and a 500 tells them nothing."""
	out = _dose(drug='unobtainium', weight_kg=20.0)
	assert out.unknown is True  # type: ignore[attr-defined]
	assert out.mg_low is None  # type: ignore[attr-defined]
	assert any('pharmacist' in w for w in out.warns)  # type: ignore[attr-defined]


def test_a_weight_outside_the_sources_range_is_warned_about_both_ways() -> None:
	"""The Pocket Book is a hospital-care manual for children under five. Extrapolating below its
	tables or above its range is the two directions a paediatric dose goes wrong."""
	low = _dose(drug='paracetamol', weight_kg=2.0)
	assert any('start at' in w for w in low.warns)  # type: ignore[attr-defined]
	high = _dose(drug='paracetamol', weight_kg=60.0)
	assert any('stop at' in w for w in high.warns)  # type: ignore[attr-defined]


def test_zinc_refuses_without_an_age_rather_than_picking_a_band() -> None:
	"""The one drug whose dose the source keys on age. Defaulting to either band would dose a
	six-month-old at the toddler amount or the reverse."""
	out = _dose(drug='zinc', weight_kg=12.0)
	assert out.lines == []  # type: ignore[attr-defined]
	assert any('age' in w for w in out.warns)  # type: ignore[attr-defined]
	infant = _dose(drug='zinc', weight_kg=7.0, age_months=3)
	assert infant.lines[0].amount_mg_low == 10.0  # type: ignore[attr-defined]
	toddler = _dose(drug='zinc', weight_kg=12.0, age_months=18)
	assert toddler.lines[0].amount_mg_low == 20.0  # type: ignore[attr-defined]


def test_artemether_lumefantrine_returns_a_tablet_count_not_a_milligram_figure() -> None:
	"""The source states it as whole tablets for a fixed-strength combined tablet. A mg/kg figure
	derived from a tablet count would be a precision the formulation does not have."""
	out = _dose(drug='coartem', weight_kg=10.0)
	line = out.lines[0]  # type: ignore[attr-defined]
	assert line.unit == 'tablet' and line.amount_low == 1
	assert line.amount_mg_low is None
	assert (out.days_low, out.days_high) == (3, 3)  # type: ignore[attr-defined]


def test_ors_is_a_volume_and_carries_no_milligram_dose() -> None:
	"""Computing mg/kg for a rehydration salt would be a category error."""
	out = _dose(drug='ors', weight_kg=9.0, age_months=12)
	assert out.mg_low is None and out.mg_high is None  # type: ignore[attr-defined]
	assert (out.after_each_stool_ml_low, out.after_each_stool_ml_high) == (50.0, 100.0)  # type: ignore[attr-defined]
	assert out.maintenance_ml_per_kg_per_hour == 5.0  # type: ignore[attr-defined]
	older = _dose(drug='ors', weight_kg=14.0, age_months=36)
	assert older.after_each_stool_ml_low == 100.0  # type: ignore[attr-defined]


def test_a_warning_added_after_the_result_is_built_survives() -> None:
	"""The bug this file's first run found, pinned so it cannot come back.

	pydantic v2 copies a list on validation, so `warns.append(...)` on the *local* list after
	`DoseResult(...)` wrote to a list the model no longer held — six warnings vanished silently and
	the zinc-without-an-age case returned an empty result with no explanation at all. Asserting on
	the served model rather than the local variable is the only way this shows up.
	"""
	out = _dose(drug='zinc', weight_kg=12.0)
	assert len(out.warns) == 1  # type: ignore[attr-defined]
	assert out.warns is not None  # type: ignore[attr-defined]
	# And the model's list is its own: mutating a fresh local must not reach it.
	probe = _dose(drug='paracetamol', weight_kg=2.0)
	assert len(probe.warns) >= 2  # type: ignore[attr-defined]


def test_the_canary_a_caller_supplied_constant_is_refused_by_the_model() -> None:
	"""Canary for `test_the_route_takes_no_mg_per_kg`: if `mg_per_kg` were ever re-added to
	`DoseRequest`, this fails and says so rather than the gate quietly passing on a field that no
	longer exists."""
	assert 'mg_per_kg' not in DoseRequest.model_fields
	assert 'total_mg' not in __import__('afya.medicine.views', fromlist=['DoseResult']).DoseResult.model_fields
