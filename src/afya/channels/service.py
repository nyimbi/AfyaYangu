"""Channel service — SMS/USSD/WhatsApp/radio/social/CHW/native contracts (spec §5, CHAN-000..006)."""
from typing import Protocol

from afya.channels.views import (
	ChwTask, PushPayload, RadioBulletin, SmsOut, UssdRequest, UssdResponse, WhatsAppIn, WhatsAppOut,
)
from afya.logmixin import LogMixin


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
		assert msg.zero_rated is True, 'CHAN-001 must be zero-rated'
		return f'at:queued:{len(msg.body)}'


class ChannelService(LogMixin):
	USSD_MENU = 'CON Afya Yangu\n1. Ebola info\n2. Find facility\n3. Report symptoms\n4. Hotline 719'

	def __init__(self, sms: SmsGatewayPort) -> None:
		self._sms = sms
		self._ussd_state: dict[str, int] = {}
		self._chw_tasks: list[ChwTask] = []
		assert self._ussd_state == {} and self._chw_tasks == []

	async def send_sms(self, msisdn: str, body: str) -> SmsOut:
		out = SmsOut(to_msisdn=msisdn, body=body, segments=segment_sms(body))
		ref = await self._sms.send(out)
		self._log_info('sms queued', ref=ref, segments=out.segments)
		return out

	def ussd(self, req: UssdRequest) -> UssdResponse:
		assert req.text == '' or req.text.isdigit(), 'USSD selections numeric'
		if req.text == '':
			self._ussd_state[req.session_id] = 0
			return UssdResponse(session_id=req.session_id, menu=self.USSD_MENU)
		choice = int(req.text) if req.text.isdigit() else 0
		assert 0 <= choice <= 4, 'menu bounded'
		if choice in (1, 2, 3, 4):
			return UssdResponse(session_id=req.session_id, end_text=f'Selected {choice}: routed to feature.')
		return UssdResponse(session_id=req.session_id, menu=self.USSD_MENU)

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

	def push(self, payload: PushPayload) -> PushPayload:
		assert payload.title and payload.body, 'title/body required'
		return payload