"""i18n string tables (en / sw) for USSD menus, SMS and triage recommendations (spec §6 content).

§ACC-002 names six languages for voice-guided symptom reporting — Swahili, Dholuo, Luhya, Kalenjin,
Kikuyu and English — and `LANGUAGE_MATRIX` puts the first five of those at tier 1. Only `en` and
`sw` have string tables here, so `rec()` raises for the rest and the triage route answers **500**:
a caller asking for a language §ACC-002 requires gets a stack trace, not an answer. `luo` is the
sharp one — §CHAN-2's own USSD menu ends "Language: English / Kiswahili / Dholuo / ...", so the
menu offers what the handler cannot do, and §4.1's Persona F (Grace, Siaya, feature phone) is the
person it happens to.

`SUPPORTED_LANGS` is the set with *tables*; `answerable()` is the set the product can answer in.
They differ by a fallback, not by a claim: a language with no table is served English and told so,
rather than served a string that pretends to be Dholuo. A machine-translated table would report the
gap as closed — which is the failure mode this whole file is written to avoid, since a wrong
recommendation at a triage boundary is worse than an honest English one.
"""

# `USSD_MENU` is rendered from `USSD_TREE` further down, so the served menu and the walkable tree
# are one fact rather than two strings kept in step by hand.

# The keys are `RiskLevel`'s members, and they are six because §8.1 prints five classifications and
# one of them — High — is two: Ebola suspicion and other cause. The tables carried four keys with a
# single `high`, so the recommendation could not say which of the two the person was in, and the
# section's own distinction between isolation-and-notify and seek-care-today had no string behind it.
TRIAGE_RECS: dict[str, dict[str, str]] = {
	'en': {
		'low': 'Monitor; standard hygiene; hydrate; call 719 if worsening.',
		'malaria_suspect': 'A fever in Kenya is most often malaria. Test and treat for malaria first; call 719 if there is no improvement in 48 hours.',
		'medium': 'Contact hotline 719; self-monitor; isolate from household if symptoms progress.',
		'high_other': 'Seek care today at the nearest facility; call 719 if you cannot get there.',
		'high_ebola_suspicion': 'Isolate yourself now, away from the household. Call 719 and say you may have had contact with Ebola. Do not travel by public transport.',
		'emergency': 'Emergency. Call 719 now and stay where you are. Do not travel alone. If there is bleeding, press firmly on it and keep the person still.',
	},
	'sw': {
		'low': 'Dumisha usafi wa kawaida; endelea kunywa maji; piga 719 kama unazidi kuwa mgonjwa.',
		'malaria_suspect': 'Homa nchini Kenya mara nyingi ni malaria. Pimwa na kutibu malaria kwanza; piga 719 kama hakuna bora katika saa 48.',
		'medium': 'Wasiliana na 719; jiekeze; jitenge na kaya kama dalili zinazidi.',
		'high_other': 'Nenda kupata matibabu leo katika kituo cha karibu; piga 719 kama huwezi kufika.',
		'high_ebola_suspicion': 'Jitenge sasa hivi, mbali na kaya. Piga 719 na useme huenda umegusana na Ebola. Usisafiri kwa usafiri wa umma.',
		'emergency': 'Dharura. Piga 719 sasa hivi na ubaki mahali ulipo. Usisafiri peke yako. Kama kuna kutokwa na damu, kanda kwa nguvu na umtulize mgonjwa.',
	},
}

# The languages with a table. Kept as the narrow set on purpose: widening it is what would let a
# language be reported as served when nothing was translated.
SUPPORTED_LANGS: frozenset[str] = frozenset(TRIAGE_RECS)


def answerable(lang: str) -> str:
	"""The language this request will actually be answered in.

	Every language §ACC-002 lists is accepted — refusing one would turn a content gap into a broken
	channel, and a person on a feature phone cannot act on a 422. What is not accepted is silence
	about it: the caller is told which language it got, so a Dholuo speaker is answered in English
	*and knows it*, rather than reading English believing it is Dholuo.
	"""
	assert isinstance(lang, str) and lang, 'lang required'
	return lang if lang in SUPPORTED_LANGS else 'en'


def rec(lang: str, risk: str) -> str:
	"""The triage recommendation, in `lang` where a table exists and in English where it does not.

	The caller can tell which it got — `TriageResult.served_in` reports the language the answer is
	actually in — so the fallback is visible in the payload instead of being an English string a
	client renders as Dholuo.
	"""
	assert risk in TRIAGE_RECS['en'], f'unknown risk level {risk}'
	return TRIAGE_RECS[answerable(lang)][risk]


# §CHAN-2's USSD menu as a structure rather than as a one-line string.
#
# The section draws a five-item tree — "1. Report symptoms" with a five-way submenu, "2. Find a
# clinic near me", "3. Health information" with three questions, "4. Request a CHW visit",
# "5. Language" — and the code served a flat four-item menu instead: "1. Ebola info / 2. Find
# facility / 3. Report symptoms / 4. Hotline 719". The two disagree on the count, on the order, and
# on what the first item is, and the section's own integration note ("reports flow into the same
# backend as app and WhatsApp reports") is about the symptom path, which the flat menu put third.
#
# `USSD_TREE` carries the section's structure; `USSD_MENU` is rendered from it so the served menu
# and the walkable tree cannot drift. The prompt strings are the section's own words.
USSD_SYMPTOM_PROMPT: dict[str, str] = {
	'en': 'Reply with the number of your symptom:',
	'sw': 'Jibu kwa namba ya dalili yako:',
}

# §CHAN-2's symptom submenu, verbatim and in order. The keys are what the engine is told; the
# labels are what the person reads. "Other" carries no symptom, which is honest: a caller with
# something not on the list has named nothing the engine knows.
USSD_SYMPTOMS: tuple[tuple[str, str], ...] = (
	('fever', 'Fever'), ('cough', 'Cough'), ('diarrhoea_vomiting', 'Diarrhoea / vomiting'),
	('bleeding', 'Bleeding'), ('other', 'Other'),
)

# Which engine symptom each submenu entry reports. `cough` and `other` map to nothing: the engine's
# vocabulary is §8.1's febrile set and neither is in it. `diarrhoea_vomiting` is the section's
# combined entry and the engine has two words for it, so both are named.
USSD_SYMPTOM_MAP: dict[str, tuple[str, ...]] = {
	'fever': ('fever',), 'cough': (), 'diarrhoea_vomiting': ('diarrhoea', 'vomiting'),
	'bleeding': ('bleeding',), 'other': (),
}

# §CHAN-2's top-level menu, as (label, children). A child list is a submenu; an empty one is a leaf
# the handler answers directly. Item 5 is the language selection, which the section ends with "..."
# because it names four languages and leaves the list open — the open end is recorded, not closed.
USSD_TREE: tuple[tuple[str, tuple[str, ...]], ...] = (
	('Report symptoms', tuple(label for _, label in USSD_SYMPTOMS)),
	('Find a clinic near me', ()),
	('Health information', ('What is Ebola?', 'How do I protect my family?', 'Is it safe to travel?')),
	('Request a CHW visit', ()),
	('Language: English / Kiswahili / Dholuo / ...', ()),
)

# The languages §CHAN-2's fifth item names, plus the "..." the section leaves open. `SUPPORTED_LANGS`
# is the pair with tables; this is the section's list, so the two are different facts and the gap
# between them is what §ACC-002's fallback exists for.
USSD_LANGUAGES: tuple[str, ...] = ('English', 'Kiswahili', 'Dholuo')

# The section's own session budget: "2 USSD sessions (approx. 360 characters)".
USSD_SESSION_LIMIT_CHARS: int = 360

# §CHAN-2's "→" prompts. They are children of their items — the first two of the symptom path, the
# third of the clinic lookup — and the two yes/no ones are what a flat menu loses entirely. Carried
# as data because §CHAN-2's symptom path ends by asking whether to send a location and whether to
# request a callback, and a report that neither asks for is a report no one follows up.
USSD_YES_NO_PROMPTS: tuple[str, ...] = ('→ Send my location? 1=Yes 2=No', '→ Request callback? 1=Yes 2=No')


# §CHAN-2's labels are English in the section, and the served menu is localised. Both facts are
# kept: `USSD_TREE` is the structural authority and carries the section's own words so the spec
# comparison reads it, and `USSD_LABELS` maps those words to what a speaker of each language reads.
# Serving English labels to a Swahili speaker was a regression the first cut of this introduced —
# the structure was right and the menu was unreadable, which is the wrong half to get right on the
# one channel §4.1's feature-phone persona has.
USSD_LABELS: dict[str, dict[str, str]] = {
	'sw': {
		'Report symptoms': 'Ripoti dalili',
		'Find a clinic near me': 'Tafuta kituo cha afya karibu',
		'Health information': 'Habari za afya',
		'Request a CHW visit': 'Omba ziara ya mhudumu wa afya',
		'Language: English / Kiswahili / Dholuo / ...': 'Lugha: Kiingereza / Kiswahili / Dholuo / ...',
		'What is Ebola?': 'Ebola ni nini?',
		'How do I protect my family?': 'Ninalindaje familia yangu?',
		'Is it safe to travel?': 'Ni salama kusafiri?',
		'Fever': 'Homa', 'Cough': 'Kikohozi', 'Diarrhoea / vomiting': 'Kuhara / kutapika',
		'Bleeding': 'Kutokwa na damu', 'Other': 'Nyingine',
	},
}


def _label(text: str, lang: str) -> str:
	"""The label as `lang` reads it, or the section's own words where there is no table for it."""
	return USSD_LABELS.get(answerable(lang), {}).get(text, text)


def ussd_menu_text(lang: str) -> str:
	"""§CHAN-2's top-level menu, rendered from `USSD_TREE` so the tree and the served menu are one fact.

	The structure is the section's; the labels are localised where a table exists. A translated menu
	whose structure drifted from §CHAN-2 would be a different menu, so the labels are looked up from
	the tree rather than written beside it.
	"""
	assert len(USSD_TREE) == 5, '§CHAN-2 lists five top-level items'
	lines = [f'{i}. {_label(label, lang)}' for i, (label, _) in enumerate(USSD_TREE, 1)]
	return 'CON Afya Yangu\n' + '\n'.join(lines)


def ussd_symptom_menu_text(lang: str) -> str:
	"""§CHAN-2's symptom submenu, in the section's order."""
	head = USSD_SYMPTOM_PROMPT[answerable(lang)]
	lines = [f'{i}. {_label(label, lang)}' for i, (_, label) in enumerate(USSD_SYMPTOMS, 1)]
	return 'CON ' + head + '\n' + '\n'.join(lines)


# Rendered from the tree at import, so the string and the structure cannot disagree.
USSD_MENU: dict[str, str] = {
	'en': ussd_menu_text('en'),
	'sw': ussd_menu_text('sw'),
}


# §CHAN-2's non-symptom leaves, as answers. These carry no clinical claim, so they are text rather
# than an engine call — and none of them is a spec code.
USSD_MENU_ANSWERS: dict[str, dict[int, str]] = {
	'en': {
		2: 'Send your location on the app, or call 719 and ask for the nearest health facility.',
		3: 'Health information: 1. What is Ebola? 2. How do I protect my family? 3. Is it safe to travel?',
		4: 'A community health worker will visit you. Keep your phone reachable.',
		5: 'Languages: English, Kiswahili, Dholuo. Reply with the one you want.',
	},
	'sw': {
		2: 'Tuma mahali ulipo kwenye programu, au piga 719 uombe kituo cha afya cha karibu.',
		3: 'Habari za afya: 1. Ebola ni nini? 2. Ninalindaje familia yangu? 3. Ni salama kusafiri?',
		4: 'Mhudumu wa afya wa jamii atakufikia. Weka simu yako karibu.',
		5: 'Lugha: Kiingereza, Kiswahili, Dholuo. Jibu kwa unayotaka.',
	},
}

# §CHAN-2's health-information submenu, as answers. §INF-001's Ebola line is the first question's
# answer, so the two sections are one fact rather than two.
USSD_INFO_ANSWERS: dict[str, tuple[str, ...]] = {
	'en': (
		'Ebola spreads by direct contact with a sick person or a body. Wash hands often; do not touch. Call 719 if you have fever with bleeding.',
		'Protect your family: wash hands with soap, do not touch anyone who is sick or has died, and call 719 if fever starts.',
		'Travel: avoid areas with active cases and follow MoH advisories. Call 719 for the current list.',
	),
	'sw': (
		'Ebola huenea kwa kugusa mtu mgonjwa au mwili. Osha mikono mara kwa mara; usiguse. Piga 719 kama una homa na kutokwa na damu.',
		'Linda familia yako: osha mikono kwa sabuni, usiguse mgonjwa au aliyefariki, na piga 719 kama homa ianze.',
		'Safari: epuka maeneo yenye visa na fuata maelekezo ya Wizara ya Afya. Piga 719 kwa orodha ya sasa.',
	),
}

# The symptom words §CHAN-3's free-text bodies are read against. Kept as the narrow set the engine
# accepts: a body naming nothing here enters the engine with an empty symptom list and is answered
# at the low risk level, which is what "no symptom named" means.
SYMPTOM_WORDS: tuple[str, ...] = ('fever', 'headache', 'muscle_pain', 'sore_throat', 'vomiting', 'diarrhoea', 'rash', 'bleeding')

# §CHAN-3's other three intents, in the languages with a table. These carry no clinical claim, so
# they are text rather than an engine call — and none of them is a spec code.
WHATSAPP_FACILITY: dict[str, str] = {
	'en': 'Send your location on the app to find the nearest facility, or call 719 and ask.',
	'sw': 'Tuma mahali ulipo kwenye programu kupata kituo cha afya cha karibu, au piga 719 uombe.',
}
WHATSAPP_HOTLINE: dict[str, str] = {
	'en': 'Call 719 (toll-free, 24/7).',
	'sw': 'Piga 719 (bila malipo, saa 24).',
}
WHATSAPP_WELCOME: dict[str, str] = {
	'en': 'Welcome to Afya Yangu. Options: symptoms, facility, hotline.',
	'sw': 'Karibu Afya Yangu. Chaguo: dalili, kituo cha afya, mstari wa dharura.',
}