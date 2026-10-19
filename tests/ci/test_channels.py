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
	from afya.identity.service import IdentityService
	from afya.registry.service import FeatureRegistry
	from afya.triage.service import TriageService
	# §5.4's two shared collaborators, both wired rather than stubbed: the triage engine the walk
	# answers through, and the identity model the report it now files is keyed on.
	return ChannelService(make_sms_port(), None, TriageService(FeatureRegistry()), IdentityService())


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
	assert '1. Report symptoms' in first.menu and '5. Language' in first.menu
	# §CHAN-2's two-level walk. Item 1 opens the symptom submenu rather than answering, because the
	# section gives it children.
	submenu = svc.ussd(UssdRequest(session_id='s1', msisdn='+254711222333', text='1'))
	assert submenu.menu and '1. Fever' in submenu.menu and '4. Bleeding' in submenu.menu
	# The second segment names the symptom and §5.4's shared engine answers — the fever entry reaches
	# §6.3's malaria trap on a feature phone. The answer arrives as a `CON` carrying the first of
	# §CHAN-2's two "→" prompts, because the section draws the prompts *after* the symptom entries and
	# the screen replaces rather than appends: the recommendation is repeated above the prompt so the
	# caller does not pay for the advice and then have it taken off the screen.
	fever = svc.ussd(UssdRequest(session_id='s1', msisdn='+254711222333', text='1*1'))
	assert fever.menu and 'malaria' in fever.menu.lower(), fever.menu
	assert 'Send my location' in fever.menu, fever.menu
	# The second prompt, and then the close — a session that ends rather than one that loops.
	callback = svc.ussd(UssdRequest(session_id='s1', msisdn='+254711222333', text='1*1*1'))
	assert callback.menu and 'Request callback' in callback.menu, callback.menu
	closed = svc.ussd(UssdRequest(session_id='s1', msisdn='+254711222333', text='1*1*1*1'))
	assert closed.end_text and 'call you' in closed.end_text.lower(), closed.end_text
	assert 'malaria' in closed.end_text.lower(), closed.end_text
	# A submenu entry the engine has no word for answers at the low risk level rather than inventing
	# a symptom from the label.
	cough = svc.ussd(UssdRequest(session_id='s1', msisdn='+254711222333', text='1*2'))
	assert cough.menu and 'malaria' not in cough.menu.lower(), cough.menu
	# §CHAN-2's item 5 says "Reply with the one you want" — a word, not a digit. A language with no
	# table is answered in English and *told* so, rather than accepted into a session that claims a
	# language it is not serving.
	asked = svc.ussd(UssdRequest(session_id='s1', msisdn='+254711222333', text='Dholuo'))
	assert asked.end_text and 'Dholuo' in asked.end_text, asked.end_text
	# A reply naming nothing this product knows re-serves the menu rather than 500ing on a phone.
	assert svc.ussd(UssdRequest(session_id='s1', msisdn='+254711222333', text='Klingon')).menu
	# The leaves answer directly.
	assert 'facility' in (svc.ussd(UssdRequest(session_id='s1', msisdn='+254711222333', text='2')).end_text or '')
	# Item 3 opens its three questions, and each is answered.
	info = svc.ussd(UssdRequest(session_id='s1', msisdn='+254711222333', text='3'))
	assert info.end_text and 'Ebola' in info.end_text
	travel = svc.ussd(UssdRequest(session_id='s1', msisdn='+254711222333', text='3*3'))
	assert travel.end_text and 'Travel' in travel.end_text
	# Out-of-range input re-serves the menu rather than crashing a feature-phone session.
	assert svc.ussd(UssdRequest(session_id='s1', msisdn='+254711222333', text='9')).menu
	assert svc.ussd(UssdRequest(session_id='s1', msisdn='+254711222333', text='1*9')).menu


def test_ussd_swahili_menu() -> None:
	"""§CHAN-2's labels are the section's English ones in both languages — the tree is a structure and
	a translated tree would be a second structure. What is localised is the prompt and the answers, so
	that is what is asserted: the symptom submenu prompt and the triage recommendation come back in
	Swahili, and the carrier envelope carries the same text the handler returned."""
	from afya.integrations.gateways import AtUssdCallback
	svc = make_channel_service()
	menu = svc.ussd(UssdRequest(session_id='s2', msisdn='+254711222333', text=''), lang='sw').menu
	assert menu and 'Ripoti dalili' in menu, menu
	submenu = svc.ussd(UssdRequest(session_id='s2', msisdn='+254711222333', text='1'), lang='sw').menu
	assert submenu and 'Jibu kwa namba ya dalili yako' in submenu, submenu
	carrier = svc.ussd_carrier_callback(AtUssdCallback(session_id='s2', phone_number='+254711222333', text=''), lang='sw')
	assert carrier['action'] == 'CON' and 'Afya Yangu' in carrier['text']
	# A fever selection answered in Swahili, through the same engine. The prompts are localised with
	# everything else, so the callback question is asked in the language the caller is reading.
	fever = svc.ussd_carrier_callback(AtUssdCallback(session_id='s2', phone_number='+254711222333', text='1*1'), lang='sw')
	assert fever['action'] == 'CON' and 'malaria' in fever['text'].lower(), fever['text']
	assert 'Tuma mahali' in fever['text'], fever['text']
	close = svc.ussd_carrier_callback(
		AtUssdCallback(session_id='s2', phone_number='+254711222333', text='1*1*1*1'), lang='sw')
	assert close['action'] == 'END' and 'atakupigia' in close['text'], close['text']


def test_the_ussd_menu_is_the_sections_tree() -> None:
	"""§CHAN-2's menu, read out of the spec rather than retyped.

	The section draws a five-item tree with a five-way symptom submenu under the first item and three
	questions under the third. The code served a flat four-item menu — "1. Ebola info / 2. Find
	facility / 3. Report symptoms / 4. Hotline 719" — which disagrees with the section on the count,
	the order and the first item, and which put the symptom path third when §CHAN-2's own integration
	note is about it. The comparison is against `docs/spec.md` so a revision fails here until the tree
	moves with it.
	"""
	from pathlib import Path
	from afya.strings import (
		USSD_INFO_ANSWERS, USSD_LANGUAGES, USSD_MENU, USSD_SESSION_LIMIT_CHARS, USSD_SYMPTOMS,
		USSD_TREE, USSD_YES_NO_PROMPTS, ussd_menu_text,
	)

	spec = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	section = spec.split('#### CHAN-2: USSD', 1)[1].split('\n---', 1)[0]
	block = section.split('```', 2)[1]
	lines = block.splitlines()

	# The top level is the unindented "N. " lines; the indented ones are submenu entries and the
	# "→" prompts. Indentation is the section's own signal for depth, so it is read rather than
	# stripped — the first attempt stripped it and counted thirteen top-level items.
	top = [ln.strip() for ln in lines if ln and not ln.startswith(' ') and len(ln) > 3 and ln[0].isdigit() and ln[1:3] == '. ']
	assert len(top) == 5, top
	assert [t[3:] for t in top] == [label for label, _ in USSD_TREE]
	# The symptom submenu is the section's five entries, indented under the first item.
	under_one = [ln.strip() for ln in lines if ln.startswith('   ') and ln.strip()[:1].isdigit() and ln.strip()[1:3] == '. ']
	assert under_one[:5] == ['1. Fever', '2. Cough', '3. Diarrhoea / vomiting', '4. Bleeding', '5. Other'], under_one
	assert USSD_TREE[0][1] == tuple(label for _, label in USSD_SYMPTOMS)
	# The "→" prompts are children of their items and are carried as the section writes them, so a
	# submenu that drops them is visible. There are three: two under the symptom path and one under
	# the clinic lookup, and the two that ask a yes/no question are the ones a flat menu loses.
	prompts = [ln.strip() for ln in lines if ln.strip().startswith('→')]
	assert prompts == [
		'→ Send my location? 1=Yes 2=No', '→ Request callback? 1=Yes 2=No', '→ Enter your area code',
	]
	assert [p for p in prompts if '1=Yes 2=No' in p] == list(USSD_YES_NO_PROMPTS)
	# The symptom submenu is the section's five entries, under the first item.
	assert [label for _, label in USSD_SYMPTOMS] == ['Fever', 'Cough', 'Diarrhoea / vomiting', 'Bleeding', 'Other']
	assert USSD_TREE[0][1] == tuple(label for _, label in USSD_SYMPTOMS)
	# The health-information questions are the section's three.
	assert USSD_TREE[2][1] == ('What is Ebola?', 'How do I protect my family?', 'Is it safe to travel?')
	assert len(USSD_INFO_ANSWERS['en']) == 3
	# The served menu is the tree rendered, not a second string — and it is localised, which the
	# first cut of this got wrong: the structure was the section's and the Swahili menu was English.
	# `USSD_MENU['en']` is the section's labels; the Swahili one is a translation of the same tree.
	assert USSD_MENU['en'] == ussd_menu_text('en')
	assert USSD_MENU['en'].splitlines()[1:] == [f'{i}. {label}' for i, (label, _) in enumerate(USSD_TREE, 1)]
	assert USSD_MENU['sw'] != USSD_MENU['en'], 'a language with a table is not served the English menu'
	assert USSD_MENU['sw'].count('\n') == USSD_MENU['en'].count('\n'), 'same structure, different words'
	# §CHAN-2's own session budget and language list, carried as the section writes them.
	assert USSD_SESSION_LIMIT_CHARS == 360
	assert USSD_LANGUAGES == ('English', 'Kiswahili', 'Dholuo')
	assert 'Dholuo' in section and '360 characters' in section
	# The menu fits the budget it states, which is the constraint the section gives the structure.
	assert len(USSD_MENU['en']) <= USSD_SESSION_LIMIT_CHARS, len(USSD_MENU['en'])


def test_the_symptom_submenu_reaches_the_shared_engine() -> None:
	"""§CHAN-2's first item is a symptom report and §5.4 says every channel shares one engine, so the
	submenu is the crossing where the two sections meet. Every entry either names a symptom the engine
	knows or is recorded as naming none — a label mapped to nothing silently is a symptom the engine
	never hears about."""
	from afya.strings import USSD_SYMPTOMS, USSD_SYMPTOM_MAP
	from afya.triage.views import EBOLA_SYMPTOMS

	assert set(USSD_SYMPTOM_MAP) == {key for key, _ in USSD_SYMPTOMS}
	for key, symptoms in USSD_SYMPTOM_MAP.items():
		assert set(symptoms) <= EBOLA_SYMPTOMS, (key, symptoms)
	# The two entries with no engine word are named, not left to be discovered.
	assert USSD_SYMPTOM_MAP['cough'] == () and USSD_SYMPTOM_MAP['other'] == ()
	assert USSD_SYMPTOM_MAP['diarrhoea_vomiting'] == ('diarrhoea', 'vomiting')
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


async def test_the_app_route_and_the_channel_route_give_one_answer(webhook_secret: str) -> None:
	"""The crossing §5.4 actually claims, driven through both entry points over HTTP.

	The app reaches triage at `POST /triage/preliminary`; a person with no data reaches it through
	`POST /channels/whatsapp`. §5.4's first bullet says those are the same clinical logic, and the
	only evidence for it is the two responses compared — a channel test against the engine and a
	route test against the engine can both pass while the two entry points differ.
	"""
	import httpx
	from conftest import sign
	from afya.service import build_services, create_app

	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		for body, payload in (
			('I have fever', {'symptoms': ['fever'], 'temperature_c': 38.0}),
			('fever and bleeding', {'symptoms': ['fever', 'bleeding'], 'temperature_c': 38.0}),
			('rash', {'symptoms': ['rash']}),
		):
			app_reply = (await c.post('/triage/preliminary', json=payload)).json()['recommendation']
			raw, h = sign({'from_msisdn': '+254711222333', 'body': body})
			channel = (await c.post('/channels/whatsapp', content=raw, headers=h)).json()
			assert channel['reply'] == app_reply, body
		# Swahili too: the language travels the same path on both, so the fallback behaviour is shared
		# rather than reimplemented per channel.
		app_sw = (await c.post('/triage/preliminary?lang=sw',
		                       json={'symptoms': ['fever'], 'temperature_c': 38.0})).json()['recommendation']
		raw, h = sign({'from_msisdn': '+254711222333', 'body': 'I have fever'})
		channel_sw = (await c.post('/channels/whatsapp?lang=sw', content=raw, headers=h)).json()
		assert channel_sw['reply'] == app_sw


async def test_chw_task_and_push() -> None:
	svc = ChannelService(make_sms_port())
	t = await svc.assign_chw_task(ChwTask(task_id='T1', chw_ref='CHW1', community='Kibera', kind='followup'))
	assert not t.done
	assert svc.open_tasks('CHW1') == [t]
	await svc.complete_task('T1')
	assert svc.open_tasks('CHW1') == []
	assert (await svc.push(PushPayload(subject_ref='s1', title='t', body='b'))).title == 't'
	assert len(svc.pushes('s1')) == 1


async def test_radio_bulletin() -> None:
	svc = ChannelService(make_sms_port())
	b = RadioBulletin(bulletin_id='R1', station='KBC', air_date='2026-10-08', duration_s=60, script='x' * 100)
	assert (await svc.schedule_bulletin(b)).station == 'KBC'
	with pytest.raises(AssertionError):
		await svc.schedule_bulletin(RadioBulletin(bulletin_id='R2', station='KBC', air_date='2026-10-08', duration_s=15, script='y' * 4501))