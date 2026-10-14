"""§8–§12's feature content lists, crossed against what the repo actually does.

The tests read `docs/spec.md` rather than the module, so a section reworded in the spec fails here
instead of silently detaching the audit from the text it claims to have read.
"""
import re
from pathlib import Path

SPEC = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')

def _every_spec_label() -> set[str]:
	"""Every bold label the spec prints on a `#### FID:` section.

	The audit's label vocabulary is a partition of this set, and that is the point of computing it
	from the spec rather than from the module: the first version of the module knew six labels and
	reported total coverage, while the spec prints ninety-five and §FND-001's ten-item content list
	sits under `**Data displayed per facility:**`. An instrument that cannot see a label cannot
	measure it, and the number it reports is then a fact about the instrument.
	"""
	labels: set[str] = set()
	for fid in _spec_feature_ids():
		labels |= set(re.findall(r'^\*\*([^*]+):\*\*', _spec_section(fid), re.M))
	return labels


def _spec_section(feature_id: str) -> str:
	"""The body of one `#### FID: name` section, up to the next heading or horizontal rule.

	Found by the section's own `**Feature ID:**` line, not by its heading spelling, because the spec
	writes a heading two ways and the second way is invisible to a regex over headings. §5's seven
	channel sections are `#### CHAN-0: Community Radio` … `#### CHAN-6:` — a one-digit suffix the
	`FID` pattern cannot match — and §14.9's two are titled in prose with no id at all
	(`#### External Device Integration (USB/OTG and BLE)`, whose body says `**Feature ID:** SENS-009`).
	Nine sections, 54 content items, in neither the audited list nor the unaudited one: the report
	said "69 of 69" and the partition test derived its ground truth from the *same* regex, so it
	could not disagree with the reader it was checking.
	"""
	for body in re.split(r'^#### ', SPEC, flags=re.M)[1:]:
		head = body.split('\n', 1)[0]
		if head.startswith(f'{feature_id}:') or re.search(
				rf'^\*\*Feature ID:\*\* {re.escape(feature_id)}\s*$', body, re.M):
			return body.split('\n---', 1)[0]
	raise AssertionError(f'{feature_id} is not a section in the spec')


def _split_items(text: str) -> list[str]:
	"""Split a prose content cell on its top-level commas and semicolons.

	Depth-tracked rather than a flat `re.split`: a separator inside a parenthesis belongs to the
	example, not to the list. §CHAN-1's Format is the case that forced it — "160 characters, plain
	language, local language option via keyword (e.g., prefix `SW`, `LU`, `KY`)" is three items and a
	flat split makes six, three of them fragments. Nothing else in the spec has a nested separator, so
	this changes no other section's bullets; that was checked against every audited pair rather than
	assumed.
	"""
	out: list[str] = []
	depth, current = 0, ''
	for char in text:
		if char == '(':
			depth += 1
		elif char == ')':
			depth -= 1
		if char in ';,' and depth == 0:
			out.append(current)
			current = ''
		else:
			current += char
	out.append(current)
	return [item.strip() for item in out if item.strip()]


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
	# The third shape: an ordered list. §LOC-002's How it works is a six-step protocol written
	# `1.` … `6.`, and the two shapes above read it as one prose cell — which is how a six-step
	# exposure-notification design became a single item, and how step 5, where a user's app checks
	# the uploaded tokens and notifies them, went unmeasured. A numbered protocol is as much a
	# content list as a bulleted one.
	numbered = [re.sub(r'^\s*\d+\.\s*', '', line).strip()
		for line in segment.splitlines() if re.match(r'^\s*\d+\.\s', line)]
	if numbered:
		return numbered
	prose = segment.strip().lstrip('- ').strip()
	assert prose, f'{feature_id} has a {label} label with nothing after it'
	# The fifth shape: a semicolon. §REC-003's Features is "Weight, height, head circumference,
	# MUAC; percentile charts; undernutrition alerts; feeding guidance by age; milestone
	# checklists." — five clauses, four of them written with the same separator the sentence uses
	# between items. Splitting on the comma alone read the whole run as one bullet named
	# "MUAC; percentile charts; …", so four of the eight things the section asks for had no row
	# and the audit reported a section covered by a cell it could not act on. A semicolon in a
	# content list separates items exactly as a comma does; REC-003 is the only section in the
	# spec that writes one, and `test_the_only_semicolon_list_in_the_spec_is_the_one_that_was_read`
	# pins that so this split cannot quietly change another section's bullets.
	# The separator only counts outside parentheses. §CHAN-1's Format is "160 characters, plain
	# language, local language option via keyword (e.g., prefix `SW`, `LU`, `KY`)" — three items, and
	# the two commas inside the parenthesis belong to the example rather than to the list. A flat
	# comma split read it as six items, three of which were fragments of one parenthetical
	# ("local language option via keyword (e.g.", "`LU`", "`KY`)"), so the audit would have carried
	# bullets the section does not print and the spec-comparison test would have demanded rows for
	# them. Depth tracking changes no other section's bullets — checked against every audited
	# (section, label) pair before the change, and §REC-003's eight still read as eight.
	items = [item.strip() for item in _split_items(prose.rstrip('.'))]
	# The fourth shape: a sequence of directives. §MED-004's Anti-gaming clause is written "Require
	# location proximity to report. Weight reports by reporter reliability. Show report age
	# clearly." — three separate controls, and the comma split read them as one item, which is how a
	# clause naming three things became a single auditable bullet.
	#
	# The discriminator is the *verb*, not the full stop, because a full stop alone is wrong: §EMG-003's
	# Access is "Available from the lock screen without unlocking the phone (opt-in). Critical for
	# unconscious patients" — one clause and a rationale for it, and splitting it would invent a
	# second bullet the section does not print. Both are two sentences and neither carries a comma,
	# so the only thing that separates them is that every sentence of the first is an instruction and
	# the second sentence of the second is not. Hence an explicit verb list rather than a heuristic.
	_DISJUNCTIVE_VERBS = ('Add', 'Allow', 'Avoid', 'Display', 'Ensure', 'Flag', 'Keep', 'Notify',
		'Provide', 'Record', 'Require', 'Send', 'Show', 'Store', 'Support', 'Use', 'Verify', 'Weight')
	if len(items) == 1 and '. ' in items[0]:
		parts = [part.strip() for part in items[0].split('. ') if part.strip()]
		if len(parts) > 1 and all(p.split(' ', 1)[0] in _DISJUNCTIVE_VERBS for p in parts):
			items = parts
	return items


def _spec_passage(feature_id: str, label: str) -> str:
	"""One claim-label passage, as the spec prints it under that label.

	The unit is the passage and not the sentence, and the distinction is the whole of why this
	reader exists rather than a second call to `_spec_bullets`. `_split_items` splits on top-level
	commas and semicolons because a *content* cell enumerates; a *claim* cell is prose. Sixty-eight
	of the ninety-two claim passages carry a comma, so the content parser would shred them — §MED-002's
	Disclaimer is "Informational only. Not a substitute for professional advice." and a comma split
	would make one sentence two fragments, neither of them the sentence the section prints.

	The passage ends at the next bold label, the next heading, or the horizontal rule, which is the
	same boundary `test_a_label_declared_out_of_scope_has_no_list_under_it` uses — one definition of
	"the body under this label", so the shape rule and the coverage gate cannot disagree about where
	a passage stops.
	"""
	body = _spec_section(feature_id)
	marker = f'**{label}:**'
	assert marker in body, f'{feature_id} has no {label}'
	return re.split(r'\n\*\*|\n####|\n###', body.split(marker, 1)[1])[0].strip()


def _spec_claims(feature_id: str, label: str) -> list[str]:
	"""The sentences of one claim passage.

	An editorial aid, not a boundary anything is asserted on: a gate over where a sentence ends is a
	gate over a regex. §CHAN-003's Privacy is four sentences and §TRI-002's Offline is one word, and
	both are one passage each.

	The split is on a full stop, question mark or exclamation followed by whitespace and a capital
	or an opening quote — so an abbreviation inside a sentence does not open a new one, and §CHAN-0's
	"e.g., known outbreak areas" stays inside the sentence that names it. A markdown table is a
	passage whose sentences are its rows, because that is how a reader reads it.
	"""
	if _spec_passage(feature_id, label).startswith('|'):
		return [line.strip() for line in _spec_passage(feature_id, label).splitlines()
			if line.strip().startswith('|') and not re.match(r'^\|[\s:|-]+\|$', line.strip())]
	return [part.strip() for part in
		re.split(r'(?<=[.!?])\s+(?=[A-Z"“])', _spec_passage(feature_id, label)) if part.strip()]


def _spec_feature_ids() -> list[str]:
	"""Every feature section in the spec, in document order, by the id the section declares.

	Two spellings: a heading that carries the id (`#### TRI-001: Broad Febrile-Illness Triage`) and a
	heading that does not, where the id is on the section's own `**Feature ID:**` line (`#### CHAN-0:`
	and §14.9's two prose-titled sections). Reading only the first spelling is how nine sections went
	unread while the report claimed 69 of 69.
	"""
	ids: list[str] = []
	for body in re.split(r'^#### ', SPEC, flags=re.M)[1:]:
		head = body.split('\n', 1)[0]
		m = re.match(r'([A-Z]{2,4}-\d{3}):', head)
		if m:
			ids.append(m.group(1))
			continue
		f = re.search(r'^\*\*Feature ID:\*\* ([A-Z]{2,4}-\d{3})\s*$', body, re.M)
		if f:
			ids.append(f.group(1))
	return ids


def _carries_a_label(feature_id: str) -> bool:
	"""Whether the section prints any of the audited content lists — the set the audit's two
	coverage lists must partition."""
	from afya.content_audit.service import _LABELS
	body = _spec_section(feature_id)
	return any(f'**{label}:**' in body for label in _LABELS)


# --- the instrument's own vocabulary ------------------------------------------------------------

def test_every_spec_label_is_either_audited_or_declared_out_of_scope() -> None:
	"""The label partition, asserted against the spec.

	This is the test the module was missing when it called its coverage total. It knew six labels —
	`Features`, `Contents`, `Additional inputs`, `Outputs`, `Signals monitored` and `Access` — and
	§8.2 FND-001's ten-item content list is under `**Data displayed per facility:**`, §8.3 FND-003's
	seven under `**Test types (context-dependent):**`, §6.2 INF-001's seven under `**Displays:**`.
	None of those sections could be measured, and three of them were reported as having nothing
	missing.

	A label in neither set is a section's content nobody can find out is unread, which is the same
	failure the unaudited list exists to prevent — one level up, about the instrument rather than
	the spec.
	"""
	from afya.content_audit.service import _CLAIM_LABELS, _LABELS
	declared = set(_LABELS) | set(_CLAIM_LABELS)
	assert len(_LABELS) + len(_CLAIM_LABELS) == len(declared), 'a label is in both sets'
	unknown = _every_spec_label() - declared
	assert unknown == set(), f'the spec prints labels the audit does not know: {sorted(unknown)}'
	stale = declared - _every_spec_label()
	assert stale == set(), f'declared labels the spec no longer prints: {sorted(stale)}'
	assert len(declared) == 95, 'the spec prints ninety-five labels'


def test_a_label_declared_out_of_scope_has_no_list_under_it() -> None:
	"""The partition is on the *shape of the body*, and this is the half that was wrong.

	`_CLAIM_LABELS` is for labels that state something about a feature rather than listing what it
	does. Eight of them were lists: `Application` (§SEC-002), `Behaviour` (§EMG-002, §LOC-004),
	`Conditions supported` (§MON-003), `Deployment points` (§LOC-004), `How it works` (§LOC-003),
	`Privacy properties` (§LOC-002), `Standards` (§SEC-003), `Technical approach` (§ACC-003,
	§ACC-004). Those eight were the whole of the eight sections the audit called contentless — the
	same failure as the six-label version, one level down: not "the instrument cannot see the label"
	but "the instrument filed the label where it would not look".

	A label whose body is a bullet or numbered list is a content list, wherever it is declared.
	"""
	from afya.content_audit.service import _CLAIM_LABELS, _LABELS
	for label in _CLAIM_LABELS:
		for fid in _spec_feature_ids():
			body = _spec_section(fid)
			if f'**{label}:**' not in body:
				continue
			segment = re.split(r'\n\*\*|\n####|\n###', body.split(f'**{label}:**', 1)[1])[0]
			listy = [line for line in segment.splitlines()
				if line.startswith('- ') or re.match(r'^\s*\d+\.\s', line)]
			assert not listy, f'§{fid} prints a list under {label!r}, which is declared out of scope'
	assert 'Application' not in _CLAIM_LABELS and 'Application' in _LABELS


def test_every_content_label_a_section_prints_has_rows_under_it() -> None:
	"""The gate that would have caught §FND-001, and the one the first version of this module
	needed. The audit was organised *by section*: a section was in `FEATURE_CONTENT` or it was not,
	and once it was in, nobody checked that every list it prints had been read. §FND-001 was in the
	table and its `**Data displayed per facility:**` — ten items — had no row at all.

	So a section is not the unit of coverage. The unit is the (section, label) pair, and this
	asserts every pair the spec prints has at least one row. Without it, adding a list to a section
	already being audited is silent, which is the exact shape of the miss that started this.
	"""
	from afya.content_audit.service import FEATURE_CONTENT, _LABELS
	covered = {(f, label) for f, label, _, _, _, _ in FEATURE_CONTENT}
	printed = {(fid, label) for fid in _spec_feature_ids() for label in _LABELS
		if f'**{label}:**' in _spec_section(fid)}
	assert printed - covered == set(), \
		f'content lists the spec prints with no rows under them: {sorted(printed - covered)}'
	assert covered - printed == set(), \
		f'rows under a label the section does not print: {sorted(covered - printed)}'


# --- the claim side, which had no gate ----------------------------------------------------------

def test_every_claim_label_a_section_prints_has_a_verdict_under_it() -> None:
	"""The gate the claim side never had, and the reason the two findings in it stayed hidden.

	`_LABELS` had two coverage gates. `_CLAIM_LABELS` had one *shape* rule — a label declared out of
	scope must not print a bullet list — which asks whether the body is a list and never whether
	anyone read it. So a claim label could carry a normative sentence for as long as the spec has
	existed and no test would notice: 92 (section, label) pairs, 165 passages, none read.

	Two of them were defects. §CHAN-2's Integration said "reports flow into the same backend as app
	and WhatsApp reports, deduplicated by phone number" while no channel wrote to that backend, and
	§AI-003's Alerting described a ledger fed by six app surfaces and no channel at all. Both are
	`carried` now, and neither was found by a count — they were found by reading this table, which is
	the argument for the table existing.

	The unit is the (section, label) pair, exactly as on the content side: a section is not the unit
	of coverage, and neither is a label.
	"""
	from afya.content_audit.service import CLAIM_CONTENT, _CLAIM_LABELS
	# A `Description` restates the section heading and a `Tier` is a position in §7's ladder. The
	# spec's own index is not a claim about a feature, so it is out of the audit's jurisdiction —
	# named here rather than silently skipped, so a fourth metadata label is a decision.
	metadata = {'Description', 'Feature ID', 'Tier'}
	covered = {(f, label) for f, label, _, _, _, _ in CLAIM_CONTENT}
	printed = {(fid, label) for fid in _spec_feature_ids() for label in _CLAIM_LABELS
		if label not in metadata and f'**{label}:**' in _spec_section(fid)}
	assert printed - covered == set(), \
		f'claim passages the spec prints with no verdict under them: {sorted(printed - covered)}'
	assert covered - printed == set(), \
		f'verdicts under a claim the section does not print: {sorted(covered - printed)}'
	assert len(printed) == 92, f'the spec prints 92 claim passages, not {len(printed)}'


def test_every_claim_is_the_sections_claim_in_its_own_words() -> None:
	"""Each claim passage is carried verbatim and in the section's order, so a reworded sentence
	fails here rather than silently detaching the audit from the text it says it read — the same
	rule `test_every_audited_bullet_is_the_sections_bullet_in_its_own_words` applies to the lists."""
	from afya.content_audit.service import CLAIM_CONTENT
	for feature_id, label in dict.fromkeys((f, l) for f, l, _, _, _, _ in CLAIM_CONTENT):
		spec = _spec_passage(feature_id, label)
		mine = [c for f, l, c, _, _, _ in CLAIM_CONTENT if (f, l) == (feature_id, label)]
		assert mine, f'{feature_id} {label} has no rows'
		# The passage is one string; its sentences are what the reader finds in it. Joined, the rows
		# must reproduce the passage, which is what "verbatim" means when the unit is the passage.
		# A markdown table is a passage whose lines are its rows, so it rejoins on the newline — minus
		# the `|---|---|` rule, which is markdown syntax rather than a row a reader reads. Every other
		# passage is prose and rejoins on the space the sentence split consumed.
		if spec.startswith('|'):
			body = '\n'.join(ln for ln in spec.splitlines()
				if not re.match(r'^\|[\s:|-]+\|$', ln.strip()))
		else:
			body = spec
		assert ('\n' if spec.startswith('|') else ' ').join(mine) == body, \
			f'{feature_id} {label}:\n  mine: {mine}\n  spec: {body!r}'
		assert len(mine) == len(_spec_claims(feature_id, label)), \
			f'{feature_id} {label}: {len(mine)} rows for {len(_spec_claims(feature_id, label))} sentences'


def test_a_claim_verdict_is_one_of_three_and_only_carried_names_code() -> None:
	"""The three verdicts, kept apart, and `narrative` is the one that needs defending.

	`carried` names code. `deferred` is a property of the handset, the broadcaster or the platform,
	or a claim the spec itself conditions on something this tree does not hold. `narrative` is a
	sentence about the world — the adoption argument, the audience, a broadcaster's figures — which
	no code can carry or refute, and reporting one as a gap would put an argument about adoption into
	a defect list.

	`narrative` is also the easiest place to hide an unbuilt capability, so it is held down two ways
	rather than described. The first is that a non-carried claim must carry a note and no reference,
	and that note must be longer than a phrase — a real reason, not a shrug. The second is the
	*pinned set* in `test_the_narrative_claims_are_the_ones_no_code_can_carry` below, which names
	every one of them: a claim that moves into `narrative` to make a gap disappear changes that set
	and fails there, which is the check this one cannot make on its own. A word list here would be an
	instrument scoped to the notes I happened to write, which is the bug wearing the gate's clothes.
	"""
	from afya.content_audit.service import CLAIM_CONTENT
	assert {k for _, _, _, k, _, _ in CLAIM_CONTENT} == {'carried', 'deferred', 'narrative'}
	for f, label, claim, kind, ref, note in CLAIM_CONTENT:
		if kind == 'carried':
			assert ref, f'§{f} {label} {claim!r} is carried and names no code'
		else:
			assert note and ref is None, f'§{f} {label} {claim!r} is {kind} with no reason'
			assert len(note.split()) >= 8, f'§{f} {label}: a reason, not a shrug — {note!r}'


def test_the_narrative_claims_are_the_ones_no_code_can_carry() -> None:
	"""The thirty-eight `narrative` claims, pinned by section and count.

	`narrative` is where an unbuilt capability could hide, so the set is asserted rather than left to
	the note's wording. Every entry is a sentence about the world: the adoption argument, the
	audience, a broadcaster's or a platform's figures, or an editorial standard the copy is held to.
	The three sections with the most are the ones whose claim labels are *entirely* argument —
	§CHAN-4's Objectives, §CHAN-5's Rationale and §CHAN-6's Role describe why a channel is in the
	product, and §MON-001's "Why this works" is the engagement case for the immunisation tracker.

	The count is asserted per section, so moving one claim into this verdict to make a gap disappear
	shows up as a changed number here rather than as a smaller total nobody reads — the same reason
	`test_the_missing_bullets_are_pinned_by_feature` counts per feature rather than in aggregate.
	"""
	from afya.content_audit.service import CLAIM_CONTENT
	per_feature: dict[str, int] = {}
	for f, _, _, kind, _, _ in CLAIM_CONTENT:
		if kind == 'narrative':
			per_feature[f'§{f}'] = per_feature.get(f'§{f}', 0) + 1
	assert per_feature == {
		'§CHAN-000': 2,   # the partnership and the free scripts; the language reach is deferred, not narrative
		'§CHAN-001': 1,   # "if a user is charged, adoption collapses" — why the requirement exists
		'§CHAN-004': 1,   # reach and credibility with youth
		'§CHAN-005': 2,   # the intermediaries' adoption argument
		'§CHAN-006': 2,   # the tier's position in the channel set
		'§MED-001': 2,    # counterfeit medicines, and the ten-second demo
		'§MED-003': 1,    # the audience
		'§EMG-002': 1,    # the audience
		'§MON-001': 3,    # why parents engage
		'§MON-002': 2,    # why pregnant women engage
		'§MON-004': 2,    # why the reminder drives opens
		'§REC-001': 2,    # the lost card
		'§MED-004': 2,    # stockouts, and the public-service argument
		'§REC-005': 1,    # the human cost of outbreaks
		'§REC-006': 3,    # the mental-health engagement argument
		'§COM-005': 1,    # civic engagement
		'§INF-009': 1,    # how valuable the offline resource is
		'§INF-010': 2,    # how the content was developed, and its editorial standard
		'§COM-102': 1,    # tested with community representatives
		'§COM-103': 1,    # the humane-interface standard
		'§LOC-002': 3,    # the method's own caveats and the DESIRE citation
		'§ALT-004': 1,    # tested with community representatives
		'§FND-006': 1,    # pilot then expand
	}, per_feature


def test_a_carried_claim_names_code_that_imports() -> None:
	"""The finding on the claim side, and the one this report was built for: a claim about the code
	that stopped being true is a rotted reference, not a capability nobody built."""
	from afya.content_audit.service import claim_report
	report = claim_report()
	assert report.unresolved == [], report.unresolved
	assert report.pairs_read == 92 and report.claims_read == 165
	assert (report.carried, report.deferred, report.narrative) == (107, 20, 38)


def test_the_two_claims_this_gate_was_built_for_are_carried() -> None:
	"""The named closure, so a regression is a failure here rather than a smaller number in a count.

	§CHAN-2's single-report-backend sentence and §AI-003's early-warning value sentence were the two
	defects the claim side hid. Both are `carried` by the channel report sink, and this asserts the
	carriers by name — a total would let one of them rot while the other stayed green.
	"""
	from afya.content_audit.service import CLAIM_CONTENT
	by_claim = {c: (kind, ref) for _, _, c, kind, ref, _ in CLAIM_CONTENT}
	integration = 'Reports flow into the same backend as app and WhatsApp reports, deduplicated by phone number.'
	assert by_claim[integration] == ('carried', 'afya.channels.service:ChannelService.record_report')
	value = ('This is how the app contributes to detecting the *next* outbreak before it is '
		'clinically recognised.')
	assert by_claim[value] == ('carried', 'afya.ai.service:WARNING_Z')


async def test_the_claim_report_view_is_auditor_scoped() -> None:
	"""The claim report names module references, so it is evidence about the build like its twin."""
	import httpx
	from typing import Any
	from afya.privacy.views import RBACRole
	from afya.service import build_services, create_app
	from afya.content_audit.service import claim_report
	svc = build_services()
	auth: Any = svc['auth']
	tok = auth.provision_staff('ca-claims', RBACRole.auditor, registrar='MoH ops').access_token
	app = create_app(svc)
	report = claim_report()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		assert (await c.get('/features/claims')).status_code in (401, 403)
		body = (await c.get('/features/claims',
			headers={'authorization': f'Bearer {tok}'})).json()
		assert body['pairs_read'] == report.pairs_read
		assert body['unresolved'] == report.unresolved
		assert body['carried'] == report.carried


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


def test_the_only_semicolon_list_in_the_spec_is_the_one_that_was_read() -> None:
	"""The semicolon split is scoped to its jurisdiction, asserted rather than assumed.

	A separator added to a parser is a change to every section the parser reads, so the claim the
	split rests on — that §REC-003 is the only prose list in the spec written with a semicolon —
	is a test and not a comment. If a later section writes one, this fails and the new section's
	bullets get read deliberately instead of silently.

	The second half checks the split *fired*, on the section it exists for: eight clauses, none of
	them still carrying a separator. A semicolon inside a bullet is a different thing and is left
	alone — §LOC-002's "Opt-in only; can be disabled at any time" is one privacy property and its
	rationale, and splitting it would invent a bullet the section does not print. That is why the
	split lives in the prose branch and not in the parser as a whole.
	"""
	from afya.content_audit.service import _LABELS
	found = []
	for fid in _spec_feature_ids():
		body = _spec_section(fid)
		for label in _LABELS:
			if f'**{label}:**' not in body:
				continue
			segment = re.split(r'\n\*\*|\n####|\n###', body.split(f'**{label}:**', 1)[1])[0]
			if segment.strip().startswith('- ') or re.match(r'^\s*\d+\.\s', segment.strip()):
				continue
			if ';' in segment:
				found.append((fid, label))
	assert found == [('REC-003', 'Features')], f'the semicolon lists are {found}'
	items = _spec_bullets('REC-003', 'Features')
	assert len(items) == 8, f'§REC-003 Features reads as {len(items)} items: {items}'
	assert not [item for item in items if ';' in item], 'a clause still reads as one bullet'


def test_the_audited_sections_are_the_ones_the_survey_found_uncited() -> None:
	"""The selection rule, asserted rather than left in a docstring, and it is a rule about what a
	person meets, not about what a survey happened to notice.

	It began as four tranches — the four sections the section-number survey found named nowhere (a
	citations rule), the nine §8 Tier-1 sections (the tier that earns the download), the seven Tier-2
	sections plus §9.2 REC-001 (the tier that earns the return visit), and the four §8 Tier-1
	sections the first pass over that tier missed. Each was a real gap when it was opened: the last
	one was a correction, because §8 has thirteen feature sections and the first pass audited nine,
	so four Tier-1 sections — the tier the whole adoption argument rests on — were named in neither
	list.

	The tranches are kept as assertions after the coverage went to 47/47 because a rule that is only
	true at the moment of the merge is a rule that rots on the next edit. Each block names sections
	whose *reason for being audited* is different, so a future removal of any one of them fails here
	with the reason attached rather than as a smaller number.
	"""
	from afya.content_audit.service import FEATURE_CONTENT
	audited = set(f for f, _, _, _, _, _ in FEATURE_CONTENT)
	assert {'MED-004', 'FND-006', 'INF-007', 'TRI-003'} <= audited, 'the uncited four'
	assert {'TRI-001', 'TRI-002', 'FND-001', 'FND-002', 'FND-004',
		'MED-001', 'MED-002', 'MED-003', 'EMG-001'} <= audited, 'the §8 Tier-1 nine'
	assert {'INF-004', 'INF-005', 'MON-001', 'MON-002', 'MON-003', 'MON-004',
		'REC-001'} <= audited, 'the Tier-2 seven'
	assert {'FND-003', 'FND-005', 'EMG-003', 'INF-006'} <= audited, 'the Tier-1 four the first pass missed'
	assert {'REC-003', 'REC-004', 'REC-005', 'REC-006', 'ALT-001', 'ALT-002',
		'MON-005', 'MON-006', 'MON-007', 'MON-008', 'MON-009'} <= audited, 'the §10 sections'
	assert {'COM-101', 'COM-102', 'COM-103', 'COM-104', 'LOC-005'} <= audited, 'the §12 sections'
	assert {'AI-001', 'AI-003', 'ACC-001', 'ACC-002', 'SEC-001', 'SEC-004',
		'SEC-006'} <= audited, 'the §12.4–§12.7 sections'
	# The eighth tranche was not a tranche anyone chose. Widening the label vocabulary moved eight
	# labels from the claim side to the content side — `Application`, `Behaviour`, `Conditions
	# supported`, `Deployment points`, `How it works`, `Privacy properties`, `Standards`, `Technical
	# approach` — and those eight were the whole of the eight sections this table called
	# contentless. They are named here as one group because they were one bug: a label filed where
	# the instrument would not look.
	assert {'EMG-002', 'LOC-002', 'LOC-003', 'LOC-004', 'ACC-003', 'ACC-004',
		'SEC-002', 'SEC-003'} <= audited, 'the sections whose labels were filed as claims'
	# The ninth tranche is the one the *pair* gate found, and it is the first tranche a count could
	# not have produced. The eight above were found by asking what the instrument could not see; this
	# one was found by asking what the instrument had read but not *finished* — 44 items sitting
	# under labels inside sections already in the table. Fixing that exposed the last fourteen
	# sections, whose content lists hang off a label that names an artefact (a `Displays`, an
	# `Entry questions`, a `Format`, a `Topics`, an `Options`, a `Targets`, a `Content`, a `User
	# rights`) rather than a feature. The first six labels the module ever knew were all
	# feature-shaped, which is why these read as sections with nothing to audit.
	assert {'INF-001', 'INF-002', 'INF-003', 'LOC-001', 'ALT-003', 'REC-002', 'COM-005',
		'INF-008', 'INF-009', 'INF-010', 'AI-002', 'ALT-004', 'ACC-005', 'SEC-005'} <= audited, \
		'the sections whose content hangs off an artefact label'
	assert len(audited) == 78, 'every section in the spec is audited exactly once'


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
	assert report.audited_features == len(audited) == 78
	assert report.unaudited_features == list(UNAUDITED_FEATURES) == []
	# 78 of 78: every `#### FID:` section in the spec prints at least one content list under a
	# label. There is no unlabelled section left to explain away, which is the version of this
	# sentence a reader can check — the earlier one said 47 of 69 and spent a paragraph accounting
	# for the other 22, and eight of those 22 were the miscategorised labels.
	#
	# The 69 was itself a fourth version of the same mistake, and the one that took longest to see
	# because the number was *right about the sections the reader could find*. The spec writes a
	# heading two ways: `#### TRI-001: Broad Febrile-Illness Triage` and `#### CHAN-0: Community
	# Radio`, whose id has one digit rather than three, plus §14.9's two sections titled in prose
	# with the id on a `**Feature ID:**` line instead of the heading. Nine sections — §5's seven
	# channels and §14.9's two sensors — were invisible to the reader, and this test derived its
	# ground truth from the *same* reader, so it could not disagree with it. A partition test whose
	# both sides come from one instrument measures the instrument, not the spec.
	assert len(labelled) == 78, 'every section in the spec prints a labelled content list'
	assert len(_spec_feature_ids()) == 78, 'the spec prints 78 feature sections' 


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
		'§ACC-001': 1,
		'§ACC-002': 1,
		# The nine sections §5 and §14.9 print and the reader could not see until it was widened.
		# Every one of these is a *content* gap rather than a device-side capability: §CHAN-0's
		# call-in and drama vignette are programmes nobody has produced, §CHAN-1's follow-up SMS is
		# a message nothing sends, and §CHAN-3's two are claims about the world (near-universal
		# reach, no app store) that no code closes. §SENS-010 has left this dict: its four NFC
		# applications name four objects that did not exist and now do, through one binding in
		# `afya.sensors.tags` — the tag names a target and the target resolves.
		'§CHAN-000': 2,
		# §CHAN-001's two were the follow-up SMS after a USSD report and the "plain language" bound.
		# Both closed and the section left this dict: the follow-up is composed at filing and sent by
		# the route through the one outbound path, and the plain-language bound measures all 183
		# outbound strings — and found one over the line (§SEC-004's pseudonym caveat, 31 words in one
		# sentence), which was fixed rather than accommodated.
		'§CHAN-003': 2,
		'§CHAN-004': 4,
		# §CHAN-005's two were the printed flip chart and the training. The training closed: the
		# content is `afya.chw.views:TRAINING_MODULES` and the per-person record is
		# `Intermediary.trained`, which `programme()` now reports as `untrained` — it was set by the
		# enrol route and read by nothing, so a programme could train nobody and every report was
		# silent. The flip chart stays: a printed artefact is genuinely not code.
		'§CHAN-005': 1,
		# §LOC-002 and §SEC-006's open-source rows were the same absence seen from two sections and
		# both closed when the owner chose a licence. The note on §LOC-002 had the reasoning right
		# while the licence was undecided — "a repository's licence is not something this tree can
		# assert about itself" — which is why the fix was the owner's decision first and the tree's
		# statement second, not a file the code wrote for itself.
		# §EMG-003, §FND-001, §FND-002, §FND-003, §FND-004, §FND-005, §TRI-001, §TRI-002 and
		# §TRI-003 are audited and carry nothing missing: every Content, Access clause, filter
		# dimension, test type and Output resolves to code, so the sections have no row here —
		# absence from this dict is the strongest verdict the audit has.
	}, per_feature


def test_med_004_can_render_its_own_example() -> None:
	"""MED-004's Features list prints "available at [pharmacy], 2 hours ago" as the thing a person
	sees, and this test used to assert the opposite: `StockReport` carried no timestamp, so no
	client could render the section's own sentence. That was the finding and it is closed, so the
	test now holds the closure rather than the gap — a report carries when it was made and an
	availability carries how old it is, and "2 hours ago" is a subtraction the server does once
	rather than every client doing with its own clock.

	The `age_hours` half matters as much as `at_iso`: §MED-004's Anti-gaming clause says "Show report
	age clearly", and a client handed an ISO string on a phone with a wrong clock prints the wrong
	age — or none at all on a phone with no clock.
	"""
	from afya.medicine.views import StockAvailability, StockReport
	assert 'at_iso' in StockReport.model_fields, 'the report must carry when it was made'
	assert {'age_hours', 'reported_at_iso'} <= set(StockAvailability.model_fields), \
		'the availability must carry the age as a number, not only the timestamp it derives from'


def test_tri_003_names_four_exposures_and_the_input_carries_them() -> None:
	"""§11.2 names funeral attendance, healthcare work, contact with a case and bushmeat consumption
	as separate inputs, and this test used to hold the opposite: `TriageInput` carried one
	`ebola_contact` boolean, so a funeral and a bushmeat exposure read identically to the classifier.

	It holds the closure now. The four are a closed vocabulary on the input, each is its own entry in
	the county team's notification, and each carries its own note — the gap was never that the words
	were absent from the tree, it was that the classifier could not tell them apart.
	"""
	from afya.triage.views import EBOLA_EXPOSURES, EXPOSURE_NOTE, TriageInput
	assert 'ebola_contact' in TriageInput.model_fields, 'the boolean stays; the four refine it'
	assert set(EBOLA_EXPOSURES) == set(EXPOSURE_NOTE), 'every route the section names has its note'
	assert len(EBOLA_EXPOSURES) == 4
	for named in ('funeral_attendance', 'healthcare_work', 'case_contact', 'bushmeat_consumption'):
		assert named in EBOLA_EXPOSURES, named
	assert 'exposures' in TriageInput.model_fields and 'isolation' in TriageInput.model_fields, \
		"§11.2's two remaining Additional inputs must have fields"


def test_the_deferred_bullets_are_the_ones_the_section_conditions_on_the_world() -> None:
	"""Seventeen bullets are deferred and they are two kinds, neither a gap. Fifteen are device
	actions — a maps app, a dialler, a barcode reader, a camera, a call-log and location permission,
	the SOS button and its auto-dial, the accelerometer stream and its "Are you OK?" prompt, a QR or
	NFC scan, the always-on microphone loop, the handset's own encrypted store and its OS keystore,
	and §MED-001's photo of the packaging — which the coverage gate's `ON_DEVICE` set already lists
	as client-side by design. The other two are conditions on the world rather than on this tree:
	TRI-003's vaccination input, written "if a vaccine is available and deployed", and ALT-002's
	check-in prompt, written "during a declared emergency in the user's area". Kept out of `missing`
	because reporting them as gaps would put a fact about vaccine deployment or about whether an
	outbreak has been declared in a defect list.

	The packaging photo is the one of the fifteen that was a `missing` row until §MED-001 was worked,
	and the reason it moved is worth stating: §MED-001's own Privacy clause says a scan is not
	transmitted unless the person reports one, and there is no OCR in this tree — so a server that
	received the image could only hand back a reading the client already had. The one case where a
	photo does travel is a report, and that path carries its hash.

	The count is asserted rather than the two kinds being described, so a bullet that moves into
	`deferred` to make a gap disappear fails here. The two world-conditioned ones are named
	individually because a deferral on a *world state* is the kind most easily abused: it is the one
	that can be claimed for a bullet that is simply unbuilt.
	"""
	from afya.content_audit.service import FEATURE_CONTENT
	deferred = [(f, b, n) for f, _, b, k, _, n in FEATURE_CONTENT if k == 'deferred']
	assert len(deferred) == 17, deferred
	world = {(f, b) for f, b, n in deferred if n is not None and 'fact about the world' in n}
	assert world == {
		('TRI-003', 'Vaccination status (if a vaccine is available and deployed)'),
		('ALT-002', "Automatic check-in prompts during a declared emergency in the user's area"),
	}, world
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
