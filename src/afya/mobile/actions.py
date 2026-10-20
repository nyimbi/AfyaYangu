"""Server-driven mobile action catalogue — the generic mechanism that exposes every backend feature.

GET /mobile/actions returns every usable action (id, title, group, method, path, fields);
a field is {name,label,type,options,placeholder,required,client_supplied,server_assigned} with type in:
	text, int, decimal, bool, select, textarea, list (comma text -> array), file, path (URL path param).
Apps render one generic form per action — no per-feature code, no app release needed to add features.

A field marked `client_supplied` is the device's own identity, not a question: the client fills it
from its session and does not draw it. On a personal-data route the server binds the subject it is
given to the token that gave it (§17), so a form that let a person type someone else's subject would
be offering a control that is refused by construction — the §11.1 defect this flag exists to
prevent. The field is carried, not dropped, because the client still has to send it.

A field marked `server_assigned` is a reference the server mints, and the second half of the same
defect: it was carried with the placeholder "generated for you" and left undrawn, which told a
person to leave it blank while the model refused the request without it. The model now defaults it,
so an omitted field is a complete request, and the flag keeps the form from asking anyone to invent
a primary key. The two flags are separate because a client that injects its own subject keys off the
first, and a reference is not an identity.

IDENTIFIERS ARE SLUGS, NOT SPEC CODES. Nothing a person reads may contain a code such as
"REC-004": ids, titles, labels, placeholders and descriptions are all plain language. The spec
codes live in FEATURE_OF, which is deliberately not serialised, so the backend keeps its
traceability to the spec without the code ever reaching a screen. tests/ci/test_ui_vocabulary.py
enforces this.
"""
from typing import Callable, Literal, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from afya.community.views import FOLLOWUP_DAYS, MISINFO_PAYLOAD_MEDIA
from afya.location.views import (
	ALERT_ZONE_RADII_M, CHECKIN_KINDS as CHECKIN_KINDS_SPEC,
	CHECKIN_METHODS as CHECKIN_METHODS_SPEC,
)
from afya.medicine import contraindications
from afya.identity.views import LinkBasis
from afya.monitoring.views import LARVICIDE_CLASSES
from afya.records.views import WALLET_DOC_KINDS
from afya.registry.diseases import DISEASES
from afya.access.views import LANGUAGE_MATRIX
from afya.alerts.views import ALERT_ISSUERS, AlertKind
from afya.community.views import CaseStatus, IssueKind, PEER_VERIFIERS
from afya.chw.views import PROVISIONERS
from afya.evidence.views import EvidenceKind
from afya.facilities.views import FacilityKind
from afya.info.views import CONTENT_LANGS, ContentStage
from afya.chronic.views import AppointmentKind
from afya.chronic.trends import REVIEW_INTERVAL_DAYS
from afya.monitoring.views import AdherenceAction, ReminderSlot
from afya.sensors.views import SenseKind
from afya.alerting.views import FEED_CATEGORIES
from afya.live.views import LivePlatform, LiveStatus
from afya.privacy.views import LegalBasis
from afya.info.submissions import StoryKind
from afya.sensors.tags import EQUIPMENT_STATUSES, TAG_TARGETS
from afya.strings import SUPPORTED_LANGS
from afya.sync.views import CONFLICT_RULES

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

FieldType: TypeAlias = Literal['text', 'int', 'decimal', 'bool', 'select', 'textarea', 'list', 'file', 'path']
FIELD_TYPES: tuple[str, ...] = ('text', 'int', 'decimal', 'bool', 'select', 'textarea', 'list', 'file', 'path')


class FieldCondition(BaseModel):
	"""What a person must have answered before this field is required — §11.1's other half.

	`required` says the route refuses without this field. It cannot say *when*, and three of this
	catalogue's routes refuse a combination: `MisinfoSubmission` wants the recording or the transcript
	when the medium is a voice note, `BorderPost` wants a turnaround and a test list when it reports a
	mobile lab, and `SuspiciousReport` wants a barcode or a batch number. A form that draws every one
	of those as optional offers a submission the route refuses, and the person has no way to know
	which answer made it incomplete — the refusal names a field they were never told to fill.

	One predicate, in two spellings:

	* `equals_any` non-empty — the trigger's answer is one of these values (`medium` is `voice`,
	  `screenshot` or `whatsapp_forward`).
	* `equals_any` empty — *any* answer at all fires it. `MisinfoSubmission` wants
	  `evidence_consent` whenever there is a recording to consent to, and naming the values a
	  recording could take is impossible.

	A rule that a field must *differ* from another is not a condition and is carried separately, as
	`MobileField.distinct_from`: `required = (a != b)` is false for every answer a person gives, so
	stating `BackTranslation`'s "the renderer is not the translator" here would produce a condition
	that can never fire.

	A rule that *one of several* fields must be answered is also not a condition on any one of them,
	and is carried on the action as `FieldGroup` — see `MobileAction.any_of`. Marking each member
	required-when-the-other-is-blank would make an empty form demand all of them, which is the mirror
	of the defect this module exists to close: a form refusing a submission the route accepts.
	"""
	model_config = MODEL_CONFIG
	when: str
	equals_any: list[str] = []


class FieldGroup(BaseModel):
	"""At least one of `fields` must be answered — `SuspiciousReport`'s "a gtin or a batch number".

	Carried on the action rather than on each field because it is not a property of any one of them.
	`gtin` is not required (a batch number satisfies the route) and not optional (nothing else does),
	and a per-field boolean has no third state to say so. `when`/`equals_any` gate the group the same
	way `FieldCondition` gates a field, so a group can itself be conditional — `MisinfoSubmission`
	wants the recording *or* its transcript, and only when the medium is one that carries a payload.
	"""
	model_config = MODEL_CONFIG
	fields: list[str] = Field(min_length=2)
	when: str | None = None
	equals_any: list[str] = []


class MobileField(BaseModel):
	model_config = MODEL_CONFIG
	name: str
	label: str
	type: Literal['text', 'int', 'decimal', 'bool', 'select', 'textarea', 'list', 'file', 'path']
	options: list[str] | None = None
	placeholder: str | None = None
	# Filled in at serve time from the route's own requirement set, never from the field's type.
	# It was `type_ == 'path'` — so no body field was ever marked, 385 offered fields a route refuses
	# without were drawn as optional, and 101 actions presented a complete-looking form whose
	# submission the route rejected. `marked()` is where the correction happens.
	required: bool = False
	# Required only when `condition` holds. Never both: `marked()` asserts the two are disjoint,
	# because a client that read a condition on an unconditionally-required field would drop the
	# asterisk exactly when the answer made the field matter most.
	condition: FieldCondition | None = None
	# The field this one must not equal. Not requiredness — see `FieldCondition` — but a rule the
	# route enforces and a form can act on by refusing to submit, which prose in a placeholder cannot.
	distinct_from: str | None = None
	# What the picker may offer, for a `file` field. The route's own claim, not the client's: a
	# recording sent to a photo route is refused after the upload, and Android offered audio for
	# every file action and images for evidence, so the cough recording and the voice note were
	# unselectable on that client.
	accept: str | None = None
	# True when the client must supply this field from its own identity and must not draw it. A
	# personal-data route binds the subject it is given to the token that gave it (§17), so a form
	# offering to type a subject would offer a control the server refuses — the §11.1 defect.
	client_supplied: bool = False
	# True when the *server* fills this field and a form must not ask for it. Distinct from
	# `client_supplied`: that one means the client knows the value and the person does not, this one
	# means nobody knows it until the request arrives. Both are undrawn, and the difference matters
	# because a client injecting its own subject keys off the first and must not key off the second.
	server_assigned: bool = False
	# True when the route reads this field from a `multipart/form-data` body rather than JSON. It is
	# the transport, not a property of the value: the same text field is JSON on one route and a form
	# part on another, and a client that sends JSON to a `File(...)`/`Form(...)` route is refused
	# before the handler runs. The four actions carrying a `file` field are all of this kind, and a
	# client that sent them a JSON body 422'd on every one.
	form: bool = False


class MobileAction(BaseModel):
	model_config = MODEL_CONFIG
	id: str
	title: str
	group: str
	method: Literal['GET', 'POST', 'DELETE']
	path: str  # may contain {placeholders} backed by type='path' fields
	fields: list[MobileField] = []
	# Groups of fields where answering *one* satisfies the route. Not a property of any member, so it
	# cannot live on a member: see `FieldGroup`.
	any_of: list[FieldGroup] = []


BLOOD_GROUPS = ['O-', 'O+', 'A-', 'A+', 'B-', 'B+', 'AB-', 'AB+']
# Every one of these is now a *view* of the enum the route validates against rather than a second
# copy of it. Six were hand-typed lists that happened to equal their enum on the day they were
# written, which is a vocabulary with a drift horizon and no symptom when it passes: the form
# submits, the route answers 200, and the value that is missing is simply not on the spinner.
# `ALERT_KINDS` and `FACILITY_KINDS` had already passed that horizon — they offered ten of twelve and
# five of six — and nothing in the tree could see it, because the only thing comparing a form to its
# route compared field *names*, never the values a field offers.
SENS_KINDS = [k.value for k in SenseKind]
# Derived from the enum the route validates against, not typed out beside it. A second list is a
# vocabulary that drifts the moment the first one grows: this one offered ten of `AlertKind`'s twelve
# and the two it omitted were `outbreak_measles` and `outbreak_other` — exactly the two the enum's own
# docstring says it was widened for, because §3.3 principle 12 names measles and ends "and the next
# unknown". Nothing failed: the form submitted, the route answered 200, and the two diseases the
# section is most explicit about could not be alerted on from the app at all.
ALERT_KINDS = [k.value for k in AlertKind]
# Same rule as ALERT_KINDS, and this one had been a hand-copy of §16.3's matrix rather than a view of
# it: the eight strings agreed with `CONFLICT_RULES` by coincidence of nobody having edited either, and
# the route's own guard (`op.dataset in STRATEGY_MATRIX`) reads a dict *comprehension* over that tuple,
# so no schema reader can see the vocabulary from the model side. Deriving it here makes the coupling
# the fix rather than the discipline — adding a dataset to §16.3's table widens the spinner, and a
# dataset the table does not carry is not offerable.
SYNC_DATASETS = [r.dataset for r in CONFLICT_RULES]
PROCEDURES = ['c_section', 'normal_delivery', 'outpatient', 'inpatient_day', 'dialysis', 'x_ray', 'theatre']
# Same rule as ALERT_KINDS: the enum is the vocabulary, and the spinner is a view of it. This one
# offered five of six and omitted `therapeutic_feeding` — §MON-008's "therapeutic feeding programme
# locations", which `NearestRequest.kind` accepts and which the enum's own comment says was added for
# that section. A capability with no screen.
FACILITY_KINDS = [k.value for k in FacilityKind]
EVIDENCE_KINDS = [k.value for k in EvidenceKind]
ISSUE_KINDS = [k.value for k in IssueKind]
CASE_STATUSES = [k.value for k in CaseStatus]
CONTACT_SETTINGS = ['home', 'work', 'transport', 'worship', 'market', 'social', 'other']
MISINFO_MEDIA = ['text', 'voice', 'screenshot', 'whatsapp_forward']
CHECKIN_KINDS = list(CHECKIN_KINDS_SPEC)
CHECKIN_METHODS = list(CHECKIN_METHODS_SPEC)
# §3.3 principle 12's vocabulary, read from the one module that carries it. This was a fourth copy
# of the list, and the copies had already drifted: this one and `community.CaseReport` had `measles`,
# `surveillance.CountySignal` did not, and `alerts.AlertKind` had neither `measles` nor `other`.
VECTOR_DISEASES = list(DISEASES)
ADHERENCE_ACTIONS = [k.value for k in AdherenceAction]
# §MON-007's larvicide classes, read off the model so a class added to the table cannot go missing
# from the form a county fills in — the same reasoning `VECTOR_DISEASES` gives for reading the
# disease list rather than restating it.
LARVICIDE_OPTIONS = list(LARVICIDE_CLASSES)
INTENSITIES = ['low', 'balanced', 'maximum']
# §LOC-005's "multi-language support for cross-border travellers", as the set a traveller path can
# actually answer in. `SUPPORTED_LANGS` is the languages with a string table, and it is the honest
# list to offer: §ACC-002 names six for voice and §LOC-005 asks for cross-border support, but a
# dropdown that offered Dholuo here would be offering a language this path answers in English.
TRAVELLER_LANGS = sorted(SUPPORTED_LANGS)
# §ACC-002's voice path offers the languages recognition actually *ships* for, which is
# `LANGUAGE_MATRIX`'s `asr` flag and not its key set — the same distinction `TRAVELLER_LANGS`
# draws for the traveller path, for the same reason: a dropdown offering Dholuo on a recogniser
# that was never trained on it promises a transcript of words nobody said.
LANGUAGE_MATRIX_ASR: dict[str, bool] = {
	str(meta['code']): bool(meta['asr']) for meta in LANGUAGE_MATRIX.values()
}
VOICE_LANGS = sorted(code for code in TRAVELLER_LANGS if LANGUAGE_MATRIX_ASR.get(code))
VOICE_PURPOSES = ['symptoms', 'note']
OUTPUT_KINDS = ['triage', 'risk_score', 'hotspot', 'exposure', 'tier4_activation']
# §6.5's content workflow, in order. The server refuses a jump, so the control offers the steps.
CONTENT_STAGES = [k.value for k in ContentStage]
ACTIVITY_KINDS = ['report', 'followup', 'sensitisation', 'referral', 'training', 'supervision']
JOB_AID_TOPICS = ['idsr_case_definition', 'ppe_donning', 'ppe_doffing', 'isolation_basics', 'safe_burial', 'reporting_flow']
CHW_TASK_KINDS = ['followup', 'referral', 'sensitisation']

# slug -> spec feature id. Internal traceability only; never serialised (see module docstring).
FEATURE_OF: dict[str, str] = {
	'febrile_triage': 'TRI-001', 'evd_triage': 'TRI-003', 'differential': 'TRI-001',
	'diary_trend': 'TRI-002', 'diary_export': 'TRI-002', 'diary_prompt': 'TRI-002',
	'diary_escalation': 'TRI-002',
	'symptom_diary': 'TRI-002',
	'what_should_i_do': 'INF-002', 'entry_answers': 'INF-002', 'health_library': 'INF-003', 'publish_content': 'INF-003',
	'search_library': 'INF-004', 'library_categories': 'INF-004', 'myth_library': 'INF-004',
	'ask_about_a_rumour': 'INF-004',
	'advance_content': 'INF-003', 'content_governance': 'INF-003', 'report_content_error': 'INF-003',
	'content_errors': 'INF-003', 'record_back_translation': 'INF-003', 'record_community_validation': 'INF-003',
	'content_localisation': 'INF-003',
	'hotline_directory': 'INF-006', 'county_risk': 'INF-001', 'set_county_risk': 'INF-001',
	'record_case_counts': 'INF-001', 'record_sub_county': 'INF-001',
	'medicine_registry': 'MED-001', 'medicine_recalls': 'MED-001', 'report_suspicious_medicine': 'MED-004',
	'sha_cover_verify': 'INF-016', 'sha_facilities': 'INF-016', 'sha_benefits': 'INF-016',
	'nearest_facilities': 'FND-001', 'ed_status': 'FND-002', 'report_wait': 'FND-004',
	'book_appointment': 'FND-006', 'view_slots': 'FND-006', 'reschedule_appointment': 'FND-006',
	'cancel_appointment': 'FND-006', 'publish_slot': 'FND-006',
	'testing_sites': 'FND-003', 'vaccination_points': 'FND-005',
	'service_status': 'INF-007', 'risk_zones_near_me': 'LOC-001',
	'zone_alerts_setting': 'LOC-001', 'set_zone_alerts': 'LOC-001', 'my_zone_events': 'LOC-001',
	'verify_medicine': 'MED-001', 'drug_interactions': 'MED-002', 'dosage': 'MED-003', 'report_stock': 'MED-004',
	'find_stock': 'MED-004', 'stock_availability': 'MED-004', 'essential_medicines': 'MED-004',
	'restock_alerts': 'MED-004',
	'sos': 'EMG-001', 'sos_countdown': 'EMG-001', 'sos_cancel': 'EMG-001', 'sos_fire': 'EMG-001',
	'sos_state': 'EMG-001',
	'emergency_card': 'EMG-003',
	'immunisation_gaps': 'REC-001', 'family_wallet': 'REC-001', 'growth_flag': 'REC-003',
	'add_family_member': 'REC-001',
	# §9.2 REC-001's features, and §10.1 REC-002's seven additions over it. Both sections describe
	# operations over one set of wallet documents, so the actions below serve both: `wallet_search`
	# and `file_document` are REC-001's, and the timeline, chart, certificate, export, share and
	# backup are REC-002's. The split is recorded here rather than in the routes because the routes
	# are deliberately shared — one document store, four operations.
	'wallet_documents': 'REC-001', 'file_document': 'REC-001', 'wallet_search': 'REC-001',
	'export_record': 'REC-001',
	'health_timeline': 'REC-002', 'share_record': 'REC-002', 'record_shares': 'REC-002',
	'revoke_share': 'REC-002', 'provider_view': 'REC-002', 'backup_wallet': 'REC-002',
	'vaccination_certificate': 'REC-002',
	# The chart is §REC-003's "percentile charts", which is the growth section rather than the wallet.
	'growth_chart': 'REC-003',
	# §REC-003's "milestone checklists", in Annex 9's two halves: the list, and the report against it.
	'milestone_checklist': 'REC-003', 'milestone_check': 'REC-003',
	'add_lab': 'REC-007', 'view_labs': 'REC-007', 'register_donor': 'REC-004', 'find_donors': 'REC-004',
	'donor_alerts': 'REC-004', 'donation_centres': 'REC-004',
	'wellbeing_check': 'REC-005', 'counselling_lines': 'REC-005', 'mood_screen': 'REC-005',
	'mood_log': 'REC-005', 'mood_trend': 'REC-005', 'coping_tips': 'REC-005',
	'outbreak_support': 'REC-005', 'ask_referral': 'REC-005',
	'log_bp': 'REC-006', 'log_glucose': 'REC-006', 'bp_trend': 'REC-006', 'track_refill': 'REC-006',
	'log_cycle': 'REC-009', 'cycle_prediction': 'REC-009',
	'contraception_methods': 'REC-009', 'set_contraception': 'REC-009',
	'contraception_due': 'REC-009', 'menopause_state': 'REC-009',
	'reproductive_referral': 'REC-009',
	'register_pregnancy': 'REC-008', 'anc_due': 'REC-008', 'record_anc': 'REC-008', 'danger_signs': 'REC-008',
	# §MON-002's other nine. The registry carries the section twice — REC-008 and MON-002 are one
	# capability under two ids, and the alias table records the divergence — so the feature id here
	# is the one the registry resolves for a maternal feature and the section is MON-002's.
	'due_date': 'MON-002', 'anc_visits': 'MON-002', 'postnatal_visits': 'MON-002',
	'record_birth': 'MON-002', 'trimester_guidance': 'MON-002', 'newborn_signs': 'MON-002',
	'birth_plan': 'MON-002', 'save_birth_plan': 'MON-002', 'pmtct_referral': 'MON-002',
	'maternity_facilities': 'MON-002',
	'child_schedule': 'MON-001', 'catch_up_doses': 'MON-001', 'record_dose': 'MON-001', 'register_child': 'MON-001',
	'missed_doses': 'MON-001', 'vaccination_campaigns': 'MON-001', 'issue_campaign': 'MON-001',
	'add_medication': 'MON-004', 'log_adherence': 'MON-004',
	'peak_flow': 'MON-003', 'log_weight': 'MON-003', 'condition_profile': 'MON-003', 'clinical_report': 'MON-003',
	# §MON-003's three conditions with no reading behind them, and its three missing features. The
	# actions carry no feature code in their titles — the ids above are internal, and a person reads
	# "My kidney results", not "MON-003".
	'kidney_result': 'MON-003', 'seizure_log': 'MON-003', 'sickle_crisis': 'MON-003',
	'trend_chart': 'MON-003', 'appointments': 'MON-003', 'lifestyle_guidance': 'MON-003',
	'schedule_review': 'MON-003',
	'vector_risk': 'MON-007', 'breeding_site': 'MON-007', 'larviciding': 'MON-007',
	'issue_larviciding': 'MON-007', 'protection_reminder': 'MON-007',
	'food_alert': 'MON-008', 'food_alerts': 'MON-008', 'nutrition': 'MON-008',
	'therapeutic_feeding': 'MON-008',
	'enrol_monitoring': 'MON-009', 'monitoring_day': 'MON-009', 'monitoring_diary': 'MON-009',
	'monitoring_reminders': 'MON-009', 'monitoring_consent': 'MON-009', 'monitoring_members': 'MON-009',
	'monitoring_member_diary': 'MON-009', 'monitoring_officer': 'MON-009',
	'remove_household_member': 'MON-009', 'request_activation': 'MON-009',
	'issue_alert': 'INF-014', 'alerts_by_county': 'INF-014',
	'water_advisory': 'INF-011', 'air_advisory': 'INF-012', 'flood_risk': 'INF-013',
	'file_price': 'INF-016', 'price_quote': 'INF-016', 'sha_cover_check': 'INF-016',
	'assign_chw_task': 'CHAN-005', 'chw_open_tasks': 'CHAN-005', 'complete_chw_task': 'CHAN-005',
	'send_sms': 'CHAN-001',
	'channel_costs': 'CHAN-001',
	# §CHAN-1's "plain language", read by the content team: the rows name strings and the sentences
	# that overran the ceiling, which is editorial state. The same scope the other content reads take.
	'plain_language': 'CHAN-001',
	'queue_sync_op': 'CHAN-006', 'flush_sync': 'CHAN-006', 'offline_state': 'ACC-003',
	'sync_conflicts': 'ACC-003', 'appeal_conflict': 'ACC-003',
	'record_consent': 'SEC-001', 'consent_choices': 'SEC-001', 'dpia_check': 'SEC-001',
	'consent_history': 'SEC-001', 'withdraw_consent': 'SEC-001',
	# §SEC-004's optional pseudonymous profile. The two are one feature because they are one setting:
	# the handle a person is shown and the handle they may choose are the same value.
	'my_pseudonym': 'SEC-004', 'choose_pseudonym': 'SEC-004',
	'link_my_profile': 'SEC-004',
	'sensor_ingest': 'SENS-005', 'analyse_cough': 'SENS-002', 'submit_evidence': 'SENS-004',
	'estimate_breathing': 'SENS-001',
	'tag_resolve': 'SENS-010', 'tag_tap': 'SENS-010', 'tag_bind': 'SENS-010',
	'tag_coverage': 'SENS-010', 'equipment_list': 'SENS-010', 'equipment_add': 'SENS-010',
	'equipment_move': 'SENS-010',
	'activate_outbreak_mode': 'TRI-003',
	'report_issue': 'COM-005', 'issues_by_county': 'COM-005', 'resolve_issue': 'COM-005',
	'submit_case': 'COM-101', 'advance_case': 'COM-101', 'ppe_reminder': 'COM-101',
	'peer_alert': 'COM-102', 'peer_alert_followup': 'COM-102', 'ack_peer_alert': 'COM-102',
	'tracing_prompts': 'COM-103', 'save_contacts': 'COM-103', 'add_contact': 'COM-103',
	'share_contacts': 'COM-103', 'contact_shares': 'COM-103', 'withdraw_contact_shares': 'COM-103',
	'flag_misinformation': 'COM-104', 'misinformation_clusters': 'COM-104',
	'misinformation_notices': 'COM-104',
	'publish_feed_item': 'ALT-001', 'alert_feed': 'ALT-001',
	'alert_preferences': 'ALT-003', 'set_alert_preference': 'ALT-003',
	'link_family': 'ALT-002', 'family_check_in': 'ALT-002', 'family_board': 'ALT-002', 'my_checkins': 'ALT-002',
	'send_exposure_notice': 'ALT-004', 'ack_exposure': 'ALT-004',
	'rotate_ebid': 'LOC-002', 'log_encounter': 'LOC-002', 'declare_exposure': 'LOC-002', 'check_exposure': 'LOC-002',
	'enable_location_history': 'LOC-003', 'log_location': 'LOC-003', 'location_report': 'LOC-003',
	'share_location_report': 'LOC-003', 'location_report_shares': 'LOC-003', 'purge_location': 'LOC-003',
	'register_checkin_point': 'LOC-004', 'check_in': 'LOC-004', 'checkin_points': 'LOC-004', 'checkin_list': 'LOC-004',
	'checkin_followup': 'LOC-004',
	'register_border': 'LOC-005', 'border_status': 'LOC-005', 'travel_advisory': 'INF-005', 'traveller_declare': 'LOC-005',
	'traveller_prompt': 'LOC-005', 'traveller_report': 'LOC-005',
	'risk_score': 'AI-002', 'early_warning': 'AI-003',
	'signal_scan': 'AI-003', 'signal_report': 'AI-003',
	'model_cards': 'AI-004', 'fairness_audit': 'AI-004', 'file_redress': 'AI-005',
	'access_profile': 'ACC-001', 'ui_screens': 'ACC-001', 'languages': 'ACC-002', 'voice': 'ACC-002',
	'voice_audio': 'ACC-002',
	'battery_profile': 'ACC-004', 'compatibility': 'ACC-005', 'sensor_capabilities': 'ACC-005',
	'screen_layouts': 'ACC-005',
	'retention_policy': 'SEC-005', 'record_holding': 'SEC-006', 'record_share': 'SEC-006',
	'correct_my_data': 'SEC-005', 'my_corrections': 'SEC-005',
	'data_inventory': 'SEC-006', 'export_my_data': 'SEC-005', 'delete_my_data': 'SEC-005', 'purge_expired': 'SEC-005',
	'encryption_posture': 'SEC-003', 'transparency_report': 'SEC-006',
	'public_transparency_report': 'SEC-006', 'publication_schedule': 'SEC-006', 'licence_terms': 'SEC-006',
	'provision_chw': 'CHAN-005', 'chw_profile': 'CHAN-005', 'chw_training': 'CHAN-005', 'job_aid': 'COM-101',
	'chw_cases': 'COM-101', 'assign_chw_case': 'COM-101', 'log_chw_activity': 'COM-101', 'chw_activity': 'COM-101',
	'callback_requests': 'CHAN-001', 'callback_handled': 'CHAN-001',
	'channel_reports': 'CHAN-002', 'channel_report_handled': 'CHAN-002',
	# §CHAN-000's call-in and §CHAN-004's clinician Q&A: the queue, the schedule and the record.
	'live_sessions': 'CHAN-000', 'ask_live_question': 'CHAN-000', 'live_transcript': 'CHAN-000',
	'schedule_live_session': 'CHAN-000', 'live_queue': 'CHAN-000', 'open_live_session': 'CHAN-000',
	'close_live_session': 'CHAN-000', 'answer_live_question': 'CHAN-000',
	'decline_live_question': 'CHAN-000',
	# §CHAN-004's user-generated content and its moderation queue.
	'submit_story': 'CHAN-004', 'story_queue': 'CHAN-004', 'moderate_story': 'CHAN-004',
	'chw_case_load': 'COM-101', 'chw_ppe_reminder': 'COM-101',
}

# Actions whose route is guarded on an operator dataset, and the scope that opens it. Everything
# not listed is a citizen action reachable with a citizen token. `OPERATOR_SCOPES` is the mobile
# mirror of the guard each route carries; `test_ui_vocabulary.py` crosses the two so a route whose
# guard changes cannot leave a control behind that 403s.
OPERATOR_SCOPES: dict[str, str] = {
	'activate_outbreak_mode': 'infrastructure',
	'publish_content': 'infrastructure',
	'advance_content': 'infrastructure',
	'report_content_error': 'infrastructure',
	'record_back_translation': 'infrastructure',
	'record_community_validation': 'infrastructure',
	'content_localisation': 'audit_logs',
	'content_governance': 'audit_logs',
	'content_errors': 'audit_logs',
	'plain_language': 'audit_logs',
	# §CHAN-1's outbound send spends the deployment's SMS budget and posts under its own sender
	# ID, so it is `infrastructure` — the scope §17.4 gives the role that touches no personal data
	# but operates the deployment, the same reading `/intermediaries/incentives` carries for an
	# airtime disbursement. It was unguarded: any caller could have the Ministry's channel text an
	# arbitrary body to an arbitrary number.
	'send_sms': 'infrastructure',
	# Publishing a community alert or a feed item is what the Ministry says, to everyone. A CHW
	# holds `assigned` (§17.4), which is the role that carries a worker's reports up; a citizen
	# holds `self` and can read the feed but not write it.
	'issue_alert': 'assigned',
	'publish_feed_item': 'assigned',
	'resolve_issue': 'assigned',
	# The CHW's own working set. §17.4 gives the role `assigned` — the people and tasks allocated
	# to it — and every one of these routes is guarded on that scope. A citizen's catalogue must
	# not carry a caseload screen, a task queue, or the form that files a case report.
	'assign_chw_case': 'assigned', 'assign_chw_task': 'assigned', 'chw_activity': 'assigned',
	'chw_case_load': 'assigned', 'chw_cases': 'assigned', 'chw_open_tasks': 'assigned',
	# §CHAN-1's callback queue. The same request §CHAN-2's second prompt collects, read and worked
	# by whoever rings people back — the CHW who takes it is the one the section's journey names, so
	# the route is guarded on `assigned` rather than left open to the phone that filed the request.
	'callback_requests': 'assigned', 'callback_handled': 'assigned',
	# §5.4's channel reports, guarded the same way and for the same reason: a report is a phone
	# number and the symptom a person reported from it, which is health data about someone who has
	# not consented to anything by pressing a menu key.
	'channel_reports': 'assigned', 'channel_report_handled': 'assigned',
	# §CHAN-000's call-in queue. Worked by a *health worker* — the section's own wording — and
	# `assigned` is §17.4's scope for that role. §CHAN-004's clinician is named on the session
	# rather than holding a token: `clinician` in the table is scoped `consented_patient`, which is
	# a read of another person's record through a share, and hosting a broadcast is not that.
	# Scheduling a programme is operations, and §17.4's eight roles hold no broadcaster.
	'schedule_live_session': 'infrastructure',
	'live_queue': 'assigned', 'open_live_session': 'assigned', 'close_live_session': 'assigned',
	'answer_live_question': 'assigned', 'decline_live_question': 'assigned',
	# §CHAN-004's moderation queue: what people have offered to share, before any reader sees it.
	'story_queue': 'infrastructure', 'moderate_story': 'infrastructure',
	'chw_profile': 'assigned', 'log_chw_activity': 'assigned', 'submit_case': 'assigned',
	'advance_case': 'assigned', 'peer_alert': 'assigned', 'send_exposure_notice': 'assigned',
	# §10.1's provider-side view. §17.4's clinician row is "Patients who have consented to share",
	# and the scope that carries it is `consented_patient` — a clinician reading a record through a
	# share the patient issued. It is an operator action for that reason: a citizen's catalogue must
	# not carry a screen that reads *another person's* record, which is what this is by construction.
	'provider_view': 'consented_patient',
	# County-level analysis and the provisioning of workers. `hotspots` is here and not in the
	# catalogue: its routes take a `list[AggregateCell]` — a list of objects — and both clients send a
	# `list` field as an array of strings, so the only control a generic form could draw would carry a
	# value the model refuses. The pair is recorded in `API_ONLY`.
	'early_warning': 'county_aggregate',
	'signal_scan': 'county_aggregate',
	# §11.7's six signals feed a county's baseline, and a baseline is what a PHEOC review is
	# triggered from. An ingest a citizen could reach would be a way to page an epidemiologist about
	# nothing, so reporting is the county health team's — the app's own surfaces emit in-process from
	# routes that already carry their own guards.
	'signal_report': 'county_aggregate',
	'provision_chw': 'infrastructure', 'transparency_report': 'audit_logs',
	# The authority's own records: the facility registry every locator reads, the risk zones every
	# device inside them is told about, the county's fever and hotline counts, and the public
	# food-safety warning. Each is guarded on the county health team's scope.
	'food_alert': 'county_aggregate',
	# §MON-007's larviciding round: a public statement about a place, on the same reasoning as the
	# food-safety warning above and the §FND-006 slot below. The read (`larviciding`) is public; a
	# citizen's catalogue must not carry the form that announces a county operation.
	'issue_larviciding': 'county_aggregate',
	# §MON-001's campaign notice, on the same reasoning as the larviciding round and the food-safety
	# warning: it is a public statement addressed to a county's parents, and the route that writes it
	# carries `county_aggregate`. The read (`vaccination_campaigns`) is the parent's and stays.
	'issue_campaign': 'county_aggregate',
	# §SENS-010's register: binding a tag is an act of the same kind as registering the check-in
	# point above it — it is what makes a tap mean something, and a tag anyone can bind is a tag
	# anyone can bind to a medicine package. The taps themselves (`tag_resolve`, `tag_tap`) are
	# deliberately absent: a person holding a phone at a bedside is the caller, and a tap behind an
	# account is a tap nobody makes.
	'tag_bind': 'county_aggregate', 'equipment_add': 'county_aggregate',
	'equipment_move': 'county_aggregate', 'equipment_list': 'county_aggregate',
	# The section's own coverage statement is an audit read, like §13.1's `/sensors/coverage`.
	'tag_coverage': 'audit_logs',
	# §INF-001: a county's risk level is what the county health authority publishes, not something a
	# citizen asserts. The read (`county_risk`) is public; this is the write behind it.
	'set_county_risk': 'infrastructure',
	# The same section's second and third Displays, on the county health team's own scope: case
	# counts and affected sub-counties are the county's epidemiological report, the same scope that
	# guards the surveillance signal they are computed from. A risk *level* is what the authority
	# publishes to the public, which is why it stays a rung above these two.
	'record_case_counts': 'county_aggregate',
	'record_sub_county': 'county_aggregate',
	# §FND-006's appointment times: publishing one is the facility saying it will see people at
	# that hour, which is the same class of claim as its §FND-001 registry row and the same scope
	# that maintains it. Booking, moving and cancelling are the person's own and carry no scope.
	'publish_slot': 'county_aggregate',
}

# Every route this app serves that no catalogue action reaches — the answer to "which of these are
# API-only?" as a file rather than a reader's head. The other direction is asserted too: every
# catalogue action has a route, so the two sets are crossed in both directions by
# `test_api_only.py`, and a route added without either an action or an entry here fails.
#
# It is a *register*, not a defect list. A route here is reachable by someone the catalogue does not
# serve — an operator console, an auditor, a carrier's webhook, a device's own upload — and the
# value that goes with each key is the jurisdiction that reaches it. What the register makes
# impossible is the silent case: a citizen route that no handset can reach, which is what the
# eleven actions added for §REC-001's wallet, §17.2's corrections, §16.3's conflicts and the rest
# were. Those were found by crossing this surface against the catalogue, and this is that cross
# written down so the next one is found by a test rather than by an audit.
#
# The jurisdictions, and why each is not a missing action:
#
#   client_direct   A native client names the path literally and does not draw it from the
#                   catalogue. `GET /mobile/actions` is the catalogue itself, so it cannot be an
#                   entry in it; `POST /auth/anonymous` issues the token every other call needs;
#                   `POST /evidence/upload` is the resumable-upload opener the iOS and Android
#                   evidence screens call by name. Read from the client sources by the test, not
#                   asserted here.
#   device_only     The device's own upload session. The subject lives on the session rather than
#                   in the token, so `require_self` cannot guard it and the owner check is
#                   `_upload_owner` instead. `/facilities/{id}/reports` is the same shape: the
#                   reporter comes from an *optional* token, so the catalogue would have to draw a
#                   form for a route that works without one.
#   citizen_self    A citizen route whose form the client fills from its own session subject
#                   (`_s()` in this module), so the catalogue carries a sibling action that reaches
#                   the same feature. Listed so the register is complete rather than to claim a gap.
#   inbound_wire    An external party posts to it: a carrier's USSD callback, the telco's inbound
#                   SMS, the hotline's follow-up and outcome, a consent granted on a channel.
#                   Authenticated by `require_webhook`'s signature, which no handset can present.
#   device_write    An unguarded write that is a pure computation with nothing stored
#                   (`/facilities/find`, `/sync/delta`, `/emergency/fall`). The same set
#                   `test_ui_vocabulary.UNGATED_WRITES` argues for, restricted to the routes no
#                   action reaches. It is not a place for a route that reads the queue: those are
#                   `citizen_self`, because the queue is shared and only the token can scope it.
#   public_read     A public document — no personal data and no token: the brand, the feature
#                   taxonomy, the personas, the rollout plan, the governance posture. §7.3's
#                   tier model, §4's segments, §21's phases. These are the spec's own tables served
#                   as JSON, and a citizen reading them is the point.
#   <scope>         Guarded on an operator dataset: `audit_logs` (the auditor's own reports),
#                   `infrastructure` (provisioning, registries, governance), `assigned` (the CHW's
#                   caseload and the §18 integration wires), `county_aggregate` and
#                   `national_aggregate` (the county's and PHEOC's own surfaces). These are
#                   reachable by a role the catalogue deliberately does not serve to citizens —
#                   `OPERATOR_SCOPES` above is the mirror of this for the actions that *do* have
#                   one.
API_ONLY: dict[tuple[str, str], str] = {
	# 5 routes: a native client names the path literally, outside the catalogue.
	('GET', '/mobile/actions'): 'client_direct',
	('GET', '/mobile/features'): 'client_direct',
	('GET', '/places/nearest'): 'client_direct',
	('POST', '/auth/anonymous'): 'client_direct',
	('POST', '/evidence/upload'): 'client_direct',

	# 4 routes: the device's own upload session; the subject is on the session.
	('GET', '/evidence/upload/{session_id}'): 'device_only',
	('POST', '/evidence/upload/{session_id}/chunk'): 'device_only',
	('POST', '/evidence/upload/{session_id}/finish'): 'device_only',
	('POST', '/facilities/{facility_id}/reports'): 'device_only',

	# 2 routes: a citizen route whose form the client fills from its own subject.
	('GET', '/triage/{ref}/diary'): 'citizen_self',
	('POST', '/integrations/jali/link'): 'citizen_self',
	# `/sync/batch` was here as `device_write` — "an unguarded write that is the device's own
	# queue". Both halves of that were wrong. It was not unguarded: it had no guard at all and
	# returned *every* caller's pending ops, payloads included, to a request with no token. And the
	# queue is one store shared by every caller, so "the device's own" was a description of what
	# the route was meant to be, not what it read. It is `self`-scoped now and filtered to the
	# caller's ops, which makes `citizen_self` the honest jurisdiction: a citizen route whose
	# subject comes from the token, with `flush_sync` as the catalogue's action over the same queue.
	('POST', '/sync/batch'): 'citizen_self',

	# 8 routes: an external party posts to it, authenticated by signature. The three channel
	# arrivals are here for the same reason the callback is: the carrier holds the shared secret and
	# no handset does. They were catalogue actions until the signature guard landed, and a form a
	# phone could fill was a control that could only ever 401 — the guard is the honest answer, and
	# an action drawing a "your phone number" field to authenticate a carrier was never reachable.
	('POST', '/channels/ussd/callback'): 'inbound_wire',
	('POST', '/channels/ussd'): 'inbound_wire',
	('POST', '/channels/whatsapp'): 'inbound_wire',
	('POST', '/channels/whatsapp/voice'): 'inbound_wire',
	('POST', '/integrations/hotline/follow-up'): 'inbound_wire',
	('POST', '/integrations/hotline/outcome'): 'inbound_wire',
	('POST', '/integrations/telco/sms/inbound'): 'inbound_wire',
	('POST', '/privacy/consent/by-phone'): 'inbound_wire',

	# 3 routes: an unguarded write that is a pure computation with nothing stored.
	('POST', '/emergency/fall'): 'device_write',
	('POST', '/facilities/find'): 'device_write',
	('POST', '/sync/delta'): 'device_write',

	# 35 routes: a public document: no personal data and no token.
	('GET', '/ai/footprint'): 'public_read',
	('GET', '/alerts/socket/stats'): 'public_read',
	('GET', '/auth/whoami'): 'public_read',
	('GET', '/brand'): 'public_read',
	('GET', '/channels/attention'): 'public_read',
	('GET', '/chw/job-aid/{topic}/print'): 'public_read',
	('GET', '/community/misinformation/protocol'): 'public_read',
	('GET', '/facilities/offline-bundle'): 'public_read',
	('GET', '/facilities/{facility_id}/reports'): 'public_read',
	('GET', '/features'): 'public_read',
	('GET', '/features/taxonomy'): 'public_read',
	('GET', '/health'): 'public_read',
	('GET', '/info/questions'): 'public_read',
	('GET', '/integrations/jali/corrections'): 'public_read',
	('GET', '/integrations/pheoc/feeds'): 'public_read',
	('GET', '/integrations/status'): 'public_read',
	('GET', '/integrations/telco/zero-rating'): 'public_read',
	('GET', '/intermediaries/kinds'): 'public_read',
	('GET', '/intermediaries/programme'): 'public_read',
	('GET', '/mental/instruments'): 'public_read',
	('GET', '/personas'): 'public_read',
	('GET', '/personas/segments'): 'public_read',
	('GET', '/places/pharmacies'): 'public_read',
	('GET', '/rollout/acquisition'): 'public_read',
	('GET', '/rollout/acquisition/levers'): 'public_read',
	('GET', '/rollout/app-size'): 'public_read',
	('GET', '/rollout/launch'): 'public_read',
	('GET', '/rollout/phases'): 'public_read',
	('GET', '/rollout/plan'): 'public_read',
	('GET', '/security/disclosure'): 'public_read',
	('GET', '/sensors/accuracy'): 'public_read',
	('GET', '/sync/policy'): 'public_read',
	('POST', '/auth/pkce/authorize'): 'public_read',
	('POST', '/auth/pkce/token'): 'public_read',
	('POST', '/auth/revoke'): 'public_read',

	# 12 routes: guarded on the assigned dataset.
	('GET', '/integrations/adam/case-definitions'): 'assigned',
	('GET', '/integrations/adam/cases/{report_id}'): 'assigned',
	('GET', '/integrations/adam/contacts'): 'assigned',
	('GET', '/integrations/hotline/outcomes'): 'assigned',
	('GET', '/integrations/jali/assessments/{assessment_id}/review'): 'assigned',
	('GET', '/intermediaries/{code}/attribution'): 'assigned',
	('GET', '/triage/rrt/{county}'): 'assigned',
	('POST', '/alerting/service-status'): 'assigned',
	('POST', '/integrations/adam/cases'): 'assigned',
	('POST', '/integrations/adam/monitoring'): 'assigned',
	('POST', '/integrations/jali/assessments'): 'assigned',
	('POST', '/intermediaries/referrals'): 'assigned',

	# 33 routes: guarded on the audit_logs dataset.
	('GET', '/features/claims'): 'audit_logs',
	('GET', '/features/content'): 'audit_logs',
	('GET', '/governance/agreements'): 'audit_logs',
	('GET', '/identity/links'): 'audit_logs',
	('GET', '/identity/model'): 'audit_logs',
	('GET', '/info/health-education'): 'audit_logs',
	('GET', '/metrics/equity'): 'audit_logs',
	('GET', '/metrics/evaluation'): 'audit_logs',
	('GET', '/metrics/kpis'): 'audit_logs',
	('GET', '/metrics/report'): 'audit_logs',
	('GET', '/operations/duties'): 'audit_logs',
	('GET', '/operations/governance'): 'audit_logs',
	('GET', '/operations/incidents'): 'audit_logs',
	('GET', '/operations/risks'): 'audit_logs',
	('GET', '/operations/support-plan'): 'audit_logs',
	('GET', '/operations/sustainability'): 'audit_logs',
	('GET', '/personas/coverage'): 'audit_logs',
	('GET', '/privacy/access-log'): 'audit_logs',
	('GET', '/privacy/dpia/topics'): 'audit_logs',
	('GET', '/privacy/rbac'): 'audit_logs',
	('GET', '/privacy/regulatory'): 'audit_logs',
	('GET', '/problem'): 'audit_logs',
	('GET', '/records/wallet/contents'): 'audit_logs',
	('GET', '/rollout/acquisition/coverage'): 'audit_logs',
	('GET', '/rollout/plan/readiness'): 'audit_logs',
	('GET', '/rollout/readiness'): 'audit_logs',
	('GET', '/rollout/status'): 'audit_logs',
	('GET', '/security/controls'): 'audit_logs',
	('GET', '/security/posture'): 'audit_logs',
	('GET', '/sensors/coverage'): 'audit_logs',
	('GET', '/sensors/tags/{tag_id}/readings'): 'audit_logs',
	('POST', '/privacy/dpia/review'): 'audit_logs',
	('POST', '/transparency/publish'): 'audit_logs',

	# 1 routes: guarded on the audit_logs+infrastructure dataset.
	('GET', '/tier4/activation'): 'audit_logs+infrastructure',

	# 6 routes: guarded on the county_aggregate dataset. Both `POST /ai/hotspots` routes take
	# `list[AggregateCell]` — a list of *objects* — and neither client can build one: Android's
	# `typed()` maps `list` to a `JSONArray` of strings and `Endpoints.jsonValue` to `[String]`, so a
	# field the catalogue renders as one text box arrives as an array of strings and the model refuses
	# it. The county health team's own surface is the scan sibling, `GET /ai/early-warning/{county}/scan`,
	# which the catalogue reaches and which runs the same pipeline end to end from the county's own
	# ledger. `POST /ai/early-warning` used to be here for the same reason; it takes
	# `name=observed=baseline=stdev` strings now, so it is reached.
	('DELETE', '/sensors/tags/{tag_id}'): 'county_aggregate',
	('POST', '/ai/hotspots'): 'county_aggregate',
	('POST', '/ai/hotspots/deploy'): 'county_aggregate',
	('POST', '/facilities'): 'county_aggregate',
	('POST', '/surveillance/geofence'): 'county_aggregate',
	('POST', '/surveillance/signal'): 'county_aggregate',

	# 2 routes: guarded on the county_aggregate+national_aggregate dataset.
	('GET', '/analytics/dashboards'): 'county_aggregate+national_aggregate',
	('GET', '/analytics/dashboards/{dashboard}'): 'county_aggregate+national_aggregate',

	# 23 routes: guarded on the infrastructure dataset.
	('GET', '/facilities/verification'): 'infrastructure',
	('GET', '/governance/capacity'): 'infrastructure',
	('GET', '/governance/egress'): 'infrastructure',
	('GET', '/governance/open-questions'): 'infrastructure',
	('GET', '/governance/residency'): 'infrastructure',
	('GET', '/governance/residency/check'): 'infrastructure',
	('GET', '/governance/stack'): 'infrastructure',
	('POST', '/auth/staff/provision'): 'infrastructure',
	('POST', '/facilities/import-mohf'): 'infrastructure',
	('POST', '/facilities/{facility_id}/correction'): 'infrastructure',
	('POST', '/governance/agreements'): 'infrastructure',
	('POST', '/governance/capacity'): 'infrastructure',
	('POST', '/info/county-office'): 'infrastructure',
	('POST', '/integrations/telco/airtime'): 'infrastructure',
	('POST', '/intermediaries/enrol'): 'infrastructure',
	('POST', '/intermediaries/incentives'): 'infrastructure',
	('POST', '/metrics/measurement'): 'infrastructure',
	('POST', '/operations/duties/{obligation_id}/performed'): 'infrastructure',
	('POST', '/operations/incidents'): 'infrastructure',
	('POST', '/places/import-osm'): 'infrastructure',
	('POST', '/security/scans'): 'infrastructure',
	('POST', '/tier4/activation/fire'): 'infrastructure',
	('POST', '/tier4/deactivate'): 'infrastructure',

	# 2 routes: guarded on the national_aggregate dataset.
	('POST', '/integrations/pheoc/feeds/{feed}'): 'national_aggregate',
	('POST', '/integrations/pheoc/feeds/{feed}/preview'): 'national_aggregate',

}

# Slugs withheld until PHEOC activates the outbreak event (§11.1). Grouped by the feature that
# governs them; every Tier-4 feature that has an action appears here in full. The registry is the
# backstop — `available()` also derives dormancy from the tier model, so a Tier-4 feature added
# later cannot leave a live control behind even if this list is forgotten.
DORMANT_SLUGS: frozenset[str] = frozenset({
	# Ebola-specific triage (TRI-003) and the activation control itself
	'evd_triage', 'activate_outbreak_mode',
	# 21-day contact monitoring (MON-009)
	'enrol_monitoring', 'monitoring_day', 'monitoring_diary', 'monitoring_reminders',
	'monitoring_consent', 'monitoring_members', 'monitoring_member_diary', 'monitoring_officer',
	'remove_household_member', 'request_activation',
	# Community health worker reporting module (COM-101)
	'submit_case', 'advance_case', 'ppe_reminder', 'job_aid', 'chw_cases', 'assign_chw_case',
	'log_chw_activity', 'chw_activity', 'chw_case_load', 'chw_ppe_reminder',
	# Peer alerts (COM-102), contact tracing (COM-103), misinformation tracking (COM-104)
	'peer_alert', 'peer_alert_followup', 'ack_peer_alert',
	'tracing_prompts', 'save_contacts', 'add_contact',
	'share_contacts', 'contact_shares', 'withdraw_contact_shares',
	'flag_misinformation', 'misinformation_clusters', 'misinformation_notices',
	# Exposure notification (ALT-004)
	'send_exposure_notice', 'ack_exposure',
	# Proximity log (LOC-002), location history (LOC-003), check-in points (LOC-004), border (LOC-005)
	'rotate_ebid', 'log_encounter', 'declare_exposure', 'check_exposure',
	'enable_location_history', 'log_location', 'location_report', 'share_location_report',
	'location_report_shares', 'purge_location',
	'register_checkin_point', 'check_in', 'checkin_points', 'checkin_list', 'checkin_followup',
	'register_border', 'border_status', 'traveller_declare', 'traveller_prompt', 'traveller_report',
	# Outbreak AI (AI-001..003)
	'risk_score', 'early_warning', 'signal_scan', 'signal_report',
	# Outbreak-mode sensors: acoustic cough (SENS-002), camera symptom capture (SENS-004)
	'analyse_cough', 'submit_evidence',
	# Respiration-rate estimation (SENS-001). The route derives a rate from a motion series rather
	# than storing one the device already computed, and it is gated on the same tier as the ingest —
	# so the action is dark until PHEOC declares the event, which is what the section's own tier
	# says about the whole sensor.
	'estimate_breathing',
})


def tier4_feature_ids() -> frozenset[str]:
	"""Feature ids the §7.3 tier model puts at Tier 4, read from the registry.

	Deriving this rather than restating it is what keeps the catalogue honest: the dormancy list
	is prose a person maintains, this is the model, and `available()` obeys both.
	"""
	from afya.registry.service import FeatureRegistry, Tier
	return frozenset(f.id for f in FeatureRegistry().by_tier(Tier.tier4))


def _f(name: str, label: str, type_: str = 'text', options: list[str] | None = None, ph: str | None = None, client_supplied: bool = False, server_assigned: bool = False, when: str | None = None, equals_any: list[str] | None = None, distinct_from: str | None = None, form: bool = False, accept: str | None = None) -> MobileField:
	"""A field, with nothing said about whether it is required.

	`required` is deliberately absent here. It used to be `type_ == 'path'`, which is a fact about the
	field rather than about the route, and it was wrong for every body field in the catalogue. What
	the route needs is only knowable from the route, so `marked()` fills it at serve time from
	`afya.access.forms.required_fields` — the same reading §ACC-001's drop list is checked against, so
	the form and the drop list cannot disagree about what a route requires.

	`when` states the condition the route's own model enforces, and is the one thing about
	requiredness a field *can* know by itself: it is a property of the answers, not of the route.
	"""
	condition = FieldCondition(when=when, equals_any=equals_any or []) if when else None
	return MobileField(name=name, label=label, type=cast(FieldType, type_), options=options, placeholder=ph, client_supplied=client_supplied, server_assigned=server_assigned, condition=condition, distinct_from=distinct_from, form=form, accept=accept)


def _auto(name: str, label: str) -> MobileField:
	"""A reference the server mints. Carried so a client can send one, marked so no form asks for it.

	The model gives it a `default_factory`, so a request that omits it is complete; the field is in
	the catalogue because an offline client wants to mint its own and have the replay keep the same
	reference. A form that drew it would be asking a person to invent a primary key.
	"""
	return _f(name, label, server_assigned=True)


def _s(type_: str = 'text', form: bool = False) -> MobileField:
	"""The caller's own subject: carried so the client can send it, marked so no form draws it.

	Every route that carries one binds it to the token (§17), so a person typing a different subject
	would be offered a control the server refuses. The label is never shown.
	"""
	return _f('subject_ref', 'Me', type_, client_supplied=True, form=form)


def crossings(act: MobileAction) -> list[str]:
	"""Every way an action's vocabulary can offer a control no client can draw or answer it can't send.

	The one predicate, read by two callers: `_a()` refuses to build an action that fails it, and
	`tests/ci/test_catalogue_vocabulary.py` reads it off the *served* document so an action built
	anywhere else is caught too. Returning the findings rather than asserting is what lets the gate
	print all of them and lets a canary plant one and watch the gate notice.

	Each entry is a crossing between two facts the catalogue states, which is why none of them can be
	seen by reading one field:

	* `options` is a *closed* answer set. Only a control that offers the set can produce a value from
	  it, and both clients offer one on a `select` alone. An `options` list on any other type is a
	  vocabulary on the wire that the person types past — the three `outbreak_support` slugs were the
	  section's own names and reached the route as whatever was typed, so a near miss 422'd with the
	  person holding a form that looked complete.
	* `placeholder` is drawn by the text controls only. A hint on a toggle, a picker or a file button
	  exists in the served document and on no screen.
	* `equals_any` names the answers that fire a condition. A value the trigger cannot produce makes
	  the condition dead code the form cannot make true — the mirror of the defect it exists to close.
	* `distinct_from` names another question; a field naming one the action lacks is a rule both
	  clients evaluate against `""` and never fire.
	* `accept` is the picker's filter for a `file` and nothing else has a picker; `form` is the
	  transport of the *whole* body, so a body half multipart and half JSON is a request no route
	  reads.
	"""
	bad: list[str] = []
	names = {f.name for f in act.fields}
	by_name = {f.name: f for f in act.fields}
	for f in act.fields:
		if f.options and f.type != 'select':
			bad.append(f'{act.id}.{f.name}: options on a {f.type!r}, which neither client offers as a set')
		if f.options and len(set(f.options)) != len(f.options):
			bad.append(f'{act.id}.{f.name}: duplicate options')
		if f.type == 'select' and not f.options:
			bad.append(f'{act.id}.{f.name}: a select with nothing to select')
		if f.accept and f.type != 'file':
			bad.append(f'{act.id}.{f.name}: accept on a {f.type!r} field')
		if f.type == 'file' and not f.accept:
			bad.append(f'{act.id}.{f.name}: a file with no accepted type')
		if f.type == 'file' and not f.form:
			bad.append(f'{act.id}.{f.name}: a file outside a multipart body')
		if f.server_assigned and f.condition:
			bad.append(f'{act.id}.{f.name}: a server value cannot be conditional')
		if f.placeholder and f.type in ('bool', 'select', 'file'):
			bad.append(f'{act.id}.{f.name}: a placeholder on a {f.type!r}, which neither client draws')
		if f.distinct_from is not None and f.distinct_from not in names:
			bad.append(f'{act.id}.{f.name}: distinct_from names {f.distinct_from!r}, which it lacks')
		if f.condition is None:
			continue
		trigger = by_name.get(f.condition.when)
		if trigger is None:
			bad.append(f'{act.id}.{f.name}: condition names {f.condition.when!r}, which it lacks')
			continue
		if f.condition.equals_any:
			offered = set(trigger.options or ()) | ({'true', 'false'} if trigger.type == 'bool' else set())
			unreachable = sorted(set(f.condition.equals_any) - offered)
			if unreachable:
				bad.append(f'{act.id}.{f.name}: condition fires on {unreachable}, which '
				           f'{trigger.name!r} cannot produce')
	forms = {f.form for f in act.fields}
	if len(forms) > 1:
		bad.append(f'{act.id}: a body is multipart or JSON, not both')
	return bad


def _a(id: str, title: str, group: str, method: str, path: str, fields: list[MobileField], any_of: list[FieldGroup] | None = None) -> MobileAction:
	"""One action, with every crossing between its fields refused here rather than shipped.

	The crossings themselves are `crossings()` — one predicate, two callers, so the constructor and
	the gate that reads the served document cannot disagree about what a fillable form is.
	"""
	assert method in ('GET', 'POST', 'DELETE') and all(fl.type in FIELD_TYPES for fl in fields), 'contract'
	assert id in FEATURE_OF, f'action {id} must declare its source feature in FEATURE_OF'
	names = [fl.name for fl in fields]
	assert len(names) == len(set(names)), f'{id}: duplicate field names in {names}'
	act = MobileAction(id=id, title=title, group=group, method=method, path=path, fields=fields, any_of=any_of or [])
	assert not (found := crossings(act)), f'{id}: unfillable vocabulary: {found}'
	return act


def catalogue() -> list[MobileAction]:
	triage_fields = [_f('symptoms', 'Symptoms', 'list', ph='fever, headache'),
		_f('temperature_c', 'Temperature °C', 'decimal'),
		_f('ebola_contact', 'Contact with someone sick with Ebola?', 'bool'),
		_f('affected_area_travel', 'Been to an area with an outbreak?', 'bool'),
		_f('exposure_site', 'Attended a funeral or other known exposure site?', 'bool'),
		_f('exposures', 'Exposures', 'list', ph='funeral_attendance, bushmeat_consumption'),
		_f('isolation', 'Isolating?', 'select', ['not_isolated', 'isolated_at_home', 'isolated_at_facility']),
		_f('red_flags', 'Red flags', 'list', ph='convulsions, confusion, bleeding gums'),
		_f('age_band', 'Age', 'select', ['under_5', '5_17', '18_49', '50_64', '65_plus']),
		_f('pregnant', 'Pregnant?', 'bool')]
	return [
		# Triage
		_a('febrile_triage', 'Check a fever', 'Triage', 'POST', '/triage/preliminary', triage_fields),
		_a('evd_triage', 'Ebola check', 'Triage', 'POST', '/triage/evd', triage_fields),
		_a('differential', 'What illness could this be?', 'Triage', 'POST', '/triage/diagnose', triage_fields),
		_a('symptom_diary', 'Log how I feel today', 'Triage', 'POST', '/triage/diary', [_auto('entry_id', 'Entry number'), _s(), _f('day', 'Day (1-21)', 'int'), _f('symptoms', 'Symptoms', 'list'), _f('temperature_c', 'Temperature °C', 'decimal'), _f('red_flags', 'Red flags', 'list', ph='convulsions, confusion'), _f('logged_at_iso', 'When', 'text', ph='2026-10-12T08:30')]),
		_a('diary_trend', 'Am I getting better or worse?', 'Triage', 'GET', '/triage/{ref}/diary/trend', [_f('ref', 'Your reference', 'path')]),
		_a('diary_export', 'Share my diary with a clinician', 'Triage', 'GET', '/triage/{ref}/diary/export', [_f('ref', 'Your reference', 'path')]),
		_a('diary_prompt', 'Today\'s check-in', 'Triage', 'GET', '/triage/{ref}/diary/prompt', [_f('ref', 'Your reference', 'path'), _f('day', 'Day (1-21)', 'int'), _f('opted_in', 'Send me a daily reminder', 'bool')]),
		# §TRI-002's "automatic escalation if new red flags are logged". The trend route above shows
		# the shape of the diary; this is the one that acts on it, and nothing reached it — so the
		# escalation the section promises when a red flag appears was computed and never shown. A
		# `null` answer is the normal case and is not an error: it means nothing new is red-flagged.
		_a('diary_escalation', 'Has anything changed since yesterday?', 'Triage', 'GET', '/triage/{ref}/diary/escalation', [_f('ref', 'Your reference', 'path')]),
		_a('what_should_i_do', 'What should I do?', 'Triage', 'GET', '/info/decision-tree', [
			_f('answers', 'Answers so far', ph='yes,no,leave blank to start'),
			_f('entry', 'Where you started', 'select', ['root', 'household'])]),
		_a('entry_answers', 'What do you need help with?', 'Triage', 'GET', '/info/entry-answers', []),
		# Information library (§6.2, INF-003/004/008/009/010/015)
		_a('health_library', 'Health information', 'Information', 'GET', '/info/library', [_f('lang', 'Language', 'select', ['en', 'sw'])]),
		# §INF-004's own four Features. `health_library` above reaches the corpus but opens a flat
		# list; these are the operations the section names over it — find a rumour, see the
		# categories, ask whether something is true, and forward the correction.
		_a('search_library', 'Search health information', 'Information', 'GET', '/info/library', [_f('q', 'What are you looking for?'), _f('lang', 'Language', 'select', ['en', 'sw'])]),
		_a('library_categories', 'Browse by topic', 'Information', 'GET', '/info/library/categories', [_f('lang', 'Language', 'select', ['en', 'sw'])]),
		_a('myth_library', 'What is rumour and what is true?', 'Information', 'GET', '/info/myths', [_f('lang', 'Language', 'select', ['en', 'sw']), _f('q', 'Something you heard', ph='optional')]),
		_a('ask_about_a_rumour', 'Is it true that…?', 'Information', 'POST', '/info/myths/ask', [_f('claim', 'What did you hear?', 'textarea'), _f('lang', 'Language', 'select', ['en', 'sw'])]),
		_a('hotline_directory', 'Useful phone numbers', 'Information', 'GET', '/info/hotlines', []),
		# §CHAN-000's call-in and §CHAN-004's clinician Q&A, from the listener's side. A person
		# hears a programme announced, asks a question on it while it is on air, and reads back what
		# was answered if they missed it — three controls, and the *asker is the token*, so there is
		# no field here for a subject: the route derives a §SEC-004 handle from whoever holds it.
		_a('live_sessions', 'Programmes on air', 'Information', 'GET', '/live/sessions',
		   [_f('platform', 'Where?', 'select', [k.value for k in LivePlatform]), _f('status', 'When?', 'select', [k.value for k in LiveStatus])]),
		_a('ask_live_question', 'Ask a question on air', 'Information', 'POST', '/live/sessions/{session_id}/questions',
		   [_f('session_id', 'Programme', 'path'), _f('text', 'Your question', 'textarea'), _f('lang', 'Language', 'select', ['en', 'sw'])]),
		_a('live_transcript', 'What was answered', 'Information', 'GET', '/live/sessions/{session_id}/transcript',
		   [_f('session_id', 'Programme', 'path')]),
		# §CHAN-004's user-generated content. `subject_ref` is carried because the consent match needs
		# the subject — a §SEC-004 handle is a different value derived from it, so a submission naming
		# only the handle could never find its own consent and the check would silently never fire.
		# The route binds it to the token, so a person cannot file a story against someone else's.
		_a('submit_story', 'Share your experience', 'Information', 'POST', '/info/stories',
		   [_s(), _f('kind', 'What kind of story?', 'select', [k.value for k in StoryKind]),
		    _f('author_role', 'Who are you?', ph='e.g. community health worker, parent, patient'),
		    _f('text', 'Your story', 'textarea'), _f('lang', 'Language', 'select', list(CONTENT_LANGS)),
		    _f('consent_id', 'Consent record', ph='the consent you gave when you agreed to share this')]),
		_a('county_risk', 'How is my county doing?', 'Information', 'GET', '/info/dashboard/{county}', [_f('county', 'County', 'path')]),
		_a('set_county_risk', 'Update a county status', 'Information', 'POST', '/info/dashboard/{county}', [_f('county', 'County', 'path'), _f('risk_level', 'Risk level', 'select', ['low', 'moderate', 'high']), _f('active_signals', 'Active signals', 'int'), _f('bulletin', 'What should people do?', 'textarea'), _f('source', 'Source', ph='county health office')]),
		_a('record_case_counts', 'Record case counts', 'Information', 'POST', '/info/dashboard/{county}/cases', [_f('county', 'County', 'path'), _f('disease', 'Disease', 'select', list(DISEASES)), _f('confirmed', 'Confirmed cases', 'int'), _f('suspected', 'Suspected cases', 'int'), _f('as_of_iso', 'Counted up to (date)', ph='YYYY-MM-DD')]),
		_a('record_sub_county', 'Record an affected area', 'Information', 'POST', '/info/dashboard/{county}/sub-counties', [_f('county', 'County', 'path'), _f('sub_county', 'Sub-county', ph='e.g. Teso North'), _f('disease', 'Disease', 'select', list(DISEASES)), _f('confirmed', 'Confirmed cases', 'int'), _f('suspected', 'Suspected cases', 'int'), _f('locations', 'Places affected', 'list', ph='e.g. Amagoro market, Kocholia'), _f('as_of_iso', 'Counted up to (date)', ph='YYYY-MM-DD')]),
		_a('service_status', 'Are services open today?', 'Information', 'GET', '/alerting/service-status', [_f('county', 'County', ph='optional')]),
		_a('testing_sites', 'Where can I get tested?', 'Facilities', 'GET', '/places/testing-sites', [
			_f('lat', 'Latitude', 'decimal'), _f('lon', 'Longitude', 'decimal'),
			_f('limit', 'How many results', 'int'),
			_f('test', 'Which test?', ph='e.g. malaria, HIV, TB'),
			_f('max_cost_kes', 'Most I can pay (KES)', 'int', ph='leave blank if cost does not matter'),
			_f('max_turnaround_hours', 'Results within how many hours?', 'int')]),
		_a('vaccination_points', 'Where can I get vaccinated?', 'Facilities', 'GET', '/places/vaccination-points', [
			_f('lat', 'Latitude', 'decimal'), _f('lon', 'Longitude', 'decimal'),
			_f('limit', 'How many results', 'int'),
			_f('vaccine', 'Which vaccine?', ph='e.g. measles, polio, HPV'),
			_f('age_months', 'Age in months', 'int', ph='for a child; leave blank for an adult'),
			_f('max_cost_kes', 'Most I can pay (KES)', 'int'),
			_f('walk_in_only', 'Walk-in only', 'bool')]),
		# §LOC-001's two paths, and they are two actions because they are two routes with different
		# guards. `risk_zones_near_me` asks which zones cover a point and is open: nothing about the
		# caller is recorded, so it carries no `subject_ref` at all — the route refuses one rather
		# than comparing it, because an unbound subject on an open route is an IDOR. `my_zone_events`
		# is the opted-in half: entry and exit against the person's own switch, guarded by
		# `require_self`, and that is why its `subject_ref` is `client_supplied`.
		_a('risk_zones_near_me', 'Have I entered a risk area?', 'Alerts', 'GET', '/surveillance/geofences-at', [_f('lat', 'Latitude', 'decimal'), _f('lon', 'Longitude', 'decimal'), _f('lang', 'Language', 'select', TRAVELLER_LANGS)]),
		_a('my_zone_events', 'Which zone did I enter or leave?', 'Alerts', 'GET', '/location/zones/{subject_ref}', [_f('subject_ref', 'Me', 'path', client_supplied=True), _f('lat', 'Latitude', 'decimal'), _f('lon', 'Longitude', 'decimal'), _f('lang', 'Language', 'select', TRAVELLER_LANGS)]),
		_a('zone_alerts_setting', 'Am I getting zone alerts?', 'Alerts', 'GET', '/location/zone-alerts/{subject_ref}', [_f('subject_ref', 'Me', 'path', client_supplied=True)]),
		_a('set_zone_alerts', 'Turn zone alerts on or off', 'Alerts', 'POST', '/location/zone-alerts/{subject_ref}', [_f('subject_ref', 'Me', 'path', client_supplied=True), _f('enabled', 'Alerts on', 'bool')]),
		_a('publish_content', 'Draft health information', 'Information', 'POST', '/info/content', [_f('item_id', 'Reference'), _f('title', 'Title'), _f('body', 'Text', 'textarea'), _f('lang', 'Language', 'select', list(CONTENT_LANGS)), _f('harmony_tag', 'Official source tag'), _f('slug', 'Short name'), _f('owner', 'Who owns this'), _f('reviewer', 'Who reviewed it'), _f('reviewed_on_iso', 'Review date', ph='YYYY-MM-DD'), _f('version', 'Version', 'int'), _f('stage', 'Stage', 'select', CONTENT_STAGES)]),
		_a('advance_content', 'Move a draft forward', 'Information', 'POST', '/info/content/{item_id}/advance', [_f('item_id', 'Reference', 'path'), _f('to', 'Next stage', 'select', CONTENT_STAGES)]),
		_a('content_governance', 'Who reviewed this?', 'Information', 'GET', '/info/content/governance', [_f('today_iso', 'As at', ph='YYYY-MM-DD'), _f('regime', 'Review cycle', 'select', ['steady', 'outbreak'])]),
		_a('report_content_error', 'Report a wrong guidance item', 'Information', 'POST', '/info/content/errors', [_f('error_id', 'Reference'), _f('item_id', 'Item reference'), _f('found_by', 'Found by'), _f('what_is_wrong', 'What is wrong', 'textarea'), _f('correction_en', 'Correction (English)', 'textarea'), _f('correction_sw', 'Correction (Kiswahili)', 'textarea'), _f('replacement_slug', 'Replacement short name')]),
		_a('content_errors', 'What guidance was found wrong?', 'Information', 'GET', '/info/content/errors', []),
		# `BackTranslation._the_renderer_is_not_the_translator`: the two names must differ, because "a
		# back-translation rendered by the translator is not a back-translation". This is *not* a
		# condition — `required = (a != b)` is false for every answer a person gives — so it is
		# carried as its own flag, which lets a client label the pair without pretending to a rule it
		# cannot evaluate. Both are marked required by `marked()`, from the route.
		_a('record_back_translation', 'Record a back-translation', 'Information', 'POST', '/info/content/back-translation', [_f('item_id', 'Translation reference'), _f('translated_by', 'Translated by'), _f('back_translated_by', 'Rendered back by', ph='someone who has not seen the source', distinct_from='translated_by'), _f('back_translation', 'Text rendered back into English', 'textarea')]),
		_a('record_community_validation', 'Record community validation', 'Information', 'POST', '/info/content/community-validation', [_f('item_id', 'Translation reference'), _f('validated_by', 'Taken to the community by'), _f('validator_role', 'Their community role', ph='religious leader, community elder, anthropologist'), _f('concerns', 'What the community raised', 'list')]),
		_a('content_localisation', 'How was this translated?', 'Information', 'GET', '/info/content/localisation', []),
		# Facilities
		_a('nearest_facilities', 'Find care near me', 'Facilities', 'POST', '/facilities/nearest', [_f('lat', 'Latitude', 'decimal'), _f('lon', 'Longitude', 'decimal'), _f('kind', 'Type of place', 'select', FACILITY_KINDS), _f('limit', 'How many results', 'int')]),
		_a('ed_status', 'How busy is the emergency unit?', 'Facilities', 'GET', '/facilities/{facility_id}/ed-status', [_f('facility_id', 'Facility', 'path')]),
		_a('report_wait', 'Report the queue length', 'Facilities', 'POST', '/facilities/{facility_id}/wait', [_f('facility_id', 'Facility', 'path'), _f('minutes', 'Minutes waited', 'int')]),
		_a('book_appointment', 'Book an appointment', 'Facilities', 'POST', '/facilities/{facility_id}/booking', [_f('facility_id', 'Facility', 'path'), _auto('booking_id', 'Booking number'), _f('slot_iso', 'Appointment time', ph='e.g. 2026-10-20T09:00+03:00')]),
		_a('view_slots', 'What times are free?', 'Facilities', 'GET', '/facilities/{facility_id}/slots', [_f('facility_id', 'Facility', 'path'), _f('day_iso', 'Which day', ph='YYYY-MM-DD')]),
		_a('reschedule_appointment', 'Move my appointment', 'Facilities', 'POST', '/facilities/booking/{booking_id}/reschedule', [_f('booking_id', 'Booking number', 'path'), _f('slot_iso', 'New appointment time', ph='e.g. 2026-10-22T14:00+03:00')]),
		_a('cancel_appointment', 'Cancel my appointment', 'Facilities', 'POST', '/facilities/booking/{booking_id}/cancel', [_f('booking_id', 'Booking number', 'path')]),
		_a('publish_slot', 'Offer appointment times', 'Facilities', 'POST', '/facilities/{facility_id}/slots', [_f('facility_id', 'Facility', 'path'), _f('slot_iso', 'Time you will see people', ph='e.g. 2026-10-20T09:00+03:00'), _f('capacity', 'How many people at that time', 'int', ph='leave blank for one')]),
		# Medicine
		_a('verify_medicine', 'Is my medicine genuine?', 'Medicine', 'POST', '/medicine/verify', [_f('batch_number', 'Batch number (on the box)'), _f('gtin', 'Barcode number')]),
		_a('drug_interactions', 'Can I take these together?', 'Medicine', 'POST', '/medicine/interactions',
			[_f('drugs', 'Medicines', 'list', ph='e.g. warfarin, aspirin'),
			 _f('pregnant', 'Pregnant or breastfeeding', 'bool'),
			 _f('age_months', 'Age in months (for a child)', 'int'),
			 _f('conditions', 'Ongoing conditions', 'list',
			    ph='e.g. Kidney problems, Asthma')]),
		# `mg_per_kg` was a field here and is gone: it asked a parent for the one constant the
		# calculator exists to look up, so the action answered a multiplication. `age_months` is the
		# section's own "Enter weight and age", and it is what zinc's dose turns on.
		_a('dosage', 'How much should I give?', 'Medicine', 'POST', '/medicine/dose', [_f('drug', 'Medicine', ph='e.g. paracetamol, amoxicillin, zinc'), _f('weight_kg', 'Weight in kg', 'decimal'), _f('age_months', 'Age in months', 'int', ph='optional; needed for zinc')]),
		_a('report_stock', 'Report whether a medicine is in stock', 'Medicine', 'POST', '/medicine/stock', [_auto('report_id', 'Report number'), _f('facility_id', 'Facility'), _f('drug', 'Medicine'), _f('in_stock', 'In stock?', 'bool'), _f('reporter_geohash', 'Where you are', ph='optional; lets us check you are at the facility')]),
		_a('find_stock', 'Where can I get this medicine?', 'Medicine', 'GET', '/medicine/stock/search', [_f('q', 'Which medicine?'), _f('limit', 'How many places', 'int', ph='optional')]),
		_a('stock_availability', 'Is it in stock right now?', 'Medicine', 'GET', '/medicine/stock/availability', [_f('drug', 'Medicine'), _f('facility_id', 'Facility')]),
		_a('essential_medicines', 'Essential medicines', 'Medicine', 'GET', '/medicine/essential', []),
		_a('restock_alerts', 'What came back in stock?', 'Medicine', 'GET', '/medicine/stock/alerts', [_f('facility_id', 'Facility', ph='optional')]),
		_a('medicine_registry', 'Which medicines are approved?', 'Medicine', 'GET', '/medicine/registry', [_f('since', 'Only changes since', ph='optional')]),
		_a('medicine_recalls', 'Has a medicine been recalled?', 'Medicine', 'GET', '/medicine/recalls', [_f('since', 'Only changes since', ph='optional')]),
		# `SuspiciousReport._names_something`: "a suspicious-medicine report needs a gtin or a batch
		# number". Either satisfies the route, so neither is required on its own — which is what the
		# placeholders said in prose ("optional if you have the batch") and what no form could act on:
		# both drew as optional, and a person with neither was refused. Marking each required-when-the-
		# other-is-blank would be the mirror defect, demanding both from an empty form.
		_a('report_suspicious_medicine', 'Report a fake medicine', 'Medicine', 'POST', '/medicine/suspicious', [_f('gtin', 'Barcode number', ph='if you have it'), _f('batch_number', 'Batch number', ph='if you have it'), _f('note', 'What is wrong?', 'textarea'), _f('photo_sha256', 'Photo of the packaging', ph='from the camera upload')],
			any_of=[FieldGroup(fields=['gtin', 'batch_number'])]),
		# Emergency
		# §EMG-001's fan-out: where the person is, how serious, who to tell and what to attach.
		# `contacts` is the section's "up to three emergency contacts" and the model caps it at
		# three, so a fourth is refused rather than silently dropped — a dropped contact is a person
		# who was never told. `channel` is the client's own answer to whether it has data, which is
		# the half of the section's SMS claim only the client can know.
		_a('sos', 'Get help now', 'Emergency', 'POST', '/emergency/sos', [_auto('sos_id', 'Alert number'), _f('lat', 'Latitude', 'decimal'), _f('lon', 'Longitude', 'decimal'), _f('severity', 'How serious?', 'select', ['low', 'medium', 'high']), _f('symptoms', 'Symptoms', 'list'), _f('contacts', 'Who to alert', 'list', ph='name:number, name:number (up to three)'), _f('channel', 'How you are sending this', 'select', ['native', 'sms']), _f('blood_group', 'Blood group', 'select', BLOOD_GROUPS), _f('allergies', 'Allergies', 'list', ph='optional'), _f('conditions', 'Ongoing conditions', 'list', ph='optional'), _f('medications', 'Medicines', 'list', ph='optional')]),
		# The countdown and its two exits. The client owns the timer — §ACC-004 wants no background
		# polling and §EMG-001's Offline note wants the alert to work with no data — so what travels
		# is the window: arming returns the deadline the client counts to, and the two exits are the
		# calls it makes when the timer expires or the person stops it.
		_a('sos_countdown', 'Start the emergency countdown', 'Emergency', 'POST', '/emergency/sos/arm', [_f('lat', 'Latitude', 'decimal'), _f('lon', 'Longitude', 'decimal'), _f('severity', 'How serious?', 'select', ['low', 'medium', 'high']), _f('symptoms', 'Symptoms', 'list'), _f('contacts', 'Who to alert', 'list', ph='name:number, name:number (up to three)'), _f('channel', 'How you are sending this', 'select', ['native', 'sms'])]),
		_a('sos_cancel', 'Stop the alert', 'Emergency', 'POST', '/emergency/sos/{sos_id}/cancel', [_f('sos_id', 'Alert number', 'path')]),
		_a('sos_fire', 'Send the alert now', 'Emergency', 'POST', '/emergency/sos/{sos_id}/fire', [_f('sos_id', 'Alert number', 'path')]),
		_a('sos_state', 'What happened to my alert?', 'Emergency', 'GET', '/emergency/alert/{sos_id}', [_f('sos_id', 'Alert number', 'path')]),
		_a('emergency_card', 'My emergency card', 'Emergency', 'POST', '/emergency/card/qr', [_f('name', 'Full name'), _f('blood_group', 'Blood group', 'select', BLOOD_GROUPS), _f('allergies', 'Allergies', 'list'), _f('conditions', 'Ongoing conditions', 'list'), _f('emergency_contacts', 'Who to call', 'list', ph='name:number, name:number')]),
		# Records & wallet
		_a('immunisation_gaps', 'Which vaccines are missing?', 'Records', 'GET', '/records/{member_ref}/immunisation-gaps', [_f('member_ref', 'Family member', 'path')]),
		_a('family_wallet', 'Family health wallet', 'Records', 'GET', '/records/{guardian_ref}/wallet', [_f('guardian_ref', 'Guardian', 'path')]),
		# §REC-001's wallet had readers and no writer: a guardian could see the family wallet and
		# every document in it, and no action enrolled a member into it, so the wallet a person
		# could read was one nothing could fill. The route is guarded `require_self_or_guardian`
		# with `may_create`, so the guardian is the token's own and no form draws one.
		_a('add_family_member', 'Add someone to my wallet', 'Records', 'POST', '/records/member', [_auto('member_ref', 'Reference'), _f('name', 'Their name', ph='optional'), _f('dob_iso', 'Date of birth'), _f('is_minor', 'Under 18?', 'bool')]),
		_a('growth_flag', 'Is my child growing well?', 'Records', 'POST', '/records/growth', [_f('member_ref', 'Family member'), _f('age_months', 'Age in months', 'int'), _f('weight_kg', 'Weight in kg', 'decimal'), _f('height_cm', 'Height in cm', 'decimal'), _f('sex', 'Boy or girl?', 'select', ['boy', 'girl']), _f('head_circumference_cm', 'Head size in cm', 'decimal', ph='optional'), _f('muac_mm', 'Mid-upper arm in mm', 'decimal', ph='optional')]),
		# §REC-003's milestone checklist, in Annex 9's two halves: read the list, then report it.
		_a('milestone_checklist', 'What should my child be doing?', 'Records', 'GET', '/records/{member_ref}/milestones', [_f('member_ref', 'Family member', 'path'), _f('age_months', 'Age in months', 'int')]),
		_a('milestone_check', 'Milestones my child has reached', 'Records', 'POST', '/records/milestones', [_f('member_ref', 'Family member'), _f('age_months', 'Age in months', 'int'), _f('present', 'Skills the child can do', 'list', ph='from the checklist'), _f('lost', 'Skills the child has stopped doing', 'list', ph='leave empty if none'), _f('checked_earlier', 'Were the earlier age groups also checked?', 'bool')]),
		_a('add_lab', 'Add a lab result', 'Records', 'POST', '/records/labs', [_f('member_ref', 'Family member'), _f('test', 'Test', 'select', ['mRDT', 'widal', 'hba1c', 'fbc', 'viral_load', 'glucose_f', 'bp', 'other']), _f('value', 'Result'), _f('unit', 'Unit', ph='optional'), _f('flag', 'Is it normal?', 'select', ['normal', 'abnormal', 'critical', 'unknown']), _f('performed_iso', 'Date of test')]),
		_a('view_labs', 'My lab results', 'Records', 'GET', '/records/{ref}/labs', [_f('ref', 'Family member', 'path')]),
		# §9.2 REC-001 and §10.1 REC-002: the wallet's documents, and the operations over them.
		_a('wallet_documents', 'Everything in the wallet', 'Records', 'GET', '/records/{member_ref}/documents', [_f('member_ref', 'Family member', 'path'), _f('kind', 'Type of document', 'select', list(WALLET_DOC_KINDS))]),
		_a('file_document', 'Add a document', 'Records', 'POST', '/records/documents', [_auto('doc_id', 'Reference'), _f('member_ref', 'Family member'), _f('kind', 'Type of document', 'select', list(WALLET_DOC_KINDS)), _f('title', 'What is it?'), _f('occurred_iso', 'Date on the document'), _f('detail', 'What does it say?', 'textarea'), _f('facility_id', 'Facility', ph='optional'), _f('media_ref', 'Photo reference', ph='from the camera upload'), _f('captured_iso', 'When the photo was taken')]),
		_a('health_timeline', 'My health history', 'Records', 'GET', '/records/timeline', []),
		_a('wallet_search', 'Find a document', 'Records', 'GET', '/records/search', [_f('q', 'What are you looking for?')]),
		_a('share_record', 'Share my record', 'Records', 'POST', '/records/share', [_auto('grant_id', 'Share reference'), _f('member_ref', 'Family member'), _f('recipient', 'Who is it for?', ph='leave blank for a link'), _f('kinds', 'What they can see', 'list', ph=', '.join(WALLET_DOC_KINDS)), _f('issued_iso', 'From'), _f('expires_iso', 'Until')]),
		_a('record_shares', 'Who has seen my record?', 'Records', 'GET', '/records/{member_ref}/shares', [_f('member_ref', 'Family member', 'path')]),
		_a('revoke_share', 'Stop sharing', 'Records', 'POST', '/records/share/{grant_id}/revoke', [_f('grant_id', 'Share reference', 'path')]),
		_a('provider_view', 'A patient record shared with me', 'Records', 'GET', '/records/share/{grant_id}/view', [_f('grant_id', 'Share reference', 'path'), _f('at_iso', 'As at')]),
		_a('export_record', 'Export a health record', 'Records', 'GET', '/records/{member_ref}/export', [_f('member_ref', 'Family member', 'path'), _f('fmt', 'Format', 'select', ['pdf', 'json']), _f('at_iso', 'As at')]),
		_a('backup_wallet', 'Back up the wallet', 'Records', 'POST', '/records/{member_ref}/backup', [_f('member_ref', 'Family member', 'path'), _f('at_iso', 'As at')]),
		_a('growth_chart', 'My child growth chart', 'Records', 'GET', '/records/{member_ref}/growth-chart', [_f('member_ref', 'Family member', 'path'), _f('sex', 'Boy or girl?', 'select', ['boy', 'girl'])]),
		_a('vaccination_certificate', 'Vaccination certificate', 'Records', 'GET', '/records/{member_ref}/vaccination-certificate', [_f('member_ref', 'Family member', 'path'), _f('purpose', 'What is it for?', 'select', ['travel', 'school', 'employment']), _f('at_iso', 'As at')]),
		_a('register_donor', 'Register as a blood donor', 'Records', 'POST', '/blood/donors', [_f('donor_ref', 'Donor reference'), _f('blood_group', 'Blood group', 'select', BLOOD_GROUPS), _f('county', 'County'), _f('last_donation_iso', 'Last donation date', ph='optional')]),
		_a('find_donors', 'Find blood donors', 'Records', 'POST', '/blood/match', [_f('request_id', 'Request number'), _f('blood_group', 'Group needed', 'select', BLOOD_GROUPS), _f('county', 'County'), _f('urgency', 'How urgent?', 'select', ['routine', 'urgent', 'critical'])]),
		_a('donor_alerts', 'Who should we call for blood?', 'Records', 'POST', '/blood/alerts', [_f('request_id', 'Request number'), _f('blood_group', 'Group needed', 'select', BLOOD_GROUPS), _f('county', 'County'), _f('urgency', 'How urgent?', 'select', ['routine', 'urgent', 'critical'])]),
		_a('donation_centres', 'Where can I give blood?', 'Records', 'GET', '/blood/donation-centres', [_f('lat', 'Latitude', 'decimal'), _f('lon', 'Longitude', 'decimal'), _f('kind', 'What kind of place?', 'select', ['blood_donation', 'blood_bank']), _f('limit', 'How many', 'int')]),
		# Wellbeing
		# Five answers, not five fields. The model holds `scores` as a list of exactly five, and the
		# form offered s1..s5 — a shape neither client could turn into the list, so the action was
		# refused however it was filled. A `list` field is what the catalogue already uses for a
		# multi-value answer (`mood_screen`'s `answers` is the same shape).
		_a('wellbeing_check', 'How have I been feeling?', 'Wellbeing', 'POST', '/mental/who5', [_s(), _f('scores', 'Your five answers, 0 to 5 each', 'list', ph='4,3,5,4,2'), _f('county', 'County', ph='optional; only used as a count, never with your name')]),
		_a('counselling_lines', 'Talk to someone', 'Wellbeing', 'GET', '/mental/lines', []),
		# The nine and seven items are served by `GET /mental/instruments` and drawn by the client;
		# the action carries the answers, not the item text, so the wording lives in one place. The
		# `lang` options are the two language codes, like `under_5` and `boy` elsewhere in this file —
		# values the caller sends, not labels a person reads.
		_a('mood_screen', 'How am I really doing?', 'Wellbeing', 'POST', '/mental/screen', [_s(), _f('instrument', 'Which check?', 'select', ['phq9', 'gad7']), _f('answers', 'Your answers', 'list', ph='0,1,2,3'), _f('lang', 'Language', 'select', ['en', 'sw']), _f('administered_at_iso', 'When')]),
		_a('mood_log', 'How is my mood today?', 'Wellbeing', 'POST', '/mental/mood', [_s(), _f('score', 'Out of 10', 'int'), _f('logged_at_iso', 'When'), _f('note', 'Anything you want to remember', 'textarea')]),
		# `subject_ref` is a query parameter here, not a path segment — it was typed 'path', so both
		# shipped clients put it in neither the URL nor the query and the route was unreachable. The
		# field stays `client_supplied`: the route binds it to the token, so a form must not draw it.
		_a('mood_trend', 'How has my mood been?', 'Wellbeing', 'GET', '/mental/mood/trend', [_f('subject_ref', 'Me', 'text', client_supplied=True), _f('window_days', 'Days to look back over', 'int')]),
		_a('coping_tips', 'What can I do to cope?', 'Wellbeing', 'GET', '/mental/coping', [_f('lang', 'Language', 'select', ['en', 'sw'])]),
		# `condition` fills a path segment, so it must be `path` — as a `select` neither client
		# substituted it and both sent the literal `{condition}` to the server. The options are the
		# section's three; a client that draws them as a picker still writes the slug into the URL.
		_a('outbreak_support', 'Support during the outbreak', 'Wellbeing', 'GET', '/mental/outbreak-support/{condition}', [_f('condition', 'What is happening?', 'path', ph='isolation_distress, grief, worker_burnout'), _f('lang', 'Language', 'select', ['en', 'sw'])]),
		_a('ask_referral', 'Ask to be referred', 'Wellbeing', 'POST', '/mental/referral', [_s(), _f('reason', 'What is this about?', 'textarea'), _f('urgency', 'How soon?', 'select', ['routine', 'soon', 'urgent'])]),
		# Chronic & daily
		_a('log_bp', 'Log my blood pressure', 'Daily care', 'POST', '/chronic/bp', [_s(), _f('systolic', 'Systolic', 'int'), _f('diastolic', 'Diastolic', 'int'), _f('pulse', 'Pulse', 'int')]),
		_a('log_glucose', 'Log my blood sugar', 'Daily care', 'POST', '/chronic/glucose', [_s(), _f('mmol_l', 'mmol/L', 'decimal'), _f('fasting', 'Before eating?', 'bool')]),
		_a('bp_trend', 'Is my blood pressure improving?', 'Daily care', 'GET', '/chronic/{ref}/bp-trend', [_f('ref', 'Who is this for?', 'path')]),
		_a('track_refill', 'When do I need a refill?', 'Daily care', 'POST', '/chronic/refill', [_s(), _f('drug', 'Medicine'), _f('days_remaining', 'Days of medicine left', 'int')]),
		_a('peak_flow', 'Log my peak flow', 'Daily care', 'POST', '/monitoring/chronic/peak-flow', [_s(), _f('litres_per_min', 'Litres per minute', 'int'), _f('personal_best', 'My best ever', 'int')]),
		_a('log_weight', 'Log my weight', 'Daily care', 'POST', '/monitoring/chronic/weight', [_s(), _f('kg', 'Weight in kg', 'decimal')]),
		_a('condition_profile', 'My ongoing conditions', 'Daily care', 'POST', '/monitoring/chronic/conditions', [_s(), _f('conditions', 'Conditions', 'list', ph='hypertension, diabetes'), _f('hiv_pin_set', 'Extra PIN set for private conditions?', 'bool')]),
		_a('clinical_report', 'Report to show my clinician', 'Daily care', 'GET', '/monitoring/chronic/{subject_ref}/report', [_s('path')]),
		_a('kidney_result', 'My kidney results', 'Daily care', 'POST', '/chronic/kidney', [_s(), _f('creatinine_mg_dl', 'Creatinine (mg/dL)', 'decimal'), _f('age_years', 'Age in years', 'int'), _f('sex', 'Sex', 'select', ['male', 'female']), _f('acr_mg_g', 'Urine albumin ratio, if known', 'decimal')]),
		_a('seizure_log', 'I had a seizure', 'Daily care', 'POST', '/chronic/seizure', [_s(), _f('duration_seconds', 'How many seconds did it last?', 'int'), _f('cluster', 'Another one before recovering?', 'bool'), _f('pregnant', 'Pregnant?', 'bool'), _f('at_iso', 'When was it?')]),
		_a('sickle_crisis', 'I am in a sickle cell crisis', 'Daily care', 'POST', '/chronic/sickle-crisis', [_s(), _f('pain_score', 'Pain, 0 to 10', 'int'), _f('temperature_c', 'Temperature °C', 'decimal'), _f('signs', 'Any of these?', 'list', ph='chest_pain, spleen_pain'), _f('at_iso', 'When did it start?')]),
		_a('trend_chart', 'Show me my readings over time', 'Daily care', 'GET', '/chronic/{ref}/chart', [_f('ref', 'Who is this for?', 'path'), _f('metric', 'Which reading?', 'select', ['bp_systolic', 'bp_diastolic', 'glucose', 'peak_flow', 'weight'])]),
		_a('appointments', 'My upcoming reviews', 'Daily care', 'GET', '/chronic/{ref}/appointments', [_f('ref', 'Who is this for?', 'path'), _f('today_iso', 'Today')]),
		# The list above had no way to put anything in it: §MON-003's "Appointment tracking" was
		# read-only from every client, so the reviews a person could see were the ones a clinician
		# had already recorded and never the ones they scheduled for themselves.
		_a('schedule_review', 'Book a review', 'Daily care', 'POST', '/chronic/appointments', [_auto('appointment_id', 'Reference'), _f('condition', 'Which condition?', 'select', list(REVIEW_INTERVAL_DAYS)), _f('due_iso', 'When is it due?'), _f('interval_days', 'Repeat every how many days?', 'int'), _f('kind', 'What kind of review?', 'select', [k.value for k in AppointmentKind]), _f('facility_id', 'Where?', ph='optional'), _s()]),
		_a('lifestyle_guidance', 'What should I eat and avoid?', 'Daily care', 'GET', '/chronic/lifestyle', [_s(), _f('condition', 'Which condition?', 'select', list(REVIEW_INTERVAL_DAYS))]),
		# Women & maternal
		_a('log_cycle', 'Log my period', 'Women', 'POST', '/women/cycle', [_s(), _f('start_iso', 'First day of period'), _f('cycle_days', 'Cycle length in days', 'int'), _f('pain_level', 'Pain level (0-10)', 'int')]),
		_a('cycle_prediction', 'When is my next period?', 'Women', 'GET', '/women/cycle/{ref}/predict', [_f('ref', 'Who is this for?', 'path'), _f('ref_date', 'As at', ph='YYYY-MM-DD')]),
		_a('contraception_methods', 'What methods are there?', 'Women', 'GET', '/women/contraception/methods', []),
		_a('set_contraception', 'Record my method', 'Women', 'POST', '/women/contraception', [_s(), _f('method', 'Which method?', 'text', ph='pill, implant, condom…'), _f('started_iso', 'Since when', ph='YYYY-MM-DD'), _f('repeat_days', 'Days between repeats', 'int', ph='leave blank for a long-acting method')]),
		_a('contraception_due', 'What is due?', 'Women', 'GET', '/women/contraception/{ref}/due', [_f('ref', 'Who is this for?', 'path'), _f('on_iso', 'As at', ph='YYYY-MM-DD')]),
		_a('menopause_state', 'Where am I in the change?', 'Women', 'GET', '/women/menopause/{ref}', [_f('ref', 'Who is this for?', 'path'), _f('today_iso', 'As at', ph='YYYY-MM-DD')]),
		_a('reproductive_referral', 'Where can I get help?', 'Women', 'POST', '/women/referral', [_f('reason', 'What do you need help with?')]),
		_a('register_pregnancy', 'Register my pregnancy', 'Maternity', 'POST', '/maternal/pregnancy', [_s(), _f('edd_iso', 'Expected delivery date'), _f('lmp_week', 'Weeks pregnant now', 'int'), _f('delivery_plan_facility_id', 'Where I plan to deliver', ph='optional')]),
		_a('anc_due', 'Which clinic visits are due?', 'Maternity', 'GET', '/maternal/{ref}/anc-due', [_f('ref', 'Who is this for?', 'path'), _f('gest_week', 'Weeks pregnant', 'int')]),
		_a('record_anc', 'Record a clinic visit', 'Maternity', 'POST', '/maternal/anc', [_s(), _f('contact_no', 'Visit number (1-8)', 'int'), _f('done_iso', 'Date of visit')]),
		_a('danger_signs', 'Check for danger signs', 'Maternity', 'POST', '/maternal/danger', [_f('signs', 'Danger signs', 'list', ph='bleeding, severe_headache')]),
		_a('due_date', 'When is my baby due?', 'Maternity', 'GET', '/maternal/due-date', [_f('lmp_iso', 'First day of my last period')]),
		_a('anc_visits', 'My clinic visit dates', 'Maternity', 'GET', '/maternal/{ref}/visits', [_f('ref', 'Who is this for?', 'path'), _f('today_iso', "Today's date", ph='2026-10-08')]),
		_a('postnatal_visits', 'My baby clinic visits', 'Maternity', 'GET', '/maternal/{ref}/postnatal', [_f('ref', 'Who is this for?', 'path')]),
		_a('record_birth', 'My baby was born', 'Maternity', 'POST', '/maternal/birth', [_s(), _f('birth_iso', 'Date of birth')]),
		_a('trimester_guidance', 'What to expect this month', 'Maternity', 'GET', '/maternal/guidance', [_f('gest_week', 'Weeks pregnant', 'int')]),
		_a('newborn_signs', 'Warning signs in a newborn', 'Maternity', 'GET', '/maternal/newborn-signs', []),
		_a('birth_plan', 'My birth plan', 'Maternity', 'GET', '/maternal/{ref}/birth-plan', [_f('ref', 'Who is this for?', 'path')]),
		_a('save_birth_plan', 'Plan where I will deliver', 'Maternity', 'POST', '/maternal/birth-plan', [_s(), _f('facility_id', 'Which facility', ph='optional'), _f('transport', 'How I will get there', ph='optional'), _f('birth_companion', 'Who comes with me', ph='optional'), _f('blood_donor', 'Who can donate blood', ph='optional'), _f('funds_kes', 'Money set aside (KES)', 'int', ph='optional')]),
		_a('pmtct_referral', 'Do I need a PMTCT referral?', 'Maternity', 'POST', '/maternal/pmtct-referral', [_s(), _f('hiv_positive', 'Did the HIV test come back positive?', 'bool')]),
		_a('maternity_facilities', 'Where can I deliver?', 'Maternity', 'GET', '/maternal/facilities', [_f('lat', 'My latitude', 'decimal'), _f('lon', 'My longitude', 'decimal'), _f('limit', 'How many to show', 'int'), _f('accepts_sha', 'Only places that take SHA', 'bool')]),
		# Child immunisation
		_a('register_child', "Add my child's date of birth", 'Children', 'POST', '/monitoring/child', [_f('member_ref', 'Child'), _f('dob_iso', 'Date of birth')]),
		_a('child_schedule', 'My child vaccine schedule', 'Children', 'GET', '/monitoring/child/{member_ref}/schedule', [_f('member_ref', 'Child', 'path')]),
		_a('catch_up_doses', 'Which doses were missed?', 'Children', 'GET', '/monitoring/child/{member_ref}/catch-up', [_f('member_ref', 'Child', 'path')]),
		_a('record_dose', 'Record a vaccine given', 'Children', 'POST', '/monitoring/child/dose', [_f('member_ref', 'Child'), _f('vaccine', 'Vaccine'), _f('dose_no', 'Dose number', 'int'), _f('given_iso', 'Date given'), _f('card_photo_sha256', 'Photo of the card', ph='optional')]),
		_a('missed_doses', 'Which doses is my child behind on?', 'Children', 'GET', '/monitoring/child/{member_ref}/alerts', [_f('member_ref', 'Child', 'path')]),
		_a('add_medication', 'Remind me to take my medicine', 'Children', 'POST', '/monitoring/medication', [_auto('schedule_id', 'Reminder number'), _f('member_ref', 'Who is this for?'), _f('drug', 'Medicine'), _f('dose', 'How much'), _f('times_per_day', 'Times a day', 'int'), _f('start_iso', 'Starting on'), _f('duration_days', 'For how many days', 'int')]),
		_a('log_adherence', 'I took my medicine', 'Children', 'POST', '/monitoring/medication/adherence', [_f('schedule_id', 'Reminder number'), _f('at_iso', 'When'), _f('action', 'What happened?', 'select', ADHERENCE_ACTIONS)]),
		# Environment & nutrition
		_a('vector_risk', 'Is there a mosquito risk here?', 'Environment', 'POST', '/monitoring/vector-risk', [_f('county', 'County'), _f('rainfall_mm_72h', 'Rainfall in the last 3 days (mm)', 'decimal'), _f('livestock_adjacent', 'Do you keep livestock?', 'bool')]),
		_a('breeding_site', 'Report a mosquito breeding site', 'Environment', 'POST', '/monitoring/breeding-site', [_f('county', 'County'), _f('lat', 'Latitude', 'decimal'), _f('lon', 'Longitude', 'decimal'), _f('description', 'What did you see?', 'textarea')]),
		_a('larviciding', 'Is my area being sprayed for mosquitoes?', 'Environment', 'GET', '/monitoring/larviciding/{county}', [_f('county', 'County', 'path'), _f('on_iso', 'Which day', ph='optional')]),
		_a('issue_larviciding', 'Announce a mosquito control round', 'Environment', 'POST', '/monitoring/larviciding', [_auto('campaign_id', 'Round number'), _f('counties', 'Counties', 'list'), _f('larvicide', 'What is being used', 'select', LARVICIDE_OPTIONS), _f('habitats', 'Water bodies being treated', 'list'), _f('first_round_iso', 'First day'), _f('issued_by', 'Issued by', 'select', ['MoH', 'PHEOC', 'County']), _f('headline', 'Headline'), _f('body', 'Message', 'textarea')]),
		_a('protection_reminder', 'Remind me about mosquitoes', 'Environment', 'GET', '/monitoring/protection-reminder', [_f('county', 'County'), _f('rainfall_mm_72h', 'Rainfall in the last 3 days (mm)', 'decimal'), _f('at_iso', 'What time is it now?', ph='YYYY-MM-DDTHH:MM+03:00')]),
		_a('food_alert', 'Issue a food safety alert', 'Environment', 'POST', '/monitoring/food-alert', [_f('county', 'County'), _f('kind', 'Kind', 'select', ['aflatoxin', 'recall', 'cholera_food', 'other']), _f('detail', 'Details', 'textarea'), _f('source', 'Source')]),
		_a('food_alerts', 'Food safety alerts', 'Environment', 'GET', '/monitoring/food-alerts/{county}', [_f('county', 'County', 'path')]),
		_a('nutrition', 'What should my child eat?', 'Environment', 'GET', '/monitoring/nutrition/{age_months}', [_f('age_months', 'Age in months', 'path'), _f('month', 'Which month is it?', 'int', ph='optional')]),
		_a('therapeutic_feeding', 'Where can a malnourished child get help?', 'Environment', 'GET', '/monitoring/therapeutic-feeding', [_f('county', 'County'), _f('lat', 'Latitude', 'decimal'), _f('lon', 'Longitude', 'decimal')]),
		_a('vaccination_campaigns', 'Any vaccination campaign near me?', 'Children', 'GET', '/monitoring/campaigns', [_f('county', 'County'), _f('on_iso', 'Which day', ph='optional')]),
		# §MON-001's campaign notification, from the side that issues it. The read above is the
		# parent's question; this is the county health team's, and the route is guarded on
		# `county_aggregate` — so it is marked operator-only or a citizen's catalogue would offer a
		# form that 403s. It was *not* marked before, because the route carried `require_self` and a
		# citizen could post it: a notice attributed to MoH, published into the immunisation feed
		# every parent in the county receives. The marking and the guard moved together.
		_a('issue_campaign', 'Announce a vaccination campaign', 'Children', 'POST', '/monitoring/campaign', [_auto('campaign_id', 'Reference'), _f('disease', 'Which disease?', ph='a registry disease slug'), _f('counties', 'Which counties?', 'list'), _f('target_age_months', 'Age band in months', 'list', ph='9, 59'), _f('starts_iso', 'Starts'), _f('ends_iso', 'Ends'), _f('headline', 'Headline'), _f('body', 'What should parents know?', 'textarea'), _f('issued_by', 'Issued by', 'select', ['MoH', 'PHEOC', 'County'])]),
		_a('water_advisory', 'Is the water safe?', 'Environment', 'POST', '/environment/water', [_f('county', 'County'), _f('ecoli_detected', 'E. coli detected?', 'bool'), _f('turbidity_ntu', 'Turbidity NTU', 'decimal'), _f('treated_at_iso', 'When you last treated water', ph='YYYY-MM-DDTHH:MM+03:00')]),
		_a('air_advisory', 'How is the air?', 'Environment', 'POST', '/environment/air', [_f('county', 'County'), _f('location', 'Where you are'), _f('pm25', 'PM2.5 µg/m³', 'decimal'), _f('hourly', 'Today\'s hourly readings', 'list', ph='6=18, 12=34, 18=52')]),
		_a('flood_risk', 'Flood and cholera risk', 'Environment', 'POST', '/environment/flood', [_f('county', 'County'), _f('rainfall_mm_72h', 'Rainfall mm in 3 days', 'decimal'), _f('population_at_risk', 'People at risk', 'int')]),
		# Alerts
		_a('issue_alert', 'Send a public alert', 'Alerts', 'POST', '/alerts', [_auto('alert_id', 'Alert number'), _f('kind', 'Kind', 'select', ALERT_KINDS), _f('county', 'County'), _f('headline', 'Headline'), _f('body', 'Message', 'textarea'), _f('issued_by', 'Issued by', 'select', list(ALERT_ISSUERS))]),
		_a('alerts_by_county', 'Alerts for my county', 'Alerts', 'GET', '/alerts/{county}', [_f('county', 'County', 'path')]),
		_a('publish_feed_item', 'Publish a verified alert', 'Alerts', 'POST', '/alerting/feed', [_f('item_id', 'Item number'), _f('category', 'Category', 'select', list(FEED_CATEGORIES)), _f('headline', 'Headline'), _f('body', 'Message', 'textarea'), _f('source', 'Source'), _f('verified', 'Verified?', 'bool'), _f('published_iso', 'Published on'), _f('county', 'County', ph='optional')]),
		_a('alert_feed', 'Alerts near me', 'Alerts', 'GET', '/alerting/feed', [_f('county', 'County', ph='optional')]),
		_a('set_alert_preference', 'Choose which alerts I get', 'Alerts', 'POST', '/alerting/preferences', [_s(), _f('category', 'Alert type'), _f('enabled', 'Turn on?', 'bool')]),
		_a('alert_preferences', 'My alert settings', 'Alerts', 'GET', '/alerting/preferences/{subject_ref}', [_s('path')]),
		_a('link_family', 'Link my family', 'Alerts', 'POST', '/alerting/family/link', [_f('family_ref', 'Family group'), _f('members', 'Family members', 'list')]),
		_a('family_check_in', "I'm safe", 'Alerts', 'POST', '/alerting/family/check-in', [_s(), _f('family_ref', 'Family group'), _f('at_iso', 'When', ph='optional'), _f('channel', 'How did you check in?', 'select', ['native', 'sms']), _f('note', 'Anything to add?', ph='optional')]),
		_a('my_checkins', 'My safety check-ins', 'Alerts', 'GET', '/alerting/family/check-ins/{subject_ref}', [_s('path')]),
		_a('family_board', 'Is my family safe?', 'Alerts', 'GET', '/alerting/family/{family_ref}', [_f('family_ref', 'Family group', 'path')]),
		# Community
		_a('report_issue', 'Report a problem in my area', 'Community', 'POST', '/community/issues', [_auto('issue_id', 'Report number'), _f('kind', 'What is the problem?', 'select', ISSUE_KINDS), _f('county', 'County'), _f('description', 'Describe it', 'textarea'), _f('lat', 'Latitude', 'decimal'), _f('lon', 'Longitude', 'decimal')]),
		_a('issues_by_county', 'Problems reported near me', 'Community', 'GET', '/community/issues/{county}', [_f('county', 'County', 'path')]),
		_a('resolve_issue', 'Mark a problem as fixed', 'Community', 'POST', '/community/issues/{issue_id}/resolve', [_f('issue_id', 'Report number', 'path')]),
		_a('submit_case', 'Report a suspected case', 'Community', 'POST', '/community/cases', [_auto('report_id', 'Report number'), _f('chw_ref', 'Health worker'), _f('county', 'County'), _f('community', 'Village or estate'), _f('symptoms', 'Symptoms', 'list'), _f('age_years', 'Age in years', 'int'), _f('sex', 'Sex', 'select', ['male', 'female', 'other']), _f('temperature_c', 'Temperature °C', 'decimal'), _f('exposure_history', 'Who has the patient been near?', 'textarea'), _f('geotagged', 'Attach location?', 'bool'), _f('suspected_disease', 'What do you suspect?', 'select', VECTOR_DISEASES), _f('reported_offline', 'Reported without network?', 'bool'),
			# `CaseReport._a_note_is_kept_in_the_language_it_was_said_in`: a transcript with no
			# language, or a language with no transcript, is half a record. §COM-101's "voice-to-text
			# notes in local languages" was implemented in the model and drawn nowhere — a CHW who
			# dictated an observation still had to type it afterwards or lose it, which is the defect
			# the model's own comment says the two fields exist to fix. `voice_note_lang` is required
			# exactly when a transcript is present, and the route refuses the reverse too, so the
			# client's pre-request check enforces the biconditional from both sides.
			_f('voice_note', 'Dictated note, as text', 'textarea', ph='the recogniser’s transcript', when='voice_note_lang'),
			_f('voice_note_lang', 'Which language was it spoken in?', 'select', VOICE_LANGS, when='voice_note')]),
		_a('advance_case', 'Update a case', 'Community', 'POST', '/community/cases/{report_id}/advance', [_f('report_id', 'Report number', 'path'), _f('status', 'New status', 'select', CASE_STATUSES)]),
		_a('ppe_reminder', 'Protective equipment reminder', 'Community', 'GET', '/community/ppe-reminder', []),
		_a('peer_alert', 'Warn people nearby', 'Community', 'POST', '/community/peer-alert', [_f('alert_id', 'Alert number'), _f('county', 'County'), _f('lat', 'Latitude', 'decimal'), _f('lon', 'Longitude', 'decimal'), _f('radius_m', 'How far? (metres)', 'select', [str(r) for r in ALERT_ZONE_RADII_M]), _f('headline', 'Headline'), _f('location', 'Which place should people avoid?'), _f('issued_iso', 'Issued on', ph='YYYY-MM-DD'), _f('verified_by', 'Verified by', 'select', list(PEER_VERIFIERS))]),
		_a('peer_alert_followup', 'Follow-up prompt for one day', 'Community', 'GET', '/community/peer-alert/{alert_id}/followup/{day}', [_f('alert_id', 'Alert number', 'path'), _f('day', 'Day of the window (' + ', '.join(str(d) for d in FOLLOWUP_DAYS) + ')', 'path')]),
		_a('tracing_prompts', 'Help me remember who I met', 'Community', 'GET', '/community/tracing-prompts', []),
		_a('save_contacts', 'Save my contact list', 'Community', 'POST', '/community/contacts', [_s(), _f('entries', 'People, and where you know them from', 'list', ph='Jane:market, the tailor:work (home, work, transport, worship, market, social, other)'), _f('share_consent', 'Share with the health team?', 'bool')]),
		_a('add_contact', 'Add one person I met', 'Community', 'POST', '/community/contacts/{subject_ref}/entry', [_s('path'), _f('description', 'Who was it?'), _f('setting', 'Where?', 'select', CONTACT_SETTINGS), _f('approx_location', 'Roughly where?'), _f('name_unknown', "I don't know their name", 'bool')]),
		_a('share_contacts', 'Share my contact list with the health team', 'Community', 'POST', '/community/contacts/{subject_ref}/share', [_s('path'), _f('with_who', 'Who should get it?', ph='optional')]),
		_a('contact_shares', 'What I have shared', 'Community', 'GET', '/community/contacts/{subject_ref}/shares', [_s('path')]),
		_a('withdraw_contact_shares', 'Take my contact list back', 'Community', 'DELETE', '/community/contacts/{subject_ref}/shares', [_s('path')]),
		_a('flag_misinformation', 'Report something I heard', 'Community', 'POST', '/community/misinformation', [_auto('submission_id', 'Report number'), _f('claim', 'What did you hear?', 'textarea'), _f('county', 'County'), _f('medium', 'How did you get it?', 'select', MISINFO_MEDIA), _f('topic', 'Topic', ph='optional'),
			# `MisinfoSubmission._payload_matches_medium`: a voice note, a picture or a forward must
			# carry the recording *or* its transcript, "otherwise it is a text report with a different
			# label". Neither is required alone and the group is required only for a payload medium —
			# which is what the label said in prose ("type it if you have no recording") and what no
			# form could act on.
			_f('evidence_ref', 'The recording or picture', ph='from the camera or recorder upload'), _f('transcript', 'What the voice note said', 'textarea', ph='type it if you have no recording'),
			# "the recording or image is shared only with explicit per-item consent, and none was
			# given for this report" — required exactly when there is something to share.
			_f('evidence_consent', 'Share the recording or picture with the health team', 'bool', when='evidence_ref'), _f('flagger_ref', 'Tell me when this is answered', ph='your number or reference')],
			any_of=[FieldGroup(fields=['evidence_ref', 'transcript'], when='medium', equals_any=list(MISINFO_PAYLOAD_MEDIA))]),
		_a('misinformation_clusters', 'Rumours going around', 'Community', 'GET', '/community/misinformation/clusters', []),
		_a('misinformation_notices', 'Answers to what I reported', 'Community', 'GET', '/community/misinformation/notices/{subject_ref}', [_s('path')]),
		# Outbreak mode
		_a('enrol_monitoring', 'Start my 21-day check-in', 'Outbreak', 'POST', '/monitoring/contact/enrol', [_s(), _f('officer', 'Monitoring officer', ph='optional'), _f('officer_number', 'Their phone number', ph='optional')]),
		_a('monitoring_day', 'Log today (21-day check-in)', 'Outbreak', 'POST', '/monitoring/contact/day', [_auto('entry_id', 'Entry number'), _s(), _f('day', 'Day (1-21)', 'int'), _f('temperature_c', 'Temperature °C', 'decimal'), _f('symptoms', 'Symptoms', 'list'), _f('household_member', 'Family member', ph='optional'), _f('slot', 'Morning or evening', 'select', [k.value for k in ReminderSlot]), _f('location_logged', 'Share where I am today', 'bool')]),
		_a('monitoring_diary', 'My 21-day diary', 'Outbreak', 'GET', '/monitoring/contact/{subject_ref}/diary', [_s('path')]),
		_a('monitoring_reminders', 'What is still to log today', 'Outbreak', 'GET', '/monitoring/contact/{subject_ref}/reminders/{day}', [_s('path'), _f('day', 'Day (1-21)', 'path')]),
		_a('monitoring_consent', 'Share my location while I am monitored', 'Outbreak', 'POST', '/monitoring/contact/{subject_ref}/location-consent', [_s('path'), _f('granted', 'Yes, share it', 'bool'), _f('at_iso', 'When')]),
		_a('monitoring_members', 'Add someone I live with', 'Outbreak', 'POST', '/monitoring/contact/{subject_ref}/members', [_s('path'), _f('member_ref', 'Who they are to you', ph='e.g. my son')]),
		_a('monitoring_member_diary', 'Their readings', 'Outbreak', 'GET', '/monitoring/contact/{subject_ref}/members/{member_ref}/diary', [_s('path'), _f('member_ref', 'Family member', 'path')]),
		# The counterpart to the add above: a household member enrolled during monitoring could not
		# be taken back off it, so a person who added someone by mistake kept them on the list for
		# the whole 21 days. §MON-009's household list is the person's own, hence `require_self`.
		_a('remove_household_member', 'Take someone off my list', 'Outbreak', 'DELETE', '/monitoring/contact/{subject_ref}/members/{member_ref}', [_s('path'), _f('member_ref', 'Family member', 'path')]),
		_a('monitoring_officer', 'Call my monitoring officer', 'Outbreak', 'GET', '/monitoring/contact/{subject_ref}/officer', [_s('path')]),
		_a('send_exposure_notice', 'Send an exposure notice', 'Outbreak', 'POST', '/alerting/exposure', [_f('subject_ref', 'Person to notify'), _f('case_ref', 'Case reference', ph='optional')]),
		_a('ack_exposure', 'I have read the notice', 'Outbreak', 'POST', '/alerting/exposure/ack', [_f('notification_id', 'Notice number'), _s(), _f('acknowledged_iso', 'When'), _f('request_callback', 'Ask a health worker to call me', 'bool')]),
		_a('ack_peer_alert', 'I have read the warning', 'Community', 'POST', '/community/peer-alert/ack', [_f('alert_id', 'Alert number'), _s(), _f('acknowledged_iso', 'When'), _f('concerned', 'I am worried about this', 'bool')]),
		_a('check_exposure', 'Was I near a case?', 'Outbreak', 'POST', '/location/proximity/check', [_f('own_pets', 'My encounter codes', 'list'), _f('window_days', 'Days to look back', 'int')]),
		_a('declare_exposure', 'Declare that I tested positive', 'Outbreak', 'POST', '/location/proximity/declare', [_f('declaration_id', 'Declaration number'), _f('pet', 'Encounter code'), _f('declared_at_ms', 'When', 'int'), _f('proxied', 'Send anonymously?', 'bool')]),
		_a('log_encounter', 'Log someone I passed nearby', 'Outbreak', 'POST', '/location/proximity/encounter', [_f('pet', 'Encounter code'), _f('seen_at_ms', 'When', 'int'), _f('rssi_dbm', 'Signal strength', 'int'), _f('county', 'County')]),
		_a('rotate_ebid', 'Get a fresh nearby-code', 'Outbreak', 'POST', '/location/proximity/ebid', [_f('seed', 'Private seed'), _f('now_ms', 'Current time', 'int')]),
		_a('enable_location_history', 'Keep a private location diary', 'Outbreak', 'POST', '/location/history/enable', [_s(), _f('window_days', 'Days to keep', 'int')]),
		# The model wants the cell and the instant; the form offered one free-text "place", so a
		# client could say neither where nor when. §LOC-003 keeps raw coordinates off this boundary,
		# which is why the client sends the geohash it already computed rather than a lat/lon pair.
		_a('log_location', 'Save where I am', 'Outbreak', 'POST', '/location/history/point', [_s(), _f('geohash', 'Where you are', ph='the location code your phone shows'), _f('at_iso', 'When', ph='2026-10-12T08:30'), _f('place_label', 'What to call this place', ph='optional; e.g. Kisumu CBD')]),
		# `share` used to be a field on this action, and the report route composed its sharing sentence
		# from it — so the form offered a switch that sent nothing and the screen said it had. Sharing
		# is a separate act with a receipt, so it is a separate action.
		_a('location_report', 'Where I have been', 'Outbreak', 'GET', '/location/history/{subject_ref}/report', [_s('path')]),
		_a('share_location_report', 'Send my location history to the health team', 'Outbreak', 'POST', '/location/history/{subject_ref}/share', [_s('path'), _f('with_who', 'Who should get it?', ph='optional; the county health team by default')]),
		_a('location_report_shares', 'Location reports I have sent', 'Outbreak', 'GET', '/location/history/{subject_ref}/shares', [_s('path')]),
		_a('purge_location', 'Delete my location diary', 'Outbreak', 'DELETE', '/location/history/{subject_ref}', [_s('path')]),
		_a('checkin_points', 'Check-in points near me', 'Outbreak', 'GET', '/location/checkin/points', [_f('county', 'County', ph='optional')]),
		_a('checkin_list', 'Where I checked in', 'Outbreak', 'GET', '/location/checkin/{subject_ref}', [_s('path')]),
		# §LOC-004's fourth Behaviour bullet, on the same route family as the two above it: what the
		# check-ins on file are *for*. `lang` is offered because the follow-up question is a sentence
		# a person reads, and the two above carry no prose at all.
		_a('checkin_followup', 'What happens after I check in?', 'Outbreak', 'GET', '/location/checkin/{subject_ref}/follow-up', [_s('path'), _f('lang', 'Which language?', 'select', TRAVELLER_LANGS)]),
		_a('register_checkin_point', 'Set up a check-in point', 'Outbreak', 'POST', '/location/checkin/point', [_f('point_id', 'Point number'), _f('kind', 'What kind of place?', 'select', CHECKIN_KINDS), _f('label', 'Name'), _f('county', 'County'), _f('token', 'Check-in code')]),
		# `share_with_authority` is labelled as the *request* it is. Whether anything was sent is the
		# receipt's `synced`, which the person reads back off this same call — so the field asks the
		# question rather than asserting the answer, which is what it did when the two were one field.
		_a('check_in', 'Check in here', 'Outbreak', 'POST', '/location/checkin', [_f('checkin_id', 'Check-in number'), _f('point_token', 'Check-in code'), _s(), _f('method', 'How?', 'select', CHECKIN_METHODS), _f('at_iso', 'When'), _f('lang', 'Which language?', 'select', TRAVELLER_LANGS), _f('share_with_authority', 'Ask to send this to the health team?', 'bool')]),
		_a('register_border', 'Set up a border post', 'Outbreak', 'POST', '/location/border', [_f('post_id', 'Post number'), _f('name', 'Name'), _f('county', 'County'), _f('country_pair', 'Between which countries?'), _f('queue_minutes', 'Queue in minutes', 'int'), _f('screening_required', 'Screening required?', 'bool'), _f('mobile_lab', 'Is there a mobile lab here?', 'bool'),
			# `BorderPost._a_lab_is_described_or_absent`: "The three fields move together or none of
			# them is set." So both are required exactly when the post reports a lab — and the client
			# sends a `bool` as the string "true", which is why the trigger's value is that string and
			# not `True`. A condition written in the other spelling is one no client would ever match.
			_f('lab_turnaround_hours', 'Results in how many hours?', 'int', when='mobile_lab', equals_any=['true']), _f('lab_tests', 'Which tests can it run?', 'list', ph='e.g. mRDT, Ebola PCR', when='mobile_lab', equals_any=['true'])]),
		_a('border_status', 'Border queue', 'Outbreak', 'GET', '/location/border/{post_id}', [_f('post_id', 'Post number', 'path')]),
		_a('travel_advisory', 'Should I travel?', 'Outbreak', 'GET', '/location/travel-advisory', [_f('destination', 'Where to?'), _f('origin_country', 'Coming from'), _f('lang', 'Which language?', 'select', TRAVELLER_LANGS)]),
		_a('traveller_declare', 'Declare my arrival', 'Outbreak', 'POST', '/location/traveller/declare', [_f('declaration_id', 'Declaration number'), _s(), _f('destination', 'Where are you going?'), _f('arrival_iso', 'Arrival date'), _f('origin_country', 'Coming from'), _f('symptoms', 'Any symptoms?', 'list'), _f('lang', 'Which language?', 'select', TRAVELLER_LANGS)]),
		_a('traveller_prompt', 'What am I asked today?', 'Outbreak', 'GET', '/location/traveller/{subject_ref}/prompt', [_s('path'), _f('day', 'Which day of the 21?', 'int')]),
		_a('traveller_report', 'Report how I feel today', 'Outbreak', 'POST', '/location/traveller/report', [_s(), _f('day', 'Which day of the 21?', 'int'), _f('symptoms', 'Any symptoms?', 'list'), _f('temperature_c', 'Temperature °C', 'decimal')]),
		# `hotspots` has no catalogue action. Both its routes take `list[AggregateCell]` and neither
		# client can build an object list, so the only control a generic form could draw is one whose
		# value the server refuses. The county health team's surface is `signal_scan`, which runs the
		# same pipeline for a week from the county's own ledger and needs no cells from the caller.
		_a('risk_score', 'What is my personal risk?', 'Outbreak', 'POST', '/ai/risk-score', [_f('symptoms', 'Symptoms', 'list'), _f('exposure_contact', 'Contact with a case?', 'bool'), _f('travel_affected_area', 'Travelled to an affected area?', 'bool'), _f('geofence_entry', 'Entered a risk area?', 'bool'), _f('proximity_encounters', 'Nearby encounters', 'int'), _f('vaccinated', 'Vaccinated?', 'bool')]),
		_a('early_warning', 'Is something unusual happening?', 'Outbreak', 'POST', '/ai/early-warning', [_f('county', 'County'), _f('disease', 'Disease'), _f('signals', 'Signals, as what was seen = this week = usual = week-to-week variation', 'list', ph='fever_triage=42=20=6, cough_events=18=11=3')]),
		_a('signal_scan', 'How is my county this week?', 'Outbreak', 'GET', '/ai/early-warning/{county}/scan', [_f('county', 'County', 'path'), _f('disease', 'Disease'), _f('week_isoyear', 'Year', 'int'), _f('week', 'Week number', 'int'), _f('baseline_weeks', 'Weeks to compare against', 'int')]),
		# The six option values are §11.7's own signal names — the strings the API accepts, like the
		# `under_5` age band and the `low` risk level elsewhere in this file. They are not spec feature
		# codes: `fever_triage` is a value the caller sends, and the label beside it is what a person
		# reads.
		_a('signal_report', 'Report a signal', 'Outbreak', 'POST', '/ai/signals', [_f('county', 'County'), _f('at_iso', 'When'), _f('signal', 'What happened', 'select', ['fever_triage', 'cough_events', 'facility_search', 'medicine_search', 'unwell_checkin', 'encounter_density']), _f('event_ref', 'Reference')]),
		# §17.3: the privacy-review key is not a field the caller sends any more — it is held by a
		# recorded review, so the form offers the processing to assess and nothing to assert.
		_a('activate_outbreak_mode', 'Activate outbreak mode', 'Outbreak', 'POST', '/tier4/activate', [_f('authorized_by_pheoc', 'PHEOC authorised?', 'bool'), _f('flag_enabled', 'Switch on?', 'bool'), _f('raw_sensor_data_retained', 'Keeping raw sensor data?', 'bool'), _f('location_tracking', 'Tracking location?', 'bool'), _f('proximity_logging', 'Proximity logging?', 'bool'), _f('contact_tracing', 'Contact tracing?', 'bool'), _f('automated_decisions', 'Automatic decisions?', 'bool'), _f('data_sharing_with_authorities', 'Sharing with health authorities?', 'bool'), _f('children_data', "Children's data?", 'bool'), _f('cross_border_transfer', 'Data leaving the country?', 'bool')]),
		# §11.1 row 5, "User requests activation" — the one trigger in the section's table a person
		# fires about themselves, and the only row with no operator behind it. It is a *request*, not
		# the switch: PHEOC still declares the event, and the route records the ask. Dormant like the
		# operator control above, because it belongs to the outbreak product, not the year-round one.
		_a('request_activation', 'Ask us to switch this on for me', 'Outbreak', 'POST', '/tier4/activation/request', [_f('county', 'Where you are', ph='optional')]),
		# Privacy & transparency
		# §SEC-001's eight categories, as the person reads them before deciding. The route served
		# this and no action reached it: `record_consent` writes a grant and `withdraw_consent` ends
		# one, and the screen that *explains what is being asked for* — the one §SEC-001's first
		# Feature bullet is about — was reachable by no client at all. `lang` because the explanation
		# is the entire content of the response, and a language with no table is served English with
		# the toggle saying so.
		_a('consent_choices', 'What am I agreeing to?', 'Privacy', 'GET', '/privacy/consent', [_f('lang', 'Which language?', 'select', TRAVELLER_LANGS)]),
		_a('record_consent', 'Record my consent', 'Privacy', 'POST', '/privacy/consent', [_s(), _f('purpose', 'What for?'), _f('data_types', 'Which data?', 'list'), _f('retention_days', 'Keep for how many days', 'int'), _f('legal_basis', 'Why are we allowed to?', 'select', [k.value for k in LegalBasis]), _f('lang', 'Which language?', 'select', TRAVELLER_LANGS)]),

		# §SEC-001's consent audit log, visible to the person it is about. No `subject_ref` field: the
		# route binds the subject to the token (`names_subject=False`), so a form drawing one would be
		# offering a control that names a stranger. `lang` because the note above the log is a sentence.
		_a('consent_history', 'What have I agreed to?', 'Privacy', 'GET', '/privacy/consent/history', [_f('lang', 'Which language?', 'select', TRAVELLER_LANGS)]),
		# §SEC-001's one-tap revocation. The id is the one `record_consent` returned, or the one the
		# log's own lines carry — a path field, so the client fills it from the screen the person is on.
		_a('withdraw_consent', 'Take my consent back', 'Privacy', 'POST', '/privacy/consent/{consent_id}/withdraw', [_f('consent_id', 'Consent reference', 'path')]),
		# §SEC-004's "optional pseudonymous profile". No `subject_ref` field: the route binds the
		# subject to the token, so a form drawing one would offer a control that names a stranger —
		# and this is the one screen where naming a stranger would hand over their handle.
		_a('my_pseudonym', 'What name do others see?', 'Privacy', 'GET', '/identity/pseudonym', [_f('lang', 'Which language?', 'select', TRAVELLER_LANGS)]),
		_a('choose_pseudonym', 'Choose the name others see', 'Privacy', 'POST', '/identity/pseudonym', [_f('handle', 'Your name on shared screens', ph='e.g. Tembo-a1b2')]),
		# §5.4's "optional linkage to an app profile" — the section's *act*, distinct from the handle
		# a person chooses above: this is joining a phone number's channel activity to the profile.
		# `subject_ref` is the caller's own and forced to the token, so the form draws no subject and
		# the two fields it does draw are the number and the consent that permits the join.
		_a('link_my_profile', 'Link my number to this profile', 'Privacy', 'POST', '/identity/link', [_auto('link_id', 'Reference'), _f('msisdn', 'Phone number', ph='07xx xxx xxx'), _f('consent_id', 'Consent reference'), _f('basis', 'Why may we link it?', 'select', [b.value for b in LinkBasis]), _s()]),
		_a('dpia_check', 'Check a new data use', 'Privacy', 'POST', '/privacy/dpia', [_f('raw_sensor_data_retained', 'Keeping raw sensor data?', 'bool'), _f('location_tracking', 'Tracking location?', 'bool'), _f('proximity_logging', 'Proximity logging?', 'bool'), _f('contact_tracing', 'Contact tracing?', 'bool'), _f('automated_decisions', 'Automatic decisions?', 'bool'), _f('data_sharing_with_authorities', 'Sharing with health authorities?', 'bool'), _f('children_data', "Children's data?", 'bool'), _f('cross_border_transfer', 'Data leaving the country?', 'bool')]),
		_a('retention_policy', 'How long is data kept?', 'Privacy', 'GET', '/retention/policy', []),
		_a('data_inventory', 'What do you know about me?', 'Privacy', 'GET', '/retention/inventory/{subject_ref}', [_s('path')]),
		_a('export_my_data', 'Download my data', 'Privacy', 'GET', '/retention/export/{subject_ref}', [_s('path'), _f('at_iso', 'When'), _f('channel', 'How?', 'select', ['native', 'sms', 'ussd', 'whatsapp'])]),
		_a('delete_my_data', 'Delete my data', 'Privacy', 'POST', '/retention/delete', [_s(), _f('data_type', 'Only this type', ph='leave blank for everything'), _f('channel', 'How?', 'select', ['native', 'sms', 'ussd', 'whatsapp'])]),
		_a('purge_expired', 'Clear what has expired', 'Privacy', 'POST', '/retention/purge-expired', [_s(), _f('age_days', 'How old each record is, by type', 'list', ph='symptom_logs=400, triage_results=30')]),
		_a('encryption_posture', 'How is my data protected?', 'Privacy', 'GET', '/retention/encryption', []),
		_a('transparency_report', 'Transparency report', 'Privacy', 'GET', '/retention/transparency', [_f('period', 'Period'), _f('subject_ref', 'Person the report is about', ph='optional')]),
		# §SEC-006's public quarterly document, which is a different thing from the row above: that
		# one is a person's view of their own data, this one is the aggregate nobody has to ask for.
		_a('public_transparency_report', 'What the programme publishes', 'Privacy', 'GET', '/transparency/report', [_f('period', 'Quarter', ph='2026-Q3'), _f('as_at_iso', 'As at')]),
		_a('publication_schedule', 'Is the public report on time?', 'Privacy', 'GET', '/transparency/schedule', [_f('period', 'Quarter', ph='2026-Q3')]),
		# §SEC-006's "Open-source client code" and §LOC-002's "Open-source client for independent
		# verification" — the same fact from two sections, and the reason it needs a *screen* rather
		# than only a file: the row says "for independent verification", which is something a reader
		# does. A licence a person can only find by opening the repository is a licence they cannot
		# check from the app they are trying to decide whether to trust.
		_a('licence_terms', 'Is this app open source?', 'Privacy', 'GET', '/security/licence', []),
		_a('record_holding', 'Record what is stored', 'Privacy', 'POST', '/retention/holding', [_s(), _f('data_type', 'Data type'), _f('count', 'How many records', 'int')]),
		_a('record_share', 'Record a data share', 'Privacy', 'POST', '/retention/share', [_s(), _f('with_who', 'Shared with'), _f('what', 'What was shared'), _f('when_iso', 'When')]),
		# §17.2's accuracy principle — "user data editable; correction workflows". The section's own
		# comment on this route calls a record a person cannot correct "a statutory gap, not a missing
		# feature", and no client could reach either half of it: the right to correct, and the history
		# that makes it a workflow rather than an overwrite. The subject is the token's own, so no
		# form draws one and `corrected_by` is the person themselves.
		_a('correct_my_data', 'Something about me is wrong', 'Privacy', 'POST', '/retention/correct', [_f('data_type', 'Which record?'), _f('field', 'Which detail?'), _f('corrected_value', 'What it should say'), _f('reason', 'Why is it wrong?', 'textarea'), _s(), _f('corrected_by', 'Who is correcting it?', ph='you'), _f('channel', 'How?', 'select', ['native', 'sms', 'ussd', 'whatsapp']), _f('at_iso', 'When', ph='2026-10-12T08:30')]),
		_a('my_corrections', 'Corrections I have asked for', 'Privacy', 'GET', '/retention/corrections', []),
		# Access & fairness
		_a('access_profile', 'Make the app easier to use', 'Access', 'POST', '/access/profile', [_s(), _f('simple_mode', 'Simple mode', 'bool'), _f('large_text', 'Large text', 'bool'), _f('high_contrast', 'High contrast', 'bool'), _f('read_aloud', 'Read screens aloud', 'bool'), _f('voice_input', 'Speak instead of typing', 'bool'), _f('lang', 'Language')]),
		_a('ui_screens', 'Screen list', 'Access', 'GET', '/access/screens', [_f('simple_mode', 'Simple mode', 'bool')]),
		_a('languages', 'Languages', 'Access', 'GET', '/access/languages', [_f('tier', 'Priority tier', 'int')]),
		_a('voice', 'Speak to the app', 'Access', 'POST', '/access/voice', [_s(), _f('lang', 'Language'), _f('utterance', 'What you said'), _f('purpose', 'Symptoms or a note?', 'select', VOICE_PURPOSES), _f('offline', 'No network?', 'bool')]),
		_a('voice_audio', 'Send a recording', 'Access', 'POST', '/access/voice/audio', [_s(form=True), _f('lang', 'Language', 'select', VOICE_LANGS, form=True), _f('purpose', 'Symptoms or a note?', 'select', VOICE_PURPOSES, form=True), _f('file', 'Recording', 'file', form=True, accept='audio/*')]),
		# §ACC-004's context flags. The device knows them, so the client fills them from its own state
		# rather than asking — but they are fields, not `server_assigned`, because a form that cannot
		# reach them would leave the adaptive rate unreachable from the one screen that shows it.
		_a('battery_profile', 'Battery use', 'Access', 'GET', '/access/battery', [_s(), _f('intensity', 'Monitoring level', 'select', INTENSITIES), _f('battery_saver', 'Battery saver', 'bool'), _f('charging', 'On charge?', 'bool'), _f('stationary', 'Phone still?', 'bool'), _f('hour', 'Hour of the day', 'int'), _f('on_call', 'On a call?', 'bool'), _f('do_not_monitor', 'Pause monitoring?', 'bool')]),
		_a('compatibility', 'Will it work on my phone?', 'Access', 'GET', '/access/compatibility/{platform}', [_f('platform', 'Phone type', 'path'), _f('smallest_width_dp', 'Screen width in dp', 'int', ph='320')]),
		_a('screen_layouts', 'How the app fits my screen', 'Access', 'GET', '/access/screen-layouts', []),
		_a('sensor_capabilities', 'What my phone can measure', 'Access', 'GET', '/sensors/capabilities', []),
		_a('model_cards', 'How the AI works', 'Access', 'GET', '/ai/models', []),
		_a('fairness_audit', 'Check an AI model is fair', 'Access', 'POST', '/ai/fairness-audit', [_f('model_id', 'Model'), _f('axes', 'Axes tested', 'list'), _f('unmet_axes', 'Failures found', 'list')]),
		_a('file_redress', 'Challenge a decision', 'Access', 'POST', '/ai/redress', [_f('request_id', 'Request number'), _s(), _f('output_kind', 'What are you challenging?', 'select', OUTPUT_KINDS), _f('output_ref', 'Which result?'), _f('challenge', 'Why do you disagree?', 'textarea')]),
		# Health workers
		_a('provision_chw', 'Register a health worker', 'Health workers', 'POST', '/chw/provision', [_f('chw_ref', 'Health worker'), _f('name', 'Full name'), _f('county', 'County'), _f('community', 'Village or estate'), _f('registry_verified', 'Verified on the national register?', 'bool'), _f('provisioned_by', 'Registered by', 'select', list(PROVISIONERS))]),
		_a('chw_profile', 'Health worker profile', 'Health workers', 'GET', '/chw/{chw_ref}', [_f('chw_ref', 'Health worker', 'path')]),
		_a('chw_training', 'Training modules', 'Health workers', 'GET', '/chw/training', []),
		_a('job_aid', 'Job aid', 'Health workers', 'GET', '/chw/job-aid/{topic}', [_f('topic', 'Topic', 'path')]),
		_a('assign_chw_case', 'Assign a case', 'Health workers', 'POST', '/chw/{chw_ref}/cases', [_f('chw_ref', 'Health worker', 'path'), _f('report_id', 'Report number'), _f('status', 'Status', 'select', CASE_STATUSES), _f('suspected_disease', 'Suspected disease', 'select', VECTOR_DISEASES), _f('reported_iso', 'Reported on'), _f('surveillance_officer', 'Surveillance officer'), _f('ppe_reminder_due', 'Protective equipment reminder due?', 'bool'), _f('next_action', 'Next step')]),
		_a('chw_cases', 'My cases', 'Health workers', 'GET', '/chw/{chw_ref}/cases', [_f('chw_ref', 'Health worker', 'path')]),
		_a('log_chw_activity', 'Log a visit', 'Health workers', 'POST', '/chw/activity', [_f('chw_ref', 'Health worker'), _f('at_iso', 'When'), _f('activity', 'What did you do?', 'select', ACTIVITY_KINDS), _f('community', 'Village or estate'), _f('notes', 'Notes', 'textarea')]),
		_a('chw_activity', 'My activity this week', 'Health workers', 'GET', '/chw/{chw_ref}/activity', [_f('chw_ref', 'Health worker', 'path'), _f('period', 'Period')]),
		_a('chw_case_load', 'How many cases am I carrying?', 'Health workers', 'GET', '/chw/{chw_ref}/case-load', [_f('chw_ref', 'Health worker', 'path')]),
		_a('chw_ppe_reminder', 'Protective equipment check', 'Health workers', 'GET', '/chw/ppe-reminder', []),
		# Channels, sync, sensors
		_a('assign_chw_task', 'Assign a task', 'Channels', 'POST', '/channels/chw/tasks', [_f('task_id', 'Task number'), _f('chw_ref', 'Health worker'), _f('community', 'Village or estate'), _f('kind', 'Kind', 'select', CHW_TASK_KINDS)]),
		_a('chw_open_tasks', 'Open tasks', 'Channels', 'GET', '/channels/chw/tasks/{chw_ref}', [_f('chw_ref', 'Health worker', 'path')]),
		_a('callback_requests', 'People waiting for a call back', 'Channels', 'GET', '/channels/callbacks', [_f('unhandled_only', 'Only those not yet called?', 'bool')]),
		_a('callback_handled', 'Mark a call back as done', 'Channels', 'POST', '/channels/callbacks/{request_id}/handled', [_f('request_id', 'Request number', 'path')]),
		_a('channel_reports', 'Symptoms reported by phone', 'Channels', 'GET', '/channels/reports', [_f('channel', 'Which channel?', 'select', ['ussd', 'sms', 'whatsapp', 'app']), _f('unhandled_only', 'Only those not yet read?', 'bool')]),
		_a('channel_report_handled', 'Mark a report as read', 'Channels', 'POST', '/channels/reports/{report_id}/handled', [_f('report_id', 'Report number', 'path')]),
		# §CHAN-000's call-in, from the side of the person working the queue. The queue holds
		# callers' words and their handles, so it is `assigned` — the same scope and the same reason
		# as the callback queue above it. Scheduling a programme is operations rather than a
		# broadcaster's, because §17.4's eight roles hold no such scope and inventing a ninth is not
		# a thing a route may do.
		_a('schedule_live_session', 'Put a programme on the schedule', 'Channels', 'POST', '/live/sessions',
		   [_f('platform', 'Where?', 'select', [k.value for k in LivePlatform]), _f('topic', 'What is it about?'),
		    _f('clinician', 'Who is answering?', ph='the name they are announced under'),
		    _f('starts_at_iso', 'Starts at', ph='YYYY-MM-DDTHH:MM:SSZ'), _f('ends_at_iso', 'Ends at', ph='YYYY-MM-DDTHH:MM:SSZ'),
		    _f('lang', 'Language', 'select', ['en', 'sw']), _f('venue', 'Where from?', ph='optional')]),
		_a('live_queue', 'Questions waiting on air', 'Channels', 'GET', '/live/sessions/{session_id}/queue',
		   [_f('session_id', 'Programme', 'path'), _f('pending_only', 'Only those not yet answered?', 'bool')]),
		_a('open_live_session', 'Start a programme', 'Channels', 'POST', '/live/sessions/{session_id}/open',
		   [_f('session_id', 'Programme', 'path')]),
		_a('close_live_session', 'End a programme', 'Channels', 'POST', '/live/sessions/{session_id}/close',
		   [_f('session_id', 'Programme', 'path')]),
		_a('answer_live_question', 'Answer a question', 'Channels', 'POST', '/live/questions/{question_id}/answer',
		   [_f('question_id', 'Question', 'path'), _f('answer', 'Your answer', 'textarea')]),
		_a('decline_live_question', 'Say a question will not be taken', 'Channels', 'POST', '/live/questions/{question_id}/decline',
		   [_f('question_id', 'Question', 'path'), _f('reason', 'Why not?', 'textarea')]),
		# §CHAN-004's moderation queue: what people have offered to share, before anyone sees it.
		_a('story_queue', 'Stories waiting to be checked', 'Channels', 'GET', '/info/stories/pending', []),
		_a('moderate_story', 'Check a story', 'Channels', 'POST', '/info/stories/{story_id}/moderate',
		   [_f('story_id', 'Story', 'path'), _f('decision', 'Decision', 'select', ['approve', 'decline']),
		    _f('note', 'Note for the record', 'textarea', when='decision', equals_any=['decline'],
		       ph='optional when approving')]),
		_a('complete_chw_task', 'Complete a task', 'Channels', 'POST', '/channels/chw/tasks/{task_id}/done', [_f('task_id', 'Task number', 'path')]),
		_a('send_sms', 'Send a free text message', 'Channels', 'POST', '/channels/sms', [_f('to_msisdn', 'Phone number'), _f('body', 'Message')]),
		_a('channel_costs', 'Will this cost me airtime?', 'Channels', 'GET', '/channels/cost', []),
		_a('plain_language', 'Is our message plain enough?', 'Channels', 'GET', '/channels/plain-language', []),
		_a('queue_sync_op', 'Save for later (offline)', 'Sync', 'POST', '/sync/ops', [_f('op_id', 'Change number'), _f('dataset', 'What kind of change?', 'select', SYNC_DATASETS), _f('client_ts', 'When it happened', 'int')]),
		_a('flush_sync', 'Send everything now', 'Sync', 'POST', '/sync/flush', [_f('connection', 'Connection', 'select', ['wifi', 'metered', 'offline'])]),
		_a('offline_state', 'Is my work saved?', 'Sync', 'GET', '/sync/state', []),
		# §16.3's conflict matrix, from the side that has to live with it. A write the server
		# overruled is invisible to a client that never asks, so the person whose edit lost had no
		# way to learn it — and the appeal the section makes available for some strategies was
		# reachable by nobody. The queue is the device's, so no form names a subject.
		_a('sync_conflicts', 'Changes that did not save', 'Sync', 'GET', '/sync/conflicts', []),
		_a('appeal_conflict', 'Ask us to look again', 'Sync', 'POST', '/sync/conflicts/{op_id}/appeal', [_f('op_id', 'Change number', 'path'), _f('note', 'Why should it be kept?', 'textarea')]),
		_a('sensor_ingest', 'Save a reading', 'Sensors', 'POST', '/sensors/ingest', [_f('kind', 'Reading type', 'select', SENS_KINDS), _s(), _f('value', 'Value', 'decimal'), _f('county', 'County')]),
		# §SENS-001's server-side half: the device measures the motion series and this turns it into
		# a rate. Distinct from `sensor_ingest` above, which stores a number the device already
		# derived — this route does the derivation, and `_INGEST_FEATURE` binds the respiration kind
		# it writes to SENS-001. Tier-4 gated like the ingest, so it stays dark until PHEOC activates.
		_a('estimate_breathing', 'Work out my breathing rate', 'Sensors', 'POST', '/sensors/breath/estimate', [_s(), _f('series', 'Motion readings', 'list', ph='a comma-separated series from the sensor'), _f('fps', 'Readings per second', 'decimal')]),
		_a('analyse_cough', 'Check a cough recording', 'Sensors', 'POST', '/ml/cough/analyze', [_f('file', 'Recording', 'file', form=True, accept='audio/*')]),
		_a('submit_evidence', 'Send a photo for review', 'Sensors', 'POST', '/evidence', [_s(form=True), _f('file', 'Photo', 'file', form=True, accept='image/*'), _f('kind', 'What is it?', 'select', EVIDENCE_KINDS, form=True), _f('note', 'What did you notice?', 'textarea', form=True), _f('consent', 'I agree to share this photo', 'bool', form=True)]),
		# Tag taps. The titles are what a person does at a bedside, not what the mechanism is: a
		# wristband, a medicine box and a station are three things in a room and one action each.
		_a('tag_resolve', 'What is this tag?', 'Sensors', 'GET', '/sensors/tags/{tag_id}', [_f('tag_id', 'Tag', 'path')]),
		_a('tag_tap', 'Record this tap', 'Sensors', 'POST', '/sensors/tags/{tag_id}/tap', [_f('tag_id', 'Tag', 'path'), _f('at_iso', 'When'), _f('worker_ref', 'Who tapped it?', ph='only for a station log')]),
		_a('tag_bind', 'Register a tag', 'Sensors', 'POST', '/sensors/tags', [_f('tag_id', 'Tag number'), _f('target', 'What is it on?', 'select', list(TAG_TARGETS)), _f('target_ref', 'Its number'), _f('label', 'What is it?'), _f('bound_at_iso', 'When')]),
		_a('tag_coverage', 'Which tag uses are live?', 'Sensors', 'GET', '/sensors/tag-coverage', []),
		_a('equipment_list', 'Where is our equipment?', 'Sensors', 'GET', '/sensors/equipment', [_f('status', 'Condition', 'select', list(EQUIPMENT_STATUSES))]),
		_a('equipment_add', 'Add equipment', 'Sensors', 'POST', '/sensors/equipment', [_f('asset_ref', 'Asset number'), _f('label', 'What is it?'), _f('status', 'Condition', 'select', list(EQUIPMENT_STATUSES))]),
		_a('equipment_move', 'Move equipment', 'Sensors', 'POST', '/sensors/equipment/{asset_ref}/move', [_f('asset_ref', 'Asset number', 'path'), _f('station', 'To which station?')]),
		# Insurance
		_a('file_price', 'Tell us what a procedure cost', 'Insurance', 'POST', '/insurance/prices', [_f('facility_id', 'Facility'), _f('procedure', 'Procedure', 'select', PROCEDURES), _f('kes', 'Cost in KES', 'int'), _f('sha_covered', 'Covered by SHA?', 'bool')]),
		_a('price_quote', 'What does it cost?', 'Insurance', 'GET', '/insurance/quote/{facility_id}/{procedure}', [_f('facility_id', 'Facility', 'path'), _f('procedure', 'Procedure', 'path')]),
		_a('sha_cover_check', 'Am I covered?', 'Insurance', 'POST', '/insurance/sha-check', [_f('member_no', 'SHA member number')]),
		_a('sha_cover_verify', 'Check my cover with SHA', 'Insurance', 'POST', '/insurance/sha/verify', [_f('member_no', 'SHA member number'), _f('purpose', 'What for?', 'select', ['facility_visit', 'registration', 'refund'])]),
		_a('sha_facilities', 'Where is my cover accepted?', 'Insurance', 'GET', '/insurance/sha/facilities', [_f('county', 'County')]),
		_a('sha_benefits', 'What does my cover include?', 'Insurance', 'GET', '/insurance/sha/benefits', [_f('product', 'Scheme', ph='SHIF')]),
	]


def dormant_slugs() -> frozenset[str]:
	"""The curated dormancy list, unioned with every action whose feature is Tier 4.

	Two sources, deliberately. `DORMANT_SLUGS` is the reviewed statement of intent; the tier model
	is the invariant. Taking the union means a Tier-4 feature added later is dark from the moment it
	exists, and `test_every_tier4_action_is_dormant` asserts the two agree so the safety net never
	quietly carries a discrepancy the curated list should have stated.
	"""
	tier4 = tier4_feature_ids()
	return DORMANT_SLUGS | frozenset(slug for slug, feat in FEATURE_OF.items() if feat in tier4)


def available(
	tier4_active: bool, scopes: frozenset[str] | None = None,
	feature_available: Callable[[str], bool] | None = None,
) -> list[MobileAction]:
	"""Actions the client may show right now.

	Two ways a control is withheld, for the same reason — a person must never see a switch that
	would refuse them. Dormant outbreak capabilities stay hidden until §11.1 activates them. And an
	operator control is hidden from a caller whose role does not hold the §17.4 dataset its route
	checks: `publish_content` is not a citizen action, and offering a health-information form to a
	phone that will get a 403 is the dormancy bug wearing a different hat.

	`feature_available` is §11.1's model, asked per feature, and it is what makes the individual
	triggers mean anything here. `tier4_active` is a single boolean — the PHEOC declaration — and
	with only that, a person who had asked for monitoring (row 5) or been identified as a contact
	(row 3) still saw no diary: the one control the row exists to give them stayed hidden behind a
	national declaration, while the route behind it would have served them. Passing the model in
	keeps this module free of the registry (it is imported by the client-facing surface) and keeps
	`tier4_active` as the honest default for operator tooling, which has no subject.

	The gate applies only to a dormant slug. `dormant_slugs()` is what marks an action as an
	outbreak capability, so a feature below Tier 4 is not asked at all — asking it would hide the
	whole catalogue whenever the event is off, which is the failure this predicate must not have.

	`scopes` is the caller's scope set. `None` means "show everything", which is what the
	catalogue's own tests and the operator tooling want; a request supplies the real set.
	"""
	hidden = dormant_slugs()
	allowed = feature_available or (lambda _feature_id: tier4_active)
	rows = [
		a for a in catalogue()
		if (a.id not in hidden or allowed(FEATURE_OF[a.id]))
		and (scopes is None or OPERATOR_SCOPES.get(a.id) is None or OPERATOR_SCOPES[a.id] in scopes)
	]
	assert rows, 'catalogue must never be empty'
	return rows


def marked(actions: 'list[MobileAction]',
           required: dict[tuple[str, str], frozenset[str]]) -> 'list[MobileAction]':
	"""The same actions with `required` read off each route rather than off each field's type.

	Pure, so the route can call it per request and a test can call it with a catalogue it built. The
	caller passes `afya.access.forms.required_fields(app)` — one reading of what a route needs, shared
	with §ACC-001's drop list, so the form and the list cannot disagree about what a route requires.

	The assertion is the contract `FieldCondition` states: a field is either unconditionally required
	or conditionally required, never both. A client that read a condition on an always-required field
	would drop the asterisk exactly when the answer made the field matter most, and the failure would
	be a form that stops warning rather than one that stops working — which is the shape this whole
	unit is about.
	"""
	out: list[MobileAction] = []
	for act in actions:
		needed = required.get((act.method, act.path), frozenset())
		names = {f.name for f in act.fields}
		# A group naming a field the action does not carry is a rule no form can satisfy: the client
		# would look for an answer to a question that is not on the screen and refuse every
		# submission. A group naming a field the route *always* requires is dead for the same reason —
		# the group can never be the thing that makes the submission complete.
		for group in act.any_of:
			unknown = set(group.fields) - names
			assert not unknown, f'{act.id}: any_of names fields the action lacks: {sorted(unknown)}'
			if group.when is not None:
				assert group.when in names, f'{act.id}: any_of is gated on {group.when!r}, which it lacks'
			dead = set(group.fields) & needed
			assert not dead, (
				f'{act.id}: any_of includes {sorted(dead)}, which the route always requires, so the '
				'group is never what makes the submission complete')
		# "The trigger has any answer" is only a condition if the trigger can be left unanswered.
		# It could not: both clients rendered a picker that always held a value, so every optional
		# select was sent with its first option and this shape was **always true** — a condition that
		# reads as conditional and behaves as `required = True`, which is the defect this unit exists
		# to close, one level down. Both clients now offer a blank choice on a select the route does
		# not require, which is what makes the shape mean what it says. On a select the route *does*
		# require the trigger can never be blank, so the shape is dead there and stays refused.
		kinds = {f.name: f.type for f in act.fields}
		for f in act.fields:
			c = f.condition
			if c is not None and not c.equals_any and kinds.get(c.when) == 'select':
				assert c.when not in needed, (
					f'{act.id}.{f.name}: the condition fires on any answer to {c.when!r}, which its '
					'route always requires — the trigger can never be blank, so the condition is '
					'always true. Name the answers that fire it instead')
		fields: list[MobileField] = []
		for f in act.fields:
			conditional = f.condition is not None
			in_group = any(f.name in g.fields for g in act.any_of)
			# A value nobody can know until the request arrives cannot be a value the route refuses
			# without: the model would refuse every request that omits it and no form could ever
			# supply it. `_auto()` marks these precisely so the route gives them a default, and this
			# is the assertion that keeps a hand-written field from undoing that.
			assert not (f.server_assigned and f.name in needed), (
				f'{act.id}.{f.name} is server-assigned and the route requires it, so no form can '
				'complete the request; give the model a default')
			assert not (conditional and f.name in needed), (
				f'{act.id}.{f.name} is both unconditionally required by its route and conditional; '
				'the condition would be shadowed and a client would stop asking for it')
			assert not (in_group and f.name in needed), (
				f'{act.id}.{f.name} is in an any_of group and unconditionally required by its route; '
				'the group would demand a field the route already has')
			fields.append(f.model_copy(update={'required': f.name in needed and not conditional}))
		out.append(act.model_copy(update={'fields': fields}))
	return out


# slug -> (screen-visible title, one-line human description). No spec codes anywhere.
FRIENDLY_COPY: dict[str, tuple[str, str]] = {
	'traveller_prompt': ('What am I asked today?', 'The question for this day of your 21-day check, in your own language'),
	'traveller_report': ('Report how I feel today', 'Send how you feel on a scheduled day of your 21-day check'),
	'county_risk': ('How is my county doing?', 'Official risk status and guidance where you live'),
	'signal_scan': ('How is my county this week?', 'The six outbreak signals, counted and compared with recent weeks'),
	'signal_report': ('Report a signal', 'Log one occurrence of an outbreak signal for your county'),
	'set_county_risk': ('Update a county status', 'Set the risk level and guidance people in a county see'),
	'record_case_counts': ('Record case counts', 'Log a county’s confirmed and suspected cases for a period'),
	'record_sub_county': ('Record an affected area', 'Log the sub-counties and places with cases, so people can see whether it is near them'),
	'decision_tree': ('Should I see a doctor?', 'Plain-language help deciding your next step'),
	'hotlines': ('Who can I call?', 'Hotline numbers that are free and answered'),
	'febrile_triage': ('Check my fever', 'Quick check: treat malaria first unless there is Ebola contact risk'),
	'what_should_i_do': ('What should I do?', 'A few yes/no questions that lead to advice'),
	'entry_answers': ('What do you need help with?', 'Six common worries, each opening the right guidance'),
	'health_library': ('Health information', 'Ebola, prevention, first aid, safe burial — official guidance'),
	'search_library': ('Search health information', 'Find guidance by what you are looking for'),
	'library_categories': ('Browse by topic', 'Guidance grouped by subject, with how much is in each'),
	'myth_library': ('What is rumour and what is true?', 'Rumours going round, each with the facts and who says so'),
	'ask_about_a_rumour': ('Is it true that…?', 'Ask about something you heard and get the answer and its source'),
	'publish_content': ('Draft health information', 'Write or correct a guidance item for review'),
	'advance_content': ('Move a draft forward', 'Send an item to the next review stage, or retire it'),
	'content_governance': ('Who reviewed this?', 'Who owns each guidance item and when it was last reviewed'),
	'report_content_error': ('Report a wrong guidance item', 'Pull a guidance item that is wrong and send the correction'),
	'content_errors': ('What guidance was found wrong?', 'Guidance items pulled for being wrong, and where each stands'),
	'record_back_translation': ('Record a back-translation', 'Write down the text someone rendered back, and who did it'),
	'record_community_validation': ('Record community validation', 'Write down who took the text to the community, and what they said'),
	'content_localisation': ('How was this translated?', 'Each translated item, who checked it, and what is still missing'),
	'hotline_directory': ('Useful phone numbers', 'Hotlines and offices you can call'),
	# §CHAN-000's call-in and §CHAN-004's clinician Q&A, in the words a listener would use.
	'live_sessions': ('Is anything on air?', 'Programmes where you can put a question to a health worker'),
	'ask_live_question': ('Ask on air', 'Put your question to whoever is answering, while the programme runs'),
	'live_transcript': ('What was answered', 'Read back the questions that were taken, if you missed it'),
	'submit_story': ('Share your experience', 'Tell others how it went for you — we ask your permission first'),
	'schedule_live_session': ('Put a programme on air', 'Announce a call-in or a live question session'),
	'live_queue': ('Questions waiting', 'What people have asked on the programme you are running'),
	'open_live_session': ('Start the programme', 'Open the lines and begin taking questions'),
	'close_live_session': ('End the programme', 'Close the lines, and see what was left unanswered'),
	'answer_live_question': ('Answer a question', 'Reply to one person, on air'),
	'decline_live_question': ('Set a question aside', 'Say why this one will not be taken, so the record shows it'),
	'story_queue': ('Stories to check', 'What people have offered to share, before anyone else sees it'),
	'moderate_story': ('Check a story', 'Approve it into the content workflow, or turn it down with a reason'),
	'medicine_registry': ('Which medicines are approved?', 'Check a medicine against the national register'),
	'find_stock': ('Where can I get this medicine?', 'Which nearby places have it, and how long ago someone checked'),
	'stock_availability': ('Is it in stock right now?', 'The latest report for one medicine at one place'),
	'essential_medicines': ('Essential medicines', 'The medicines the health service says must always be available'),
	'restock_alerts': ('What came back in stock?', 'Medicines that had run out and are available again'),
	'medicine_recalls': ('Has a medicine been recalled?', 'Recalls and safety notices from the regulator'),
	'report_suspicious_medicine': ('Report a fake medicine', 'Tell the regulator about a suspected falsified drug'),
	'sha_cover_verify': ('Check my cover with SHA', 'Confirm your cover directly with the authority'),
	'sha_facilities': ('Where is my cover accepted?', 'Facilities that accept your cover, by county'),
	'sha_benefits': ('What does my cover include?', 'Benefits included in your scheme'),
	'service_status': ('Are services open today?', 'School, market, water, road and transport disruptions near you'),
	'testing_sites': ('Where can I get tested?', 'Testing sites near you for malaria, HIV, TB and more'),
	'vaccination_points': ('Where can I get vaccinated?', 'Routine and campaign vaccination points near you'),
	'risk_zones_near_me': ('Have I entered a risk area?', 'Check whether you are inside an outbreak advisory zone'),
	'symptom_diary': ('My symptom diary', 'Track how you feel if you were exposed'),
	'evd_triage': ('Ebola check', 'Deeper screening when officials activate outbreak mode'),
	'nearest_facilities': ('Find care near me', 'Nearest clinics and hospitals with walking directions'),
	'ed_status': ('How busy is A&E?', 'Live queues at casualty units'),
	'book_appointment': ('Book an appointment', 'Skip the queue with a slot'),
	'view_slots': ('What times are free?', 'See a clinic’s appointment times for a day, and which are full'),
	'reschedule_appointment': ('Move my appointment', 'Change the time of an appointment you booked'),
	'cancel_appointment': ('Cancel my appointment', 'Give up your appointment time so someone else can take it'),
	'publish_slot': ('Offer appointment times', 'Publish the times your facility will see people, and how many at each'),
	'verify_medicine': ('Is my medicine real?', 'Check any drug against the national registry'),
	'drug_interactions': ('Can I take these together?', 'Check risky medicine combinations'),
	'dosage': ('How much do I give?', 'Correct dose by weight'),
	'sos': ('Get help now', 'One tap: alerts the hotline and your people'),
	'sos_countdown': ('Hold on — sending in a moment', 'A few seconds to stop an accidental alert'),
	'sos_cancel': ('Stop the alert', 'Call off an alert before it goes out'),
	'sos_fire': ('Send the alert now', 'Send an alert you already started the countdown for'),
	'sos_state': ('What happened to my alert?', 'Whether your alert was sent, stopped or is waiting'),
	'emergency_card': ('My emergency card', 'Works with no signal on your lock screen'),
	'family_wallet': ('Family health wallet', "Everyone's immunisations and records in one place"),
	'growth_flag': ('Is my child growing well?', 'Compare growth with healthy ranges'),
	'wallet_documents': ('Everything in the wallet', 'Every card, result and letter you have saved'),
	'file_document': ('Add a document', 'Photograph a card or letter and keep it in the wallet'),
	'health_timeline': ('My health history', 'Everything that has happened, newest first'),
	'wallet_search': ('Find a document', 'Search everything saved in the wallet'),
	'share_record': ('Share my record', 'Give a clinic or a person a link that expires'),
	'record_shares': ('Who has seen my record?', 'Every share you have given, and when each ends'),
	'revoke_share': ('Stop sharing', 'End a share before it expires'),
	'provider_view': ('A patient record shared with me', 'Read a record a patient has shared with you'),
	'export_record': ('Export a health record', 'A PDF or a file for school, travel or work'),
	'backup_wallet': ('Back up the wallet', 'Keep an encrypted copy so nothing is lost'),
	'growth_chart': ('My child growth chart', 'Weight and height against the healthy range'),
	'milestone_checklist': ('What should my child be doing?', 'The skills expected at this age'),
	'milestone_check': ('Milestones my child has reached', 'Check the skills and get advice'),
	'vaccination_certificate': ('Vaccination certificate', 'Proof of doses for travel, school or work'),
	'child_schedule': ('My child vaccine schedule', 'Every dose due, and the ones that were missed'),
	'add_medication': ('Remind me to take my medicine', 'Never miss a dose or a refill'),
	'register_donor': ('Donate blood', 'Join the donor list for your county'),
	'find_donors': ('Find blood', 'Matching for nearby eligible donors'),
	'donor_alerts': ('Who can give blood?', 'The donors to call, and how far each one is'),
	'donation_centres': ('Where can I give blood?', 'Donation sites near you, and blood banks'),
	'wellbeing_check': ('How am I feeling?', 'Gentle check-in plus free counselling lines'),
	'mood_screen': ('How am I really doing?', 'A short, well-known check for low mood or worry'),
	'mood_log': ('How is my mood today?', 'One tap a day, and you can see the shape of your weeks'),
	'mood_trend': ('How has my mood been?', 'Your own scores, and which way they are moving'),
	'coping_tips': ('What can I do to cope?', 'Practical steps for hard days, from WHO guidance'),
	'outbreak_support': ('Support during the outbreak', 'Isolation, grief, and looking after yourself on shift'),
	'ask_referral': ('Ask to be referred', 'We point you to a service and tell you if a number is unchecked'),
	'log_bp': ('My blood pressure', 'Daily readings and trends'),
	'log_glucose': ('My blood sugar', 'Daily readings and trends'),
	'track_refill': ('Refill reminders', 'Know before your medicine runs out'),
	'peak_flow': ('My peak flow', 'Asthma zones from your own best reading'),
	'log_weight': ('My weight', 'A real trend, logged weekly'),
	'kidney_result': ('My kidney results', 'What your creatinine and urine albumin mean'),
	'seizure_log': ('Log a seizure', 'How long it lasted, and whether to call for help'),
	'sickle_crisis': ('Sickle cell crisis', 'Pain and the signs that mean go to a facility now'),
	'trend_chart': ('My readings over time', 'See whether a number is going the right way'),
	'appointments': ('My reviews', 'What is due, and what you have missed'),
	'lifestyle_guidance': ('Living with my condition', 'What helps, what to avoid, and why'),
	'register_pregnancy': ('Pregnancy care', 'Visits and danger signs we take seriously'),
	'danger_signs': ('Something feels wrong', 'One tap to escalate a pregnancy danger sign'),
	'log_cycle': ('My cycle', 'Private period tracking and predictions'),
	'cycle_prediction': ('When is my next period?', 'Your next period and fertile days, from your own logs'),
	'contraception_methods': ('What methods are there?', 'What is available, and how well each one works'),
	'set_contraception': ('Record my method', 'Keep track and get a reminder when it is due'),
	'contraception_due': ('What is due?', 'Anything you need to take or change today'),
	'menopause_state': ('Where am I in the change?', 'What your cycle is doing, and what may help'),
	'reproductive_referral': ('Where can I get help?', 'Services for family planning and reproductive health'),
	'submit_evidence': ('Send a photo for review', 'Show a nurse; we verify and route it'),
	'tag_resolve': ('What is this tag?', 'Tap a wristband, a medicine box or a station tag to see what it is'),
	'tag_tap': ('Record this tap', 'Log that a tag was tapped, and by whom where that matters'),
	'tag_bind': ('Register a tag', 'Attach a tag to a patient bed, a medicine box, a station or a piece of equipment'),
	'tag_coverage': ('Which tag uses are live?', 'Each use of a tag, and whether anything is set up behind it'),
	'equipment_list': ('Where is our equipment?', 'Every asset on the register, its condition, and where it is'),
	'equipment_add': ('Add equipment', 'Put an asset on the register so a tag can point at it'),
	'equipment_move': ('Move equipment', 'Record that an asset has gone to another station'),
	'provision_chw': ('Community health workers', 'Tasks and the people you help'),
	'submit_case': ('Report a suspected case', 'Structured report that alerts the officer for you'),
	'report_issue': ('Report a problem in my area', 'Sewage, dumping, broken water points'),
	'flag_misinformation': ('Report something I heard', 'Help stop a rumour before it spreads'),
	'water_advisory': ('Is the water safe?', 'Boil-water advisories for your area, and how to make it safe'),
	'air_advisory': ('How is the air?', 'The air quality index where you are, and when it is cleanest to go out'),
	'vector_risk': ('Mosquito and vector risk', 'Seasonal risk from the rain you just had'),
	'larviciding': ('Is my area being treated?', 'Mosquito control rounds in your county'),
	'issue_larviciding': ('Announce a mosquito control round', 'Tell residents where and when spraying happens'),
	'protection_reminder': ('Remind me about mosquitoes', 'When to use your net, and when to clear standing water'),
	'nutrition': ('What should my child eat?', 'Age-appropriate feeding and what is in season'),
	'therapeutic_feeding': ('Where can a malnourished child get help?', 'Therapeutic feeding programmes near you'),
	'issue_alert': ('Send a public alert', 'Broadcast an official notice to a county'),
	'price_quote': ('What does it cost?', 'Typical prices per facility'),
	'data_inventory': ('What do you know about me?', 'Everything stored, and who it was shared with'),
	'export_my_data': ('Download my data', 'A copy of everything held about you, and what it leaves out'),
	'delete_my_data': ('Delete my data', 'Remove what is yours; we tell you what must stay'),
	'access_profile': ('Make the app easier to use', 'Bigger text, simple mode, read aloud'),
	'channel_costs': ('Will this cost me airtime?', 'What each way of reaching us costs you, and whether it is free'),
	'callback_requests': ('Who is waiting for a call back?', 'People who asked to be phoned, and whether anyone has rung them yet'),
	'callback_handled': ('Mark a call back as done', 'Say you have rung someone, so the next person does not ring them again'),
	'channel_reports': ('What symptoms came in by phone?', 'Reports sent by text or USSD, and which ones nobody has read yet'),
	'channel_report_handled': ('Mark a report as read', 'Say you have read a report, so the next person does not read it again'),
	'voice': ('Speak to the app', 'Ask in your own language'),
	'voice_audio': ('Send a recording', 'Speak a symptom report or a note and we will write it down'),
	'enrol_monitoring': ('Start my 21-day check-in', 'A short daily temperature log while you are being watched over'),
	'monitoring_day': ('Log today', 'Temperature and how you feel, morning and evening'),
	'monitoring_diary': ('My 21-day diary', 'Every day you have logged, and the countdown to the end'),
	'monitoring_reminders': ('What is still to log today', 'The check-ins you have done, and the ones you have not'),
	'monitoring_consent': ('Share my location while I am monitored', 'Off unless you turn it on, and you can turn it off again'),
	'monitoring_members': ('Add someone I live with', 'Their readings go in the same diary as yours'),
	'monitoring_member_diary': ('Their readings', 'What the person you added has logged so far'),
	'monitoring_officer': ('Call my monitoring officer', 'The health worker assigned to your check-in'),
}
