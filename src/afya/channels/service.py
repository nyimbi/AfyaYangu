"""Channel service — SMS/USSD/WhatsApp/radio/social/CHW/native contracts (spec §5, CHAN-000..006)."""
from pathlib import Path
from typing import Awaitable, Callable, Protocol

from afya.auth.views import now_ms
from afya.channels.cost import ChannelCostVerdict, ZeroRatingRule, cost_report, cost_verdict
from afya.channels.outbound import follow_up_message
from afya.access.views import LANGUAGE_MATRIX, VoiceAudioRequest, VoiceResult
from afya.channels.views import (
	CallbackRequest, ChannelReport, ChwTask, PushPayload, RadioBulletin, RadioVignette, SmsOut,
	UssdRequest, UssdResponse, WhatsAppIn, WhatsAppOut,
)
from afya.identity.service import IdentityService
from afya.integrations.gateways import AtUssdCallback
from afya.logmixin import LogMixin
from afya.privacy.service import PrivacyService
from afya.privacy.views import ConsentCategory
from afya.strings import (
	LANGUAGE_NAME_FOR, SYMPTOM_WORDS, USSD_CLOSE, USSD_INFO_ANSWERS, USSD_LANGUAGE_SET, USSD_MENU,
	USSD_MENU_ANSWERS, USSD_SYMPTOMS, USSD_SYMPTOM_MAP, USSD_TREE, USSD_YES_NO_PROMPTS,
	WHATSAPP_FACILITY, WHATSAPP_HOTLINE, WHATSAPP_WELCOME, answerable, symptoms_named, ussd_label,
	ussd_symptom_menu_text,
)
from afya.triage.service import TriageService
from afya.triage.views import TriageInput, TriageResult


class SmsGatewayPort(Protocol):
	async def send(self, msg: SmsOut) -> str: ...


GSM7 = set(
	'@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !"#¤%&\'()*+,-./0123456789:;<=>?'
	'¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà'
)


def segment_sms(body: str) -> int:
	assert len(body) <= 1600, 'body exceeds 1600 chars'
	non_gsm = set(body) - GSM7
	assert not non_gsm, f'non-GSM7 chars: {"".join(sorted(non_gsm))[:5]}'
	return max(1, -(-len(body) // 153))


class AfricaTalkingSmsPort:
	"""Zero-rated SMS via Africa's Talking (spec 15.2); endpoint injected."""

	def __init__(self, base_url: str, api_key: str) -> None:
		self._base_url = base_url.rstrip('/')
		self._key = api_key
		assert self._base_url.startswith('http'), 'valid base_url'
		assert self._key, 'api key'

	async def send(self, msg: SmsOut) -> str:
		"""Send regardless of what the message costs the person.

		This used to assert `msg.zero_rated is True`, which read as a §5.3 control and was a
		tautology: the flag was a default this port had just been handed, so the assert could not
		fail and said nothing about whether a carrier agreement existed. Now that the flag is
		resolved from the real rules, refusing here would be worse than the defect — it would drop an
		outbreak alert because the telco paperwork lapsed, trading a shilling for a case. The charge
		is carried on the message and reported by the caller instead.
		"""
		return f'at:queued:{len(msg.body)}'


class ChannelService(LogMixin):
	def __init__(self, sms: SmsGatewayPort, zero_rating: Callable[[], Awaitable[list[ZeroRatingRule] | None]] | None = None,
	             triage: TriageService | None = None, identity: IdentityService | None = None,
	             privacy: PrivacyService | None = None, access: object | None = None,
	             record_signal: Callable[[str, str, str], Awaitable[None]] | None = None) -> None:
		"""`zero_rating` supplies §18.8's billing rules when the carrier is reachable, and None when
		they have not been pulled. Injected rather than constructed here because the rules live on the
		telco client and the channel service must not depend on the integration layer; a deployment
		with no carrier configured passes nothing, and every free claim is then reported unverified
		rather than assumed true.

		`triage` is the single clinical engine §5.4 requires every channel to share. It is optional
		only so a unit test can build the channel layer alone; the service wires the real one, and
		`_triage_for` refuses rather than answering from a second implementation when it is absent.

		`identity` is §5.4's single identity model and `privacy` the registry built on it. Both are
		optional for the same reason and for a sharper one: the channel layer's only identity is an
		MSISDN, and without the index a USSD session cannot see the consent the same person granted in
		the app — so `subject_of` refuses rather than minting a second subject for a phone the app
		already knows, which would be a silent duplicate rather than a visible failure.
		"""
		self._sms = sms
		self._zero_rating = zero_rating
		self._triage = triage
		self._identity = identity
		self._privacy = privacy
		self._access = access
		# §AI-003's signal ledger, as a callable rather than as an `AIService`. The channel layer must
		# not import `afya.ai` — it would be a dependency from the channels onto the detection layer,
		# and `afya.ai` reads the channel vocabulary rather than the other way round. The same
		# late-binding §ALT-002's two legs use, and for the same reason: a deployment with no detector
		# still triages and still files reports, and this is only the leg that counts them.
		self._record_signal = record_signal
		self._ussd_state: dict[str, int] = {}
		# §CHAN-2's two "→" answers, per session. Held beside the level because the walk is over the
		# accumulated input rather than over a conversation: a carrier that resends the whole string
		# re-answers both prompts in one request, and the record is what the report is built from.
		self._ussd_answers: dict[str, tuple[bool, ...]] = {}
		# §CHAN-2's symptom, per session, so the callback request carries the reason for the call.
		self._ussd_symptom: dict[str, str] = {}
		# §CHAN-1's "Callback requests (`CALLBACK`)". The queue the walk writes into and the
		# deployment reads; a request with no queue is a request recorded nowhere, which is the
		# state this was in until the prompt was walked.
		self._callbacks: list[CallbackRequest] = []
		# §5.4's "single case-report backend" for the channels with no CHW behind them. The sink the
		# USSD walk and the WhatsApp router write into; before it existed, both channels answered a
		# person and recorded nothing, and §AI-003's signal ledger — which six app surfaces feed —
		# could not see a fever reported from the two channels built for people without smartphones.
		self._reports: list[ChannelReport] = []
		# Which reports have already been counted into §AI-003's ledger. The routes emit by walking
		# the sink, and a walk that re-emitted on every request would count one fever once per
		# subsequent USSD session — a signal that rises with the number of requests rather than the
		# number of reports, which is the worst possible failure for a detector whose whole job is to
		# notice a rise. Emission is idempotent by this set, not by the caller remembering.
		self._signalled: set[str] = set()
		# §CHAN-1's "Follow-up after a USSD report", composed at filing and sent by the route. Keyed
		# by report id so the send is idempotent per report for the same reason `_signalled` is: the
		# route walks the whole sink, and a walk that re-sent on every request would text a person
		# once per subsequent session — a follow-up that arrives twenty times is worse than none.
		self._follow_ups: dict[str, str] = {}
		self._followed_up: set[str] = set()
		self._chw_tasks: list[ChwTask] = []
		# §CHAN-000's call-in queue, attached after construction rather than passed in, because the
		# live service is built *from* this one's sink — it marks the reports already filed as read
		# before it is handed over. A constructor parameter would have to be built first, and the
		# backlog it must skip does not exist until this sink does. Held as a protocol-shaped object
		# so the channels layer does not import the live layer, the same late binding `_record_signal`
		# uses: a deployment with no live sessions still files reports and still answers callers.
		self._live: object | None = None
		# Every payload handed to `push`. Held rather than fired and forgotten for §16.1's reason:
		# the delivery path is a transport, and what the deployment owes a person must be readable
		# after the transport has had its say.
		self._pushes: list[PushPayload] = []
		assert self._ussd_state == {} and self._ussd_answers == {} and self._ussd_symptom == {}
		assert self._callbacks == [] and self._reports == [] and self._signalled == set()
		assert self._chw_tasks == [] and self._pushes == []

	async def zero_rating_rules(self) -> list[ZeroRatingRule] | None:
		"""§18.8's rules, or None when they have not been pulled.

		None is returned rather than an empty list on purpose: an empty list means the carrier
		answered and covers nothing, which is a finding, while None means nobody asked. A carrier
		that is configured but unreachable is the second case, and it must not be reported as the
		first.
		"""
		if self._zero_rating is None:
			return None
		try:
			return await self._zero_rating()
		except Exception as exc:  # a carrier that is down is not a carrier that charges
			self._log_warn('zero-rating rules unavailable', error=str(exc))
			return None

	async def cost_report(self) -> list[ChannelCostVerdict]:
		"""What each of §5.2's seven channels costs a person right now."""
		return cost_report(await self.zero_rating_rules())

	async def send_sms(self, msisdn: str, body: str) -> SmsOut:
		"""Queue one SMS, with `zero_rated` resolved rather than assumed.

		§5.3 CHAN-1's critical requirement is that the person is not charged, and the thing that
		makes that true is the carrier's zero-rating rule — not a default on this model. The rule is
		read here, at the moment a message is actually sent, because that is the only point where the
		claim reaches a person: a rule that changed and was not re-pulled means the app tells people
		alerts are free when they are not (§18.8).
		"""
		verdict = cost_verdict('sms', await self.zero_rating_rules())
		out = SmsOut(to_msisdn=msisdn, body=body, segments=segment_sms(body), zero_rated=verdict.free_at_point_of_use)
		if verdict.charged:
			self._log_warn('sms is not zero-rated right now', channel='sms', verified=verdict.verified)
		ref = await self._sms.send(out)
		self._log_info('sms queued', ref=ref, segments=out.segments, zero_rated=out.zero_rated)
		return out

	def ussd(self, req: UssdRequest, lang: str = 'en') -> UssdResponse:
		"""§CHAN-2's menu, walked as the tree the section draws.

		The section's structure is five top-level items with a symptom submenu under the first and
		three questions under the third, and it must "complete within 2 USSD sessions" — so the walk
		is four levels deep on the symptom path and every path ends. The session state records the
		level reached, which is what makes a second request a continuation rather than a fresh menu.

		**The two `→` prompts are walked, and until this unit they were not.** `USSD_YES_NO_PROMPTS`
		was defined, asserted against the spec by a test, and cited by an audit row for §CHAN-1's
		callback request — while `ussd()` went from the symptom selection straight to the triage
		answer. A caller was told their risk level and never asked for a callback, so the constant
		described a conversation the channel did not have. The symptom path is now
		`1*<symptom>*<yes/no>*<yes/no>`: the engine's answer first, then the two prompts, because
		§CHAN-2 draws them *after* the symptom entries and a person who has just been told to
		isolate themselves is owed the callback question rather than a menu.

		`answerable` serves English for a language with no table rather than asserting: a USSD session
		that dies mid-menu is a dead channel for the one persona §4.1 gives no smartphone, and there
		is no way to render a traceback on a feature phone.
		"""
		served = answerable(lang)
		# §CHAN-2's item 5 is "Language: English / Kiswahili / Dholuo / ..." and its answer says
		# "Reply with the one you want" — a *word*, not a digit. The digits-only assert below made
		# that reply a 500, so the one item the section gives to change language was the one item
		# that could not be used. Read here, before the assert, and only on the item-5 path.
		if req.text.strip() and req.text.strip()[0].isalpha():
			return self._ussd_language_choice(req, req.text.strip())
		assert all(c.isdigit() or c == '*' for c in req.text) and req.text == req.text.strip(), 'USSD input is digits joined by *'
		# Africa's Talking sends the accumulated input ("1*2"), so the walk is over the segments
		# rather than over the last keystroke — a handler that read only the last digit would lose
		# which submenu the caller was in.
		segments = [int(s) for s in req.text.split('*') if s.strip().isdigit()] if req.text else []
		if not segments:
			self._ussd_state[req.session_id] = 0
			return UssdResponse(session_id=req.session_id, menu=USSD_MENU[served])
		top = segments[0]
		if not 1 <= top <= len(USSD_TREE):
			return UssdResponse(session_id=req.session_id, menu=USSD_MENU[served])
		label, children = USSD_TREE[top - 1]
		assert label, 'every §CHAN-2 item has a label'

		# Level 1 → 2: the two items §CHAN-2 gives children.
		if children and len(segments) == 1:
			self._ussd_state[req.session_id] = top
			if top == 1:
				return UssdResponse(session_id=req.session_id, menu=ussd_symptom_menu_text(served))
			return UssdResponse(session_id=req.session_id, end_text=USSD_MENU_ANSWERS[served][top])
		# Level 2 under "Health information": the three questions, answered from §INF's own content.
		if top == 3 and len(segments) == 2:
			sub = segments[1]
			if 1 <= sub <= len(USSD_INFO_ANSWERS[served]):
				return UssdResponse(session_id=req.session_id, end_text=USSD_INFO_ANSWERS[served][sub - 1])
			return UssdResponse(session_id=req.session_id, end_text=USSD_MENU_ANSWERS[served][3])
		# Level 2 under "Report symptoms": the submenu names the symptom, and §5.4's shared engine
		# answers — so a feature phone and the app give one clinical answer. A submenu entry the
		# engine has no word for ("Cough", "Other") enters with an empty list, which is the honest
		# reading of "named nothing the engine knows" rather than a symptom assumed from the label.
		if top == 1 and len(segments) >= 2:
			sub = segments[1]
			if not 1 <= sub <= len(USSD_SYMPTOMS):
				return UssdResponse(session_id=req.session_id, menu=ussd_symptom_menu_text(served))
			key = USSD_SYMPTOMS[sub - 1][0]
			symptoms = list(USSD_SYMPTOM_MAP[key])
			inp = TriageInput(symptoms=symptoms, temperature_c=38.0 if 'fever' in symptoms else 36.5)
			recommendation = self._triage_for(inp, served).recommendation
			# §CHAN-2 draws two "→" prompts under the symptom entries. The first answer the person
			# gives is recorded and the second prompt follows; the second answer ends the session
			# with the recommendation they were already given, so the clinical advice is not lost to
			# the questions asked after it.
			answers = segments[2:]
			if not answers:
				self._ussd_state[req.session_id] = -top
				self._ussd_symptom[req.session_id] = key
				return UssdResponse(session_id=req.session_id,
					menu=self._ussd_prompt_text(0, served, recommendation))
			if len(answers) == 1:
				self._ussd_answers[req.session_id] = (answers[0] == 1,)
				return UssdResponse(session_id=req.session_id,
					menu=self._ussd_prompt_text(1, served, recommendation))
			location, callback = answers[0] == 1, answers[1] == 1
			self._ussd_answers[req.session_id] = (location, callback)
			# §CHAN-1's Inbound use case, recorded at the point it is asked rather than at the point
			# it is read. A prompt that collects an answer and drops it is the defect this walk was
			# in: the constant existed, the prompt was never served, and had the walk reached the
			# prompt without a queue behind it the request would have been read aloud and lost.
			if callback:
				self.record_callback(req.msisdn, session_id=req.session_id, symptom=key, lang=served,
				                     location_shared=location)
			# §5.4's "single case-report backend" and §CHAN-2's Integration sentence ("Reports flow
			# into the same backend as app and WhatsApp reports"). The walk recorded the callback and
			# the two answers and no report at all, so a fever reported from the one channel §4.1
			# gives to people without smartphones reached no backend and no signal.
			#
			# Filed whether or not the callback was requested, because the report and the request are
			# two different things a person did: declining a call does not retract the symptom. The
			# label is the section's own menu item and travels beside the engine keys, so a "Cough"
			# report — which the engine has no word for — is still a record of what was chosen rather
			# than an empty list the deployment cannot read.
			label = USSD_SYMPTOMS[sub - 1][1]
			self.record_report(req.msisdn, 'ussd', symptoms, lang=served, symptom_label=label,
			                   callback_requested=callback)
			return UssdResponse(session_id=req.session_id,
				end_text=self._ussd_close(served, recommendation, location, callback))
		# Every other path ends: the two leaves answer, and a third segment has nowhere to go.
		if top in USSD_MENU_ANSWERS[served]:
			return UssdResponse(session_id=req.session_id, end_text=USSD_MENU_ANSWERS[served][top])
		return UssdResponse(session_id=req.session_id, menu=USSD_MENU[served])

	def _ussd_prompt_text(self, which: int, served: str, recommendation: str) -> str:
		"""One of §CHAN-2's two `→` prompts, with the engine's answer carried above it.

		The recommendation is repeated on the first prompt because a USSD screen replaces rather than
		appends: the caller has just paid a session to read the advice, and a prompt that dropped it
		would take it away. The two prompts are the section's own words.
		"""
		assert 0 <= which <= 1, f'there are two prompts, not {which + 1}'
		prompt = USSD_YES_NO_PROMPTS[which]
		assert prompt, 'a §CHAN-2 prompt is load-bearing and cannot be empty'
		return f'CON {recommendation}\n{ussd_label(prompt, served)}'

	def _ussd_close(self, served: str, recommendation: str, location: bool, callback: bool) -> str:
		"""The end of the symptom path, once both prompts are answered.

		It says what was recorded, in the language the person is being served rather than the one
		they asked for — the rule `answerable` establishes everywhere else. A caller who asked for a
		callback is told one was requested; a caller who did not is told what to do instead, because
		"no callback" is not the same news as "nothing happened".

		`location` is the **consent** the first prompt collected, not a transmission, and the sentence
		names it as one. The pair used to read "Your location was shared", which asserted a completed
		act this channel cannot perform: a USSD session carries no coordinates, and `afya.channels.
		views:CallbackRequest`'s own docstring says `location_shared` "is the *consent* §CHAN-2's first
		prompt asks for, not a position". The sentence and the docstring contradicted each other, and
		the docstring was right.

		The sentence therefore reads the same whether or not a callback was requested, because it is
		about the agreement rather than about a record — which matters, since the consent reaches
		`CallbackRequest.location_shared` only when a callback was asked for. Promising a record on the
		path that keeps none would be the same defect the other way round.
		"""
		key = 'callback' if callback else 'no_callback'
		recorded = USSD_CLOSE[served]['location' if location else 'no_location']
		return f'{recorded} ' + USSD_CLOSE[served][key].format(recommendation=recommendation)

	def _ussd_language_choice(self, req: UssdRequest, text: str) -> UssdResponse:
		"""§CHAN-2's item 5, answered with a language rather than a digit.

		The section's menu ends "Language: English / Kiswahili / Dholuo / ..." and its own answer
		text says "Reply with the one you want", so the reply is a word. The handler asserted digits
		and the item was therefore the one thing in the menu that could not be used — a dead end
		whose failure was a 500 on a feature phone, where there is nothing to show a traceback.

		The reply is matched against the section's own list by name and against §ACC-002's codes, so
		"Dholuo", "luo" and "5" all name the same language. What comes back is `answerable`'s answer
		and not the request: a person who asks for Dholuo is told they will get English, because the
		alternative is a session that claims to be in Dholuo and is not. That sentence is the whole
		point of this method — silently accepting the choice would be the fake translation the
		module docstring refuses.
		"""
		assert text, 'a language reply is a word'
		wanted = text.strip().lower()
		code: str | None = None
		for name, entry in LANGUAGE_MATRIX.items():
			if wanted in (name.lower(), str(entry['code']).lower()):
				code = str(entry['code'])
				break
		if code is None:
			# Not a language this product knows. Re-serve the menu rather than 500, and rather than
			# guessing: a reply matched to the nearest language would put a person in a language
			# nobody chose.
			return UssdResponse(session_id=req.session_id, menu=USSD_MENU[answerable('en')])
		served = answerable(code)
		return UssdResponse(session_id=req.session_id, end_text=USSD_LANGUAGE_SET[served].format(
			asked=LANGUAGE_NAME_FOR.get(code, code)))

	# --- §5.4's identity and consent crossings ---------------------------------------------------

	def subject_of(self, msisdn: str) -> str:
		"""The subject a channel's phone belongs to, through §5.4's single identity model.

		A channel has an MSISDN and nothing else. Resolving it here — rather than letting each channel
		mint its own handle — is what makes a USSD session, a WhatsApp message and an app profile one
		person, and it is the step the section's cross-channel journeys ("WhatsApp → USSD → CHW") are
		made of. Refuses when the index is absent instead of minting a subject locally: a second index
		is a second person, and the duplicate would be invisible.
		"""
		if self._identity is None:
			raise RuntimeError('the channel service has no identity model wired; §5.4 requires the shared one')
		return self._identity.resolve(msisdn)

	def may_store_symptoms(self, msisdn: str) -> bool:
		"""§5.4's "consent granted on one channel applies across channels", asked from a channel.

		False when the registry is absent, which is the safe direction: a deployment that cannot read
		the consent ledger has no basis to store anything, and a default of True would be the app
		storing health data on the strength of a wiring mistake.

		Called by `ussd_carrier_callback` before it accepts a symptom report, so the grant a person
		made in the app is what permits their USSD report to be kept — the crossing §5.4 claims, at
		the one point where a channel actually has a phone and something worth storing.
		"""
		if self._privacy is None:
			return False
		return self._privacy.has_category_consent_for_phone(msisdn, ConsentCategory.symptom_storage)

	@staticmethod
	def _normalise(raw: str) -> str:
		"""§5.4's identity model's E.164 spelling, imported at call time.

		Deferred because `afya.identity` and this module would otherwise import each other — the
		identity service has no dependency on the channels, and this is the only direction that needs
		the function. A local `'+' + raw` was the second implementation of a rule that must have one.
		"""
		from afya.identity.service import IdentityService
		return IdentityService.normalise(raw)

	def _triage_for(self, inp: TriageInput, lang: str) -> TriageResult:
		"""§5.4's single triage engine, or a refusal that says so.

		The channel layer must not grow a second clinical implementation — that is the drift §5.4's
		"same clinical logic regardless of entry point" exists to forbid, and a channel that answers
		from its own keyword rules is exactly the second engine. A unit test that builds this service
		without one gets a `RuntimeError` rather than a plausible reply.
		"""
		if self._triage is None:
			raise RuntimeError('the channel service has no triage engine wired; §5.4 requires the shared one')
		return self._triage.assess(inp, lang)

	def ussd_carrier_callback(self, cb: AtUssdCallback, lang: str = 'en') -> dict[str, str]:
		"""Africa's Talking callback -> {text: ..., action: CONTINUE|END} response envelope.

		The subject is resolved from the carrier's own `phone_number` rather than minted per session,
		because §5.4's identity is the phone: a person who reports over USSD and then opens the app is
		one subject, and a session-scoped handle would make them a new person every time the menu was
		opened. `store_symptoms` is §5.4's cross-channel consent — the grant made in the app is what
		permits this session's report to be kept, and a session that has no such grant still gets its
		answer, because refusing to triage someone is not a privacy protection.
		"""
		# Normalised through §5.4's one identity model rather than by prepending a `+`: the carrier
		# sends the number bare and the telco inbound route strips a leading zero, so the two entry
		# points used to spell the same handset two ways. Two spellings are two phones, and the dedup
		# and the consent crossing both then find nothing.
		msisdn = self._normalise(cb.phone_number)
		resp = self.ussd(UssdRequest(session_id=cb.session_id, msisdn=msisdn, text=cb.text), lang)
		store_symptoms = self.may_store_symptoms(msisdn)
		if not store_symptoms:
			self._log_info('ussd session has no symptom-storage grant', session=cb.session_id)
		# §CHAN-1's callback request, reported back on the envelope the carrier sees so a request that
		# was taken can be told from one that was not — the alternative is a queue nobody can tell is
		# empty because it is empty or because nothing writes to it.
		queued = [c for c in self._callbacks if c.session_id == cb.session_id]
		envelope = {'store_symptoms': str(store_symptoms).lower(), 'callback_requested': str(bool(queued)).lower()}
		if resp.menu:
			return {'text': resp.menu, 'action': 'CON', **envelope}
		return {'text': resp.end_text or '', 'action': 'END', **envelope}

	def record_callback(self, msisdn: str, session_id: str, symptom: str | None, lang: str = 'en',
	                    location_shared: bool = False) -> CallbackRequest:
		"""File one §CHAN-1 callback request, from whichever channel asked for it.

		The single writer for the queue. Both producers go through it — the USSD walk's second `→`
		prompt and the SMS `CALLBACK` keyword — so the two channels cannot file two shapes of the
		same request, which is the drift §CHAN-2's one-backend clause exists to prevent.

		`session_id` is required and is the *session*, not the person: the SMS path has no session
		and passes the resolved subject, because a request that arrived without one still has to be
		distinguishable from another request by the same phone.
		"""
		assert msisdn.startswith('+254'), 'a callback request is filed against an E.164 number'
		assert session_id, 'a callback request names the session it came from'
		req = CallbackRequest(
			msisdn=msisdn, session_id=session_id, symptom=symptom,
			location_shared=location_shared, lang=answerable(lang), requested_at_ms=now_ms(),
		)
		self._callbacks.append(req)
		self._log_warn('callback requested', msisdn=msisdn, symptom=symptom, channel=session_id.split(':')[0])
		return req

	def callback_requests(self, msisdn: str | None = None, unhandled_only: bool = True) -> list[CallbackRequest]:
		"""§CHAN-1's `CALLBACK` queue, as the deployment reads it.

		`unhandled_only` defaults True because the queue exists to be worked: a reader that returned
		every request ever made would grow without bound and bury the ones nobody has rung back, which
		is the failure mode of a queue with no state. `handled` is the state, and a deployment marks
		it through `handle_callback`.
		"""
		return [c for c in self._callbacks
		        if (msisdn is None or c.msisdn == msisdn) and (not unhandled_only or not c.handled)]

	def handle_callback(self, request_id: str) -> CallbackRequest:
		"""Mark one request taken. The queue is append-only otherwise, so a request rung back twice
		stays one record and the second reader can see it was already answered."""
		for c in self._callbacks:
			if c.request_id == request_id:
				c.handled = True
				self._log_info('callback request handled', request=request_id, symptom=c.symptom)
				return c
		raise KeyError(request_id)

	# --- §5.4's "single case-report backend", on the channels that had no writer ------------------

	def record_report(self, msisdn: str, channel: str, symptoms: list[str], lang: str = 'en',
	                  symptom_label: str | None = None, county: str | None = None,
	                  callback_requested: bool = False) -> ChannelReport:
		"""File one channel report into §5.4's single backend, from whichever channel heard it.

		The single writer, for the reason `record_callback` is: the USSD walk and the WhatsApp router
		must not file two shapes of the same report, and the dedup key has to be built in one place or
		two channels will build two keys for one phone.

		**The key is `IdentityService.dedup_key`, which is the same one `CommunityService.submit_case`
		uses.** That is the whole of §5.4's claim: a person who reports a fever on WhatsApp and then
		the same fever over USSD is one report and not two, and the only way that is true is if both
		sinks key on the one spelling the identity model decides. A local normalisation here would be a
		second key, and a second key finds nothing.

		`consent_to_store` is read from §5.4's consent registry through `may_store_symptoms`, which
		refuses when the registry is absent. It is recorded rather than used to refuse the report: a
		person who has not granted symptom storage still gets triaged — refusing to answer someone is
		not a privacy protection — and the field is what lets the deployment see that the record is
		held without a grant rather than having to infer it. A report the product may not keep is a
		report the product may still answer.

		Refuses rather than raising when the identity model is absent, because a report that cannot be
		keyed is a report that cannot be deduplicated, and §5.4's claim is about the key.
		"""
		assert msisdn.startswith('+254'), 'a channel report is filed against an E.164 number'
		assert channel in ('ussd', 'sms', 'whatsapp', 'app'), f'unknown channel {channel!r}'
		if self._identity is None:
			raise RuntimeError(
				'the channel service has no identity model wired; §5.4 requires the shared one, and a '
				'report with no dedup key is a report that cannot be deduplicated')
		report = ChannelReport(
			channel=channel, msisdn=msisdn, symptoms=list(symptoms), symptom_label=symptom_label,
			county=county, lang=answerable(lang), reported_at_ms=now_ms(),
			dedup_key=self._identity.dedup_key(msisdn), consent_to_store=self.may_store_symptoms(msisdn),
		)
		self._reports.append(report)
		self._log_info('channel report filed', channel=channel, symptoms=len(symptoms),
		               placed=county is not None, stored=report.consent_to_store)
		# §CHAN-1's "Follow-up after a USSD report". Composed here, at filing, because this is where
		# the menu item and the callback answer are both in hand; sent by the route, because the walk
		# is synchronous and a send is not. Composed for the USSD channel only — §CHAN-3's WhatsApp
		# router replies inside the conversation the person is already in, so an SMS on top of that
		# reply would be two messages for one report, and an SMS report already arrives as one.
		if channel == 'ussd':
			self._follow_ups[report.report_id] = follow_up_message(
				symptom_label, lang=report.lang, callback_requested=callback_requested)
		return report

	def channel_reports(self, msisdn: str | None = None, channel: str | None = None,
	                    unhandled_only: bool = False) -> list[ChannelReport]:
		"""§5.4's backend as the deployment reads it, filtered the two ways a reader asks.

		`unhandled_only` defaults **False** here, which is the opposite of the callback queue and
		deliberately so: a callback request exists to be worked and one nobody has rung back is the
		work, while a report is a record of what a person said and the default read is the record.
		A caller that wants the work remaining asks for it by name.
		"""
		return [r for r in self._reports
		        if (msisdn is None or r.msisdn == msisdn)
		        and (channel is None or r.channel == channel)
		        and (not unhandled_only or not r.handled)]

	def reports_for_signal(self) -> list[ChannelReport]:
		"""The reports a locality can be read from — the ones that name a county.

		§AI-003's signal is a rise *in a locality*, and `_record_signal` refuses an event with no
		county for exactly that reason. Every USSD and SMS report today is in this method's complement:
		those channels carry no locality, so the honest count of what the ledger can see from them is
		zero, and this method is how the deployment reads that rather than assuming it. A report that
		names a county — a WhatsApp message with a shared location, or a caller whose area code
		resolved — is counted, and the split is the product's to close by giving the channels a way to
		name where they are.
		"""
		return [r for r in self._reports if r.county is not None]

	def handle_report(self, report_id: str) -> ChannelReport:
		"""Mark one report read. The record is kept, so a report looked at twice is one report."""
		for r in self._reports:
			if r.report_id == report_id:
				r.handled = True
				self._log_info('channel report handled', report=report_id, channel=r.channel)
				return r
		raise KeyError(report_id)

	async def emit_report_signal(self, report: ChannelReport) -> bool:
		"""Count one channel report into §AI-003's ledger, when the report names a locality.

		**The gap this closes is the whole reason the ledger was blind to two channels.** §AI-003's
		early warning counts fever triages, and six app surfaces record their events through
		`_record_signal` — but `ChannelService` was wired to nothing, so a fever reported over USSD or
		WhatsApp never reached the ledger at all. Those are the two channels §4.1 gives to people
		without smartphones, which is to say the population an outbreak in a low-connectivity county
		would show up in first. A detection layer that cannot see them is a detection layer with a
		hole the size of its target.

		Returns whether an event was recorded, and `False` is the honest answer for every USSD and SMS
		report today: those channels carry no locality and `_record_signal` refuses a count with no
		county, because a national count against a county baseline is a number that cannot mean
		anything. So the method reports the split rather than papering over it — the report is held,
		the ledger is told nothing, and the deployment can read `reports_for_signal()` to see exactly
		how many reports it holds that its detector cannot see.

		**Idempotent per report, and that is not a nicety.** The routes emit by walking the sink, so
		without this a fever would be counted once per subsequent USSD session — a signal that rises
		with the number of requests rather than the number of reports, which is the one failure mode a
		rise-detector must not have. The guard is a set of report ids rather than the caller's memory.
		"""
		assert report.report_id, 'a signal is emitted for a report that exists'
		if report.report_id in self._signalled:
			return False
		if self._record_signal is None or report.county is None:
			return False
		# Only a fever is §AI-003's `fever_triage` signal. The ledger's vocabulary is fixed and
		# adding a channel-only signal name would be a second vocabulary the detector does not read.
		if 'fever' not in report.symptoms:
			return False
		await self._record_signal(report.county, 'fever_triage', report.report_id)
		self._signalled.add(report.report_id)
		self._log_info('channel report counted into the signal ledger', report=report.report_id,
		               county=report.county)
		return True

	# --- §CHAN-000's call-in queue, fed from §5.4's one sink -------------------------------------

	def attach_live(self, live: object) -> None:
		"""Hand over the live-session queue this sink feeds. Called once, at wiring time.

		A setter rather than a constructor parameter because the live service is built *from* this
		object's reports — it marks the backlog already filed as read before it is attached. Two
		objects that must each see the other cannot both be constructed first, and the alternative
		(a channel service that reads `services['live']`) is the ordering dependency the services
		dict is deliberately written to avoid.

		Refuses a second attach: two live services reading one sink would queue every question twice,
		and the one that answered it would be the one the clinician is not looking at.
		"""
		assert self._live is None, 'the call-in queue is attached once'
		self._live = live
		self._log_info('live queue attached to the channel sink')

	async def absorb_into_live(self, report: ChannelReport) -> str | None:
		"""Offer one filed report to §CHAN-000's queue, and say whether it became a question.

		Called on the routes that already walk the sink, beside `emit_report_signal` and
		`send_follow_up`, for the same reason: the walk is where a filed report is turned into
		whatever else it is owed, and the queue is one of those things. Returns the question id, or
		`None` when there is no programme on air for this channel or the report carries no words —
		both of which are ordinary and neither of which is an error.

		The absorb is idempotent inside the live service, on the report id. It has to be: the walk
		covers the whole sink on every request, so a person who texted one question would otherwise
		have it queued again each time they opened the USSD menu afterwards.
		"""
		if self._live is None:
			return None
		absorb = getattr(self._live, 'absorb_report', None)
		if absorb is None:
			return None
		question = await absorb(report, now_ms())
		return getattr(question, 'question_id', None) if question is not None else None

	async def send_follow_up(self, report: ChannelReport) -> SmsOut | None:
		"""Send the §CHAN-1 follow-up for one report, once.

		Returns `None` for every report that has no follow-up to send, which is every report from a
		channel other than USSD and every report already followed up. `None` is the honest answer and
		not an error: §CHAN-1's bullet is one entry in a list of six outbound use cases and names the
		USSD channel, so a report that arrives with no session behind it is a report the bullet does
		not cover.

		The send goes through `send_sms`, which is the point. A follow-up composed here and pushed at
		the gateway would be a second outbound path, and the cost flag — the §CHAN-1 Critical
		requirement that decides whether adoption holds — is resolved on the one path that exists. A
		second path is a second place for a message to go out charged.

		**Idempotent by report id, like the signal emit, and the route relies on it.** The USSD route
		walks the whole sink after every session, so without this a person who reported a fever once
		would be texted again on every later session — which is not a follow-up, it is a subscription
		to their own report.
		"""
		assert report.report_id, 'a follow-up is sent for a report that exists'
		body = self._follow_ups.get(report.report_id)
		if body is None or report.report_id in self._followed_up:
			return None
		self._followed_up.add(report.report_id)
		out = await self.send_sms(report.msisdn, body)
		self._log_info('follow-up sent', report=report.report_id, segments=out.segments,
		               plain=out.plain.plain)
		return out

	def route_whatsapp_voice(self, msg: WhatsAppIn, note: Path) -> VoiceResult:
		"""§ACC-002's "voice note triage on WhatsApp", as a transcription and then a triage.

		A WhatsApp voice note reaches the webhook as *media*, not as text, so the router had no body
		to read: it read the media reference as the message and answered at the low risk level,
		because a media id contains no symptom word. The branch that fixes that runs the note through
		the *same* `AccessService.transcribe_audio` the app uses — one recogniser, one triage engine,
		so a person who speaks into WhatsApp and the same person speaking into the app get one
		answer rather than two.

		The language is `msg.voice_note_lang`, which the model requires on a voice note: §ACC-002
		ships recognition per language, and detecting it from a three-word report is how a
		recogniser comes back with a fluent transcript of the wrong words.
		"""
		assert msg.kind == 'voice', 'this path transcribes a voice note and not a text message'
		assert msg.voice_note_lang is not None, 'a voice note must declare its language'
		assert self._access is not None, (
			'the accessibility service is not wired into the channel layer; a voice note cannot be '
			'transcribed without it'
		)
		return self._access.transcribe_audio(  # type: ignore[attr-defined]
			VoiceAudioRequest(
				subject_ref=msg.from_msisdn, lang=msg.voice_note_lang, purpose='symptoms',
			),
			note,
		)

	def route_whatsapp(self, msg: WhatsAppIn, lang: str = 'en') -> WhatsAppOut:
		"""§CHAN-3's keyword router, answering through §5.4's shared triage engine.

		The intents are §CHAN-3's own (symptoms, facility, hotline), and the symptom intent no longer
		carries a private recommendation: it maps the body onto a `TriageInput` and returns what the
		engine says, so the WhatsApp answer and the app answer are one fact. The body is free text
		("I have fever"), so the symptoms it names are read out of it rather than assumed — a body
		that mentions no symptom the engine knows enters with an empty list and is answered at the
		low risk level, which is the honest reading of "no symptom named".
		"""
		assert msg.kind == 'text', (
			'a voice note has no body to read; route it through `route_whatsapp_voice`, which '
			'transcribes it first'
		)
		body = msg.body.lower()
		if 'fever' in body or 'symptom' in body or any(s in body for s in SYMPTOM_WORDS) \
				or symptoms_named(body, lang):
			# A body that says "fever" is a report of fever, and the engine has one way to hear it:
			# its fever threshold. Without this the body entered at the 36.5 °C default — which means
			# "no fever" — and §6.3's malaria trap never fired on the one channel where a feverish
			# person with no thermometer is most likely to be writing. `symptom` alone (the word from
			# §CHAN-3's intent list) names no symptom, so it enters with an empty list.
			#
			# The vocabulary is read in the language the report was written in, which is what
			# §CHAN-1's prefix makes possible and what it obliges: a body that says "nina homa" after
			# a `SW` prefix named a fever, and reading only English words answered it with the welcome
			# menu. The prefix was honoured and the report was dropped.
			symptoms = symptoms_named(body, lang)
			inp = TriageInput(
				symptoms=symptoms or (['fever'] if 'fever' in body else []),
				temperature_c=38.0 if 'fever' in symptoms or 'fever' in body else 36.5,
			)
			reply = self._triage_for(inp, lang).recommendation
			# §5.4's "single case-report backend". A WhatsApp body that named a symptom is a report
			# and this is where it is filed, keyed on the same `dedup_key` the USSD walk and
			# `CommunityService.submit_case` use — which is what makes a person who reports a fever on
			# WhatsApp and the same fever over USSD one report rather than two.
			#
			# Filed only when the body named a symptom the engine heard, and *not* on the bare word
			# "symptom": §CHAN-3's intent list contains "symptom" as a trigger word, and a person
			# asking "what is a symptom?" has asked a question rather than reported one. The guard is
			# the symptom list and not the branch, because the branch is the intent and the list is
			# the report.
			if inp.symptoms:
				self.record_report(msg.from_msisdn, 'whatsapp', inp.symptoms, lang=lang)
		elif 'facility' in body or 'hospital' in body:
			reply = WHATSAPP_FACILITY[answerable(lang)]
		elif '719' in body:
			reply = WHATSAPP_HOTLINE[answerable(lang)]
		else:
			reply = WHATSAPP_WELCOME[answerable(lang)]
		return WhatsAppOut(to_msisdn=msg.from_msisdn, reply=reply)

	async def schedule_bulletin(self, b: RadioBulletin) -> RadioBulletin:
		assert len(b.script) <= 300 * b.duration_s, 'script too long for slot'
		return b

	async def schedule_vignette(self, v: RadioVignette) -> RadioVignette:
		"""§CHAN-000's drama vignette, run through §6.2 and refused when it fails.

		**This is a hard gate, unlike the live answer one section over.** A live answer is spoken
		once by a clinician and the verdicts are carried rather than raised, because refusing to
		answer a caller's question mid-programme helps nobody and there is no second reader. A
		vignette is the opposite on both counts: it is *written*, and it is reviewed before a station
		ever broadcasts it. Refusing costs nothing but a rewrite, and the failure it prevents is the
		one this row's own theme list invites — a vignette about stigma that itself calls somebody
		"an Ebola victim" is a segment that teaches the audience the exact word the section forbids.

		The rules that bite are §6.2's universal ones — `_stigma` (§6.2.9), `_directives` (§6.2.5)
		and `_reader_facing` (§3.3 principle 9) — and *not* the answer-only pair. A vignette is a
		scene between characters, so it is `Subject.content` and not `Subject.answer`: §6.2.1's
		action rule and §6.2.6's forwardability are about an *answer* to a question, and demanding
		an imperative verb of every line of dialogue would refuse a correct script. `_low_literacy`
		still runs and still only flags for review; a long line of dialogue is a writer's choice, not
		a defect, and the review flags are logged rather than raised.

		The script judged is the assembled dialogue — every line's text with its speaker — and not
		the free-text `script` field alone, because a stigmatising word spoken by a character is
		stigmatising whoever typed it, and the `script` field is the narration around the dialogue
		rather than the dialogue itself.
		"""
		# Imported here rather than at module scope: `afya.info.principles` imports `GSM7` from this
		# module, so a top-level import would be a cycle. The same late binding `_triage_for` and the
		# live-session sink use, and for the same reason — this method is the only place in the
		# channels layer that needs §6.2.
		from afya.info.principles import Finding, Subject, judge
		spoken = ' '.join(line.text for scene in v.scenes for line in scene.lines)
		finding: Finding = judge(f'vignette:{v.vignette_id}', spoken, Subject.content)
		failures = finding.failures()
		assert not failures, (
			f'{v.vignette_id} fails §6.2 and cannot be broadcast: '
			+ '; '.join(f'{verdict.rule} — {verdict.detail}' for verdict in failures)
		)
		self._log_info('vignette scheduled', vignette=v.vignette_id, theme=v.theme.value,
		               lang=v.lang, reviews=len(finding.reviews()))
		return v

	async def assign_chw_task(self, task: ChwTask) -> ChwTask:
		self._chw_tasks.append(task)
		assert len([t for t in self._chw_tasks if not t.done]) <= 1000, 'CHW backlog unbounded'
		return task

	def open_tasks(self, chw_ref: str) -> list[ChwTask]:
		return [t for t in self._chw_tasks if t.chw_ref == chw_ref and not t.done]

	async def complete_task(self, task_id: str) -> ChwTask:
		for t in self._chw_tasks:
			if t.task_id == task_id:
				t.done = True
				self._log_info('chw task done', task_id=task_id)
				return t
		raise KeyError(task_id)

	async def push(self, payload: PushPayload) -> PushPayload:
		"""Hand one notification to the delivery path, and record that it went.

		`sent` is a fact about this method, not about the person's handset: the transport here is the
		service's own outbox, and a deployment that wires FCM or APNs behind it is what turns the
		entry into a delivery. That distinction is the point — the predecessor returned the payload
		unchanged and had no call sites, so §11.4's correction was drafted, addressed and never
		handed to anything. A caller that needs to know whether the *person* was reached reads
		`sent`; a caller that needs to know whether the notice is owed reads the payload back.
		"""
		assert payload.title and payload.body, 'title/body required'
		assert payload.subject_ref, 'a notification without a recipient reaches nobody'
		self._pushes.append(payload)
		self._log_info('push queued', subject=payload.subject_ref, category=payload.category)
		return payload

	def pushes(self, subject_ref: str | None = None) -> list[PushPayload]:
		"""What this deployment has handed to the delivery path, newest last."""
		return [p for p in self._pushes if subject_ref is None or p.subject_ref == subject_ref]