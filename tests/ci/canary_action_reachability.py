"""Canaries for tests/ci/test_action_reachability.py — each gate pointed at a planted defect and watched to fail.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script.

Each mutation is **disjoint** from what its predicate looks for: the first three move a field to a
place no client writes to rather than renaming it, because a name-only comparison would let a
renamed-but-still-query field through. The fourth plants an open map, which the gate's comparison
is blind to by construction — that is the reason the open-map check is separate, and it must fail
when the map is planted.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
SVC = ROOT / 'src/afya/service.py'
ACT = ROOT / 'src/afya/mobile/actions.py'

GATE = 'tests/ci/test_action_reachability.py'

CANARIES = [
	# 1. A scalar body field goes back to a plain parameter, which FastAPI reads from the *query
	#    string* — and both clients send no query string on a write. The value the catalogue offers
	#    becomes one no form can deliver, which is the defect class this gate exists for.
	('a write field moves back to the query string', SVC,
	 "	async def facility_wait(facility_id: str, minutes: int = Body(..., embed=True)) -> dict[str, int]:",
	 "	async def facility_wait(facility_id: str, minutes: int) -> dict[str, int]:",
	 'test_every_field_a_form_offers_is_one_the_route_accepts'),

	# 2. The same, on a route whose body is a bare list: `embed=True` is what makes the list a named
	#    property instead of the whole body, and dropping it makes `signs` unreadable.
	('a list body field loses its name', SVC,
	 "	async def maternal_danger(signs: list[str] = Body(..., embed=True)) -> dict[str, object]:",
	 "	async def maternal_danger(signs: list[str] = Body(...)) -> dict[str, object]:",
	 'test_every_field_a_form_offers_is_one_the_route_accepts'),

	# 3. A composed body loses its extra field, so the model's own properties are all the route
	#    takes and the catalogue's control for it has nowhere to go.
	('a composed body drops a field', SVC,
	 "	async def environment_water(w: WaterAdvisoryRequest) -> dict[str, object]:",
	 "	async def environment_water(w: WaterQuality) -> dict[str, object]:",
	 'test_every_field_a_form_offers_is_one_the_route_accepts'),

	# 4. An open map returns to a route the catalogue reaches. `dict[str, str]` accepts any key, so
	#    the comparison above is blind to it — which is exactly why the separate check must fail.
	('a route takes an open map body again', SVC,
	 "	async def women_referral(body: ReproductiveReferralRequest, _subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:",
	 "	async def women_referral(body: dict[str, str], _subject: str = Depends(require_self(names_subject=False))) -> dict[str, object]:",
	 'test_a_write_route_takes_no_open_map_body'),

	# 5. A catalogue action offers a field the route genuinely never reads — not one spelled
	#    differently. This is the mutation the gate's own synthetic canary cannot make, because that
	#    one is driven against a fake action and proves the comparison rather than the wiring.
	('the catalogue offers a field the route does not read', ACT,
	 "		_a('request_activation', 'Ask us to switch this on for me', 'Outbreak', 'POST', '/tier4/activation/request', [_f('county', 'Where you are', ph='optional')]),",
	 "		_a('request_activation', 'Ask us to switch this on for me', 'Outbreak', 'POST', '/tier4/activation/request', [_f('county', 'Where you are', ph='optional'), _f('nowhere_to_go', 'Nowhere')]),",
	 'test_every_field_a_form_offers_is_one_the_route_accepts'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_reach.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', f'{GATE}::{node}'],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
	print(f'{"CAUGHT " if caught else "MISSED "} {name}')
	if not caught:
		failures.append(name)
		print(proc.stdout[-1200:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
