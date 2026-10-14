"""Retention, encryption and transparency models (spec §17, SEC-003/005/006, §12.2)."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from afya.analytics.views import MetricRow

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# §SEC-006's "quarterly". Derived rather than restated, the way §22.8's `EvaluationMethod` derives
# it: a cadence of "Quarterly" as a string is a duty nobody can be late for, which is the state
# §24's `Obligation` model refuses for the same reason.
QUARTERLY_CADENCE_DAYS = 91

# §SEC-005 retention table. `deletion_trigger` is either `automatic` (clock) or `user` (on request).
RETENTION_TABLE: dict[str, dict[str, object]] = {
	'symptom_logs': {'days': 90, 'trigger': 'automatic'},
	'triage_results': {'days': 90, 'trigger': 'automatic'},
	'location_history': {'days': 21, 'trigger': 'automatic'},
	'proximity_tokens': {'days': 21, 'trigger': 'automatic'},
	'contact_lists': {'days': 21, 'trigger': 'automatic'},
	'case_reports': {'days': 3650, 'trigger': 'policy'},
	'immunisation_records': {'days': 36500, 'trigger': 'user'},
	'chatbot_conversations': {'days': 90, 'trigger': 'automatic'},
	'photos': {'days': 30, 'trigger': 'automatic'},
	'consent_records': {'days': 3650, 'trigger': 'policy'},
}

ENCRYPTION_STANDARD = 'AES-256-GCM at rest, TLS 1.3 in transit'


class RetentionPolicy(BaseModel):
	model_config = MODEL_CONFIG
	data_type: str
	retention_days: int = Field(ge=1)
	deletion_trigger: str
	user_can_delete: bool


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
