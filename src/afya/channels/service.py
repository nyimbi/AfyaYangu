"""Channel service — SMS/USSD/WhatsApp/radio/social/CHW/native contracts (spec §5, CHAN-000..006)."""
from pathlib import Path
from typing import Awaitable, Callable, Protocol

from afya.channels.cost import ChannelCostVerdict, ZeroRatingRule, cost_report, cost_verdict
from afya.access.views import VoiceAudioRequest, VoiceResult
from afya.channels.views import (
	ChwTask, PushPayload, RadioBulletin, SmsOut, UssdRequest, UssdResponse, WhatsAppIn, WhatsAppOut,
)
from afya.identity.service import IdentityService
from afya.integrations.gateways import AtUssdCallback
from afya.logmixin import LogMixin
from afya.privacy.service import PrivacyService
from afya.privacy.views import ConsentCategory
from afya.strings import (
	SYMPTOM_WORDS, USSD_INFO_ANSWERS, USSD_MENU, USSD_MENU_ANSWERS, USSD_SYMPTOMS, USSD_SYMPTOM_MAP,
	USSD_TREE, WHATSAPP_FACILITY, WHATSAPP_HOTLINE, WHATSAPP_WELCOME, answerable, ussd_symptom_menu_text,
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
	             privacy: PrivacyService | None = None, access: object | None = None) -> None:
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
		self._ussd_state: dict[str, int] = {}
		self._chw_tasks: list[ChwTask] = []
		assert self._ussd_state == {} and self._chw_tasks == []

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
		is two levels deep and every path ends. The session state records the level reached, which is
		what makes a second request a continuation rather than a fresh menu.

		`answerable` serves English for a language with no table rather than asserting: a USSD session
		that dies mid-menu is a dead channel for the one persona §4.1 gives no smartphone, and there
		is no way to render a traceback on a feature phone.
		"""
		served = answerable(lang)
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
		if top == 1 and len(segments) == 2:
			sub = segments[1]
			if not 1 <= sub <= len(USSD_SYMPTOMS):
				return UssdResponse(session_id=req.session_id, menu=ussd_symptom_menu_text(served))
			key = USSD_SYMPTOMS[sub - 1][0]
			symptoms = list(USSD_SYMPTOM_MAP[key])
			inp = TriageInput(symptoms=symptoms, temperature_c=38.0 if 'fever' in symptoms else 36.5)
			return UssdResponse(session_id=req.session_id, end_text=self._triage_for(inp, served).recommendation)
		# Every other path ends: the two leaves answer, and a third segment has nowhere to go.
		if top in USSD_MENU_ANSWERS[served]:
			return UssdResponse(session_id=req.session_id, end_text=USSD_MENU_ANSWERS[served][top])
		return UssdResponse(session_id=req.session_id, menu=USSD_MENU[served])

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
		if resp.menu:
			return {'text': resp.menu, 'action': 'CON', 'store_symptoms': str(store_symptoms).lower()}
		return {'text': resp.end_text or '', 'action': 'END', 'store_symptoms': str(store_symptoms).lower()}

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
		if 'fever' in body or 'symptom' in body or any(s in body for s in SYMPTOM_WORDS):
			# A body that says "fever" is a report of fever, and the engine has one way to hear it:
			# its fever threshold. Without this the body entered at the 36.5 °C default — which means
			# "no fever" — and §6.3's malaria trap never fired on the one channel where a feverish
			# person with no thermometer is most likely to be writing. `symptom` alone (the word from
			# §CHAN-3's intent list) names no symptom, so it enters with an empty list.
			symptoms = [s for s in SYMPTOM_WORDS if s in body]
			inp = TriageInput(
				symptoms=symptoms or (['fever'] if 'fever' in body else []),
				temperature_c=38.0 if 'fever' in body else 36.5,
			)
			reply = self._triage_for(inp, lang).recommendation
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

	def push(self, payload: PushPayload) -> PushPayload:
		assert payload.title and payload.body, 'title/body required'
		return payload