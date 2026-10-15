"""§REC-004's reproductive-health content, every claim traceable to the WHO fact sheets.

Four of the section's six Features — contraception reminders, fertility awareness, menopause support
and referral to services — are statements about reproductive physiology, and each contains a figure
or a grouping that has to come from somewhere. They come from two WHO fact sheets, archived at
`sources/who-reproductive-health/` with both checksums and the verbatim claims recorded in
`sources/INDEX.md`:

- "Menopause", 16 October 2024.
- "Family planning/contraception methods", 3 July 2025.

The rule this module is written to is the one the archive states: **where the source gives no number,
the code carries no number.** WHO groups contraceptive methods into three reliability bands and
states no efficacy percentage for any of them, so `reliability` here is WHO's own three-group
wording and never a failure rate. The one figure the tracker computes — the twelve-month rule — is
stated verbatim by the menopause fact sheet, and it is the sentence that ties contraception to
menopause in a single number.
"""

# The menopause fact sheet's own figure, and the reason it is load-bearing: "Pregnancy is still
# possible during perimenopause. Contraception is recommended to avoid unintended pregnancy until
# after 12 consecutive months without menstruation." It is the whole of the menopause state machine
# — a person is perimenopausal, and still needs contraception, until twelve consecutive months have
# passed with no period. Computed from the person's own logged cycles, never from their age.
PERIMENOPAUSE_MONTHS = 12

# "Most women experience menopause between the ages of 45 and 55 years." *Most*, and the source says
# so. An age outside this range is not an error and the tracker never rules on a person's menopausal
# status from their age — it is carried so the output can say where the person sits relative to the
# population figure the source states, and nothing more.
MENOPAUSE_TYPICAL_AGE = (45, 55)


class Reliability:
	"""WHO's own three reliability groups, verbatim from the family-planning fact sheet.

	Not an enum with numbers behind it. The fact sheet states "highly effective", "work well when
	taken correctly" and "less reliable" and gives no percentage for any method, so these are the
	strings the code repeats — a failure rate invented to fill the column would read as one WHO
	publishes.
	"""

	HIGHLY_EFFECTIVE = 'highly effective and long-lasting'
	WHEN_TAKEN_CORRECTLY = 'works well when taken correctly'
	LESS_RELIABLE = 'less reliable'


# WHO's grouping, in the source's own order and with its own examples. `prevents_sti` is the one
# distinction the fact sheet draws between methods: "Only one contraceptive method, condoms, can
# prevent both pregnancy and the transmission of sexually transmitted infections, including HIV."
CONTRACEPTIVE_METHODS: tuple[dict[str, object], ...] = (
	{'slug': 'implant', 'label': 'Implant', 'reliability': Reliability.HIGHLY_EFFECTIVE,
	 'prevents_sti': False},
	{'slug': 'iud', 'label': 'Intrauterine device (IUD)', 'reliability': Reliability.HIGHLY_EFFECTIVE,
	 'prevents_sti': False},
	{'slug': 'sterilisation', 'label': 'Sterilisation', 'reliability': Reliability.HIGHLY_EFFECTIVE,
	 'prevents_sti': False},
	{'slug': 'pill', 'label': 'Pill', 'reliability': Reliability.WHEN_TAKEN_CORRECTLY,
	 'prevents_sti': False},
	{'slug': 'injection', 'label': 'Injection', 'reliability': Reliability.WHEN_TAKEN_CORRECTLY,
	 'prevents_sti': False},
	{'slug': 'patch', 'label': 'Patch', 'reliability': Reliability.WHEN_TAKEN_CORRECTLY,
	 'prevents_sti': False},
	{'slug': 'vaginal_ring', 'label': 'Vaginal ring', 'reliability': Reliability.WHEN_TAKEN_CORRECTLY,
	 'prevents_sti': False},
	{'slug': 'condom', 'label': 'Condoms', 'reliability': Reliability.WHEN_TAKEN_CORRECTLY,
	 'prevents_sti': True},
	{'slug': 'fertility_awareness', 'label': 'Fertility awareness-based methods',
	 'reliability': Reliability.LESS_RELIABLE, 'prevents_sti': False},
	{'slug': 'withdrawal', 'label': 'Withdrawal', 'reliability': Reliability.LESS_RELIABLE,
	 'prevents_sti': False},
)

METHODS_BY_SLUG: dict[str, dict[str, object]] = {str(m['slug']): m for m in CONTRACEPTIVE_METHODS}

# The sentence the fact sheet states about the two methods in its least reliable group, and the
# reason the tracker's own fertile-window output must carry it: a calendar estimate is not a
# contraceptive method of the same standing as an implant, and a tracker that presented its own
# window as a green light would be causing the pregnancy it exists to help avoid.
FERTILITY_AWARENESS_NOTE = (
	'Fertility awareness-based methods and withdrawal are less reliable than the methods above. '
	'A predicted fertile window is an estimate from past cycles, not a contraceptive method.'
)

# --- the fertile window, and every figure in it ---------------------------------------------------
#
# Neither WHO fact sheet states when ovulation happens, so the arithmetic comes from NHS UK's
# "Fertility in the menstrual cycle" page, archived beside them at
# `sources/who-reproductive-health/nhs-fertility-menstrual-cycle.*`. Two figures, both with a spread
# the source states and neither narrowed here:
#
#   "The time from the release of an egg to the start of a period is around 10 to 16 days."
#   "Sperm can survive in the fallopian tubes for up to 7 days after sex."
#
# The window is therefore *ovulation minus sperm survival* through *ovulation plus the egg's own
# viability*. NHS gives **no** egg-viability figure — the 12-to-24-hour number that circulates is not
# on this page — so `EGG_VIABILITY_DAYS` is 1 and the gap is recorded rather than filled: the code
# reports the conservative end (a window that does not claim the egg outlives a day), and
# `sources/INDEX.md` says why the figure is what it is. A number invented to fill that column would
# read as one NHS publishes.
#
# The luteal phase's own spread (10–16 days) is *not* used to widen the window: the midpoint-14
# estimate is the conventional one and widening it by the spread would produce a window covering
# most of the cycle, which is a window that tells a person nothing. `LUTEAL_PHASE_DAYS` is the
# conventional 14 and the output states the spread the source gives.
SPERM_SURVIVAL_DAYS = 7
EGG_VIABILITY_DAYS = 1
LUTEAL_PHASE_DAYS = 14
LUTEAL_PHASE_RANGE = (10, 16)

# The source's own caveat, which travels with every window the tracker reports: the day-14 estimate
# is for a regular 28-day cycle and "this won't apply to women whose cycles are shorter or longer".
FERTILE_WINDOW_CAVEAT = (
	'Ovulation is estimated as 14 days before your next period, from your own logged cycle length. '
	'NHS gives the time from ovulation to the next period as around 10 to 16 days, so the real day '
	'moves. It is difficult to pinpoint exactly when ovulation happens.'
)

# The misconception the fact sheet names outright, because a person who believes it stops using a
# method they need: "modern contraceptive methods do not cause infertility."
NO_INFERTILITY_NOTE = 'Modern contraceptive methods do not cause infertility.'

# The fact sheet's own definition, carried as a definition and never applied as a diagnosis.
INFERTILITY_DEFINITION = 'the inability to conceive after 12 months of regular unprotected sex'

# §REC-004's "menopause support". The symptoms are the fact sheet's list, verbatim and unabridged —
# six of them, plus the two long-term risks it states in the same paragraph. Nothing is added: a
# symptom the source does not name would be a symptom the app is guessing at.
MENOPAUSE_SYMPTOMS: tuple[dict[str, str], ...] = (
	{'slug': 'hot_flushes', 'label': 'Hot flushes and night sweats',
	 'detail': 'A sudden feeling of heat in the face, neck and chest, often with flushing, sweating '
	           'and palpitations, lasting several minutes.'},
	{'slug': 'cycle_changes', 'label': 'Changes in the regularity and flow of your period',
	 'detail': 'The cycle becomes irregular before it stops altogether.'},
	{'slug': 'vaginal_dryness', 'label': 'Vaginal dryness, pain during sex, or incontinence',
	 'detail': 'The vaginal wall thins, which can also increase the risk of tears and of HIV '
	           'transmission during vaginal sex.'},
	{'slug': 'sleep', 'label': 'Difficulty sleeping',
	 'detail': 'Insomnia is common through the menopausal transition.'},
	{'slug': 'mood', 'label': 'Changes in mood, depression and anxiety',
	 'detail': 'Low mood and anxiety are associated with the transition, not with a personal failing.'},
	{'slug': 'cardiovascular', 'label': 'Heart and circulation risk',
	 'detail': "Women's advantage over men in cardiovascular disease gradually disappears after "
	           'menopause.'},
	{'slug': 'bone_density', 'label': 'Bone density loss',
	 'detail': 'Loss of bone density at menopause contributes to higher rates of osteoporosis and '
	           'fractures.'},
)

# The fact sheet's own sentence about what to do with a symptom, which is as far as the source goes:
# it states no threshold at which a symptom needs review, so neither does the code.
MENOPAUSE_ADVICE = (
	'Symptoms that affect your health and well-being should be discussed with a health-care provider, '
	'who can consider your medical history and what matters to you. There are non-hormonal and '
	'hormonal options that can help.'
)

# §REC-004's "referral to services". Each row is a service the app actually serves elsewhere in the
# tree, read from the directory that owns it rather than duplicated here — the same discipline
# `afya.info.service._directory_rows` uses for §INF-006. `afya.mental.views.COUNSELLING_LINES` holds
# the counselling numbers and `afya.info.service.HOTLINES` the national ones, so a number cannot
# drift between the two screens that show it.
REFERRAL_SERVICES: tuple[dict[str, str], ...] = (
	{'slug': 'family_planning', 'label': 'Family planning and contraception',
	 'where': 'any public health facility or Marie Stopes Kenya clinic',
	 'note': 'A health worker can help you choose a method that suits your health and preferences.'},
	{'slug': 'antenatal', 'label': 'Antenatal and maternity care',
	 'where': 'your nearest health facility', 'note': 'Booking early in pregnancy matters.'},
	{'slug': 'gbv', 'label': 'Gender-based violence support',
	 'where': 'the national GBV helpline, or a health facility', 'note': ''},
	{'slug': 'counselling', 'label': 'Counselling and emotional support',
	 'where': 'the counselling lines in the hotline directory', 'note': ''},
	{'slug': 'infertility', 'label': 'Fertility assessment',
	 'where': 'a health facility with reproductive health services',
	 'note': f'Infertility is defined as {INFERTILITY_DEFINITION}, and treating it is part of '
	         'family planning.'},
)


# --- §17.6's last line: "Extra protections for adolescent reproductive health data" --------------
#
# What "reproductive health data" *is*, as a classification the server computes from a document's
# own content rather than a field a caller sets. The distinction is the whole of the mechanism: a
# `sensitive: bool` on the request would be a value the person filing the record attests about
# itself, and the one case this protection exists for — a guardian filing their daughter's
# contraceptive under a benign title — is exactly the case that flag would be set to `False` on.
# The DPIA gate in `afya.privacy` refuses a boolean the caller supplies about itself for the same
# reason, and this is that rule applied to a wallet document.
#
# The vocabulary is the WHO family-planning table above plus the SRH referral services, both of
# which this module already carries from archived sources — so the classifier reads the *same*
# method list the contraception feature records against, and a method added there is classified
# here without a second list to keep in step.
#
# The match is on the words a clinical record actually contains: a prescription names the drug
# ("Levonorgestrel"), a referral names the service ("Family planning"), and an ANC document names
# the visit. Substring matching is deliberately loose in one direction only — it may over-classify
# (a document mentioning "condom" in passing is withheld from a guardian) and must not
# under-classify, because the failure that matters is an adolescent's record being readable by the
# person she is avoiding, not a guardian being asked to look at one document fewer.
_DERIVED_TERMS: tuple[str, ...] = (
	# WHO's method labels and slugs, read off `CONTRACEPTIVE_METHODS` rather than retyped.
	*tuple(str(m['label']).lower() for m in CONTRACEPTIVE_METHODS),
	*tuple(str(m['slug']).replace('_', ' ').lower() for m in CONTRACEPTIVE_METHODS),
)

_EXPLICIT_TERMS: tuple[str, ...] = (
	# The drugs the contraception feature records against, which is how a prescription names the
	# method: a pill is filed as `Levonorgestrel`, never as "Pill". These are the progestogens and
	# estrogens the WHO Model Formulary lists for contraception, plus the two long-acting methods
	# that appear by name in a procedure note.
	'levonorgestrel', 'medroxyprogesterone', 'norethisterone', 'etonogestrel', 'desogestrel',
	'ethinylestradiol', 'contracept', 'implanon', 'jadelle', 'depo-provera', 'depo provera',
	'intrauterine', 'iud', 'iucd',
	# Pregnancy and its care. An ANC visit, a maternity booking and a delivery are reproductive
	# health data about the adolescent herself, and the spec's own §17.6 line names adolescent
	# pregnancy as the case the protection is for.
	'antenatal', 'prenatal', 'anc', 'pregnan', 'maternity', 'postnatal', 'obstetric',
	# The SRH services `REFERRAL_SERVICES` names, so a referral document is classified by the
	# service it refers to rather than by the word "referral". `REFERRAL_SERVICES` also lists
	# counselling and GBV support, and those are deliberately **not** here: §17.6's line names
	# *reproductive* health data, and a mental-health counselling referral is not that. Sweeping it
	# in would withhold a record §17.6's third line gives the guardian, which is this protection
	# widening itself past the sentence it implements.
	'family planning', 'reproductive health', 'fertility', 'infertility',
)

# The two sources overlap on purpose — a method's label and its slug can be the same word ("iud"),
# and the explicit list names a drug the WHO table gives no slug for. Deduped in order rather than
# asserted disjoint, because the overlap is the two sources agreeing, not a mistake.
REPRODUCTIVE_TERMS: tuple[str, ...] = tuple(dict.fromkeys(_DERIVED_TERMS + _EXPLICIT_TERMS))

# The terms above are matched as substrings, and two of them are short enough to appear inside
# unrelated words: "anc" is in "balance", "iud" is in nothing but "anc" needs the guard. Rather than
# shorten the list — an abbreviation a clinical note really uses is worth keeping — the short ones
# are matched on a word boundary and the long ones as substrings. `_SHORT_TERMS` is the split, and
# it is asserted below so a term added to one tuple cannot be silently matched the other way.
_SHORT_TERMS = frozenset({'anc', 'iud', 'iucd'})

assert _SHORT_TERMS <= set(REPRODUCTIVE_TERMS), 'every short term is one of the classified terms'
assert len(REPRODUCTIVE_TERMS) >= len(_DERIVED_TERMS), 'the WHO table survives dedup whole'


def is_reproductive_health_data(*, kind: str, title: str, detail: str = '') -> bool:
	"""Whether a wallet document is reproductive health data under §17.6's last line.

	Reads the document's own fields — the kind, the title and the free-text detail — and nothing the
	caller separately asserts. A `prescription` for Levonorgestrel is caught by the drug name in its
	title; an `anc` document is caught by its kind; a `referral` to family planning is caught by the
	service in its title or detail.

	The `kind` argument is matched against the reproductive terms too rather than compared to a set
	of kinds, because `anc` is both a wallet kind (§9.2's contents) and a term in the list — one
	spelling, read once, rather than a kind list that could drift from the term list beside it.
	"""
	import re
	haystack = f'{kind} {title} {detail}'.lower()
	for term in REPRODUCTIVE_TERMS:
		if term in _SHORT_TERMS:
			if re.search(rf'\b{re.escape(term)}\b', haystack):
				return True
		elif term in haystack:
			return True
	return False


assert is_reproductive_health_data(kind='prescription', title='Prescription: Levonorgestrel'), \
	'the classifier finds a contraceptive by its drug name'
assert is_reproductive_health_data(kind='anc', title='Antenatal visit 1'), \
	'the classifier finds an ANC document by its kind'
assert not is_reproductive_health_data(kind='immunisation', title='OPV dose 1'), \
	'an immunisation is not reproductive health data'
assert not is_reproductive_health_data(kind='lab', title='Malaria RDT'), \
	'a malaria test is not reproductive health data'
assert not is_reproductive_health_data(kind='lab', title='Balance test'), \
	'the short term "anc" does not match inside "balance"'
