"""Alerting services (spec §9.6 ALT-003, §10.3 ALT-001/002, §11.8 ALT-004).

Verification is structural: an unverified item cannot enter the feed, and the critical
categories in ALT-003 have no toggle at all rather than a toggle that is merely ignored.
"""
import hashlib
import re
from typing import Awaitable, Callable

from afya.alerting.views import (
	CRITICAL, TOGGLEABLE, AlertPreferences, ExposureAck, ExposureNotification, FamilyStatus,
	FeedItem, PreferenceReceipt, SafetyCheckIn,
)
from afya.logmixin import LogMixin
from afya.strings import (
	SMS_FAMILY_BOARD, SMS_FAMILY_BOARD_ALL, SMS_FAMILY_MANY_GROUPS, SMS_FAMILY_NO_GROUP,
	SMS_FAMILY_NOT_SAFE, SMS_FAMILY_SAFE, SMS_FAMILY_THIRD_PARTY, SMS_FAMILY_UNKNOWN_GROUP,
	SMS_SAFE_KEYWORDS, answerable,
)

EXPOSURE_BODY = (
	'You may have been in contact with a confirmed case. Please self-monitor for 21 days. '
	'Call 719 if you develop fever or feel unwell. Tap for more information.'
)


# How a check-in reaches a family member who is not on the app. §5.3's channel service owns the
# gateway and the zero-rating rule, so this is the *one* method this module needs from it — a port
# rather than an import, for the reason `EmergencyService.SmsPort` is one: the channel layer imports
# the triage engine and the identity model, and `afya.channels` importing `afya.alerting` back would
# be a cycle for a single call.
SmsPort = Callable[[str, str], Awaitable[object]]

# Words that turn a keyword back into its opposite. "I am not safe" contains "safe", and a substring
# test would file it as a check-in — telling a family their relative is accounted for on the strength
# of a message that says the opposite. That is the one error here worse than silence, so the match is
# on word sequences with the word before the keyword read, not on `'safe' in body`.
# Kiswahili negates inside the verb, so the word before the keyword is not the only carrier: `hatuko
# salama` is "we are not safe" and `hayuko`/`siko` are the same for one person. All of them are here,
# because this is the direction where a miss tells a family the opposite of what they were sent.
# Words that put the safety in the message on somebody else. A message framed by one of these is
# answered rather than filed: the sender may be relaying good news about a relative, and marking the
# sender safe on the strength of it is the negation error one step removed.
_THIRD_PARTY = frozenset({
	'my', 'his', 'her', 'their', 'our', 'your', 'brother', 'sister', 'mother', 'father', 'mum',
	'dad', 'son', 'daughter', 'wife', 'husband', 'family', 'kaka', 'dada', 'mama', 'baba', 'ndugu',
})

# A negation glued to the keyword, which is how both languages do it: "unsafe" in English, and in
# Kiswahili the negative is a prefix on the verb, so `hatusalama` is one word where `hatuko salama`
# is two. Without this, "unsafe" matches no keyword at all and falls through to the welcome menu —
# the same fall-through the live probe caught for the two-word form.
_NEG_PREFIXES = ('un', 'not', 'hatu', 'hawa', 'haku', 'bado', 'sio', 'si')

_NEGATIONS = frozenset({
	'not', 'no', 'never', 'without', 'bado', 'si', 'sio', 'hatuko', 'hatupo', 'hayuko', 'hako',
	'siko', 'sipo', 'hawako', 'hawa', 'haku',
})


def _words(text: str) -> tuple[str, ...]:
	"""A message as comparable words. Punctuation and case are the sender's, not the product's."""
	return tuple(re.findall(r'[a-z0-9]+', text.lower()))


def safe_intent(body: str) -> str:
	"""What an inbound message that mentions safety is *about*: `check-in`, `third-party`, or `none`.

	Three answers rather than a boolean, because the two failures here need different replies and
	collapsing them would make one of them silent:

	* **A negation is not a check-in, and it is not nothing either.** "I am not safe" contains "safe",
	  and a substring test would file it as one — telling a family their relative is accounted for on
	  the strength of a message that says the opposite. That is the one error here worse than silence,
	  so the word before the keyword is read; and the answer is the 719 line rather than the fall-through
	  the live probe caught, where a person saying they are in danger got the welcome menu.
	* **A report about someone else is not a check-in either.** "My brother is safe" would mark the
	  *sender* safe, which is the same error one step removed, and no keyword list can tell the two
	  apart from the framing alone. It is answered with a question instead of being filed.

	`SMS_SAFE_KEYWORDS` is matched as a contiguous *word sequence*, so "unsafe" is not "safe" and
	"niko salama" is found where "salama" inside a longer word would have been read as a hit. A group
	name appended to a check-in does not break the match: the sequence only has to appear, and
	`_group_named_in` is what decides which group the extra words name.
	"""
	words = _words(body)
	for keyword in SMS_SAFE_KEYWORDS:
		k = _words(keyword)
		for i in range(len(words) - len(k) + 1):
			if words[i:i + len(k)] != k:
				continue
			if i and words[i - 1] in _NEGATIONS:
				# Its own answer, not `none`. A message that says the opposite of safe is not a message
				# the keyword map can act on, and the live probe found what happened when it fell
				# through: a person saying they are in danger was answered with the welcome menu.
				return 'negated'
			if set(words[:i]) & _THIRD_PARTY:
				return 'third-party'
			return 'check-in'
	for word in words:
		for prefix in _NEG_PREFIXES:
			stem = word[len(prefix):]
			if word.startswith(prefix) and stem and any(stem == w for k in SMS_SAFE_KEYWORDS for w in _words(k)):
				return 'negated'
	return 'none'


def safe_reply(body: str) -> bool:
	"""Whether an inbound message is the sender's own check-in. `safe_intent` is the whole rule."""
	return safe_intent(body) == 'check-in'


class AlertingService(LogMixin):
	def __init__(self, sms: SmsPort | None = None,
	             msisdn_of: Callable[[str], str | None] | None = None) -> None:
		# Both are late-bound callables rather than objects, because `build_services` builds the
		# alerting service before the channel and identity services exist — §LOC-001's zone registry
		# is wired the same way. A deployment with neither wired still checks people in and still
		# serves the board; it reports `sms_sent=0` and says so, rather than claiming a fan-out it
		# cannot make.
		self._sms = sms
		self._msisdn_of = msisdn_of
		self._feed: list[FeedItem] = []
		self._prefs: dict[str, AlertPreferences] = {}
		self._checkins: dict[str, dict[str, str]] = {}
		# §ALT-002's check-ins as records rather than as board entries. The board answers "who is
		# safe" and this answers "how did they say so", which is the question §5.4's channel
		# reporting and §ALT-002's own SMS bullet both ask.
		self._checkins_log: list[SafetyCheckIn] = []
		self._family: dict[str, set[str]] = {}
		self._exposures: dict[str, ExposureNotification] = {}
		assert self._feed == [] and self._prefs == {}

	# --- ALT-001 community alert feed -----------------------------------------------------

	async def publish(self, item: FeedItem) -> FeedItem:
		# §ALT-001's verification rule, named here rather than in the message a caller reads back.
		assert item.verified, 'an unverified item must not reach the feed'
		assert item.source, 'source attribution is mandatory'
		self._feed.append(item)
		self._log_info('feed item published', category=item.category, county=item.county)
		return item

	def feed(self, county: str | None = None, since_iso: str | None = None) -> list[FeedItem]:
		rows = [i for i in self._feed if county is None or i.county in (None, county)]
		if since_iso is not None:
			rows = [i for i in rows if i.published_iso > since_iso]
		return sorted(rows, key=lambda i: i.published_iso, reverse=True)

	def feed_revision(self, county: str | None = None) -> str:
		"""§16.4 content caching. A short digest of what this subscriber would be served.

		A revision of the *served* set, not of the whole feed: a client filtering on one county must
		not be told to re-download because an unrelated county got an item. Derived from content
		rather than a counter so it is identical after a restart and carries no item count.
		"""
		import hashlib
		body = '\x1f'.join(f'{i.item_id}|{i.published_iso}' for i in self.feed(county))
		return hashlib.sha256(body.encode()).hexdigest()[:16]

	# --- ALT-003 personalised preferences -------------------------------------------------

	def _ensure(self, subject_ref: str) -> AlertPreferences:
		if subject_ref not in self._prefs:
			self._prefs[subject_ref] = AlertPreferences(subject_ref=subject_ref, enabled={c: True for c in TOGGLEABLE})
		return self._prefs[subject_ref]

	def set_preference(self, subject_ref: str, category: str, enabled: bool) -> PreferenceReceipt:
		prefs = self._ensure(subject_ref)
		if category in CRITICAL:
			return PreferenceReceipt(
				subject_ref=subject_ref, category=category, enabled=True, critical=True,
				message='This alert cannot be switched off — it tells you about a real danger to your health.',
			)
		assert category in TOGGLEABLE, f'unknown alert category {category}'
		prefs.enabled[category] = enabled
		self._log_info('alert preference set', subject=subject_ref, category=category, enabled=enabled)
		return PreferenceReceipt(
			subject_ref=subject_ref, category=category, enabled=enabled, critical=False,
			message=f'{category.replace("_", " ").title()} alerts {"on" if enabled else "off"}.',
		)

	def preferences(self, subject_ref: str) -> AlertPreferences:
		return self._ensure(subject_ref)

	def should_deliver(self, subject_ref: str, category: str) -> bool:
		"""Critical categories always deliver; everything else honours the toggle."""
		if category in CRITICAL:
			return True
		return self._ensure(subject_ref).enabled.get(category, True)

	# --- ALT-002 family safety check-in ---------------------------------------------------

	def link_family(self, family_ref: str, members: list[str]) -> FamilyStatus:
		assert members, 'a family group needs at least one member'
		self._family[family_ref] = set(members)
		return self.family_board(family_ref)

	def is_member(self, family_ref: str, subject_ref: str) -> bool:
		"""§ALT-002: the board names its members' subjects, so only a member may read it."""
		return subject_ref in self._family.get(family_ref, set())

	async def check_in(self, subject_ref: str, family_ref: str, at_iso: str, lang: str = 'en',
	                   notify: bool = True, channel: str = 'native',
	                   note: str | None = None) -> FamilyStatus:
		"""§ALT-002's "I'm safe" button, and the "notifies linked family members" half of it.

		The check-in is recorded first and the fan-out second, so a gateway that refuses every message
		still leaves the board correct — the person *is* safe whatever the carrier did with the text,
		and a check-in lost because an SMS failed would be the button failing at the moment it
		matters.

		The members who are **not on the app** are the ones the messages go to. A member who has
		already checked in has, by definition, reached the service by some route and does not need
		texting; §5.4's identity model is what decides who that is, and a subject with no phone on
		file is reported as unreachable rather than silently skipped.
		"""
		assert family_ref in self._family, 'unknown family group'
		assert subject_ref in self._family[family_ref], 'not a member of this family group'
		self._checkins.setdefault(family_ref, {})[subject_ref] = at_iso
		# The `SafetyCheckIn` record itself, which until now was a model with no writer: the board
		# kept a bare timestamp per member and the check-in's own id, note and channel had nowhere
		# to go. `channel` is what makes §ALT-002's SMS leg auditable after the fact — a deployment
		# asked to show that the feature works without data can show which check-ins arrived that
		# way, and a board that stored only the time could not.
		checkin_id = self._checkin_id(subject_ref, at_iso)
		if not any(c.checkin_id == checkin_id for c in self._checkins_log):
			# Keyed by the derived id rather than appended blindly: a gateway that retries, or a
			# queued client that resends, is one act and must not read as two on the record either.
			self._checkins_log.append(SafetyCheckIn(
				checkin_id=checkin_id, subject_ref=subject_ref, at_iso=at_iso,
				channel=channel, note=note,
			))
		self._log_info('safety check-in', subject=subject_ref, family=family_ref, channel=channel)
		board = self.family_board(family_ref)
		sent, unreachable = await self._notify_family(family_ref, board, lang) if notify else (0, [])
		# The body is composed either way. It is the message, not the receipt — `sms_sent` is what
		# says whether it went — and a board that carried an empty string whenever nothing was sent
		# would leave a client rendering a blank line where the person's own check-in is confirmed.
		return board.model_copy(update={
			'sms_sent': sent, 'sms_unreachable': unreachable,
			'sms_body': self._family_sms_body(board, lang),
		})

	async def _notify_family(self, family_ref: str, board: FamilyStatus,
	                         lang: str) -> tuple[int, list[str]]:
		"""Text every member who has not checked in, and name the ones a message could not reach.

		The sender is not texted: the board is built *after* their check-in is written, so they are
		already in `members_safe` and never reach this loop. An earlier cut skipped them explicitly
		inside it — a branch that could not change any answer, because the only way to enter it was to
		be both safe and unaccounted for. Removed rather than left as a guard nobody can trip.
		"""
		if self._sms is None or self._msisdn_of is None:
			self._log_warn('family check-in has no SMS path wired', family=family_ref)
			return 0, []
		body = self._family_sms_body(board, lang)
		sent = 0
		unreachable: list[str] = []
		for member in board.members_unknown:
			number = self._msisdn_of(member)
			if number is None:
				unreachable.append(member)
				# "Cannot be reached", not "no phone on file". The live probe printed the second for a
				# member whose number is a Nairobi landline, which sends an operator looking for a
				# missing field that is not missing. The service cannot tell the two apart — the
				# deployment's port returns None for both, and a second identity read here would be a
				# second answer to "can this person be texted" — so it reports the fact it does know.
				self._log_warn('family member cannot be reached by SMS', family=family_ref)
				continue
			try:
				await self._sms(number, body)
			except Exception as exc:  # one dead leg must not silence the others
				unreachable.append(member)
				self._log_error('family SMS failed', family=family_ref, error=str(exc))
				continue
			sent += 1
		return sent, unreachable

	def _family_sms_body(self, board: FamilyStatus, lang: str) -> str:
		"""The one message, composed from the board's own counts.

		It carries the counts and not the members' subjects: an SMS lands on a handset that may be
		shared, and a list of subject references would put §17.2's personal data in plain text to a
		number the server has not verified belongs to the person who asked for it.
		"""
		served = answerable(lang)
		total = len(board.members_safe) + len(board.members_unknown)
		if board.members_unknown:
			summary = SMS_FAMILY_BOARD[served].format(safe=len(board.members_safe), total=total)
		else:
			summary = SMS_FAMILY_BOARD_ALL[served].format(total=total)
		return SMS_FAMILY_SAFE[served].format(board=summary)

	@staticmethod
	def _checkin_id(subject_ref: str, at_iso: str) -> str:
		"""A stable reference for a check-in, derived rather than random.

		`SafetyCheckIn.checkin_id` is `SAFE-` plus eight or more uppercase alphanumerics, and deriving
		it from the subject and the instant makes a replay of the same check-in — an SMS gateway that
		retries, a client that queues and resends — land on the same id instead of minting a second
		check-in for one act. A person pressing the button once must not appear twice on a board whose
		whole purpose is counting who is accounted for.
		"""
		digest = hashlib.sha256(f'{subject_ref}:{at_iso}'.encode()).hexdigest()
		return 'SAFE-' + digest[:16].upper()

	def checkins(self, family_ref: str | None = None) -> list[SafetyCheckIn]:
		"""Every check-in recorded, optionally for one group. §ALT-002's own record of the feature."""
		if family_ref is None:
			return list(self._checkins_log)
		return [c for c in self._checkins_log if c.subject_ref in self._family.get(family_ref, set())]

	def family_of(self, subject_ref: str) -> list[str]:
		"""Every family group this subject belongs to, in a stable order.

		§ALT-002's board is per group and the SMS path has no group to read off a free-text message,
		so the groups are resolved from the sender's own number. A person in two groups gets asked
		which one rather than being guessed into the wrong one — a check-in filed against the wrong
		family is a family told the wrong thing.
		"""
		return sorted(ref for ref, members in self._family.items() if subject_ref in members)

	async def check_in_by_msisdn(self, msisdn: str, body: str, at_iso: str,
	                             lang: str = 'en') -> str:
		"""§ALT-002's "Works over SMS when data is unavailable", as an inbound message.

		Returns the reply text and never raises for a message it cannot act on: an SMS that gets no
		answer is indistinguishable from a network that dropped it, so every branch answers. The
		refusals are answers — an unlinked number is told it is unlinked and given the 719 line,
		which is more than silence would have told them.
		"""
		assert isinstance(body, str) and body.strip(), 'an inbound SMS needs a body'
		served = answerable(lang)
		if safe_intent(body) == 'negated':
			# Answered before anything is looked up: the message is not a check-in, so whether the
			# sender's number is linked is not the question that decides the reply.
			return SMS_FAMILY_NOT_SAFE[served]
		if safe_intent(body) == 'third-party':
			# Answered before anything is looked up: the message is not the sender's own check-in, so
			# whether their number is linked is not the question that decides the reply.
			return SMS_FAMILY_THIRD_PARTY[served]
		if self._msisdn_of is None:
			return SMS_FAMILY_NO_GROUP[served]
		# The same one-way edge the fan-out uses, read backwards: §5.4's index maps a subject to a
		# phone, and this needs the reverse. Built by scanning the subjects we can see rather than by
		# a second index, because a second index is a second answer to "who is this number".
		subject = None
		for ref in {m for members in self._family.values() for m in members}:
			if self._msisdn_of(ref) == msisdn:
				subject = ref
				break
		if subject is None:
			self._log_info('inbound family SMS from an unlinked number')
			return SMS_FAMILY_NO_GROUP[served]
		groups = self.family_of(subject)
		named = self._group_named_in(body, groups)
		if named is None:
			# A group was named and it is not one of the sender's. Refused by name rather than filed
			# against their own: a check-in addressed to somebody else's family, recorded as this
			# person's, tells two families the wrong thing at once.
			if self._group_named_in(body, sorted(self._family)) is not None:
				return SMS_FAMILY_UNKNOWN_GROUP[served]
			# Nothing named and more than one group possible: ask which. With exactly one group there
			# is nothing to ask — the person said they are safe, and which group they meant is not in
			# doubt, so trailing words ("safe please") are not read as a name at all.
			if len(groups) > 1:
				return SMS_FAMILY_MANY_GROUPS[served]
			named = groups[0]
		try:
			board = await self.check_in(subject, named, at_iso, lang, notify=True, channel='sms')
		except AssertionError:
			return SMS_FAMILY_UNKNOWN_GROUP[served]
		self._log_info('family check-in by SMS', family=named)
		# The board's own `sms_body`, so the reply and the message the family received are one string
		# composed once — a second call to the composer is a second chance for them to differ.
		return board.sms_body

	@staticmethod
	def _group_named_in(body: str, refs: list[str]) -> str | None:
		"""Which of `refs` the message names, or None when it names none of them.

		Case-insensitive, and a substring of the body because the sender appends the name to the
		keyword: "SAFE KARIBU" is a check-in for the group called `karibu`. Callers pass either the
		sender's own groups — to find the one meant — or every group on record, to tell "named nothing"
		from "named somebody else's".
		"""
		text = body.lower()
		for ref in refs:
			if ref.lower() in text:
				return ref
		return None

	def family_board(self, family_ref: str) -> FamilyStatus:
		members = self._family.get(family_ref, set())
		seen = self._checkins.get(family_ref, {})
		safe = sorted(m for m in members if m in seen)
		unknown = sorted(m for m in members if m not in seen)
		last = max(seen.values()) if seen else None
		board = (
			f'{len(safe)} of {len(members)} checked in safe.'
			if unknown else f'Everyone in this group has checked in safe ({len(safe)}).'
		)
		return FamilyStatus(family_ref=family_ref, members_safe=safe, members_unknown=unknown, last_checkin_iso=last, board=board)

	# --- ALT-004 exposure notification ----------------------------------------------------

	async def notify_exposure(self, subject_ref: str, case_ref: str | None = None) -> ExposureNotification:
		"""Critical, non-disableable. Never names the case; routes through the trusted proxy."""
		from uuid6 import uuid7
		seed = f'{subject_ref}:{case_ref or ""}:{uuid7()}'
		notification = ExposureNotification(
			notification_id='EXP-' + hashlib.sha256(seed.encode()).hexdigest()[:12].upper(),
			subject_ref=subject_ref,
			headline='Possible exposure — please read',
			body=EXPOSURE_BODY,
			delivery_channels=['native', 'sms', 'whatsapp'],
			enrols_monitoring=True,
			callback_offered=True,
		)
		self._exposures[notification.notification_id] = notification
		self._log_warn('exposure notification sent', subject=subject_ref)
		return notification

	async def acknowledge(self, ack: ExposureAck) -> ExposureNotification:
		assert ack.notification_id in self._exposures, 'unknown notification'
		note = self._exposures[ack.notification_id]
		note.acknowledged = True
		if ack.request_callback:
			self._log_info('callback requested', notification=ack.notification_id)
		return note

	def exposure(self, notification_id: str) -> ExposureNotification:
		assert notification_id in self._exposures, 'unknown notification'
		return self._exposures[notification_id]
