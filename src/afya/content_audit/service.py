"""Feature content audit — what each §8–§12 feature section says it does, against what does it.

The registry gate (`tests/ci/test_feature_coverage.py`) answers one question: can a client *reach*
this feature? It is a route check, and it is why 24 orphaned `/ops/*` endpoints were found. It says
nothing about whether the feature does what its section says — a feature can be registered,
reachable, tested, and missing half its own spec.

That is not hypothetical. §9.2's REC-001 was "reachable" the whole time and named eight wallet
contents of which one had no model at all. This module applies the same treatment to feature
sections' labelled content lists: `**Features:**`, `**Contents:**`, `**Additional inputs:**`,
`**Outputs:**` and `**Signals monitored:**`.

**Coverage is partial and the report says so.** §8–§12 print 292 labelled content items across 47
feature sections — the sections carrying a `**Features:**`-style list, counting each comma-separated
item of a prose cell (the spec writes these lists two ways, and §9.5 INF-007's Contents is one
sentence of six). Twenty are audited here: the four the section-number survey found named nowhere in
the source (§9.3 MED-004, §9.4 FND-006, §9.5 INF-007, §11.2 TRI-003), the nine §8 Tier-1 sections,
and the seven Tier-2 sections a person meets next (INF-004, INF-005, REC-001 and MON-001–004).
`audited_features` and `UNAUDITED_FEATURES` are served alongside the findings, because a report that
showed 74 gaps without saying how much of the spec it had read would invite the reader to take it as
complete — which is the failure mode of every gate that scopes itself.

**A bullet is carried when something in the repo does it.** `carried_by` is a `module:attr`
reference and `missing` is the finding, reported rather than repaired — whether an absent bullet is
a gap or a deliberate deferral is a product call, and a table that quietly resolved its own gaps
would be the failure it exists to catch.

**The three verdicts are not one list.** `carried` resolves to code. `deferred` is a bullet the
spec itself puts out of scope here (a `(see X)` cross-reference, or a clause conditional on
something that has not happened). `missing` is a bullet nothing does, and it is the only one that is
a finding. Merging them would report every cross-reference as a gap and bury the real ones.
"""
from afya.content_audit.views import ContentBullet, FeatureContent, FeatureContentReport
from afya.refs import resolves

# §8–§12's feature sections, each with its labelled content bullets in the section's order.
#
# Tuple shape: (feature_id, section_label, bullet, kind, ref, note)
#   kind='carried'  — ref names the code that does it
#   kind='deferred' — the bullet is a cross-reference or a conditional, and note says which
#   kind='missing'  — nothing does it, and note says what is absent
#
# Every bullet is transcribed verbatim from the section, so a revision that rewords one fails the
# spec-comparison test rather than silently detaching the audit from the text.
FEATURE_CONTENT: tuple[tuple[str, str, str, str, str | None, str | None], ...] = (
	# --- §8.1 TRI-001: Broad Febrile-Illness Triage -------------------------------------------
	('TRI-001', 'Outputs',
		'Risk classification: Emergency / High (Ebola suspicion) / High (other cause) / Moderate / Low',
		'missing', None,
		'`RiskLevel` has four members (low, medium, malaria_suspect, high) and none of them '
		'distinguishes "High (Ebola suspicion)" from "High (other cause)" — the distinction the '
		'section prints as two separate outputs'),
	('TRI-001', 'Outputs', 'Recommended action with one-tap execution (call 719, find facility, request CHW visit)',
		'missing', None,
		'`TriageResult.recommendation` is prose and `escalate_719` is a boolean; neither carries an '
		'action a client can execute in one tap'),
	('TRI-001', 'Outputs', 'Watch-for list for the next 24–48 hours', 'missing', None,
		'nothing carries a watch-for list'),
	('TRI-001', 'Outputs', 'Forwardable summary card', 'missing', None,
		'§3.3 principle 10 requires every output to be shareable as a WhatsApp card; no triage '
		'result has one'),

	# --- §8.1 TRI-002: Symptom Diary and Follow-Up --------------------------------------------
	('TRI-002', 'Features', 'Log symptoms with timestamp', 'carried',
		'afya.triage.service:TriageService.diary_append',
		'`DiaryEntry` has `day` and no clock; the timestamp is the day number'),
	('TRI-002', 'Features', 'Daily "how are you feeling?" prompt (opt-in)', 'missing', None,
		'nothing prompts; the diary is written only when the person opens it'),
	('TRI-002', 'Features', 'Automatic escalation if new red flags are logged', 'missing', None,
		'`diary_append` stores the entry and returns it — it reads no red flag and escalates nothing'),
	('TRI-002', 'Features', 'Trend view: is this getting better or worse?', 'missing', None,
		'`diary` returns the entries in order and computes no trend'),
	('TRI-002', 'Features', 'Exportable summary for a clinician', 'missing', None,
		'no export of any kind'),

	# --- §8.2 FND-001: Facility Finder --------------------------------------------------------
	('FND-001', 'Features', 'GPS-based nearest search', 'carried',
		'afya.facilities.service:FacilityService.nearest', None),
	('FND-001', 'Features', 'Search by area name or code', 'missing', None,
		'`NearestRequest` takes lat/lon only; there is no lookup by area name or code'),
	('FND-001', 'Features', 'Filter by service, level, cost, SHA acceptance', 'missing', None,
		'`NearestRequest.kind` filters by facility kind alone — not by service, level, cost or SHA'),
	('FND-001', 'Features', 'One-tap directions (opens maps app)', 'deferred', None,
		'opening a maps app is a client action with no server call, like the other device-side '
		'capabilities the coverage gate lists in ON_DEVICE'),
	('FND-001', 'Features', 'One-tap call', 'deferred', None, 'the device dials; there is no route to call'),
	('FND-001', 'Features',
		"Offline mode: caches facilities within 50 km of the user's home area",
		'missing', None,
		'the county cache caches by county, not by a 50 km radius of a home area'),

	# --- §8.2 FND-002: Emergency Department Status --------------------------------------------
	('FND-002', 'Features', 'ICU bed availability', 'missing', None,
		'`Facility` carries no bed counts of any kind'),
	('FND-002', 'Features', 'Emergency department queue status', 'carried',
		'afya.facilities.views:Facility', 'ed_status, crowdload and wait_minutes'),
	('FND-002', 'Features', 'Ambulance availability', 'missing', None, 'no ambulance field or service'),
	('FND-002', 'Features', 'Trauma capability', 'missing', None, 'no trauma-capability field'),
	('FND-002', 'Features', 'Isolation bed availability (Tier 4)', 'missing', None,
		'no isolation-bed field; §8.2 prints this as a Tier 4 row and nothing carries it at any tier'),

	# --- §8.2 FND-004: Pharmacy and Chemist Finder --------------------------------------------
	('FND-004', 'Features', 'Nearest registered pharmacies (PPB registry)', 'carried',
		'afya.facilities.views:FacilityKind', 'kind=pharmacy'),
	('FND-004', 'Features', 'Open now', 'carried', 'afya.facilities.views:Facility', 'open_now and hours24'),
	('FND-004', 'Features', 'Whether they accept SHA', 'missing', None,
		'`SHAClient` verifies cover for a member and nothing records which facilities accept it'),
	('FND-004', 'Features', 'Crowdsourced stock reports (see MED-004)', 'carried',
		'afya.medicine.service:MedicineService.stock_for', None),
	('FND-004', 'Features', 'One-tap call', 'deferred', None, 'the device dials; there is no route to call'),

	# --- §8.3 MED-001: Medicine Verifier ------------------------------------------------------
	('MED-001', 'Features', 'Barcode scan using the camera', 'deferred', None,
		'reading a barcode is a device capability; the number it yields is what `verify` takes'),
	('MED-001', 'Features', 'Manual entry of the PPB registration number', 'carried',
		'afya.medicine.service:MedicineService.verify', None),
	('MED-001', 'Features', 'Photo of packaging for batch verification (where supported)', 'missing', None,
		'`VerifyRequest` carries a `batch_number` and no photo; nothing ingests an image'),
	('MED-001', 'Features', 'Result: Registered / Not found / Expired registration / Recalled', 'missing', None,
		'`VerifyResult` is `genuine: bool` plus a free-text note, so the four named outcomes cannot '
		'be distinguished by a client — a recalled medicine and a not-found one read the same'),
	('MED-001', 'Features',
		'Display: product name, manufacturer, registration status, expiry, batch recalls',
		'missing', None,
		'`VerifyResult` carries none of the five display fields'),
	('MED-001', 'Features', '**Report a suspicious medicine** — one tap to flag to PPB', 'missing', None,
		'no report route to PPB exists; `medicine_recalls` reads the registry and reports nothing'),

	# --- §8.3 MED-002: Drug Interaction and Safety Checker ------------------------------------
	('MED-002', 'Features', 'Select or scan two or more medicines', 'carried',
		'afya.medicine.service:MedicineService.check_interactions', None),
	('MED-002', 'Features', 'Check for known interactions', 'carried',
		'afya.medicine.service:MedicineService.check_interactions', None),
	('MED-002', 'Features', 'Flag contraindications for pregnancy, children, and common conditions',
		'missing', None,
		'`_INTERACTIONS` is drug-pair rows only; there is no contraindication axis for pregnancy, '
		'age or a condition'),
	('MED-002', 'Features', 'Guidance to consult a pharmacist', 'missing', None,
		'the check returns severity strings and no guidance line'),

	# --- §8.3 MED-003: Dosage Calculator ------------------------------------------------------
	('MED-003', 'Features', 'Enter weight and age', 'missing', None,
		'`DoseRequest` carries `weight_kg` and no age'),
	('MED-003', 'Features', 'Select medicine', 'carried', 'afya.medicine.views:DoseRequest', 'drug'),
	('MED-003', 'Features', 'Get dose range', 'missing', None,
		'`dose` returns one `total_mg` computed from a caller-supplied mg/kg; there is no range and '
		'the caller supplies the very constant a calculator exists to look up'),
	('MED-003', 'Features',
		'Common paediatric formulations (paracetamol, amoxicillin, ORS, zinc, artemether-lumefantrine)',
		'missing', None, 'no formulation table'),
	('MED-003', 'Features', 'Warning for maximum doses', 'missing', None,
		'`warns` fires on weight < 5 kg and mg/kg > 60 — neither is a maximum-dose check'),

	# --- §8.4 EMG-001: Emergency SOS ----------------------------------------------------------
	('EMG-001', 'Features', 'Large, hard-to-mistap SOS button', 'deferred', None,
		'a button is the client surface; the call it makes is `/emergency/sos`'),
	('EMG-001', 'Features', 'Sends location and a preset message to up to three emergency contacts',
		'missing', None,
		'`SOSEvent` carries no contacts and `sos` notifies the hotline; the "three emergency '
		'contacts" the section names are not on the event'),
	('EMG-001', 'Features', 'Sends to the nearest ambulance dispatch where integrated', 'missing', None,
		'no ambulance dispatch integration'),
	('EMG-001', 'Features', '**Works over SMS when data is unavailable**', 'missing', None,
		'the SOS route is HTTP only; the `sms-contacts` action string is a label in `actions` and '
		'nothing sends one'),
	('EMG-001', 'Features', 'Countdown with cancel option (prevents accidental activation)', 'missing', None,
		'a countdown is client state; nothing on the server models the cancel window'),
	('EMG-001', 'Features',
		'Optional medical profile attachment (blood group, allergies, conditions, medications)',
		'carried', 'afya.emergency.views:EmergencyCard',
		'blood group, allergies and conditions are carried; medications is not a field'),
	('EMG-001', 'Features', 'Optional auto-dial of emergency services', 'deferred', None,
		'the device dials; `actions` names call-719 for the client to perform'),

	# --- §9.2 REC-001: Family Health Wallet (Basic) --------------------------------------------
	# The Contents list is audited here as well as in `afya.records.service:WALLET_ITEMS`, which
	# pairs the same eight bullets with their models. The two read the same section for different
	# questions — that one asks whether the wallet assembles what it claims, this one whether the
	# section's whole content list is carried — and the spec-comparison test keeps both honest.
	('REC-001', 'Contents', 'Immunisation cards (photo or digital)', 'carried',
		'afya.records.views:ImmunisationRecord',
		'the EPI schedule and the doses given are modelled; the card itself is not stored as an image'),
	('REC-001', 'Contents', 'ANC cards', 'carried', 'afya.maternal.views:ANCRecord',
		'the eight ANC contacts are modelled against the visit schedule'),
	('REC-001', 'Contents', 'Lab results', 'carried', 'afya.records.views:LabResult', None),
	('REC-001', 'Contents', 'Prescriptions', 'carried', 'afya.records.views:Prescription', None),
	('REC-001', 'Contents', 'Discharge summaries', 'missing', None,
		'no model anywhere; a discharge summary is a facility document and nothing ingests one'),
	('REC-001', 'Contents', 'Referral letters', 'carried', 'afya.intermediaries.views:Referral',
		'the referral is modelled for code attribution, not as a document in the wallet'),
	('REC-001', 'Contents', 'Insurance/SHA details', 'carried', 'afya.records.views:InsuranceCard',
		'the SHA member number is stored as a hash, so the card cannot be reconstructed from it'),
	('REC-001', 'Contents', 'Clinic appointment cards', 'carried', 'afya.facilities.views:Booking',
		'the booking is modelled; the card the facility prints is not stored'),
	('REC-001', 'Features', 'Multiple profiles (up to 10)', 'carried',
		'afya.records.service:MAX_WALLET_PROFILES',
		'enforced at enrolment: `add_member` refuses the eleventh profile for a guardian'),
	('REC-001', 'Features', 'Photo capture and storage', 'missing', None,
		'no document model carries an image or attachment field; `SyncService.image_budget` sizes an '
		'upload and nothing stores one'),
	('REC-001', 'Features', 'Offline access', 'missing', None,
		'nothing caches the wallet payload; `SyncService.offline_state` reports the write queue, and '
		'§15.2 records that the client caches the last good response in SharedPreferences — so the '
		'capability is on the device and not in this tree, the same place FND-001\'s offline mode is'),
	('REC-001', 'Features', 'Share via secure link or PDF export', 'missing', None,
		'`RetentionService.export` is §SEC-005\'s export of everything held about a subject; there is '
		'no wallet share link and no PDF renderer for a wallet document'),
	('REC-001', 'Features', 'Optional encrypted cloud backup', 'missing', None,
		'`cloud_backup` is a §SEC-001 consent category and `afya.retention.service` states '
		'`cloud_backup_e2e=True` as a design property; no code performs a backup'),
	('REC-001', 'Features', 'Search', 'missing', None,
		'`wallet` returns members and their immunisation gaps; there is no query across the documents'),

	# --- §9.3 MED-004: Drug Stock Crowdsourcing -----------------------------------------------
	('MED-004', 'Features', 'Search for a medicine', 'missing', None,
		'`stock_for` is keyed on (drug, facility) and needs both; there is no search across drugs'),
	('MED-004', 'Features', 'See recent reports ("available at [pharmacy], 2 hours ago")', 'missing', None,
		'`StockReport` carries no timestamp, so "2 hours ago" — the section\'s own example — cannot '
		'be rendered by any client'),
	('MED-004', 'Features', 'Report availability yourself (one tap)', 'carried',
		'afya.medicine.service:MedicineService.report_stock', None),
	('MED-004', 'Features', 'Flag stockouts', 'carried',
		'afya.medicine.views:StockReport', 'in_stock=False is the flag'),
	('MED-004', 'Features',
		'Essential medicines list prioritised (insulin, ARVs, TB drugs, oxytocin, malaria ACTs, ORS, zinc, contraceptives)',
		'missing', None, 'no essential-medicines constant anywhere in the repo'),
	('MED-004', 'Features', 'Alert when a previously out-of-stock medicine becomes available', 'missing', None,
		'nothing watches a transition from out-of-stock to in-stock'),

	# --- §9.4 FND-006: Appointment Booking and Queue Management -------------------------------
	('FND-006', 'Features', 'View available slots at participating facilities', 'missing', None,
		'`book` takes a `slot_iso` the caller supplies; nothing lists a facility\'s open slots'),
	('FND-006', 'Features', 'Book, reschedule, cancel', 'missing', None,
		'`book` exists; there is no reschedule and no cancel'),
	('FND-006', 'Features', 'Queue number and estimated wait time', 'carried',
		'afya.facilities.views:Booking', 'queue_position and wait_minutes'),
	('FND-006', 'Features', 'Check-in on arrival via QR code (see LOC-004)', 'carried',
		'afya.location.service:LocationService.check_in', None),
	('FND-006', 'Features', 'Reminder notifications', 'missing', None,
		'a booking has no reminder; `MedReminder` is the medication schedule, not an appointment'),

	# --- §9.5 INF-007: Service Status Feed ----------------------------------------------------
	('INF-007', 'Contents', 'School closures', 'carried', 'afya.alerts.views:AlertKind', None),
	('INF-007', 'Contents', 'border post status', 'carried',
		'afya.location.service:LocationService.border_status', None),
	('INF-007', 'Contents', 'market closures', 'missing', None, 'no market-closure status anywhere'),
	('INF-007', 'Contents', 'water interruptions', 'missing', None,
		'`water_quality` is a §10.2 MON-005 alert about safety, not a service interruption'),
	('INF-007', 'Contents', 'road closures affecting facility access', 'missing', None,
		'no road-closure status anywhere'),
	('INF-007', 'Contents', 'public transport disruptions', 'missing', None,
		'no transport-disruption status anywhere'),

	# --- §11.2 TRI-003: Ebola-Specific Triage -------------------------------------------------
	('TRI-003', 'Additional inputs',
		'Specific exposure history (funeral attendance, healthcare work, contact with a case, consumption of bushmeat)',
		'missing', None,
		'`TriageInput` carries one `ebola_contact` boolean; the four named exposures are not '
		'distinguished, so a funeral and a bushmeat exposure read the same'),
	('TRI-003', 'Additional inputs', 'Vaccination status (if a vaccine is available and deployed)', 'deferred', None,
		'the section conditions this on a vaccine being deployed, which is a fact about the world '
		'rather than about this tree — nothing here can carry it until one is'),
	('TRI-003', 'Additional inputs', 'Isolation status', 'missing', None,
		'`TriageResult` says "isolate immediately" as advice and carries no status input'),
	('TRI-003', 'Outputs', 'Ebola suspicion classification', 'carried',
		'afya.triage.service:TriageService.assess_evd', None),
	('TRI-003', 'Outputs',
		'Immediate action (call 719, do not travel by public transport, await instructions)',
		'missing', None,
		'the high-risk recommendation names 719 and isolation but not the transport instruction'),
	('TRI-003', 'Outputs', 'Isolation guidance for the household', 'missing', None,
		'`JOB_AIDS["isolation_basics"]` is CHW-facing reference material, not an output of triage'),
	('TRI-003', 'Outputs', 'Contact list building (see COM-103)', 'carried',
		'afya.community.service:CommunityService.add_contact', None),

	# --- §10.1 INF-004: Myth-Busting Library ---------------------------------------------------
	# The section's own format is "Rumour: [claim]. Fact: [correction]. Source: [authority]." — three
	# parts, and the model carries a title and a body. That is why the library cannot be searched by
	# claim and why a source is a free-text tag rather than a named authority.
	('INF-004', 'Features', 'Search', 'missing', None,
		'`InfoService.library` filters by language and stage and returns the whole corpus; there is '
		'no query over title or body, and no index'),
	('INF-004', 'Features', 'Browse by category', 'missing', None,
		'`ContentItem.harmony_tag` is the only grouping key and it is not served as a facet — '
		'`/info/library` returns a flat list, so a client cannot render a category list'),
	('INF-004', 'Features', '"Ask about a rumour" — submit a claim for verification', 'missing', None,
		'`CommunityService.flag_misinfo` takes a `MisinfoSubmission` with a claim, county and medium '
		'and returns a cluster; nothing accepts a claim *for verification* and returns a correction '
		'to the person who asked'),
	('INF-004', 'Features', 'Shareable as a card', 'missing', None,
		'§3.3 principle 10 requires every output to be shareable as a WhatsApp card; `/info/library` '
		'serves `{slug,title,body,harmony_tag}` and nothing renders a card'),

	# --- §10.1 INF-005: Travel Advisory --------------------------------------------------------
	('INF-005', 'Features', 'Country and county advisories', 'missing', None,
		'`LocationService.advisory(destination, origin_country)` returns one fixed paragraph for '
		'any pair, so the country half is a constant rather than a table; the county half has no '
		'carrier at all'),
	('INF-005', 'Features', 'Border point status and wait times', 'carried',
		'afya.location.views:BorderPost', 'queue_minutes and screening_required, read via border_status'),
	('INF-005', 'Features', 'Screening requirements', 'carried',
		'afya.location.views:BorderPost', 'screening_required'),
	('INF-005', 'Features', 'What to do if you feel unwell after travel', 'carried',
		'afya.location.service:LocationService.advisory',
		'one fixed sentence — "call 719 and say where you travelled"; `self_declare` logs symptoms '
		'declared on arrival, so the path exists and the guidance is a constant'),
	('INF-005', 'Features', '21-day self-monitoring enrolment for travellers (links to MON-009)',
		'carried', 'afya.location.service:LocationService.self_declare',
		'the 21 days and the day 1/3/7/14/21 schedule are carried; the link is a message string, so '
		'the enrolment does not reach `MonitoringService.enrol` and the diary stays empty'),

	# --- §10.2 MON-001: Child Immunisation Tracker ---------------------------------------------
	('MON-001', 'Features', 'Add children with date of birth', 'carried',
		'afya.monitoring.service:MonitoringService.register_child', None),
	('MON-001', 'Features',
		'Automatic schedule generation (BCG, OPV, Pentavalent, PCV, Rotavirus, Measles-Rubella, Yellow Fever where relevant, HPV for girls)',
		'carried', 'afya.monitoring.views:EPI_DUE_WEEKS',
		'all nine named vaccines are rows; the section spells two of them differently ("Pentavalent" '
		'is `DPT-HepB-Hib`, "Rotavirus" is `RV`)'),
	('MON-001', 'Features', 'Reminders 3 days and 1 day before due date', 'carried',
		'afya.monitoring.views:REMINDER_LEAD_DAYS', '`schedule` fills `remind_days_before` from it'),
	('MON-001', 'Features', 'Record doses given (with photo of card)', 'missing', None,
		'`record_dose` takes the vaccine, dose number and date; there is no image field on '
		'`ImmunisationRecord` and nothing stores a photo'),
	('MON-001', 'Features', 'Catch-up schedule for defaulters', 'carried',
		'afya.monitoring.service:MonitoringService.catch_up', None),
	('MON-001', 'Features', 'Missed-dose alerts', 'missing', None,
		'`schedule` marks a dose `overdue` and `catch_up` names it; nothing raises an alert, and '
		'`immunisation_reminders` is a §9.6 toggle no producer ever publishes under'),
	('MON-001', 'Features', 'Facility finder integration for vaccination points', 'carried',
		'afya.places.views:PlacesService.nearest',
		'the kind exists and `/places/vaccination-points` serves it; the immunisation schedule does '
		'not call it, so the client has to join the two itself'),
	('MON-001', 'Features', 'Campaign notifications (polio, measles)', 'missing', None,
		'no campaign notice is produced anywhere; the feed has no immunisation category and '
		'`AlertKind` carries neither polio nor a campaign type'),
	('MON-001', 'Features', 'Shareable immunisation record', 'missing', None,
		'`immunisation_gaps` returns the doses outstanding and there is no shareable record of the '
		'doses given'),

	# --- §10.2 MON-002: Pregnancy and Antenatal Care Tracker -----------------------------------
	('MON-002', 'Features', 'Estimated due date calculator', 'missing', None,
		'`Pregnancy.edd_iso` is an input the caller computes; there is no calculator from an LMP '
		'date, and `lmp_week` is a week count rather than a date to compute from'),
	('MON-002', 'Features', 'WHO/Kenya ANC visit schedule (8 contacts)', 'carried',
		'afya.maternal.views:ANC_CONTACTS_WEEKS', '8 contacts at 12/20/26/30/34/36/38/40 weeks'),
	('MON-002', 'Features', 'Visit reminders', 'missing', None,
		'`anc_due` returns the contact numbers outstanding; nothing schedules a reminder, and there '
		'is no antenatal category in the alert preferences'),
	('MON-002', 'Features', 'Danger sign education and one-tap escalation', 'missing', None,
		'`assess_danger` classifies and writes a message; the escalation is the message text, and '
		'there is no action a client can execute in one tap'),
	('MON-002', 'Features', 'Birth plan builder (facility, transport, birth companion, blood donor, funds)',
		'missing', None,
		'`delivery_plan` returns the facility and the EDD; transport, birth companion, blood donor '
		'and funds are five named fields of which one exists'),
	('MON-002', 'Features', 'Trimester-specific guidance', 'missing', None,
		'nothing in `afya.maternal` varies by trimester; `ANC_CONTACTS_WEEKS` places the visits and '
		'the guidance is the same at week 12 and week 40'),
	('MON-002', 'Features', 'Postnatal visit reminders', 'missing', None,
		'`Pregnancy` ends at the EDD and `ANC_CONTACTS_WEEKS` stops at 40; there is no postnatal '
		'contact, so there is nothing to remind about'),
	('MON-002', 'Features', 'Newborn danger signs', 'missing', None,
		'`DANGER_SIGNS` is nine maternal signs and none of them is a newborn sign; `GrowthRecord` '
		'tracks weight and height and flags stunting, not danger'),
	('MON-002', 'Features', 'Facility finder for maternity services', 'missing', None,
		'`FacilityKind` has five members and no maternity or delivery kind, so no route can filter '
		'for one; `PlaceKind` has eight and none of them either'),
	('MON-002', 'Features', 'Referral to PMTCT where relevant', 'missing', None,
		'no PMTCT reference exists anywhere in the tree'),

	# --- §10.2 MON-003: Chronic Disease Log ----------------------------------------------------
	('MON-003', 'Features', 'Log readings (BP, blood sugar, peak flow, weight)', 'carried',
		'afya.chronic.service:ChronicService.bp', '`glucose`, `log_peak_flow` and `log_weight` too'),
	('MON-003', 'Features', 'Trend charts', 'missing', None,
		'`bp_trend` returns a one-line direction and there is no series for glucose, peak flow or '
		'weight; no route serves a chart'),
	('MON-003', 'Features', 'Medication reminders', 'carried',
		'afya.monitoring.views:MedSchedule',
		'`times_per_day` and `duration_days` are the schedule; the section lists this under MON-003 '
		'and the model is MON-004\'s, so the two sections share one carrier'),
	('MON-003', 'Features', 'Refill reminders', 'carried',
		'afya.chronic.service:ChronicService.set_refill', '`refill_due` at seven days remaining'),
	('MON-003', 'Features', 'Appointment tracking', 'missing', None,
		'`Booking` is a facility slot with a queue position; it is not attached to a condition '
		'profile and no route lists a subject\'s appointments'),
	('MON-003', 'Features', 'Lifestyle guidance', 'missing', None,
		'nothing in `afya.chronic` varies by condition; the condition list is carried and no '
		'guidance keys on it'),
	('MON-003', 'Features', 'Shareable reports for clinicians', 'carried',
		'afya.monitoring.service:MonitoringService.shareable_report',
		'the report withholds HIV unless separately consented'),
	('MON-003', 'Features', 'Danger thresholds with escalation', 'carried',
		'afya.chronic.views:BPReading.stage',
		'`stage`, `level` and `ALERT_LIMITS` set the thresholds; escalation is a `_log_warn`, which '
		'is a server log and not a message to anyone'),

	# --- §10.2 MON-004: Medication Reminders ---------------------------------------------------
	('MON-004', 'Features', 'Add medication, dose, frequency, duration', 'carried',
		'afya.monitoring.views:MedSchedule', 'drug, dose, times_per_day and duration_days'),
	('MON-004', 'Features', 'Multiple daily reminders', 'missing', None,
		'`times_per_day` is a count, not a list of times; no reminder instant is carried anywhere'),
	('MON-004', 'Features', 'Mark as taken / skipped / snooze', 'carried',
		'afya.monitoring.views:AdherenceAction', 'taken, skipped, snoozed'),
	('MON-004', 'Features', 'Adherence history', 'carried',
		'afya.monitoring.service:MonitoringService.adherence',
		'counts by action over the schedule; `record_adherence` keeps the events'),
	('MON-004', 'Features', 'Refill alerts when supply is running low', 'carried',
		'afya.monitoring.views:MedSchedule',
		'`adherence` raises `refill_due` from it'),
	('MON-004', 'Features', 'Support for multiple family members', 'carried',
		'afya.monitoring.views:MedSchedule',
		'keyed per member; the route binds the member to the caller\'s own wallet'),
	('MON-004', 'Features', 'Works with no data connection', 'missing', None,
		'`/monitoring/medication` and `/monitoring/medication/adherence` are HTTP routes; '
		'`SyncService` has a `medication` conflict rule and nothing queues a dose through it'),
)

_LABELS: tuple[str, ...] = ('Features', 'Contents', 'Additional inputs', 'Outputs', 'Signals monitored')

# §8–§12's feature sections that carry a labelled content list and are not audited above. Listed
# rather than omitted so the report cannot be read as covering the spec: 292 such items across 47
# sections, and a finding list presented without that context invites exactly the misreading this
# module exists to prevent. Each is a section whose content nobody has crossed against the code yet
# — a to-do with a count, not a claim of coverage.
UNAUDITED_FEATURES: tuple[str, ...] = (
	'FND-003', 'FND-005', 'EMG-003', 'INF-006',
	'MON-005', 'MON-006', 'MON-007', 'MON-008',
	'REC-003', 'REC-004', 'REC-005', 'REC-006',
	'ALT-001', 'ALT-002', 'MON-009',
	'COM-101', 'COM-102', 'COM-103', 'COM-104',
	'LOC-005', 'AI-001', 'AI-003',
	'ACC-001', 'ACC-002', 'SEC-001', 'SEC-004', 'SEC-006',
)

assert not (set(UNAUDITED_FEATURES) & {f for f, _, _, _, _, _ in FEATURE_CONTENT}), \
	'a feature is either audited or listed as unaudited, never both'

assert all(kind in ('carried', 'deferred', 'missing') for _, _, _, kind, _, _ in FEATURE_CONTENT), \
	'every bullet has one of the three verdicts'
assert all(ref for _, _, _, kind, ref, _ in FEATURE_CONTENT if kind == 'carried'), \
	'a carried bullet must name the code that carries it'
assert all(note for _, _, _, kind, _, note in FEATURE_CONTENT if kind != 'carried'), \
	'a deferred or missing bullet must say why'
assert all(label in _LABELS for _, label, _, _, _, _ in FEATURE_CONTENT), \
	'every label is one of the five the spec uses'


def content_report() -> FeatureContentReport:
	"""Every audited feature section, its bullets, and the three verdicts separated.

	`missing` is the finding and it is reported, not repaired: whether an absent bullet is a gap or
	a deliberate deferral is a product decision. `unresolved` is a different finding — a `carried`
	reference that does not import is a bullet whose carrier rotted, not one nobody built.
	"""
	features: list[FeatureContent] = []
	for feature_id in dict.fromkeys(f for f, _, _, _, _, _ in FEATURE_CONTENT):
		bullets = [
			ContentBullet(label=label, bullet=bullet, kind=kind, carried_by=ref,
				resolves=resolves(ref) if ref else False, note=note)
			for f, label, bullet, kind, ref, note in FEATURE_CONTENT if f == feature_id
		]
		features.append(FeatureContent(
			feature_id=feature_id, bullets=bullets,
			missing=[b.bullet for b in bullets if b.kind == 'missing'],
			carried_count=sum(1 for b in bullets if b.kind == 'carried'),
		))
	return FeatureContentReport(
		features=features,
		missing=[f'§{f.feature_id}: {m}' for f in features for m in f.missing],
		unresolved=[f'§{f.feature_id}: {b.carried_by}' for f in features for b in f.bullets
			if b.carried_by and not b.resolves],
		audited_features=len(features),
		unaudited_features=list(UNAUDITED_FEATURES),
	)
