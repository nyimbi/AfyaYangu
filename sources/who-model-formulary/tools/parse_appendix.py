"""Extract the WHO Model Formulary appendices from the pdftotext -layout copy.

Appendix 1 (interactions) is a two-column table whose left column is a drug name and whose right
column is the note. Two facts about the extraction drive the whole parser:

* The note column starts at column ~28 and a wrapped note continues at indent 30-36, while a row's
  name starts at indent 5-6 and a wrapped *name* (combination drugs: "Sulfadoxine +" /
  "pyrimethamine") continues at indent 7. So indent alone separates the cases: >=20 is a note
  continuation, <=14 is a row or a name continuation.
* The indent and the column both shift by a column or two across a page break, so neither may be
  treated as a constant. The note column is computed per drug block as the modal gap position.

A star at the start of a row is the source's own hazard marker. The appendix defines it: "the
symbol * indicates a potentially hazardous interaction and the combined administration of the drugs
involved should be avoided, or only taken with caution and appropriate monitoring."
"""
import json
import pathlib
import re
import sys
from collections import Counter

SRC = pathlib.Path(sys.argv[1])
lines = SRC.read_text().split('\n')

GAP = re.compile(r'\s{2,}')
# A drug heading is a line that is just a name. `p-Aminosalicylic acid` is one of them and begins
# with a lowercase chemical locant, so the leading capital cannot be required — but the locant can,
# which is what keeps a wrapped name continuation (" hydroxide; Magnesium hydroxide)") out.
HEADING = re.compile(r'^ (?P<drug>(?:[a-z]-)?[A-Z][A-Za-z0-9 ,()+\-/.\'’;:&]{2,70})$')


def appendix_body(first_line, last_line):
	"""The appendix's lines, each tagged with a page number.

	The page number is not decoration: the two columns of the table are typeset slightly
	differently on each page, so the note column moves by a character or two across a page break
	and a single modal column for a whole drug block lands between the two and matches neither.
	"""
	start = next(i for i, l in enumerate(lines) if l.startswith(first_line)) + 1
	end = next(i for i, l in enumerate(lines) if l.strip() == last_line and i > start)
	out, page = [], 0
	for l in lines[start:end]:
		if not l.strip():
			continue
		if 'WHO Model Formulary 2008' in l or 'Appendix 1: Interactions' in l:
			page += 1
			continue
		out.append((page, l))
	return out


def split_rows(block_lines):
	"""One drug heading's (page, line) pairs into (rows, notes, anomalies)."""
	# The note column is modal *within a page*, not within the block: a block that straddles a page
	# break has two columns, and a single mode lands between them and matches neither.
	cols: dict[int, int] = {}
	for page in {p for p, _ in block_lines}:
		cands = [m.end() for p, ln in block_lines if p == page
		         for m in GAP.finditer(ln) if m.end() >= 18]
		cols[page] = max(set(cands), key=cands.count) if cands else 28
	rows, notes, anom = [], [], []
	# What the previous non-empty line was, because a line at row indent with no column separator
	# is ambiguous on its own: it is a wrapped note when the line above it was a `NOTE.` line, and
	# a wrapped drug *name* when the line above it was a row. "hydroxide; Magnesium" continues
	# "Antacids (Aluminium"; "they may impair absorption." continues a NOTE.
	last = ''
	for page, ln in block_lines:
		note_col = cols[page]
		ind = len(ln) - len(ln.lstrip())
		s = ln.strip()
		if s.startswith('NOTE.'):
			notes.append(s)
			last = 'note'
			continue
		if ind <= 14 and s.startswith('see '):
			rows.append([drug, s[4:].strip(), 'reference', ''])
			last = 'row'
			continue
		if ind >= 20:
			if rows and rows[-1][3]:
				rows[-1][3] += ' ' + s
			elif rows:
				rows[-1][3] = s
			else:
				anom.append(('LEAD', drug, s[:70]))
			last = 'row'
			continue
		star = s.startswith('*')
		rest = s[1:] if star else s
		off = ind + (1 if star else 0)
		seps = [m.end() for m in GAP.finditer(rest)]
		cut = next((p for p in seps if off + p >= note_col - 5), None)
		if cut is None:
			# No column separator: a wrapped name or a wrapped note, decided by what came before.
			if last == 'note' and notes:
				notes[-1] += ' ' + s
			elif rows:
				rows[-1][1] += ' ' + rest.strip()
			else:
				anom.append(('ORPHAN', drug, ln[:70]))
			continue
		a, note = rest[:cut].strip(), rest[cut:].strip()
		# A wrapped combination-drug name sits at row indent and *does* have a column separator,
		# so it is only distinguishable from a new row by what the row above it looks like. Three
		# signals, any one of which is decisive: the name above ended mid-name ("Sulfadoxine +"),
		# it has an unclosed parenthesis ("Antacids (Aluminium"), or this name begins with a
		# lowercase letter or a bracket ("hydroxide; Magnesium hydroxide)", "(human), Anti-D").
		# No drug in the appendix is named with a leading lowercase letter or bracket, so the last
		# signal cannot swallow a real row — with one exception, `p-Aminosalicylic acid`, whose
		# chemical locant prefix makes it start lowercase. A leading `x-` followed by a capital is
		# a locant and the line is a real row, not a continuation of the one above it.
		prev = rows[-1][1] if rows else ''
		if rows and not re.match(r'^[a-z]-[A-Z]', a) and (
		           prev.endswith(('+', ',', ' and', ' or'))
		           or prev.count('(') > prev.count(')')
		           or a[:1].islower() or a.startswith('(')):
			rows[-1][1] += ' ' + a
			rows[-1][3] += ' ' + note
			last = 'row'
			continue
		if a and note:
			rows.append([drug, a, 'hazardous' if star else 'noted', note])
			last = 'row'
		else:
			anom.append(('EMPTY', drug, ln[:70]))
	return rows, notes, anom


body = appendix_body('In the following table the symbol', 'Appendix 2: Pregnancy')
blocks, cur, drug = [], None, ''
for page, ln in body:
	h = HEADING.match(ln)
	if h:
		drug = h.group('drug').strip()
		cur = {'drug': drug, 'lines': []}
		blocks.append(cur)
	elif cur is not None:
		cur['lines'].append((page, ln))

allrows, allnotes, anoms = [], [], []
for blk in blocks:
	drug = blk['drug']
	r, n, a = split_rows(blk['lines'])
	allrows += r
	allnotes += n
	anoms += a

print(f'blocks {len(blocks)}  rows {len(allrows)}  notes {len(allnotes)}  anomalies {len(anoms)}')
print(Counter(a[0] for a in anoms))
for a in anoms[:15]:
	print(' ', a)
trunc = [r for r in allrows if r[3].endswith((' and', ' of', ' the', ' in', ' with', ' a', ' to', ' or', ' risk', ' by'))]
print('truncated-looking notes:', len(trunc))
for r in trunc[:6]:
	print(' ', r)
print('sample:')
for r in allrows[:3] + allrows[-3:]:
	print(' ', r)
json.dump({'rows': allrows, 'notes': allnotes, 'drugs': [b['drug'] for b in blocks]},
          open(pathlib.Path(__file__).parent / 'app1.json', 'w'), indent=1)
