"""§10.5's three features: the topics each names, the formats, and what the corpus actually covers.

§10.5 is "Information (Extended)" — INF-008 Health Tips and Education, INF-009 First Aid Guide,
INF-010 Safe and Dignified Burial Guidance. All three are in the registry (`FeatureSpec`), all three
have seed items in `content_seed`, and all three are accounted for in the coverage gate as "items in
the health library corpus". What none of that carries is the *topic list*: §INF-008 names eight
subjects it rotates through, §INF-009 names eleven injuries it covers, and §INF-010 names six things
its content must say. Those are the section's own inventory of what these features are, and nothing
read them.

**Why the topic list is the load-bearing part.** "Health Tips and Education" is not one item — the
section says "Rotating, seasonal, locally relevant health education" and then names the rotation:
hygiene, nutrition, mental health, first aid, child development, chronic disease management, injury
prevention, sexual and reproductive health. A corpus with one handwashing tip satisfies the feature
id and serves one eighth of what the feature is. The same is true of §INF-009: a first-aid guide
with a choking item and no bleeding item is a guide with a hole in it, and "Fully offline. One of the
most valuable offline resources possible" is the section's own estimate of what that hole costs.
So `coverage()` reports which named topics the corpus has an item for, and which it does not.

**The coverage is reported, not enforced.** A deployment that has not yet received the MoH's corpus
for snakebite is not broken, and refusing to serve the bleeding item because snakebite is missing
would trade the content that exists for the content that does not. `content_seed` says the same thing
in its own docstring — it is "a stand-in for the MoH corpus". The finding is the list of gaps, which
is what a content owner needs and what nothing produced.

**§INF-010 is the one row with a `Sensitivity` clause**, and it is the clause a build is most likely
to drop: "Developed with religious leaders, community elders, and anthropologists. Available in all
relevant languages. Emphasises dignity, not just safety." The last sentence is a content rule, not a
process note — burial guidance that reads as safety instructions with no dignity in them fails the
section even when it is clinically correct, and `content_seed`'s own burial item is written to it
("dignity is preserved"). `SENSITIVITY_REVIEWERS` carries the three parties as data so the
requirement is one a governance view can check rather than a sentence in a spec.
"""
from afya.info.views import ContentItem

# §INF-008's Topics cell, verbatim and in the section's order. Eight subjects the rotation runs
# through; a corpus with one of them serves one eighth of the feature.
HEALTH_TIP_TOPICS: tuple[str, ...] = (
	'Hygiene', 'nutrition', 'mental health', 'first aid', 'child development',
	'chronic disease management', 'injury prevention', 'sexual and reproductive health',
)

# §INF-009's Topics cell, verbatim and in order. Eleven injuries, and the order is the section's.
FIRST_AID_TOPICS: tuple[str, ...] = (
	'Bleeding', 'burns', 'choking', 'drowning', 'fractures', 'poisoning', 'snakebite', 'seizure',
	'unconsciousness', 'CPR', 'shock',
)

# §INF-010's Content list, verbatim. Six things the guidance must say — the fourth and fifth are the
# ones a safety-only reading drops, and the sixth is the question a family asks when it cannot
# perform the burial itself.
BURIAL_CONTENT: tuple[str, ...] = (
	'Why safe burial matters for Ebola',
	'How to conduct a safe and dignified burial',
	'Who to contact (burial team)',
	'Cultural and religious considerations',
	'Support for grieving families',
	'What happens if the family cannot conduct the burial themselves',
)

# §INF-008's Format cell, verbatim: "Short cards, 30-second videos, audio clips."
HEALTH_TIP_FORMATS: tuple[str, ...] = ('Short cards', '30-second videos', 'audio clips')

# §INF-010's Sensitivity clause, the three parties the section names as having developed it. Carried
# as data because "developed with religious leaders, community elders, and anthropologists" is a
# requirement on the process that produced the content, and a process note is one nothing checks.
SENSITIVITY_REVIEWERS: tuple[str, ...] = ('religious leaders', 'community elders', 'anthropologists')

# The corpus tag each feature's items carry in `content_seed`. INF-008 and INF-009 are tagged `tips`
# and `first-aid`; §INF-010's items carry `burial`. The tag is what makes coverage computable against
# the corpus rather than against a claim about it.
FEATURE_TAG: dict[str, str] = {'INF-008': 'tips', 'INF-009': 'first-aid', 'INF-010': 'burial'}

# §10.5 is three features and each is its own subsection. The order is the section's.
SPEC_FEATURES: tuple[str, ...] = ('INF-008', 'INF-009', 'INF-010')

assert len(HEALTH_TIP_TOPICS) == 8, '§INF-008 names eight topics'
assert len(FIRST_AID_TOPICS) == 11, '§INF-009 names eleven topics'
assert len(BURIAL_CONTENT) == 6, '§INF-010 lists six content points'
assert len(SENSITIVITY_REVIEWERS) == 3, '§INF-010 names three parties'
assert set(FEATURE_TAG) == set(SPEC_FEATURES), 'every §10.5 feature carries a corpus tag'

# The words that carry no topic on their own. `health` appears in "Daily health tips" and would make
# every *-health topic covered by any health item; `prevention` appears in the seed's Ebola-prevention
# slug and would make "injury prevention" covered by it; `management` is the tail of "chronic disease
# management". The first version of this matched any keyword, and the handwashing tip reported as
# covering mental health, injury prevention and reproductive health — a check scoped wider than its
# jurisdiction, which is the failure that makes a gate's real findings get ignored.
_GENERIC = frozenset({
	'and', 'of', 'the', 'health', 'management', 'prevention', 'considerations',
})


def _keywords(topic: str) -> tuple[str, ...]:
	"""The words that must appear for an item to cover `topic`.

	A multi-word topic is matched on its distinctive word rather than the whole phrase: "chronic
	disease management" is covered by an item about chronic disease, and requiring the literal string
	would make coverage depend on phrasing the spec does not fix. Generic words are dropped for the
	same reason — "sexual and reproductive health" is about sexual or reproductive health, and
	"Cultural and religious considerations" about culture or religion.
	"""
	words = [w.strip('(),.').lower() for w in topic.replace('-', ' ').split()]
	meaningful = [w for w in words if w and w not in _GENERIC]
	return tuple(meaningful) or (topic.lower(),)


def covers(item: ContentItem, topic: str) -> bool:
	"""Whether a corpus item is about `topic`, read off the item's own words.

	**This errs toward under-reporting coverage, deliberately.** The seed's handwashing tip is hygiene
	and does not contain the word "hygiene", so it reports as a gap; the burial item preserves dignity
	without saying "cultural" or "religious", so those report as gaps too. The check is literal because
	the alternative — a synonym table — is this module inventing the vocabulary the spec would have
	used, and a false "covered" is the failure that hides a hole: it says a content owner has nothing
	to do. A false gap costs someone one question. The docstring says which way the error runs so the
	report is read as what it is rather than as a claim the corpus is short.
	"""
	haystack = f'{item.title} {item.body} {item.slug}'.lower()
	return any(kw in haystack for kw in _keywords(topic))


def coverage(items: list[ContentItem], feature_id: str, topics: tuple[str, ...]) -> dict[str, object]:
	"""Which of a feature's named topics the corpus has an item for, and which it does not.

	`covered` and `gaps` are both reported. A feature whose corpus is missing four of eleven first-aid
	topics is not a feature that is broken — it is one a content owner needs to know about, and the
	alternative (a boolean "has items") is the shape that made this invisible: `test_feature_coverage`
	accounts for INF-009 as "first-aid items are in the health library corpus", which is true of one
	item and says nothing about the other ten.
	"""
	assert feature_id in FEATURE_TAG, f'{feature_id} is not a §10.5 feature'
	tag = FEATURE_TAG[feature_id]
	tagged = [i for i in items if i.harmony_tag == tag]
	covered = [t for t in topics if any(covers(i, t) for i in tagged)]
	gaps = [t for t in topics if t not in covered]
	return {
		'feature_id': feature_id,
		'items': len(tagged),
		'topics': len(topics),
		'covered': covered,
		'gaps': gaps,
	}


def report(items: list[ContentItem]) -> list[dict[str, object]]:
	"""§10.5's three features, each against the corpus. The gaps are the finding."""
	return [
		coverage(items, 'INF-008', HEALTH_TIP_TOPICS),
		coverage(items, 'INF-009', FIRST_AID_TOPICS),
		coverage(items, 'INF-010', BURIAL_CONTENT),
	]


def first_aid_is_offline() -> str:
	"""§INF-009's Offline cell, verbatim. It is the section's own estimate of what this feature is
	worth — "One of the most valuable offline resources possible" — and it is the reason a first-aid
	item is in the base install rather than fetched, which is a delivery decision §16.5's table reads.
	"""
	return 'Fully offline. One of the most valuable offline resources possible.'
