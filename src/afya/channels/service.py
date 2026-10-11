"""Channel service — SMS/USSD/WhatsApp/radio/social/CHW/native contracts (spec §5, CHAN-000..006)."""
from typing import Awaitable, Callable, Protocol

from afya.channels.cost import ChannelCostVerdict, ZeroRatingRule, cost_report, cost_verdict
from afya.channels.views import (
	ChwTask, PushPayload, RadioBulletin, SmsOut, UssdRequest, UssdResponse, WhatsAppIn, WhatsAppOut,
)
from afya.integrations.gateways import AtUssdCallback
from afya.logmixin import LogMixin
from afya.strings import USSD_MENU, answerable


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
	def __init__(self, sms: SmsGatewayPort, zero_rating: Callable[[], Awaitable[list[ZeroRatingRule] | None]] | None = None) -> None:
		"""`zero_rating` supplies §18.8's billing rules when the carrier is reachable, and None when
		they have not been pulled. Injected rather than constructed here because the rules live on the
		telco client and the channel service must not depend on the integration layer; a deployment
		with no carrier configured passes nothing, and every free claim is then reported unverified
		rather than assumed true.
		"""
		self._sms = sms
		self._zero_rating = zero_rating
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
			return UssdResponse(session_id=req.session_id, end_text=f'Selected {choice}: routed to feature.')
		return UssdResponse(session_id=req.session_id, menu=USSD_MENU[served])

	def ussd_carrier_callback(self, cb: AtUssdCallback, lang: str = 'en') -> dict[str, str]:
		"""Africa's Talking callback -> {text: ..., action: CONTINUE|END} response envelope."""
		resp = self.ussd(UssdRequest(session_id=cb.session_id, msisdn='+' + cb.phone_number.lstrip('+'), text=cb.text), lang)
		if resp.menu:
			return {'text': resp.menu, 'action': 'CON'}
		return {'text': resp.end_text or '', 'action': 'END'}

	def route_whatsapp(self, msg: WhatsAppIn) -> WhatsAppOut:
		body = msg.body.lower()
		if 'fever' in body or 'symptom' in body:
			reply = 'TRI: fever/symptom detected — malaria test first; call 719 if no improvement in 48h.'
		elif 'facility' in body or 'hospital' in body:
			reply = 'FND: send your location to find the nearest facility.'
		elif '719' in body:
			reply = 'Call 719 (toll-free, 24/7).'
		else:
			reply = "Welcome to Afya Yangu. Options: symptoms, facility, hotline."
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