# §SEC-003 — encryption at rest, and where the key lives

Retrieved 2026-10-13. Written because three of §SEC-003's five Standards were `missing` for one
reason — the tree stated the standard and applied it nowhere — and the fix involved two decisions a
reviewer will ask about: which primitive, and where the key is kept.

## What the section asks for

| Standard | Status after this work |
|---|---|
| At rest: AES-256 | implemented — AES-256-GCM, key in a 0600 sidecar |
| In transit: TLS 1.3 | already carried (Caddy terminator) |
| Contact lists and location history: additional application-layer encryption | implemented — a second, distinct key |
| Cloud backup: end-to-end encrypted with user-held key | implemented — scrypt-derived from a passphrase |
| Key management: hardware-backed keystore | **still `deferred`** — see below |

## Decisions

### AES-256-GCM, not AES-256-CBC

The section says "AES-256" and does not name a mode. GCM was chosen because it authenticates: a
tampered ciphertext fails to open rather than decrypting to a plausible contact. CBC with a separate
MAC is the other correct answer and needs the encrypt-then-MAC construction got right; GCM is one
primitive with one call. Source: NIST SP 800-38D (Recommendation for Block Cipher Modes of
Operation: GCM and GMAC).

The nonce is 96 bits, random per message, never derived from a counter or the plaintext. GCM's
security collapses on nonce reuse under one key; a random 96-bit nonce is safe to ~2^32 messages.

### scrypt for the user-held key, not PBKDF2 or a hash

A passphrase is not a key. Hashing or padding it is how an encrypted-looking backup becomes an
unencrypted one. scrypt is memory-hard, so an offline dictionary attack pays in RAM rather than in
parallelism. Parameters n=2^15, r=8, p=1 — ~64 MB and ~0.1 s, chosen so a backup does not feel
broken to the person waiting for it. Source: RFC 7914.

Rejected: **PBKDF2** (not memory-hard, so a GPU farm is the right tool against it); **Argon2id**
(better, but not in the `cryptography` wheel and adding a second crypto dependency for one KDF is
not worth it); **HKDF** (a KDF for high-entropy input, wrong tool for a passphrase).

### Two keys, not one fitted twice

§SEC-003 asks for an *additional* application layer over contact lists and location history. One key
used twice is not a layer: a database dump yielding the at-rest key would yield the contact lists
with it. So `CryptoService` holds `at_rest_key` and `app_layer_key`, refuses to be constructed with
them equal, and tags every sealed value with the layer that produced it so a reader never guesses.

### The key is a 0600 sidecar, and this is not the standard the section asks for

The section's key-management standard names the Android Keystore and the iOS Secure Enclave. A
server-side Python process cannot reach either. What this build does instead: generate the at-rest
key on first use and persist it in `<db>.key`, mode 0600, opened with `O_CREAT|O_EXCL` so there is no
window where the key is world-readable.

**What that protects:** a copy of the database file alone — a dump, a backup bucket holding only
`.db`, a snapshot of one file.

**What it does not:** a reader with access to the whole directory has the key beside the ciphertext.

This is why the key-management row stays `deferred` and `EncryptionPosture.at_rest` reads `none`
when no key is wired. A sidecar is a real improvement on plaintext and is not the hardware-backed
keystore, and the posture reports the difference rather than claiming AES-256 has closed it.

## Rejected: hand-rolling the cipher

The repo hand-rolled a PDF writer rather than add a library, so the precedent was worth checking. It
does not transfer: a PDF format is a data layout where a bug is a malformed file, and a cipher is a
security primitive where a bug is silent. `cryptography` (50.0.2) was added instead — the only new
runtime dependency, maintained, and with no known vulnerabilities at `pip-audit`.

## Sources

- NIST SP 800-38D — Recommendation for Block Cipher Modes of Operation: GCM and GMAC.
  <https://csrc.nist.gov/pubs/sp/800/38/d/final>
- RFC 7914 — The scrypt Password-Based Key Derivation Function. <https://www.rfc-editor.org/rfc/rfc7914>
- `cryptography` documentation, AESGCM and Scrypt. <https://cryptography.io/en/latest/hazmat/primitives/>

No PDF is archived for these: each is a specification whose current text is the authority, and a
snapshot would go stale against the live document. The decisions above record what was taken from
each.
