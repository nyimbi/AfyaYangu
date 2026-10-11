"""§3's vision, positioning, design principles and non-goals — and the brand check §20.2 declares
and nothing performed.

The unit under test is `afya.brand`, which exists because §3 was the one section of the spec with no
representation in the code: §3.3's twelve principles were cited by number in five modules and the
table saying which number means what was nowhere, and §3.2's "It is not 'the Ebola app'" had a check
named in `rollout.ANTIPATTERNS` that no code ran.
"""
import httpx
import pytest

from afya.brand.service import (
	BRAND,
	NON_GOALS,
	PRINCIPLE,
	PRINCIPLES,
	VISION,
	brand_is_clean,
	brand_violations,
	principle,
)
from afya.brand.views import NonGoal
from afya.registry.diseases import DISEASE_ROWS


def _spec_section(heading: str) -> str:
	"""One `###` subsection of `docs/spec.md`, terminated by the next heading of the same depth."""
	from pathlib import Path
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	return text.split(heading, 1)[1].split('\n### ', 1)[0]


def _bold(cell: str) -> str:
	return cell.removeprefix('**').removesuffix('**').strip()


def test_the_principle_table_is_the_sections_twelve_rows() -> None:
	"""§3.3 transcribed row for row. Four of these numbers are cited elsewhere in the source
	(`personas` cites 1, the channel cost model 3, the content rules 8 and 9, `registry.diseases` 12),
	so a revision that renumbers the table silently repoints every one of those citations. Comparing
	against the spec text is what makes the renumbering fail here instead."""
	rows = [
		line for line in _spec_section('### 3.3 Design Principles').splitlines()
		if line.startswith('|') and not set(line) <= set('|-: ')
	]
	rows = [r for r in rows if r.strip('|').strip().split('|')[0].strip() != '#']
	spec = [(_bold(c[1]), c[2].strip()) for c in ([x.strip() for x in r.strip('|').split('|')] for r in rows)]

	assert len(spec) == 12, '§3.3 is twelve rows'
	assert [(p.principle, p.implication) for p in PRINCIPLES] == spec
	assert [p.number for p in PRINCIPLES] == list(range(1, 13))


def test_the_non_goals_are_the_sections_five_and_nothing_else() -> None:
	"""§3.4's five bullets, verbatim. An enum rather than a list because each is a boundary a feature
	crosses by accident — a premium flag, a follower graph, a diagnosis string — and a boundary only
	written in prose is one nothing refuses."""
	spec = [
		line.removeprefix('- ').strip()
		for line in _spec_section('### 3.4 Non-Goals').splitlines()
		if line.startswith('- ')
	]
	assert len(spec) == 5
	assert [g.value for g in NON_GOALS] == spec
	assert len(NonGoal) == 5


def test_the_vision_and_the_two_names_are_the_sections_own_words() -> None:
	"""§3.1 and §3.2. The vision is the whole argument for §7.1's tier model in one sentence; the two
	names are carried with their English gloss because the section writes them as pairs and a reader
	meeting "Mlinzi" in a log has nowhere else to learn what it means."""
	vision = _spec_section('### 3.1 Vision').strip().removeprefix('> ').strip()
	assert VISION == vision
	assert BRAND.public_name == 'Afya Yangu' and BRAND.public_name_english == 'My Health'
	assert BRAND.programme_name == 'Mlinzi' and BRAND.programme_name_english == 'Guardian'
	assert 'the Ebola app' in BRAND.not_the_ebola_app


def test_a_citation_to_a_principle_resolves_or_refuses() -> None:
	"""A "§3.3 principle N" citation is only checkable if something carries the row. `principle()`
	refuses a number the section does not have rather than returning None, because a citation that
	resolves to nothing is the failure this module exists to make impossible."""
	assert principle(12).principle == 'Build for the outbreak after this one'
	assert principle(1).principle == 'Channels before apps'
	with pytest.raises(AssertionError):
		principle(13)
	with pytest.raises(AssertionError):
		principle(0)
	assert PRINCIPLE[3].implication.startswith('Data cost')


def test_the_brand_check_fires_on_the_name_the_antipattern_names() -> None:
	"""§20.2's "A name with 'Ebola' in it", which `rollout.ANTIPATTERNS` declares with
	`check='the served product name contains no disease name'` and nothing performed. The check is
	the point of this test: the anti-pattern being *present* in the table was already asserted, and a
	declared check that never runs is indistinguishable from a passing one."""
	assert brand_violations('Afya Yangu') == []
	assert brand_is_clean('Afya Yangu') is True
	assert brand_violations('Ebola Tracker') == ['Ebola']
	assert brand_violations('EBOLA Response') == ['Ebola'], 'case-insensitive: the store listing is the failure'
	assert brand_is_clean('Ebola Tracker') is False


def test_the_forbidden_words_are_the_disease_vocabulary_itself() -> None:
	"""The list is derived from `DISEASE_ROWS`, not written out, so a disease added to §3.3 principle
	12's set is one the brand check refuses with no second edit. `other` is excluded — "Unnamed
	disease (the next unknown)" is a placeholder, and a name containing it is not the anti-pattern."""
	from afya.brand.service import _disease_words
	from afya.registry.diseases import OTHER

	words = _disease_words()
	assert set(words) == {r.english for r in DISEASE_ROWS if r.slug != OTHER}
	assert not any('Unnamed' in w for w in words)
	for word in words:
		assert brand_violations(f'Kenya {word} Line') == [word], word


def test_every_disease_is_reported_not_just_the_first() -> None:
	"""A name that manages to carry two diseases is not half-reported — the caller gets the whole
	list, so a reviewer sees the full extent of the rename rather than one word of it."""
	found = brand_violations('Ebola and Cholera Watch')
	assert set(found) == {'Ebola', 'Cholera'}


def test_the_antipatterns_declared_check_is_performed_here() -> None:
	"""§20.2's anti-pattern declares `check='the served product name contains no disease name'` and,
	until this module, nothing performed it. The test that already existed asserts the anti-pattern is
	*present*; this one asserts the declared check is the check that runs — the same code path the
	route and the import-time assert call, so a reworded check string fails here rather than drifting
	away from the function it names."""
	from afya.rollout.service import ANTIPATTERNS

	declared = {p.antipattern: p for p in ANTIPATTERNS}['A name with "Ebola" in it']
	assert declared.checkable is True
	assert declared.check == 'the served product name contains no disease name'
	# The check, performed on the artefact it names: a served name with a disease in it is refused.
	assert brand_is_clean(BRAND.public_name) is True, declared.check
	assert brand_violations('Ebola Response') != [], declared.check


async def test_the_section_is_served_with_its_own_verdict() -> None:
	"""§3 over HTTP. The brand check travels with the section rather than being a function a caller
	has to know to import — a route that served the principles and left the check behind would put
	the anti-pattern back in the position it was in."""
	from afya.service import build_services, create_app

	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		body = (await c.get('/brand')).json()

	assert body['vision'] == VISION
	assert body['brand']['public_name'] == 'Afya Yangu'
	assert len(body['principles']) == 12 and body['principles'][11]['number'] == 12
	assert len(body['non_goals']) == 5
	# The verdict is checked against the function rather than against a literal. A literal here would
	# pass for a route that hard-coded the answer, which is the failure the check exists to prevent —
	# the first version of this assertion compared to `True` and the canary that replaced the call
	# with `True` sailed through it.
	check = body['name_check']
	assert check['name'] == BRAND.public_name
	assert check['violations'] == brand_violations(check['name'])
	assert check['clean'] == brand_is_clean(check['name'])
