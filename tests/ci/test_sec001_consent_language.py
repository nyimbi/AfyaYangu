"""§SEC-001's "Plain-language explanations in local languages" — the bullet that was English-only.

The section lists five Features under Consent Management. Four were carried. The fifth was
`missing` for a reason the audit row states plainly: "`ConsentScope.explains` is a plain-language
sentence but exists in English only; nothing carries a per-language consent explanation".

The shape of the gap is the one this repo keeps finding — every visible part present and the join
absent. There was a catalogue, a sentence beside each toggle, a route serving it, and a log copying
it. What there was not, was any way for the sentence to be in a language other than English, and
that is precisely what the bullet asks for. It matters more here than anywhere else in the product:
consent that a person cannot read is not informed consent, and DPA 2019 requires the consent it
recognises to be informed.

**The language set stays at two, deliberately.** `en` and `sw` have tables; every other language
§ACC-002 names falls back to English *and the toggle says so*. Widening `CONSENT_SCOPE_STRINGS` to
six languages with machine-translated sentences would report this row closed while making the one
screen where comprehension is the entire point unreadable — the same failure `test_personas.py`
pins for §ACC-002's six-language bullet, and the one `afya.strings`' own docstring refuses for
triage recommendations.

So the tests come in five parts: the sentences live in one table rather than in the catalogue, a
Swahili request gets Swahili, a language with no table gets English *and is told*, the log records
the language the person was actually shown, and the toggle screen is reachable by a client at all.
The last one is the join: the route served the catalogue and no catalogue action pointed at it.
"""
import re

from fastapi.testclient import TestClient

from afya.mobile.actions import FEATURE_OF, catalogue
from afya.privacy.service import CONSENT_CATALOGUE, PrivacyService
from afya.privacy.views import ConsentCategory, ConsentRecord, LegalBasis
from afya.service import build_services, create_app
from afya.strings import (
	CONSENT_LANGS, CONSENT_SCOPE_STRINGS, SUPPORTED_LANGS, answerable, consent_scope_text,
)

FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')

# Swahili function words, matched on word boundaries. A substring probe would pass on `navigator`
# for `na` — the over-broad predicate that once made a tone gate flag Tanzania's real Social
# Security Regulatory Authority. No English sentence on this screen contains one of these as a word.
SWAHILI_MARKER = re.compile(r'\b(?:ya|na|wa|kwa|ili|bila|yako|wako|lako|hili|cha|za|kama)\b', re.I)


def _grant(subject: str = 'U-1', purpose: str = 'symptom_storage', lang: str = 'en',
           **kw: object) -> ConsentRecord:
	return ConsentRecord(subject_ref=subject, purpose=purpose, data_types=[purpose],
	                     retention_days=365, legal_basis=LegalBasis.consent, lang=lang,
	                     **kw)  # type: ignore[arg-type]


# --- the sentences live in one table, not in the catalogue -------------------------------------

def test_the_catalogue_is_built_from_the_string_table_rather_than_restating_it() -> None:
	"""The finding this unit closes is that the sentences were English literals in `privacy/service.py`
	with no second language anywhere. A translation kept beside an English literal is two sources for
	one sentence and they drift on the first edit — so the catalogue is *built* from the table, and
	this asserts the build rather than the wording."""
	for scope in CONSENT_CATALOGUE:
		words = consent_scope_text(scope.category.value)
		assert scope.label == words['label']
		assert scope.explains == words['explains']
		assert scope.on_withdrawal == words['on_withdrawal']


def test_every_category_the_section_names_is_translated_in_every_language() -> None:
	"""§SEC-001 lists eight categories and the bullet asks for explanations in *local languages*.
	A category translated in one language and not another is a toggle that goes half-English for the
	people who need it most, and it is invisible in any count of "how many languages do we serve"."""
	assert {s.value for s in ConsentCategory} == set(CONSENT_SCOPE_STRINGS['en'])
	assert {s.value for s in ConsentCategory} == set(CONSENT_SCOPE_STRINGS['sw'])
	for lang, table in CONSENT_SCOPE_STRINGS.items():
		for slug, row in table.items():
			assert set(row) == {'label', 'explains', 'on_withdrawal'}, f'{lang}/{slug}'
			assert all(row.values()), f'{lang}/{slug} has an empty sentence'


def test_the_language_set_is_the_one_the_product_can_answer_in() -> None:
	"""`CONSENT_LANGS == SUPPORTED_LANGS`, asserted rather than assumed. A language gaining a triage
	table and not a consent one is a person who reads her recommendation in Dholuo and her consent
	explanation in English — and the fallback rule would hide it, because English is what she gets
	either way."""
	assert CONSENT_LANGS == SUPPORTED_LANGS == frozenset({'en', 'sw'})


def test_the_swahili_is_not_the_english_under_a_swahili_key() -> None:
	"""A table of six languages where five hold the English string is the cheapest way to make this
	row look closed, and it is worse than leaving it open: the person reads English believing it is
	her language. Every Swahili sentence must differ from its English counterpart."""
	for slug, english in CONSENT_SCOPE_STRINGS['en'].items():
		swahili = CONSENT_SCOPE_STRINGS['sw'][slug]
		for field in ('label', 'explains', 'on_withdrawal'):
			assert swahili[field] != english[field], f'{slug}.{field} is the English string'
		# And it is Swahili, not English with a word swapped. The probe is Swahili function words
		# matched on word boundaries: a substring probe would pass on `navigator` for `na`, which is
		# the same over-broad predicate that once made a tone gate flag real regulators. These are
		# words no English sentence of this kind contains, and one must appear in every sentence.
		assert SWAHILI_MARKER.search(swahili['explains']), (
			f'{slug}.explains reads as English: {swahili["explains"]}'
		)


# --- a request in Swahili is answered in Swahili ------------------------------------------------

def test_a_swahili_request_gets_swahili_toggles() -> None:
	"""The bullet, end to end. Before this every toggle was English whatever the caller asked for."""
	svc = PrivacyService()
	toggles = svc.consent_toggles(lang='sw')
	assert len(toggles) == 8
	assert all(t.served_in == 'sw' and t.language_fallback is False for t in toggles)
	location = next(t for t in toggles if t.category is ConsentCategory.location_tracking)
	assert location.label == CONSENT_SCOPE_STRINGS['sw']['location_tracking']['label']
	assert location.explains != CONSENT_SCOPE_STRINGS['en']['location_tracking']['explains']


def test_all_three_sentences_are_translated_and_not_only_the_label() -> None:
	"""A Swahili label over an English consequence tells a person what she is switching off in her
	own language and what it will cost her in one she may not read. That is the half-translated
	screen this unit exists to prevent, and it would pass a test that checked the label alone."""
	toggle = next(t for t in PrivacyService().consent_toggles(lang='sw')
	              if t.category is ConsentCategory.location_tracking)
	assert toggle.label != CONSENT_SCOPE_STRINGS['en']['location_tracking']['label']
	assert toggle.explains != CONSENT_SCOPE_STRINGS['en']['location_tracking']['explains']
	assert toggle.on_withdrawal != CONSENT_SCOPE_STRINGS['en']['location_tracking']['on_withdrawal']
	assert toggle.on_withdrawal == CONSENT_SCOPE_STRINGS['sw']['location_tracking']['on_withdrawal']


def test_a_language_with_no_table_is_served_english_and_told_so() -> None:
	"""§ACC-002's `answerable` rule, and the part that makes the fallback honest rather than silent.
	A Dholuo speaker is answered in English *and the payload says so*, so a client can add its own
	preamble instead of rendering English as if it were Dholuo. On this screen that distinction is
	the difference between consent that was informed and consent that merely looks like it."""
	toggles = PrivacyService().consent_toggles(lang='luo')
	assert all(t.served_in == 'en' and t.language_fallback is True for t in toggles)
	assert answerable('luo') == 'en'
	# The English served is the real English, not a placeholder.
	assert toggles[0].explains == CONSENT_SCOPE_STRINGS['en'][toggles[0].category.value]['explains']


# --- the log records the language the person was actually shown --------------------------------

async def test_the_grant_records_the_language_it_was_made_in() -> None:
	"""The log's design is that an event carries the words the person was shown *then* rather than
	looking them up now. A copy of the *English* sentence is not what a person who read the Swahili
	one was shown, so the record has to carry the language as well as the words."""
	svc = PrivacyService()
	await svc.record_consent(_grant(lang='sw'))
	event = svc.consent_history('U-1').events[0]
	assert event.lang == 'sw'
	assert event.label == CONSENT_SCOPE_STRINGS['sw']['symptom_storage']['label']
	assert event.consequence == CONSENT_SCOPE_STRINGS['sw']['symptom_storage']['on_withdrawal']


async def test_a_withdrawal_is_logged_in_the_language_of_the_grant() -> None:
	"""A person reads her own history in one screen. A grant line in Swahili and its withdrawal in
	English would be the same conversation described in two languages on the page she opened to
	check whether the withdrawal took."""
	svc = PrivacyService()
	rec = await svc.record_consent(_grant(lang='sw'))
	await svc.withdraw(rec.consent_id)
	events = svc.consent_history('U-1').events
	assert [e.action for e in events] == ['withdrawn', 'granted']
	assert all(e.lang == 'sw' for e in events)
	assert all(e.label == CONSENT_SCOPE_STRINGS['sw']['symptom_storage']['label'] for e in events)


async def test_a_language_with_no_table_is_recorded_as_the_english_it_was_served() -> None:
	"""The record says what the person could actually read. Logging `luo` for a grant served in
	English would make the consent record claim an explanation was given in a language it was not —
	and the record of an informed consent is the one place that must not flatter itself."""
	svc = PrivacyService()
	await svc.record_consent(_grant(lang='luo'))
	assert svc.consent_history('U-1').events[0].lang == 'en'


async def test_the_phone_door_carries_the_sessions_language() -> None:
	"""A USSD grant is made by pressing a key after reading a menu, and §CHAN-2's own menu offers
	"English / Kiswahili / Dholuo / ...". Without this the channel path logged every grant as
	English whatever language the session ran in."""
	from afya.identity.service import IdentityService
	svc = PrivacyService(identity=IdentityService())
	rec = await svc.record_consent_for_phone('0712345678', ConsentCategory.symptom_storage,
	                                         channel='ussd', lang='sw')
	assert rec.lang == 'sw'
	event = svc.consent_history(rec.subject_ref).events[0]
	assert event.lang == 'sw' and event.channel == 'ussd'


# --- the toggle screen is reachable by a client at all -----------------------------------------

def test_the_catalogue_route_serves_the_language_it_was_asked_for() -> None:
	"""The front door. A green service test says nothing about what the route serves, and the route
	is where the language parameter has to arrive."""
	app = create_app(build_services())
	with TestClient(app) as c:
		sw = c.get('/privacy/consent', params={'lang': 'sw'}).json()
		en = c.get('/privacy/consent', params={'lang': 'en'}).json()
		fallback = c.get('/privacy/consent', params={'lang': 'luo'}).json()
	assert sw['lang'] == 'sw' and sw['language_fallback'] is False
	assert en['lang'] == 'en' and en['language_fallback'] is False
	assert fallback['lang'] == 'en' and fallback['language_fallback'] is True
	assert sw['toggles'][0]['label'] != en['toggles'][0]['label'], 'the two languages serve one string'
	assert sw['toggles'][0]['explains'] != en['toggles'][0]['explains']


def test_the_toggle_screen_has_a_catalogue_action() -> None:
	"""The join this section was missing twice over. `GET /privacy/consent` served the explanation
	and *no catalogue action pointed at it* — a client could record a grant and withdraw one and had
	no screen for the question §SEC-001's first bullet is about. This asserts the action exists and
	its slug is a slug rather than a spec code."""
	acts = {a.id: a for a in catalogue()}
	assert 'consent_choices' in acts, 'no catalogue action reaches the consent explanation'
	act = acts['consent_choices']
	assert (act.method, act.path) == ('GET', '/privacy/consent')
	assert FEATURE_OF['consent_choices'] == 'SEC-001'
	assert any(f.name == 'lang' for f in act.fields), 'the language cannot be chosen'
	assert FEATURE_CODE.search(act.id) is None and FEATURE_CODE.search(act.title) is None


def test_no_spec_code_or_internal_slug_reaches_a_sentence_a_person_reads() -> None:
	"""Spec ids are internal handles. The consent screen is the last place one may appear: it is the
	screen where a person is deciding whether to trust the product with her health data.

	The slug probe is deliberately *not* `slug not in joined`. `research` is both a category slug and
	the ordinary English word in "Allow research use", and a checker that flagged it would be the
	tone gate that flagged Tanzania's real Social Security Regulatory Authority — a global assumption
	about a canonical value, wearing a lint's clothes. What is unmistakably an internal handle is a
	slug rendered *as* the label, or one that keeps its underscore. Those two are checked."""
	for lang, table in CONSENT_SCOPE_STRINGS.items():
		for slug, row in table.items():
			for field, text in row.items():
				assert FEATURE_CODE.search(text) is None, f'{lang}/{slug}.{field}: {text}'
				assert text != slug, f'{lang}/{slug}.{field} renders its slug as the label'
			# An identifier that keeps its underscore is unmistakably internal. The bare word is not:
			# `research` is the slug *and* the ordinary English word in "used in research", and
			# flagging that would be a checker failing on correct copy.
			assert '_' not in ' '.join(row.values()), f'{lang}/{slug} leaks an internal handle'
