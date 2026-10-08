"""i18n string tables (en / sw) for USSD menus, SMS and triage recommendations (spec §6 content)."""

USSD_MENU: dict[str, str] = {
	'en': 'CON Afya Yangu\n1. Ebola info\n2. Find facility\n3. Report symptoms\n4. Hotline 719',
	'sw': 'CON Afya Yangu\n1. Habari za Ebola\n2. Tafuta kituo cha afya\n3. Ripoti dalili\n4. Mstari wa dharura 719',
}

TRIAGE_RECS: dict[str, dict[str, str]] = {
	'en': {
		'low': 'Monitor; standard hygiene; hydrate; call 719 if worsening.',
		'malaria_suspect': 'Febrile illness: test and treat for malaria FIRST (spec 6.3 malaria trap); call 719 if no improvement in 48h.',
		'medium': 'Contact hotline 719; self-monitor; isolate from household if symptoms progress.',
		'high': 'Isolate immediately; call 719; go to nearest isolation treatment unit.',
	},
	'sw': {
		'low': 'Dumisha usafi wa kawaida; endelea kunywa maji; piga 719 kama unazidi kuwa mgonjwa.',
		'malaria_suspect': 'Ukiwa na homa: pimwa na kutibu malaria KWANZA (spec 6.3); piga 719 kama hakuna bora katika saa 48.',
		'medium': 'Wasiliana na 719; jiekeze; jitenge na kaya kama dalili zinazidi.',
		'high': 'Tenga wewe mwenyewe sasa hivi; piga 719; nenda kituo cha matibabu cha karibu.',
	},
}

SUPPORTED_LANGS: frozenset[str] = frozenset({'en', 'sw'})


def rec(lang: str, risk: str) -> str:
	assert lang in SUPPORTED_LANGS, f'unsupported lang {lang}'
	return TRIAGE_RECS[lang][risk]