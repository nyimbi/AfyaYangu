"""§3's vision, positioning, design principles and non-goals — as data, with the one check §3.2
declares and nothing performed.

§3 is the section that says what the product *is*, and none of it was in the code. §3.1 is the
vision sentence, §3.2 is the brand, §3.3 is twelve design principles, §3.4 is five non-goals. Four
of the twelve principles are cited in the source by number (§3.3 principle 1 in `personas`, 3 in the
channel cost model, 8 and 9 in the content rules, 12 in `registry.diseases`), so the table is
partially load-bearing already — and the table itself, the thing that says which number means what,
was nowhere. A citation to "§3.3 principle 8" is unverifiable if nothing carries the row.

**§3.2's claim has a declared check and no check.** `rollout.ANTIPATTERNS` carries "A name with
'Ebola' in it" with `checkable=True` and `check='the served product name contains no disease name'`.
That string is read by one test, which asserts the anti-pattern is *present* — not that its check is
*performed*. So the anti-pattern that §23.1 names as the highest-likelihood strategic risk ("Branded
as an Ebola app and abandoned post-outbreak") had a check named in a table and nothing running it,
which is the same shape as §16.2's `backoff_delay_s`: a control that exists is not a control that is
applied. `brand_violations()` is the check, and it is derived from `registry.diseases` rather than
from a list of words — the disease the name must not contain is the vocabulary the system already
carries, so adding a disease to §3.3 principle 12's list adds it to the brand check with no second
edit.

**§3.3 principle 12's list is the reason the check can be derived at all.** It names the diseases
Tier 4 activates for and ends "and the next unknown"; `DISEASE_ROWS` carries all of them with the
English spelling, which is what a product name would actually contain. `english()` refuses an
unknown slug, so the check cannot silently compare against an empty string.
"""
from afya.brand.views import Brand, NonGoal, Principle
from afya.registry.diseases import DISEASE_ROWS, OTHER

# §3.1's vision, verbatim. It is one sentence and it is the whole argument for the tier model in
# §7.1: find care today, protect the family tomorrow, stand together in an outbreak.
VISION = (
	'Every person in Kenya carries a guardian in their pocket — a tool that helps them find care '
	'today, protect their family tomorrow, and stand together against an outbreak when it comes.'
)

# §3.2's identity. The two names are the section's own: "Afya Yangu (My Health)" public, "Mlinzi
# (Guardian)" internal. Both are carried with their English gloss because the section writes them as
# pairs and a reader meeting "Mlinzi" in a log has nowhere else to learn what it means.
BRAND = Brand(
	public_name='Afya Yangu',
	public_name_english='My Health',
	programme_name='Mlinzi',
	programme_name_english='Guardian',
	positioning=(
		'Afya Yangu is the free health companion for every Kenyan family — find care, verify your '
		"medicine, keep your family's health records safe, and get warned early when something is "
		'going around.'
	),
	not_the_ebola_app=(
		'It is not "the Ebola app." Ebola is one of the conditions it handles. The brand must '
		"survive the outbreak's end."
	),
)

# §3.3's twelve rows, verbatim and in the section's order. The implication column is what makes the
# table actionable; four of these numbers are cited elsewhere in the source, so this is the table
# those citations resolve against.
PRINCIPLES: tuple[Principle, ...] = (
	Principle(number=1, principle='Channels before apps',
		implication='Reach is achieved through WhatsApp, SMS, USSD, and radio. The app is the power tier, not the entry point.'),
	Principle(number=2, principle='Zero friction to first value',
		implication='Under 60 seconds from install to usefulness. No login, no signup, no permissions required for Tier 1.'),
	Principle(number=3, principle="Zero-rated or it doesn't count",
		implication='Data cost is the single largest barrier. Every channel must be zero-rated or free-at-point-of-use.'),
	Principle(number=4, principle='Offline-first, always',
		implication='Every core feature works with no connectivity. Sync is opportunistic.'),
	Principle(number=5, principle='Triage all causes, not one',
		implication='A fever in Kenya is malaria far more often than Ebola. Broad differential triage is clinically correct and commercially durable.'),
	Principle(number=6, principle='Anonymity by default',
		implication='No account required. Identity is opt-in.'),
	Principle(number=7, principle='On-device processing',
		implication='Raw sensor data never leaves the phone. Only derived metrics, with consent.'),
	Principle(number=8, principle='Local language first',
		implication='Swahili and major local languages are primary. English is secondary.'),
	Principle(number=9, principle='Answers, not information',
		implication='Never "Ebola is a viral haemorrhagic fever." Always "You have fever and no travel history — most likely malaria. Go to a clinic today."'),
	Principle(number=10, principle='Every output is forwardable',
		implication='Any answer must be shareable as a WhatsApp card. That is how information moves in Kenya.'),
	Principle(number=11, principle='Trust through transparency',
		implication='Open-source client. Privacy policy in Swahili. In-app data dashboard. Co-branded with trusted institutions.'),
	Principle(number=12, principle='Build for the outbreak after this one',
		implication='Tier 4 activates for Ebola, cholera, Rift Valley fever, mpox, measles, and the next unknown.'),
)

PRINCIPLE: dict[int, Principle] = {p.number: p for p in PRINCIPLES}

# §3.4's five non-goals, verbatim. Each is a boundary a feature crosses by accident rather than on
# purpose — a premium flag, a follower count, a diagnosis string — so they are carried as an enum a
# gate can read rather than as a paragraph nobody re-reads.
NON_GOALS: tuple[NonGoal, ...] = tuple(NonGoal)

assert len(PRINCIPLES) == 12 and tuple(p.number for p in PRINCIPLES) == tuple(range(1, 13)), \
	'§3.3 lists twelve principles, numbered 1..12 in order'
assert len(NON_GOALS) == 5, '§3.4 lists five non-goals'


def principle(number: int) -> Principle:
	"""Resolve a "§3.3 principle N" citation. Refuses a number the section does not carry rather
	than returning None, because a citation to a row that does not exist is the failure this module
	exists to make impossible."""
	assert number in PRINCIPLE, f'§3.3 has no principle {number}'
	return PRINCIPLE[number]


def _disease_words() -> tuple[str, ...]:
	"""The English names a product name must not contain, from the disease vocabulary itself.

	Derived rather than listed: §3.3 principle 12's diseases are what `DISEASE_ROWS` carries, so a
	disease added there is one the brand check refuses without a second edit. The `other` slot is
	excluded — "Unnamed disease (the next unknown)" is a placeholder, and a name containing it is not
	the anti-pattern §20.2 describes.
	"""
	return tuple(row.english for row in DISEASE_ROWS if row.slug != OTHER)


def brand_violations(name: str) -> list[str]:
	"""The check §20.2 declares for "A name with 'Ebola' in it" and nothing performed.

	Case-insensitive on the whole name, because the anti-pattern is about the *word* reaching a
	store listing — "EBOLA Response" is the same failure as "Ebola Response". Returns every disease
	found rather than the first, so a name that manages to carry two is not half-reported.
	"""
	lowered = name.lower()
	return [word for word in _disease_words() if word.lower() in lowered]


def brand_is_clean(name: str) -> bool:
	"""Whether a served name survives the outbreak's end, which is what §3.2 requires of it."""
	return not brand_violations(name)


# The check, run against the names this build actually ships, at import. A rename that puts a disease
# in the product name fails here rather than in a review nobody holds — §23.1 names "branded as an
# Ebola app and abandoned post-outbreak" as the highest-likelihood strategic risk, and a risk whose
# check is a table row is the shape §16.2's `backoff_delay_s` had.
assert brand_is_clean(BRAND.public_name), f'§20.2: the served name carries {brand_violations(BRAND.public_name)}'
assert brand_is_clean(BRAND.programme_name), f'§20.2: the programme name carries {brand_violations(BRAND.programme_name)}'
