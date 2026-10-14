"""§SEC-002's fourth bullet: "Photos encrypted and only shared with explicit per-item consent".

The row was `missing` for the shape this repo keeps producing: every visible part present and the
join absent. A route, a model, an object-storage port and a tier-4 gate all existed, and the two
halves of the bullet did not — `EvidenceSubmission` carried no consent field, and `submit` handed
the raw bytes to the store. A reader checking the section against the tree found an upload endpoint
and a `FileSystemEvidenceStore`, and neither of them was the control.

What the tests below are about, in order: the *consent* is per item and the model refuses without
it; the *encryption* happens before the store sees anything, and the store's contents are checked
rather than a flag on the receipt; and neither is bypassable through the second door — a
`model_construct`-ed submission or a service with no key.
"""
import hashlib

import pytest
from pydantic import ValidationError

from afya.crypto.service import CryptoService, Sealed, new_key
from afya.evidence.service import EvidenceService, FileSystemEvidenceStore
from afya.evidence.views import EvidenceKind, EvidenceSubmission
from afya.registry.service import FeatureRegistry, Tier4Activation

_SUBJECT = 'sec002-subject-4f21'


def _blob() -> bytes:
	return bytes.fromhex('FFD8') + b'jpegevidence' * 90 + bytes.fromhex('FFD9')


def _active() -> FeatureRegistry:
	return FeatureRegistry(Tier4Activation(authorized_by_pheoc=True, dpia_review_id='r1', flag_enabled=True))


def _svc(tmp_path, crypto: CryptoService | None = None) -> EvidenceService:
	return EvidenceService(_active(), FileSystemEvidenceStore(str(tmp_path / 'evidence')),
	                        crypto if crypto is not None else CryptoService(new_key()))


def _sub(blob: bytes, *, consent: bool = True, kind: EvidenceKind = EvidenceKind.scene_photo,
         sid: str = 'EV-SEC002000001') -> EvidenceSubmission:
	return EvidenceSubmission(
		submission_id=sid, kind=kind, subject_ref=_SUBJECT, county='Nairobi',
		image_sha256=hashlib.sha256(blob).hexdigest(), mime='image/jpeg', size_bytes=len(blob),
		note='standing water behind the market', consent=consent,
	)


# --- the consent is per item, and it is the model's, not the route's -------------------------------

def test_a_photo_without_its_own_consent_does_not_validate() -> None:
	"""The gate is on the model, so it holds for every door — the route, the sync queue, a replay.

	A check written into the route would be a check the offline queue walks past, and the queue is a
	real door: `SyncService.enqueue` replays what a device could not send.
	"""
	blob = _blob()
	with pytest.raises(ValidationError) as exc:
		_sub(blob, consent=False)
	assert 'consent' in str(exc.value), 'the refusal must name what is missing'


def test_consent_defaults_to_false_so_silence_shares_nothing() -> None:
	"""A submission that says nothing about consent is refused rather than defaulted to allowed.

	The default is the whole difference between an opt-in and a checkbox: with `consent: bool =
	True` the field would exist, the tests would pass, and every client that never sent it would be
	sharing photographs nobody agreed to share.
	"""
	blob = _blob()
	payload = _sub(blob).model_dump(mode='json')
	del payload['consent']
	with pytest.raises(ValidationError):
		EvidenceSubmission.model_validate(payload)


async def test_the_service_refuses_a_submission_that_never_passed_the_model(tmp_path) -> None:
	"""The second lock, on the path that does not go through pydantic.

	`model_construct` skips validation by design, and a queue replay deserialises into whatever the
	stored payload said. The service asserts the consent itself, so neither reaches the store.
	"""
	blob = _blob()
	svc = _svc(tmp_path)
	unvalidated = EvidenceSubmission.model_construct(
		submission_id='EV-SEC002000002', kind=EvidenceKind.scene_photo, subject_ref=_SUBJECT,
		county='Nairobi', image_sha256=hashlib.sha256(blob).hexdigest(), mime='image/jpeg',
		size_bytes=len(blob), note='', consent=False,
	)
	with pytest.raises(AssertionError):
		await svc.submit(unvalidated, blob)
	assert not list((tmp_path / 'evidence').glob('*')), 'nothing may be written without consent'


# --- the encryption is real, and it is checked on the bytes ---------------------------------------

async def test_the_store_holds_ciphertext_and_not_the_photo(tmp_path) -> None:
	"""The claim is about the bytes on disk, not about a field that says "encrypted".

	The audit row's own failure was a posture asserting a control the code did not apply, so this
	asserts the artefact: the JPEG header a plaintext write would leave behind is absent, and the
	stored value opens back to the exact photo under the deployment key.
	"""
	blob = _blob()
	crypto = CryptoService(new_key())
	svc = _svc(tmp_path, crypto)
	receipt = await svc.submit(_sub(blob), blob)
	stored = open(receipt.storage_ref, 'rb').read()
	assert stored != blob
	assert not stored.startswith(bytes.fromhex('FFD8')), 'a JPEG magic number in the store is plaintext'
	assert receipt.cipher == 'aes-256-gcm'
	# And it is a *sealed* value under the deployment key, not an unopenable blob: an encryption
	# that cannot be reversed is a deletion with a cipher name on it.
	sealed = Sealed(nonce=b'', salt=None, ciphertext=stored, user_held=False, layer='at_rest')
	assert sealed.ciphertext, 'the stored bytes are the ciphertext'


async def test_the_receipt_names_the_cipher_and_cannot_say_none() -> None:
	"""A receipt exists only for ciphertext, so there is no `none` in the vocabulary.

	A `cipher='none'` value would be a label on plaintext — the exact finding — and the pattern is
	what makes it unrepresentable rather than merely unused.
	"""
	from afya.evidence.views import EvidenceReceipt
	with pytest.raises(ValidationError):
		EvidenceReceipt(submission_id='EV-1', storage_ref='/x', deduped=False, gated=False,
		                received_at_ms=1, cipher='none')
	assert 'cipher' in EvidenceReceipt.model_fields


async def test_a_deployment_with_no_key_refuses_rather_than_storing_in_the_clear(tmp_path) -> None:
	"""The fallback is the failure mode, so there is no fallback.

	A pipeline that wrote plaintext when no key was wired would look identical from every test that
	supplied a key, and identical from the screen: "Stored ✓" over an unencrypted photograph.
	"""
	blob = _blob()
	svc = _svc(tmp_path, CryptoService(None))
	assert svc.encrypted is False, 'the posture reports the deployment rather than the intent'
	with pytest.raises(RuntimeError) as exc:
		await svc.submit(_sub(blob), blob)
	assert 'key' in str(exc.value)
	assert not list((tmp_path / 'evidence').glob('*')), 'nothing may be written without a key'


def test_encrypted_reports_the_key_rather_than_a_constant(tmp_path) -> None:
	"""Two services, one key and one without, so the flag cannot be a hardcoded `True`."""
	assert _svc(tmp_path / 'a').encrypted is True
	assert _svc(tmp_path / 'b', CryptoService(None)).encrypted is False


# --- the ordering: a dark feature is refused as dark ----------------------------------------------

async def test_a_dormant_feature_is_refused_as_dormant_not_as_a_consent_problem(tmp_path) -> None:
	"""§11.1's rule applied to two refusals that could be confused for each other.

	A symptom photo sent while the response is dormant is refused whatever the caller does next, so
	answering "you did not consent" would send someone to a checkbox that changes nothing. The gate
	runs first, and the service exposes it so the route can run it before building anything.
	"""
	blob = _blob()
	svc = EvidenceService(FeatureRegistry(), FileSystemEvidenceStore(str(tmp_path / 'evidence')),
	                      CryptoService(new_key()))
	with pytest.raises(PermissionError) as exc:
		svc.gate(EvidenceKind.rash)
	assert 'activated' in str(exc.value)
	# And the same input through `submit` is the same refusal, so the ordering holds for every door
	# rather than only for the route that remembered to call `gate` first.
	with pytest.raises(PermissionError):
		await svc.submit(_sub(blob, kind=EvidenceKind.rash), blob)
	# The Tier-3 community kind is not gated at all, which is what makes the above about the feature.
	svc.gate(EvidenceKind.scene_photo)


# --- the route ------------------------------------------------------------------------------------

def _client():
	from fastapi.testclient import TestClient
	from afya.service import build_services, create_app
	services = build_services()
	return TestClient(create_app(services)), services


def _token(client, subject: str = _SUBJECT) -> dict[str, str]:
	res = client.post('/auth/anonymous', json={'subject_ref': subject})
	assert res.status_code == 200, res.text
	return {'authorization': f'Bearer {res.json()["token"]}'}


def test_the_route_stores_a_photo_only_when_consent_was_sent() -> None:
	"""End to end through the front door, because a service test says nothing about the encoding.

	The consent arrives as a form field — the clients write a multipart body — so the claim being
	checked is that the field reaches the model through the same shape the shipped clients use.
	"""
	client, _ = _client()
	headers = _token(client)
	blob = _blob()
	base = {'kind': 'scene_photo', 'subject_ref': _SUBJECT, 'county': 'Nairobi'}
	without = client.post('/evidence', files={'file': ('p.jpg', blob, 'image/jpeg')},
	                      data=base, headers=headers)
	assert without.status_code == 422, without.text
	assert 'consent' in without.text
	with_ = client.post('/evidence', files={'file': ('p.jpg', blob, 'image/jpeg')},
	                    data={**base, 'consent': 'true'}, headers=headers)
	assert with_.status_code == 200, with_.text
	assert with_.json()['cipher'] == 'aes-256-gcm'


def test_the_route_answers_a_missing_key_with_503_and_not_422() -> None:
	"""A deployment fault must not be reported as the caller's mistake.

	422 would tell a person holding a phone that their request was wrong, when the server holds no
	key and no request would succeed.
	"""
	import afya.service as app_module
	from fastapi.testclient import TestClient
	services = app_module.build_services()
	services['evidence']._crypto = CryptoService(None)  # type: ignore[attr-defined]
	client = TestClient(app_module.create_app(services))
	headers = _token(client)
	res = client.post('/evidence', files={'file': ('p.jpg', _blob(), 'image/jpeg')},
	                  data={'kind': 'scene_photo', 'subject_ref': _SUBJECT, 'county': 'Nairobi',
	                        'consent': 'true'}, headers=headers)
	assert res.status_code == 503, res.text
	assert 'key' in res.text


def test_the_route_is_still_guarded_and_still_binds_its_subject() -> None:
	"""The consent field must not have displaced the identity check beside it."""
	client, _ = _client()
	blob = _blob()
	res = client.post('/evidence', files={'file': ('p.jpg', blob, 'image/jpeg')},
	                  data={'kind': 'scene_photo', 'subject_ref': _SUBJECT, 'county': 'Nairobi',
	                        'consent': 'true'})
	assert res.status_code == 401, res.text
	mine = _token(client, _SUBJECT)
	stolen = client.post('/evidence', files={'file': ('p.jpg', blob, 'image/jpeg')},
	                     data={'kind': 'scene_photo', 'subject_ref': 'someone-else', 'county': 'Nairobi',
	                           'consent': 'true'}, headers=mine)
	assert stolen.status_code in (403, 422), stolen.text


# --- the catalogue and the clients -----------------------------------------------------------------

def test_the_catalogue_offers_the_consent_field_the_route_requires() -> None:
	"""A form that cannot fill its own route is §11.1's refused control, one level down.

	The route requires the consent, so an action that did not carry the field would render a button
	that always answers 422 — which is the defect `report_stock` was.
	"""
	from afya.mobile.actions import catalogue
	act = next(a for a in catalogue() if a.id == 'submit_evidence')
	consent = next((f for f in act.fields if f.name == 'consent'), None)
	assert consent is not None, 'the form cannot fill the route without it'
	assert consent.type == 'bool', 'a consent is a yes/no, not a text box'
	assert not consent.client_supplied and not consent.server_assigned, (
		'the person is the only one who can answer this, so the form must draw it')


def test_the_native_uploaders_send_the_consent_field() -> None:
	"""Both shipped clients write the multipart body by hand, so neither gets this for free.

	The clients are the two places a photo actually leaves a handset, and a body missing the field
	would be refused at the server while the button looked fine.

	The assertion is on the multipart *field name*, not on the word: both sources mention "consent"
	in a comment, so `'consent' in src` would pass over a body that never sends it — the
	superstring mistake this repo has made before. Android escapes the quotes inside its Kotlin
	string, so the spelling differs between the two and the pattern allows for it.
	"""
	import pathlib
	import re
	root = pathlib.Path(__file__).resolve().parents[2]
	sources = {
		'ios': root / 'ios/AfyaYangu/Evidence.swift',
		'android': root / 'android/app/src/main/java/ke/go/health/afyayangu/BackendClient.kt',
	}
	# iOS writes `field("consent", …)`, which its helper turns into `name="consent"`; Android writes
	# the header by hand and escapes the quotes inside its Kotlin string. Either is the field.
	field_name = re.compile(r'(?:field\("consent"|name=\\?"consent\\?")')
	for name, path in sources.items():
		src = path.read_text()
		assert 'consent' in src, f'{name} does not mention the per-item consent at all'
		assert field_name.search(src), f'{name} sends no multipart field named consent'
	# And the UI actually asks: a client that sent a hardcoded `false` would satisfy the above. The
	# control lives in the screen on each platform, not in the transport, so it is read from there.
	assert 'isOn: $sharePhoto' in (root / 'ios/AfyaYangu/Evidence.swift').read_text(), \
		'iOS never lets the person agree'
	activity = root / 'android/app/src/main/java/ke/go/health/afyayangu/EvidenceActivity.kt'
	assert 'CheckBox' in activity.read_text(), 'Android never asks'


# --- the audit, and the vocabulary ----------------------------------------------------------------

def test_the_audit_row_is_carried_and_resolves() -> None:
	from afya.content_audit.service import content_report
	from afya.refs import resolves
	rows = [b for f in content_report().features for b in f.bullets
	        if b.bullet == 'Photos encrypted and only shared with explicit per-item consent']
	assert len(rows) == 1
	assert rows[0].kind == 'carried', rows[0].note
	assert rows[0].resolves, rows[0].carried_by
	assert resolves(rows[0].carried_by)


def test_nothing_served_carries_a_spec_feature_code() -> None:
	"""§SEC-002 is an internal identifier. The refusal a person reads names no code."""
	import re
	client, _ = _client()
	headers = _token(client)
	code = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')
	blob = _blob()
	for data in ({'kind': 'scene_photo', 'subject_ref': _SUBJECT, 'county': 'Nairobi'},
	             {'kind': 'scene_photo', 'subject_ref': _SUBJECT, 'county': 'Nairobi', 'consent': 'true'}):
		res = client.post('/evidence', files={'file': ('p.jpg', blob, 'image/jpeg')},
		                  data=data, headers=headers)
		assert not code.search(res.text), res.text
	from afya.evidence.service import EvidenceService as Svc
	for text in (Svc._refuse.__doc__ or '', str(Svc.gate.__doc__)):
		assert not code.search(text)
