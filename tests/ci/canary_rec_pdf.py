"""Canaries for tests/ci/test_wallet.py's PDF assertions.

§REC-001's "PDF export" is rendered by `afya.records.pdf`, a hand-written writer with no library
behind it. The writer had a canary for its cross-reference table and none for its text encoding —
and the encoding is where it was wrong, so every export the wallet produced read
`Health record ? Achieng` and a name carrying O’Brien lost its apostrophe.

*A font with no `/Encoding` is not a font that draws Latin-1.* The base-14 fonts are read as
StandardEncoding when the dictionary declares nothing, and StandardEncoding leaves every byte from
0x80 up undefined — so the writer could emit the right bytes and still draw nothing. **#1** removes
the declaration, which is the half a test asserting only the byte values would pass.

*`ord(c) < 256` is a Latin-1 test, and Helvetica draws cp1252.* The two sets differ by exactly the
punctuation this tree writes: em dash, en dash, typographic apostrophe, ellipsis. **#2** restores the
Latin-1 bound, which destroys each of them and replaces it with `?` — the defect the export's own
heading makes unavoidable, since `RecordsService.export` builds that heading with an em dash.

*The weak assertion is the one that was there.* `test_the_pdf_escapes_a_parenthesis_in_a_title`
asserts the character must not reach the stream raw, and the mangling satisfies it — `?` is not
`\\xe2`. **#3** is that shape: it makes the escaper drop a character it cannot draw rather than
substituting, so nothing raw reaches the stream and the name is silently *absent* from the
certificate instead of visibly unrenderable. The new test catches it because it asserts the
character survives, not merely that the raw byte is gone.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line fails this script. The `__pycache__` purge
after each write is load-bearing for the reason `canary_inf001.py` documents: a same-second write
of the same size reuses the previous canary's bytecode and the canary then tests code it never
mutated.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
P = ROOT / 'src/afya/records/pdf.py'

CANARIES = [
	# 1. The encoding declaration is dropped, which is the writer's state before this fix. The bytes
	#    are still cp1252 and the font still draws nothing with them: a reader under StandardEncoding
	#    has no glyph at 0x97, so the em dash vanishes from a heading that has one.
	('the font stops declaring the encoding that gives its bytes glyphs', P,
		"		3: b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',",
		"		3: b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',",
		'test_the_pdf_keeps_the_punctuation_helvetica_can_draw'),

	# 2. The Latin-1 bound is restored. `ord(c) < 256` is true of nothing cp1252 adds, so the em dash
	#    in the export's own heading and the apostrophe in a name both become `?` — and the export
	#    still reports success, which is what made this survive every gate.
	('the escaper falls back to a Latin-1 bound', P,
		"		try:\n			drawable.append(char.encode('cp1252').decode('latin-1'))\n"
		"		except UnicodeEncodeError:\n			drawable.append('?')",
		"		drawable.append(char if ord(char) < 256 else '?')",
		'test_the_pdf_keeps_the_punctuation_helvetica_can_draw'),

	# 3. The undrawable character is dropped rather than replaced. This is the weak assertion's own
	#    defect: nothing raw reaches the stream, so a check for the raw byte passes, and a name in a
	#    script this font cannot draw disappears from the certificate without a mark where it was.
	('an undrawable character is dropped instead of marked', P,
		"		except UnicodeEncodeError:\n			drawable.append('?')",
		"		except UnicodeEncodeError:\n			drawable.append('')",
		'test_the_pdf_marks_a_character_the_font_cannot_draw'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_rec_pdf.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly',
			f'tests/ci/test_wallet.py::{node}'], cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	print(f'{"CAUGHT " if caught else "MISSED "} {name}')
	if not caught:
		failures.append(name)
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
