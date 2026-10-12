"""§EMG-001 — the SOS that had three of its five Features and a fan-out with one leg.

The section prints five Features and the code carried one and a half. `SOSEvent` held a position
and a severity; `sos` notified the 719 hotline and returned `['call-719', 'geofence-perimeter',
'sms-contacts']` — three strings naming three things it did not do. The contacts the section says
the alert goes to were not on the event, the preset message nobody composed was the string
`sms-contacts`, the ambulance leg did not exist, and the countdown was called "client state".

Each gate below is canaried against a planted defect in `canary_emg001.py`: a check that has never
been watched to fail is a check nobody has read.
"""
import httpx
import pytest

from afya.channels.service import AfricaTalkingSmsPort, ChannelService
from afya.emergency.service import (
	DEFAULT_COUNTDOWN_S, EmergencyService, FacilityAmbulancePort, Inline719Port, _sms_dialable,
)
from afya.emergency.views import EmergencyContact, SOSEvent
from afya.facilities.service import FacilityService
from afya.facilities.views import Facility, FacilityKind
from afya.service import build_services, create_app


def _svc() -> EmergencyService:
	"""A service wired the way `build_services` wires it, minus the telco client.

	The SMS leg is the real `ChannelService` over the real `AfricaTalkingSmsPort`, not a stub: the
	zero-rating resolution and the GSM7 segment check are two of the things this file asserts, and a
	fake gateway would pass both without either running.
	"""
	channels = ChannelService(AfricaTalkingSmsPort('https://api.africastalking.com', 'test-key'))
	return EmergencyService(Inline719Port(), channels)


def _event(**kw: object) -> SOSEvent:
	base: dict[str, object] = {'lat': -1.3, 'lon': 36.8, 'severity': 'high', 'symptoms': ['fever']}
	return SOSEvent(**{**base, **kw})  # type: ignore[arg-type]


# --- the fan-out the section prints ---------------------------------------------------------------

async def test_the_alert_reaches_the_contacts_the_section_names() -> None:
	"""§EMG-001: "Sends location and a preset message to up to three emergency contacts". The event
	carried no contacts and `sms-contacts` was a string in a list, so this is the bullet itself."""
	out = await _svc().sos(_event(contacts=[
		EmergencyContact(name='Peter', number='+254711222333'),
		EmergencyContact(name='Grace', number='0722333444'),
	]))
	assert out.contacts_notified == ['Peter', 'Grace'], out.contacts_notified
	assert out.sms_sent == 2
	assert not out.contacts_unreachable


async def test_the_contacts_cap_is_three_and_a_fourth_is_refused_not_dropped() -> None:
	"""The section says "up to three". Silently dropping a fourth would be a person who was never
	told and a receipt that said three."""
	with pytest.raises(Exception):
		_event(contacts=[EmergencyContact(name=f'C{i}', number='+254711222333') for i in range(4)])


async def test_a_number_that_cannot_receive_an_sms_is_reported_not_counted() -> None:
	"""§EMG-003's card accepts any 7–15 digit number, which includes landlines and foreign mobiles.
	A fan-out that counted those as delivered would report a contact told who was never told.

	The landline is in E.164 here and in local spelling in the unit gate below, so the two spellings
	are watched separately: a reachability test loosened to `^\\+254\\d{9}$` passes the local gate and
	fails this one, which is exactly the defect that shipped in the first version of `_sms_dialable`.
	"""
	out = await _svc().sos(_event(contacts=[
		EmergencyContact(name='Peter', number='+254711222333'),
		EmergencyContact(name='Landline', number='+254202712345'),
		EmergencyContact(name='Abroad', number='+14155552671'),
	]))
	assert out.contacts_notified == ['Peter']
	assert out.contacts_unreachable == ['Landline', 'Abroad']
	assert out.sms_sent == 1, 'the count is deliveries, not attempts'


def test_the_local_spelling_is_dialled_in_the_form_a_gateway_takes() -> None:
	"""A person types `0722333444`; the gateway needs `+254722333444`. `SmsOut.to_msisdn` refuses
	anything else by pattern, so getting this wrong is a 500 on the one route that must not fail.
	A landline is a real Kenyan number that cannot receive a text, and counting one as delivered
	would tell a person their mother had been alerted when nobody had rung her."""
	assert _sms_dialable('0722333444') == '+254722333444'
	assert _sms_dialable('0112222333') == '+254112222333'
	assert _sms_dialable('+254722333444') == '+254722333444'
	assert _sms_dialable('+254 722 333 444') == '+254722333444'
	assert _sms_dialable('0202712345') is None, 'a Nairobi landline takes no SMS'
	assert _sms_dialable('+254202712345') is None, (
		'the same landline in E.164 takes no SMS either — the mobile test is a prefix test, and a '
		'number that merely starts +254 is not a phone that can receive a text')
	assert _sms_dialable('+14155552671') is None, 'a foreign number is not a Kenyan gateway target'


async def test_the_preset_message_is_gsm7_so_it_can_be_zero_rated_and_segmented() -> None:
	"""§5.3's zero-rating and `segment_sms` both turn on GSM7, and this is the one message in the
	product that must not fail to send — an em dash or a degree sign here would be refused at the
	gateway. The message carries location and a maps link and names nobody: `SOSEvent` holds the
	recipients' contacts and nothing about the sender, so a name would be a guess."""
	from afya.channels.service import GSM7
	out = await _svc().sos(_event(contacts=[EmergencyContact(name='Peter', number='+254711222333')]))
	assert set(out.message) <= GSM7, ''.join(sorted(set(out.message) - GSM7))
	assert '-1.3,36.8' in out.message and 'google.com/maps' in out.message
	assert '719' in out.message and 'fever' in out.message


async def test_a_contact_leg_that_fails_does_not_silence_the_hotline_leg() -> None:
	"""The one thing an emergency path may not do is go quiet. A gateway that raises on one message
	must not take the fan-out down with it."""
	class Exploding:
		async def send_sms(self, msisdn: str, body: str) -> object:
			raise RuntimeError('gateway down')

	svc = EmergencyService(Inline719Port(), Exploding())
	out = await svc.sos(_event(contacts=[EmergencyContact(name='Peter', number='+254711222333')]))
	assert out.notified == ['719-hotline', 'nearest-treatment-unit'], 'the hotline leg still ran'
	assert out.contacts_unreachable == ['Peter']


# --- §EMG-001's "nearest ambulance dispatch where integrated" -------------------------------------

async def test_the_ambulance_leg_reads_the_facility_registry() -> None:
	"""The facilities that have an ambulance *are* the facility registry — `Facility.ambulances` is
	§FND-002's field. A second list of bases would be a second answer to "where is the nearest one"."""
	facilities = FacilityService()
	await facilities.upsert(Facility(
		facility_id='F-NAI-01', name='Kenyatta National Hospital', kind=FacilityKind.treatment_unit,
		county='Nairobi', lat=-1.301, lon=36.807, ambulances=4))
	svc = EmergencyService(Inline719Port(), _svc()._sms, FacilityAmbulancePort(facilities))
	out = await svc.sos(_event())
	assert out.ambulance_dispatch == 'ambulance:F-NAI-01'
	assert 'call-ambulance' in out.actions


async def test_a_registry_with_no_ambulance_reports_the_leg_absent_rather_than_inventing_one() -> None:
	"""The "where integrated" half of the bullet. A deployment with no facility registry passes no
	port and the dispatch says so; a facility with no ambulance filed is not a dispatch point."""
	facilities = FacilityService()
	await facilities.upsert(Facility(
		facility_id='F-NAI-02', name='A clinic', kind=FacilityKind.pharmacy,
		county='Nairobi', lat=-1.301, lon=36.807))
	svc = EmergencyService(Inline719Port(), _svc()._sms, FacilityAmbulancePort(facilities))
	out = await svc.sos(_event())
	assert out.ambulance_dispatch is None
	assert 'call-ambulance' not in out.actions
	# And with no port at all, the leg is absent rather than an error.
	none_out = await _svc().sos(_event())
	assert none_out.ambulance_dispatch is None


# --- §EMG-001's countdown -------------------------------------------------------------------------

def test_the_countdown_is_a_window_the_server_owns_and_the_deadline_travels() -> None:
	"""§EMG-001: "Countdown with cancel option (prevents accidental activation)". The device owns
	the timer — §ACC-004 wants no background polling and the section's Offline note wants the alert
	to work with no data — so what the server owns is the window and the instant it closes."""
	svc = _svc()
	alert = svc.arm(_event(), at_ms=1_000_000)
	assert alert.cancel_deadline_ms == 1_000_000 + DEFAULT_COUNTDOWN_S * 1000
	assert alert.countdown_s == DEFAULT_COUNTDOWN_S
	assert not alert.fired and not alert.cancelled


async def test_cancelling_before_the_deadline_stops_the_alert_going_out() -> None:
	"""The feature's whole purpose. A cancel that did not stop the fan-out would be worse than no
	cancel at all: the person believes nobody was told."""
	svc = _svc()
	alert = svc.arm(_event(contacts=[EmergencyContact(name='Peter', number='+254711222333')]),
	                at_ms=1_000_000)
	svc.cancel(alert.sos_id, at_ms=1_000_000 + 3_000)
	with pytest.raises(AssertionError, match='cancelled'):
		await svc.fire(alert.sos_id, at_ms=1_000_000 + 20_000)


def test_a_cancel_after_the_deadline_is_refused() -> None:
	"""A late cancel is the case this exists for: the person fumbled the phone and the alert is
	already with their contacts. Reporting that as cancelled would leave them believing nobody was
	told."""
	svc = _svc()
	alert = svc.arm(_event(), at_ms=1_000_000)
	with pytest.raises(AssertionError, match='countdown has closed'):
		svc.cancel(alert.sos_id, at_ms=1_000_000 + (DEFAULT_COUNTDOWN_S + 1) * 1000)


async def test_firing_twice_sends_once() -> None:
	"""§EMG-001's Offline note means a client may be replaying a queued alert over a link that
	dropped mid-request. A second fan-out would text the same three people twice and ring the
	hotline again for one emergency.

	Counted at the port, not by comparing the two dispatches: `SOSDispatch` is a value, so a second
	fan-out produces an equal one and `first == second` holds whether or not anyone was texted
	again. The count of messages that left the gateway is the only thing that distinguishes the two.
	"""
	class Counting:
		def __init__(self, inner: object) -> None:
			self._inner = inner
			self.sent: list[str] = []

		async def send_sms(self, msisdn: str, body: str) -> object:
			self.sent.append(msisdn)
			return await self._inner.send_sms(msisdn, body)  # type: ignore[attr-defined]

	port = Counting(_svc()._sms)
	svc = EmergencyService(Inline719Port(), port)  # type: ignore[arg-type]
	alert = svc.arm(_event(contacts=[EmergencyContact(name='Peter', number='+254711222333')]),
	                at_ms=1_000_000)
	first = await svc.fire(alert.sos_id, at_ms=1_000_000 + 11_000)
	second = await svc.fire(alert.sos_id, at_ms=1_000_000 + 12_000)
	assert first == second and second.sms_sent == 1
	assert port.sent == ['+254711222333'], 'one emergency is one text, however many times it is fired'


async def test_an_alert_cannot_fire_before_it_was_armed() -> None:
	"""A clock that runs backwards is a client bug, and firing on it would be a fan-out for an
	alert whose window never opened."""
	svc = _svc()
	alert = svc.arm(_event(), at_ms=1_000_000)
	with pytest.raises(AssertionError, match='before it was armed'):
		await svc.fire(alert.sos_id, at_ms=999_000)


# --- §EMG-001's optional medical profile attachment -----------------------------------------------

async def test_the_profile_is_attached_when_given_and_absent_when_not() -> None:
	"""The section's "optional medical profile attachment (blood group, allergies, conditions,
	medications)" — all four. Absent rather than an empty object, because an empty object on a
	receipt reads as "attached and blank"."""
	bare = await _svc().sos(_event())
	assert bare.profile is None
	out = await _svc().sos(_event(
		blood_group='O+', allergies=['penicillin'], conditions=['asthma'], medications=['salbutamol']))
	assert out.profile is not None
	assert (out.profile.blood_group, out.profile.allergies) == ('O+', ['penicillin'])
	assert out.profile.medications == ['salbutamol']


# --- the wire -------------------------------------------------------------------------------------

async def test_the_routes_serve_the_fan_out_the_countdown_and_the_state() -> None:
	"""End to end through the real app, because the legs are wired in `build_services` and a test
	that constructs its own service would not notice the wiring going missing."""
	app = create_app(build_services())
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		posted = await c.post('/emergency/sos', json={
			'lat': -1.3, 'lon': 36.8, 'severity': 'high',
			'contacts': ['Peter:0711222333', 'Grace:0722333444'],
			'blood_group': 'O+', 'medications': ['salbutamol'],
		})
		assert posted.status_code == 200, posted.text
		body = posted.json()
		assert body['contacts_notified'] == ['Peter', 'Grace']
		assert body['sms_sent'] == 2 and body['message']
		assert body['profile']['blood_group'] == 'O+'

		armed = await c.post('/emergency/sos/arm', json={'lat': -1.3, 'lon': 36.8, 'severity': 'high'})
		assert armed.status_code == 200, armed.text
		sos_id = armed.json()['sos_id']
		state = await c.get(f'/emergency/alert/{sos_id}')
		assert state.json()['dispatch'] is None and not state.json()['fired']
		fired = await c.post(f'/emergency/sos/{sos_id}/fire')
		assert fired.status_code == 200
		after = await c.get(f'/emergency/alert/{sos_id}')
		assert after.json()['dispatch']['sos_id'] == sos_id


async def test_a_cancelled_alert_fires_a_conflict_not_a_receipt() -> None:
	"""A client that fires a stale timer must be told the alert did not go out, not handed a
	dispatch receipt for one that never happened."""
	app = create_app(build_services())
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		armed = await c.post('/emergency/sos/arm', json={'lat': -1.3, 'lon': 36.8, 'severity': 'high'})
		sos_id = armed.json()['sos_id']
		assert (await c.post(f'/emergency/sos/{sos_id}/cancel')).status_code == 200
		refused = await c.post(f'/emergency/sos/{sos_id}/fire')
		assert refused.status_code == 409
		assert 'cancel' in refused.json()['detail']


async def test_an_unknown_alert_is_a_404() -> None:
	app = create_app(build_services())
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		assert (await c.get('/emergency/alert/SOS-NOPE00')).status_code == 404
		assert (await c.post('/emergency/sos/SOS-NOPE00/fire')).status_code == 409
