"""Behavioural tests for retention, deletion, encryption and transparency (spec §17, SEC-003/005/006)."""
import pytest
from pydantic import ValidationError

from afya.retention.service import POLICY_RETAINED, USER_DELETABLE, RetentionService
from afya.retention.views import ENCRYPTION_STANDARD, RETENTION_TABLE, CorrectionRequest, DeletionRequest


def test_every_data_type_has_finite_window_and_trigger() -> None:
	"""The table is the contract: no data type may have an unbounded lifetime."""
	svc = RetentionService()
	policies = svc.retention_table()
	assert len(policies) == len(RETENTION_TABLE)
	assert {p.data_type for p in policies} == set(RETENTION_TABLE)
	for p in policies:
		assert p.retention_days >= 1, f'{p.data_type} has no finite window'
		assert p.deletion_trigger in ('automatic', 'user', 'policy'), f'{p.data_type} has no trigger'
		assert p.user_can_delete == (p.data_type in USER_DELETABLE)


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
	svc.record_holding('U6', 'photos', 1)  # automatic, 30 days
	assert svc.purge_expired('U6', {'photos': 31, 'triage_results': 400}) == ['photos']
	assert svc.inventory('U6').held == {}


def test_encryption_posture_reports_aes256_and_tls13() -> None:
	posture = RetentionService.encryption_posture()
	assert posture.at_rest == 'AES-256'
	assert posture.in_transit == 'TLS 1.3'
	assert posture.contact_lists_extra_layer is True
	assert posture.cloud_backup_e2e is True
	assert posture.user_held_key is True
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

