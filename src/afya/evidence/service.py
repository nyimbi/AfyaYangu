"""Evidence service — photo+note pipeline: hash-verify, dedupe, object-storage port, tier-4 gating."""
import hashlib
import time
from typing import Protocol

from afya.evidence.views import EvidenceKind, EvidenceReceipt, EvidenceSubmission, EvidenceView
from afya.logmixin import LogMixin
from afya.registry.service import FeatureRegistry

MIN_BLOB = 1000
MAX_BLOB = 8_388_608


class EvidenceStorePort(Protocol):
	async def put(self, submission: EvidenceSubmission, blob: bytes) -> str: ...


class FileSystemEvidenceStore:
	"""Local object storage (S3/MinIO port swap in production, §15.2)."""

	def __init__(self, root: str) -> None:
		import os
		os.makedirs(root, exist_ok=True)
		self._root = root
		assert self._root.endswith('evidence') or '/' in root, 'valid root'

	async def put(self, submission: EvidenceSubmission, blob: bytes) -> str:
		assert 1000 <= len(blob) <= MAX_BLOB, 'blob size cap'
		import os
		path = os.path.join(self._root, f'{submission.submission_id}.blob')
		with open(path, 'wb') as fh:
			fh.write(blob)
		return path


class EvidenceService(LogMixin):
	TIER4_KINDS = {EvidenceKind.rash, EvidenceKind.red_eye, EvidenceKind.pallor}

	def __init__(self, registry: FeatureRegistry, store: EvidenceStorePort) -> None:
		self._registry = registry
		self._store = store
		self._dedupe: dict[str, str] = {}
		self._ledger: dict[str, tuple[EvidenceView, EvidenceReceipt]] = {}
		assert self._dedupe == {}

	def _gated(self, kind: EvidenceKind) -> bool:
		return kind in self.TIER4_KINDS

	async def submit(self, submission: EvidenceSubmission, blob: bytes) -> EvidenceReceipt:
		assert len(blob) >= MIN_BLOB and len(blob) <= MAX_BLOB, 'blob size contract'
		assert hashlib.sha256(blob).hexdigest() == submission.image_sha256, 'image hash mismatch'
		now_ms = int(time.time() * 1000)
		deduped = submission.image_sha256 in self._dedupe
		if self._gated(submission.kind) and not self._registry.tier4_active():
			raise PermissionError(f'{submission.kind.value} evidence is Tier 4 dormant (SENS-004)')
		ref = await self._store.put(submission, blob)
		self._dedupe.setdefault(submission.image_sha256, submission.submission_id)
		receipt = EvidenceReceipt(submission_id=submission.submission_id, storage_ref=ref, deduped=deduped, gated=self._gated(submission.kind), received_at_ms=now_ms)
		view = EvidenceView(kind=submission.kind, subject_ref=submission.subject_ref, county=submission.county, note=submission.note, size_bytes=submission.size_bytes, image_sha256=submission.image_sha256)
		self._ledger[submission.submission_id] = (view, receipt)
		self._log_info('evidence stored', id=submission.submission_id, kind=submission.kind.value)
		return receipt

	def view(self, submission_id: str) -> EvidenceView:
		return self._ledger[submission_id][0]