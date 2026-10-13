"""§INF-005's country advisories, as a table read off WHO's own risk assessment.

The audit row said the country half of "Country and county advisories" was **a constant rather than
a table**: `LocationService.advisory(destination, origin_country)` interpolated the two arguments
into one fixed paragraph and said the same thing about Kampala, Kinshasa and Kinshasa-from-Nairobi.
A traveller asking whether it is safe to cross at Busia was answered with a sentence that would have
been identical had the outbreak been in a different hemisphere.

**The table holds only what the source states, and it is short because the source is short.** WHO
publishes a *band per group of countries*, not a row per country: the Democratic Republic of the
Congo is very high, "countries sharing land borders with the Democratic Republic of the Congo" are
high, the rest of the African Region and the world are low. Three countries are then named
individually as being "of particular concern" inside the high band, and three more are named because
cases were detected or treated there. Every other country is `not_assessed`, which is a real verdict
and the only honest one: Burundi shares a land border with the DRC and has no row in the source, so
answering it "low" from the regional band would be exactly the kind of invented number
`sources/INDEX.md` exists to prevent.

**A traveller types a city.** `destination` is free text — "Kampala", "Busia", "Goma" — so the
resolver reports `matched=False` rather than guessing a country from a place name, and the report
carries WHO's advice for the countries it *does* name. An unrecognised destination is served as
unrecognised; it is never served as safe.

Sources: `sources/who-ebola-outbreak-news/` — see `sources/INDEX.md` for what each states and, as
importantly, what it does not.
"""
from typing import NamedTuple


class CountryRow(NamedTuple):
	"""One country WHO names, with the sentence it is named in.

	`stated` is the source's own words rather than a paraphrase, for the reason every other table in
	this tree keeps its provenance: a band with no sentence behind it is a number a reader cannot
	check, and the band for this outbreak moved twice in four months.
	"""
	iso2: str
	iso3: str
	name: str
	band: str
	stated: str


# WHO's own four-row risk table, 14 August 2026 (v4). Served as the report's context because it is
# the frame every country row is read in — and because it is the only place the "rest of the African
# Region" and "global" bands exist, which are bands for *groups* and cannot be resolved to a country.
WHO_RISK_TABLE: tuple[tuple[str, str, str], ...] = (
	('Democratic Republic of the Congo', 'very_high', 'Very High'),
	('Countries sharing land borders with the Democratic Republic of the Congo', 'high', 'High'),
	('Rest of the African Region', 'low', 'Low'),
	('Global', 'low', 'Low'),
)

# WHO's confidence in the assessment, printed beside the bands and carried for the reason the
# assessment is worth reading at all: the DRC and land-border rows are "Moderate" confidence, so a
# traveller is owed that alongside the band rather than a certainty the source does not claim.
WHO_CONFIDENCE: tuple[tuple[str, str], ...] = (
	('Democratic Republic of the Congo', 'moderate'),
	('Countries sharing land borders with the Democratic Republic of the Congo', 'moderate'),
	('Rest of the African Region', 'moderate'),
	('Global', 'high'),
)

VERY_HIGH, HIGH, MODERATE, LOW, NOT_ASSESSED, UNKNOWN = (
	'very_high', 'high', 'moderate', 'low', 'not_assessed', 'unknown')

# The bands a row may carry. This is the **union** of two vocabularies, and `PlaceAdvisory.kind`
# says which table a row came from: a country carries WHO's `very_high|high|low|not_assessed`, a
# Kenyan county carries §INF-001's `low|moderate|high`. They are not one scale and a client must
# not rank across them — "high" for a county and "high" for a land-border country are two different
# authorities' words — so the union exists for the model's pattern and the kind exists to keep them
# apart. `not_assessed` and `unknown` are this table's own two refusals: a country WHO did not name,
# and a place no table matches at all.
BANDS: tuple[str, ...] = (VERY_HIGH, HIGH, MODERATE, LOW, NOT_ASSESSED, UNKNOWN)

# What a band is called on a screen. Served into the localised sentence rather than the slug, for
# §ACC-002's reason: a traveller reading "very_high" is reading a field name.
BAND_LABELS: dict[str, str] = {
	VERY_HIGH: 'very high', HIGH: 'high', MODERATE: 'moderate', LOW: 'low',
	NOT_ASSESSED: 'not assessed', UNKNOWN: 'not assessed',
}

# The date of the assessment every country row is read from. Named once and served on each row: a
# risk band is a statement about a moment, and a payload that stamped it at serve time would present
# a 14 August assessment as this morning's.
ASSESSED_ON_ISO = '2026-08-14'

COUNTRIES: tuple[CountryRow, ...] = (
	CountryRow('CD', 'COD', 'Democratic Republic of the Congo', VERY_HIGH,
		'The risk in the Democratic Republic of the Congo was assessed as very high, the risk for '
		'countries sharing land borders with the Democratic Republic of the Congo was assessed as '
		'high, and the risks for the rest of the African region and at the global level was again '
		'assessed as low.'),
	CountryRow('UG', 'UGA', 'Uganda', HIGH,
		'Countries sharing land borders with the Democratic Republic of the Congo remain at risk '
		'because of frequent cross-border population movement. Uganda, the Central African Republic '
		'and South Sudan are of particular concern for importation given their proximity, high '
		'population mobility and connectivity with areas of the Democratic Republic of the Congo '
		'currently experiencing intense transmission.'),
	CountryRow('CF', 'CAF', 'Central African Republic', HIGH,
		'Countries sharing land borders with the Democratic Republic of the Congo remain at risk '
		'because of frequent cross-border population movement. Uganda, the Central African Republic '
		'and South Sudan are of particular concern for importation given their proximity, high '
		'population mobility and connectivity with areas of the Democratic Republic of the Congo '
		'currently experiencing intense transmission. For the Central African Republic and South '
		'Sudan, these risks are further compounded by high humanitarian needs, population '
		'displacement, insecurity and underlying limitations in health-system capacity.'),
	CountryRow('SS', 'SSD', 'South Sudan', HIGH,
		'Countries sharing land borders with the Democratic Republic of the Congo remain at risk '
		'because of frequent cross-border population movement. Uganda, the Central African Republic '
		'and South Sudan are of particular concern for importation given their proximity, high '
		'population mobility and connectivity with areas of the Democratic Republic of the Congo '
		'currently experiencing intense transmission. For the Central African Republic and South '
		'Sudan, these risks are further compounded by high humanitarian needs, population '
		'displacement, insecurity and underlying limitations in health-system capacity.'),
	# Kenya is the row this whole section is for, and WHO has not assessed it. The source says so in
	# its own words and names the reason: the assessment was still running when the notice was
	# published. Serving `low` here from the regional band would be the single most consequential
	# invented number in the table — it is the answer to the question every Kenyan user is asking.
	CountryRow('KE', 'KEN', 'Kenya', NOT_ASSESSED,
		'A detailed rapid risk assessment is currently ongoing to assess the risk in Kenya and will '
		'be reported once available.'),
	CountryRow('FR', 'FRA', 'France', LOW,
		'France reported a single imported BVD case on 24 June 2026, with no secondary transmission. '
		'The case was discharged on 4 July, and all five identified flight contacts completed the '
		'required 21-day follow-up period without developing symptoms. The 42-day enhanced '
		'monitoring period comes to an end on 15 August.'),
	CountryRow('DE', 'DEU', 'Germany', LOW,
		'Germany reported two BVD cases diagnosed in the Democratic Republic of the Congo and '
		'subsequently medically evacuated to Germany for treatment. Both patients recovered and were '
		'discharged on 6 June and 28 July, respectively. The cases were managed under strict '
		'infection prevention and control measures, and no secondary transmission was reported, '
		'therefore, no contacts were identified.'),
)

# Every spelling a client or a traveller may use, lowercased, pointing at the row above. Kept as an
# explicit map rather than a fuzzy match: "Congo" alone is two countries and guessing which one a
# traveller meant is a guess about where they are going.
ALIASES: dict[str, str] = {
	'democratic republic of the congo': 'CD', 'democratic republic of congo': 'CD',
	'dr congo': 'CD', 'drc': 'CD', 'congo (kinshasa)': 'CD', 'cd': 'CD', 'cod': 'CD',
	'uganda': 'UG', 'ug': 'UG', 'uga': 'UG',
	'central african republic': 'CF', 'car': 'CF', 'cf': 'CF', 'caf': 'CF',
	'south sudan': 'SS', 'ss': 'SS', 'ssd': 'SS',
	'kenya': 'KE', 'ke': 'KE', 'ken': 'KE',
	'france': 'FR', 'fr': 'FR', 'fra': 'FR',
	'germany': 'DE', 'de': 'DE', 'deu': 'DE',
}

# WHO's own advice on travel restrictions, verbatim, and it is the *whole* of the answer to "should
# I travel?": the source does not say "do not travel to X", it says countries should not close
# against each other. A product that turned this into a per-destination go/no-go would be answering
# a question the authority deliberately declined to answer.
WHO_TRAVEL_ADVICE = (
	'WHO advises against any restriction of travel to, or trade with, affected countries.'
)

# The companion sentence, and the reason the advice above is not a licence to ignore the outbreak.
WHO_BORDER_NOTE = (
	'Entry and exit health screening and surveillance measures are in place at airports, ports and '
	'official land border crossings; however, movement through informal border crossing routes may '
	'occur, presenting an ongoing risk of virus exportation, importation and onward transmission.'
)

# What the table cannot answer, served with every report. Same shape as §MED-002's pregnancy caveat:
# an absent row is not a reassurance, and a report that returned one silently would turn "WHO has
# not assessed this country" into "this country is fine".
NOT_ASSESSED_CAVEAT = (
	'WHO publishes its assessment for groups of countries, not for every country. A country with no '
	'row here has not been assessed in this notice — that is not the same as being assessed as low '
	'risk. Check the current advisory before you travel.'
)

# §INF-005's fourth Feature: "What to do if you feel unwell after travel". It was one fixed sentence
# inside the advisory paragraph. The steps below are the source's own, and each carries where it
# came from, because two of the five are WHO's and three are this deployment's own operating rule —
# and a traveller is owed the difference.
POST_TRAVEL_STEPS: tuple[tuple[str, str, str], ...] = (
	('monitor',
		'Monitor your health for 21 days after you return from an area with an ongoing Ebola '
		'outbreak.',
		'cdc-ebola-about'),
	('seek_care',
		'Seek medical care immediately if you develop symptoms of Ebola disease.',
		'cdc-ebola-about'),
	('symptoms',
		'The symptoms can be sudden and include fever, fatigue, malaise, muscle pain, headache and '
		'sore throat, followed by vomiting, diarrhoea, abdominal pain, rash, and symptoms of '
		'impaired kidney and liver functions.',
		'who-ebola-factsheet'),
	('call',
		'Call 719 and say where you travelled. Do not travel by public transport to reach care.',
		'deployment'),
	('declare',
		'Declare your arrival so the 21 days are recorded and you are asked how you feel on days 1, '
		'3, 7, 14 and 21.',
		'deployment'),
)

# What each step's source is, so the report can label a step WHO's or the deployment's rather than
# presenting five instructions as one authority's.
STEP_SOURCES: dict[str, str] = {
	'cdc-ebola-about': 'CDC, About Ebola Disease',
	'who-ebola-factsheet': 'WHO fact sheet, Ebola disease, 24 April 2025',
	'deployment': 'This deployment’s operating rule (not stated by either source)',
}

# The one fact in the whole section that runs the other way, and it is served because a traveller who
# reads only the bands would conclude the opposite: the source states that the risk to travellers as
# a group is low even while the outbreak is severe.
TRAVELLER_RISK_NOTE = (
	'The viruses that cause Ebola disease pose little risk to travelers or the general public. A '
	'person is only contagious once they begin showing symptoms, and the disease does not spread '
	'through the air.'
)

SOURCE_LABEL = 'WHO Rapid risk assessment, Ebola Bundibugyo virus disease, DRC, v4, 14 August 2026'


def canonical(place: str) -> str | None:
	"""The ISO-2 code for a country name or code, or None if this table has no row for it.

	`None` is the answer for a city, a misspelling and a country WHO did not name alike, because from
	here they are the same fact: nothing in the source addresses it. The caller reports the
	destination as unrecognised rather than falling through to a band.
	"""
	assert isinstance(place, str), 'place must be a string'
	key = ' '.join(place.strip().lower().split())
	return ALIASES.get(key)


def row_for(place: str) -> CountryRow | None:
	"""The source's row for a country, or None. See `canonical` for why None is not "low"."""
	code = canonical(place)
	if code is None:
		return None
	return next((c for c in COUNTRIES if c.iso2 == code), None)
