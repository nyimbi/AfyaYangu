"""Retention, encryption and transparency models (spec §17, SEC-003/005/006, §12.2)."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from afya.analytics.views import MetricRow

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# §SEC-006's "quarterly". Derived rather than restated, the way §22.8's `EvaluationMethod` derives
# it: a cadence of "Quarterly" as a string is a duty nobody can be late for, which is the state
# §24's `Obligation` model refuses for the same reason.
QUARTERLY_CADENCE_DAYS = 91

# §SEC-005 retention table. `deletion_trigger` is the *mechanism* the clock runs on:
#   `automatic`                  — fires on age alone
#   `automatic_unless_retained`  — fires on age unless the person chose to keep it
#   `user`                       — fires only on request
#   `policy`                     — fires under an obligation this build does not hold the clock for
#
# `stated` and `stated_trigger` are §SEC-005's own two cells, verbatim. They are carried beside the
# derived `days` because the section's Retention column is not always a number — Photos is "Until
# clinical review complete", an *event*, and Contact lists is "Until tracing window closes" — so a
# reader of `retention_days` alone cannot tell the section's figure from this build's reading of it.
# That is the distinction §16.5's `stated_total_mb` and §13.1's `SPEC_AVAILABILITY` both carry, and
# the reason a bare `'photos': 30` was able to drop "unless user retains" without anything noticing.
RETENTION_TABLE: dict[str, dict[str, object]] = {
	'symptom_logs': {'days': 90, 'trigger': 'automatic', 'stated': '90 days',
		'stated_trigger': 'User deletion or automatic'},
	'triage_results': {'days': 90, 'trigger': 'automatic', 'stated': '90 days',
		'stated_trigger': 'User deletion or automatic'},
	'location_history': {'days': 21, 'trigger': 'automatic', 'stated': '21 days rolling',
		'stated_trigger': 'Automatic'},
	'proximity_tokens': {'days': 21, 'trigger': 'automatic', 'stated': '21 days',
		'stated_trigger': 'Automatic'},
	'contact_lists': {'days': 21, 'trigger': 'automatic', 'stated': 'Until tracing window closes',
		'stated_trigger': 'Automatic'},
	'case_reports': {'days': 3650, 'trigger': 'policy', 'stated': 'Per MoH record retention policy',
		'stated_trigger': 'Policy-driven'},
	'immunisation_records': {'days': 36500, 'trigger': 'user', 'stated': 'Lifetime (user-controlled)',
		'stated_trigger': 'User deletion'},
	'chatbot_conversations': {'days': 90, 'trigger': 'automatic', 'stated': '90 days',
		'stated_trigger': 'Automatic'},
	'photos': {'days': 30, 'trigger': 'automatic_unless_retained',
		'stated': 'Until clinical review complete', 'stated_trigger': 'Automatic unless user retains'},
	# Not a §SEC-005 row. The consent ledger is kept under the same legal obligation as a
	# notification record, and its absence from the section's table is stated rather than filled:
	# the spec-comparison test names it as a build addition instead of reading it as a spec row.
	'consent_records': {'days': 3650, 'trigger': 'policy', 'stated': '',
		'stated_trigger': ''},
}

# §SEC-005 rows whose trigger cell carries the "unless user retains" carve-out. Derived from the
# stated cell rather than hand-listed, so a row whose section text gains the phrase gains the
# mechanism in the same edit — and a module-level assert below fails if the two ever disagree.
USER_RETAINABLE: frozenset[str] = frozenset(
	t for t, row in RETENTION_TABLE.items()
	if 'unless user retains' in str(row['stated_trigger']).lower()
)
assert all(
	(RETENTION_TABLE[t]['trigger'] == 'automatic_unless_retained') == (t in USER_RETAINABLE)
	for t in RETENTION_TABLE
), 'a row whose §SEC-005 trigger cell says "unless user retains" must carry the mechanism, and no other'


ENCRYPTION_STANDARD = 'AES-256-GCM at rest, TLS 1.3 in transit'


class RetentionPolicy(BaseModel):
	"""One §SEC-005 row: the window this build enforces, beside the section's own two cells.

	`stated` and `stated_trigger` are not decoration. The section's Retention column is an event for
	two rows ("Until clinical review complete", "Until tracing window closes"), so a client showing
	`retention_days` alone would render "30 days" where the section says the photo is kept until a
	clinician has looked at it — a different promise, and the shorter one. `within_statement` is the
	comparison the row exists for: whether the derived window and the stated cell are the same claim.
	"""
	model_config = MODEL_CONFIG
	data_type: str
	retention_days: int = Field(ge=1)
	deletion_trigger: str
	user_can_delete: bool
	# §SEC-005's own Retention and Deletion-trigger cells, verbatim.
	stated: str
	stated_trigger: str
	# §SEC-005's trigger cell says "unless user retains", so the clock is not the whole rule.
	user_may_retain: bool
	# True when the derived window is the section's claim; False where the section states an event
	# and this build has had to choose a number. Reported rather than resolved, because inventing
	# agreement is the thing the field prevents.
	within_statement: bool


class DataInventory(BaseModel):
	"""§SEC-006 in-app data dashboard: what is held, what was shared, with whom, when."""
	model_config = MODEL_CONFIG
	subject_ref: str
	held: dict[str, int]
	shared_with: list[dict[str, str]]
	earliest_auto_delete_in_days: int | None = None
	export_available: bool = True


class PersonalDataExport(BaseModel):
	"""§SEC-005 "export all personal data at any time".

	An export that overstated its own coverage would be worse than none: a person could hand it to
	a regulator believing it complete. It therefore carries `caveats`, and it is built from the same
	register the dashboard reads, so what a person sees and what they can download cannot disagree.
	"""
	model_config = MODEL_CONFIG
	subject_ref: str
	exported_at_iso: str
	channel: str
	format: str = 'json'
	holdings: dict[str, int]
	shared_with: list[dict[str, str]]
	deletions: list[dict[str, str]]
	caveats: list[str]


class DeletionRequest(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	data_type: str | None = None  # None = everything
	channel: str = Field(default='native', pattern=r'^(native|sms|ussd|whatsapp)$')


class DeletionReceipt(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	deleted_types: list[str]
	retained_types: list[str]
	retention_reason: str
	message: str


class CorrectionRequest(BaseModel):
	"""§17.2 accuracy: "user data editable; correction workflows". §17.1 puts the same duty on the
	ODPC guidance note, which names accuracy as a processing principle — so a record a person cannot
	correct is a statutory gap, not a missing feature.

	`corrected_by` is the subject themselves for a self-service correction and the DPO for one made
	on their behalf, because the two are different facts about the record: one is the person
	exercising a right, the other is the controller acting on a request.
	"""

	model_config = MODEL_CONFIG
	subject_ref: str
	data_type: str
	field: str = Field(min_length=1)
	corrected_value: str
	reason: str = Field(min_length=1)
	corrected_by: str = Field(min_length=1)
	channel: str = Field(default='native', pattern=r'^(native|sms|ussd|whatsapp)$')


class CorrectionReceipt(BaseModel):
	model_config = MODEL_CONFIG
	correction_id: str
	subject_ref: str
	data_type: str
	field: str
	previous_value: str | None
	corrected_value: str
	corrected_by: str
	at_iso: str
	message: str


class EncryptionPosture(BaseModel):
	model_config = MODEL_CONFIG
	at_rest: str
	in_transit: str
	keystore: str
	contact_lists_extra_layer: bool
	cloud_backup_e2e: bool
	user_held_key: bool


class TransparencyReport(BaseModel):
	model_config = MODEL_CONFIG
	period: str
	subject_ref: str | None
	rows: list[dict[str, object]]
	notes: list[str]


class PublicationStatus(str, Enum):
	"""What state a period's public report is in.

	`published` and `due` are the two states a recurring document has; `not_yet_due` is the one that
	makes a cadence meaningful, because a report that is neither published nor late is the only
	honest way to describe a quarter that has not ended. An enum rather than a boolean for the reason
	§11.5's eligibility values are: `overdue: false` cannot distinguish "done" from "not asked for".
	"""

	published = 'published'
	due = 'due'
	not_yet_due = 'not_yet_due'


class TransparencySection(BaseModel):
	"""One part of the published report, carrying the source's own rule with it.

	`rule` is the sentence a reader needs to interpret the numbers — §11.7's min-cell rule, §19.4's
	reported-not-confirmed caveat, §24.8's 72-hour clock. Without it a table of counts reads as a
	measurement of the thing named rather than of what people reported, and the difference is the
	whole reason the section exists.
	"""

	model_config = MODEL_CONFIG
	key: str
	title: str
	rows: list[MetricRow]
	rule: str
	withheld_cells: int = Field(ge=0)


class TransparencyPublication(BaseModel):
	"""§SEC-006's "Public transparency reports (quarterly)" — the aggregate document itself.

	Distinct from `TransparencyReport`, which is a *subject's* own view of their own data. The two
	were one model name apart and the section prints both as separate Features, which is exactly how
	the bullet read as carried while no aggregate existed: a report about a person is not a
	publication to the public.

	`audience` is on the model because it is the one field that cannot be inferred from the payload:
	every count here is over people, and a document built for the public has to say so.
	"""

	model_config = MODEL_CONFIG
	period: str
	generated_at_iso: str
	cadence_days: int = Field(gt=0)
	audience: str
	sections: list[TransparencySection]
	breaches: list[dict[str, object]]
	open_obligations: list[str]
	withheld_cells: int = Field(ge=0)
	min_cell_size: int = Field(ge=1)
	notes: list[str]
	# §SEC-006's "Open-source client code" and §LOC-002's "Open-source client for independent
	# verification", as the publication states them. Deliberately *not* a `TransparencySection`:
	# every section there is a count over people, governed by §11.7's min-cell rule and carrying the
	# source's own measurement caveat. A licence is not a measurement and has no cell to suppress,
	# so folding it in would put a row with no denominator under a rule about withholding, and would
	# make "the publication has no sections" — which is a real state when no source is wired —
	# stop being true. `offered` is read from the root `LICENSE` by `afya.licensing`.
	licence: dict[str, object] | None = None


class PublicationSchedule(BaseModel):
	"""Whether the quarterly duty has been met, reported rather than assumed.

	`overdue` is the same distinction `ScanObligation` and `ObligationStatus` draw: a duty never
	performed is overdue, not exempt, because a publication that has never happened is the one most
	likely to be quietly skipped.
	"""

	model_config = MODEL_CONFIG
	cadence_days: int = Field(gt=0)
	period: str
	last_published_iso: str | None
	due_on_iso: str | None
	status: PublicationStatus
	overdue: bool
	periods_published: int = Field(ge=0)
	missing_periods: list[str]
