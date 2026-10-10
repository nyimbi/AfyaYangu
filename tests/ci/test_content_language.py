"""Gate: §6.2.4's "never publish English-only for a life-safety message", and §6.1 behind it.

§6.2.4's second sentence had no jurisdiction. `ContentItem` carried a `lang` and `library(lang='en')`
served whatever existed in English, so a life-safety message could be published in English alone and
served to an audience whose first language §3.3 principle 8 says is Swahili. Nothing marked an item
life-safety, so the rule could not bite — the same shape as §6.2's nine prose rules before they
became tables.

§6.1 is what supplies the jurisdiction. It ranks ten questions "by real demand, not by what health
authorities want to publish"; the first eight decide whether someone seeks care or infects a
household, and an item that answers one of them is a life-safety message. The rank is a reference
into the section's own table rather than a boolean an author sets, because whoever is drafting under
time pressure is the last person to mark their own copy as life-safety.

The rule is enforced in three places and all three are tested here: the library withholds an
untranslated life-safety item in *both* languages, `POST /info/content` refuses to publish one, and
`/info/content/{id}/advance` refuses to walk one into `published` — the third because an item
drafted in English reaches the published stage through the advance route, so a check on the write
alone would guard the door beside the one everybody uses.
"""
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from afya.info.questions import RANKED_QUESTIONS, REQUIRED_LANGS, is_life_safety, life_safety_ranks
from afya.info.service import InfoService
from afya.info.views import ContentItem, ContentStage

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / 'docs' / 'spec.md'


def _item(**overrides: object) -> ContentItem:
	"""A published, governed, *dated* item. The stamp is set because these tests write straight into
	`_content` rather than through `upsert_content`, and `library()` withholds an item carrying no
	timestamp (§6.2.3) — without it every assertion here would fail for a reason that has nothing to
	do with §6.2.4. `test_content_recency.py` is where the undated case belongs."""
	body: dict[str, object] = {
		'item_id': 'x', 'title': 't', 'body': 'b', 'lang': 'en', 'harmony_tag': 'official', 'slug': 's',
		'owner': 'MoH Health Promotion Unit', 'reviewer': 'Clinical advisory group',
		'reviewed_on_iso': '2026-10-01', 'version': 1, 'stage': ContentStage.published,
		'updated_at_ms': 1_790_812_800_000,
	}
	return ContentItem(**{**body, **overrides})  # type: ignore[arg-type]


# --- §6.1's table, and what makes a message life-safety -----------------------------------------

def test_the_ten_questions_are_the_sections_own() -> None:
	"""Transcribed, not paraphrased. The ordering is the section's whole contribution — it is
	explicit that it is "by real demand, not by what health authorities want to publish" — so a
	revision that reorders the table must fail here until the code moves with it."""
	spec = SPEC.read_text(encoding='utf-8')
	assert [q.rank for q in RANKED_QUESTIONS] == list(range(1, 11))
	for q in RANKED_QUESTIONS:
		assert q.question in spec, f'rank {q.rank} question {q.question!r} is not §6.1’s wording'
		assert q.response in spec, f'rank {q.rank} response {q.response!r} is not §6.1’s wording'


def test_a_life_safety_claim_carries_its_reason() -> None:
	"""A row cannot claim the flag without stating the consequence that makes it one, and a reason
	without the claim is equally refused — the flag is what §6.2.4's language rule keys on, so an
	unjustified True would withhold content on no stated grounds."""
	with pytest.raises(ValidationError):
		_ranked(rank=1, life_safety=True, why_life_safety=None)
	with pytest.raises(ValidationError):
		_ranked(rank=1, life_safety=False, why_life_safety='because')
	assert all(q.why_life_safety for q in RANKED_QUESTIONS if q.life_safety)


def _ranked(**overrides: object) -> object:
	from afya.info.questions import RankedQuestion
	body: dict[str, object] = {
		'rank': 1, 'question': 'q', 'response': 'r', 'life_safety': False, 'why_life_safety': None,
	}
	return RankedQuestion(**{**body, **overrides})  # type: ignore[arg-type]


def test_the_life_safety_set_is_not_the_whole_table() -> None:
	"""Canary for the flag: if every rank were life-safety the rule would withhold everything and
	§6.2.4 would stop being a rule about life-safety messages. Two of §6.1's ten are informational."""
	assert life_safety_ranks() == frozenset({1, 2, 3, 4, 5, 6, 7, 8}), life_safety_ranks()
	assert not is_life_safety(9) and not is_life_safety(10), 'the case count and service status are not life-safety'
	assert not is_life_safety(None), 'an item answering no §6.1 question is not claimed as life-safety'


# --- the library withholds an untranslated life-safety item ---------------------------------------

def test_a_life_safety_item_is_withheld_until_both_languages_exist() -> None:
	"""§6.2.4 forbids publishing English-only for a life-safety message, and serving *is* publishing.
	The item is withheld in both languages rather than served in one — a gap a reviewer can see beats
	an English-only message a Swahili speaker cannot read."""
	svc = InfoService()
	svc._content['new-en'] = _item(item_id='new-en', slug='new-guidance', answers_rank=3)
	assert 'new-guidance' not in {c.slug for c in svc.library('en')}, 'English-only life-safety must not be served'
	assert svc.untranslated() == ['new-guidance'], 'and the gap must be named, not silent'
	svc._content['new-sw'] = _item(item_id='new-sw', slug='new-guidance', lang='sw', answers_rank=3)
	assert 'new-guidance' in {c.slug for c in svc.library('en')}, 'with the counterpart it is served'
	assert svc.untranslated() == []


def test_an_item_answering_no_ranked_question_is_unconstrained() -> None:
	"""The canary that keeps the rule from being a blanket translation requirement. First aid for
	choking answers none of §6.1's ten questions and is served in whichever languages exist — a rule
	that withheld it would be enforcing a policy the section does not state."""
	svc = InfoService()
	svc._content['aid-en'] = _item(item_id='aid-en', slug='aid-only', answers_rank=None)
	assert 'aid-only' in {c.slug for c in svc.library('en')}, 'unranked content is not withheld'
	assert svc.untranslated() == []


def test_an_unpublished_translation_does_not_count() -> None:
	"""A counterpart in the workflow is not a counterpart. §6.5's stages exist so that unreviewed
	clinical text is not read; a Swahili translation sitting at `clinical_review` satisfies §6.2.4's
	*letter* — the item exists in two languages — while leaving the reader with an English-only
	message. The counterpart must be published to count, which is what the stage filter in
	`translated()` is for."""
	svc = InfoService()
	svc._content['pair-en'] = _item(item_id='pair-en', slug='pair', answers_rank=3)
	svc._content['pair-sw'] = _item(item_id='pair-sw', slug='pair', lang='sw', answers_rank=3,
	                                stage=ContentStage.clinical_review)
	assert 'pair' not in {c.slug for c in svc.library('en')}, 'a draft translation is not a translation'
	assert svc.untranslated() == ['pair']
	svc._content['pair-sw'] = svc._content['pair-sw'].model_copy(update={'stage': ContentStage.published})
	assert 'pair' in {c.slug for c in svc.library('en')}


def test_the_seed_is_fully_translated_where_it_is_life_safety() -> None:
	"""The shipped corpus obeys its own rule, and the two unranked pairs prove the rule is not
	vacuous — a corpus where nothing was life-safety would pass every test above while enforcing
	nothing."""
	svc = InfoService()
	assert svc.untranslated() == [], 'the seed must not ship an English-only life-safety message'
	ranks = {c.answers_rank for c in svc.all_items()}
	assert ranks & life_safety_ranks(), 'the seed must exercise the life-safety path'
	assert None in ranks, 'and must contain at least one item answering no ranked question'
	slugs = {c.slug for c in svc.all_items()}
	for slug in slugs:
		langs = {c.lang for c in svc.all_items() if c.slug == slug}
		assert langs == set(REQUIRED_LANGS), f'{slug} exists in {langs} only'


def test_the_seed_assigns_the_ranks_six_one_gives_them() -> None:
	"""The rank is an assignment, so it is pinned rather than left to whatever the corpus happens to
	carry. Every check above passes while a life-safety row is quietly marked `None` — the corpus
	stays bilingual, some other row still exercises the path — and the effect is that §6.2.4 stops
	protecting that message. That is the mutation this test exists to catch: `prevention` answers
	§6.1 rank 4, "How do I protect my family?", and the household checklist is exactly the guidance
	§6.2.4 must not ship English-only."""
	svc = InfoService()
	assigned = {c.slug: c.answers_rank for c in svc.all_items() if c.lang == 'en'}
	assert assigned == {
		'ebola-basics': 3,       # I have a fever right now — what do I do?
		'prevention': 4,         # How do I protect my family?
		'myth-salt-water': 5,    # What's true and what's rumour?
		'safe-burial': 4,        # household risk; the burial row answers the protection question
		'health-tips': None,     # a general tip, not one of §6.1's ten questions
		'first-aid-choking': None,  # choking is not a question §6.1 ranks
	}, assigned
	# And every slug the corpus marks life-safety must be gated, so the two cannot disagree.
	for item in svc.all_items():
		if is_life_safety(item.answers_rank):
			assert item.slug in {'ebola-basics', 'prevention', 'myth-salt-water', 'safe-burial'}, item.slug


# --- the two publishing paths both refuse ---------------------------------------------------------

def _governed(**overrides: object) -> dict[str, object]:
	body: dict[str, object] = {
		'item_id': 'x', 'title': 'Fever guidance', 'body': 'Call 719 if you have fever.', 'lang': 'en',
		'harmony_tag': 'official', 'slug': 'fever-guidance',
		'owner': 'MoH Health Promotion Unit', 'reviewer': 'Clinical advisory group',
		'reviewed_on_iso': '2026-10-01', 'version': 1, 'answers_rank': 3,
	}
	return {**body, **overrides}


async def _app_and_headers() -> tuple[Any, dict[str, str]]:
	from afya.auth.service import AuthService
	from afya.privacy.views import RBACRole
	from afya.service import build_services, create_app
	services = build_services()
	auth: AuthService = services['auth']  # type: ignore[assignment]
	token = auth.provision_staff('ops-0', RBACRole.sysadmin, registrar='MoH ops').access_token
	return create_app(services), {'authorization': f'Bearer {token}'}


async def test_publishing_refuses_an_english_only_life_safety_message() -> None:
	"""§6.2.4 at the moment of publishing, which is the only point where the missing translation can
	still be written. The refusal names the question that made it life-safety, so the author knows
	why this item and not the last one."""
	import httpx
	app, h = await _app_and_headers()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		refused = await c.post('/info/content', json=_governed(stage='published'), headers=h)
		assert refused.status_code == 422, refused.text
		assert 'content_language' in refused.text and 'life-safety' in refused.text
		# A draft of the same item is accepted — the rule bites at publishing, not at drafting, so an
		# author is never blocked from writing the English text first.
		assert (await c.post('/info/content', json=_governed(stage='draft'), headers=h)).status_code == 200


async def test_advancing_into_published_refuses_it_too() -> None:
	"""The second door. An item drafted in English reaches `published` through the advance route, so
	a check on `POST /info/content` alone guards the entrance beside the one everybody uses. This is
	the call-site canary that matters: the first version of this work checked only the write."""
	import httpx
	app, h = await _app_and_headers()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		assert (await c.post('/info/content', json=_governed(stage='draft'), headers=h)).status_code == 200
		for stage in ('clinical_review', 'translation', 'back_translation', 'community_validation'):
			assert (await c.post(f'/info/content/x/advance?to={stage}', headers=h)).status_code == 200
		refused = await c.post('/info/content/x/advance?to=published', headers=h)
		assert refused.status_code == 422, refused.text
		assert 'content_language' in refused.text, 'the advance route must refuse on §6.2.4, not on the workflow'


async def test_the_governance_view_names_the_withheld_items() -> None:
	"""A gate that withheld content silently would be worse than the English-only message it
	prevents: the audience sees nothing and nobody is told why. The audit is served on §6.5's own
	governance view, where the reviewer already is."""
	import httpx
	from afya.auth.service import AuthService
	from afya.info.service import InfoService
	from afya.privacy.views import RBACRole
	from afya.service import build_services, create_app
	services = build_services()
	auth: AuthService = services['auth']  # type: ignore[assignment]
	auditor = auth.provision_staff('ops-1', RBACRole.auditor, registrar='MoH ops').access_token
	# Withhold one life-safety item by publishing it in English alone, at the service, so the served
	# audit has something to report. The route refuses to do this — which is the other test — so the
	# state is constructed directly rather than reached through a door that is correctly shut.
	svc: InfoService = services['info']  # type: ignore[assignment]
	svc._content['lonely'] = _item(item_id='lonely', slug='lonely-guidance', answers_rank=3)
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		gov = (await c.get('/info/content/governance', headers={'authorization': f'Bearer {auditor}'})).json()
		assert gov['untranslated_life_safety'] == ['lonely-guidance'], gov['untranslated_life_safety']
		assert 'lonely-guidance' not in {r['slug'] for r in (await c.get('/info/library?lang=en')).json()}, \
			'the withheld item must not be served while the audit names it'


def test_the_ranked_question_route_serves_the_order() -> None:
	"""§6.1's order is the section's contribution; a client that lists the library alphabetically has
	thrown it away. Served so a client can lead with what people actually ask first."""
	svc = InfoService()
	served = [q.rank for q in svc.ranked_questions()]
	assert served == list(range(1, 11)), served
	assert svc.ranked_questions()[0].question == 'Is it near me?'
