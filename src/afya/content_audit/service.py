"""Feature content audit — what each §8–§12 feature section says it does, against what does it.

The registry gate (`tests/ci/test_feature_coverage.py`) answers one question: can a client *reach*
this feature? It is a route check, and it is why 24 orphaned `/ops/*` endpoints were found. It says
nothing about whether the feature does what its section says — a feature can be registered,
reachable, tested, and missing half its own spec.

That is not hypothetical. §9.2's REC-001 was "reachable" the whole time and named eight wallet
contents of which one had no model at all. This module applies the same treatment to feature
sections' labelled content lists: `**Features:**`, `**Contents:**`, `**Additional inputs:**`,
`**Outputs:**` and `**Signals monitored:**`.

**Coverage is partial and the report says so.** §8–§12 print 221 labelled content bullets across 35
feature sections — the sections carrying a `**Features:**`-style list, with §9.5 INF-007's prose
Contents cell counted as its six comma-separated items. Thirteen are audited here: the four the
section-number survey found named nowhere in the source (§9.3 MED-004, §9.4 FND-006, §9.5 INF-007,
§11.2 TRI-003) and the nine §8 Tier-1 sections, the tier that earns the download and the one a
person meets first. `audited_features` and `UNAUDITED_FEATURES` are served alongside the findings,
because a report that showed 45 gaps without saying how much of the spec it had read would invite
the reader to take it as complete — which is the failure mode of every gate that scopes itself.

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
)

_LABELS: tuple[str, ...] = ('Features', 'Contents', 'Additional inputs', 'Outputs', 'Signals monitored')

# §8–§12's feature sections that carry a labelled content list and are not audited above. Listed
# rather than omitted so the report cannot be read as covering the spec: 221 such bullets across 35
# sections, and a finding list presented without that context invites exactly the misreading this
# module exists to prevent. Each is a section whose content nobody has crossed against the code yet
# — a to-do with a count, not a claim of coverage. §9.2 REC-001 is here although its wallet contents
# *are* audited in `afya.records.service:WALLET_ITEMS`; what is unaudited is the rest of its list.
UNAUDITED_FEATURES: tuple[str, ...] = (
	'FND-003', 'FND-005', 'EMG-003', 'INF-004', 'INF-005', 'INF-006',
	'MON-001', 'MON-002', 'MON-003', 'MON-004', 'MON-005', 'MON-006', 'MON-007', 'MON-008',
	'REC-001', 'REC-003', 'REC-004', 'REC-005', 'REC-006',
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
