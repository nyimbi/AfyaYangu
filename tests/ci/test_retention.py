"""Behavioural tests for retention, deletion, encryption and transparency (spec §17, SEC-003/005/006)."""
import pytest
from pydantic import ValidationError

from afya.retention.service import POLICY_RETAINED, USER_DELETABLE, RetentionService
from afya.retention.views import (
	ENCRYPTION_STANDARD, RETENTION_TABLE, USER_RETAINABLE, CorrectionRequest, DeletionRequest,
)


def test_every_data_type_has_finite_window_and_trigger() -> None:
	"""The table is the contract: no data type may have an unbounded lifetime."""
	svc = RetentionService()
	policies = svc.retention_table()
	assert len(policies) == len(RETENTION_TABLE)
	assert {p.data_type for p in policies} == set(RETENTION_TABLE)
	for p in policies:
		assert p.retention_days >= 1, f'{p.data_type} has no finite window'
		assert p.deletion_trigger in (
			'automatic', 'automatic_unless_retained', 'user', 'policy'), f'{p.data_type} has no trigger'
		assert p.user_can_delete == (p.data_type in USER_DELETABLE)
		# Every row carries §SEC-005's own two cells, so a client can render the section's promise
		# rather than this build's derived number.
		# A §SEC-005 row carries the section's own two cells; a row this build adds beyond the
		# section carries none, so an addition cannot be mistaken for a stated requirement.
		assert bool(p.stated) == bool(p.stated_trigger), f'{p.data_type} carries half a stated row'
		assert p.user_may_retain == (p.data_type in USER_RETAINABLE)


def test_every_retention_cell_is_the_sections_own() -> None:
	"""§SEC-005's nine rows, read off `docs/spec.md` rather than from the table they check.

	The table carried day counts with nothing comparing them to the section, which is how `photos`
	came to say `{'days': 30, 'trigger': 'automatic'}` against a row reading "Until clinical review
	complete" / "Automatic **unless user retains**". Both halves of the drift were load-bearing: the
	30 is a window the section does not state, and the plain `automatic` made `purge_expired` delete
	a photo the person had chosen to keep — the one thing the trigger cell carves out.

	The reader takes the section's own cells, so a row reworded in the spec fails here rather than
	passing against a constant that was edited to match.
	"""
	import pathlib
	import re
	spec = pathlib.Path(__file__).resolve().parents[2] / 'docs' / 'spec.md'
	block = spec.read_text().split('#### SEC-005')[1].split('#### SEC-006')[0]
	rows = {}
	for line in block.splitlines():
		if line.startswith('|') and '---' not in line and not line.startswith('| Data type'):
			cells = [c.strip() for c in line.strip('|').split('|')]
			if len(cells) == 3:
				rows[cells[0]] = (cells[1], cells[2])
	assert len(rows) == 9, rows

	def slug(label: str) -> str:
		# The section's human label, turned into the table's key by a rule rather than a name list —
		# a mapping kept by hand is the artefact that drifts. "Proximity tokens (PET)" drops the
		# parenthetical because the section is naming the same PET token row.
		return re.sub(r'[^a-z0-9]+', '_', re.sub(r'\s*\([^)]*\)', '', label).lower()).strip('_')

	svc = RetentionService()
	by_slug = {p.data_type: p for p in svc.retention_table()}
	missing = sorted(slug(label) for label in rows if slug(label) not in by_slug)
	assert not missing, f'§SEC-005 rows with no policy: {missing}'
	for label, (retention, trigger) in rows.items():
		policy = by_slug[slug(label)]
		assert policy.stated == retention, f'{label}: Retention cell drifted'
		assert policy.stated_trigger == trigger, f'{label}: trigger cell drifted'
		# §SEC-005 states a number for seven rows; the other two are events, and the row says so.
		stated_days = re.fullmatch(r'(\d+) days?(?: rolling)?', retention)
		if stated_days:
			assert policy.retention_days == int(stated_days.group(1)), f'{label}: window drifted'
			assert policy.within_statement, f'{label}: derived window is the stated one'
		else:
			assert not policy.within_statement, f'{label}: the section states an event, not a window'
	# A row beyond the section's nine says so by carrying no stated cells.
	for p in svc.retention_table():
		if p.data_type not in {slug(label) for label in rows}:
			assert p.stated == '' and p.stated_trigger == '', \
				f'{p.data_type} is not a §SEC-005 row but carries stated cells'

	# Where the section states an event rather than a number, this build has had to choose a window —
	# and §SEC-005 names no figure for these four, so the choice is this build's reading rather than
	# the section's claim. Pinned here as a literal because it is *served*: `/retention/policy` hands
	# a client "30 days" for a photo, and a number that can drift silently is a promise nobody made.
	# A changed reading is a deliberate edit to this dict, which is what the pin is for.
	DERIVED_WHERE_THE_SECTION_STATES_AN_EVENT = {
		'contact_lists': 21, 'case_reports': 3650, 'immunisation_records': 36500, 'photos': 30,
	}
	for data_type, days in DERIVED_WHERE_THE_SECTION_STATES_AN_EVENT.items():
		policy = by_slug[data_type]
		assert not policy.within_statement, f'{data_type} should state an event, not a window'
		assert policy.retention_days == days, (
			f'{data_type}: the derived window drifted from {days} to {policy.retention_days}')

	# The carve-out is the finding, so it is asserted by name rather than through the loop.
	photos = next(p for p in svc.retention_table() if p.data_type == 'photos')
	assert photos.user_may_retain, 'the "unless user retains" carve-out is not carried'
	assert not svc.is_automatic('photos'), 'a photo the person kept is still on an automatic clock'


def test_a_retained_photo_is_not_purged_by_the_automatic_clock() -> None:
	"""§SEC-005: Photos is "Automatic unless user retains".

	`purge_expired` compared the trigger to the string `'automatic'`, so the carve-out had no effect
	and a photo the person had chosen to keep was destroyed at the derived window — a deletion the
	section explicitly does not authorise, performed by the code that exists to enforce it.
	"""
	svc = RetentionService()
	svc.record_holding('U7', 'photos', 1)
	svc.record_holding('U7', 'symptom_logs', 1)
	expired = svc.purge_expired('U7', {'photos': 4000, 'symptom_logs': 4000})
	assert expired == ['symptom_logs'], 'the automatic clock fired on a retainable photo'
	assert svc.inventory('U7').held == {'photos': 1}, 'a kept photo was deleted'
	# And the inventory's "next automatic deletion" must not name a window that cannot fire.
	assert svc.inventory('U7').earliest_auto_delete_in_days is None


def test_unknown_data_type_is_refused() -> None:
	"""A type the table does not define cannot be granted a window — the refusal is the safety."""
	svc = RetentionService()
	with pytest.raises(AssertionError, match='no retention window defined'):
		svc.policy_for('dna_sequencing')
	with pytest.raises(AssertionError):
		svc.record_holding('U1', 'dna_sequencing', 1)
	assert svc.inventory('U1').held == {}, 'a refused holding stores nothing'


async def test_delete_of_unknown_data_type_is_refused() -> None:
	svc = RetentionService()
	svc.record_holding('U8', 'symptom_logs', 1)
	with pytest.raises(AssertionError, match='no retention window defined'):
		await svc.delete(DeletionRequest(subject_ref='U8', data_type='dna_sequencing'))
	assert svc.inventory('U8').held == {'symptom_logs': 1}, 'a refused delete changes nothing'


async def test_blanket_delete_removes_user_data_keeps_case_and_consent() -> None:
	svc = RetentionService()
	for t in ('symptom_logs', 'triage_results', 'case_reports', 'consent_records'):
		svc.record_holding('U2', t, 3)

	receipt = await svc.delete(DeletionRequest(subject_ref='U2'))

	assert receipt.deleted_types == ['symptom_logs', 'triage_results']
	assert receipt.retained_types == ['case_reports', 'consent_records']
	assert receipt.retention_reason == 'Case reports and consent records are kept under a legal obligation.'
	assert 'Kept case_reports, consent_records because the law requires it.' in receipt.message
	# the receipt names what survived, and the survivors really are still held
	remaining = svc.inventory('U2').held
	assert set(remaining) == set(POLICY_RETAINED)
	assert remaining == {'case_reports': 3, 'consent_records': 3}


async def test_the_retention_reason_names_only_what_is_actually_kept() -> None:
	"""`retention_reason` asserted both types whenever either was kept.

	`POLICY_RETAINED` holds two types, and the blanket branch reached for one fixed sentence for any
	non-empty `retained` — so a person holding only case reports was told their consent records were
	also being kept under a legal obligation. The receipt's own `message` interpolated the real set,
	so the two prose fields disagreed. Each count is asserted against the set the receipt carries,
	rather than against a wording, because the defect was the sentence describing a different set
	from the one beside it.
	"""
	svc = RetentionService()
	svc.record_holding('U-only-case', 'case_reports', 2)
	svc.record_holding('U-only-case', 'symptom_logs', 1)

	receipt = await svc.delete(DeletionRequest(subject_ref='U-only-case'))
	assert receipt.retained_types == ['case_reports']
	assert 'consent records' not in receipt.retention_reason, receipt.retention_reason
	assert 'Case reports is kept under a legal obligation.' == receipt.retention_reason
	# The two fields must describe the same set; that is the property, not the phrasing.
	for t in receipt.retained_types:
		assert t.replace('_', ' ') in receipt.retention_reason.lower(), receipt.retention_reason

	# And the other single-type case, so the fix is not one hardcoded sentence swapped for another.
	svc.record_holding('U-only-consent', 'consent_records', 4)
	other = await svc.delete(DeletionRequest(subject_ref='U-only-consent'))
	assert other.retained_types == ['consent_records']
	assert 'case reports' not in other.retention_reason.lower(), other.retention_reason
	assert other.retention_reason != receipt.retention_reason, 'two sets, one sentence again'


async def test_single_type_delete_removes_only_that_type() -> None:
	svc = RetentionService()
	svc.record_holding('U3', 'symptom_logs', 4)
	svc.record_holding('U3', 'photos', 2)

	receipt = await svc.delete(DeletionRequest(subject_ref='U3', data_type='symptom_logs', channel='ussd'))

	assert receipt.deleted_types == ['symptom_logs']
	assert receipt.retained_types == []
	assert svc.inventory('U3').held == {'photos': 2}


async def test_deleting_policy_retained_type_is_refused_with_legal_reason() -> None:
	svc = RetentionService()
	svc.record_holding('U4', 'case_reports', 7)

	receipt = await svc.delete(DeletionRequest(subject_ref='U4', data_type='case_reports'))

	assert receipt.deleted_types == []
	assert receipt.retained_types == ['case_reports']
	assert 'legal obligation' in receipt.retention_reason
	assert 'notifiable disease' in receipt.retention_reason
	assert 'cannot be deleted on request' in receipt.message
	assert svc.inventory('U4').held == {'case_reports': 7}, 'policy-retained data survives'


def test_purge_expired_fires_only_automatic_clocks() -> None:
	"""Manual (`user`) and policy clocks must not fire on their own."""
	svc = RetentionService()
	svc.record_holding('U5', 'symptom_logs', 1)          # automatic, 90 days
	svc.record_holding('U5', 'location_history', 1)      # automatic, 21 days
	svc.record_holding('U5', 'case_reports', 1)          # policy, 3650 days
	svc.record_holding('U5', 'immunisation_records', 1)  # user, 36500 days

	expired = svc.purge_expired('U5', {
		'symptom_logs': 100, 'location_history': 5, 'case_reports': 99999, 'immunisation_records': 99999,
	})

	assert expired == ['symptom_logs']
	held = svc.inventory('U5').held
	assert set(held) == {'location_history', 'case_reports', 'immunisation_records'}


def test_purge_expired_ignores_types_not_held() -> None:
	svc = RetentionService()
	# `photos` is used here for its *absence* from the held set: it is retainable, so the clock
	# does not fire on it and the type that is not held is the one the call must ignore.
	svc.record_holding('U6', 'symptom_logs', 1)
	assert svc.purge_expired('U6', {'photos': 4000, 'triage_results': 400}) == []
	assert svc.inventory('U6').held == {'symptom_logs': 1}


def test_encryption_posture_reports_what_is_deployed_not_what_is_intended() -> None:
	"""The posture is a report, so it must be able to say `none`.

	This test used to assert three hardcoded `True`s — it pinned the claim rather than the control,
	which is why §SEC-003's row stayed `missing` while the posture said everything was in place. A
	deployment with no crypto service reports plaintext; one with an at-rest key reports AES-256 but
	no second layer for contact lists; only one holding *both* keys reports the extra layer.
	"""
	svc = RetentionService()
	bare = svc.encryption_posture()
	assert bare.at_rest == 'none', 'no key, no AES-256 — the posture must be able to say so'
	assert bare.contact_lists_extra_layer is False
	assert bare.cloud_backup_e2e is False and bare.user_held_key is False
	assert bare.in_transit == 'TLS 1.3'

	from afya.crypto.service import CryptoService, new_key
	at_only = svc.encryption_posture(CryptoService(new_key()))
	assert at_only.at_rest == 'AES-256'
	assert at_only.contact_lists_extra_layer is False, 'one key fitted twice is not two layers'

	both = svc.encryption_posture(CryptoService(new_key(), new_key()))
	assert both.at_rest == 'AES-256' and both.contact_lists_extra_layer is True

	standard = RetentionService.standard()
	assert standard == ENCRYPTION_STANDARD
	assert 'AES-256' in standard and 'TLS 1.3' in standard


def test_transparency_report_carries_suppression_and_raw_sensor_notes() -> None:
	svc = RetentionService()
	svc.record_holding('U7', 'symptom_logs', 5)
	svc.record_share('U7', 'KEMRI', 'aggregated symptom counts', '2026-10-01T00:00:00Z')

	report = svc.transparency_report('2026-Q3', subject_ref='U7')

	assert report.period == '2026-Q3'
	assert {'data_type': 'symptom_logs', 'records': 5} in report.rows
	assert {'shared_with': 'KEMRI', 'what': 'aggregated symptom counts', 'when': '2026-10-01T00:00:00Z'} in report.rows
	assert any('Raw sensor data never leaves the handset' in n for n in report.notes)
	assert any('suppresses any cell below 10 people' in n for n in report.notes)


def test_transparency_report_requires_period() -> None:
	with pytest.raises(AssertionError, match='reporting period required'):
		RetentionService().transparency_report('')


def test_export_returns_everything_held_and_names_what_it_leaves_out() -> None:
	"""§SEC-005 "export all personal data at any time" — a right with no route is not a right.

	The export must agree with the dashboard (same register), and must not read as more complete
	than it is: an incomplete export a person hands to a regulator is worse than none.
	"""
	svc = RetentionService()
	svc.record_holding('U9', 'symptom_logs', 4)
	svc.record_holding('U9', 'photos', 2)
	svc.record_share('U9', 'Nairobi PHEOC', 'symptom counts', '2026-10-01T09:00:00Z')
	out = svc.export('U9', at_iso='2026-10-10T12:00:00Z', channel='native')
	assert out.holdings == svc.inventory('U9').held == {'symptom_logs': 4, 'photos': 2}
	assert out.shared_with == svc.inventory('U9').shared_with
	assert out.exported_at_iso == '2026-10-10T12:00:00Z' and out.channel == 'native'
	assert out.caveats, 'an export must state what it does not contain'
	assert any('never leave the handset' in c for c in out.caveats)
	# Another subject's holdings never appear.
	assert svc.export('U10', at_iso='2026-10-10T12:00:00Z').holdings == {}


def test_export_requires_the_moment_it_was_taken() -> None:
	svc = RetentionService()
	with pytest.raises(AssertionError, match='must carry the moment'):
		svc.export('U9', at_iso='')


# --- §17.2 accuracy: "user data editable; correction workflows" ---------------------------------

def _correction(**over: object) -> CorrectionRequest:
	base: dict[str, object] = {
		'subject_ref': 'U9', 'data_type': 'symptom_logs', 'field': 'age',
		'corrected_value': '31', 'reason': 'I mistyped my age', 'corrected_by': 'U9',
	}
	base.update(over)
	return CorrectionRequest(**base)  # type: ignore[arg-type]


async def test_a_correction_keeps_what_it_replaced() -> None:
	"""§17.2 says user data is editable and names a *workflow*, which is a different thing from an
	overwrite. A correction that destroyed what it corrected would leave a record that agrees with
	itself and with nothing else — and "what did we tell them, and on what basis" stops being
	answerable exactly when it matters, after a wrong reading has driven a triage verdict."""
	svc = RetentionService()
	first = await svc.correct(_correction(corrected_value='31'), at_iso='2026-10-12T08:00:00Z')
	assert first.previous_value is None, 'nothing was there before the first correction'
	second = await svc.correct(_correction(corrected_value='32'), at_iso='2026-10-12T09:00:00Z')
	assert second.previous_value == '31', 'the value it replaced is the one the last correction set'
	history = svc.corrections('U9')
	assert [c['corrected_value'] for c in history] == ['31', '32']
	assert all(c['at_iso'] for c in history), 'a correction with no time is not a history'
	assert svc.corrections('U10') == [], "another subject's corrections never appear"


async def test_a_correction_is_scoped_to_a_data_type_and_a_field() -> None:
	"""Two fields of one data type are two corrections, and a correction to one does not report the
	other as its predecessor — the `previous_value` chain is per field, which is what makes the
	history readable rather than a list of unrelated writes."""
	svc = RetentionService()
	await svc.correct(_correction(field='age', corrected_value='31'), at_iso='2026-10-12T08:00:00Z')
	other = await svc.correct(_correction(field='county', corrected_value='Kisumu'), at_iso='2026-10-12T08:05:00Z')
	assert other.previous_value is None, 'a different field has its own history'
	assert len(svc.corrections('U9')) == 2


async def test_an_untracked_data_type_cannot_be_corrected() -> None:
	"""The retention table is the contract for what may be held, and a correction writes to a
	holding. A type with no window is a type the deployment does not track, so a correction against
	one would create a record that no retention rule governs."""
	svc = RetentionService()
	with pytest.raises(AssertionError, match='not a retention-tracked data type'):
		await svc.correct(_correction(data_type='dna_sequencing'), at_iso='2026-10-12T08:00:00Z')
	assert svc.corrections('U9') == [], 'a refused correction writes nothing'


async def test_a_correction_must_say_who_made_it_and_why() -> None:
	"""§17.1 puts accountability on the ODPC guidance note and §17.2's accuracy row is the same
	duty from the other side. A correction attributed to nobody is a record that changed itself.

	Two layers refuse it, and the test names both: the model refuses an empty `reason` or
	`corrected_by` at construction, and the service refuses an empty corrected value, which the
	model leaves unconstrained because a field's empty string is a legitimate value to *hold* and
	not a legitimate thing to *write* as a correction.
	"""
	svc = RetentionService()
	with pytest.raises(ValidationError):
		_correction(reason='')
	with pytest.raises(ValidationError):
		_correction(corrected_by='')
	with pytest.raises(AssertionError):
		await svc.correct(_correction(corrected_value=''), at_iso='2026-10-12T08:00:00Z')
	assert svc.corrections('U9') == []



def test_the_policy_route_serves_the_sections_own_cells() -> None:
	"""§SEC-005 through the front door: a client renders the section's promise, not this build's number.

	`/retention/policy` is the surface `retention_policy` in the mobile catalogue calls, so it is where
	a person's "how long is my data kept" answer is read. Before this, the route served a `photos` row
	reading `30 days` / `automatic` — neither of which is what §SEC-005 says, and the second of which
	is the deletion of a photo the person chose to keep.
	"""
	from fastapi.testclient import TestClient
	from afya.service import build_services, create_app
	client = TestClient(create_app(build_services()))
	res = client.get('/retention/policy')
	assert res.status_code == 200, res.text
	rows = {r['data_type']: r for r in res.json()}
	assert len(rows) == len(RETENTION_TABLE)

	photos = rows['photos']
	assert photos['stated'] == 'Until clinical review complete', photos
	assert photos['stated_trigger'] == 'Automatic unless user retains', photos
	assert photos['user_may_retain'] is True, photos
	assert photos['within_statement'] is False, 'the section states an event, not a 30-day window'

	symptom = rows['symptom_logs']
	assert symptom['stated'] == '90 days' and symptom['within_statement'] is True, symptom
	# Among the rows §SEC-005 states, the two whose Retention cell is an event are the only ones that
	# report a disagreement. `consent_records` is not a §SEC-005 row at all — it carries no stated
	# cells — so it is out of this comparison rather than counted as a fourth disagreement.
	# The rule, not a list: a row agrees with the section exactly when the section's Retention cell
	# is the number of days this build enforces. Four rows state an event or a policy instead, and
	# they report the disagreement — which is the point of the field.
	import re as _re
	stated_rows = [r for r in rows.values() if r['stated']]
	for r in stated_rows:
		stated_days = _re.fullmatch(r'(\d+) days?(?: rolling)?', r['stated'])
		assert r['within_statement'] == bool(stated_days), (
			f"{r['data_type']}: stated {r['stated']!r} against {r['retention_days']} days")
	# And the four that do not agree are the ones the section states as an event, a policy or a
	# lifetime — the set is asserted so a fifth row cannot start disagreeing unnoticed.
	assert sorted(r['data_type'] for r in stated_rows if not r['within_statement']) == [
		'case_reports', 'contact_lists', 'immunisation_records', 'photos']
