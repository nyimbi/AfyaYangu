"""§CHAN-1's `CALLBACK` and §CHAN-2's two `→` prompts, as behaviour rather than as constants.

Three defects met here and they are one defect seen from three sides: the product carried the
*wording* of a callback request in three places and the *mechanism* in none.

1. `USSD_YES_NO_PROMPTS` was defined, asserted against the spec by a test, and cited by an audit row
   for §CHAN-1's callback request — while `ussd()` walked from the symptom selection straight to the
   triage answer. The constant described a conversation the channel did not have.
2. §CHAN-2's item 5 says "Reply with the one you want" and its answer names a language; the handler
   asserted digits, so the one item the section gives to change language was the one item that could
   not be used, and its failure was a 500 on a feature phone.
3. §CHAN-1's Format names "local language option via keyword (e.g., prefix `SW`, `LU`, `KY`)", and
   the inbound route took `lang` as a query parameter — which the person sending a text cannot set.

Each of the three is tested here against what a person does, not against what the tree contains: a
constant that is never reached passes any test that reads the constant.
"""
import pytest

from afya.channels.service import ChannelService
from afya.channels.views import UssdRequest, UssdResponse, WhatsAppIn
from afya.identity.service import IdentityService
from afya.integrations.gateways import AtUssdCallback
from afya.registry.service import FeatureRegistry
from afya.strings import (
	SMS_LANG_PREFIXES, USSD_YES_NO_PROMPTS, WHATSAPP_WELCOME, answerable, sms_language,
	symptoms_named,
)
from afya.triage.service import TriageService

MSISDN = '+254711222333'


def _svc() -> ChannelService:
	return ChannelService(AfricaTalkingSmsPort(), None, TriageService(FeatureRegistry()), IdentityService())


class AfricaTalkingSmsPort:
	"""A port that does not send. The tests here are about what is recorded, not what is delivered."""

	async def send(self, msg: object) -> str:
		return 'at:queued'


def _walk(svc: ChannelService, text: str, lang: str = 'en', session: str = 's1') -> UssdResponse:
	"""`session` is a parameter because a callback request is filed against the session it came from,
	and two requests by one handset have to be two records for the queue's order to mean anything."""
	return svc.ussd(UssdRequest(session_id=session, msisdn=MSISDN, text=text), lang)


def test_the_two_prompts_are_reached_and_the_spec_prints_them() -> None:
	"""The prompt is served, and what is served is the section's own sentence.

	Both halves matter. A walk that reached a *paraphrase* of the prompt would be a second wording of
	a question whose wording is the section's; a walk that served the constant without reaching it is
	the defect being closed. The assertion is against `USSD_YES_NO_PROMPTS` rather than against a
	literal, so the test fails if the tree and the walk drift apart in either direction.
	"""
	svc = _svc()
	first = _walk(svc, '1*1')
	assert first.menu, 'the symptom path asks the first prompt rather than ending'
	assert USSD_YES_NO_PROMPTS[0] in first.menu, first.menu
	second = _walk(svc, '1*1*1')
	assert second.menu and USSD_YES_NO_PROMPTS[1] in second.menu, second.menu


def test_the_recommendation_survives_the_prompts() -> None:
	"""A USSD screen replaces rather than appends, so the advice must be repeated on the prompt.

	The caller paid a session to read it. A prompt that dropped the recommendation would take the
	clinical answer away at the moment it asked a question about it — and the closing screen carries
	it again, because the person who answered `2` to both prompts is the one most likely to need it.
	"""
	svc = _svc()
	assert 'malaria' in (_walk(svc, '1*1').menu or '').lower()
	assert 'malaria' in (_walk(svc, '1*1*1').menu or '').lower()
	assert 'malaria' in (_walk(svc, '1*1*1*1').end_text or '').lower()


def test_a_callback_request_is_recorded_and_readable() -> None:
	"""§CHAN-1's Inbound use case, end to end on the USSD leg.

	The request is filed against the phone that made it, with the symptom that prompted it, and the
	queue is readable — a record nothing can read is not a record, it is a variable.
	"""
	svc = _svc()
	assert svc.callback_requests() == [], 'nothing is requested until the prompt is answered'
	_walk(svc, '1*1*1*1')
	queued = svc.callback_requests()
	assert len(queued) == 1, queued
	assert queued[0].msisdn == MSISDN and queued[0].symptom == 'fever'
	assert queued[0].location_shared is True, 'the first prompt was answered 1'
	assert queued[0].handled is False


def test_answering_no_requests_nothing() -> None:
	"""The load-bearing default. `2` is a person who was asked and declined, and a queue that filled
	on a declined prompt would have the whole country requesting a call.

	The location half asserts *consent*, not transmission, which is what the prompt collects: a USSD
	session carries no coordinates, and `CallbackRequest.location_shared`'s own docstring says so.
	The old wording — "Your location was not shared" — asserted an act, and on the path where the
	callback prompt is also declined the answer is recorded nowhere at all, so the sentence was
	false in a second way as well.
	"""
	svc = _svc()
	_walk(svc, '1*1*2*2')
	assert svc.callback_requests() == []
	assert 'did not agree to share your location' in (_walk(svc, '1*2*2*2').end_text or '').lower()


def test_the_closing_screen_says_which_of_the_two_happened() -> None:
	"""'No callback' is different news from 'nothing happened'.

	A single closing sentence for both would tell a person who declined that a health worker is
	coming, or tell a person who asked that nobody is — and both are worse than saying nothing.
	"""
	svc = _svc()
	asked = _walk(svc, '1*1*1*1').end_text or ''
	declined = _walk(svc, '1*1*2*2').end_text or ''
	assert 'call you' in asked.lower(), asked
	assert 'No callback was requested' in declined, declined
	assert asked != declined


def test_the_closing_screen_reports_the_consent_rather_than_a_transmission() -> None:
	"""The USSD session carries no coordinates, so no sentence may say a location was sent.

	`CallbackRequest.location_shared`'s own docstring calls it "the *consent* §CHAN-2's first prompt
	asks for, not a position", and the screen said "Your location was shared" — an act the channel
	cannot perform, contradicted by the tree's own model. The assertion is a *blocklist of the claim*
	rather than a pin on the new wording, because the defect is a sentence asserting a transmission
	and any future phrasing that does so is the same bug wearing different words.

	Both answers to the first prompt are walked, and both halves of the closing screen are read: the
	consent sentence is composed before the callback sentence is chosen, so a fix applied only to the
	callback-requested path would leave the other one claiming the same thing.
	"""
	svc = _svc()
	for walk in ('1*1*1*1', '1*1*1*2', '1*1*2*1', '1*1*2*2'):
		screen = (_walk(svc, walk).end_text or '').lower()
		assert screen, walk
		assert 'was shared' not in screen and 'was sent' not in screen and 'was recorded' not in screen, (
			f'{walk}: the channel does not transmit a position and does not keep one without a callback'
		)
		assert 'agree' in screen, f'{walk}: the prompt collected an agreement and the screen must name it'
	# A caller who agreed is told what they agreed to, and one who declined is told so plainly.
	agreed = (_walk(svc, '1*1*1*1').end_text or '').lower()
	refused = (_walk(svc, '1*1*2*2').end_text or '').lower()
	assert 'did not agree' not in agreed and 'did not agree' in refused


def test_a_handled_request_leaves_the_default_read() -> None:
	"""The queue is worked, not accumulated. `unhandled_only` defaults True so the default read is
	the work remaining; the record itself is kept, so a request rung back twice is one request."""
	svc = _svc()
	_walk(svc, '1*1*1*1')
	req = svc.callback_requests()[0]
	svc.handle_callback(req.request_id)
	assert svc.callback_requests() == []
	assert [c.request_id for c in svc.callback_requests(unhandled_only=False)] == [req.request_id]
	with pytest.raises(KeyError):
		svc.handle_callback('CB-NOSUCH')


def test_a_call_outcome_settles_the_request_it_closes() -> None:
	"""§18.4's fifth row: the code is recorded, and settles the call it closes.

	`record_call_outcome` is the carrier §18.4's outcome code was missing. The route that received it
	returned `{'recorded': True, 'outcome_code': code}` and stored nothing, so the section's inbound
	row was a wire acknowledging a write it never made — and the code was read nowhere in the tree,
	which is the tell: a field whose only occurrences are the line reading it off the payload and the
	line echoing it back is data the system collects and never uses.

	The outcome is its **own** record, not a field on the queue, and the second half of this test is
	why: the section's row closes every 719 call, but only one of the three rows above it files a
	callback request. A one-tap call and the auto-call on fall detection are dispatched from the SOS
	path and leave nothing in this queue, so an outcome carried on the queue could only ever close a
	third of the calls the row is about.
	"""
	svc = _svc()
	_walk(svc, '1*1*1*1')
	req = svc.callback_requests()[0]
	outcome = svc.record_call_outcome('transported', MSISDN)  # the hotline's spelling, not ours
	assert outcome.call_ref == req.request_id, 'the outcome did not settle the call it closed'
	assert outcome.outcome_code == 'transported'
	assert svc.callback_requests() == [], 'a settled request left the work queue'
	assert svc.callback_requests(unhandled_only=False)[0].handled is True
	# The queue is ordered and a person who asks twice is rung twice, so the code settles the
	# *oldest* open request. Taking the newest is the plausible-looking bug: every "an outcome was
	# recorded" assertion still passes and the call that was actually closed is left open. Two
	# requests is what makes the two orders distinguishable — with one, `[0]` and `[-1]` are the same
	# object and the test proves nothing.
	_walk(svc, '1*1*1*1', session='s2')
	_walk(svc, '1*1*1*1', session='s3')
	first, second = [c.request_id for c in svc.callback_requests()]
	settled_first = svc.record_call_outcome('self_care', MSISDN)
	assert settled_first.call_ref == first, 'the outcome settled the newer call'
	assert [c.request_id for c in svc.callback_requests()] == [second], 'the newer call is still open'

	# A code for a call nobody asked for is still a real outcome. Rows 1 and 2 of §18.4's table —
	# the one-tap call and the fall auto-call — file no callback request, so refusing an outcome
	# with no queue entry behind it would lose the row for two of the three calls it closes.
	orphan = svc.record_call_outcome('transported', '+254799999999')
	assert orphan.call_ref is None, 'an unmatched number settled nothing'
	assert orphan.msisdn == '+254799999999'
	# And a code with no number at all is the section's own Data column — "Outcome code (where
	# consented)" names no number — so it records too rather than being refused.
	nameless = svc.record_call_outcome('self_care')
	assert nameless.call_ref is None and nameless.msisdn is None
	assert [o.outcome_code for o in svc.call_outcomes()] == ['transported', 'self_care', 'transported', 'self_care']
	# A number that is not Kenyan is refused by §5.4's identity model rather than normalised into
	# something that looks like one, which is the same rule every channel entry point follows.
	with pytest.raises(ValueError):
		svc.record_call_outcome('transported', '+15551234567')


def test_the_carrier_envelope_reports_the_request() -> None:
	"""What the carrier sees. A request taken and not reported is a queue nobody can tell is empty
	because it is empty or because nothing writes to it."""
	svc = _svc()
	cb = AtUssdCallback(session_id='s9', phone_number='254711222333', text='1*1*1*1')
	envelope = svc.ussd_carrier_callback(cb)
	assert envelope['action'] == 'END' and envelope['callback_requested'] == 'true', envelope
	quiet = svc.ussd_carrier_callback(AtUssdCallback(session_id='s8', phone_number='254711222333', text=''))
	assert quiet['action'] == 'CON' and quiet['callback_requested'] == 'false', quiet


def test_item_five_takes_a_word_rather_than_a_digit() -> None:
	"""§CHAN-2's own answer text: "Reply with the one you want".

	The handler asserted digits, so this path was a 500 — on a feature phone, where there is nothing
	to show a traceback and no way to discover that the item is unusable.
	"""
	svc = _svc()
	# Named by the section's own spelling, by the §ACC-002 code, and in the served language.
	for reply in ('Dholuo', 'luo', 'Kiswahili', 'sw'):
		out = _walk(svc, reply)
		assert out.end_text, f'{reply!r} answered with a menu rather than a language'
	# Dholuo has no table, so the person is told what they will actually get rather than accepted
	# into a session that claims a language it is not serving.
	assert 'Dholuo' in (_walk(svc, 'Dholuo').end_text or '')
	assert 'English' in (_walk(svc, 'Dholuo').end_text or '')
	assert 'Kiswahili' in (_walk(svc, 'Kiswahili').end_text or '')


def test_an_unknown_language_reply_reserves_the_menu() -> None:
	"""Not a 500, and not a guess. Matching 'Klingon' to the nearest language would put a person in
	a language nobody chose; the menu is the honest answer to a reply that named nothing."""
	svc = _svc()
	out = _walk(svc, 'Klingon')
	assert out.menu and not out.end_text, out


def test_the_language_prefix_is_read_off_the_body() -> None:
	"""§CHAN-1's Format: "local language option via keyword (e.g., prefix `SW`, `LU`, `KY`)".

	The prefix is read off the body the person sent, because `lang` is a query parameter and the
	sender of a text cannot set one. The three prefixes the section prints are the ones asserted
	here; the rest of the map is §ACC-002's code list.
	"""
	for prefix in ('SW', 'LU', 'KY'):
		assert prefix in SMS_LANG_PREFIXES, f'§CHAN-1 prints {prefix} and the map does not read it'
	assert sms_language('SW na homa') == ('sw', 'na homa')
	assert sms_language('LU an gi tuo') == ('luo', 'an gi tuo')
	assert sms_language('KY: ndi mũrimu') == ('ki', 'ndi mũrimu')


def test_a_body_with_no_prefix_is_unchanged() -> None:
	"""Optional, not required. Every existing sender keeps working, and a body that merely *starts*
	with those letters is a word rather than a prefix — 'SWAHILI' is not a request for Kiswahili,
	and stripping it would silently eat the first word of a real report."""
	assert sms_language('fever and bleeding') == ('en', 'fever and bleeding')
	assert sms_language('SWAHILI ni lugha') == ('en', 'SWAHILI ni lugha')
	assert sms_language('   ') == ('en', '   ')
	# A bare prefix is a person who asked for a language and then stopped. The language comes back
	# with an empty remainder, and the caller's own "needs text" refusal handles the rest rather
	# than this function returning a language for a message with nothing in it.
	assert sms_language('SW:') == ('sw', '')


def test_the_asked_for_language_is_not_the_served_one() -> None:
	"""The distinction the whole mechanism turns on. `sms_language` reports what was *asked for*;
	`answerable` decides what is *served*. Dholuo has a prefix and no table, so the two differ — and
	the route reports both rather than letting the prefix imply a translation that does not exist.
	"""
	asked, _ = sms_language('LU na homa')
	assert asked == 'luo'
	assert answerable(asked) == 'en', 'Dholuo has no table and the fallback must be visible'
	assert answerable(asked) != asked, 'which is what `language_fallback` reports'


def test_a_report_written_in_kiswahili_reaches_the_engine() -> None:
	"""The other half of the prefix, and the half that was missing.

	Reading the prefix off the body and then reading only English symptom words is a mechanism that
	appears to work: the sender asked for Kiswahili, got Kiswahili, and had their fever dropped. The
	vocabulary is read in the language the report was written in, translated onto the engine's own
	keys rather than into new ones.
	"""
	assert symptoms_named('nina homa', 'sw') == ['fever']
	assert symptoms_named('kuhara na kutapika', 'sw') == ['diarrhoea', 'vomiting']
	# Longest phrase first: "maumivu ya kichwa" contains "kichwa", and a report that counted one
	# symptom twice is a report the triage thresholds read wrong.
	assert symptoms_named('maumivu ya kichwa', 'sw') == ['headache']
	assert symptoms_named('maumivu ya misuli', 'sw') == ['muscle_pain']
	# English is unaffected, and a body naming nothing returns nothing rather than guessing from the
	# language it asked to be answered in.
	assert symptoms_named('fever and bleeding') == ['fever', 'bleeding']
	assert symptoms_named('habari za afya', 'sw') == []
	assert symptoms_named('nina homa', 'luo') == [], 'no word map, so no symptom is claimed'


def test_the_swahili_report_gets_the_swahili_triage_answer() -> None:
	"""Through the router, which is where the two halves meet. A `SW` body naming a fever in Swahili
	must reach §6.3's malaria trap and be answered in Swahili — not with the welcome menu, which is
	what one English word list produced for a message that named a symptom perfectly well."""
	svc = _svc()
	out = svc.route_whatsapp(WhatsAppIn(from_msisdn=MSISDN, body='nina homa'), lang='sw')
	assert 'malaria' in out.reply.lower(), out.reply
	assert out.reply == WHATSAPP_WELCOME['sw'] or 'Karibu' not in out.reply, out.reply


def test_every_screen_the_walk_serves_fits_the_sections_budget() -> None:
	"""§CHAN-2's Session limits: "Must complete within 2 USSD sessions (approx. 360 characters)".

	The walk is four levels deep now rather than two, and a prompt that carried the recommendation
	*and* both questions would be the way a section's budget gets spent without anyone noticing:
	the screens are all served and the caller is cut off mid-sentence on a feature phone. Every
	screen on every path is measured against the section's own figure.
	"""
	from afya.strings import USSD_SESSION_LIMIT_CHARS

	svc = _svc()
	for symptom in ('1', '2', '3', '4', '5'):
		for tail in ('', '*1', '*1*1', '*2', '*2*2'):
			out = _walk(svc, f'1*{symptom}{tail}')
			screen = out.menu or out.end_text or ''
			assert screen, f'1*{symptom}{tail} served nothing'
			assert len(screen) <= USSD_SESSION_LIMIT_CHARS, f'1*{symptom}{tail}: {len(screen)} chars'
