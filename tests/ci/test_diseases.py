"""Gate: §3.3 principle 12's outbreak diseases, and every surface that has to accept them.

Principle 12 is the sentence the product's second half rests on — "Tier 4 activates for Ebola,
cholera, Rift Valley fever, mpox, measles, and the next unknown" — and nothing carried the list. What
existed instead was four spellings of a disease vocabulary on four surfaces, none of them the section
that names it, and they had drifted: `surveillance.CountySignal`, the model the early-warning signal
is computed from, refused `measles` — a disease principle 12 names — while `community.CaseReport` and
the mobile catalogue accepted it. Dengue was on three surfaces and appears nowhere in the spec.

The tests here are the class, not the instance. A gate that only pinned measles would pass the day
somebody added `typhoid` to one surface and not the others, which is the same defect with a different
word in it.
"""
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from afya.alerts.views import OUTBREAK_KINDS, AlertKind, CommunityAlert
from afya.community.views import CaseReport
from afya.mobile.actions import VECTOR_DISEASES
from afya.registry.diseases import (
	DISEASE, DISEASE_PATTERN, DISEASE_ROWS, DISEASES, OTHER, SPEC_DISEASES, english,
	spec_disease_slugs,
)
from afya.surveillance.views import CountySignal, SignalReading

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / 'docs' / 'spec.md'


def _principle_12() -> str:
	"""§3.3's principle 12 row, read out of the spec. The row is located by its own number rather
	than by the disease names, so a revision that changes which diseases it lists fails here rather
	than passing against a section that no longer says what the code claims."""
	lines = SPEC.read_text(encoding='utf-8').splitlines()
	row = next(ln for ln in lines if ln.startswith('| 12 |'))
	assert 'outbreak after this one' in row, 'row 12 is not the principle this module carries'
	return row


def _signal(disease: str) -> CountySignal:
	return CountySignal(
		county='Nairobi', disease=disease, week_isoyear=2026, week=41,
		fever_reports=1, hotline_calls=1, confirmed_cases=0,
	)


# --- the vocabulary, against §3.3 principle 12 ---------------------------------------------------

def test_the_spec_diseases_are_the_sections_own() -> None:
	"""Every disease the code calls a spec disease must be named in principle 12's row, and every
	disease the row names must be a spec disease here. Both directions, because a list that only
	checks one way either carries a disease the section never asked for or drops one it did."""
	row = _principle_12()
	assert SPEC_DISEASES == ('evd', 'cholera', 'rvf', 'mpox', 'measles')
	# The section's row is not capitalised consistently — it writes "cholera" and "Rift Valley fever"
	# in lower case — so the comparison is case-folded. The names are still required verbatim
	# otherwise; folding case is not the same as accepting a paraphrase.
	folded = row.casefold()
	for slug in SPEC_DISEASES:
		name = DISEASE[slug].english
		assert name.casefold() in folded, f'{slug} ({name}) is not in §3.3 principle 12'
	# The other direction, and the one a one-way check misses: the section's list is parsed and the
	# code must carry *it*, not merely include it. A revision that adds a sixth disease to the row
	# must fail here, or the module keeps claiming to be §3.3 principle 12's list while the section
	# has moved on — which is how `measles` came to be missing from a copy in the first place.
	listed = row.split('activates for', 1)[1].split(', and the next unknown', 1)[0]
	names = [n.strip().rstrip('.') for n in listed.split(',') if n.strip()]
	by_name = {DISEASE[s].english.casefold(): s for s in SPEC_DISEASES}
	assert [by_name.get(n.casefold()) for n in names] == list(SPEC_DISEASES), \
		f'§3.3 principle 12 now lists {names}, which the code does not carry in that order'


def test_the_next_unknown_is_a_slot_and_not_a_disease() -> None:
	"""Principle 12 ends "and the next unknown". The sixth outbreak is the one nobody has named, and
	a vocabulary that cannot carry it can only ever alert on the five that already happened — so
	`other` is a required member everywhere and is deliberately not a spec disease."""
	assert OTHER in DISEASES
	assert OTHER not in SPEC_DISEASES, 'the unknown slot is not one of the named diseases'
	assert DISEASE[OTHER].beyond_spec is False, 'it is the section’s own slot, not the repo’s addition'
	assert 'unknown' in DISEASE[OTHER].english.lower()


def test_the_repos_own_diseases_are_marked_as_such() -> None:
	"""Dengue is on three surfaces and nowhere in the spec; malaria is §3.3 principle 5's whole
	argument and also not on principle 12's list. Both are kept — removing a working capability to
	tidy a list is the wrong trade — and both are marked, so a reader can tell a disease the spec
	asked for from one this repo added."""
	assert set(DISEASE[slug].english for slug in ('malaria', 'dengue')) <= {
		'Malaria', 'Dengue',
	}
	assert {s for s in DISEASES if DISEASE[s].beyond_spec} == {'malaria', 'dengue'}
	for slug in SPEC_DISEASES + (OTHER,):
		assert DISEASE[slug].beyond_spec is False, f'{slug} is the section’s, not the repo’s'


def test_the_slug_and_the_english_name_are_joined() -> None:
	"""`evd` is the wire code every surface has always used and §3.3 spells the disease "Ebola"; the
	row is where those two spellings meet. `english()` refuses an unknown slug rather than echoing it
	back, because a report printing an unrecognised code looks exactly like one printing a disease."""
	assert english('rvf') == 'Rift Valley fever'
	assert english('measles') == 'Measles'
	assert DISEASE['malaria'].label().endswith('(beyond the spec’s list)')
	assert not DISEASE['cholera'].label().endswith('(beyond the spec’s list)')
	with pytest.raises(AssertionError):
		english('typhoid')


def test_every_row_is_in_the_pattern_and_the_pattern_is_the_rows() -> None:
	"""The regex the four surfaces validate against is built from the list, so the two cannot drift —
	which is exactly how `surveillance` came to omit measles while the list it was copied from had
	it."""
	assert DISEASE_PATTERN == '^(' + '|'.join(DISEASES) + ')$'
	compiled = re.compile(DISEASE_PATTERN)
	for slug in DISEASES:
		assert compiled.match(slug), f'{slug} is in the list but not the pattern'
	assert not compiled.match('typhoid'), 'an unknown disease must not match'


# --- every surface accepts the whole vocabulary ---------------------------------------------------

def test_the_surveillance_signal_accepts_every_disease() -> None:
	"""The surface measles was refused on. `CountySignal` is what the early-warning signal is
	computed from (§19.2, AI-001), so a disease it refuses is a disease whose signal the system
	cannot compute — and the county that reports measles is the county that most needs one."""
	for slug in DISEASES:
		assert _signal(slug).disease == slug
		reading = SignalReading(county='Nairobi', disease=slug, z_score=0.0, risk='low', weeks_observed=1)
		assert reading.disease == slug
	with pytest.raises(ValidationError):
		_signal('typhoid')


def test_the_case_report_accepts_every_disease() -> None:
	def _report(disease: str) -> CaseReport:
		return CaseReport(
			report_id='CR-ABC12345', chw_ref='chw-1', county='Busia', community='Bukhayo',
			symptoms=['fever'], suspected_disease=disease,
		)

	for slug in DISEASES:
		assert _report(slug).suspected_disease == slug
	with pytest.raises(ValidationError):
		_report('typhoid')


def test_the_mobile_catalogue_offers_every_disease() -> None:
	"""A person filling the case-report form chooses from this list, so a disease missing here is one
	no CHW can report through the app however many the server accepts."""
	assert VECTOR_DISEASES == list(DISEASES)
	assert set(SPEC_DISEASES) <= set(VECTOR_DISEASES)


def test_every_disease_has_an_outbreak_alert_kind() -> None:
	"""The enum had no `outbreak_measles` and no `outbreak_other`, so two of the diseases principle
	12 is most explicit about were the two an outbreak alert could not be raised for. The mapping is
	onto the whole vocabulary, and the import-time assert in `alerts.views` makes a gap a crash
	rather than a missing branch."""
	assert tuple(k.value.removeprefix('outbreak_') for k in OUTBREAK_KINDS) == DISEASES
	for slug in DISEASES:
		assert AlertKind(f'outbreak_{slug}') in OUTBREAK_KINDS


def test_a_measles_outbreak_alert_can_be_raised() -> None:
	"""The end the vocabulary exists for: the alert itself. Principle 12 names measles, so a measles
	outbreak alert must be constructible — the enum member existing is not the same as the factory
	accepting it."""
	alert = CommunityAlert.outbreak(
		'AL-MEASLES01', AlertKind.outbreak_measles, 'Garissa',
		'Measles cases confirmed', 'Two confirmed cases in Garissa. Check your child’s immunisation card.',
	)
	assert alert.kind is AlertKind.outbreak_measles
	assert alert.multi_disease is True


# --- the vocabulary is one list, not four ----------------------------------------------------------

def test_no_surface_restates_a_disease_regex() -> None:
	"""The class of defect, not the instance. Four surfaces carried four spellings of this list and
	the copies drifted; a fifth copy written tomorrow drifts the same way. Every module that
	validates a disease must take the pattern from `registry.diseases`, so this scans the tree for
	the shape of a restated list rather than for the old string — which is invisible in a module that
	was written from scratch."""
	modules = [p for p in (REPO / 'src' / 'afya').rglob('*.py') if p.name != 'diseases.py']
	offenders: list[str] = []
	for path in modules:
		text = path.read_text(encoding='utf-8')
		# Every string literal, not only the `pattern=` spelling. The first version of this check
		# matched `pattern=r'...'` alone and a canary walked straight past it with a bare
		# `DISEASE_RE = r'^(evd|cholera|rvf)$'` — a checker that enumerates one of the two ways to
		# write the thing is the bug wearing the gate's clothes.
		#
		# The alternatives are compared as a *set*, not counted as substrings. Counting matched
		# `cholera_food` in §8.5's food-alert kinds as two diseases (`cholera`, `other`), which is a
		# real list of a different thing — the failure a check for "does it mention these words"
		# always has, and the reason this one parses the literal.
		for match in re.finditer(r"""(['"])(\^?\(?[^'"]*?\)?\$?)\1""", text):
			alternatives = {a for a in match.group(2).strip('^$()').split('|') if a}
			overlap = alternatives & set(DISEASES)
			if len(overlap) >= 2:
				offenders.append(f'{path.relative_to(REPO)}: {match.group(0)}')
	assert not offenders, 'a disease list is restated rather than read from registry.diseases: ' + '; '.join(offenders)


def test_the_vocabulary_is_reachable_from_the_registry() -> None:
	"""`registry.diseases` sits beside the feature registry because §3.3 principle 12 is a rule about
	which features activate, and §11.1's activation table is where the diseases are consumed. Keeping
	it in the registry package is what lets the surveillance, community and alert surfaces import it
	without importing each other."""
	import afya.registry.diseases as mod

	assert mod.__name__ == 'afya.registry.diseases'
	assert len(DISEASE_ROWS) == len(DISEASES)
	assert spec_disease_slugs() == frozenset(SPEC_DISEASES)
