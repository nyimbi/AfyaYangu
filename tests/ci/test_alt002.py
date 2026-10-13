"""§10.3 ALT-002: the family check-in, and the half of it that needed no data connection.

The section bolds "**Works over SMS when data is unavailable**" as a property of the whole feature,
and the audit recorded the gap precisely: `/alerting/family/check-in` was HTTP only, and
`SafetyCheckIn.channel` accepted `sms` while nothing in the product ever sent one. A check-in button
that only works in an app is a check-in button that does not work in the week the network is the
thing that broke, which is the week it exists for.

Two directions had to be built, and they fail differently:

* **Outbound.** The check-in texts every member who has not answered. The failure to guard against
  is not "no message" but "a message reported as delivered that never was": a member with no phone
  on file, or a landline, must land in `sms_unreachable` rather than in the count, because a family
  told it reached everyone when it reached two is the failure the split exists to prevent.
* **Inbound.** A body carrying a safe word is filed as a check-in from the sender's own number. The
  failure here is the opposite one: a keyword match that reads "I am not safe" as "safe" tells a
  family their relative is accounted for on the strength of a message that says the opposite. That
  is the one error worse than silence, so the match is on word sequences with the word before the
  keyword read — not `'safe' in body`.
"""
import ast
import hashlib
import hmac
import json
import pathlib
import re
from typing import Any

import httpx
import pytest

from afya.alerting.service import AlertingService, safe_intent, safe_reply
from afya.alerting.views import FamilyStatus
from afya.channels.service import GSM7, segment_sms
from afya.identity.service import IdentityService
from afya.identity.views import IdentityLink, LinkBasis
from afya.service import build_services, create_app
from afya.strings import (
	SMS_FAMILY_BOARD, SMS_FAMILY_BOARD_ALL, SMS_FAMILY_MANY_GROUPS, SMS_FAMILY_NO_GROUP,
	SMS_FAMILY_NOT_SAFE, SMS_FAMILY_SAFE, SMS_FAMILY_THIRD_PARTY, SMS_FAMILY_UNKNOWN_GROUP,
	SMS_SAFE_KEYWORDS,
	SUPPORTED_LANGS, answerable,
)

FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')

ROOT = pathlib.Path(__file__).resolve().parents[2]

MINE = 'subj-mine'
MUM = 'subj-mum'
DAD = 'subj-dad'
GROUP = 'karibu'
OTHER_GROUP = 'upcountry'
AT = '2026-10-13T09:00:00+00:00'

# A phone per member, and a Nairobi landline for the member who has one — the case that must be
# refused rather than texted.
NUMBERS = {MINE: '+254711111111', MUM: '+254722222222', DAD: '+254733333333'}


def _svc(*, sms: Any = None, msisdn_of: Any = None) -> AlertingService:
	"""A service with both SMS legs wired to stand-ins, in the shape the deployment wires them.

	The stand-ins are callables rather than objects because that is what the ports are: passing a
	gateway object would test a shape production does not have, and the cycle this design exists to
	avoid (`afya.alerting` importing `afya.channels`) would come straight back.
	"""
	sent: list[tuple[str, str]] = []

	async def _send(number: str, body: str) -> object:
		sent.append((number, body))
		return object()

	svc = AlertingService(sms or _send, msisdn_of or NUMBERS.get)
	svc._sent = sent  # type: ignore[attr-defined]  the stand-in's own record, not the service's state
	return svc


def _grouped(*, members: tuple[str, ...] = (MINE, MUM, DAD), ref: str = GROUP) -> AlertingService:
	svc = _svc()
	svc.link_family(ref, list(members))
	return svc


async def _citizen(c: httpx.AsyncClient, subject: str | None = None) -> tuple[dict[str, str], str]:
	tok = (await c.post('/auth/anonymous', json={'subject_ref': subject} if subject else {})).json()
	return {'Authorization': f'Bearer {tok["token"]}'}, str(tok['subject_ref'])


def _signed(body: dict[str, Any], secret: str) -> tuple[bytes, dict[str, str]]:
	raw = json.dumps(body).encode()
	sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
	return raw, {'content-type': 'application/json', 'x-afya-signature': sig}


# --- outbound: the fan-out ---------------------------------------------------------------------

async def test_the_check_in_texts_every_member_who_has_not_answered() -> None:
	svc = _grouped()
	board = await svc.check_in(MINE, GROUP, AT)
	assert board.members_safe == [MINE]
	assert sorted(board.members_unknown) == sorted([MUM, DAD])
	assert board.sms_sent == 2, 'the two members who have not answered are the ones to text'
	assert sorted(n for n, _ in svc._sent) == sorted([NUMBERS[MUM], NUMBERS[DAD]])  # type: ignore[attr-defined]


async def test_the_check_in_does_not_text_the_person_who_checked_in() -> None:
	"""The board is built after the check-in is written, so the sender is already accounted for. The
	test asserts the number was not dialled rather than that the branch skipped them: an earlier cut
	guarded this inside the loop, where the guard could not fire, and a test that read the branch
	would have passed against code that texted the sender every time."""
	svc = _grouped()
	await svc.check_in(MINE, GROUP, AT)
	assert NUMBERS[MINE] not in [n for n, _ in svc._sent]  # type: ignore[attr-defined]


async def test_a_member_with_no_phone_is_reported_rather_than_counted_as_told() -> None:
	"""The dangerous direction. A member with no number on file cannot be texted, and reporting the
	check-in as having reached the family would be the app telling someone their mother knows."""
	svc = _svc(msisdn_of=lambda ref: NUMBERS.get(ref) if ref == MUM else None)
	svc.link_family(GROUP, [MINE, MUM, DAD])
	board = await svc.check_in(MINE, GROUP, AT)
	assert board.sms_sent == 1
	assert board.sms_unreachable == [DAD], 'a member with no phone is named, not silently dropped'


async def test_a_landline_is_not_a_phone_that_can_receive_a_text() -> None:
	"""`_sms_dialable` refuses a Nairobi landline, and the deployment routes the identity model's
	answer through it. Without that the gateway is handed a number it will drop, and the fan-out
	reports a family told that never was."""
	services = build_services()
	identity: IdentityService = services['identity']  # type: ignore[assignment]
	alerting: AlertingService = services['alerting']  # type: ignore[assignment]
	await identity.link(IdentityLink(msisdn='+254202222222', subject_ref=MUM, consent_id='c1',
	                                 basis=LinkBasis.self_entered))
	alerting.link_family(GROUP, [MINE, MUM])
	board = await alerting.check_in(MINE, GROUP, AT)
	assert board.sms_unreachable == [MUM], 'a landline reached the gateway as a textable number'
	assert board.sms_sent == 0


async def test_a_dead_gateway_leg_does_not_silence_the_others() -> None:
	"""One member whose message fails must not cost the others theirs. The count is asserted beside
	the refusal, because "sent" and "unreachable" that sum to more than the group is a fan-out
	reporting two contradictory things."""
	calls: list[str] = []

	async def _flaky(number: str, body: str) -> object:
		calls.append(number)
		if number == NUMBERS[MUM]:
			raise RuntimeError('gateway refused')
		return object()

	svc = _svc(sms=_flaky)
	svc.link_family(GROUP, [MINE, MUM, DAD])
	board = await svc.check_in(MINE, GROUP, AT)
	assert board.sms_sent == 1
	assert board.sms_unreachable == [MUM]
	# `members_unknown` is sorted, so the order is the board's and not the gateway's.
	assert sorted(calls) == sorted([NUMBERS[MUM], NUMBERS[DAD]]), 'the second leg ran after the first failed'


async def test_the_check_in_is_recorded_even_when_no_message_goes_out() -> None:
	"""The check-in is written first and the fan-out second, so a carrier that refuses everything
	still leaves the board correct. The person *is* safe whatever the gateway did with the text, and
	a check-in lost because an SMS failed would be the button failing at the moment it matters."""
	async def _dead(number: str, body: str) -> object:
		raise RuntimeError('carrier down')

	svc = _svc(sms=_dead)
	svc.link_family(GROUP, [MINE, MUM, DAD])
	board = await svc.check_in(MINE, GROUP, AT)
	assert board.members_safe == [MINE]
	assert (await _async_board(svc)) == [MINE]


async def _async_board(svc: AlertingService) -> list[str]:
	return svc.family_board(GROUP).members_safe


async def test_a_deployment_with_no_sms_path_reports_zero_rather_than_claiming_a_fan_out() -> None:
	"""Both ports are optional so a unit test can build the service alone. A deployment with neither
	wired still checks people in and still serves the board — it says `sms_sent=0` rather than
	asserting a fan-out it has no gateway for."""
	svc = AlertingService()
	svc.link_family(GROUP, [MINE, MUM])
	board = await svc.check_in(MINE, GROUP, AT)
	assert board.sms_sent == 0 and board.sms_unreachable == []
	assert board.members_safe == [MINE], 'the check-in itself still happened'


async def test_a_notify_false_check_in_does_not_send() -> None:
	"""A replay of a queued check-in, or a check-in relayed from a channel that has already told the
	family, must not text them a second time."""
	svc = _grouped()
	board = await svc.check_in(MINE, GROUP, AT, notify=False)
	assert board.sms_sent == 0
	assert svc._sent == []  # type: ignore[attr-defined]
	# And the body is still composed. It is the message, not the receipt — `sms_sent` is what says
	# whether it went — so a board that carried an empty string whenever nothing was sent would leave
	# a client rendering a blank line where the person's own confirmation belongs.
	assert board.sms_body, 'notify=False emptied the message as well as the send'


# --- the message itself ------------------------------------------------------------------------

async def test_the_message_names_who_is_accounted_for_and_who_is_not() -> None:
	"""A reply that said only "recorded" would leave the person unable to tell whether their family
	had heard anything, which is the whole question the button asks."""
	svc = _grouped()
	board = await svc.check_in(MINE, GROUP, AT)
	body = board.sms_body
	assert body == SMS_FAMILY_SAFE['en'].format(board=SMS_FAMILY_BOARD['en'].format(safe=1, total=3))
	assert '1 of 3' in body


async def test_the_message_says_everyone_when_everyone_has_answered() -> None:
	"""The all-clear is a different sentence, not the count sentence with a full numerator: "3 of 3"
	reads as a tally and "everyone has checked in" reads as the answer."""
	svc = _grouped(members=(MINE, MUM))
	await svc.check_in(MUM, GROUP, AT, notify=False)
	board = await svc.check_in(MINE, GROUP, AT, notify=False)
	assert board.sms_sent == 0, 'notify=False is not a send'
	assert SMS_FAMILY_BOARD_ALL['en'].format(total=2) in board.sms_body


async def test_no_members_subject_appears_in_the_message() -> None:
	"""An SMS lands on a handset that may be shared, and the server has not verified the number
	belongs to the person who asked. §17.2's personal data does not go into that plain text, so the
	message carries counts and never the subject references the board is keyed on."""
	svc = _grouped()
	board = await svc.check_in(MINE, GROUP, AT)
	for subject in (MINE, MUM, DAD):
		assert subject not in board.sms_body
	assert 'subj' not in board.sms_body


async def test_every_message_the_sms_path_can_print_survives_a_gsm7_gateway() -> None:
	"""§5.3's zero-rating and `segment_sms` both turn on the alphabet: an em dash, a curly quote or a
	degree sign is refused at the gateway, and a reply refused there is a person who pressed "I'm
	safe" and heard nothing back. The alphabet is asserted rather than trusted, in every language the
	product can answer in — the English one passing says nothing about the Kiswahili one."""
	tables = (SMS_FAMILY_SAFE, SMS_FAMILY_BOARD, SMS_FAMILY_BOARD_ALL, SMS_FAMILY_NO_GROUP,
	          SMS_FAMILY_MANY_GROUPS, SMS_FAMILY_NOT_SAFE, SMS_FAMILY_THIRD_PARTY,
	          SMS_FAMILY_UNKNOWN_GROUP)
	for table in tables:
		for lang, template in table.items():
			rendered = template.format(safe=1, total=3, board='x')
			assert set(rendered) <= GSM7, f'{lang}: non-GSM7 in {rendered!r}'
			assert segment_sms(rendered) >= 1
			assert lang in SUPPORTED_LANGS, f'{lang} is not a language the product serves'


async def test_the_reply_is_answered_in_a_language_the_product_can_answer_in() -> None:
	"""`answerable` is the language actually answered in, not the one asked for. Serving a Kiswahili
	template beside an English sentence tells the person the opposite of the truth about what the
	product speaks."""
	svc = _grouped()
	board = await svc.check_in(MINE, GROUP, AT, lang='luo')
	assert board.sms_body == SMS_FAMILY_SAFE[answerable('luo')].format(
		board=SMS_FAMILY_BOARD[answerable('luo')].format(safe=1, total=3))


# --- inbound: the message as the button --------------------------------------------------------

def test_a_safe_word_is_a_check_in_and_a_negated_one_is_not() -> None:
	"""The one error here worse than silence. A substring test reads "I am not safe" as "safe" and
	tells a family their relative is accounted for on the strength of a message that says the
	opposite — so the word before the keyword is read."""
	for body in ('safe', 'SAFE', 'Safe!', 'niko salama', 'nikosalama', 'safe karibu',
	             'I am safe', 'tuko salama'):
		assert safe_reply(body), body
	for body in ('I am not safe', 'not safe', 'sio salama', 'si salama', 'unsafe', 'notsafe',
	             'hatuko salama', 'bado salama', 'hatusalama'):
		assert not safe_reply(body), body
		# And the negation has its own answer rather than falling through to §CHAN-3's map. The live
		# probe caught the fall-through: a person saying they are in danger was handed the welcome
		# menu, which is the one reply this message must not get.
		assert safe_intent(body) == 'negated', body


async def test_a_person_saying_they_are_not_safe_is_given_the_line_that_helps() -> None:
	"""The live probe found this and no unit test had: "I am not safe" matched no keyword, fell
	through to the keyword map, and was answered with the welcome menu — a person saying they are in
	danger, handed a list of options. The refusal is an answer, and here the answer is 719."""
	svc = _grouped()
	reply = await svc.check_in_by_msisdn(NUMBERS[MINE], 'I am not safe', AT)
	assert reply == SMS_FAMILY_NOT_SAFE['en']
	assert '719' in reply
	assert svc.checkins() == [], 'a negation filed a check-in'


def test_a_message_about_somebody_else_is_not_the_senders_check_in() -> None:
	"""The negation error one step removed. "My brother is safe" marks the *sender* safe under any
	keyword test, and no keyword list can tell a relayed message from a first-person one — so the
	intent is reported as third-party and the product asks rather than guessing."""
	for body in ('my brother is safe', 'mama yuko salama', 'my family is safe', 'our mother is safe'):
		assert safe_intent(body) == 'third-party', body
		assert not safe_reply(body), body
	# And the first-person forms are still check-ins, including the ones that merely contain a word
	# from the third-party list.
	for body in ('safe', 'niko salama', 'I am safe'):
		assert safe_intent(body) == 'check-in', body


def test_a_safe_word_inside_another_word_is_not_a_check_in() -> None:
	"""`essential_slug`'s rule: matching on substrings makes "act" a hit inside "contact". "unsafe"
	and "safely" are not the keyword, and a report mentioning either must not file a check-in."""
	assert not safe_reply('the water is unsafe')
	assert not safe_reply('I drove safely')
	assert safe_reply('salama')


def test_the_keywords_the_product_prints_are_the_keywords_it_matches() -> None:
	"""The list is data, so a keyword added for a client's benefit must be matched by the server's
	own matcher — a list the router does not read is a list that documents a behaviour nobody has."""
	for keyword in SMS_SAFE_KEYWORDS:
		assert safe_reply(keyword), keyword


async def test_an_unlinked_number_is_told_it_is_unlinked_rather_than_ignored() -> None:
	"""An SMS that gets no answer is indistinguishable from a network that dropped it. Every branch
	answers, and the refusal is an answer: an unlinked number is told it is unlinked and given the
	719 line, which is more than silence would have told them."""
	svc = _grouped()
	reply = await svc.check_in_by_msisdn('+254799999999', 'safe', AT)
	assert reply == SMS_FAMILY_NO_GROUP['en']
	assert svc.checkins() == [], 'an unlinked number filed a check-in against somebody'


async def test_a_person_in_two_groups_is_asked_which_one_rather_than_guessed_into_one() -> None:
	"""A check-in filed against the wrong family is a family told the wrong thing, so an ambiguous
	message is answered with a question."""
	svc = _grouped()
	svc.link_family(OTHER_GROUP, [MINE, DAD])
	reply = await svc.check_in_by_msisdn(NUMBERS[MINE], 'safe', AT)
	assert reply == SMS_FAMILY_MANY_GROUPS['en']
	assert svc.checkins() == []
	assert svc.family_board(GROUP).members_safe == [], 'a guess filed a check-in anyway'


async def test_naming_the_group_files_the_check_in_against_it() -> None:
	svc = _grouped()
	svc.link_family(OTHER_GROUP, [MINE, DAD])
	reply = await svc.check_in_by_msisdn(NUMBERS[MINE], 'safe upcountry', AT)
	assert '1 of 2' in reply, reply
	assert svc.family_board(OTHER_GROUP).members_safe == [MINE]
	assert svc.family_board(GROUP).members_safe == [], 'the check-in landed in the other group'


async def test_a_group_name_that_is_not_one_of_theirs_is_refused_by_name() -> None:
	"""A check-in addressed to somebody else's family, filed against this person's, tells two
	families the wrong thing at once — so the name is checked against every group on record, not only
	against the sender's, which is the difference between "named nothing" and "named a stranger's"."""
	svc = _grouped()
	svc.link_family(OTHER_GROUP, [DAD])
	reply = await svc.check_in_by_msisdn(NUMBERS[MINE], 'safe upcountry', AT)
	assert reply == SMS_FAMILY_UNKNOWN_GROUP['en']
	assert svc.checkins() == [], 'the check-in was filed against the wrong family'


async def test_a_person_with_one_group_is_not_asked_which_one_by_a_trailing_word() -> None:
	"""With exactly one group there is nothing to ask: the person said they are safe, and which
	group they meant is not in doubt. Refusing "safe please" for want of a group name would make the
	canonical bare "SAFE" the only message that works, which is not how anyone types."""
	svc = _grouped()
	reply = await svc.check_in_by_msisdn(NUMBERS[MINE], 'safe please', AT)
	assert '1 of 3' in reply, reply
	assert svc.family_board(GROUP).members_safe == [MINE]


async def test_the_reply_to_a_check_in_is_the_message_the_family_received() -> None:
	"""One string composed once. A second call to the composer is a second chance for the reply and
	the delivered message to differ, and the person reading one would have no way to tell."""
	svc = _grouped()
	reply = await svc.check_in_by_msisdn(NUMBERS[MINE], 'safe', AT)
	bodies = {body for _, body in svc._sent}  # type: ignore[attr-defined]
	assert bodies == {reply}, bodies


async def test_an_sms_check_in_is_recorded_as_having_come_over_sms() -> None:
	"""`SafetyCheckIn.channel` is what makes §ALT-002's SMS leg auditable after the fact: a
	deployment asked to show the feature works without data can show which check-ins arrived that
	way, and a board that stored only the instant could not."""
	svc = _grouped()
	await svc.check_in_by_msisdn(NUMBERS[MINE], 'safe', AT)
	records = svc.checkins()
	assert len(records) == 1
	assert records[0].channel == 'sms' and records[0].subject_ref == MINE
	# And the button's own path says so too, rather than inheriting the default by accident.
	await svc.check_in(MUM, GROUP, AT, notify=False)
	assert svc.checkins()[1].channel == 'native'


async def test_a_retried_message_is_one_check_in_and_not_two() -> None:
	"""A gateway that retries and a client that queues and resends are one act. The record is keyed
	on a derived id, so the second arrival lands on the first rather than appearing twice on a board
	whose whole purpose is counting who is accounted for."""
	svc = _grouped()
	await svc.check_in_by_msisdn(NUMBERS[MINE], 'safe', AT)
	await svc.check_in_by_msisdn(NUMBERS[MINE], 'safe', AT)
	assert len(svc.checkins()) == 1
	assert svc.family_board(GROUP).members_safe == [MINE]


async def test_an_inbound_check_in_still_texts_the_members_who_have_not_answered() -> None:
	"""The SMS path is not a lesser version of the feature: a person who checks in over SMS reaches
	the same fan-out, so a family whose phones are all feature phones is told by the same rule."""
	svc = _grouped()
	await svc.check_in_by_msisdn(NUMBERS[MINE], 'safe', AT)
	assert sorted(n for n, _ in svc._sent) == sorted([NUMBERS[MUM], NUMBERS[DAD]])  # type: ignore[attr-defined]


# --- the front door ----------------------------------------------------------------------------

async def test_the_inbound_sms_files_a_check_in_through_the_deployment(tmp_path, monkeypatch) -> None:
	"""The service tests above construct the ports by hand; this one proves `build_services` wires
	§5.4's identity index and §5.3's channel service into the alerting service, and that the carrier's
	own entry point reaches them. A unit test that builds the service itself proves the call and
	nothing about the deployment."""
	secret = 'alt002-secret'
	monkeypatch.setenv('AFYA_WEBHOOK_SECRET', secret)
	services = build_services(db_path=str(tmp_path / 'afya.db'))
	app = create_app(services)
	identity: IdentityService = services['identity']  # type: ignore[assignment]
	alerting: AlertingService = services['alerting']  # type: ignore[assignment]
	await identity.link(IdentityLink(msisdn=NUMBERS[MINE], subject_ref=MINE, consent_id='c1',
	                                 basis=LinkBasis.self_entered))
	alerting.link_family(GROUP, [MINE, MUM])
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		raw, headers = _signed({'from': NUMBERS[MINE], 'text': 'safe'}, secret)
		resp = await c.post('/integrations/telco/sms/inbound', content=raw, headers=headers)
		assert resp.status_code == 200, resp.text
		out = resp.json()
		assert out['intent'] == 'family-check-in'
		assert '1 of 2' in out['reply'], out
		assert alerting.family_board(GROUP).members_safe == [MINE]
		# And the number is §5.4's own spelling, so the SMS path and the app path are one identity.
		assert out['linked'] is True


async def test_a_safe_word_does_not_displace_the_triage_intent(tmp_path, monkeypatch) -> None:
	"""§CHAN-3's keyword map still answers everything that is not a check-in. A router that claimed
	every message containing a common word would take the fever report with it, and the fever report
	is the one the outbreak response cannot lose."""
	secret = 'alt002-secret'
	monkeypatch.setenv('AFYA_WEBHOOK_SECRET', secret)
	app = create_app(build_services(db_path=str(tmp_path / 'afya.db')))
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		for text, intent in (('I have fever', None), ('find facility', None), ('719', None)):
			raw, headers = _signed({'from': '0712345678', 'text': text}, secret)
			resp = await c.post('/integrations/telco/sms/inbound', content=raw, headers=headers)
			assert resp.status_code == 200, resp.text
			assert resp.json().get('intent') == intent, f'{text!r} was claimed by the check-in branch'


async def test_the_check_in_route_defaults_the_instant_rather_than_requiring_it(tmp_path) -> None:
	"""`at_iso` exists so a queued check-in can carry the instant it was actually made, not so every
	person has to have one. A required "When" field is a question the server can answer itself, and a
	question between a person and the button is where a check-in is lost."""
	app = create_app(build_services(db_path=str(tmp_path / 'afya.db')))
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers, subject = await _citizen(c)
		linked = await c.post('/alerting/family/link', headers=headers,
		                      params={'family_ref': GROUP}, json=[subject])
		assert linked.status_code == 200, linked.text
		out = await c.post('/alerting/family/check-in', headers=headers,
		                   params={'subject_ref': subject, 'family_ref': GROUP})
		assert out.status_code == 200, out.text
		assert out.json()['members_safe'] == [subject]
		# And the instant it stamped is a real one, so a client can show it rather than guess it.
		recorded = out.json()['last_checkin_iso']
		assert recorded and recorded.startswith('20'), recorded
		# §MON-004's offline queue still sends its own instant and is still honoured.
		queued = await c.post('/alerting/family/check-in', headers=headers, params={
			'subject_ref': subject, 'family_ref': GROUP, 'at_iso': AT})
		assert queued.status_code == 200, queued.text
		assert queued.json()['last_checkin_iso'] == AT


async def test_a_token_may_not_read_another_persons_check_ins(tmp_path) -> None:
	"""A check-in carries a subject and an instant, which together are a log of who is where. The
	route is self-scoped and filtered to the caller, and this is the half a scope check alone does
	not give: every citizen passes the scope while the subject is whoever the caller typed."""
	app = create_app(build_services(db_path=str(tmp_path / 'afya.db')))
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers, _mine = await _citizen(c)
		_, theirs = await _citizen(c)
		resp = await c.get(f'/alerting/family/check-ins/{theirs}', headers=headers)
		assert resp.status_code == 403, f'{resp.status_code} {resp.text}'


async def test_a_check_in_naming_a_group_the_caller_is_not_in_is_refused(tmp_path) -> None:
	app = create_app(build_services(db_path=str(tmp_path / 'afya.db')))
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers, subject = await _citizen(c)
		await c.post('/alerting/family/link', headers=headers,
		             params={'family_ref': GROUP}, json=[subject])
		resp = await c.post('/alerting/family/check-in', headers=headers,
		                    params={'subject_ref': subject, 'family_ref': 'not-mine'})
		assert resp.status_code == 422, resp.text


async def test_the_family_routes_serve_no_spec_feature_code(tmp_path) -> None:
	"""§3.3 principle 9: a spec id is an internal handle. The board and the reply are read by a
	person on a phone, which is the surface where a code would do the most damage."""
	app = create_app(build_services(db_path=str(tmp_path / 'afya.db')))
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers, subject = await _citizen(c)
		await c.post('/alerting/family/link', headers=headers,
		             params={'family_ref': GROUP}, json=[subject])
		payloads = [
			(await c.post('/alerting/family/check-in', headers=headers,
			              params={'subject_ref': subject, 'family_ref': GROUP})).text,
			(await c.get(f'/alerting/family/{GROUP}', headers=headers)).text,
			(await c.get(f'/alerting/family/check-ins/{subject}', headers=headers)).text,
		]
		for payload in payloads:
			assert not FEATURE_CODE.search(payload), payload


async def test_the_sms_reply_serves_no_spec_feature_code() -> None:
	"""The reply is the one string this feature prints outside the app, on a handset with no client
	to hide anything."""
	svc = _grouped()
	svc.link_family(OTHER_GROUP, [MINE, DAD])
	for reply in (await svc.check_in_by_msisdn(NUMBERS[MINE], 'safe', AT),
	              await svc.check_in_by_msisdn('+254799999999', 'safe', AT),
	              await svc.check_in_by_msisdn(NUMBERS[MINE], 'safe nairobi', AT),
	              await svc.check_in_by_msisdn(NUMBERS[MINE], 'my brother is safe', AT),
	              await svc.check_in_by_msisdn(NUMBERS[MINE], 'I am not safe', AT)):
		assert not FEATURE_CODE.search(reply), reply


# --- the shape of the wiring -------------------------------------------------------------------

def test_the_alerting_module_imports_neither_channels_nor_identity() -> None:
	"""The cycle this design exists to avoid. `afya.channels` imports the triage engine and the
	identity model, so `afya.alerting` importing either back would close the loop — and the port is
	what makes the dependency one-way. The gate reads the module's own imports rather than trusting
	the docstring that says so."""
	tree = ast.parse((ROOT / 'src/afya/alerting/service.py').read_text())
	imported: set[str] = set()
	for node in ast.walk(tree):
		if isinstance(node, ast.ImportFrom) and node.module:
			imported.add(node.module)
		elif isinstance(node, ast.Import):
			imported.update(alias.name for alias in node.names)
	assert not [m for m in imported if m.startswith(('afya.channels', 'afya.identity'))], sorted(imported)


def test_the_ports_are_callables_rather_than_services() -> None:
	"""A deployment passes `channels_svc.send_sms` and `identity_svc.msisdn_for` — the two methods,
	not the two services. Passing the objects would put the import back in the type annotation, and a
	`Protocol` method annotation is evaluated at class-creation time, so the cycle would be a
	collection error rather than a design note."""
	import inspect

	sig = inspect.signature(AlertingService.__init__)
	assert list(sig.parameters) == ['self', 'sms', 'msisdn_of']
	# The ports are optional, so a unit test can build the service alone — and a deployment with
	# neither still checks people in.
	assert sig.parameters['sms'].default is None
	assert sig.parameters['msisdn_of'].default is None


def test_the_check_in_is_recorded_against_the_group_the_caller_named() -> None:
	"""`checkins()` is the feature's own record, and a record that ignored the group argument would
	name every group's check-ins to a caller asking about one."""
	svc = _grouped()
	svc.link_family(OTHER_GROUP, [MINE, DAD])
	assert svc.checkins(GROUP) == [] and svc.checkins(OTHER_GROUP) == []


@pytest.mark.parametrize('lang', sorted(SUPPORTED_LANGS))
def test_every_language_the_product_serves_has_a_family_message(lang: str) -> None:
	"""A language the product claims to serve and has no string for is a person answered in a
	language they did not ask for — `answerable` hides it, and hiding it is how the gap survives."""
	for table in (SMS_FAMILY_SAFE, SMS_FAMILY_NO_GROUP, SMS_FAMILY_NOT_SAFE,
	              SMS_FAMILY_THIRD_PARTY, SMS_FAMILY_UNKNOWN_GROUP, SMS_FAMILY_MANY_GROUPS):
		assert lang in table, f'{lang} is missing from a family string table'


async def test_the_board_carries_the_message_it_sent() -> None:
	"""`sms_body` is what the client shows instead of describing what was sent. Empty when the
	check-in arrived over SMS, because there the reply *is* the message."""
	svc = _grouped()
	board = await svc.check_in(MINE, GROUP, AT)
	assert isinstance(board, FamilyStatus)
	assert board.sms_body
	assert json.dumps(board.model_dump(mode='json')), 'the board must survive a JSON response'
