"""§6.4's misinformation response protocol, as a clock rather than a table.

§6.4 prints six steps with an owner and an SLA each, and six myth categories "to pre-draft". Both
were prose. `MisinfoCluster` carried a velocity and a correction string, so a rumour could be
`spiking` and `correction_published` on the same call that first saw it, with nothing anywhere
measuring whether the four-hour triage or the twenty-four-hour correction had happened. §6.2.7's
"correct misinformation within 24 hours" was a sentence with no clock behind it, and §24.8's own
incident row for a misinformation spike says "rapid response protocol" with no number, which is
what a rule looks like when the number lives only in another section.

Two things this module adds, then:

* **The clock.** `response_clock` computes each step's due time from the moment of detection and
  reports which are overdue as a fact. Detection is the caller's timestamp — the service has no
  clock of its own, the same discipline §24.8's breach deadline follows.
* **The coverage.** §6.4 says which myth categories must have a correction drafted *before* the
  rumour arrives, and two of the six had none: conspiracy narratives and stigma narratives. A
  correction drafted during a spike is drafted under pressure, which is the thing pre-drafting
  exists to avoid.

Corrections are per-language. §6.4's step 4 says the correction is drafted "in all relevant
languages", and §6.2.4 forbids publishing English-only for a life-safety message — so a correction
that exists only in English is a correction half the audience cannot read, and `untranslated`
reports exactly that.
"""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from afya.info.myths import MYTH_CATEGORIES, MythCategory

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# §6.2.4 and §6.4 step 4: the languages a life-safety correction must reach. English is second by
# §3.3 principle 8, which is why Swahili is the one that must not be missing rather than the reverse.
CORRECTION_LANGS: tuple[str, ...] = ('en', 'sw')


class StepState(str, Enum):
	completed = 'completed'
	pending = 'pending'
	due = 'due'
	overdue = 'overdue'
	open_ended = 'open_ended'


class ProtocolStep(BaseModel):
	"""One row of §6.4's table. `sla_hours` is None for the two rows the section writes as
	"Continuous" and "Ongoing" — those are cadences, not deadlines, and inventing an hour count for
	them would be inventing a commitment the section declines to make."""
	model_config = MODEL_CONFIG
	step: int = Field(ge=1, le=6)
	action: str = Field(min_length=1)
	owner: str = Field(min_length=1)
	sla_hours: float | None = Field(default=None, gt=0)
	sla_label: str = Field(min_length=1)

	def deadline_ms(self, detected_at_ms: int) -> int | None:
		"""When this step comes due, or None when the section sets no clock."""
		return None if self.sla_hours is None else detected_at_ms + int(self.sla_hours * 3_600_000)


class StepStatus(BaseModel):
	model_config = MODEL_CONFIG
	step: int
	action: str
	owner: str
	sla_label: str
	due_at_ms: int | None
	state: StepState


class ResponseClock(BaseModel):
	"""Where a response stands, measured from detection.

	`breached` is the §6.2.7 promise as a boolean: a step whose SLA has passed without completion.
	The service does not track completion per step — it has no per-step state and inventing one would
	be inventing a workflow nobody runs — so `completed_through` is the caller's fact, and the clock
	reports what it is given rather than assuming a response is on time.
	"""
	model_config = MODEL_CONFIG
	topic: str
	detected_at_ms: int
	completed_through: int = Field(ge=0, le=6)
	steps: list[StepStatus]
	breached: bool
	next_due_ms: int | None


class ProtocolCoverage(BaseModel):
	"""§6.4's readiness, reported rather than assumed."""
	model_config = MODEL_CONFIG
	steps: list[ProtocolStep]
	categories: list[MythCategory]
	undrafted: list[str]
	untranslated: dict[str, list[str]]
	orphan_corrections: list[str]


# §6.4's six steps, transcribed with the owners and SLAs the section prints.
PROTOCOL: tuple[ProtocolStep, ...] = (
	ProtocolStep(step=1, action='Detect', owner='Community tracker, social listening, WhatsApp flags',
	             sla_label='continuous'),
	ProtocolStep(step=2, action='Triage', owner='PHEOC risk communication team',
	             sla_hours=4, sla_label='4 hours'),
	ProtocolStep(step=3, action='Verify', owner='Technical working group',
	             sla_hours=12, sla_label='12 hours'),
	ProtocolStep(step=4, action='Draft correction', owner='Comms team, in all relevant languages',
	             sla_hours=24, sla_label='24 hours'),
	ProtocolStep(step=5, action='Publish', owner='All channels simultaneously',
	             sla_hours=24, sla_label='24 hours'),
	ProtocolStep(step=6, action='Monitor', owner='Track spread and sentiment',
	             sla_label='ongoing'),
)

STEP_BY_NUMBER: dict[int, ProtocolStep] = {s.step: s for s in PROTOCOL}
assert set(STEP_BY_NUMBER) == set(range(1, 7)), '§6.4 has six steps'

# §6.4's "Common myth categories to pre-draft", with the parenthetical examples the section gives.
# Defined in `afya.info.myths` beside the corpus they describe and re-exported here, because the
# category a correction answers is a property of the correction: stated in both places, a category
# could gain a topic in one and not the other, and `coverage()` would then report a gap the library
# had closed.
__all__ = ['CORRECTION_LANGS', 'MYTH_CATEGORIES', 'PROTOCOL', 'MythCategory', 'ProtocolCoverage',
           'ProtocolStep', 'ResponseClock', 'StepState', 'StepStatus', 'coverage', 'response_clock',
           'step_statuses']


def step_statuses(detected_at_ms: int, now_ms: int, completed_through: int) -> list[StepStatus]:
	"""Each step as it stands, given what has been completed.

	A step with no deadline is `open_ended` whether or not it is done — "continuous" is not a state
	that completes. A step at or before `completed_through` is done and cannot be overdue; the rest
	are overdue once their due time has passed, `due` within the final hour, `pending` before that.
	"""
	out: list[StepStatus] = []
	for step in PROTOCOL:
		due = step.deadline_ms(detected_at_ms)
		if step.step <= completed_through:
			# Done. A completed step cannot be overdue, which is why `breached` asks about the steps
			# still open rather than about the clock alone.
			state = StepState.completed
		elif step.sla_hours is None:
			state = StepState.open_ended
		elif due is None or now_ms < due - 3_600_000:
			state = StepState.pending
		elif now_ms <= due:
			# At the deadline is not past it. `due` is the last instant the step is on time, which is
			# why the boundary is `<=` here and `>` below — an off-by-one on a four-hour SLA is the
			# difference between a breach and a report.
			state = StepState.due
		else:
			state = StepState.overdue
		out.append(StepStatus(
			step=step.step, action=step.action, owner=step.owner, sla_label=step.sla_label,
			due_at_ms=due, state=state,
		))
	return out


def response_clock(topic: str, detected_at_ms: int, now_ms: int, completed_through: int = 0) -> ResponseClock:
	"""§6.4's clock for one rumour, from detection to now.

	`breached` is a fact about the steps still open, not a judgement: it is True when any step the
	response has not completed is past its deadline. A response that has completed through step 5 by
	hour 3 is not breached even at hour 30, because the work is done.
	"""
	assert detected_at_ms > 0 and now_ms >= detected_at_ms, 'a clock needs a detection and a later now'
	assert 0 <= completed_through <= 6, 'completed_through counts §6.4 steps'
	steps = step_statuses(detected_at_ms, now_ms, completed_through)
	breached = any(s.state is StepState.overdue for s in steps)
	upcoming = [s.due_at_ms for s in steps if s.due_at_ms is not None and s.due_at_ms > now_ms]
	return ResponseClock(
		topic=topic, detected_at_ms=detected_at_ms, completed_through=completed_through,
		steps=steps, breached=breached, next_due_ms=min(upcoming) if upcoming else None,
	)


def coverage(corrections: dict[str, dict[str, str]]) -> ProtocolCoverage:
	"""§6.4's readiness: which categories have a correction, and which corrections are thin.

	Three gaps are named, and each is a different kind of incompleteness:

	* `undrafted` — a category §6.4 lists with nothing drafted for it. This is the gap the section
	  warns about directly.
	* `untranslated` — a correction missing a language §6.2.4 requires. An English-only life-safety
	  correction is one the audience §3.3 principle 8 puts first cannot read.
	* `orphan_corrections` — a correction answering no category. Not an error, but a reader should be
	  able to see that `denial_claim` is a seventh topic the section's list does not name.
	"""
	claimed = {t for c in MYTH_CATEGORIES for t in c.topics}
	undrafted = [c.slug for c in MYTH_CATEGORIES if not c.topics]
	untranslated = {
		topic: [lang for lang in CORRECTION_LANGS if not texts.get(lang)]
		for topic, texts in sorted(corrections.items())
		if any(not texts.get(lang) for lang in CORRECTION_LANGS)
	}
	orphans = sorted(t for t in corrections if t not in claimed)
	return ProtocolCoverage(
		steps=list(PROTOCOL), categories=list(MYTH_CATEGORIES), undrafted=undrafted,
		untranslated=untranslated, orphan_corrections=orphans,
	)
