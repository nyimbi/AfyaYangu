"""Canaries for tests/ci/test_sec004.py.

§SEC-004's "Optional pseudonymous profile" was `missing` in the audit and *leaking* in the code.
`POST /facilities/{facility_id}/reports` took `reporter_ref` out of the request body and
`GET /facilities/{facility_id}/reports` served it back on a feed the route itself calls a public
screen — so the app published the string that keys `/records/{ref}`, `/maternal/{ref}`, `/wallet`
and every other personal route, to anyone who asked, with the caller choosing whose it was.

The canaries are the cheap ways to have a handle that is not one:

* **#1** is the defect exactly as it was found: the feed stores the subject reference it was given.
  It is worth reading because it *looked* correct — the field is even named `reporter_ref`.
* **#2** derives the handle from the subject alone, with no epoch in the digest. The handle is then
  stable forever, which is a relabelled identifier and correlates every post a person ever makes.
* **#7** puts the reporter back in the request body, so a caller can attribute a report to someone
  else — the second half of the same leak, and the half a feed-shaped fix would miss.
* **#10** drops the caveat. A handle that hides a name is not anonymity, and a screen implying
  otherwise changes what a person is willing to write.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script. The `__pycache__`
purge after each write is load-bearing for the reason `canary_inf001.py` documents.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
IS = ROOT / 'src/afya/identity/service.py'
IV = ROOT / 'src/afya/identity/views.py'
FS = ROOT / 'src/afya/facilities/service.py'
FV = ROOT / 'src/afya/facilities/views.py'
G = ROOT / 'src/afya/service.py'
ST = ROOT / 'src/afya/strings.py'
M = ROOT / 'src/afya/mobile/actions.py'

CANARIES = [
	# 1. The feed stores the reference it was handed — the defect as found. The public screen then
	#    carries a subject reference, which is the lookup key for every personal route.
	('the feed publishes the subject reference', FS,
	 "		report = FacilityReport(facility_id=facility_id, text=text.strip(), reporter_ref=handle)",
	 "		report = FacilityReport(facility_id=facility_id, text=text.strip(), reporter_ref=reporter_ref)",
	 'test_the_report_feed_publishes_a_handle_not_the_subject_reference'),

	# 2. The epoch leaves the digest, so the handle never changes. It is still not the subject, so a
	#    weaker test would pass — but it correlates every post the person ever makes, which is the
	#    property the leak had. This is the canary that proves the rotation is load-bearing.
	('the handle never rotates', IS,
	 "		digest = hashlib.sha256(f'{subject_ref}:{epoch}'.encode()).hexdigest()",
	 "		digest = hashlib.sha256(f'{subject_ref}'.encode()).hexdigest()",
	 'test_the_handle_rotates_with_the_epoch'),

	# 3. The handle is derived from the subject in a way that carries it, so the "pseudonym" contains
	#    the reference it was meant to replace.
	('the handle carries the subject reference', IS,
	 "			subject_ref=subject_ref, handle=f'{word}-{digest[8:12]}', epoch=epoch,",
	 "			subject_ref=subject_ref, handle=f'{word}-{subject_ref[-4:]}', epoch=epoch,",
	 'test_the_handle_is_derived_from_the_subject_and_not_from_it'),

	# 4. The suffix collapses to a constant, so every subject in a window shares one handle — the
	#    handle labels a window rather than separating the people in it, and two people's posts read
	#    as one person's. The word alone is *not* the mutation: the digest suffix separates subjects
	#    regardless, which an earlier cut of this canary got wrong and MISSED.
	('the handle does not separate subjects', IS,
	 "			subject_ref=subject_ref, handle=f'{word}-{digest[8:12]}', epoch=epoch,",
	 "			subject_ref=subject_ref, handle=f'{word}-0000', epoch=epoch,",
	 'test_two_subjects_in_one_window_do_not_share_a_handle'),

	# 5. A chosen handle is ignored, so the setting exists and does nothing — the person picks a name
	#    and the app keeps showing the derived one.
	('the chosen handle is ignored', IS,
	 "		if subject_ref in self._chosen_handles:",
	 "		if False:",
	 'test_a_chosen_handle_is_used_and_does_not_rotate'),

	# 6. The identifier refusal goes, so a person can publish their own phone number as a handle —
	#    the key §SEC-004 exists to keep off the screen, typed in by the person themselves.
	('a phone number is a legal handle', IS,
	 "		assert not (digits and digits == handle.replace('+', '').replace(' ', '')), \\\n			'a phone number is not a pseudonym'",
	 "		assert True, 'a phone number is not a pseudonym'",
	 'test_a_person_cannot_choose_their_own_identifier_as_a_handle'),

	# 7. The reporter goes back into the request body, so a caller can file a report *as* someone
	#    else — their handle next to words they never wrote. The route still reads the token, so only
	#    the model test catches this; that is why the model field is asserted directly.
	('the reporter is a request field again', FV,
	 "	model_config = MODEL_CONFIG\n	text: str = Field(min_length=1, max_length=280)\n\n\nclass FacilityReport(BaseModel):",
	 "	model_config = MODEL_CONFIG\n	text: str = Field(min_length=1, max_length=280)\n	reporter_ref: str | None = None\n\n\nclass FacilityReport(BaseModel):",
	 'test_a_caller_cannot_attribute_a_report_to_someone_else'),

	# 8. The service stops consulting the identity model, so a named reporter is published
	#    anonymously. That is the safe direction and it is still a defect: §SEC-004's feature is
	#    absent, and the feed cannot show that two reports came from one person.
	('the service never derives a handle', FS,
	 "		if reporter_ref and self._identity is not None:",
	 "		if False:",
	 'test_the_report_feed_publishes_a_handle_not_the_subject_reference'),

	# 9. The caveat is dropped from the note, so the screen promises more than the handle delivers.
	('the note loses the caveat', ST,
	 "		'caveat': 'A name like this hides your details, but if only a few people are reporting from the same place at the same time, someone may still work out who you are. Do not put anything in a public report you would not want read back to you.',",
	 "		'caveat': '',",
	 'test_the_caveat_is_served_rather_than_paraphrased'),

	# 10. The note reads the same for a derived and a chosen handle, so a person cannot tell whether
	#     the name they are seeing is one they picked or one that will change under them.
	('a chosen handle is described as derived', ST,
	 "	if chosen:\n		return table['chosen']",
	 "	if False:\n		return table['chosen']",
	 'test_the_note_says_which_kind_of_handle_this_is'),

	# 11. The route names a subject, which is the IDOR shape: any caller can ask what a given subject
	#     is called, undoing the unlinkability the handle exists to provide.
	('the route takes a subject it must not take', G,
	 "	async def identity_pseudonym(_subject: str = Depends(require_self(names_subject=False)),\n	                             lang: str = 'en') -> dict[str, object]:",
	 "	async def identity_pseudonym(subject: str = Depends(require_self()),\n	                             lang: str = 'en') -> dict[str, object]:",
	 'test_the_route_has_no_parameter_a_caller_can_name_a_stranger_with'),

	# 12. The catalogue stops offering the choice, so the setting is unreachable from every client —
	#     the `missing` row again, with the code behind it.
	('the catalogue drops the profile actions', M,
	 "		_a('my_pseudonym', 'What name do others see?', 'Privacy', 'GET', '/identity/pseudonym', [_f('lang', 'Which language?', 'select', TRAVELLER_LANGS)]),\n		_a('choose_pseudonym', 'Choose the name others see', 'Privacy', 'POST', '/identity/pseudonym', [_f('handle', 'Your name on shared screens', ph='e.g. Tembo-a1b2')]),",
	 "",
	 'test_the_catalogue_offers_the_profile_and_reaches_the_routes'),

	# 13. The model's pattern admits a bare digit string, so a phone number is a legal handle by
	#     shape — the service's own refusal is the second line of defence and this removes the first.
	#     Named against the *model* test rather than the route test: the route catches the same input
	#     one frame later through the service's assertion, so a route-level node passes either way and
	#     this canary MISSED there. The anchor names the `PseudonymChoice` field specifically — the
	#     same pattern appears twice in the file, so a shorter target is not unique.
	('the handle pattern admits an identifier', IV,
	 "	handle: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9 _-]{1,23}$')\n\n\nclass CaseReportRef",
	 "	handle: str = Field(min_length=1, max_length=64)\n\n\nclass CaseReportRef",
	 'test_the_model_refuses_a_handle_shaped_like_a_number'),
	# 14. The route serves the handle and drops the caveat. This is the *first cut of this unit* —
	#     the sentence was in the string table and no route read it — and it is the same absent-join
	#     defect the handle exists to close, one level up. A live probe found it; the table-only test
	#     did not, which is why the node named here asserts the served field.
	('the route drops the caveat', G,
	 "		        'caveat': pseudonym_caveat(lang)}",
	 "		        'caveat': ''}",
	 'test_the_route_serves_the_callers_own_handle'),
]


def _node(canary_node: str) -> str:
	return canary_node if '/' in canary_node else f'tests/ci/test_sec004.py::{canary_node}'


_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only',
	'tests/ci/test_sec004.py'],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_sec004.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	# See the module docstring: a same-second write of the same size reuses the previous canary's
	# bytecode, and the canary then tests code it never mutated. Purged for the file just written.
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', _node(node)],
			cwd=ROOT, capture_output=True, text=True)
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
