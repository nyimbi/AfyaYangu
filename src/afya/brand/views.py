"""§3's vision, positioning, design principles and non-goals (spec §3.1–§3.4)."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class Principle(BaseModel):
	"""One §3.3 row: the number the section gives it, the principle, and the implication.

	Both columns are carried because the section is written as a pair: the principle is the value and
	the implication is what it costs to hold it. "Zero-rated or it doesn't count" is a value;
	"every channel must be zero-rated or free-at-point-of-use" is the constraint a build has to meet.
	A table of the first column alone is a poster.
	"""

	model_config = MODEL_CONFIG
	number: int = Field(ge=1, le=12)
	principle: str = Field(min_length=1)
	implication: str = Field(min_length=1)


class NonGoal(str, Enum):
	"""§3.4's five prohibitions. An enum rather than a list because each one is a boundary a feature
	can cross by accident — a "premium" flag, a follower count, a diagnosis string — and a boundary
	that is only prose is one nothing refuses."""

	clinical_replacement = 'Not a replacement for clinical care, laboratory confirmation, or official case definitions'
	diagnostic_device = 'Not a diagnostic device; all outputs are triage guidance, not diagnosis'
	surveillance_tool = 'Not a government surveillance tool; all data sharing is consented and minimised'
	paid_product = 'Not a paid product; no premium tier, no advertising, no data monetisation'
	social_network = 'Not a social network; no public posting, no follower graph'


class Brand(BaseModel):
	"""§3.2's identity: the public name, the programme name, the positioning statement, and the
	disclaimer the section writes as a warning — "It is not 'the Ebola app.' … The brand must survive
	the outbreak's end.\""""

	model_config = MODEL_CONFIG
	public_name: str = Field(min_length=1)
	public_name_english: str = Field(min_length=1)
	programme_name: str = Field(min_length=1)
	programme_name_english: str = Field(min_length=1)
	positioning: str = Field(min_length=1)
	not_the_ebola_app: str = Field(min_length=1)
