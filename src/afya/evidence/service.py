"""Evidence service — photo+note pipeline: consent, encrypt, hash-verify, dedupe, object-storage port, tier-4 gating."""
import base64
import hashlib
import time
from dataclasses import dataclass, field
from typing import Protocol

from afya.crypto.service import CryptoService
from afya.evidence.views import (
	EvidenceKind, EvidenceReceipt, EvidenceSubmission, EvidenceView, UploadChunk, UploadSession,
)
from afya.logmixin import LogMixin
from afya.registry.service import FeatureRegistry, Tier

MIN_BLOB = 1000
MAX_BLOB = 8_388_608

# §16.4 resumable upload. The chunk size is the *default* the server offers, not a contract on what
# a client may send: a client that slices differently still resumes correctly because chunks are
# addressed by byte offset rather than by index. It is 512 KiB because that is the size at which a
# dropped connection on a Kenyan mobile link costs one chunk rather than the whole photo, while the
# per-chunk hash and JSON framing stay a rounding error against the bytes themselves.
DEFAULT_CHUNK_BYTES = 524_288
# A session that is never finished must not hold memory forever — a phone that dies mid-upload
# leaves a prefix nobody will claim, and on a deployment serving many handsets those add up.
UPLOAD_TTL_MS = 24 * 60 * 60 * 1000


@dataclass
class _Upload:
	"""One upload in progress. Not a model: it holds bytes, and a model that round-trips a
	multi-megabyte prefix through validation is work spent on the one thing that is not the claim."""

	session_id: str
	submission: EvidenceSubmission
	declared_bytes: int
	chunk_bytes: int
	started_at_ms: int
	received: bytearray = field(default_factory=bytearray)


class EvidenceStorePort(Protocol):
	async def put(self, submission: EvidenceSubmission, blob: bytes) -> str: ...


class FileSystemEvidenceStore:
	"""Local object storage (S3/MinIO port swap in production, §15.2).

	What it is handed is always ciphertext: §SEC-002's "photos encrypted" is enforced one level up,
	where the key lives, and this store never sees the key — which is what makes the object-storage
	port a place a copy of the bytes can safely sit. The size contract is on the *sealed* blob, so
	it is checked here rather than trusted from the submission: GCM's tag makes a sealed blob
	strictly larger than the plaintext, and a store that re-checked the plaintext figure would be
	checking a number the caller supplied.
	"""

	def __init__(self, root: str) -> None:
		import os
		os.makedirs(root, exist_ok=True)
		self._root = root
		assert self._root.endswith('evidence') or '/' in root, 'valid root'

	async def put(self, submission: EvidenceSubmission, blob: bytes) -> str:
		assert MIN_BLOB <= len(blob) <= MAX_BLOB, 'blob size cap'
		import os
		path = os.path.join(self._root, f'{submission.submission_id}.blob')
		with open(path, 'wb') as fh:
			fh.write(blob)
		return path


class EvidenceService(LogMixin):
	"""Photo+note pipeline. Gating is by the kind's owning feature, not a hand-kept kind list.

	`SENS-004` (Camera-Based Symptom Capture, Tier 4) owns the symptom-photo kinds; `COM-005`
	(Community Reporting, Tier 3) owns `scene_photo`, which is the same pipeline pointed at an
	environmental hazard. Keeping the mapping here rather than a second list means a new kind
	cannot be added to `EvidenceKind` without declaring which feature governs it — `_FEATURE_OF`
	is asserted total below.

	§SEC-002's fourth bullet — *"Photos encrypted and only shared with explicit per-item consent"* —
	is the two things this class does before it stores anything, and it is worth naming why they are
	here rather than in the route. The route was the only door, and the sync queue is a second one;
	a control fitted to one door is a control the other walks past. So the *consent* is a field the
	model refuses to validate without, and the *encryption* is a refusal in `submit` when no key is
	wired. What is not done: the key is the deployment's at-rest key, so this is encryption against
	a reader of the object store — a dump, a copied bucket — and not against the deployment. That is
	the honest scope of the control, and it is stated rather than implied by the word "encrypted".
	"""

	_FEATURE_OF: dict[EvidenceKind, str] = {
		EvidenceKind.rash: 'SENS-004',
		EvidenceKind.red_eye: 'SENS-004',
		EvidenceKind.pallor: 'SENS-004',
		EvidenceKind.scene_photo: 'COM-005',
	}

	def __init__(self, registry: FeatureRegistry, store: EvidenceStorePort,
	             crypto: CryptoService | None = None) -> None:
		assert set(self._FEATURE_OF) == set(EvidenceKind), 'every evidence kind must declare its feature'
		self._registry = registry
		self._store = store
		# Optional so a unit test that only wants the gating or the dedupe need not mint a key — and
		# the consequence is reported rather than hidden: `encrypted` is False and `submit` refuses,
		# so an unkeyed deployment stores nothing instead of storing plaintext under the label.
		self._crypto = crypto
		self._dedupe: dict[str, str] = {}
		self._ledger: dict[str, tuple[EvidenceView, EvidenceReceipt]] = {}
		# §16.4 resumable upload: bytes written so far, per session, in the order they arrived. Held
		# as a bytearray rather than a list of chunks because `next_offset` is a byte position and a
		# chunk list would make "where does this go" a sum the caller could get wrong.
		self._uploads: dict[str, _Upload] = {}
		assert self._dedupe == {} and self._uploads == {}

	@property
	def encrypted(self) -> bool:
		"""Whether this deployment can seal a photo. Reported, never assumed — the audit row was a
		posture that said encrypted while the bytes went to the store as they arrived."""
		return self._crypto is not None and self._crypto.available

	def _gated(self, kind: EvidenceKind) -> bool:
		"""Whether this kind belongs to a Tier-4 feature, resolved through the registry."""
		return self._registry.get(self._FEATURE_OF[kind]).tier is Tier.tier4

	def _refuse(self, kind: EvidenceKind) -> None:
		"""Refusal text a person may read: no spec code, no tier number."""
		if self._gated(kind):
			raise PermissionError('photo review for symptoms opens when the outbreak response is activated')

	def gate(self, kind: EvidenceKind) -> None:
		"""The dark-feature refusal, callable before anything else about a request is examined.

		Public and called by the route *ahead of* building the submission, because the refusals are
		not interchangeable. A Tier-4 feature is dark whatever the caller does next, so answering
		"you did not consent" to a symptom photo sent while the response is dormant would send a
		person to a checkbox that changes nothing — §11.1's "a control the server refuses", wearing
		a consent label. `submit` calls it too, so the ordering holds for every door and not only
		for the one route that remembered.
		"""
		if self._gated(kind) and not self._registry.tier4_active():
			self._refuse(kind)

	async def submit(self, submission: EvidenceSubmission, blob: bytes) -> EvidenceReceipt:
		assert len(blob) >= MIN_BLOB and len(blob) <= MAX_BLOB, 'blob size contract'
		assert hashlib.sha256(blob).hexdigest() == submission.image_sha256, 'image hash mismatch'
		now_ms = int(time.time() * 1000)
		deduped = submission.image_sha256 in self._dedupe
		# The feature gate first, then consent, then the key. Order is not arbitrary: the dark-feature
		# refusal is true whatever the caller does next, so answering "you did not consent" to a
		# request that consenting would not fix would send someone to a checkbox that changes nothing.
		self.gate(submission.kind)
		# §SEC-002's consent, re-asserted here as well as on the model: the model is the gate for
		# anything built through pydantic, and this is the gate for a caller that reached `submit`
		# with a `model_construct`-ed object or a queue replay. Both are cheap and neither is the
		# other's substitute — the model refuses a request, this refuses a store.
		assert submission.consent, (
			'the photo is shared only with the consent recorded for this submission')
		if self._crypto is None or not self._crypto.available:
			# A deployment fault, not the caller's: there is no request that would succeed, and
			# answering 422 would blame the person for the server holding no key.
			raise RuntimeError(
				'this deployment holds no encryption key, so a photo cannot be stored safely; '
				'ask the operator to configure one')
		sealed = self._crypto.seal(blob)
		ref = await self._store.put(submission, sealed.ciphertext)
		self._dedupe.setdefault(submission.image_sha256, submission.submission_id)
		receipt = EvidenceReceipt(submission_id=submission.submission_id, storage_ref=ref, deduped=deduped, gated=self._gated(submission.kind), received_at_ms=now_ms, cipher='aes-256-gcm')
		view = EvidenceView(kind=submission.kind, subject_ref=submission.subject_ref, county=submission.county, note=submission.note, size_bytes=submission.size_bytes, image_sha256=submission.image_sha256)
		self._ledger[submission.submission_id] = (view, receipt)
		self._log_info('evidence stored', id=submission.submission_id, kind=submission.kind.value)
		return receipt

	def view(self, submission_id: str) -> EvidenceView:
		return self._ledger[submission_id][0]

	# --- §16.4 resumable upload ----------------------------------------------------------------

	def open_upload(self, submission: EvidenceSubmission, *, declared_bytes: int,
	                chunk_bytes: int = DEFAULT_CHUNK_BYTES) -> UploadSession:
		"""Start an upload for a photo the caller will send in pieces (§16.4 resumable upload).

		The gate runs here, at the *start*, not at the finish. A symptom photo sent while the
		response is dormant is refused before the first byte rather than after the last one: a
		client that spent 6 MB of a metered link uploading a picture the server was always going to
		refuse has been made to pay for the refusal, and on a link where the upload takes minutes
		that is the difference between a person retrying and a person giving up.

		`declared_bytes` is checked against the same cap the single-shot path uses, so the two doors
		admit the same photos. It is a *declaration*, and the session refuses a prefix longer than it
		— a client that under-declares to slip past the cap would otherwise have the cap checked
		against a number it chose.
		"""
		assert MIN_BLOB <= declared_bytes <= MAX_BLOB, 'declared size is the same cap the single-shot path uses'
		assert chunk_bytes >= 1024, 'a chunk smaller than a kilobyte is framing, not payload'
		self.gate(submission.kind)
		assert submission.consent, 'the photo is shared only with the consent recorded for this submission'
		session = _Upload(
			session_id='UP-' + submission.submission_id.removeprefix('EV-')[:12],
			submission=submission, declared_bytes=declared_bytes, chunk_bytes=chunk_bytes,
			started_at_ms=int(time.time() * 1000),
		)
		self._uploads[session.session_id] = session
		self._log_info('upload opened', session=session.session_id, declared=declared_bytes,
		               chunk_bytes=chunk_bytes)
		return self._session_view(session)

	def append_chunk(self, session_id: str, chunk: UploadChunk) -> UploadSession:
		"""Append one chunk at the offset the client claims, or refuse it.

		Every refusal here is a *resumable* one: the session survives and the caller is told the
		offset to send next. That is the whole point of the mechanism, and it is why a wrong offset
		is a 409 rather than a 422 — the client's next move is to re-read `next_offset` and continue,
		not to abandon an upload that is 90% on the server.

		The order the checks run in is the order of what they cost the client. An offset the server
		already holds is the common case after a dropped connection, so it is answered first and
		without decoding anything; then the chunk's own hash, so a corrupted chunk is refused before
		its bytes are appended to a prefix that would then hash wrong for reasons the client could
		not see; then the declared cap, so a session cannot grow past what it said it would.
		"""
		now_ms = int(time.time() * 1000)
		self._expire(now_ms)
		session = self._uploads.get(session_id)
		if session is None:
			raise KeyError('no upload in progress under that session')
		have = len(session.received)
		if chunk.offset < have:
			# Bytes the server already holds. Not an error the client caused — a retry after an
			# unacknowledged chunk is exactly this — so the answer is the true position, not a
			# refusal. Returning `next_offset` is what makes the retry safe to issue blindly.
			self._log_info('upload chunk already held', session=session_id, offset=chunk.offset, have=have)
			return self._session_view(session)
		if chunk.offset > have:
			raise ValueError(
				f'the server holds {have} bytes and this chunk starts at {chunk.offset}, so a gap '
				f'would be written; resume from byte {have}')
		raw = base64.urlsafe_b64decode(chunk.data + '=' * (-len(chunk.data) % 4))
		if hashlib.sha256(raw).hexdigest() != chunk.chunk_sha256:
			raise ValueError('this chunk arrived corrupted; send it again from the same offset')
		if have + len(raw) > session.declared_bytes:
			raise ValueError(
				f'this upload declared {session.declared_bytes} bytes and the chunk would take it past '
				f'that; open a new upload with the correct size')
		session.received.extend(raw)
		return self._session_view(session)

	async def finish_upload(self, session_id: str) -> EvidenceReceipt:
		"""Complete an upload whose every byte has arrived, through the same door as a single-shot one.

		The reassembled bytes go through `submit`, which is deliberate and is the reason this method
		is four lines: the hash check, the consent assertion, the encryption and the store are the
		*same* controls, so an upload cannot arrive at a stored photo by a path that skips one. A
		resumable path that sealed its own bytes would be a second implementation of §SEC-002, and
		the second implementation is where the control goes missing.
		"""
		session = self._uploads.get(session_id)
		if session is None:
			raise KeyError('no upload in progress under that session')
		blob = bytes(session.received)
		if len(blob) != session.declared_bytes:
			raise ValueError(
				f'{len(blob)} of {session.declared_bytes} bytes have arrived; the upload is not complete')
		submission = session.submission.model_copy(update={'size_bytes': len(blob)})
		receipt = await self.submit(submission, blob)
		del self._uploads[session_id]
		self._log_info('upload finished', session=session_id, bytes=len(blob))
		return receipt

	def upload_session(self, session_id: str) -> UploadSession:
		"""What the server holds for this upload — the answer a resuming client asks for."""
		self._expire(int(time.time() * 1000))
		session = self._uploads.get(session_id)
		if session is None:
			raise KeyError('no upload in progress under that session')
		return self._session_view(session)

	def _expire(self, now_ms: int) -> None:
		"""Drop sessions nobody finished. Expiry is reported at the session's own TTL rather than
		leaving a client to guess why a resume answered 404."""
		dead = [sid for sid, up in self._uploads.items() if now_ms - up.started_at_ms > UPLOAD_TTL_MS]
		for sid in dead:
			del self._uploads[sid]
		if dead:
			self._log_info('uploads expired', count=len(dead))

	def _session_view(self, session: _Upload) -> UploadSession:
		have = len(session.received)
		complete = have == session.declared_bytes
		return UploadSession(
			session_id=session.session_id, submission_id=session.submission.submission_id,
			subject_ref=session.submission.subject_ref, kind=session.submission.kind, declared_bytes=session.declared_bytes,
			chunk_bytes=session.chunk_bytes, received_bytes=have, next_offset=have, complete=complete,
			expires_at_ms=session.started_at_ms + UPLOAD_TTL_MS,
			note=(
				f'{have} of {session.declared_bytes} bytes received; send the next chunk at byte {have}'
				if not complete else
				f'all {session.declared_bytes} bytes received; call the finish step to store the photo'
			),
		)