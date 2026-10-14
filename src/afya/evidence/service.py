"""Evidence service — photo+note pipeline: consent, encrypt, hash-verify, dedupe, object-storage port, tier-4 gating."""
import hashlib
import time
from typing import Protocol

from afya.crypto.service import CryptoService
from afya.evidence.views import EvidenceKind, EvidenceReceipt, EvidenceSubmission, EvidenceView
from afya.logmixin import LogMixin
from afya.registry.service import FeatureRegistry, Tier

MIN_BLOB = 1000
MAX_BLOB = 8_388_608


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
		assert self._dedupe == {}

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