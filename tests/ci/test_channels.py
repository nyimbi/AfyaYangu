import pytest

from afya.channels.service import AfricaTalkingSmsPort, ChannelService, segment_sms
from afya.channels.views import (
	ChwTask, PushPayload, RadioBulletin, UssdRequest, WhatsAppIn,
)


def make_sms_port() -> AfricaTalkingSmsPort:
	return AfricaTalkingSmsPort('http://at.ke', 'key')


def make_channel_service() -> ChannelService:
	"""The channel service as the app builds it, with §5.4's shared triage engine behind it.

	The engine is passed rather than left out because `route_whatsapp` and the USSD answers now
	delegate to it, and a bare service would raise. That refusal is the point — a channel handler
	that answered from its own keyword rules would be the second clinical engine §5.4 forbids — so
	the test wires the real one instead of a stub.
	"""
	from afya.registry.service import FeatureRegistry
	from afya.triage.service import TriageService
	return ChannelService(make_sms_port(), None, TriageService(FeatureRegistry()))


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
	svc = make_channel_service()
	first = svc.ussd(UssdRequest(session_id='s1', msisdn='+254711222333', text=''))
	assert first.menu and first.menu.startswith('CON Afya Yangu')
	second = svc.ussd(UssdRequest(session_id='s1', msisdn='+254711222333', text='2'))
	assert second.end_text and 'facility' in second.end_text
	# §5.4: the selection answers with the shared engine's words, not a developer's sentence. The
	# hotline selection is the one that reaches no clinical logic, so it is the one that proves the
	# menu is answered rather than acknowledged.
	hotline = svc.ussd(UssdRequest(session_id='s1', msisdn='+254711222333', text='4'))
	assert hotline.end_text and '719' in hotline.end_text
	# And the symptom selection asks for the symptoms rather than inventing an answer for an empty
	# list — a numeric menu cannot name one, and a recommendation for symptoms nobody named is
	# clinical advice the engine never gave.
	symptoms = svc.ussd(UssdRequest(session_id='s1', msisdn='+254711222333', text='3'))
	assert symptoms.end_text and 'symptom' in symptoms.end_text.lower()
	assert 'malaria' not in (symptoms.end_text or '').lower(), 'no recommendation for unnamed symptoms'


def test_ussd_swahili_menu() -> None:
	from afya.integrations.gateways import AtUssdCallback
	svc = ChannelService(make_sms_port())
	menu = svc.ussd(UssdRequest(session_id='s2', msisdn='+254711222333', text=''), lang='sw').menu
	assert menu and 'Tafuta kituo' in menu
	carrier = svc.ussd_carrier_callback(AtUssdCallback(session_id='s2', phone_number='+254711222333', text=''), lang='sw')
	assert carrier['action'] == 'CON' and 'Ebola' in carrier['text']
	assert svc.ussd_carrier_callback(AtUssdCallback(session_id='s2', phone_number='+254711222333', text='3'), lang='sw')['action'] == 'END'


def test_whatsapp_routing() -> None:
	svc = make_channel_service()
	# §5.4's shared engine, reached through §CHAN-3's keyword intent: the reply is the engine's own
	# recommendation for a fever, which is where §6.3's malaria trap lives.
	assert 'malaria' in svc.route_whatsapp(WhatsAppIn(from_msisdn='+254711222333', body='I have fever')).reply
	assert 'nearest facility' in svc.route_whatsapp(WhatsAppIn(from_msisdn='+254711222333', body='find facility')).reply
	# A body naming no symptom enters with an empty list and is answered at the low risk level —
	# the honest reading of "no symptom named", not a fever assumed from the word "symptom".
	none_named = svc.route_whatsapp(WhatsAppIn(from_msisdn='+254711222333', body='I have a symptom'))
	assert 'malaria' not in none_named.reply
	# Swahili reaches the same engine and the same malaria trap, in Swahili. The keyword router
	# matches §CHAN-3's English intent words — widening it to Swahili keywords is a separate change
	# and not claimed here — so the body is the English word and the answer is Swahili.
	sw = svc.route_whatsapp(WhatsAppIn(from_msisdn='+254711222333', body='I have fever'), lang='sw')
	assert 'malaria' in sw.reply and 'Homa' in sw.reply, sw.reply


def test_the_channel_answers_are_the_shared_engines_own_words() -> None:
	"""§5.4's first bullet, asserted as equality rather than as a substring.

	A substring assertion passes against a second implementation that happens to contain the same
	word — which is exactly the drift §5.4 forbids and exactly what the old code was: `route_whatsapp`
	held its own fever sentence. The reply is compared to what the engine returns for the same input,
	so a channel that grew its own clinical logic fails here however plausible its wording.
	"""
	from afya.registry.service import FeatureRegistry
	from afya.triage.service import TriageService
	from afya.triage.views import TriageInput

	engine = TriageService(FeatureRegistry())
	svc = make_channel_service()
	for body, inp in (
		('I have fever', TriageInput(symptoms=['fever'], temperature_c=38.0)),
		('fever and bleeding', TriageInput(symptoms=['fever', 'bleeding'], temperature_c=38.0)),
		('I have a symptom', TriageInput(symptoms=[])),
		('rash', TriageInput(symptoms=['rash'])),
	):
		reply = svc.route_whatsapp(WhatsAppIn(from_msisdn='+254711222333', body=body)).reply
		assert reply == engine.assess(inp, 'en').recommendation, body


async def test_the_app_route_and_the_channel_route_give_one_answer() -> None:
	"""The crossing §5.4 actually claims, driven through both entry points over HTTP.

	The app reaches triage at `POST /triage/preliminary`; a person with no data reaches it through
	`POST /channels/whatsapp`. §5.4's first bullet says those are the same clinical logic, and the
	only evidence for it is the two responses compared — a channel test against the engine and a
	route test against the engine can both pass while the two entry points differ.
	"""
	import httpx
	from afya.service import build_services, create_app

	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		for body, payload in (
			('I have fever', {'symptoms': ['fever'], 'temperature_c': 38.0}),
			('fever and bleeding', {'symptoms': ['fever', 'bleeding'], 'temperature_c': 38.0}),
			('rash', {'symptoms': ['rash']}),
		):
			app_reply = (await c.post('/triage/preliminary', json=payload)).json()['recommendation']
			channel = (await c.post('/channels/whatsapp',
			                        json={'from_msisdn': '+254711222333', 'body': body})).json()
			assert channel['reply'] == app_reply, body
		# Swahili too: the language travels the same path on both, so the fallback behaviour is shared
		# rather than reimplemented per channel.
		app_sw = (await c.post('/triage/preliminary?lang=sw',
		                       json={'symptoms': ['fever'], 'temperature_c': 38.0})).json()['recommendation']
		channel_sw = (await c.post('/channels/whatsapp?lang=sw',
		                           json={'from_msisdn': '+254711222333', 'body': 'I have fever'})).json()
		assert channel_sw['reply'] == app_sw


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