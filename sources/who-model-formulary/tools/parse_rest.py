"""Extract Appendix 2 (pregnancy), Appendix 3 (breastfeeding) and the per-drug
`Contraindications:` lines from the WHO Model Formulary.

Appendix 2 and 3 are the same shape: a drug name at indent 0, the comment at indent 25 on the same
line or the next, with further comment lines at indent 25. Appendix 4 and 5 use severity headings
rather than per-drug rows and are not extracted here.

The monograph `Contraindications:` extraction is bounded by the *next* field keyword rather than by
a character window. A window-based read is how the first attempt attributed Propranolol's clause to
Paracetamol: Paracetamol has no `Contraindications:` line at all, so a fixed-size window ran past
`Precautions:` and `Dose:` into the next drug.
"""
import json
import pathlib
import re
import sys


SRC = pathlib.Path(sys.argv[1])
lines = SRC.read_text().split('\n')
GAP = re.compile(r'\s{2,}')
FIELD = re.compile(r'^(Contraindications|Precautions|Dose|Uses|Interactions|Adverse effects|'
                   r'Notes?|Administration|Monitoring|Indications|Cautions|Storage|'
                   r'Adverse reactions|Side-effects|Side effects):')


def body(label, stop_labels):
	start = next(i for i, l in enumerate(lines) if l.strip() == label)
	end = next(i for i, l in enumerate(lines)
	           if i > start and any(l.strip() == s for s in stop_labels))
	out, page = [], 0
	for l in lines[start:end]:
		if not l.strip():
			continue
		# Running headers: the folio line (`604    WHO Model Formulary 2008`) and the section
		# title repeated at the top of every page, both of which the pdftotext pass prefixes with
		# a form feed. One of the two appears per page and both must be dropped — a header left in
		# is appended to the comment above it, which is how `Not known to be harmful` acquired an
		# `Appendix 2: Pregnancy` tail. The two tests are separate `or` branches, not
		# `A or B and C`, which Python parses as `A or (B and C)` and which therefore drops only
		# the folio line and keeps every section title.
		if 'WHO Model Formulary 2008' in l or label in l:
			page += 1
			continue
		out.append((page, l))
	return out


# Salt and ester forms the appendices name but the monograph headings do not: the heading is
# `Pentamidine` and the appendix row is `Pentamidine isetionate`. A trailing word from this set
# belongs to the drug's name, not to its comment.
SALTS = {'isetionate', 'isethionate', 'hydrochloride', 'sodium', 'potassium', 'calcium',
         'sulfate', 'sulphate', 'tartrate', 'maleate', 'mesylate', 'besylate', 'acetate',
         'citrate', 'phosphate', 'nitrate', 'chloride', 'iodide', 'bromide', 'fumarate',
         'succinate', 'lactate', 'gluconate', 'valerate', 'dipropionate', 'propionate',
         'benzoate', 'salicylate', 'stearate', 'hydrate', 'dihydrate', 'base', 'salt'}


def monograph_names():
	"""Every drug name the formulary gives a monograph heading, lowercased.

	A monograph heading is an unindented line that is just a name — `Phenoxymethylpenicillin`,
	`Levodopa + carbidopa`. This is the source's own vocabulary, and it is what resolves the two
	Appendix 2 rows that are typeset with a single space between the name and the comment:

		Levodopa + carbidopa Toxicity in animal studies
		Phenoxymethylpenicillin Not known to be harmful

	Neither the 2+-space rule nor the comment column can find that boundary — one of the two names
	is longer than the column the rest of the page uses. What does find it is that "Levodopa +
	carbidopa" is a name this book uses and "Levodopa + carbidopa Toxicity" is not.
	"""
	return {ln.strip().lower() for ln in lines
	        if ln[:1].isupper() and len(ln) - len(ln.lstrip()) == 0
	        and len(ln.strip()) <= 60 and not ln.strip().endswith(('.', ':', ';', ','))
	        and GAP.search(ln.strip()) is None}


MONOGRAPH_NAMES = monograph_names()


def split_tight(s: str, names: set[str]) -> list[str] | None:
	"""Split a tightly-typeset row at the longest leading substring that is a drug name.

	Longest, not first: `Levodopa` and `Levodopa + carbidopa` are both prefixes of the same row and
	only the second is the source's name for the drug. A trailing salt word is taken as part of the
	name — `Pentamidine isetionate` is one drug, and stopping at `Pentamidine` would leave
	`isetionate` at the head of the comment.

	Failing that, a comma-delimited name is split at its last comma: the appendix writes combination
	and vaccine names that way (`Vaccine, Poliomyelitis, live`), and such a name can overflow the
	comment column, leaving a single space where the gap should be.
	"""
	best = None
	for idx in range(len(s)):
		if s[idx] != ' ' or not s[:idx].strip():
			continue
		if s[:idx].strip().lower() in names:
			best = idx
	if best is None:
		m = re.match(r"^([A-Z][A-Za-z0-9 ()+\-/.'’]*(?:,\s*[A-Za-z][A-Za-z0-9\-]*)+),\s+([A-Z].*)$", s)
		if m:
			return [m.group(1).strip(), m.group(2).strip()]
		return None
	words = s[:best].strip().split(' ')
	while True:
		rest = s[best:].lstrip()
		head = rest.split(' ', 1)[0].lower().strip('.,;')
		if head in SALTS and ' ' in rest:
			best = s.index(rest.split(' ', 1)[0], best) + len(rest.split(' ', 1)[0])
			words.append(head)
		else:
			break
	if not s[best:].strip():
		return None
	return [s[:best].strip(), s[best:].strip()]


def two_col(label, stop_labels, col_min=18):
	"""Parse a name/comment table. Returns rows of (name, comment).

	The table proper begins after its `Medicine  Comment` header; everything before it is the
	appendix's prose preamble, which has no column separator and would otherwise be captured as
	a run of nameless rows.
	"""
	raw = body(label, stop_labels)
	hdr = next((i for i, (_, ln) in enumerate(raw)
	            if re.match(r'^Medicine\s{2,}Comment$', ln.strip())), None)
	if hdr is not None:
		raw = raw[hdr + 1:]
	rows, page_col = [], {}
	for page, ln in raw:
		cols = [m.end() for m in GAP.finditer(ln) if m.end() >= col_min]
		if cols:
			page_col.setdefault(page, []).extend(cols)
	if not page_col:
		return rows
	mode = {p: max(set(v), key=v.count) for p, v in page_col.items()}
	# `fresh` is False once a row's name has been continued across a line break, and stays False
	# until a new row starts. A comment line arriving while it is False belongs to the row *below*,
	# not to the row above: a long name pushes its own comment onto the following line, and
	# appending that line to the previous row's comment would file one drug's warning under another.
	# `Sulfamethoxazole + trimethoprim` is the case — its name runs to indent 1 and its comment
	# starts on the next line, which is the first line of the row's comment rather than a
	# continuation of the previous drug's.
	fresh = True
	for page, ln in raw:
		ind = len(ln) - len(ln.lstrip())
		s = ln.strip()
		if s in ('Medicine', 'Comment', 'Medicines present in breast milk'):
			continue
		col = mode.get(page, 25)
		if ind == 0:
			m = GAP.search(s)
			if m and m.end() >= col - 5:
				rows.append([s[:m.start()].strip(), s[m.end():].strip()])
			else:
				rows.append(split_tight(s, MONOGRAPH_NAMES) or [s, ''])
			fresh = True
		elif ind == 1 and rows:
			# A wrapped *name*, not a comment. The two columns are typeset one space apart at the
			# margin (`Amoxicillin + clavulanic` / ` acid`, `Sulfadoxine +` / ` pyrimethamine`), and
			# a comment continuation never sits at indent 1 — it sits at the comment column. Both
			# appendices separate cleanly on this: indent 0 is a row, indent 1 is a name, and every
			# indent of 3 or more is a comment or the appendix's own bulleted preamble.
			#
			# The continuation line carries its own column gap where the name is short enough to
			# reach it (` pyrimethamine         outweigh risk`), and where it does, the text after
			# the gap is the rest of the comment rather than more name.
			m = GAP.search(s)
			if m and m.end() >= col - 5:
				rows[-1][0] += ' ' + s[:m.start()].strip()
				rows[-1][1] += ' ' + s[m.end():].strip()
			else:
				# A comma-delimited name continues across the line break and may be followed by
				# the start of the comment on the same line (`Vaccine, Poliomyelitis,` / ` live
				# malformations, but need for vaccination may`). Split at the last comma when one
				# is present; otherwise the whole line is more name.
				tail = split_tight(s, set())
				if tail:
					rows[-1][0] += ' ' + tail[0]
					rows[-1][1] += ' ' + tail[1]
				else:
					rows[-1][0] += ' ' + s
			fresh = False
		elif rows:
			if fresh:
				rows[-1][1] += ' ' + s
			else:
				rows[-1][1] += (' ' if rows[-1][1] else '') + s
				fresh = True
	return rows


def monographs():
	"""Per-drug `Contraindications:` text, bounded by the next field keyword."""
	out = {}
	for i, ln in enumerate(lines):
		if not ln.startswith('Contraindications:'):
			continue
		# The drug name is the nearest preceding line that is a bare heading.
		name = None
		for j in range(i - 1, max(0, i - 90), -1):
			if re.match(r'^[A-Z][A-Za-z0-9 ,()+\-/.\'’]{2,60}$', lines[j]):
				name = lines[j].strip()
				break
		if name is None:
			continue
		chunks = [ln[len('Contraindications:'):].strip()]
		for k in range(i + 1, min(len(lines), i + 40)):
			nxt = lines[k]
			if not nxt.strip():
				continue
			if FIELD.match(nxt.strip()):
				break
			if 'WHO Model Formulary 2008' in nxt or 'Appendix' in nxt:
				break
			chunks.append(nxt.strip())
		text = re.sub(r'\s+', ' ', ' '.join(chunks)).strip()
		if name not in out or len(text) > len(out[name]):
			out[name] = text
	return out


preg = two_col('Appendix 2: Pregnancy', ['Appendix 3: Breastfeeding'])
bf = two_col('Appendix 3: Breastfeeding', ['Appendix 4: Renal impairment'])
# The two appendices spell a few salt forms differently from each other (`Pentamidine isetionate`
# is tight in Appendix 2 and clean in Appendix 3), so the second pass re-splits Appendix 2's rows
# against the names Appendix 3 spelled out. A name the *other* table knows is still the source's
# own vocabulary; this is not a guess about where the column is.
APPENDIX_NAMES = MONOGRAPH_NAMES | {n.lower() for n, _ in bf if n}
preg = [[split_tight(' '.join(r), APPENDIX_NAMES) or r][0] if not r[1] else r for r in preg]
contra = monographs()

print('pregnancy rows', len(preg), 'breastfeeding rows', len(bf), 'monograph contraindications', len(contra))
print('--- pregnancy sample ---')
for r in preg[:4] + preg[-2:]:
	print(' ', r)
print('--- bf sample ---')
for r in bf[:3] + bf[-2:]:
	print(' ', r)
print('--- paracetamol present? ---', 'Paracetamol' in contra)
print('--- contraindication samples ---')
for k in ['Paracetamol', 'Metformin', 'Warfarin', 'Doxycycline', 'Metronidazole', 'Propranolol']:
	print(' ', k, '=>', contra.get(k, '<absent>')[:150])
json.dump({'pregnancy': preg, 'breastfeeding': bf, 'contraindications': contra},
          open(pathlib.Path(__file__).parent / 'app2.json', 'w'), indent=1)
