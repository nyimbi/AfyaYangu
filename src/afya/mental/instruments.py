"""PHQ-9 and GAD-7: the item banks, the response scale, and the scoring cut-points.

§REC-005's first bullet is "PHQ-9 and GAD-7 screenings (validated, localised)", and `afya.mental`
carried **WHO-5** instead — five positional 0–5 scores with no item text at all. That is a different
instrument with different cut-points (`sources/INDEX.md` says so in as many words), and a screening
whose items are never shown cannot be localised: a person answering item 3 needs to read item 3 in a
language they have, and `WHO5.scores[2]` is a number nobody can be asked.

Everything here is transcribed from the archived primary sources, not from a summary:

* `sources/phq9-gad7/PHQ-9_English.pdf` and `GAD-7_English.pdf` — the item text and the response
  scale, verbatim.
* `sources/phq9-gad7/PHQ-9_Kiswahili.pdf` — the nine Kiswahili items and the four translated options.
* `sources/phq9-gad7/instructions.pdf` — the cut-points. PHQ-9's are Table 4, p. 6; GAD-7's are
  stated on pp. 6–7 with the recommended further-evaluation threshold of 10.

**GAD-7 has no Kiswahili form.** That is the publisher's gap, not this repo's: the language listing
carries Afrikaans through Urdu and Swahili is not on it (the enumeration and its derivation are in
`sources/INDEX.md`). The alternative to saying so is administering English items under a Kiswahili
label, which returns a score from a person who could not read the questions — so the service refuses
that combination by name rather than silently serving it.

**Licence.** The instruments state "No permission required to reproduce, translate, display or
distribute", and the Kiswahili form carries the same sentence translated, so reproducing the items
here is what the publisher asks for rather than something tolerated.

**Item 9 is the exception to scoring.** PHQ-9's ninth item asks about being better off dead or
hurting yourself, and a total that lands in a low band with a positive item 9 is a person at risk
who a band would wave through. It is scored like every other item and it is *also* read on its own.
"""

# The four response options, in the instrument's own order and wording. The scores are positional,
# so the option list and the scoring rule cannot drift apart without this file failing its own test.
RESPONSE_OPTIONS: dict[str, tuple[str, ...]] = {
	'en': ('Not at all', 'Several days', 'More than half the days', 'Nearly every day'),
	'sw': ('Haijatoke kabisa', 'Siku kadhaa', 'Zaidi ya nusu ya siku hizo', 'Takriban kila siku'),
}

# "Over the last 2 weeks" is the window both instruments ask about, and it is not decoration: a score
# is a claim about a fortnight, so the record dates the administration and the band is read against
# that date rather than against "now".
TIMEFRAME: dict[str, str] = {
	'en': 'Over the last 2 weeks, how often have you been bothered by the following problems?',
	'sw': 'Katika kipindi cha wiki mbili zilizopita ni mara ngapi umesumbuliwa na matatizo haya yafuatayo?',
}

# --- The item banks ---------------------------------------------------------------------------

PHQ9_ITEMS: dict[str, tuple[str, ...]] = {
	'en': (
		'Little interest or pleasure in doing things',
		'Feeling down, depressed, or hopeless',
		'Trouble falling or staying asleep, or sleeping too much',
		'Feeling tired or having little energy',
		'Poor appetite or overeating',
		'Feeling bad about yourself — or that you are a failure or have let yourself or your family down',
		'Trouble concentrating on things, such as reading the newspaper or watching television',
		'Moving or speaking so slowly that other people could have noticed? Or the opposite — being so '
		'fidgety or restless that you have been moving around a lot more than usual',
		'Thoughts that you would be better off dead or of hurting yourself in some way',
	),
	'sw': (
		'Kutokuwa na hamu au raha ya kufanya kitu',
		'Kujisikia tabu sana au kukata tamaa',
		'Matatizo ya kupata usingizi au kuweza kulala au kulala sana',
		'Kujisikia kuchoka au kutokuwa na nguvu',
		'Kutokuwa na hamu ya kula au kula sana',
		'Kujisikia vibaya — au kujiona kuwa umeshindwa kabisa au umejiangusha au kuikatisha tama familia yako',
		'Matatizo ya kuwa makini kwa mfano unaposoma gazeti au kuangalia TV',
		'Kutembea au kuongea taratibu sana mpaka watu wakawa wameona tofauti? Au kinyume chake kwamba '
		'hutulizani na unahangaika sana kuliko ilivyo kawaida',
		'Mawazo kuwa ni afadhali zaidi ufe au ujidhuru kwa namna fulani',
	),
}

# GAD-7 is English-only: the publisher ships no Kiswahili form, and a translated-by-us instrument
# would be the one thing a screening must not be — a scale nobody validated, wearing a validated
# instrument's name. `afya.mental` serves the English items for `sw` and says that is what it did.
GAD7_ITEMS: dict[str, tuple[str, ...]] = {
	'en': (
		'Feeling nervous, anxious or on edge',
		'Not being able to stop or control worrying',
		'Worrying too much about different things',
		'Trouble relaxing',
		'Being so restless that it is hard to sit still',
		'Becoming easily annoyed or irritable',
		'Feeling afraid as if something awful might happen',
	),
}

ITEM_BANKS: dict[str, dict[str, tuple[str, ...]]] = {'phq9': PHQ9_ITEMS, 'gad7': GAD7_ITEMS}

# The one language each instrument has a publisher-supplied form in. A request outside this set is
# answered in English with the substitution named, never with the requested language's label on
# English items.
AVAILABLE_LANGS: dict[str, tuple[str, ...]] = {'phq9': ('en', 'sw'), 'gad7': ('en',)}

# --- Scoring ----------------------------------------------------------------------------------
#
# The bands are the manual's, and the manual's Table 4 also proposes treatment actions per band.
# Those are proposals for a clinician and this module does not carry them: `afya.mental` triages and
# routes, it does not prescribe, and a drug name in a self-check response is a prescription nobody
# wrote. The advice strings below say what to do next, which is what a screening can honestly say.

# The ceilings are the *top* of each band, so 4 closes `none_minimal` and 5 opens `mild`. Writing
# the cut-points themselves here (5, 10, 15, 20) reads as if 5 were still `none_minimal`, which is
# the off-by-one this table had until a boundary test caught it: the manual's Table 4 prints 0–4
# None-minimal and 5–9 Mild, and "scores of 5, 10, 15 and 20 represent cutpoints for mild, moderate,
# moderately severe and severe" is a statement about where each band *starts*.
PHQ9_BANDS: tuple[tuple[int, str], ...] = ((4, 'none_minimal'), (9, 'mild'), (14, 'moderate'),
                                           (19, 'moderately_severe'), (27, 'severe'))
GAD7_BANDS: tuple[tuple[int, str], ...] = ((4, 'minimal'), (9, 'mild'), (14, 'moderate'),
                                           (21, 'severe'))

# GAD-7's cut-points are severity bands *and* a referral threshold, and they are different numbers:
# 5/10/15 grade the severity, and the manual's recommended cut-point "for further evaluation" is 10.
# Reporting a 7 as "mild" is right; reporting it as needing evaluation is not, so the two are
# separate fields rather than one band doing double duty.
GAD7_FURTHER_EVALUATION_AT = 10

# PHQ-9's functional-impairment question is unnumbered and unscored — it is asked after the nine and
# never added in. It is carried so the client can render it, and it is deliberately absent from
# `PHQ9_ITEMS` so that nothing can sum it by accident.
PHQ9_IMPAIRMENT_QUESTION: dict[str, str] = {
	'en': 'If you checked off any problems, how difficult have these problems made it for you to do '
	      'your work, take care of things at home, or get along with other people?',
	'sw': 'Kama ulitia alama matatizo yoyote, matatizo hayo yamefanye iwe vigumu kivipi kwako kufanya '
	      'kazi yako, kushughulikia vitu nyumbani, au kutangamana na watu wengine?',
}

# Item 9's follow-up. The manual cites the P4 screener (Dube et al.) for what to ask next when item 9
# is positive; the four questions are not reproduced here because the P4 itself is not archived, and
# inventing four questions and calling them P4 is the failure this file exists to avoid. What is
# implemented is the part the archived sources do support: item 9 above zero is never a band, always
# a crisis line and a referral.
SUICIDE_RISK_ITEM = 9


def max_total(instrument: str) -> int:
	"""The highest score the instrument can produce — nine items of 0–3, or seven.

	Derived from the item bank rather than written as 27 and 21, because the two constants are the
	same fact stated twice and only one of them is checked when someone edits the items.
	"""
	assert instrument in ITEM_BANKS, f'unknown instrument {instrument}'
	return len(ITEM_BANKS[instrument]['en']) * (len(RESPONSE_OPTIONS['en']) - 1)


def bands_for(instrument: str) -> tuple[tuple[int, str], ...]:
	"""The cut-point table for one instrument. Keyed lookup so an unknown name fails here."""
	assert instrument in ITEM_BANKS, f'unknown instrument {instrument}'
	return PHQ9_BANDS if instrument == 'phq9' else GAD7_BANDS


def band_of(instrument: str, total: int) -> str:
	"""The severity band a total falls in — the first row whose ceiling the total does not exceed.

	The ceilings are upper bounds, so the table is walked in order. A total of exactly 10 is
	`moderate`, not `mild`: the cut-point belongs to the band it opens, which is what "scores of 5,
	10, 15 and 20 represent cutpoints for mild, moderate, moderately severe and severe" means read as
	intervals — 5–9 Mild, 10–14 Moderate, and so on.
	"""
	assert 0 <= total <= max_total(instrument), f'total {total} outside {instrument} range'
	for ceiling, name in bands_for(instrument):
		if total <= ceiling:
			return name
	return bands_for(instrument)[-1][1]
