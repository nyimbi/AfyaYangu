"""Emergency service — SOS fan-out, IMU fall detection, offline card payloads."""
import math
import re
from typing import Protocol

from afya.auth.views import now_ms as clock_ms
from afya.emergency.views import (
	EmergencyCard, FallResult, IMUSample, MedicalProfile, SOSAlert, SOSDispatch, SOSEvent,
)
from afya.facilities.views import Facility, NearestRequest
from afya.logmixin import LogMixin

# §EMG-001 prints no countdown figure. A number invented here would read as one the section states,
# so the duration is a deployment parameter with a default and it travels on the alert, where the
# client that owns the timer can read the same value the server will enforce.
DEFAULT_COUNTDOWN_S = 10

# What an SMS can actually reach. §EMG-003's card accepts any 7–15 digit number, which includes
# landlines and foreign mobiles, and a fan-out that counted those as delivered would report a
# contact told who was never told. Kenya's mobile ranges are `07xx` and `01xx`; the landline area
# codes (`020` Nairobi, `041` Nakuru, …) are the ones a person is most likely to have filed.
_KE_MOBILE = re.compile(r'^\+254[17]\d{8}$')
_KE_LOCAL = re.compile(r'^0([17]\d{8})$')


def _sms_dialable(number: str) -> str | None:
	"""The E.164 spelling an SMS gateway takes, or None when the number cannot receive one."""
	clean = number.replace(' ', '').replace('-', '')
	if _KE_MOBILE.match(clean):
		return clean
	local = _KE_LOCAL.match(clean)
	return f'+254{local.group(1)}' if local else None


def _sos_message(event: SOSEvent) -> str:
	"""§EMG-001's "preset message" — the one string every leg carries.

	No name is attached to the person in trouble: `SOSEvent` carries the *recipients'* contacts and
	nothing about the sender, and a message that said "Peter needs help" because Peter was the first
	contact would tell his family the wrong person was hurt. What the message can honestly carry is
	where and what, plus the maps link a responder can act on. GSM7 only, because §5.3's zero-rating
	and `segment_sms` both turn on it — an em dash or a degree sign here would be refused at the
	gateway, and this is the one message in the product that must not fail to send.
	"""
	link = f'https://www.google.com/maps/dir/?api=1&destination={event.lat},{event.lon}'
	bits = ['AFYA SOS: someone needs help.', f'Where: {event.lat},{event.lon}', link]
	if event.symptoms:
		bits.append('Symptoms: ' + ', '.join(event.symptoms[:4]) + '.')
	bits.append('Call 719.')
	return ' '.join(bits)


class HotlinePort(Protocol):
	async def dispatch_sos(self, event: SOSEvent) -> list[str]: ...


class AmbulancePort(Protocol):
	async def nearest_dispatch(self, lat: float, lon: float) -> str | None: ...


class SmsPort(Protocol):
	async def send_sms(self, msisdn: str, body: str) -> object: ...


class FacilityLookup(Protocol):
	"""§FND-001's finder, as the ambulance leg sees it.

	The real signature rather than `object`: a protocol with a looser parameter type is not
	implemented by the class that has the tighter one, so `FacilityService` would fail to satisfy it
	and the wiring would need a cast that hides exactly the mismatch the protocol is for.
	"""

	def find(self, req: NearestRequest) -> tuple[list[tuple[Facility, float]], list[str]]: ...


class Inline719Port:
	"""Direct hotline dispatch used when telco gateway unavailable."""

	async def dispatch_sos(self, event: SOSEvent) -> list[str]:
		return ['719-hotline', 'nearest-treatment-unit']


class FacilityAmbulancePort:
	"""§EMG-001's "nearest ambulance dispatch where integrated".

	Wrapped around §FND-001's finder rather than implemented beside it, because the facilities that
	have an ambulance *are* the facility registry — `Facility.ambulances` is §FND-002's own field,
	and a second list of ambulance bases would be a second answer to "where is the nearest one".
	The "where integrated" half is this class existing at all: a deployment with no facility registry
	passes no port and the leg reports itself absent rather than inventing a dispatch.
	"""

	def __init__(self, facilities: FacilityLookup) -> None:
		self._facilities = facilities

	async def nearest_dispatch(self, lat: float, lon: float) -> str | None:
		found, _ = self._facilities.find(
			NearestRequest(lat=lat, lon=lon, needs_ambulance=True, limit=1))
		return f'ambulance:{found[0][0].facility_id}' if found else None


class EmergencyService(LogMixin):
	"""§EMG-001's SOS, its countdown window, and §EMG-002's fall verdict.

	The four legs are separable on purpose. The hotline is §18.4's wire; the contacts are the
	section's own three, reached by SMS because that is the leg its bolded claim rests on; the
	ambulance is "where integrated"; and the profile is what the person attached. A leg that cannot
	run reports itself absent — the dispatch names it — rather than the whole alert failing, because
	the one thing an emergency path may not do is go quiet.
	"""

	def __init__(self, hotline: HotlinePort, sms: SmsPort | None = None,
	             ambulance: AmbulancePort | None = None,
	             countdown_s: int = DEFAULT_COUNTDOWN_S) -> None:
		self._hotline = hotline
		# §5.3's zero-rating is resolved by the channel service, so the emergency path sends through
		# it rather than around it: `send_sms` reads the carrier's rules at the moment of sending and
		# reports an unrated message, which is the §18.8 claim. A second SMS port here would be a
		# second place that decides what an emergency message costs, and the wrong one would be the
		# quiet one.
		self._sms = sms
		self._ambulance = ambulance
		self._countdown_s = countdown_s
		self._armed: dict[str, SOSAlert] = {}
		self._fired: dict[str, SOSDispatch] = {}
		assert self._hotline is not None and 0 <= countdown_s <= 60, 'countdown out of contract'

	# --- §EMG-001 the countdown ------------------------------------------------------------------

	def armed(self, sos_id: str) -> SOSAlert | None:
		"""One armed alert, or None. Read by the state route so a person can see what their tap did."""
		return self._armed.get(sos_id)

	def fired(self, sos_id: str) -> SOSDispatch | None:
		"""The dispatch for an alert that has gone out, or None while it has not."""
		return self._fired.get(sos_id)

	def arm(self, event: SOSEvent, at_ms: int | None = None) -> SOSAlert:
		"""Start the countdown. Nothing is sent until `fire`, which is the whole of the feature.

		The deadline is computed here and travels with the alert, so the client counts down to the
		server's instant rather than to its own — a device whose clock is a minute fast would
		otherwise show a window that had already closed.
		"""
		now = clock_ms() if at_ms is None else at_ms
		alert = SOSAlert(
			sos_id=event.sos_id, message=_sos_message(event), countdown_s=self._countdown_s,
			armed_at_ms=now, cancel_deadline_ms=now + self._countdown_s * 1000, event=event,
		)
		self._armed[alert.sos_id] = alert
		self._log_info('sos armed', sos_id=alert.sos_id, countdown_s=self._countdown_s)
		return alert

	def cancel(self, sos_id: str, at_ms: int | None = None) -> SOSAlert:
		"""§EMG-001's cancel. Refused past the deadline, and refused after it has gone out.

		A cancel that arrived late is the case this exists for: the person fumbled the phone, the
		countdown ran out, and the alert is already with their contacts and the hotline. Reporting
		that as cancelled would leave them believing nobody was told.
		"""
		alert = self._armed.get(sos_id)
		assert alert is not None, f'no armed alert {sos_id}'
		now = clock_ms() if at_ms is None else at_ms
		assert not alert.fired, 'this alert has already gone out and cannot be cancelled'
		assert now <= alert.cancel_deadline_ms, 'the countdown has closed'
		alert.cancelled = True
		self._log_info('sos cancelled', sos_id=sos_id)
		return alert

	async def fire(self, sos_id: str, at_ms: int | None = None) -> SOSDispatch:
		"""Send an armed alert, once. A replay returns the first dispatch rather than sending twice.

		Idempotence is not decoration on this route: §EMG-001's Offline note means the client may be
		replaying a queued alert over a link that dropped mid-request, and a second fan-out would
		text the same three people twice and ring the hotline again for one emergency.
		"""
		alert = self._armed.get(sos_id)
		assert alert is not None, f'no armed alert {sos_id}'
		if alert.fired:
			return self._fired[sos_id]
		assert not alert.cancelled, 'this alert was cancelled before it went out'
		now = clock_ms() if at_ms is None else at_ms
		assert now >= alert.armed_at_ms, 'an alert cannot fire before it was armed'
		out = await self._dispatch(alert)
		alert.fired = True
		self._fired[sos_id] = out
		return out

	# --- §EMG-001 the fan-out --------------------------------------------------------------------

	async def sos(self, event: SOSEvent) -> SOSDispatch:
		"""The one-tap path: arm and fire with no window, for a client that has none.

		§EMG-001's countdown is a client feature the section describes as "prevents accidental
		activation"; a caller that already knows the person meant it — a device that has been through
		its own confirm, or a replay of a queued alert — posts here and gets the fan-out directly.
		"""
		alert = self.arm(event)
		out = await self._dispatch(alert)
		alert.fired = True
		self._fired[alert.sos_id] = out
		return out

	async def _dispatch(self, alert: SOSAlert) -> SOSDispatch:
		event = alert.event
		assert event.severity in ('low', 'medium', 'high'), 'severity bound'
		notified = await self._hotline.dispatch_sos(event)
		reached, unreachable, sent = await self._text_contacts(event, alert.message)
		ambulance = await self._call_ambulance(event)
		actions = ['call-719', 'geofence-perimeter', 'sms-contacts']
		if ambulance:
			actions.append('call-ambulance')
		profile = MedicalProfile(
			blood_group=event.blood_group, allergies=event.allergies,
			conditions=event.conditions, medications=event.medications)
		out = SOSDispatch(
			sos_id=event.sos_id, message=alert.message, notified=notified,
			contacts_notified=reached, contacts_unreachable=unreachable,
			ambulance_dispatch=ambulance, sms_sent=sent,
			profile=None if profile.is_empty() else profile, actions=actions,
		)
		self._log_warn('SOS dispatched', sos_id=event.sos_id, severity=event.severity,
		               channel=event.channel, contacts=len(reached), sms=sent, ambulance=ambulance)
		return out

	async def _text_contacts(self, event: SOSEvent, message: str) -> tuple[list[str], list[str], int]:
		"""Text every contact the section allows, and say which ones a message could not reach.

		Sent whether the alert arrived over data or over SMS. §EMG-001 bolds "**Works over SMS when
		data is unavailable**" as a property of the whole feature, and the contacts leg is the one it
		is a claim about — a client with no data cannot POST at all, so the version of this that
		mattered is the one where the alert was relayed in and the fan-out still has to reach people
		who are not on the app.
		"""
		if not event.contacts:
			return [], [], 0
		assert self._sms is not None or not event.contacts, (
			'an SOS naming contacts needs a channel service to reach them')
		reached: list[str] = []
		unreachable: list[str] = []
		sent = 0
		for contact in event.contacts:
			target = _sms_dialable(contact.number)
			if target is None or self._sms is None:
				unreachable.append(contact.name)
				self._log_warn('emergency contact not reachable by SMS', name=contact.name)
				continue
			try:
				await self._sms.send_sms(target, message)  # type: ignore[attr-defined]
			except Exception as exc:  # one dead leg must not silence the others
				unreachable.append(contact.name)
				self._log_error('emergency SMS failed', name=contact.name, error=str(exc))
				continue
			reached.append(contact.name)
			sent += 1
		return reached, unreachable, sent

	async def _call_ambulance(self, event: SOSEvent) -> str | None:
		"""§EMG-001's "nearest ambulance dispatch where integrated", or None where it is not."""
		if self._ambulance is None:
			return None
		try:
			return await self._ambulance.nearest_dispatch(event.lat, event.lon)
		except Exception as exc:  # a registry that is down is not a reason to withhold the alert
			self._log_warn('ambulance lookup failed', error=str(exc))
			return None

	# --- §EMG-002 fall detection -----------------------------------------------------------------

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
		"""§EMG-003's card as a QR payload — the offline half of "lock-screen-accessible".

		A QR is read by whatever scanner the responding clinician has, so the payload carries all seven
		Contents rather than the five the model used to hold. Two deliberate choices: the emergency
		contacts are joined with `;` and each is `name:number`, because a bare number tells a clinician
		nothing about who they are ringing; and `organ_donor` is rendered `yes`/`no`/`unknown`, because
		the field is tri-state and collapsing "never said" into "no" is the one reading error on this
		card with a clinical consequence.
		"""
		assert card.emergency_contacts, 'at least one emergency contact is required (§EMG-003)'
		donor = {True: 'yes', False: 'no', None: 'unknown'}[card.organ_donor]
		return 'AFYA|' + '|'.join([
			card.name, card.blood_group, ','.join(card.allergies), ','.join(card.conditions),
			';'.join(f'{c.name}:{c.number}' for c in card.emergency_contacts),
			','.join(card.medications), donor, card.sha_number or '',
		])
