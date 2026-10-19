"""§CHAN-1's two outbound bullets: the follow-up after a USSD report, and "plain language".

Both were `missing` for the same shape of reason. The follow-up was a sentence the section prints
and nothing sent — the USSD walk ended with a screen, and a screen is read once. The plain-language
bound was a claim in a comment: `escalation._summary` called itself "one sentence an operator can act
on, in plain language" and no gate refused a message a person cannot read.

The tests that matter are the ones about the *failures*, not the happy path: a follow-up that is
re-sent on every later session is a subscription to a person's own report, and a bound with no
ceiling is the comment it replaced.
"""
import pathlib
import re
from typing import Any, cast

import httpx

from afya.channels.outbound import (
	MAX_SENTENCE_WORDS, MAX_WORD_CHARS, MESSAGE_CHARS, FOLLOW_UP_STRINGS, NOT_A_MESSAGE,
	follow_up_message, plain_language, plain_language_report,
)
from afya.channels.service import ChannelService
from afya.channels.views import SmsOut, UssdRequest
from afya.service import build_services, create_app

MSISDN = '+254711222333'


def _channels(services: dict[str, object]) -> ChannelService:
	"""`build_services` returns a heterogeneous mapping; this names the one service these tests drive."""
	return cast(ChannelService, services['channels'])


def _walk(svc: ChannelService, session: str = 'S-1', text: str = '') -> object:
	return svc.ussd(UssdRequest(session_id=session, msisdn=MSISDN, text=text), 'en')


# --- the measurement ----------------------------------------------------------------------------

def test_a_plain_message_reads_plain_and_says_nothing() -> None:
	reading = plain_language('Call 719 if you feel unwell.')
	assert reading.plain and reading.findings == []
	assert reading.longest_sentence_words == 6 and reading.segments == 1


def test_a_long_sentence_is_reported_rather_than_refused() -> None:
	"""The bound reports; it does not drop an outbreak alert over a sentence.

	The one place it *acts* is on the strings this module composes, asserted at import. Everywhere
	else the reading travels on the message, which is the trade `AfricaTalkingSmsPort` already makes
	for the cost flag: refusing to send is worse than sending something imperfect.

	The input is a literal, not `MAX_SENTENCE_WORDS + 3`: an input computed from the bound moves with
	it, so a ceiling loosened to fit a long sentence would loosen the test that is supposed to catch
	it. This canary went MISSED until the input was pinned, which is how the tautology was found.
	"""
	reading = plain_language(' '.join(['word'] * 40) + '.')
	assert reading.plain is False
	assert any('sentence runs to' in f for f in reading.findings)


def test_the_bound_is_a_bound_and_not_a_description_of_the_status_quo() -> None:
	"""The ceiling has to sit *between* the content and the sentence this unit fixed.

	Two literals, in both directions. Above: §SEC-004's pseudonym caveat was 31 words in one
	sentence, and a ceiling high enough to admit it is a description of what the tree already wrote
	rather than a bound — the reason that string was split into three instead. Below: the widest
	sentence the tables now carry is 24 words, and a ceiling under that fails on correct content and
	teaches its operator to bypass it. Both ends are pinned as numbers here because the module's own
	constants are what a canary moves.
	"""
	assert MAX_SENTENCE_WORDS <= 30, 'a ceiling that admits the 31-word caveat this unit split is not a bound'
	assert MAX_SENTENCE_WORDS >= 24, 'a ceiling under the 24-word table maximum fails on correct content'
	assert plain_language(' '.join(['word'] * 31) + '.').plain is False, '31 words is over the line'
	assert plain_language(' '.join(['word'] * 24) + '.').plain is True, '24 words is not'


def test_a_jargon_word_is_reported_but_a_long_swahili_word_is_not() -> None:
	"""The word bound is a ceiling on jargon, and Swahili is agglutinative.

	`kinachofuatiliwa` is 16 characters and is an ordinary Swahili word; the ceiling is 18 so the
	language is not flagged as jargon. A bound set to the longest *English* word would have failed on
	correct Kiswahili content, which is the §3.3 principle 8 audience.
	"""
	assert plain_language('Kitu kinachofuatiliwa.').plain is True
	assert plain_language('Pneumonoultramicroscopic silicovolcanoconiosis.').plain is False


def test_the_body_size_is_reported_separately_from_readability() -> None:
	"""§CHAN-1's 160 and its "plain language" are two different properties of one message.

	A two-segment message is not *unplain*: §LOC-005's traveller advisory is two and is the tree's
	clearest writing. Collapsing the size into `plain` would have refused it.
	"""
	body = 'Call 719 if you feel unwell. ' * 8
	reading = plain_language(body)
	assert len(body) > MESSAGE_CHARS and reading.segments > 1
	assert reading.plain is True, 'length is not illegibility'
	assert any('messages' in f for f in reading.findings)


def test_the_ceiling_is_above_everything_the_tree_actually_sends() -> None:
	"""The bound has to be one the product already meets, or it fails on correct content.

	This is the assertion that would have caught the bound being set to fit §SEC-004's 31-word caveat
	— a ceiling derived from the widest sentence already written is a description of the status quo.
	"""
	rows = plain_language_report()
	# The figures are read out of the walker's own docstring rather than restated here: a second
	# copy of "30 and 191" is the two-sources-of-truth drift this test exists to catch, and it would
	# move with the walker. The flat-only walker sees 15 / 30, so these floors fail on a walker that
	# stopped recursing long before they fail on content being edited.
	quoted = re.search(r'against \*\*(\d+) tables and (\d+) strings\*\*',
		pathlib.Path('src/afya/channels/outbound.py').read_text())
	assert quoted is not None, 'the walker no longer states its own measured totals'
	assert (len(rows), sum(r.strings for r in rows)) == (int(quoted.group(1)), int(quoted.group(2))), \
		f'the walker measures {len(rows)} / {sum(r.strings for r in rows)}; its docstring says ' \
		f'{quoted.group(1)} / {quoted.group(2)} — one of the two is stale'
	assert len(rows) >= 28, f'the walker is not seeing the tables: {len(rows)}'
	assert sum(r.strings for r in rows) >= 170, 'the walker is not recursing into the nested tables'
	over = [f'{r.surface}: {r.over_the_ceiling}' for r in rows if r.over_the_ceiling]
	assert over == [], f'outbound strings over the ceiling: {over}'
	worst = max(r.worst_sentence_words for r in rows)
	assert worst <= MAX_SENTENCE_WORDS
	assert max(r.worst_word_chars for r in rows) <= MAX_WORD_CHARS


def test_the_walker_sees_the_nested_tables_and_not_only_the_flat_ones() -> None:
	"""The checker-that-enumerates-one-shape defect, caught on the walker itself.

	`afya.strings` carries three nesting shapes: a flat `{key: sentence}` (`CALLBACK_ACK`), a
	`{lang: {key: sentence}}` (`TRAVELLER_STRINGS`) and a `{lang: {int: sentence}}`
	(`USSD_MENU_ANSWERS`). The flat-only walker reported **15 tables and 30 strings** against the
	**30 and 191** below, silently skipping the fifteen that carry the clinical advice — a gate
	losing 15 of its 30 tables and 161 of its 191 strings without failing, which is the failure mode
	this whole file is written against. It was written that way first, in this unit, and the canary
	reverts it.
	"""
	surfaces = {r.surface for r in plain_language_report()}
	assert 'afya.strings:CALLBACK_ACK' in surfaces, 'a flat table'
	assert 'afya.strings:TRAVELLER_STRINGS' in surfaces, 'a per-language table'
	assert 'afya.strings:USSD_MENU_ANSWERS' in surfaces, 'a per-language table with int keys'
	assert 'afya.strings:TRIAGE_RECS' in surfaces, 'the clinical recommendations'


def test_a_language_code_is_not_measured_as_a_message() -> None:
	"""`SMS_LANG_PREFIXES` and `LANGUAGE_NAME_FOR` live beside the sentences and are not sentences.

	The first is excluded by the property — a message holds a space, a code does not. The second is
	not: `Luhya (Bukusu)` and `Luhya (Maragoli)` are the only multi-word entries in a vocabulary
	table, so it is named in `NOT_A_MESSAGE` and asserted here in both directions, the rule
	`test_ui_vocabulary.py` applies to `UNGATED_WRITES`. A named exception checked both ways is a
	different thing from a filter nobody re-reads.
	"""
	from afya import strings

	surfaces = {r.surface for r in plain_language_report()}
	assert 'afya.strings:SMS_LANG_PREFIXES' not in surfaces, 'a code is not a message'
	assert 'afya.strings:LANGUAGE_NAME_FOR' not in surfaces, 'a vocabulary is not a message'
	# The list cannot rot: every name on it must exist, and every one must be a table the property
	# would otherwise have admitted. A name that no longer exists is a filter for a table that is gone.
	for name in NOT_A_MESSAGE:
		assert hasattr(strings, name), f'{name} is named as not-a-message and does not exist'
		obj = getattr(strings, name)
		spaced = [v for v in obj.values() if isinstance(v, str) and ' ' in v]
		assert spaced, f'{name} is on NOT_A_MESSAGE but holds no string the property would admit'


def test_every_string_this_module_composes_is_inside_its_own_bound() -> None:
	"""The one place the measurement acts, asserted rather than trusted to the import-time check."""
	for lang in FOLLOW_UP_STRINGS:
		for label in (None, 'Kutokwa na damu'):
			for callback in (False, True):
				body = follow_up_message(label, lang, callback)
				reading = plain_language(body)
				assert reading.plain, f'{lang}/{label}/{callback}: {reading.findings}'


# --- the follow-up ------------------------------------------------------------------------------

def test_a_ussd_report_gets_a_follow_up_and_it_names_what_was_reported() -> None:
	channels = _channels(build_services())
	_walk(channels, text='1*1*1*2')
	report = channels.channel_reports()[-1]
	assert report.channel == 'ussd' and report.symptom_label == 'Fever'
	body = channels._follow_ups[report.report_id]
	assert 'Fever' in body, 'the follow-up names the menu item the person chose'


async def test_the_follow_up_is_sent_once_however_many_sessions_follow() -> None:
	"""The failure a follow-up actually has, and the reason it is keyed by report id.

	The routes emit by walking the whole sink, so a send with no memory would text a person once per
	subsequent USSD session — which is not a follow-up, it is a subscription to their own report.

	`async def` rather than `asyncio.get_event_loop().run_until_complete(...)`: in a *sync* test that
	call raises `RuntimeError: There is no current event loop` as soon as any earlier test in the
	session has called `asyncio.run`, which closes the loop and sets the policy's `_set_called`. The
	file passed alone and failed in the full suite, which is the ordering dependence this repo's own
	convention — plain async functions — exists to avoid.
	"""
	channels = _channels(build_services())
	_walk(channels, text='1*1*1*2')
	report = channels.channel_reports()[-1]
	first = await channels.send_follow_up(report)
	second = await channels.send_follow_up(report)
	assert first is not None and second is None, 'the second send must be a no-op'


async def test_a_report_from_another_channel_gets_no_follow_up() -> None:
	"""§CHAN-1's bullet names the USSD channel, and the reason is the conversation.

	§CHAN-3's WhatsApp router replies inside the thread the person is already in, so an SMS on top of
	that reply is two messages for one report. `None` is the honest answer, not an error.
	"""
	channels = _channels(build_services())
	report = channels.record_report(MSISDN, 'whatsapp', ['fever'])
	assert await channels.send_follow_up(report) is None


def test_a_report_with_no_menu_label_still_gets_a_sentence() -> None:
	"""A channel with no menu has a symptom list and no label, which is not "reported nothing"."""
	body = follow_up_message(None, 'en')
	assert 'symptom report' in body
	assert plain_language(body).plain


def test_the_follow_up_says_whether_a_callback_was_promised() -> None:
	"""Two sentences, not one with a clause: a person waiting is owed the difference.

	`USSD_CLOSE` draws the same distinction on the screen, and a follow-up that blurred it would be
	the message the person keeps contradicting the one they just read.
	"""
	assert 'health worker will call' in follow_up_message('Fever', 'en', callback_requested=True)
	assert 'health worker will call' not in follow_up_message('Fever', 'en', callback_requested=False)


def test_the_follow_up_is_served_in_the_language_the_person_was_served() -> None:
	"""A caller who asked for Dholuo is served English on the screen, and the text must match it.

	The alternative is a message in one language contradicting the screen in another, which is the
	fake-translation failure `answerable` exists to refuse.
	"""
	assert follow_up_message('Homa', 'luo') == follow_up_message('Homa', 'en')
	assert follow_up_message('Homa', 'sw') != follow_up_message('Homa', 'en')


# --- end to end, as a person reaches it -----------------------------------------------------------

async def test_the_ussd_route_sends_the_follow_up_over_the_one_outbound_path() -> None:
	"""The send goes through `send_sms`, so §CHAN-1's Critical requirement is resolved on it.

	A follow-up composed here and pushed at the gateway would be a second outbound path, and the cost
	flag would be resolved in one place and not the other.
	"""
	sent: list[SmsOut] = []

	class _Recording:
		async def send(self, msg: SmsOut) -> str:
			sent.append(msg)
			return f'rec:{len(sent)}'

	services = build_services()
	channels = _channels(services)
	channels._sms = _Recording()  # type: ignore[assignment]
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		for text in ('1*1', '1*1*1', '1*1*1*2'):
			r = await c.post('/channels/ussd', json={'session_id': 'S-9', 'msisdn': MSISDN, 'text': text})
			assert r.status_code == 200, r.text[:200]
	assert len(sent) == 1, f'the follow-up must go once, not once per session: {len(sent)}'
	assert sent[0].zero_rated is True, 'the follow-up is resolved on the cost path'
	assert sent[0].plain.plain is True, 'and carries its own plain-language reading'


async def test_the_plain_language_route_serves_the_measurement() -> None:
	"""Scoped `audit_logs`, the content team's scope — and the sysadmin is refused it.

	A citizen is refused because the rows are editorial state, and a *sysadmin* is refused because
	§17.4 splits the operator scopes: `infrastructure` is not `audit_logs`. Asserting the citizen
	alone would pass on a route that merely required any token.
	"""
	from afya.privacy.views import RBACRole

	svc = build_services()
	auth: Any = svc['auth']
	app = create_app(svc)
	auditor = auth.provision_staff('chan-audit', RBACRole.auditor, registrar='MoH content').access_token
	sysadmin = auth.provision_staff('chan-sys', RBACRole.sysadmin, registrar='MoH ops').access_token
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		anon = (await c.post('/auth/anonymous', json={})).json()['token']
		assert (await c.get('/channels/plain-language',
		                    headers={'authorization': f'Bearer {anon}'})).status_code == 403
		assert (await c.get('/channels/plain-language',
		                    headers={'authorization': f'Bearer {sysadmin}'})).status_code == 403
		resp = await c.get('/channels/plain-language',
		                   headers={'authorization': f'Bearer {auditor}'})
	assert resp.status_code == 200, resp.text[:300]
	body = resp.json()
	assert body['over_the_ceiling'] == 0
	assert body['ceiling'] == {'sentence_words': MAX_SENTENCE_WORDS, 'word_chars': MAX_WORD_CHARS,
	                           'message_chars': MESSAGE_CHARS}
	assert body['measured'] >= 150


def test_an_sms_carries_its_own_reading_and_still_round_trips() -> None:
	"""`plain` is a computed field, so the model must not refuse the payload it just served.

	Without `DerivedFields` a client that read a message back and posted it would be refused for a key
	it never wrote — the §INF-004 share-card defect, on a second model.
	"""
	msg = SmsOut(to_msisdn=MSISDN, body='Call 719.', segments=1, zero_rated=True)
	dumped = msg.model_dump(mode='json')
	assert dumped['plain']['plain'] is True
	assert SmsOut(**dumped).body == 'Call 719.'

	# And the reading is *of this body*, not a constant. Asserting `plain is True` on a body already
	# known to be plain passes on a hardcoded reading, which is how the first version of this canary
	# went MISSED — the property has to be exercised on both sides of the line to be a property.
	long = SmsOut(to_msisdn=MSISDN, body=' '.join(['word'] * 40) + '.', segments=1, zero_rated=True)
	assert msg.plain.longest_sentence_words == 2
	assert long.plain.plain is False and long.plain.longest_sentence_words == 40
	assert 'plain' not in SmsOut.model_fields, 'a computed field is not settable'
