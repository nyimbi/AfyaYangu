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