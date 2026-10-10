"""Real-time delivery models (spec §15.5).

§15.5 asks for WebSocket "for real-time alerts". The alerts in question are ALT-001's community
feed, so the wire format is deliberately thin: a subscriber says which county and which
categories it wants, and the server sends one `SocketEvent` per delivery. Nothing here carries a
feature id, and nothing here carries a subject reference — a socket is not a place to learn who
else is listening.
"""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from afya.alerting.views import FEED_SCOPED_PREFERENCES, FeedItem, governing_preference

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# Every preference a subscriber may name. The reminder and advice categories are excluded: no
# feed item is ever governed by "medication_reminders", so accepting it would promise a delivery
# that could not happen.
KNOWN_CATEGORIES: frozenset[str] = FEED_SCOPED_PREFERENCES

# A socket that cannot drain its queue is closed rather than buffered. An alert that arrives ten
# minutes late, after the person has already walked past the water point, is worse than a client
# that reconnects and pulls the feed.
SOCKET_QUEUE_DEPTH = 64
SOCKET_PING_INTERVAL_SECONDS = 30


def now_iso() -> str:
	return datetime.now(timezone.utc).isoformat(timespec='seconds')


class SocketSubscription(BaseModel):
	"""What one connection asked to hear. `county=None` means every county.

	`categories` are *preference* names, not feed categories: a person subscribes to "disease
	alerts", and the feed item that arrives says "outbreak". `FEED_PREFERENCE` is the mapping.
	"""
	model_config = MODEL_CONFIG
	county: str | None = None
	categories: list[str] = Field(default_factory=lambda: sorted(KNOWN_CATEGORIES))
	enabled: bool = True

	def wants(self, item: FeedItem) -> bool:
		"""Whether this subscriber should receive `item`.

		Only toggleable preferences appear here, because every feed category is governed by one.
		The critical categories (`exposure_notification`, `immediate_danger`) are deliberately not
		reachable through this socket: they are delivered per subject by
		`AlertingService.notify_exposure`, and broadcasting one to a county-wide socket would
		tell every listener that a named individual had been exposed.
		"""
		if not self.enabled:
			return False
		if not (self.county is None or item.county in (None, self.county)):
			return False
		return governing_preference(item.category) in self.categories


class SocketEvent(BaseModel):
	"""One frame. `kind` is the only field a client switches on."""
	model_config = MODEL_CONFIG
	kind: Literal['hello', 'alert', 'pong', 'error']
	at_iso: str
	subscription: SocketSubscription | None = None
	item: FeedItem | None = None
	message: str | None = None


class SocketStats(BaseModel):
	"""Connection counts for operators. Deliberately aggregate: a socket registry that reported
	per-connection detail would be a list of who is listening to which county."""
	model_config = MODEL_CONFIG
	connections: int
	counties: int
	delivered: int
