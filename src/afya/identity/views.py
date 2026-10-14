"""Identity models — §5.4's single identity model (phone number, with optional linkage to a profile).

§5.4 names one identity and §17.2 puts an MSISDN in the personal-data class, so the two sections meet
here: the model that makes channels share a subject is also the model that must not let a phone number
become a lookup key for anyone who asks.
"""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from afya.ids import uuid7str

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class LinkBasis(str, Enum):
	"""How a phone came to be joined to an app profile.

	§5.4 says the linkage is *optional*, and §17.1 wants the DPA basis for a processing act. A single
	"linked" flag would say neither, so the basis travels with the link: a person who typed their own
	number in the app is a different act from a CHW who registered them, and the second is the one
	§17.2's withdrawal has to be able to undo.
	"""
	self_entered = 'self_entered'
	verified_otp = 'verified_otp'
	chw_registered = 'chw_registered'
	facility_registered = 'facility_registered'


class IdentityLink(BaseModel):
	"""One phone joined to one app profile, with the consent behind it.

	`consent_id` is required rather than optional: §17.1's basis for processing a phone number is the
	consent the person gave, and a link with no consent on record is the automatic merge §3.3's
	"identity is opt-in" forbids. The field is what makes the refusal in `IdentityService.link`
	possible instead of a convention nobody checks.
	"""
	model_config = MODEL_CONFIG
	link_id: str = Field(default_factory=uuid7str)
	msisdn: str = Field(pattern=r'^\+[1-9]\d{6,14}$')
	subject_ref: str = Field(min_length=1)
	consent_id: str = Field(min_length=1)
	basis: LinkBasis


class PhoneConsent(BaseModel):
	"""A consent granted on a channel: a phone and the category granted.

	The body of the carrier-facing consent route rather than two query parameters, because the two
	values belong to one act and a request that supplies one and not the other is not a half-grant to
	be completed — it is a malformed request, and a model refuses it before the service sees it.
	"""
	model_config = MODEL_CONFIG
	msisdn: str = Field(min_length=9, max_length=16)
	category: str = Field(min_length=1)
	# Which channel the session came from. §SEC-001's log is the person's own history and a USSD
	# grant is a session they may not remember, so the carrier says which it was rather than the
	# log guessing. Defaults to `unknown`, never to `app`.
	channel: str = Field(pattern='^(app|ussd|sms|whatsapp|chw|unknown)$', default='unknown')


class CaseReportRef(BaseModel):
	"""A case report as the identity model sees it: an identifier and the reporter behind it.

	The case-report store itself is `afya.community`; this is the projection §5.4's dedup needs, and
	it is deliberately *not* a phone number. Carrying the number here would make the identity index a
	lookup key for the surveillance store, which §17.2 does not allow — so the key is the subject, and
	the phone stays where the person gave it.
	"""
	model_config = MODEL_CONFIG
	report_id: str
	dedup_key: str = Field(min_length=1)
	source_channel: str = Field(min_length=1)
