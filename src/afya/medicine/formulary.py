"""Paediatric dose reference — §MED-003's five formulations, from the WHO Pocket Book.

`dose` computed `weight_kg * mg_per_kg` and asked the *caller* for `mg_per_kg`. That is the one
number a person opens a dosing calculator to look up: a parent who already knew the mg/kg figure
for their child's medicine did not need the app, and a parent who did not could not use it. The
route answered a multiplication, not the question the section asks.

This module is the table. Each entry is a drug as the Pocket Book doses it — a low and a high
mg/kg figure where the source states a range, the formulation it is dispensed as, and the maximum
the source states, if it states one. `afya.medicine.service.dose` computes with it.

The numbers are reproduced here rather than read at runtime, for the reason
`afya.records.growth_standards` gives: no network egress inside a clinical calculation, and a
dosing table that can silently change under a running service is not a reference. The source PDF is
archived at `sources/who-pocket-book/` with its checksums and page references in `sources/INDEX.md`.

WHERE THE SOURCE STATES NO MAXIMUM, `max_mg_per_dose` IS `None`. The Pocket Book gives paracetamol
a *frequency* ceiling ("up to six times a day") and no mg/kg-per-day total, and gives amoxicillin
and zinc no maximum at all. A number invented to fill that column would be the most dangerous kind
of wrong — a limit a prescriber trusts that no guideline set — so the field stays empty and the
calculator warns on what the source does support.

ARTEMETHER–LUMEFANTRINE IS DOSED BY WEIGHT BAND, NOT BY MG/KG. The Pocket Book states it as
tablet counts for a fixed-strength combined tablet ("child weighing 5 – < 15 kg: one tablet twice a
day for 3 days"), so that is what this table returns for it. Its `mg_per_kg_low`/`high` are the
target the band achieves, recorded for the record and not used to compute a milligram dose — a
mg/kg figure derived from a tablet count would be a precision the formulation does not have.
"""
from typing import NamedTuple


class Formulation(NamedTuple):
	"""One dispensed form of a drug: what the pharmacy hands over, and how much is in it."""

	form: str
	strength: str
	# Milligrams in the unit the strength names — a tablet, or 5 ml of syrup. `None` where the
	# form's amount is not a fixed milligram figure a dose divides into (ORS is made up by volume).
	mg_per_unit: float | None = None
	# Millilitres per unit, for a liquid. A syrup's strength is "250 mg/5 ml", so one unit is 5 ml
	# and a dose in ml is the dose in mg divided by `mg_per_unit` times this.
	ml_per_unit: float | None = None


class WeightBand(NamedTuple):
	"""A dose stated as a count of a fixed-strength tablet, for a range of weights."""

	min_kg: float
	max_kg: float | None
	units_low: float
	units_high: float
	per_day: int


class PaediatricDose(NamedTuple):
	"""One drug as §MED-003's calculator needs it."""

	slug: str
	label: str
	aliases: tuple[str, ...]
	# The mg/kg range the source states. Equal low and high where the source gives one figure.
	mg_per_kg_low: float
	mg_per_kg_high: float
	# Doses per day the source states. A range where it gives one (ORS is not per-dose at all and
	# carries 0 here, because it is dosed by volume after each stool rather than on a schedule).
	doses_per_day_low: int
	doses_per_day_high: int
	formulations: tuple[Formulation, ...]
	# The source's own maximum, where it states one. `None` is a real answer: see the module note.
	max_mg_per_dose: float | None
	max_mg_per_day: float | None
	# The lowest weight the source's own tables start at. Below it the calculator refuses rather
	# than extrapolating downward, which is where a paediatric error is most dangerous.
	min_kg: float
	max_kg: float
	source_page: str
	# Set only for a drug dosed by weight band. Empty for the rest.
	bands: tuple[WeightBand, ...] = ()
	# A clause the source conditions the dose on, carried so a screen can print it. Empty where the
	# source states the dose unconditionally.
	note: str = ''


# --- the five the section names -------------------------------------------------------------------

PARACETAMOL = PaediatricDose(
	slug='paracetamol', label='Paracetamol',
	aliases=('paracetamol', 'acetaminophen', 'panadol', 'calpol'),
	mg_per_kg_low=10.0, mg_per_kg_high=15.0,
	doses_per_day_low=4, doses_per_day_high=6,
	formulations=(
		Formulation(form='tablet', strength='100 mg tablet', mg_per_unit=100.0),
		Formulation(form='tablet', strength='500 mg tablet', mg_per_unit=500.0),
		Formulation(form='syrup', strength='120 mg/5 ml syrup', mg_per_unit=120.0, ml_per_unit=5.0),
		Formulation(form='syrup', strength='250 mg/5 ml syrup', mg_per_unit=250.0, ml_per_unit=5.0),
	),
	# The source states "up to six times a day" and no milligram ceiling. Filling this would be
	# inventing the number a prescriber would most rely on.
	max_mg_per_dose=None, max_mg_per_day=None,
	min_kg=4.0, max_kg=35.0, source_page='Appendix 2, p. 367',
)

AMOXICILLIN = PaediatricDose(
	slug='amoxicillin', label='Amoxicillin',
	aliases=('amoxicillin', 'amoxil', 'amoxycillin'),
	mg_per_kg_low=25.0, mg_per_kg_high=40.0,
	doses_per_day_low=2, doses_per_day_high=2,
	formulations=(
		Formulation(form='tablet', strength='250 mg dispersible tablet', mg_per_unit=250.0),
		Formulation(form='syrup', strength='250 mg/5 ml syrup', mg_per_unit=250.0, ml_per_unit=5.0),
	),
	# No ceiling in the source. The 40 mg/kg figure is the pneumonia dose and the 25 mg/kg figure
	# the general one; both are per dose, twice a day, and the range carries that difference rather
	# than the calculator choosing between them.
	max_mg_per_dose=None, max_mg_per_day=None,
	min_kg=4.0, max_kg=35.0, source_page='Appendix 2, p. 357',
	note='25 mg/kg twice a day for mild illness; 40 mg/kg twice a day for pneumonia.',
)

ORS = PaediatricDose(
	slug='ors', label='ORS (oral rehydration salts)',
	aliases=('ors', 'oral rehydration salts', 'oral rehydration solution', 'rehydration'),
	# ORS is not dosed in mg/kg. It is a volume after each loose stool, plus a maintenance rate.
	mg_per_kg_low=0.0, mg_per_kg_high=0.0,
	doses_per_day_low=0, doses_per_day_high=0,
	formulations=(
		Formulation(form='sachet', strength='one sachet dissolved in 1 litre of clean water'),
	),
	max_mg_per_dose=None, max_mg_per_day=None,
	min_kg=0.0, max_kg=35.0, source_page='pp. 135–136',
	note='Not a milligram dose: give after each loose stool, and about 5 ml/kg per hour alongside '
	     'IV fluids while the child is rehydrating.',
)

ZINC = PaediatricDose(
	slug='zinc', label='Zinc',
	aliases=('zinc', 'zinc sulphate', 'zinc sulfate'),
	# Zinc is dosed as a fixed daily amount by age band, not by weight. Zero here rather than a
	# fabricated mg/kg, and the age rule lives in `ZINC_DAILY_MG`.
	mg_per_kg_low=0.0, mg_per_kg_high=0.0,
	doses_per_day_low=1, doses_per_day_high=1,
	formulations=(
		Formulation(form='tablet', strength='20 mg dispersible tablet', mg_per_unit=20.0),
	),
	max_mg_per_dose=None, max_mg_per_day=None,
	min_kg=0.0, max_kg=35.0, source_page='p. 134',
	note='Given by age, not by weight: half a tablet (10 mg) a day under 6 months, one tablet '
	     '(20 mg) a day from 6 months, for 10–14 days.',
)

ARTEMETHER_LUMEFANTRINE = PaediatricDose(
	slug='artemether-lumefantrine', label='Artemether–lumefantrine',
	aliases=('artemether-lumefantrine', 'artemether lumefantrine', 'coartem', 'al', 'act'),
	# The band target, recorded for the record. The dose returned is a tablet count: see the module
	# note on why a mg/kg figure is not derived from it.
	mg_per_kg_low=2.0, mg_per_kg_high=2.0,
	doses_per_day_low=2, doses_per_day_high=2,
	formulations=(
		Formulation(form='tablet', strength='20 mg artemether / 120 mg lumefantrine tablet',
		            mg_per_unit=20.0),
	),
	max_mg_per_dose=None, max_mg_per_day=None,
	min_kg=5.0, max_kg=35.0, source_page='p. 164',
	bands=(
		WeightBand(min_kg=5.0, max_kg=15.0, units_low=1, units_high=1, per_day=2),
		WeightBand(min_kg=15.0, max_kg=24.0, units_low=2, units_high=2, per_day=2),
		WeightBand(min_kg=25.0, max_kg=35.0, units_low=3, units_high=3, per_day=2),
	),
	note='Given twice a day for 3 days, as whole tablets for the weight band — not a milligram dose.',
)

PAEDIATRIC_FORMULARY: tuple[PaediatricDose, ...] = (
	PARACETAMOL, AMOXICILLIN, ORS, ZINC, ARTEMETHER_LUMEFANTRINE,
)

# §MED-003's "Enter weight and age" — age is a *threshold* for zinc, and nothing else in the source
# doses by age. Zinc's rule turns on six months, so the field is required for zinc and unused for
# the other four, which is a fact about the source rather than an omission here.
ZINC_MONTHS_THRESHOLD = 6
ZINC_MG_UNDER = 10.0
ZINC_MG_FROM = 20.0
ZINC_DAYS_LOW = 10
ZINC_DAYS_HIGH = 14

# The two fluids the calculator gives by volume rather than by milligram, from the same pages.
ORS_ML_PER_KG_MAINTENANCE = 5.0
ORS_ML_UNDER_2Y_LOW = 50.0
ORS_ML_UNDER_2Y_HIGH = 100.0
ORS_ML_FROM_2Y_LOW = 100.0
ORS_ML_FROM_2Y_HIGH = 200.0
ORS_TWO_YEAR_MONTHS = 24


def match(name: str) -> PaediatricDose | None:
	"""The formulary entry a free-text drug name refers to, or `None`.

	Matched on whole words, for the reason `essential_slug` gives: "act" is inside "contact" and a
	substring test would dose an antibiotic for a malaria tablet. A name that matches nothing is
	not in the formulary, which is a different answer from "no dose" and is what the caller
	reports.
	"""
	import re

	words = set(re.findall(r'[a-z0-9-]+', name.lower()))
	if not words:
		return None
	for entry in PAEDIATRIC_FORMULARY:
		for alias in entry.aliases:
			alias_words = set(re.findall(r'[a-z0-9-]+', alias))
			if alias_words and alias_words <= words:
				return entry
	return None
