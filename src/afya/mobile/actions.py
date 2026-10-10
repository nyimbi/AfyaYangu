"""Server-driven mobile action catalogue — the generic mechanism that exposes every backend feature.

GET /mobile/actions returns every usable action (id, title, group, method, path, fields);
a field is {name,label,type,options,placeholder} with type in:
	text, int, decimal, bool, select, textarea, list (comma text -> array), file, path (URL path param).
Apps render one generic form per action — no per-feature code, no app release needed to add features.

IDENTIFIERS ARE SLUGS, NOT SPEC CODES. Nothing a person reads may contain a code such as
"REC-004": ids, titles, labels, placeholders and descriptions are all plain language. The spec
codes live in FEATURE_OF, which is deliberately not serialised, so the backend keeps its
traceability to the spec without the code ever reaching a screen. tests/ci/test_ui_vocabulary.py
enforces this.
"""
from typing import Literal, TypeAlias, cast

from pydantic import BaseModel, ConfigDict

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
VECTOR_DISEASES = ['evd', 'cholera', 'malaria', 'dengue', 'mpox', 'rvf', 'measles', 'other']
ADHERENCE_ACTIONS = ['taken', 'skipped', 'snoozed']
INTENSITIES = ['low', 'balanced', 'maximum']
OUTPUT_KINDS = ['triage', 'risk_score', 'hotspot', 'exposure', 'tier4_activation']
ACTIVITY_KINDS = ['report', 'followup', 'sensitisation', 'referral', 'training', 'supervision']
JOB_AID_TOPICS = ['idsr_case_definition', 'ppe_donning', 'ppe_doffing', 'isolation_basics', 'safe_burial', 'reporting_flow']
CHW_TASK_KINDS = ['followup', 'referral', 'sensitisation']

# slug -> spec feature id. Internal traceability only; never serialised (see module docstring).
FEATURE_OF: dict[str, str] = {
	'febrile_triage': 'TRI-001', 'evd_triage': 'TRI-003', 'differential': 'TRI-001', 'symptom_diary': 'TRI-002',
	'nearest_facilities': 'FND-001', 'ed_status': 'FND-002', 'report_wait': 'FND-004', 'book_appointment': 'FND-006',
	'verify_medicine': 'MED-001', 'drug_interactions': 'MED-002', 'dosage': 'MED-003', 'report_stock': 'MED-004',
	'sos': 'EMG-001', 'emergency_card': 'EMG-003',
	'immunisation_gaps': 'REC-001', 'family_wallet': 'REC-001', 'growth_flag': 'REC-003',
	'add_lab': 'REC-007', 'view_labs': 'REC-007', 'register_donor': 'REC-004', 'find_donors': 'REC-004',
	'wellbeing_check': 'REC-005', 'counselling_lines': 'REC-005',
	'log_bp': 'REC-006', 'log_glucose': 'REC-006', 'bp_trend': 'REC-006', 'track_refill': 'REC-006',
	'log_cycle': 'REC-009', 'cycle_prediction': 'REC-009',
	'register_pregnancy': 'REC-008', 'anc_due': 'REC-008', 'record_anc': 'REC-008', 'danger_signs': 'REC-008',
	'child_schedule': 'MON-001', 'catch_up_doses': 'MON-001', 'record_dose': 'MON-001', 'register_child': 'MON-001',
	'add_medication': 'MON-004', 'log_adherence': 'MON-004',
	'peak_flow': 'MON-003', 'log_weight': 'MON-003', 'condition_profile': 'MON-003', 'clinical_report': 'MON-003',
	'vector_risk': 'MON-007', 'breeding_site': 'MON-007', 'food_alert': 'MON-008', 'food_alerts': 'MON-008', 'nutrition': 'MON-008',
	'enrol_monitoring': 'MON-009', 'monitoring_day': 'MON-009', 'monitoring_diary': 'MON-009',
	'issue_alert': 'INF-014', 'alerts_by_county': 'INF-014',
	'water_advisory': 'INF-011', 'air_advisory': 'INF-012', 'flood_risk': 'INF-013',
	'file_price': 'INF-016', 'price_quote': 'INF-016', 'sha_cover_check': 'INF-016',
	'assign_chw_task': 'CHAN-005', 'chw_open_tasks': 'CHAN-005', 'complete_chw_task': 'CHAN-005',
	'send_sms': 'CHAN-001', 'whatsapp_send': 'CHAN-003', 'ussd_menu': 'CHAN-002',
	'queue_sync_op': 'CHAN-006', 'flush_sync': 'CHAN-006',
	'record_consent': 'SEC-001', 'dpia_check': 'SEC-001',
	'sensor_ingest': 'SENS-005', 'analyse_cough': 'SENS-002', 'submit_evidence': 'SENS-004',
	'activate_outbreak_mode': 'TRI-003',
	'report_issue': 'COM-005', 'issues_by_county': 'COM-005', 'resolve_issue': 'COM-005',
	'submit_case': 'COM-101', 'advance_case': 'COM-101', 'ppe_reminder': 'COM-101',
	'peer_alert': 'COM-102', 'tracing_prompts': 'COM-103', 'save_contacts': 'COM-103', 'add_contact': 'COM-103',
	'flag_misinformation': 'COM-104', 'misinformation_clusters': 'COM-104',
	'publish_feed_item': 'ALT-001', 'alert_feed': 'ALT-001',
	'alert_preferences': 'ALT-003', 'set_alert_preference': 'ALT-003',
	'link_family': 'ALT-002', 'family_check_in': 'ALT-002', 'family_board': 'ALT-002',
	'send_exposure_notice': 'ALT-004', 'ack_exposure': 'ALT-004',
	'rotate_ebid': 'LOC-002', 'log_encounter': 'LOC-002', 'declare_exposure': 'LOC-002', 'check_exposure': 'LOC-002',
	'enable_location_history': 'LOC-003', 'log_location': 'LOC-003', 'location_report': 'LOC-003', 'purge_location': 'LOC-003',
	'register_checkin_point': 'LOC-004', 'check_in': 'LOC-004', 'checkin_points': 'LOC-004', 'checkin_list': 'LOC-004',
	'register_border': 'LOC-005', 'border_status': 'LOC-005', 'travel_advisory': 'LOC-005', 'traveller_declare': 'LOC-005',
	'hotspots': 'AI-001', 'risk_score': 'AI-002', 'early_warning': 'AI-003',
	'model_cards': 'AI-004', 'fairness_audit': 'AI-004', 'file_redress': 'AI-005',
	'access_profile': 'ACC-001', 'ui_screens': 'ACC-001', 'languages': 'ACC-002', 'voice': 'ACC-002',
	'battery_profile': 'ACC-004', 'compatibility': 'ACC-005',
	'retention_policy': 'SEC-005', 'record_holding': 'SEC-006', 'record_share': 'SEC-006',
	'data_inventory': 'SEC-006', 'delete_my_data': 'SEC-005', 'purge_expired': 'SEC-005',
	'encryption_posture': 'SEC-003', 'transparency_report': 'SEC-006',
	'provision_chw': 'CHAN-005', 'chw_profile': 'CHAN-005', 'chw_training': 'CHAN-005', 'job_aid': 'COM-101',
	'chw_cases': 'COM-101', 'assign_chw_case': 'COM-101', 'log_chw_activity': 'COM-101', 'chw_activity': 'COM-101',
	'chw_case_load': 'COM-101', 'chw_ppe_reminder': 'COM-101',
}

# Slugs whose feature is dormant until PHEOC activates the outbreak event (§11.1).
DORMANT_SLUGS: frozenset[str] = frozenset({
	'evd_triage', 'activate_outbreak_mode', 'enrol_monitoring', 'monitoring_day', 'monitoring_diary',
	'submit_case', 'advance_case', 'peer_alert', 'save_contacts', 'add_contact', 'flag_misinformation',
	'misinformation_clusters', 'send_exposure_notice', 'ack_exposure',
	'rotate_ebid', 'log_encounter', 'declare_exposure', 'check_exposure',
	'enable_location_history', 'log_location', 'location_report', 'purge_location',
	'register_checkin_point', 'check_in', 'register_border', 'border_status', 'traveller_declare',
	'hotspots', 'risk_score', 'early_warning',
})


def _f(name: str, label: str, type_: str = 'text', options: list[str] | None = None, ph: str | None = None) -> MobileField:
	return MobileField(name=name, label=label, type=cast(FieldType, type_), options=options, placeholder=ph, required=type_ == 'path')


def _a(id: str, title: str, group: str, method: str, path: str, fields: list[MobileField]) -> MobileAction:
	assert method in ('GET', 'POST', 'DELETE') and all(fl.type in FIELD_TYPES for fl in fields), 'contract'
	assert id in FEATURE_OF, f'action {id} must declare its source feature in FEATURE_OF'
	return MobileAction(id=id, title=title, group=group, method=method, path=path, fields=fields)


def catalogue() -> list[MobileAction]:
	triage_fields = [_f('symptoms', 'Symptoms', 'list', ph='fever, headache'), _f('temperature_c', 'Temperature °C', 'decimal'), _f('ebola_contact', 'Contact with an Ebola patient?', 'bool')]
	return [
		# Triage
		_a('febrile_triage', 'Check a fever', 'Triage', 'POST', '/triage/preliminary', triage_fields),
		_a('evd_triage', 'Ebola check', 'Triage', 'POST', '/triage/evd', triage_fields),
		_a('differential', 'What illness could this be?', 'Triage', 'POST', '/triage/diagnose', triage_fields),
		_a('symptom_diary', 'Log how I feel today', 'Triage', 'POST', '/triage/diary', [_f('entry_id', 'Entry number', ph='generated for you'), _f('subject_ref', 'Who is this for?'), _f('day', 'Day (1-21)', 'int'), _f('symptoms', 'Symptoms', 'list'), _f('temperature_c', 'Temperature °C', 'decimal')]),
		# Facilities
		_a('nearest_facilities', 'Find care near me', 'Facilities', 'POST', '/facilities/nearest', [_f('lat', 'Latitude', 'decimal'), _f('lon', 'Longitude', 'decimal'), _f('kind', 'Type of place', 'select', FACILITY_KINDS), _f('limit', 'How many results', 'int')]),
		_a('ed_status', 'How busy is the emergency unit?', 'Facilities', 'GET', '/facilities/{facility_id}/ed-status', [_f('id', 'Facility', 'path')]),
		_a('report_wait', 'Report the queue length', 'Facilities', 'POST', '/facilities/{facility_id}/wait', [_f('id', 'Facility', 'path'), _f('minutes', 'Minutes waited', 'int')]),
		_a('book_appointment', 'Book an appointment', 'Facilities', 'POST', '/facilities/{facility_id}/booking', [_f('id', 'Facility', 'path'), _f('booking_id', 'Booking number', ph='generated for you'), _f('slot_iso', 'Appointment time')]),
		# Medicine
		_a('verify_medicine', 'Is my medicine genuine?', 'Medicine', 'POST', '/medicine/verify', [_f('batch_number', 'Batch number (on the box)'), _f('gtin', 'Barcode number')]),
		_a('drug_interactions', 'Can I take these together?', 'Medicine', 'POST', '/medicine/interactions', [_f('drugs', 'Medicines', 'list')]),
		_a('dosage', 'How much should I give?', 'Medicine', 'POST', '/medicine/dose', [_f('drug', 'Medicine'), _f('weight_kg', 'Weight in kg', 'decimal'), _f('mg_per_kg', 'mg per kg', 'decimal')]),
		_a('report_stock', 'Report whether a medicine is in stock', 'Medicine', 'POST', '/medicine/stock', [_f('report_id', 'Report number', ph='generated for you'), _f('facility_id', 'Facility'), _f('drug', 'Medicine'), _f('in_stock', 'In stock?', 'bool')]),
		# Emergency
		_a('sos', 'Get help now', 'Emergency', 'POST', '/emergency/sos', [_f('sos_id', 'Alert number', ph='generated for you'), _f('lat', 'Latitude', 'decimal'), _f('lon', 'Longitude', 'decimal'), _f('severity', 'How serious?', 'select', ['low', 'medium', 'high']), _f('symptoms', 'Symptoms', 'list')]),
		_a('emergency_card', 'My emergency card', 'Emergency', 'POST', '/emergency/card/qr', [_f('name', 'Full name'), _f('blood_group', 'Blood group', 'select', BLOOD_GROUPS), _f('allergies', 'Allergies', 'list'), _f('conditions', 'Ongoing conditions', 'list'), _f('emergency_contact', 'Who to call')]),
		# Records & wallet
		_a('immunisation_gaps', 'Which vaccines are missing?', 'Records', 'GET', '/records/{member_ref}/immunisation-gaps', [_f('ref', 'Family member', 'path')]),
		_a('family_wallet', 'Family health wallet', 'Records', 'GET', '/records/{guardian_ref}/wallet', [_f('ref', 'Guardian', 'path')]),
		_a('growth_flag', 'Is my child growing well?', 'Records', 'POST', '/records/growth', [_f('member_ref', 'Family member'), _f('age_months', 'Age in months', 'int'), _f('weight_kg', 'Weight in kg', 'decimal'), _f('height_cm', 'Height in cm', 'decimal')]),
		_a('add_lab', 'Add a lab result', 'Records', 'POST', '/records/labs', [_f('member_ref', 'Family member'), _f('test', 'Test', 'select', ['mRDT', 'widal', 'hba1c', 'fbc', 'viral_load', 'glucose_f', 'bp', 'other']), _f('value', 'Result'), _f('unit', 'Unit', ph='optional'), _f('flag', 'Is it normal?', 'select', ['normal', 'abnormal', 'critical', 'unknown']), _f('performed_iso', 'Date of test')]),
		_a('view_labs', 'My lab results', 'Records', 'GET', '/records/{ref}/labs', [_f('ref', 'Family member', 'path')]),
		_a('register_donor', 'Register as a blood donor', 'Records', 'POST', '/blood/donors', [_f('donor_ref', 'Donor reference'), _f('blood_group', 'Blood group', 'select', BLOOD_GROUPS), _f('county', 'County'), _f('last_donation_iso', 'Last donation date', ph='optional')]),
		_a('find_donors', 'Find blood donors', 'Records', 'POST', '/blood/match', [_f('request_id', 'Request number'), _f('blood_group', 'Group needed', 'select', BLOOD_GROUPS), _f('county', 'County'), _f('urgency', 'How urgent?', 'select', ['routine', 'urgent', 'critical'])]),
		# Wellbeing
		_a('wellbeing_check', 'How have I been feeling?', 'Wellbeing', 'POST', '/mental/who5', [_f('subject_ref', 'Who is this for?'), _f('s1', 'Question 1 (0-5)', 'int'), _f('s2', 'Question 2 (0-5)', 'int'), _f('s3', 'Question 3 (0-5)', 'int'), _f('s4', 'Question 4 (0-5)', 'int'), _f('s5', 'Question 5 (0-5)', 'int')]),
		_a('counselling_lines', 'Talk to someone', 'Wellbeing', 'GET', '/mental/lines', []),
		# Chronic & daily
		_a('log_bp', 'Log my blood pressure', 'Daily care', 'POST', '/chronic/bp', [_f('subject_ref', 'Who is this for?'), _f('systolic', 'Systolic', 'int'), _f('diastolic', 'Diastolic', 'int'), _f('pulse', 'Pulse', 'int')]),
		_a('log_glucose', 'Log my blood sugar', 'Daily care', 'POST', '/chronic/glucose', [_f('subject_ref', 'Who is this for?'), _f('mmol_l', 'mmol/L', 'decimal'), _f('fasting', 'Before eating?', 'bool')]),
		_a('bp_trend', 'Is my blood pressure improving?', 'Daily care', 'GET', '/chronic/{ref}/bp-trend', [_f('ref', 'Who is this for?', 'path')]),
		_a('track_refill', 'When do I need a refill?', 'Daily care', 'POST', '/chronic/refill', [_f('subject_ref', 'Who is this for?'), _f('drug', 'Medicine'), _f('days_remaining', 'Days of medicine left', 'int')]),
		_a('peak_flow', 'Log my peak flow', 'Daily care', 'POST', '/monitoring/chronic/peak-flow', [_f('subject_ref', 'Who is this for?'), _f('litres_per_min', 'Litres per minute', 'int'), _f('personal_best', 'My best ever', 'int')]),
		_a('log_weight', 'Log my weight', 'Daily care', 'POST', '/monitoring/chronic/weight', [_f('subject_ref', 'Who is this for?'), _f('kg', 'Weight in kg', 'decimal')]),
		_a('condition_profile', 'My ongoing conditions', 'Daily care', 'POST', '/monitoring/chronic/conditions', [_f('subject_ref', 'Who is this for?'), _f('conditions', 'Conditions', 'list', ph='hypertension, diabetes'), _f('hiv_pin_set', 'Extra PIN set for private conditions?', 'bool')]),
		_a('clinical_report', 'Report to show my clinician', 'Daily care', 'GET', '/monitoring/chronic/{subject_ref}/report', [_f('subject_ref', 'Who is this for?', 'path')]),
		# Women & maternal
		_a('log_cycle', 'Log my period', 'Women', 'POST', '/women/cycle', [_f('subject_ref', 'Who is this for?'), _f('start_iso', 'First day of period'), _f('cycle_days', 'Cycle length in days', 'int'), _f('pain_level', 'Pain level (0-10)', 'int')]),
		_a('cycle_prediction', 'When is my next period?', 'Women', 'GET', '/women/cycle/{ref}/predict', [_f('ref', 'Who is this for?', 'path')]),
		_a('register_pregnancy', 'Register my pregnancy', 'Maternity', 'POST', '/maternal/pregnancy', [_f('subject_ref', 'Who is this for?'), _f('edd_iso', 'Expected delivery date'), _f('lmp_week', 'Weeks pregnant now', 'int'), _f('delivery_plan_facility_id', 'Where I plan to deliver', ph='optional')]),
		_a('anc_due', 'Which clinic visits are due?', 'Maternity', 'GET', '/maternal/{ref}/anc-due', [_f('ref', 'Who is this for?', 'path'), _f('gest_week', 'Weeks pregnant', 'int')]),
		_a('record_anc', 'Record a clinic visit', 'Maternity', 'POST', '/maternal/anc', [_f('subject_ref', 'Who is this for?'), _f('contact_no', 'Visit number (1-8)', 'int'), _f('done_iso', 'Date of visit')]),
		_a('danger_signs', 'Check for danger signs', 'Maternity', 'POST', '/maternal/danger', [_f('signs', 'Danger signs', 'list', ph='bleeding, severe_headache')]),
		# Child immunisation
		_a('register_child', "Add my child's date of birth", 'Children', 'POST', '/monitoring/child', [_f('member_ref', 'Child'), _f('dob_iso', 'Date of birth')]),
		_a('child_schedule', 'My child vaccine schedule', 'Children', 'GET', '/monitoring/child/{member_ref}/schedule', [_f('member_ref', 'Child', 'path')]),
		_a('catch_up_doses', 'Which doses were missed?', 'Children', 'GET', '/monitoring/child/{member_ref}/catch-up', [_f('member_ref', 'Child', 'path')]),
		_a('record_dose', 'Record a vaccine given', 'Children', 'POST', '/monitoring/child/{member_ref}/dose', [_f('member_ref', 'Child', 'path'), _f('vaccine', 'Vaccine'), _f('dose_no', 'Dose number', 'int'), _f('given_iso', 'Date given')]),
		_a('add_medication', 'Remind me to take my medicine', 'Children', 'POST', '/monitoring/medication', [_f('schedule_id', 'Reminder number', ph='generated for you'), _f('member_ref', 'Who is this for?'), _f('drug', 'Medicine'), _f('dose', 'How much'), _f('times_per_day', 'Times a day', 'int'), _f('start_iso', 'Starting on'), _f('duration_days', 'For how many days', 'int')]),
		_a('log_adherence', 'I took my medicine', 'Children', 'POST', '/monitoring/medication/adherence', [_f('schedule_id', 'Reminder number'), _f('at_iso', 'When'), _f('action', 'What happened?', 'select', ADHERENCE_ACTIONS)]),
		# Environment & nutrition
		_a('vector_risk', 'Is there a mosquito risk here?', 'Environment', 'POST', '/monitoring/vector-risk', [_f('county', 'County'), _f('rainfall_mm_72h', 'Rainfall in the last 3 days (mm)', 'decimal'), _f('livestock_adjacent', 'Do you keep livestock?', 'bool')]),
		_a('breeding_site', 'Report a mosquito breeding site', 'Environment', 'POST', '/monitoring/breeding-site', [_f('county', 'County'), _f('lat', 'Latitude', 'decimal'), _f('lon', 'Longitude', 'decimal'), _f('description', 'What did you see?', 'textarea')]),
		_a('food_alert', 'Issue a food safety alert', 'Environment', 'POST', '/monitoring/food-alert', [_f('county', 'County'), _f('kind', 'Kind', 'select', ['aflatoxin', 'recall', 'cholera_food', 'other']), _f('detail', 'Details', 'textarea'), _f('source', 'Source')]),
		_a('food_alerts', 'Food safety alerts', 'Environment', 'GET', '/monitoring/food-alerts/{county}', [_f('county', 'County', 'path')]),
		_a('nutrition', 'What should my child eat?', 'Environment', 'GET', '/monitoring/nutrition/{age_months}', [_f('age_months', 'Age in months', 'path')]),
		_a('water_advisory', 'Is the water safe?', 'Environment', 'POST', '/environment/water', [_f('county', 'County'), _f('ecoli', 'E. coli detected?', 'bool'), _f('turbidity_ntu', 'Turbidity NTU', 'decimal')]),
		_a('air_advisory', 'How is the air?', 'Environment', 'POST', '/environment/air', [_f('county', 'County'), _f('pm25', 'PM2.5 µg/m³', 'decimal')]),
		_a('flood_risk', 'Flood and cholera risk', 'Environment', 'POST', '/environment/flood', [_f('county', 'County'), _f('rainfall_mm_72h', 'Rainfall mm in 3 days', 'decimal'), _f('population_at_risk', 'People at risk', 'int')]),
		# Alerts
		_a('issue_alert', 'Send a community alert', 'Alerts', 'POST', '/alerts', [_f('alert_id', 'Alert number', ph='generated for you'), _f('kind', 'Kind', 'select', ALERT_KINDS), _f('county', 'County'), _f('headline', 'Headline'), _f('body', 'Message', 'textarea'), _f('issued_by', 'Issued by', 'select', ['PHEOC', 'MoH', 'County', 'KMD'])]),
		_a('alerts_by_county', 'Alerts for my county', 'Alerts', 'GET', '/alerts/{county}', [_f('county', 'County', 'path')]),
		_a('publish_feed_item', 'Publish a verified alert', 'Alerts', 'POST', '/alerting/feed', [_f('item_id', 'Item number'), _f('category', 'Category', 'select', ['outbreak', 'weather', 'flood', 'fire', 'road', 'security', 'drug_recall', 'water', 'food_recall', 'service']), _f('headline', 'Headline'), _f('body', 'Message', 'textarea'), _f('source', 'Source'), _f('verified', 'Verified?', 'bool'), _f('published_iso', 'Published on'), _f('county', 'County', ph='optional')]),
		_a('alert_feed', 'Alerts near me', 'Alerts', 'GET', '/alerting/feed', [_f('county', 'County', ph='optional')]),
		_a('set_alert_preference', 'Choose which alerts I get', 'Alerts', 'POST', '/alerting/preferences', [_f('subject_ref', 'Who is this for?'), _f('category', 'Alert type'), _f('enabled', 'Turn on?', 'bool')]),
		_a('alert_preferences', 'My alert settings', 'Alerts', 'GET', '/alerting/preferences/{subject_ref}', [_f('subject_ref', 'Who is this for?', 'path')]),
		_a('link_family', 'Link my family', 'Alerts', 'POST', '/alerting/family/link', [_f('family_ref', 'Family group'), _f('members', 'Family members', 'list')]),
		_a('family_check_in', "I'm safe", 'Alerts', 'POST', '/alerting/family/check-in', [_f('subject_ref', 'Who is this?'), _f('family_ref', 'Family group'), _f('at_iso', 'When')]),
		_a('family_board', 'Is my family safe?', 'Alerts', 'GET', '/alerting/family/{family_ref}', [_f('family_ref', 'Family group', 'path')]),
		# Community
		_a('report_issue', 'Report a problem in my area', 'Community', 'POST', '/community/issues', [_f('issue_id', 'Report number', ph='generated for you'), _f('kind', 'What is the problem?', 'select', ISSUE_KINDS), _f('county', 'County'), _f('description', 'Describe it', 'textarea'), _f('lat', 'Latitude', 'decimal'), _f('lon', 'Longitude', 'decimal')]),
		_a('issues_by_county', 'Problems reported near me', 'Community', 'GET', '/community/issues/{county}', [_f('county', 'County', 'path')]),
		_a('resolve_issue', 'Mark a problem as fixed', 'Community', 'POST', '/community/issues/{issue_id}/resolve', [_f('id', 'Report number', 'path')]),
		_a('submit_case', 'Report a suspected case', 'Community', 'POST', '/community/cases', [_f('report_id', 'Report number', ph='generated for you'), _f('chw_ref', 'Health worker'), _f('county', 'County'), _f('community', 'Village or estate'), _f('symptoms', 'Symptoms', 'list'), _f('age_years', 'Age in years', 'int'), _f('sex', 'Sex', 'select', ['male', 'female', 'other']), _f('temperature_c', 'Temperature °C', 'decimal'), _f('exposure_history', 'Who has the patient been near?', 'textarea'), _f('geotagged', 'Attach location?', 'bool'), _f('suspected_disease', 'What do you suspect?', 'select', VECTOR_DISEASES), _f('reported_offline', 'Reported without network?', 'bool')]),
		_a('advance_case', 'Update a case', 'Community', 'POST', '/community/cases/{report_id}/advance', [_f('report_id', 'Report number', 'path'), _f('status', 'New status', 'select', CASE_STATUSES)]),
		_a('ppe_reminder', 'Protective equipment reminder', 'Community', 'GET', '/community/ppe-reminder', []),
		_a('peer_alert', 'Warn people nearby', 'Community', 'POST', '/community/peer-alert', [_f('alert_id', 'Alert number'), _f('county', 'County'), _f('lat', 'Latitude', 'decimal'), _f('lon', 'Longitude', 'decimal'), _f('radius_m', 'How far? (metres)', 'int'), _f('headline', 'Headline'), _f('body', 'Message', 'textarea'), _f('verified_by', 'Verified by', 'select', ['County', 'PHEOC', 'MoH'])]),
		_a('tracing_prompts', 'Help me remember who I met', 'Community', 'GET', '/community/tracing-prompts', []),
		_a('save_contacts', 'Save my contact list', 'Community', 'POST', '/community/contacts', [_f('subject_ref', 'Who is this for?'), _f('entries', 'People', 'list'), _f('share_consent', 'Share with the health team?', 'bool')]),
		_a('add_contact', 'Add one person I met', 'Community', 'POST', '/community/contacts/{subject_ref}/entry', [_f('subject_ref', 'Who is this for?', 'path'), _f('description', 'Who was it?'), _f('setting', 'Where?', 'select', CONTACT_SETTINGS), _f('approx_location', 'Roughly where?'), _f('name_unknown', "I don't know their name", 'bool')]),
		_a('flag_misinformation', 'Report something I heard', 'Community', 'POST', '/community/misinformation', [_f('submission_id', 'Report number', ph='generated for you'), _f('claim', 'What did you hear?', 'textarea'), _f('county', 'County'), _f('medium', 'How did you get it?', 'select', MISINFO_MEDIA), _f('topic', 'Topic', ph='optional')]),
		_a('misinformation_clusters', 'Rumours going around', 'Community', 'GET', '/community/misinformation/clusters', []),
		# Outbreak mode
		_a('enrol_monitoring', 'Start my 21-day check-in', 'Outbreak', 'POST', '/monitoring/contact/enrol', [_f('subject_ref', 'Who is this for?'), _f('officer', 'Monitoring officer', ph='optional')]),
		_a('monitoring_day', 'Log today (21-day check-in)', 'Outbreak', 'POST', '/monitoring/contact/day', [_f('entry_id', 'Entry number', ph='generated for you'), _f('subject_ref', 'Who is this for?'), _f('day', 'Day (1-21)', 'int'), _f('temperature_c', 'Temperature °C', 'decimal'), _f('symptoms', 'Symptoms', 'list'), _f('household_member', 'Family member', ph='optional')]),
		_a('monitoring_diary', 'My 21-day diary', 'Outbreak', 'GET', '/monitoring/contact/{subject_ref}/diary', [_f('subject_ref', 'Who is this for?', 'path')]),
		_a('send_exposure_notice', 'Send an exposure notice', 'Outbreak', 'POST', '/alerting/exposure', [_f('subject_ref', 'Who is this for?'), _f('case_ref', 'Case reference', ph='optional')]),
		_a('ack_exposure', 'I have read the notice', 'Outbreak', 'POST', '/alerting/exposure/ack', [_f('notification_id', 'Notice number'), _f('subject_ref', 'Who is this for?'), _f('acknowledged_iso', 'When'), _f('request_callback', 'Ask a health worker to call me', 'bool')]),
		_a('check_exposure', 'Was I near a case?', 'Outbreak', 'POST', '/location/proximity/check', [_f('own_pets', 'My encounter codes', 'list'), _f('window_days', 'Days to look back', 'int')]),
		_a('declare_exposure', 'Declare that I tested positive', 'Outbreak', 'POST', '/location/proximity/declare', [_f('declaration_id', 'Declaration number'), _f('pet', 'Encounter code'), _f('declared_at_ms', 'When', 'int'), _f('proxied', 'Send anonymously?', 'bool')]),
		_a('log_encounter', 'Log someone I passed nearby', 'Outbreak', 'POST', '/location/proximity/encounter', [_f('pet', 'Encounter code'), _f('seen_at_ms', 'When', 'int'), _f('rssi_dbm', 'Signal strength', 'int'), _f('county', 'County')]),
		_a('rotate_ebid', 'Get a fresh nearby-code', 'Outbreak', 'POST', '/location/proximity/ebid', [_f('seed', 'Private seed'), _f('now_ms', 'Current time', 'int')]),
		_a('enable_location_history', 'Keep a private location diary', 'Outbreak', 'POST', '/location/history/enable', [_f('subject_ref', 'Who is this for?'), _f('window_days', 'Days to keep', 'int')]),
		_a('log_location', 'Save where I am', 'Outbreak', 'POST', '/location/history/point', [_f('subject_ref', 'Who is this for?'), _f('point', 'Place', 'text')]),
		_a('location_report', 'Where I have been', 'Outbreak', 'GET', '/location/history/{subject_ref}/report', [_f('subject_ref', 'Who is this for?', 'path'), _f('share', 'Share with the health team?', 'bool')]),
		_a('purge_location', 'Delete my location diary', 'Outbreak', 'DELETE', '/location/history/{subject_ref}', [_f('subject_ref', 'Who is this for?', 'path')]),
		_a('checkin_points', 'Check-in points near me', 'Outbreak', 'GET', '/location/checkin/points', [_f('county', 'County', ph='optional')]),
		_a('checkin_list', 'Where I checked in', 'Outbreak', 'GET', '/location/checkin/{subject_ref}', [_f('subject_ref', 'Who is this for?', 'path')]),
		_a('register_checkin_point', 'Set up a check-in point', 'Outbreak', 'POST', '/location/checkin/point', [_f('point_id', 'Point number'), _f('kind', 'What kind of place?', 'select', CHECKIN_KINDS), _f('label', 'Name'), _f('county', 'County'), _f('token', 'Check-in code')]),
		_a('check_in', 'Check in here', 'Outbreak', 'POST', '/location/checkin', [_f('checkin_id', 'Check-in number'), _f('point_token', 'Check-in code'), _f('subject_ref', 'Who is this for?'), _f('method', 'How?', 'select', CHECKIN_METHODS), _f('at_iso', 'When'), _f('share_with_authority', 'Share with the health team?', 'bool')]),
		_a('register_border', 'Set up a border post', 'Outbreak', 'POST', '/location/border', [_f('post_id', 'Post number'), _f('name', 'Name'), _f('county', 'County'), _f('country_pair', 'Between which countries?'), _f('queue_minutes', 'Queue in minutes', 'int'), _f('screening_required', 'Screening required?', 'bool')]),
		_a('border_status', 'Border queue', 'Outbreak', 'GET', '/location/border/{post_id}', [_f('post_id', 'Post number', 'path')]),
		_a('travel_advisory', 'Should I travel?', 'Outbreak', 'GET', '/location/travel-advisory', [_f('destination', 'Where to?'), _f('origin_country', 'Coming from')]),
		_a('traveller_declare', 'Declare my arrival', 'Outbreak', 'POST', '/location/traveller/declare', [_f('declaration_id', 'Declaration number'), _f('subject_ref', 'Who is this for?'), _f('destination', 'Where are you going?'), _f('arrival_iso', 'Arrival date'), _f('origin_country', 'Coming from'), _f('symptoms', 'Any symptoms?', 'list')]),
		_a('hotspots', 'Where might cases appear next?', 'Outbreak', 'POST', '/ai/hotspots', [_f('cells', 'Area data', 'list')]),
		_a('risk_score', 'What is my personal risk?', 'Outbreak', 'POST', '/ai/risk-score', [_f('symptoms', 'Symptoms', 'list'), _f('exposure_contact', 'Contact with a case?', 'bool'), _f('travel_affected_area', 'Travelled to an affected area?', 'bool'), _f('geofence_entry', 'Entered a risk area?', 'bool'), _f('proximity_encounters', 'Nearby encounters', 'int'), _f('vaccinated', 'Vaccinated?', 'bool')]),
		_a('early_warning', 'Is something unusual happening?', 'Outbreak', 'POST', '/ai/early-warning', [_f('county', 'County'), _f('disease', 'Disease'), _f('signals', 'Signals', 'list')]),
		_a('activate_outbreak_mode', 'Activate outbreak mode', 'Outbreak', 'POST', '/tier4/activate', [_f('authorized_by_pheoc', 'PHEOC authorised?', 'bool'), _f('dpia_reviewed', 'Privacy review done?', 'bool'), _f('flag_enabled', 'Switch on?', 'bool')]),
		# Privacy & transparency
		_a('record_consent', 'Record my consent', 'Privacy', 'POST', '/privacy/consent', [_f('subject_ref', 'Who is this for?'), _f('purpose', 'What for?'), _f('data_types', 'Which data?', 'list'), _f('retention_days', 'Keep for how many days', 'int'), _f('legal_basis', 'Why are we allowed to?', 'select', ['consent', 'legal_obligation', 'legitimate_interest'])]),
		_a('dpia_check', 'Check a new data use', 'Privacy', 'POST', '/privacy/dpia', [_f('raw_sensor_data_retained', 'Keeping raw sensor data?', 'bool'), _f('automated_decisions', 'Automatic decisions?', 'bool'), _f('cross_border_transfer', 'Data leaving the country?', 'bool'), _f('children_data', "Children's data?", 'bool'), _f('proximity_logging', 'Proximity logging?', 'bool')]),
		_a('retention_policy', 'How long is data kept?', 'Privacy', 'GET', '/retention/policy', []),
		_a('data_inventory', 'What do you know about me?', 'Privacy', 'GET', '/retention/inventory/{subject_ref}', [_f('subject_ref', 'Who is this for?', 'path')]),
		_a('delete_my_data', 'Delete my data', 'Privacy', 'POST', '/retention/delete', [_f('subject_ref', 'Who is this for?'), _f('data_type', 'Only this type', ph='leave blank for everything'), _f('channel', 'How?', 'select', ['native', 'sms', 'ussd', 'whatsapp'])]),
		_a('purge_expired', 'Clear what has expired', 'Privacy', 'POST', '/retention/purge-expired', [_f('subject_ref', 'Who is this for?'), _f('age_days', 'How old each record is, by type', 'text')]),
		_a('encryption_posture', 'How is my data protected?', 'Privacy', 'GET', '/retention/encryption', []),
		_a('transparency_report', 'Transparency report', 'Privacy', 'GET', '/retention/transparency', [_f('period', 'Period'), _f('subject_ref', 'Who is this for?', ph='optional')]),
		_a('record_holding', 'Record what is stored', 'Privacy', 'POST', '/retention/holding', [_f('subject_ref', 'Who is this for?'), _f('data_type', 'Data type'), _f('count', 'How many records', 'int')]),
		_a('record_share', 'Record a data share', 'Privacy', 'POST', '/retention/share', [_f('subject_ref', 'Who is this for?'), _f('with_who', 'Shared with'), _f('what', 'What was shared'), _f('when_iso', 'When')]),
		# Access & fairness
		_a('access_profile', 'Make the app easier to use', 'Access', 'POST', '/access/profile', [_f('subject_ref', 'Who is this for?'), _f('simple_mode', 'Simple mode', 'bool'), _f('large_text', 'Large text', 'bool'), _f('high_contrast', 'High contrast', 'bool'), _f('read_aloud', 'Read screens aloud', 'bool'), _f('voice_input', 'Speak instead of typing', 'bool'), _f('lang', 'Language')]),
		_a('ui_screens', 'Screen list', 'Access', 'GET', '/access/screens', [_f('simple_mode', 'Simple mode', 'bool')]),
		_a('languages', 'Languages', 'Access', 'GET', '/access/languages', [_f('tier', 'Priority tier', 'int')]),
		_a('voice', 'Speak to the app', 'Access', 'POST', '/access/voice', [_f('subject_ref', 'Who is this for?'), _f('lang', 'Language'), _f('utterance', 'What you said'), _f('offline', 'No network?', 'bool')]),
		_a('battery_profile', 'Battery use', 'Access', 'GET', '/access/battery', [_f('subject_ref', 'Who is this for?'), _f('intensity', 'Monitoring level', 'select', INTENSITIES), _f('battery_saver', 'Battery saver', 'bool')]),
		_a('compatibility', 'Will it work on my phone?', 'Access', 'GET', '/access/compatibility/{platform}', [_f('platform', 'Phone type', 'path')]),
		_a('model_cards', 'How the AI works', 'Access', 'GET', '/ai/models', []),
		_a('fairness_audit', 'Check an AI model is fair', 'Access', 'POST', '/ai/fairness-audit', [_f('model_id', 'Model'), _f('axes', 'Axes tested', 'list'), _f('unmet_axes', 'Failures found', 'list')]),
		_a('file_redress', 'Challenge a decision', 'Access', 'POST', '/ai/redress', [_f('request_id', 'Request number'), _f('subject_ref', 'Who is this for?'), _f('output_kind', 'What are you challenging?', 'select', OUTPUT_KINDS), _f('output_ref', 'Which result?'), _f('challenge', 'Why do you disagree?', 'textarea')]),
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
		_a('chw_open_tasks', 'Open tasks', 'Channels', 'GET', '/channels/chw/tasks/{chw_ref}', [_f('ref', 'Health worker', 'path')]),
		_a('complete_chw_task', 'Complete a task', 'Channels', 'POST', '/channels/chw/tasks/{task_id}/done', [_f('id', 'Task number', 'path')]),
		_a('send_sms', 'Send a free text message', 'Channels', 'POST', '/channels/sms', [_f('to_msisdn', 'Phone number'), _f('body', 'Message')]),
		_a('ussd_menu', 'USSD menu', 'Channels', 'POST', '/channels/ussd', [_f('session_id', 'Session'), _f('msisdn', 'Phone number'), _f('text', 'Selection')]),
		_a('whatsapp_send', 'WhatsApp reply', 'Channels', 'POST', '/channels/whatsapp', [_f('from_msisdn', 'Phone number'), _f('body', 'Message')]),
		_a('queue_sync_op', 'Save for later (offline)', 'Sync', 'POST', '/sync/ops', [_f('op_id', 'Change number'), _f('dataset', 'What kind of change?', 'select', SYNC_DATASETS), _f('client_ts', 'When it happened', 'int')]),
		_a('flush_sync', 'Send everything now', 'Sync', 'POST', '/sync/flush', []),
		_a('sensor_ingest', 'Save a reading', 'Sensors', 'POST', '/sensors/ingest', [_f('kind', 'Reading type', 'select', SENS_KINDS), _f('subject_ref', 'Who is this for?'), _f('value', 'Value', 'decimal'), _f('county', 'County')]),
		_a('analyse_cough', 'Check a cough recording', 'Sensors', 'POST', '/ml/cough/analyze', [_f('file', 'Recording', 'file')]),
		_a('submit_evidence', 'Send a photo for review', 'Sensors', 'POST', '/evidence', [_f('file', 'Photo', 'file'), _f('kind', 'What is it?', 'select', EVIDENCE_KINDS), _f('note', 'What did you notice?', 'textarea')]),
		# Insurance
		_a('file_price', 'Tell us what a procedure cost', 'Insurance', 'POST', '/insurance/prices', [_f('facility_id', 'Facility'), _f('procedure', 'Procedure', 'select', PROCEDURES), _f('kes', 'Cost in KES', 'int'), _f('sha_covered', 'Covered by SHA?', 'bool')]),
		_a('price_quote', 'What does it cost?', 'Insurance', 'GET', '/insurance/quote/{facility_id}/{procedure}', [_f('facility_id', 'Facility', 'path'), _f('procedure', 'Procedure', 'path')]),
		_a('sha_cover_check', 'Am I covered?', 'Insurance', 'POST', '/insurance/sha-check', [_f('member_no', 'SHA member number')]),
	]


def available(tier4_active: bool) -> list[MobileAction]:
	"""Actions the client may show right now. Dormant outbreak capabilities stay hidden until
	PHEOC activates the event, so a person never sees a switch that would refuse them."""
	rows = [a for a in catalogue() if tier4_active or a.id not in DORMANT_SLUGS]
	assert rows, 'catalogue must never be empty'
	return rows


# slug -> (screen-visible title, one-line human description). No spec codes anywhere.
FRIENDLY_COPY: dict[str, tuple[str, str]] = {
	'county_risk': ('What is happening in my county?', 'Up-to-date risk status and official guidance nearby'),
	'decision_tree': ('Should I see a doctor?', 'Plain-language help deciding your next step'),
	'hotlines': ('Who can I call?', 'Hotline numbers that are free and answered'),
	'febrile_triage': ('Check my fever', 'Quick check: treat malaria first unless there is Ebola contact risk'),
	'symptom_diary': ('My symptom diary', 'Track how you feel if you were exposed'),
	'evd_triage': ('Ebola check', 'Deeper screening when officials activate outbreak mode'),
	'nearest_facilities': ('Find care near me', 'Nearest clinics and hospitals with walking directions'),
	'ed_status': ('How busy is A&E?', 'Live queues at casualty units'),
	'book_appointment': ('Book an appointment', 'Skip the queue with a slot'),
	'verify_medicine': ('Is my medicine real?', 'Check any drug against the national registry'),
	'drug_interactions': ('Can I take these together?', 'Check risky medicine combinations'),
	'dosage': ('How much do I give?', 'Correct dose by weight'),
	'sos': ('Get help now', 'One tap: alerts the hotline and your people'),
	'emergency_card': ('My emergency card', 'Works with no signal on your lock screen'),
	'family_wallet': ('Family health wallet', "Everyone's immunisations and records in one place"),
	'growth_flag': ('Is my child growing well?', 'Compare growth with healthy ranges'),
	'child_schedule': ('My child vaccine schedule', 'Every dose due, and the ones that were missed'),
	'add_medication': ('Remind me to take my medicine', 'Never miss a dose or a refill'),
	'register_donor': ('Donate blood', 'Join the donor list for your county'),
	'find_donors': ('Find blood', 'Matching for nearby eligible donors'),
	'wellbeing_check': ('How am I feeling?', 'Gentle check-in plus free counselling lines'),
	'log_bp': ('My blood pressure', 'Daily readings and trends'),
	'log_glucose': ('My blood sugar', 'Daily readings and trends'),
	'track_refill': ('Refill reminders', 'Know before your medicine runs out'),
	'peak_flow': ('My peak flow', 'Asthma zones from your own best reading'),
	'log_weight': ('My weight', 'A real trend, logged weekly'),
	'register_pregnancy': ('Pregnancy care', 'Visits and danger signs we take seriously'),
	'danger_signs': ('Something feels wrong', 'One tap to escalate a pregnancy danger sign'),
	'log_cycle': ('My cycle', 'Private period tracking and predictions'),
	'submit_evidence': ('Send a photo for review', 'Show a nurse; we verify and route it'),
	'provision_chw': ('Community health workers', 'Tasks and the people you help'),
	'submit_case': ('Report a suspected case', 'Structured report that alerts the officer for you'),
	'report_issue': ('Report a problem in my area', 'Sewage, dumping, broken water points'),
	'flag_misinformation': ('Report something I heard', 'Help stop a rumour before it spreads'),
	'water_advisory': ('Is the water safe?', 'Boil-water advisories for your area'),
	'air_advisory': ('How is the air?', 'Air quality alerts where you live'),
	'vector_risk': ('Mosquito and vector risk', 'Seasonal risk from the rain you just had'),
	'nutrition': ('What should my child eat?', 'Age-appropriate feeding and local foods'),
	'issue_alert': ('School and public notices', 'Closures and official announcements'),
	'price_quote': ('What does it cost?', 'Typical prices per facility'),
	'data_inventory': ('What do you know about me?', 'Everything stored, and who it was shared with'),
	'delete_my_data': ('Delete my data', 'Remove what is yours; we tell you what must stay'),
	'access_profile': ('Make the app easier to use', 'Bigger text, simple mode, read aloud'),
	'voice': ('Speak to the app', 'Ask in your own language'),
}
