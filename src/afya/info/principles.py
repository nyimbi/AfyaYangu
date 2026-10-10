"""§6.2's ten content principles, as data with a verdict rather than a paragraph.

The section is titled "Content Principles" and every one of its ten rules was prose. Nine of them
had no check anywhere: a library item, a triage recommendation, a peer alert, a myth correction or
a USSD menu could carry an unactionable sentence, stigmatise the person it describes, or show the
reader a spec section number, and nothing failed.

Two distinctions this module is built on, because getting either wrong produces a gate that lies:

* **Advice and answer are different genres.** §6.2.1 is "Answer 'what should I do,' not 'what is
  X'" — it governs an *answer* to a question, not a library entry. The seed's first-aid and burial
  items are reference material on purpose, and a gate that demanded an imperative verb of every
  library body would flag correct content. So `Subject` says which genre a text belongs to, and the
  action rule applies only to an `answer`.
* **A tone word is checked on the text it is banned in.** "Avoid stigmatising language" is a rule
  about content; "never say 'don't panic'" is a rule about *instruction* — "don't panic" is itself
  a directive, and so is the exact phrasing §6.2.5 tells the writer to use instead. A single scan
  for the word "panic" over everything would fail §6.2.5's own remedy. The stigmatising rule is
  therefore scoped to content, the panic rule to instruction.

`BANNED_DIRECTIVES` and `STIGMA_SUBSTITUTIONS` are deliberately not derived from the spec text at
runtime. They are the section's own words, transcribed, and `tests/ci/test_content_principles.py`
asserts each one is literally present in `docs/spec.md` — so the table cannot drift from the rule
it claims to enforce, and a spec revision that changes a substitution fails until the table moves
with it.
"""
import re
from enum import Enum
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict

from afya.channels.service import GSM7
from afya.info.views import ContentItem, DecisionNode

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class Subject(str, Enum):
	"""What kind of text is being judged.

	Only two genres, because only two rules are genre-dependent: §6.2.1's action rule and §6.2.6's
	forwardability are about *an answer to a question*, and everything else — the stigmatising
	substitution, the calm-down ban, the spec reference — governs any text a person reads.

	An earlier version had a third genre, `instruction`, and exempted it from the stigma rule on the
	theory that a sentence addressed to the reader names nobody. A peer alert disproves it: it is
	broadcast to a village and can name a neighbour as "an Ebola victim", which is the harm §6.2.9
	exists to prevent. The exemption was a precaution against a false positive that the corpus never
	produced, and it cost the rule its most consequential surface.
	"""
	answer = 'answer'
	content = 'content'


class Severity(str, Enum):
	fail = 'fail'
	review = 'review'


class Verdict(BaseModel):
	"""One finding. `review` is a flag for a person, not a rejection — a long sentence in a burial
	protocol may be the right sentence, and §6.2.10's "short sentences" is a design intent rather
	than a threshold the code should enforce."""
	model_config = MODEL_CONFIG
	principle: int
	rule: str
	severity: Severity
	detail: str


class Finding(BaseModel):
	model_config = MODEL_CONFIG
	surface: str
	subject: Subject
	verdicts: list[Verdict]

	def failures(self) -> list[Verdict]:
		return [v for v in self.verdicts if v.severity is Severity.fail]

	def reviews(self) -> list[Verdict]:
		return [v for v in self.verdicts if v.severity is Severity.review]

	def clean(self) -> bool:
		return not self.verdicts


# --- §6.2's rules, as tables -------------------------------------------------------------------

# §6.2.5: 'Never say "don't panic." It doesn't work. Give a concrete action instead.' The rule is
# the *construction*, not the word: the sentence it forbids and the sentence it prescribes are both
# instructions to stay calm. Matched as a pattern so "Don't panic, but…" is caught too.
BANNED_DIRECTIVES: tuple[tuple[int, str, str], ...] = (
	(5, r"\b(?:don'?t|do not|never)\s+panic\b", 'the calm-down instruction §6.2.5 forbids — give an action instead'),
	(5, r"\busiogope\b", 'the calm-down instruction §6.2.5 forbids — give an action instead'),
)

# §6.2.9, transcribed verbatim: 'Say "a person who is sick," not "an Ebola victim." Say "the area
# where a case was reported," not "the Ebola zone."' Each pattern is what the rule rejects, with the
# section's own replacement. English only: the substitution the spec writes is English, and inventing
# Swahili equivalents would be inventing a rule the section does not state.
STIGMA_SUBSTITUTIONS: tuple[tuple[int, str, str, str], ...] = (
	(9, r'\bEbola (?:victim|patient|case|spreader)\b', 'a person who is sick', 'an Ebola victim'),
	(9, r'\bEbola zone\b', 'the area where a case was reported', 'the Ebola zone'),
	(9, r'\bEbola area\b', 'the area where a case was reported', 'the Ebola zone'),
	(9, r'\bsuperspreader\b', 'a person who passed the infection to others', 'a superspreader'),
)

# §6.2.5, the second half: the rule bans the calm-down instruction because it "doesn't work", and
# the thing that works instead is a concrete action. These are the alarmist words the peer-alert
# gate already carried, kept as data here rather than as a list inside one service, so the section
# has one home. Applied to any text a person reads: "everyone will die" is a false certainty whether
# it is a broadcast or a library item.
ALARMIST_PHRASES: tuple[tuple[int, str, str], ...] = (
	(5, r'\bpanic\b', 'alarmist wording — §6.2.5 asks for a concrete action instead'),
	(5, r'\bdeadly killer\b', 'alarmist wording — §6.2.5 asks for a concrete action instead'),
	(5, r'\beveryone will die\b', 'a certainty about an outcome nobody can promise — §6.2.8'),
	(5, r'\bmass grave\b', 'alarmist wording — §6.2.5 asks for a concrete action instead'),
)

# §6.2.10: 'Design for low literacy. Short sentences.' A design intent, so the long-sentence rule
# flags for review rather than failing. The threshold is a review prompt, not a standard: the
# longest correct sentence in the seed corpus runs to 20 words, so 25 leaves real content alone.
LONG_SENTENCE_WORDS = 25

# §6.2.1: 'Answer "what should I do," not "what is X." Information without action is noise.' The
# predicate is that the answer *contains a disposition*, not that it opens with a verb — the malaria
# recommendation leads with "Febrile illness: test and treat…" and is exactly the answer the section
# asks for. "No action needed" is a disposition too: telling someone there is nothing to do is an
# answer to "what should I do", and a gate that demanded an imperative verb of it would be enforcing
# a rule the section does not state.
DIRECTIVE = re.compile(
	r'\b(?:call|wash|avoid|use|test|treat|go|get|monitor|isolate|seek|contact|report|encourage|keep|'
	r'drink|cover|stay|take|give|tell|check|ring|visit|start|stop|rest|watch|nothing|do not|never|'
	r'no action|piga|osha|epuka|tumia|nenda|pimwa|tibu|dumisha|jitenge|wasiliana|kataa|fuata|kula|'
	r'nywa|chukua|ripoti|wahi)\b',
	re.IGNORECASE,
)

# §3.3 principle 9 and §6.2.1 together: an answer is written for a person, not for the spec. A
# section reference that reaches a screen is the same failure as a feature code, and it reached two
# of them — the malaria recommendation served "(spec 6.3 malaria trap)" in both languages.
SPEC_REFERENCE = re.compile(r'\bspec\s*§?\s*\d|§\s*\d+\.\d+|\bTier\s*[1-4]\b')

# §3.3 principle 10 / §6.2.6: 'Every answer must be forwardable as a WhatsApp card or an SMS.' An
# SMS is GSM-7; a character outside that set doubles the cost of the message and can arrive as
# mojibake. The rule is scoped to text that *is* an answer — a triage recommendation, a correction,
# a tree leaf. A form label ("Temperature °C") and a question ("Do you have fever (≥38.0 °C)?") are
# neither, and §6.2.6's "every answer" does not reach them: the card that travels carries the
# answer, and the seed library's em dash is typography in reference material rather than a
# recommendation anyone forwards. Scoping this to answers is what keeps the gate from failing
# correct content, which is the only way a gate stays trusted.
NON_GSM7 = tuple(sorted(set('—–’‘“”…°≥≤µ') - GSM7))


def _sentences(text: str) -> list[str]:
	"""Split on sentence enders. A decimal point inside a number is not an ender — "38.5 °C" is one
	sentence, and splitting it would count a fragment as a long sentence."""
	return [s for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]


def _stigma(text: str) -> list[Verdict]:
	"""§6.2.9, on any text a person reads. A broadcast to a village can name a neighbour as "an Ebola
	victim" as easily as a library item can, so this is not scoped to reference material."""
	out: list[Verdict] = []
	for principle, pattern, replacement, rejected in STIGMA_SUBSTITUTIONS:
		for m in re.finditer(pattern, text):
			out.append(Verdict(
				principle=principle, rule='stigmatising_language', severity=Severity.fail,
				detail=f'{m.group(0)!r} — say {replacement!r}, not {rejected!r}',
			))
	return out


def _directives(text: str) -> list[Verdict]:
	"""§6.2.5, on any text a person reads."""
	return [
		Verdict(principle=p, rule='banned_directive', severity=Severity.fail, detail=f'{m.group(0)!r}: {why}')
		for p, pattern, why in BANNED_DIRECTIVES + ALARMIST_PHRASES
		for m in re.finditer(pattern, text, re.IGNORECASE)
	]


def _actionable(text: str) -> list[Verdict]:
	"""§6.2.1, on an answer only."""
	if DIRECTIVE.search(text):
		return []
	return [Verdict(
		principle=1, rule='no_action', severity=Severity.fail,
		detail='an answer must contain an action — §6.2.1: information without action is noise',
	)]


def _low_literacy(text: str) -> list[Verdict]:
	"""§6.2.10, as a review flag rather than a failure."""
	return [
		Verdict(principle=10, rule='long_sentence', severity=Severity.review,
		        detail=f'{len(s.split())} words: {s[:60]}')
		for s in _sentences(text) if len(s.split()) > LONG_SENTENCE_WORDS
	]


def _forwardable(text: str) -> list[Verdict]:
	"""§6.2.6, as a hard failure: a character outside GSM-7 breaks the SMS half of the promise."""
	return [
		Verdict(principle=6, rule='not_forwardable', severity=Severity.fail,
		        detail=f'{ch!r} is outside GSM-7, so this cannot be sent as a plain SMS')
		for ch in NON_GSM7 if ch in text
	]


def _reader_facing(text: str) -> list[Verdict]:
	"""§3.3 principle 9 / §6.2.1: no spec section reference reaches a person."""
	return [
		Verdict(principle=1, rule='spec_reference', severity=Severity.fail,
		        detail=f'{m.group(0)!r} is written for the spec, not for the reader')
		for m in SPEC_REFERENCE.finditer(text)
	]


def judge(surface: str, text: str, subject: Subject) -> Finding:
	"""Apply every rule that governs this kind of text, and return what it found.

	An empty `verdicts` is the pass. Callers that need a boolean ask `clean()`; callers that need to
	know *which* principle was broken read the verdicts, which is the point of returning them rather
	than a bool.
	"""
	assert surface and text.strip(), 'a surface needs a name and text to judge'
	verdicts: list[Verdict] = []
	# Universal rules: any text a person reads, in any genre.
	verdicts += _directives(text)
	verdicts += _stigma(text)
	verdicts += _reader_facing(text)
	# Answer-only rules: §6.2.1 and §6.2.6 are about an answer to a question.
	if subject is Subject.answer:
		verdicts += _actionable(text)
		verdicts += _forwardable(text)
	verdicts += _low_literacy(text)
	return Finding(surface=surface, subject=subject, verdicts=verdicts)


# --- the corpora the rules run over ------------------------------------------------------------

# One text a person reads, with the genre §6.2 judges it as. Kept as one shape so a new surface is
# added here rather than in a second place that forgets the first.
Surface: TypeAlias = tuple[str, str, Subject]


def judge_corpus(items: list[Surface]) -> list[Finding]:
	"""Judge many surfaces. The caller supplies the texts, so the same rules run over the seed
	library, a served recommendation, or a peer alert that was just written."""
	return [judge(surface, text, subject) for surface, text, subject in items]


def library_texts(items: list[ContentItem]) -> list[Surface]:
	"""The library, title and body together — a title reaches a screen."""
	return [(f'library:{i.slug or i.item_id}', f'{i.title} {i.body}', Subject.content) for i in items]


def tree_texts(tree: dict[str, DecisionNode]) -> list[Surface]:
	"""The decision tree, node by node, each judged as what it is.

	A node's `question` is asked of the reader, so it is not an answer and §6.2.1 does not govern it
	— "Do you have fever (38.0 C)?" is the right question and contains no action, correctly. The
	leaf's `recommendation` is the answer, and that is where the action rule bites. Judging the two
	as one text is how a gate ends up demanding an imperative verb of a question.
	"""
	out: list[Surface] = []
	for node_id, node in tree.items():
		if node.leaf_recommendation is not None:
			out.append((f'tree:{node_id}', node.leaf_recommendation, Subject.answer))
		else:
			out.append((f'tree:{node_id}', node.question, Subject.content))
	return out
