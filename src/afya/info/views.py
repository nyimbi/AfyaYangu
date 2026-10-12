"""Information content models (INF-001..010, §6 content strategy, §18.4 hotline)."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, computed_field

from afya.info.recency import UNDATED_MS

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class CountyRisk(BaseModel):
	model_config = MODEL_CONFIG
	county: str
	risk_level: str = Field(pattern=r'^(low|moderate|high)$')
	active_signals: int = Field(ge=0)
	bulletin: str
	# §6.2.3 and §8.5's "Last updated timestamp" / "Data source attribution". A dashboard is the
	# surface where an undated figure does the most damage: a county with no signal is answered with
	# a defaulted low-risk row, and with no stamp that row reads as today's assessment.
	updated_at_ms: int = Field(default=UNDATED_MS, ge=0)
	source: str = ''


class ContactKind(str, Enum):
	"""§INF-006's eight Contents as a closed set of contact types.

	The section prints the directory as a list of *kinds* of contact — a hotline, a county office, a
	facility, an ambulance, a CHW, and three helplines — and `HotlineInfo` carried no kind at all,
	so the rows were indistinguishable and the route could not say which of the eight a deployment
	had. The four the tree has no number for (`county_health_office`, `chw`, `gbv_helpline`,
	`child_helpline`) are members here rather than absent, because the *gap* is a fact the report
	has to be able to name; a deployment that later signs a GBV line adds a row, not an enum member.
	"""

	emergency_hotline = 'emergency_hotline'
	mental_health_helpline = 'mental_health_helpline'
	substance_abuse_helpline = 'substance_abuse_helpline'
	ambulance = 'ambulance'
	nearest_facility = 'nearest_facility'
	county_health_office = 'county_health_office'
	chw = 'chw'
	gbv_helpline = 'gbv_helpline'
	child_helpline = 'child_helpline'
	complaints_desk = 'complaints_desk'


# §INF-006's Contents, in the section's own order. Held apart from the enum because two members are
# not the section's: `complaints_desk` is a row the deployment has and the section does not name, and
# `substance_abuse_helpline` is the kind NACADA's number answers under. Completeness is coverage of
# *these eight* — an enum-wide count would report the directory incomplete for holding an extra.
SPEC_CONTENTS: tuple[ContactKind, ...] = (
	ContactKind.emergency_hotline,
	ContactKind.county_health_office,
	ContactKind.nearest_facility,
	ContactKind.ambulance,
	ContactKind.chw,
	ContactKind.mental_health_helpline,
	ContactKind.gbv_helpline,
	ContactKind.child_helpline,
)


class HotlineActions(BaseModel):
	"""§INF-006's four Features, rendered as the URIs a client can act on.

	The section's Features are "One-tap call, one-tap SMS, save to contacts, share", and all four
	were absent: `HotlineInfo` carried the number and the route served it as text, so a directory of
	life-safety numbers was data a client could not act on. This is the same shape `Directions`
	already had — the server renders the deep link and the client opens it, so no platform SDK is
	needed and the four features exist as fields rather than as a client's obligation.

	`vcard` is a vCard 3.0 body rather than a URL, because there is no cross-platform scheme for
	"saving a contact" the way there is for dialling: a client hands the text to the contacts app.
	"""

	model_config = MODEL_CONFIG
	tel_uri: str = Field(pattern=r'^tel:')
	sms_uri: str = Field(pattern=r'^sms:')
	vcard: str = Field(min_length=1)
	share_url: str = Field(pattern=r'^https://wa\.me/')



class HotlineInfo(BaseModel):
	model_config = MODEL_CONFIG
	name: str
	number: str
	hours: str
	verified: bool = False
	# §18.4 and §6.2.3. `verified=False` is an assertion about the number that nobody can act on
	# without knowing when it was last checked, which is why the stamp travels with it.
	verified_at_ms: int = Field(default=UNDATED_MS, ge=0)
	# §INF-006's own list is of contact *kinds*; without this the eight rows the section names are
	# indistinguishable and "which of the eight does this deployment have" is unanswerable.
	kind: ContactKind = ContactKind.emergency_hotline
	# §INF-006's Features, rendered by the service rather than left to each client.
	actions: HotlineActions | None = None
	# §6.2.3's age line for this entry, computed at serve time. A field rather than a key the route
	# bolts on, because `HotlineInfo` is `extra='forbid'` and a `model_copy` update with an undeclared
	# key would add it silently — the directory would then serve one shape and its model describe
	# another. None means never verified, which is a fact to render, not silence to infer from.
	updated_line: str | None = None

	def model_post_init(self, _context: object) -> None:
		assert not self.verified or self.verified_at_ms > UNDATED_MS, (
			f'{self.name}: a number claimed as verified carries the instant it was checked (§6.2.3)'
		)


class ContactDirectory(BaseModel):
	"""§INF-006's directory as a screen: the contacts this deployment has, and the ones it lacks.

	The section asks for "a single screen with all relevant contacts" and prints eight. Serving only
	the rows that exist would answer the question "what is in the directory" while hiding the one a
	reader of the section is actually asking — which of the eight is missing.

	`absent` is *derived* rather than passed in, and that is the point: as a field it was a line the
	service had to remember to compute from `SPEC_CONTENTS`, and a directory that counted the whole
	enum instead would report a deployment incomplete for holding a row the section does not name
	(the ODPC desk) — a wrong answer no type could catch, because both spellings produce a
	`list[ContactKind]`. Deriving it here makes the invariant structural, and a caller can no longer
	hand over a gap list that disagrees with the rows beside it.
	"""

	model_config = MODEL_CONFIG
	contacts: list[HotlineInfo]

	@computed_field
	@property
	def absent(self) -> list[ContactKind]:
		"""The section's Contents no row covers, in the section's own order."""
		present = {row.kind for row in self.contacts}
		return [k for k in SPEC_CONTENTS if k not in present]

	@computed_field
	@property
	def complete(self) -> bool:
		"""Whether the screen carries every Content §INF-006 prints.

		Coverage only — the four Features are a property of each row and are read off the row, where
		`actions is None` says "listed, but there is nothing to dial". Folding that into `complete`
		would make a deployment that honestly lists a facility OSM gave no number for report its whole
		directory as incomplete, which conflates a missing contact with an unlisted number.
		"""
		return not self.absent




class ContentStage(str, Enum):
	"""§6.5 localisation workflow, as an order. An item advances through these; only `published`
	is ever served, and `archived` is terminal — retirement keeps the item for audit rather than
	deleting it."""

	draft = 'draft'
	clinical_review = 'clinical_review'
	translation = 'translation'
	back_translation = 'back_translation'
	community_validation = 'community_validation'
	published = 'published'
	archived = 'archived'


# §6.5: "English draft → clinical review → translation → back-translation → community validation
# → publish". The order is the rule; `advance` walks it one step at a time so a draft cannot jump
# to published, which is what would let unreviewed clinical content reach a screen.
WORKFLOW: tuple[ContentStage, ...] = (
	ContentStage.draft,
	ContentStage.clinical_review,
	ContentStage.translation,
	ContentStage.back_translation,
	ContentStage.community_validation,
	ContentStage.published,
)


class ContentFormat(str, Enum):
	"""The delivery formats §8.5 and §10.5 print, closed.

	§INF-003 asks for "Short articles (under 200 words), illustrations, audio versions, video
	versions" and §INF-008 for "Short cards, 30-second videos, audio clips" — seven formats across
	two sections, and nothing carried any of them. A corpus item is text, so a library with nine
	articles and no audio satisfies "Ebola Information Library" while serving none of the audience
	§3.3 principle 8 puts first, and no reader of the corpus could tell. The set is closed for the
	same reason `TestType` is: an open string is a value nothing can report the absence of.
	"""

	article = 'article'
	card = 'card'
	illustration = 'illustration'
	audio = 'audio'
	video = 'video'

	@property
	def is_text(self) -> bool:
		"""Whether the format is delivered as prose the item's own `body` carries.

		An article and a short card are both text — the card is shorter, not a different medium — so
		they are the two that need no `media_ref`. An illustration, an audio version and a video
		version are renditions of the text, and each is a file somewhere that the item must point at,
		because "we made an audio version" with nothing to play is the claim §6.2.3 exists to stop one
		field over.
		"""
		return self in (ContentFormat.article, ContentFormat.card)


class ContentItem(BaseModel):
	"""One library item, carrying the governance §6.5 requires of everything published.

	`owner`, `reviewer`, `reviewed_on_iso` and `version` have no defaults. §6.5 says every content
	item has all four; an item that could be constructed without them would be one that is served
	while nobody is accountable for it, which is the failure the section names. A missing field is
	a ValidationError at construction, not a blank cell in a table a reader has to notice.
	"""

	model_config = MODEL_CONFIG
	item_id: str
	title: str
	body: str
	lang: str = Field(pattern=r'^(en|sw|sheng)$')
	harmony_tag: str | None = None  # verified/official-source tag per §6.2
	# A stable, code-free handle. The seed ids embed spec codes (`INF-003-en`); this is what a client
	# keys on and what may reach a screen, so the code stays internal like every other spec id.
	slug: str = ''
	owner: str = Field(min_length=1, description='the unit accountable for this item (§6.5)')
	reviewer: str = Field(min_length=1, description='who clinically reviewed it (§6.5)')
	reviewed_on_iso: str = Field(min_length=10, description='date of the last clinical review')
	version: int = Field(ge=1)
	stage: ContentStage = ContentStage.draft
	# Which §6.1 question this item answers, by the section's own rank. §6.2.4's "never publish
	# English-only for a life-safety message" has no jurisdiction without it: nothing said which
	# items *are* life-safety, so the rule could not bite. The rank is a reference into §6.1's table
	# rather than a boolean an author sets, because the person drafting under time pressure is the
	# last one to mark their own copy as life-safety.
	answers_rank: int | None = Field(default=None, ge=1, le=10)
	# §8.5's and §10.5's Format cells. `article` is the default because every item in the corpus is
	# text and an author writing one should not have to say so; the other four are what the sections
	# ask for *beyond* text, and a format nothing carries is the finding.
	format: ContentFormat = ContentFormat.article
	# Where the non-text rendition lives. A format with no `media_ref` is a claim to have produced an
	# audio version with nothing to play, which is the shape §6.2.3's "timestamp everything" exists to
	# stop one field over.
	media_ref: str | None = None
	# The slug of the text item this is a rendition of. A rendition is not an article: it has no prose
	# of its own, so serving it in the library would put a blank card in front of a reader, and
	# without the link there is nothing to serve *instead* — the reader would get the audio version as
	# a separate entry rather than the article with an audio version beside it. Named rather than
	# derived from the slug, because `f'{parent}-{fmt.value}'` is a convention and a parent whose slug
	# happens to end in a format word would silently point at the wrong item.
	rendition_of: str | None = None

	def model_post_init(self, _context: object) -> None:
		assert self.format.is_text == (self.media_ref is None), (
			f'{self.item_id}: a text item needs no media reference and a rendition without one is a '
			'format that cannot be served'
		)
		assert self.format.is_text == (self.rendition_of is None), (
			f'{self.item_id}: a rendition names the item it is a rendition of, and a text item is not '
			'one — a non-text item with no parent is a blank entry in the library'
		)
	# §6.2.3 "Timestamp everything." When the item was last written or moved, as an instant. It has
	# a default because the *service* stamps it — on write, on advance and at seed — and
	# `upsert_content` overwrites whatever it is handed rather than keeping it. `UNDATED_MS` is the
	# sentinel for "no time recorded", and `library()` withholds an item carrying it rather than
	# serving the undated content §6.2.3 calls destructive. The *sentence* a reader sees is not a
	# field at all: it is computed at serve time, because a stored "2 hours ago" is wrong an hour
	# later.
	updated_at_ms: int = Field(default=UNDATED_MS, ge=0)


class DecisionNode(BaseModel):
	model_config = MODEL_CONFIG
	question: str
	yes_next: str | None
	no_next: str | None
	leaf_recommendation: str | None = None


class EntryAnswer(BaseModel):
	"""One thing a person can open with, and the screen it opens.

	§INF-002 prints six entry questions — "I have a fever", "Someone in my house is sick", "I'm
	worried about travel", "I want to protect my family", "I heard something — is it true?", "I need
	to go to hospital" — and the tree's root asked "Do you have fever (38.0 °C)?". Those are not the
	same question. The section's first entry is a statement of fact by someone who has already
	decided they are unwell; the root asks them to measure a temperature first, which is a step the
	person who came to the screen does not have and should not need. A tree whose only door is a
	numeric reading is a tree most of its audience cannot enter.

	`kind` says what the client does with `href`, so nothing parses the label: `tree` is a path into
	the walk, `screen` is another API path the app already has, and `call` is a device scheme. The
	six entries are deliberately *not* six tree roots — three of them are questions this tree cannot
	ask ("is it true?" is §6.4's myth library, not a symptom walk) and pretending otherwise would be
	a branch that lies about what it classifies. What the section asks for is that the six open
	something specific, which is what `href` is.

	`asks_for` names the inputs the destination needs before it can answer — a travel advisory wants
	where you are going, a facility search wants where you are. It is a list rather than a claim that
	the screen needs nothing, because the alternative is a client that opens the entry and gets a
	422, which is a door that does not open.
	"""

	model_config = MODEL_CONFIG
	question: str = Field(min_length=1)
	kind: str = Field(pattern=r'^(tree|screen|call)$')
	href: str = Field(min_length=1)
	# The one-line answer the entry leads to, so a client can render the six as a menu with their
	# outcomes visible rather than as six identical buttons.
	leads_to: str = Field(min_length=1)
	asks_for: list[str] = []


class InfoLink(BaseModel):
	"""One destination §INF-002's Output attaches to a leaf, as something a client can dispatch.

	The section's Output is "Specific, actionable guidance with facility and hotline links". The
	first half is a property of the sentence and §6.2 judges it; the second half is not, because a
	sentence cannot be tapped. `kind` says what the device does with `href` so no client parses the
	label — the same contract `TriageAction` and `CareAction` keep.

	The facility link is a *search*, not a facility id: a leaf does not know where the reader is, so
	a recommendation naming a fixed clinic is wrong for everyone not standing beside it.
	"""

	model_config = MODEL_CONFIG
	kind: str = Field(pattern=r'^(call|find_facility)$')
	label: str = Field(min_length=1)
	href: str = Field(min_length=1)


class DecisionStep(BaseModel):
	"""One step of the walk, as a validated shape rather than keys a client guesses.

	`question` is the next thing to ask and is None at a leaf; `done` says which of the two a client
	is looking at, so it does not have to infer it from a null. `links` is empty until the leaf,
	because a question with a facility button under it offers the reader a way to leave before they
	have answered.
	"""

	model_config = MODEL_CONFIG
	question: str | None
	done: bool
	recommendation: str | None
	links: list[InfoLink] = []