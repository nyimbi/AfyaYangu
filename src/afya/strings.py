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


# --- §11.5 LOC-005's cross-border traveller strings ---------------------------------------------
#
# §LOC-005's sixth Feature is "multi-language support for cross-border travellers" and the reason it
# is a *traveller* bullet and not a restatement of §ACC-002 is that a border is where the language
# mix is widest and the person is least able to ask again: a Kenyan returning from Kampala may read
# Dholuo, a Ugandan trader crossing at Busia reads English or Kiswahili, and a Somali speaker at
# Mandera reads neither.
#
# These are **hand-written** strings for the two languages the repo already carries a table for, and
# they are the *whole* of what a traveller reads on this path — the advisory, the arrival
# acknowledgement and the post-arrival prompt. A language without a table is served English and told
# so, on the same reasoning as `answerable`: a wrong instruction at a point of entry is worse than
# an honest English one, and a machine-translated table would report the gap as closed.
TRAVELLER_STRINGS: dict[str, dict[str, str]] = {
	'en': {
		# §INF-005's first Feature is two advisories and the string was one sentence for every
		# pair of places — the audit row's "the country half is a constant rather than a table".
		# `{band}` and `{stated}` are the destination's own row from `afya.location.advisories`,
		# so the same question about two countries returns two answers. `{stated}` is the
		# authority's own words and is English in both tables: WHO publishes in English, and
		# translating a risk statement on the traveller's behalf is the machine-translation failure
		# this file's docstring refuses. The frame around it is localised.
		'advisory': (
			'Travel to {destination} from {origin_country}. Outbreak risk for {destination}: '
			'{band}. {stated} Screening may apply at the border. If you feel unwell after arrival, '
			'call 719 and say where you travelled. Health advisories change — confirm with official '
			'channels.'
		),
		'enrolled': (
			'Declaration recorded. You are enrolled for 21 days of self-monitoring — we will ask how '
			'you feel on days 1, 3, 7, 14 and 21. Call 719 sooner if you develop fever.'
		),
		'prompt': (
			'Day {day} of 21: how do you feel? Reply 1 if you have fever, 2 if you have any other '
			'symptom, 3 if you are well. Call 719 at once if you have bleeding or difficulty '
			'breathing.'
		),
		'well': 'Day {day} of 21 recorded, no warning signs. {remaining} days to go.',
		'warned': (
			'Day {day} of 21: {reason} recorded. Call 719 now and await instructions — do not travel '
			'by public transport.'
		),
	},
	'sw': {
		'advisory': (
			'Safari kwenda {destination} kutoka {origin_country}. Hatari ya mlipuko kwa {destination}: '
			'{band}. {stated} Uchunguzi unaweza kufanyika mpakani. Kama unajihisi mgonjwa baada ya '
			'kufika, piga 719 na useme uliposafiri. Matangazo ya afya hubadilika — thibitisha kwa '
			'njia rasmi.'
		),
		'enrolled': (
			'Tamko limehifadhiwa. Umeandikishwa kwa siku 21 za kujiangalia — tutakuuliza hali yako '
			'siku 1, 3, 7, 14 na 21. Piga 719 mapema zaidi ukipata homa.'
		),
		'prompt': (
			'Siku {day} kati ya 21: unajihisi vipi? Jibu 1 kama una homa, 2 kama una dalili nyingine, '
			'3 kama uko mzima. Piga 719 mara moja kama unatoka damu au unashindwa kupumua.'
		),
		'well': 'Siku {day} kati ya 21 imeandikwa, hakuna dalili za hatari. Siku {remaining} zimesalia.',
		'warned': (
			'Siku {day} kati ya 21: {reason} imeandikwa. Piga 719 sasa hivi na subiri maelekezo — '
			'usisafiri kwa usafiri wa umma.'
		),
	},
}


def traveller(lang: str, key: str, **fields: object) -> str:
	"""A §LOC-005 traveller string in `lang`, or in English where there is no table for it.

	`answerable` decides which, so the fallback rule is one function and not two that agree today.
	An unknown key raises rather than returning a placeholder: a missing string is a defect to fix,
	and a silent empty string is a screen that renders blank where an instruction should be.
	"""
	assert key in TRAVELLER_STRINGS['en'], f'unknown traveller string {key}'
	return TRAVELLER_STRINGS[answerable(lang)][key].format(**fields)


# --- §11.5 LOC-004's check-in follow-up strings -------------------------------------------------
#
# §LOC-004's fourth Behaviour bullet is that a check-in is *used*: attendance, a follow-up schedule
# and an exposure window. The schedule is a set of questions, and a question is a string — the same
# finding §LOC-005's `prompt` closed for a traveller, on the surface a person reaches by scanning a
# code at a gate. The days are the same days (§MON-009's 21-day window), so the sentence is the same
# sentence; what differs is the noun, and a school screening point is not a border post.
#
# The window's closing line says what the source says. The WHO fact sheet gives the incubation
# period as a range with a lower bound — "varies from 2 to 21 days" — and a line that promised the
# person they were clear would be this code making a claim the source does not. So the line reports
# the window's end and leaves the clinical reading to the person and to 719.
CHECKIN_STRINGS: dict[str, dict[str, str]] = {
	'en': {
		'prompt': (
			'Day {day} of 21: have you had a fever, a headache, muscle pain, vomiting or unusual '
			'bleeding? Call 719 at once if you have, and say where you checked in.'
		),
		'window_open': (
			'Your check-in at {place} on {day} opened a 21-day symptom watch. It has {remaining} '
			'days left, to {closes}. Call 719 if you feel unwell.'
		),
		'window_closed': (
			'The 21-day symptom watch from your check-in at {place} on {day} ended on {closes}. '
			'Call 719 if you feel unwell at any time.'
		),
		'no_checkins': (
			'No check-ins are on file, so nothing is being followed up. Scan the code at a check-in '
			'point to start.'
		),
		# Distinct from `no_checkins` because the two read identically on a screen and are different
		# facts: a person who scanned in at an office has a record and no watch, and telling them
		# nothing is on file contradicts the screen they are looking at.
		'no_watch': (
			'Your check-ins are on file. None of them is at a point that opens a symptom watch, so '
			'no follow-up is scheduled. Call 719 if you feel unwell.'
		),
	},
	'sw': {
		'prompt': (
			'Siku {day} kati ya 21: umekuwa na homa, kichwa kuuma, maumivu ya misuli, kutapika au '
			'kutoka damu isiyo ya kawaida? Piga 719 mara moja kama unayo, na useme ulipoingia.'
		),
		'window_open': (
			'Kuingia kwako katika {place} siku ya {day} kulianzisha kipindi cha siku 21 cha '
			'kufuatilia dalili. Zimesalia siku {remaining}, hadi {closes}. Piga 719 kama unajihisi '
			'mgonjwa.'
		),
		'window_closed': (
			'Kipindi cha siku 21 cha kufuatilia dalili kutoka kuingia kwako katika {place} siku ya '
			'{day} kiliisha {closes}. Piga 719 wakati wowote kama unajihisi mgonjwa.'
		),
		'no_checkins': (
			'Hakuna kuingia kulikorekodiwa, hivyo hakuna kinachofuatiliwa. Skani msimbo katika kituo '
			'cha kuingia ili kuanza.'
		),
		'no_watch': (
			'Kuingia kwako kumerekodiwa. Hakuna kulikofanyika katika kituo kinachofungua kipindi cha '
			'kufuatilia dalili, hivyo hakuna ufuatiliaji uliopangwa. Piga 719 kama unajihisi mgonjwa.'
		),
	},
}


def checkin(lang: str, key: str, **fields: object) -> str:
	"""A §LOC-004 check-in string in `lang`, or in English where there is no table for it.

	The same rule as `traveller` above and for the same reason: `answerable` is one function, so the
	fallback cannot differ between two paths that both serve a person at a gate. An unknown key
	raises — a missing string is a screen that renders blank where a question should be.
	"""
	assert key in CHECKIN_STRINGS['en'], f'unknown check-in string {key}'
	return CHECKIN_STRINGS[answerable(lang)][key].format(**fields)


# §LOC-001's **Alert content** is printed in the spec as one exact sentence and it had no home: the
# geofence route emitted a near-verbatim line built inline, nothing resolved to it, and the section's
# own `[specific location]` placeholder was replaced by the words "the named location" — so the one
# thing the alert is for, telling a person *which* place to avoid, was the part the string dropped.
#
# `{place}` is therefore the zone's own label and not a stand-in. The fallback is deliberately the
# section's own words rather than a second sentence: a zone registered without a label says so,
# instead of naming a location it does not have.
GEOFENCE_ALERT_STRINGS: dict[str, dict[str, str]] = {
	'en': {
		'alert': (
			'You have entered an area where a case was reported. Avoid {place}. Monitor for symptoms '
			'for 21 days. Call 719 if you feel unwell.'
		),
		# The fallback when a zone has no label, and it names the county rather than a placeholder:
		# §LOC-001's Alert content is "Avoid [specific location]" and the bracket is the one part of
		# the sentence a person acts on, so "avoid the named location" tells someone to avoid a thing
		# the alert declined to name — the defect the audit row records, reproduced as the fallback.
		'no_place': 'the area covered by this alert',
		'no_place_county': 'the area this alert covers in {county} County',
		# The entry/exit half of the Tier 4 behaviour, and the two directions are not the same news:
		# an exit is not "you are safe", it is that the zone's boundary was crossed and the 21-day
		# window that started on entry is still running.
		# The alert already opens with "You have entered an area where a case was reported", so an
		# entry template that says it again prints the section's sentence twice. The alert *is* the
		# entry message; the key stays so a client-side prefix has somewhere to go without editing the
		# section's own words.
		'entry': '{alert}',
		'exit': (
			'You have left {place}. The 21-day symptom watch that started when you entered is still '
			'running — keep monitoring and call 719 if you feel unwell.'
		),
		# §LOC-001's Privacy line — "Only entry/exit events logged, and only with consent" — said to
		# the person rather than only checkable in the payload. A person who turned alerts off is owed
		# the fact that nothing was kept, and a person who left them on is owed the fact that
		# something was: both are answers to "what do you know about where I have been".
		'not_logged': (
			'Your entry was not recorded. Alerts are off, so nothing about where you go is kept on '
			'this phone or sent anywhere.'
		),
		'logged': 'Your entry was recorded on this phone so the 21-day window can be followed up.',
	},
	'sw': {
		'alert': (
			'Umeingia eneo ambalo kesi iliripotiwa. Epuka {place}. Fuatilia dalili kwa siku 21. Piga '
			'719 kama unajihisi mgonjwa.'
		),
		'no_place': 'eneo linalohusika na tahadhari hii',
		'no_place_county': 'eneo linalohusika na tahadhari hii katika Kaunti ya {county}',
		'entry': '{alert}',
		'exit': (
			'Umetoka {place}. Kipindi cha siku 21 cha kufuatilia dalili kilichoanza ulipoingia '
			'kinaendelea — endelea kujiangalia na piga 719 kama unajihisi mgonjwa.'
		),
		'not_logged': (
			'Kuingia kwako hakukurekodiwa. Tahadhari zimezimwa, hivyo hakuna kinachohifadhiwa '
			'kuhusu unakoenda kwenye simu hii wala kutumwa popote.'
		),
		'logged': 'Kuingia kwako kulirekodiwa kwenye simu hii ili kipindi cha siku 21 kifuatiliwe.',
	},
}


def zone_place(lang: str, place_label: str | None = None, county: str = '') -> str:
	"""What §LOC-001's `[specific location]` resolves to for one zone.

	The section's bracket is the load-bearing part of the sentence: the one action it asks for is to
	avoid a particular place, and an alert that answered "the named location" asks a person to avoid
	something it did not name. So the label is used when the county health authority set one, and
	when it did not the alert narrows as far as the registry actually knows — the county — rather
	than to a phrase that names nothing. A zone with neither gets the section's own words said
	plainly, and `Geofence.place_label` being optional is what makes that reachable.
	"""
	assert isinstance(lang, str) and lang, 'lang required'
	table = GEOFENCE_ALERT_STRINGS[answerable(lang)]
	label = place_label.strip() if place_label and place_label.strip() else ''
	if label:
		return label
	return table['no_place_county'].format(county=county) if county else table['no_place']


def geofence_alert(lang: str, place_label: str | None = None, county: str = '') -> str:
	"""§LOC-001's Alert content, verbatim from the section, with the place resolved."""
	assert isinstance(lang, str) and lang, 'lang required'
	table = GEOFENCE_ALERT_STRINGS[answerable(lang)]
	return table['alert'].format(place=zone_place(lang, place_label, county))


def zone_privacy_note(lang: str, logged: bool) -> str:
	"""§LOC-001's Privacy line, addressed to the person rather than to a reader of the payload.

	Both answers are owed. A person who turned alerts off is told nothing was kept, and a person who
	left them on is told something was — a feature that said only the reassuring half would be
	describing the switch as a preference when it is a consent decision."""
	assert isinstance(lang, str) and lang, 'lang required'
	table = GEOFENCE_ALERT_STRINGS[answerable(lang)]
	return table['logged'] if logged else table['not_logged']


# §SEC-001's "consent audit log visible to the user" needs three sentences, and they are three
# because the three states are different facts: nothing has ever happened, something is on, and
# everything that was granted has been withdrawn. A single "here is your log" would make the second
# and third read the same on the screen where a person checks whether their withdrawal took.
CONSENT_HISTORY_STRINGS: dict[str, dict[str, str]] = {
	'en': {
		'none': 'You have not made any consent choices yet. Nothing is being kept or shared.',
		'live': 'These are your consent choices, most recent first. What is switched on now is listed below them.',
		'all_off': 'You have withdrawn everything you granted. Nothing is being kept or shared now.',
	},
	'sw': {
		'none': 'Bado hujafanya uamuzi wowote wa ridhaa. Hakuna kinachohifadhiwa au kushirikiwa.',
		'live': 'Haya ni maamuzi yako ya ridhaa, ya hivi karibuni kwanza. Yanayowaka sasa yameorodheshwa chini yao.',
		'all_off': 'Umeondoa kila kitu ulichokubali. Hakuna kinachohifadhiwa au kushirikiwa sasa.',
	},
}


def consent_history_note(has_events: bool, has_live: bool, lang: str = 'en') -> str:
	"""The sentence above a person's own consent log.

	`lang` defaults to English and the caller passes the request's, because this is prose a person
	reads on the screen where they check whether a withdrawal took — the same rule as every other
	string here: served in the language asked for where there is a table, and in English where there
	is not.
	"""
	assert isinstance(has_events, bool) and isinstance(has_live, bool), 'two booleans, not two truths'
	table = CONSENT_HISTORY_STRINGS[answerable(lang)]
	if not has_events:
		return table['none']
	return table['live'] if has_live else table['all_off']


# §SEC-001's first Feature bullet is *"Plain-language explanations in local languages"*, and the
# catalogue lived in `privacy/service.py` as English literals — so a person met a screen of English
# sentences at the one moment the product asks her to decide something about her own health data.
# The English is here now rather than there, because a translation kept beside an English literal
# is two sources for one sentence and they drift on the first edit; `CONSENT_CATALOGUE` is built
# from this table, so the sentence a toggle serves and the sentence a log copies are one fact.
#
# The language set is the honest one, and it is the same rule `SUPPORTED_LANGS` applies. Only `en`
# and `sw` have tables, and every other language §ACC-002 names falls back to English *and is told
# so* through `served_in`, rather than being served a sentence that pretends to be Dholuo. A
# machine-translated consent explanation would report this row closed while making the one screen
# where comprehension is the entire point unreadable — worse than an honest English one, and the
# same refusal the triage tables' own docstring already makes for recommendations.
#
# All three fields are translated and not only the label. A Swahili label over an English
# consequence tells a person what she is switching off in her own language and what it will cost
# her in a language she may not read, which is the half-translated screen this exists to prevent.
CONSENT_SCOPE_STRINGS: dict[str, dict[str, dict[str, str]]] = {
	'en': {
		'symptom_storage': {
			'label': 'Keep my symptom history',
			'explains': 'We store the symptoms you log so you and your health worker can see how you have been.',
			'on_withdrawal': 'Your symptom history stops being used and is deleted on the next clean-up.',
		},
		'location_tracking': {
			'label': 'Use my location',
			'explains': 'We use your area to find the nearest clinic and to show risk alerts where you are.',
			'on_withdrawal': 'You can still use the app, but you will type your area by hand and alerts will be less precise.',
		},
		'proximity_logging': {
			'label': 'Nearby contact log',
			'explains': 'The app can note when it is close to another app user, without either of you being identified.',
			'on_withdrawal': 'Close-contact alerts cannot reach you if you are exposed.',
		},
		'sensor_monitoring': {
			'label': 'Phone sensors',
			'explains': 'Your phone can measure things like breathing, coughing and falls. Each one is a separate choice.',
			'on_withdrawal': 'The sensors you switch off stop measuring immediately and their readings are deleted.',
		},
		'share_health_authorities': {
			'label': 'Share with health authorities',
			'explains': 'Counts of illness, with no names, go to the Ministry so they can see where an outbreak is moving.',
			'on_withdrawal': 'Your data is left out of the counts the Ministry sees.',
		},
		'share_chw': {
			'label': 'Share with my health worker',
			'explains': 'Your community health worker can see your record so they can follow up with you.',
			'on_withdrawal': 'Your health worker will not be able to see your record or follow up.',
		},
		'cloud_backup': {
			'label': 'Back up my data',
			'explains': 'A copy of your record is kept so you do not lose it if you change or lose your phone.',
			'on_withdrawal': 'Your record stays only on this phone. If you lose it, the record goes with it.',
		},
		'research': {
			'label': 'Allow research use',
			'explains': 'De-identified data may be used to study how illness spreads. This is never required.',
			'on_withdrawal': 'Your data is not used in research. Nothing else about the app changes.',
		},
	},
	'sw': {
		'symptom_storage': {
			'label': 'Hifadhi historia yangu ya dalili',
			'explains': 'Tunahifadhi dalili unazoandika ili wewe na mhudumu wako wa afya muone jinsi umekuwa.',
			'on_withdrawal': 'Historia yako ya dalili haitatumika tena na itafutwa wakati wa usafishaji unaofuata.',
		},
		'location_tracking': {
			'label': 'Tumia mahali nilipo',
			'explains': 'Tunatumia eneo lako kupata kituo cha afya cha karibu na kuonyesha tahadhari za hatari mahali ulipo.',
			'on_withdrawal': 'Unaweza kuendelea kutumia programu, lakini utaandika eneo lako kwa mkono na tahadhari hazitakuwa sahihi.',
		},
		'proximity_logging': {
			'label': 'Kumbukumbu ya mtu wa karibu',
			'explains': 'Programu inaweza kubaini inapokuwa karibu na mtumiaji mwingine, bila yeyote wenu kutambuliwa.',
			'on_withdrawal': 'Tahadhari za kuwa karibu na mtu mgonjwa hazitaweza kukufikia ikiwa umeambukizwa.',
		},
		'sensor_monitoring': {
			'label': 'Vihisi vya simu',
			'explains': 'Simu yako inaweza kupima mambo kama kupumua, kukohoa na kuanguka. Kila kimoja ni uamuzi wake.',
			'on_withdrawal': 'Vihisi unavyozima vinaacha kupima mara moja na vipimo vyake hufutwa.',
		},
		'share_health_authorities': {
			'label': 'Shiriki na mamlaka ya afya',
			'explains': 'Idadi ya wagonjwa, bila majina, huenda kwa Wizara ili waone ugonjwa unakoenea.',
			'on_withdrawal': 'Taarifa zako hazitahesabiwa katika idadi ambayo Wizara inaona.',
		},
		'share_chw': {
			'label': 'Shiriki na mhudumu wangu wa afya',
			'explains': 'Mhudumu wako wa afya ya jamii anaweza kuona kumbukumbu yako ili aweze kukufuatilia.',
			'on_withdrawal': 'Mhudumu wako wa afya hataweza kuona kumbukumbu yako wala kukufuatilia.',
		},
		'cloud_backup': {
			'label': 'Hifadhi nakala ya taarifa zangu',
			'explains': 'Nakala ya kumbukumbu yako huhifadhiwa ili usipoteze ukibadilisha au ukipoteza simu yako.',
			'on_withdrawal': 'Kumbukumbu yako inabaki kwenye simu hii pekee. Ukiipoteza, kumbukumbu inaenda nayo.',
		},
		'research': {
			'label': 'Ruhusu matumizi ya utafiti',
			'explains': 'Taarifa zisizotambulisha mtu zinaweza kutumika kuchunguza jinsi ugonjwa huenea. Hili halihitajiki kamwe.',
			'on_withdrawal': 'Taarifa zako hazitatumika katika utafiti. Hakuna kingine kinachobadilika.',
		},
	},
}

CONSENT_LANGS: frozenset[str] = frozenset(CONSENT_SCOPE_STRINGS)

# One language translated further than another is a toggle that goes half-English for the people
# who need it most, and it is invisible in any count of "how many languages do we serve". The two
# key sets are asserted equal rather than assumed, so a category added to one and not the other
# fails at import instead of on a screen.
assert set(CONSENT_SCOPE_STRINGS['en']) == set(CONSENT_SCOPE_STRINGS['sw']), (
	'a consent category is translated in one language and not the other'
)


def _check_consent_tables() -> None:
	"""Every row carries all three sentences, and none of them is empty.

	A helper rather than a module-level loop so the iteration variables do not become module
	attributes — `del` after the loop reads as a leak being tidied, and Pyright is right that the
	names are unbound if the loop body never runs.
	"""
	for lang, table in CONSENT_SCOPE_STRINGS.items():
		for slug, row in table.items():
			assert set(row) == {'label', 'explains', 'on_withdrawal'}, f'{lang}/{slug} is incomplete'
			assert all(row.values()), f'{lang}/{slug} has an empty sentence'


_check_consent_tables()

# The fallback is `answerable`'s, and this is what keeps it so: the consent tables cover exactly
# the languages with a triage table. A language gaining one and not the other is a person who reads
# her recommendation in Dholuo and her consent explanation in English.
assert CONSENT_LANGS == SUPPORTED_LANGS, (
	f'consent is served in {sorted(CONSENT_LANGS)} and the product answers in {sorted(SUPPORTED_LANGS)}'
)


def consent_scope_text(slug: str, lang: str = 'en') -> dict[str, str]:
	"""One §SEC-001 category's label, explanation and withdrawal consequence, in `lang`.

	Served in the language asked for where there is a table and in English where there is not, the
	same rule as every other string here — the caller passes the request's language and reads
	`served_in` off the toggle to know which it got.

	An unknown slug raises rather than returning a placeholder: a category with no sentence is a
	defect to fix, and a silent empty dict would render a toggle with nothing beside it on the one
	screen where the person is deciding whether to hand over her health data.
	"""
	assert slug in CONSENT_SCOPE_STRINGS['en'], f'unknown consent category {slug}'
	return CONSENT_SCOPE_STRINGS[answerable(lang)][slug]


# §SEC-004's "optional pseudonymous profile": the sentence that tells a person what the handle is
# for, and — the part that matters — what it does *not* protect against. The second half is not
# decoration: a handle that rotated forever would still be re-identifiable in a small enough group,
# which is the same admission §SEC-004's "minimum cell size of 10" makes one level up, and a person
# who believes a pseudonym is anonymity will post something they would not have posted otherwise.
PSEUDONYM_STRINGS: dict[str, dict[str, str]] = {
	'en': {
		'derived': 'This is the name shown on shared screens instead of your details. It changes every {days} days.',
		'chosen': 'You chose this name. It is shown on shared screens instead of your details, and it stays the same until you change it.',
		'caveat': 'A name like this hides your details, but if only a few people are reporting from the same place at the same time, someone may still work out who you are. Do not put anything in a public report you would not want read back to you.',
	},
	'sw': {
		'derived': 'Hili ni jina linaloonyeshwa kwenye skrini za umma badala ya taarifa zako. Hubadilika kila siku {days}.',
		'chosen': 'Ulijichagulia jina hili. Linaonyeshwa kwenye skrini za umma badala ya taarifa zako, na linabaki hivyo hadi ulibadilishe.',
		'caveat': 'Jina kama hili huficha taarifa zako, lakini kama ni watu wachache wanaoripoti kutoka sehemu moja kwa wakati mmoja, mtu anaweza kukutambua. Usiweke kwenye ripoti ya umma kitu usichotaka kirejeshwe kwako.',
	},
}


def pseudonym_note(chosen: bool, rotation_days: int, lang: str = 'en') -> str:
	"""What a person is told about the handle standing in for them.

	Served in the language asked for where there is a table and in English where there is not, the
	same rule as every string here — and the caller passes the request's language rather than this
	function guessing it.
	"""
	assert isinstance(chosen, bool), 'whether the handle was chosen is a fact, not a guess'
	assert rotation_days >= 1, 'a rotation window is at least a day'
	table = PSEUDONYM_STRINGS[answerable(lang)]
	if chosen:
		return table['chosen']
	return table['derived'].format(days=rotation_days)


def pseudonym_caveat(lang: str = 'en') -> str:
	"""The limit of what the handle protects, as a string a route can serve.

	A separate function and not a sentence appended to the note, because the two say different
	things and a client may render them in different places — the note is a caption under the name,
	the caveat belongs beside the box a person types a report into. What is *not* optional is that
	it is served: an earlier cut of this module had the caveat in the table and no route reading it,
	which is the same "every visible part present and the join absent" defect the handle itself was
	added to close. A pseudonym screen that shows a name and omits the caveat promises more than the
	handle delivers.
	"""
	table = PSEUDONYM_STRINGS[answerable(lang)]
	caveat = table['caveat']
	assert caveat, 'the caveat is load-bearing and cannot be empty'
	return caveat


def zone_transition(lang: str, event: str, place_label: str | None = None,
                    alert: str | None = None, county: str = '') -> str:
	"""The sentence served on a zone entry or exit. §LOC-001's Tier 4 behaviour is "alert on entry
	*and exit*", and the exit is the one a client is likeliest to render as an all-clear: leaving a
	zone is not the same news as never having been in it, because the 21-day watch has started."""
	assert event in ('entry', 'exit'), f'unknown zone event {event}'
	table = GEOFENCE_ALERT_STRINGS[answerable(lang)]
	place = zone_place(lang, place_label, county)
	if event == 'entry':
		return table['entry'].format(alert=alert or geofence_alert(lang, place_label, county))
	return table['exit'].format(place=place)


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

# §ALT-002's "Works over SMS when data is unavailable", as the strings a reply is made of.
#
# These are the only strings in the product that must survive a gateway that refuses anything outside
# GSM7, so they carry no em dash, no curly quote and no degree sign — `segment_sms` and §5.3's
# zero-rating both turn on the alphabet, and a reply refused at the gateway is a person who pressed
# "I'm safe" and heard nothing back. `test_alt002.py` asserts the alphabet rather than trusting it.
#
# The reply names **who is accounted for and who is not**, because a check-in that answered only
# "recorded" would leave the person unable to tell whether their family had heard anything. It never
# names the members' subjects: an SMS lands on a handset that may be shared, and §17.2's personal
# data does not belong in a plain-text message to a number the server has not verified belongs to the
# person who asked.
SMS_FAMILY_SAFE: dict[str, str] = {
	'en': 'Afya: you are marked safe. {board}',
	'sw': 'Afya: umewekwa salama. {board}',
}
SMS_FAMILY_BOARD: dict[str, str] = {
	'en': '{safe} of {total} checked in safe.',
	'sw': '{safe} kati ya {total} wamejisalimisha salama.',
}
SMS_FAMILY_BOARD_ALL: dict[str, str] = {
	'en': 'Everyone in your group has checked in safe ({total}).',
	'sw': 'Kila mtu katika kikundi chako amejisalimisha salama ({total}).',
}
SMS_FAMILY_NO_GROUP: dict[str, str] = {
	'en': (
		'Afya: your number is not linked to a family group yet. Ask a family member to add you, '
		'or call 719.'
	),
	'sw': (
		'Afya: namba yako haijaunganishwa na kikundi cha familia bado. Omba mwanafamilia akuongeze, '
		'au piga 719.'
	),
}
SMS_FAMILY_MANY_GROUPS: dict[str, str] = {
	'en': 'Afya: you are in more than one family group. Reply SAFE and the group name.',
	'sw': 'Afya: uko katika vikundi zaidi ya kimoja vya familia. Jibu SAFE na jina la kikundi.',
}
# A message that mentions safety but is not the sender's own check-in. Answered rather than filed:
# "my brother is safe" would otherwise mark the *sender* safe, and a keyword list cannot tell a
# relayed message from a first-person one — so the product asks instead of guessing.
SMS_FAMILY_THIRD_PARTY: dict[str, str] = {
	'en': 'Afya: reply SAFE if you are safe yourself. To report someone else, call 719.',
	'sw': 'Afya: jibu SALAMA ikiwa wewe mwenyewe uko salama. Kuripoti mtu mwingine, piga 719.',
}
# A message that says the opposite of safe. The live probe found this: "I am not safe" matched no
# keyword, fell through to §CHAN-3's map, and was answered with the welcome menu — a person saying
# they are in danger, handed a list of options. The reply names the line that can actually help.
SMS_FAMILY_NOT_SAFE: dict[str, str] = {
	'en': 'Afya: if you are in danger, call 719 now, free and 24/7. Reply SAFE when you are safe.',
	'sw': 'Afya: ikiwa uko hatarini, piga 719 sasa, bure na saa 24. Jibu SALAMA ukiwa salama.',
}
SMS_FAMILY_UNKNOWN_GROUP: dict[str, str] = {
	'en': 'Afya: we could not find that family group. Check the name and reply again, or call 719.',
	'sw': 'Afya: hatukupata kikundi hicho cha familia. Angalia jina na ujibu tena, au piga 719.',
}

# The words that make an inbound SMS a check-in. "safe" is the button's own word and "salama" is its
# Kiswahili, which is what a person on a feature phone would actually type; a keyword list of one
# English word would refuse the reply of the person the SMS path exists for.
# `nikosalama` is there because a feature phone's keyboard is where the space goes missing, and a
# check-in refused for a typo is a person told their family was not notified.
SMS_SAFE_KEYWORDS: tuple[str, ...] = ('safe', 'salama', 'niko salama', 'nikosalama')