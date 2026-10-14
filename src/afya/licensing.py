"""The licence the client is published under (§LOC-002, §SEC-006).

Two audit rows ask for the same thing from two directions:

- §11.5 LOC-002's third Privacy property: *"Open-source client for independent verification"*.
- §12.2 SEC-006's third Feature: *"Open-source client code"*.

Both were `missing` for one reason, and the note on the first had it exactly right: *"a repository's
licence is not something this tree can assert about itself"*. That was true while the licence was
undecided — a tree cannot declare its own terms, the owner does. It is now decided (MIT), so the
tree can carry the fact, and the reason it belongs in a module rather than only in the `LICENSE`
file at the root is `afya/refs.py`: an audit row's reference is `module:attr`, walked by import, so
a control whose evidence is a file nothing imports is a control the audit cannot check.

**What this module does and does not claim.** It states the licence, the holder, the file the terms
live in, and whether that file is actually present with a matching identifier — `licence_is_offered`
reads the root `LICENSE` rather than trusting the constant, so a tree that says MIT and ships no
terms fails rather than passes. What it does *not* claim is that the client is independently
verifiable in the sense the row means: a licence permits verification, it does not perform it, and
no external party has audited this tree. The audit row's note says so rather than letting "MIT" read
as "verified".

The holder is the repository's owner and is stated as a constant because a licence with no copyright
line is not a licence. It is not derived from git config: a commit's author is whoever pushed, and a
copyright holder is a legal person the owner names.
"""
from pathlib import Path

# The repository root, from this file: src/afya/licensing.py -> src/afya -> src -> root.
REPO_ROOT = Path(__file__).resolve().parents[2]

LICENCE_FILE = REPO_ROOT / 'LICENSE'

# SPDX identifier, which is what a tool reads, alongside the human name a person reads.
SPDX_ID = 'MIT'
LICENCE_NAME = 'MIT License'

# The copyright line the terms carry. Stated here rather than parsed out of the file so the two can
# be compared: `test_the_licence_file_matches_what_the_code_declares` asserts the file's own line
# contains this holder, and a rename that updated one and not the other fails instead of drifting.
COPYRIGHT_HOLDER = 'Nyimbi Odero'
COPYRIGHT_YEAR = 2026

# §LOC-002's property is "open-source client **for independent verification**", and this is the
# honest statement of where that stands. A permissive licence is what makes verification *possible*
# — anyone may read, build and test the clients — and it is not evidence that anyone has. The three
# clients are the Python service, the Kotlin app and the Swift app, all in this tree, which is what
# makes "the client" a thing a reader can actually obtain.
VERIFICATION_NOTE = (
	'MIT permits anyone to read, build and test the clients in this tree. It does not mean any '
	'external party has done so: no independent audit of this repository has been performed.'
)


def licence_is_offered() -> bool:
	"""Whether the tree ships the terms it claims to ship.

	Reads the file rather than returning True from the constant, because the failure this guards
	against is a repository that declares a licence in code and ships no `LICENSE` — which is
	all-rights-reserved with a comment saying otherwise, the worst of both.
	"""
	if not LICENCE_FILE.is_file():
		return False
	text = LICENCE_FILE.read_text(encoding='utf-8')
	return SPDX_ID in text and COPYRIGHT_HOLDER in text


def licence_offer() -> dict[str, object]:
	"""The licence as the transparency publication and the audit cite it."""
	return {
		'spdx_id': SPDX_ID,
		'name': LICENCE_NAME,
		'copyright_holder': COPYRIGHT_HOLDER,
		'copyright_year': COPYRIGHT_YEAR,
		'file': LICENCE_FILE.name,
		'offered': licence_is_offered(),
		'note': VERIFICATION_NOTE,
	}
