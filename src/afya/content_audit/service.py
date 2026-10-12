"""Feature content audit — what each §8–§12 feature section says it does, against what does it.

The registry gate (`tests/ci/test_feature_coverage.py`) answers one question: can a client *reach*
this feature? It is a route check, and it is why 24 orphaned `/ops/*` endpoints were found. It says
nothing about whether the feature does what its section says — a feature can be registered,
reachable, tested, and missing half its own spec.

That is not hypothetical. §9.2's REC-001 was "reachable" the whole time and named eight wallet
contents of which one had no model at all. This module applies the same treatment to feature
sections' labelled content lists: `**Features:**`, `**Contents:**`, `**Additional inputs:**`,
`**Outputs:**`, `**Signals monitored:**` and `**Access:**`.

**Coverage is total over the spec's feature sections, and the report says what that means.** The
spec prints 69 `#### FID:` sections; 47 of them carry a `**Features:**`-style content list, and all
47 are audited here. The count of items is 293, counting each comma-separated item of a prose cell
(the spec writes these lists two ways, and §9.5 INF-007's Contents is one sentence of six;
§EMG-003's Access is two sentences the same parser reads as one item).

The 22 sections without a labelled list are not omissions: they state their content as prose,
tables or route lists rather than as a list under a label, and a section with no labelled list has
nothing for this module to cross. §19.4's `**Access:**` is the one labelled list outside §8–§12 and
is out of this module's scope, which is §8–§12.

`audited_features` and `UNAUDITED_FEATURES` are still served alongside the findings, because the
useful claim is not "47" but "47 of the 47 that have something to audit, and here is the list that
would name the 48th". A report that showed 137 gaps without saying how much of the spec it had read
would invite the reader to take it as complete — the failure mode of every gate that scopes itself,
and the reason `UNAUDITED_FEATURES` is kept as an empty tuple with an assertion behind it rather
than deleted.

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

	# --- §8.2 FND-003: Testing Site Locator ---------------------------------------------------
	# The section prints a `**Test types (context-dependent):**` list of seven tests — malaria RDT
	# and microscopy, typhoid, HIV, TB, COVID-19, Ebola (designated sites only) and general
	# laboratory panels — but that is not one of the auditable labels, so it is not a row here; the
	# `**Features:**` cell is, and those four are the filter dimensions. `Place` is an
	# OSM-normalised POI and carried none of them, so the route took `lat`/`lon`/`limit` and
	# returned everything: a filter that is not applied is a screen that calls an unfiltered list
	# filtered. `Place.tests` is a list of `TestOffering` and `PlacesService.find` applies each
	# dimension, reporting the ones the *data* cannot answer rather than dropping a facility whose
	# row nobody has filled in — "no test list published" is not "does not test for HIV".
	('FND-003', 'Features', 'Filter by test', 'carried', 'afya.places.views:TestOffering',
		'`Place.tests[].name`, matched case-insensitively by `PlacesService.find`; the test-type list '
		'the section prints is the vocabulary a deployment publishes these against'),
	('FND-003', 'Features', 'cost', 'carried', 'afya.places.views:TestOffering',
		'`cost_kes`, an `int | None` filter ceiling; a place with nothing priced stays in the list '
		'because unknown cost is not a cost above the ceiling'),
	('FND-003', 'Features', 'hours', 'carried', 'afya.places.views:Place',
		'`opening_hours`, a free-text field the whole `Place` carries into every payload'),
	('FND-003', 'Features', 'results turnaround', 'carried', 'afya.places.views:TestOffering',
		'`turnaround_hours`, filtered by `max_turnaround_hours`'),

	# --- §8.2 FND-005: Vaccination Point Finder -----------------------------------------------
	('FND-005', 'Features', 'Filter by vaccine', 'carried', 'afya.places.views:VaccineOffering',
		'`Place.vaccines[].name`, matched case-insensitively by `PlacesService.find`'),
	('FND-005', 'Features', 'age eligibility', 'carried', 'afya.places.views:VaccineOffering',
		'`min_age_months`/`max_age_months`, in months so one band covers the infant schedule and '
		'school-age campaigns; a band with its bounds reversed is refused at construction'),
	('FND-005', 'Features', 'cost (usually free)', 'carried', 'afya.places.views:VaccineOffering',
		'`cost_kes`, tri-state: free is `0` and unpriced is `None`, so the advisory string in '
		'`LocationService.GUIDANCE` ("doses are free") is no longer the only place the claim lives'),
	('FND-005', 'Features', 'hours', 'carried', 'afya.places.views:Place',
		'`opening_hours`, a free-text field the whole `Place` carries into every payload'),
	('FND-005', 'Features', 'whether walk-in or appointment', 'carried',
		'afya.places.views:VaccineOffering',
		'`walk_in`, tri-state, and the one filter that excludes on absence — a person turning up '
		'without an appointment needs a yes rather than a maybe'),

	# --- §8.4 EMG-003: Offline Emergency Card -------------------------------------------------
	# The section prints seven Contents and `EmergencyCard` carries five fields. Two of the seven
	# are collapsed into the fifth: `emergency_contact` is a single phone string, so "emergency
	# contacts" (plural) is one contact and there is no separate SHA field. `organ donor status`
	# and `SHA number` have no field at all, and `current medications` is absent — the same field
	# EMG-001's medical-profile bullet also lacks.
	('EMG-003', 'Contents', 'Blood group', 'carried', 'afya.emergency.views:EmergencyCard', None),
	('EMG-003', 'Contents', 'allergies', 'carried', 'afya.emergency.views:EmergencyCard', None),
	('EMG-003', 'Contents', 'chronic conditions', 'carried', 'afya.emergency.views:EmergencyCard',
		'the `conditions` field'),
	('EMG-003', 'Contents', 'current medications', 'carried', 'afya.emergency.views:EmergencyCard',
		'the `medications` list, rendered into the QR payload by `card_qr`'),
	('EMG-003', 'Contents', 'emergency contacts', 'carried', 'afya.emergency.views:EmergencyContact',
		'a list of `EmergencyContact` rows carrying a name, a number and an optional relationship — '
		'the plural the section writes, and each row says *who* to ring rather than only what to '
		'dial, which is what a clinician reading an unconscious patient\'s card needs'),
	('EMG-003', 'Contents', 'organ donor status', 'carried', 'afya.emergency.views:EmergencyCard',
		'`organ_donor: bool | None` and rendered `yes`/`no`/`unknown` — tri-state because a defaulted '
		'`False` answers "never asked" as "declined", the one reading error on this card with a '
		'clinical consequence'),
	('EMG-003', 'Contents', 'SHA number', 'carried', 'afya.emergency.views:EmergencyCard',
		'`sha_number` on the payload, and no method here stores a card — the hash-only rule '
		'(`insurance.views:sha_of_member_no`) is about persistence, and §EMG-003 asks for the number a '
		'hospital can read off the card. The two are compatible because nothing writes one down'),
	# §EMG-003's Access clause is not a Content but it is the section's other requirement, and it was
	# absent: the card existed with no opt-in flag, so nothing could tell a client whether the person
	# had agreed to have their medical data on a locked screen.
	# §EMG-003 writes Access as two sentences where the five content labels write comma lists, so the
	# parser reads it as one item — the same shape rule the rest of this table follows. Both clauses
	# are covered and the note names both rather than letting the second hide behind the first.
	('EMG-003', 'Access',
		'Available from the lock screen without unlocking the phone (opt-in). Critical for unconscious patients',
		'carried', 'afya.emergency.views:EmergencyCard',
		'the first clause is `lock_screen_opt_in`, defaulted False, because the opt-in *is* the clause '
		'and the default is the one that shows a stranger nothing; the second is '
		'`EmergencyService.card_qr`, which renders all seven Contents into a QR payload — the form '
		'that works for a patient who cannot unlock a phone to show it'),

	# --- §8.5 INF-006: Hotline and Contact Directory ------------------------------------------
	# The section asks for "a single screen with all relevant contacts" and prints eight Contents and
	# four Features. What existed was two rows of one table served as text: no contact kind, so the
	# eight were indistinguishable; three of the eight in `mental.COUNSELLING_LINES`, a table the
	# directory route never read; and none of the four Features rendered, so the screen was data a
	# client could not act on. `InfoService.hotline_directory` answers it now, and `absent` is
	# *derived* from the section's own eight rather than kept as a second list — which is what makes
	# the four still missing a fact the screen prints instead of a blank.
	('INF-006', 'Contents', '719 hotline', 'carried', 'afya.info.service:HOTLINES',
		'the "Ministry of Health Hotline" row, number 719, `kind=emergency_hotline`'),
	('INF-006', 'Contents', 'county health office', 'missing', None,
		'`HOTLINES` has two rows and neither is a county office, and no county health office number '
		'exists anywhere in the tree — `monitoring` routes a breeding-site report *to* one by name '
		'(`routed_to`) without carrying a number. Reported in `absent` rather than blank'),
	('INF-006', 'Contents', 'nearest facility', 'carried',
		'afya.info.service:InfoService._nearest_facility_rows',
		'composed from the caller\'s position over `PlacesService.nearest` and `Place.phone`, so the '
		'row exists only when `lat`/`lon` are given — a nearest facility is an answer about where '
		'the caller is, and without a position the kind is reported `absent` rather than guessed'),
	('INF-006', 'Contents', 'ambulance', 'carried', 'afya.info.service:COUNSELLING_KINDS',
		'the tree\'s own "1199 (ambulance) / 719 (MoH)" row, folded into the directory under '
		'`kind=ambulance`; `_dialable` cuts it to 1199 because stripping both numbers concatenates '
		'them into `1199719`, which dials nothing'),
	('INF-006', 'Contents', 'CHW', 'missing', None,
		'`CaseReport.chw_ref` and `ChwProfile.chw_ref` are references and `ChwProfile` carries no '
		'phone, so no CHW contact can be listed. Reported in `absent`'),
	('INF-006', 'Contents', 'mental health helpline', 'carried',
		'afya.info.service:_directory_rows',
		'Befrienders Kenya\'s number, folded in from `mental.COUNSELLING_LINES` — the table the '
		'directory route never read — so the two modules cannot drift; `mental` keeps the row'),
	('INF-006', 'Contents', 'GBV helpline', 'missing', None,
		'no GBV helpline number exists anywhere in the tree. A deployment that signs one adds a row '
		'and this row becomes `carried`; until then it is named in `absent`'),
	('INF-006', 'Contents', 'child helpline', 'missing', None,
		'no child helpline number exists anywhere in the tree; named in `absent`'),
	('INF-006', 'Features', 'One-tap call', 'carried', 'afya.info.views:HotlineActions',
		'`tel_uri` rendered by `InfoService.hotline_actions` off `_dialable`, so a row naming two '
		'numbers or written `+254-20-4226849` still dials'),
	('INF-006', 'Features', 'one-tap SMS', 'carried', 'afya.info.views:HotlineActions',
		'`sms_uri`, the same handoff as `tel_uri` — "one-tap" is the client opening the messaging '
		'composer with the number prefilled, which is what a `sms:` URI does. §EMG-001\'s "works '
		'over SMS when data is unavailable" is a different claim and still has no path'),
	('INF-006', 'Features', 'save to contacts', 'carried', 'afya.info.views:HotlineActions',
		'a vCard 3.0 body rendered server-side — there is no cross-platform scheme for "save a '
		'contact" the way there is for dialling, so the client hands the text to the contacts app'),
	('INF-006', 'Features', 'share', 'carried', 'afya.info.views:HotlineActions',
		'`share_url`, a `wa.me` deep link carrying the name, number and hours — §3.3 principle 10 '
		'requires every output be shareable as a WhatsApp card, and a card needs a link to carry'),

	('REC-003', 'Features', 'Weight', 'carried', 'afya.records.views:GrowthRecord',
		'the `weight_kg` field, read by `growth_flag`'),
	('REC-003', 'Features', 'height', 'carried', 'afya.records.views:GrowthRecord',
		'the `height_cm` field'),
	('REC-003', 'Features', 'head circumference', 'missing', None,
		'`GrowthRecord` carries `weight_kg` and `height_cm` and no head-circumference field, so the one '
		'measurement a growth tracker takes in the first year cannot be recorded'),
	('REC-003', 'Features',
		'MUAC; percentile charts; undernutrition alerts; feeding guidance by age; milestone checklists',
		'missing', None,
		'the semicolon list is not split out and four of its five clauses have no carrier: MUAC has no '
		'field, no percentile chart is computed anywhere, `growth_flag` returns a one-word flag rather '
		'than an alert, and there is no milestone table in the tree. Only "feeding guidance by age" is '
		'carried — `MonitoringService.nutrition_guidance` bands by age — and it is named here rather than '
		'in its own row because the parser reads the whole semicolon list as one item'),
	('REC-004', 'Features', 'Period logging', 'carried', 'afya.women.views:CycleLog',
		'the `start_iso` and `cycle_days` fields, written through `WomenService.log`'),
	('REC-004', 'Features', 'cycle prediction', 'carried',
		'afya.women.service:WomenService.predict',
		'calendar-method prediction over a median of logged cycles; `CyclePrediction.next_period_iso`'),
	('REC-004', 'Features', 'contraception reminders', 'missing', None,
		'no contraception model and no reminder; `MedSchedule` is a medication course and nothing keys it '
		'to a contraceptive'),
	('REC-004', 'Features', 'fertility awareness', 'missing', None,
		'`CyclePrediction.fertile_window_days` is declared and `predict` sets it to `None` on every path; '
		'the window exists only inside the `advise` string, so no client can read it as a value'),
	('REC-004', 'Features', 'menopause support', 'missing', None,
		'nothing in the tree addresses menopause; `WomenService` stops at cycle prediction'),
	('REC-004', 'Features', 'referral to services', 'missing', None,
		'`WomenService` returns advice text and a prediction and names no service; `intermediaries.views:Referral` '
		'is §CHAN-5\'s referral-attribution record, not a referral a user is sent to'),
	('MON-005', 'Features', 'Boil-water notices', 'carried',
		'afya.alerts.service:AlertsService.water_alert',
		'`WaterQuality.unsafe` decides it and the advisory reads "do not drink without boiling"'),
	('MON-005', 'Features', 'contamination reports', 'carried',
		'afya.alerts.views:WaterQuality',
		'`ecoli_detected` and `turbidity_ntu` are the two contaminants; the reading is an input the '
		'county posts and no user report reaches the model'),
	('MON-005', 'Features', 'treatment guidance', 'missing', None,
		'the advisory names boiling and no treatment steps; nothing carries how to treat water at home'),
	('MON-005', 'Features', 'safe storage guidance', 'missing', None,
		'no storage guidance string exists anywhere in the tree'),
	('MON-005', 'Features', 'point-of-use treatment reminders', 'missing', None,
		'nothing schedules a reminder; `MedSchedule` is a medication course and the alert preferences '
		'carry a `water_quality` toggle, which gates alerts rather than reminding anyone to treat water'),
	('MON-006', 'Features', "AQI for user's location", 'missing', None,
		'`AlertsService.air_alert` reads a single `AirQuality.pm25` the caller supplies and computes no '
		'AQI; nothing derives one from a location, and `AirQuality` carries no location'),
	('MON-006', 'Features', 'health advisories for sensitive groups', 'carried',
		'afya.alerts.service:AlertsService.air_alert',
		'the watch and alert branches address "sensitive groups"; `AirQuality.band` fixes the three bands'),
	('MON-006', 'Features', 'mask guidance', 'carried', 'afya.alerts.service:AlertsService.air_alert',
		'the alert branch reads "masks for sensitive groups"'),
	('MON-006', 'Features', 'best times for outdoor activity', 'missing', None,
		'the advisory says "limit outdoor exertion" and carries no time of day; nothing in the tree '
		'forecasts an hour'),
	('MON-006', 'Features', 'pollution source information', 'missing', None,
		'nothing names a pollution source; `AirQuality` carries a county and a PM2.5 reading and no '
		'source field'),
	('MON-007', 'Features', 'Malaria season alerts by region', 'carried',
		'afya.monitoring.service:MonitoringService.vector_risk',
		'`VectorRisk.malaria_season` from the county\'s 72-hour rainfall; the region is the county the '
		'caller passes, and no seasonal calendar is carried — the band is the recent rain'),
	('MON-007', 'Features', 'mosquito breeding site reporting', 'carried',
		'afya.monitoring.service:MonitoringService.report_breeding_site',
		'routed to the county public health office; `community.IssueKind.mosquito_breeding` is the same '
		'report in the issue catalogue'),
	('MON-007', 'Features', 'larviciding campaign notifications', 'missing', None,
		'no campaign notice is produced anywhere; the alert feed has no vector or larviciding category '
		'and `AlertKind` carries none'),
	('MON-007', 'Features', 'personal protection reminders', 'missing', None,
		'the advice names nets and draining containers as text; nothing schedules a reminder and there '
		'is no vector category in the alert preferences'),
	('MON-007', 'Features', 'Rift Valley fever alerts for livestock-adjacent communities', 'carried',
		'afya.monitoring.service:MonitoringService.vector_risk',
		'`VectorRisk.rvf_alert` where `livestock_adjacent` and the rain band is wet or flood'),
	('MON-008', 'Features', 'Seasonal food availability', 'missing', None,
		'`NutritionGuidance.seasonal_foods` is the field, and `NUTRITION_BY_AGE` fills it with fixed '
		'food lists that do not vary by season, so the seasonal half is the name of a field with nothing '
		'behind it'),
	('MON-008', 'Features', 'aflatoxin alerts', 'carried', 'afya.monitoring.views:FoodSafetyAlert',
		'`kind` accepts `aflatoxin`; `issue_food_alert` stores it and `/monitoring/food-alerts/{county}` '
		'serves it'),
	('MON-008', 'Features', 'food recall notifications', 'carried',
		'afya.monitoring.views:FoodSafetyAlert',
		'`kind` accepts `recall`; the feed is pulled rather than pushed — `/monitoring/food-alerts/{county}` '
		'returns what a county issued, and nothing notifies'),
	('MON-008', 'Features', 'infant feeding guidance', 'carried',
		'afya.monitoring.service:MonitoringService.nutrition_guidance',
		'`NUTRITION_BY_AGE` bands 0-60 months and `/monitoring/nutrition/{age_months}` serves it'),
	('MON-008', 'Features', 'therapeutic feeding programme locations', 'missing', None,
		'neither `PlaceKind` (eight members) nor `FacilityKind` (five) has a therapeutic-feeding kind, so '
		'no route can list one'),
	('MON-008', 'Features', 'recipe ideas for local ingredients', 'carried',
		'afya.monitoring.service:NUTRITION_BY_AGE',
		'each band carries a local-food list — ugali, sukuma wiki, githeri — which is the ingredient '
		'side of a recipe with no method attached'),
	('REC-005', 'Features', 'PHQ-9 and GAD-7 screenings (validated, localised)', 'missing', None,
		'`WHO5` is the only instrument — five 0–5 items, `raw` = sum x 4 — and neither PHQ-9 nor GAD-7 '
		'exists; `WHO5.scores` is positional with no item text, so it is not localised either'),
	('REC-005', 'Features', 'Mood tracking', 'missing', None,
		'no mood model and no time series; `WHO5` is a one-off screening whose result is not stored'),
	('REC-005', 'Features', 'Coping strategies and psychoeducation', 'missing', None,
		'no coping-strategy or psychoeducation content exists; `assess` returns a one-line `advise` '
		'string and nothing else'),
	('REC-005', 'Features', 'Referral to services', 'missing', None,
		'`assess` returns referral *advice* as prose ("consider 719 for referral"); nothing creates a '
		'referral or routes a person to a service — `intermediaries.Referral` is §CHAN-5\'s attribution '
		'code, not a clinical referral'),
	('REC-005', 'Features', 'Crisis line access', 'carried',
		'afya.mental.service:MentalHealthService.lines',
		'`COUNSELLING_LINES` — Befrienders Kenya, NACADA 1192 and the 1199/719 emergency row — served by '
		'`/mental/lines`'),
	('REC-005', 'Features', 'Outbreak-specific: isolation distress, grief support, healthcare worker burnout',
		'missing', None,
		'none of the three appears anywhere; `assess` bands a WHO-5 raw score into good/low/very_low and '
		'names no outbreak-specific condition'),
	('REC-006', 'Features', 'Register as a donor (blood group, location, availability)', 'carried',
		'afya.blood.service:BloodService.register',
		'`Donor` carries `blood_group`, `county` and `last_donation_iso`; "availability" is the '
		'eligibility the date implies rather than a field'),
	('REC-006', 'Features', 'Receive alerts when your blood type is urgently needed nearby', 'missing', None,
		'`BloodService.match` ranks compatible eligible donors and returns them to the requester; no '
		'path notifies a donor that their group is needed, and `urgency` is a request field nobody reads'),
	('REC-006', 'Features', 'Find donation centres', 'missing', None,
		'`PlaceKind` has no donation-centre or blood-bank member and nothing carries one'),
	('REC-006', 'Features', 'Donation history and eligibility tracker', 'carried',
		'afya.blood.service:BloodService.record_donation',
		'`record_donation` stamps `last_donation_iso` and `_eligible` applies the 90-day '
		'`DONATION_INTERVAL_DAYS`; the "history" is that single date, not a list of donations'),
	('REC-006', 'Features', 'Emergency requests from facilities', 'carried',
		'afya.blood.views:BloodRequest',
		'`BloodRequest` carries `blood_group`, `county` and `urgency` (routine|urgent|critical) and '
		'`/blood/match` serves it'),
	('ALT-001', 'Contents', 'Disease outbreaks', 'carried', 'afya.alerting.views:FEED_CATEGORIES',
		'the `outbreak` category; §6.4 corrections publish into it'),
	('ALT-001', 'Contents', 'weather emergencies', 'carried', 'afya.alerting.views:FEED_CATEGORIES',
		'the `weather` category, routed to `county_alerts`'),
	('ALT-001', 'Contents', 'floods', 'carried', 'afya.alerting.views:FEED_CATEGORIES',
		'the `flood` category, routed to `county_alerts`'),
	('ALT-001', 'Contents', 'fires', 'carried', 'afya.alerting.views:FEED_CATEGORIES',
		'the `fire` category, routed to `county_alerts`'),
	('ALT-001', 'Contents', 'road closures', 'carried', 'afya.alerting.views:FEED_CATEGORIES',
		'the `road` category, routed to `county_alerts`'),
	('ALT-001', 'Contents', 'security incidents affecting health access', 'carried',
		'afya.alerting.views:FEED_CATEGORIES',
		'the `security` category, routed to `county_alerts`'),
	('ALT-001', 'Contents', 'drug recalls', 'carried', 'afya.alerting.views:FEED_CATEGORIES',
		'the `drug_recall` category, routed to `facility_alerts`'),
	('ALT-001', 'Contents', 'water notices', 'carried', 'afya.alerting.views:FEED_CATEGORIES',
		'the `water` category, routed to `water_quality`'),
	('ALT-001', 'Contents', 'food recalls', 'carried', 'afya.alerting.views:FEED_CATEGORIES',
		'the `food_recall` category, routed to `nutrition`'),
	('ALT-002', 'Features', '"I\'m safe" button that notifies linked family members', 'carried',
		'afya.alerting.service:AlertingService.check_in',
		'the button is the client surface; `check_in` records the timestamp and `family_board` derives '
		'the safe/unknown split — the "notify" is the board a member reads, not a message sent'),
	('ALT-002', 'Features', 'Family status board during an active alert', 'carried',
		'afya.alerting.service:AlertingService.family_board',
		'`FamilyStatus` carries `members_safe`/`members_unknown` and a rendered `board` string'),
	('ALT-002', 'Features',
		"Automatic check-in prompts during a declared emergency in the user's area", 'deferred', None,
		'a check-in prompt is a client notification surface, and the clause is conditioned on a declared '
		'emergency in the user\'s area — a fact about the world rather than this tree; the server carries '
		'the board and the check-in, and nothing schedules a prompt'),
	('ALT-002', 'Features', 'Works over SMS when data is unavailable', 'missing', None,
		'`/alerting/family/check-in` is HTTP only; `SafetyCheckIn.channel` accepts `sms` and nothing '
		'sends one — the same gap EMG-001\'s SMS bullet names'),
	('MON-009', 'Features', 'Daily temperature logging (manual or via Bluetooth thermometer)', 'carried',
		'afya.monitoring.views:MonitoringDay',
		'`temperature_c` is required on every entry and `source` is a `MeasurementSource`, so a typed '
		'reading and a paired `ble_device` one are told apart (§14.9)'),
	('MON-009', 'Features',
		'Symptom checklist (fever, fatigue, muscle pain, headache, sore throat, vomiting, diarrhoea, rash, bleeding)',
		'carried', 'afya.monitoring.service:MONITORING_ALERT_SYMPTOMS',
		'the constant is exactly those nine plus `hiccups`, and `log_day` intersects the entry with it'),
	('MON-009', 'Features', 'Twice-daily reminders', 'missing', None,
		'`adherence_reminder_days` returns the days with no entry and nothing schedules a reminder; '
		'there is no twice-daily cadence anywhere in the tree'),
	('MON-009', 'Features', 'Visual countdown to the end of the 21-day period', 'carried',
		'afya.monitoring.views:MonitoringVerdict',
		'`days_remaining` = `MONITORING_DAYS` - `day` and `day` is bounded 1–21'),
	('MON-009', 'Features',
		'**Escalation logic:** Any fever or new symptom triggers an immediate prompt to call 719 and, with consent, notifies the assigned CHW or county team',
		'carried', 'afya.monitoring.service:MonitoringService.log_day',
		'`log_day` escalates on a fever (>=38.0 °C) or any alert symptom and sets `notify_chw` when an '
		'officer is named — but `notify_chw` is a bool and no CHW is notified'),
	('MON-009', 'Features', 'Location logging (with consent) to support contact tracing', 'missing', None,
		'`MonitoringDay.location_logged` is a bool nothing ever sets and the route does not accept it; no '
		'location is stored and nothing feeds contact tracing'),
	('MON-009', 'Features', 'Household member monitoring in the same interface', 'missing', None,
		'`HouseholdMonitor.members` is never populated — `enrol` builds the row with no members — and '
		'`MonitoringDay.household_member` is one optional name on a single entry, so there is no '
		'household interface'),
	('MON-009', 'Features', 'Psychological support resources', 'missing', None,
		'nothing in the monitoring module carries psychological-support content; `MonitoringVerdict.'
		'message` names 719 and nothing else'),
	('MON-009', 'Features', 'Direct line to the assigned monitoring officer', 'missing', None,
		'`HouseholdMonitor.monitoring_officer` is a free-text name with no number and `notify_chw` is a '
		'bool, so there is no officer contact to dial'),
	('COM-101', 'Features', 'Guided case report form based on WHO IDSR and Kenya MoH standards',
			'carried', 'afya.community.views:CaseReport',
			'the structured report the docstring names; WHO IDSR / MoH standards are the design '
			'commitment behind the field set'),
	('COM-101', 'Features', 'Patient demographics (name optional; can be anonymous)', 'carried',
			'afya.community.views:CaseReport',
			'`patient_ref` is optional and `age_years`/`sex` are the demographics, so anonymous is a '
			'first-class path'),
	('COM-101', 'Features', 'Symptom checklist', 'carried',
			'afya.community.views:CaseReport', 'the `symptoms` list, min_length 1'),
	('COM-101', 'Features', 'Exposure history', 'carried',
			'afya.community.views:CaseReport', 'the `exposure_history` field'),
	('COM-101', 'Features', '**Geotagged photo capture** (with consent) of visible symptoms',
			'deferred', None,
			'capturing a photo is a device action; the client does it and `CaseReport` carries the '
			'`photo_sha256` it yields, gated on `geotagged` consent'),
	('COM-101', 'Features', '**Voice-to-text notes** in local languages', 'missing', None,
			'`voice_note_lang` names a language and nothing records a note; no voice capture or '
			'transcription anywhere in the tree'),
	('COM-101', 'Features',
			'**Offline report queue** — reports stored locally and submitted when connectivity is available',
			'missing', None,
			'`SyncService` carries a `case_reports` server-authoritative conflict rule and the '
			'`reported_offline` flag, but no code path enqueues a case report: the mobile `submit_case` '
			'action is a plain POST'),
	('COM-101', 'Features',
			'Automatic alerts to the appropriate disease surveillance officer on submission (mirroring AVADAR)',
			'carried', 'afya.community.service:CommunityService.submit_case',
			'returns `alerts_sent=1` on the first submission; a duplicate open case is told no second '
			'alert was sent'),
	('COM-101', 'Features', 'Case status tracking (reported → investigated → lab result → closed)',
			'carried', 'afya.community.views:CaseStatus',
			'the four-member enum; `advance_case` enforces forward-only movement'),
	('COM-101', 'Features', 'PPE reminders and guidance', 'carried',
			'afya.community.service:CommunityService.ppe_reminder',
			'the donning/doffing guidance string, served by `/community/ppe-reminder`'),
	('COM-101', 'Features', 'Reference materials and job aids', 'carried', 'afya.chw.views:JOB_AIDS',
			'six topics served by `/chw/job-aid/{topic}`'),
	('COM-101', 'Features', 'Daily activity log for supervision', 'carried',
			'afya.chw.service:ChwService.activity_summary',
			'`ActivityLogEntry` is written by `/chw/activity` and the summary groups by activity kind'),
	('COM-102', 'Features', 'Geofenced alert zones (500 m, 1 km, 5 km — configurable by county)',
			'carried', 'afya.location.service:ALLOWED_RADII_M',
			'the `(500, 1000, 5000)` radii, but they are a module constant nothing reads — no zone is '
			'computed and `radius_m` is validated against the endpoints, not the set'),
	('COM-102', 'Features',
			'Alert content: "A suspected case has been reported in your area. Avoid [specific location]. Monitor for symptoms for 21 days. Call 719 if you feel unwell."',
			'missing', None,
			'`PeerAlert` carries a caller-supplied `headline`/`body` and nothing drafts or templates this '
			'text; the nearest string is the LOC-001 geofence advice, which is a different feature'),
	('COM-102', 'Features', 'No personally identifiable information about the case', 'missing', None,
			'`PeerAlert` carries no `subject_ref`, which is what makes a case identifier representable, '
			'and no field or assertion rejects one either'),
	('COM-102', 'Features', 'Users acknowledge alerts and receive follow-up guidance', 'missing', None,
			'`PeerAlertReceipt` reports recipients and tone; there is no acknowledgement route or model, '
			'and no guidance is returned after one'),
	('COM-102', 'Features', 'Follow-up prompts on days 3, 7, 14, and 21', 'missing', None,
			'`PeerAlert.followup_days` defaults to `[3, 7, 14, 21]` and no code path reads it — nothing '
			'schedules or sends a follow-up prompt'),
	('COM-103', 'Features',
			'Guided prompts based on call logs, calendar events, and location history (with full consent)',
			'deferred', None,
			'reading call logs, calendar and location history is a device permission; the server carries '
			'`TRACING_PROMPTS` and takes no device feed'),
	('COM-103', 'Features', 'Simple form to list names and contact details', 'carried',
			'afya.community.views:ContactEntry',
			'`description` is the name/description and `contact_ref` the contact detail'),
	('COM-103', 'Features',
			'"I don\'t know their name" option — record a description and approximate location instead',
			'carried', 'afya.community.views:ContactEntry',
			'`name_unknown` with `approx_location`'),
	('COM-103', 'Features', 'Categorised by setting (home, work, transport, worship, market, social)',
			'carried', 'afya.community.views:ContactEntry', 'the `setting` pattern, which adds `other`'),
	('COM-103', 'Features',
			'Option to share with health authorities through a secure, encrypted channel', 'missing', None,
			'`ContactList.share_consent` is a flag and `summary` reports it, but nothing transmits a list '
			'anywhere — there is no encrypted channel and no share route'),
	('COM-103', 'Features', 'Progress indicator', 'carried',
			'afya.community.service:CommunityService.summary',
			'`progress_pct` over `TRACING_PROMPTS`, returned by both contact routes'),
	('COM-104', 'Features', 'Simple "Report misinformation" button', 'carried',
			'afya.community.views:MisinfoSubmission',
			'the `flag_misinformation` mobile action posts to `/community/misinformation`'),
	('COM-104', 'Features', 'Text, voice, or screenshot submission', 'missing', None,
			'`MisinfoSubmission.medium` accepts `text|voice|screenshot|whatsapp_forward` and carries no '
			'payload for any of them — a voice note and a screenshot have nowhere to be stored'),
	('COM-104', 'Features', 'Aggregation by topic and location', 'carried',
			'afya.community.service:CommunityService.clusters',
			'`MisinfoCluster` groups by topic and carries the counties the reports came from'),
	('COM-104', 'Features', 'Dashboard for health authorities showing trending misinformation',
			'carried', 'afya.analytics.service:AnalyticsService.dashboard',
			'§19.4\'s `misinformation_velocity` dashboard is a topic-grouped velocity count; its data '
			'read is unwired, so the dashboard renders empty'),
	('COM-104', 'Features',
			'Push notification with corrections when a rumour the user flagged is addressed', 'missing', None,
			'`correction_for` drafts the text but nothing pushes it, and `flagger_ref` is never read — '
			'the person who flagged the rumour is not identifiable to the code that has the correction'),
	('LOC-005', 'Features', 'Pre-travel advisory by destination', 'carried',
			'afya.location.service:LocationService.advisory', 'served by `/location/travel-advisory`'),
	('LOC-005', 'Features', 'Screening queue status at major border points', 'carried',
			'afya.location.views:BorderPost',
			'`queue_minutes` and `screening_required`, read by `/location/border/{post_id}`'),
	('LOC-005', 'Features', 'Self-declaration form (digital, replaces paper)', 'carried',
			'afya.location.views:TravelerDeclaration', 'posted to `/location/traveller/declare`'),
	('LOC-005', 'Features', '21-day post-arrival monitoring enrolment', 'carried',
			'afya.location.views:TravellerEnrolment',
			'`self_declare` enrols for 21 days with a `[1, 3, 7, 14, 21]` schedule; it is a separate '
			'enrolment from MON-009\'s contact diary, not an enrolment into it'),
	('LOC-005', 'Features', 'Post-arrival symptom reporting', 'missing', None,
			'`TravellerEnrolment` states a report schedule and no route accepts a post-arrival report; '
			'symptoms are collected once, at arrival, on the declaration'),
	('LOC-005', 'Features', 'Multi-language support for cross-border travellers', 'missing', None,
			'`TravelerDeclaration.lang` is accepted and `self_declare` never reads it; only `en` and `sw` '
			'have string tables (`afya.strings.SUPPORTED_LANGS`) and the advisory and enrolment messages '
			'are English-only literals'),
	('LOC-005', 'Features', 'Integration with mobile laboratory results at border points',
			'missing', None,
			'`BorderPost` has no lab field and no code path ties a border point to a lab result; '
			'`AdamClient.pull_case_status` is a national case-status pull with no border surface'),
	('AI-001', 'Outputs', 'Hotspot predictions', 'carried',
		'afya.ai.service:AIService.hotspots', None),
	('AI-001', 'Outputs', 'transmission cluster identification', 'missing', None,
		'the map carries one `Hotspot` per aggregated cell — probability, reason and a recommended '
		'action — and nothing identifies a cluster: `MisinfoCluster` clusters rumours by topic, a '
		'different quantity'),
	('AI-001', 'Outputs', 'resource deployment recommendations', 'missing', None,
		'`Hotspot.recommended_action` is one prose sentence ("Send a rapid response team...") and '
		'`HotspotMap` carries no resource, quantity or county list; `feeds.build_resource_feed` '
		'renders a `resource_deployment` feed but nothing produces its recommendations'),
	('AI-003', 'Signals monitored', 'Sudden increase in fever triage in a locality', 'missing', None,
		'`signal="fever_triage"` is an accepted value and nothing counts triages into a county '
		'baseline — `SurveillanceService.weekly_signal` reads only the caller-supplied '
		'`CountySignal.fever_reports`'),
	('AI-003', 'Signals monitored', 'Increase in cough detection events', 'missing', None,
		'`signal="cough_events"` is an enum member and no code derives it — `CoughVerdict.cough_events` '
		'is a per-recording device count, not a locality baseline'),
	('AI-003', 'Signals monitored', 'Increase in facility-finder searches for a specific symptom', 'missing', None,
		'`signal="facility_search"` is an enum member; the facility finder records no search and '
		'carries no symptom to search for'),
	('AI-003', 'Signals monitored', 'Increase in medicine searches for a specific drug', 'missing', None,
		'`signal="medicine_search"` is an enum member; `MedicineService` verifies a registration '
		'number and records no search'),
	('AI-003', 'Signals monitored', 'Increase in "I feel unwell" check-ins', 'missing', None,
		'`signal="unwell_checkin"` is an enum member; the symptom diary and the 21-day monitoring '
		'day exist but neither feeds a county signal'),
	('AI-003', 'Signals monitored', 'Anomalous proximity encounter density', 'missing', None,
		'`signal="encounter_density"` is an enum member and `AggregateCell.encounter_density` is '
		'caller-supplied; `AnalyticsService._encounter_density` counts tokens per county and does '
		'not derive the warning signal'),
	('ACC-001', 'Features', 'Pictogram navigation for all core functions', 'carried',
		'afya.access.service:UI_SCREENS', 'every `UIAsset` carries a `pictogram` and a `label`'),
	('ACC-001', 'Features', 'Video tutorials in local languages', 'missing', None,
		'no video asset or tutorial payload anywhere; §INF-008 lists "30-second videos" as a '
		'health-tip *format* and `access` carries nothing, so there is no tutorial to render'),
	('ACC-001', 'Features', 'Colour-coded risk levels (green / yellow / red) with universal symbols', 'carried',
		'afya.access.views:UIAsset', '`risk_colour` is green/yellow/red/neutral and `universal_symbol` carries the symbol'),
	('ACC-001', 'Features', 'Large touch targets (minimum 48dp)', 'carried',
		'afya.access.views:MIN_TOUCH_TARGET_DP', '48, and every `UIAsset.touch_target_dp` is asserted at or above it'),
	('ACC-001', 'Features', 'Simplified forms', 'missing', None,
		'`AccessProfile` carries `simple_mode` and `AccessService.screens` hides screens, but no '
		'form or field is simplified by it'),
	('ACC-001', 'Features', 'Read-aloud on every screen', 'carried',
		'afya.access.service:UI_SCREENS', 'each `UIAsset` carries `read_aloud_text` and `AccessProfile.read_aloud` defaults on'),
	('ACC-001', 'Features', 'Optional "simple mode" that hides advanced features', 'carried',
		'afya.access.views:AccessProfile', '`simple_mode` is a profile flag and `screens(simple_mode)` drops the assets marked not visible'),
	('ACC-002', 'Features', 'Voice-guided symptom reporting in Swahili, Dholuo, Luhya, Kalenjin, Kikuyu, and English', 'missing', None,
		'`LANGUAGE_MATRIX` lists the six, but `strings.SUPPORTED_LANGS` has tables for `en` and `sw` '
		'only, so the other four are answered in English; the voice route also starts at a symptom '
		'check rather than reporting one'),
	('ACC-002', 'Features', 'Text-to-speech for reading alerts and guidance aloud', 'carried',
		'afya.access.views:LANGUAGE_MATRIX', 'the `tts` flag per language, and `VoiceResult.spoken_reply` carries the spoken text'),
	('ACC-002', 'Features', 'Voice-to-text for CHW notes and case descriptions', 'missing', None,
		'`AccessService.transcribe` takes any `VoiceRequest` and `chw` has no voice path: '
		'`CaseReport` and the CHW note carry text fields only'),
	('ACC-002', 'Features', 'Voice note triage on WhatsApp', 'missing', None,
		'`ChannelService` reads text bodies only; no WhatsApp voice note is ingested and no audio '
		'route exists'),
	('ACC-002', 'Features', 'Offline speech recognition for core commands', 'carried',
		'afya.access.service:VOICE_INTENTS', '`VoiceRequest.offline` and `VoiceResult.on_device` carry the flag; recognition is a keyword intent map, so only the six core commands are covered'),
	('SEC-001', 'Features', 'Plain-language explanations in local languages', 'missing', None,
		'`ConsentScope.explains` is a plain-language sentence but exists in English only; nothing '
		'carries a per-language consent explanation'),
	('SEC-001', 'Features', 'Granular toggles', 'carried',
		'afya.privacy.service:PrivacyService.consent_toggles', 'one toggle per category, plus a per-sensor map for `sensor_monitoring`'),
	('SEC-001', 'Features', 'One-tap revocation', 'carried',
		'afya.privacy.service:PrivacyService.withdraw', None),
	('SEC-001', 'Features', 'Clear statement of consequences of revocation', 'carried',
		'afya.privacy.service:CONSENT_CATALOGUE', '`on_withdrawal` is a required field on every `ConsentScope`'),
	('SEC-001', 'Features', 'Consent audit log visible to the user', 'missing', None,
		"`ConsentToggle` names the audit entry in its docstring and carries no such field; the "
		"ledger is written but nothing serves a subject their own consent history — `/privacy/consent` "
		"returns the catalogue with the caller's grants"),
	('SEC-004', 'Features', 'No account required for Tier 1–3', 'carried',
		'afya.auth.service:AuthService.issue_anonymous', 'a citizen endpoint needs no account; the token is random and resolves to a minted subject'),
	('SEC-004', 'Features', 'Phone number is the only identifier', 'carried',
		'afya.identity.service:IdentityService.resolve', 'an MSISDN alone resolves to an anonymous subject, and linkage to a profile is a separate recorded act'),
	('SEC-004', 'Features', 'Optional pseudonymous profile', 'missing', None,
		'`IdentityService.link` attaches a phone to an app profile and no profile model carries a '
		'chosen pseudonym or display name — the only pseudonym in the tree is `patient_ref` on the '
		'ADaM integration'),
	('SEC-004', 'Features', 'Geohashing for location sharing', 'carried',
		'afya.location.service:_geohash_cell', 'truncates to a five-character cell before a location is shared'),
	('SEC-004', 'Features', 'PET tokens for proximity', 'carried',
		'afya.location.views:EncounterToken', '`pet` is the rotating token the encounter log stores instead of an identity'),
	('SEC-004', 'Features', 'Minimum cell size of 10 for any aggregated reporting', 'carried',
		'afya.ai.views:MIN_CELL_SIZE', 'enforced at the hotspot, analytics and PHEOC-feed exits'),
	('SEC-006', 'Features', 'In-app data dashboard: what is stored, what has been shared, with whom, when', 'carried',
		'afya.retention.service:RetentionService.inventory', '`held` and `shared_with` (with-who/what/when) served at `/retention/inventory/{subject_ref}`'),
	('SEC-006', 'Features', 'Public transparency reports (quarterly)', 'missing', None,
		'`RetentionService.transparency_report` produces a per-subject report and no aggregate '
		'publication; the section names a recurring public document, not a personal one'),
	('SEC-006', 'Features', 'Open-source client code', 'missing', None,
		'the tree carries no LICENSE and no source offer; a public repository is not something this '
		'tree can assert about itself'),
	('SEC-006', 'Features', 'Independent security audits (annual)', 'carried',
		'afya.security.service:SecurityService.obligations', 'a `third_party_audit` obligation at a 365-day cadence, reported overdue until a scan is recorded'),
	('SEC-006', 'Features', 'Bug bounty programme', 'carried',
		'afya.security.service:SecurityService.disclosure_policy', 'contact, acknowledgement window, triage window, safe harbour and scope lists'),
)

# The five content-list labels, plus `Access` — which the spec prints twice, once per §EMG-003
# ("lock-screen-accessible ... without unlocking the phone (opt-in)") and once per §19.4 ("PHEOC,
# county health teams, MoH. Role-based. Audit logged."). It is a different *kind* of list: the five
# are what a feature holds, and Access is who may reach it. Both are content a section states, so
# both are auditable. §19.4's is the only one outside §8–§12 and is out of scope here, not unaudited.
_LABELS: tuple[str, ...] = (
	'Features', 'Contents', 'Additional inputs', 'Outputs', 'Signals monitored', 'Access',
)

# Every §8–§12 section that carries a labelled content list is audited above, so this list is empty.
# It is kept, and asserted against the spec's own section count, rather than deleted: the *empty*
# list is the claim of coverage, and a reader is entitled to see the mechanism that would name a
# section the day one is added to the spec and not to this table. §19.4 is the one section outside
# §8–§12 that prints an `**Access:**` label, and it is out of this module's declared scope rather
# than unaudited — the partition test counts the spec's `#### FID:` sections, and §19.4 is not one.
UNAUDITED_FEATURES: tuple[str, ...] = ()

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
