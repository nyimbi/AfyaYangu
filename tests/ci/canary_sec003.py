"""Canaries for tests/ci/test_crypto.py.

§SEC-003's three rows were `missing` for one reason: the tree *stated* the standard and applied it
nowhere. `ENCRYPTION_STANDARD` was a string, `EncryptionPosture` was three hardcoded `True`s, and
`SqliteStore` wrote plaintext. So the canaries that matter are the ones that break the *application*
of the control and watch a test notice — not the ones that break the ciphertext, which no test could
pass anyway.

The three worth reading as a set:

* **#2** drops the second key, so contact lists get the at-rest layer. Every round-trip still works
  and the store still reports itself encrypted; only a test that hands the store the at-rest key
  *alone* can see it.
* **#4** makes the store fall back to plaintext when no crypto is wired, which is the shape the audit
  row described and the failure mode a fallback always has. The round-trip still passes.
* **#7** restores the posture's hardcoded `True`s — the original defect, where the report could not
  disagree with the design.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary that
passes is a bug in the canary, so a MISSED line is a failure of this script. The `__pycache__` purge
after each write is load-bearing: two canaries mutating two files with same-length edits in the same
second make CPython reuse the previous canary's bytecode.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
CR = ROOT / 'src/afya/crypto/service.py'
PS = ROOT / 'src/afya/persistence/service.py'
RS = ROOT / 'src/afya/retention/service.py'
BK = ROOT / 'src/afya/records/service.py'

CANARIES = [
	# 1. The tag is dropped from the sealed blob, so a reader cannot tell which key produced a
	#    value and tries the at-rest key on an application-layer contact list. The authentication
	#    failure is then indistinguishable from tampering.
	('a sealed value no longer records its key layer', CR,
	 "		layer = 'user_held' if user_key is not None else ('app_layer' if app_layer else 'at_rest')",
	 "		layer = 'at_rest'",
	 'test_a_sealed_value_records_which_key_produced_it'),

	# 2. Contact lists and location history lose their second layer, so one key opens everything.
	#    Every round-trip still passes — only handing the store the at-rest key alone shows it.
	('contact lists lose their second layer', PS,
	 "				 self._seal(json.dumps(op.payload), app_layer=op.dataset in APP_LAYER_DATASETS),",
	 "				 self._seal(json.dumps(op.payload)),",
	 'test_contact_lists_and_location_history_get_the_second_key'),

	# 3. The application-layer key is allowed to equal the at-rest key, so the "additional" layer is
	#    the same lock fitted twice and a database dump yields both.
	('the application layer may reuse the at-rest key', CR,
	 "		assert not (at_rest_key and app_layer_key and at_rest_key == app_layer_key), (",
	 "		assert True or (at_rest_key and app_layer_key and at_rest_key == app_layer_key), (",
	 'test_the_application_layer_key_must_differ_from_the_at_rest_key'),

	# 4. The store falls back to plaintext when no crypto is wired, while still reporting itself
	#    encrypted. This is the original finding: a control named and not applied.
	('the store falls back to plaintext under an encryption label', PS,
	 "		if self._crypto is None:\n			return plaintext\n		sealed = self._crypto.seal(plaintext.encode('utf-8'), app_layer=app_layer)  # type: ignore[attr-defined]",
	 "		if self._crypto is None:\n			return plaintext\n		return plaintext\n		sealed = self._crypto.seal(plaintext.encode('utf-8'), app_layer=app_layer)  # type: ignore[attr-defined]",
	 'test_the_store_does_not_write_a_payload_in_the_clear'),

	# 5. The nonce stops being fresh, so identical plaintexts produce identical ciphertexts. GCM's
	#    security collapses completely on nonce reuse under one key.
	('the nonce stops being fresh per message', CR,
	 "		nonce = os.urandom(NONCE_BYTES)\n		ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)",
	 "		nonce = bytes(NONCE_BYTES)\n		ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)",
	 'test_the_same_plaintext_seals_to_a_different_ciphertext_every_time'),

	# 6. The backup returns the plaintext documents beside the ciphertext, so the encryption it just
	#    performed is undone by the payload that ships with it.
	('the backup ships the plaintext beside its ciphertext', BK,
	 "			consent_category='cloud_backup', documents=[],",
	 "			consent_category='cloud_backup', documents=docs,",
	 'test_a_passphrase_makes_the_backup_end_to_end'),

	# 7. The posture goes back to asserting the design instead of reading the deployment — the
	#    original defect, where the report could not disagree with the intent.
	('the posture asserts the design instead of the deployment', RS,
	 "		at_rest = 'AES-256' if crypto is not None and getattr(crypto, 'available', False) else 'none'",
	 "		at_rest = 'AES-256'",
	 'test_the_posture_reports_the_deployment_and_not_the_design'),

	# 8. The at-rest key is regenerated per boot, so a restart makes the store it encrypted
	#    unreadable — "encrypted" turned into "lost", which is worse than the plaintext it replaced.
	('the at-rest key is regenerated on every boot', ROOT / 'src/afya/service.py',
	 "	if sidecar.exists():\n		key = bytes.fromhex(sidecar.read_text().strip())\n		assert len(key) == KEY_BYTES, f'{sidecar} does not hold a {KEY_BYTES}-byte key'\n		return key",
	 "	if sidecar.exists():\n		return os.urandom(KEY_BYTES)",
	 'test_the_key_persists_across_a_restart'),

	# 9. A passphrase with no crypto service is ignored rather than refused, so a caller who asked
	#    for encryption gets the wallet in the clear under an end-to-end label.
	('a passphrase is ignored when no crypto service is wired', BK,
	 "		assert crypto is not None, (\n			'a passphrase was given but no crypto service is wired, so the wallet cannot be sealed; '\n			'refusing rather than returning the documents unencrypted under an end-to-end label')",
	 "		assert True, (\n			'a passphrase was given but no crypto service is wired, so the wallet cannot be sealed; '\n			'refusing rather than returning the documents unencrypted under an end-to-end label')",
	 'test_a_passphrase_with_no_crypto_service_is_refused_not_ignored'),

	# 10. A tampered ciphertext is swallowed and returned as empty bytes, so an attack becomes a
	#     missing record — the two are not the same event.
	('a tampered ciphertext is swallowed instead of raised', CR,
	 "		except InvalidTag:\n			self._log_warn('sealed value failed authentication', user_held=sealed.user_held)\n			raise",
	 "		except InvalidTag:\n			self._log_warn('sealed value failed authentication', user_held=sealed.user_held)\n			return b''",
	 'test_a_tampered_ciphertext_fails_rather_than_returning_something'),

	# 11. A legacy plaintext row stops being readable once a key appears, so upgrading a handset
	#     silently loses the queue the encryption was added to protect.
	('a legacy plaintext row stops reading back', PS,
	 "		if self._crypto is None or not stored.startswith('v1.'):\n			return stored",
	 "		if self._crypto is None:\n			return stored",
	 'test_a_row_written_before_encryption_stays_readable'),
]

# Which test module each canary's target lives in. Explicit, because a wrong guess is a canary that
# passes on a collection error.
WALLET_NODES = {'test_a_passphrase_makes_the_backup_end_to_end',
	'test_a_passphrase_with_no_crypto_service_is_refused_not_ignored'}

failures = []
for name, path, old, new, node in CANARIES:
	test_file = 'tests/ci/test_wallet.py' if node in WALLET_NODES else 'tests/ci/test_crypto.py'
	backup = pathlib.Path(f'/tmp/canary_sec003.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		# The test file is named per canary. Passing a node that does not exist makes pytest exit
		# non-zero on the collection error, which reads as CAUGHT — a canary that passes for the
		# wrong reason, which is the failure this whole script exists to avoid.
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', f'{test_file}::{node}'],
			cwd=ROOT, capture_output=True, text=True)
		if 'no tests ran' in proc.stdout or 'ERROR' in proc.stdout.splitlines()[-1:][0:1]:
			raise SystemExit(f'{name}: the target test did not run — the canary proved nothing')
		caught = proc.returncode != 0
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
	print(f'{"CAUGHT " if caught else "MISSED "} {name}')
	if not caught:
		failures.append(name)
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
