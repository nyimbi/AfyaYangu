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
