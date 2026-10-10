"""Alerting services (spec §9.6 ALT-003, §10.3 ALT-001/002, §11.8 ALT-004).

Verification is structural: an unverified item cannot enter the feed, and the critical
categories in ALT-003 have no toggle at all rather than a toggle that is merely ignored.
"""
from afya.alerting.views import (
	CRITICAL, TOGGLEABLE, AlertPreferences, ExposureAck, ExposureNotification, FamilyStatus,
	FeedItem, PreferenceReceipt,
)
from afya.logmixin import LogMixin

EXPOSURE_BODY = (
	'You may have been in contact with a confirmed case. Please self-monitor for 21 days. '
	'Call 719 if you develop fever or feel unwell. Tap for more information.'
)


class AlertingService(LogMixin):
	def __init__(self) -> None:
		self._feed: list[FeedItem] = []
		self._prefs: dict[str, AlertPreferences] = {}
		self._checkins: dict[str, dict[str, str]] = {}
		self._family: dict[str, set[str]] = {}
		self._exposures: dict[str, ExposureNotification] = {}
		assert self._feed == [] and self._prefs == {}

	# --- ALT-001 community alert feed -----------------------------------------------------

	async def publish(self, item: FeedItem) -> FeedItem:
		assert item.verified, 'unverified items must not reach the feed (§ALT-001)'
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

	async def check_in(self, subject_ref: str, family_ref: str, at_iso: str) -> FamilyStatus:
		assert family_ref in self._family, 'unknown family group'
		assert subject_ref in self._family[family_ref], 'not a member of this family group'
		self._checkins.setdefault(family_ref, {})[subject_ref] = at_iso
		self._log_info('safety check-in', subject=subject_ref, family=family_ref)
		return self.family_board(family_ref)

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
		import hashlib
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
