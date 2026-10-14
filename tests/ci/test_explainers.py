"""§CHAN-004's animated explainers, and the generator that produces them from the corpus.

§CHAN-004's Content types ask for "Animated explainers on symptoms and prevention", which was the
`missing` row the section carried: the corpus had an `illustration` format, and a still SVG is a
different medium from one that moves. What closes it is not an asset checked in by hand — that would
be a file nothing keeps in step with the text it explains — but a generator that turns a parent item's
*own* sentences into a scene sequence, plus the committed output of that generator, compared byte for
byte here.

The tests are shaped by what would make each check pass vacuously:

* A determinism test that calls the generator twice and compares is only meaningful if the output has
  something in it that could vary — so it is run over the real corpus items and the SVG is asserted to
  carry the animation it is supposed to.
* A committed-asset test that asserted the file *exists* would pass on an empty file. This one compares
  bytes against a fresh render, so a corpus edit that is not regenerated fails.
* The animation test parses the XML and asserts a timeline, not the presence of an `<animate>` tag: a
  still with one `<animate>` in it is exactly the thing the audit row is about, and it would satisfy a
  substring check.
* The format-coverage test reads the set of non-text formats off the enum rather than naming them, so
  the next format added is covered by the check rather than by whoever remembers to widen a literal.
"""
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from afya.info.content_seed import seed_rows
from afya.info.explainers import (
	EXPLAINER_DIR,
	asset_path,
	explainer_assets,
	render_explainer,
	scene_plan,
)
from afya.info.recency import UNDATED_MS
from afya.info.service import InfoService
from afya.info.views import ContentFormat, ContentItem, ContentStage

SVG_NS = '{http://www.w3.org/2000/svg}'
COMMITTED = sorted(EXPLAINER_DIR.glob('*.svg'))


@pytest.fixture
def svc() -> InfoService:
	return InfoService()


def _parents() -> dict[str, ContentItem]:
	"""The seed's parent items by slug, `en` preferred — the ones the explainers caption from."""
	return {i.slug: i for i in seed_rows() if i.slug and i.lang == 'en'}


def _animation_elements(root: ET.Element) -> list[ET.Element]:
	"""Every SMIL animation element in the tree. `<animate>` and `<animateTransform>` are separate tags,
	and a check for one would miss a file that only slides."""
	return [e for e in root.iter() if e.tag in (f'{SVG_NS}animate', f'{SVG_NS}animateTransform')]


def test_the_generator_is_deterministic_for_the_same_item() -> None:
	"""Same input, byte-identical output — the property the committed assets rest on.

	Two calls on one item, and a second `ContentItem` constructed with the same fields: a generator that
	reached for a clock, a random seed or a dict's iteration order would differ on one of these.
	"""
	parent = _parents()['ebola-basics']
	first = render_explainer(parent)
	assert first == render_explainer(parent), 'two renders of one item must be identical'
	twin = parent.model_copy(deep=True)
	assert render_explainer(twin) == first, 'a field-for-field copy must render identically'
	# And the output is not trivially empty or still — the determinism would be meaningless otherwise.
	root = ET.fromstring(first)
	assert _animation_elements(root), 'a still is deterministic for the wrong reason'


@pytest.mark.parametrize('path', COMMITTED, ids=lambda p: p.name)
def test_the_committed_asset_equals_a_fresh_render(path: Path) -> None:
	"""The committed file is the generator's output, byte for byte. Existence would pass on a stale file
	or an empty one; this fails the moment the corpus changes without `python -m afya.info.explainers`
	being re-run."""
	generated = {asset_path(ref): svg for ref, svg in explainer_assets()}
	assert path in generated, f'{path.name} is committed but the generator no longer produces it'
	assert path.read_bytes() == generated[path].encode('utf-8'), (
		f'{path.name} has drifted from the generator — regenerate the explainers'
	)


def test_the_committed_set_is_exactly_what_the_generator_produces() -> None:
	"""No orphan and no missing file: the directory is the generator's output rather than a place files
	also happen to live."""
	assert COMMITTED, 'no explainer is committed, so §CHAN-004 has no asset behind it'
	assert {p.name for p in COMMITTED} == {Path(ref).name for ref, _ in explainer_assets()}


@pytest.mark.parametrize('path', COMMITTED, ids=lambda p: p.name)
def test_the_asset_animates_and_carries_a_timeline(path: Path) -> None:
	"""Real animation, read off the parsed XML.

	A timeline is a `<g>` sequence whose `begin=` offsets walk forward with the scenes *and* a progress
	element keyed to the same cumulative durations. Asserting on `<animate>` alone would pass on a still
	that has one animation attached to nothing that changes, which is the exact defect §CHAN-004's row
	names.
	"""
	root = ET.parse(path).getroot()
	animations = _animation_elements(root)
	assert len(animations) >= 2, f'{path.name} carries {len(animations)} animation elements'
	begins = sorted(
		float(e.get('begin', '0').rstrip('s')) for e in animations if e.get('begin') is not None
	)
	assert len(set(begins)) >= 2, f'{path.name} animates everything at one instant, not in sequence'
	assert max(begins) > 0, f'{path.name} has no offset after the first frame'
	# The timeline: an animated track whose keyTimes are the cumulative scene durations, so the bar
	# reaches each mark when that scene ends.
	tracks = [e for e in animations if e.get('attributeName') == 'width' and e.get('keyTimes')]
	assert tracks, f'{path.name} has no progress timeline keyed to the scenes'
	key_times = [float(k) for k in tracks[0].get('keyTimes', '').split(';')]
	assert key_times[0] == 0.0 and key_times[-1] == 1.0, key_times
	assert key_times == sorted(key_times), 'a timeline that does not advance is not a timeline'


def test_an_animated_item_is_a_rendition_of_a_served_parent(svc: InfoService) -> None:
	"""The item side of the row: an `animation` is a rendition, its parent is published and stamped, and
	`renditions_of` returns it — the same gate every other rendition passes."""
	items = svc.all_items()
	animated = [i for i in items if i.format is ContentFormat.animation]
	assert animated, 'no item carries the animation format, so the row is not closed'
	by_slug = {i.slug: i for i in items if i.lang == 'en' and i.rendition_of is None}
	for rendition in animated:
		assert rendition.rendition_of, f'{rendition.item_id} names no parent'
		assert rendition.media_ref, f'{rendition.item_id} points at no file'
		assert not rendition.format.is_text, 'an animation is a rendition, not prose'
		parent = by_slug[rendition.rendition_of]
		assert parent.stage is ContentStage.published, f'{parent.slug} is not published'
		assert parent.updated_at_ms > UNDATED_MS, f'{parent.slug} carries no timestamp (§6.2.3)'
		assert rendition in svc.renditions_of(parent.slug), (
			f'{rendition.item_id} is not returned by renditions_of({parent.slug!r})'
		)


def test_every_non_text_format_has_a_rendition_behind_it(svc: InfoService) -> None:
	"""Read off the enum, never a hand-written list: `{f for f in ContentFormat if not f.is_text}` is the
	set of formats that need a file, and each must have one — published and stamped, since
	`renditions_of` withholds an unstamped rendition and a format served by nothing is the finding."""
	needs_media = {f.value for f in ContentFormat if not f.is_text}
	assert needs_media, 'every format is text, so nothing is a rendition'
	served = {
		i.format.value for i in svc.all_items()
		if i.media_ref and i.stage is ContentStage.published and i.updated_at_ms > UNDATED_MS
	}
	assert needs_media <= served, f'formats with no servable rendition behind them: {needs_media - served}'


def test_the_caption_language_is_the_parents_not_a_default() -> None:
	"""The Swahili article's explainer is captioned in Swahili.

	`rendition_rows()` stamps every rendition row `en`, so a generator that read the language off the
	rendition — or defaulted to English — would render Swahili prose under English captions and no field
	would show it. The parent carries the language; the generator reads it there.
	"""
	swahili = next(i for i in seed_rows() if i.slug == 'ebola-basics' and i.lang == 'sw')
	svg = render_explainer(swahili)
	root = ET.fromstring(svg)
	assert root.get('lang') == 'sw' and root.get('{http://www.w3.org/XML/1998/namespace}lang') == 'sw'
	# The captions are the parent's own words, not a translation and not English.
	captions = ' '.join(e.text or '' for e in root.iter(f'{SVG_NS}text'))
	assert 'Dalili' in captions or 'Piga' in captions, captions
	english = render_explainer(next(i for i in seed_rows() if i.slug == 'ebola-basics' and i.lang == 'en'))
	assert ET.fromstring(english).get('lang') == 'en'
	assert svg != english, 'the two languages must not render the same bytes'


def test_the_scenes_are_the_parents_own_sentences_and_its_timeline() -> None:
	"""The scene set and the timeline are derived from the parent's copy — no new clinical text.

	`scenes` is the parent's body split on sentence and list boundaries, and the durations are a function
	of each scene's own length, so the timeline is keyed to the prose rather than to a fixed slot.
	"""
	parent = _parents()['prevention']
	plan = scene_plan(parent.body)
	assert len(plan) >= 2, 'a one-scene explainer has no sequence to animate'
	scenes = [scene for scene, _ in plan]
	# Every scene's words come from the body: nothing was authored here. Punctuation is normalised
	# because the split drops the `;` and `.` a scene was cut at.
	body_words = {w.strip(';.,:') for w in parent.body.split()}
	for scene in scenes:
		assert {w.strip(';.,:') for w in scene.split()} <= body_words, (
			f'scene invents words: {scene!r}'
		)
	# The durations are the scenes' own, and the timeline they sum to is the one the SVG carries.
	assert all(duration > 0 for _, duration in plan)
	total_ms = sum(duration for _, duration in plan)
	root = ET.fromstring(render_explainer(parent))
	track = next(e for e in _animation_elements(root) if e.get('attributeName') == 'width')
	bar_dur = float(track.get('dur', '0').rstrip('s')) * 1000
	assert bar_dur == total_ms, f'the bar runs {bar_dur}ms and the scenes sum to {total_ms}ms'
