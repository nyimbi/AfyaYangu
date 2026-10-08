"""Telco / WhatsApp Business gateway clients (spec §5, §15.2, §18.8) — contract-tested against real HTTP."""
import httpx
from pydantic import BaseModel, ConfigDict, Field

from afya.channels.views import SmsOut

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class AtUssdCallback(BaseModel):
	"""Africa's Talking USSD callback payload (sessionId/serviceCode/phoneNumber/text)."""
	model_config = MODEL_CONFIG
	session_id: str
	phone_number: str = Field(pattern=r'^\+?\d{8,15}$')
	text: str = ''


class AtSmsRestSend:
	"""Zero-rated SMS via Africa's Talking REST (used when AT_API_KEY present)."""

	def __init__(self, base_url: str, api_key: str, username: str, client: httpx.AsyncClient) -> None:
		self._base = base_url.rstrip('/')
		self._key = api_key
		self._user = username
		self._http = client
		assert self._base.startswith('http') and self._key and self._user, 'AT config incomplete'

	async def send(self, msg: SmsOut) -> str:
		resp = await self._http.post(
			f'{self._base}/version1/messaging',
			json={'username': self._user, 'to': [msg.to_msisdn], 'message': msg.body},
			headers={'apiKey': self._key, 'content-type': 'application/json'},
		)
		resp.raise_for_status()
		return str(resp.json().get('SMSMessageData', {}).get('Recipients', [{}])[0].get('messageId', 'at-accepted'))


class WhatsAppBusinessClient:
	"""Meta WhatsApp Business Cloud API message send (CHAN-003 outbound)."""

	def __init__(self, phone_number_id: str, token: str, client: httpx.AsyncClient, api_base: str = 'https://graph.facebook.com') -> None:
		self._id = phone_number_id
		self._token = token
		self._http = client
		self._base = api_base.rstrip('/')
		assert self._id and self._token and self._base.startswith('http'), 'WA config incomplete'

	async def send_text(self, to_msisdn: str, body: str) -> str:
		resp = await self._http.post(
			f'{self._base}/v22.0/{self._id}/messages',
			json={'messaging_product': 'whatsapp', 'to': to_msisdn, 'type': 'text', 'text': {'body': body}},
			headers={'Authorization': f'Bearer {self._token}', 'content-type': 'application/json'},
		)
		resp.raise_for_status()
		return str(resp.json()['messages'][0]['id'])