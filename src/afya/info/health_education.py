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
from afya.info.views import ContentFormat, ContentItem

# §INF-003's Topics list, verbatim and in the section's order. Nine subjects, and the section's
# Format cell adds "under 200 words" — a constraint on the articles rather than on the topics, which
# is why `ARTICLE_MAX_WORDS` is checked against the corpus and not against this tuple.
EBOLA_TOPICS: tuple[str, ...] = (
	'What Ebola is and how it spreads',
	'Symptoms and when they appear',
	'How to protect yourself and your family',
	"What to do if you think you've been exposed",
	'Testing and treatment',
	'Safe and dignified burial (see INF-010)',
	'Stigma and how to fight it',
	'What happens at an isolation facility',
	'Recovery and survivors',
)

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

# §INF-003's Format cell, verbatim: "Short articles (under 200 words), illustrations, audio versions,
# video versions." Four formats, and the first carries the section's own length limit — which is why
# it is a number here rather than a phrase, so a corpus item can be checked against it.
EBOLA_FORMATS: tuple[str, ...] = (
	'Short articles (under 200 words)', 'illustrations', 'audio versions', 'video versions',
)
ARTICLE_MAX_WORDS = 200

# §INF-010's Sensitivity clause, the three parties the section names as having developed it. Carried
# as data because "developed with religious leaders, community elders, and anthropologists" is a
# requirement on the process that produced the content, and a process note is one nothing checks.
SENSITIVITY_REVIEWERS: tuple[str, ...] = ('religious leaders', 'community elders', 'anthropologists')

# The corpus tag each feature's items carry in `content_seed`. INF-003 is `ebola-library`, INF-008
# and INF-009 are tagged `tips` and `first-aid`, and §INF-010's items carry `burial`. The tag is what
# makes coverage computable against the corpus rather than against a claim about it.
FEATURE_TAG: dict[str, str] = {
	'INF-003': 'ebola-library', 'INF-008': 'tips', 'INF-009': 'first-aid', 'INF-010': 'burial',
}

# Each feature's own topics, so `coverage` can be driven from one table rather than from four call
# sites that could each pass the wrong list. §INF-003 is in here because it is the same shape: nine
# topics the section prints, a corpus that answers some of them, and no reader of the difference.
FEATURE_TOPICS: dict[str, tuple[str, ...]] = {
	'INF-003': EBOLA_TOPICS, 'INF-008': HEALTH_TIP_TOPICS, 'INF-009': FIRST_AID_TOPICS,
	'INF-010': BURIAL_CONTENT,
}

# Each feature's Format cell, and the item kind that satisfies each format. §INF-003 prints four and
# §INF-008 three, and none of the seven was a field: a corpus item is text, so "audio versions" and
# "30-second videos" were formats the spec asks for and nothing could report the absence of. The
# value is the `ContentFormat` member a corpus item carries to satisfy that format.
FEATURE_FORMATS: dict[str, tuple[tuple[str, str], ...]] = {
	'INF-003': (
		('Short articles (under 200 words)', 'article'), ('illustrations', 'illustration'),
		('audio versions', 'audio'), ('video versions', 'video'),
	),
	'INF-008': (
		('Short cards', 'card'), ('30-second videos', 'video'), ('audio clips', 'audio'),
	),
}

# §10.5 is three features and each is its own subsection; §INF-003 is §8.5's library and has the same
# shape. The order is the spec's — §8.5 before §10.5.
SPEC_FEATURES: tuple[str, ...] = ('INF-003', 'INF-008', 'INF-009', 'INF-010')

assert len(EBOLA_TOPICS) == 9, '§INF-003 names nine topics'
assert len(HEALTH_TIP_TOPICS) == 8, '§INF-008 names eight topics'
assert len(FIRST_AID_TOPICS) == 11, '§INF-009 names eleven topics'
assert len(BURIAL_CONTENT) == 6, '§INF-010 lists six content points'
assert len(SENSITIVITY_REVIEWERS) == 3, '§INF-010 names three parties'
assert set(FEATURE_TAG) == set(FEATURE_TOPICS) == set(SPEC_FEATURES), \
	'every feature here carries a corpus tag and a topic list'
assert len(EBOLA_FORMATS) == 4 and len(HEALTH_TIP_FORMATS) == 3, 'the two Format cells as printed'
assert {f for f, _ in FEATURE_FORMATS['INF-003']} == set(EBOLA_FORMATS), \
	"§INF-003's format table is the section's own four, spelled the same way"
assert {f for f, _ in FEATURE_FORMATS['INF-008']} == set(HEALTH_TIP_FORMATS), \
	"§INF-008's format table is the section's own three"
assert set(FEATURE_FORMATS) <= set(SPEC_FEATURES), 'a format table for a feature not in the spec'

# The words that carry no topic on their own. Three kinds, and the third is the one that made this
# check fail open.
#
# * **Subject words too broad to be a subject**: `health` appears in "Daily health tips" and would
#   make every *-health topic covered by any health item; `prevention` appears in the seed's
#   Ebola-prevention slug and would make "injury prevention" covered by it; `management` is the tail
#   of "chronic disease management". The first version of this matched any keyword and the
#   handwashing tip reported as covering mental health, injury prevention and reproductive health.
# * **Function words**: `what`, `how`, `is`, `it`, `to`, `for`, `if`, `an`, `a`. These are the
#   fail-open half, and they are worse than the broad ones because they match *everything*. The
#   spec's topics are written as questions — "What Ebola is and how it spreads", "What happens at an
#   isolation facility", "Support for grieving families" — so a keyword list built from the topic's
#   own words contains `for` and `it`, and `any(kw in haystack)` then reports every topic covered by
#   any English sentence containing them. The burial item covered "Support for grieving families" by
#   containing the word "for", and an Ebola item covered "Stigma and how to fight it" by containing
#   the word "it". A predicate that is a strict subset of what it tests fails toward "clean", which
#   is the direction that hides a hole: it tells a content owner there is nothing to do.
# * **Words the section uses as connectives**: `considerations` in "Cultural and religious
#   considerations", which is the tail of the phrase rather than its subject.
_GENERIC = frozenset({
	'and', 'of', 'the', 'health', 'management', 'prevention', 'considerations',
	'a', 'an', 'at', 'be', 'been', 'by', 'do', 'does', 'for', 'from', 'how', 'if', 'in', 'is',
	'it', 'its', 'on', 'or', 'that', 'this', 'to', 'was', 'what', 'when', 'where', 'who', 'why',
	'you', 'your', 'themselves', 'they', 'them', 'there', 'think', 'conduct',
	# The residue of a contraction split on its apostrophe: "you've" is `you` (generic) plus `ve`,
	# and the half that survives the split carries no meaning on its own.
	've', 'll', 're', 's',
})


def _stem(word: str) -> str:
	"""A crude English stem, enough to match "burns" against "burn" and "drowning" against "drown".

	Not a stemming library: the corpus is short prose and the vocabulary is the spec's, so the only
	inflections that matter are the plural and the participle. A real stemmer would also collapse
	words that are different subjects, which is the direction that hides a gap.
	"""
	for suffix in ('ing', 'es', 's'):
		if word.endswith(suffix) and len(word) - len(suffix) >= 4:
			return word[: -len(suffix)]
	return word


def _topic_words(topic: str) -> tuple[str, ...]:
	"""The stemmed words of `topic` after the generic ones are dropped. No distinctiveness yet.

	The cross-reference parenthetical is dropped first: "Safe and dignified burial (see INF-010)" is
	the burial topic with a pointer to the section that owns it, and `010` and `inf` are words no
	corpus item will contain — a topic made unmatchable by its own cross-reference would report as a
	permanent gap. It is dropped rather than the whole phrase being special-cased so any parenthetical
	the spec adds later is handled the same way.
	"""
	head = topic.split('(')[0] if '(' in topic else topic
	# The apostrophe is a word separator: "you've" is the two words the contraction is short for, and
	# leaving it attached makes a topic matchable only by an item that writes the same contraction.
	words = [w.strip("(),.'").lower() for w in head.replace("'", ' ').replace('-', ' ').split()]
	return tuple(_stem(w) for w in words if w and w not in _GENERIC) or (_stem(head.lower()),)


def _keywords(topic: str, siblings: tuple[str, ...] = ()) -> tuple[str, ...]:
	"""The words of `topic` that a corpus item must share to cover it.

	A multi-word topic is matched on its distinctive words rather than the whole phrase: "chronic
	disease management" is covered by an item about chronic disease, and requiring the literal string
	would make coverage depend on phrasing the spec does not fix. The function words are dropped by
	`_GENERIC`, which is what stops a question-shaped topic matching on the words it is phrased with.

	`siblings` is the feature's own other topics, and a word appearing in more than one of them is
	dropped: it names the *feature* rather than the topic. §INF-010's six topics all say "burial" and
	two say "family", so without this any burial item covers all six — the seed's one item reported
	"what happens if the family cannot conduct the burial themselves" as covered on the word "burial"
	alone, which is the over-report that makes the gaps list read as shorter than it is. The fallback
	keeps a topic whose every word is a sibling word (none is) from becoming unmatchable.
	"""
	words = _topic_words(topic)
	if siblings:
		shared: set[str] = set()
		for other in siblings:
			if other != topic:
				shared |= set(_topic_words(other))
		distinctive = tuple(w for w in words if w not in shared)
		return distinctive or words
	return words


# Topics whose keyword list is a word too broad to stand alone. The generic list is a blocklist and
# it cannot know that "aid" means "first aid" in one topic and "aid worker" in another, so the two
# that need it are named here with the phrase that has to appear instead. This is the same finding
# as the function words, one scale down: a keyword that matches the wrong subject reports coverage
# the corpus does not have, and a false "covered" is the failure that hides the hole.
_TOPIC_PHRASES: dict[str, tuple[str, ...]] = {
	'first aid': ('first aid',),
	"what to do if you think you've been exposed": ('exposed',),
	'what happens at an isolation facility': ('isolation',),
	'what happens if the family cannot conduct the burial themselves': ('family cannot', 'cannot conduct'),
	'why safe burial matters for ebola': ('ebola',),
}


def covers(item: ContentItem, topic: str, siblings: tuple[str, ...] = ()) -> bool:
	"""Whether a corpus item is about `topic`, read off the item's own words.

	**This errs toward under-reporting coverage, deliberately.** The check is literal because the
	alternative — a synonym table — is this module inventing the vocabulary the spec would have used,
	and a false "covered" is the failure that hides a hole: it says a content owner has nothing to do.
	A false gap costs someone one question. The docstring says which way the error runs so the report
	is read as what it is rather than as a claim the corpus is short.

	Matching is on whole words rather than substrings, and on stems rather than exact forms. Both are
	corrections to a check that failed open: `'for' in haystack` is true of nearly every English
	sentence, so the burial item covered "Support for grieving families" by containing the word "for",
	and an Ebola item covered "Stigma and how to fight it" by containing "it". A predicate that is a
	strict subset of what it tests reports clean forever, and clean is the answer that hides the hole.
	"""
	text = f'{item.title} {item.body} {item.slug}'.lower()
	phrases = _TOPIC_PHRASES.get(topic.lower())
	if phrases is not None:
		return any(p in text for p in phrases)
	words = {_stem(w.strip('.,;:()')) for w in text.split()}
	return any(kw in words for kw in _keywords(topic, siblings))


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
	covered = [t for t in topics if any(covers(i, t, topics) for i in tagged)]
	gaps = [t for t in topics if t not in covered]
	return {
		'feature_id': feature_id,
		'items': len(tagged),
		'topics': len(topics),
		'covered': covered,
		'gaps': gaps,
	}


def format_coverage(items: list[ContentItem], feature_id: str) -> dict[str, object]:
	"""Which of a feature's printed formats the corpus actually delivers, and which it does not.

	The same finding as `coverage`, one dimension over: §INF-003 asks for audio and video versions
	and a corpus of articles answers neither, which is invisible while "the Ebola library has items"
	is the check. A format counts as delivered only when an item of that format carries a
	`media_ref` — the model refuses to construct one without it, so the count here is over renditions
	that can be served rather than over claims to have made them.
	"""
	assert feature_id in FEATURE_FORMATS, f'{feature_id} prints no format cell'
	table = FEATURE_FORMATS[feature_id]
	tagged = [i for i in items if i.harmony_tag == FEATURE_TAG[feature_id]]
	delivered = [
		label for label, fmt in table
		if any(i.format.value == fmt for i in tagged)
	]
	missing = [label for label, _ in table if label not in delivered]
	return {
		'feature_id': feature_id,
		'formats': len(table),
		'delivered': delivered,
		'missing_formats': missing,
	}


def over_length(items: list[ContentItem]) -> list[str]:
	"""§INF-003's own length limit: "Short articles (under 200 words)".

	The section prints the limit inside the Format cell, so it is a requirement on the corpus rather
	than on the format's name. Named by slug, and reported rather than enforced: an article at 210
	words is not a defect a serving route should refuse over, and a reader who can see the number can
	decide whether to cut it.
	"""
	return sorted(
		i.slug or i.item_id for i in items
		if i.format is ContentFormat.article and len(i.body.split()) > ARTICLE_MAX_WORDS
	)


# §INF-009's Description, verbatim: "Offline first-aid instructions with illustrations." The
# illustration is asked for in the *Description* rather than in a Format cell, so the section has no
# format table, `FEATURE_FORMATS` has no entry for it, and the audit has no row for a Description —
# which is precisely why it needs its own check. A requirement stated in prose is the one nothing
# reads, and the eleven topics this section names are the ones it is stated over.
FIRST_AID_DESCRIPTION = 'Offline first-aid instructions with illustrations.'


def illustrated(items: list[ContentItem]) -> dict[str, object]:
	"""Which of §INF-009's topics have an illustration behind them, and which do not.

	The same finding as `format_coverage`, from a label the format tables cannot see. `illustration`
	is a rendition, so the model refuses one without a `media_ref` and an illustration here is a file
	rather than a claim to have drawn one. Coverage is per *topic* rather than per item because the
	section's requirement is that the guide is illustrated, and a guide with one illustration and ten
	bare topics is not.
	"""
	tagged = [i for i in items if i.harmony_tag == FEATURE_TAG['INF-009']]
	illustrations = [i for i in tagged if i.format is ContentFormat.illustration]
	return {
		'feature_id': 'INF-009',
		'topics': len(FIRST_AID_TOPICS),
		'illustrations': len(illustrations),
		'covered': [t for t in FIRST_AID_TOPICS if any(covers(i, t, FIRST_AID_TOPICS) for i in illustrations)],
		'gaps': [
			t for t in FIRST_AID_TOPICS
			if not any(covers(i, t, FIRST_AID_TOPICS) for i in illustrations)
		],
	}


def report(items: list[ContentItem]) -> list[dict[str, object]]:
	"""§8.5's and §10.5's four features, each against the corpus. The gaps are the finding.

	One row per feature, and each row carries both dimensions where the section prints both: the
	topics it names and the formats it asks for. §INF-009 and §INF-010 print no Format cell, so they
	have topics only — a format row for a section that names none would be this module inventing a
	requirement.
	"""
	rows: list[dict[str, object]] = []
	for feature_id in SPEC_FEATURES:
		row = coverage(items, feature_id, FEATURE_TOPICS[feature_id])
		if feature_id in FEATURE_FORMATS:
			row.update(format_coverage(items, feature_id))
		if feature_id == 'INF-009':
			# §INF-009 asks for illustrations in its Description rather than in a Format cell, so it is
			# the one feature whose second dimension is not in `FEATURE_FORMATS` and would otherwise go
			# unmeasured — a requirement stated in prose being the one nothing reads.
			row['illustrations'] = illustrated(items)
		rows.append(row)
	return rows


def first_aid_is_offline() -> str:
	"""§INF-009's Offline cell, verbatim. It is the section's own estimate of what this feature is
	worth — "One of the most valuable offline resources possible" — and it is the reason a first-aid
	item is in the base install rather than fetched, which is a delivery decision §16.5's table reads.
	"""
	return 'Fully offline. One of the most valuable offline resources possible.'
