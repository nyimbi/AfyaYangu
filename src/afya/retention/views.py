"""Retention, encryption and transparency models (spec §17, SEC-003/005/006, §12.2)."""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

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
