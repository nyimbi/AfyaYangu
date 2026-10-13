"""Emit src/afya/medicine/contraindications.py from the parsed WHO Model Formulary appendices.

Run:  python3 -I emit_contra.py <formulary.txt> <outdir>

The age and condition axes are parsed out of each monograph's `Contraindications:` line and frozen
as literal tables, so the runtime does no regular expression over clinical prose. The parse is here
and the result is committed: a regex that runs on every request is a regex nobody can review, and a
pattern that silently stops matching is a contraindication that silently stops firing.
"""
import json
import pathlib
import re
import subprocess
import sys


def lit(v: str) -> str:
	return "'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'"

FORMULARY = pathlib.Path(sys.argv[1])
OUT = pathlib.Path(sys.argv[2])
HERE = pathlib.Path(__file__).parent

subprocess.run([sys.executable, '-I', str(HERE / 'parse_rest.py'), str(FORMULARY)], check=True,
               capture_output=True)
app2 = json.load(open(HERE / 'app2.json'))

# --- age thresholds -----------------------------------------------------------------------------
# The source states an age as a floor in months or years, or as the bare word "children" /
# "neonates" with no number. A bare word is kept as its own row with a floor of None rather than
# being converted to a number the source did not state.
AGE_PATTERNS = [
	(re.compile(r'children? (?:and adolescents )?under (\d+) years?', re.I), lambda m: int(m.group(1)) * 12),
	(re.compile(r'child under (\d+) years?', re.I), lambda m: int(m.group(1)) * 12),
	(re.compile(r'infants? less than (\d+) months?', re.I), lambda m: int(m.group(1))),
	(re.compile(r'infants? under (\d+) months? of age', re.I), lambda m: int(m.group(1))),
	(re.compile(r'under (\d+) years', re.I), lambda m: int(m.group(1)) * 12),
]
NEONATE = re.compile(r'\bneonates?\b', re.I)
CHILDREN = re.compile(r'\bchildren\b', re.I)

age_limits = []
for drug, text in app2['contraindications'].items():
	# A monograph name that ends in a full stop or begins with a lowercase word is a prose line the
	# heading matcher caught, not a drug.
	if drug.endswith('.') or drug[:1].islower() or len(drug) > 44:
		continue
	for pat, conv in AGE_PATTERNS:
		m = pat.search(text)
		if m:
			age_limits.append((drug, conv(m), text))
			break
	else:
		if NEONATE.search(text):
			age_limits.append((drug, 0, text))
		elif CHILDREN.search(text):
			age_limits.append((drug, None, text))
age_limits.sort(key=lambda r: (r[1] is not None, r[1] or 0, r[0].lower()))

# --- condition axes -----------------------------------------------------------------------------
# The 20 condition families the source states, each with the pattern that recognises it in a
# monograph's contraindication line and the label a person would recognise. The pattern is the
# source's own wording, not a diagnosis: "renal impairment (Appendix 4)" and "renal function" are
# how the Formulary says it, and a narrower pattern would miss rows the source wrote.
CONDITIONS = [
	('renal_impairment', 'Kidney problems', r'renal impairment|renal function|Appendix 4'),
	('hepatic_impairment', 'Liver problems', r'hepatic impairment|liver disease|severe liver|Appendix 5'),
	('porphyria', 'Porphyria', r'porphyria'),
	('asthma', 'Asthma or other breathing problems', r'asthma|obstructive airway|bronchospasm'),
	('peptic_ulcer', 'Stomach ulcer or bleeding', r'peptic ulcer|active ulcer|gastro-?intestinal (bleeding|ulceration)|bleeding disorder'),
	('heart_failure', 'Heart failure', r'heart failure|cardiac failure|cardiac decompensation'),
	('conduction_block', 'Heart rhythm or conduction problems', r'atrioventricular block|heart block|sinoatrial block|sino-atrial block|sick sinus|Stokes-Adams'),
	('hypertension', 'Severe high blood pressure', r'severe hypertension|marked hypertension'),
	('diabetes', 'Diabetes', r'diabetes|ketoacidosis'),
	('g6pd_deficiency', 'G6PD deficiency', r'G6PD'),
	('alcohol_dependence', 'Alcohol dependence', r'alcohol dependence|alcoholism|chronic alcohol'),
	('myasthenia_gravis', 'Myasthenia gravis', r'myasthenia gravis'),
	('glaucoma', 'Glaucoma', r'glaucoma'),
	('lupus', 'Lupus', r'lupus erythematosus'),
	('thyroid_disease', 'Thyroid disease', r'thyrotoxicosis|hyperthyroid'),
	('blood_disorders', 'Blood disorders', r'blood disorder|bone marrow|granulocytopen|thrombocytopen|haemophilia|anaemia|neutropenia'),
	('hypersensitivity', 'Allergy to this medicine', r'hypersensitivity|known allergy|allergic to'),
	('gout', 'Gout', r'\bgout\b'),
	('epilepsy', 'Epilepsy', r'\bepilep|seizure disorder'),
	('pregnancy_listed', 'Pregnancy (see the pregnancy list)', r'pregnancy \(Appendix 2\)'),
]
# Drop the last: it duplicates the pregnancy axis, which has its own table and its own caveat, and
# a condition a caller selects by hand is not the same input as "I am pregnant".
CONDITIONS = [c for c in CONDITIONS if c[0] != 'pregnancy_listed']

condition_flags = []
for drug, text in app2['contraindications'].items():
	if drug.endswith('.') or drug[:1].islower() or len(drug) > 44:
		continue
	for slug, _label, pat in CONDITIONS:
		if re.search(pat, text, re.I):
			condition_flags.append((drug, slug, text))

# --- pregnancy and breastfeeding -----------------------------------------------------------------
preg = [(d, c) for d, c in app2['pregnancy'] if c and not d.endswith('.')]
bf = [(d, c) for d, c in app2['breastfeeding'] if c and not d.endswith('.')]

HEAD = '''"""Contraindication reference — §MED-002, from the WHO Model Formulary 2008.

The section's third bullet asks the checker to "flag contraindications for pregnancy, children, and
common conditions". `check_interactions` had no such axis: it read a table of drug *pairs*, and a
contraindication is a property of one drug in one patient, not of two drugs together.

Four axes, each from the Formulary's own tables rather than from a summary of them:

* **Pregnancy** — Appendix 2 (p. 582), @PREGNANCY@ drugs.
* **Breastfeeding** — Appendix 3 (p. 599), @BREASTFEEDING@ drugs.
* **Children** — the age floor in each drug's own `Contraindications:` line, @AGE@ drugs.
* **Conditions** — the @CONDITIONS@ condition families the monographs name, @FLAGS@ drug/condition
  pairs.

The numbers are reproduced here rather than read at runtime, for the reason
`afya.records.growth_standards` gives: no network egress inside a clinical calculation, and a table
that can silently change under a running service is not a reference. The source PDF is archived at
`sources/who-model-formulary/` with its checksums and page references in `sources/INDEX.md`.

TWO CAVEATS THE SOURCE STATES, WHICH TRAVEL WITH ITS DATA.

Appendix 2 says in its own words that "Absence of a medicine from the list does not imply safety",
and that "Drugs should be prescribed in pregnancy only if the expected benefits to the mother are
thought to be greater than the risk to the fetus". A checker that returned "no flag" for a drug the
appendix does not list, without those sentences, would turn an absent row into a reassurance the
source explicitly refuses to give. Both are served with every pregnancy answer.

THE AGE AXIS IS A FLOOR THE SOURCE STATES, NOT A DOSE. Some monographs state a number ("children
under 8 years", "infants less than 3 months") and some state only a word ("children", "neonates").
A word is kept as `None` rather than converted to a number the source did not write — the same
reason `afya.medicine.formulary` leaves `max_mg_per_dose` empty where no maximum is stated.
"""
import re

from afya.medicine.interactions import canonical as _interactions_canonical

# Appendix 2, verbatim.
PREGNANCY_CAVEAT = 'Absence of a medicine from the list does not imply safety'
PREGNANCY_BENEFIT_CAVEAT = (
	'Drugs should be prescribed in pregnancy only if the expected benefits to the mother are '
	'thought to be greater than the risk to the fetus.'
)

# (drug, comment) — Appendix 2, p. 582. Drugs the appendix lists as harmful in pregnancy.
PREGNANCY: tuple[tuple[str, str], ...] = (
'''

MID_1 = ''')

# (drug, comment) — Appendix 3, p. 599. Drugs present in breast milk, and what they do there.
BREASTFEEDING: tuple[tuple[str, str], ...] = (
'''

MID_2 = ''')

# (drug, min_age_months, source text) — the age floor in the monograph's own contraindication line.
# `None` where the source states a word ("children", "neonates") rather than a number.
AGE_LIMITS: tuple[tuple[str, int | None, str], ...] = (
'''

MID_3 = ''')

# (slug, label) — the condition families the monographs name. The label is what a person selects;
# the slug is what the service compares against.
CONDITION_AXES: tuple[tuple[str, str], ...] = (
'''

MID_4 = ''')

# (drug, condition_slug, source text) — a condition the drug's own contraindication line names.
CONDITION_FLAGS: tuple[tuple[str, str, str], ...] = (
'''

TAIL = ''')

_BY_NAME = {drug.lower(): (drug, text) for drug, text in PREGNANCY}
_BF_BY_NAME = {drug.lower(): (drug, text) for drug, text in BREASTFEEDING}
_AGE_BY_NAME = {drug.lower(): (drug, months, text) for drug, months, text in AGE_LIMITS}
_FLAGS_BY_NAME: dict[str, list[tuple[str, str]]] = {}
for _drug, _slug, _text in CONDITION_FLAGS:
	_FLAGS_BY_NAME.setdefault(_drug.lower(), []).append((_slug, _text))
CONDITION_LABELS: dict[str, str] = dict(CONDITION_AXES)


def canonical(name: str) -> str | None:
	"""The table's own name for a drug, or `None`. Whole-word matched, as `interactions.canonical`.

	Falls back to `interactions.canonical` for a name this module has never heard of: the brand and
	colloquial aliases live with the interaction table, and a person who types `panadol` is asking
	about paracetamol whether they are asking about a pair or about a pregnancy.
	"""
	low = name.strip().lower()
	if not low:
		return None
	for table in (_BY_NAME, _BF_BY_NAME, _AGE_BY_NAME, _FLAGS_BY_NAME):
		if low in table:
			hit = table[low]
			return hit[0] if isinstance(hit, tuple) else low
	words = set(re.findall(r'[a-z0-9+/-]+', low))
	if not words:
		return None
	for table in (_BY_NAME, _BF_BY_NAME, _AGE_BY_NAME):
		for key, value in table.items():
			key_words = set(re.findall(r'[a-z0-9+/-]+', key))
			if key_words and key_words <= words:
				return value[0]  # type: ignore[index]
	for key in _FLAGS_BY_NAME:
		key_words = set(re.findall(r'[a-z0-9+/-]+', key))
		if key_words and key_words <= words:
			return key
	return _interactions_canonical(name)


def for_patient(drugs: list[str], pregnant: bool | None = None,
                age_months: int | None = None,
                conditions: list[str] | None = None) -> list[tuple[str, str, str]]:
	"""Flags for these drugs in this patient, as (drug, axis, source text).

	Each axis fires only on the input that selects it: pregnancy on `pregnant`, breastfeeding is
	*not* inferred from it (they are different clinical states and the source keeps separate
	tables), the age axis on an age below the floor the source states, and a condition only when
	the caller names that condition. Nothing is inferred from an input the caller did not give.
	"""
	assert drugs is not None, 'a drug list is required'
	wanted = {c.strip().lower() for c in (conditions or [])}
	flags: list[tuple[str, str, str]] = []
	for raw in drugs:
		name = canonical(raw)
		if name is None:
			continue
		low = name.lower()
		if pregnant:
			hit = _BY_NAME.get(low)
			if hit:
				flags.append((hit[0], 'pregnancy', hit[1]))
		if age_months is not None:
			hit_age = _AGE_BY_NAME.get(low)
			if hit_age and (hit_age[1] is None or age_months < hit_age[1]):
				flags.append((hit_age[0], 'children', hit_age[2]))
		for slug, text in _FLAGS_BY_NAME.get(low, []):
			if slug in wanted:
				flags.append((name, slug, text))
	return flags
'''

lines = [HEAD.replace('@PREGNANCY@', str(len(preg)))
             .replace('@BREASTFEEDING@', str(len(bf)))
             .replace('@AGE@', str(len(age_limits)))
             .replace('@CONDITIONS@', str(len(CONDITIONS)))
             .replace('@FLAGS@', str(len(condition_flags)))]
for section, rows_ in [(MID_1, preg), (MID_2, bf)]:
	for d, c in rows_:
		lines.append(f"\t({lit(d)}, {lit(c)}),\n")
	lines.append(section)
for d, months, text in age_limits:
	lines.append(f"\t({lit(d)}, {months!r}, {lit(text)}),\n")
lines.append(MID_3)
for slug, label, _pat in CONDITIONS:
	lines.append(f"\t({lit(slug)}, {lit(label)}),\n")
lines.append(MID_4)
for d, slug, text in condition_flags:
	lines.append(f"\t({lit(d)}, {lit(slug)}, {lit(text)}),\n")
lines.append(TAIL)

(OUT / 'contraindications.py').write_text(''.join(lines))
print(f'contraindications.py: pregnancy {len(preg)}, breastfeeding {len(bf)}, '
      f'age {len(age_limits)}, conditions {len(CONDITIONS)}, flags {len(condition_flags)}')
