from afya.emergency.service import EmergencyService, Inline719Port
from afya.emergency.views import EmergencyCard, IMUSample, SOSEvent


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
	card = EmergencyCard(name='Wanjiku', blood_group='O+', allergies=['penicillin'], conditions=[], emergency_contact='+254711222333')
	assert EmergencyService.card_qr(card).startswith('AFYA|Wanjiku|O+|penicillin|')