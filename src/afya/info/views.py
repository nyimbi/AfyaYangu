"""Information content models (INF-001..010, §6 content strategy, §18.4 hotline)."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class CountyRisk(BaseModel):
	model_config = MODEL_CONFIG
	county: str
	risk_level: str = Field(pattern=r'^(low|moderate|high)$')
	active_signals: int = Field(ge=0)
	bulletin: str


class HotlineInfo(BaseModel):
	model_config = MODEL_CONFIG
	name: str
	number: str
	hours: str
	verified: bool = False


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


class DecisionNode(BaseModel):
	model_config = MODEL_CONFIG
	question: str
	yes_next: str | None
	no_next: str | None
	leaf_recommendation: str | None = None