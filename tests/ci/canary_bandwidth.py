"""Canaries for §16.4's two uncarried mechanisms: Brotli, and resumable upload.

The section names six mechanisms and four were carried. The two that were not had the shape this
repo keeps producing — a capability named in the spec with no carrier anywhere in the tree, and no
test that could see the absence because nothing was failing:

* **"Payload compression: gzip / Brotli"** — the slash is a set, and only gzip was ever tried. The
  test that covered it asserted `batch.encoding == 'gzip'`, which is a check on *which codec the
  implementation happened to use* rather than on what the section asks for: it passed for as long
  as gzip was the only one tried, and would have gone on passing if gzip were the only one ever
  tried. That is the same failure the §20.2 lever canary names — a test that is a strict subset of
  the section it covers.
* **"resumable upload"** — named in the image-compression bullet, with nothing behind it: the only
  upload route read the whole body in one request, so a dropped connection on a 6 MB photo meant
  starting again from zero.

Each mutation is *disjoint* from what its predicate reads:

* **#1 makes the codec choice unconditional** — gzip always wins — which is the defect as it
  shipped. Aimed at the property test, because the old assertion (`== 'gzip'`) would still pass:
  that is exactly why the assertion had to change rather than the code alone.
* **#2 drops Brotli from the model's pattern**, so the encoding that goes on the wire is refused by
  the model that carries it. Aimed at the property test.
* **#3 makes a replayed chunk an error instead of an answer.** The retry-after-a-drop is the case
  the mechanism exists for; refusing it sends a client hunting a bug in its own arithmetic. Aimed
  at the service test that pins the position returned.
* **#4 appends a chunk before checking its hash.** The corruption then surfaces at the end as a
  whole-file mismatch, after the person paid for every chunk. Aimed at the service test.
* **#5 skips the declared-bytes cap**, so a session grows past what it said it would. Aimed at the
  service test.
* **#6 lets a gap through** — the offset check removed, so a chunk lands at the wrong place and the
  finished photo hashes wrong for its owner. Aimed at the service test.
* **#7 serves the session without checking the owner.** The subject lives on the session, so
  `require_self` cannot guard these routes; this restores the hole where any token can read and
  append to any in-flight upload. Aimed at the **front door**, because the finding is reachable
  over HTTP and a guard unit test would prove less.
* **#8 moves the tier-4 gate from the start of the upload to the finish.** A client then spends the
  whole metered upload on a photo the server was always going to refuse. Aimed at the service test
  that pins the refusal at open time.

Canary #9 is the one that reads a client rather than the server: "the route exists" and "a handset
calls it" are different facts, and only the second is a capability.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). `__pycache__`
is purged after each write, for the reason `canary_inf001.py` documents. A canary that passes is a
bug in the canary, so a MISSED line fails this script.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
SY = ROOT / 'src/afya/sync/service.py'
SV = ROOT / 'src/afya/sync/views.py'
E = ROOT / 'src/afya/evidence/service.py'
S = ROOT / 'src/afya/service.py'
IOS = ROOT / 'ios/AfyaYangu/Evidence.swift'

CANARIES = [
	# 1. gzip always wins — the defect as it shipped, where Brotli was never tried. The old
	#    `== 'gzip'` assertion would still pass, which is why the assertion is the finding.
	('gzip is preferred by construction', SY,
	 "			candidates = {'gzip': gzip.compress(raw, compresslevel=6),\n"
	 "			              'br': brotli.compress(raw, quality=5)}\n"
	 "			best = min(candidates, key=lambda k: len(candidates[k]))",
	 "			candidates = {'gzip': gzip.compress(raw, compresslevel=6)}\n"
	 "			best = 'gzip'",
	 'test_both_codecs_the_section_names_are_tried_and_the_smaller_wins'),

	# 2. Brotli dropped from the pattern the model carries, so the winning encoding is refused by
	#    the model that is supposed to describe it. Disjoint from the codec selection itself.
	('the model no longer admits the brotli encoding', SV,
	 "	encoding: str = Field(pattern=r'^(identity|gzip|br)$')",
	 "	encoding: str = Field(pattern=r'^(identity|gzip)$')",
	 'test_both_codecs_the_section_names_are_tried_and_the_smaller_wins'),

	# 3. A replayed chunk is refused instead of answered with the true position — the retry the
	#    mechanism exists for. Aimed at the service test that pins what a retry returns.
	('a replayed chunk is refused instead of answered', E,
	 "		if chunk.offset < have:\n"
	 "			# Bytes the server already holds. Not an error the client caused — a retry after an\n"
	 "			# unacknowledged chunk is exactly this — so the answer is the true position, not a\n"
	 "			# refusal. Returning `next_offset` is what makes the retry safe to issue blindly.\n"
	 "			self._log_info('upload chunk already held', session=session_id, offset=chunk.offset, have=have)\n"
	 "			return self._session_view(session)",
	 "		if chunk.offset < have:\n"
	 "			raise ValueError('this chunk was already received')",
	 'test_a_replayed_chunk_is_answered_with_the_true_position'),

	# 4. The chunk's hash checked after it is appended, so a corrupted chunk is stored and the
	#    failure surfaces at the end as a whole-file mismatch.
	('a corrupted chunk is appended before it is checked', E,
	 "		raw = base64.urlsafe_b64decode(chunk.data + '=' * (-len(chunk.data) % 4))\n"
	 "		if hashlib.sha256(raw).hexdigest() != chunk.chunk_sha256:\n"
	 "			raise ValueError('this chunk arrived corrupted; send it again from the same offset')",
	 "		raw = base64.urlsafe_b64decode(chunk.data + '=' * (-len(chunk.data) % 4))\n"
	 "		if False:\n"
	 "			raise ValueError('this chunk arrived corrupted; send it again from the same offset')",
	 'test_a_corrupted_chunk_is_refused_before_it_is_appended'),

	# 5. The declared-bytes cap removed, so a session grows past what it said it would and the size
	#    limit is checked against nothing.
	('an upload may grow past what it declared', E,
	 "		if have + len(raw) > session.declared_bytes:\n"
	 "			raise ValueError(\n"
	 "				f'this upload declared {session.declared_bytes} bytes and the chunk would take it past '\n"
	 "				f'that; open a new upload with the correct size')",
	 "		if False:\n"
	 "			raise ValueError('unreachable')",
	 'test_an_upload_cannot_grow_past_what_it_declared'),

	# 6. A gap is accepted, so a chunk lands at the wrong place and the finished photo hashes wrong
	#    for its owner. Aimed at the service test that pins the resume offset.
	('a gap in the prefix is accepted', E,
	 "		if chunk.offset > have:\n"
	 "			raise ValueError(\n"
	 "				f'the server holds {have} bytes and this chunk starts at {chunk.offset}, so a gap '\n"
	 "				f'would be written; resume from byte {have}')",
	 "		if False:\n"
	 "			raise ValueError('unreachable')",
	 'test_a_gap_is_refused_with_the_offset_to_resume_from'),

	# 7. The ownership check removed from the session guard, so any token can read and append to any
	#    in-flight upload. Aimed at the front door, because the hole is reachable over HTTP.
	('an upload session is reachable by any token', S,
	 "			if owner != subject:\n"
	 "				raise HTTPException(status_code=403, detail='this upload belongs to another person')",
	 "			if False:\n"
	 "				raise HTTPException(status_code=403, detail='unreachable')",
	 'test_another_persons_upload_session_is_not_reachable'),

	# 8. The tier-4 gate moved off the open and onto the finish, so a client spends the whole
	#    metered upload on a photo the server was always going to refuse.
	('a dormant photo is refused at the end rather than the start', E,
	 "		self.gate(submission.kind)\n"
	 "		assert submission.consent, 'the photo is shared only with the consent recorded for this submission'\n"
	 "		session = _Upload(\n"
	 "			session_id='UP-' + submission.submission_id.removeprefix('EV-')[:12],",
	 "		assert submission.consent, 'the photo is shared only with the consent recorded for this submission'\n"
	 "		session = _Upload(\n"
	 "			session_id='UP-' + submission.submission_id.removeprefix('EV-')[:12],",
	 'test_a_dormant_tier4_photo_is_refused_at_the_start_not_the_end'),

	# 9. The iOS client stops naming the session path, so the route is carried on the server and
	#    reachable from one handset only — the "a route with no call is a capability nobody can
	#    reach" shape. Aimed at the client-source test, because no server-side test can see it.
	('the iOS client never reaches the resumable route', IOS,
	 r'evidence/upload/\(sessionId)/chunk', r'evidence/upload/\(sessionId)/zzz',
	 'test_both_native_clients_reach_the_resumable_route'),
]

_FILES = {
	'test_both_codecs_the_section_names_are_tried_and_the_smaller_wins': 'tests/ci/test_sync.py',
	'test_a_replayed_chunk_is_answered_with_the_true_position': 'tests/ci/test_evidence.py',
	'test_a_corrupted_chunk_is_refused_before_it_is_appended': 'tests/ci/test_evidence.py',
	'test_an_upload_cannot_grow_past_what_it_declared': 'tests/ci/test_evidence.py',
	'test_a_gap_is_refused_with_the_offset_to_resume_from': 'tests/ci/test_evidence.py',
	'test_a_dormant_tier4_photo_is_refused_at_the_start_not_the_end': 'tests/ci/test_evidence.py',
	'test_another_persons_upload_session_is_not_reachable': 'tests/ci/test_sec002.py',
	'test_both_native_clients_reach_the_resumable_route': 'tests/ci/test_sec002.py',
}

# A canary whose test does not exist would "pass" for the wrong reason, so collection is asserted
# for every file a canary aims at, before anything is mutated.
for _f in sorted(set(_FILES.values())):
	_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only', _f],
		cwd=ROOT, capture_output=True, text=True)
	assert _collected.returncode == 0, _collected.stdout[-2000:]

failures = []
for name, path, old, new, node in CANARIES:
	f = _FILES[node]
	backup = pathlib.Path(f'/tmp/canary_bandwidth.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	# A same-second write of the same size reuses the previous canary's bytecode, and the canary then
	# tests code it never mutated. Purged for the file just written.
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		# `-v`, not `-q`: a passing run under `-q` prints no node name, so `aimed` could not tell
		# the right test ran from a collection that silently picked up nothing.
		proc = subprocess.run(['uv', 'run', 'pytest', '-v', '-p', 'no:randomly', f'{f}::{node}'],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
		aimed = node in proc.stdout
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
		for cache in path.parent.rglob('__pycache__'):
			shutil.rmtree(cache, ignore_errors=True)
	ok = caught and aimed
	print(f'{"CAUGHT " if ok else "MISSED "} {name}')
	if not ok:
		failures.append(name)
		print(f'  returncode={proc.returncode} aimed_at_node={aimed}')
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
