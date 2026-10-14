"""Photo + textual evidence submission models (SENS-004, community reporting; §6, §17.2)."""
from enum import Enum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class EvidenceKind(str, Enum):
	rash = 'rash'
	red_eye = 'red_eye'
	pallor = 'pallor'
	scene_photo = 'scene_photo'


class EvidenceSubmission(BaseModel):
	model_config = MODEL_CONFIG
	submission_id: str = Field(pattern=r'^EV-[ A-Z0-9]{10,}$')  # generated server-side
	kind: EvidenceKind
	subject_ref: str
	county: str
	image_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
	mime: str = Field(pattern=r'^image/(jpeg|webp|png)$')
	size_bytes: int = Field(ge=1000, le=8_388_608)  # 8 MB cap (§16.4 image compression)
	note: str = Field(default='', max_length=1000)
	# §SEC-002's "explicit per-item consent" for the photograph itself, given per submission rather
	# than once at install. Defaults False: a submission that says nothing shares nothing. The
	# validator below is what makes the default mean something — without it the field is a checkbox
	# nobody reads, which is the shape the audit row described.
	consent: bool = False

	@field_validator('note')
	@classmethod
	def strip_note(cls, v: str) -> str:
		return v.strip()

	@model_validator(mode='after')
	def _a_photo_is_shared_only_on_its_own_consent(self) -> Self:
		"""§SEC-002: the photo is shared with explicit per-item consent, and this is the gate.

		Placed on the model rather than in the route because there is more than one way in — the
		route, the offline sync queue, and any future caller — and a check at one door is a check
		the others walk past. The refusal names what is missing without naming a spec code.
		"""
		if not self.consent:
			raise ValueError(
				'this photo is shared only if you agree to share it — tick the consent box for '
				'this submission, or send the note without the picture')
		return self


class EvidenceReceipt(BaseModel):
	model_config = MODEL_CONFIG
	submission_id: str
	storage_ref: str
	deduped: bool
	gated: bool
	received_at_ms: int
	# §SEC-002's "photos encrypted". The cipher the stored bytes are under, named on the receipt so
	# a client can say what happened to the picture rather than showing a tick and a guess. There is
	# no `none`: a submission that could not be sealed is refused, so a receipt exists only for
	# ciphertext — a `cipher='none'` value would be a label on plaintext, which is the finding.
	cipher: str = Field(pattern=r'^aes-256-gcm$')


class EvidenceView(BaseModel):
	model_config = MODEL_CONFIG
	kind: EvidenceKind
	subject_ref: str
	county: str
	note: str
	size_bytes: int
	image_sha256: str