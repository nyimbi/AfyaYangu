"""§8.5's library and §10.5's three features — the topics each names, and what the corpus covers.

§10.5 is INF-008 Health Tips, INF-009 First Aid and INF-010 Burial Guidance; §INF-003 is §8.5's
Ebola Information Library, which has the same shape one section up. All four were in the registry and
all four were accounted for in the coverage gate as "items in the health library corpus", which is
true of the one item each had and says nothing about the nine, eight, eleven and six topics the
sections name. What is tested here is that the topic lists are read off the spec, that coverage is
computed against the corpus rather than asserted about it, that the printed *formats* are delivered,
and that the report errs toward naming a gap rather than naming a coverage it cannot see.
"""
import httpx

from afya.info.health_education import (
	ARTICLE_MAX_WORDS,
	BURIAL_CONTENT,
	EBOLA_FORMATS,
	EBOLA_TOPICS,
	FEATURE_FORMATS,
	FEATURE_TAG,
	FEATURE_TOPICS,
	FIRST_AID_TOPICS,
	HEALTH_TIP_FORMATS,
	HEALTH_TIP_TOPICS,
	SENSITIVITY_REVIEWERS,
	SPEC_FEATURES,
	covers,
	coverage,
	first_aid_is_offline,
	format_coverage,
	over_length,
	report,
)
from afya.info.service import InfoService
from afya.info.views import ContentItem


def _spec_section(heading: str) -> str:
	from pathlib import Path
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	return text.split(heading, 1)[1].split('\n#### ', 1)[0]


def _spec_list(heading: str, label: str) -> list[str]:
	"""A "**Topics:**", "**Content:**" or "**Format:**" cell as a list. The content lists are bullets,
	the topic and format lists are one comma-separated line, and both are read from the spec rather
	than retyped."""
	section = _spec_section(heading)
	lines = section.splitlines()
	start = next(i for i, ln in enumerate(lines) if ln.startswith(f'**{label}:**'))
	head = lines[start].split(':', 1)[1].strip().removeprefix('**').strip()
	if head:
		# The cell ends with a sentence period, which is punctuation and not part of the last
		# topic — "…and sexual and reproductive health." is a sentence, not a topic spelled with a
		# full stop. Stripped here so the list compares as topics rather than as prose.
		return [t.strip().rstrip('.') for t in head.split(',') if t.strip()]
	items: list[str] = []
	for ln in lines[start + 1:]:
		if not ln.startswith('- '):
			break
		items.append(ln[2:].strip())
	return items


def test_the_topic_lists_are_the_sections_own() -> None:
	"""§INF-003's nine, §INF-008's eight, §INF-009's eleven and §INF-010's six, read out of the spec. A
	revision that adds a topic the corpus has no item for is exactly the drift this catches: the list
	is what says the feature is more than the item behind it."""
	assert list(EBOLA_TOPICS) == _spec_list('#### INF-003', 'Topics')
	assert list(HEALTH_TIP_TOPICS) == _spec_list('#### INF-008', 'Topics')
	assert list(FIRST_AID_TOPICS) == _spec_list('#### INF-009', 'Topics')
	assert list(BURIAL_CONTENT) == _spec_list('#### INF-010', 'Content')
	assert len(EBOLA_TOPICS) == 9 and len(HEALTH_TIP_TOPICS) == 8
	assert len(FIRST_AID_TOPICS) == 11 and len(BURIAL_CONTENT) == 6


def test_the_format_and_the_sensitivity_clause_are_carried() -> None:
	"""The two Format cells and §INF-010's Sensitivity clause. The clause's last sentence — "Emphasises
	dignity, not just safety" — is a content rule, and the three parties it names are a requirement on
	the process that produced the guidance, which is why they are data rather than a paragraph."""
	assert list(EBOLA_FORMATS) == _spec_list('#### INF-003', 'Format')
	assert list(HEALTH_TIP_FORMATS) == _spec_list('#### INF-008', 'Format')
	for party in SENSITIVITY_REVIEWERS:
		assert party in _spec_section('#### INF-010'), party
	assert 'dignity' in _spec_section('#### INF-010').lower()
	assert first_aid_is_offline().startswith('Fully offline.')
	assert first_aid_is_offline() in _spec_section('#### INF-009')


def test_every_feature_here_has_a_corpus_tag_and_a_topic_list() -> None:
	"""The crossing from a feature to the corpus items that serve it. Without the tag, coverage is a
	claim about the corpus rather than a computation over it; without the topic list there is nothing
	to compute coverage *of*."""
	assert set(FEATURE_TAG) == set(FEATURE_TOPICS) == set(SPEC_FEATURES)
	assert set(SPEC_FEATURES) == {'INF-003', 'INF-008', 'INF-009', 'INF-010'}


def test_coverage_is_computed_against_the_corpus_and_reports_both_ways() -> None:
	"""`covered` and `gaps` together account for every topic the section names, and the report is a
	computation over the corpus rather than a claim about it. The partition is asserted before the
	content of the two halves, because a report that dropped a topic would pass any assertion about
	what it did name."""
	rows = {r['feature_id']: r for r in report(InfoService().all_items())}
	assert set(rows) == set(SPEC_FEATURES)
	for fid, topics in FEATURE_TOPICS.items():
		row = rows[fid]
		covered, gaps = row['covered'], row['gaps']
		assert isinstance(covered, list) and isinstance(gaps, list)
		assert len(covered) + len(gaps) == len(topics), fid
		assert sorted(covered + gaps) == sorted(topics), fid
		assert row['topics'] == len(topics)
		counted = row['items']
		assert isinstance(counted, int) and counted > 0, f'{fid} has a tag nothing in the corpus carries'


def test_the_corpus_covers_every_topic_the_four_sections_name() -> None:
	"""The gaps list is the finding, and it is empty. A gap here is a topic the section prints and no
	item answers — the hole a reader of "the Ebola library has items" could not see. Named per feature
	rather than as a total, so a regression in one section cannot hide behind a repair in another."""
	rows = {r['feature_id']: r for r in report(InfoService().all_items())}
	for fid, row in sorted(rows.items()):
		assert row['gaps'] == [], f'{fid} names topics no corpus item covers: {row["gaps"]}'


def test_the_formats_the_sections_print_are_delivered() -> None:
	"""The second dimension. §INF-003 asks for "illustrations, audio versions, video versions" and
	§INF-008 for "30-second videos, audio clips", and a corpus of articles answers none of them — a
	library that serves the audience §3.3 principle 8 puts first (low literacy, low bandwidth) none of
	what the section asks for, invisible while "the library has items" is the check."""
	items = InfoService().all_items()
	for fid in FEATURE_FORMATS:
		row = format_coverage(items, fid)
		assert row['missing_formats'] == [], f'{fid} prints formats nothing delivers: {row}'
		delivered = row['delivered']
		assert isinstance(delivered, list), row
		assert set(delivered) == {label for label, _ in FEATURE_FORMATS[fid]}
	# The rendition formats are the ones that carry a file, and the model refuses one without it, so
	# this is a count over servable renditions rather than over claims to have made them.
	renditions = [i for i in items if i.media_ref is not None]
	assert {i.format.value for i in renditions} <= {'illustration', 'audio', 'video'}
	assert renditions, 'a format table with no rendition behind it is a format table'


def test_no_article_exceeds_the_sections_own_word_limit() -> None:
	"""§INF-003 prints the limit inside its Format cell — "Short articles (under 200 words)" — so it is
	a requirement on the corpus rather than on the format's name. Reported rather than enforced: an
	article at 210 words is not a defect a serving route should refuse over."""
	assert ARTICLE_MAX_WORDS == 200
	assert over_length(InfoService().all_items()) == []
	planted = ContentItem(
		item_id='X-9', title='Long', body='word ' * (ARTICLE_MAX_WORDS + 1), lang='en',
		harmony_tag='ebola-library', slug='too-long', owner='o', reviewer='r',
		reviewed_on_iso='2026-10-01', version=1,
	)
	assert over_length([planted]) == ['too-long'], 'the check must be able to name one'


def test_a_topic_is_covered_by_an_items_own_words_not_by_its_tag() -> None:
	"""A tag saying `first-aid` over an item about burns does not cover snakebite. `covers` reads the
	item's title, body and slug, so the report is about what the corpus says rather than about how it
	is filed — and the test plants the counter-case: the same tag, a different subject."""
	choking = next(i for i in InfoService().all_items() if i.slug == 'first-aid-choking')
	assert covers(choking, 'choking') is True
	assert covers(choking, 'snakebite') is False
	assert covers(choking, 'drowning') is False


def test_the_check_errs_toward_naming_a_gap() -> None:
	"""The direction the error runs, asserted rather than left to a docstring, and asserted against
	planted items so it is a test of the predicate rather than of the seed.

	The first version of `covers` matched any keyword and read `'for' in haystack`, so a burial item
	covered "Support for grieving families" by containing the word "for" and an Ebola item covered
	"Stigma and how to fight it" by containing "it". A predicate that is a strict subset of what it
	tests fails toward "clean", and clean is the answer that hides the hole.
	"""
	# The subject is hygiene and the item does not say the word: an under-report, which is the safe way.
	handwashing = ContentItem(
		item_id='X-1', title='Wash your hands', body='Soap and running water at five key times.',
		lang='en', harmony_tag='tips', slug='health-tips-handwashing', owner='o', reviewer='r',
		reviewed_on_iso='2026-10-01', version=1,
	)
	assert covers(handwashing, 'Hygiene') is False
	# The generic-word guard: "health" alone must not cover the -health topics, and the burial item's
	# "for" must not cover a topic phrased with it.
	assert covers(handwashing, 'mental health') is False
	assert covers(handwashing, 'sexual and reproductive health') is False
	# But a planted item that does say it is covered, so the check is not simply always-false.
	planted = ContentItem(
		item_id='X-2', title='Snakebite first aid', body='Immobilise the limb and go to a clinic.',
		lang='en', harmony_tag='first-aid', slug='first-aid-snakebite', owner='o', reviewer='r',
		reviewed_on_iso='2026-10-01', version=1,
	)
	assert covers(planted, 'snakebite') is True
	assert covers(planted, 'shock') is False
	assert coverage([planted], 'INF-009', FIRST_AID_TOPICS)['covered'] == ['snakebite']
	# And the sibling rule: the burial topics all say "burial", so an item that only says it does not
	# cover them all. The one it *does* cover needs the word the topic is about — "Ebola" — because
	# "burial" is shared by all six topics and is what the sibling filter drops.
	burial = ContentItem(
		item_id='X-3', title='Safe burial', body='Burial teams wear protective equipment.',
		lang='en', harmony_tag='burial', slug='safe-burial', owner='o', reviewer='r',
		reviewed_on_iso='2026-10-01', version=1,
	)
	assert covers(burial, 'Cultural and religious considerations', BURIAL_CONTENT) is False
	assert covers(burial, 'Why safe burial matters for Ebola', BURIAL_CONTENT) is False, \
		'it does not say why burial matters for Ebola, and "burial" is shared by all six topics'
	ebola_burial = burial.model_copy(update={
		'title': 'Why safe burial matters for Ebola',
		'body': 'Traditional washing of Ebola bodies spreads the virus.',
	})
	assert covers(ebola_burial, 'Why safe burial matters for Ebola', BURIAL_CONTENT) is True
	assert covers(ebola_burial, 'Support for grieving families', BURIAL_CONTENT) is False


async def test_the_report_is_served() -> None:
	"""§8.5's and §10.5's four features over HTTP, auditor-scoped because the report names what the
	corpus is missing rather than what a client may read."""
	from afya.service import build_services, create_app

	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		r = await c.get('/info/health-education')
	assert r.status_code in (200, 401, 403), r.status_code
	if r.status_code == 200:
		body = r.json()
		assert len(body['coverage']) == len(SPEC_FEATURES)
		assert {row['feature_id'] for row in body['coverage']} == set(SPEC_FEATURES)
		assert len(body['first_aid_topics']) == 11
		assert body['first_aid_offline'] == first_aid_is_offline()
