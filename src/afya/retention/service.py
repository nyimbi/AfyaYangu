"""Retention, encryption and transparency services (spec §17, SEC-003/005/006).

Two rules are load-bearing and enforced here:
  * A retention window the table does not define cannot be granted — the table is the contract,
    so a new data type cannot quietly acquire an unbounded lifetime.
  * Deletion removes what the user owns and states plainly what survives and why. Immunisation
    records survive a blanket delete because they are the child's, not the requester's, to erase.
"""
from datetime import date, timedelta

from afya.analytics.views import MIN_CELL_SIZE, MetricRow
from afya.licensing import licence_offer
from afya.logmixin import LogMixin
from afya.retention.views import (
	ENCRYPTION_STANDARD, QUARTERLY_CADENCE_DAYS, RETENTION_TABLE, USER_RETAINABLE, CorrectionReceipt,
	CorrectionRequest, DataInventory, DeletionReceipt, DeletionRequest, EncryptionPosture,
	PersonalDataExport, PublicationSchedule, PublicationStatus, RetentionPolicy,
	TransparencyPublication, TransparencyReport, TransparencySection,
)

# Types a user may always delete outright, and types that survive a blanket request.
USER_DELETABLE: frozenset[str] = frozenset({
	'symptom_logs', 'triage_results', 'location_history', 'proximity_tokens', 'contact_lists',
	'chatbot_conversations', 'photos', 'immunisation_records',
})
POLICY_RETAINED: frozenset[str] = frozenset({'case_reports', 'consent_records'})

DELETION_COMMANDS: tuple[str, ...] = ('DELETE MY DATA', 'FUTA DATA YANGU')


def _kept_reason(retained: list[str]) -> str:
	"""The legal-obligation sentence, naming the types that are actually kept.

	It named both — "Case reports and consent records are kept under a legal obligation" — whenever
	`retained` was non-empty, so a person holding only case reports was told their consent records
	were also being kept. The sibling `message` on the same receipt interpolated the real set, so the
	two prose fields in one object disagreed about what survived the request.
	"""
	if not retained:
		return ''
	named = ' and '.join(t.replace('_', ' ') for t in retained)
	return f'{named.capitalize()} {"is" if len(retained) == 1 else "are"} kept under a legal obligation.'


class RetentionService(LogMixin):
	def __init__(self) -> None:
		self._holdings: dict[str, dict[str, int]] = {}
		self._shares: dict[str, list[dict[str, str]]] = {}
		self._deletions: list[DeletionReceipt] = []
		# The current value of each (data_type, field) a subject has corrected, and the log of the
		# corrections that produced it. Both are needed: the log is the workflow a person can read,
		# and the current value is what a second correction reports as `previous_value`.
		self._values: dict[str, dict[tuple[str, str], str]] = {}
		self._corrections: list[dict[str, object]] = []
		# §SEC-006's public record. The periods actually published, the breach notices a deployment
		# has filed, and the source reads the publication draws on. `_sources` is injectable because
		# a publication that could only be produced by a live deployment is a publication no test and
		# no reviewer can check — the same reason §19.4's builders are overridable reads.
		self._publications: dict[str, str] = {}
		self._breaches: list[dict[str, object]] = []
		self._sources: dict[str, object] | None = None
		assert self._holdings == {} and self._publications == {}

	# --- SEC-005 retention -----------------------------------------------------------------

	@staticmethod
	def policy_for(data_type: str) -> RetentionPolicy:
		assert data_type in RETENTION_TABLE, f'no retention window defined for {data_type}'
		row = RETENTION_TABLE[data_type]
		days = int(row['days'])  # type: ignore[arg-type]
		stated = str(row['stated'])
		trigger = str(row['trigger'])
		return RetentionPolicy(
			data_type=data_type, retention_days=days, deletion_trigger=trigger,
			user_can_delete=data_type in USER_DELETABLE,
			stated=stated, stated_trigger=str(row['stated_trigger']),
			user_may_retain=data_type in USER_RETAINABLE,
			# The section's Retention cell is a number of days for seven of its nine rows and an
			# *event* for two — Photos is "Until clinical review complete" and Contact lists is
			# "Until tracing window closes". Where it is an event this build holds a derived window
			# and no clock for the event, and the two are not the same claim, so the row reports the
			# disagreement rather than a 30 that reads as the section's own figure.
			within_statement=stated.startswith(f'{days} day'),
		)

	@staticmethod
	def is_automatic(data_type: str) -> bool:
		"""Whether §SEC-005's clock runs on age for this type, carve-out included.

		`automatic_unless_retained` is a clock with a condition, and the condition is the person's own
		choice — so it is *not* automatic here. Every caller that asked
		`deletion_trigger == 'automatic'` was asking "does this disappear on its own", and for a photo
		the person chose to keep the answer is no. The plain string comparison answered yes, which is
		how a kept photo got purged.
		"""
		assert data_type in RETENTION_TABLE, f'no retention window defined for {data_type}'
		return RETENTION_TABLE[data_type]['trigger'] == 'automatic'

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
			self.policy_for(t).retention_days for t in held if self.is_automatic(t)
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
				retention_reason=_kept_reason(retained),
				message=(
					f'Deleted {len(deleted)} data type(s). '
					+ (f'Kept {", ".join(retained)} because the law requires it.' if retained else 'Nothing else is held about you.')
				),
			)
		self._holdings[req.subject_ref] = held
		self._deletions.append(receipt)
		self._log_warn('deletion request processed', subject=req.subject_ref, channel=req.channel, deleted=len(receipt.deleted_types))
		return receipt

	def export(self, subject_ref: str, at_iso: str, channel: str = 'native') -> PersonalDataExport:
		"""§SEC-005: everything held about a subject, with what it does not contain stated plainly.

		Built from the same register the dashboard reads, so the two cannot disagree. The caveats are
		not decoration: an export a person hands to a regulator must not read as more complete than it
		is, and the raw sensor streams never left the handset to be exported in the first place.
		"""
		assert at_iso, 'an export must carry the moment it was taken'
		inv = self.inventory(subject_ref)
		deletions = [
			{'deleted_types': ', '.join(d.deleted_types) or 'none', 'retained_types': ', '.join(d.retained_types) or 'none'}
			for d in self._deletions if d.subject_ref == subject_ref
		]
		caveats = [
			'Raw sensor streams (microphone, camera, accelerometer) never leave the handset; only derived '
			'rates, counts and verdicts are held, and those appear above as counts.',
			'This export covers data this service holds about you. Case reports and consent records kept '
			'under a legal obligation are named where they are held but their contents are not included.',
		]
		self._log_info('personal data exported', subject=subject_ref, channel=channel, types=len(inv.held))
		return PersonalDataExport(
			subject_ref=subject_ref, exported_at_iso=at_iso, channel=channel,
			holdings=inv.held, shared_with=inv.shared_with, deletions=deletions, caveats=caveats,
		)

	def purge_expired(self, subject_ref: str, age_days: dict[str, int]) -> list[str]:
		"""Apply the automatic clocks. `age_days` is how old each holding is."""
		held = self._holdings.get(subject_ref, {})
		expired = [
			t for t, age in age_days.items()
			if t in held and self.is_automatic(t) and age > self.policy_for(t).retention_days
		]
		for t in expired:
			held.pop(t, None)
		if expired:
			self._log_info('retention clocks fired', subject=subject_ref, expired=expired)
		return sorted(expired)

	# --- SEC-003 encryption ----------------------------------------------------------------

	def encryption_posture(self, crypto: object | None = None) -> EncryptionPosture:
		"""§SEC-003's posture, read off the wired crypto service instead of asserted.

		This method used to return three hardcoded `True`s, and the audit row said so: the standard
		was stated and applied nowhere. A posture that cannot be false is not a report. Each flag is
		now the answer to a question the deployment can fail:

		* `at_rest` is AES-256 only when a key exists to encrypt with, so a store writing plaintext
		  reports plaintext.
		* `contact_lists_extra_layer` is true only when the *second* key is configured — the layer
		  §SEC-003 asks for is a distinct key, and one key fitted twice is not two layers.
		* `cloud_backup_e2e` and `user_held_key` are true only when a user-held backup can actually
		  be produced, which needs a passphrase the deployment does not keep. Until the backup route
		  accepts one, both stay false and the gap is visible here rather than in a neighbouring
		  module's docstring.

		`crypto=None` reports the undeployed posture rather than the design intent, because a caller
		with no crypto service is a deployment that has not enabled any of it.
		"""
		at_rest = 'AES-256' if crypto is not None and getattr(crypto, 'available', False) else 'none'
		app_layer = crypto is not None and bool(getattr(crypto, 'has_app_layer', False))
		return EncryptionPosture(
			at_rest=at_rest, in_transit='TLS 1.3', keystore='Android Keystore / iOS Secure Enclave',
			contact_lists_extra_layer=app_layer,
			# The backup is end-to-end only when a user-held key exists, which the crypto service
			# cannot answer on its own — the route must be handed a passphrase. `RecordsService.backup`
			# sets these on the envelope it returns; here they report the deployment default.
			cloud_backup_e2e=False, user_held_key=False,
		)

	@staticmethod
	def standard() -> str:
		return ENCRYPTION_STANDARD

	# --- correction workflow (§17.2 accuracy) ------------------------------------------------

	async def correct(self, req: CorrectionRequest, at_iso: str) -> CorrectionReceipt:
		"""Apply a correction and keep what was replaced.

		§17.2 says "user data editable; correction workflows", and §17.1 hangs the same duty on the
		ODPC guidance note's accuracy principle. Two rules make this a correction rather than an
		overwrite.

		The old value is kept. A correction that destroyed what it corrected would leave a record
		that agrees with itself and with nothing else — the state a person is in when a wrong
		reading has already driven a triage verdict, and the one where "what did we tell them, and
		on what basis" stops being answerable.

		The correction is scoped to a data type and a field. `case_reports` is in
		`POLICY_RETAINED`, not `USER_DELETABLE`, and that is not a contradiction: §17.2's
		lawfulness row makes mandatory disease notification a legal obligation rather than a
		consent, so a subject may correct their own demographic fields and may not rewrite the
		clinical content of a notification the Public Health Act requires be filed. What they can
		correct there is bounded by the same rule that lets the report exist without their consent.
		"""
		assert req.subject_ref and req.field and req.corrected_value != '', 'a correction needs a subject, a field and a value'
		assert req.data_type in RETENTION_TABLE, f'{req.data_type} is not a retention-tracked data type'
		previous = self._values.get(req.subject_ref, {}).get((req.data_type, req.field))
		self._values.setdefault(req.subject_ref, {})[(req.data_type, req.field)] = req.corrected_value
		self._corrections.append({
			'subject_ref': req.subject_ref, 'data_type': req.data_type, 'field': req.field,
			'previous_value': previous, 'corrected_value': req.corrected_value,
			'corrected_by': req.corrected_by, 'at_iso': at_iso, 'channel': req.channel,
		})
		self._log_info('record corrected', subject=req.subject_ref, data_type=req.data_type,
			field=req.field, by=req.corrected_by, had_previous=previous is not None)
		return CorrectionReceipt(
			correction_id=f'COR-{len(self._corrections):06d}', subject_ref=req.subject_ref,
			data_type=req.data_type, field=req.field, previous_value=previous,
			corrected_value=req.corrected_value, corrected_by=req.corrected_by, at_iso=at_iso,
			message='Your record has been corrected. What it said before is kept in your history.',
		)

	def corrections(self, subject_ref: str) -> list[dict[str, object]]:
		"""Every correction made to a subject's records, which is what makes the workflow a workflow
		rather than a write: a person can see what was changed and who changed it."""
		return [c for c in self._corrections if c['subject_ref'] == subject_ref]

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

	# --- SEC-006 public transparency publication ---------------------------------------------

	def register_sources(self, sources: dict[str, object]) -> None:
		"""The reads the publication is drawn from, injected by `build_services`.

		A `dict[str, object]` rather than typed parameters, for the reason `OperationsService.EGRESS_WIRES`
		and `GovernanceService.audit_egress` take a dict: the publication reads *other services*, and a
		signature naming eight of them would make this module depend on each. A key that is absent is
		reported as an absent section, never silently skipped — a report that quietly drops the section
		whose source is missing reads as a quarter in which nothing happened.
		"""
		self._sources = dict(sources)

	def record_breach(self, breach: dict[str, object]) -> None:
		"""One §24.8 breach, as the public record holds it: the data classes and the count, never a person."""
		assert breach.get('affected_data') is not None, 'a breach record must name the data classes'
		self._breaches.append(dict(breach))

	@staticmethod
	def _quarter_of(period: str) -> tuple[int, int]:
		"""`2026-Q3` → `(2026, 3)`. Parsed rather than pattern-matched, so a period that cannot name a
		quarter is refused here rather than compared as a string and reported as missing forever."""
		year_s, _, q_s = period.partition('-Q')
		if not (year_s.isdigit() and q_s.isdigit() and 1 <= int(q_s) <= 4):
			raise ValueError(f'{period!r} does not name a quarter (expected e.g. 2026-Q3)')
		return int(year_s), int(q_s)

	@staticmethod
	def period_end_iso(period: str) -> str:
		"""The last day of the quarter the period names. A publication covers a window, and a window
		with no end cannot be compared against a generated-at date.

		Computed as the day before the next quarter opens rather than by adding a month's worth of
		days: Q1 ends on 31 March and Q2 on 30 June, and an arithmetic that produced "the first day
		plus 31" reports 1 March for the first of those.
		"""
		year, q = RetentionService._quarter_of(period)
		opens = date(year + 1, 1, 1) if q == 4 else date(year, q * 3 + 1, 1)
		return (opens - timedelta(days=1)).isoformat()

	def publication_schedule(self, period: str, today: date) -> PublicationSchedule:
		"""Whether the quarterly publication has happened, is late, or is not yet owed.

		The three states are the point. `published` and `due` are what a recurring duty can be; the
		third is what makes the cadence honest, because a quarter that has not ended cannot be late,
		and a model with only `overdue: bool` would report "not overdue" for a report nobody has ever
		written. `missing_periods` names every quarter between the first publication and the current
		one that was skipped, so a single gap is visible rather than averaged away.
		"""
		self._quarter_of(period)
		end = date.fromisoformat(self.period_end_iso(period))
		published = self._publications.get(period)
		due_on = (end + timedelta(days=QUARTERLY_CADENCE_DAYS)).isoformat()
		if published is not None:
			status = PublicationStatus.published
		elif today <= end:
			status = PublicationStatus.not_yet_due
		else:
			status = PublicationStatus.due
		return PublicationSchedule(
			cadence_days=QUARTERLY_CADENCE_DAYS, period=period, last_published_iso=published,
			due_on_iso=due_on, status=status,
			overdue=status is PublicationStatus.due,
			periods_published=len(self._publications),
			missing_periods=self._missing_periods(period, end),
		)

	def _missing_periods(self, period: str, end: date) -> list[str]:
		"""Every quarter between the earliest publication and this one that has no record.

		Bounded by the earliest publication rather than by the beginning of time: a service that has
		just been deployed has not skipped four years of quarters, and a list that said it had would
		be the kind of overstatement that makes a real gap unreadable.
		"""
		if not self._publications:
			return []
		# `[:10]`: the register holds the moment each report was generated, not just its day, and a
		# full timestamp is not a date `fromisoformat` accepts.
		earliest = min(date.fromisoformat(p[:10]) for p in self._publications.values())
		missing: list[str] = []
		year, q = earliest.year, (earliest.month - 1) // 3 + 1
		while (year, q) <= self._quarter_of(period):
			candidate = f'{year}-Q{q}'
			candidate_end = date.fromisoformat(self.period_end_iso(candidate))
			if candidate != period and candidate not in self._publications and candidate_end < end:
				missing.append(candidate)
			year, q = (year + 1, 1) if q == 4 else (year, q + 1)
		return missing

	def _publication_sections(self, as_at_iso: str) -> tuple[list[TransparencySection], list[str]]:
		"""The aggregate sections, built from the wired services. Returns the sections and the names
		of the sources that were not wired, so an absent section is reported rather than omitted."""
		sources = self._sources or {}
		sections: list[TransparencySection] = []
		absent: list[str] = []
		dashboards = sources.get('dashboards')
		if dashboards is None:
			absent.append('dashboards')
		else:
			# `all_dashboards` already applies §11.7's min-cell rule, and its suppressed rows carry
			# `value=None` — so the withheld counts are *counted here from the rows it returned*
			# rather than recomputed against a second copy of the rule. A publication that applied
			# its own threshold would be a second place the number lives, and the first to be wrong.
			#
			# The dashboards are flattened into one section each, with `key` prefixed by the
			# dashboard: a published table whose rows carry no indication of which dashboard they
			# came from reads as one population when it is nine different ones.
			built = dashboards.all_dashboards(as_at_iso)  # type: ignore[attr-defined]
			for dash in built:
				sections.append(TransparencySection(
					key=f'dashboard:{dash.dashboard.value}', title=dash.title, rows=list(dash.rows),
					rule=f'{dash.caveat} Cells drawn from fewer than {dash.min_cell_size} people are withheld, and the withheld count is reported.',
					withheld_cells=dash.suppressed_cells,
				))
		scans = sources.get('scans')
		if scans is None:
			absent.append('scans')
		else:
			obligations = scans.obligations(date.fromisoformat(as_at_iso[:10]))  # type: ignore[attr-defined]
			sections.append(TransparencySection(
				key='security', title='Security scans and audits',
				rows=[
					MetricRow(key=o.kind, label=o.kind, value=None if o.overdue else 1.0,
						denominator=None, suppressed=False,
						note=f'last performed {o.last_performed_iso or "never"}; due {o.due_on_iso or "now"}')
					for o in obligations
				],
				rule='A scan never performed is reported overdue rather than exempt.',
				withheld_cells=0,
			))
		return sections, absent

	def publish(self, period: str, as_at_iso: str) -> TransparencyPublication:
		"""Record that a period was published, and return the document that was.

		The *act*, separated from the *read* below, because the two have different callers and only
		one of them may write. A public route that recorded its own access would let any reader mark
		a quarter published — including one that has not ended — and the schedule would then report a
		duty met that nobody performed. The record is the operator's; the document is the public's.
		"""
		publication = self.build_publication(period, as_at_iso)
		self._publications[period] = as_at_iso
		self._log_info('transparency publication recorded', period=period,
			sections=len(publication.sections), withheld=publication.withheld_cells)
		return publication

	def build_publication(self, period: str, as_at_iso: str) -> TransparencyPublication:
		"""§SEC-006's quarterly public report, produced as a document a person can read.

		Pure: it reads the wired services and records nothing, which is what makes it safe to serve
		with no token. Every number in it comes from a service that already applies its own
		publication rule, and the rule travels with the section. The alternative — recomputing counts
		here — would put a second copy of the min-cell threshold in a second module, which is how a
		suppressed cell becomes an unsuppressed one in the document nobody diffs.
		"""
		self._quarter_of(period)
		assert as_at_iso, 'a publication must carry the moment it was generated'
		sections, absent = self._publication_sections(as_at_iso)
		notes = [
			'Every count is what people reported or searched for, not a laboratory-confirmed figure.',
			f'Cells drawn from fewer than {MIN_CELL_SIZE} people are withheld, and the withheld count is published beside the table.',
			'No row in this document names a person, and no row can be used to single one out.',
		]
		if absent:
			# Named, not omitted. A section missing because a service was not wired is a fact about
			# this deployment, and a reader comparing two quarters has to be able to tell it from a
			# quarter in which the thing it measures did not happen.
			notes.append(
				'Not included this period, because the deployment has no source for it: ' + ', '.join(sorted(absent)) + '.'
			)
		return TransparencyPublication(
			period=period, generated_at_iso=as_at_iso, cadence_days=QUARTERLY_CADENCE_DAYS,
			audience='public', sections=sections, breaches=list(self._breaches),
			open_obligations=self._open_obligations(), withheld_cells=sum(s.withheld_cells for s in sections),
			min_cell_size=MIN_CELL_SIZE, notes=notes,
			# §SEC-006's "Open-source client code" and §LOC-002's "Open-source client for independent
			# verification", in the document a member of the public actually reads. A licence stated
			# only in the repository is a fact about the repository; stated here it is one a person
			# who never clones anything can find — and the row's own words are *for independent
			# verification*, which is a thing done by someone outside. A separate field rather than a
			# section, because every section is a count over people under §11.7's min-cell rule and a
			# licence is neither a count nor suppressible. `offered` is read from the root `LICENSE`
			# by `afya.licensing`, so a tree that declares MIT and ships no terms publishes false.
			licence=licence_offer(),
		)

	def publications(self) -> dict[str, str]:
		"""Period → generated-at, so a caller can see the record the schedule is computed from."""
		return dict(self._publications)

	def _open_obligations(self) -> list[str]:
		"""§24's duties that name a software control, as the publication lists them.

		Read off `afya.operations.service:OBLIGATIONS` rather than restated: a transparency report
		that carried its own list of duties would be the second place they live, and the first to go
		stale. The import is inside the function because `operations` imports nothing from here but
		the dependency runs the other way through `build_services`.
		"""
		from afya.operations.service import OBLIGATIONS
		return sorted(o.duty for o in OBLIGATIONS if o.control is not None)
