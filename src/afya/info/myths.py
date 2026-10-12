"""§INF-004's myth library, and §6.4's pre-drafted corrections, as one corpus.

§INF-004 prints a Format — `"Rumour: [claim]. Fact: [correction]. Source: [authority]."` — and a
library of rumours is only searchable *by claim* if the claim is a field. The corpus had the
correction and nothing else: `CORRECTION_LIBRARY` held one string per topic per language with the
authority glued on with a hyphen, and the library's two myth rows held a correction as prose in
`body`. Two tables, one subject, no link between them — so the response protocol could publish a
correction the myth library could not show, and neither could be searched, browsed or carded.

This module is the one table. `Myth` carries the claim, the correction and the named authority as
three fields; `correction_text` renders the form §6.4 publishes; `MYTH_CATEGORIES` says which of
§6.4's six pre-drafting categories each topic answers. `afya.community.protocol` re-exports the
categories and `afya.community.service` derives `CORRECTION_LIBRARY` from here, so the correction
the protocol publishes and the correction the library serves are the same string by construction
rather than by two authors agreeing.

The module imports nothing from `afya`. `afya.community.protocol` imports it, and that module is
the §6.4 clock — keeping the corpus free of the service layer is what stops the import graph from
becoming circular the moment the protocol needs a correction and the library needs a clock.

Every string here is GSM-7. §6.4 step 5 publishes "on all channels simultaneously" and §6.2.6 names
SMS as one, so a correction with an em dash is one that cannot be sent on a channel the section
requires — which is what the six corrections in `CORRECTION_LIBRARY` were before §6.4 was built.
The separator is a hyphen and `tests/ci/test_inf004.py` holds the whole corpus to the character set.
"""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# The languages a rumour correction must reach. §6.2.4 forbids publishing English-only for a
# life-safety message and §6.4 step 4 drafts the correction "in all relevant languages"; a rumour
# correction answers §6.1's rank 5, which is one of the section's life-safety questions.
MYTH_LANGS: tuple[str, ...] = ('en', 'sw')


class MythCategory(BaseModel):
	"""One of §6.4's six categories to pre-draft, and the topics that answer it.

	`topics` names the correction-library keys that answer this category, so the link is data rather
	than a naming convention a reader has to guess. An empty list is the gap the section warns about.

	`examples` is empty for the two categories §6.4 names without any — "Vaccine myths" and "Burial
	and body-handling myths" are printed bare, while the other four carry a parenthetical. The field
	is not defaulted to something plausible: inventing "infertility" for the vaccine row would put a
	myth into the pre-drafting brief that the section never listed, and a brief is acted on.
	"""
	model_config = MODEL_CONFIG
	slug: str = Field(pattern=r'^[a-z][a-z0-9_]*$')
	label: str = Field(min_length=1)
	examples: list[str]
	topics: list[str]


class Myth(BaseModel):
	"""One rumour, with the correction and the authority that answers it.

	Three fields rather than one rendered sentence, because §INF-004's Format prints three parts and
	each is read differently: the claim is what a person searches for and what a browse list shows,
	the correction is what they are told, and the authority is what makes the correction checkable.
	Glued together, the claim cannot be indexed, the authority cannot be listed, and the correction
	cannot be published on its own — which is what the single-string table could not do.

	`source` is empty for the fallback and for nothing else. A correction with no named authority is
	one a reader cannot weigh, so an empty source is the honest statement that none exists rather
	than a placeholder standing in for one.
	"""
	model_config = MODEL_CONFIG
	topic: str = Field(pattern=r'^[a-z][a-z0-9_]*$')
	# The stable, code-free handle a client keys on, and what may reach a screen. Shared across the
	# two languages: it is the rumour that has a slug, not the sentence stating it.
	slug: str = Field(pattern=r'^[a-z][a-z0-9-]*$')
	lang: str = Field(pattern=r'^(en|sw)$')
	# The short heading a browse list shows. Not the claim: §INF-004's card prints the claim under
	# "Rumour:", so a title that *is* the claim renders the rumour twice on the card it appears on,
	# and a browse list of ten claims is ten sentences where ten labels would scan.
	label: str = Field(min_length=5)
	claim: str = Field(min_length=5)
	fact: str = Field(min_length=5)
	source: str = ''

	def model_post_init(self, _context: object) -> None:
		# A fact and a claim that read as one sentence are the defect this model exists to fix, so
		# the two are asserted to differ rather than left to an author to keep apart by hand. The
		# label is asserted to differ from the claim for the same reason one field over: a label
		# that restates the claim is the duplication this model was built to remove.
		assert self.claim != self.fact, f'{self.topic}/{self.lang}: the claim is not the correction'
		assert self.label != self.claim, f'{self.topic}/{self.lang}: the label is not the claim'
		assert not self.fact.endswith('.'), f'{self.topic}/{self.lang}: the fact is rendered with its stop'


# §6.4's "Common myth categories to pre-draft", with the parenthetical examples the section gives.
# Held here rather than in the protocol module because the categories are a property of the myth
# corpus — a category with no topic behind it is the gap `coverage()` reports — and stating the
# relation in the module that owns the corpus is what keeps it from being stated twice.
MYTH_CATEGORIES: tuple[MythCategory, ...] = (
	MythCategory(slug='false_cures', label='False cures', topics=['cure_claim'],
	             examples=['herbal', 'spiritual', 'pharmaceutical']),
	MythCategory(slug='transmission', label='Transmission myths', topics=['transmission_claim'],
	             examples=['airborne', 'mosquito-borne', 'cursed']),
	MythCategory(slug='vaccine', label='Vaccine myths', topics=['vaccine_claim'], examples=[]),
	MythCategory(slug='conspiracy', label='Conspiracy narratives', topics=[],
	             examples=['population control', 'bioweapon']),
	MythCategory(slug='stigma', label='Stigma narratives', topics=[],
	             examples=['blaming specific communities', 'counties', 'nationalities']),
	MythCategory(slug='burial', label='Burial and body-handling myths', topics=['burial_claim'], examples=[]),
)

# The topics the corpus drafts a correction for. `denial_claim` answers no category §6.4 names and is
# a real narrative anyway — an orphan in `coverage()`, deliberately, because a reader should be able
# to tell the section's list from the library's coverage.
MYTHS: tuple[Myth, ...] = (
	Myth(topic='cure_claim', slug='myth-salt-water', lang='en',
	     label='Salt water cures Ebola',
	     claim='Warm salt water cures Ebola.',
	     fact='No herbal or religious remedy cures Ebola. Only supportive care in a treatment unit improves survival',
	     source='MoH/PHEOC'),
	Myth(topic='cure_claim', slug='myth-salt-water', lang='sw',
	     label='Maji ya chumvi huponya Ebola',
	     claim='Maji ya chumvi yenye joto huponya Ebola.',
	     fact='Hakuna dawa ya miti shamba wala ya kidini inayotibu Ebola. Huduma katika kituo cha matibabu pekee huongeza nafasi ya kupona',
	     source='Wizara ya Afya/PHEOC'),
	Myth(topic='transmission_claim', slug='myth-airborne', lang='en',
	     label='Ebola spreads through the air',
	     claim='Ebola spreads through the air, so a whole village can catch it from one person.',
	     fact='Ebola spreads through direct contact with blood or body fluids of a sick or dead person. It is not airborne and not spread by food',
	     source='WHO'),
	Myth(topic='transmission_claim', slug='myth-airborne', lang='sw',
	     label='Ebola huenea kwa hewa',
	     claim='Ebola huenea kwa hewa, hivyo kijiji chote kinaweza kuambukizwa na mtu mmoja.',
	     fact='Ebola huenea kwa kugusa damu au majimaji ya mwili ya mtu mgonjwa au aliyefariki. Hauenei kwa hewa wala kwa chakula',
	     source='WHO'),
	Myth(topic='vaccine_claim', slug='myth-vaccine', lang='en',
	     label='The vaccine is an untested experiment',
	     claim='The Ebola vaccine is an untested experiment on our people.',
	     fact='Approved Ebola vaccines are tested and free at designated points. Vaccination protects your family',
	     source='MoH'),
	Myth(topic='vaccine_claim', slug='myth-vaccine', lang='sw',
	     label='Chanjo ni jaribio lisilopimwa',
	     claim='Chanjo ya Ebola ni jaribio lisilopimwa kwa watu wetu.',
	     fact='Chanjo za Ebola zilizoidhinishwa zimepimwa na ni bure katika vituo vilivyotajwa. Chanjo inalinda familia yako',
	     source='Wizara ya Afya'),
	Myth(topic='burial_claim', slug='myth-burial', lang='en',
	     label='The family is never told where the grave is',
	     claim='The burial team takes the body away and the family is never told where the grave is.',
	     fact='Safe and dignified burial protects the family while respecting the deceased. Burial teams are trained and free',
	     source='MoH/PHEOC'),
	Myth(topic='burial_claim', slug='myth-burial', lang='sw',
	     label='Familia haielezwi kaburi lilipo',
	     claim='Timu ya maziko huchukua mwili na familia haielezwi kaburi lilipo.',
	     fact='Mazishi salama na ya heshima hulinda familia na kumheshimu marehemu. Timu za mazishi zimefundishwa na hazina malipo',
	     source='Wizara ya Afya/PHEOC'),
	Myth(topic='denial_claim', slug='myth-denial', lang='en',
	     label='Ebola is not real',
	     claim='Ebola is not real. It was invented so that money could be collected.',
	     fact='Ebola is real and Kenya has activated its response. Reporting symptoms early saves lives',
	     source='PHEOC'),
	Myth(topic='denial_claim', slug='myth-denial', lang='sw',
	     label='Ebola si kweli',
	     claim='Ebola si kweli. Iliundwa ili fedha zikusanywe.',
	     fact='Ebola ni kweli na Kenya imeanzisha mwitikio wake. Kuripoti dalili mapema huokoa maisha',
	     source='PHEOC'),
)

# What is said when a claim matches nothing drafted. Not a myth — it is the honest answer §6.2.8 asks
# for, and it is held apart from `MYTHS` because a rumour library item whose "claim" is "a claim we
# have not seen" is a card with nothing on it. The correction is the whole content.
FALLBACK_TOPIC = 'unknown'
FALLBACK_CORRECTION: dict[str, str] = {
	'en': 'This claim is under verification by MoH. Treat unverified health claims as unconfirmed and follow official channels.',
	'sw': 'Madai haya yanachunguzwa na Wizara ya Afya. Chukulia madai ya afya yasiyothibitishwa kama hayajathibitishwa na fuata njia rasmi.',
}

# §6.2.3 "Timestamp everything": when the corpus was last drafted. A correction shown to someone
# asking about a live rumour has to carry when it was written, or they cannot weigh it. The seed's
# stand-in review date, matching `content_seed.SEED_REVIEWED_ON` — a real deployment replaces both
# with the MoH Health Promotion Unit's own.
DRAFTED_ON_ISO = '2026-10-01'

# What a claim has to say to be recognised as this rumour. Substring matches against the lowered
# claim, not a word-boundary pattern, because the claim arrives as free text from a person and
# "saltwater" and "salt water" are the same rumour. English and Swahili together: §3.3 principle 8
# puts the Swahili reader first, and a classifier that only understood English would answer every
# Swahili claim with "under verification" while the correction sat drafted in the same table.
MYTH_KEYWORDS: dict[str, tuple[str, ...]] = {
	'cure_claim': ('salt water', 'saltwater', 'chumvi', 'herbal', 'miti shamba', 'traditional', 'prayer',
	               'remedy', 'cure', 'tiba', 'dawa', 'spiritual', 'hot water', 'maji ya joto'),
	'transmission_claim': ('airborne', 'through the air', 'kwa hewa', 'hewa', 'mosquito', 'mbu',
	                       'breathe', 'cough', 'sneeze', 'chakula', 'food', 'market', 'sokoni'),
	'vaccine_claim': ('vaccine', 'chanjo', 'jab', 'sindano', 'injection', 'microchip', 'chip',
	                  'sterilis', 'utasa'),
	'burial_claim': ('burial', 'mazishi', 'grave', 'kaburi', 'funeral', 'mwili', 'wash the body',
	                 'kunawa mwili', 'body'),
	'denial_claim': ('not real', 'si kweli', 'hoax', 'invented', 'iliundwa', 'fake', 'uongo',
	                 'conspiracy', 'njama', 'money', 'fedha', 'funding'),
}

assert {m.topic for m in MYTHS} == {t for c in MYTH_CATEGORIES for t in c.topics} | {'denial_claim'}, \
	'every drafted topic is either a §6.4 category or the orphan the coverage view reports'
assert {c.slug for c in MYTH_CATEGORIES} == {
	'false_cures', 'transmission', 'vaccine', 'conspiracy', 'stigma', 'burial',
}, 'the six categories §6.4 names'
assert set(MYTH_KEYWORDS) == {m.topic for m in MYTHS}, 'every myth topic is recognisable from its claim'
for _topic in {m.topic for m in MYTHS}:
	assert {m.lang for m in MYTHS if m.topic == _topic} == set(MYTH_LANGS), \
		f'{_topic}: a correction drafted in one language is one half the audience cannot read (§6.2.4)'
assert set(FALLBACK_CORRECTION) == set(MYTH_LANGS), 'the fallback is answered in both languages'
assert FALLBACK_TOPIC not in {m.topic for m in MYTHS}, \
	'the fallback is not a myth, and a library row for it would be a card with nothing on it'


def myth_for(topic: str, lang: str) -> Myth | None:
	"""The myth for a topic in a language, or None when neither the topic nor the language exists.

	None rather than a fallback to English: `correction_text` is what a channel sends, and it needs a
	string in *some* language; a browse list or a card needs the reader's own, and serving English
	under a Swahili heading is the failure `answerable()` exists to name one layer up. The caller
	decides which of the two it needs.
	"""
	return next((m for m in MYTHS if m.topic == topic and m.lang == lang), None)


def myths_in(lang: str) -> list[Myth]:
	"""Every drafted myth in one language, in the corpus's own order."""
	return [m for m in MYTHS if m.lang == lang]


def correction_text(myth: Myth) -> str:
	"""The correction as §6.4 step 5 publishes it: the fact, the authority, one sentence.

	Rendered rather than stored, which is the point of the three fields. The separator is a hyphen
	and not an em dash: §6.2.6 names SMS as a channel §6.4 publishes on, and an em dash is outside
	GSM-7, so it doubles the cost of the message and can arrive as mojibake.
	"""
	return f'{myth.fact} - {myth.source}.' if myth.source else f'{myth.fact}.'


def correction_library() -> dict[str, dict[str, str]]:
	"""`topic -> language -> published correction`, derived from the corpus.

	This is the shape `afya.community.service` served before the corpus had claims, and it is kept
	because §6.4's coverage check and the response clock both read it. Deriving it means the
	correction the protocol publishes is the correction the library shows — the two cannot drift,
	which they could while both were hand-written.
	"""
	out: dict[str, dict[str, str]] = {}
	for myth in MYTHS:
		out.setdefault(myth.topic, {})[myth.lang] = correction_text(myth)
	out[FALLBACK_TOPIC] = dict(FALLBACK_CORRECTION)
	return out


def categories_of(topic: str) -> list[str]:
	"""The §6.4 categories a topic answers. Empty for the orphan, which is a fact `coverage()` reports."""
	return [c.slug for c in MYTH_CATEGORIES if topic in c.topics]


def topic_for_slug(slug: str, lang: str) -> str | None:
	"""The rumour topic a library slug stands for, or None when the slug is not a drafted myth.

	The library keys on a slug and the corpus keys on a topic, and the two are not the same name:
	`myth-salt-water` is the `cure_claim`. A caller that has the one and needs the other looks it up
	rather than deriving it from the string, because a slug is a label a reader sees and a topic is a
	classification, and a naming convention that happens to line them up is one that breaks silently
	the first time a rumour is renamed for a screen.
	"""
	return next((m.topic for m in MYTHS if m.slug == slug and m.lang == lang), None)


def classify(claim: str) -> tuple[str | None, list[str]]:
	"""Which drafted rumour a claim is, and the words that decided it.

	The matched words are returned rather than discarded so the surface can say *why* it recognised a
	claim. A classifier that answered "this is the salt-water rumour" with no evidence is one a reader
	cannot argue with, and arguing with it is the whole point of submitting a claim for verification.

	None when nothing matches — the caller answers with the fallback, which says the claim is under
	verification rather than pretending to have recognised it. That is §6.2.8's honest answer and it
	is better than a wrong correction.
	"""
	assert claim.strip(), 'a claim is needed to classify anything'
	text = claim.lower()
	scored = [
		(topic, [kw for kw in kws if kw in text])
		for topic, kws in MYTH_KEYWORDS.items()
	]
	matched = [(topic, hits) for topic, hits in scored if hits]
	if not matched:
		return None, []
	# Most distinct keywords wins; ties break on the corpus order so the answer is deterministic
	# rather than dependent on dict iteration.
	order = list(MYTH_KEYWORDS)
	matched.sort(key=lambda pair: (-len(pair[1]), order.index(pair[0])))
	return matched[0][0], sorted(matched[0][1])
