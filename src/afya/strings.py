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

USSD_MENU: dict[str, str] = {
	'en': 'CON Afya Yangu\n1. Ebola info\n2. Find facility\n3. Report symptoms\n4. Hotline 719',
	'sw': 'CON Afya Yangu\n1. Habari za Ebola\n2. Tafuta kituo cha afya\n3. Ripoti dalili\n4. Mstari wa dharura 719',
}

TRIAGE_RECS: dict[str, dict[str, str]] = {
	'en': {
		'low': 'Monitor; standard hygiene; hydrate; call 719 if worsening.',
		'malaria_suspect': 'A fever in Kenya is most often malaria. Test and treat for malaria first; call 719 if there is no improvement in 48 hours.',
		'medium': 'Contact hotline 719; self-monitor; isolate from household if symptoms progress.',
		'high': 'Isolate immediately; call 719; go to nearest isolation treatment unit.',
	},
	'sw': {
		'low': 'Dumisha usafi wa kawaida; endelea kunywa maji; piga 719 kama unazidi kuwa mgonjwa.',
		'malaria_suspect': 'Homa nchini Kenya mara nyingi ni malaria. Pimwa na kutibu malaria kwanza; piga 719 kama hakuna bora katika saa 48.',
		'medium': 'Wasiliana na 719; jiekeze; jitenge na kaya kama dalili zinazidi.',
		'high': 'Tenga wewe mwenyewe sasa hivi; piga 719; nenda kituo cha matibabu cha karibu.',
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