"""Feature content audit models — what a feature section says it does, against what does it."""
from pydantic import BaseModel, ConfigDict

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class ContentBullet(BaseModel):
	"""One labelled bullet under a spec feature section, and what carries it.

	`kind` is tri-state because the bullets are not all the same sort of claim. `carried` names code;
	`deferred` is a bullet the spec itself puts out of scope here (a `(see X)` cross-reference, or a
	clause conditional on something that has not happened); `missing` is a bullet nothing does. Only
	the third is a finding — merging them would report every cross-reference as a gap and bury the
	real ones under it.
	"""

	model_config = MODEL_CONFIG
	label: str
	bullet: str
	kind: str
	carried_by: str | None = None
	resolves: bool = False
	note: str | None = None


class FeatureContent(BaseModel):
	model_config = MODEL_CONFIG
	feature_id: str
	bullets: list[ContentBullet]
	missing: list[str]
	carried_count: int


class FeatureContentReport(BaseModel):
	"""Every audited feature section, with the two findings kept apart, and the coverage stated.

	`missing` is a bullet nothing does. `unresolved` is a bullet whose named carrier does not import
	— a rotted reference, which is a different defect from a capability nobody built. `unaudited_features`
	is what the report did not read, so a list of gaps cannot be mistaken for a complete audit.
	"""

	model_config = MODEL_CONFIG
	features: list[FeatureContent]
	missing: list[str]
	unresolved: list[str]
	audited_features: int
	unaudited_features: list[str]
