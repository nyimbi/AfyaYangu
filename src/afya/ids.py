"""UUID7 string helpers per project convention."""
import itertools
import secrets
import threading

from uuid6 import uuid7


def uuid7str() -> str:
	return str(uuid7())


# A UUID7 is not uniformly random, and reading one as if it were is a defect that hides until two
# records are made close together. Its first 48 bits are a millisecond timestamp, so `uuid7str()[:10]`
# — ten hex characters, the top 40 bits of that timestamp — is constant across a **256 ms** window:
# two diary entries logged in the same breath took the same `entry_id`, and the second silently
# replaced the first in the store's dict, which turned two days of symptoms into one. `[-6:]` is a
# different failure with the same shape: the last six hex are 24 bits of the random field, which
# repeats by birthday at roughly 4,800 ids in a process.
#
# `ref8` is therefore not a UUID7 read differently, it is a counter. Twelve bits are drawn once per
# process so two processes do not march in step, and the remaining twenty are a monotonic sequence,
# so an id cannot repeat until a million have been minted. It is deliberately eight characters: the
# short reference a person reads out over the phone is the point, and the guarantee a store needs is
# that the key it files under is the key it will be asked for.
_REF_PREFIX = secrets.randbits(12)
_REF_SEQ = itertools.count()
_REF_LOCK = threading.Lock()


def ref8() -> str:
	"""Eight hex characters, distinct for a million ids within a process.

	The counter is the whole guarantee and the prefix is only there to keep two processes apart, so
	an id that has to be unique beyond a million per process belongs in a store that can say so —
	not in a truncation of a UUID7, which never carried that guarantee at all.
	"""
	with _REF_LOCK:
		n = next(_REF_SEQ)
	return f'{_REF_PREFIX:03X}{n & 0xFFFFF:05X}'
