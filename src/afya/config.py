"""Environment-driven vendor configuration (§15.2/§18.8); all optional at dev time."""
import os
from dataclasses import dataclass, field


@dataclass(slots=True)
class ServiceConfig:
	at_base_url: str = 'https://api.africastalking.com'
	at_api_key: str = ''
	at_username: str = ''
	wa_token: str = ''
	wa_phone_id: str = ''
	ppb_url: str = 'https://ppb.health.go.ke/api'
	jali_url: str = 'https://jali.health.go.ke/api'
	pheoc_url: str = 'https://pheoc.health.go.ke/api'
	mohf_url: str = 'https://kmhfl.health.go.ke/api'
	db_path: str | None = field(default=None)

	@classmethod
	def from_env(cls) -> 'ServiceConfig':
		return cls(
			at_base_url=os.environ.get('AT_BASE_URL', 'https://api.africastalking.com'),
			at_api_key=os.environ.get('AT_API_KEY', ''),
			at_username=os.environ.get('AT_USERNAME', ''),
			wa_token=os.environ.get('WHATSAPP_TOKEN', ''),
			wa_phone_id=os.environ.get('WHATSAPP_PHONE_ID', ''),
			ppb_url=os.environ.get('PPB_URL', 'https://ppb.health.go.ke/api'),
			jali_url=os.environ.get('JALI_URL', 'https://jali.health.go.ke/api'),
			pheoc_url=os.environ.get('PHEOC_URL', 'https://pheoc.health.go.ke/api'),
			mohf_url=os.environ.get('MOHF_URL', 'https://kmhfl.health.go.ke/api'),
			db_path=os.environ.get('AFYA_DB_PATH') or None,
		)

	def live_vendors(self) -> dict[str, bool]:
		return {'sms': bool(self.at_api_key), 'whatsapp': bool(self.wa_token and self.wa_phone_id)}