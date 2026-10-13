"""Emit src/afya/medicine/interactions.py from the parsed WHO Model Formulary appendices.

Run:  python3 -I emit.py <formulary.txt> <outdir>

Three transforms between the source and the table, each stated in the emitted module's docstring
because each is a decision rather than a transcription:

1. The appendix lists each pair twice, once under each drug. The table stores one row per unordered
   pair, and `lookup` keys on the unordered pair.
2. A few pairs carry a different hazard marking under the two listings. The table keeps the *more
   severe* one, so the disagreement always resolves toward the warning. The count is measured here
   and written into the emitted module, not asserted from the plan that commissioned the work — the
   plan said 54 and the extraction says 7, and the emitted number is the one a reader can check
   against the source.
3. The source names generic drugs; callers type brands. ALIASES maps the common names onto the
   source's own.
"""
import json
import pathlib
import subprocess
import sys
from collections import Counter
FORMULARY = pathlib.Path(sys.argv[1])
OUT = pathlib.Path(sys.argv[2])

# Re-run the two parsers against the archived source and read back their JSON.
HERE = pathlib.Path(__file__).parent
subprocess.run([sys.executable, '-I', str(HERE / 'parse_appendix.py'), str(FORMULARY)], check=True,
               capture_output=True)
subprocess.run([sys.executable, '-I', str(HERE / 'parse_rest.py'), str(FORMULARY)], check=True,
               capture_output=True)
app1 = json.load(open(HERE / 'app1.json'))
app2 = json.load(open(HERE / 'app2.json'))

SEVERITY = {'noted': 0, 'hazardous': 1}

# --- 1 & 2: one row per unordered pair, the more severe hazard winning ---------------------------
pairs: dict[tuple[str, str], list] = {}
disagreements = []
for drug, other, hazard, note in app1['rows']:
	if hazard == 'reference':
		continue
	key = tuple(sorted((drug, other), key=str.lower))
	if key not in pairs:
		pairs[key] = [key[0], key[1], hazard, note]
		continue
	prev = pairs[key]
	if SEVERITY[hazard] > SEVERITY[prev[2]]:
		# The more severe marking wins; keep whichever note came with it.
		disagreements.append((key[0], key[1], prev[2], hazard))
		pairs[key] = [key[0], key[1], hazard, note]
	elif prev[2] != hazard:
		disagreements.append((key[0], key[1], hazard, prev[2]))

rows = sorted(pairs.values(), key=lambda r: (r[0].lower(), r[1].lower()))

# How many pairs the appendix actually lists from both sides, measured rather than assumed.
_counts = Counter(tuple(sorted((d, o), key=str.lower)) for d, o, h, _ in app1['rows'] if h != 'reference')
listed_twice = sum(1 for n in _counts.values() if n > 1)

# --- 3: brands and colloquial names -> the source's generic -------------------------------------
# Only names whose mapping is unambiguous. Every entry is a name a person in Kenya would type that
# the appendix spells differently, or a brand whose single active ingredient the appendix lists.
ALIASES = {
	'aspirin': 'Acetylsalicylic acid', 'asa': 'Acetylsalicylic acid',
	'panadol': 'Paracetamol', 'calpol': 'Paracetamol', 'acetaminophen': 'Paracetamol',
	'paracetamol': 'Paracetamol',
	'flagyl': 'Metronidazole', 'brufen': 'Ibuprofen', 'nurofen': 'Ibuprofen',
	'ventolin': 'Salbutamol', 'salbutamol': 'Salbutamol', 'albuterol': 'Salbutamol',
	'lasix': 'Furosemide', 'frusemide': 'Furosemide',
	'coumadin': 'Warfarin', 'augmentin': 'Amoxicillin', 'amoxil': 'Amoxicillin',
	'glucophage': 'Metformin', 'lanoxin': 'Digoxin',
	'coartem': 'Artemether + lumefantrine', 'coartem 20/120': 'Artemether + lumefantrine',
	'act': 'Artemether + lumefantrine', 'al': 'Artemether + lumefantrine',
	'septrin': 'Sulfamethoxazole + trimethoprim', 'co-trimoxazole': 'Sulfamethoxazole + trimethoprim',
	'cotrimoxazole': 'Sulfamethoxazole + trimethoprim',
	'zithromax': 'Azithromycin', 'cipro': 'Ciprofloxacin',
	'vibramycin': 'Doxycycline', 'voltaren': 'Diclofenac',
	'prednisone': 'Prednisolone', 'ventolin inhaler': 'Salbutamol',
	'phenobarbitone': 'Phenobarbital', 'phenytoin sodium': 'Phenytoin',
	'vitamin a': 'Retinol', 'folic acid': 'Folic acid',
}
# Keep only aliases whose target is a name the appendix actually uses, so the map cannot point at
# a drug the table has never heard of.
names = {r[0] for r in rows} | {r[1] for r in rows}
ALIASES = {k: v for k, v in ALIASES.items() if v in names}
dropped_aliases = sorted(set(ALIASES) - {k for k, v in ALIASES.items() if v in names})

HEAD = '''"""Drug interaction reference — §MED-002, from the WHO Model Formulary 2008, Appendix 1.

`check_interactions` used to read a four-row tuple typed into `service.py`, and returned a list of
strings. Four rows is not a database and a string is not a finding: the route could not say *how*
hazardous a pair was in the source's own terms, could not say what it did not know, and had nowhere
to put the contraindication the section's third bullet asks for.

This module is the table. Appendix 1 of the Formulary lists, for each drug, the drugs it interacts
with and what happens; `afya.medicine.service.check_interactions` reads it.

The numbers are reproduced here rather than read at runtime, for the reason
`afya.records.growth_standards` gives: no network egress inside a clinical calculation, and a table
that can silently change under a running service is not a reference. The source PDF is archived at
`sources/who-model-formulary/` with its checksums and page references in `sources/INDEX.md`.

THREE THINGS ABOUT THIS TABLE THAT ARE NOT TRANSCRIPTION.

The appendix lists each pair **twice**, once under each drug, and the two listings are not always
identical. @TWICE@ of the @ROWS@ pairs below appear under both drugs, and **@DISAGREE@ of them carry a
different hazard marking** depending on which drug's section you read — Clomipramine + Warfarin is
marked `noted` under clomipramine and `hazardous` under warfarin. This table keeps the **more
severe** of the two. Where a source disagrees with itself the disagreement is resolved toward the
warning, never away from it, and the count is recorded here rather than left for a reader to
rediscover.

The hazard vocabulary is the appendix's own, and it is **two-valued, not graded**. The appendix
defines it: "the symbol * indicates a potentially hazardous interaction and the combined
administration of the drugs involved should be avoided, or only taken with caution and appropriate
monitoring. Interactions with no symbol do not usually have serious consequences." So a row is
`hazardous` or it is `noted`, and `HAZARD_DEFINITION` carries the source's sentence verbatim
because "noted" is not a reassurance and a client that renders it as one has misread the source.

**A name that matches nothing is not a name with no interactions.** `lookup` returns the names it
could not place, separately, for the reason `DoseResult.unknown` exists: "we do not have this
medicine" and "this medicine is safe with the others" are opposite claims, and the second is the
one a person acts on.
"""
import re

from afya.medicine.views import InteractionPair

# The appendix's two marks, named rather than spelled inline so a caller cannot compare against a
# string literal that a typo would silently turn into a third value.
HAZARDOUS = 'hazardous'
NOTED = 'noted'

# Appendix 1, verbatim.
HAZARD_DEFINITION = (
	'The symbol * indicates a potentially hazardous interaction and the combined administration of '
	'the drugs involved should be avoided, or only taken with caution and appropriate monitoring. '
	'Interactions with no symbol do not usually have serious consequences.'
)

# Pairs listed under both drugs, and the subset whose two listings disagree on the hazard mark.
PAIRS_LISTED_TWICE = @TWICE@
PAIRS_WITH_DISAGREEING_HAZARD = @DISAGREE@

'''

BODY = '''
# (drug_a, drug_b, hazard, note) — Appendix 1, one row per unordered pair.
INTERACTIONS: tuple[tuple[str, str, str, str], ...] = (
'''

TAIL = ''')

# Names a caller may type that the appendix spells differently: brands whose single active
# ingredient it lists, and the common colloquial names. Matched on whole words, for the reason
# `essential_slug` gives — "act" is inside "contact" and a substring match would make every
# medicine an antimalarial.
ALIASES: dict[str, str] = @ALIASES@

# Every name the table knows, lowercased, for the caller-facing list of what can be checked.
KNOWN_NAMES: frozenset[str] = frozenset(
	name.lower() for row in INTERACTIONS for name in row[:2]
) | frozenset(ALIASES)

_BY_PAIR: dict[frozenset[str], tuple[str, str, str, str]] = {
	frozenset((row[0].lower(), row[1].lower())): row for row in INTERACTIONS
}


def canonical(name: str) -> str | None:
	"""The source's own name for a drug a caller named, or `None` if the table does not know it.

	Whole-word matching, so "panadol extra" resolves through "panadol" while "act" does not resolve
	inside "contact". A brand and its generic are the same drug to the appendix, which is the whole
	reason this function exists: a person types what is printed on the box.
	"""
	low = name.strip().lower()
	if not low:
		return None
	if low in ALIASES:
		return ALIASES[low]
	words = set(re.findall(r'[a-z0-9+/-]+', low))
	if not words:
		return None
	for row in INTERACTIONS:
		for candidate in row[:2]:
			cand_words = set(re.findall(r'[a-z0-9+/-]+', candidate.lower()))
			if cand_words and cand_words <= words:
				return candidate
	for alias, target in ALIASES.items():
		alias_words = set(re.findall(r'[a-z0-9+/-]+', alias))
		if alias_words and alias_words <= words:
			return target
	return None


def lookup(drugs: list[str]) -> tuple[list[InteractionPair], list[str]]:
	"""Every interaction among `drugs`, and the names the table could not place.

	Order-independent: the pair is looked up by its unordered key, so `['warfarin', 'aspirin']` and
	`['aspirin', 'warfarin']` are the same question. The second return value is not a warning list
	— it is the set of names the answer does not cover, and a caller that ignores it is reporting
	"no interaction" for a medicine it never checked.
	"""
	assert drugs is not None, 'a drug list is required'
	resolved: list[str] = []
	unmatched: list[str] = []
	for raw in drugs:
		name = canonical(raw)
		if name is None:
			unmatched.append(raw)
		else:
			resolved.append(name)
	seen: set[frozenset[str]] = set()
	found: list[InteractionPair] = []
	for idx, left in enumerate(resolved):
		for right in resolved[idx + 1:]:
			key = frozenset((left.lower(), right.lower()))
			if len(key) < 2 or key in seen:
				continue
			seen.add(key)
			row = _BY_PAIR.get(key)
			if row is not None:
				found.append(InteractionPair(a=row[0], b=row[1], hazard=row[2], note=row[3]))
	found.sort(key=lambda p: (p.hazard != HAZARDOUS, p.a.lower(), p.b.lower()))
	return found, unmatched
'''


def lit(s: str) -> str:
	return "'" + s.replace('\\', '\\\\').replace("'", "\\'") + "'"


head = (HEAD.replace('@ROWS@', str(len(rows)))
        .replace('@DISAGREE@', str(len(disagreements))).replace('@TWICE@', str(listed_twice)))
lines = [head]
lines.append(BODY)
for a, b, hazard, note in rows:
	lines.append(f"\t({lit(a)}, {lit(b)}, {lit(hazard)}, {lit(note)}),\n")
alias_src = '{\n' + ''.join(f"\t{lit(k)}: {lit(v)},\n" for k, v in sorted(ALIASES.items())) + '}'
lines.append(TAIL.replace('@ALIASES@', alias_src))

(OUT / 'interactions.py').write_text(''.join(lines))
print(f'interactions.py: {len(rows)} rows, {len(disagreements)} disagreements, {len(ALIASES)} aliases')
print('dropped aliases (target not in table):', dropped_aliases)
