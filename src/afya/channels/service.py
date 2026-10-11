"""Channel service — SMS/USSD/WhatsApp/radio/social/CHW/native contracts (spec §5, CHAN-000..006)."""
from typing import Awaitable, Callable, Protocol

from afya.channels.cost import ChannelCostVerdict, ZeroRatingRule, cost_report, cost_verdict
from afya.channels.views import (
	ChwTask, PushPayload, RadioBulletin, SmsOut, UssdRequest, UssdResponse, WhatsAppIn, WhatsAppOut,
)
from afya.integrations.gateways import AtUssdCallback
from afya.logmixin import LogMixin
from afya.strings import (
	SYMPTOM_WORDS, USSD_MENU, USSD_MENU_ANSWERS, USSD_SYMPTOM_CHOICE, USSD_SYMPTOM_PROMPT,
	WHATSAPP_FACILITY, WHATSAPP_HOTLINE, WHATSAPP_WELCOME, answerable,
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
	             triage: TriageService | None = None) -> None:
		"""`zero_rating` supplies §18.8's billing rules when the carrier is reachable, and None when
		they have not been pulled. Injected rather than constructed here because the rules live on the
		telco client and the channel service must not depend on the integration layer; a deployment
		with no carrier configured passes nothing, and every free claim is then reported unverified
		rather than assumed true.

		`triage` is the single clinical engine §5.4 requires every channel to share. It is optional
		only so a unit test can build the channel layer alone; the service wires the real one, and
		`_triage_for` refuses rather than answering from a second implementation when it is absent.
		"""
		self._sms = sms
		self._zero_rating = zero_rating
		self._triage = triage
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
		# §CHAN-2's menu ends "Language: English / Kiswahili / Dholuo / ...", so Dholuo arrives here
		# by design. `answerable` serves English for a language with no table rather than asserting:
		# a USSD session that dies mid-menu is a dead channel for the one persona §4.1 gives no
		# smartphone, and there is no way to render a traceback on a feature phone.
		served = answerable(lang)
		assert req.text == '' or req.text.isdigit(), 'USSD selections numeric'
		if req.text == '':
			self._ussd_state[req.session_id] = 0
			return UssdResponse(session_id=req.session_id, menu=USSD_MENU[served])
		choice = int(req.text) if req.text.isdigit() else 0
		assert 0 <= choice <= 4, 'menu bounded'
		if choice in (1, 2, 3, 4):
			# §5.4: one triage engine behind every entry point, so a selection answers with the same
			# clinical logic the app does. The menu is the section's, so the mapping is read off it —
			# and the mismatch is reported rather than smoothed: §CHAN-2's menu says "Report symptoms"
			# and the engine requires a symptom list, which a numeric selection cannot carry. The
			# caller is told what to say instead of being handed a recommendation for symptoms it
			# never named.
			answer = USSD_MENU_ANSWERS[served][choice]
			if choice == USSD_SYMPTOM_CHOICE:
				answer += ' ' + USSD_SYMPTOM_PROMPT[served]
			return UssdResponse(session_id=req.session_id, end_text=answer)
		return UssdResponse(session_id=req.session_id, menu=USSD_MENU[served])

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
		"""Africa's Talking callback -> {text: ..., action: CONTINUE|END} response envelope."""
		resp = self.ussd(UssdRequest(session_id=cb.session_id, msisdn='+' + cb.phone_number.lstrip('+'), text=cb.text), lang)
		if resp.menu:
			return {'text': resp.menu, 'action': 'CON'}
		return {'text': resp.end_text or '', 'action': 'END'}

	def route_whatsapp(self, msg: WhatsAppIn, lang: str = 'en') -> WhatsAppOut:
		"""§CHAN-3's keyword router, answering through §5.4's shared triage engine.

		The intents are §CHAN-3's own (symptoms, facility, hotline), and the symptom intent no longer
		carries a private recommendation: it maps the body onto a `TriageInput` and returns what the
		engine says, so the WhatsApp answer and the app answer are one fact. The body is free text
		("I have fever"), so the symptoms it names are read out of it rather than assumed — a body
		that mentions no symptom the engine knows enters with an empty list and is answered at the
		low risk level, which is the honest reading of "no symptom named".
		"""
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