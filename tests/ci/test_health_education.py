"""§10.5's three features — the topics each names, and what the corpus actually covers.

§10.5 is INF-008 Health Tips, INF-009 First Aid and INF-010 Burial Guidance. All three were in the
registry and all three were accounted for in the coverage gate as "items in the health library
corpus", which is true of the one item each has and says nothing about the eight, eleven and six
topics the section names. What is tested here is that the topic lists are read off the spec, that
coverage is computed against the corpus rather than asserted about it, and that the report errs
toward naming a gap rather than naming a coverage it cannot see.
"""
import httpx

from afya.info.health_education import (
	BURIAL_CONTENT,
	FEATURE_TAG,
	FIRST_AID_TOPICS,
	HEALTH_TIP_FORMATS,
	HEALTH_TIP_TOPICS,
	SENSITIVITY_REVIEWERS,
	SPEC_FEATURES,
	covers,
	coverage,
	first_aid_is_offline,
	report,
)
from afya.info.service import InfoService
from afya.info.views import ContentItem


def _spec_section(heading: str) -> str:
	from pathlib import Path
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	return text.split(heading, 1)[1].split('\n#### ', 1)[0]


def _topic_list(heading: str, label: str) -> list[str]:
	"""A "**Topics:**" or "**Content:**" cell as a list. The content list is bullets, the topic lists
	are one comma-separated line, and both are read from the spec rather than retyped."""
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
	"""§INF-008's eight, §INF-009's eleven and §INF-010's six, read out of the spec. A revision that
	adds a topic the corpus has no item for is exactly the drift this catches: the list is what says
	the feature is more than the item behind it."""
	assert list(HEALTH_TIP_TOPICS) == _topic_list('#### INF-008', 'Topics')
	assert list(FIRST_AID_TOPICS) == _topic_list('#### INF-009', 'Topics')
	assert list(BURIAL_CONTENT) == _topic_list('#### INF-010', 'Content')
	assert len(HEALTH_TIP_TOPICS) == 8 and len(FIRST_AID_TOPICS) == 11 and len(BURIAL_CONTENT) == 6


def test_the_format_and_the_sensitivity_clause_are_carried() -> None:
	"""§INF-008's Format cell and §INF-010's Sensitivity clause. The clause's last sentence — "Emphasises
	dignity, not just safety" — is a content rule, and the three parties it names are a requirement on
	the process that produced the guidance, which is why they are data rather than a paragraph."""
	assert list(HEALTH_TIP_FORMATS) == ['Short cards', '30-second videos', 'audio clips']
	for party in SENSITIVITY_REVIEWERS:
		assert party in _spec_section('#### INF-010'), party
	assert 'dignity' in _spec_section('#### INF-010').lower()
	assert first_aid_is_offline().startswith('Fully offline.')
	assert first_aid_is_offline() in _spec_section('#### INF-009')


def test_every_section_10_5_feature_has_a_corpus_tag() -> None:
	"""The crossing from a feature to the corpus items that serve it. Without the tag, coverage is a
	claim about the corpus rather than a computation over it."""
	assert set(FEATURE_TAG) == set(SPEC_FEATURES) == {'INF-008', 'INF-009', 'INF-010'}


def test_coverage_is_computed_against_the_corpus_and_reports_both_ways() -> None:
	"""The finding. `covered` and `gaps` together account for every topic the section names, and the
	seed's first-aid item covers exactly one of §INF-009's eleven — which is the fact the old
	accounting ("first-aid items are in the health library corpus") could not express."""
	rows = {r['feature_id']: r for r in report(InfoService().all_items())}
	assert set(rows) == set(SPEC_FEATURES)
	for fid, topics in (('INF-008', HEALTH_TIP_TOPICS), ('INF-009', FIRST_AID_TOPICS), ('INF-010', BURIAL_CONTENT)):
		row = rows[fid]
		covered, gaps = row['covered'], row['gaps']
		assert isinstance(covered, list) and isinstance(gaps, list)
		assert len(covered) + len(gaps) == len(topics), fid
		assert sorted(covered + gaps) == sorted(topics), fid
		assert row['topics'] == len(topics)
	# The seed's first-aid item is the choking item and there is one of it.
	assert rows['INF-009']['covered'] == ['choking']
	first_aid_gaps = rows['INF-009']['gaps']
	assert isinstance(first_aid_gaps, list)
	assert 'snakebite' in first_aid_gaps and 'Bleeding' in first_aid_gaps


def test_a_topic_is_covered_by_an_items_own_words_not_by_its_tag() -> None:
	"""A tag saying `first-aid` over an item about burns does not cover snakebite. `covers` reads the
	item's title, body and slug, so the report is about what the corpus says rather than about how it
	is filed — and the test plants the counter-case: the same tag, a different subject."""
	choking = next(i for i in InfoService().all_items() if i.harmony_tag == 'first-aid')
	assert covers(choking, 'choking') is True
	assert covers(choking, 'snakebite') is False
	assert covers(choking, 'drowning') is False


def test_the_check_errs_toward_naming_a_gap() -> None:
	"""The direction the error runs, asserted rather than left to a docstring. The seed's handwashing
	tip is hygiene and does not contain the word, so it reports as a gap; and a generic word like
	"health" must not make every health topic covered, which is the false positive that would hide a
	hole by reporting the corpus as complete."""
	svc = InfoService()
	tip = next(i for i in svc.all_items() if i.slug == 'health-tips')
	# The tip's own subject is hygiene, and it does not say so — an under-report, which is the safe way.
	assert covers(tip, 'Hygiene') is False
	# The generic-word guard: "health" alone must not cover the -health topics.
	assert covers(tip, 'mental health') is False
	assert covers(tip, 'sexual and reproductive health') is False
	# But a planted item that does say it is covered, so the check is not simply always-false.
	planted = ContentItem(
		item_id='X-1', title='Snakebite first aid', body='Immobilise the limb and go to a clinic.',
		lang='en', harmony_tag='first-aid', slug='first-aid-snakebite', owner='o', reviewer='r',
		reviewed_on_iso='2026-10-01', version=1,
	)
	assert covers(planted, 'snakebite') is True
	assert coverage([planted], 'INF-009', FIRST_AID_TOPICS)['covered'] == ['snakebite']


async def test_the_report_is_served() -> None:
	"""§10.5 over HTTP, auditor-scoped because it reports what the corpus is missing rather than what
	a client may read."""
	from afya.service import build_services, create_app

	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		r = await c.get('/info/health-education')
	assert r.status_code in (200, 401, 403), r.status_code
	if r.status_code == 200:
		body = r.json()
		assert len(body['coverage']) == 3
		assert len(body['first_aid_topics']) == 11
		assert body['first_aid_offline'] == first_aid_is_offline()
