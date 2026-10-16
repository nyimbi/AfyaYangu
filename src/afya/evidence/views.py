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


class UploadOpen(BaseModel):
	"""The claims a client makes about a photo it is about to send in chunks (§16.4).

	Separate from `EvidenceSubmission` because it is a different request shape: this carries no
	bytes, only the assertions about them, and the server mints the submission id. The photo's own
	hash is here rather than derived from the chunks as they arrive — the client knows the file it
	holds, and a server-side hash of a reassembled prefix would be checking its own reassembly rather
	than the picture the person chose.
	"""

	model_config = MODEL_CONFIG
	kind: EvidenceKind
	subject_ref: str
	county: str
	note: str = ''
	consent: bool = False
	declared_bytes: int = Field(ge=1000, le=8_388_608)
	image_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
	mime: str = Field(pattern=r'^image/(jpeg|webp|png)$')
	chunk_bytes: int = Field(default=524_288, ge=1024)


class UploadChunk(BaseModel):
	"""One slice of a large photo, addressed by where it sits in the whole (§16.4 resumable upload).

	The offset is the client's claim about the *bytes*, not about the chunk's index, because that is
	the only address a client can recover after a dropped connection: a client that has 3 MB on the
	server and does not know whether chunk 3 landed asks "what do you have" and resumes from the
	answer. An index would require the client to remember how it sliced the file, and a client that
	re-slices differently on resume — which is what a phone restarting the camera app does — would
	then write its bytes into the wrong place and still produce a hash mismatch nobody could explain.

	`chunk_sha256` is checked against the bytes received rather than trusted: a chunk corrupted in
	transit that was appended anyway would surface as a whole-file hash mismatch at the end, after
	the person had spent the bandwidth for every chunk.
	"""

	model_config = MODEL_CONFIG
	offset: int = Field(ge=0)
	chunk_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
	data: str  # base64url, unpadded — the chunk as it travels inside the JSON body


class UploadSession(BaseModel):
	"""What the server holds for an upload in progress, and what a resuming client is told.

	`received_bytes` is the prefix length actually written, and `next_offset` is where the next chunk
	must start. They are the same number today and are both reported because they answer different
	questions: a client asking "did my last chunk land" reads `received_bytes`, and one asking "what
	do I send now" reads `next_offset`. A session whose two disagreed would be a server that had
	written bytes out of order, which is a defect rather than a state.
	"""

	model_config = MODEL_CONFIG
	session_id: str = Field(pattern=r'^UP-[A-Z0-9]{10,}$')
	submission_id: str = Field(pattern=r'^EV-[A-Z0-9]{10,}$')
	# The subject the upload is for. Carried on the session because the three chunk routes are
	# separate requests with no `subject_ref` in their bodies, so this is the only place a route
	# guard can read who the upload belongs to — and without it any token could append bytes to any
	# session by guessing an id derived from a submission id.
	subject_ref: str
	kind: EvidenceKind
	declared_bytes: int = Field(ge=1000, le=8_388_608)
	chunk_bytes: int = Field(ge=1024)
	received_bytes: int = Field(ge=0)
	next_offset: int = Field(ge=0)
	complete: bool
	expires_at_ms: int
	note: str
