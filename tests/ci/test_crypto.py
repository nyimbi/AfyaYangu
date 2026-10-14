"""§SEC-003's encryption, tested on what it must *fail* to do.

Three of the five Standards were `missing` because the tree stated the standard and applied it
nowhere: `ENCRYPTION_STANDARD` was a string, `EncryptionPosture` was three hardcoded `True`s, and
`SqliteStore` wrote plaintext. The tests that matter here are therefore not "does it round-trip" —
a store that wrote plaintext round-trips too — but "does a reader without the key get nothing".
"""
import os
import pathlib

import pytest

from afya.crypto.service import (
	KEY_BYTES, CryptoService, Sealed, derive_key, new_key,
)
from afya.persistence.service import APP_LAYER_DATASETS, SqliteStore
from afya.retention.service import RetentionService
from afya.sync.views import SyncOp


def _two_keys() -> CryptoService:
	return CryptoService(new_key(), new_key())


# --- the primitive ------------------------------------------------------------------------------

def test_a_sealed_value_opens_with_its_key_and_not_without_it() -> None:
	svc = _two_keys()
	sealed = svc.seal(b'a contact list')
	assert svc.open(sealed) == b'a contact list'
	other = CryptoService(new_key(), new_key())
	with pytest.raises(Exception):
		other.open(sealed)


def test_a_tampered_ciphertext_fails_rather_than_returning_something() -> None:
	"""GCM authenticates. A store that returned empty bytes on a bad tag would turn an attack into
	a missing record, and the two are not the same event."""
	svc = _two_keys()
	sealed = svc.seal(b'location history')
	flipped = bytes([sealed.ciphertext[0] ^ 1]) + sealed.ciphertext[1:]
	with pytest.raises(Exception):
		svc.open(Sealed(nonce=sealed.nonce, salt=None, ciphertext=flipped, user_held=False))


def test_the_same_plaintext_seals_to_a_different_ciphertext_every_time() -> None:
	"""A fresh nonce per message. GCM's security collapses on nonce reuse under one key, and two
	identical ciphertexts for the same contact list would leak exactly that reuse."""
	svc = _two_keys()
	first, second = svc.seal(b'same'), svc.seal(b'same')
	assert first.ciphertext != second.ciphertext
	assert first.nonce != second.nonce


def test_the_application_layer_key_must_differ_from_the_at_rest_key() -> None:
	"""§SEC-003 asks for an *additional* layer. One key fitted twice is not two layers, and the
	service refuses to be constructed that way rather than reporting a layer it does not add."""
	key = new_key()
	with pytest.raises(AssertionError, match='must differ'):
		CryptoService(key, key)


def test_the_application_layer_is_not_openable_with_the_at_rest_key() -> None:
	"""The finding the row names: a database dump that yields the at-rest key must not also yield
	the contact lists."""
	svc = _two_keys()
	sealed = svc.seal(b'who I was near', app_layer=True)
	assert sealed.layer == 'app_layer'
	at_only = CryptoService(svc._at_rest)
	with pytest.raises(Exception):
		at_only.open(sealed)


def test_a_sealed_value_records_which_key_produced_it() -> None:
	"""The layer travels with the value, so a reader never guesses — a wrong key and a tampered
	value would otherwise be indistinguishable."""
	svc = _two_keys()
	for layer, app_layer in (('at_rest', False), ('app_layer', True)):
		sealed = svc.seal(b'x', app_layer=app_layer)
		back = Sealed.from_blob(sealed.to_blob())
		assert back.layer == layer
		assert svc.open(back) == b'x'


def test_a_deployment_with_no_key_refuses_rather_than_writing_plaintext() -> None:
	"""The failure mode a fallback always has. A store that silently wrote plaintext under an
	encryption label is the exact shape the audit row described."""
	with pytest.raises(AssertionError, match='no at-rest key'):
		CryptoService().seal(b'x')


# --- the user-held path (§SEC-003's cloud backup) ------------------------------------------------

def test_a_backup_opens_only_with_its_passphrase() -> None:
	svc = _two_keys()
	sealed = svc.seal_for_user(b'the family wallet', 'a-long-enough-passphrase')
	assert sealed.user_held and sealed.salt is not None
	assert svc.open_for_user(sealed, 'a-long-enough-passphrase') == b'the family wallet'
	with pytest.raises(Exception):
		svc.open_for_user(sealed, 'a-different-passphrase')


def test_the_same_passphrase_twice_uses_a_different_salt() -> None:
	"""A shared salt would let an attacker who broke one backup break every other for free."""
	svc = _two_keys()
	first = svc.seal_for_user(b'wallet', 'a-long-enough-passphrase')
	second = svc.seal_for_user(b'wallet', 'a-long-enough-passphrase')
	assert first.salt != second.salt
	assert first.ciphertext != second.ciphertext


def test_a_short_passphrase_is_refused() -> None:
	with pytest.raises(AssertionError, match='12 characters'):
		derive_key('short', os.urandom(16))


def test_the_derived_key_is_not_the_passphrase() -> None:
	"""Padding or hashing a passphrase is how an encrypted-looking backup becomes an unencrypted
	one; scrypt is memory-hard, so the cost of a dictionary attack is paid in RAM."""
	salt = os.urandom(16)
	key = derive_key('a-long-enough-passphrase', salt)
	assert len(key) == KEY_BYTES
	assert b'a-long-enough-passphrase' not in key
	assert derive_key('a-long-enough-passphrase', salt) == key, 'the salt makes it reproducible'
	assert derive_key('a-long-enough-passphrase', os.urandom(16)) != key


# --- the store ----------------------------------------------------------------------------------

async def test_the_store_does_not_write_a_payload_in_the_clear(tmp_path) -> None:
	"""The row's own words: `SqliteStore` wrote plaintext rows. The check is on the *file*, because
	a round-trip through the same service would pass either way."""
	db = str(tmp_path / 'afya.db')
	store = SqliteStore(db, _two_keys())
	await store.save_sync_op(SyncOp(op_id='OP-AAA111', dataset='symptom_logs', client_ts=1,
		payload={'fever': 'Amina said so'}))
	assert b'Amina' not in pathlib.Path(db).read_bytes(), 'the payload is on disk in the clear'
	assert (await SqliteStore(db, store._crypto).sync_ops())[0].payload == {'fever': 'Amina said so'}


async def test_contact_lists_and_location_history_get_the_second_key(tmp_path) -> None:
	"""§SEC-003's "additional application-layer encryption", checked by handing the store the
	at-rest key alone and confirming the contact list does not open."""
	db = str(tmp_path / 'afya.db')
	svc = _two_keys()
	store = SqliteStore(db, svc)
	await store.save_sync_op(SyncOp(op_id='OP-AAA111', dataset='contact_lists', client_ts=1,
		payload={'who': 'Amina'}))
	raw = pathlib.Path(db).read_bytes()
	assert b'.app_layer.' in raw, 'a contact list must carry the application layer'
	assert b'Amina' not in raw
	with pytest.raises(Exception):
		await SqliteStore(db, CryptoService(svc._at_rest)).sync_ops()


async def test_a_store_with_no_crypto_writes_plaintext_and_says_so(tmp_path) -> None:
	"""The unit-test path stays available, and `encrypted` reports the truth rather than asserting
	AES-256 over a file anyone can read."""
	db = str(tmp_path / 'afya.db')
	store = SqliteStore(db)
	assert store.encrypted is False
	await store.save_sync_op(SyncOp(op_id='OP-AAA111', dataset='symptom_logs', client_ts=1,
		payload={'f': '1'}))
	assert b'"f"' in pathlib.Path(db).read_bytes()
	assert SqliteStore(db, _two_keys()).encrypted is True


async def test_a_row_written_before_encryption_stays_readable(tmp_path) -> None:
	"""The upgrade path. `CREATE TABLE IF NOT EXISTS` is a no-op on an existing handset, so a queue
	written by the old build is already there and must not become unreadable when a key appears."""
	db = str(tmp_path / 'afya.db')
	await SqliteStore(db).save_sync_op(SyncOp(op_id='OP-AAA111', dataset='symptom_logs',
		client_ts=1, payload={'f': '1'}))
	rows = await SqliteStore(db, _two_keys()).sync_ops()
	assert rows[0].payload == {'f': '1'}, 'a legacy plaintext row must still read back'


def test_the_application_layer_covers_the_datasets_the_section_names() -> None:
	assert {'contact_lists', 'location_history'} <= APP_LAYER_DATASETS


# --- the posture, which must be able to report a gap ---------------------------------------------

def test_the_posture_reports_the_deployment_and_not_the_design() -> None:
	svc = RetentionService()
	assert svc.encryption_posture().at_rest == 'none'
	assert svc.encryption_posture(_two_keys()).at_rest == 'AES-256'
	assert svc.encryption_posture(_two_keys()).contact_lists_extra_layer is True
	assert svc.encryption_posture(CryptoService(new_key())).contact_lists_extra_layer is False


# --- end to end, as a client reaches it -----------------------------------------------------------

async def test_the_encryption_route_reports_what_is_deployed() -> None:
	import httpx

	from afya.service import create_app
	app = create_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		resp = await c.get('/retention/encryption')
	assert resp.status_code == 200
	body = resp.json()
	assert body['at_rest'] == 'AES-256', 'the deployment builds with an at-rest key'
	assert body['in_transit'] == 'TLS 1.3'


def test_the_key_persists_across_a_restart(tmp_path) -> None:
	"""A random per-boot key would turn "encrypted" into "lost", which is worse than the plaintext
	it replaced."""
	from afya.service import build_services
	db = str(tmp_path / 'afya.db')
	first = build_services(db_path=db)
	second = build_services(db_path=db)
	first_crypto = first['crypto']
	second_crypto = second['crypto']
	assert isinstance(first_crypto, CryptoService) and isinstance(second_crypto, CryptoService)
	assert first_crypto._at_rest == second_crypto._at_rest
	sidecar = pathlib.Path(f'{db}.key')
	assert sidecar.exists()
	assert oct(sidecar.stat().st_mode & 0o777) == '0o600', 'the key is not world-readable'


def test_an_in_memory_database_writes_no_key_sidecar(tmp_path, monkeypatch) -> None:
	"""An in-memory database has no file to protect, so it must leave no key on disk.

	`:memory:` is not a path, it is SQLite's marker for a database that never touches the filesystem.
	`Path(':memory:.key')` is a perfectly valid *relative* filename, so the sidecar logic wrote a
	persistent 0600 file literally named `:memory:.key` into the working directory — one per test run,
	read back by the next, so a fixture that asked for an ephemeral database was keyed by whatever
	happened to be lying in the CWD. This asserts the marker is recognised and nothing is written.
	"""
	from afya.service import build_services
	monkeypatch.chdir(tmp_path)
	build_services(db_path=':memory:')
	# Scoped to the sidecar, not to "the directory is empty": the service legitimately creates its own
	# data directories, and an assertion that forbids those would fail for a reason unrelated to keys.
	assert not (tmp_path / ':memory:.key').exists(), 'an in-memory database left a key on disk'
