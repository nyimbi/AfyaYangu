import pytest
from pydantic import ValidationError

from afya.emergency.service import EmergencyService, Inline719Port
from afya.emergency.views import EmergencyCard, EmergencyContact, IMUSample, SOSEvent


async def test_sos_dispatch() -> None:
	svc = EmergencyService(Inline719Port())
	out = await svc.sos(SOSEvent(sos_id='SOS-ABC123XY99', lat=-1.3, lon=36.8, severity='high', symptoms=['fever']))
	assert '719-hotline' in out.notified and 'call-719' in out.actions


def test_fall_detection_freefall_spike() -> None:
	svc = EmergencyService.__new__(EmergencyService)
	samples = [IMUSample(x=0, y=0, z=0.2, timestamp_ms=i * 20) for i in range(10)]  # freefall (≈0 g)
	samples.append(IMUSample(x=2, y=1, z=-28.0, timestamp_ms=200))  # impact spike
	samples.append(IMUSample(x=0.5, y=0.5, z=9.4, timestamp_ms=204))
	res = EmergencyService.fall(samples)
	assert res.fall_detected and res.auto_alert


def test_no_fall_impact_without_freefall() -> None:
	svc = EmergencyService.__new__(EmergencyService)
	samples = [IMUSample(x=0.2, y=0.1, z=9.8, timestamp_ms=i * 20) for i in range(10)]
	samples.append(IMUSample(x=3, y=1, z=-28.0, timestamp_ms=200))  # spike but never freefall
	samples += [IMUSample(x=0.2, y=0.1, z=9.8, timestamp_ms=220 + i * 20) for i in range(8)]
	res = EmergencyService.fall(samples)
	assert not res.fall_detected


def test_offline_card_qr() -> None:
	card = EmergencyCard(name='Wanjiku', blood_group='O+', allergies=['penicillin'], conditions=[],
		emergency_contacts=[EmergencyContact(name='Peter', number='+254711222333', relationship='husband')])
	qr = EmergencyService.card_qr(card)
	assert qr.startswith('AFYA|Wanjiku|O+|penicillin|')
	assert 'Peter:+254711222333' in qr, 'a contact carries who it is, not only a number'


def test_the_offline_card_carries_the_sections_seven_contents() -> None:
	"""§EMG-003 prints seven Contents and the card held five fields, with "emergency contacts" (plural)
	collapsed into one phone string and no medications, organ-donor status or SHA number at all."""
	card = EmergencyCard(
		name='Wanjiku', blood_group='O+', allergies=['penicillin'], conditions=['asthma'],
		emergency_contacts=[
			EmergencyContact(name='Peter', number='+254711222333', relationship='husband'),
			EmergencyContact(name='Grace', number='+254722333444'),
		],
		medications=['salbutamol'], organ_donor=True, sha_number='SHA12345678',
	)
	qr = EmergencyService.card_qr(card)
	fields = qr.split('|')
	assert fields[0] == 'AFYA' and len(fields) == 9, fields
	assert 'Peter:+254711222333;Grace:+254722333444' in qr, 'the plural survives'
	assert 'salbutamol' in qr and 'SHA12345678' in qr


def test_organ_donor_status_is_tri_state_because_never_said_is_not_no() -> None:
	"""The one field where a defaulted boolean is a safety property. A hospital reading the card of an
	unconscious patient must be able to tell "declined" from "never asked"; `False` as a default
	answers the second as the first, and nothing on the card would say which had happened."""
	def donor(value: bool | None) -> str:
		return EmergencyService.card_qr(EmergencyCard(
			name='A', blood_group='O+', allergies=[], conditions=[],
			emergency_contacts=[EmergencyContact(name='B', number='+254711222333')],
			organ_donor=value)).split('|')[7]

	assert donor(True) == 'yes' and donor(False) == 'no' and donor(None) == 'unknown'
	assert EmergencyCard(name='A', blood_group='O+', allergies=[], conditions=[],
		emergency_contacts=[EmergencyContact(name='B', number='+254711222333')]).organ_donor is None


def test_a_card_with_no_emergency_contact_is_refused() -> None:
	"""§EMG-003's Contents list "emergency contacts" and the card is for an unconscious patient: a
	card with none is a card that tells a clinician nothing to do."""
	with pytest.raises(ValidationError):
		EmergencyCard(name='A', blood_group='O+', allergies=[], conditions=[], emergency_contacts=[])


def test_the_lock_screen_access_clause_is_a_field_and_defaults_off() -> None:
	"""§EMG-003's Access: "Available from the lock screen without unlocking the phone (opt-in)." The
	opt-in is the whole clause — a card is not lock-screen readable because it exists, and the default
	must be the one that shows a stranger nothing."""
	card = EmergencyCard(name='A', blood_group='O+', allergies=[], conditions=[],
		emergency_contacts=[EmergencyContact(name='B', number='+254711222333')])
	assert card.lock_screen_opt_in is False, 'opt-in means off until asked'
	assert card.model_copy(update={'lock_screen_opt_in': True}).lock_screen_opt_in is True
