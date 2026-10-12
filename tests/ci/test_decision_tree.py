"""§INF-002's six Entry questions and its Output, as served.

The section prints six ways in and an Output that is "specific, actionable guidance with facility
and hotline links". What existed was one root — "Do you have fever (≥38.0 °C)?" — and one sentence
per leaf. Those are two different products. The root asks the reader to measure a temperature before
they can be helped, and a sentence naming 719 is a number they have to retype from text §ACC-001 is
reading aloud. Both are §6.2.10 failures in a tree built for low-literacy use.

These tests read the spec for the six entries rather than restating them, so a spec revision that
changes an entry fails here instead of silently leaving the menu serving the old six.
"""
from pathlib import Path

import httpx

from afya.info.service import ENTRY_ANSWERS, InfoService, LEAF_LINKS
from afya.info.views import EntryAnswer
from afya.service import build_services, create_app

SPEC = Path(__file__).resolve().parents[2] / 'docs' / 'spec.md'


def _spec_section(heading: str) -> str:
	text = SPEC.read_text(encoding='utf-8')
	return text.split(heading, 1)[1].split('\n#### ', 1)[0]


def _entry_questions() -> list[str]:
	"""§INF-002's Entry questions, read off the section rather than transcribed here."""
	section = _spec_section('### INF-002')
	start = section.index('**Entry questions:**')
	out: list[str] = []
	for line in section[start:].splitlines()[1:]:
		if not line.startswith('- '):
			break
		out.append(line[2:].strip())
	return out


def test_the_six_entries_are_the_sections_own_and_all_are_served() -> None:
	"""The gate. Six entries in the spec, six served, the same six in the same order."""
	printed = _entry_questions()
	assert len(printed) == 6, f'the section prints six entry questions, found {printed}'
	assert [e.question for e in ENTRY_ANSWERS] == printed, (
		f'the served entries are not the section\'s: served={[e.question for e in ENTRY_ANSWERS]}, '
		f'printed={printed}'
	)
	served = InfoService().entry_answers()
	assert [e.question for e in served] == printed


def _served_paths() -> set[str]:
	"""Every path the running app serves, by walking the nested router tree.

	`app.routes` is nested — every `include_router` is an `_IncludedRouter` whose paths live on
	`original_router.routes` under `include_context.prefix` — so a flat walk sees a handful of
	entries and reports a live route as missing.
	"""
	app = create_app(build_services())
	leaves: list[object] = []

	def walk(routes: object) -> None:
		for r in routes:  # type: ignore[attr-defined]
			if hasattr(r, 'routes'):
				walk(r.routes)
				continue
			leaves.append(r)

	walk(app.routes)
	return {getattr(r, 'path', '') for r in leaves}


def _unreachable(entries: tuple[EntryAnswer, ...], paths: set[str]) -> list[str]:
	"""The gate's comparison, over whatever entries it is handed — so the canary runs this, not a copy."""
	return [
		e.href for e in entries
		if e.kind != 'call' and e.href.split('?', 1)[0] not in paths
	]


def test_every_entry_opens_something_that_exists() -> None:
	"""A door that does not open is worse than no door.

	`href` is a path or a device scheme, and `kind` says which. A `screen` or `tree` entry must name
	a path the app actually serves — checked against the running app's own route table, because an
	inventory read from the source is not an inventory of what the app serves. `call` must be a
	scheme the device handles, which is not a route and is asserted as such rather than skipped.
	"""
	paths = _served_paths()
	assert _unreachable(ENTRY_ANSWERS, paths) == [], (
		f'entry questions open paths the app does not serve: {_unreachable(ENTRY_ANSWERS, paths)}'
	)
	for e in ENTRY_ANSWERS:
		if e.kind == 'call':
			assert e.href.startswith('tel:'), f'{e.question} calls {e.href}, which is not a tel: URI'
			continue
		assert e.kind in ('tree', 'screen'), e.kind


def test_an_entry_that_needs_input_names_it() -> None:
	"""An entry that opens a screen needing arguments and does not say so is a 422 the reader sees.

	The travel advisory needs a destination and an origin; the facility search needs a position. The
	tree entries need nothing — the walk asks. Two directions, because either alone is a lie: every
	parameter the route *requires* must be declared (or the client opens a door that refuses), and
	every declared input must be a real parameter (or the client prompts for something the route
	ignores). An optional filter the entry merely wants to pass is declared and not required, which
	is why the comparison is not equality.
	"""
	import inspect

	app = create_app(build_services())
	by_path: dict[str, object] = {}
	leaves: list[object] = []

	def walk(routes: object) -> None:
		for r in routes:  # type: ignore[attr-defined]
			if hasattr(r, 'routes'):
				walk(r.routes)
				continue
			leaves.append(r)

	walk(app.routes)
	for r in leaves:
		by_path.setdefault(getattr(r, 'path', ''), r)
	for e in ENTRY_ANSWERS:
		if e.kind != 'screen':
			assert e.asks_for == [], f'{e.question} is a {e.kind} entry and asks for nothing'
			continue
		route = by_path[e.href.split('?', 1)[0]]
		sig = inspect.signature(route.endpoint)  # type: ignore[attr-defined]
		required = {
			name for name, p in sig.parameters.items()
			if p.default is inspect.Parameter.empty and name not in ('self',)
		}
		known = {name for name in sig.parameters if name != 'self'}
		assert required <= set(e.asks_for), (
			f'{e.question} opens {e.href}: the route requires {sorted(required)} and the entry '
			f'declares {sorted(e.asks_for)}, so the client opens it without them'
		)
		assert set(e.asks_for) <= known, (
			f'{e.question} declares {sorted(set(e.asks_for) - known)}, which {e.href} does not take'
		)


def test_every_leaf_carries_the_links_the_output_names() -> None:
	"""§INF-002's Output: "facility and hotline links". One leaf is deliberately empty."""
	svc = InfoService()
	leaves = {k for k, v in svc.TREE.items() if v.leaf_recommendation}
	assert set(LEAF_LINKS) == leaves, (
		f'a leaf with no link row is a recommendation with nowhere to go: '
		f'{sorted(leaves - set(LEAF_LINKS))}'
	)
	for node_id in leaves:
		links = LEAF_LINKS[node_id]
		if node_id == 'leaf_ok':
			# "No action needed" is the answer; a facility button under it sends someone who needs
			# nothing to a clinic.
			assert links == (), 'leaf_ok must offer nothing'
			continue
		assert links, f'{node_id} recommends an action and offers nowhere to take it'
		kinds = {link.kind for link in links}
		assert 'find_facility' in kinds, f'{node_id} has no facility link, which the Output names'
		for link in links:
			assert link.href, f'{node_id}: {link.label} has nowhere to go'


def test_a_question_step_offers_no_way_out() -> None:
	"""Links belong to the leaf. A facility button under an unanswered question is a reader leaving
	the walk before it has said anything."""
	svc = InfoService()
	step = svc.step([])
	assert step.done is False and step.links == [] and step.recommendation is None
	assert step.question == svc.TREE['root'].question


def test_the_household_entry_is_a_second_root_and_not_a_branch() -> None:
	"""The section's second Entry asks about a different person.

	Routing "someone in my house is sick" through the fever tree is the defect: the caller answers
	"no" to "do you have fever" — they do not — and is told no action is needed, while the person in
	their house is the one who is unwell. The household walk asks about the sick person and reaches
	a different pair of leaves.
	"""
	svc = InfoService()
	household = svc.step([], 'household')
	assert household.done is False
	assert 'sick person' in (household.question or ''), household.question
	# Contact risk: isolate and call, with both links.
	risk = svc.step([True], 'household')
	assert risk.done is True and '719' in (risk.recommendation or '')
	assert {link.kind for link in risk.links} == {'call', 'find_facility'}
	# No contact risk: home care, and the facility link without the call.
	care = svc.step([False], 'household')
	assert care.done is True
	assert {link.kind for link in care.links} == {'find_facility'}, (
		'a household caring for a feverish person at home needs the clinic in two days, not an '
		'ambulance today — the call belongs to the leaf where the answer is the call'
	)
	# And the two roots reach different leaves: the fever root's four are not the household's two.
	fever_leaves = {svc.step([a, b]).recommendation for a in (True, False) for b in (True, False)}
	household_leaves = {svc.step([a], 'household').recommendation for a in (True, False)}
	assert fever_leaves & household_leaves == set(), (
		f'a leaf shared between the two roots is a leaf that answers one question with the other: '
		f'{fever_leaves & household_leaves}'
	)
	assert len(fever_leaves) == 4 and len(household_leaves) == 2


def test_an_unknown_entry_is_refused_rather_than_defaulted() -> None:
	"""An entry name nothing defines must fail, not fall back to the fever root — a silent fallback
	answers a household question with the caller's own temperature."""
	svc = InfoService()
	try:
		svc.step([], 'no_such_entry')
	except AssertionError as exc:
		assert 'unknown entry node' in str(exc)
	else:
		raise AssertionError('an unknown entry was accepted')


async def test_the_served_entries_and_the_household_walk() -> None:
	"""The two routes as a client reaches them."""
	app = create_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		entries = (await c.get('/info/entry-answers')).json()
		assert len(entries) == 6
		assert [e['question'] for e in entries] == _entry_questions()
		household = (await c.get('/info/decision-tree?entry=household')).json()
		assert household['done'] is False and 'sick person' in household['question']
		leaf = (await c.get('/info/decision-tree?entry=household&answers=yes')).json()
		assert leaf['done'] is True
		assert {link['kind'] for link in leaf['links']} == {'call', 'find_facility'}
		# An entry nothing defines is a 422, not the fever root.
		assert (await c.get('/info/decision-tree?entry=nope')).status_code == 422
		# And the tag filter the fourth and fifth entries open.
		myths = (await c.get('/info/library?tag=mythbusting')).json()
		assert myths and all(m['harmony_tag'] == 'mythbusting' for m in myths)


def test_the_gate_catches_an_entry_pointing_nowhere() -> None:
	"""Canary. Point an entry at a path no route serves and the reachability gate must fail.

	The canary runs the gate's own `_unreachable` comparison rather than restating it: asserting
	only that the patched href is absent from the route table would prove the fixture and not the
	gate, which is the canary that passes for the wrong reason. The target is asserted present and
	unique before the patch, so a patch that does not apply cannot read as a gate that did not fire.
	"""
	paths = _served_paths()
	assert _unreachable(ENTRY_ANSWERS, paths) == [], 'the real table must be reachable first'
	target = ENTRY_ANSWERS[2]
	assert target.href == '/location/travel-advisory', f'canary target moved: {target.href}'
	assert sum(1 for e in ENTRY_ANSWERS if e.href == target.href) == 1, 'canary target not unique'
	patched = tuple(
		e.model_copy(update={'href': '/location/no-such-route'}) if e is target else e
		for e in ENTRY_ANSWERS
	)
	assert _unreachable(patched, paths) == ['/location/no-such-route'], (
		'the gate is blind to an entry pointing at a path the app does not serve'
	)

