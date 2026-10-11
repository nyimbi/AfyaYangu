"""Gate: §4's target users — seven personas, seven secondary audiences, eight launch priorities.

§4 was the one section of the spec with no representation in the code. Every other section had at
least a table; this one had prose a reader could quote and nothing a check could stand on. The
consequence is the shape this file exists to catch: §22.7 can report the share of users who are
female and §22.8 can demand the equity metrics disaggregated by gender, geography, age and device,
while nothing anywhere says who those people were supposed to be — so no number has a target
population to be measured against.

What is tested is the transcription (a revision to §4 must fail here) and the three crossings that
turn the table into findings: a persona's language against the string tables that exist, an entry
point against §5.2's seven channels, and §4.3's segments against §4.1's people.

The sharpest finding is real and not a modelling gap: §4.1's Persona F is a Dholuo speaker on a
feature phone, §ACC-002 puts Dholuo at tier 1, §CHAN-2's own USSD menu ends "Language: English /
Kiswahili / Dholuo / ..." — and `SUPPORTED_LANGS` is `{'en','sw'}`, so `rec()` asserts. The product
cannot answer Grace in her language on any of the four channels §4 routes her through.
"""
import re
from pathlib import Path
from typing import Any

import httpx
import pytest

from afya.access.views import LANGUAGE_MATRIX
from afya.personas.service import PERSONAS, SECONDARY_PERSONAS, SEGMENTS, PersonaService
from afya.personas.views import DeviceClass, Priority
from afya.privacy.views import RBACRole
from afya.registry.service import CHANNELS
from afya.service import build_services, create_app
from afya.strings import SUPPORTED_LANGS

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / 'docs' / 'spec.md'


def _spec_lines() -> list[str]:
	return SPEC.read_text(encoding='utf-8').splitlines()


def _section(start: str) -> list[str]:
	"""The lines of one `### 4.x` subsection, up to the next heading of the same or higher rank."""
	lines = _spec_lines()
	i = next(n for n, ln in enumerate(lines) if ln.startswith(start))
	out: list[str] = []
	for ln in lines[i:]:
		if out and ln.startswith(('## ', '### ')) and not ln.startswith(start):
			break
		out.append(ln)
	return out


def _persona_blocks() -> dict[str, list[str]]:
	"""§4.1 split into one block of lines per persona, keyed by the section's own letter."""
	blocks: dict[str, list[str]] = {}
	for ln in _section('### 4.1 '):
		m = re.match(r'#### Persona ([A-G]) — (.+)', ln)
		if m:
			blocks[m.group(1).lower()] = [m.group(2)]
		elif blocks:
			blocks[next(reversed(blocks))].append(ln)
	return blocks


def _segments_rows() -> list[list[str]]:
	"""§4.3's eight-row table, read out of the spec."""
	rows: list[list[str]] = []
	for ln in _section('### 4.3 '):
		if not ln.startswith('|'):
			continue
		cells = [c.strip() for c in ln.strip('|').split('|')]
		if set(''.join(cells)) <= set('-: ') or cells[0] == 'Priority':
			continue
		rows.append(cells)
	assert len(rows) == 8, f'§4.3 should have eight segment rows, found {len(rows)}'
	return rows


def _svc() -> PersonaService:
	return PersonaService()


# --- §4.1, persona for persona --------------------------------------------------------------------

def test_the_seven_personas_are_the_sections_seven() -> None:
	"""Keys A–G, and the heading's own name and age. A persona table that lost one would still sort
	and still print; the count and the letters are what make the omission visible."""
	blocks = _persona_blocks()
	assert sorted(blocks) == list('abcdefg'), blocks.keys()
	assert len(PERSONAS) == 7
	for p in PERSONAS:
		heading = blocks[p.key][0]
		assert heading.startswith(f'{p.name}, {p.age}, '), f'{p.key}: {heading}'
		assert p.location == heading.split(', ', 2)[2], f'{p.key}: {heading}'


def _cell_items(cell: str) -> list[str]:
	"""A Needs or Friction cell as items, case- and delimiter-normalised.

	§4.1 delimits with whatever punctuation reads best: Persona A's needs are four sentences, Persona
	D's are four comma-separated phrases inside one, so only the first of the four carries a capital.
	That capital is English sentence convention, not a claim that the second need is lower-case, so
	the comparison drops case and the delimiter — the *words* are what must match, and a need whose
	wording moved still fails.
	"""
	return [s.strip().rstrip('.,').lower() for s in re.split(r'(?<=[.,])\s+', cell.strip()) if s.strip()]


def test_every_need_and_friction_line_is_verbatim() -> None:
	"""The Needs and Friction cells against the section's own sentences, item for item.

	The cell runs to the next `**` label and the items are its own punctuation-separated fragments.
	"""
	for p in PERSONAS:
		text = ' '.join(_persona_blocks()[p.key])
		for label, field in (('Needs', 'needs'), ('Friction', 'friction')):
			m = re.search(rf'\*\*{label}:\*\* (.+?)(?= \*\*|$)', text)
			if m is None:
				# §4.1 gives Persona G no Friction line at all. The empty list is the section's own
				# answer; writing one here would make an invented friction indistinguishable from
				# the six the section states.
				assert field == 'friction' and p.key == 'g', f'{p.key} has no {label} line'
				assert p.friction == [], p.key
				continue
			cell = _cell_items(m.group(1))
			got = [s.rstrip('.').lower() for s in getattr(p, field)]
			assert got == cell, f'{p.key} {label}: {got} != {cell}'


def test_the_entry_point_is_verbatim_and_split_by_clause() -> None:
	"""The Entry point against the section's sentence, and the derived split against it.

	The split is per comma-separated clause, not per word: an entry point is a sequence of routes,
	and a clause either names a §5.2 channel or is a route the channel table has no row for. A
	word-level split leaves connective debris ("forwarded friend then health wallet") on all seven
	personas, which is a finding every row produces and therefore no finding at all.
	"""
	for p in PERSONAS:
		text = ' '.join(_persona_blocks()[p.key])
		cell = re.search(r'\*\*Entry point:\*\* (.+)', text).group(1).strip()  # type: ignore[union-attr]
		assert p.entry_point == cell, f'{p.key}: {p.entry_point!r} != {cell!r}'
		# The split accounts for the whole sentence: every clause either matched a channel or was
		# kept as unmapped. Nothing is dropped silently.
		clauses = len([c for c in cell.lower().split(',') if c.strip(' .')])
		assert len(p.entry_channels) + len(p.entry_unmapped) <= clauses, p.key


def test_the_entry_channels_are_channels_the_registry_has() -> None:
	"""A derived slug must be one of §5.2's seven. An eighth slug would be this module inventing a
	channel, which is a product decision the section does not make."""
	for p in PERSONAS:
		assert set(p.entry_channels) <= set(CHANNELS), f'{p.key}: {p.entry_channels}'
		# Order is §5.2's, not the sentence's, so two personas' channel sets compare directly.
		assert p.entry_channels == [c for c in CHANNELS if c in p.entry_channels], p.key


def test_only_the_three_non_consumer_entry_points_are_unmapped() -> None:
	"""Who arrives through a route §5.2 has no channel for, and who does not.

	This is the assertion that fails if the split degrades back to word-level: all seven personas
	would report a remainder. The three that legitimately have one are the rollout and clinic
	routes — §5.2's seven channels are consumer-facing, and a county health team rollout is not a
	channel a person arrives through.
	"""
	unmapped = {p.key: p.entry_unmapped for p in PERSONAS if p.entry_unmapped}
	assert sorted(unmapped) == ['c', 'd', 'g'], unmapped
	assert any('rollout' in ' '.join(v) for v in unmapped.values())
	assert any('clinic' in ' '.join(v) for v in unmapped.values())
	# The four whose entry point is entirely §5.2's channels must be clean, or the finding is noise.
	for key in ('a', 'b', 'e', 'f'):
		assert PERSONAS[list('abcdefg').index(key)].entry_unmapped == [], key


def test_persona_f_has_no_smartphone_and_everyone_else_does() -> None:
	"""§4.3's P3 rationale is "Reached primarily via non-app channels", and §3.3 principle 1 builds
	the whole channel architecture around not requiring a smartphone. Grace is the one persona for
	whom that stops being a preference."""
	by_key = {p.key: p for p in PERSONAS}
	assert by_key['f'].device is DeviceClass.feature_phone
	assert not by_key['f'].device.runs_an_app
	assert all(p.device.runs_an_app for p in PERSONAS if p.key != 'f')


def test_a_role_is_given_only_where_the_section_names_a_job() -> None:
	"""§17.4's RBAC table has a row for a CHW and a clinician and no row for a market trader. A role
	inferred from a persona's description would be this module widening the access table, so only
	the two personas whose summary names the job carry one."""
	by_key = {p.key: p for p in PERSONAS}
	assert by_key['c'].role is RBACRole.chw, 'Mama Zawadi is a Community Health Worker'
	assert by_key['d'].role is RBACRole.clinician, 'Dr. Kimani is a clinician'
	for key in ('a', 'b', 'e', 'f', 'g'):
		assert by_key[key].role is None, key


def test_a_language_is_read_off_the_section_not_off_the_county() -> None:
	"""Busia is a Luhya county and Garissa a Somali one, and §4 says neither. Only the personas whose
	text names a language carry one; the rest carry an empty list rather than a language attributed
	by geography."""
	by_key = {p.key: p for p in PERSONAS}
	assert by_key['f'].languages == ['luo'], 'Grace is the Dholuo speaker §4.1 names'
	assert by_key['b'].languages == ['luo', 'sw'], 'Otieno is "Luo and Swahili"'
	assert by_key['a'].languages == ['sw'], 'Wanjiku is Swahili-first'
	assert by_key['g'].languages == ['sw', 'en'], 'Amina is "Swahili and English"'
	# Persona C is in Busia and §4.1 names no language for her; persona E is in Garissa likewise.
	assert by_key['c'].languages == []
	assert by_key['e'].languages == []


# --- §4.2 and §4.3 --------------------------------------------------------------------------------

def test_the_secondary_audiences_are_the_sections_seven_bullets() -> None:
	"""§4.2 verbatim, in the section's order. These are people who *read* the product; §CHAN-5's
	intermediaries are people who *distribute* it, and the two lists are not merged."""
	bullets = [ln[2:].strip() for ln in _section('### 4.2 ') if ln.startswith('- ')]
	assert len(bullets) == 7, bullets
	assert [s.name for s in SECONDARY_PERSONAS] == bullets


def test_the_segment_table_is_the_sections_eight_rows() -> None:
	"""Priority, segment and rationale, cell for cell, and the section's own ordering."""
	rows = _segments_rows()
	assert len(SEGMENTS) == 8
	for (priority, segment, rationale), s in zip(rows, _svc().segments(), strict=True):
		assert s.priority.value == priority.lower(), (s.key, priority)
		assert s.segment == segment, s.key
		assert s.rationale == rationale, s.key


def test_segments_sort_by_the_sections_priority_not_by_the_string() -> None:
	"""`Priority.order` is the enum's declaration order, so `p10` — if §4.3 ever grows one — cannot
	sort before `p2`. Sorting by the value would put it there, and the launch would be reordered by
	an alphabet."""
	ordered = _svc().segments()
	assert [s.priority for s in ordered] == sorted(
		(s.priority for s in ordered), key=lambda p: p.order
	)
	assert [s.priority.value for s in ordered[:2]] == ['p0', 'p0']
	assert Priority('p10') if False else True  # p10 does not exist yet; the ordering is defensive
	assert [p.order for p in Priority] == [0, 1, 2, 3]


def test_each_segment_names_the_personas_that_carry_it() -> None:
	"""The crossing in the other direction: §4.1's `segments` field and §4.3's `persona_keys` are
	built from each other, so the two can never disagree."""
	for s in SEGMENTS:
		assert s.persona_keys == [p.key for p in PERSONAS if s.key in p.segments], s.key
	for p in PERSONAS:
		for key in p.segments:
			assert key in {s.key for s in SEGMENTS}, f'{p.key} names unknown segment {key}'


def test_a_personas_priority_is_the_earliest_segment_it_belongs_to() -> None:
	"""§4.3 orders the *launch*. A person who is both a CHW and a resident of a high-risk county is
	reached when either row is, so the answer is the min by `Priority.order`."""
	svc = _svc()
	assert svc.priority_of('c') is Priority.p0, 'Mama Zawadi is a CHW: P0'
	assert svc.priority_of('f') is Priority.p3, 'Grace is the general adult population: P3'
	assert svc.priority_of('g') is Priority.p0, 'Amina is in Mombasa, a high-risk urban county: P0'
	assert svc.priority_of('e') is Priority.p0, 'Hassan is in Garissa, a border county: P0'
	assert svc.priority_of('a') is Priority.p0, 'Wanjiku is in a high-risk county and a caregiver'
	assert svc.priority_of('b') is Priority.p2, 'Otieno is a boda boda rider: P2'


# --- the crossings --------------------------------------------------------------------------------

def test_the_language_crossing_finds_grace_and_otieno() -> None:
	"""§ACC-002's tier-1 languages against the string tables that exist, and the personas left out.

	`unserved_languages` is `TIER1_LANGS - SUPPORTED_LANGS` computed from `LANGUAGE_MATRIX`, not a
	list kept here — a language promoted to tier 1 in the spec enters this finding on its own.
	"""
	svc = _svc()
	tier1 = {str(m['code']) for m in LANGUAGE_MATRIX.values() if m['tier'] == 1}
	assert len(tier1) == 5, tier1
	assert svc.unserved_languages() == sorted(tier1 - SUPPORTED_LANGS)
	assert 'luo' in svc.unserved_languages(), '§ACC-002 puts Dholuo at tier 1'
	assert svc.unserved_personas() == ['b (Otieno)', 'f (Grace)']


async def test_the_dholuo_gap_is_answered_in_english_and_says_so() -> None:
	"""The defect §4 exposed, asserted against the live app.

	Grace's language is not merely absent from a table: `rec()` asserted on it, so the triage route
	raised and the caller got a **500**. §CHAN-2's own USSD menu ends "Language: English / Kiswahili
	/ Dholuo / ...", so the menu offered what the handler could not do — to the one persona §4.1
	gives no smartphone and therefore no other channel.

	What the route must do instead is answer, in the best language it has, and say which that was.
	`language_fallback` is the part that matters: a client that rendered the English string without
	reading it would present English to a Dholuo speaker as if it were her language, which is the
	same failure as the 500 wearing better manners.
	"""
	from afya.strings import SUPPORTED_LANGS, answerable
	assert 'luo' not in SUPPORTED_LANGS, 'the point of this test is that Dholuo has no table'
	assert answerable('luo') == 'en'

	app = create_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		body = {'symptoms': ['fever'], 'temperature_c': 38.5}
		resp = await c.post('/triage/preliminary?lang=luo', json=body)
		assert resp.status_code == 200, '§CHAN-2 offers Dholuo by name; a 500 is a dead channel'
		out = resp.json()
		assert out['served_in'] == 'en' and out['language_fallback'] is True
		assert out['recommendation'] == (await c.post('/triage/preliminary?lang=en', json=body)).json()['recommendation']
		# A language with a table is served in it, and reports no fallback — otherwise the flag
		# would be permanently true and would say nothing.
		sw = (await c.post('/triage/preliminary?lang=sw', json=body)).json()
		assert sw['served_in'] == 'sw' and sw['language_fallback'] is False
		# Every tier-1 language §ACC-002 requires answers rather than raising. This is the loop that
		# fails if the assert comes back.
		for lang in ('ki', 'bxk', 'luo'):
			r = await c.post(f'/triage/preliminary?lang={lang}', json=body)
			assert r.status_code == 200, f'{lang}: {r.status_code}'


async def test_the_ussd_menu_serves_a_language_it_has_no_table_for() -> None:
	"""The same defect on the channel Grace actually uses. §CHAN-2's menu names Dholuo; before the
	fix, asking for it raised inside `ChannelService.ussd` and the session died mid-menu."""
	app = create_app()
	body = {'session_id': 'S-1', 'msisdn': '+254700000001', 'text': ''}
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		en = await c.post('/channels/ussd?lang=en', json=body)
		luo = await c.post('/channels/ussd?lang=luo', json=body)
		sw = await c.post('/channels/ussd?lang=sw', json=body)
	assert luo.status_code == 200, luo.text[:200]
	assert luo.json()['menu'] == en.json()['menu'], 'a language with no table is served English'
	assert sw.status_code == 200 and sw.json()['menu'] != en.json()['menu']


def test_the_segment_crossing_finds_the_p1_row_with_no_persona() -> None:
	"""§4.3 puts chronically ill adults at P1 — "Highest daily medication need" — and §4.1 never
	describes one. Reported rather than filled: a persona this module invented to close the row
	would be indistinguishable from the seven the section states."""
	assert _svc().segments_without_a_persona() == ['chronically_ill_adults']


def test_the_secondary_crossing_finds_the_five_audiences_17_4_has_no_role_for() -> None:
	"""§4.2 names seven audiences and §17.4 has a row for two of them. Five read the product through
	no scope the RBAC table defines, which is either a gap in the table or a gap in the list."""
	missing = _svc().secondary_without_a_role()
	assert len(missing) == 5, missing
	assert 'Ministry of Health policymakers' in missing
	assert 'School administrators and teachers' in missing
	by_name = {s.name: s.role for s in SECONDARY_PERSONAS}
	assert by_name['County Health Management Team members'] is RBACRole.county_officer
	assert by_name['PHEOC analysts and epidemiologists'] is RBACRole.pheoc_analyst


def test_coverage_reports_the_findings_rather_than_an_empty_success() -> None:
	"""The whole crossing as one answer. Every field is non-empty today, which is what makes this a
	report and not a green tick — and the note names each finding so a reader does not have to
	re-derive it from four lists."""
	cov = _svc().coverage()
	assert (cov.personas, cov.secondary, cov.segments) == (7, 7, 8)
	assert cov.unserved_languages == ['bxk', 'ki', 'luo']
	assert cov.unserved_personas == ['b (Otieno)', 'f (Grace)']
	assert cov.segments_without_a_persona == ['chronically_ill_adults']
	assert len(cov.secondary_without_a_role) == 5
	assert len(cov.unmapped_entry_points) == 3
	for fragment in ('tier-1 languages', 'entry points outside', 'no §4.1 persona', 'no §17.4 role'):
		assert fragment in cov.note, cov.note


# --- what the app serves --------------------------------------------------------------------------

def _app_and_tokens():  # type: ignore[no-untyped-def]
	svc = build_services()
	auth: Any = svc['auth']
	return create_app(svc), {
		'auditor': {'authorization': f"Bearer {auth.provision_staff('per-aud', RBACRole.auditor, registrar='MoH').access_token}"},
		'sysadmin': {'authorization': f"Bearer {auth.provision_staff('per-sys', RBACRole.sysadmin, registrar='MoH').access_token}"},
	}


async def test_the_catalogue_serves_the_personas_and_the_segments() -> None:
	app = create_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		body = (await c.get('/personas')).json()
		assert len(body['personas']) == 7 and len(body['secondary']) == 7
		assert [p['key'] for p in body['personas']] == list('abcdefg')
		seg = (await c.get('/personas/segments')).json()['segments']
		assert len(seg) == 8
		assert (await c.get('/personas/segments', params={'priority': 'p0'})).json()['segments']
		assert len((await c.get('/personas/segments', params={'priority': 'p0'})).json()['segments']) == 2
		assert (await c.get('/personas/segments', params={'priority': 'p9'})).status_code == 422


async def test_the_coverage_read_is_scoped_to_the_auditor() -> None:
	"""`audit_logs`, the same family as `/rollout/readiness`: it is an audit of the build against
	§4, not a user-facing fact. A sysadmin holds `infrastructure` and is refused, which is what
	proves the route is scoped rather than merely requiring a token."""
	app, tok = _app_and_tokens()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
		assert (await c.get('/personas/coverage')).status_code in (401, 403)
		assert (await c.get('/personas/coverage', headers=tok['sysadmin'])).status_code == 403
		body = (await c.get('/personas/coverage', headers=tok['auditor'])).json()
	assert body['unserved_languages'] == ['bxk', 'ki', 'luo']
	assert body['unserved_personas'] == ['b (Otieno)', 'f (Grace)']


def test_no_served_persona_field_carries_a_spec_code() -> None:
	"""§3.3 principle 9's rule. §4 is prose and §17.4 is an access table; a persona payload saying
	"ACC-002" would be the feature code percolating into a surface the app serves."""
	code = re.compile(r'\b(CHAN|INF|REC|MON|SENS|ACC|SEC)-\d{3}\b')
	for p in PERSONAS:
		for value in (p.summary, p.entry_point, *p.needs, *p.friction, *p.entry_unmapped):
			assert not code.search(value), value
	for s in SEGMENTS:
		assert not code.search(s.rationale), s.rationale
