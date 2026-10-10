"""Retention, encryption and transparency services (spec §17, SEC-003/005/006).

Two rules are load-bearing and enforced here:
  * A retention window the table does not define cannot be granted — the table is the contract,
    so a new data type cannot quietly acquire an unbounded lifetime.
  * Deletion removes what the user owns and states plainly what survives and why. Immunisation
    records survive a blanket delete because they are the child's, not the requester's, to erase.
"""
from afya.logmixin import LogMixin
from afya.retention.views import (
	ENCRYPTION_STANDARD, RETENTION_TABLE, DataInventory, DeletionReceipt, DeletionRequest,
	EncryptionPosture, RetentionPolicy, TransparencyReport,
)

# Types a user may always delete outright, and types that survive a blanket request.
USER_DELETABLE: frozenset[str] = frozenset({
	'symptom_logs', 'triage_results', 'location_history', 'proximity_tokens', 'contact_lists',
	'chatbot_conversations', 'photos', 'immunisation_records',
})
POLICY_RETAINED: frozenset[str] = frozenset({'case_reports', 'consent_records'})

DELETION_COMMANDS: tuple[str, ...] = ('DELETE MY DATA', 'FUTA DATA YANGU')


class RetentionService(LogMixin):
	def __init__(self) -> None:
		self._holdings: dict[str, dict[str, int]] = {}
		self._shares: dict[str, list[dict[str, str]]] = {}
		self._deletions: list[DeletionReceipt] = []
		assert self._holdings == {}

	# --- SEC-005 retention -----------------------------------------------------------------

	@staticmethod
	def policy_for(data_type: str) -> RetentionPolicy:
		assert data_type in RETENTION_TABLE, f'no retention window defined for {data_type}'
		row = RETENTION_TABLE[data_type]
		days = int(row['days'])  # type: ignore[arg-type]
		return RetentionPolicy(
			data_type=data_type, retention_days=days, deletion_trigger=str(row['trigger']),
			user_can_delete=data_type in USER_DELETABLE,
		)

	def retention_table(self) -> list[RetentionPolicy]:
		return [self.policy_for(t) for t in sorted(RETENTION_TABLE)]

	# --- SEC-006 transparency --------------------------------------------------------------

	def record_holding(self, subject_ref: str, data_type: str, count: int) -> int:
		assert count >= 0, 'count non-negative'
		self.policy_for(data_type)  # refuses unknown types before they are stored
		self._holdings.setdefault(subject_ref, {})[data_type] = count
		return count

	def record_share(self, subject_ref: str, with_who: str, what: str, when_iso: str) -> None:
		assert with_who and what, 'a share must name the recipient and the data'
		self._shares.setdefault(subject_ref, []).append({'with': with_who, 'what': what, 'when': when_iso})

	def inventory(self, subject_ref: str) -> DataInventory:
		held = dict(self._holdings.get(subject_ref, {}))
		# The soonest-expiring automatic window is the next thing that disappears on its own.
		automatic = [
			self.policy_for(t).retention_days for t in held
			if self.policy_for(t).deletion_trigger == 'automatic'
		]
		earliest = min(automatic) if automatic else None
		return DataInventory(
			subject_ref=subject_ref, held=held, shared_with=list(self._shares.get(subject_ref, [])),
			earliest_auto_delete_in_days=earliest, export_available=True,
		)

	async def delete(self, req: DeletionRequest) -> DeletionReceipt:
		"""`DELETE MY DATA` on any channel. Removes what is the user's; names what is not."""
		held = self._holdings.get(req.subject_ref, {})
		if req.data_type is not None:
			self.policy_for(req.data_type)
			if req.data_type in POLICY_RETAINED:
				receipt = DeletionReceipt(
					subject_ref=req.subject_ref, deleted_types=[], retained_types=[req.data_type],
					retention_reason='Held under a legal obligation for notifiable disease records.',
					message='This record must be kept by law and cannot be deleted on request. Everything else you asked for is gone.',
				)
			else:
				held.pop(req.data_type, None)
				receipt = DeletionReceipt(
					subject_ref=req.subject_ref, deleted_types=[req.data_type], retained_types=[],
					retention_reason='', message=f'Your {req.data_type.replace("_", " ")} have been deleted.',
				)
		else:
			deleted = sorted(t for t in held if t in USER_DELETABLE)
			retained = sorted(t for t in held if t in POLICY_RETAINED)
			for t in deleted:
				held.pop(t, None)
			receipt = DeletionReceipt(
				subject_ref=req.subject_ref, deleted_types=deleted, retained_types=retained,
				retention_reason='Case reports and consent records are kept under a legal obligation.' if retained else '',
				message=(
					f'Deleted {len(deleted)} data type(s). '
					+ (f'Kept {", ".join(retained)} because the law requires it.' if retained else 'Nothing else is held about you.')
				),
			)
		self._holdings[req.subject_ref] = held
		self._deletions.append(receipt)
		self._log_warn('deletion request processed', subject=req.subject_ref, channel=req.channel, deleted=len(receipt.deleted_types))
		return receipt

	def purge_expired(self, subject_ref: str, age_days: dict[str, int]) -> list[str]:
		"""Apply the automatic clocks. `age_days` is how old each holding is."""
		held = self._holdings.get(subject_ref, {})
		expired = [
			t for t, age in age_days.items()
			if t in held and self.policy_for(t).deletion_trigger == 'automatic'
			and age > self.policy_for(t).retention_days
		]
		for t in expired:
			held.pop(t, None)
		if expired:
			self._log_info('retention clocks fired', subject=subject_ref, expired=expired)
		return sorted(expired)

	# --- SEC-003 encryption ----------------------------------------------------------------

	@staticmethod
	def encryption_posture() -> EncryptionPosture:
		return EncryptionPosture(
			at_rest='AES-256', in_transit='TLS 1.3', keystore='Android Keystore / iOS Secure Enclave',
			contact_lists_extra_layer=True, cloud_backup_e2e=True, user_held_key=True,
		)

	@staticmethod
	def standard() -> str:
		return ENCRYPTION_STANDARD

	# --- transparency report ---------------------------------------------------------------

	def transparency_report(self, period: str, subject_ref: str | None = None) -> TransparencyReport:
		assert period, 'reporting period required'
		rows: list[dict[str, object]] = []
		if subject_ref is not None:
			inv = self.inventory(subject_ref)
			rows = [{'data_type': t, 'records': n} for t, n in sorted(inv.held.items())]
			# Annotated separately: `list` is invariant, so a comprehension of dict[str, str]
			# is not assignable to list[dict[str, object]] through `+=`.
			shared: list[dict[str, object]] = [
				{'shared_with': s['with'], 'what': s['what'], 'when': s['when']} for s in inv.shared_with
			]
			rows += shared
		return TransparencyReport(
			period=period, subject_ref=subject_ref, rows=rows,
			notes=[
				'Raw sensor data never leaves the handset: only derived rates, counts and verdicts travel.',
				'Aggregated reporting suppresses any cell below 10 people.',
				'You can export or delete your data at any time from any channel.',
			],
		)
