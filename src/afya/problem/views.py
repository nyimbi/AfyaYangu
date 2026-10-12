"""§2's problem statement as data — seven citizen-layer gaps and five conditioned lessons
(spec §2.2, §2.3)."""
from pydantic import BaseModel, ConfigDict

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class CitizenGap(BaseModel):
	"""One §2.2 row: the gap in the citizen layer, its consequence, and what closes it.

	§2.2 is the argument for the whole product — seven things the health-system layer does not do
	and a citizen-facing app must. `closed_by` is a `module:attr` reference, or None where the build
	has nothing, which is a finding rather than a rounding error: a product whose problem statement
	names seven gaps and closes six has a claim it cannot support, and the section is the first place
	a reader looks to decide whether the app is worth building.
	"""

	model_config = MODEL_CONFIG
	gap: str
	consequence: str
	closed_by: str | None = None
	resolves: bool = False
	note: str | None = None


class GapReport(BaseModel):
	model_config = MODEL_CONFIG
	gaps: list[CitizenGap]
	unclosed: list[str]
	closed_count: int


class Lesson(BaseModel):
	"""One §2.3 paragraph: the system, the lesson it yields, and the *condition* the lesson carries.

	Every one of §2.3's five lessons is written as a claim with a condition attached — "works, *when*
	the tool is simple and the alerting is automatic"; "feasible and privacy-preservable, *but only
	if* it is opt-in and transparent"; "possible without a privacy catastrophe, *if* processing stays
	on-device." The two halves are not equally checkable: the claim is about somebody else's
	deployment, the condition is a requirement on this one. `condition` is carried as the verbatim
	clause so a revision that drops the qualifier fails against the section rather than quietly
	weakening the requirement.

	`honoured` is tri-state. True and False are verdicts; None means the repo cannot decide it, and
	`note` says why — §2.3's LiDAR lesson claims viability on consumer handsets and §13.1's own
	availability cell says "Select flagships", so the question is a fact about the phone market
	rather than about this tree.
	"""

	model_config = MODEL_CONFIG
	system: str
	lesson: str
	condition: str | None = None
	honoured_by: str | None = None
	resolves: bool = False
	honoured: bool | None = None
	note: str | None = None


class LessonReport(BaseModel):
	model_config = MODEL_CONFIG
	lessons: list[Lesson]
	unhonoured: list[str]
	unresolved: list[str]
	undecided: list[str]
