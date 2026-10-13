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

from pydantic import BaseModel, ConfigDict

from afya.community.views import FOLLOWUP_DAYS
from afya.location.views import ALERT_ZONE_RADII_M
from afya.medicine import contraindications
from afya.monitoring.views import LARVICIDE_CLASSES
from afya.records.views import WALLET_DOC_KINDS
from afya.registry.diseases import DISEASES
from afya.access.views import LANGUAGE_MATRIX
from afya.strings import SUPPORTED_LANGS

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

FieldType: TypeAlias = Literal['text', 'int', 'decimal', 'bool', 'select', 'textarea', 'list', 'file', 'path']
FIELD_TYPES: tuple[str, ...] = ('text', 'int', 'decimal', 'bool', 'select', 'textarea', 'list', 'file', 'path')


class MobileField(BaseModel):
	model_config = MODEL_CONFIG
	name: str
	label: str
	type: Literal['text', 'int', 'decimal', 'bool', 'select', 'textarea', 'list', 'file', 'path']
	options: list[str] | None = None
	placeholder: str | None = None
	required: bool = False
	# True when the client must supply this field from its own identity and must not draw it. A
	# personal-data route binds the subject it is given to the token that gave it (§17), so a form
	# offering to type a subject would offer a control the server refuses — the §11.1 defect.
	client_supplied: bool = False
	# True when the *server* fills this field and a form must not ask for it. Distinct from
	# `client_supplied`: that one means the client knows the value and the person does not, this one
	# means nobody knows it until the request arrives. Both are undrawn, and the difference matters
	# because a client injecting its own subject keys off the first and must not key off the second.
	server_assigned: bool = False


class MobileAction(BaseModel):
	model_config = MODEL_CONFIG
	id: str
	title: str
	group: str
	method: Literal['GET', 'POST', 'DELETE']
	path: str  # may contain {placeholders} backed by type='path' fields
	fields: list[MobileField] = []


BLOOD_GROUPS = ['O-', 'O+', 'A-', 'A+', 'B-', 'B+', 'AB-', 'AB+']
SENS_KINDS = ['respiration', 'cough', 'fall', 'ppg', 'sleep', 'ambient']
ALERT_KINDS = ['outbreak_cholera', 'outbreak_malaria', 'outbreak_dengue', 'outbreak_mpox', 'outbreak_rvf', 'outbreak_evd', 'flood', 'water_quality', 'school_closure', 'public_health_notice']
SYNC_DATASETS = ['symptom_logs', 'temperature', 'case_reports', 'immunisation', 'medication', 'facility', 'content', 'proximity_tokens']
PROCEDURES = ['c_section', 'normal_delivery', 'outpatient', 'inpatient_day', 'dialysis', 'x_ray', 'theatre']
FACILITY_KINDS = ['treatment_unit', 'ed', 'testing_site', 'pharmacy', 'vaccination_point']
EVIDENCE_KINDS = ['rash', 'red_eye', 'pallor', 'scene_photo']
ISSUE_KINDS = ['broken_water_point', 'open_sewage', 'illegal_dumping', 'mosquito_breeding', 'dead_animal', 'unsafe_food_vendor', 'counterfeit_medicine', 'facility_stockout', 'facility_staff_absence']
CASE_STATUSES = ['reported', 'investigated', 'lab_result', 'closed']
CONTACT_SETTINGS = ['home', 'work', 'transport', 'worship', 'market', 'social', 'other']
MISINFO_MEDIA = ['text', 'voice', 'screenshot', 'whatsapp_forward']
CHECKIN_KINDS = ['border_post', 'health_facility', 'isolation_unit', 'vaccination_point', 'school', 'workplace', 'event']
CHECKIN_METHODS = ['qr', 'nfc', 'manual']
# §3.3 principle 12's vocabulary, read from the one module that carries it. This was a fourth copy
# of the list, and the copies had already drifted: this one and `community.CaseReport` had `measles`,
# `surveillance.CountySignal` did not, and `alerts.AlertKind` had neither `measles` nor `other`.
VECTOR_DISEASES = list(DISEASES)
ADHERENCE_ACTIONS = ['taken', 'skipped', 'snoozed']
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
CONTENT_STAGES = ['draft', 'clinical_review', 'translation', 'back_translation', 'community_validation', 'published', 'archived']
ACTIVITY_KINDS = ['report', 'followup', 'sensitisation', 'referral', 'training', 'supervision']
JOB_AID_TOPICS = ['idsr_case_definition', 'ppe_donning', 'ppe_doffing', 'isolation_basics', 'safe_burial', 'reporting_flow']
CHW_TASK_KINDS = ['followup', 'referral', 'sensitisation']

# slug -> spec feature id. Internal traceability only; never serialised (see module docstring).
FEATURE_OF: dict[str, str] = {
	'febrile_triage': 'TRI-001', 'evd_triage': 'TRI-003', 'differential': 'TRI-001',
	'diary_trend': 'TRI-002', 'diary_export': 'TRI-002', 'diary_prompt': 'TRI-002',
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
	'missed_doses': 'MON-001', 'vaccination_campaigns': 'MON-001',
	'add_medication': 'MON-004', 'log_adherence': 'MON-004',
	'peak_flow': 'MON-003', 'log_weight': 'MON-003', 'condition_profile': 'MON-003', 'clinical_report': 'MON-003',
	# §MON-003's three conditions with no reading behind them, and its three missing features. The
	# actions carry no feature code in their titles — the ids above are internal, and a person reads
	# "My kidney results", not "MON-003".
	'kidney_result': 'MON-003', 'seizure_log': 'MON-003', 'sickle_crisis': 'MON-003',
	'trend_chart': 'MON-003', 'appointments': 'MON-003', 'lifestyle_guidance': 'MON-003',
	'vector_risk': 'MON-007', 'breeding_site': 'MON-007', 'larviciding': 'MON-007',
	'issue_larviciding': 'MON-007', 'protection_reminder': 'MON-007',
	'food_alert': 'MON-008', 'food_alerts': 'MON-008', 'nutrition': 'MON-008',
	'therapeutic_feeding': 'MON-008',
	'enrol_monitoring': 'MON-009', 'monitoring_day': 'MON-009', 'monitoring_diary': 'MON-009',
	'monitoring_reminders': 'MON-009', 'monitoring_consent': 'MON-009', 'monitoring_members': 'MON-009',
	'monitoring_member_diary': 'MON-009', 'monitoring_officer': 'MON-009',
	'issue_alert': 'INF-014', 'alerts_by_county': 'INF-014',
	'water_advisory': 'INF-011', 'air_advisory': 'INF-012', 'flood_risk': 'INF-013',
	'file_price': 'INF-016', 'price_quote': 'INF-016', 'sha_cover_check': 'INF-016',
	'assign_chw_task': 'CHAN-005', 'chw_open_tasks': 'CHAN-005', 'complete_chw_task': 'CHAN-005',
	'send_sms': 'CHAN-001', 'whatsapp_send': 'CHAN-003', 'ussd_menu': 'CHAN-002',
	'channel_costs': 'CHAN-001',
	'queue_sync_op': 'CHAN-006', 'flush_sync': 'CHAN-006', 'offline_state': 'ACC-003',
	'record_consent': 'SEC-001', 'dpia_check': 'SEC-001',
	'sensor_ingest': 'SENS-005', 'analyse_cough': 'SENS-002', 'submit_evidence': 'SENS-004',
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
	'enable_location_history': 'LOC-003', 'log_location': 'LOC-003', 'location_report': 'LOC-003', 'purge_location': 'LOC-003',
	'register_checkin_point': 'LOC-004', 'check_in': 'LOC-004', 'checkin_points': 'LOC-004', 'checkin_list': 'LOC-004',
	'register_border': 'LOC-005', 'border_status': 'LOC-005', 'travel_advisory': 'INF-005', 'traveller_declare': 'LOC-005',
	'traveller_prompt': 'LOC-005', 'traveller_report': 'LOC-005',
	'hotspots': 'AI-001', 'risk_score': 'AI-002', 'early_warning': 'AI-003',
	'signal_scan': 'AI-003', 'signal_report': 'AI-003',
	'model_cards': 'AI-004', 'fairness_audit': 'AI-004', 'file_redress': 'AI-005',
	'access_profile': 'ACC-001', 'ui_screens': 'ACC-001', 'languages': 'ACC-002', 'voice': 'ACC-002',
	'voice_audio': 'ACC-002', 'whatsapp_voice': 'ACC-002',
	'battery_profile': 'ACC-004', 'compatibility': 'ACC-005', 'sensor_capabilities': 'ACC-005',
	'retention_policy': 'SEC-005', 'record_holding': 'SEC-006', 'record_share': 'SEC-006',
	'data_inventory': 'SEC-006', 'export_my_data': 'SEC-005', 'delete_my_data': 'SEC-005', 'purge_expired': 'SEC-005',
	'encryption_posture': 'SEC-003', 'transparency_report': 'SEC-006',
	'provision_chw': 'CHAN-005', 'chw_profile': 'CHAN-005', 'chw_training': 'CHAN-005', 'job_aid': 'COM-101',
	'chw_cases': 'COM-101', 'assign_chw_case': 'COM-101', 'log_chw_activity': 'COM-101', 'chw_activity': 'COM-101',
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
	'chw_profile': 'assigned', 'log_chw_activity': 'assigned', 'submit_case': 'assigned',
	'advance_case': 'assigned', 'peer_alert': 'assigned', 'send_exposure_notice': 'assigned',
	# §10.1's provider-side view. §17.4's clinician row is "Patients who have consented to share",
	# and the scope that carries it is `consented_patient` — a clinician reading a record through a
	# share the patient issued. It is an operator action for that reason: a citizen's catalogue must
	# not carry a screen that reads *another person's* record, which is what this is by construction.
	'provider_view': 'consented_patient',
	# County-level analysis and the provisioning of workers.
	'early_warning': 'county_aggregate', 'hotspots': 'county_aggregate',
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
	'enable_location_history', 'log_location', 'location_report', 'purge_location',
	'register_checkin_point', 'check_in', 'checkin_points', 'checkin_list',
	'register_border', 'border_status', 'traveller_declare', 'traveller_prompt', 'traveller_report',
	# Outbreak AI (AI-001..003)
	'hotspots', 'risk_score', 'early_warning', 'signal_scan', 'signal_report',
	# Outbreak-mode sensors: acoustic cough (SENS-002), camera symptom capture (SENS-004)
	'analyse_cough', 'submit_evidence',
})


def tier4_feature_ids() -> frozenset[str]:
	"""Feature ids the §7.3 tier model puts at Tier 4, read from the registry.

	Deriving this rather than restating it is what keeps the catalogue honest: the dormancy list
	is prose a person maintains, this is the model, and `available()` obeys both.
	"""
	from afya.registry.service import FeatureRegistry, Tier
	return frozenset(f.id for f in FeatureRegistry().by_tier(Tier.tier4))


def _f(name: str, label: str, type_: str = 'text', options: list[str] | None = None, ph: str | None = None, client_supplied: bool = False, server_assigned: bool = False) -> MobileField:
	return MobileField(name=name, label=label, type=cast(FieldType, type_), options=options, placeholder=ph, required=type_ == 'path', client_supplied=client_supplied, server_assigned=server_assigned)


def _auto(name: str, label: str) -> MobileField:
	"""A reference the server mints. Carried so a client can send one, marked so no form asks for it.

	The model gives it a `default_factory`, so a request that omits it is complete; the field is in
	the catalogue because an offline client wants to mint its own and have the replay keep the same
	reference. A form that drew it would be asking a person to invent a primary key.
	"""
	return _f(name, label, server_assigned=True)


def _s(type_: str = 'text') -> MobileField:
	"""The caller's own subject: carried so the client can send it, marked so no form draws it.

	Every route that carries one binds it to the token (§17), so a person typing a different subject
	would be offered a control the server refuses. The label is never shown.
	"""
	return _f('subject_ref', 'Me', type_, client_supplied=True)


def _a(id: str, title: str, group: str, method: str, path: str, fields: list[MobileField]) -> MobileAction:
	assert method in ('GET', 'POST', 'DELETE') and all(fl.type in FIELD_TYPES for fl in fields), 'contract'
	assert id in FEATURE_OF, f'action {id} must declare its source feature in FEATURE_OF'
	return MobileAction(id=id, title=title, group=group, method=method, path=path, fields=fields)


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
			_f('walk_in_only', 'Walk-in only', 'bool', ph='yes if you cannot book ahead')]),
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
		_a('publish_content', 'Draft health information', 'Information', 'POST', '/info/content', [_f('item_id', 'Reference'), _f('title', 'Title'), _f('body', 'Text', 'textarea'), _f('lang', 'Language', 'select', ['en', 'sw', 'sheng']), _f('harmony_tag', 'Official source tag'), _f('slug', 'Short name'), _f('owner', 'Who owns this'), _f('reviewer', 'Who reviewed it'), _f('reviewed_on_iso', 'Review date', ph='YYYY-MM-DD'), _f('version', 'Version', 'int'), _f('stage', 'Stage', 'select', CONTENT_STAGES)]),
		_a('advance_content', 'Move a draft forward', 'Information', 'POST', '/info/content/{item_id}/advance', [_f('item_id', 'Reference', 'path'), _f('to', 'Next stage', 'select', CONTENT_STAGES)]),
		_a('content_governance', 'Who reviewed this?', 'Information', 'GET', '/info/content/governance', [_f('today_iso', 'As at', ph='YYYY-MM-DD'), _f('regime', 'Review cycle', 'select', ['steady', 'outbreak'])]),
		_a('report_content_error', 'Report a wrong guidance item', 'Information', 'POST', '/info/content/errors', [_f('error_id', 'Reference'), _f('item_id', 'Item reference'), _f('found_by', 'Found by'), _f('what_is_wrong', 'What is wrong', 'textarea'), _f('correction_en', 'Correction (English)', 'textarea'), _f('correction_sw', 'Correction (Kiswahili)', 'textarea'), _f('replacement_slug', 'Replacement short name')]),
		_a('content_errors', 'What guidance was found wrong?', 'Information', 'GET', '/info/content/errors', []),
		_a('record_back_translation', 'Record a back-translation', 'Information', 'POST', '/info/content/back-translation', [_f('item_id', 'Translation reference'), _f('translated_by', 'Translated by'), _f('back_translated_by', 'Rendered back by'), _f('back_translation', 'Text rendered back into English', 'textarea')]),
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
			 _f('conditions', 'Ongoing conditions', 'select',
			    options=[label for _slug, label in contraindications.CONDITION_AXES])]),
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
		_a('report_suspicious_medicine', 'Report a fake medicine', 'Medicine', 'POST', '/medicine/suspicious', [_f('gtin', 'Barcode number', ph='optional if you have the batch'), _f('batch_number', 'Batch number', ph='optional if you have the barcode'), _f('note', 'What is wrong?', 'textarea'), _f('photo_sha256', 'Photo', 'file', ph='optional')]),
		# Emergency
		# §EMG-001's fan-out: where the person is, how serious, who to tell and what to attach.
		# `contacts` is the section's "up to three emergency contacts" and the model caps it at
		# three, so a fourth is refused rather than silently dropped — a dropped contact is a person
		# who was never told. `channel` is the client's own answer to whether it has data, which is
		# the half of the section's SMS claim only the client can know.
		_a('sos', 'Get help now', 'Emergency', 'POST', '/emergency/sos', [_auto('sos_id', 'Alert number'), _f('lat', 'Latitude', 'decimal'), _f('lon', 'Longitude', 'decimal'), _f('severity', 'How serious?', 'select', ['low', 'medium', 'high']), _f('symptoms', 'Symptoms', 'list'), _f('contacts', 'Who to alert', 'list', ph='name:number, name:number (up to three)'), _f('channel', 'How you are sending this', 'select', ['native', 'sms']), _f('blood_group', 'Blood group', 'select', BLOOD_GROUPS, ph='optional'), _f('allergies', 'Allergies', 'list', ph='optional'), _f('conditions', 'Ongoing conditions', 'list', ph='optional'), _f('medications', 'Medicines', 'list', ph='optional')]),
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
		_a('growth_flag', 'Is my child growing well?', 'Records', 'POST', '/records/growth', [_f('member_ref', 'Family member'), _f('age_months', 'Age in months', 'int'), _f('weight_kg', 'Weight in kg', 'decimal'), _f('height_cm', 'Height in cm', 'decimal'), _f('sex', 'Boy or girl?', 'select', ['boy', 'girl']), _f('head_circumference_cm', 'Head size in cm', 'decimal', ph='optional'), _f('muac_mm', 'Mid-upper arm in mm', 'decimal', ph='optional')]),
		# §REC-003's milestone checklist, in Annex 9's two halves: read the list, then report it.
		_a('milestone_checklist', 'What should my child be doing?', 'Records', 'GET', '/records/{member_ref}/milestones', [_f('member_ref', 'Family member', 'path'), _f('age_months', 'Age in months', 'int')]),
		_a('milestone_check', 'Milestones my child has reached', 'Records', 'POST', '/records/milestones', [_f('member_ref', 'Family member'), _f('age_months', 'Age in months', 'int'), _f('present', 'Skills the child can do', 'list', ph='from the checklist'), _f('lost', 'Skills the child has stopped doing', 'list', ph='leave empty if none'), _f('checked_earlier', 'Were the earlier age groups also checked?', 'bool', ph='only if you asked about them')]),
		_a('add_lab', 'Add a lab result', 'Records', 'POST', '/records/labs', [_f('member_ref', 'Family member'), _f('test', 'Test', 'select', ['mRDT', 'widal', 'hba1c', 'fbc', 'viral_load', 'glucose_f', 'bp', 'other']), _f('value', 'Result'), _f('unit', 'Unit', ph='optional'), _f('flag', 'Is it normal?', 'select', ['normal', 'abnormal', 'critical', 'unknown']), _f('performed_iso', 'Date of test')]),
		_a('view_labs', 'My lab results', 'Records', 'GET', '/records/{ref}/labs', [_f('ref', 'Family member', 'path')]),
		# §9.2 REC-001 and §10.1 REC-002: the wallet's documents, and the operations over them.
		_a('wallet_documents', 'Everything in the wallet', 'Records', 'GET', '/records/{member_ref}/documents', [_f('member_ref', 'Family member', 'path'), _f('kind', 'Type of document', 'select', list(WALLET_DOC_KINDS))]),
		_a('file_document', 'Add a document', 'Records', 'POST', '/records/documents', [_auto('doc_id', 'Reference'), _f('member_ref', 'Family member'), _f('kind', 'Type of document', 'select', list(WALLET_DOC_KINDS)), _f('title', 'What is it?'), _f('occurred_iso', 'Date on the document'), _f('detail', 'What does it say?', 'textarea'), _f('facility_id', 'Facility', ph='optional'), _f('media_ref', 'Photo reference', ph='from the camera upload'), _f('captured_iso', 'When the photo was taken')]),
		_a('health_timeline', 'My health history', 'Records', 'GET', '/records/timeline', []),
		_a('wallet_search', 'Find a document', 'Records', 'GET', '/records/search', [_f('q', 'What are you looking for?')]),
		_a('share_record', 'Share my record', 'Records', 'POST', '/records/share', [_auto('grant_id', 'Share reference'), _f('member_ref', 'Family member'), _f('recipient', 'Who is it for?', ph='leave blank for a link'), _f('kinds', 'What they can see', 'list', list(WALLET_DOC_KINDS)), _f('issued_iso', 'From'), _f('expires_iso', 'Until')]),
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
		_a('outbreak_support', 'Support during the outbreak', 'Wellbeing', 'GET', '/mental/outbreak-support/{condition}', [_f('condition', 'What is happening?', 'path', options=['isolation_distress', 'grief', 'worker_burnout']), _f('lang', 'Language', 'select', ['en', 'sw'])]),
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
		_a('lifestyle_guidance', 'What should I eat and avoid?', 'Daily care', 'GET', '/chronic/lifestyle', [_f('condition', 'Which condition?', 'select', ['hypertension', 'diabetes', 'asthma', 'epilepsy', 'sickle_cell', 'hiv', 'chronic_kidney'])]),
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
		_a('maternity_facilities', 'Where can I deliver?', 'Maternity', 'GET', '/maternal/facilities', [_f('lat', 'My latitude', 'decimal'), _f('lon', 'My longitude', 'decimal'), _f('limit', 'How many to show', 'int'), _f('accepts_sha', 'Only places that take SHA', 'bool', ph='optional')]),
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
		_a('water_advisory', 'Is the water safe?', 'Environment', 'POST', '/environment/water', [_f('county', 'County'), _f('ecoli_detected', 'E. coli detected?', 'bool'), _f('turbidity_ntu', 'Turbidity NTU', 'decimal'), _f('treated_at_iso', 'When you last treated water', ph='YYYY-MM-DDTHH:MM+03:00')]),
		_a('air_advisory', 'How is the air?', 'Environment', 'POST', '/environment/air', [_f('county', 'County'), _f('location', 'Where you are'), _f('pm25', 'PM2.5 µg/m³', 'decimal'), _f('hourly', 'Today\'s hourly readings', 'list', ph='6=18, 12=34, 18=52')]),
		_a('flood_risk', 'Flood and cholera risk', 'Environment', 'POST', '/environment/flood', [_f('county', 'County'), _f('rainfall_mm_72h', 'Rainfall mm in 3 days', 'decimal'), _f('population_at_risk', 'People at risk', 'int')]),
		# Alerts
		_a('issue_alert', 'Send a public alert', 'Alerts', 'POST', '/alerts', [_auto('alert_id', 'Alert number'), _f('kind', 'Kind', 'select', ALERT_KINDS), _f('county', 'County'), _f('headline', 'Headline'), _f('body', 'Message', 'textarea'), _f('issued_by', 'Issued by', 'select', ['PHEOC', 'MoH', 'County', 'KMD'])]),
		_a('alerts_by_county', 'Alerts for my county', 'Alerts', 'GET', '/alerts/{county}', [_f('county', 'County', 'path')]),
		_a('publish_feed_item', 'Publish a verified alert', 'Alerts', 'POST', '/alerting/feed', [_f('item_id', 'Item number'), _f('category', 'Category', 'select', ['outbreak', 'weather', 'flood', 'fire', 'road', 'security', 'drug_recall', 'water', 'food_recall', 'service']), _f('headline', 'Headline'), _f('body', 'Message', 'textarea'), _f('source', 'Source'), _f('verified', 'Verified?', 'bool'), _f('published_iso', 'Published on'), _f('county', 'County', ph='optional')]),
		_a('alert_feed', 'Alerts near me', 'Alerts', 'GET', '/alerting/feed', [_f('county', 'County', ph='optional')]),
		_a('set_alert_preference', 'Choose which alerts I get', 'Alerts', 'POST', '/alerting/preferences', [_s(), _f('category', 'Alert type'), _f('enabled', 'Turn on?', 'bool')]),
		_a('alert_preferences', 'My alert settings', 'Alerts', 'GET', '/alerting/preferences/{subject_ref}', [_s('path')]),
		_a('link_family', 'Link my family', 'Alerts', 'POST', '/alerting/family/link', [_f('family_ref', 'Family group'), _f('members', 'Family members', 'list')]),
		_a('family_check_in', "I'm safe", 'Alerts', 'POST', '/alerting/family/check-in', [_s(), _f('family_ref', 'Family group'), _f('at_iso', 'When', ph='optional'), _f('channel', 'How did you check in?', 'select', ['native', 'sms'], ph='optional'), _f('note', 'Anything to add?', ph='optional')]),
		_a('my_checkins', 'My safety check-ins', 'Alerts', 'GET', '/alerting/family/check-ins/{subject_ref}', [_s('path')]),
		_a('family_board', 'Is my family safe?', 'Alerts', 'GET', '/alerting/family/{family_ref}', [_f('family_ref', 'Family group', 'path')]),
		# Community
		_a('report_issue', 'Report a problem in my area', 'Community', 'POST', '/community/issues', [_auto('issue_id', 'Report number'), _f('kind', 'What is the problem?', 'select', ISSUE_KINDS), _f('county', 'County'), _f('description', 'Describe it', 'textarea'), _f('lat', 'Latitude', 'decimal'), _f('lon', 'Longitude', 'decimal')]),
		_a('issues_by_county', 'Problems reported near me', 'Community', 'GET', '/community/issues/{county}', [_f('county', 'County', 'path')]),
		_a('resolve_issue', 'Mark a problem as fixed', 'Community', 'POST', '/community/issues/{issue_id}/resolve', [_f('issue_id', 'Report number', 'path')]),
		_a('submit_case', 'Report a suspected case', 'Community', 'POST', '/community/cases', [_auto('report_id', 'Report number'), _f('chw_ref', 'Health worker'), _f('county', 'County'), _f('community', 'Village or estate'), _f('symptoms', 'Symptoms', 'list'), _f('age_years', 'Age in years', 'int'), _f('sex', 'Sex', 'select', ['male', 'female', 'other']), _f('temperature_c', 'Temperature °C', 'decimal'), _f('exposure_history', 'Who has the patient been near?', 'textarea'), _f('geotagged', 'Attach location?', 'bool'), _f('suspected_disease', 'What do you suspect?', 'select', VECTOR_DISEASES), _f('reported_offline', 'Reported without network?', 'bool')]),
		_a('advance_case', 'Update a case', 'Community', 'POST', '/community/cases/{report_id}/advance', [_f('report_id', 'Report number', 'path'), _f('status', 'New status', 'select', CASE_STATUSES)]),
		_a('ppe_reminder', 'Protective equipment reminder', 'Community', 'GET', '/community/ppe-reminder', []),
		_a('peer_alert', 'Warn people nearby', 'Community', 'POST', '/community/peer-alert', [_f('alert_id', 'Alert number'), _f('county', 'County'), _f('lat', 'Latitude', 'decimal'), _f('lon', 'Longitude', 'decimal'), _f('radius_m', 'How far? (metres)', 'select', [str(r) for r in ALERT_ZONE_RADII_M]), _f('headline', 'Headline'), _f('location', 'Which place should people avoid?'), _f('issued_iso', 'Issued on', ph='YYYY-MM-DD'), _f('verified_by', 'Verified by', 'select', ['County', 'PHEOC', 'MoH'])]),
		_a('peer_alert_followup', 'Follow-up prompt for one day', 'Community', 'GET', '/community/peer-alert/{alert_id}/followup/{day}', [_f('alert_id', 'Alert number', 'path'), _f('day', 'Day of the window (' + ', '.join(str(d) for d in FOLLOWUP_DAYS) + ')', 'path')]),
		_a('tracing_prompts', 'Help me remember who I met', 'Community', 'GET', '/community/tracing-prompts', []),
		_a('save_contacts', 'Save my contact list', 'Community', 'POST', '/community/contacts', [_s(), _f('entries', 'People', 'list'), _f('share_consent', 'Share with the health team?', 'bool')]),
		_a('add_contact', 'Add one person I met', 'Community', 'POST', '/community/contacts/{subject_ref}/entry', [_s('path'), _f('description', 'Who was it?'), _f('setting', 'Where?', 'select', CONTACT_SETTINGS), _f('approx_location', 'Roughly where?'), _f('name_unknown', "I don't know their name", 'bool')]),
		_a('share_contacts', 'Share my contact list with the health team', 'Community', 'POST', '/community/contacts/{subject_ref}/share', [_s('path'), _f('with_who', 'Who should get it?', ph='optional')]),
		_a('contact_shares', 'What I have shared', 'Community', 'GET', '/community/contacts/{subject_ref}/shares', [_s('path')]),
		_a('withdraw_contact_shares', 'Take my contact list back', 'Community', 'DELETE', '/community/contacts/{subject_ref}/shares', [_s('path')]),
		_a('flag_misinformation', 'Report something I heard', 'Community', 'POST', '/community/misinformation', [_auto('submission_id', 'Report number'), _f('claim', 'What did you hear?', 'textarea'), _f('county', 'County'), _f('medium', 'How did you get it?', 'select', MISINFO_MEDIA), _f('topic', 'Topic', ph='optional'), _f('evidence_ref', 'The recording or picture', 'file', ph='voice note or screenshot'), _f('transcript', 'What the voice note said', 'textarea', ph='type it if you have no recording'), _f('evidence_consent', 'Share the recording or picture with the health team', 'bool'), _f('flagger_ref', 'Tell me when this is answered', ph='your number or reference')]),
		_a('misinformation_clusters', 'Rumours going around', 'Community', 'GET', '/community/misinformation/clusters', []),
		_a('misinformation_notices', 'Answers to what I reported', 'Community', 'GET', '/community/misinformation/notices/{subject_ref}', [_s('path')]),
		# Outbreak mode
		_a('enrol_monitoring', 'Start my 21-day check-in', 'Outbreak', 'POST', '/monitoring/contact/enrol', [_s(), _f('officer', 'Monitoring officer', ph='optional'), _f('officer_number', 'Their phone number', ph='optional')]),
		_a('monitoring_day', 'Log today (21-day check-in)', 'Outbreak', 'POST', '/monitoring/contact/day', [_auto('entry_id', 'Entry number'), _s(), _f('day', 'Day (1-21)', 'int'), _f('temperature_c', 'Temperature °C', 'decimal'), _f('symptoms', 'Symptoms', 'list'), _f('household_member', 'Family member', ph='optional'), _f('slot', 'Morning or evening', 'select', ['morning', 'evening']), _f('location_logged', 'Share where I am today', 'bool')]),
		_a('monitoring_diary', 'My 21-day diary', 'Outbreak', 'GET', '/monitoring/contact/{subject_ref}/diary', [_s('path')]),
		_a('monitoring_reminders', 'What is still to log today', 'Outbreak', 'GET', '/monitoring/contact/{subject_ref}/reminders/{day}', [_s('path'), _f('day', 'Day (1-21)', 'path')]),
		_a('monitoring_consent', 'Share my location while I am monitored', 'Outbreak', 'POST', '/monitoring/contact/{subject_ref}/location-consent', [_s('path'), _f('granted', 'Yes, share it', 'bool'), _f('at_iso', 'When')]),
		_a('monitoring_members', 'Add someone I live with', 'Outbreak', 'POST', '/monitoring/contact/{subject_ref}/members', [_s('path'), _f('member_ref', 'Who they are to you', ph='e.g. my son')]),
		_a('monitoring_member_diary', 'Their readings', 'Outbreak', 'GET', '/monitoring/contact/{subject_ref}/members/{member_ref}/diary', [_s('path'), _f('member_ref', 'Family member', 'path')]),
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
		_a('location_report', 'Where I have been', 'Outbreak', 'GET', '/location/history/{subject_ref}/report', [_s('path'), _f('share', 'Share with the health team?', 'bool')]),
		_a('purge_location', 'Delete my location diary', 'Outbreak', 'DELETE', '/location/history/{subject_ref}', [_s('path')]),
		_a('checkin_points', 'Check-in points near me', 'Outbreak', 'GET', '/location/checkin/points', [_f('county', 'County', ph='optional')]),
		_a('checkin_list', 'Where I checked in', 'Outbreak', 'GET', '/location/checkin/{subject_ref}', [_s('path')]),
		_a('register_checkin_point', 'Set up a check-in point', 'Outbreak', 'POST', '/location/checkin/point', [_f('point_id', 'Point number'), _f('kind', 'What kind of place?', 'select', CHECKIN_KINDS), _f('label', 'Name'), _f('county', 'County'), _f('token', 'Check-in code')]),
		_a('check_in', 'Check in here', 'Outbreak', 'POST', '/location/checkin', [_f('checkin_id', 'Check-in number'), _f('point_token', 'Check-in code'), _s(), _f('method', 'How?', 'select', CHECKIN_METHODS), _f('at_iso', 'When'), _f('share_with_authority', 'Share with the health team?', 'bool')]),
		_a('register_border', 'Set up a border post', 'Outbreak', 'POST', '/location/border', [_f('post_id', 'Post number'), _f('name', 'Name'), _f('county', 'County'), _f('country_pair', 'Between which countries?'), _f('queue_minutes', 'Queue in minutes', 'int'), _f('screening_required', 'Screening required?', 'bool'), _f('mobile_lab', 'Is there a mobile lab here?', 'bool'), _f('lab_turnaround_hours', 'Results in how many hours?', 'int'), _f('lab_tests', 'Which tests can it run?', 'list', ph='e.g. mRDT, Ebola PCR')]),
		_a('border_status', 'Border queue', 'Outbreak', 'GET', '/location/border/{post_id}', [_f('post_id', 'Post number', 'path')]),
		_a('travel_advisory', 'Should I travel?', 'Outbreak', 'GET', '/location/travel-advisory', [_f('destination', 'Where to?'), _f('origin_country', 'Coming from'), _f('lang', 'Which language?', 'select', TRAVELLER_LANGS)]),
		_a('traveller_declare', 'Declare my arrival', 'Outbreak', 'POST', '/location/traveller/declare', [_f('declaration_id', 'Declaration number'), _s(), _f('destination', 'Where are you going?'), _f('arrival_iso', 'Arrival date'), _f('origin_country', 'Coming from'), _f('symptoms', 'Any symptoms?', 'list'), _f('lang', 'Which language?', 'select', TRAVELLER_LANGS)]),
		_a('traveller_prompt', 'What am I asked today?', 'Outbreak', 'GET', '/location/traveller/{subject_ref}/prompt', [_s('path'), _f('day', 'Which day of the 21?', 'int')]),
		_a('traveller_report', 'Report how I feel today', 'Outbreak', 'POST', '/location/traveller/report', [_s(), _f('day', 'Which day of the 21?', 'int'), _f('symptoms', 'Any symptoms?', 'list'), _f('temperature_c', 'Temperature °C', 'decimal')]),
		_a('hotspots', 'Where might cases appear next?', 'Outbreak', 'POST', '/ai/hotspots', [_f('cells', 'Area data', 'list')]),
		_a('risk_score', 'What is my personal risk?', 'Outbreak', 'POST', '/ai/risk-score', [_f('symptoms', 'Symptoms', 'list'), _f('exposure_contact', 'Contact with a case?', 'bool'), _f('travel_affected_area', 'Travelled to an affected area?', 'bool'), _f('geofence_entry', 'Entered a risk area?', 'bool'), _f('proximity_encounters', 'Nearby encounters', 'int'), _f('vaccinated', 'Vaccinated?', 'bool')]),
		_a('early_warning', 'Is something unusual happening?', 'Outbreak', 'POST', '/ai/early-warning', [_f('county', 'County'), _f('disease', 'Disease'), _f('signals', 'Signals', 'list')]),
		_a('signal_scan', 'How is my county this week?', 'Outbreak', 'GET', '/ai/early-warning/{county}/scan', [_f('county', 'County', 'path'), _f('disease', 'Disease'), _f('week_isoyear', 'Year', 'int'), _f('week', 'Week number', 'int'), _f('baseline_weeks', 'Weeks to compare against', 'int')]),
		# The six option values are §11.7's own signal names — the strings the API accepts, like the
		# `under_5` age band and the `low` risk level elsewhere in this file. They are not spec feature
		# codes: `fever_triage` is a value the caller sends, and the label beside it is what a person
		# reads.
		_a('signal_report', 'Report a signal', 'Outbreak', 'POST', '/ai/signals', [_f('county', 'County'), _f('at_iso', 'When'), _f('signal', 'What happened', 'select', ['fever_triage', 'cough_events', 'facility_search', 'medicine_search', 'unwell_checkin', 'encounter_density']), _f('ref', 'Reference')]),
		# §17.3: the privacy-review key is not a field the caller sends any more — it is held by a
		# recorded review, so the form offers the processing to assess and nothing to assert.
		_a('activate_outbreak_mode', 'Activate outbreak mode', 'Outbreak', 'POST', '/tier4/activate', [_f('authorized_by_pheoc', 'PHEOC authorised?', 'bool'), _f('flag_enabled', 'Switch on?', 'bool'), _f('raw_sensor_data_retained', 'Keeping raw sensor data?', 'bool'), _f('location_tracking', 'Tracking location?', 'bool'), _f('proximity_logging', 'Proximity logging?', 'bool'), _f('contact_tracing', 'Contact tracing?', 'bool'), _f('automated_decisions', 'Automatic decisions?', 'bool'), _f('data_sharing_with_authorities', 'Sharing with health authorities?', 'bool'), _f('children_data', "Children's data?", 'bool'), _f('cross_border_transfer', 'Data leaving the country?', 'bool')]),
		# Privacy & transparency
		_a('record_consent', 'Record my consent', 'Privacy', 'POST', '/privacy/consent', [_s(), _f('purpose', 'What for?'), _f('data_types', 'Which data?', 'list'), _f('retention_days', 'Keep for how many days', 'int'), _f('legal_basis', 'Why are we allowed to?', 'select', ['consent', 'legal_obligation', 'legitimate_interest'])]),
		_a('dpia_check', 'Check a new data use', 'Privacy', 'POST', '/privacy/dpia', [_f('raw_sensor_data_retained', 'Keeping raw sensor data?', 'bool'), _f('location_tracking', 'Tracking location?', 'bool'), _f('proximity_logging', 'Proximity logging?', 'bool'), _f('contact_tracing', 'Contact tracing?', 'bool'), _f('automated_decisions', 'Automatic decisions?', 'bool'), _f('data_sharing_with_authorities', 'Sharing with health authorities?', 'bool'), _f('children_data', "Children's data?", 'bool'), _f('cross_border_transfer', 'Data leaving the country?', 'bool')]),
		_a('retention_policy', 'How long is data kept?', 'Privacy', 'GET', '/retention/policy', []),
		_a('data_inventory', 'What do you know about me?', 'Privacy', 'GET', '/retention/inventory/{subject_ref}', [_s('path')]),
		_a('export_my_data', 'Download my data', 'Privacy', 'GET', '/retention/export/{subject_ref}', [_s('path'), _f('at_iso', 'When'), _f('channel', 'How?', 'select', ['native', 'sms', 'ussd', 'whatsapp'])]),
		_a('delete_my_data', 'Delete my data', 'Privacy', 'POST', '/retention/delete', [_s(), _f('data_type', 'Only this type', ph='leave blank for everything'), _f('channel', 'How?', 'select', ['native', 'sms', 'ussd', 'whatsapp'])]),
		_a('purge_expired', 'Clear what has expired', 'Privacy', 'POST', '/retention/purge-expired', [_s(), _f('age_days', 'How old each record is, by type', 'text')]),
		_a('encryption_posture', 'How is my data protected?', 'Privacy', 'GET', '/retention/encryption', []),
		_a('transparency_report', 'Transparency report', 'Privacy', 'GET', '/retention/transparency', [_f('period', 'Period'), _f('subject_ref', 'Person the report is about', ph='optional')]),
		_a('record_holding', 'Record what is stored', 'Privacy', 'POST', '/retention/holding', [_s(), _f('data_type', 'Data type'), _f('count', 'How many records', 'int')]),
		_a('record_share', 'Record a data share', 'Privacy', 'POST', '/retention/share', [_s(), _f('with_who', 'Shared with'), _f('what', 'What was shared'), _f('when_iso', 'When')]),
		# Access & fairness
		_a('access_profile', 'Make the app easier to use', 'Access', 'POST', '/access/profile', [_s(), _f('simple_mode', 'Simple mode', 'bool'), _f('large_text', 'Large text', 'bool'), _f('high_contrast', 'High contrast', 'bool'), _f('read_aloud', 'Read screens aloud', 'bool'), _f('voice_input', 'Speak instead of typing', 'bool'), _f('lang', 'Language')]),
		_a('ui_screens', 'Screen list', 'Access', 'GET', '/access/screens', [_f('simple_mode', 'Simple mode', 'bool')]),
		_a('languages', 'Languages', 'Access', 'GET', '/access/languages', [_f('tier', 'Priority tier', 'int')]),
		_a('voice', 'Speak to the app', 'Access', 'POST', '/access/voice', [_s(), _f('lang', 'Language'), _f('utterance', 'What you said'), _f('purpose', 'Symptoms or a note?', 'select', VOICE_PURPOSES), _f('offline', 'No network?', 'bool')]),
		_a('voice_audio', 'Send a recording', 'Access', 'POST', '/access/voice/audio', [_s(), _f('lang', 'Language', 'select', VOICE_LANGS), _f('purpose', 'Symptoms or a note?', 'select', VOICE_PURPOSES), _f('file', 'Recording', 'file')]),
		_a('battery_profile', 'Battery use', 'Access', 'GET', '/access/battery', [_s(), _f('intensity', 'Monitoring level', 'select', INTENSITIES), _f('battery_saver', 'Battery saver', 'bool')]),
		_a('compatibility', 'Will it work on my phone?', 'Access', 'GET', '/access/compatibility/{platform}', [_f('platform', 'Phone type', 'path')]),
		_a('sensor_capabilities', 'What my phone can measure', 'Access', 'GET', '/sensors/capabilities', []),
		_a('model_cards', 'How the AI works', 'Access', 'GET', '/ai/models', []),
		_a('fairness_audit', 'Check an AI model is fair', 'Access', 'POST', '/ai/fairness-audit', [_f('model_id', 'Model'), _f('axes', 'Axes tested', 'list'), _f('unmet_axes', 'Failures found', 'list')]),
		_a('file_redress', 'Challenge a decision', 'Access', 'POST', '/ai/redress', [_f('request_id', 'Request number'), _s(), _f('output_kind', 'What are you challenging?', 'select', OUTPUT_KINDS), _f('output_ref', 'Which result?'), _f('challenge', 'Why do you disagree?', 'textarea')]),
		# Health workers
		_a('provision_chw', 'Register a health worker', 'Health workers', 'POST', '/chw/provision', [_f('chw_ref', 'Health worker'), _f('name', 'Full name'), _f('county', 'County'), _f('community', 'Village or estate'), _f('registry_verified', 'Verified on the national register?', 'bool'), _f('provisioned_by', 'Registered by', 'select', ['County', 'MoH'])]),
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
		_a('complete_chw_task', 'Complete a task', 'Channels', 'POST', '/channels/chw/tasks/{task_id}/done', [_f('task_id', 'Task number', 'path')]),
		_a('send_sms', 'Send a free text message', 'Channels', 'POST', '/channels/sms', [_f('to_msisdn', 'Phone number'), _f('body', 'Message')]),
		_a('channel_costs', 'Will this cost me airtime?', 'Channels', 'GET', '/channels/cost', []),
		_a('ussd_menu', 'USSD menu', 'Channels', 'POST', '/channels/ussd', [_f('session_id', 'Session'), _f('msisdn', 'Phone number'), _f('text', 'Selection')]),
		_a('whatsapp_send', 'WhatsApp reply', 'Channels', 'POST', '/channels/whatsapp', [_f('from_msisdn', 'Phone number'), _f('body', 'Message')]),
		_a('whatsapp_voice', 'Send a WhatsApp voice note', 'Channels', 'POST', '/channels/whatsapp/voice', [_f('from_msisdn', 'Phone number'), _f('voice_note_lang', 'Language', 'select', VOICE_LANGS), _f('file', 'Voice note', 'file')]),
		_a('queue_sync_op', 'Save for later (offline)', 'Sync', 'POST', '/sync/ops', [_f('op_id', 'Change number'), _f('dataset', 'What kind of change?', 'select', SYNC_DATASETS), _f('client_ts', 'When it happened', 'int')]),
		_a('flush_sync', 'Send everything now', 'Sync', 'POST', '/sync/flush', [_f('connection', 'Connection', 'select', ['wifi', 'metered', 'offline'], ph='wifi')]),
		_a('offline_state', 'Is my work saved?', 'Sync', 'GET', '/sync/state', []),
		_a('sensor_ingest', 'Save a reading', 'Sensors', 'POST', '/sensors/ingest', [_f('kind', 'Reading type', 'select', SENS_KINDS), _s(), _f('value', 'Value', 'decimal'), _f('county', 'County')]),
		_a('analyse_cough', 'Check a cough recording', 'Sensors', 'POST', '/ml/cough/analyze', [_f('file', 'Recording', 'file')]),
		_a('submit_evidence', 'Send a photo for review', 'Sensors', 'POST', '/evidence', [_f('file', 'Photo', 'file'), _f('kind', 'What is it?', 'select', EVIDENCE_KINDS), _f('note', 'What did you notice?', 'textarea')]),
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
	'voice': ('Speak to the app', 'Ask in your own language'),
	'voice_audio': ('Send a recording', 'Speak a symptom report or a note and we will write it down'),
	'whatsapp_voice': ('Send a WhatsApp voice note', 'Hold the button, speak, and we will triage it'),
	'enrol_monitoring': ('Start my 21-day check-in', 'A short daily temperature log while you are being watched over'),
	'monitoring_day': ('Log today', 'Temperature and how you feel, morning and evening'),
	'monitoring_diary': ('My 21-day diary', 'Every day you have logged, and the countdown to the end'),
	'monitoring_reminders': ('What is still to log today', 'The check-ins you have done, and the ones you have not'),
	'monitoring_consent': ('Share my location while I am monitored', 'Off unless you turn it on, and you can turn it off again'),
	'monitoring_members': ('Add someone I live with', 'Their readings go in the same diary as yours'),
	'monitoring_member_diary': ('Their readings', 'What the person you added has logged so far'),
	'monitoring_officer': ('Call my monitoring officer', 'The health worker assigned to your check-in'),
}
