"""§CHAN-004's animated explainers, generated from a parent item's own sentences.

**This module authors no clinical copy, and that is the whole reason the audit row closes.** §CHAN-004's
Content types ask for "Animated explainers on symptoms and prevention". The temptation is to write an
explainer script, and it is the wrong move twice over: a generator that writes its own sentences is a
second, unreviewed author of clinical content that §6.5's workflow (English draft → clinical review →
translation → back-translation → community validation) has never seen, and a corpus with two copies of
the same advice is two copies that drift. So every caption here is a slice of the *parent* `ContentItem`'s
own `body` — split into scenes, wrapped, and given motion — and nothing else. The parent has already been
through §6.5; the animation is a delivery format for text that exists.

**If this generator ever writes its own copy, the §CHAN-004 row belongs back in `missing`.** A generated
explainer whose captions are not the parent's sentences is not a rendition of reviewed content, it is new
content wearing an animation, and the audit's own note on that row ("§INF-003's `illustration` format is a
still SVG, which is a different medium") would be describing the wrong defect.

**Language comes from the parent, never from a default.** `content_seed.rendition_rows()` stamps every
rendition row `lang='en'`, which is the trap: reading the caption language off the rendition would render
the Swahili article's explainer with English captions. `render_explainer` reads `item.lang` off the parent
it is handed, and `explainer_assets()` asserts the rendition row and its parent agree before generating.

**Determinism.** The same item produces byte-identical output: no clock, no random source, no dependence
on dict iteration order (assets are sorted by path, and every value is computed from the parent's own
fields with integer arithmetic). That is what lets the committed files under `media/explainers/` be
compared to the generator by byte equality in `tests/ci/test_explainers.py` rather than by existence —
a drift between the corpus and the asset it ships then fails a test instead of reaching a reader.

The output is SVG with SMIL animation: each scene is a `<g>` that fades in at a `begin=` offset equal to
the cumulative duration of the scenes before it, and a progress bar whose `keyTimes` are those same
cumulative durations. It is a sequence that changes over time rather than a still with an `<animate>`
element in it — the distinction the audit row is actually about.
"""
import re
import sys
from pathlib import Path

from afya.info.views import ContentFormat, ContentItem

# The repository root, three levels up from this file (`src/afya/info/explainers.py`). `media_ref` is
# stored relative to it, so the generator and the committed asset agree on the path without a second
# convention.
REPO_ROOT = Path(__file__).resolve().parents[3]

# Where the generated explainers live. `media/` is not gitignored (checked with `git check-ignore`), and
# it is the same directory the corpus's `media_ref` values already name, so the assets are served the way
# every other rendition is rather than through a path only this module knows.
EXPLAINER_DIR = REPO_ROOT / 'media' / 'explainers'

WIDTH = 720
HEIGHT = 405

# A scene's screen time is a function of its own length, so the timeline is keyed to the parent's copy
# rather than to a fixed slot: a 40-character sentence and a 200-character one do not get the same beat.
# Clamped at both ends so a one-word sentence is still readable and a long one does not stall the piece.
MS_PER_CHAR = 55
MIN_SCENE_MS = 3000
MAX_SCENE_MS = 6000

# Fade and slide durations, in milliseconds. Short relative to the shortest scene, so a scene is on
# screen for most of its own window.
FADE_MS = 400
SLIDE_MS = 500

# Caption wrapping. Deterministic greedy wrap at a fixed character count — a font metrics measurement
# would make the output depend on the renderer, which is the one thing this module may not do.
CAPTION_CHARS = 42
CAPTION_LINE_PX = 40
CAPTION_TOP_Y = 150
CAPTION_X = 84
ICON_CX = 52
ICON_CY = 140
ICON_R = 8

TITLE_Y = 56
BAR_X = 40
BAR_Y = 368
BAR_W = 640
BAR_H = 8

# Sentence terminators, semicolons and newlines all end a scene. A semicolon is not a sentence boundary
# in prose, but it *is* a beat in a list of instructions — "Wash hands with soap frequently; avoid
# bushmeat; avoid contact with body fluids; use safe burial practices." is four things a reader does, and
# rendering it as one caption is a scene nobody can follow. The split adds no word either way: every
# scene is still a slice of the parent's own body.
_SCENE_SPLIT = re.compile(r'(?<=[.!?])\s+|\s*;\s*|\n+')

_COLOURS = {
	'background': '#0b1220',
	'band': '#111c33',
	'title': '#f8fafc',
	'caption': '#e2e8f0',
	'counter': '#94a3b8',
	'icon': '#38bdf8',
	'track': '#1f2937',
	'fill': '#38bdf8',
}


def sentences(body: str) -> list[str]:
	"""The parent's own body, split into scenes. Never empty for a body with any text in it.

	An empty body is a rendition with nothing to animate — `rendition_rows()` builds one with an empty
	body by construction — so a caller must pass the *parent*, and `render_explainer` asserts there is
	at least one scene rather than emitting a still.
	"""
	parts = [p.strip() for p in _SCENE_SPLIT.split(body)]
	return [p for p in parts if p]


def scene_duration_ms(scene: str) -> int:
	"""How long a scene stays on screen, from its own length. Deterministic and clamped."""
	return max(MIN_SCENE_MS, min(MAX_SCENE_MS, len(scene) * MS_PER_CHAR))


def scene_plan(body: str) -> list[tuple[str, int]]:
	"""The parent's body as `(scene, duration_ms)` pairs — the scene set and the timeline in one place.

	The public seam over `sentences` and `scene_duration_ms`, so a caller (and the test) reads the plan
	the renderer uses rather than re-deriving it and drifting from the output.
	"""
	return [(scene, scene_duration_ms(scene)) for scene in sentences(body)]


def _wrap(text: str, width: int = CAPTION_CHARS) -> list[str]:
	"""Greedy word wrap at a fixed character count. No text is dropped: a word longer than `width` gets
	its own line rather than being cut."""
	lines: list[str] = []
	current = ''
	for word in text.split():
		if not current:
			current = word
		elif len(current) + 1 + len(word) <= width:
			current = f'{current} {word}'
		else:
			lines.append(current)
			current = word
	if current:
		lines.append(current)
	return lines or ['']


def _esc(text: str) -> str:
	"""XML-escape for text content and attribute values. Deterministic and total."""
	return (
		text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
		.replace('"', '&quot;')
	)


def _secs(ms: int) -> str:
	"""A duration as SMIL's clock syntax, at a fixed precision so the bytes do not depend on the value."""
	return f'{ms / 1000:.1f}s'


def _width_px(fraction: float) -> str:
	return f'{fraction * BAR_W:.1f}'


def _keytime(fraction: float) -> str:
	return f'{fraction:.4f}'


def render_explainer(item: ContentItem, scenes: list[str] | None = None) -> str:
	"""The animated explainer for `item`, as SVG text.

	`item` is the *parent*: the published text item whose sentences become the captions and whose `lang`
	becomes the caption language. `scenes` overrides the split for a caller that has already made one,
	and exists so a test can pin the scene set; it is never a way to introduce copy the parent does not
	carry, because the default path is the parent's own body.
	"""
	assert item.item_id and item.title, 'an explainer needs the parent item it is a rendition of'
	scene_texts = list(scenes) if scenes is not None else sentences(item.body)
	assert scene_texts, (
		f'{item.item_id}: a body with no scene is a still, and a still is not an animated explainer'
	)
	assert item.lang, f'{item.item_id}: the caption language is the parent\'s, never a default'
	lang = item.lang

	durations = [scene_duration_ms(s) for s in scene_texts]
	total_ms = sum(durations)
	assert total_ms > 0, 'a timeline of zero length is not a timeline'

	parts: list[str] = [
		f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
		f'width="{WIDTH}" height="{HEIGHT}" lang="{_esc(lang)}" xml:lang="{_esc(lang)}" '
		f'role="img" font-family="system-ui, sans-serif">',
		f'<title>{_esc(item.title)}</title>',
		f'<rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" fill="{_COLOURS["background"]}"/>',
		f'<rect x="0" y="0" width="{WIDTH}" height="88" fill="{_COLOURS["band"]}"/>',
		f'<text x="{BAR_X}" y="{TITLE_Y}" font-size="30" font-weight="600" '
		f'fill="{_COLOURS["title"]}">{_esc(item.title)}</text>',
	]

	# Each scene: a group that fades and slides in at its own offset, holds, and (except for the last)
	# fades out when the next begins. `begin` is the cumulative duration of the scenes before it, which is
	# what makes this a sequence rather than a stack of independent effects.
	offset_ms = 0
	count = len(scene_texts)
	for index, (scene, duration_ms) in enumerate(zip(scene_texts, durations)):
		start = _secs(offset_ms)
		end_ms = offset_ms + duration_ms
		animations = [
			f'<animate attributeName="opacity" begin="{start}" dur="{_secs(FADE_MS)}" '
			f'values="0;1" fill="freeze"/>',
			f'<animateTransform attributeName="transform" type="translate" begin="{start}" '
			f'dur="{_secs(SLIDE_MS)}" values="0,16;0,0" fill="freeze"/>',
		]
		if index < count - 1:
			animations.append(
				f'<animate attributeName="opacity" begin="{_secs(end_ms)}" dur="{_secs(FADE_MS)}" '
				f'values="1;0" fill="freeze"/>'
			)
		lines = _wrap(scene)
		captions = ''.join(
			f'<text x="{CAPTION_X}" y="{CAPTION_TOP_Y + i * CAPTION_LINE_PX}" font-size="28" '
			f'fill="{_COLOURS["caption"]}">{_esc(line)}</text>'
			for i, line in enumerate(lines)
		)
		parts.append(
			f'<g opacity="0">{"".join(animations)}'
			f'<circle cx="{ICON_CX}" cy="{ICON_CY}" r="{ICON_R}" fill="{_COLOURS["icon"]}">'
			f'<animate attributeName="r" begin="{start}" dur="{_secs(duration_ms)}" '
			f'values="{ICON_R};{ICON_R + 5};{ICON_R}" repeatCount="indefinite"/>'
			f'</circle>'
			f'{captions}'
			f'<text x="{WIDTH - BAR_X}" y="{HEIGHT - 9}" text-anchor="end" font-size="16" '
			f'fill="{_COLOURS["counter"]}">{index + 1}/{count}</text>'
			f'</g>'
		)
		offset_ms = end_ms

	# The timeline: the progress bar's `keyTimes` are the cumulative scene durations and its `values` the
	# matching fractions of the track, so the bar reaches each mark exactly when that scene ends. It is a
	# second, independent statement of the same timeline the `begin=` offsets carry, which is why a
	# still-with-an-`<animate>` cannot satisfy this module's contract.
	cumulative = 0
	key_times = ['0.0000']
	values = ['0.0']
	for duration_ms in durations:
		cumulative += duration_ms
		key_times.append(_keytime(cumulative / total_ms))
		values.append(_width_px(cumulative / total_ms))
	parts.append(
		f'<rect x="{BAR_X}" y="{BAR_Y}" width="{BAR_W}" height="{BAR_H}" rx="4" '
		f'fill="{_COLOURS["track"]}"/>'
	)
	parts.append(
		f'<rect x="{BAR_X}" y="{BAR_Y}" width="0" height="{BAR_H}" rx="4" fill="{_COLOURS["fill"]}">'
		f'<animate attributeName="width" begin="0.0s" dur="{_secs(total_ms)}" '
		f'values="{";".join(values)}" keyTimes="{";".join(key_times)}" calcMode="linear" '
		f'fill="freeze"/>'
		f'</rect>'
	)
	parts.append('</svg>')
	svg = '\n'.join(parts) + '\n'
	assert svg.count('<animate') >= 2 * count, 'every scene animates or it is not a scene'
	return svg


def asset_path(media_ref: str) -> Path:
	"""Where a `media_ref` lives on disk. The corpus stores it relative to the repository root."""
	return REPO_ROOT / media_ref


def explainer_assets() -> list[tuple[str, str]]:
	"""Every animation rendition in the seed, as `(media_ref, svg)`, sorted by path.

	Read off `rendition_rows()` rather than from a list here, so adding an explainer to the corpus adds
	an asset rather than a generator nobody calls. The parent is resolved by `(slug, lang)` because a slug
	is shared between an item's translations — resolving by slug alone would hand the Swahili rendition the
	English parent's captions, which is exactly the language trap this module exists to avoid.
	"""
	from afya.info.content_seed import rendition_rows, seed_rows

	parents = {(i.slug, i.lang): i for i in seed_rows() if i.slug}
	out: list[tuple[str, str]] = []
	for row in rendition_rows():
		if row.format is not ContentFormat.animation:
			continue
		assert row.rendition_of is not None, f'{row.item_id}: an animation names no parent to caption from'
		parent = parents.get((row.rendition_of, row.lang))
		assert parent is not None, (
			f'{row.item_id}: no {row.lang} parent with slug {row.rendition_of!r} to caption from'
		)
		assert parent.lang == row.lang, 'the caption language is the parent\'s, not the row\'s'
		out.append((row.media_ref or '', render_explainer(parent)))
	assert out, 'the corpus carries an animation format and nothing produces its asset'
	return sorted(out, key=lambda pair: pair[0])


def write_explainers() -> list[Path]:
	"""Write every generated explainer under `media/explainers/`. Returns the paths written.

	The CLI's body, and the only place the assets are produced: the committed files are a cache of this
	function's output, which `tests/ci/test_explainers.py` compares byte for byte.
	"""
	EXPLAINER_DIR.mkdir(parents=True, exist_ok=True)
	written: list[Path] = []
	for media_ref, svg in explainer_assets():
		assert media_ref.startswith('media/explainers/'), (
			f'{media_ref} is not under media/explainers/, and this command only owns that directory'
		)
		path = asset_path(media_ref)
		path.write_text(svg, encoding='utf-8', newline='\n')
		written.append(path)
	assert written, 'nothing was written'
	return written


def main() -> int:
	"""Write the committed explainers. `uv run python -m afya.info.explainers`."""
	for path in write_explainers():
		print(f'wrote {path.relative_to(REPO_ROOT)}')
	return 0


if __name__ == '__main__':
	sys.exit(main())
