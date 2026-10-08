"""Information content models (INF-001..010, §6 content strategy, §18.4 hotline)."""
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


class ContentItem(BaseModel):
	model_config = MODEL_CONFIG
	item_id: str
	title: str
	body: str
	lang: str = Field(pattern=r'^(en|sw|sheng)$')
	harmony_tag: str | None = None  # verified/official-source tag per §6.2


class DecisionNode(BaseModel):
	model_config = MODEL_CONFIG
	question: str
	yes_next: str | None
	no_next: str | None
	leaf_recommendation: str | None = None