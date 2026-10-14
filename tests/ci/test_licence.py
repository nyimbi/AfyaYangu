"""§LOC-002's "Open-source client for independent verification" and §SEC-006's "Open-source client code".

Two sections asked for the same thing from two directions and both rows were `missing` for one
reason. §LOC-002's note had it exactly right:

	nothing makes the client open source — the tree carries no LICENSE and no source offer;
	§SEC-006's "Open-source client code" row is the same absence, and a repository's licence is not
	something this tree can assert about itself

The last clause is the whole difficulty. A tree cannot choose its own terms; the owner does. So the
fix had two halves and only one of them is code: the owner decided MIT, and *then* the tree could
carry the fact. What the code adds is the part a licence file alone does not give — a `module:attr`
reference `afya/refs.py` can walk, so the audit row cites something checkable rather than a filename,
and a gate that reads the root `LICENSE` instead of trusting a constant.

That gate is the point of most of this file. A repository that declares MIT in code and ships no
terms is all-rights-reserved with a comment saying otherwise — the worst of both, and exactly the
failure a constant cannot catch.

The last test records the honest boundary, because the row's own words are "for independent
verification" and a permissive licence is not a verification: it makes one *possible*. Nothing here
claims an audit that has not happened.
"""
import re
from pathlib import Path

import httpx
import pytest

from afya.content_audit.service import content_report
from afya.licensing import (
	COPYRIGHT_HOLDER, LICENCE_FILE, REPO_ROOT, SPDX_ID, licence_is_offered, licence_offer,
)
from afya.refs import resolves
from afya.service import build_services, create_app

REPO = Path(__file__).resolve().parents[2]
FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')


# --- the tree ships the terms it claims ---------------------------------------------------------

def test_the_licence_file_exists_at_the_repository_root() -> None:
	"""The artefact, not the claim. A licence that lives only in a constant is a repository with no
	licence, so the file is asserted to be where GitHub and every licence scanner looks for it."""
	assert LICENCE_FILE.is_file(), f'no LICENSE at {LICENCE_FILE}'
	assert LICENCE_FILE.parent == REPO_ROOT == REPO, 'the licence must sit at the repository root'


def test_the_file_actually_says_mit_and_names_a_holder() -> None:
	"""Read, not trusted. `licence_is_offered` is what the audit row cites and it reads the file, so
	this pins the reading against a file that is present but says something else — a BSD or Apache
	text sitting under an MIT constant is the drift the constant cannot see."""
	text = LICENCE_FILE.read_text(encoding='utf-8')
	assert SPDX_ID in text, f'the LICENSE does not carry the identifier {SPDX_ID!r}'
	assert COPYRIGHT_HOLDER in text, 'a licence with no copyright line names no holder'
	assert 'Permission is hereby granted, free of charge' in text, 'this is not the MIT grant'


def test_a_declared_licence_with_no_file_is_reported_as_not_offered(tmp_path: Path,
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
	"""The gate, canaried in-process. `licence_is_offered` must answer false when the file is gone —
	otherwise it is a constant with a function around it, and a repository that deleted its LICENSE
	would keep publishing `offered: true`. Pointed at an empty directory rather than deleting the
	real file, so the canary cannot damage the tree it is checking."""
	import afya.licensing as lic
	monkeypatch.setattr(lic, 'LICENCE_FILE', tmp_path / 'LICENSE')
	assert lic.licence_is_offered() is False, 'a missing LICENSE must not read as offered'
	(tmp_path / 'LICENSE').write_text('All rights reserved.', encoding='utf-8')
	assert lic.licence_is_offered() is False, 'a file that is not the MIT grant must not read as offered'


def test_the_offer_reports_the_identifier_holder_and_file() -> None:
	"""What the route serves and what the audit cites. `offered` is computed, so this also asserts
	the real tree passes its own gate — the one fact that makes the row true rather than stated."""
	offer = licence_offer()
	assert offer['spdx_id'] == 'MIT' and offer['name'] == 'MIT License'
	assert offer['copyright_holder'] == COPYRIGHT_HOLDER
	assert offer['file'] == 'LICENSE'
	assert offer['offered'] is True, 'the audit row claims a licence the tree must actually ship'


def test_the_note_does_not_let_mit_read_as_verified() -> None:
	"""The row says "for independent verification". A licence permits verification; it does not
	perform it, and no external party has audited this tree. The served note has to say so, or the
	closure of this row would be a stronger claim than the fact behind it."""
	note = str(licence_offer()['note'])
	assert 'no independent audit' in note.lower(), 'the note must not imply a verification happened'
	assert 'read, build and test' in note.lower(), 'the note must say what MIT actually enables'


# --- the audit can check it ---------------------------------------------------------------------

def test_the_audit_rows_resolve_to_something_importable() -> None:
	"""`afya/refs.py` walks a `module:attr` by import, so a row citing a filename would not resolve.
	This is why the licence needed a module and not only a root file."""
	assert resolves('afya.licensing:licence_is_offered')
	assert resolves('afya.licensing:licence_offer')


def test_both_rows_that_asked_for_this_are_carried() -> None:
	"""§LOC-002 and §SEC-006 are the same absence from two sections, so they are asserted together:
	closing one and leaving the other would report a gap shut that is still open from the other
	section's direction."""
	report = content_report()
	missing = report.missing
	assert not any(m.startswith('§LOC-002:') for m in missing), '§LOC-002 is still missing its row'
	assert not any(m.startswith('§SEC-006:') for m in missing), '§SEC-006 is still missing its row'


# --- reachable, and free of internal handles ----------------------------------------------------

async def test_the_route_serves_the_licence_with_no_token() -> None:
	"""Open, like `/security/disclosure` and for the same reason: a licence that required a token
	would not be the licence the client is offered under. A reader deciding whether to trust the app
	is exactly who this is for."""
	transport = httpx.ASGITransport(app=create_app(build_services()))
	async with httpx.AsyncClient(transport=transport, base_url='http://test') as c:
		r = await c.get('/security/licence')
	assert r.status_code == 200, 'the licence must be readable without a token'
	body = r.json()
	# The fields only `licence_offer()` produces, not a stub's idea of them. Asserting the id and
	# `offered` alone passes against a route that returns `{'spdx_id': 'MIT', 'offered': True}` and
	# never reads the file — a canary caught exactly that, and the assertion was the weak part.
	assert body['spdx_id'] == 'MIT' and body['offered'] is True
	assert body['copyright_holder'] == COPYRIGHT_HOLDER, 'the route did not read the offer'
	assert body['copyright_year'] == 2026 and body['name'] == 'MIT License'
	assert body['file'] == 'LICENSE'
	assert 'no independent audit' in str(body['note']).lower()
	assert FEATURE_CODE.search(r.text) is None, 'a spec code reached the served licence'


def test_the_licence_has_a_screen_and_its_slug_is_a_slug() -> None:
	"""The row says *for independent verification*, which is something a reader does. A licence a
	person can only find by opening the repository is one they cannot check from the app they are
	deciding whether to trust — the same join §SEC-001's toggle screen was missing."""
	from afya.mobile.actions import FEATURE_OF, catalogue
	acts = {a.id: a for a in catalogue()}
	assert 'licence_terms' in acts, 'no catalogue action reaches the licence'
	act = acts['licence_terms']
	assert (act.method, act.path) == ('GET', '/security/licence')
	assert FEATURE_OF['licence_terms'] == 'SEC-006'
	assert FEATURE_CODE.search(act.id) is None and FEATURE_CODE.search(act.title) is None


def test_the_publication_carries_the_licence_for_a_reader_who_never_opens_the_repo() -> None:
	"""§SEC-006's quarterly document is the surface a member of the public actually reads. A licence
	stated only in the repository is a fact about the repository; stated in the publication it is
	one a person who never clones anything can find.

	It is a field of its own rather than a `TransparencySection`, and this asserts the distinction:
	every section is a count over people under §11.7's min-cell rule, and a licence is neither a
	count nor suppressible. Folding it in would also make "the publication has no sections" — a real
	state when no source is wired — stop being true.
	"""
	from afya.retention.service import RetentionService
	pub = RetentionService().build_publication('2026-Q3', '2026-10-05T09:00:00Z')
	assert pub.licence is not None, 'the publication dropped the licence'
	assert pub.licence['spdx_id'] == 'MIT' and pub.licence['offered'] is True
	assert 'no independent audit' in str(pub.licence['note']).lower(), 'the same boundary as the route'
	assert all(s.key != 'licence' for s in pub.sections), 'the licence is not a suppressed cell count'
