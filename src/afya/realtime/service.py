"""Real-time fan-out (spec §15.5).

The socket is a transport, not a second source of truth. A publisher writes to `AlertingService`
and hands the same `FeedItem` here; subscribers get it if their subscription matches. That
ordering matters: if the socket were authoritative, a person who was offline when the alert fired
would never see it, and §16.1 says every queued write must survive a restart.

`publish` is synchronous and never blocks on a slow client. A subscriber whose queue is full is
dropped rather than awaited — one stalled phone must not delay the alert for everyone else in the
county. The client reconnects and reads the REST feed, which is the durable path.
"""
import asyncio

from afya.alerting.views import FeedItem
from afya.logmixin import LogMixin
from afya.realtime.views import (
	SOCKET_QUEUE_DEPTH, SocketEvent, SocketStats, SocketSubscription, now_iso,
)


class Subscriber:
	"""One connection. Holds a bounded queue and the subscription it asked for."""

	def __init__(self, subscription: SocketSubscription) -> None:
		self.subscription = subscription
		self.queue: asyncio.Queue[SocketEvent] = asyncio.Queue(maxsize=SOCKET_QUEUE_DEPTH)
		self.dropped = 0
		self.closed = False

	def offer(self, event: SocketEvent) -> bool:
		"""Non-blocking. False means the client is too far behind and has been disconnected."""
		if self.closed:
			return False
		try:
			self.queue.put_nowait(event)
			return True
		except asyncio.QueueFull:
			self.dropped += 1
			self.closed = True
			return False


class RealtimeService(LogMixin):
	def __init__(self) -> None:
		self._subscribers: set[Subscriber] = set()
		self._delivered = 0
		assert self._subscribers == set() and self._delivered == 0

	def subscribe(self, subscription: SocketSubscription) -> Subscriber:
		sub = Subscriber(subscription)
		self._subscribers.add(sub)
		self._log_info('socket subscribed', county=subscription.county, categories=len(subscription.categories))
		return sub

	def unsubscribe(self, sub: Subscriber) -> int:
		"""Idempotent: a socket can close twice (client hang-up and server teardown)."""
		sub.closed = True
		removed = 1 if sub in self._subscribers else 0
		self._subscribers.discard(sub)
		assert removed <= 1
		return removed

	def hello(self, sub: Subscriber) -> SocketEvent:
		"""The first frame, so a client knows what it is actually subscribed to rather than
		assuming its request was honoured."""
		return SocketEvent(kind='hello', at_iso=now_iso(), subscription=sub.subscription)

	def publish(self, item: FeedItem) -> int:
		"""Fan an item out to matching subscribers. Returns how many received it."""
		assert item.verified, 'an unverified item must not reach a socket either (§ALT-001)'
		event = SocketEvent(kind='alert', at_iso=now_iso(), item=item)
		delivered = 0
		for sub in list(self._subscribers):
			if not sub.subscription.wants(item):
				continue
			if sub.offer(event):
				delivered += 1
			else:
				self._log_warn('socket dropped, client too far behind', dropped=sub.dropped)
				self.unsubscribe(sub)
		self._delivered += delivered
		if delivered:
			self._log_info('alert fanned out', category=item.category, county=item.county, delivered=delivered)
		return delivered

	def stats(self) -> SocketStats:
		counties = {s.subscription.county for s in self._subscribers}
		return SocketStats(connections=len(self._subscribers), counties=len(counties), delivered=self._delivered)

	def drop_all(self) -> int:
		"""Teardown for tests and shutdown. Returns how many connections were closed."""
		count = len(self._subscribers)
		for sub in list(self._subscribers):
			sub.closed = True
		self._subscribers.clear()
		return count
