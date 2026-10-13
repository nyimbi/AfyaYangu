"""Application-layer encryption (spec §12.2 SEC-003).

Three of §SEC-003's five Standards were `missing` for the same reason: the tree stated the standard
and applied it nowhere. `ENCRYPTION_STANDARD` was a string constant; `EncryptionPosture` was three
hardcoded `True`s; `SqliteStore` wrote plaintext rows. A control named in a table and absent from the
code is worse than an absent control, because the table is what a reader checks.

What this module is:

* **AES-256-GCM**, the standard §SEC-003 names, with a fresh 96-bit nonce per message and the
  authentication tag verified on open. GCM rather than CBC because the contact list and the location
  history are the two stores where a silent bit-flip matters: a tampered ciphertext must fail to
  open rather than decrypt to a plausible contact.
* **A key hierarchy**, because the two rows need different keys. `at_rest` is the deployment's own
  key, unwrapped from the OS keystore at boot (§SEC-003's key-management standard, which stays
  `deferred` — the keystore is the platform's). `user_held` is derived from a passphrase the
  deployment never stores, which is what makes the backup end-to-end.

What this module is not, stated because the audit row turns on it: it does not make the deployment
unable to read its own store. A server that holds `at_rest` can decrypt it, and §SEC-003's
"additional application-layer encryption" is a control against a *reader of the file* — a stolen
handset, a database dump, a backup bucket — not against the deployment. The backup row is the one
where the key is genuinely out of reach, and `BackupEnvelope.user_held_key` now reports which of the
two produced it rather than asserting either.
"""
import base64
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from afya.logmixin import LogMixin

KEY_BYTES = 32
NONCE_BYTES = 12
SALT_BYTES = 16
TAG_BYTES = 16

# scrypt parameters. §SEC-003 does not name a KDF, so these are chosen for the threat: a
# user-chosen passphrase, on a handset, where the attacker has the ciphertext. n=2**15 with r=8
# costs ~64 MB and ~0.1 s here — enough to make an offline dictionary attack expensive without
# making the backup feel broken to the person waiting for it. `Scrypt` bounds its own memory from
# n/r/p (128*n*r bytes), so no separate cap is passed.
SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1

CIPHER_NAME = 'aes-256-gcm'

# The three keys a sealed value can have been produced by. Named rather than inferred so a reader
# never has to guess which one to try, and so the application layer is distinguishable from the
# at-rest key it is layered over.
LAYERS: frozenset[str] = frozenset({'at_rest', 'app_layer', 'user_held'})


def new_key() -> bytes:
	"""A fresh 256-bit key. `os.urandom`, never `random` — the latter is a Mersenne twister."""
	key = os.urandom(KEY_BYTES)
	assert len(key) == KEY_BYTES, 'a 256-bit key is 32 bytes'
	return key


def derive_key(passphrase: str, salt: bytes) -> bytes:
	"""Derive the user-held key from a passphrase. The salt is stored beside the ciphertext.

	A passphrase is not a key, and treating it as one — hashing it, or padding it — is how a
	backup that looks encrypted becomes one that is not. scrypt is memory-hard, so the cost of a
	dictionary attack is paid in RAM rather than in parallelism.
	"""
	assert len(passphrase) >= 12, 'a user-held key needs a passphrase of at least 12 characters'
	assert len(salt) == SALT_BYTES, f'a {SALT_BYTES}-byte salt is required'
	derived = Scrypt(salt=salt, length=KEY_BYTES, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P).derive(
		passphrase.encode('utf-8'))
	assert len(derived) == KEY_BYTES, 'derived key is 256 bits'
	return derived


@dataclass(frozen=True)
class Sealed:
	"""A ciphertext and what is needed to open it. The salt and nonce are not secret.

	`layer` records which key produced it, because the two are not interchangeable and a reader
	that guessed would try the at-rest key on an application-layer value and report a failed
	authentication — an attack and a wrong key are different events and must not share a symptom.
	"""

	nonce: bytes
	salt: bytes | None
	ciphertext: bytes
	user_held: bool
	layer: str = 'at_rest'

	def to_blob(self) -> str:
		"""One URL-safe string, so a sealed value fits a TEXT column and a JSON field alike.

		The layout is `v1.<layer>.<nonce>.<salt-or-dash>.<ciphertext>`: versioned, because a second
		scheme will arrive and a reader must be able to tell which one produced a row.
		"""
		assert self.layer in LAYERS, f'unknown key layer {self.layer!r}'
		salt = base64.urlsafe_b64encode(self.salt).decode() if self.salt else '-'
		blob = (f'v1.{self.layer}.{base64.urlsafe_b64encode(self.nonce).decode()}.{salt}.'
			f'{base64.urlsafe_b64encode(self.ciphertext).decode()}')
		assert blob.startswith('v1.'), 'sealed values are version-tagged'
		return blob

	@classmethod
	def from_blob(cls, blob: str) -> 'Sealed':
		assert blob.startswith('v1.'), f'unknown sealed-value version: {blob[:3]!r}'
		_, layer, nonce_b64, salt_b64, ct_b64 = blob.split('.', 4)
		assert layer in LAYERS, f'unknown key layer {layer!r}'
		nonce = base64.urlsafe_b64decode(nonce_b64)
		assert len(nonce) == NONCE_BYTES, 'a GCM nonce is 96 bits'
		salt = None if salt_b64 == '-' else base64.urlsafe_b64decode(salt_b64)
		assert (layer == 'user_held') == (salt is not None), (
			'a user-held value carries its salt, and no other layer does')
		return cls(nonce=nonce, salt=salt, ciphertext=base64.urlsafe_b64decode(ct_b64),
			user_held=layer == 'user_held', layer=layer)


class CryptoService(LogMixin):
	"""§SEC-003's encryption, as functions a store can call rather than a standard it can cite.

	`at_rest_key` is the deployment key. When it is absent the service refuses to seal rather than
	returning plaintext with a cipher label on it — a store that silently falls back is the exact
	shape the audit row described, and it is the failure mode a fallback always has.

	`app_layer_key` is the *second* key §SEC-003's contact-list standard asks for. It is separate
	from `at_rest_key` on purpose: a database dump that yields the at-rest key must not also yield
	the contact lists, or the "additional application-layer encryption" is the same lock fitted
	twice. The two are stored apart — the at-rest key unwraps from the keystore, the application
	key from a separate secret — and neither derives from the other.
	"""

	def __init__(self, at_rest_key: bytes | None = None, app_layer_key: bytes | None = None) -> None:
		self._at_rest = at_rest_key
		self._app_layer = app_layer_key
		self._sealed_count = 0
		assert self._at_rest is None or len(self._at_rest) == KEY_BYTES, 'at-rest key is 256 bits'
		assert self._app_layer is None or len(self._app_layer) == KEY_BYTES, 'app-layer key is 256 bits'
		assert not (at_rest_key and app_layer_key and at_rest_key == app_layer_key), (
			'the application-layer key must differ from the at-rest key, or it adds no layer')

	@property
	def available(self) -> bool:
		"""Whether this deployment can seal. Reported rather than assumed."""
		return self._at_rest is not None

	@property
	def has_app_layer(self) -> bool:
		"""Whether contact lists and location history get their second layer."""
		return self._app_layer is not None

	def seal(self, plaintext: bytes, user_key: bytes | None = None, app_layer: bool = False) -> Sealed:
		"""Encrypt with a fresh nonce. `user_key` selects the user-held path.

		The nonce is random per message and never derived from the plaintext or a counter: GCM's
		security collapses completely on nonce reuse under one key, and a random 96-bit nonce is
		safe to ~2^32 messages, far beyond a handset's lifetime.

		`app_layer` selects §SEC-003's second key for contact lists and location history. It is a
		parameter rather than a separate method because the caller decides what a value *is*, and
		the store is where that is known.
		"""
		assert plaintext, 'nothing to seal'
		assert not (app_layer and user_key is not None), 'the two key paths are alternatives'
		if user_key is not None:
			assert len(user_key) == KEY_BYTES, 'a user-held key is 256 bits'
			key = user_key
		elif app_layer:
			assert self._app_layer is not None, (
				'no application-layer key is configured, so contact lists and location history '
				'cannot be sealed; refusing rather than writing them under the at-rest key alone')
			key = self._app_layer
		else:
			assert self._at_rest is not None, (
				'this deployment holds no at-rest key, so it cannot seal; refusing rather than '
				'writing plaintext under an encryption label')
			key = self._at_rest
		layer = 'user_held' if user_key is not None else ('app_layer' if app_layer else 'at_rest')
		nonce = os.urandom(NONCE_BYTES)
		ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
		assert len(ciphertext) == len(plaintext) + TAG_BYTES, 'GCM appends a 128-bit tag'
		self._sealed_count += 1
		return Sealed(nonce=nonce, salt=None, ciphertext=ciphertext, user_held=user_key is not None,
			layer=layer)

	def open(self, sealed: Sealed, user_key: bytes | None = None, app_layer: bool = False) -> bytes:
		"""Decrypt, and fail loudly on a tampered ciphertext.

		`InvalidTag` is not caught. A store that returned empty bytes on a failed authentication
		would turn an attack into a missing record, and the two are not the same event.
		"""
		# The layer comes off the value, never off the caller's argument. A caller that passed the
		# wrong `app_layer` would otherwise get a failed authentication for a value that is intact,
		# and a wrong key would be indistinguishable from tampering.
		if sealed.layer == 'user_held':
			key = user_key
		elif sealed.layer == 'app_layer':
			key = self._app_layer
		else:
			key = self._at_rest
		assert key is not None, f'no {sealed.layer} key for this sealed value'
		assert len(key) == KEY_BYTES, 'key is 256 bits'
		try:
			return AESGCM(key).decrypt(sealed.nonce, sealed.ciphertext, None)
		except InvalidTag:
			self._log_warn('sealed value failed authentication', user_held=sealed.user_held)
			raise

	# --- the user-held path, for §SEC-003's cloud backup ---------------------------------------

	def seal_for_user(self, plaintext: bytes, passphrase: str) -> Sealed:
		"""Seal under a key derived from a passphrase the deployment does not keep.

		The salt is fresh per backup, so the same passphrase on two backups does not produce the
		same key — which would let an attacker who broke one break the other for free.
		"""
		salt = os.urandom(SALT_BYTES)
		sealed = self.seal(plaintext, user_key=derive_key(passphrase, salt))
		# `seal` does not know the salt; the derived key is only reproducible with it.
		return Sealed(nonce=sealed.nonce, salt=salt, ciphertext=sealed.ciphertext, user_held=True,
			layer='user_held')

	def open_for_user(self, sealed: Sealed, passphrase: str) -> bytes:
		"""Open a backup with the passphrase. Without it, the ciphertext is inert."""
		assert sealed.user_held and sealed.salt is not None, (
			'a user-held backup carries its own salt; this value was sealed with the deployment key')
		return self.open(sealed, user_key=derive_key(passphrase, sealed.salt))

	def sealed_count(self) -> int:
		return self._sealed_count
