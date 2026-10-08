import pytest

from afya.channels.service import AfricaTalkingSmsPort, ChannelService, segment_sms
from afya.channels.views import (
	ChwTask, PushPayload, RadioBulletin, UssdRequest, WhatsAppIn,
)


def make_sms_port() -> AfricaTalkingSmsPort:
	return AfricaTalkingSmsPort('http://at.ke', 'key')


def test_sms_segmentation_single() -> None:
	assert segment_sms('Hello Afya Yangu') == 1


def test_sms_segmentation_multi() -> None:
	assert segment_sms('x' * 154) == 2
	with pytest.raises(AssertionError):
		segment_sms('y' * 1601)


def test_sms_rejects_non_gsm7() -> None:
	with pytest.raises(AssertionError):
		segment_sms('emoji 🎉 text')


async def test_sms_send_requires_zero_rating() -> None:
	svc = ChannelService(make_sms_port())
	out = await svc.send_sms('+254711222333', 'Call 719 if fever persists.')
	assert out.zero_rated and out.segments == 1


def test_ussd_flow() -> None:
	svc = ChannelService(make_sms_port())
	first = svc.ussd(UssdRequest(session_id='s1', msisdn='+254711222333', text=''))
	assert first.menu and first.menu.startswith('CON Afya Yangu')
	second = svc.ussd(UssdRequest(session_id='s1', msisdn='+254711222333', text='2'))
	assert second.end_text and 'routed to feature' in second.end_text


def test_ussd_swahili_menu() -> None:
	from afya.integrations.gateways import AtUssdCallback
	svc = ChannelService(make_sms_port())
	menu = svc.ussd(UssdRequest(session_id='s2', msisdn='+254711222333', text=''), lang='sw').menu
	assert menu and 'Tafuta kituo' in menu
	carrier = svc.ussd_carrier_callback(AtUssdCallback(session_id='s2', phone_number='+254711222333', text=''), lang='sw')
	assert carrier['action'] == 'CON' and 'Ebola' in carrier['text']
	assert svc.ussd_carrier_callback(AtUssdCallback(session_id='s2', phone_number='+254711222333', text='3'), lang='sw')['action'] == 'END'


def test_whatsapp_routing() -> None:
	svc = ChannelService(make_sms_port())
	assert 'malaria' in svc.route_whatsapp(WhatsAppIn(from_msisdn='+254711222333', body='I have fever')).reply
	assert 'nearest facility' in svc.route_whatsapp(WhatsAppIn(from_msisdn='+254711222333', body='find facility')).reply


async def test_chw_task_and_push() -> None:
	svc = ChannelService(make_sms_port())
	t = await svc.assign_chw_task(ChwTask(task_id='T1', chw_ref='CHW1', community='Kibera', kind='followup'))
	assert not t.done
	assert svc.open_tasks('CHW1') == [t]
	await svc.complete_task('T1')
	assert svc.open_tasks('CHW1') == []
	assert svc.push(PushPayload(title='t', body='b')).title == 't'


async def test_radio_bulletin() -> None:
	svc = ChannelService(make_sms_port())
	b = RadioBulletin(bulletin_id='R1', station='KBC', air_date='2026-10-08', duration_s=60, script='x' * 100)
	assert (await svc.schedule_bulletin(b)).station == 'KBC'
	with pytest.raises(AssertionError):
		await svc.schedule_bulletin(RadioBulletin(bulletin_id='R2', station='KBC', air_date='2026-10-08', duration_s=15, script='y' * 4501))