import hashlib

import pytest

from afya.evidence.service import EvidenceService, FileSystemEvidenceStore
from afya.evidence.views import EvidenceKind, EvidenceSubmission
from afya.registry.service import FeatureRegistry, Tier4Activation


def fake_jpeg() -> bytes:
	return bytes.fromhex('FFD8') + b'jpegevidence' * 90 + bytes.fromhex('FFD9')


@pytest.fixture
def svc(tmp_path) -> EvidenceService:
	reg = FeatureRegistry(Tier4Activation(authorized_by_pheoc=True, dpia_reviewed=True, flag_enabled=True))
	return EvidenceService(reg, FileSystemEvidenceStore(str(tmp_path / 'evidence')))


def _sub(kind: EvidenceKind, blob: bytes) -> EvidenceSubmission:
	return EvidenceSubmission(
		submission_id='EV-TEST0000001', kind=kind, subject_ref='U1', county='Nairobi',
		image_sha256=hashlib.sha256(blob).hexdigest(), mime='image/jpeg', size_bytes=len(blob),
		note=' rash on forearms since this morning ',
	)


async def test_photo_and_note_accepted(svc: EvidenceService, tmp_path) -> None:
	blob = fake_jpeg()
	receipt = await svc.submit(_sub(EvidenceKind.rash, blob), blob)
	assert receipt.gated and receipt.storage_ref.endswith('EV-TEST0000001.blob')
	view = svc.view(receipt.submission_id)
	assert view.note == 'rash on forearms since this morning'  # stripped, linked to image
	with open(receipt.storage_ref, 'rb') as fh:
		assert fh.read() == blob


async def test_hash_mismatch_rejected(svc: EvidenceService) -> None:
	blob = fake_jpeg()
	bad = _sub(EvidenceKind.scene_photo, blob)
	bad = bad.model_copy(update={'image_sha256': '0' * 64})
	with pytest.raises(AssertionError):
		await svc.submit(bad, blob)


async def test_tier4_gating_blocks_epi_photo_when_dormant(tmp_path) -> None:
	svc = EvidenceService(FeatureRegistry(), FileSystemEvidenceStore(str(tmp_path / 'evidence')))
	blob = fake_jpeg()
	with pytest.raises(PermissionError):
		await svc.submit(_sub(EvidenceKind.rash, blob), blob)


async def test_dedupe(svc: EvidenceService) -> None:
	blob = fake_jpeg()
	r1 = await svc.submit(_sub(EvidenceKind.scene_photo, blob), blob)
	r2 = await svc.submit(_sub(EvidenceKind.scene_photo, blob).model_copy(update={'note': ''}), blob)
	assert not r1.deduped and r2.deduped


async def test_mime_whitelist() -> None:
	with pytest.raises(Exception):
		_sub(EvidenceKind.rash, fake_jpeg()).model_validate_json('{}') if False else EvidenceSubmission(
			submission_id='EV-TEST0000002', kind=EvidenceKind.rash, subject_ref='U1', county='N',
			image_sha256='a' * 64, mime='image/tiff', size_bytes=2000, note='',
		)
