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
	ppb_api_key: str = ''
	jali_url: str = 'https://jali.health.go.ke/api'
	jali_api_key: str = ''
	pheoc_url: str = 'https://pheoc.health.go.ke/api'
	pheoc_api_key: str = ''
	mohf_url: str = 'https://kmhfl.health.go.ke/api'
	adam_url: str = 'https://adam.health.go.ke/api'
	adam_api_key: str = ''
	adam_client_cert: str = ''
	adam_client_key: str = ''
	sha_url: str = 'https://sha.go.ke/api'
	sha_api_key: str = ''
	telco_zero_rating_url: str = ''
	telco_airtime_url: str = ''
	telco_api_key: str = ''
	webhook_secret: str = ''
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
			ppb_api_key=os.environ.get('PPB_API_KEY', ''),
			jali_url=os.environ.get('JALI_URL', 'https://jali.health.go.ke/api'),
			jali_api_key=os.environ.get('JALI_API_KEY', ''),
			pheoc_url=os.environ.get('PHEOC_URL', 'https://pheoc.health.go.ke/api'),
			pheoc_api_key=os.environ.get('PHEOC_API_KEY', ''),
			mohf_url=os.environ.get('MOHF_URL', 'https://kmhfl.health.go.ke/api'),
			adam_url=os.environ.get('ADAM_URL', 'https://adam.health.go.ke/api'),
			adam_api_key=os.environ.get('ADAM_API_KEY', ''),
			adam_client_cert=os.environ.get('ADAM_CLIENT_CERT', ''),
			adam_client_key=os.environ.get('ADAM_CLIENT_KEY', ''),
			sha_url=os.environ.get('SHA_URL', 'https://sha.go.ke/api'),
			sha_api_key=os.environ.get('SHA_API_KEY', ''),
			telco_zero_rating_url=os.environ.get('TELCO_ZERO_RATING_URL', ''),
			telco_airtime_url=os.environ.get('TELCO_AIRTIME_URL', ''),
			telco_api_key=os.environ.get('TELCO_API_KEY', ''),
			webhook_secret=os.environ.get('AFYA_WEBHOOK_SECRET', ''),
			db_path=os.environ.get('AFYA_DB_PATH') or None,
		)

	@property
	def webhook_authenticated(self) -> bool:
		"""Whether inbound webhooks can be authenticated at all.

		False in dev, where there is no shared secret. The routes read this to decide between
		verifying a signature and refusing, so an unconfigured deployment is a loud failure rather
		than an open endpoint.
		"""
		return bool(self.webhook_secret)

	def adam_cert(self) -> tuple[str, str] | None:
		"""The mTLS pair, or None when the deployment has not configured one (§18.1).

		Returned as a pair only when both halves are present: a certificate without its key is a
		misconfiguration that would otherwise surface as an opaque TLS handshake failure.
		"""
		if self.adam_client_cert and self.adam_client_key:
			return (self.adam_client_cert, self.adam_client_key)
		return None

	def live_vendors(self) -> dict[str, bool]:
		return {
			'sms': bool(self.at_api_key), 'whatsapp': bool(self.wa_token and self.wa_phone_id),
			'adam': bool(self.adam_api_key), 'sha': bool(self.sha_api_key),
			'zero_rating': bool(self.telco_zero_rating_url), 'airtime': bool(self.telco_airtime_url),
		}