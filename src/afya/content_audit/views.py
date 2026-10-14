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


class ClaimContent(BaseModel):
	"""One claim-label passage a section prints, and what carries it.

	`kind` is tri-state for the same reason `ContentBullet.kind` is, with one substitution: the
	claim side's third verdict is `narrative` rather than `missing`. A claim is a sentence *about* a
	feature, so the failure mode is not "nobody built it" but "nobody read it" — and a sentence about
	the world (the adoption argument, the audience, a broadcaster's figures) is neither carried nor
	absent, which is what `narrative` names. `deferred` is the claim the spec itself conditions on
	something this tree does not hold, or a property of the handset or the platform.

	The unit is the passage, not the sentence: `claims` is the passage as the spec prints it and
	`claims_count` is how many sentences a reader will find in it. Nothing is asserted on that
	boundary — a gate over sentence splitting would be a gate over a regex.
	"""

	model_config = MODEL_CONFIG
	feature_id: str
	label: str
	claims: list[str]
	kinds: dict[str, int]


class ClaimContentReport(BaseModel):
	"""The claim side of the same audit, served beside it.

	`unresolved` is the finding that matters here, and it is the same one the content side reports:
	a `carried` claim whose reference does not import is a claim whose carrier rotted. `narrative`
	and `deferred` are reported as counts rather than lists, because a list of thirty-eight sentences
	about adoption would read as thirty-eight gaps — the failure the three verdicts exist to prevent.
	"""

	model_config = MODEL_CONFIG
	sections: list[ClaimContent]
	pairs_read: int
	claims_read: int
	carried: int
	deferred: int
	narrative: int
	unresolved: list[str]


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
