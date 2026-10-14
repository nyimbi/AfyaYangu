"""§CHAN-000's call-in and §CHAN-004's clinician Q&A, as models.

Both sections print a live session as a *content format*, and both were `missing` for the same
reason: a live programme needs a schedule, a queue and a record of a call answered, and this tree
had none of the three. The two are one mechanism here because they are one thing — a clinician
answering questions from people who are listening — and the section's own two entries differ in
which platform carries it, not in what happens.

Three models, and each of the three is one of the things the audit note names as absent:

* `LiveSession` is the *schedule*: when it starts, when it ends, who is answering and about what.
* `SessionQuestion` is the *queue*: one question, the handle of the person who asked it, and the
  answer once there is one.
* `SessionTranscript` is the *record of a call answered* — the part a person who missed the
  programme reads afterwards, and the part a broadcaster can hand to a regulator.

**No model here carries a person.** `asked_by` is a §SEC-004 rotating handle, derived from the
subject and never the subject itself, which is the same rule `PseudonymPolicy` states for the
public feed: a live programme's queue is read by whoever is running it and its transcript is read
by anyone at all, so the identifier that reaches either has to be one that stops naming the person
when the window turns over.

Both ids come from `ref8()` rather than from a truncation of a UUID7. A UUID7's leading bits are a
millisecond timestamp, so `uuid7str()[:10]` is constant across a 256 ms window — and a queue is
exactly the place two records are made in the same breath: a clinician working down a queue mints
one question after another, and a truncated timestamp gave the second the first's id, which
`ask()` filed over it. `afya.ids` documents that failure and ships the counter for it.
"""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from afya.ids import ref8

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class LivePlatform(str, Enum):
	"""Which of §5's channels is carrying the programme.

	§CHAN-000 is Community Radio and §CHAN-004 is Social Media, and the two print the same format —
	a clinician taking questions live. Kept as a field rather than as two services because the
	difference is where the audience is, and a deployment that ran the radio call-in and the
	WhatsApp live session as two queues would answer one person's question twice.
	"""

	radio_callin = 'radio_callin'
	social_live = 'social_live'


class LiveStatus(str, Enum):
	"""A session's position in time, as a state rather than as two instants to compare.

	`scheduled` is the state a queue may not be filled in: a question asked before the programme
	opens is a question nobody is there to hear, and §CHAN-000's format is a *live* programme rather
	than a mailbox. The refusal is the whole reason this is a closed set rather than a timestamp
	comparison — "is it between the two instants" answers the same question and cannot say why.
	"""

	scheduled = 'scheduled'
	live = 'live'
	ended = 'ended'


class QuestionStatus(str, Enum):
	queued = 'queued'
	answered = 'answered'
	declined = 'declined'


class LiveSession(BaseModel):
	"""One programme: the schedule §CHAN-000 and §CHAN-004 print and nothing here carried.

	`topic`, `clinician` and `venue` are the section's own programme information — a call-in
	announcement names who is answering and what about, which is what makes it a programme rather
	than an open line. `ends_at_iso` is required because a live session that never ends is one whose
	queue never closes, and the audit note's absence was as much "no schedule" as "no queue".
	"""

	model_config = MODEL_CONFIG
	session_id: str = Field(default_factory=lambda: 'LS-' + ref8())
	platform: LivePlatform
	topic: str = Field(min_length=1)
	clinician: str = Field(min_length=1, description='who is answering, by the name they are announced under')
	starts_at_iso: str = Field(min_length=10)
	ends_at_iso: str = Field(min_length=10)
	lang: str = 'en'
	venue: str | None = None
	status: LiveStatus = LiveStatus.scheduled


class SessionQuestion(BaseModel):
	"""One question in the queue, and the answer once a clinician has given one.

	`asked_by` is a handle and `asked_at_ms` is an instant, and neither is the person: the handle is
	§SEC-004's derived, rotating one, so the same asker carries a different name next month and a
	reader of the queue cannot assemble a person's question history out of it.

	`verdicts` is the §6.2 finding on the *answer*, carried rather than raised. An answer is clinical
	speech spoken live, and the section's own rules would refuse ordinary sentences — "it is likely a
	viral infection" contains no action, and an em dash is outside GSM-7 — so a gate that rejected on
	them would refuse correct medicine. What the field is for is the rule that *must* bite: an answer
	that calls someone "an Ebola victim" is the stigmatising sentence §6.2.9 exists to stop, and a
	supervisor reading the queue sees it named on the row it is on.
	"""

	model_config = MODEL_CONFIG
	question_id: str = Field(default_factory=lambda: 'LQ-' + ref8())
	session_id: str
	asked_by: str = Field(min_length=1, description='§SEC-004 rotating handle, never a subject reference')
	text: str = Field(min_length=1)
	lang: str = 'en'
	asked_at_ms: int = Field(ge=0)
	status: QuestionStatus = QuestionStatus.queued
	# The channel report this question came from, when it arrived through §5.4's backend rather than
	# through the route. It is what makes the absorb idempotent: the channel routes walk the whole
	# report sink after every session, so without this a person who texted a question once would
	# have it queued again on every later session they opened.
	source_report_id: str | None = None
	answer: str | None = None
	answered_by: str | None = None
	answered_at_ms: int | None = None
	declined_reason: str | None = None
	verdicts: list[str] = []


class TranscriptEntry(BaseModel):
	"""One answered exchange as a reader who missed the programme sees it.

	Deliberately **not** a `SessionQuestion`: the queue holds who asked, and the transcript is
	published to everyone. Dropping the handle here rather than filtering it at the route is the
	difference between a model that cannot carry a person and one that is trusted not to — and the
	second is the shape that leaks the day someone adds a field to the response.
	"""

	model_config = MODEL_CONFIG
	question: str
	answer: str
	answered_by: str
	lang: str = 'en'


class SessionTranscript(BaseModel):
	"""§CHAN-000's "record of a call answered", as the document a reader gets.

	`unanswered` is carried beside the entries rather than left off, because a transcript that showed
	only what was answered would read as a programme where every question was taken — which is a
	claim about the session nobody made, and the one a person who asked and was not reached would
	most want contradicted.
	"""

	model_config = MODEL_CONFIG
	session_id: str
	topic: str
	clinician: str
	platform: LivePlatform
	lang: str = 'en'
	status: LiveStatus
	entries: list[TranscriptEntry]
	questions_asked: int = Field(ge=0)
	questions_answered: int = Field(ge=0)


class QuestionIn(BaseModel):
	"""What an asker sends. Two fields, and neither of them is who they are.

	`asked_by` is deliberately **not** here. A handle in the body is a handle a caller can choose,
	and a queue where anyone may ask under anyone's name is one a clinician cannot use — the whole
	point of §SEC-004's rotating handle is that it is derived rather than claimed. The route derives
	it from the token's own subject, so the asker is whoever holds the token and there is no field
	to lie in.
	"""

	model_config = MODEL_CONFIG
	text: str = Field(min_length=1)
	lang: str = 'en'


class AnswerIn(BaseModel):
	"""What a clinician sends back. As with `QuestionIn`, who answered is the token, not a field."""

	model_config = MODEL_CONFIG
	answer: str = Field(min_length=1)


class DeclineIn(BaseModel):
	"""Why a question was not taken. Required, for the reason `decline()` states."""

	model_config = MODEL_CONFIG
	reason: str = Field(min_length=1)
