"""§2's problem statement — the seven citizen-layer gaps and the five conditioned lessons.

The tests compare against `docs/spec.md` rather than against the module, so a revision that rewords
a gap or drops a condition fails here instead of quietly repointing the tables.
"""
from pathlib import Path

SPEC = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')


def _spec_situation_bullets() -> list[str]:
	section = SPEC.split('### 2.1 Current Situation', 1)[1].split('### 2.2', 1)[0]
	return [line[2:].strip() for line in section.splitlines() if line.startswith('- ')]


def _spec_gap_rows() -> list[tuple[str, str]]:
	section = SPEC.split('### 2.2 The Last-Mile Gap', 1)[1].split('### 2.3', 1)[0]
	rows: list[tuple[str, str]] = []
	for line in section.splitlines():
		if not line.startswith('|') or set(line) <= set('|-: '):
			continue
		cells = [c.strip() for c in line.strip('|').split('|')]
		if len(cells) == 2 and cells[0] != 'Gap':
			rows.append((cells[0], cells[1]))
	return rows


def _spec_lessons() -> list[tuple[str, str]]:
	"""§2.3's five paragraphs as (system, bolded key lesson), read out of the prose."""
	section = SPEC.split('### 2.3 Lessons from Comparable Systems', 1)[1].split('\n---', 1)[0]
	out: list[tuple[str, str]] = []
	for para in [p.strip() for p in section.split('\n\n') if p.strip()]:
		system = para.split('**', 2)[1].rstrip('.')
		lesson = para.split('Key lesson: **', 1)[1].split('**', 1)[0]
		out.append((system, lesson))
	return out


# --- §2.1 and §2.2: the gaps the product claims to close ----------------------------------------

def test_the_citizen_gaps_are_the_sections_rows_in_its_own_words() -> None:
	"""§2.2 lists seven gaps. Each is carried in the section's order with its Consequence cell, so a
	row added to the spec and not to the table fails here rather than going unclosed unnoticed."""
	from afya.problem.service import CITIZEN_GAPS
	spec = _spec_gap_rows()
	assert len(spec) == 7, f'the section names {len(spec)} gaps'
	assert [(g, c) for g, c, _, _ in CITIZEN_GAPS] == spec


def test_every_gap_the_product_claims_to_close_has_something_closing_it() -> None:
	"""The finding the module exists to produce. A product whose problem statement names seven gaps
	and closes six has a claim it cannot support, so `unclosed` is reported rather than padded."""
	from afya.problem.service import gap_report
	report = gap_report()
	assert len(report.gaps) == 7
	assert report.unclosed == [], report.unclosed
	assert report.closed_count == 7
	assert all(g.resolves for g in report.gaps), \
		'a module:attr that does not import is a rotted reference, not a closed gap'


def test_the_situation_bullets_are_the_sections_and_only_two_name_a_join() -> None:
	"""§2.1 is Kenya's existing posture — eight facts about the country, not about this tree. Two name
	a system §18 integrates with; the join is keyed on the section's own wording so a reworded bullet
	fails here rather than silently detaching it."""
	from afya.problem.service import SITUATION_ITEMS, SITUATION_JOINS
	spec = _spec_situation_bullets()
	assert len(spec) == 8
	assert list(SITUATION_ITEMS) == spec
	assert len(SITUATION_JOINS) == 2, 'only the chatbot and the dashboards name an integration'
	assert set(SITUATION_JOINS) <= set(spec), 'a join must name a bullet the section carries'


# --- §2.3: five lessons, each carrying the condition that makes it safe -------------------------

def test_the_lessons_are_the_sections_paragraphs_in_its_own_words() -> None:
	from afya.problem.service import LESSONS
	spec = _spec_lessons()
	assert len(spec) == 5, f'the section draws {len(spec)} lessons'
	assert [(system, lesson) for system, lesson, _, _, _, _ in LESSONS] == spec


def test_every_condition_is_a_clause_of_its_own_lesson() -> None:
	"""The condition is the half that constrains this build, and a paraphrase of it would be a
	different requirement. Asserted as a substring so a condition invented rather than transcribed
	fails here."""
	from afya.problem.service import LESSONS
	for system, lesson, condition, _, _, _ in LESSONS:
		if condition is None:
			continue
		assert condition in lesson, f'{system}: {condition!r} is not a clause of its lesson'


def test_the_lessons_that_carry_a_condition_are_the_ones_that_qualify_something() -> None:
	"""Four of the five lessons qualify their claim; the LiDAR one does not. Recorded because the
	module reads the condition as the checkable half, so a lesson with none is a lesson the report
	cannot reach a verdict on by that route."""
	from afya.problem.service import LESSONS
	assert [c is not None for _, _, c, _, _, _ in LESSONS] == [True, True, True, False, True]


def test_the_verdicts_separate_what_this_repo_owes_from_what_it_cannot_decide() -> None:
	"""`unhonoured`, `unresolved` and `undecided` are three different findings. The first is a
	condition this build was supposed to meet and does not, the second a reference that does not
	land, the third a question about the world rather than about this tree. Mixed into one list they
	read as three ways of saying 'incomplete'."""
	from afya.problem.service import lesson_report
	report = lesson_report()
	assert len(report.lessons) == 5
	assert report.unresolved == [], report.unresolved
	assert len(report.unhonoured) == 1, report.unhonoured
	assert 'opt-in' in report.unhonoured[0]
	assert len(report.undecided) == 1 and 'consumer handsets' in report.undecided[0]


def test_proximity_logging_is_a_consent_category_no_proximity_path_reads() -> None:
	"""§2.3 lesson 3's condition, and §LOC-002's own "Opt-in only; can be disabled at any time",
	against the code. `proximity_logging` is a §SEC-001 category with a written scope and a written
	revocation consequence, and `LocationService` never reads it: `log_encounter` appends the token
	and asserts a bound on the store. The gate exists and is correct — `has_category_consent` — and
	nothing on this path calls it.

	The declaration side *is* gated, by `proxied`, and that is a different property: it prevents
	social-graph inference, not collection without consent.
	"""
	from afya.location.service import LocationService
	from afya.privacy.views import ConsentCategory
	assert ConsentCategory.proximity_logging.value == 'proximity_logging'
	# The category is documented with a consequence a person can act on.
	from afya.privacy.service import CONSENT_CATALOGUE
	scope = [c for c in CONSENT_CATALOGUE if c.category is ConsentCategory.proximity_logging]
	assert scope and scope[0].on_withdrawal, '§SEC-001 requires a revocation consequence'
	# And the service that logs encounters holds no consent service at all, so it cannot be reading
	# one. This is the assertion that fails when someone wires the gate in — which is the point.
	svc = LocationService()
	assert not hasattr(svc, '_privacy'), 'log_encounter has no consent dependency to consult'


async def test_the_problem_view_is_auditor_scoped() -> None:
	"""The report names module references and the consent gap, which is evidence about the build
	rather than something a citizen reads."""
	import httpx
	from afya.privacy.views import RBACRole
	from afya.service import build_services, create_app
	from typing import Any
	svc = build_services()
	auth: Any = svc['auth']
	tok = auth.provision_staff('prob-aud', RBACRole.auditor, registrar='MoH ops').access_token
	app = create_app(svc)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		assert (await c.get('/problem')).status_code in (401, 403)
		body = (await c.get('/problem', headers={'authorization': f'Bearer {tok}'})).json()
		assert body['gaps']['unclosed'] == []
		assert body['gaps']['closed_count'] == 7
		assert len(body['lessons']['unhonoured']) == 1
		assert len(body['lessons']['undecided']) == 1
