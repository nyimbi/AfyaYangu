"""Gate: §INF-004's Myth-Busting Library, and the four Features the section prints over it.

The corpus existed before this gate and satisfied none of them. A rumour was one `body` string, so
there was no claim to search for, no correction to weigh against a named authority, and nothing a
client could forward as a card — the section's own Format, "Rumour: [claim]. Fact: [correction].
Source: [authority].", was a sentence the seed happened to write in the right order. §INF-004 prints
four Features and each is a different thing done to the same rumour, so each is checked against the
surface that does it rather than against the corpus holding a row.

Two properties run through the file. The three parts of the Format are *fields*, not prose, and they
travel together — the model refuses a claim with no authority and refuses either on a row that is not
a myth. And the correction the library serves is the correction §6.4's protocol publishes, because
they are now derived from one table: `afya.info.myths.MYTHS`. A rumour answered one way in the
library and another way by the response protocol is the same fact stated twice, which is the failure
`test_the_library_and_the_protocol_serve_one_correction` exists to catch.
"""
import asyncio
import re
from pathlib import Path
from urllib.parse import unquote

import httpx
import pytest
from pydantic import ValidationError

from afya.community.service import CORRECTION_LIBRARY, CommunityService
from afya.info.content_seed import MYTH_RANK, myth_rows, seed_rows
from afya.info.myths import (
	DRAFTED_ON_ISO,
	FALLBACK_CORRECTION,
	FALLBACK_TOPIC,
	MYTH_CATEGORIES,
	MYTH_KEYWORDS,
	MYTH_LANGS,
	MYTHS,
	Myth,
	classify,
	correction_library,
	correction_text,
	myth_for,
	topic_for_slug,
)
from afya.info.service import InfoService
from afya.info.views import MYTH_TAG, ContentItem, ContentStage
from afya.service import build_services, create_app

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / 'docs' / 'spec.md'

# The spec codes must not reach anything a person reads — the standing rule for the whole product,
# and the one §INF-004 is most exposed to because its rows carry an authority string and a slug.
FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')

# §6.4's six myth categories, transcribed. The section names them as the ones "to pre-draft", so the
# set is the section's and a category added to the code without the spec moving fails here.
SPEC_CATEGORY_SLUGS = frozenset({'false_cures', 'transmission', 'vaccine', 'conspiracy', 'stigma', 'burial'})


def _app() -> object:
	return create_app(build_services())


def _client(app: object) -> httpx.AsyncClient:
	return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t')  # type: ignore[arg-type]


# --- the Format: three parts, as fields ----------------------------------------------------------

def test_the_format_is_the_sections_own_wording() -> None:
	"""Transcribed, not paraphrased. The Format cell is the section's whole specification of what a
	myth row is, so a revision that reorders or drops a part must fail here until the code moves."""
	spec = SPEC.read_text(encoding='utf-8')
	assert '**Format:** "Rumour: [claim]. Fact: [correction]. Source: [authority]."' in spec, (
		'§INF-004\'s Format cell is no longer the wording this corpus renders'
	)
	for part in ('Rumour:', 'Fact:', 'Source:'):
		assert part in spec


def test_a_claim_and_its_authority_are_one_format() -> None:
	"""Neither half may travel alone. A claim with no source is a correction nobody can weigh, and a
	source with no claim corrects nothing — so the model refuses both, and refuses them on a row that
	is not a myth at all."""
	base: dict[str, object] = {
		'item_id': 'x', 'title': 't', 'body': 'b', 'lang': 'en', 'slug': 's',
		'owner': 'MoH Health Promotion Unit', 'reviewer': 'Clinical advisory group',
		'reviewed_on_iso': '2026-10-01', 'version': 1, 'stage': ContentStage.published,
	}
	# A claim with no authority, and an authority with no claim.
	with pytest.raises(ValidationError):
		ContentItem(**{**base, 'harmony_tag': MYTH_TAG, 'claim': 'Warm salt water cures Ebola.'})  # type: ignore[arg-type]
	with pytest.raises(ValidationError):
		ContentItem(**{**base, 'harmony_tag': MYTH_TAG, 'source': 'MoH/PHEOC'})  # type: ignore[arg-type]
	# And both on a row that is not a myth: a first-aid card has no rumour to refute.
	with pytest.raises(ValidationError):
		ContentItem(**{**base, 'harmony_tag': 'first-aid', 'claim': 'c', 'source': 's'})  # type: ignore[arg-type]
	# The myth row itself is accepted, which is what makes the three refusals above about the rule
	# rather than about the model rejecting everything.
	assert ContentItem(**{**base, 'harmony_tag': MYTH_TAG, 'claim': 'c', 'source': 's'}).claim == 'c'  # type: ignore[arg-type]


def test_every_seeded_myth_row_carries_all_three_parts() -> None:
	"""The corpus obeys its own Format, and the myth rows are the only rows that do."""
	rows = myth_rows()
	assert rows, 'the corpus must carry myths, or every assertion in this file is vacuous'
	for row in rows:
		assert row.claim and row.source and row.body, f'{row.slug} is missing a part of the Format'
		assert row.harmony_tag == MYTH_TAG, f'{row.slug} is a myth not tagged as one'
		assert row.answers_rank == MYTH_RANK, f'{row.slug} answers §6.1 rank 5'
		# The correction is the body and the claim is not: a row whose body restates the rumour
		# corrects nothing, which is the shape the old single-string corpus had.
		assert row.body != row.claim, f'{row.slug} states the rumour as the correction'
	for row in seed_rows():
		if row.harmony_tag != MYTH_TAG:
			assert row.claim is None and row.source is None, (
				f'{row.slug} is not a myth and carries a rumour'
			)


def test_the_corpus_drafts_every_topic_in_both_languages() -> None:
	"""§6.2.4's rule reaches this corpus: every myth row answers §6.1 rank 5, so an English-only
	rumour correction is the message the section forbids publishing. The pair is asserted per topic
	rather than as a total, because a total hides one topic losing a language while another gains it."""
	for topic in {m.topic for m in MYTHS}:
		langs = {m.lang for m in MYTHS if m.topic == topic}
		assert langs == set(MYTH_LANGS), f'{topic} is drafted in {langs} only'


def test_the_six_categories_are_the_sections_own() -> None:
	"""§6.4 names six categories "to pre-draft". The code's set is checked against the spec's, so a
	category invented in the corpus is a row the section never asked for."""
	spec = SPEC.read_text(encoding='utf-8')
	assert {c.slug for c in MYTH_CATEGORIES} == SPEC_CATEGORY_SLUGS
	for category in MYTH_CATEGORIES:
		assert category.slug.replace('_', ' ') in spec or category.label in spec, (
			f'§6.4 does not name the category {category.slug!r}'
		)


# --- Feature: Search -----------------------------------------------------------------------------

def test_search_matches_the_claim_not_only_the_prose() -> None:
	"""The half that needed the corpus to carry a claim. "salt water" is a rumour, and while the
	rumour lived inside `body` it was findable by accident rather than on purpose — a search that
	happened to hit the correction's wording.

	The query is `warm`, which appears in `myth-salt-water`'s claim and in neither its title nor its
	correction. That distinction is the test: an earlier version of it searched for "salt water",
	which the *title* also carries, so it passed with the claim dropped from the haystack entirely.
	A canary caught that, and the term has to be one the claim is the only home of or the assertion
	restates what the title already proves.
	"""
	svc = InfoService()
	hits = svc.search('warm', 'en')
	assert {h.slug for h in hits} >= {'myth-salt-water'}, 'the claim is what was searched'
	# And the premise, asserted rather than assumed: `warm` is nowhere in that row but its claim.
	row = next(r for r in myth_rows() if r.slug == 'myth-salt-water' and r.lang == 'en')
	assert 'warm' not in row.title.lower() and 'warm' not in row.body.lower(), (
		'`warm` must be findable only through the claim, or this test proves nothing about the claim'
	)
	assert row.claim is not None and 'warm' in row.claim.lower()


def test_search_requires_every_term() -> None:
	"""A search that matched any term would answer "salt water" with every row containing "water",
	which is the library again rather than a search. The terms are AND-ed, so a query narrows."""
	svc = InfoService()
	both = {c.slug for c in svc.search('salt water', 'en')}
	one = {c.slug for c in svc.search('salt', 'en')}
	assert both <= one, 'adding a term must not widen the result'


def test_search_is_scoped_to_the_served_language_and_stage() -> None:
	"""A draft is not content. Search reads through `library()`, so a query cannot surface an item
	§6.5 has not cleared — the failure that would make search a way around the workflow — and a query
	in one language cannot surface another language's row."""
	svc = InfoService()
	svc._content['draft-sw'] = ContentItem(  # type: ignore[attr-defined]
		item_id='draft-sw', title='Hadithi', body='maji ya chumvi ni tiba', lang='sw', slug='draft-rumour',
		harmony_tag=MYTH_TAG, claim='maji ya chumvi ni tiba', source='MoH/PHEOC',
		owner='MoH Health Promotion Unit', reviewer='Clinical advisory group',
		reviewed_on_iso='2026-10-01', version=1, stage=ContentStage.draft,
	)
	assert 'draft-rumour' not in {c.slug for c in svc.search('chumvi', 'sw')}, 'a draft is not content'
	assert 'draft-rumour' not in {c.slug for c in svc.search('chumvi', 'en')}, 'and not in the other language'


# --- Feature: Browse by category -----------------------------------------------------------------

def test_every_facet_has_something_behind_it() -> None:
	"""A browse screen that opens onto an empty list because the facet counted a draft is the failure
	the count exists to prevent, so the counts are read through `library()` rather than off the store
	and every offered category is checked to have that many rows."""
	svc = InfoService()
	facets = svc.facets('en')
	assert facets, 'the corpus must offer categories to browse'
	for facet in facets:
		tag, count = str(facet['tag']), int(str(facet['count']))
		served = [c for c in svc.library('en') if c.harmony_tag == tag]
		assert len(served) == count, f'{tag} offers {count} and has {len(served)}'
		assert count > 0, f'{tag} is offered with nothing behind it'


def test_a_category_is_labelled_for_a_person_not_by_its_tag() -> None:
	"""The tag is a slug. A browse screen showing `mythbusting` is the feature-code failure one
	level down, so every facet carries a human label and no label is the tag it stands for."""
	svc = InfoService()
	for facet in svc.facets('en'):
		tag, label = str(facet['tag']), str(facet['label'])
		assert label and label != tag, f'{tag} has no label'
		assert FEATURE_CODE.search(label) is None


def test_the_myth_tag_is_browsable() -> None:
	"""The category the section is about, asserted by name: if the corpus stopped tagging myths, the
	browse screen would still offer four categories and nothing would fail."""
	assert MYTH_TAG in {f['tag'] for f in InfoService().facets('en')}


# --- Feature: "Ask about a rumour" ---------------------------------------------------------------

def test_asking_answers_the_asker_with_the_correction_and_its_authority() -> None:
	"""Not a flag. `flag_misinfo` takes a rumour someone *else* spread and returns PHEOC a cluster;
	someone asking whether something is true is not reporting anything, and answering them with a
	surveillance row answers a question they did not ask."""
	svc = CommunityService()
	answer = svc.answer_claim('I heard warm salt water cures Ebola')
	assert answer.recognised is True
	assert answer.topic == 'cure_claim'
	assert answer.source == 'MoH/PHEOC', 'a correction with no named authority cannot be weighed'
	assert answer.fact and answer.fact != answer.claim
	assert answer.slug == 'myth-salt-water'
	assert answer.drafted_on_iso == DRAFTED_ON_ISO


def test_an_unrecognised_claim_is_answered_honestly() -> None:
	"""Attaching an unknown claim to the nearest rumour is a confident correction to the wrong
	question, which is worse than §6.2.8's "under verification". The flag says which it is."""
	svc = CommunityService()
	answer = svc.answer_claim('the moon is made of cheese')
	assert answer.recognised is False
	assert answer.topic is None
	assert answer.matched == []
	assert answer.fact == FALLBACK_CORRECTION['en']
	assert answer.slug == ''


def test_the_fallback_is_answered_in_the_askers_language() -> None:
	"""The fallback is drafted in both languages, so there is no reason to answer a Swahili speaker
	in English — and `answered_in` must report the language actually served rather than the one
	asked for, or a client renders a Swahili correction under an English heading."""
	svc = CommunityService()
	answer = svc.answer_claim('the moon is made of cheese', 'sw')
	assert answer.answered_in == 'sw'
	assert answer.fact == FALLBACK_CORRECTION['sw']
	assert answer.fact != FALLBACK_CORRECTION['en']


def test_a_known_topic_in_an_unwritten_language_falls_back_and_says_so() -> None:
	"""`answerable` resolves a language with no string table to English rather than refusing: a rumour
	correction that cannot be sent to a Dholuo-speaking community is the audience §4.1's Persona F is.
	The disclosure is what stops the fallback reading as a translation."""
	svc = CommunityService()
	answer = svc.answer_claim('warm salt water cures Ebola', 'luo')
	assert answer.answered_in == 'en', 'the language actually served, not the one asked for'
	assert answer.correction == correction_text(myth_for('cure_claim', 'en'))  # type: ignore[arg-type]


def test_the_classifier_is_not_fooled_by_a_claim_that_merely_mentions_a_topic() -> None:
	"""A keyword classifier is the shape that answers every question with the nearest rumour. The
	corpus carries the negative case so the fallback path is exercised by the seed rather than only
	by a test, and an unrelated claim is asserted to match nothing."""
	topic, matched = classify('the moon is made of cheese')
	assert (topic, matched) == (None, [])
	# And the positive case, so the two are told apart by the classifier rather than by the caller.
	topic, matched = classify('I heard warm salt water cures Ebola')
	assert topic == 'cure_claim' and matched


def test_the_swahili_corpus_is_searchable_in_swahili() -> None:
	"""A Swahili speaker searching for a rumour they heard in Swahili must find it. The keywords are
	per-language for this reason: an English-only keyword list would answer a Swahili claim with the
	fallback while the corpus held the correction."""
	topic, matched = classify('maji ya chumvi ni tiba')
	assert topic == 'cure_claim', 'the Swahili claim must be recognised, not fall back'
	assert matched


# --- Feature: Shareable as a card ----------------------------------------------------------------

def test_a_myth_card_renders_the_sections_own_three_lines() -> None:
	"""§3.3 principle 10 requires every output be shareable as a WhatsApp card. For a myth the card
	is the Format itself: a card stating the correction alone reads as an assertion out of nowhere,
	and the person receiving it cannot tell what it answers."""
	row = next(r for r in myth_rows() if r.slug == 'myth-salt-water')
	card = row.share_card
	assert f'Rumour: {row.claim}' in card
	assert f'Fact: {row.body}' in card
	assert f'Source: {row.source}' in card
	assert row.share_url.startswith('https://wa.me/?text=')


def test_a_non_myth_card_is_title_and_body() -> None:
	"""A first-aid card has no rumour to refute, so its card is the heading and the text — the shape
	every other item in the library shares."""
	row = next(r for r in seed_rows() if r.harmony_tag == 'first-aid' and r.format.is_text)
	assert row.claim is None
	assert row.share_card == f'{row.title}\n{row.body}'
	assert 'Rumour:' not in row.share_card


def test_the_card_is_rendered_server_side_and_url_encoded() -> None:
	"""Rendered here for the reason `TriageResult.summary_card` is: §5.4 puts this answer on WhatsApp,
	USSD and SMS, and only one of those can compose a forwardable message. Encoded so a claim
	containing `&` or a newline survives the deep link."""
	row = next(r for r in myth_rows() if r.slug == 'myth-salt-water')
	encoded = row.share_url.removeprefix('https://wa.me/?text=')
	assert ' ' not in encoded and '\n' not in encoded
	assert unquote(encoded) == row.share_card


# --- one table behind the library and the protocol -----------------------------------------------

def test_the_library_and_the_protocol_serve_one_correction() -> None:
	"""The reason `myths.py` exists. §6.4's response protocol publishes a correction per topic and
	§INF-004's library serves one per rumour; a rumour answered one way in the library and another
	way by the protocol is the same fact stated twice, and the two drift the moment either is edited.
	Both now derive from `MYTHS`, so this asserts the derivation rather than the agreement."""
	assert CORRECTION_LIBRARY == correction_library(), (
		'the protocol\'s table must be derived from the myth corpus, not maintained beside it'
	)
	svc = CommunityService()
	for myth in MYTHS:
		assert svc.correction_for(myth.topic, myth.lang) == correction_text(myth), (
			f'{myth.slug} is served differently by the protocol and the library'
		)


def test_the_fallback_topic_is_not_a_drafted_one() -> None:
	"""`unknown` must stay outside the corpus: a real rumour filed under it would be indistinguishable
	from an unrecognised claim, and `recognised` would report True for a correction nobody drafted."""
	assert FALLBACK_TOPIC not in {m.topic for m in MYTHS}
	assert FALLBACK_TOPIC in CORRECTION_LIBRARY, 'the fallback must be answerable through the protocol'


def test_a_myth_cannot_restate_its_own_claim() -> None:
	"""The model refuses a row whose correction is the rumour, which is the shape the old corpus had:
	one string holding both, so a reader was told the rumour and left to infer the correction."""
	with pytest.raises(ValidationError):
		Myth(topic='cure_claim', slug='myth-x', lang='en', label='A label long enough',
		     claim='Salt water cures Ebola.', fact='Salt water cures Ebola.', source='MoH/PHEOC')


# --- the served surfaces -------------------------------------------------------------------------

def test_the_myth_routes_serve_the_format_and_no_spec_codes() -> None:
	"""The route is what a client reads. Every row carries all three parts, every slug is a slug, and
	nothing a person sees carries a section number."""
	app = _app()

	async def run() -> None:
		async with _client(app) as c:
			rows = (await c.get('/info/myths?lang=en')).json()
			assert rows, 'the route must serve the corpus'
			for row in rows:
				assert row['claim'] and row['fact'] and row['source'], row['slug']
				assert FEATURE_CODE.search(str(row)) is None, f'spec code in {row["slug"]}'
			# Search narrows, and the category route offers the myth tag.
			narrowed = (await c.get('/info/myths?lang=en&q=salt')).json()
			assert {r['slug'] for r in narrowed} == {'myth-salt-water'}
			facets = (await c.get('/info/library/categories?lang=en')).json()
			assert MYTH_TAG in {f['tag'] for f in facets}
			# The library search reaches the same corpus through the same implementation.
			lib = (await c.get('/info/library?lang=en&q=salt')).json()
			assert 'myth-salt-water' in {r['slug'] for r in lib}
			assert all('share_card' in r and 'share_url' in r for r in lib)

	asyncio.run(run())


def test_asking_about_a_rumour_is_served_without_an_account() -> None:
	"""§6.2.7's whole point is that the correction reaches the person who has the rumour. Requiring an
	account to ask whether something is true is how a correction stays unread, so the route is
	unauthenticated — and it stores nothing, which is why it is a justified unguarded write."""
	app = _app()

	async def run() -> None:
		async with _client(app) as c:
			refused = await c.post('/info/myths/ask')  # no claim
			assert refused.status_code == 422
			answer = await c.post('/info/myths/ask', json={'claim': 'warm salt water cures ebola'})
			assert answer.status_code == 200, answer.text
			body = answer.json()
			assert body['recognised'] is True and body['source'] == 'MoH/PHEOC'
			assert FEATURE_CODE.search(str(body)) is None

	asyncio.run(run())


def test_the_matching_topics_are_the_drafted_ones() -> None:
	"""A keyword table naming a topic with no myth is a classifier that answers with the fallback
	after claiming to have recognised the claim — the two must be the same set."""
	assert set(MYTH_KEYWORDS) == {m.topic for m in MYTHS}


def test_a_slug_resolves_back_to_its_topic_in_the_language_it_was_drafted() -> None:
	"""The route needs the category for a served row and has only the slug, so the lookup must be
	language-aware: the same slug exists in both languages and a topic found through the wrong one
	would report the wrong category."""
	for myth in MYTHS:
		assert topic_for_slug(myth.slug, myth.lang) == myth.topic
	assert topic_for_slug('no-such-slug', 'en') is None
