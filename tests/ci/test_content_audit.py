"""§8–§12's feature content lists, crossed against what the repo actually does.

The tests read `docs/spec.md` rather than the module, so a section reworded in the spec fails here
instead of silently detaching the audit from the text it claims to have read.
"""
import re
from pathlib import Path

SPEC = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')

LABELS = ('Features', 'Contents', 'Additional inputs', 'Outputs', 'Signals monitored')


def _spec_section(feature_id: str) -> str:
	"""The body of one `#### FID: name` section, up to the next heading or horizontal rule."""
	marker = f'#### {feature_id}:'
	assert marker in SPEC, f'{feature_id} is not a section in the spec'
	return SPEC.split(marker, 1)[1].split('\n---', 1)[0]


def _spec_bullets(feature_id: str, label: str) -> list[str]:
	"""The bullets under one labelled list in a section, in the section's order."""
	body = _spec_section(feature_id)
	marker = f'**{label}:**'
	if marker not in body:
		return []
	segment = body.split(marker, 1)[1]
	segment = re.split(r'\n\*\*|\n####|\n###', segment)[0]
	return [line[2:].strip() for line in segment.splitlines() if line.startswith('- ')]


def _spec_inline_list(feature_id: str, label: str) -> list[str]:
	"""A label whose content is one prose sentence of comma-separated items, not bullets.

	§9.5 INF-007's Contents cell is the only one of these: "School closures, border post status,
	market closures, water interruptions, road closures affecting facility access, public transport
	disruptions."
	"""
	body = _spec_section(feature_id)
	marker = f'**{label}:**'
	assert marker in body, f'{feature_id} has no {label}'
	segment = re.split(r'\n\*\*|\n####|\n###', body.split(marker, 1)[1])[0].strip()
	return [item.strip() for item in segment.rstrip('.').split(',')]


# --- the audit reads the section it says it read ------------------------------------------------

def test_every_audited_bullet_is_the_sections_bullet_in_its_own_words() -> None:
	"""Each audited feature section's bullets are carried in the section's order, so a bullet added
	to the spec and not to the audit fails here rather than going unmeasured."""
	from afya.content_audit.service import FEATURE_CONTENT
	for feature_id in dict.fromkeys(f for f, _, _, _, _, _ in FEATURE_CONTENT):
		for label in dict.fromkeys(l for f, l, _, _, _, _ in FEATURE_CONTENT if f == feature_id):
			spec = (_spec_inline_list(feature_id, label) if label == 'Contents'
				else _spec_bullets(feature_id, label))
			mine = [b for f, l, b, _, _, _ in FEATURE_CONTENT if f == feature_id and l == label]
			assert mine == spec, f'{feature_id} {label}: {mine} != {spec}'


def test_the_four_audited_sections_are_the_ones_the_survey_found_uncited() -> None:
	"""The selection rule, asserted rather than left in a docstring: these are the feature sections
	the section-number survey found named nowhere in the source."""
	from afya.content_audit.service import FEATURE_CONTENT
	assert set(f for f, _, _, _, _, _ in FEATURE_CONTENT) == {'MED-004', 'FND-006', 'INF-007', 'TRI-003'}


# --- the three verdicts, kept apart -------------------------------------------------------------

def test_every_verdict_is_one_of_three_and_only_one_is_a_finding() -> None:
	"""`carried` names code, `deferred` is out of scope here, `missing` is a bullet nothing does.
	Merged into one list the cross-references would read as gaps and bury the real ones."""
	from afya.content_audit.service import FEATURE_CONTENT
	kinds = {k for _, _, _, k, _, _ in FEATURE_CONTENT}
	assert kinds == {'carried', 'deferred', 'missing'}
	for _, _, _, kind, ref, note in FEATURE_CONTENT:
		if kind == 'carried':
			assert ref, 'a carried bullet names the code that carries it'
		else:
			assert note and ref is None, 'a non-carried bullet names no code and says why'


def test_a_carried_bullet_names_code_that_imports() -> None:
	"""`unresolved` is the second finding and it is not the same as `missing`: a carrier that rotted
	is a bullet someone built, and a bullet nobody built is a different defect."""
	from afya.content_audit.service import content_report
	report = content_report()
	assert report.unresolved == [], report.unresolved


def test_the_report_states_how_much_of_the_spec_it_read() -> None:
	"""§8–§12 carry 220 labelled bullets across 35 feature sections and four are audited. A finding
	list served without that context invites the reader to take it as complete — the failure mode of
	every gate that scopes itself, which is why the unaudited sections are data rather than prose."""
	from afya.content_audit.service import UNAUDITED_FEATURES, content_report
	report = content_report()
	assert report.audited_features == 4
	assert len(report.unaudited_features) == 32, 'thirty-two feature sections carry content nobody has crossed'
	assert report.unaudited_features == list(UNAUDITED_FEATURES)
	assert not set(report.unaudited_features) & {f.feature_id for f in report.features}


# --- the findings -------------------------------------------------------------------------------

def test_the_missing_bullets_are_the_fifteen_this_audit_found() -> None:
	"""The finding, pinned by name so a repair shows up as a change here rather than as a smaller
	number nobody reads. Each is a bullet the section prints and nothing in the repo does."""
	from afya.content_audit.service import content_report
	missing = content_report().missing
	assert len(missing) == 15, missing
	assert sum(1 for m in missing if m.startswith('§MED-004')) == 4
	assert sum(1 for m in missing if m.startswith('§FND-006')) == 3
	assert sum(1 for m in missing if m.startswith('§INF-007')) == 4
	assert sum(1 for m in missing if m.startswith('§TRI-003')) == 4


def test_med_004_cannot_render_its_own_example() -> None:
	"""MED-004's Features list prints the string "available at [pharmacy], 2 hours ago" as the thing
	a person sees. `StockReport` carries no timestamp, so no client can render the section's own
	example — the same shape as §6.2.3's "Updated 2 hours ago", which also had nothing behind it."""
	from afya.medicine.views import StockReport
	assert not any('time' in f or 'at_iso' in f or 'when' in f for f in StockReport.model_fields), \
		'the absence is the finding; a timestamp here means the gap is closed and this test must change'


def test_tri_003_names_four_exposures_the_input_cannot_distinguish() -> None:
	"""§11.2 names funeral attendance, healthcare work, contact with a case and bushmeat consumption
	as separate inputs. `TriageInput` carries one `ebola_contact` boolean, so a funeral and a
	bushmeat exposure read identically to the classifier."""
	from afya.triage.views import TriageInput
	assert 'ebola_contact' in TriageInput.model_fields
	for named in ('funeral', 'healthcare_work', 'bushmeat'):
		assert not any(named in f for f in TriageInput.model_fields), \
			f'{named} is carried now, so §11.2\'s exposure list is no longer a gap'


def test_the_deferred_bullet_is_the_one_the_section_conditions_on_the_world() -> None:
	"""TRI-003's vaccination input is written "if a vaccine is available and deployed" — a condition
	on the world, not on this tree, so nothing here can carry it and it is not a gap. Kept separate
	from `missing` because reporting it as one would put a fact about vaccine deployment in a defect
	list."""
	from afya.content_audit.service import FEATURE_CONTENT
	deferred = [(f, b, n) for f, _, b, k, _, n in FEATURE_CONTENT if k == 'deferred']
	assert len(deferred) == 1, deferred
	feature_id, bullet, note = deferred[0]
	assert feature_id == 'TRI-003' and bullet.startswith('Vaccination status')
	assert note is not None and 'fact about the world' in note


async def test_the_content_audit_view_is_auditor_scoped() -> None:
	"""The report names module references and fifteen gaps, which is evidence about the build."""
	import httpx
	from typing import Any
	from afya.privacy.views import RBACRole
	from afya.service import build_services, create_app
	svc = build_services()
	auth: Any = svc['auth']
	tok = auth.provision_staff('ca-aud', RBACRole.auditor, registrar='MoH ops').access_token
	app = create_app(svc)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		assert (await c.get('/features/content')).status_code in (401, 403)
		body = (await c.get('/features/content',
			headers={'authorization': f'Bearer {tok}'})).json()
		assert len(body['missing']) == 15
		assert body['audited_features'] == 4
		assert len(body['unaudited_features']) == 32
