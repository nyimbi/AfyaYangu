"""Server-driven mobile action catalogue — the generic mechanism that exposes ALL backend features ergonomically.

GET /mobile/actions returns every usable action (id, title, group, method, path, fields);
a field is {name,label,type,options,placeholder} with type in:
	text, int, decimal, bool, select, textarea, list (comma text -> array), file, path (URL path param).
Apps render one generic form per action — no per-feature code, no app release needed to add features.
"""
from typing import Literal, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, Field

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
	method: Literal['GET', 'POST']
	path: str  # may contain {placeholders} backed by type='path' fields
	fields: list[MobileField] = []


BLOOD_GROUPS = ['O-', 'O+', 'A-', 'A+', 'B-', 'B+', 'AB-', 'AB+']
SENS_KINDS = ['respiration', 'cough', 'fall', 'ppg', 'sleep', 'ambient']
ALERT_KINDS = ['outbreak_cholera', 'outbreak_malaria', 'outbreak_dengue', 'outbreak_mpox', 'outbreak_rvf', 'outbreak_evd', 'flood', 'water_quality', 'school_closure', 'public_health_notice']
SYNC_DATASETS = ['symptom_logs', 'temperature', 'case_reports', 'immunisation', 'medication', 'facility', 'content', 'proximity_tokens']
PROCEDURES = ['c_section', 'normal_delivery', 'outpatient', 'inpatient_day', 'dialysis', 'x_ray', 'theatre']
FACILITY_KINDS = ['treatment_unit', 'ed', 'testing_site', 'pharmacy', 'vaccination_point']


def catalogue() -> list[MobileAction]:
	def f(name: str, label: str, type_: str = 'text', options: list[str] | None = None, ph: str | None = None) -> MobileField:
		return MobileField(name=name, label=label, type=cast(FieldType, type_), options=options, placeholder=ph, required=type_ == 'path')

	def a(id: str, title: str, group: str, method: str, path: str, fields: list[MobileField]) -> MobileAction:
		assert method in ('GET', 'POST') and all(fl.type in FIELD_TYPES for fl in fields), 'contract'
		return MobileAction(id=id, title=title, group=group, method=method, path=path, fields=fields)

	triage_fields = [f('symptoms', 'Symptoms (comma separated)', 'list', ph='fever, headache'), f('temperature_c', 'Temperature °C', 'decimal'), f('ebola_contact', 'Contact with EVD patient?', 'bool')]
	return [
		a('TRI-001', 'Febrile triage', 'Triage', 'POST', '/triage/preliminary', triage_fields),
		a('TRI-003', 'EVD-specific triage', 'Triage', 'POST', '/triage/evd', triage_fields),
		a('DIAG', 'Full differential diagnosis', 'Triage', 'POST', '/triage/diagnose', triage_fields),
		a('TRI-002', 'Log diary day', 'Triage', 'POST', '/triage/diary', [f('entry_id', 'Entry ID', ph='DIARY-...'), f('subject_ref', 'Subject ref'), f('day', 'Day (1-21)', 'int'), f('symptoms', 'Symptoms', 'list'), f('temperature_c', 'Temp °C', 'decimal')]),
		a('FND-001', 'Nearest facilities', 'Facilities', 'POST', '/facilities/nearest', [f('lat', 'Latitude', 'decimal'), f('lon', 'Longitude', 'decimal'), f('kind', 'Type', 'select', FACILITY_KINDS), f('limit', 'Limit', 'int')]),
		a('FND-002', 'Emergency dept status', 'Facilities', 'GET', '/facilities/{facility_id}/ed-status', [f('id', 'Facility ID', 'path')]),
		a('FND-004W', 'Report wait time', 'Facilities', 'POST', '/facilities/{facility_id}/wait', [f('id', 'Facility ID', 'path'), f('minutes', 'Minutes', 'int')]),
		a('FND-006', 'Book appointment', 'Facilities', 'POST', '/facilities/{facility_id}/booking', [f('id', 'Facility ID', 'path'), f('booking_id', 'Booking ID', ph='BOOK-...'), f('slot_iso', 'Slot ISO time')]),
		a('MED-001', 'Verify medicine', 'Medicine', 'POST', '/medicine/verify', [f('batch_number', 'Batch number'), f('gtin', 'GTIN barcode')]),
		a('MED-002', 'Drug interactions', 'Medicine', 'POST', '/medicine/interactions', [f('drugs', 'Drugs (comma separated)', 'list')]),
		a('MED-003', 'Dosage calculator', 'Medicine', 'POST', '/medicine/dose', [f('drug', 'Drug'), f('weight_kg', 'Weight kg', 'decimal'), f('mg_per_kg', 'mg/kg', 'decimal')]),
		a('MED-004', 'Report drug stock', 'Medicine', 'POST', '/medicine/stock', [f('report_id', 'Report ID', ph='STOCK-...'), f('facility_id', 'Facility ID'), f('drug', 'Drug'), f('in_stock', 'In stock?', 'bool')]),
		a('EMG-001', 'Emergency SOS', 'Emergency', 'POST', '/emergency/sos', [f('sos_id', 'SOS ID', ph='SOS-...'), f('lat', 'Latitude', 'decimal'), f('lon', 'Longitude', 'decimal'), f('severity', 'Severity', 'select', ['low', 'medium', 'high']), f('symptoms', 'Symptoms', 'list')]),
		a('EMG-003', 'Offline emergency card QR', 'Emergency', 'POST', '/emergency/card/qr', [f('name', 'Full name'), f('blood_group', 'Blood group', 'select', BLOOD_GROUPS), f('allergies', 'Allergies', 'list'), f('conditions', 'Conditions', 'list'), f('emergency_contact', 'Emergency contact')]),
		a('REC-001G', 'Immunisation gaps', 'Records', 'GET', '/records/{member_ref}/immunisation-gaps', [f('ref', 'Member ref', 'path')]),
		a('REC-001W', 'Family wallet', 'Records', 'GET', '/records/{guardian_ref}/wallet', [f('ref', 'Guardian ref', 'path')]),
		a('REC-003', 'Growth flag', 'Records', 'POST', '/records/growth', [f('member_ref', 'Member ref'), f('age_months', 'Age months', 'int'), f('weight_kg', 'Weight kg', 'decimal'), f('height_cm', 'Height cm', 'decimal')]),
		a('REC-007L', 'Add lab result', 'Records', 'POST', '/records/labs', [f('member_ref', 'Member ref'), f('test', 'Test', 'select', ['mRDT', 'widal', 'hba1c', 'fbc', 'viral_load', 'glucose_f', 'bp', 'other']), f('value', 'Value'), f('unit', 'Unit', ph='optional'), f('flag', 'Flag', 'select', ['normal', 'abnormal', 'critical', 'unknown']), f('performed_iso', 'Performed date ISO')]),
		a('REC-007V', 'View lab results', 'Records', 'GET', '/records/{ref}/labs', [f('ref', 'Member ref', 'path')]),
		a('REC-009L', 'Log cycle start', 'Women', 'POST', '/women/cycle', [f('subject_ref', 'Subject ref'), f('start_iso', 'Period start date'), f('cycle_days', 'Cycle length days', 'int'), f('pain_level', 'Pain level (0-10)', 'int')]),
		a('REC-009P', 'Cycle prediction', 'Women', 'GET', '/women/cycle/{ref}/predict', [f('ref', 'Subject ref', 'path')]),
		a('REC-008P', 'Register pregnancy', 'Maternal', 'POST', '/maternal/pregnancy', [f('subject_ref', 'Subject ref'), f('edd_iso', 'EDD ISO date'), f('lmp_week', 'Gestation week', 'int'), f('delivery_plan_facility_id', 'Delivery facility ID', ph='optional')]),
		a('REC-008D', 'ANC contacts due', 'Maternal', 'GET', '/maternal/{ref}/anc-due', [f('ref', 'Subject ref', 'path'), f('gest_week', 'Gestation week', 'int')]),
		a('REC-008A', 'Record ANC visit', 'Maternal', 'POST', '/maternal/anc', [f('subject_ref', 'Subject ref'), f('contact_no', 'Contact no (1-8)', 'int'), f('done_iso', 'Done date')]),
		a('REC-008S', 'Danger signs check', 'Maternal', 'POST', '/maternal/danger', [f('signs', 'Danger signs', 'list', ph='bleeding, severe_headache')]),
		a('REC-006B', 'Log blood pressure', 'Chronic', 'POST', '/chronic/bp', [f('subject_ref', 'Subject ref'), f('systolic', 'Systolic', 'int'), f('diastolic', 'Diastolic', 'int'), f('pulse', 'Pulse', 'int')]),
		a('REC-006G', 'Log blood glucose', 'Chronic', 'POST', '/chronic/glucose', [f('subject_ref', 'Subject ref'), f('mmol_l', 'mmol/L', 'decimal'), f('fasting', 'Fasting?', 'bool')]),
		a('REC-006T', 'BP trend', 'Chronic', 'GET', '/chronic/{ref}/bp-trend', [f('ref', 'Subject ref', 'path')]),
		a('REC-006R', 'Track refill', 'Chronic', 'POST', '/chronic/refill', [f('subject_ref', 'Subject ref'), f('drug', 'Drug'), f('days_remaining', 'Days of medicine left', 'int')]),
		a('REC-005W', 'Well-being check (WHO-5)', 'Mental', 'POST', '/mental/who5', [f('subject_ref', 'Subject ref'), f('s1', 'Q1 0-5', 'int'), f('s2', 'Q2 0-5', 'int'), f('s3', 'Q3 0-5', 'int'), f('s4', 'Q4 0-5', 'int'), f('s5', 'Q5 0-5', 'int')]),
		a('REC-005L', 'Counselling lines', 'Mental', 'GET', '/mental/lines', []),
		a('REC-004D', 'Register as donor', 'Blood', 'POST', '/blood/donors', [f('donor_ref', 'Donor ref'), f('blood_group', 'Blood group', 'select', BLOOD_GROUPS), f('county', 'County'), f('last_donation_iso', 'Last donation date', ph='optional')]),
		a('REC-004M', 'Find donors', 'Blood', 'POST', '/blood/match', [f('request_id', 'Request ID'), f('blood_group', 'Group needed', 'select', BLOOD_GROUPS), f('county', 'County'), f('urgency', 'Urgency', 'select', ['routine', 'urgent', 'critical'])]),
		a('AL-NEW', 'Issue community alert', 'Alerts', 'POST', '/alerts', [f('alert_id', 'Alert ID', ph='AL-...'), f('kind', 'Kind', 'select', ALERT_KINDS), f('county', 'County'), f('headline', 'Headline'), f('body', 'Body', 'textarea'), f('issued_by', 'Issuer', 'select', ['PHEOC', 'MoH', 'County', 'KMD'])]),
		a('AL-LIST', 'Alerts by county', 'Alerts', 'GET', '/alerts/{county}', [f('county', 'County', 'path')]),
		a('INF-011', 'Water advisory', 'Environment', 'POST', '/environment/water', [f('county', 'County'), f('ecoli', 'E. coli detected?', 'bool'), f('turbidity_ntu', 'Turbidity NTU', 'decimal')]),
		a('INF-012', 'Air advisory', 'Environment', 'POST', '/environment/air', [f('county', 'County'), f('pm25', 'PM2.5 µg/m³', 'decimal')]),
		a('INF-013', 'Flood + cholera risk', 'Environment', 'POST', '/environment/flood', [f('county', 'County'), f('rainfall_mm_72h', 'Rainfall mm/72h', 'decimal'), f('population_at_risk', 'People at risk', 'int')]),
		a('INF-016P', 'File a price', 'Insurance', 'POST', '/insurance/prices', [f('facility_id', 'Facility ID'), f('procedure', 'Procedure', 'select', PROCEDURES), f('kes', 'Cost KES', 'int'), f('sha_covered', 'SHA covered?', 'bool')]),
		a('INF-016Q', 'Get a price quote', 'Insurance', 'GET', '/insurance/quote/{facility_id}/{procedure}', [f('facility_id', 'Facility ID', 'path'), f('procedure', 'Procedure', 'path')]),
		a('SHA-C1', 'Check SHA cover', 'Insurance', 'POST', '/insurance/sha-check', [f('member_no', 'SHA member number')]),
		a('CHW-NEW', 'Assign CHW task', 'Channels', 'POST', '/channels/chw/tasks', [f('task_id', 'Task ID'), f('chw_ref', 'CHW ref'), f('community', 'Community'), f('kind', 'Kind', 'select', ['followup', 'referral', 'sensitisation'])]),
		a('CHW-LIST', 'CHW open tasks', 'Channels', 'GET', '/channels/chw/tasks/{chw_ref}', [f('ref', 'CHW ref', 'path')]),
		a('CHW-DONE', 'Complete CHW task', 'Channels', 'POST', '/channels/chw/tasks/{task_id}/done', [f('id', 'Task ID', 'path')]),
		a('SMS-OUT', 'Send zero-rated SMS', 'Channels', 'POST', '/channels/sms', [f('to_msisdn', 'To (+254...)'), f('body', 'Message (max 1600)')]),
		a('WA-OUT', 'WhatsApp send', 'Channels', 'POST', '/channels/whatsapp', [f('from_msisdn', 'From (+254...)'), f('body', 'Message')]),
		a('SYNC-Q', 'Queue offline op', 'Sync', 'POST', '/sync/ops', [f('op_id', 'Op ID', ph='OP-...'), f('dataset', 'Dataset', 'select', SYNC_DATASETS), f('client_ts', 'Client timestamp ms', 'int')]),
		a('SYNC-F', 'Flush sync queue', 'Sync', 'POST', '/sync/flush', []),
		a('PRIV-C', 'Record consent', 'Privacy', 'POST', '/privacy/consent', [f('subject_ref', 'Subject ref'), f('purpose', 'Purpose'), f('data_types', 'Data types', 'list'), f('retention_days', 'Retention days (max 730)', 'int'), f('legal_basis', 'Legal basis', 'select', ['consent', 'legal_obligation', 'legitimate_interest'])]),
		a('PRIV-D', 'Run DPIA check', 'Privacy', 'POST', '/privacy/dpia', [f('sensitiveData', 'Sensitive health data?', 'bool'), f('automatedDecisions', 'Automated decisions?', 'bool'), f('crossBorderTransfer', 'Cross-border transfer?', 'bool'), f('childrenData', "Children's data?", 'bool'), f('proximity_logging', 'Proximity logging?', 'bool')]),
		a('SENS-ING', 'Sensor ingest (derived only)', 'Sensors', 'POST', '/sensors/ingest', [f('kind', 'Kind', 'select', SENS_KINDS), f('subject_ref', 'Subject ref'), f('value', 'Value', 'decimal'), f('county', 'County')]),
		a('SENS-002M', 'Analyse cough audio', 'Sensors', 'POST', '/ml/cough/analyze', [f('file', 'WAV file (16 kHz mono)', 'file')]),
		a('SENS-004M', 'Submit photo evidence + note', 'Sensors', 'POST', '/evidence', [f('file', 'Photo (jpeg/webp/png)', 'file'), f('kind', 'Kind', 'select', ['rash', 'red_eye', 'pallor', 'scene_photo']), f('note', 'What did you observe?', 'textarea')]),
		a('T4-ON', 'Activate Tier 4 (official)', 'Outbreak', 'POST', '/tier4/activate', [f('authorized_by_pheoc', 'PHEOC authorized?', 'bool'), f('dpia_reviewed', 'DPIA reviewed?', 'bool'), f('flag_enabled', 'Flag enabled?', 'bool')]),
	]