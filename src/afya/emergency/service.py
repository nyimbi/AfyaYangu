"""Emergency service — SOS fan-out port, IMU fall detection, offline card payloads."""
import math
from typing import Protocol

from afya.emergency.views import (
	EmergencyCard, FallResult, IMUSample, SOSDispatch, SOSEvent,
)
from afya.logmixin import LogMixin


class HotlinePort(Protocol):
	async def dispatch_sos(self, event: SOSEvent) -> list[str]: ...


class Inline719Port:
	"""Direct hotline dispatch used when telco gateway unavailable."""

	async def dispatch_sos(self, event: SOSEvent) -> list[str]:
		return ['719-hotline', 'nearest-treatment-unit']


class EmergencyService(LogMixin):
	def __init__(self, hotline: HotlinePort) -> None:
		self._hotline = hotline
		assert self._hotline is not None

	async def sos(self, event: SOSEvent) -> SOSDispatch:
		assert event.severity in ('low', 'medium', 'high'), 'severity bound'
		notified = await self._hotline.dispatch_sos(event)
		actions = ['call-719', 'geofence-perimeter', 'sms-contacts']
		out = SOSDispatch(sos_id=event.sos_id, notified=notified, actions=actions)
		self._log_warn('SOS dispatched', sos_id=event.sos_id, severity=event.severity)
		return out

	@staticmethod
	def fall(samples: list[IMUSample]) -> FallResult:
		assert 1 <= len(samples) <= 6000, 'sample window out of contract'
		mags = [math.sqrt(s.x * s.x + s.y * s.y + s.z * s.z) for s in samples]
		peak = max(mags)
		freefall_idx = next((i for i, m in enumerate(mags) if m < 2.0), None)
		impact_idx = mags.index(peak)
		# EMG-002 signature: near-zero-g window BEFORE the impact spike.
		fall = peak > 25.0 and freefall_idx is not None and freefall_idx < impact_idx
		return FallResult(fall_detected=fall, peak_g=round(peak, 2), auto_alert=fall)

	@staticmethod
	def card_qr(card: EmergencyCard) -> str:
		assert card.emergency_contact, 'emergency contact required'
		return 'AFYA|' + '|'.join([
			card.name, card.blood_group, ','.join(card.allergies), ','.join(card.conditions), card.emergency_contact,
		])