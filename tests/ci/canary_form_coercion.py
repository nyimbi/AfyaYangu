"""Canaries for the four routes whose bodies had to learn the shape their own control sends.

Each defect in this file was the same sentence wearing four hats: **the catalogue draws a control
whose value the route refuses.** A generic form draws one text box per field; both shipped clients
send a `list` field as an array of strings (`ActionsActivity.typed`, `Endpoints.jsonValue`) and a
`select` as the option's own text. A route typed `list[SomeModel]`, `dict[str, int]`, or a matcher
keyed on slugs while the spinner offers labels, therefore 422s on the value its own form produced.

The mutations are chosen so each is **disjoint** from what its predicate looks at:

* **#1** puts the `member_ref` takeover back — the guard waives the taken-reference check again.
  Aimed at the IDOR test, because that is the consequence: a stranger re-enrols a member another
  wallet holds and the original guardian loses the record. It is a *removal of a check*, not a
  renamed one, so nothing about names can hide it.
* **#2** moves the `purge_expired` parse back outside the `try`. Aimed at the 422 test: the
  `ValueError` escapes the handler and the route answers a typo with a 500. The parse still
  *works* for a well-formed string, so the success-path test stays green — which is exactly why
  the refusal test has to exist.
* **#3** drops the label→slug bridge, so the spinner's own text matches no axis. Aimed at the
  front-door test: the label and the slug stop producing the same flag set, and the catalogue's
  own option becomes a control that silently selects nothing.
* **#4** removes the `try` around the `early_warning` parse, so a mistyped signal name escapes as
  a `ValidationError` and the route 500s instead of naming the six signals it accepts.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script. The
`__pycache__` purge after each write is load-bearing for the reason `canary_inf001.py` documents:
two canaries mutating two files with same-length edits in the same second make CPython reuse the
previous canary's bytecode, and the gate then reports a mutation it never made.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
G = ROOT / 'src/afya/service.py'
C = ROOT / 'src/afya/medicine/contraindications.py'
V = ROOT / 'src/afya/community/views.py'

CANARIES = [
	# 1. `may_create` waives the ownership check *and* the taken-reference one again. The enrolment
	#    map is keyed by the reference, so a create naming a reference another wallet holds re-enrols
	#    that member under the caller's guardianship.
	('the member-ref takeover is allowed again', G,
	 "				if named and str(named) in records.member_refs() and not records.owns(subject, str(named)):\n					raise HTTPException(status_code=403, detail='that reference belongs to another wallet')",
	 "				if False:\n					raise HTTPException(status_code=403, detail='unreachable')",
	 'tests/ci/test_self_scope.py::test_a_stranger_cannot_re_enrol_a_member_reference_that_is_already_taken'),

	# 2. The `purge_expired` parse moves back outside the `try`, so `int('soon')` escapes the handler.
	#    The success path is untouched — the age is still read as the number it names — so only the
	#    refusal test can see it.
	('a bad age escapes the purge handler', G,
	 "		try:\n			ages: dict[str, int] = {}\n			for pair in age_days:",
	 "		ages: dict[str, int] = {}\n		if True:\n			for pair in age_days:",
	 'tests/ci/test_retention.py::test_the_purge_route_refuses_an_age_that_is_not_a_number'),

	# 3. The label→slug bridge is dropped, so the catalogue's own option text selects nothing. The
	#    slug path still works, which is why the test asserts the two spellings against *each other*
	#    rather than only that a flag exists.
	('the condition label stops resolving to its axis', C,
	 "	return CONDITION_SLUGS.get(key)",
	 "	return None",
	 'tests/ci/test_med002.py::test_the_catalogue_offers_condition_labels_and_the_route_reads_them'),

	# 4. The `early_warning` parse loses its `try`, so a signal name outside §11.7's six escapes as a
	#    `ValidationError` and the route answers a typo with a 500 rather than a 422 naming the shape.
	('a bad signal name escapes the warning handler', G,
	 "		parsed: list[WarningSignal] = []\n		try:\n			for spec in signals:",
	 "		parsed: list[WarningSignal] = []\n		if True:\n			for spec in signals:",
	 'tests/ci/test_ai003.py::test_the_warning_route_refuses_a_signal_name_outside_the_six'),

	# 5. The contact-list coercion keeps the object branch and drops the string one, so the value a
	#    client's single text box produces is refused. This is the mutation the object-form assertion
	#    cannot see — the hand-built request still works — which is why the test drives the *strings*
	#    the control actually sends.
	('the contact list stops accepting typed strings', V,
	 "		entries = raw.split(',') if isinstance(raw, str) else (raw if isinstance(raw, list) else [raw])\n		if not any(isinstance(e, str) for e in entries):\n			return data",
	 "		entries = raw if isinstance(raw, list) else [raw]\n		if True:\n			return data",
	 'tests/ci/test_community.py::test_the_contacts_route_reads_the_typed_entries_the_form_sends'),

	# 6. The comma split goes back to replacing only the first comma, which is the shipped defect:
	#    `Jane:market, the tailor:work` files the tailor as part of Jane's setting, so two people
	#    become one and the tracing summary counts a setting nobody named. Aimed at the same test,
	#    whose `by_setting` assertion is the consequence rather than the parse.
	('the contact split swallows the second person', V,
	 "		entries = raw.split(',') if isinstance(raw, str) else (raw if isinstance(raw, list) else [raw])\n		if not any(isinstance(e, str) for e in entries):",
	 "		entries = [raw] if isinstance(raw, str) else (raw if isinstance(raw, list) else [raw])\n		if not any(isinstance(e, str) for e in entries):",
	 'tests/ci/test_community.py::test_the_contacts_route_reads_the_typed_entries_the_form_sends'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_coercion.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', node],
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
