import hashlib

import pytest

from afya.crypto.service import CryptoService, new_key
from afya.evidence.service import EvidenceService, FileSystemEvidenceStore
from afya.evidence.views import EvidenceKind, EvidenceSubmission, UploadChunk
from afya.registry.service import FeatureRegistry, Tier4Activation


def fake_jpeg() -> bytes:
	return bytes.fromhex('FFD8') + b'jpegevidence' * 90 + bytes.fromhex('FFD9')


@pytest.fixture
def svc(tmp_path) -> EvidenceService:
	reg = FeatureRegistry(Tier4Activation(authorized_by_pheoc=True, dpia_review_id='r1', flag_enabled=True))
	return EvidenceService(reg, FileSystemEvidenceStore(str(tmp_path / 'evidence')), CryptoService(new_key()))


def _sub(kind: EvidenceKind, blob: bytes) -> EvidenceSubmission:
	return EvidenceSubmission(
		submission_id='EV-TEST0000001', kind=kind, subject_ref='U1', county='Nairobi',
		image_sha256=hashlib.sha256(blob).hexdigest(), mime='image/jpeg', size_bytes=len(blob),
		note=' rash on forearms since this morning ', consent=True,
	)


async def test_photo_and_note_accepted(svc: EvidenceService, tmp_path) -> None:
	blob = fake_jpeg()
	receipt = await svc.submit(_sub(EvidenceKind.rash, blob), blob)
	assert receipt.gated and receipt.storage_ref.endswith('EV-TEST0000001.blob')
	assert receipt.cipher == 'aes-256-gcm', 'the receipt names what the bytes are under'
	view = svc.view(receipt.submission_id)
	assert view.note == 'rash on forearms since this morning'  # stripped, linked to image
	with open(receipt.storage_ref, 'rb') as fh:
		stored = fh.read()
	# §SEC-002's "photos encrypted": what reached the object store is not the picture. The JPEG
	# header is the first thing a plaintext write would leave behind.
	assert stored != blob and not stored.startswith(bytes.fromhex('FFD8')), 'the store holds plaintext'


async def test_hash_mismatch_rejected(svc: EvidenceService) -> None:
	blob = fake_jpeg()
	bad = _sub(EvidenceKind.scene_photo, blob)
	bad = bad.model_copy(update={'image_sha256': '0' * 64})
	with pytest.raises(AssertionError):
		await svc.submit(bad, blob)


async def test_tier4_gating_blocks_epi_photo_when_dormant(tmp_path) -> None:
	svc = EvidenceService(FeatureRegistry(), FileSystemEvidenceStore(str(tmp_path / 'evidence')),
	                      CryptoService(new_key()))
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
			image_sha256='a' * 64, mime='image/tiff', size_bytes=2000, note='', consent=True,
		)


# --- §16.4 resumable upload ------------------------------------------------------------------

def _chunk(blob: bytes, offset: int) -> UploadChunk:
	import base64
	return UploadChunk(
		offset=offset, chunk_sha256=hashlib.sha256(blob).hexdigest(),
		data=base64.urlsafe_b64encode(blob).decode().rstrip('='),
	)


async def test_a_resumable_upload_stores_the_same_photo_as_a_single_shot_one(svc: EvidenceService) -> None:
	"""§16.4's "resumable upload" is a *transport* for the same photo, not a second pipeline.

	The reassembled bytes go through `submit`, so the consent assertion, the hash check, the
	encryption and the store are the same controls — a resumable path that sealed its own bytes
	would be a second implementation of §SEC-002, and the second implementation is where a control
	goes missing. Asserted by finishing an upload and checking what reached the store is ciphertext,
	which is the property the single-shot test checks for its own path.
	"""
	blob = fake_jpeg()
	sub = _sub(EvidenceKind.scene_photo, blob)
	session = svc.open_upload(sub, declared_bytes=len(blob), chunk_bytes=1024)
	assert session.received_bytes == 0 and session.next_offset == 0 and not session.complete
	half = len(blob) // 2
	after_first = svc.append_chunk(session.session_id, _chunk(blob[:half], 0))
	assert after_first.received_bytes == half and after_first.next_offset == half
	after_second = svc.append_chunk(session.session_id, _chunk(blob[half:], half))
	assert after_second.complete, 'every declared byte has arrived'
	receipt = await svc.finish_upload(session.session_id)
	assert receipt.submission_id == sub.submission_id and receipt.cipher == 'aes-256-gcm'
	with open(receipt.storage_ref, 'rb') as fh:
		stored = fh.read()
	assert stored != blob and not stored.startswith(bytes.fromhex('FFD8')), 'the store holds plaintext'


async def test_a_replayed_chunk_is_answered_with_the_true_position(svc: EvidenceService) -> None:
	"""The case the mechanism exists for. A client whose chunk went unacknowledged retries it
	blindly, and the server must answer with where it actually is rather than refuse — a refusal
	would send the client looking for a bug in its own offset arithmetic, and the honest answer is
	"already have it, continue from here"."""
	blob = fake_jpeg()
	session = svc.open_upload(_sub(EvidenceKind.scene_photo, blob), declared_bytes=len(blob), chunk_bytes=1024)
	half = len(blob) // 2
	svc.append_chunk(session.session_id, _chunk(blob[:half], 0))
	again = svc.append_chunk(session.session_id, _chunk(blob[:half], 0))
	assert again.received_bytes == half and again.next_offset == half, 'the retry did not double the prefix'


async def test_a_gap_is_refused_with_the_offset_to_resume_from(svc: EvidenceService) -> None:
	"""An offset past what the server holds would leave a hole in the middle of the photo, and the
	failure would surface at the end as a hash mismatch on bytes the client sent correctly. Refused
	at the chunk, naming the offset to send, because the session is still good."""
	blob = fake_jpeg()
	session = svc.open_upload(_sub(EvidenceKind.scene_photo, blob), declared_bytes=len(blob), chunk_bytes=1024)
	with pytest.raises(ValueError, match='resume from byte 0'):
		svc.append_chunk(session.session_id, _chunk(blob, 500))
	assert svc.upload_session(session.session_id).received_bytes == 0, 'the session survived the refusal'


async def test_a_corrupted_chunk_is_refused_before_it_is_appended(svc: EvidenceService) -> None:
	"""The chunk hash is checked against the bytes received rather than trusted. A chunk corrupted
	in transit that was appended anyway would surface as a whole-file mismatch at the end, after the
	person had paid for every chunk — so the refusal is at the chunk, and it is recoverable."""
	blob = fake_jpeg()
	session = svc.open_upload(_sub(EvidenceKind.scene_photo, blob), declared_bytes=len(blob), chunk_bytes=1024)
	bad = _chunk(blob, 0).model_copy(update={'chunk_sha256': '0' * 64})
	with pytest.raises(ValueError, match='corrupted'):
		svc.append_chunk(session.session_id, bad)
	assert svc.upload_session(session.session_id).received_bytes == 0


async def test_an_upload_cannot_grow_past_what_it_declared(svc: EvidenceService) -> None:
	"""`declared_bytes` is the caller's claim, so the cap is enforced against the claim *and* the
	claim is enforced against the real cap — otherwise a client under-declares and the size limit is
	checked against a number the client chose."""
	blob = fake_jpeg()
	with pytest.raises(AssertionError):
		svc.open_upload(_sub(EvidenceKind.scene_photo, blob), declared_bytes=9_000_000, chunk_bytes=1024)
	session = svc.open_upload(_sub(EvidenceKind.scene_photo, blob), declared_bytes=len(blob), chunk_bytes=1024)
	with pytest.raises(ValueError, match='declared'):
		svc.append_chunk(session.session_id, _chunk(blob + b'x' * 100, 0))


async def test_finishing_an_incomplete_upload_is_refused(svc: EvidenceService) -> None:
	"""A photo stored from a partial prefix would be a picture nobody took, and its hash would match
	what the server holds rather than what the client sent — which is the one failure the whole hash
	chain exists to make impossible."""
	blob = fake_jpeg()
	session = svc.open_upload(_sub(EvidenceKind.scene_photo, blob), declared_bytes=len(blob), chunk_bytes=1024)
	svc.append_chunk(session.session_id, _chunk(blob[:len(blob) // 2], 0))
	with pytest.raises(ValueError, match='not complete'):
		await svc.finish_upload(session.session_id)


async def test_a_dormant_tier4_photo_is_refused_at_the_start_not_the_end(tmp_path) -> None:
	"""The gate runs when the upload opens, so a client never spends a metered link on a photo the
	server was always going to refuse. On a link where 6 MB takes minutes, that is the difference
	between retrying and giving up."""
	dormant = EvidenceService(FeatureRegistry(), FileSystemEvidenceStore(str(tmp_path / 'e2')),
	                          CryptoService(new_key()))
	blob = fake_jpeg()
	with pytest.raises(PermissionError):
		dormant.open_upload(_sub(EvidenceKind.rash, blob), declared_bytes=len(blob), chunk_bytes=1024)
	assert dormant._uploads == {}  # noqa: SLF001
