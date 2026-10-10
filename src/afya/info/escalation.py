"""§6.5's escalation clause — a content error affecting safety, as a trigger rather than a sentence.

§6.5 ends with "**Escalation:** Any content error affecting safety triggers immediate review and
correction broadcast." Nothing carried it. §6.5's *retirement* bullet was modelled — `archived` is a
stage, reachable from anywhere — but retirement for being **outdated** and retirement for being
**wrong** were the same state. An item could be pulled because its review date passed or because it
told people to drink salt water, and the record said `archived` either way. Nothing said when it was
found wrong, who found it, or that the escalation had fired at all.

Three things this module adds, then:

* **The trigger has a jurisdiction, and it is read off §6.1 rather than asserted.** "Affecting
  safety" is exactly `is_life_safety(item.answers_rank)` — the same set §6.2.4's language rule keys
  on. Whoever is retiring content under pressure is the last person to mark their own item as
  safety-affecting, and §6.5's clause exists precisely for the item someone is rushing out. One
  definition of life-safety serves both rules, so they cannot disagree the first time either moves.

* **"Immediate" is a clock, not a word.** §6.5 names no number and §24.8's own row for a clinical
  content error says "Immediate correction, clinical review, user notification" without one either.
  The number that *does* exist is §24.3's support ladder: §24.8 rates this incident `critical`, and
  a critical incident is answered in 15 minutes. So the deadline is `SUPPORT_SLA_HOURS[critical]`
  read from the ladder rather than a figure invented here, and the label beside it is derived from
  the same hours so the two cannot drift apart.

* **The broadcast is a channel event, not a string.** §6.5 says the error triggers a correction
  broadcast, and §6.4 step 5 publishes "all channels simultaneously". A correction is therefore an
  *answer*: it is judged by §6.2 like any other, it carries every language §6.2.4 requires of a
  life-safety message, and it goes out on the alert feed the socket fans out from — the surface
  §6.4's own corrections use.

Two gaps are reported rather than papered over, because both are ways the clause reads as discharged
while nothing reaches a reader:

* **A broadcast the subscriber can switch off.** The correction lands in the `outbreak` category —
  §6.1's ranked questions *are* the outbreak questions, so a life-safety correction belongs to the
  disease-alert preference — and that preference is toggleable. §9.6 makes only per-subject critical
  alerts non-disableable, so the one message that must reach a person is one they may have turned
  off. `preference_gap` says so instead of pretending the broadcast is guaranteed.

* **An item pulled with nothing to put in its place.** A wrong item is withheld the moment it is
  found wrong, which is the point — but a shelf with the guidance removed and no replacement is a
  reader with no answer. `superseded` reports whether the library holds the corrected item.
"""
from pydantic import BaseModel, ConfigDict, Field

from afya.alerting.views import TOGGLEABLE, governing_preference
from afya.info.questions import REQUIRED_LANGS, is_life_safety
from afya.info.views import ContentItem
from afya.operations.views import SUPPORT_SLA_HOURS, IncidentClass, IncidentSeverity

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# §24.8's own row for a content error, read from the table rather than restated: the incident this
# escalation opens is the one the section names, at the severity it names, notifying the two parties
# it names. Restating any of the three here would be a second definition of §24.8.
CONTENT_ERROR_KIND = IncidentClass.clinical_content_error
CONTENT_ERROR_SEVERITY = IncidentSeverity.critical

# The §24.3 rung the severity maps to — the only number §6.5's "immediate" can honestly resolve to,
# since neither §6.5 nor §24.8 prints one. Derived so it moves with the ladder.
REVIEW_SLA_HOURS: float = SUPPORT_SLA_HOURS[CONTENT_ERROR_SEVERITY]

# The feed category the correction is broadcast in. §6.1's ten questions are the outbreak content
# strategy — ranks 1 to 8 are "is it near me", "is school safe", "I have a fever", "how do I protect
# my family", "what is rumour", "where do I go", "is there a vaccine", "can I get tested" — so an
# item answering one of them is outbreak guidance by construction, and its correction belongs to the
# disease-alert preference rather than to a category invented for it.
CORRECTION_FEED_CATEGORY = 'outbreak'


def _hours_label(hours: float) -> str:
	"""The §24.3 ladder rung as a reader reads it.

	Derived from the hours rather than carried beside them: §6.4's own SLA label and `sla_hours`
	were two statements of one number and disagreed in a canary, which is a rate stated in one place
	and used in another.
	"""
	assert hours > 0, 'an SLA is a positive duration'
	if hours < 1:
		return f'{round(hours * 60)} minutes'
	return '1 hour' if hours == 1 else f'{round(hours)} hours'


REVIEW_SLA_LABEL: str = _hours_label(REVIEW_SLA_HOURS)


class ContentError(BaseModel):
	"""A published item found wrong, and what replaces it.

	`found_at_ms` has a default because the *service* stamps it, the same discipline §6.2.3's
	`updated_at_ms` follows: when an error was found is a fact the server records, not one a writer
	chooses. `what_is_wrong` is required — an item pulled with no stated reason is one nobody can
	decide the follow-up for, and §6.5's clause is about *a content error*, which has to be sayable.

	The correction is one field per language rather than a `dict` keyed by language code, because
	the mobile catalogue's generic form has no object type — a correction sent as a nested map is a
	correction no client can compose. §6.2.4's required set is exactly the two languages the app
	publishes in, so naming them is exact rather than lossy, and the unsupported-language case stops
	being a validator and becomes a shape the model cannot take.

	Both are empty by default: a non-safety item's error may be reported with no correction drafted
	yet, and `missing_langs` is what reports the gap rather than a validation error refusing the
	report. A wrong item must be pullable the moment it is found wrong.
	"""
	model_config = MODEL_CONFIG
	error_id: str = Field(min_length=1)
	item_id: str = Field(min_length=1)
	found_at_ms: int = Field(default=0, ge=0)
	found_by: str = Field(min_length=1)
	what_is_wrong: str = Field(min_length=1)
	langs: list[str] = Field(default_factory=list)
	correction_en: str = ''
	correction_sw: str = ''
	replacement_slug: str | None = None

	@property
	def correction(self) -> dict[str, str]:
		"""The correction as a language map, in the order §6.2.4 lists the languages.

		The escalation logic reads this, so the two spellings of one fact cannot drift: the fields
		are what a client sends and what a form draws, this is what the rules are applied to.
		"""
		return {lang: text for lang, text in
		        (('en', self.correction_en), ('sw', self.correction_sw)) if text}


class ContentEscalation(BaseModel):
	"""§6.5's clause as the facts a person acting on it needs.

	`affects_safety` is the whole trigger, and it is read off §6.1 rather than asserted by whoever
	retired the item. Everything below it follows from that one fact, which is why it is a field and
	not a paragraph: a non-safety error is archived quietly and escalates nothing.

	**The item is named by slug, never by id.** This row is served — it is the body of the refusal a
	correction missing a language comes back with, and it is what the escalation-log route returns —
	and a seed id embeds its spec code (`INF-003-en`). The slug is the code-free handle for the same
	reason `/info/library` withholds the id: what a person reads must not carry `INF-003`. The
	internal log keeps the id; the served row does not.
	"""
	model_config = MODEL_CONFIG
	error_id: str
	slug: str
	affects_safety: bool
	incident_kind: str
	severity: str
	notifies: list[str]
	found_at_ms: int
	review_due_ms: int
	review_due_label: str
	review_overdue: bool
	broadcast_required: bool
	correction_langs: list[str]
	missing_langs: list[str]
	withheld_langs: list[str]
	preference_gap: bool
	superseded: bool
	summary: str


def escalate(item: ContentItem, error: ContentError, now_ms: int, withheld_langs: list[str],
             replacement_published: bool) -> ContentEscalation:
	"""§6.5's escalation for one error, computed from the item's own place in §6.1.

	`withheld_langs` and `replacement_published` are the service's facts and are passed in rather
	than guessed: this function knows what §6.5 requires, and the service knows what it did. A
	function that assumed either would report an escalation the shelf does not reflect.
	"""
	assert error.found_at_ms > 0, 'an escalation is measured from the instant the error was found'
	assert now_ms >= error.found_at_ms, 'the clock cannot precede the finding'
	safety = is_life_safety(item.answers_rank)
	due = error.found_at_ms + int(REVIEW_SLA_HOURS * 3_600_000)
	# §6.2.4 requires every language of a life-safety message. A non-safety item is not held to it:
	# a health tip published in one language is a gap, not the act §6.2.4 forbids.
	required = list(REQUIRED_LANGS) if safety else [item.lang]
	missing = [lang for lang in required if not error.correction.get(lang)]
	return ContentEscalation(
		error_id=error.error_id, slug=item.slug or item.item_id,
		affects_safety=safety,
		incident_kind=CONTENT_ERROR_KIND.value, severity=CONTENT_ERROR_SEVERITY.value,
		notifies=list(_notifies()),
		found_at_ms=error.found_at_ms,
		review_due_ms=due, review_due_label=REVIEW_SLA_LABEL, review_overdue=now_ms > due,
		broadcast_required=safety,
		correction_langs=list(error.correction), missing_langs=missing,
		withheld_langs=sorted(withheld_langs),
		preference_gap=safety and governing_preference(CORRECTION_FEED_CATEGORY) in TOGGLEABLE,
		superseded=replacement_published,
		summary=_summary(item, safety, missing, replacement_published),
	)


def _notifies() -> tuple[str, ...]:
	"""Who §24.8 says this incident notifies, read from its own row."""
	from afya.operations.service import INCIDENT_KINDS
	for kind in INCIDENT_KINDS:
		if kind.kind is CONTENT_ERROR_KIND:
			return tuple(kind.notifies)
	raise AssertionError(f'{CONTENT_ERROR_KIND} is not a §24.8 incident type')


def _summary(item: ContentItem, safety: bool, missing: list[str], superseded: bool) -> str:
	"""One sentence an operator can act on, in plain language and inside GSM-7.

	It carries no spec code and no section reference — §6.2.1 and §3.3 principle 9 apply to
	anything a person reads, and this line is read by the team under time pressure.
	"""
	if not safety:
		return f'{item.slug or item.item_id} was retired. It is not a life-safety item, so nothing is broadcast.'
	parts = ['This is a life-safety item, so the correction must go out on every channel.']
	if missing:
		parts.append('Missing languages: ' + ', '.join(missing) + '.')
	if not superseded:
		parts.append('No corrected item is published yet, so the guidance is currently withdrawn.')
	return ' '.join(parts)
