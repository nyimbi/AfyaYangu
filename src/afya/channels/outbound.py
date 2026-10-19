"""§CHAN-1's two outbound bullets that were prose: the follow-up after a USSD report, and "plain language".

§5.3 CHAN-1's Format line is four properties — "160 characters, plain language, local language option
via keyword". Three of the four were `carried`: `segment_sms` does the 160 arithmetic, `SmsOut.body`
bounds the body, `sms_language` reads the prefix. The fourth was a claim in a comment. §5.2's own
examples are written plainly, several composers say so in a docstring — `escalation._summary` calls
itself "one sentence an operator can act on, in plain language" — and a claim in a comment is not a
check. The audit row's note states the closure condition in its own words: "The bullet names a
property of every message the channel sends, so it closes when something measures one."

**The bound is derived from what this product already sends, not invented.** Measured over §5.3
CHAN-1's five printed examples, §5.1's and §5.2's prose, and every channel string table in
`afya.strings`:

* the section's own outbound examples run to **7 words a sentence**, **9 characters a word**, **66
  characters a body**;
* the widest sentence any channel table in the tree actually sent was §SEC-004's pseudonym caveat at
  **31 words**, and the longest single word is `kinachofuatiliwa` at **16 characters** — Swahili, and
  agglutinative, so a long word there is the language rather than jargon;
* after the caveat was split, the widest sentence remaining is **24 words** and the longest word is
  **16 characters**, both of them in the tables `plain_language_report` walks.

So the ceiling is set below the point where a sentence stops being readable in one pass: **25 words a
sentence, 18 characters a word**. A bound tighter than the tree already meets would fail on correct
content and teach its operator to bypass it; a bound with no ceiling at all is the comment this module
replaces. The section's **160** is carried beside them as the body size and the segment count, reported
rather than enforced, for the reason the sibling audit row already gives: `SmsOut` permits ten segments
on purpose, and refusing to send a §LOC-005 advisory because it runs to two would trade a shilling for
a case.

**Writing this module found one string over the line, and the string was fixed rather than the
bound.** §SEC-004's pseudonym caveat ran to 31 words in a single sentence — "A name like this hides
your details, but if only a few people are reporting…" — which is a screen-reader's paragraph served
under a handle, and the one place in the tree where the plain-language claim was false. It is three
sentences now and says the same thing. The bound moved for nothing: a ceiling set to fit the widest
sentence already written is a description of the status quo rather than a bound.

**The follow-up is composed where the report is filed and sent where the report is completed.** §5.3
CHAN-1's Outbound list ends "Follow-up after a USSD report", and nothing sent one: a USSD session ends
with a screen, and a screen is read once and gone. The walk is synchronous and the send is not, so the
sentence is composed at filing time and the route sends it — the same split `emit_report_signal`
already uses, and for the same reason. It is composed for the USSD channel and not for the others,
which is the bullet's own scope and also a rule with a reason: §CHAN-3's WhatsApp router answers in
the conversation the person is already in, so an SMS on top of that reply would be a second message
for one report, while a USSD session leaves nothing behind to keep.
"""
import re

from pydantic import BaseModel, ConfigDict, Field

from afya.strings import answerable

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# The ceiling, derived above. Named as constants rather than inlined so a canary can loosen one and
# watch a test fail — a bound no test has ever seen move is a bound nobody has checked.
MAX_SENTENCE_WORDS = 25
MAX_WORD_CHARS = 18
# §5.3 CHAN-1's "160 characters", carried as the size a single message holds. Reported, not refused.
MESSAGE_CHARS = 160
CHARS_PER_SEGMENT = 153

_SENTENCE_SPLIT = re.compile(r'(?<=[.!?])\s+')
_WORD = re.compile(r"[A-Za-z'\-0-9]+")

# Tables in `afya.strings` that are vocabularies rather than messages, each named with the reason the
# property above admitted it. Asserted in both directions by the test suite, so this cannot rot into a
# filter that hides a table nobody looked at — the `UNGATED_WRITES` rule, on a walker instead of on
# routes.
NOT_A_MESSAGE: frozenset[str] = frozenset({
	# §ACC-002's language codes to the names §CHAN-2 prints. A vocabulary, not a message: nothing here
	# is sent to anyone. `Luhya (Bukusu)` and `Luhya (Maragoli)` are the two entries that hold a space.
	'LANGUAGE_NAME_FOR',
})


class PlainLanguageReading(BaseModel):
	"""How plain one outbound body is, and what about it is not.

	`plain` is the whole of the §CHAN-1 Format bullet made checkable, and `findings` is why — a
	boolean with no reason is the shape that gets re-read as "the gate is noisy". The reading is
	carried on every `SmsOut` the channel produces, so the property travels with the message instead
	of living in a report nobody reads.
	"""

	model_config = MODEL_CONFIG
	chars: int = Field(ge=0)
	segments: int = Field(ge=1)
	sentences: int = Field(ge=0)
	longest_sentence_words: int = Field(ge=0)
	longest_word: str
	longest_word_chars: int = Field(ge=0)
	plain: bool
	findings: list[str]


def plain_language(body: str) -> PlainLanguageReading:
	"""Measure one outbound body against §5.3 CHAN-1's Format line.

	Deliberately a *measurement* and not a refusal. A composer that refused a body over the ceiling
	would drop an outbreak alert because a sentence was long, which is the trade `AfricaTalkingSmsPort`
	already refuses for the cost flag — and the direction matters: this reports, and the one place it
	acts is on the strings this module itself owns, asserted at import below.
	"""
	assert isinstance(body, str), 'a body is text'
	words = _WORD.findall(body)
	sentences = [s for s in _SENTENCE_SPLIT.split(body.strip()) if s.strip()] if body.strip() else []
	longest_sentence = max((len(_WORD.findall(s)) for s in sentences), default=0)
	longest_word = max(words, key=len, default='')
	segments = max(1, -(-len(body) // CHARS_PER_SEGMENT))
	findings: list[str] = []
	if longest_sentence > MAX_SENTENCE_WORDS:
		findings.append(f'a sentence runs to {longest_sentence} words (limit {MAX_SENTENCE_WORDS})')
	if len(longest_word) > MAX_WORD_CHARS:
		findings.append(f'the word "{longest_word}" is {len(longest_word)} characters (limit {MAX_WORD_CHARS})')
	if len(body) > MESSAGE_CHARS:
		findings.append(f'the body is {len(body)} characters, so it is {segments} messages')
	return PlainLanguageReading(
		chars=len(body), segments=segments, sentences=len(sentences),
		longest_sentence_words=longest_sentence, longest_word=longest_word,
		longest_word_chars=len(longest_word),
		# A body over §CHAN-1's 160 is not *unplain* — it is two messages, and the section's own
		# §LOC-005 advisory is one. Only the readability pair decides `plain`, and the size finding
		# rides along so the sender sees what the message costs without being told it is illegible.
		plain=longest_sentence <= MAX_SENTENCE_WORDS and len(longest_word) <= MAX_WORD_CHARS,
		findings=findings,
	)


# §CHAN-1's "Follow-up after a USSD report", in the two languages this repo carries a table for.
# `{symptom}` is §CHAN-2's own menu item localised by `ussd_label`, so the sentence names what the
# person chose in the words they chose it in — and the no-symptom fallback exists because a report
# from a channel that carries no menu (a WhatsApp body, an inbound keyword) has a symptom list and no
# label, which is a different thing from having reported nothing.
FOLLOW_UP_STRINGS: dict[str, dict[str, str]] = {
	'en': {
		'symptom': 'your report of {symptom}',
		'no_symptom': 'your symptom report',
		'plain': 'Afya Yangu: we recorded {symptom}. Call 719 if you feel worse.',
		'callback': (
			'Afya Yangu: we recorded {symptom}. A health worker will call you. '
			'Call 719 if you feel worse.'
		),
	},
	'sw': {
		'symptom': 'taarifa yako ya {symptom}',
		'no_symptom': 'taarifa yako ya dalili',
		'plain': 'Afya Yangu: tumerekodi {symptom}. Piga 719 kama unajihisi mgonjwa zaidi.',
		'callback': (
			'Afya Yangu: tumerekodi {symptom}. Mhudumu wa afya atakupigia. '
			'Piga 719 kama unajihisi mgonjwa zaidi.'
		),
	},
}


def follow_up_message(symptom_label: str | None, lang: str = 'en', callback_requested: bool = False) -> str:
	"""The §CHAN-1 follow-up sentence for one report, in `answerable`'s language.

	`callback_requested` picks between two sentences rather than adding a clause, because the two say
	different things to a person who is waiting: one is a record, the other is a promise that someone
	will ring. `USSD_CLOSE` draws the same distinction for the screen, and a follow-up that blurred it
	would be the sentence the person keeps contradicting the one they just read.

	The label is `None` on a report that carried no menu — the fallback names the report rather than
	inventing a symptom, which is the rule `ChannelReport` already holds: a report names what was
	actually said.
	"""
	assert lang, 'a follow-up is written in some language'
	table = FOLLOW_UP_STRINGS[answerable(lang)]
	key = 'callback' if callback_requested else 'plain'
	subject = table['symptom'].format(symptom=symptom_label) if symptom_label else table['no_symptom']
	return table[key].format(symptom=subject)


# Every sentence this module composes is inside the bound it states, checked at import so a bad edit
# fails here rather than in a person's message. This is the one place the measurement *acts*, and it
# acts on the strings this module owns — the rest of the tree is reported through `SmsOut.plain`.
for _lang, _table in FOLLOW_UP_STRINGS.items():
	for _key in ('plain', 'callback'):
		_reading = plain_language(
			_table[_key].format(symptom=_table['symptom'].format(symptom='Kutokwa na damu')))
		assert _reading.plain, f'the {_lang} {_key} follow-up is not plain: {_reading.findings}'


class OutboundReading(BaseModel):
	"""One outbound string table's reading, named so a finding says which surface it is on."""

	model_config = MODEL_CONFIG
	surface: str
	lang: str
	strings: int = Field(ge=0)
	worst_sentence_words: int = Field(ge=0)
	worst_word: str
	worst_word_chars: int = Field(ge=0)
	over_the_ceiling: list[str]


def _outbound_tables() -> list[tuple[str, dict[str, str]]]:
	"""Every outbound string table this tree composes a message from, as (surface, strings).

	Read off `afya.strings` by walking it, rather than from a hand-written list: a table added for a
	new outbound use case arrives here without anyone remembering to add it twice — the rule
	`test_operator_scopes_match_the_routes` established for scopes.

	The walk is recursive because the tables are nested to different depths and in two shapes — a
	flat `{key: sentence}` (`CALLBACK_ACK`) and a `{lang: {key: sentence}}` (`TRAVELLER_STRINGS`),
	with `USSD_MENU_ANSWERS` a third (`{lang: {int: sentence}}`). A walker that handled one shape is
	the checker that enumerates one of the ways the thing it checks can be written: the flat-only
	version reports **15 tables and 30 strings**, silently skipping the fifteen nested tables that
	carry the clinical advice, against **30 tables and 191 strings** here. A gate that loses 15 of
	its 30 tables and 161 of its 191 strings without failing is the failure mode this walk exists to
	avoid — and it was written, caught and rewritten inside this unit, which is why the canary that
	reverts it is the one worth keeping.

	**A string is a message when it holds a space.** That is the property, not a name filter: a
	language *code* (`SMS_LANG_PREFIXES`) and most language *names* (`LANGUAGE_NAME_FOR`) live in the
	same module as the sentences and are not sentences. Excluding them by name would be a list to
	maintain and would silently drop the next such table; requiring two words is true of every message
	and of all but two of those, so the rule holds without being told what to look for.

	Two names survive it — `Luhya (Bukusu)` and `Luhya (Maragoli)`, the only multi-word entries in a
	vocabulary table — so those two tables are named in `NOT_A_MESSAGE` below, with the staleness
	check `test_ui_vocabulary.py` uses for `UNGATED_WRITES`: the list must name tables that exist, and
	every one of them must be a table the property would otherwise have admitted. A named exception
	that is asserted in both directions is a different thing from a filter nobody re-reads.
	"""
	from afya import strings

	surfaces: list[tuple[str, dict[str, str]]] = []

	def collect(obj: object, path: str, out: dict[str, str]) -> None:
		if isinstance(obj, str):
			if ' ' in obj:
				out[path] = obj
			return
		if isinstance(obj, dict):
			for key, value in obj.items():
				collect(value, f'{path}.{key}', out)
			return
		if isinstance(obj, (list, tuple, frozenset, set)):
			for i, value in enumerate(obj):
				collect(value, f'{path}[{i}]', out)

	for name in dir(strings):
		if not name.isupper() or name in NOT_A_MESSAGE:
			continue
		obj = getattr(strings, name)
		if not isinstance(obj, (dict, tuple, list)):
			continue
		found: dict[str, str] = {}
		collect(obj, name, found)
		if found:
			surfaces.append((f'afya.strings:{name}', found))
	return surfaces


def plain_language_report() -> list[OutboundReading]:
	"""§CHAN-1's Format bullet as the deployment reads it: every outbound table, measured.

	Served rather than kept internal because the bullet is a property of *every* message the channel
	sends, and a property checked only where this module writes the string is a property checked in
	one place. The ceiling is the module's, so a table that drifts past it shows up here with the
	sentence named — which is the difference between a bound and a comment about one.
	"""
	readings: list[OutboundReading] = []
	for surface, table in _outbound_tables():
		over: list[str] = []
		worst_sentence = 0
		worst_word = ''
		for key, text in sorted(table.items()):
			reading = plain_language(text)
			worst_sentence = max(worst_sentence, reading.longest_sentence_words)
			if reading.longest_word_chars > len(worst_word):
				worst_word = reading.longest_word
			if not reading.plain:
				over.append(f'{key}: {"; ".join(reading.findings)}')
		readings.append(OutboundReading(
			surface=surface, lang=surface.rsplit('.', 1)[-1], strings=len(table),
			worst_sentence_words=worst_sentence, worst_word=worst_word,
			worst_word_chars=len(worst_word), over_the_ceiling=over,
		))
	assert readings, 'the tree composes outbound messages and the report must see them'
	return readings
