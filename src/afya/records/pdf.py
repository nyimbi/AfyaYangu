"""A minimal PDF writer, for §REC-001's "PDF export" and §10.1's "Export to PDF".

No PDF library is among this deployment's dependencies, and the honest options were to add one or to
write the format. The format is small enough to write: a PDF is a header, a handful of numbered
objects, a cross-reference table giving each object's byte offset, and a trailer pointing at the
table. Text is drawn with one of the fourteen fonts every reader already has, so nothing is
embedded and no font file is needed.

What this deliberately does not do: images, fonts other than Helvetica, compression, encryption, or
tagged-PDF accessibility. A wallet export is a list of documents for a school or a clinic, and the
failure mode of a half-implemented layout engine is worse than the failure mode of plain text.

The font is declared `/WinAnsiEncoding`, and that declaration is load-bearing rather than decoration:
a base-14 font with no `/Encoding` is read as StandardEncoding, under which every byte from 0x80 up
is undefined — so the punctuation this tree actually writes (the em dash in the export's own heading,
a typographic apostrophe in a name) draws as nothing or as garbage. cp1252 is the set that mapping
gives glyphs to, and it is wider than Latin-1 by exactly the characters that matter here.

Two things here are load-bearing and easy to get wrong, which is why they have tests rather than
comments alone: the cross-reference offsets must be the *byte* offsets of each object in the file
that was actually written, and the text must be escaped. A `(` in a document title — "(review)" in a
clinic note — terminates a PDF string literal early and produces a file that opens to garbage.
"""
from typing import Iterable

# The page geometry, in points (72 per inch). A4.
PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN = 56
LEADING = 16.0
FONT_SIZE = 11.0
TITLE_SIZE = 16.0
MAX_LINES_PER_PAGE = int((PAGE_HEIGHT - 2 * MARGIN - 40) / LEADING)
"""Lines that fit between the margins, with room for the header. Fixed rather than measured: the
font is a known width, and a paginator that measured would be a text-layout engine."""

CHARS_PER_LINE = 92
"""Wrap width at 11pt Helvetica in a 483pt text column. Approximate — Helvetica is not monospaced —
so a long line may run slightly past the margin, which is legible; a line clipped at the page edge
is not, which is why the wrap is conservative rather than exact."""


def escape(text: str) -> str:
	"""Escape a PDF string literal and map it into the font's encoding.

	Backslash first: escaping it after the parentheses would double-escape the backslashes this
	function itself introduces, so `\\(` would become `\\\\` and the literal would close early.

	The encoding half is not cosmetic. The font is `/WinAnsiEncoding`, so a character is drawable
	when cp1252 has a glyph for it — which is a *different* set from Latin-1, and wider by exactly
	the punctuation this tree writes. An em dash (U+2014), an en dash, a typographic apostrophe and
	an ellipsis are all cp1252 and none Latin-1, so a `ord(c) < 256` test destroyed every one of
	them and the export's own heading rendered `Health record ? Achieng`. What cp1252 cannot draw
	becomes `?` rather than being dropped: a name in a script this font has no glyph for should be
	visibly unrenderable, not silently absent from a certificate.
	"""
	out = text.replace('\\', r'\\').replace('(', r'\(').replace(')', r'\)')
	out = out.replace('\r', ' ').replace('\n', ' ')
	drawable: list[str] = []
	for char in out:
		try:
			drawable.append(char.encode('cp1252').decode('latin-1'))
		except UnicodeEncodeError:
			drawable.append('?')
	return ''.join(drawable)


def wrap(text: str, width: int = CHARS_PER_LINE) -> list[str]:
	"""Break text into lines at word boundaries, hard-splitting a word longer than the width.

	The hard split is the part that matters: a URL or an unbroken reference longer than the column
	has no space to break at, and a wrapper that only breaks on spaces returns it whole and lets it
	run off the page.
	"""
	lines: list[str] = []
	for paragraph in text.split('\n'):
		if not paragraph.strip():
			lines.append('')
			continue
		current = ''
		for word in paragraph.split(' '):
			while len(word) > width:
				if current:
					lines.append(current)
					current = ''
				lines.append(word[:width])
				word = word[width:]
			candidate = f'{current} {word}'.strip()
			if len(candidate) <= width:
				current = candidate
			else:
				lines.append(current)
				current = word
		if current:
			lines.append(current)
	return lines


def _content_stream(lines: Iterable[tuple[str, float]]) -> str:
	"""The page's content stream: each (text, size) drawn at the next baseline down the page."""
	parts: list[str] = ['BT']
	y = PAGE_HEIGHT - MARGIN
	first = True
	for text, size in lines:
		if first:
			parts.append(f'/F1 {size} Tf')
			first = False
		else:
			parts.append(f'/F1 {size} Tf')
		parts.append(f'1 0 0 1 {MARGIN} {y:.2f} Tm')
		parts.append(f'({escape(text)}) Tj')
		y -= LEADING
	parts.append('ET')
	return '\n'.join(parts)


def render(title: str, lines: list[str]) -> bytes:
	"""A PDF containing `title` as a heading and `lines` as body text, paginated.

	Returns bytes, not a string: a PDF is binary, and a caller that encoded it as text would corrupt
	it on the first non-ASCII byte.
	"""
	assert title, 'a document needs a title'
	pages: list[list[tuple[str, float]]] = []
	current: list[tuple[str, float]] = []
	for line in [title, ''] + lines:
		if len(current) >= MAX_LINES_PER_PAGE:
			pages.append(current)
			current = []
		current.append((line, TITLE_SIZE if not pages and not current else FONT_SIZE))
	if current:
		pages.append(current)
	assert pages, 'a PDF with no pages is not a document'

	# Object numbering: 1 catalog, 2 pages, 3 font, then 2 objects per page (page + contents).
	page_ids = [4 + 2 * i for i in range(len(pages))]
	objects: dict[int, bytes] = {
		1: b'<< /Type /Catalog /Pages 2 0 R >>',
		2: ('<< /Type /Pages /Kids [' + ' '.join(f'{i} 0 R' for i in page_ids) +
		    f'] /Count {len(pages)} >>').encode(),
		3: b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
	}
	for idx, lines_on_page in enumerate(pages):
		page_id = page_ids[idx]
		content_id = page_id + 1
		stream = _content_stream(lines_on_page)
		objects[page_id] = (
			f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] '
			f'/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>'
		).encode()
		body = stream.encode('latin-1')
		objects[content_id] = (
			f'<< /Length {len(body)} >>\nstream\n'.encode() + body + b'\nendstream'
		)

	# The cross-reference table is why this function assembles the file by hand: every entry is the
	# byte offset of an object in the bytes actually written, so the file must be built in one pass
	# with the offsets recorded as it goes.
	out = bytearray(b'%PDF-1.4\n')
	offsets: dict[int, int] = {}
	for obj_id in sorted(objects):
		offsets[obj_id] = len(out)
		out += f'{obj_id} 0 obj\n'.encode() + objects[obj_id] + b'\nendobj\n'
	xref_at = len(out)
	highest = max(objects) + 1
	out += f'xref\n0 {highest}\n'.encode()
	out += b'0000000000 65535 f \n'
	for obj_id in range(1, highest):
		offset = offsets.get(obj_id, 0)
		out += f'{offset:010d} 00000 n \n'.encode()
	out += (
		f'trailer\n<< /Size {highest} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n'
	).encode()
	return bytes(out)
