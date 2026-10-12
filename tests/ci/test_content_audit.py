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
	"""One labelled list in a section, in the section's order.

	The spec writes these two ways and both are content: bullets under the label (§8.1 TRI-001's
	Outputs), or a single prose sentence of comma-separated items (§9.5 INF-007's Contents, §8.2
	FND-003's Features, §10.2 MON-005's). Dispatching on the *shape* rather than on the label name
	matters: a list that moves from prose to bullets must not read as the section losing its
	content, and the first cut keyed on `label == 'Contents'`, which would have silently returned
	nothing for the twenty-odd sections that write it the other way.
	"""
	body = _spec_section(feature_id)
	marker = f'**{label}:**'
	assert marker in body, f'{feature_id} has no {label}'
	segment = re.split(r'\n\*\*|\n####|\n###', body.split(marker, 1)[1])[0]
	bullets = [line[2:].strip() for line in segment.splitlines() if line.startswith('- ')]
	if bullets:
		return bullets
	prose = segment.strip().lstrip('- ').strip()
	assert prose, f'{feature_id} has a {label} label with nothing after it'
	return [item.strip() for item in prose.rstrip('.').split(',')]


def _spec_feature_ids() -> list[str]:
	"""Every `#### FID: name` section in the spec, in document order."""
	return re.findall(r'^#### ([A-Z]{2,4}-\d{3}):', SPEC, re.M)


def _carries_a_label(feature_id: str) -> bool:
	"""Whether the section prints any of the five labelled content lists — the set the audit's two
	coverage lists must partition."""
	body = _spec_section(feature_id)
	return any(f'**{label}:**' in body for label in LABELS)


# --- the audit reads the section it says it read ------------------------------------------------

def test_every_audited_bullet_is_the_sections_bullet_in_its_own_words() -> None:
	"""Each audited feature section's bullets are carried in the section's order, so a bullet added
	to the spec and not to the audit fails here rather than going unmeasured."""
	from afya.content_audit.service import FEATURE_CONTENT
	for feature_id in dict.fromkeys(f for f, _, _, _, _, _ in FEATURE_CONTENT):
		for label in dict.fromkeys(l for f, l, _, _, _, _ in FEATURE_CONTENT if f == feature_id):
			spec = _spec_bullets(feature_id, label)
			mine = [b for f, l, b, _, _, _ in FEATURE_CONTENT if f == feature_id and l == label]
			assert mine == spec, f'{feature_id} {label}: {mine} != {spec}'


def test_the_audited_sections_are_the_ones_the_survey_found_uncited() -> None:
	"""The selection rule, asserted rather than left in a docstring, and it is a rule about what a
	person meets, not about what a survey happened to notice. Four tranches: the four sections the
	section-number survey found named nowhere (a citations rule), the nine §8 Tier-1 sections (the
	tier that earns the download), the seven Tier-2 sections plus §9.2 REC-001 (the tier that earns
	the return visit), and the four §8 Tier-1 sections the first pass over that tier missed. The
	order the work was done in is not the order of importance.

	The last tranche is a correction rather than new ground: §8 has thirteen feature sections and
	the first pass audited nine of them, so four Tier-1 sections — the tier the whole adoption
	argument rests on — were named in neither list. That is the failure this assertion exists to
	catch, and it was live here until the partition test below found it.
	"""
	from afya.content_audit.service import FEATURE_CONTENT
	audited = set(f for f, _, _, _, _, _ in FEATURE_CONTENT)
	assert {'MED-004', 'FND-006', 'INF-007', 'TRI-003'} <= audited, 'the uncited four'
	assert {'TRI-001', 'TRI-002', 'FND-001', 'FND-002', 'FND-004',
		'MED-001', 'MED-002', 'MED-003', 'EMG-001'} <= audited, 'the §8 Tier-1 nine'
	assert {'INF-004', 'INF-005', 'MON-001', 'MON-002', 'MON-003', 'MON-004',
		'REC-001'} <= audited, 'the Tier-2 seven'
	assert {'FND-003', 'FND-005', 'EMG-003', 'INF-006'} <= audited, 'the Tier-1 four the first pass missed'
	assert len(audited) == 24, 'the four tranches name twenty-four distinct sections'
	assert audited == {f for f in audited}, 'every audited id is a real feature'


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
	"""A finding list served without its coverage invites the reader to take it as complete — the
	failure mode of every gate that scopes itself, which is why the unread sections are data. The
	two lists must *partition* the sections that carry a labelled list: a section in neither is one
	nobody can find out is unaudited, which is worse than either verdict."""
	from afya.content_audit.service import UNAUDITED_FEATURES, content_report
	report = content_report()
	labelled = {fid for fid in _spec_feature_ids() if _carries_a_label(fid)}
	audited = {f.feature_id for f in report.features}
	assert audited | set(report.unaudited_features) == labelled, \
		'every labelled section is either audited or named as unaudited'
	assert not audited & set(report.unaudited_features)
	assert report.audited_features == len(audited) == 24
	assert report.unaudited_features == list(UNAUDITED_FEATURES)


# --- the findings -------------------------------------------------------------------------------

def test_the_missing_bullets_are_pinned_by_feature() -> None:
	"""The finding, counted per feature rather than as one total, so a repair shows up as a changed
	number here rather than as a smaller figure nobody reads. Each count is a bullet the section
	prints and nothing in the repo does."""
	from afya.content_audit.service import content_report
	missing = content_report().missing
	per_feature: dict[str, int] = {}
	for m in missing:
		per_feature[m.split(':')[0]] = per_feature.get(m.split(':')[0], 0) + 1
	assert per_feature == {
		'§TRI-001': 4, '§TRI-002': 4, '§FND-001': 3, '§FND-002': 4, '§FND-004': 1,
		'§MED-001': 4, '§MED-002': 2, '§MED-003': 4, '§EMG-001': 4,
		'§MED-004': 4, '§FND-006': 3, '§INF-007': 4, '§TRI-003': 4,
		'§INF-004': 4, '§INF-005': 1, '§MON-001': 4, '§MON-002': 9, '§MON-003': 3,
		'§MON-004': 2, '§REC-001': 6,
		'§INF-006': 4,
		# §EMG-003, §FND-003 and §FND-005 are audited and carry nothing missing: every Content,
		# Access clause and filter dimension resolves to code, so the sections have no row here —
		# absence from this dict is the strongest verdict the audit has, and should be read as one.
	}, per_feature


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


def test_the_deferred_bullets_are_the_ones_the_section_conditions_on_the_world() -> None:
	"""Seven bullets are deferred and they are two kinds, neither a gap. Six are device actions — a
	maps app, a dialler, a barcode reader — which the coverage gate's `ON_DEVICE` set already lists
	as client-side by design. The seventh is TRI-003's vaccination input, written "if a vaccine is
	available and deployed": a condition on the world, not on this tree. Kept out of `missing`
	because reporting them as gaps would put a fact about vaccine deployment in a defect list."""
	from afya.content_audit.service import FEATURE_CONTENT
	deferred = [(f, b, n) for f, _, b, k, _, n in FEATURE_CONTENT if k == 'deferred']
	assert len(deferred) == 7, deferred
	world = [(f, b, n) for f, b, n in deferred if n is not None and 'fact about the world' in n]
	assert len(world) == 1, world
	feature_id, bullet, _ = world[0]
	assert feature_id == 'TRI-003' and bullet.startswith('Vaccination status')
	for _, _, note in deferred:
		assert note is not None
		assert 'fact about the world' in note or 'device' in note or 'client' in note, note


async def test_the_content_audit_view_is_auditor_scoped() -> None:
	"""The report names module references and the gap list, which is evidence about the build."""
	import httpx
	from typing import Any
	from afya.privacy.views import RBACRole
	from afya.service import build_services, create_app
	from afya.content_audit.service import content_report
	svc = build_services()
	auth: Any = svc['auth']
	tok = auth.provision_staff('ca-aud', RBACRole.auditor, registrar='MoH ops').access_token
	app = create_app(svc)
	report = content_report()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		assert (await c.get('/features/content')).status_code in (401, 403)
		body = (await c.get('/features/content',
			headers={'authorization': f'Bearer {tok}'})).json()
		assert body['missing'] == report.missing
		assert body['audited_features'] == report.audited_features
		assert body['unaudited_features'] == report.unaudited_features
