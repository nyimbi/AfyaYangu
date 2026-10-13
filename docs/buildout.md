# Engineering Buildout Map (spec § → module → tests)

| Spec area | Module | Tests |
|---|---|---|
| §7 tiers, App. B features | `src/afya/registry/` | `test_registry.py` |
| §5 CHAN-000..006 | `src/afya/channels/` (SMS GSM-7 segmentation, USSD FSM, WhatsApp router, radio/CHW/push) | `test_channels.py` |
| §5.4 channel interoperability, §CHAN-2 USSD tree | `src/afya/channels/service.py`, `src/afya/strings.py` (one triage engine behind every entry point; §CHAN-2's five-item tree walked as data) | `test_channels.py`, `test_ui_vocabulary.py`, `test_personas.py` |
| §5.4 identity model, case-report dedup, cross-channel consent | `src/afya/identity/` (one MSISDN→subject index; dedup keyed on the normalised phone; `reassign_subject` moves a channel grant to the profile) | `test_identity.py`, `test_ui_vocabulary.py`, `test_inbound_webhooks.py` |
| §8.1 TRI-001/002/003 + §6.3 malaria trap | `src/afya/triage/` | `test_triage.py` |
| §8.2 FND-001..006, §18.5 MoHF | `src/afya/facilities/` | `test_facilities.py` |
| §8.3 MED-001..004, §18.7 PPB | `src/afya/medicine/` (port + stub fallback + interaction table + dosing) | `test_medicine.py` |
| §8.4 EMG-001..003 | `src/afya/emergency/` (SOS fan-out port, IMU fall detection, offline card) | `test_emergency.py` |
| §8.5 INF-001..006, §6 content harmony | `src/afya/info/` (decision tree, county dashboard, hotlines) | `test_info.py` |
| §6.2 ten content principles | `src/afya/info/principles.py` (rules as tables, judged per genre, enforced at the publishing and peer-alert routes) | `test_content_principles.py` |
| §6.4 misinformation response protocol | `src/afya/community/protocol.py` (six steps with a computed clock, six myth categories with a coverage report) | `test_misinfo_protocol.py` |
| §6.1 demand-ordered questions, §6.2.4 local language first | `src/afya/info/questions.py` (ten ranked questions; the life-safety set that gives §6.2.4 a jurisdiction) | `test_content_language.py` |
| §6.2.3 timestamp everything, §8.5 last-updated | `src/afya/info/recency.py` (the age line computed from a stamp; the withheld undated item) | `test_content_recency.py` |
| §9–10 REC-001..003, EPI, growth | `src/afya/records/` | `test_records.py` |
| §16 offline sync, conflict matrix | `src/afya/sync/` | `test_sync.py` |
| §11/§19.4 Tier-4 surveillance | `src/afya/surveillance/` (z-score signal, geofences, PET store, activation gate) | `test_surveillance.py` |
| §17 DPA 2019 / ODPC / DHA 2023 | `src/afya/privacy/` (consent ledger, DPIA gate, RBAC, anonymize, 72h breach) | `test_privacy.py` |
| §17.4 RBAC table vs. the routes | `src/afya/privacy/rbac.py` (role→scope map crossed against the guards in `service.py` and the token-issuing paths) | `test_rbac.py` |
| §22 success metrics, §22.8 equity cuts and the five-level evaluation framework | `src/afya/metrics/` (42 KPIs as data, measurement rule, disaggregation coverage, evaluation levels crossed against the metric families) | `test_metrics.py` |
| §23 risks, §24 operations, governance, support, training, funding, sustainability, incident response, SLAs | `src/afya/operations/` (33-risk register with resolvable controls, incident clocks, duty cadences, §24.1's 6 bodies joined to the duty owners, §24.3's 5 support channels, §24.4's 7 audiences joined to the bodies, §24.5's 4 funding bands tiled over §21's phases, §24.6's 8 mitigations resolved against the artefacts they name) | `test_operations.py` |
| §20 growth levers, acquisition, partnerships, §21 rollout phasing | `src/afya/rollout/` (7 phases with tier ceilings, 6 levers with 2 checkable repo claims, §20.3's 7 channels crossed against §5.2, §20.4's 10 partner types joined to §20.2's levers, §20.6 retention crossed against the registry, §21.2–21.7's deliverables and success criteria as data) | `test_rollout.py` |
| §13 sensor matrix, §14 sensor specs | `src/afya/sensors/` (18-row §13.1 inventory with its sensitivity column, §13.2 fallback coverage crossed against it) | `test_sensors.py` |
| §12.2 consent granularity, §SEC-001 | `src/afya/privacy/` (8-category consent catalogue with per-sensor enumeration off the §13.1 matrix, withdrawal consequences as required fields) | `test_privacy.py` |
| §18 ADaM/JALI/PHEOC/PPB/MoHF | `src/afya/integrations/` (httpx adapters) | `test_integrations.py` |
| §15.5 API (REST, WebSocket, versioning, OpenAPI 3.1) | `src/afya/service.py`, `src/afya/realtime/`, `src/afya/auth/` | `test_app.py`, `test_realtime.py`, `test_auth.py` |
| §15.5 gRPC internal | `proto/afya_internal.proto`, `src/afya/grpc_api/` | `test_grpc.py` |
| Native clients | `ios/` (SwiftUI), `android/` (Kotlin) | xcodebuild + gradle assembleDebug |

Everyday-health domain modules (2026-10-08, commit 4e06739): women/ (cycle tracking), maternal/ (ANC + danger signs), chronic/ (BP/glucose/refill), mental/ (WHO-5 + lines), blood/ (donor matching), alerts/ (water/air/flood/school/multi-disease), insurance/ (SHA + price transparency) — new tests/ci/test_expansion.py; registry now 58 features incl. REC-004..009/INF-011..016/SENS-009.

Full-surface buildout (2026-10-10): closed the gap between the README's "58 registered" claim and the spec's actual surface. Five namespaces had zero registry presence (MON, ALT, COM, AI, ACC/SEC) and four of five LOC features were missing, so a large fraction of the product was described as done but unimplemented. Now 97 features across all 15 spec namespaces, 156 operations over 154 paths.
- New modules: `monitoring/` (MON-001..009 — EPI schedule + catch-up, adherence/refill, peak-flow zones, 21-day contact diary with fever escalation), `community/` (COM-005/101..104 — issue routing to county authorities, case reporting with automatic officer alert, verified peer alerts with a tone check, misinfo clustering), `alerting/` (ALT-001..004 — unified feed, family board, preferences where critical categories have no off switch, exposure notification), `location/` (LOC-002..005 — rotating derived EBID, proxied declarations, geohash-only history truncated to a 5-char cell on share, check-in points, border/travel), `ai/` (AI-001..005 — hotspot suppression below 10-person cells, on-device risk score, early warning that never auto-publishes, model cards, fairness audit, redress), `access/` (ACC-001..005 — 13-language matrix, 48dp targets, battery budget), `retention/` (SEC-003/005/006 — finite windows enforced by the table, deletion that names what survives, transparency), `chw/` (CHAN-005/COM-101 — provisioning gated on registry verification).
- Feature ids never reach a screen. The mobile catalogue is now semantic slugs; spec codes live only in `FEATURE_OF`, which is not serialised. Two gates enforce it: `test_ui_vocabulary.py` (scans served payloads, catalogue, friendly copy and native string literals for the `PREFIX-000` pattern; canaried against planted text) and `test_spec_coverage.py` (every id in `docs/spec.md` resolves in the registry; canaried by dropping a feature).
- Dormant capabilities are withheld, not just refused: `/mobile/actions` serves 110 of 140 actions until PHEOC activates the event, then all 140. `/tier4/activate` now names the missing key(s) and what activation unlocked, instead of returning a bare boolean.
- Bugs found and fixed while testing: `/chw/training` was shadowed by `/chw/{chw_ref}` and 404'd (FastAPI matches in declaration order); the misinfo flag returned whichever *other* topic had the most reports, so a reporter was shown an unrelated correction; the early-warning gate trusted a caller-supplied `z_score` rather than deriving it from the observed counts, and the derivation helper was dead code — `WarningSignal` now carries counts plus a stated stdev and the service computes the z (regression tests for both). Spec-id divergence in §10.1 (REC-004..006) is recorded in `SPEC_ID_ALIASES` rather than papered over.
- 279 tests green, pyright clean.

Known gaps (tracked): persistence layer is SQLite adapter; production Postgres/Timescale (asyncpg) swap of same Protocol pending; §19.1 TFLite/ONNX model assets not present — Tier 4 ML stays dormant by design; spec.md appendices C–D reconstructed (source truncation); hotline codes unverified per spec's own verification note; Android BackendClient context-bound paths lack JVM tests (pure-logic extraction or Robolectric pending).
gRPC internal surface (2026-10-10, spec §15.5 "gRPC for internal service-to-service"): `proto/afya_internal.proto` (package `afya.internal.v1`) declares `AfyaInternal` with five unary RPCs — `Health` (status, api_version, tier4_active), `LookupFeature` (spec-id aliases resolve; NOT_FOUND otherwise), `ListFeatures` (tier filter, 0 = all), `Triage` (urgency, recommendation, red_flags), `ActivationStatus` (tier4_active + unmet_keys). Stubs are committed at `src/afya/grpc_api/` (module named `grpc_api`, not `grpc`, so it cannot shadow the grpc package); the generated `*_pb2_grpc.py` carries one patched import line (absolute `afya_internal_pb2` -> `from afya.grpc_api import afya_internal_pb2`) because protoc's default does not resolve inside a package. The servicer (`grpc_api/service.py`) subclasses the generated base and delegates to `FeatureRegistry` and `TriageService` — no algorithm is reimplemented, so the gRPC and REST surfaces cannot drift. `Triage` carries no thermometer field, so it enters the algorithm at the standard 36.5 °C and expresses fever through the symptom list. `serve(services, port)` returns a `grpc.aio.Server` bound to the OS-chosen port (0 = ephemeral). Regenerate with `uv run python -m grpc_tools.protoc --proto_path=proto --python_out=src/afya/grpc_api --grpc_python_out=src/afya/grpc_api --mypy_out=src/afya/grpc_api proto/afya_internal.proto`; `--mypy_out` (mypy-protobuf) replaces `--pyi_out` because the two write the same `.pyi` and protoc refuses the duplicate. Tests start a real `grpc.aio` server on an ephemeral port and dial it with a real channel (`test_grpc.py`); the two generated files with unhandled type stubs are excluded in `pyrightconfig.json`.

Buildout increments (2026-10-08): mobile feature screens shipped on both platforms — iOS (Finder/Wallet/Diary/CHW tabs, xcodebuild+XCTest 5/5 green) and Android (FeaturesActivity with FND-001/REC-001/TRI-002/CHAN-005/sensor-ingest sections, APK assembled); server-side sensor ingestion with band engines (tier4-gated, raw-payload rejection); AT SMS REST + WhatsApp Business clients (HTTP-tested) with env-driven ServiceConfig; en/sw i18n (USSD menus, triage recommendations); CHW task assign/open/done + AT USSD callback endpoints; wallet aggregate endpoint.

§15.5 completed (2026-10-10). The three remaining requirements — WebSocket, versioning, published OpenAPI — plus auth, which landed in commit f84ef30.
- **WebSocket** (`src/afya/realtime/`): `/alerts/socket?county=&categories=` sends a `hello` frame naming the resolved subscription, then one `alert` frame per matching `FeedItem`. `POST /alerting/feed` writes the durable feed first and returns `delivered_realtime` — a socket is a transport, never a second source of truth, so §16.1's "nothing is lost" still holds for a client that was offline when the alert fired. A subscriber whose queue fills is dropped rather than awaited: one stalled phone must not delay the county. Critical categories (`exposure_notification`, `immediate_danger`) are not reachable through the socket at all — they are per-subject, and broadcasting one would tell every listener that a named individual was exposed.
- **The bug this found**: `FeedItem.category` (`outbreak`, `flood`, `water`, …) and the preference categories (`disease_alerts`, `county_alerts`, `water_quality`, …) were two disjoint vocabularies with nothing linking them, so every socket subscription matched nothing and delivered zero — silently, with a 200. `FEED_PREFERENCE` now states the mapping and `governing_preference()` is the single accessor; the model asserts every value is toggleable, and a gate fails if any feed category loses its mapping.
- **Versioning** (`/v1/`): `create_app()` returns a facade that mounts the API at both `/v1` and `/`. The facade holds no routes of its own, so its spec would describe a mount table — `root.openapi` is pointed at the API's, which is what `create_app().openapi()` is read for. `GET /` names the current version; `/v1/openapi.json` and `/v1/docs` are served. Both spellings enforce the same guards: the rate-limit and idempotency middleware runs per request under the mount, verified by a test that floods `/v1/health` and expects a 429.
- **OpenAPI 3.1** was already emitted (161 operations, every one with an operationId and a response schema); it is now published at `/openapi.json` and `/v1/openapi.json`. 343 tests green, pyright clean.

Tier-4 dormancy enforced from the tier model, not a hand-kept list (2026-10-10). Auditing whether the dormant set mapped onto Tier-4 features found it did not: 14 actions on six Tier-4 features were live — the whole COM-101 CHW reporting module (`ppe_reminder`, `job_aid`, `chw_cases`, `assign_chw_case`, `log_chw_activity`, `chw_activity`, `chw_case_load`, `chw_ppe_reminder`), `tracing_prompts` (COM-103), `checkin_points`/`checkin_list` (LOC-004), `analyse_cough` (SENS-002) and `submit_evidence` (SENS-004). The client showed controls the spec says stay dark until PHEOC activates the event, and the server refused them — the "switch that refuses you" §11.1 exists to prevent. The existing gate checked `DORMANT_SLUGS` against itself, so it could not see this.
- Dormancy now derives from `FeatureRegistry.by_tier(Tier.tier4)`; `dormant_slugs()` unions the curated list with every action whose feature is Tier 4, so a Tier-4 feature added later is dark from the moment it exists. `/mobile/actions` serves 97 of 140 before activation, 140 after.
- `travel_advisory` was mapped to LOC-005 (Border, Tier 4) when the spec's Travel Advisory is **INF-005, Tier 1** — an always-on capability wrongly withheld. Re-mapped, with a gate pinning it.
- **Two more real defects found by driving the routes rather than reading them.** The evidence gate could be encoded around: FastAPI leaves undeclared parameters at their defaults for a multipart request, so `kind=rash` in the *body* submitted the route's `scene_photo` default instead — a Tier-3 feature — while the identical request as query parameters was correctly refused. Android's `uploadEvidence` writes the form shape, so the SENS-004 gate was bypassable from the shipped client. The fields are now `Form(...)`, and a content type outside the model's contract is refused rather than relabelled by a defaulted mime. Separately, four refusals named the feature id to the user: `"Tier 4 dormant (SENS-004)"`, `"TRI-003 is Tier 4 dormant"`, `"SENS-002 acoustic cough is Tier 4 dormant"`, `"rash evidence is Tier 4 dormant (SENS-004)"` — a code leak on the error path, which is why a gate that only scanned served payloads never saw it. All four now read as plain language.
- Four new gates, each canaried against a known-bad edit before being believed: `test_every_tier4_action_is_dormant` (fails on a dropped slug), `test_tier4_feature_set_is_not_vacuous` (pins the count so the check cannot go vacuous), `test_travel_advisory_belongs_to_travel_advisory`, `test_tier4_refusals_carry_no_codes` and `test_the_symptom_photo_gate_cannot_be_encoded_around`. 351 tests green, pyright clean.

Durability and audit: two features that were claimed but not wired (2026-10-10). Both were "done" in the sense that every piece existed, and neither worked end to end.
- **Queued writes never replayed (§16.1).** `SyncService` wrote every op to SQLite and never read the table back, so a write queued before a restart was durable on disk and invisible to `flush` — the promise was half kept, in the direction that looks like it works. `SyncService.load()` rehydrates unsynced ops and `flush` calls it; already-synced ops are excluded so a restart does not re-upload the history. Two tests, one canaried against a removed `load()` call.
- **The audit log had no writer and no reader (§17.4).** `afya.audit_log` existed in the schema and nothing inserted into it; the live log was an in-memory list that died with the process. `require_scope` now calls `check_access_logged`, so every guarded route writes an append-only `access_audit` row — there is no update or delete path in the store. `GET /privacy/access-log` reads it back, and the test is canaried against an unlogged `require_scope`.
- **The auditor role was unreachable**, which is why the log had no reader: `auditor` and `sysadmin` are deliberately not issuable through the app PKCE flow, and nothing else issued them, so the only role scoped to `audit_logs` could never hold a token. `POST /auth/staff/provision` issues them, guarded by the infrastructure scope so only a sysadmin can mint staff tokens. `OPERATIONAL_ROLES` is asserted to be the complement of `ISSUABLE_ROLES` over all staff roles, so no role can be unreachable in future without failing an import-time check. 356 tests green, pyright clean.
§18 wired end to end, and the webhook hole that had been open since the USSD callback shipped (2026-10-10). §18 was "implemented" in the sense that client code existed for seven national systems and no route reached any of them — a claim nothing outside the process could check. 191 operations over 189 paths now, up from 161.
- **Clients completed.** `AdamClient` (§18.1) is new: push case report and consented monitoring summary, pull status/contacts/case-definitions. It refuses a raw MSISDN or national ID on the way out (`PII_FIELDS` plus a pattern guard), because §18.1's field-level encryption presumes pseudonyms and this is the last cheap place to catch a caller that skipped them. `mutual_tls_configured` *reports* the cert pair rather than asserting mTLS — a client cannot claim a negotiation on its own behalf. `JaliClient` gained launch-link, corrections, assessment-share and clinician-review; `PheocClient` gained feed push; `MoHFFacilityClient` gained corrections and verification; `PPBClient` gained registry, recalls and suspicious-medicine reports; `SHAClient` and `TelcoGatewayClient` are new. The telco airtime call bounds an incentive at 500 KES in the client, since an unbounded one drains a budget through a single compromised worker token.
- **Feeds (§18.3).** `integrations/feeds.py` builds all six, with the min-cell-10 floor enforced on *both* feeds that carry counts — the geofence feed and the symptom feed — because a rule enforced at one egress is not enforced. The floor is on distinct subjects, not events: ten visits by four people is a cell of four, and counting events would clear the floor with a cell that describes those four. `cells_withheld` counts withheld cells, never rows folded into an aggregate — the first version of that number told a PHEOC operator records had been dropped when they had been merged.
- **The webhook hole.** `/channels/ussd/callback` was open, and every inbound webhook added after it inherited the shape. An unauthenticated webhook is an open write attributed to a real person: an unsigned hotline follow-up is someone else speaking as 719 into a feed citizens read, and an unsigned USSD callback is anyone driving the national menu. `require_webhook` now HMAC-signs the body and compares in constant time; an unconfigured deployment answers 503 rather than serving an open endpoint, because a dev box with an open webhook is how an open webhook ships. `tests/ci/test_inbound_webhooks.py` derives the guarded set from the routes' own OpenAPI parameters, so a webhook added later without the guard fails without anyone remembering — with the expected routes named, because a purely derived gate would let a dropped guard remove the route from its own check.
- **Four real defects found by driving the routes rather than reading them.** (1) Three request-validation `assert`s in the new routes raised `AssertionError`, which FastAPI serves as an unhandled 500, not a 422 — the same bug class as the evidence route. (2) `build_geofence_feed` reported rows folded into an aggregate as suppressed rows. (3) `/insurance/sha/facilities` and `/insurance/sha/benefits` were unguarded, making the app an open proxy that spends our SHA credentials on someone else's behalf. (4) Pyright found `InlineJaliPort` missing `share_assessment` — an `AttributeError` on every deployment without JALI credentials, on a route typed against the protocol.
- **My own guard test was not a gate.** Its first version accepted 401, 403 *or* 422 as evidence of a guard; an unguarded route whose vendor call fails also returns 422, so removing the guard passed. Tightened to exactly 401 and re-canaried. Five canaries on the new work (geofence floor, event-vs-subject counting, symptom floor, ADaM PII guard, signature comparison, unconfigured-deployment fallback), each watched failing before being believed. 386 tests green, pyright clean.

§16.4 bandwidth minimisation, made behaviour rather than intent (2026-10-10). The section names six mechanisms; batching and delta sync already existed in the sync path, and the other four were claims. 396 tests green, pyright clean.
- **Connection classes (`sync/views.py`).** `ConnectionClass` (wifi/metered/offline) with a `SyncPolicy` per class: batch size, delta-only, compression threshold, poll interval, and an image budget. `metered` is not "wifi, but slower" — it batches 50 rather than 500, polls every 300 s rather than 30 s, and uploads at 1280 px / q60. `offline` polls nothing at all. The policy is looked up from the connection class, never supplied by the caller: a phone that could ask for the wifi batch size while on mobile data would spend the user's airtime to defeat the policy it was handed.
- **Delta sync (`delta_payload`/`apply_delta`).** A removal travels as an explicit `-field` entry. Omitting the field means "unchanged", so a deletion the user made would never reach the server and the record would come back on the next pull — the round-trip is asserted over additions, removals, and no-ops alike. `remember_synced` is what makes the second write to a record a delta; without it every write re-sends the whole payload and §16.4's delta sync is a claim. An unchanged record produces no op at all rather than an empty request.
- **Compression is a threshold, not decoration.** gzip is applied only above the policy's byte threshold *and* only when the compressed form is actually smaller — gzip on a 200-byte body adds framing overhead and makes a metered request bigger. `SyncBatch` reports `encoding`, `wire_bytes`, `raw_bytes` and `saved_ratio` so a client can show the user the cost before spending it.
- **Content caching (`push not pull`), and the bug the section's own wording hid.** The alert feed was re-sent whole on every poll. It now carries a content-derived `revision` (a 16-hex digest of the *served* set, so a county subscriber is not told to re-download because another county got an item, and the revision is stable across a restart rather than an accident of process memory). A client that sends back the revision it holds is told `changed: false` and served no items; `since` returns only items newer than the last one seen. Both are opt-in, so a first-time client still gets the whole feed.
- Three canaries, each watched failing: a counter-based revision (fails the stability and county-scope tests), an ignored conditional request (fails the no-re-download test), and an ignored `since` filter (fails the incremental-poll test).

The §17 IDOR class, and the catalogue that offered the control it refused (2026-10-10). Forty citizen routes took a `subject_ref` out of the path or body, checked `self` scope, and then acted on whatever subject the caller typed — so the scope check passed for *every* citizen while the subject was the caller's to choose. Reading one person's location diary, deleting another's records and reading a stranger's contact list were reachable with a token issued to somebody else, and several of those routes required no token at all.
- **`require_self`** replaces the bare scope check on every personal-data route: it resolves the token, refuses any role that is not `citizen_anonymous`/`citizen_identified`, and requires the named subject to equal the token's own. Routes whose subject is a path segment (`/chronic/{ref}/bp-trend`, `/triage/{ref}/diary`) pass a reader instead. Family routes take `names_subject=False` and check membership separately, because a family board names its members' subjects and only a member may read it.
- **`tests/ci/test_self_scope.py`** derives the guarded set from the app's own OpenAPI (`subject_ref` as a parameter, or a body schema carrying one) and reads the guard's *identity* from the route's dependency graph — the spec does not name a dependency, and checking for an `authorization` parameter would have passed a route swapped from `require_self` to `require_scope('self')`. Four canaries, each watched failing: a dropped guard, a guard applied but not enforcing, a family-membership check that is always true, and the wrong guard.
- **The catalogue was the §11.1 defect the server fix created.** Every one of ~40 actions advertised a drawn `subject_ref` field labelled "Who is this for?" — a control the newly-guarded route refuses by construction. `MobileField.client_supplied` now marks the field so a generic client supplies it from its session and does not draw it; the field is carried, not dropped, because the client still has to send it. `test_a_client_supplied_field_is_marked_exactly_where_the_route_binds_a_subject` checks both directions against the route's guard, canaried both ways (an unmarked self-bound subject, and a marked worker subject).
- **The two worker actions are the counterexample that keeps the flag honest.** `send_exposure_notice` (CHW notifies a contact) and `transparency_report` (auditor) name someone else deliberately, so their subject is unmarked and relabelled "Person to notify" / "Person the report is about" — a client that overwrote those with its own subject would notify the wrong person. 407 tests green, pyright clean, both native clients build.

§SEC-005 export: a right with no route is not a right (2026-10-10). The spec grants "view, export, and delete all personal data at any time"; view and delete were wired, and export was a hardcoded `export_available=True` with nothing behind it — a claim no client could act on.
- `GET /retention/export/{subject_ref}` (self-bound, like the dashboard it sits beside) returns `PersonalDataExport`: the holdings, the shares, the deletion receipts, and `caveats`. It is built from the same register the dashboard reads, so what a person sees and what they can download cannot disagree.
- **The caveats are the substance, not decoration.** An export that read as more complete than it is would be worse than none — a person could hand it to a regulator believing it whole. It states plainly that raw sensor streams never left the handset, and that policy-retained records are named but not included.
- Exposed as `export_my_data` in the catalogue (SEC-005), so the right is reachable from every client without an app release. 409 tests green, pyright clean.

Android transport hardening: cleartext to any host, and credentials in the backup (2026-10-10). The manifest carried `android:usesCleartextTraffic="true"` — plain HTTP to *any* host, which cannot coexist with §SEC-003's "TLS 1.3 in transit". It is the setting added to reach a dev server and left in because nothing fails: the demo works, the release ships, every request readable on the wire.
- A `network_security_config` denies cleartext by default and permits it only to loopback (`localhost`, `127.0.0.1`, `10.0.2.2`), which is what the documented demo path (`adb reverse tcp:8000`) needs. Every other host is HTTPS-only.
- The bearer token and cached responses live in the `afya` SharedPreferences file; `fullBackupContent` and `dataExtractionRules` (the Android 12+ path, which `targetSdk 35` prefers) both exclude it, so a cloud backup a user did not ask for cannot carry the device's credential off it.
- `tests/ci/test_android_transport.py` canaries both the manifest and the config against planted defects, then checks the real files and follows the manifest's own `@xml/` references so a renamed rules file cannot silently stop excluding. Verified against the real manifest (reverting cleartext makes it fire).
- **Known flake, not from this change:** the full suite occasionally exits 134 at teardown (`recursive_mutex lock failed`) after reporting all tests passed — native resource contention from many app instances, observed once in ~20 runs. Not yet root-caused; the test *results* are unaffected.

Client-side write-ahead queue, and the DELETE that was a POST (2026-10-10). §16.1 promises the client works offline. Both native clients cached *reads* and had no queue for writes: a submit made with no network threw and was lost, which is the promise broken in the direction that looks like it works.
- **The outbox.** `performOrQueue` (Android) and `submitOrQueue` (iOS) keep a write made with no network, or one the server failed with a 5xx (a retry may fix it; a 4xx is a refusal a retry will not). It is persisted, replayed on the next successful submit or on resume/appear, and the count is shown ("N changes saved on this phone, waiting to send") so a user knows nothing was lost.
- **Replay is safe because the server makes it safe.** Each queued op carries an idempotency key derived from its own content, so the same op always carries the same key; the server returns the first response for a repeated key with a byte-identical body (§15.5). The client therefore never double-writes on a retry, and the iOS path builds the exact body text up front so the replay is byte-identical rather than merely equivalent. A file upload is never queued: its multipart boundary differs every time, so the replay could not be byte-identical.
- **An op the server refuses (4xx) is dropped, not retried forever** — otherwise one bad op would block the queue behind it. An unreachable server stops the replay rather than skipping ahead, so ordering holds.
- **The DELETE that was a POST.** `perform` sent `DELETE` as `request(resolved, "{}")`, and `request` inferred the verb from the body — so every DELETE action went out as POST and returned 405. Verified against the server: the old shape gives 405 on `/location/history/{ref}`, the fixed one gives 200. The verb is now explicit, and a non-2xx is a thrown `HttpError` carrying its code rather than being silently read as a body.

The health library that nothing served, and the decision tree behind it (2026-10-10). Auditing the registry against the catalogue found 30 features with no action. Most are legitimately non-user-facing (on-device sensing, encryption at rest, pseudonymity). Two were real: the §6.2 content library (INF-003/004/008/009/010/015) and the INF-002 "What Should I Do" decision tree. Both were fully implemented — `InfoService.library()` and `.decide()` existed, a 12-item en/sw corpus was seeded — and neither had a route, so Tier-1 health information was unreachable from every client.
- `GET /info/library?lang=` serves the corpus as `{slug,title,body,harmony_tag,lang}`. Never `item_id`: the seed ids embed spec codes (`INF-003-en`), which must not reach a screen. `ContentItem.slug` is the code-free handle the client keys on, the same move the action catalogue makes.
- `POST /info/content` publishes or corrects an item, and refuses one with no `harmony_tag` — §6.2 serves nothing that has not been harmonised against the official source.
- `GET /info/decision-tree?answers=` returns the root question, then the next question or the leaf recommendation as the caller passes `y`/`n`. A token that is not yes/no is refused rather than silently read as false. The answers are the caller's own symptoms, so no subject is named and no token is needed.
- Exposed as `what_should_i_do` and `health_library` in the catalogue. 416 tests green, pyright clean.

The feature codes on the screen, and the registry both clients were reading (2026-10-10). The vocabulary gate scanned served payloads, the catalogue, friendly copy and native string *literals* for the `PREFIX-000` pattern. A code can also reach a screen through a served payload, and Android's `MainActivity` rendered `list.joinToString { it.id }` over `/features` — the ops registry, whose `id` is the spec code (`CHAN-000`, `TRI-001`). A literal scan cannot see that: nothing in the Kotlin source spells a code, it prints whatever the registry sent.
- Android's `features()` now reads `/mobile/features` (ids are slugs) and renders `title`; `MainActivity` renders `it.name`. iOS had the same call in `AppState.refresh()` — it fed a `features` property no screen read, so the code never showed, but it still fetched the code-bearing registry on every launch; both the call and `FeatureDTO`'s consumption are gone, with the DTO kept and commented so nobody re-adds it.
- `test_clients_do_not_read_the_code_bearing_registry` flags any client string literal `"features"` without `mobile` on the same line. Canaried against a planted `send(path: "features")` in the iOS client (fails), and reverted.
- **The eight new catalogue actions were not offered by accident.** `hotline_directory`, `county_risk`, `medicine_registry`, `medicine_recalls`, `report_suspicious_medicine`, `sha_cover_verify`, `sha_facilities` and `sha_benefits` route to services that already existed with no client path to them. Each declares its source feature in `FEATURE_OF` — the catalogue build asserts it, so an action with no spec feature fails the whole suite rather than shipping unattributed — and each carries `FRIENDLY_COPY` in plain language.
- **`/insurance/sha/verify` and `/medicine/suspicious` were unguarded egress.** The first is a member-number oracle spending our SHA credentials; the second is an open relay into PPB's intake. Both now take `require_scope('self')`. 418 tests green, pyright clean, both native clients build.

Three spec sections that were prose, and nothing else (2026-10-10). Auditing the spec against the code found §15.3 (data residency and sovereignty), §15.4 (scalability targets) and §17.7 (data sharing agreements) had zero presence in `src/` — not a stub, not a comment, nothing. Every outbound client posted wherever it was configured; no code knew whether any agreement existed; no target was measured. These are the sections a regulator reads first, and a document that claims them with nothing behind it is the exact failure this repo has been closing all week.
- **Residency is a decision made before a request is built, not a log line after it was sent.** `GovernanceService.jurisdiction_of` maps a host to a jurisdiction by longest-suffix match, and an unrecognised host is *outside Africa* — the default that fails open is the one that ships a transfer nobody reviewed. `RESIDENCY_RULES` encodes §15.3 directly: case management and contact tracing may not leave Kenya; citizen personal data may sit anywhere in the AU; only anonymised analytics may be processed outside Africa.
- **§15.3's "without explicit legal review" is a gate, and §17.7's agreement is the review.** The two sections are one rule: an outside-Africa transfer of a class under legal review is permitted *given* a signed agreement with that party, and refused otherwise. A test canaries it both ways — the same transfer is refused with no agreement, refused with an unsigned one, and allowed only once signed with a date and a review reference. A free-text party name clears nothing, because the exception keys on a §17.7 party.
- **The agreements are state the deployment holds.** `DataSharingAgreement` requires every clause §17.7 names — purpose, scope, retention, security, audit rights — enforced by the model, so an incomplete agreement cannot be constructed and later read as one that permits sharing. `sharing_posture()` reports the seven parties, which are cleared, and which are unsigned; absent and unsigned are the same answer to a caller.
- **The egress audit reads the deployment's own config.** `EGRESS_WIRES` names each outbound wire, its §17.7 party and its data class; `GET /governance/egress` classifies the hosts `ServiceConfig` actually points at. A deployment whose ADaM URL is set to a non-Kenyan host is reported as a violation here rather than discovered on the wire.
- **Capacity is measured, and silence is not compliance.** `GET /governance/capacity` reports all thirteen §15.4 targets; with no measurements supplied every one is *unmeasured* and `all_measured_targets_met` is false — the honest report for a process that has not been load-tested. Latency and the two recovery times are upper bounds, so a 250 ms p95 meets the 300 ms target and a 3-hour RTO does not meet the 1-hour one; a canary confirms the direction is not ignored.
- Three canaries, each watched failing and reverted: the exception ignoring the agreement (2 tests fail), an unknown host defaulting to Kenya (6 fail), and every target treated as higher-is-better (2 fail). 436 tests green, pyright clean.

The security controls that claimed a CI that did not exist (2026-10-10). §17.5's table has eleven rows. Ten describe properties other modules already implement. The eleventh — "Secure development — SAST, DAST, dependency scanning in CI" — was false in the plainest way: there was no CI. No `.github/workflows`, no gate, nothing that ran on a change. A control table is read as evidence, so a row that names a pipeline nobody has is worse than a row that admits it is manual.
- **The controls are data, and each names where it is enforced.** `CONTROLS` maps every §17.5 row to the module that enforces it (`kind=code`), the cadence that obliges it (`kind=process`), or the command CI must run (`kind=ci`). `unimplemented` is deliberately *not* a kind — a control nobody has built should fail the test that asserts all eleven are accounted for, not pass as a fourth category.
- **The workflow and the table are locked together.** `CI_COMMANDS` names the exact shell fragments `.github/workflows/ci.yml` must contain; `test_workflow_runs_every_command_the_control_table_claims` reads the YAML and asserts each is present. Canaried by deleting the SAST step — the test fails. This is what stops the table drifting back into a claim.
- **DAST is not claimed as a CI gate, and the test says why.** §17.5 names it, but a dynamic scan needs a running deployment the job does not stand up. Listing it in `CI_COMMANDS` would make the row claim a gate that never runs. It stays a `process` obligation on a 30-day cadence instead.
- **Cadence is a date, not an intention.** `obligations()` reports each scan kind's last run and due date, and a kind never performed is *overdue* rather than exempt — an audit that has never run is the one most likely to be forgotten. `GET /security/posture` returns the controls, the CI commands, the obligations and the open findings; `GET /security/disclosure` is deliberately open, because a disclosure policy nobody can read is not one.
- **The gates were run before being claimed.** Bandit over `src/afya`: 307 findings, all `B101` (assert), which is this codebase's documented runtime-check style, and zero findings of any other kind. `pip-audit`: zero vulnerable dependencies. Both are now steps in the workflow. 447 tests green, pyright clean.

The gate that keyed on a parameter's name, and the family routes it could not see (2026-10-10). `test_self_scope.py` derived its guarded set from the *name* `subject_ref`. Six routes took a person's identifier under a different name — `/records/{ref}/labs`, `/records/{member_ref}/immunisation-gaps`, `/records/{guardian_ref}/wallet`, `/maternal/{ref}/anc-due`, `/women/cycle/{ref}/predict`, `/monitoring/child/{member_ref}/{schedule,catch-up,dose}` — and every one was invisible to it. They returned another family's records with a token issued to anybody, and several needed no token at all. This is the failure the repo has been naming all week: a gate is scoped to the bug you found, not the class it belongs to.
- **The set is now derived from any subject-bearing name, in the path or in the body.** `SUBJECT_PARAM_NAMES` includes `ref`, `member_ref`, `guardian_ref`, `family_ref`, `chw_ref`; the body half catches `/records/labs` and `/records/member`, which name their subject only in JSON. Over-inclusion is deliberate: a false positive is a route someone must justify, and the alternative is the next instance of the bug sailing through.
- **`require_self` was the wrong relation for a family route.** It compares for equality, which is right where a person names themselves and wrong where a guardian names a child — equality refuses the very user the route exists for. `require_self_or_guardian` applies `records.owns` instead, the single ownership rule (`subject == member`, or the member's recorded `guardian_ref` is the subject), so a family route cannot invent a looser one. The gate now asserts that any route naming `member_ref`/`guardian_ref` carries *that* guard and not the equality one.
- **`/records/member` creates the member, so nothing owns it yet.** That one route carries the ownership guard with `may_create=True` — a flag rather than a second guard, so the two stay visibly one rule with one exemption — and binds the write itself by forcing the recorded guardian to be the caller. A guardian_ref that is not the caller is a 403.
- **The unguarded worker routes were found too.** `/channels/chw/tasks`, `/channels/chw/tasks/{chw_ref}` and `/chw/{chw_ref}/case-load` served CHW task lists and caseloads with no token; all three now take `require_scope('assigned')`. The gate asserts every exempted worker route carries `require_scope`, so "worker route" cannot become a synonym for "unguarded", and `/auth/anonymous` — which issues the token and must require none — is a separate named set.
- **Canaried three ways.** The gate was watched failing against a planted unguarded `{ref}` route, against a planted `{guardian_ref}` route, and against the real app with one guard removed (`GET /records/{ref}/labs (None)`); each reverted. A driven test confirms U1's token is refused all nine family routes while U2 still reads their own child. 451 tests green, pyright clean.

The features nobody could reach, and the gate that asked the other question (2026-10-10). The catalogue's own test asserted that every *action* maps to a route. Nothing asked the reverse — which *features* no action reaches — and the answer was 24. A feature registered, marked available, and offered by no action is a capability no client can use, and a green suite over it is the appearance of coverage rather than coverage.
- **Four were real gaps with services already built behind them.** FND-003 (testing sites) and FND-005 (vaccination points) are `PlaceKind` values the places registry already holds and `/places/nearest` already returns, but the only way to ask was to pass `kinds` by hand — so a client could ask the testing-site screen for pharmacies and render them as test locations. Both now have their own route with the kind fixed server-side. INF-007 (service status: school and market closures, water interruptions, road and transport disruptions) is the `service` category the alerting feed already carries and the preference map already routes to `facility_alerts`; `/alerting/service-status` is a view over that one category rather than a second store, so a closure cannot be published twice and read as two events. LOC-001 (geofenced risk alerts) had `geofences_at` implemented and no route at all; `/surveillance/geofences-at` returns the advisory zones covering a point, open and read-only, with the entry advice the spec quotes.
- **`/places/nearest` returned a 500 for a deployment with nothing imported.** `PlacesService.nearest` asserts a non-empty pool, so the first client to ask a fresh deployment hit a server error instead of an empty answer. A locator with nothing imported has no answer, and the honest one is "none found yet".
- **The remaining 20 are on-device capabilities, not missing routes, and the code now says so.** `ON_DEVICE` names each with its reason: the three cross-cutting properties (offline-first, on-device processing, pseudonymity) have no call to make; the sensors (fall, sleep, wearable, external device, NFC) run on the device and post only a derived metric through `sensor_ingest`; radio and social are broadcast programmes run outside the app; and five spec ids are duplicates of a sibling the catalogue already reaches (MON-005/INF-011 water, MON-006/INF-012 air, MON-002/REC-008 antenatal, REC-002/REC-001 wallet, and the four library ids sharing one corpus).
- **A second test stops the list rotting.** An entry naming a feature that is covered, dormant or gone is stale and fails — otherwise the list accumulates reasons for gaps that no longer exist and stops meaning anything. The gate was canaried by removing the two new actions: it named `['FND-003', 'FND-005']` and exited non-zero. 455 tests green, pyright clean.

The content the app served with nobody accountable for it (2026-10-10). §6.5 says every content item has an owner, a reviewer, a date and a version, and that content moves through a workflow — English draft → clinical review → translation → back-translation → community validation → publish — before anyone reads it. `ContentItem` had four fields. The library was served to every client, in full, with no owner, no review date, no version and no stage, so an item could be written by anyone with a token and read by everyone the moment it existed. The spec section was not missing from the code; it was contradicted by it, which is worse, because the section reads as evidence that the governance exists.
- **The four fields have no defaults, so an unattributed item cannot be constructed.** `owner`, `reviewer`, `reviewed_on_iso` and `version` are required by the model. §6.5 says every item has them; an item that could be built without them is one served while nobody is accountable for it, and that is the failure the section names. A missing field is a ValidationError at construction, not a blank cell in a table a reader has to notice.
- **Only `published` is served, and the filter is at the one place the route reads.** `library()` filters on the stage rather than trusting a caller to have advanced the item. A draft, an item awaiting back-translation, or one retired for being wrong must not reach a screen, and the caller cannot be trusted to remember that.
- **The workflow is one step at a time.** `advance()` walks `WORKFLOW` in order and refuses a jump: a draft cannot be marked published without the four stages §6.5 puts before it, which would make every earlier stage decorative. `archived` is reachable from any stage — retiring something wrong should not require walking it forward first — and an archived item is terminal, not revived.
- **Staleness is a date, not a monthly intention.** §6.5 sets a review cycle (weekly in an outbreak, monthly otherwise); `stale()` reports the published items past it. Without a review date the cycle is an intention, and the item served longest ago is the one nobody has looked at since.
- **The write route is no longer open.** `POST /info/content` took any caller's content; it now takes the operations scope. §17.4 defines eight data-access roles and none owns content, so this rides `infrastructure` rather than inventing a ninth role the spec's table does not have. `POST /info/content/{item_id}/advance` and `GET /info/content/governance` are new — the first operator-scoped, the second auditor-scoped like the other evidence views.
- **The catalogue gained the two new actions and the write form gained the fields it now needs.** `publish_content` would have started returning 422 the moment the model required the governance fields; it carries them now, alongside `advance_content` and `content_governance`, each with friendly copy in plain language.
- **Canaried three ways, each watched failing and reverted.** Removing the stage filter served a draft (2 tests fail); removing the step check let a draft jump to published (2 fail); giving `owner` a default let an unattributed item be constructed (2 fail). 460 tests green, pyright clean.

The nine dashboards §19.4 named and nothing built (2026-10-10). §19.4 lists nine public-health dashboards for PHEOC, county health teams and MoH, and closes with "Role-based. Audit logged." None existed. The data did — triage assessments, case reports, contact lists, proximity tokens, content engagement, misinformation clusters, facility availability, alert deliveries — but nothing assembled it, so the named consumers had the raw routes and no view of the thing the section promises them.
- **The min-cell rule is the point, and it is enforced at the boundary.** §11.7 and §19.3 both set a minimum cell size of 10; a row drawn from nine people re-identifies whether or not it carries a flag. A suppressed row carries `value` and `denominator` as None — the count does not reach the wire at all, because a flagged small count is still a small count. `suppressed_cells` is reported rather than hidden, so a reader can tell coverage from emptiness.
- **The cell size is the group, not the county.** The rule tests the number of people the cell describes. A county of four million with one reported case is a cell of one, and clearing it on the population would report the single case the rule forbids. The population is context in the breakdown, not a licence — the first draft got this backwards and the test caught it.
- **Contact adherence and alert reach use their own denominator.** Completed over recorded contacts, acknowledged over delivered alerts — and the min-cell test uses that denominator, because a contact list is a small group by nature and that is exactly where re-identification lives. A county's population would clear it and should not.
- **The access rule is data, and it exposed a real lockout.** §19.4 names PHEOC, county teams and MoH; §17.4 gives the county officer `county_aggregate` and the PHEOC analyst `national_aggregate`. Guarding the dashboard on either scope alone locks out two thirds of the audience the spec names, so `require_any_scope` takes the set and still requires the role to hold one of them through the same `_SCOPE` map — no role was widened to make the route reachable. `individual_level_data` is reported as False because no dashboard returns a person.
- **The service reads from other services rather than keeping a second copy.** A dashboard cannot disagree with the route a person used to record the thing it counts; `_misinfo_clusters` and `_facility_rows` are overridable reads that return empty until a deployment wires the community and facility services, because a dashboard with no data is an honest empty and a fabricated one is not.
- **Canaried by breaking the threshold** (`< MIN_CELL_SIZE` to `< 0`): four tests fail, including the boundary case at exactly ten. Reverted; 467 tests green, pyright clean.

The success metrics §22 describes and nothing measured (2026-10-10). §22 is eight tables of targets — north star, reach, engagement, health outcome, technical, privacy and trust, equity — plus an evaluation framework. It is the section a funder reads. Nothing in the codebase knew a single one of the numbers, so every target existed only as prose in a document, which is the state in which a target is indistinguishable from an aspiration.
- **The targets are data, and the direction is per row.** `KPIS` is 42 rows carrying id, definition, target, unit, family, source subsection, and `higher_is_better`. That last flag is not decoration: latency, median symptom-to-care time, battery drain, APK size and complaint rates pass by being *under* the target, and a report that got the direction backwards would present a 40-hour care-seeking delay as comfortably inside a 24-hour cap. A test asserts a 250 ms latency passes a 300 ms cap and a 40-hour delay fails a 24-hour one.
- **"Lives saved" carries no invented number.** §22.1 gives it none — it is "measured via modelling" — so the row is flagged `modelled=True` with target 0.0 rather than being given a plausible figure. A fabricated target is worse than an absent one, because the absent one is visibly absent and the fabricated one is read as evidence.
- **An unmeasured target is not a met one.** `all_measured_targets_met` ignores the unmeasured rather than counting them as passes, so an empty report is `False` with every KPI named in `unmeasured` — not a green report assembled from silence. This is the same rule §15.4's capacity report already applies, and the section is more dangerous here because a funder acts on it.
- **§22.5 repeats §15.4 and the two are asserted equal.** `api_latency_p95_ms` and `uptime_pct` appear in both sections with the same numbers; `capacity_agreement()` walks the pairs and the test fails if they drift. Two copies of one number is the self-contradiction this repo keeps finding, and a reader comparing the two sections is exactly who would find it.
- **§22.7's equity metrics cannot be a single percentage.** §22.8 requires disaggregation by gender, geography, age and device; a metric whose whole purpose is a disparity, reported as one aggregate, cannot show one. `equity()` reports which of the four cuts it actually holds a number for and which it is claiming without — the coverage, not an assertion of coverage.
- **Five routes, scoped to the roles that own the question.** `GET /metrics/report`, `/metrics/kpis`, `/metrics/equity` and `/metrics/evaluation` take the audit scope — this is the evidence half and it names no person; `POST /metrics/measurement` takes the operations scope, and an unknown KPI is refused rather than stored and silently ignored.
- **Canaried four ways, each watched failing and reverted.** Counting an unmeasured target as met (3 tests fail), ignoring the direction flag (the direction test fails), deleting the no-cut gap branch (the equity test fails), and drifting §22.5's p95 to 500 ms (the §15.4 agreement test fails). 475 tests green, pyright clean.

The switch that turned on the outbreak capabilities for anyone who asked (2026-10-10). `POST /tier4/activate` had no guard. A request with no token at all — not a bad token, no `Authorization` header — activated all seventeen Tier-4 capabilities deployment-wide: EVD triage, the contact-monitoring module, the proximity tokens, the whole CHW reporting module, the exposure notifications and the early-warning engine. `/health` then read `tier4: true` for every subsequent caller. §11.1's three keys were a JSON body the caller filled in about itself, which is a gate that asks the intruder whether they hold the key.
- **The route now takes the operations scope**, checked through the same `_SCOPE` map every other route uses rather than a second list that could drift. §11.1's keys are held by PHEOC, the DPO and the flag, and none of them is a client describing itself; §17.4 puts infrastructure in the sysadmin's hands, so that is the role the route checks.
- **`dpia_reviewed` is no longer taken on the caller's word.** §24.7 puts the DPIA before each Tier-4 activation, and the key exists to hold shut the risk `raw_sensor_data_retained` names. The activation now carries a `dpia_input`, the surveillance service assesses it, and a *blocked* assessment cannot be acknowledged away by passing `dpia_reviewed=True` beside it — the assessment clears the key, not the caller. The refusal names what the assessment found.
- **The refusal is read off the activation that ran, not off the request.** With the DPIA clearing the key, `unmet_keys` computed from the caller's own claims reported every key held while nothing turned on — the diagnosability the route exists to provide, inverted. It now reads `registry.activation`.
- **The mobile catalogue offered four operator controls to citizens.** `publish_content`, `advance_content`, `content_governance` and `activate_outbreak_mode` are all guarded on an operator dataset, and all four were served to every caller — four screens that 403. That is §11.1's dormancy rule on a different axis: the rule exists so a person never sees a switch that would refuse them, and it was applied to the *feature* while the *caller* went unconsidered. `available()` now takes the caller's scope set and `OPERATOR_SCOPES` is the mobile mirror of each route's guard.
- **The mirror is crossed against the routes, not restated.** `test_operator_scopes_match_the_routes` reads each route's own dependency and asserts the catalogue names the same scope, so a guard that changes cannot leave a stale control behind. It walks the versioning facade's mounts to find the real routes — reading `app.routes` alone sees a mount table, which is how the earlier route count was wrong three times.
- **Canaried four ways, each watched failing and reverted.** Dropping the route guard (activation returns 200 to an anonymous caller), letting a blocked DPIA be acknowledged away, removing the catalogue's operator filter, and making the route ignore the caller's scopes. 477 tests green, pyright clean.

The county broadcast an anonymous caller could send (2026-10-10). `POST /alerts` had no guard either, and the route is the one that reaches every phone in a county. A request with no token published `{"kind": "outbreak_evd", "county": "Nairobi", "headline": "Ebola confirmed in Nairobi", "issued_by": "PHEOC"}` and the service logged it as a PHEOC-issued outbreak alert. `POST /alerting/feed` was the same shape: the durable broadcast behind the websocket, writable by anyone, and read by every subscriber. Both now carry the CHW's `assigned` scope — §17.4's role for a worker carrying a report up — and `POST /community/issues/{id}/resolve` carries it too, because anyone who can resolve an issue can close one they filed against their own facility.
- **This was found by asking the reverse of the question the IDOR gate asks.** That gate walks routes that *name a subject* and asks whether each is guarded. These three name no subject, so they were invisible to it — the same blindness as the parameter-name bug, one layer out. The question that finds them is "which routes write state shared between users, and who may write it".
- **The mobile catalogue carried seventeen more operator controls.** The CHW caseload and task screens, the case-report and peer-alert forms, the exposure notification, the hotspot and early-warning analysis, worker provisioning and the transparency report — all guarded on `assigned`, `county_aggregate`, `infrastructure` or `audit_logs`, all served to citizens as controls that would refuse them. `OPERATOR_SCOPES` now covers every one, derived by reading each route's own dependency rather than by inspection.
- **The gate runs in both directions, which is what makes it a gate.** One assertion fails when a marked action's route carries no guard; the other fails when a route guarded on a non-citizen dataset has its action unmarked. The second direction was blind at first — removing `issue_alert` from the marking list left the suite green — because a path-only lookup saw `GET /alerting/feed` (a citizen's read) and concluded the path was reachable. Keying on `(method, path)` fixed it, and the canary now names the missing action.
- **Canaried four ways, each watched failing and reverted.** Dropping the `/alerts` guard (three tests fail), removing a marking (the reverse gate names `chw_case_load`), marking a citizen action as operator-only (two fail), and removing the catalogue filter (one fails). 478 tests green, pyright clean.

The outbreak zone an anonymous caller could declare (2026-10-10). `POST /surveillance/geofence` had no guard. A request with no token declared a `risk_type: outbreak`, `alert_level: high` zone of 20 km over Nairobi, and `GET /surveillance/geofences-at` then returned it to every device inside it with the advice text attached. `POST /facilities` was the same: an anonymous caller added a facility to the registry the locator reads, and `/facilities/nearest` answered with it for everyone. `POST /surveillance/signal` took the county's fever and hotline counts — the numbers the early-warning z-score is computed from — and `POST /monitoring/food-alert` issued a public warning about a named product.
- **The class is "writes the authority's own record", and the guard is the county health team's scope.** §17.4 gives `county_aggregate` to the county officer, which is the role that maintains a facility registry and declares a risk zone. `/places/import-osm` takes `infrastructure`, because importing an OSM extract is a deployment operation rather than a county one.
- **`/integrations/jali/assessments` was missing the guard its ADaM twin carries.** `POST /integrations/adam/cases` takes `assigned`; the JALI route that pushes a summary of one person's assessment to a national system took nothing. Both now take `assigned`, so the two integrations cannot disagree about who may send a person's data out.
- **The gate asks the plainest question, which none of the others asked.** The IDOR gate walks routes that *name a subject*; the operator-marking gate walks routes a catalogue action points at; the broadcast guard was found by hand. This one walks every unguarded `POST`/`PUT`/`PATCH`/`DELETE` in the app and requires each to be named in `UNGATED_WRITES` with a reason that is about how a person reaches the service rather than about the data — the telco webhooks, the token issuer, the pure computations, the citizen's own reports, and the emergency routes that must not wait for a token. It also fails on a stale entry, so a route that is later guarded has to come off the list.
- **Canaried both ways, each watched failing and reverted.** Dropping the geofence guard named `('POST', '/surveillance/geofence')` as unjustified; guarding `/medicine/stock` — which the list justifies as a crowd-sourced report — named it as stale. 479 tests green, pyright clean.

The risk register §23 lists and the operations §24 describes, neither of which existed (2026-10-10). §23 is thirty-three named risks in five subsections with a mitigation column; §24 is six governance bodies, four cadence tables, a support SLA ladder, a training matrix, a funding model and an incident-response table. Every word of it was prose, and prose cannot be checked — which matters most in §23's mitigation column, where "automated staleness alerts", "bug bounty", "transparency reports", "manual fallback" and "PET architecture; min cell size" are claims about *this repo*, each of which either resolves to a module or does not.
- **The register is data and every mitigation naming software must resolve.** `Risk.control` is a `module:attr` reference and `OperationsService.resolve` imports the module and walks the attribute. All twenty-eight code rows land, so `unbacked_risks` is empty — and the test that says so is only meaningful because a canary proves the walk can fail. Two rows needed correcting on the way: `AdamClient` lives in `afya.integrations.adam`, not `.service`, and the first draft's `test_exposure_ranks_...` asserted Very High impact outranks High×High when §23 rates those rows *Low likelihood* — the product is the ranking, not the impact column.
- **A mitigation claiming code enforcement with nothing behind it cannot be constructed.** A model validator refuses `control_kind=code` with no `control`, so the failure is a `ValidationError` at import rather than a row that passes every check asking only whether a kind was given.
- **§24.8's breach deadline is statutory and the clock runs from detection, not from when the incident was written up.** `_instant` normalises a bare `2026-10-10` and a full `...T09:00:00Z` to aware UTC datetimes — the first version subtracted a naive from an aware datetime and turned "how long has this breach been open" into a 500 for the ordinary case of asking at the start of a day.
- **The defect this section exposed in existing code.** `PrivacyService.breach_notification` computed `max(0, 3 - days_ago)`, which made a breach notified three days late and one notified with three days to spare both report `0` — a report that cannot distinguish a met statutory duty from a missed one. It now carries `overdue`, logged at error level when the window has closed. Canarying it required adding the assertion to `test_privacy.py` first: the field was unguarded, so removing it changed no test.
- **A row with no spec deadline is not given an invented one.** §24.8 describes the outage and false-alert responses qualitatively, so those rows carry `deadline_hours=None` and the §24.3 ladder entry instead. A fabricated deadline reads as a commitment.
- **§24's duties recur or they are not duties.** A model validator refuses an obligation with neither a cadence nor a trigger. §24.7's "on change" and "on publish" carry triggers and no due date, because only a change can make them late; giving them cadence 0 would make the overdue list meaningless. A duty never performed is overdue, not exempt — the rule §17.5's scan cadence already applies.
- **The read routes are the auditor's and the write routes the sysadmin's, and the first test run proved it.** §17.4 gives those two roles `audit_logs` and `infrastructure` respectively; the initial helper minted one sysadmin token for both, and the GET assertions passed on a 403 body until the token was split. The test now asserts a sysadmin is *refused* the evidence views rather than widening either role.
- **Four routes.** `GET /operations/risks`, `/operations/incidents` and `/operations/duties` take the audit scope; `POST /operations/incidents` and `/operations/duties/{id}/performed` take the operations scope.
- **Canaried four ways, each watched failing and reverted.** Pointing a mitigation at a nonexistent method (the register names `R-O2`), measuring the breach clock from opening rather than detection (the detection test fails), treating a never-performed duty as not overdue (the duty test fails), and dropping `overdue` from the breach notification (the §17 privacy test fails, once it asserts the field). 500 tests green, pyright clean.

The growth strategy §20 and the rollout plan §21, where two of the six levers are claims about this repo (2026-10-10). §20 and §21 read as marketing — six growth levers, seven phases, nine retention mechanisms, an eighteen-step launch sequence — and most of it is: partnership terms, radio buys, training cohorts. But two of §20.2's six levers make claims about *this repository*. Lever 3 says "open-source client" and §23.5 repeats it as the answer to "perceived as government surveillance". Lever 5 says "Under 15 MB". Neither was checkable, and a claim about the artefact that nobody checks stays true by nobody looking.
- **The phasing table is a gate, not a calendar.** §21.1 gives each phase a tier ceiling and §11.1 puts three keys on Tier 4. `status` crosses the two, so a deployment running Tier 4 while its own plan says Phase 2 is a named finding with both numbers in it rather than a comparison a reader has to make by eye.
- **The APK budget is read from §22.5, not restated.** Lever 5's "Under 15 MB" and §22.5's `apk_base_size` are the same number in two sections; the rollout reads the KPI table, because a second copy is the drift this repo keeps finding. A test asserts the two are equal.
- **An unweighed build is not a small one.** `apk_within_budget` is None when nobody has weighed the build — the rule §15.4's capacity report and §22's metrics already apply, and the one that matters most here because the claim is being made to a partner.
- **The licence claim is reported, not assumed.** §20.2 says "open-source client" and the spec names no licence, so `licence()` returns the file's first line or None, and None is a real answer meaning the claim is currently unbacked. Picking a licence is the product owner's call; the code's job is to stop the claim passing silently. **The repository currently carries no licence file** — §20.2 lever 3 and §23.5's mitigation are unbacked until one is chosen, and `/rollout/readiness` says so.
- **§20.6's retention engine is crossed against the registry.** The section names nine features as the reason a person comes back after the outbreak; all nine resolve, so the argument has something under it. The mechanism table is injectable so the *negative* direction is reachable — with the real table every feature resolves, and a check that could never report a gap would be indistinguishable from one that works.
- **Four of §20.2's six levers are marked uncheckable.** Zero-rating, sixty-second utility, social proof and incentives are partnership and design commitments with no artefact to inspect. Marking them checkable would be the dodge this module exists to avoid, so they carry `checkable=False` and no check.
- **Three routes.** `GET /rollout/phases` is open — §21.1 names no person and no number about one, and a rollout plan a partner cannot read is not one they can align to. `GET /rollout/readiness` and `/rollout/status` take the audit scope, consistent with every other read in the evidence family.
- **Canaried three ways, each watched failing and reverted.** Disabling the phase ceiling (the mismatch test fails), reporting an unweighed build as inside budget (the size test fails), and returning no unregistered mechanisms (the injected-orphan test fails — this one passed on the first run because the path was unreachable, which is why the table is now injectable). 516 tests green, pyright clean.

§13's sensor matrix and §14's sensor specs, of which only §13.2 existed as data (2026-10-10). §13.1 is eighteen sensors with an Android column, an iOS column, the features each carries, a **Data Sensitivity** class and a battery cost. §13.2's nine fallbacks were already `SENSOR_FALLBACKS` in `afya/access/`. The inventory was not — and the sensitivity column is the load-bearing part, because §17.2's "raw sensor data is never retained" and SEC-002's "raw sensor data never leaves the device" are claims about *that classification*, per sensor. Nothing carried it, so "GPS is High" was a sentence in a document.
- **The matrix is data, and each class states what it permits.** `SENSORS` holds all eighteen rows; `HANDLING` holds one row per sensitivity class with `raw_may_be_retained`, `capture_requires_consent` and `share_requires_consent`. Every class carries `raw_may_be_retained=False` — §17.2 says never, for any class — and `raw_streams_retained()` computes that from the table rather than restating it, so the claim is checkable rather than asserted beside itself.
- **Two model validators refuse rows the spec's own wording forbids.** §13.1 writes LiDAR's class as "Low (derived only)": a row claiming derived-only *and* High is describing two different things, so that is refused at construction. And a retention cap on a Low-sensitivity sensor is a rule with nothing to protect — §14.1's LOC-003 gives location 21 days *because* it is High.
- **§13.1 and §13.2 are one promise in two modules, and crossing them found four disagreements.** The first cross-check reported `barometer`, `heart_rate`, `magnetometer`, `usb_otg` as absence-prone sensors with no fallback. Three are not real: §14.8 reaches SENS-008 through five sensors and calls the thermometer "where available", and the magnetometer carries no feature at all — losing either costs an enhancement, not a path, so §13.2's principle asks nothing of them. They are marked `enhancement_only` with the §14 reason rather than given a fabricated fallback.
- **The fourth disagreement was real, and a canary found it.** `missing_fallbacks` keyed on `universal()` — hardware present on both platforms. §13.2's microphone row reads "No microphone **access**", so a *permission the user declined* is an absent sensor even though the microphone is on every handset; §13.2 has no row for the accelerometer precisely because it can neither be absent nor denied. The predicate is now `can_be_absent()`, and six sensors carry `permission_gated`. Removing the `gps` fallback text now fails the test; under the old predicate it passed.
- **The `guard_raw` that was dead code.** `SenseIngest.guard_raw` asserted `not RAW_FORBIDDEN` on a non-empty tuple — always false, so it raised whenever anything called it, and nothing did. `extra='forbid'` already rejects a raw key; a `mode='before'` validator now refuses it by name with the §17.2 reason, and a test drives both the refusal and the legitimate payload.
- **Two routes, and the matrix is public.** `GET /sensors/capabilities` names no person and no reading, so a prospective user deciding whether the app suits their handset can read it; `GET /sensors/coverage` is evidence about the build and takes the audit scope like its siblings, with a test that a sysadmin is refused. The matrix is served with `used_for` and without `primary_features`, so no spec code reaches a screen.
- **Canaried four ways.** Downgrading GPS to Low (the sensitivity test fails), letting one class retain raw data (the raw-stream test fails), emptying the alias table (the two camera rows surface), and removing a fallback (this one passed on the first run — it exposed the `universal()` bug above, which is the whole reason a canary is pointed at a mutation rather than at a happy path). 530 tests green, pyright clean.

§SEC-001's eight consent categories (2026-10-10). §12.2 lists consent granularity as the mechanism behind ACC-001's "no feature is gated on a category the user did not opt into", and §SEC-001 names the categories, requires a plain-language explanation and a **clear statement of the consequences of revocation** for each, one-tap revocation, and a consent log the user can see. The consent *ledger* existed (`ConsentRecord`, `has_consent`, `withdraw`); the catalogue did not, so "granular toggles" was a sentence and a client had no list to render.
- **The catalogue is data, and every category carries its consequence.** `CONSENT_CATALOGUE` holds the eight rows with `label`, `explains` (the sentence beside the toggle) and `on_withdrawal`. Both prose fields are `min_length=1`, so a toggle cannot ship without telling a person what switching it off costs — the part of consent the section exists for. No spec code reaches either string.
- **Only research is separate, and the model enforces it.** §SEC-001 marks research "opt-in, separate". A validator refuses `separate_from_core=True` on any other category, so a second separate category — which would mean something else was being withheld from the core flow — fails at construction rather than at review.
- **Sensor monitoring is one decision per sensor, enumerated from §13.1.** §SEC-001's own parenthetical is "(each sensor separately)", so `sensor_consents()` walks `SENSORS` and `consent_toggles()` fills a per-sensor map for that one category. A sensor added to §13.1 without a consent entry would be a measurement nobody consented to; a test pins the two counts equal at 18. Each row is marked with whether §17.2 requires a grant for its class, so a Low-sensitivity row (a barometer reading) still appears — the granularity is per sensor — but a client is not told to demand consent it does not need.
- **Opt-in is the default, in code rather than in prose.** `consent_toggles` reads a category absent from the granted map as off. A default of on is not consent, so there is no path where a missing grant reads as a grant.
- **A blanket grant is not a per-sensor grant.** `sensor_consented` matches `sensor_monitoring:<slug>` exactly, so recording `sensor_monitoring` alone consents to no sensor. A canary that loosened this to a prefix match fails the test — which is the difference between the section's claim and a single boolean wearing its name.
- **One route, and it takes no subject.** `GET /privacy/consent` is public because the catalogue names no person and a prospective user deciding whether to use the app is who the plain-language text is for. It reads a subject from the token and nowhere else: the first version took a defaulted `subject_ref`, which meant an unauthenticated caller read a live stranger's grants. The existing IDOR gate in `test_self_scope.py` flagged it, and the fix was to delete the parameter rather than exempt the route — a subject a public caller can name is the IDOR shape `require_self` exists to prevent, and this route has no guard to bind it.
- **Canaried five ways, each watched failing and reverted.** Marking a non-research category separate (the validator fires), emptying a withdrawal consequence (the min-length fires), collapsing per-sensor consent to a prefix match (the blanket-grant test fails), reading grants without resolving the caller (the stranger test fails), and — the one that mattered — the route's own defaulted-subject bug, which the pre-existing gate caught before any canary I wrote.
- **One constant, one definition.** `MIN_CELL_SIZE = 10` was defined twice, in `afya/ai/views.py` and `afya/analytics/views.py`, under a comment claiming it was "reused rather than restated" — a comment that was false. §11.7, §19.3 and §SEC-004 state the same number, so `analytics` now imports it. 541 tests green, pyright clean.

§14.9 SENS-009's clinical-grade claim (2026-10-10). §14.9 lists six device classes a paired sensor can read and states the value: pairing "converts consumer measurements into clinical-grade data, improving triage accuracy", with the data flowing into the health wallet and the monitoring diary. The feature was recorded as an exemption — "external device pairing is a platform API, not a server call" — which is true of the pairing and false of the claim. `BPReading`, `GlucoseReading` and `MonitoringDay` carried no provenance at all, so a cuff measurement and a number typed from memory were the same row and the improvement the section promises had nowhere to appear.
- **Provenance is data.** `SOURCES` holds four classes — manual, Bluetooth, cable, facility — each with `clinical_grade`, `patient_entered` and `paired_device`. §14.9's value *is* the pairing, so two validators hold the line: a class claiming clinical grade without a device behind it is refused, and a class claiming to be both patient-entered and device-measured is refused. A canary that flips manual to clinical grade trips the second.
- **`clinical_grade` is a boolean, not a trust weight.** §14.9 says a paired device improves accuracy and does not say by how much. A coefficient would have looked like rigour while resting on nothing, so what travels is the fact a triage reader can act on: whether a person measured this or a device did.
- **The three readings §14.9 names carry it, and the fever verdict reports it.** A `MonitoringVerdict` now carries `clinical_grade` and `reading_source`, because the escalation fires on the temperature either way — 38.5 is a fever whether typed or measured — so the difference is only visible if the verdict says so. Default is manual: an unstated source is a person's number, not a device's.
- **The claim is checkable, not asserted.** `external_device_gap()` returns a `DeviceProvenance` naming the classes, the sources that reach clinical grade, and `unprovenanced_readings` — the gap. It is served on the existing audit-scoped `GET /sensors/coverage`. Before this the only statement that pairing mattered was a sentence in the spec.
- **Canaried four ways, each watched failing and reverted**, plus one re-canary after `external_device_gap` moved from a dict to a model. Making a hand-typed reading clinical grade, dropping provenance from the diary entry (the gap names `MonitoringDay`), letting the fever verdict drop `clinical_grade`, and removing the clinical-grade validator. 547 tests green, pyright clean.

§16.3's conflict matrix, and the appeal its immunisation row promises (2026-10-10). §16 was already the best-covered part of the offline story — `STRATEGY_MATRIX` matched §16.3's eight rows and `POLICY_BY_CONNECTION` covered §16.4 — so this was not a missing module but two things the existing shape could not express.
- **A losing op was retried forever.** In `flush`, a client op that lost a server-authoritative conflict had its `attempt` incremented and stayed in the queue. Every later flush therefore re-sent a payload the server had already overruled, walked `attempt` toward the backoff ceiling, and would have gone on doing so for the life of the install — a silent discard dressed as a transient network failure. §16.1's "nothing is lost" is a promise about writes that have *not* been decided; a decided conflict is a different thing, so the op now leaves the queue and the conflict is recorded.
- **`SyncStatus.conflicts` was reporting `pending`.** A queued write waiting for a network and a write the server overruled are different facts, and the one a person needs — my reading was overruled — was the one not carried. They are now counted separately, and a canary that re-conflates them fails.
- **The row is the unit, not the strategy.** §16.3's immunisation entry reads "Server-authoritative on conflict, **user can appeal**". A `ConflictStrategy` cannot hold a qualifier, which is why the appeal was nowhere: `CONFLICT_RULES` now carries the dataset, the strategy, the spec's own rationale, and `appealable`. A validator refuses `appealable` on anything but a server-authoritative row — an appeal against last-write-wins is an appeal against arithmetic, and append-only has no conflict to appeal.
- **The overruled value survives, which is what makes an appeal possible at all.** `ConflictRecord` keeps both payloads and both timestamps, so a person can see what the server kept and what it discarded. Without it the client's version was gone by the time anyone could ask.
- **`GET /sync/conflicts` and `POST /sync/conflicts/{op_id}/appeal`.** The first binds the caller's token with no subject parameter to get wrong; it returns non-appealable conflicts too, marked, because "the server decided and that is the end of it" is a fact a user should see rather than infer from silence. Filing an appeal is not deciding one: `open_conflicts()` keeps an appealable conflict open until the appeal is upheld or declined.
- **Canaried five ways, each watched failing and reverted.** Restoring the retry-forever bug, re-conflating `pending` with `conflicts`, marking a second row appealable, removing the appeal validator, and making every conflict read as resolved. The fifth canary initially *passed* — I patched the wrong file, so it ran against unmodified code; a canary that passes is a bug in the canary, and re-running it against the right file failed correctly. 554 tests green, pyright clean.

§16.1 principle 4 / ACC-003's offline indicator (2026-10-10). §16.1 lists five principles; four were behaviours the sync service already had. The fourth — "Offline state is visible. The UI clearly indicates sync status" — was not, and ACC-003 spells it out as "clear offline indicator in the UI". Nothing served the state of the queue, so a person had no way to learn whether their work was safe, and `ACC-003` sat in `ON_DEVICE` as "a property of every screen, not an action".
- **`OfflineState` computes the indicator rather than asserting it.** `pending`, `conflicts` and `open_conflicts` are read from the queue, and the label moves through offline → not yet sent → needs your attention → up to date. A person whose reading the health service overruled is told, rather than shown "up to date" because their op left the queue.
- **`durable` is read off the store, not stated as a constant.** §16.1 principle 5 promises "every queued write survives app restart and device reboot". A deployment with no store does not keep that promise, so the indicator says so in the same sentence it reports the queue — the difference between an indicator and a reassurance. A canary that hard-codes `durable=True` fails.
- **`GET /sync/state` is unscoped**, because it names no person: it is the state of *this* handset's queue, which the client reads to draw its own banner. `offline_state` joins the mobile catalogue as "Is my work saved?", and ACC-003 left `ON_DEVICE` as a result — the coverage gate flagged the stale exemption the moment the action existed, which is what that gate is for.
- **Canaried three ways, each watched failing and reverted**: hard-coding durability, hiding overruled writes behind "up to date", and reporting a caller-supplied zero for the queue depth. 558 tests green, pyright clean.

§14's accuracy statements and the disclosure §14.5 makes an ethical requirement (2026-10-10). §14 states an accuracy figure and a limitation list for each sensing capability, and §14.5 goes further than any other section: "PPG accuracy varies with skin pigmentation. Models must be validated across diverse skin tones, and the app must disclose known accuracy limitations. This is an ethical requirement, not an optional refinement." Nothing carried any of it — `ppg_band` returned a band and a detail string, and `SenseIngest.quality` was a field no code read.
- **`ACCURACY` holds one row per sense kind**, each with the spec's stated accuracy, its limitation list, and the plain-language `disclosure` the app owes. The disclosure is a required field, so a capability whose limits are known and unstated fails at construction — which is the thing §14.5 forbids.
- **The bias disclosure must name the bias.** `bias_disclosure_required` is set only on PPG, and a validator refuses the row unless its limitations actually mention skin. A flag saying "a disclosure is owed" would have been satisfiable by an empty promise; the check is that the limitation is stated.
- **`SenseIngest.quality` is consulted at last.** §14.5's own hedge is "blood oxygen saturation — where signal quality permits", and nothing enforced it. Below the capability's `quality_floor` the reading is reported as `not_available` and is *not* offered as an estimate — a band computed from an unusable signal is a number presented as a measurement, which is precisely what the disclosure exists to prevent.
- **The verdict travels with what it owes.** `POST /sensors/ingest` now returns a `QualifiedVerdict`: the band, a confidence, the disclosure, the limitations, whether it is diagnostic at all, and `seek_clinician` when an anomaly lands on a capability the spec calls not diagnostic. Two things are reported because they fail independently — a reading can be in range and unreliable.
- **`GET /sensors/accuracy` serves the disclosure**, public because it names no person and no reading, and because it is the text a person needs *before* trusting a number.
- **Canaried four ways, each watched failing and reverted.** Dropping the skin-tone limitation, ignoring signal quality, offering an unusable reading as an estimate, and serving the band without the disclosure. The fourth canary was first run with `git checkout` to revert it, which reverted the uncommitted route changes along with the canary; re-run from a file backup it failed correctly, and the routes were restored. 564 tests green, pyright clean.

§6.2's ten content principles, as checks (2026-10-10). §6.2 is titled "Content Principles" and all ten of its rules were prose. Nine had no check anywhere: a library item, a triage recommendation, a myth correction, a peer alert or a USSD menu could stigmatise the person it described, name the spec section it was implementing, or promise a certainty nobody can promise, and nothing failed. The only tone check in the repo was a four-word alarmist list inside `send_peer_alert`, which would not have moved if the section did.
- **Rules as tables, transcribed from the section.** `STIGMA_SUBSTITUTIONS` carries §6.2.9's own substitutions ("a person who is sick" not "an Ebola victim", "the area where a case was reported" not "the Ebola zone"), `BANNED_DIRECTIVES` carries §6.2.5's forbidden construction, and `ALARMIST_PHRASES` absorbs the list the peer-alert gate was keeping to itself. A test asserts each stated substitution is literally present in `docs/spec.md`, so the table cannot drift from the rule it claims to enforce.
- **The genre is the whole design.** §6.2.1 governs an *answer*, not a reference entry, and §6.2.6's "every answer" does not reach a form label or a question asked of the reader. The first version of this gate demanded an imperative verb of every library body and failed the seed's first-aid and burial items, which are reference material on purpose; it also flagged "Temperature °C" as un-forwardable. Both were the gate being wrong, and both were rescoped rather than the content changed — a check that fails correct content trains its reader to skip the line.
- **One genre exemption was removed after a canary caught it.** An `instruction` genre exempted from the stigma rule looked reasonable and was wrong: a peer alert is broadcast to a village and can name a neighbour as "an Ebola victim", which is the exact harm §6.2.9 exists to prevent. Canary 6 — reverting the peer-alert call site to its old local list — passed, which is how the exemption surfaced. The table now applies to any text a person reads, and the test carries the text that distinguishes the shared table from the local list.
- **Three genuine findings, all now fixed.** Three served strings named the spec section they implemented — the malaria recommendation in both languages carried "(spec 6.3 malaria trap)" and the differential advice carried "(spec 6.3)", which is the same failure as a feature code reaching a screen and reached the same surfaces §ACC-001 reads aloud. Two differential answers carried an em dash, outside GSM-7, so they could not be sent as the SMS §6.2.6 promises. And the decision tree's fever question asked about "an Ebola patient" instead of "someone who is sick with Ebola"; that one now reaches the mobile catalogue, the Swift and Kotlin clients and their parse test.
- **Enforced where content is written, not only in CI.** `POST /info/content` refuses a violating item with the verdicts, so the drafting screen can say what to fix, and `GET /info/content/governance` carries the audit over the whole corpus so a finding that predates the check is visible rather than assumed absent. The long-sentence rule is a `review` verdict and blocks nothing — §6.2.10 is a design intent and a burial protocol may legitimately run long.
- **Canaried nine ways, each watched failing and reverted.** Each of the five rules detached from the judge in turn, a spec section number and an em dash put back into served strings, a stigmatising sentence planted in a published library item, and both call sites reverted. The first pass had two canaries *pass* — the publishing test asserted the service method rather than the route, and the peer-alert test's text was caught by the old list too — and both tests were rewritten until their canaries failed. 581 tests green, pyright clean.

§6.4's misinformation response protocol, which was a table with no clock behind it (2026-10-10). §6.4 prints six steps with an owner and an SLA each, and six myth categories "to pre-draft". Both were prose. `MisinfoCluster` carried a velocity and a correction string and no time at all, so a rumour could be `spiking` and `correction_published` on the call that first saw it — the response appeared complete the instant the rumour was noticed — and §6.2.7's "correct misinformation within 24 hours" was a sentence with no clock behind it. §24.8's own incident row for a misinformation spike says "rapid response protocol" and names no number, which is what a rule looks like when its number lives only in another section.
- **The deadline is computed from detection, not asserted.** `ProtocolStep.deadline_ms(detected_at_ms)` derives every due time from the instant the rumour was first seen, and `response_clock` reports which steps are late as a fact. The detection instant is injectable on `flag_misinfo` and `clusters` for the same reason §24.8's breach deadline is computed from a supplied instant: a clock nobody can move is a clock nobody can test, and a deadline asserted is not a deadline measured. The first report for a topic starts the clock and a later report does not restart it — detection is the first sighting, not the latest.
- **Two of §6.4's six steps have no deadline, and the code says so.** Steps 1 and 6 are written "Continuous" and "Ongoing". They carry `sla_hours=None` and read as `open_ended` — a state that never completes, because "continuous" is not something that finishes. Inventing an hour count for either would be inventing a commitment the section declines to make.
- **Breach is a fact about the open steps, not about elapsed time.** A response that completed through step 5 inside the hour is not in breach at hour 30; one that has done nothing is in breach at hour 5. `completed_through` is the caller's fact — the service has no per-step state and inventing one would be inventing a workflow nobody runs — so the clock reports what it is given rather than assuming a response is on time. At the four-hour mark the triage is `due`, not late: an off-by-one on a four-hour SLA is the difference between a breach report and a false alarm.
- **Two of §6.4's six myth categories had no correction anywhere.** Conspiracy narratives and stigma narratives are named in the section and drafted nowhere. `coverage()` reports them as `undrafted` — a correction drafted during a spike is drafted under pressure, which is exactly what pre-drafting exists to avoid. It also reports `untranslated` (a correction missing a language §6.2.4 requires) and `orphan_corrections` (`denial_claim` and `unknown` answer no category the section lists, which a reader should be able to see).
- **Every correction was unpostable on a channel §6.4 requires.** Step 5 publishes "all channels simultaneously" and §6.2.6 names SMS. All six corrections separated their attribution with an em dash, outside GSM-7 — so the six strings the section exists to publish could not be sent as a plain SMS. The separator is now a hyphen, held shut by the same `NON_GSM7` table §6.2 uses. The table also became per-language: §6.4 step 4 drafts "in all relevant languages", and every correction now carries both.
- **One invented detail was removed from the table.** The first version gave the vaccine row `['infertility', 'microchip', 'untested']` and the burial row two myths of its own. §6.4 prints a parenthetical for four categories and none for those two. A pre-drafting brief is acted on, so an invented example is an invented work item; the bare rows stay bare and a test pins which they are.
- **Served, and carried on the feed PHEOC reads.** `GET /community/misinformation/protocol` returns the six steps with their owners and SLAs plus the coverage report — a coverage report that exists only in a test is one an operator cannot read, and PHEOC owns the step that is most often late. The hourly `misinformation_flags` feed now carries `detected_at_ms`, `next_due_at_ms` and `response_overdue` on every row: a cluster that arrives `spiking` with no due time is a rumour the one team able to act on it has no way to know is late.
- **Canaried eleven ways, each watched failing and reverted from a file backup.** Nothing carrying the clock on the cluster, a later report restarting it, `sla_hours` changed to disagree with the label printed beside it, breach computed from elapsed time instead of open work, an em dash returned to a correction, a correction losing Swahili, an invented myth example returning, the protocol route renamed away, the feed dropping the clock, the deadline boundary made exclusive, and a category slug changed. Two of the first pass were wrong and both were the test's fault: the "clock removed" mutation was a no-op that could not change behaviour, and the spec-drift test checked the SLA *label* against the spec but never the `sla_hours` the clock computes from — so `sla_hours=2` beside a label reading "4 hours" passed, which is a rate stated in one place and used in another. A second test now derives the hours from the label. 598 tests green, pyright clean.

§6.1's demand order and §6.2.4's language rule, which had no jurisdiction (2026-10-11). §6.1 is a table of ten questions "ordered by real demand, not by what health authorities want to publish", each mapped to the content response that answers it. None of the ten was modelled: the library existed, the dashboard existed, the triage flow existed, and nothing said which of them answers "Is it near me?" — so the ordering that is the section's entire contribution was absent, and a client had a flat list of routes with no idea which one a person asks first. §6.2.4's second sentence, "**Never publish English-only for a life-safety message**", had no jurisdiction to bite on: `ContentItem` carried a `lang` and `library(lang='en')` served whatever existed in English, and nothing marked an item life-safety.
- **The rank is a reference into §6.1, not a boolean an author sets.** `ContentItem.answers_rank` names which of the section's ten questions the item answers, and `is_life_safety` reads the flag off the section's own table. A per-item boolean fails for a specific reason: whoever is drafting under time pressure is the last person to mark their own copy as life-safety, and §6.2.4 exists precisely for the message someone is rushing out. Ranks 1–8 decide whether someone seeks care or infects a household; ranks 9 and 10 are the case count and the service status, and `why_life_safety` is a required field whenever the flag is set, so a row cannot claim it without stating the consequence.
- **Withheld in both languages, not served in one.** `library()` drops a life-safety item whose counterpart in the other required language is missing — serving it *is* publishing, which is the act the section forbids. A gap a reviewer can see beats an English-only message a Swahili speaker cannot read, so `untranslated()` names the held-back slugs and §6.5's governance view serves them.
- **A counterpart in the workflow is not a counterpart.** A Swahili translation sitting at `clinical_review` satisfies §6.2.4's letter — the item exists in two languages — while leaving the reader with an English-only message. `translated()` requires the counterpart to be published, which is what §6.5's stage filter is for.
- **Refused at both publishing doors.** `POST /info/content` refuses an English-only life-safety item at the moment of publishing, which is the only point where the missing translation can still be written; `/info/content/{id}/advance` refuses to walk one into `published`, because an item drafted in English reaches that stage through the advance route and a check on the write alone guards the entrance beside the one everybody uses. `GET /info/questions` serves the ten in the section's order.
- **Canaried ten ways, each watched failing and reverted from a file backup.** The library ceasing to withhold, an informational rank becoming life-safety, the flag losing its reason, each of the two publishing routes ceasing to refuse, the audit going silent, a seed row losing its Swahili counterpart, a seed row losing its rank, the question order being sorted away, and `translated()` ignoring the stage. Two mutations initially passed and both were the test's fault: the corpus test checked that the seed was bilingual but never tied a row's *rank* to §6.1's assignment, so marking the household-protection row `None` — silently un-gating the guidance §6.2.4 most needs to cover — passed while the corpus stayed bilingual. The ranks are now pinned. 610 tests green, pyright clean.

§6.2.3's "Timestamp everything", the last of §6.2's ten principles with nothing behind it (2026-10-11). §6.2.3 is one sentence — "**Timestamp everything.** 'Updated 2 hours ago' builds trust; undated content destroys it." — and nothing carried it. The library route served `{slug,title,body,harmony_tag,lang,answers_rank}` and no time at all, so the line the section prints as its own example could not be rendered by any client; `dashboard()` answered an unknown county with a defaulted low-risk row that read as today's assessment; and a hotline carried `verified=False` with nothing saying when anyone last looked at the number. §8.5 lists "Last updated timestamp" among the dashboard's fields and §23.2 asks for "automated staleness alerts", so the section was load-bearing in three places at once.
- **The age is computed from two instants, never stored.** `updated_at_ms` is an instant; the sentence is derived at serve time against the caller's clock. A stored "2 hours ago" is wrong an hour later, and the section exists precisely so that the age a reader is shown can be believed — so the test moves the clock and requires the line to move with it, which a hard-coded string cannot do.
- **The line is built server-side because USSD and SMS have nowhere to build it.** §5.4 names one content repository as what the channels share, and only one of WhatsApp, USSD, SMS and radio can do date arithmetic. `updated_iso` travels beside the line because the two fail in opposite directions: a relative age is unreadable the moment a page is cached offline (§16.4) and an instant is unreadable at a glance. Both are UTC, so a reader in Nairobi can compare them against their own clock.
- **The stamp is the service's, not the writer's.** `upsert_content` overwrites `updated_at_ms` unconditionally, and `advance` restamps on every step — an item published an hour ago is not an English draft written in September. The *sentence* is not a field at all, so nothing a caller posts can become the age a reader is shown.
- **An undated item is withheld, not served blank.** "Undated content destroys it" is the rule, so `library()` drops an item carrying no stamp and `undated()` names it on §6.5's governance view — the same shape as §6.2.4's withholding, and for the same reason: a gap someone can see beats a message that misleads.
- **A defaulted row is not an assessment.** `dashboard()` answers an unknown county with a low-risk default so a client always has something to draw, and `dashboard_freshness()` returns None for it — which is how a client tells the two apart. `HotlineInfo` refuses `verified=True` without the instant it was checked, because a tick nobody can date is an assertion nobody can act on.
- **The seed is stamped from its own review date, not from the wall clock.** A corpus claiming "Updated just now" for text written in September renders exactly the untrustworthy line the section names, and would also make the `undated()` path vacuous.
- **One writer was missing, so the stamp could never fire.** Nothing in the repo called `set_county_risk`, so the dashboard route could only ever answer its default — §8.5's "Current outbreak status by county" and the timestamp on it were both unreachable. `POST /info/dashboard/{county}` is that door, operator-scoped, and it joins the mobile catalogue.
- **Swahili's noun class governs the verb.** "saa 2 zilizopita" but "saa 1 iliyopita"; a single template prints "saa 1 zilizopita", which is not Swahili. The singular and plural are separate strings, and §6.2.4 puts the Swahili first. The line is inside GSM-7 in both languages, because §6.2.6 forwards it as an SMS along with the answer it dates.
- **Canaried seventeen ways, each watched failing and reverted from a file backup.** The library ceasing to withhold, the line becoming a constant, a writer keeping its own stamp, advancing not restamping, the seed stamping from the wall clock, an unassessed county given a line, a verified number needing no date, each band boundary moved by one, the numeric age going negative, the audit going silent, Swahili losing its agreement, the governance view dropping the audit, each route dropping or inventing the line, the sentinel becoming a plausible instant, and an em dash returning to the template. One mutation initially passed and was dead code: `max(0, ...)` in `age_label` is unreachable, because a negative age is already below a minute and lands in "just now" at the band boundary. The clamp that matters is on the numeric `age_ms` a client might draw a bar from, and that is now asserted. 628 tests green, pyright clean.

§6.5's escalation clause, the last of the section's six bullets with nothing behind it (2026-10-11). §6.5 ends "**Escalation:** Any content error affecting safety triggers immediate review and correction broadcast." The section's *retirement* bullet was modelled — `archived` is a stage reachable from anywhere — but retirement for being **outdated** and retirement for being **wrong** were the same state. An item pulled because its review date passed and an item pulled because it told people to drink salt water both read `archived`, and nothing said when the second was found, by whom, or that the escalation had fired at all. The retirement was also per-item, so a wrong English item could be archived while its Swahili translation kept being served to the audience §3.3 principle 8 puts first.
- **"Affecting safety" is read off §6.1, not accepted from the reporter.** The trigger is `is_life_safety(item.answers_rank)` — the same set §6.2.4's language rule keys on — and `ContentError` has no field for it, so a client that believes it is declaring its own item safe finds the model refuses the attempt. Whoever is retiring content under pressure is the last person to mark their own item as safety-affecting, and §6.5's clause exists precisely for the item someone is rushing out. One definition of life-safety serves both rules, so they cannot disagree the first time either moves.
- **"Immediate" is a clock, not a word.** §6.5 names no number and §24.8's own row for a clinical content error says "Immediate correction, clinical review, user notification" without one either. The number that *does* exist is §24.3's support ladder, and §24.8 rates this incident `critical`, so the deadline is `SUPPORT_SLA_HOURS[critical]` read from the ladder rather than a figure invented here — 15 minutes — and the label beside it is derived from the same hours so the two cannot drift, which is the failure §6.4's own `sla_hours` and `sla_label` demonstrated in a canary. The incident kind, severity and the two parties notified are read from §24.8's `INCIDENT_KINDS` row rather than restated.
- **Retirement is per-message, not per-item.** A wrong English item and its Swahili translation are one claim in two languages, and reporting an error withdraws every published item sharing the slug. The test asserts this on the **stored stage** rather than on `library()`, which is the finding the canary produced: §6.2.4 already withholds the English half of a life-safety message whose counterpart is gone, so a library-only assertion passed on a retirement that archived the English item and left the Swahili one published — the exact defect the test existed for. The stage is the fact; the shelf is a second rule that happens to hide it.
- **The correction is a message, so §6.2.4 applies to it.** §6.4 step 4 drafts a correction "in all relevant languages" and step 5 publishes "all channels simultaneously"; a correction that exists in one language is one half the audience cannot read. The gap is *reported* (`missing_langs`) rather than thrown at construction, because a wrong item must be pullable the instant it is found wrong — but the route refuses the broadcast when a required language is missing, before anything is published. The order is the assertion: a 422 that has already written the feed is not a refusal, and the item stays retired either way.
- **The broadcast is a channel event, not a string.** The correction goes to the `outbreak` feed category — §6.1's ranks 1–8 *are* the outbreak questions, so a life-safety correction belongs to the disease-alert preference — written durably first via `alerting.publish()` and then fanned out by `realtime.publish()`, the same two-step `/alerting/feed` uses, so a client offline when the correction fired still finds it. It is headlined by the retired item's own title, because a correction to "Boil drinking water" that arrives headlined by a slug is a correction to nothing a reader can recognise.
- **Two gaps are reported rather than papered over.** `preference_gap` says the correction lands in a category §9.6's preference model makes toggleable, so the one message that must reach a person is one they may have switched off. `superseded` asks whether the library holds a *published* item under the same slug stamped after the error was found — a fact about the shelf a reader sees, not about a POST — because a shelf with the guidance removed and no replacement is a reader with no answer.
- **The correction is one field per language, because a form has to be able to build it.** The mobile catalogue's generic form has no object type, so a correction sent as a nested `dict` is a correction no client can compose. The two flat fields are the wire shape and `correction` is the language map the rules read, so the two spellings cannot drift. The served escalation row is named by **slug**, never by `item_id`: a seed id embeds its spec code (`INF-003-en`), and this row is served twice — as the body of the language refusal and as the escalation log — so it is read by a person. The internal log keeps the id; the wire does not.
- **One gate was reading the wrong route.** `test_operator_scopes_match_the_routes` keyed its lookup by path alone, so `POST /info/content/errors` (guarded `infrastructure`) and `GET` on the same path (guarded `audit_logs`) collided and the gate compared one control's catalogue entry against the other's guard. It is keyed by `(method, path)` now, the lesson its own sibling gate already documented for `GET`/`POST /alerting/feed`. A canary confirms it: forcing the lookup back to a single method fails the gate.
- **Canaried seventeen ways, each watched failing and reverted from a file backup.** The severity not read from §24.8's row, the label carried beside the hours, the trigger asking "is it ranked" instead of "is it life-safety", only the named item withdrawn, the broadcast written before the language check, `review_overdue` frozen at report time, a non-safety item held to §6.2.4's full language set, the finding-instant assertion removed, the item named by id, the feed category invented, the correction headlined by a slug, a non-safety error broadcasting anyway, the archive skipped, `superseded` never asking the shelf, `by_slug` published-only, a duplicate error id accepted, and an unpublished item escalated. **Three of the first pass passed while mutated, and all three were the test's fault.** The corpus has life-safety items and unranked ones but no *ranked yet not life-safety* item, so "reads §6.1's flag" and "any ranked question is safety" were the same claim over that data — ranks 9 and 10 are now pinned. The non-safety language case used an English tip, where both readings agree; the Swahili tip is where they diverge. And the `preference_gap` assertion compared the constant to itself, so changing `outbreak` to `service` passed it and would have sent the correction to a subscriber who asked for facility alerts. 651 tests green, pyright clean.

§6.5's localisation workflow, the last of the section's six bullets with nothing behind it (2026-10-11). §6.5's fourth bullet is an arrow: "English draft → clinical review → translation → back-translation → community validation → publish." Four of the six steps were carried — the draft and the clinical review are `ContentItem` fields nobody can omit, `published` is the stage the library filters on, and `translation` is the step that brings a translated row into existence. The two between the translation and the publish were **names**: `advance(item_id, to='back_translation')` moved an item and recorded nothing about whether anyone had rendered the translation back, or taken it to a community, or what either found. The whole workflow could be walked by one person in a minute with every stage behind it and no check performed at any of them.
- **The arrow is one sequence read across the two rows of a slug, not one list walked per row.** §6.5's sentence is one arrow and the code carried it as one flat `WORKFLOW` list, so `advance` walked *every* row through `translation`, `back_translation` and `community_validation` — including the English row, which would have to be translated from English and rendered back into it. The section's own test proved the nonsense: it walked `x`, an English item, through `translation` and `back_translation` and asserted 200 for both. Read as what the section describes, the steps in the middle are steps of *producing a translation*: the source row goes draft → clinical review → published, the translated row is created at `translation` and carries the rest. `workflow_for(lang)` returns each walk and the two concatenated are §6.5's own order with `translation` at the handover — asserted, so a stage added to the section must land in one of the two.
- **Reaching a stage means the step that produced it is done.** That is the reading `published` already carried, so the evidence is required *at* the stage rather than after it: `advance` refuses `back_translation` without the render on file and `community_validation` without the community's record. Without the gate the two stages are names, which is what they were. The gate reads the same `localisation()` the review route serves, so "is this step done" has one answer — a canary removes the record and watches the gate and the report flip together.
- **A back-translation is a text and a person, and the person is not the translator.** The method's content is that someone who has not seen the source renders the translation back, so the record carries the rendered text and who produced it, and a record naming the translator as the renderer is refused at construction — the same person reading their own work and calling it a check. A render that comes back identical to the source is *reported* (`back_translation_matches_source`) and not gated: the premise is that a faithful render returns in different words, so an identical one is a signal, but a two-word string can match by chance and refusing it would block a legitimate short item. Whitespace and case are not differences.
- **Community validation is done by the community, and by a third person.** §1452 is explicit that the sensitive content is "developed with religious leaders, community elders, and anthropologists" while §6.5's table puts the drafting with the Comms team, so the record names the validator's role. The separation rule spans both records — the validator may be neither the translator nor the back-translator — and it lives in `separation_breach` because neither record can see the other; it is checked on the write that makes it checkable. It is refused, not reported as a gap: a step authored by the person whose work it checks is the step's name without the step.
- **The two records are two models, written in the order the arrow is walked.** One model with the community half optional would let a caller date a check to before it happened, and one POST carrying both would ask a client to re-send the rendered text on the second write — a client that can silently change what was verified. So `BackTranslation` is written when the item reaches `back_translation` and `CommunityValidation` when it reaches `community_validation`, and the community record is refused until the back-translation is on file: the community is shown what the render produced, and validating before it exists is validating nothing.
- **The report names the step that is absent, not the list of steps not yet done.** `missing` is the machine-readable list and `summary` is the sentence a person reads; the first version printed "back_translation, community_validation missing" for an item whose render was on file, which sends a reviewer to redo a check that is already done. The prose names the one absent step ("no back-translation on file"), and `_missing` judges each step separately rather than collapsing the set. The summary carries no spec code: the seed ids embed `INF-003`, so the row is named by slug — the same rule the escalation row follows for the same reason.
- **The review lists translations *and* a source row stranded at a translation stage.** The second set is the one a shelf-scoped view misses, and it is the workflow's own failure mode: an English item at `back_translation` is the defect the split fixes, and a report over translations alone would not surface it. The report is auditor-scoped for the same reason the escalation log is — the person who walked the item through the workflow is not the person who checks it was walked.
- **Canaried seventeen ways, each watched failing and reverted from a file backup.** The source row walking the full list, the gate removed, the renderer-is-not-the-translator rule removed, the cross-record separation removed, the render comparison forced false, `_claims` returning no evidence requirement, the "source text" refusal replaced with a generic word, the back-translation requirement on community validation removed, the review not auditor-scoped, the review dropping stranded source rows, the summary leaking the seed id, a source row accepting a back-translation, the comparison becoming exact-string, a draft accepting a back-translation before its translation, `next_stage` not refusing a wrong target, `recorded` always true, and `_missing` collapsing to the whole set. One canary initially passed while mutated — `_missing` returning `list(wanted)` whenever *either* record was absent — which is the same defect the "names the absent step" work fixed; it is now canaried. Three assertions in the new tests were wrong before the code was: the review's `missing` list, the summary text, and a test variable shadowing the token string with a header dict. 663 tests green, pyright clean.

§5.2's "Cost to User" column and §3.3 principle 3, "Zero-rated or it doesn't count" (2026-10-11). §5.2 is a seven-row table whose fourth column states what each channel costs the person, and §3.3 principle 3 is the rule the column exists for: "Data cost is the single largest barrier. Every channel must be zero-rated or free-at-point-of-use." Nothing carried either. `CHANNELS` in the registry is a bare tuple of slugs, so a channel had a name and no cost. What the repo carried instead was a *claim that could not be wrong*: `SmsOut.zero_rated` defaulted to `True`, so every message the system sent was stamped free whether or not any agreement existed, and the only check on it was `AfricaTalkingSmsPort.send` asserting the flag it had just been handed — a tautology that reads like a §5.3 control. §18.8's `zero_rating_rules()` pulls the carrier's billing rules and its own docstring says why ("a zero-rating rule that changed but was not pulled means the app tells people alerts are free when they are not"); it was fetched, served at a route, and applied to nothing. A control that exists is not a control that is applied.
- **The column is data, and the class is derived from the cell.** Five spellings — "Free", "Data (zero-rated)", "Data", "n/a", "Data + storage" — collapse into three claims: nothing is charged, the user pays for data, or the user pays *unless a carrier rule says otherwise*. "Free" and "n/a" stay separate because they are different facts (a radio costs nothing to hear; a CHW visit has no channel to bill), and the label is kept verbatim beside the class so every cell can be checked against §5.2 rather than trusted. `test_channel_cost` reads the table out of `docs/spec.md` and compares all seven rows cell for cell, including the parenthetical in WhatsApp's cost cell — that parenthetical is the whole difference between it and social media's "Data", and a paraphrase would drop exactly the part carrying the rule.
- **The qualifier is not the name.** §5.2 writes "SMS (zero-rated)", and the first version of the row put the whole cell in `name`. The sentence for an unverified SMS then read "SMS (zero-rated) is meant to be free … nothing has confirmed it" — contradicting itself in its own first three words. `qualifier` is held apart and `label()` reconstructs the cell exactly, which the spec comparison asserts.
- **Only the channels whose cell implies a rule require one.** SMS by §5.3 CHAN-1's critical requirement ("Zero-rated at the telco level. If a user is charged, adoption collapses"), WhatsApp by the "(zero-rated)" in its own cell. Marking radio, USSD or the human channel as requiring one would fire the gap report on channels that cannot gap.
- **"Nobody pulled the rules" and "the rules were pulled and do not cover this" are different facts.** Collapsing them reports every deployment with no carrier agreement — every dev environment, and the state before §20.5's Phase 0 step — as a channel that charges people, a finding derived from an absence. `charged` requires `verified`; `rules=None` is unverified, an empty list is the carrier answering "nothing", and only the second is a gap. A carrier that is *down* is the first case, not the second: an unreachable telco is not a telco that charges.
- **Each channel is matched against its own billing destination.** `covering_rule` reads the channel's `rule_prefix_hint` rather than a destination the caller passes — the fix for a defect in an earlier draft, where one `{'prefix': '719', 'rate': 0}` rule made WhatsApp report as covered because with no destination to match, any rate-0 rule counted. A shortcode rule cannot zero-rate Meta's data charges. WhatsApp's hint is `None` because the spec states no prefix, so it stays unverified rather than falsely covered; guessing one would manufacture the coverage.
- **A non-zero rate is evidence the carrier bills.** `rate` is what the carrier charges per unit, so a rule that arrived above zero is the opposite of coverage; reading its presence as free inverts the thing it is evidence for.
- **The free claim is resolved at send time, and the port sends regardless.** `send_sms` reads the rules at the moment a message actually goes out, because that is the only point where the claim reaches a person. `SmsOut.zero_rated` lost its default so a caller that does not know has to say so by omission rather than inherit "free" — and removing it immediately caught a caller: `test_at_sms_rest_send` constructed a message without the flag, and now states it *false*, which is the case the old default made inexpressible. The port no longer asserts the flag at all: refusing to deliver an outbreak alert because the telco paperwork lapsed would trade a shilling for a case, and neither §5.3 nor §3.3 asks for a refusal — both ask for the free-ness to be real, which means the claim must be able to come out false. The charge is carried on the message and reported instead.
- **Canaried eight ways, each watched failing and reverted from a file backup.** Rules unpulled treated as uncovered, `charged` no longer requiring `verified`, a non-zero rate read as coverage, `SmsOut.zero_rated` defaulted back to `True`, a §5.2 cost cell paraphrased, the SMS shortcode hint replaced with a guess, radio marked as requiring a rule, and — the one that initially passed — `covering_rule` returning the first rate-0 rule regardless of destination. That last one was the module's own defect still live one line further down, and it passed because the fixture held only the rule that matches: the positive path is not the path a gate is for. A rule for a different shortcode, a longer number, and the carrier's rule ordering are now pinned. One mutation (`charged=not free` for `verified and not free`) is logically equivalent given `free` already folds in `not verified`, so no test can distinguish them; the explicit form is kept because it documents why the field exists. 685 tests green, pyright clean.

§3.3 principle 12's outbreak diseases, and the four lists that were not the section's (2026-10-11). Principle 12 is the sentence the product's second half rests on — "Build for the outbreak after this one — Tier 4 activates for Ebola, cholera, Rift Valley fever, mpox, measles, and the next unknown" — and nothing carried the list. What existed was four spellings of a disease vocabulary on four surfaces, none of them the section that names it: `surveillance.CountySignal` and `SignalReading` had `^(evd|cholera|malaria|dengue|mpox|rvf)$`, `community.CaseReport` and the mobile catalogue had the same plus `measles|other`, and `alerts.AlertKind` had six `outbreak_*` members with neither `measles` nor `other`.
- **Measles is the defect that makes the class visible.** Principle 12 names it as a disease Tier 4 activates for, and `CountySignal` — the model the early-warning signal is computed from — refused it. The county that reports measles is the county whose signal the system cannot compute, and it is the county that most needs one. Dengue, on three of the four surfaces, appears nowhere in the spec at all.
- **One vocabulary in `registry/diseases.py`, with the spec's six joined to the repo's two.** `SPEC_DISEASES` is principle 12's own list in its order, `evd` carrying the wire code every surface has always used beside the section's prose "Ebola". `beyond_spec` marks `malaria` and `dengue` — real Kenyan outbreak diseases the section does not name — as this repo's additions rather than folding them in with the spec's, because a vocabulary that cannot say which of its members the spec asked for is the state this module exists to end. `other` is principle 12's own slot, "the next unknown": required everywhere a disease is reported, and deliberately not one of the named diseases, since a system that accepts only the five named ones can only ever alert on the outbreaks that already happened.
- **The pattern is built from the list, so the two cannot drift.** `DISEASE_PATTERN` is `'^(' + '|'.join(DISEASES) + ')$'` and all four surfaces now import it. `alerts.views` asserts at import that its `outbreak_*` members map onto the whole vocabulary — that assert fired on the first run, because the members had been added in the wrong order, which is the gate catching its author.
- **The gate is the class, not the instance.** A gate that pinned measles would pass the day somebody added `typhoid` to one surface and not the others. `test_diseases.py` parses principle 12's row, requires the code's list to be *it* rather than merely to include it, and scans the tree for any restated list — matching every string literal rather than the `pattern=` spelling, which a canary walked straight past with a bare module-level `DISEASE_RE = r'^(evd|cholera|rvf)$'`. Counting matched `cholera_food` in §8.5's food-alert kinds as two diseases, so the alternatives are compared as a set.
- **Canaried eight ways, each watched failing and reverted from a file backup.** Measles dropped from the spec list, the surveillance regex restored with measles missing, the `other` slot removed, `outbreak_measles` deleted, the mobile catalogue reverted to its own copy, dengue unmarked as the repo's, `english()` echoing an unknown slug instead of refusing, and a fifth surface restating the list. The last one initially passed: the check enumerated one of the two ways to write a regex, so it was widened and re-canaried against a bare module-level literal. 697 tests green, pyright clean.

§11.1's activation model — five triggers, three scopes, and the deactivation clause (2026-10-11). §11 opens with the constraint the whole Tier-4 half rests on: "Dormant until triggered by PHEOC. **Activates automatically for users in affected areas.** Requires no separate adoption effort because Tiers 1–3 already earned the install." §11.1 then gives the model as a five-row table — a trigger, a scope, and the features each turns on — and closes with a deactivation clause. What existed was `Tier4Activation`, one boolean over three keys, and `FeatureRegistry.available()` reading it. One switch for five triggers and three scopes, so the model was not the section's in either direction, and the collapse was not confined to the server: the mobile catalogue's `available(tier4_active: bool)` and the `/mobile/actions` route carried the same single flag, so a person the model activated for was shown no control at all.
- **The individual triggers could not fire, and that is the defect in one sentence.** §11.1 rows 3–5 activate `MON-009`, `LOC-001` and `LOC-002` for *one person* — "User identified as a contact", "User enters a high-risk zone", "User requests activation". Under one global gate, a person identified as a contact could not get their 21-day diary until PHEOC declared a *national* event, while §11's own sentence says activation is automatic for the affected user and is the mechanism by which the product reaches people without a separate adoption effort. The person who most needs the diary is the one contact in a county with no declared event. The county trigger could not fire either: row 2's scope is the county, and a confirmed case in Busia is not a national declaration.
- **The three individual rows are three facts, not one flag.** "Identified as a contact", "enters a high-risk zone" and "requests activation" are different determinations that activate different features — row 3 gives the diary, row 4 gives `LOC-001` and `ALT-004`. `SubjectCondition` keeps them distinct, and `ActivationState` carries a separate subject list per trigger number, because a single `is_individual` flag would make three triggers one, which is the same collapse the global gate performed one level up. A canary that unions the three lists is refused by the test written for exactly it.
- **A feature with two triggers is reachable by either.** `MON-009` is rows 3 and 5, `ALT-004` is rows 1, 2 and 4, `LOC-002` is rows 1 and 5, so `feature_available` is an `any` over the feature's rows and not a lookup of one. The `any` is what makes a person who *asks* for monitoring get the same diary as one identified as a contact.
- **The declaration is still the three-key gate, and a firing is not a declaration.** `pheoc_event_active` reads `Tier4Activation` rather than holding a fourth copy of "is the outbreak on", and it requires *both* the keys and a recorded row-1 firing: a declaration recorded while the DPIA or the flag is unheld is not an active event. §11.1's own Appendix-D question 3 leaves who holds the three keys open, which is why the gate is where that decision lives and the table is not.
- **Two of the seven named features are not Tier 4, and the divergence is recorded rather than resolved.** §11.1 rows 2 and 4 activate `LOC-001`; §7.3's tier table puts `LOC-001` in Tier 1, and §7.3 says cross-cutting and Tier 1 are always available. A feature cannot be both always-on and dormant behind a gate. The code follows §7.3 and `DIVERGENCES` says so where a reader will find it, because picking one silently is how the next reader loses an afternoon to it.
- **Twelve Tier-4 features have no trigger, and naming them is the point.** §11.1 names seven features and the registry has eighteen in Tier 4; six of the seven are Tier 4, so twelve are dormant with no row that turns them on — a capability nobody can reach. `unassigned()` reads them off the *registry* against the table, which is the only way to see it: a check that read the table alone would report perfect coverage forever. The count is asserted at twelve rather than described, because the arithmetic slip is one line away — counting the table's seven against the registry's eighteen gives eleven, and the difference is exactly the `LOC-001` divergence, so a docstring written from that sum would describe a set the function does not return.
- **The refusal names the trigger that would fire.** §11.1's rows are the only thing that turns a Tier-4 feature on, so a refusal says which one would: "This turns on when you are identified as a contact, or you ask for it." A person told "not available" with no way to find out what changes it has a switch that refuses them, which is what §11.1 exists to prevent. The sentence carries no spec code — it is read by the person refused — and the available branch is tested too, since a test of refusals alone never reaches it.
- **Firing a trigger needs the scope's own evidence, and the invariant is enforced rather than assumed.** A county trigger must name the county, an individual one must name the person, a declaration must not be about one person. A canary widened `deactivate`'s notified-subject filter and *passed*, which showed the filter was the only thing keeping a person out of the notified set: nothing refused a county firing carrying a `subject_ref`, so such a firing would have been counted in the notified subjects and the notified counties at once. The refusal is now asserted in `fire`, and a canary that removes the invariant and widens the filter together fails the test written for it.
- **Deactivation is the clause's three sentences as three fields, and the clocks are §17's.** "Automatic when PHEOC closes the event. Users are notified. Data retention clocks begin." The clocks are computed from `RETENTION_TABLE` rather than a number written here — §11.1 says the clocks begin, not how long they run — and the subjects notified are read off the individual firings, the people a trigger actually reached. Closing clears the firings, so a closed event stops activating its features: an event that is closed and a gate that is still open is the state the sentence exists to prevent.
- **Row 5 needed its own route, because the operator route is one a citizen cannot hold.** `/tier4/activation/fire` is `infrastructure`-scoped, and without a citizen route the one trigger a person fires about themselves is the one they cannot fire. `/tier4/activation/request` is `require_self(names_subject=False)` — the subject is the token's own and there is no `subject_ref` in the request to compare against, so the guard would otherwise 422 every call for failing to name a subject that naming would only let a caller forge.
- **The catalogue route resolves per caller, which is the half the client sees.** `available()` now takes a `feature_available` predicate and asks it per feature; the dormancy gate applies only to a dormant slug, so a feature below Tier 4 is never asked and the catalogue does not vanish whenever the event is off. A person who asked for monitoring is shown the diary the route behind it would serve them — a hidden control and a refusing one are the same failure from the person's side. `tier4_active` stays as the default for operator tooling, which has no subject.
- **Two gates were reading their subject too narrowly, and both are the same shape.** `test_self_scope._guard_of` recognised `require_scope` but not `require_any_scope`, so `/tier4/activation` — scope-guarded twice over — was reported as carrying no guard at all: the checker enumerating one of the two ways to write the thing. And the activation view guarded on `audit_logs` alone, which locks out the sysadmin who fires the triggers and closes the event; it is `require_any_scope(('infrastructure', 'audit_logs'))` now, the shape that guard exists for.
- **Two test assertions were wrong before the code was, and both were the test's fault.** `[A-Z]{3}-\d{3}` silently dropped `AI-001` from row 1's cell while the set comparison still looked meaningful. And `send_exposure_notice` carries an `assigned` operator scope, so a sysadmin's own §17.4 scope hid it and an activation claim read as a failure of activation — `ack_exposure` is the same feature with no operator scope, so it isolates the filter under test. Asserting `log_encounter` for row 2 was worse: row 2 activates `LOC-001, ALT-004` and `LOC-002` belongs to rows 1 and 5, so that test asserted a claim §11.1 does not make, and it would have passed had I widened the row to include it.
- **Canaried twelve ways, each watched failing and reverted from a file backup.** `feature_available` back to the global gate, the county scope losing its membership test, the three individual conditions collapsed into one list, the notified-subject filter widened (with and without the invariant that makes it redundant), unassigned Tier-4 always available, row 5 losing `LOC-002`, the activation view narrowed to `audit_logs`, `_guard_of` forgetting `require_any_scope`, the catalogue route dropping the model, and the catalogue predicate collapsed to one boolean. 731 tests green, pyright clean.

§4's target users — seven personas, seven secondary audiences, eight launch priorities (2026-10-11). §4 is the section that says who the product is for, and it was the only section in the spec with no representation in the code at all. Every other section had at least a table; this one had prose a reader could quote and nothing a check could stand on. The consequence is the shape the repo keeps finding: §22.7 can report the share of users who are female and §22.8 can demand the equity metrics disaggregated by gender, geography, age and device, while nothing anywhere says who those people were supposed to be — so no number has a target population to be measured against. What is built is the table, plus three crossings that turn it into findings rather than a second document.
- **The section is transcribed, not summarised.** `summary`, `needs`, `friction`, `entry_point` and §4.3's `segment`/`rationale` are §4's own words, and `test_personas.py` reads §4.1 and §4.3 out of `docs/spec.md` and compares them cell for cell. A persona re-written in a developer's words is one nobody can check against the section; the transcription is what makes a revision fail here rather than pass against a section that no longer says what the code claims. The item split is the section's own punctuation — Wanjiku's needs are four sentences, Dr. Kimani's four comma-separated phrases — and only case and the delimiter are normalised, so a need whose wording moved still fails.
- **Persona G has no Friction line, and the empty list is the section's answer.** §4.1 gives Amina Needs and an Entry point and no Friction at all, while the other six carry one. Every persona obviously *has* friction, and writing one would have been the easy fix — but an invented friction would be indistinguishable from the six the section states, which is the failure this module is written to avoid. `friction: list[str] = []` is the section's own answer, and the test asserts the absence rather than tolerating it.
- **Nothing is inferred that the section does not say.** A persona's `role` is None where §4.1 names no job §17.4 has a row for — only Mama Zawadi (a CHW) and Dr. Kimani (a clinician) do. A `languages` list is empty where the section names no language rather than filled from the county the persona lives in: Busia is a Luhya county and Garissa a Somali one, but §4 says neither, and a language attributed by geography is a claim the section does not make. A canary that gives Dr. Kimani a role from his description fails the test written for it.
- **The entry point is split by clause, not by word, and the first version split by word.** That version kept every remaining token longer than three characters, so all seven personas reported an unmapped entry point — `a: ['forwarded','friend','then','health','wallet']` — and a finding every row produces is not a finding. The unit is the comma-separated clause: an entry point is a sequence of routes, and a clause either names a §5.2 channel or is a route the channel table has no row for. The three that legitimately have one are the rollout and clinic routes — §5.2's seven channels are all consumer-facing, and a county health team rollout is not a channel a person arrives through. The other four are now clean, which is the assertion that fails if the split degrades back.
- **The channel slugs are derived and ordered by §5.2.** `ENTRY_CHANNEL_WORDS` maps the section's prose to the registry's slugs, longest phrase first so "community radio" is claimed by `radio` before `radio` alone can match it and a consumed phrase is not matched twice. `entry_channels` is re-ordered to §5.2's own sequence, so two personas' channel sets compare directly, and a derived slug is asserted to be one of the seven — an eighth would be this module inventing a channel.
- **The language crossing is a real defect, and §4 is what gives it a population.** `unserved_languages()` is `TIER1_LANGS - SUPPORTED_LANGS` computed from `LANGUAGE_MATRIX`, so a language promoted to tier 1 in the spec enters the finding on its own: `['bxk', 'ki', 'luo']`. §ACC-002 names six voice-reporting languages — Swahili, Dholuo, Luhya, Kalenjin, Kikuyu and English — and only two have string tables, so `rec()` raised and the triage route answered **500**. `unserved_personas()` names who is waiting: `['b (Otieno)', 'f (Grace)']`, and Grace is the sharp case — Siaya, a feature phone, reached by "SMS alerts, USSD menus, community radio, CHW visit", with §CHAN-2's own USSD menu ending "Language: English / Kiswahili / Dholuo / ...". The menu offered what the handler could not do, on the four channels that are the only ones she has.
- **The fix is a fallback that says which language it used, not a translated table.** A machine-translated Dholuo recommendation would report the gap as closed, and a wrong recommendation at a triage boundary is worse than an honest English one. `answerable()` accepts every language §ACC-002 lists and resolves one with no table to English; `TriageResult.served_in` and `language_fallback` carry the substitution into the payload, so a client that rendered the English string without reading the flag would present English to a Dholuo speaker as if it were her language — the same failure as the 500 wearing better manners. The same assert sat in `ChannelService.ussd` (a USSD session dying mid-menu, on the one channel Grace has) and in `CommunityService.correction_for` (a rumour correction that could not be sent to the community §6.2.8's response clock is most likely running for); both now resolve through `answerable`.
- **A second defect fell out of the USSD test: the route never accepted `lang`.** `/channels/ussd` took only the body, so Swahili — the language §ACC-002 puts first, and the one the menu table has — was unreachable on USSD. The test that caught it asserted the Swahili menu *differs* from the English one, which is the assertion a test of the fallback alone never makes.
- **The segment table keeps §4.3's order within a priority band.** `segments()` sorts by `Priority.order` — the enum's declaration order, so a future `p10` cannot sort before `p2` — and the sort is stable, so the two P0 rows stay in the section's order: High-risk counties before Community Health Workers, not alphabetically. The first version sorted by `(order, segment)` and failed its own spec comparison on exactly that row.
- **`priority_of` is the earliest segment, and Mombasa is a high-risk county.** §4.3 orders the *launch*, and a person in two segments is reached when either row is. The test asserting Amina was P1 was wrong before the code was: Mombasa is an urban high-risk county and §4.3's P0 row is "High-risk counties (border, urban)", so she is P0 by the same rule that makes Grace P3. The wrong assertion would have passed against a `priority_of` that ignored the segment's own text.
- **Two gaps are reported rather than filled.** §4.3 puts chronically ill adults at P1 — "Highest daily medication need" — and §4.1 never describes one, so `segments_without_a_persona()` returns `['chronically_ill_adults']`: a launch priority resting on a population the section never describes. And §4.2 names seven audiences while §17.4 has a row for two, so five read the product through no scope the RBAC table defines. A persona or a role invented to close either would be indistinguishable from the ones the section states.
- **Canaried five ways, each watched failing and reverted from a file backup.** The language fallback removed, the unmapped-clause capture disabled, the USSD `lang` forwarding dropped, the clinician role removed, and a transcribed need reworded. One canary's target string was wrong and the `assert before in s` caught it rather than letting a no-op pass as a green result — the failure being in the instrument, and invisible precisely because it looks like a clean result. 753 tests green, pyright clean.

§CHAN-5's human intermediary programme — seven kinds, five tools, and the code Persona B arrives through (2026-10-11). §CHAN-5 is the section §20.2 lever 4 rests on — "CHWs, chemists, faith leaders drive adoption, not app stores", answered by "Structured intermediary programme (CHAN-5)" — and its own rationale is the mechanism: "These people, not app stores, drive adoption in Kenya. Trust transfers through relationships." Nothing carried it, and the gap was load-bearing rather than cosmetic: §4.1's Persona B arrives through "SOS feature recommended by his SACCO chairman", §CHAN-5 names the SACCO chairmen as a target intermediary who gets a code, and the only thing in the tree called `referral` was a CHW activity label. The route a named persona takes into the product did not exist.
- **The section's lists are transcribed whole, including the parts that are not code.** Seven target intermediaries and five tools, verbatim and in the section's order, read out of `docs/spec.md` by the test. Three of the five tools are not code — a printed flip chart, an airtime incentive that depends on a carrier agreement, and a two-hour training — and `uncarried_tools` reports them rather than the list holding only what this repository ships. A tool list that dropped them would describe a programme §CHAN-5 does not.
- **A code is per intermediary, and a duplicate is refused rather than overwriting.** §CHAN-5's whole attribution mechanism is "each intermediary gets a code", so a code that resolved to two people attributes a referral to neither. The prefix names the kind (`BOD` for a boda SACCO chairman) so a code read off a flip chart says what the intermediary is without a lookup, and the alphabet excludes I, O, 0 and 1 — a code is read aloud to a person standing next to the intermediary and copied by hand, so the characters ambiguous in speech or handwriting are not in it. That is a property of how the code is used, not a claim about the section, and the docstring says which.
- **"Verified referrals" is the section's word and the code makes it checkable, and the first half of it is not in the section either.** A referral names the person who actually arrived — without one, the record is the intermediary's claim about their own activity, and paying on it would pay for assertions. §20.2 lever 6 says what the incentive is *for* ("Airtime or data bundles for health profile completion"), so completion is the qualifying event and an arrival alone is a click.
- **The replay guard is the half a real programme actually needs.** §18.8 puts the disbursement on a weekly run, and a weekly run that can pay the same referral twice is a budget drain reachable by replaying a request. It is refused rather than reported, because a second payment is money already gone, and the gate sits in the service rather than the route — the route sees an amount and a phone number, and a caller that posted the same body twice would otherwise be paid twice. A canary that removes the guard watches two carrier calls go out.
- **No amount is invented.** §CHAN-5 states none, so `kes` has no default and no value is written in the module; §18.8's telco client keeps its own 500 KES bound, which is the last place the figure is checkable. A default would be this module deciding a programme's budget.
- **"This deployment cannot pay" and "the request was wrong" are different answers.** An unconfigured deployment has no airtime agreement, and the route returns 503 rather than 422 for it — a caller can act on a bad request and cannot act on a carrier it does not have. The refusal leaves the referral unpaid, so a later run with an agreement in place can still pay it, which the test asserts.
- **Two roles, because issuing a code and recording a referral are different acts.** Enrolment is `infrastructure` (it spends the right to issue a payable code) and recording a referral is `assigned` (the same kind of write as the CHW activity routes). A CHW is refused enrolment and a sysadmin is refused nothing it should not have, which is what proves the two routes are scoped to different roles rather than merely token-guarded.
- **The §4.2/§CHAN-5 lists are not merged.** Pharmacy staff, faith leaders and teachers appear on both — §4.2 names people who *read* the product, §CHAN-5 names people who *distribute* it — so an intermediary holds a code, not a session, and `PersonaService`'s secondary audiences stay separate from `IntermediaryKind`. Collapsing them would make a distributor look like a user, which is the same error the two lists exist to distinguish.
- **Canaried seven ways, each watched failing and reverted from a file backup.** The replay guard removed (two carrier calls observed), the profile-completion gate removed, the duplicate-code refusal removed, a kind's name drifted, a tool paraphrased, the enrolment route unscoped, and the 503 collapsed into a 422. One test helper was wrong before the code was: it provisioned a CHW token through `provision_staff`, which is for §17.4's two operational roles only, so the assertion would have failed at provisioning rather than at the route under test — the token now comes from the PKCE flow the app actually uses. 771 tests green, pyright clean.

§19.1's on-device model table, §19.2's fifth model, §16.5's delivery plan — and the on-device flag that lied about Dholuo (2026-10-11). Three tables in the AI and app-size sections, and the defect that made one of them matter.
- **§19.1 is a seven-row table and the module carried five.** The two absent rows are the speech model and the cough *classifier*, and they are 21 of the 29 MB the section states — which is how the gap was found rather than by looking for a missing route. §19.1 closes "Total on-device model footprint: ~30 MB (loaded as needed, not all at once)", and the cards summed to 8. A footprint that read 8 MB would have described a client carrying neither model §ACC-002's "offline speech recognition for core commands" and §14.2's "cough type distribution" output depend on. Both are now transcribed, with the section's own bounds (`<20 MB`, `<1 MB`) and its fourth column.
- **`framework` is §19.1's fourth column, and §19.2 has no equivalent.** The section names a framework for all seven of its rows, so a device model without one is a row nobody transcribed — `register_model` refuses it. The refusal is scoped to on-device cards rather than to the field, because the server table is Model, Purpose, Inputs, Outputs and a blank framework there is the spec being silent, not a gap. A canary that blanks one watches the transcription test and both footprint tests fail.
- **The defect the missing speech model was hiding: `on_device` was `asr or req.offline`.** The flag was unfalsifiable — every offline request was on-device by construction, including one in a language `LANGUAGE_MATRIX` records as shipping no recogniser. Dholuo, Luhya (Bukusu) and Kikuyu are tier-1 languages with `asr: False`, and a request in any of them offline reported `on_device=True`, which is §SEC-002's "raw sensor data never leaves the device" reading as satisfied for a transcript the handset cannot produce. The flag now answers the only question it can — does recognition ship for this language — and the old test, which asserted the defect, was the thing that had to change. The intent is still served; the gap is in recognition, not in the response, and the test says so.
- **§19.2's fifth row is content recommendation**, the only server model whose output a *user* sees; the other four route to an epidemiologist, a supply chain officer or a risk communication officer. Its limitations are where the section's other rules bite: it ranks the existing library rather than writing content, so it cannot outrun §6.5 governance, and §6.1's demand order outranks personalisation for a life-safety item.
- **§16.5's delivery table had no representation at all**, and it is the table §19.1's "loaded as needed, not all at once" points at. The two sections disagree unless the Delivery column is carried: §16.5 lists a 20 MB speech model, a 25 MB medicine registry and a 15 MB content library and still closes "Base install under 15 MB", which is only true because the column makes them on-demand. Summing the table into one number reports 78 MB and reads as a breach the section does not have; summing only the initial rows reports 15 MB and hides everything the person may later carry. Both are reported, and the budget is read from §22.5's KPI table so §20.2 lever 5, §16.5's closing line and §22.5's target stay one number.
- **`at_install` is the property the split rests on**, and the one row that arrives without being asked is the per-county facility cache — the only size spent on every device whether or not anyone wants it. A canary that drops `automatic` from `at_install` watches that test fail.
- **Canaried five ways, each watched failing and reverted from a file backup.** The cough classifier removed (three tests), a framework blanked (four, including the pre-existing model-card test), the `asr or req.offline` defect restored (one — after a first attempt that patched only one of the two `on_device` sites and so did not fire, which is the canary telling me the branch was not the one under test), a module's delivery mislabelled (three), and `at_install` narrowed (one). One canary was reverted from the wrong file's backup because the patch was in `views.py` and the backup was `service.py`; the diff check caught it. 781 tests green, pyright clean.

§7's tier model and feature-ID scheme — the four tiers, the sixteenth prefix, and the map that flattened §14 (2026-10-11). §7 is three tables and a sentence, and it is the section the whole feature architecture is indexed by. Nothing carried any of them: `Tier` was an `IntEnum` with four members and no names, `FeatureSpec.id` had a hand-written regex, and §7.3 was a table nothing read. The ids were enforced and the scheme that gives them meaning was prose.
- **§7.2 declares sixteen prefixes and the validator accepted fifteen.** The sixteenth is `GTM-xxx`, Go-to-market, and it is the only prefix with no feature behind it — §7.3 names no `GTM-` id and no section defines one. So the gap was not a missing feature; it was a declared namespace the code refused, which means a `GTM-001` failed validation with a message listing fifteen prefixes that did not include the one §7.2 gives it. `id_pattern()` is now built from the section's table, so the regex and §7.2 cannot drift — the pattern was written once by hand, and a table in prose cannot change a string literal.
- **§7.1's "Ebola-Specific?" column is a check, not a label.** Three tiers are No and Tier 4 is Yes, and §11's opening sentence — "Dormant until triggered by PHEOC" — is the rule it encodes. `ebola_specific_mismatches()` reports a feature the column marks Ebola-specific that the registry places outside Tier 4: the activation gate cannot reach it, so it would be live year-round, which is the opposite of what the column says. The module asserts at import that exactly one tier carries the flag, which is what makes a canary on it fail at collection rather than in a test.
- **§7.1's "Usage Frequency" is the column nothing else states**, and it is what §22.3's engagement targets and §20.6's retention table are both measured against without either saying it. §20.6 gives each mechanism a cadence in days; §22.3 gives DAU/MAU a ratio; the tier's own expected frequency — "First session", "Weekly–monthly", "Daily", "Dormant → daily in outbreak" — was nowhere.
- **§7.1's closing paragraph is carried verbatim**, because it is the argument for the tier order rather than a remark: a person who installs for the facility finder in November has the outbreak module in March with no second adoption effort. `install_earns_later_tier()` is that sentence as a property the table must satisfy.
- **§7.3 is a summary and two of its rows are coarser than the sections they summarise.** It lists `SENS-001…008` under Tier 4 while §14 gives each sensor its own tier — §14.3 is "1 (basic) / 4 (outbreak-enhanced)", §14.5 "1 (basic) / 4 (monitoring)", §14.6 "2 (basic) / 4 (outbreak)", §14.7 and §14.8 are "3" — and the registry follows §14, correctly. The four ids that differ are recorded as divergences and both crossings exclude them, because a gate that re-reports a resolved divergence on every run is one whose real findings get ignored. That is the same failure as a check scoped wider than its jurisdiction.
- **The unmapped ids are reported, not forced.** Eighteen registry features §7.3's summary does not name: every `CHAN-` id (the summary names none), the extended `INF-011…016`, `REC-007…009`, `SENS-009/010`. §7.3 is a summary and these are features §5 and §8–§14 define without it catching up; a feature outside the tier map is one whose tier nothing in the spec states, which is exactly the state §7.3 exists to prevent, so it is a finding rather than a silent pass.
- **Canaried four ways, each watched failing and reverted from a file backup.** The `GTM` prefix dropped (three tests), a tier's Ebola-specific flag flipped (one, at import), the divergence exclusion removed (three — the resolved §14 rows reappear as findings), and the tier-map comparison made vacuous (one). 792 tests green, pyright clean.

§16.2's sync queue was a diagram with a function beside it and nothing applying it (2026-10-11). §16.2 is a flow with four labelled branches: `[Network available?]` → Yes → "Batch & send (exponential backoff)" / No → "Retry with exponential backoff", then `Ack received?` → Yes → "Mark synced" / No → "Retry". One of the four had code. `flush` iterated the queue, resolved each op, and marked it synced; it had no send-failure path at all, so an op could only ever succeed. `backoff_delay_s` was defined at `sync/service.py:13`, tested for monotonicity, and called by nothing — the only hit for its name in `src/` was a §23 control-catalogue *string* (`afya.sync.service:backoff_delay_s`), which is what made the gap look covered: the register said the mitigation was enforced in software, and the software it named was a function nobody called. That is the same class as the `resolve_sensitivity` finding — a control that exists is not a control that is applied — and the §23 gate could not catch it, because it checks that a control *resolves* (imports), not that anything calls it.
- **`SyncOp` gains `retry_at_ms`**, and `attempt` stops being write-only. `attempt` numbered the attempt about to be made and nothing read it; `retry_at_ms` is when the op may next be offered to the network, `None` meaning *due now*. That distinction is what makes the offline case correct: an op deferred because there was no network keeps its due-now status, so it goes out the instant a network appears rather than waiting out a delay it did not cause.
- **The two "No" edges are not the same wait, and the diagram draws them as the same box.** An op the network carried but the server did not ack has failed a *send* — the transport is up and the server is unhappy — so it earns a backoff and waits it out, because asking again immediately is the hammering the backoff exists to prevent. An op that could not be sent because there was no network failed nothing, so it earns no backoff. Both stay in the queue. `SendOutcome` (`acked` / `no_ack` / `no_network`) is what carries the difference, because a bool would collapse the two.
- **`flush` takes the connection, so the first diamond is answered rather than assumed.** `flush(now_ms, connection)` — with no transport configured the local model *is* the server, so without this an offline flush would mark every op synced, reporting work done because nobody asked the network. The transport seam (`send=`) exists for the same reason: with no transport, "Ack received?" can only ever answer Yes, so the branch below it was unreachable and the retry it schedules could never be observed.
- **`SyncStatus` separates `deferred` from `waiting`.** `deferred` is due-now-but-unsent (the diagram's "No" edges); `waiting` is queued inside its backoff window and not offered to the network at all. A client that conflated them would re-send an op the backoff had just scheduled to wait — the retry storm the backoff is for. `next_retry_at_ms` is the soonest any waiting op becomes due, so a client schedules its next attempt instead of polling on a fixed interval that is either too eager or too slow.
- **The retry schedule is durable, and an old database gains the column.** §16.1(5) promises a queued write survives a restart; a scheduled retry that did not survive one would lose the op on the restart that follows its first failure. `CREATE TABLE IF NOT EXISTS` is a no-op against a file that already has the table, so a handset that queued writes under the old build would keep its old schema and the first insert naming `retry_at_ms` would fail — losing the very queue the column protects. SQLite has no `ADD COLUMN IF NOT EXISTS`, so the store reads `PRAGMA table_info` first; Postgres gets the same guard as `ALTER TABLE … ADD COLUMN IF NOT EXISTS` in `schema.sql`, because the `CREATE TABLE` above it is equally a no-op against a deployed database.
- **The §23 control now names the applier.** R-T4's mitigation reads "Robust queue; exponential backoff; user-visible status" — three things — and the control named one function that computed a delay. It names `SyncService.flush`, which is where all three happen.
- **Canaried four ways, each watched failing and reverted from a file backup.** The backoff replaced with a constant delay (two tests), a no-network deferral made to earn a backoff (two), the schema migration disabled (one — the old database raises `IndexError` on the missing column, which is the data loss the migration prevents), and the offline branch removed (one). The first attempt at the backoff canary *passed*: I substituted a hardcoded `2000` for `backoff_delay_s(1) * 1000`, and the two are equal, so the canary proved nothing until I used a value that differed. A canary that passes is a bug in the canary. 798 tests green, pyright clean.

§3's vision, positioning, design principles and non-goals — the section that says what the product is, and the one section with no code (2026-10-11). §3.1 is one sentence, §3.2 is the brand, §3.3 is twelve principles, §3.4 is five non-goals, and none of it was anywhere in the source. Four of the twelve principles were already load-bearing by number — principle 1 in `personas`, 3 in the channel cost model, 8 and 9 in the content rules, 12 in `registry.diseases` — so the code cited a table that did not exist. A citation to "§3.3 principle 8" is unverifiable if nothing carries the row, and the number is the part that moves when a section is revised.
- **§3.2's claim had a declared check and no check.** `rollout.ANTIPATTERNS` carries `AntiPattern(antipattern='A name with "Ebola" in it', checkable=True, check='the served product name contains no disease name')`. One test read that string, and it asserted the anti-pattern was *present* — never that its check was performed. So the risk §23.1 names first ("Branded as an Ebola app and abandoned post-outbreak") had a check named in a table and nothing running it, which is exactly the shape §16.2's `backoff_delay_s` had one commit earlier: a control that exists is not a control that is applied. `brand_violations()` is the check, it runs at import against both names this build ships, and it travels with the `/brand` route rather than staying a function a caller has to know to import.
- **The forbidden words are the disease vocabulary, not a list.** `_disease_words()` reads `registry.diseases.DISEASE_ROWS`, so a disease added to §3.3 principle 12's set is one the brand check refuses with no second edit. `other` is excluded because "Unnamed disease (the next unknown)" is a placeholder, not a name anyone would ship. The check is case-insensitive across the whole name — the anti-pattern is about the *word* reaching a store listing, and "EBOLA Response" is the same failure as "Ebola Response" — and it returns every disease found rather than the first, so a rename carrying two is not half-reported.
- **`principle(n)` refuses a number the section does not carry** rather than returning `None`. The four existing citations are the reason: a citation that resolves to nothing is the failure the module exists to make impossible, and `None` would let it resolve quietly.
- **The tests compare against `docs/spec.md`, not against the module.** §3.3's twelve rows and §3.4's five bullets are read out of the spec text and compared cell for cell, so a revision that renumbers the table fails here rather than silently repointing the five modules that cite it. Two literal-vs-typographic apostrophes in §3.3 row 3 and §3.2 were the first thing this caught — my transcription had curly quotes where the spec has straight ones, which is a one-character difference that would have made every future comparison noise.
- **Canaried six ways, each watched failing and reverted from a file backup.** §3.3 row 5's principle reworded (the transcription test), a §3.4 bullet reworded (the non-goals test), the `other` exclusion dropped (the vocabulary test), case sensitivity restored (the brand check), a disease planted in the served name (the import-time assert and the brand test), and the first-disease-only truncation (the multi-report test). The route canary *passed* on its first run: I replaced `brand_is_clean(...)` with the literal `True`, and the test asserted `clean == True`, so the canary proved nothing — a canary that passes is a bug in the canary, and here it was a bug in the test too, which was asserting a literal where it should have been asserting agreement with the function. Both were fixed, and the canary now fails correctly. 807 tests green, pyright clean.

§5.1's rationale and the third ordering nothing carried (2026-10-11). §5.1 is two paragraphs, and the second is an ordering: "Information must live where people already are. In Kenya that is, in rough order of daily attention: WhatsApp, SMS, radio, Facebook, TikTok, and human conversation." It is the argument §3.3 principle 1 draws its conclusion from, and it was nowhere in the source.
- **§5.2 has two orderings and §5.1 has a third, and all three are different.** §5.2's Ch column numbers the channels 0–6 for reference; its Reach column ranks radio first ("Highest") down to the app ("Moderate"); §5.1 ranks WhatsApp first and radio third. Reach is not attention — community radio reaches the most people and is not where anyone's attention is at a given hour, which is why §5.2 itself gives it "Daily situation updates" rather than a role in reaching a person now. A build that read the Reach column as the priority for placing an alert would lead with radio every time. The test states the disagreement rather than resolving it: `by_ch[0] == 'radio'` and `by_attention[0] == 'whatsapp'`, asserted side by side.
- **§5.1 names six places and §5.2 has seven channels, and the sets are not the same set.** Facebook and TikTok are two §5.1 entries and one §5.2 row (`social`); USSD and the native app are rows §5.1 does not name at all. Both directions are carried — `COLLAPSED` for the fold, `UNRANKED` for the two the rationale is silent about — because a channel list sorted by an ordering that silently omits half of itself puts the omitted channels at an arbitrary end and calls it the section's answer. `attention_rank` returns `None` for an unranked channel rather than a large sentinel, since "§5.1 does not rank USSD" and "§5.1 ranks USSD last" are different facts and the caller needs to tell them apart.
- **The rank of a folded channel is its earlier entry.** `social` has two §5.1 entries and one rank, and Facebook (third in the sentence) decides it rather than TikTok (fourth). The alternative — averaging, or taking the later entry — would be a number §5.1 does not give.
- **A defect I nearly claimed and did not.** `AlertingService.notify_exposure` builds `delivery_channels=['native', 'sms', 'whatsapp']`, which leads with the app, and my first draft of the module docstring called that a violation of §3.3 principle 1. It is not: §ALT-004's Delivery cell reads "Push notification, SMS fallback, WhatsApp fallback", and the list is that cell transcribed in order. The two sections answer different questions — §ALT-004 orders the channels one exposure notification may travel by, starting with the one the app itself raises; §5.1 orders where information should be *placed* so a person meets it without being reached. Reading §5.1's order onto that list would reorder a cell that is already correct, so `order_channels` is offered as a function and not applied to it. The corrected docstring says which question each ordering answers.
- **Canaried five ways, each watched failing and reverted from a file backup.** The order's first two entries swapped (the sentence-sequence test), the app silently ranked instead of recorded (the coverage test), the folded channel made to take its later entry (the rank test), the unranked channels dropped from the sort (the stability test), and the verbatim sentence paraphrased ("must" → "should"). 814 tests green, pyright clean.

§10.5's three features: the topics each names, and what the corpus covers (2026-10-11). §10.5 is INF-008 Health Tips, INF-009 First Aid and INF-010 Burial Guidance. All three were in the registry, all three had seed items, and all three were accounted for in the coverage gate as "items in the health library corpus" — which is true of the one item each has and says nothing about the eight, eleven and six topics the section names.
- **The topic list is the load-bearing part, and nothing read it.** §INF-008 says "Rotating, seasonal, locally relevant health education" and then names the rotation: hygiene, nutrition, mental health, first aid, child development, chronic disease management, injury prevention, sexual and reproductive health. A corpus with one handwashing tip satisfies the feature id and serves one eighth of what the feature is. §INF-009 names eleven injuries and carries the section's own estimate of what a hole costs — "Fully offline. One of the most valuable offline resources possible." So `coverage()` reports which named topics the corpus has an item for and which it does not, and the seed's first-aid corpus covers exactly one of eleven.
- **Coverage is computed against the corpus, not asserted about it.** The item's own title, body and slug decide, so the report is about what the corpus says rather than how it is filed — the test plants the counter-case, an item tagged `first-aid` about burns, and asserts it does not cover snakebite. A tag saying `first-aid` over one item is what made the gap invisible.
- **The check errs toward naming a gap, and the first version erred the other way.** It matched any keyword of a multi-word topic, so the handwashing tip reported as covering mental health, injury prevention *and* reproductive health — the word "health" appears in its title and "prevention" in the seed's Ebola-prevention slug. A false "covered" is the failure that hides a hole, because it tells a content owner there is nothing to do; a false gap costs one question. The generic-word guard (`health`, `prevention`, `management`, `considerations`) is a canary, and the direction of the remaining error is asserted rather than left in a docstring: the handwashing tip *is* hygiene and does not say so, and the test requires it to report as a gap.
- **The gaps are reported, not enforced.** A deployment that has not received the MoH's snakebite guidance is not broken, and refusing to serve the bleeding item because snakebite is missing would trade the content that exists for the content that does not. `content_seed` says the same thing in its own docstring — it is a stand-in for the MoH corpus — and §INF-010's Sensitivity clause is carried as data (`SENSITIVITY_REVIEWERS`) because "developed with religious leaders, community elders, and anthropologists" is a requirement on the process that produced the guidance, and a process note is one nothing checks.
- **Two transcription errors the spec comparison caught.** The §INF-008 Topics cell ends "sexual and reproductive health." and §INF-009's ends "shock." — the trailing period is sentence punctuation, and the parser strips it so the list compares as topics rather than as prose. A comparison against the spec text is what surfaced both, and both were my transcription rather than the spec's.
- **Canaried five ways, each watched failing and reverted from a file backup.** A §INF-009 topic dropped from the list, `gaps` forced empty (the hole hidden), `covers` made to return `True` regardless of words, the generic-word guard removed (the false positives return), and one §INF-010 sensitivity party dropped. 821 tests green, pyright clean.

§17.4's RBAC table against the routes and the token-issuing paths (2026-10-11). §17.4 is an eight-row table — role, access — and `privacy/views.py:_SCOPE` transcribes it as a role → scope-set map. §17.5's Authorisation control names that map as the enforcement of "RBAC with least privilege". Nothing compared the table to the routes, so two failures were invisible, and they are the same class as the `resolve_sensitivity` finding: a control that exists is not a control that is applied.
- **Three declared scopes have no route.** `_SCOPE` declares nine scopes; the routes guard on six. The unguarded three are `family`, `community_aggregate` and `consented_patient`, which are §17.4's "Own and linked family data" (citizen identified), "community aggregates" (CHW) and "Patients who have consented to share" (facility clinician). A scope with no route is a capability the table claims and no caller can reach — the same shape as `rollout.ANTIPATTERNS`' declared-and-unperformed brand check, and the same shape as a §7.3 feature outside the tier map.
- **The family case is the sharpest, and it is why this is a finding rather than a defect.** §ALT-002's family board is a Tier 3 feature and its three routes — `/alerting/family/link`, `/alerting/family/check-in`, `/alerting/family/{family_ref}` — are guarded on `self`, so a caller reaches a family route through a scope §17.4 does not give it, and the `family` scope the table grants `citizen_identified` is what the row says rather than what the app does. Both readings are safe here: the `self` guard compares the token's subject and the board checks membership. The test asserts the negative (`'family' not in names`), which is weak by shape — it passes on an empty set — so it is canaried by re-guarding the route on `require_scope('family')` and watching it fail.
- **One role can never hold a token.** `RBACRole.citizen_identified` exists, holds `self` and `family`, and is issued by nothing: `require_token` resolves any anonymous token to `citizen_anonymous`, and the PKCE flow asserts the requested role is in `ISSUABLE_ROLES`, which excludes both citizen roles. §3.3 principle 6's "Identity is opt-in" is the sentence that gives §17.4's second row a reason to exist, and nothing implements the opt-in. `citizen_anonymous` being unissuable is correct for a different reason — §15.5 issues anonymous tokens and the guard resolves them to that role by construction — so `unissuable_roles()` returns both facts and `identity_gap()` names the one that is a gap.
- **`route_scopes()` reads the source, not a list.** A hand-kept list is the thing that drifts: the whole finding is that the table and the routes disagree, and a second list would agree with whichever of the two it was written beside. The assertion is exact (`found == {...}`) rather than a superset, so a `route_scopes` that reported every scope it could think of would fail it.
- **Two canaries passed, and both were bugs in the checker rather than in the code.** The first version carried a `GUARD_SCOPES = ('self',)` constant that papered over the gap, which made the assertion that `self` was found vacuous: the canary that emptied the constant still passed, because six routes carry `require_scope('self')` literally. The constant is gone and `_DATASET_CALL` reads the `dataset='self'` literal inside the guards. Then the canary that removed `_DATASET_CALL` still passed, proving that spelling is not load-bearing in this codebase — it is kept with a comment saying so rather than deleted, because the route-level spelling is an accident of where `self` happens to appear and not a property of the guard.
- **Reported, not repaired.** Adding a route so a scope has a caller would be this code inventing an endpoint the spec does not ask for, and issuing `citizen_identified` needs an identity-upgrade flow §15.5 does not specify. Both are product decisions, and what a build owes is the finding. `/privacy/rbac` serves the table with both findings attached, auditor-scoped, because either alone reads as a complete answer: a scope no route requires looks fine next to a role list, and a role no path issues looks fine next to a route list.
- **Canaried nine ways, each watched failing and reverted from a file backup.** A role given a scope §17.4 does not give it, `citizen_identified` made issuable, the `require_scope` reads removed (every guarded scope disappears), a real gap filtered out of `unreachable_scopes`, the Access cell paraphrased, a row dropped, the identity gap papered over, the family board re-guarded on the `family` scope, and a gap filtered out of what the route returns. Two of the nine were pointed at `views.py` on the first run when `ROLE_ACCESS` lives in `rbac.py` — the canary asserts its target string is present before mutating, which is what caught it rather than a silent no-op and a false all-clear. 828 tests green, pyright clean.

§5.4's channel interoperability: the shared triage engine, and the spec codes on the channel surfaces (2026-10-11). §5.4 is five "All channels share" claims and four cross-channel journeys. The first claim is "a single triage engine — same clinical logic regardless of entry point", and nothing checked it: the app reached triage at `/triage/preliminary`, and every channel answered from its own keyword rules. Two of those rules put a spec code in front of a person.
- **`route_whatsapp` replied `'TRI: fever/symptom detected — malaria test first; call 719 if no improvement in 48h.'`** — a feature id, a colon and a developer's shorthand, served to whoever messaged "I have fever" on WhatsApp. The second branch replied `'FND: send your location to find the nearest facility.'` The USSD menu was worse: every selection answered `f'Selected {choice}: routed to feature.'`, which is a sentence written for a log line, read on the one channel §4.1's feature-phone persona has. The user's standing constraint is that spec ids must not reach the UI, and the gate enforcing it scanned the action catalogue, the friendly-copy table, the served `/mobile/*` payloads and the native string literals — every one of them a structured surface. A channel reply is a sentence, and no gate looked at one.
- **The gate is widened to the channel surfaces as they are served.** `test_the_channel_surfaces_carry_no_codes` drives the WhatsApp route, the inbound-SMS route and every USSD selection over HTTP and scans the reply strings, because a gate scoped to the fields a payload happens to have is the checker that enumerates one of the ways the thing it checks can be written. Canaried three ways, including a replay of the exact original defect.
- **The second engine is gone, and the crossing is asserted as equality.** `ChannelService` now takes the `TriageService` the API routes use — built once in `build_services` rather than twice, since two constructions are two engines and §5.4's claim is false the moment they diverge. `route_whatsapp` maps §CHAN-3's intent onto a `TriageInput` and returns what the engine says; the USSD selections answer from `USSD_MENU_ANSWERS`. The test compares the WhatsApp reply to `POST /triage/preliminary`'s recommendation over HTTP, for four inputs and both languages, because a channel test against the engine and a route test against the engine can both pass while the two entry points differ.
- **A fever on WhatsApp never reached §6.3's malaria trap.** The keyword router built `TriageInput` with no temperature, so a body saying "fever" entered the engine at the 36.5 °C default — which means *no fever* — and was answered at the low risk level. The malaria trap is the one clinical decision §6.3 exists for, and it did not fire on the channel where a feverish person with no thermometer is most likely to be writing. A body naming "fever" now enters at the 38.0 °C threshold; a body naming the word "symptom" and no symptom enters with an empty list and is answered honestly.
- **§CHAN-2's third selection names a symptom report the menu cannot carry.** A numeric USSD selection has no symptom list, so answering it with the engine's verdict on an empty list would be clinical advice the engine never gave. The selection now asks for the symptoms in a word or two, and the test asserts the reply contains no recommendation. The other three selections answer with §CHAN-2's own content, in both languages with a table.
- **A `RuntimeError` rather than a plausible reply when the engine is absent.** A unit test that builds the channel service bare gets the refusal; `test_channels.py` wires the real engine, which is what made the two stale assertions ("routed to feature") fail loudly instead of passing against a service that no longer answers that way.
- **Canaried eleven ways, each watched failing and reverted from a file backup.** Four on the gate (a code in the WhatsApp reply, a code in the USSD acknowledgement, a code in a menu answer table, and the menu-answer path itself), four on the shared engine (a plausible second fever sentence, a constant reply, fever not reaching the threshold, the symptom selection answering unnamed symptoms), and three on the USSD selection table. 831 tests green, pyright clean.

§CHAN-2's USSD menu was a different menu from the one the section draws (2026-10-11). The section draws a five-item tree — "1. Report symptoms" with a five-way submenu and two "→" follow-up prompts, "2. Find a clinic near me", "3. Health information" with three questions, "4. Request a CHW visit", "5. Language: English / Kiswahili / Dholuo / ..." — and the code served a flat four-item menu: "1. Ebola info / 2. Find facility / 3. Report symptoms / 4. Hotline 719". The two disagree on the count, the order and what the first item is, and the flat menu put the symptom path third when §CHAN-2's own integration note is about it.
- **The tree is data and the menu is rendered from it.** `USSD_TREE` carries the section's structure, `USSD_SYMPTOMS` its submenu, `USSD_INFO_ANSWERS` its three questions, and `USSD_MENU` is `ussd_menu_text()` over the tree — so the served string and the walkable structure cannot drift. The test reads the menu out of `docs/spec.md` with indentation as the depth signal: the first attempt stripped it and counted thirteen top-level items, which is the checker enumerating one of the two ways the block is written.
- **The walk is two levels deep, because the section says so.** "Must complete within 2 USSD sessions (approx. 360 characters)" is the constraint that fixes the depth, and the test asserts the served menu fits the budget the section states. Session state records the level reached; an out-of-range segment re-serves the menu rather than raising, because a USSD session that dies mid-menu is a dead channel for the one persona §4.1 gives no feature phone.
- **The symptom submenu is where §CHAN-2 and §5.4 meet.** The section's first item is a symptom report and §5.4 says every channel shares one engine, so `1*1` (Fever) enters the engine at the 38.0 °C threshold and reaches §6.3's malaria trap from a feature phone. Two submenu entries — "Cough" and "Other" — name nothing in the engine's §8.1 febrile vocabulary, and they are mapped to an empty list explicitly rather than dropped: a label mapped to nothing silently is a symptom the engine never hears about. The test pins the two.
- **The first cut served the English menu in Swahili, and an existing test caught it.** The tree carries the section's English labels and the served menu must be localised; serving English labels to a Swahili speaker was a regression on the one channel §4.1's feature-phone persona has. `USSD_LABELS` maps the section's words to what each language reads, so the structure stays the section's and the menu is readable. `test_personas.py`'s `sw.json()['menu'] != en.json()['menu']` failed on it — an assertion written for an earlier fix, doing its job on a later one.
- **The USSD "→" prompts are carried.** §CHAN-2's symptom path ends by asking whether to send a location and whether to request a callback, and a report that neither asks for is a report no one follows up. `USSD_YES_NO_PROMPTS` is the two of them, and the test reads all three "→" lines out of the spec so one cannot be quietly dropped.
- **The no-codes gate now presses a second keystroke.** The submenu is a separate served surface and the gate had only ever requested `text=''` and single digits; it now walks `1*1` through `1*5`, the three information questions and the out-of-range paths, in both languages. A gate that never pressed a second key never saw the submenu.
- **Canaried eight ways, each watched failing and reverted from a file backup.** A top-level item dropped (the flat menu returns), the symptom submenu reordered, the information questions truncated, Swahili served the English menu, a symptom label mapped to a word the engine does not know, the submenu answering instead of opening, fever no longer reaching the threshold, and an out-of-range selection raising instead of re-serving. 832 tests green, pyright clean.

§5.4's last three "All channels share" claims rest on a linkage the build did not have (2026-10-11). The section names five shared things. The first — "a single triage engine" — was built in the preceding unit. The other four are "a single case-report backend — deduplicated by phone number", "a single content repository" (already cited by `info/recency.py`), "a single identity model — phone number, with optional linkage to an app profile" and "a single consent registry — consent granted on one channel applies across channels", and all three of the unbuilt ones rested on one missing fact.
- **A phone number and a subject were two identifiers with nothing between them.** The channel layer's identity is an MSISDN — `UssdRequest.msisdn`, `WhatsAppIn.from_msisdn`, the telco inbound route. The app layer's is a `subject_ref`: `AuthService.issue_anonymous` mints one, `require_self` compares against it, and the consent ledger, symptom diary, wallet and case reports are all keyed by it. Nothing in `src/afya/` held both. `CaseReport` had no phone field at all, so the dedup §5.4 promises could not be performed: the same person reporting over USSD and in the app was two cases, and the second inflated the count PHEOC reads.
- **The two channel entry points hand-rolled E.164 differently, and got it wrong.** USSD did `'+' + cb.phone_number.lstrip('+')`; the telco inbound route did `'+' + raw.lstrip('0')`. So `0712345678` and `254712345678` were two phones, two subjects, and a dedup that could never match — the defect the shared model exists to close, live in the two paths that were supposed to share it. `IdentityService.normalise` is now the one place the spelling is decided, and both ingress paths go through it; a number that is not Kenyan is refused rather than rewritten into something that looks like one, because a wrong number here is a report attributed to the wrong person.
- **The dedup is keyed on the phone number, because that is what the section says.** The first cut keyed on the resolved *subject*, on the theory that linking an app profile should make a person's app and channel reports collide. That was wrong and the canary said so twice: `link()` repoints a phone from its anonymous subject to the profile, so a case opened before the link became unreachable after it, and the history-of-keys fix that followed decided nothing, because the raw number was always in the set. The subject bought nothing the number did not give. `dedup_key` returns `normalise(msisdn)`.
- **Linkage is an act with a consent behind it, not a merge.** §5.4 says "**optional** linkage" and §3.3 principle 6 says "Identity is opt-in", so `IdentityLink.consent_id` is required (`min_length=1`) and `link()` refuses without one — an automatic merge cannot be constructed. `LinkBasis` travels with the link (`self_entered`, `verified_otp`, `chw_registered`, `facility_registered`) because §17.1 wants the DPA basis for the act and a CHW registering someone is a different act from a person typing their own number. The first cut refused *any* existing entry, which made §5.4's own journey — use USSD, then install the app — impossible; it now refuses only a phone belonging to a *different linked profile*.
- **A grant made over USSD survives the person installing the app.** `PrivacyService.has_category_consent_for_phone` reads the one ledger through the resolved subject, so the USSD callback reports `store_symptoms` from the same record the app's toggle reads. The first fix made the reader look through the absorbed handles, which left two records for one grant and broke one-tap withdrawal; `reassign_subject(old, new)` now **moves** every grant including withdrawn ones, called from `/identity/link` — the one place both services are in hand — and the route returns `consents_moved`.
- **The finding is reported, not repaired.** `report()['can_deduplicate']` is False with `dedup_gap` naming why: the identifier alone cannot perform the dedup, because §4.1 has shared handsets, CHWs reporting for others and borrowed phones, so which of two reports is the same person is a product decision and `dedup_key` is the input it would need. Same shape as §17.4's two findings — a presence that reads as a working control next to a list that looks complete.
- **Canaried twenty ways, each watched failing and reverted from a file backup.** Three of them exposed dead code and led to its removal rather than to a fix: the `_phone_history` append in `link` (an absorbed handle only exists when `resolve` already recorded it), the explicit `normalise` call in the telco route (`channels.subject_of` already normalises), and the service's "already belongs to another person" refusal over HTTP (the route's own subject-binding guard fires first — re-pointed at the test that fires). Two were pointed at the wrong file on the first run and the target-string assert caught it rather than a silent no-op. 857 tests green, pyright clean.

§21's phase sections described work the rollout could not schedule (2026-10-11). §21.1's seven-row table was carried — each phase's timeline, objective, channels and tier ceiling — and §21.2–21.7, the six sections under it, were not. So the rollout had seven gates and a description of none of them: `PHASES` said Phase 3 authorises Tier 2 and nothing said Phase 3 ships an immunisation tracker, an ANC tracker, a chronic disease log, medication reminders, a family wallet, drug stock crowdsourcing, an appointment pilot and a service status feed.
- **The sections' deliverables are now data, and the ones naming a capability are crossed against the registry.** §21.4 lists "Family health wallet (basic)" and the registry holds `REC-001`; a phase listing a capability nobody built is a schedule for something that will not arrive, which is the §11.1 defect in the phase dimension — a plan naming a feature that does not exist reads identically to one that does. `feature_id` is set only where the section's own words name a registry capability; "Zero-rated app data", "Facility data loaded for all 47 counties" and "Full PHEOC integration" are operational acts or integration states, not features, and marking them unbuilt would make the report cry wolf on every phase.
- **A success criterion with no §22 KPI behind it is reported, not invented.** §21.2's "50 stations broadcasting", §21.3's "4.0+ rating" and "40% D30 retention", §21.4's "100,000 children tracked", §21.6's "Tier 4 activation in under 60 minutes" — §22 measures none of them, so the phase's own exit cannot be computed from §22's report. Same shape as §17.4's unreachable scopes and §11.1's untriggered Tier-4 features: a target that reads as a commitment and has no measurement behind it.
- **§21 and §22 disagree about the same numbers, and the finding is reported rather than resolved.** §21.3 says 300,000 installs and §22.2 sets `app_downloads` at 2,000,000; §21.4 says 25% DAU/MAU and §22.1 sets `retention_dau_mau` at 35%; §21.2 says 500,000 SMS opt-ins and §22.2 sets `sms_optins` at 3,000,000. Both sections are the product owner's, so neither is overruled — a rollout judged against the phase criterion would pass while the KPI report read as a failure, and that gap is the finding. `criterion_drift` carries both numbers.
- **§21.6's testing paragraph is carried with it.** "Tabletop exercises with PHEOC; simulated outbreak activation; red team review of privacy controls" is the phase's precondition and the only Testing paragraph in the six sections; the test asserts it is the only plan carrying one, so a section that gains one from the wrong place fails.
- **The plan is public without its traceability handles; the readiness evidence is auditor-scoped with them.** The same split `/sensors/capabilities` and `/sensors/coverage` already make. A deliverable's `feature_id` is a spec code, and `/rollout/plan` is a document a county team and a telco align to — the text says what ships. `/rollout/plan/readiness` keeps the ids, because there the id *is* the finding.
- **The section number is the phase number plus one, and the test states that rather than inferring it.** §21.1 calls the section after Phase 0 "Phase 1 — Information First", so §21.2 is Phase 1 and §21.7 is Phase 6. A reader who took the phase's ordinal for the section number would compare Phase 1 against §21.1's table and see six empty lists — an off-by-one that produces a green test over uncompared data. The mapping is a literal dict in the test.
- **Canaried seven ways, each watched failing and reverted from a file backup.** A deliverable dropped from §21.4, a deliverable pointed at an id the registry lacks (`FND-099`), §21.4's DAU/MAU made to agree with §22.1, an id restored to the public plan, the readiness route re-guarded on `self`, §21.6's testing paragraph emptied, and a criterion given a KPI it should not have. The seventh **passed** on the first run: the mutation moved the criterion from `unmeasurable_criteria` into `criterion_drift`, and the assertion only asked whether the list was non-empty. The test was rewritten to pin the exact lists, and the canary then fired — the same lesson as the passing canary that is a bug in the canary. 866 tests green, pyright clean.

§22.8's five-level evaluation framework was a table nothing ran (2026-10-11). §22's eight subsections were carried as 42 KPI rows with targets, directions and families, and §22.8 — the level at which those numbers are actually read — was not. So the product knew what it would measure and had nothing that said who looks at it, how often, or by what method; §22.8's Privacy row also named a DPIA review that §24.7 schedules on a different clock entirely, and the two sections could drift apart with nothing to catch it.
- **The five rows are data, and the cadence is a number.** `EVALUATION` carries level, method, frequency and `cadence_days` — monthly 30, quarterly 91, semi-annually 182, annually 365 — because "Quarterly" as a string is a duty nobody can be late for. That is the same rule §24's `Obligation` model already applies to the operational calendar, and the evaluation framework is a calendar of the same kind: a level with a label and no interval is a review that happens whenever someone remembers.
- **The finding is `uncovered_families`.** §22 has seven metric families and §22.8 names five levels; the section states the levels and leaves the mapping implicit, since "Early detection rates" and "user trust survey" are not family names. `MetricsService.evaluation()` crosses the two and names any family no level reads. As built every family is covered, and the check is what makes that a computed fact rather than a reading of two tables placed side by side — the same shape as §7.3's tier map, where a feature outside it is a capability that exists and is never scheduled.
- **A level with no family behind it is refused at construction.** `families` is `min_length=1`, because the reverse failure is just as real: a review level reading no metrics is a meeting with an agenda and no numbers, and it would sit in the table looking exactly like the other four.
- **The privacy level and the §24.7 DPIA are two clocks, and both are kept.** §22.8 puts "DPIA review, audit findings, user trust survey" on a semi-annual cycle; §24.7 makes the DPIA *update* a trigger — "Before each Tier 4 activation". They are different duties and neither substitutes for the other: a semi-annual review does not authorise an activation, and a per-activation update is not a periodic review. A test walks both, asserts the §24 obligation exists and is still trigger-only (`cadence_days is None` — giving a triggered duty a cadence is what makes it read as perpetually overdue), and pins the cadence as 182 days. This is the §22.5/§15.4 agreement check applied across sections rather than within one.
- **One route, auditor-scoped, like its three siblings.** `GET /metrics/evaluation` takes the audit scope; the framework is the evidence half of the report and names no person.
- **Canaried three ways, each watched failing and reverted from a file backup.** §22.8's Process method extended with a phrase the code does not carry (the spec-comparison test fails), `uncovered_families` short-circuited to an empty list (the coverage test and its own canary both fail), and §24.7's DPIA given a 182-day cadence (the clock test fails). The coverage canary drops the equity level from `EVALUATION` in a `try`/`finally` and asserts the family is named — if that passes, the check is comparing the family list against itself. 871 tests green, pyright clean.

§20's acquisition plan named partners the partnership map did not have (2026-10-11). §20.2's six levers and §20.6's retention table were carried; §20.3's channel-by-channel acquisition table and §20.4's ten-row partnership map were not. So the growth section had a strategy and no plan for it: nothing said radio is for mass awareness and WhatsApp is the primary conversion, and nothing said who the forty named organisations actually are.
- **The acquisition table is data, and it is crossed against §5.2.** `ACQUISITION` carries each channel's role and its tactics split into items — "Daily segments, call-ins, drama vignettes" is three tactics and WhatsApp's "Forwardable cards with download links; bot → app handoff" is two, so the split is on both separators. The section's own word is kept beside §5.2's slug, because the two are not the same set: §20.3 says "App stores" where the registry's channel is `native`, and the app store is how the app is *found* while the app is what is found. Collapsing the label would read as the section naming a channel the registry does not carry.
- **The finding is `unmapped_channels`.** §20.3 is how a person is reached and §5.2 is the channel list; a channel with no acquisition row is one the product can reach someone through with no plan to reach them. All seven map today, and the check is what makes that a computed fact — the same shape as §7.3's tier map and §22.8's evaluation coverage.
- **The sharper finding is `unsourced_levers`.** §20.2 lever 1 says "Negotiate with Safaricom, Airtel, Telkom before launch" and lever 3 says "Co-brand with Kenya Red Cross, AMREF, WHO, faith networks". §20.4 is the section that says who is a partner, and a lever resting on an organisation the map does not list is a growth strategy waiting on an agreement nobody asked for. The join is a literal map of the two levers that name a body, spelled as §20.4 spells it — "Airtel Kenya", not "Airtel". "faith networks" is a category rather than an organisation and is left out rather than mapped to a row, because a category given a row's worth of partners would be this code inventing the join.
- **The partner count is names, not rows.** `PARTNERS` splits the Specific-partners cell on its commas, so the map reports thirty-nine organisations across ten partner types. A count that counted rows would say ten and let a map of four names pass as a map of forty — which is the §20.4 analogue of a register whose rows are all `process`.
- **Two surfaces, split as the rest of this family is.** `GET /rollout/acquisition` is what a telco, an NGO or a county team reads to see what is being asked of them, and it serves no registry handle; `/rollout/acquisition/coverage` is auditor-scoped and keeps them, because there the id is the finding. Same split as `/rollout/plan` against `/rollout/plan/readiness` and `/sensors/capabilities` against `/sensors/coverage`.
- **Canaried four ways, each watched failing and reverted from a file backup.** §20.3's USSD row dropped (the channel-coverage check names it), §20.4's Telcos row losing Safaricom (the lever join names lever 1), and both canaries run against their own checks. 878 tests green, pyright clean.
- **One process failure worth recording.** The first revert restored `/tmp/rsvc.bak`, taken *before* the §20.3–20.4 work existed, and wiped the unit's additions to `service.py` along with the canary mutation. The rule the repo already carries is to revert from a file backup rather than `git checkout` — but a backup is only a backup of what it was taken after, and a stale one is `git checkout` wearing the right name. Re-applied, and the backups for the remaining canaries were taken after the work existed.

§24's duty register had no bodies and no support desk (2026-10-11). §23's 33-risk register, §24.2's and §24.7's duty cadences and §24.8's incident clocks were all carried. §24.1's six governance bodies and §24.3's five support channels were not — so the register assigned twenty duties to owners like `clinical_advisory_group` and `community_advisory_panel` with nothing anywhere saying what those bodies are, who sits on them, or whether any of them exists.
- **The six bodies are data, and the join to the duty owners is written down rather than inferred.** §24.2–§24.7 name owners as role slugs; §24.1 names bodies and the roles that sit on them. The two vocabularies are never related in the spec, so `owners` on each `GovernanceBody` states the reading — `dpo` and `legal` sit on the Privacy and Ethics Board, `ciso` on the Technical Working Group, `programme_manager`, `content_lead` and `comms_lead` on the Operations Cell — and the test checks the reading covers every owner. A join left in a reader's head is one that silently drops an owner the day a duty is added.
- **The finding is `unowned_bodies`, and the Steering Committee is the honest instance.** Its role is "strategic direction, funding, escalation", none of which is a recurring duty §24 schedules. It is reported rather than given a fabricated owner: a body cleared off the list by inventing a duty would make the register lie about what it checks, which is the §11.1 defect in the governance dimension.
- **§24.3's coverage column is carried verbatim.** "8am–8pm, 7 days" and "24/7 (self-service)" are different commitments, and a boolean `always_on` would flatten the difference between a staffed line and a help page — so `coverage` is the section's own string and `always_on` sits beside it as a derived convenience. The self-service row carries an em dash in the Staffing column, which is `None` rather than 0: a zero would read as an unstaffed channel rather than one nobody is rostered on. Eight rostered agents, three of five channels 24/7.
- **One route, auditor-scoped.** `GET /operations/governance` takes the audit scope like its siblings — it names roles and headcounts, not people.
- **Canaried three ways, each watched failing and reverted from a file backup.** §24.1's Privacy and Ethics Board unseated from the DPO (the owner join names `dpo`), `unowned_bodies` short-circuited to empty (the governance test and the route test both fail), and the canary's own `finally` restoring the module. 883 tests green, pyright clean.

§24.4's training matrix and §24.5's funding model were two tables nobody had (2026-10-11). §24.1's bodies and §24.3's support channels were carried in the preceding unit; §24.4's seven training audiences and §24.5's four funding bands were not. So the operational plan trained seven groups and paid for six phases without either table existing anywhere — and §24.5's last band is the one §24.6's whole sustainability argument rests on, "Fully integrated into national health budget", which nothing carried.
- **The training matrix is data, with the duration as a number.** `TRAINING` carries each audience's content, format and the section's own duration string beside an `hours` figure — "2 days" is 16 hours at an 8-hour day — so the matrix totals to 71 hours rather than to a list of strings. The section's words stay because "2 days" and "4 hours" are both durations and only one is a number of hours.
- **The finding is `untrained_audiences`.** §24.4 names seven audiences and §24.1 names six bodies with the roles that sit on them; an audience no body accounts for is a group expected to use the product with nobody in the governance structure responsible for teaching them. Two are reported — Facility staff and Radio partners — rather than assigned a fabricated owner. CHWs sit on the Community Advisory Panel and support agents staff the Operations Cell, so the join is narrow because the section is silent, not because the reading is off.
- **The funding bands tile §21's phases, and the check had to be fixed to say so.** §24.5's four bands are "Phase 0–1", "Phase 2–3", "Phase 4–5" and "Phase 6+", and `unfunded_stages` names any §21 phase no band pays for. The first cut gave each band a single `phase_ceiling` and tested `order > max(ceiling)` — which is false for every phase by construction, because the last band's ceiling is the last phase. **The canary passed**, and a gate that cannot fail is not a gate: the model now carries `phase_floor` and `phase_ceiling` as a range, the test asserts the ranges tile 0–6 with no gap or overlap, and the canary fires both when a band is narrowed and when it is dropped. Same lesson as the §21 canary that passed on the first run.
- **The em dashes are None, not empty.** §24.5's first two bands have no sustainability column, because the emergency and build phases are not meant to sustain; a fabricated one would read as a plan for the integration the next row says has not begun. §24.3's self-service row carries an em dash in Staffing, which is `None` rather than 0 for the same reason.
- **Two routes, auditor-scoped.** `GET /operations/governance` and `/operations/support-plan` take the audit scope — they name roles, headcounts and budgets, not people. The sysadmin is refused both, which the tests assert rather than assume.
- **Canaried five ways, each watched failing and reverted from a file backup.** §24.1's Privacy and Ethics Board unseated from the DPO, `unowned_bodies` short-circuited, `untrained_audiences` short-circuited, and the funding check canaried twice — once narrowing a band's range and once dropping the band entirely. The second funding canary is the one that found the vacuous predicate. 889 tests green, pyright clean.

§24.6's eight mitigations were an argument nobody was checking (2026-10-11). It is the section that says the product survives the outbreak — position it as permanent infrastructure, keep Tier 1–3 useful year-round, integrate into the MoH budget, widen the disease scope, measure non-outbreak impact, keep the telco, stay open-source, expand regionally — and it was prose. Seven of the eight name something this build either has or has not, so they resolve the way §23's mitigation column already does.
- **The rule is §23's, applied to the continuity argument.** `SUSTAINABILITY` carries each mitigation with a `module:attr` reference where the section names an artefact, and `sustainability()` walks it. Seven resolve: the brand (`BRAND`), the retention engine (`RETENTION`), the funding band (`FUNDING`), the disease scope (`DISEASE_ROWS`), the metric set (`KPIS`), the partner map (`PARTNERS`) and the licence lookup (`LICENCE_FILES`). A mitigation naming a capability the build does not have is a claim that reads as a plan and is not one — which is the §23 defect in the section about the product outliving its launch.
- **The two lists are different findings, and conflating them was the first cut.** `unbacked_mitigations` is a mitigation that *names* an artefact and does not resolve — the sharper failure. `process_mitigations` is one naming no artefact at all, which is a commitment about the world rather than a claim about the build; regional expansion is the single instance. §23's register makes the same split through `ControlKind`, and `resolve(None)` returns True for a process control, so reading the process list off `resolve` would have reported eight of eight. The docstring claiming "the eighth is reported as unresolvable" was wrong when written and the data said so.
- **One route, auditor-scoped.** `GET /operations/sustainability` takes the audit scope like its siblings — a funding and continuity argument, naming no person.
- **Canaried once, watched failing and reverted from a file backup.** Mitigation 7 pointed at `afya.nothing.service:MISSING` and the check names it. 893 tests green, pyright clean.

§17.1's six instruments and §17.2's seven principles were prose nothing checked (2026-10-12). §17.4's retention table, §17.5's encryption posture and §17.7's transparency report were all carried; §17.1's regulatory-instrument table and §17.2's seven-principle table were not. The section that says which law the product answers to, and on what basis it may process anything, had no software in it at all — the only §17.2 trace in the tree was a string in `assess_dpia` complaining that raw sensor retention violates data minimisation.
- **Thirteen obligations across six instruments, and the Implementation cells are the interesting part.** §17.1's table has one row per instrument and a cell that lists what compliance requires, so "Data Protection Act 2019" carries four obligations and "ODPC Guidance Note" carries two. Each obligation is a row with an `ObligationKind` — `code`, `process`, `registration` or `agreement` — because "the software enforces this" and "a human does this" are different claims and a table that cannot tell them apart reports eight of eight backed.
- **The resolver is now shared, and that is why `afya/refs.py` exists.** §23's risk register and §24.6's mitigations each walked a `module:attr` reference with their own copy of the same four-line import loop. §17.1 and §17.2 are the third and fourth tables to need it, so the walk moved to one module rather than becoming four places to drift. `OperationsService.resolve` now delegates to it and keeps its docstring.
- **§17.2's lawfulness row was a label a caller chose, and now it is a door.** The row reads "legal obligation basis for mandatory disease notification only", and "only" is the whole content: before this unit, `record_consent` accepted `LegalBasis.legal_obligation` for any purpose, so a person's symptom history could be filed against a statute instead of against their consent and the ledger would show a lawful record. `MANDATORY_NOTIFICATION_PURPOSES` is a list of purposes rather than of callers, because the rule is about what the data is for. `case_report_basis(purpose)` is the one place that decides which basis a purpose gets, and the Public Health Act row points at it.
- **Two obligations split, because a cell is not a claim.** §17.2's integrity row reads "AES-256 at rest, TLS 1.3 in transit, RBAC, audit logging" — four claims in one cell, and a single row would let three of them go unbuilt while the row resolved. Its data-minimisation row separates two items with a full stop rather than a semicolon, which the first cut of the test's item splitter missed: the checker enumerated one of the two ways to write the same list, which is the failure mode this repo has recorded before.
- **Five obligations are unbacked and are reported, not repaired.** `Digital Health Act: MoH registration` and `Compliance review` are `registration`/`process` obligations against sets the deployment supplies; `ODPC Guidance Note: DPO appointed` likewise; §17.2's accountability row names the same DPO. A deployment with no registrations held is the honest empty set, and the report says so rather than assuming the paper exists. The registrations come from `obligation_status` filtered to duties actually performed, and the agreements from `sharing_posture()['cleared_to_share']` — narrowed with `cast` because that dict is typed `dict[str, object]` and carries four shapes of value.
- **§17.6's age rule was wrong twice over, and the test found both.** The arithmetic was `(2026 - year) * 12 + (10 - month)` — the clock written into the expression, correct in October 2026 and nowhere else. It made a child born in 2008 read as 18 forever, so the transfer of control never fired, and it aged nobody, so a 17-year-old enrolled in 2026 was still a minor in 2030. `age_years(dob_iso, today)` computes from the dates. The second fault was the rule itself: `owns` read `member.is_minor`, a flag frozen at enrolment, and a flag is the wrong place for a rule whose whole content is that it stops being true. `owns` now computes the age on every call, and `transfers_at` reports the date a guardian's access ends — a guardian told "no" without a date cannot tell whether the record moved or they mistyped a reference.
- **An adult cannot be enrolled as someone else's dependent.** The assert closes the other direction: a `guardian_ref` on an adult is a reference `owns` would have honoured, so the model refuses the enrolment rather than storing a relation nothing will ever apply. Naming yourself is allowed, because that is not a guardianship claim.
- **§17.2's accuracy row is a workflow, not an overwrite.** "User data editable; correction workflows" — `POST /retention/correct` keeps the value it replaced and appends to a per-subject history, scoped to a data type and a field, because a correction that destroyed what it corrected leaves a record that agrees with itself and with nothing else. `PATCH` and `PUT` appeared nowhere on personal data before this. The route rebinds `subject_ref` and `corrected_by` to the token subject, so a caller cannot correct someone else's record by naming them.
- **Two surfaces, split as the rest of this family is.** `GET /privacy/regulatory` is auditor-scoped and keeps the instrument names and `module:attr` references, because there the reference *is* the finding. `POST /retention/correct` and `GET /retention/corrections` are self-scoped.
- **Canaried four ways, each watched failing and reverted from a file backup.** The `owns` age conjunct dropped (two tests name it), `refs.resolves` short-circuited to True (the §17.1 canary names the broken reference that then read as backed), and the §17.2 basis check. A fifth canary — `test_the_canary_watches_the_minor_check_fire` — was rewritten rather than kept: it set `is_minor` directly, which the new date-computed `owns` correctly ignores, so it would have passed against the defect it was meant to catch. 911 tests green, pyright clean.

§17.3's DPIA was a gate any caller could open by saying so (2026-10-12). The section names eight topics a DPIA must cover, requires a review before each Tier-4 activation, and had five input fields and a `dpia_reviewed` boolean the caller filled in about itself.
- **Three of the eight topics had no field to be described by.** Location tracking and geofencing, contact tracing assistance, and data sharing with health authorities could not be raised at all, so the assessment's silence about them read as clearance. `DPIA_TOPICS` is now the section's eight bullets as data — topic, field, and the finding the assessment raises — and `assess_dpia` walks it rather than spelling out five `if` statements. A bullet added to the spec and not to the table is now the one thing the topic-list test fails on.
- **The defect was the parameter itself.** `activate_tier4(authorized_by_pheoc, dpia_reviewed, flag_enabled)` took the DPIA key as an argument, and the route assessed the DPIA only when `dpia_input` happened to be present — so a request carrying `dpia_reviewed: true` and nothing else turned the outbreak capabilities on. `dpia_reviewed` is now a derived `@property` on `Tier4Activation`, true only when `dpia_review_id` names a record; the field is gone from the request model, so a caller sending it gets a 422, and `activate_tier4` no longer has the parameter to pass. There is no path to the key except recording a review.
- **A review is a thing that happened, so it is recorded rather than asserted.** `POST /privacy/dpia/review` takes the processing, a timestamp and a named reviewer, and refuses a blocked assessment — §17.2's data-minimisation violation has to be fixed in the processing, not recorded away and then cited at the gate. `dpia_reviews()` is the register.
- **The fingerprint is what makes "updated" mean something.** §17.3 says "reviewed and updated before each Tier 4 activation", so a review recorded for a proximity-logging rollout must not answer for one that has since added cross-border transfer. The fingerprint is the sorted set of topics the processing raises, and the lookup compares it — which is the difference between "a DPIA was done once" and the sentence the section actually writes.
- **The gate names the review it was held by.** `dpia_review_id` rides on the activation, so "which DPIA authorised this" is answerable after the fact rather than reconstructible from a boolean.
- **The UI surface moved with it.** The mobile action catalogue offered `dpia_reviewed` as a boolean form field on `activate_outbreak_mode` and five topics on `dpia_check`; both now carry the eight processing flags and nothing to assert.
- **Canaried twice, each watched failing and reverted from a file backup.** A topic dropped from `DPIA_TOPICS` (the topic-list test, the per-topic finding test and the canary all name it) and `dpia_reviewed` restored as a settable stored field (the app-level gate test names it). 918 tests green, pyright clean.

§15.2's stack table and §15.1's architecture were the two claims nothing compared (2026-10-12). §15.3's residency rules, §15.4's thirteen targets and §17.7's agreements were all carried in the same module. §15.2 names eighteen layers of technology and §15.1 draws a thirty-box diagram, and neither had a line of code behind it — so "we run the spec's stack" was a sentence with no instrument.
- **The stack table is a comparison, not a copy.** Every §15.2 row is carried verbatim on its first three columns with what the build actually runs beside it, and each layer is `shipped`, `deferred` or `diverged`. The three are different answers: a deferred layer is one the programme has not stood up, a diverged layer runs something else, and an unbacked layer *claims to ship* with nothing pointing at it — the sharpest of the three, because it reads as true.
- **The divergences are now computed rather than remembered.** Five: Flutter → SwiftUI + Kotlin, Node.js + Fastify → FastAPI only, PostGIS → application-level haversine, Unleash → the in-process three-key gate, and — found by writing the table rather than by reading the memory — the local DB. §15.1 draws the local data layer as an ACID offline-first store and §15.2 names SQLite + Room and Core Data; the clients cache the last good response in SharedPreferences and UserDefaults, which has neither transactions nor a schema. The first cut of this row read `shipped` with `android/` as its evidence, and the evidence check passed because the directory exists — which is the failure mode the table exists to catch, caught on the table itself.
- **Both evidence spellings are walked.** A layer's evidence is a `module:attr` reference where the layer is code and a repo path where it is configuration, and `_evidence_resolves` checks each form. A checker that knew only the import form would have passed every configuration layer for free — and the `android/` directory that made the wrong Local DB row look backed was exactly that shape.
- **Five layers are deferred and reported, not repaired.** Time-series (TimescaleDB), cache/queue (Redis), search (OpenSearch), message queue (RabbitMQ or Kafka) and monitoring (Prometheus + Grafana + Sentry). None is required by anything the repo does — sensor rows land in the primary store and alert fan-out is in-process — so reporting them as deferred is the honest form. Repairing them would be building infrastructure to make a table green.
- **§15.1's diagram is checked box by box.** Twenty-five of the twenty-seven boxes name a module and every one resolves; the two that do not are the client-side keystore and the client-side store, which are the OS's and live outside this repo. They carry a `note` saying so rather than a fabricated module, and the test asserts that every module-less box has one — so a box added with no module and no explanation fails rather than being silently tolerated.
- **One route, infrastructure-scoped.** `GET /governance/stack` takes the infrastructure scope like its siblings — what runs and where is a deployment fact.
- **Canaried three ways, each watched failing and reverted from a file backup.** A shipped layer pointed at a phantom class (`unbacked_layers` names it), an architecture box pointed at a phantom module (the canary test names it), and `refs.resolves` short-circuited to always-yes. The third is the one worth recording: run in the same batch as the first it *masked* it — a resolver that says yes to everything makes a phantom reference read as backed, so the unbacked-layer assertion passed against the planted defect. Re-run alone, both fire. A canary batched with another canary is not two canaries. 923 tests green, pyright clean.

§13's sensor matrix was two tables nothing compared to the section that printed them (2026-10-12). §13.1's eighteen rows and §13.2's nine fallbacks were both carried as data — `SENSORS` in `afya/sensors/service.py`, `SENSOR_FALLBACKS` in `afya/access/service.py` — and every test over them checked internal consistency: a fallback exists for each absence-prone sensor, slugs are unique, three sensitivity classes. Nothing read `docs/spec.md`. A row rewritten, a fallback reworded, a tenth row added to either table, and the suite stayed green.
- **The enum was quietly lossy and nothing recorded the loss.** §13.1 writes nine Android/iOS strings — All, Most, Some, Select flagships, iPhone Pro / iPad Pro, Rare, Very rare, Limited, None — and `Availability` has six members. "Rare" and "Very rare" both become `rare`; "Some", "iPhone Pro / iPad Pro" and "Limited" all become `some`. The collapse is sound for the one predicate §13.2 is keyed on, because `all` is the only value that is not absence-prone and no spelling collapses onto it — but a client rendering a capability matrix from the enum tells a user their handset is supported on the same terms as one the section called "Limited". `SPEC_AVAILABILITY` now carries the section's own cells, `AVAILABILITY_SPELLINGS` maps all nine, and a module-level assert fails at import if a sensor's enum and its cell disagree.
- **The comparison is exact in both directions, with the exceptions named.** §13.1's Primary Features column mixes ids with prose ("SENS-008, altitude", "External thermometer, BP cuff"), and USB/OTG's cell names no id at all — the code's SENS-009 comes from §14.9. Rather than a superset test that would tolerate any addition, the one addition is named in `SPEC_FEATURE_ADDITIONS`, so a row that gains an id the section never prints fails.
- **§13.2 keys its rows on a different vocabulary, which is how the two tables could drift.** The section writes "No LiDAR", "No camera", "No wearable"; the table keys on slugs. §13.2 says `camera` where §13.1 splits rear from front, and `wearable` where §13.1 has no sensor row at all — a wearable is a §14.6 integration, not a handset sensor. `SPEC_FALLBACK_ROWS` carries the section's nine labels verbatim, the test asserts the row set is exactly the section's, and the three mismatches are named rather than assumed away.
- **The served matrix now prints the section's words.** `capabilities()` served `android`/`ios` from the enum; it now serves §13.1's cells under those keys and the normalised value under `android_availability`/`ios_availability`, with `absence_prone` carrying the only answer the enum is good for. A user asking "does my phone work?" gets the section's answer, not a rounding of it.
- **Canaried eight ways, each watched failing and reverted from a file backup.** The spec availability cell rewritten, the sensor enum disagreeing with its cell (fails at import with the sensor named), a sensor gaining an unprinted id, a §13.2 row label rewritten, a row dropped from the fallback table, the rendered fallback replaced with the section verbatim, a tenth spelling entering the map, and the served cell reverting to the enum.
- **The first canary batch ran zero tests and reported six clean results.** zsh does not word-split unquoted expansions, so `uv run pytest -q $testexpr` passed the whole selector as one argument; pytest answered `no tests ran` and the wrapper printed it as a pass. The canary harness was itself the bug — the same shape as a gate whose name collides with a shell builtin, failing open in a way that looks like success. Fixed by `shift 4` and `"$@"`.
- **A same-length canary patch restored within the same mtime tick reuses the canary's `.pyc`.** Swapping `Availability.rare` for `Availability.some` and restoring immediately left the compiled file current, so `import` raised the canary's own assertion after the source was already correct — twenty minutes chasing a defect that had been reverted. Clear `__pycache__` after a canary batch, or the canary's residue reads as a code failure.

§11.6's feature→sensor table is §13.1 read the other way round, and the two sections contradict each other (2026-10-12). §11.6 is eight rows mapping a feature to the sensors that carry it; §13.1 is eighteen rows mapping a sensor to the features it carries. One mapping, described from both ends, and nothing crossed them.
- **The disagreement is five distinct facts, and it is reported rather than reconciled.** §11.6's single "Camera" row cannot say which of §13.1's two camera rows it means — on SENS-004 and again on SENS-005; §13.1 gives SENS-005 the optical heart-rate sensor and §11.6 lists only "Camera, flash, screen"; and §11.6 reaches SENS-006 and SENS-007 through "HealthKit / Health Connect" and "wearables", which are platform surfaces rather than §13.1 sensor rows. The code follows §13.1 — the section that classifies the sensors — so the defect is in one of the *sections*, which is a question for whoever owns the spec. `sensor_feature_disagreements()` names each pair instead of choosing.
- **The alias table is declared, not fuzzy.** The two sections spell the same hardware differently: §11.6 writes "gyroscope", "flash" and "BLE" where §13.1 writes "Gyroscope", "Flash / LED" and "Bluetooth LE". A fuzzy matcher would read "flash" as matching nothing and report a false omission, so every §11.6 sensor name is mapped explicitly and an unmapped name raises rather than being skipped.
- **One ambiguity is reported once.** "Camera" maps to both §13.1 camera rows, and the first cut let that surface as a spurious omission on one row and a spurious extra on the next — the same fact counted three times. Slugs reached through an ambiguous name are excluded from the set difference, so the ambiguity line stands alone.
- **Canaried five ways, each watched failing and reverted from a file backup.** A §11.6 row label rewritten, a cell losing a sensor, the alias table losing a spelling, "Camera" ceasing to be ambiguous, and a ninth row added to the table.

§9.2's REC-001 listed eight wallet contents and the wallet assembled none of them (2026-10-12). The section names what a family health wallet holds, then two hard numbers — "up to 10" profiles — and a feature list. The wallet payload returned members and immunisation gaps; the contents were carried by five models scattered across four modules, nothing named the mapping, and the ten-profile cap was enforced nowhere.
- **Seven of the eight contents have a model; discharge summaries has none, and that is reported.** `WALLET_ITEMS` carries the section's eight bullets in order, each paired with a `module:attr` reference to the model that holds it. Seven resolve. Discharge summaries has no model at all — a facility document nothing ingests — and is reported as unbacked rather than given a fabricated one, because the wallet is what a person opens when they have lost the paper and an item with nothing behind it is a document the app promises to keep and cannot.
- **The three non-obvious mappings are named, not left to inference.** ANC cards live in `afya.maternal.views:ANCRecord`, referral letters in `afya.intermediaries.views:Referral`, appointment cards in `afya.facilities.views:Booking` — none in `records/`, which is why nothing crossed them. Insurance/SHA details carries a note that the member number is stored as a hash, so the card cannot be reconstructed from it.
- **The ten-profile cap is enforced at enrolment.** "Multiple profiles (up to 10)" is a number in the section, so it belongs where a member joins a wallet rather than in a report read later. The assert names the section and the cap, and the test checks the cap is *per guardian* — a second wallet is unaffected — because a global cap would pass a per-wallet test by accident.
- **Canaried four ways, each watched failing and reverted from a file backup.** Discharge summaries given a phantom model, a wallet bullet reworded, the cap raised to 11, and the cap check replaced with a no-op at enrolment.

§2's problem statement — seven citizen-layer gaps and five conditioned lessons, the last block in the spec with no carrier (2026-10-12). §2.1 is Kenya's existing posture, §2.2 is a table of seven things the health-system layer does not do, §2.3 is five lessons from comparable deployments. §2 was the only numbered section cited nowhere in `src/`, `tests/` or this file, and it is not decorative: §2.2 is the product's own claim list and §2.3's lessons are where several features' design constraints come from.
- **§2.2's seven rows are claims, and all seven resolve.** Every gap names a capability the product says it closes — self-triage, persistent monitoring, citizen reporting, localised risk, consented contact tracing, passive surveillance, a misinformation counter. `CITIZEN_GAPS` pairs each with a `module:attr` reference and `unclosed` is the finding, reported rather than repaired because whether a gap is this repo's to close is a product decision. All seven land, so `unclosed` is empty — and that assertion is only worth anything because a canary rotted a reference and watched it go non-empty.
- **§2.3's lessons are conditions, and the condition is the checkable half.** Each paragraph reads "X works, *when* Y" or "X is feasible, *but only if* Y". The claim is about somebody else's deployment; the qualifier is a requirement on this one, and a build that reads only the bolded half implements the lesson and drops the thing that made it safe. `condition` is carried as a verbatim clause and asserted to be a substring of its own lesson, so a paraphrase — a different requirement — fails here.
- **One condition is not honoured, and §LOC-002 rests on the same gate.** Lesson 3's condition is "only if it is opt-in and transparent". `proximity_logging` is a §SEC-001 consent category with a written scope and a written revocation consequence ("Close-contact alerts cannot reach you if you are exposed"), and `LocationService` never reads it: `log_encounter` appends the token and asserts a bound on the store, and the module holds no privacy dependency at all. Four routes reach proximity logging (`/location/proximity/{ebid,encounter,declare,check}`) and none consults consent. The gate exists and is correct — `PrivacyService.has_category_consent` — and nothing on this path calls it, which is the shape §16.2's `backoff_delay_s` had. The declaration side *is* gated by `proxied`, and that is a different property: it prevents social-graph inference, not collection without consent. Reported on the auditor-scoped `/problem`, not repaired — wiring a consent dependency into `LocationService` changes a constructor signature and is a product call about what an encounter without opt-in should do.
- **A verdict and an undecidable question are kept apart.** `honoured` is tri-state. True and False are verdicts this repo can reach; None means the question is not about this tree. Lesson 4 claims viability "on consumer handsets" and §13.1's own availability cell gives LiDAR "Select flagships" / "iPhone Pro / iPad Pro" — whether that is a consumer handset is a fact about the phone market, so it is reported as `undecided` with the reason rather than forced into a verdict. `unhonoured`, `unresolved` and `undecided` are three separate lists because mixed into one they read as three ways of saying "incomplete".
- **§2.1 is carried so a citation resolves, and only two bullets name a join.** Eight facts about Kenya's posture, none about this tree except two that name systems §18 integrates with — the WhatsApp chatbot (JALI) and the daily dashboards (PHEOC). `SITUATION_JOINS` keys on the section's own wording, so a reworded bullet fails here rather than silently detaching the join.
- **Canaried five ways, each watched failing and reverted from a file backup.** The consent finding flipped to honoured (the report test), a gap reference rotted to a nonexistent attribute (the resolve test), a gap reworded (the spec-comparison test), a condition paraphrased into a clause the lesson does not contain (the substring test), and a privacy dependency wired into `LocationService` (the test that notices the gate being added). The fourth canary *passed* on its first attempt: I substituted "when the tool is simple" for the full clause, and that is a substring of the lesson, so the canary proved nothing — a canary whose mutation is not actually absent from its target is a canary that did not run. Rewritten to a clause the lesson does not carry, it failed correctly. 9 tests green, pyright clean.

§8–§12's feature content lists, which nothing had crossed against the code (2026-10-12). The registry gate answers whether a feature is *reachable*; it is a route check, and it is what found the 24 orphaned `/ops/*` endpoints. It says nothing about whether a feature does what its own section says. §9.2's REC-001 was reachable the whole time and named eight wallet contents of which one had no model — the same defect one level down. §8–§12 carry 220 labelled content bullets (`**Features:**`, `**Contents:**`, `**Additional inputs:**`, `**Outputs:**`, `**Signals monitored:**`) across 35 feature sections; four had been read.
- **The four are the sections the section-number survey found named nowhere.** §9.3 MED-004, §9.4 FND-006, §9.5 INF-007 and §11.2 TRI-003. `FEATURE_CONTENT` carries each labelled bullet verbatim with a `module:attr` reference where something does it, and the spec-comparison test reads `docs/spec.md` cell for cell.
- **Fifteen bullets are missing and each is a named capability.** MED-004: no search across drugs, no essential-medicines list, no restock alert, and no timestamp on `StockReport` — so the section's own example, "available at [pharmacy], 2 hours ago", cannot be rendered by any client. That is the shape §6.2.3's "Updated 2 hours ago" had. FND-006: no slot listing, no reschedule and no cancel, no appointment reminder (`MedReminder` is the medication schedule). INF-007: four of its six service-status contents have no carrier — market closures, water interruptions, road closures and transport disruptions; `water_quality` is a MON-005 safety alert, not a service interruption. TRI-003: `TriageInput` carries one `ebola_contact` boolean where the section names four distinct exposures, so a funeral and a bushmeat exposure read identically to the classifier; and the high-risk recommendation names 719 and isolation but not the transport instruction the section prints.
- **Three verdicts, and only one is a finding.** `carried` resolves to code, `deferred` is a bullet the spec itself puts out of scope here, `missing` is a bullet nothing does. Merging them would report every cross-reference as a gap and bury the real ones. TRI-003's vaccination input is `deferred` and not `missing`: the section conditions it on "if a vaccine is available and deployed", which is a fact about the world rather than about this tree, and putting it in a defect list would be a wrong finding.
- **The report states how much of the spec it read.** `audited_features` is 4 and `unaudited_features` names the other 32. A list of fifteen gaps served without that context invites the reader to take it as complete — the failure mode of every gate that scopes itself, and the one this module would otherwise reproduce.
- **Canaried five ways, each watched failing and reverted from a file backup.** A carried reference rotted to a nonexistent method (the resolve test), a bullet reworded (the spec-comparison test), a timestamp added to `StockReport` (the absence test — it fails when the gap closes, so a repair shows up here), a `funeral_attendance` field added to `TriageInput` (the exposure test), and an unaudited section dropped from the list (the coverage test). 10 tests green, pyright clean.

§8's nine Tier-1 feature sections, the second tranche of the content audit (2026-10-12). The first tranche read the four sections the section-number survey found named nowhere; that is a rule about citations, not about importance, and it left the tier that earns the download unread. TRI-001, TRI-002, FND-001, FND-002, FND-004, MED-001, MED-002, MED-003 and EMG-001 are now carried bullet-for-bullet, and the report reads 13 audited / 34 unaudited / 45 missing / 0 unresolved.
- **The coverage claim was wrong in two directions and is now derived.** The first tranche asserted "220 bullets across 35 sections" and "the other 32"; the spec prints 215 bullets across 34 sections that carry a labelled list, and INF-007's prose Contents cell adds six comma-separated items for 221 — §9.5 is the only section whose list is a sentence rather than bullets. The two lists must now *partition* the labelled sections, asserted against the spec, because a section in neither list is one nobody can find out is unaudited. `LOC-003` was in the unaudited list and carries no labelled list at all — §6.3's privacy features are prose — so it was a name that could never be audited; `FND-003`, `FND-005`, `EMG-003`, `INF-006`, `MON-005`–`MON-008`, `REC-003`, `REC-004`, `ALT-001` and `AI-001` carry labelled lists and were in neither, so the report understated its own coverage by twelve.
- **Thirty more bullets are missing, and the sharpest are two collapses of a named set into a boolean.** MED-001 prints four outcomes — "Registered / Not found / Expired registration / Recalled" — and `VerifyResult` is `genuine: bool` plus free text, so a recalled medicine and a medicine that was never registered read identically to every client. TRI-001 prints five risk levels and `RiskLevel` has four members, none of which separates "High (Ebola suspicion)" from "High (other cause)" — the distinction the section exists to make, since one is a contact-tracing trigger and the other is not. Both are the §13.1 lossy-enum defect, one level up: a set the spec names, collapsed where a client can no longer tell the members apart.
- **EMG-001's bolded claim is the one nothing does.** "**Works over SMS when data is unavailable**" is set in bold in the section and echoed in its `Offline:` line ("Yes, via SMS"); `/emergency/sos` is HTTP-only and there is no SMS path in the tree. "Sends to the nearest ambulance dispatch where integrated" is a gap for the same reason: §18 lists eight integrations and ambulance dispatch is not among them, so the condition has nothing to attach to. "Sends location and a preset message to up to three emergency contacts" is the third — `SOSEvent` carries no contacts and `sos` notifies the hotline instead.
- **MED-003's calculator takes the constant it exists to look up.** `dose` accepts a caller-supplied `mg_per_kg`, so the weight-based lookup — the whole of a dosage calculator — is done by the client. The section's "Common paediatric formulations" names five drugs and the module carries its own set, so the lists can drift with nothing comparing them.
- **Seven deferred bullets, two kinds, neither a gap.** Six are device actions — a maps app, a dialler, a barcode reader — which `tests/ci/test_feature_coverage.py`'s `ON_DEVICE` set already lists as client-side by design. The seventh is TRI-003's vaccination input. The test now asserts the split rather than the count, so a `missing` bullet cannot be quietly reclassified as `deferred` to make the finding list shorter.
- **Canaried six ways, each watched failing and reverted from a file backup.** A §8 bullet reworded (the spec-comparison test), a `missing` bullet turned `carried` (the per-feature count pin), a third verdict value `'gap'` (the vocabulary test), a carrier rotted to a nonexistent attribute (the resolve test), a `missing` bullet declared `deferred` (the partition test), and a §8 id dropped from the audit set (the coverage test). 10 tests green, pyright clean.

The registry's divergence register was prose, and two of its four notes were false (2026-10-12). `DIVERGENCES` in `src/afya/registry/taxonomy.py` recorded four sensor ids whose tier §7.3's summary states differently from §14, and both crossings that read it (`spec_tier_mismatches`, `ebola_specific_mismatches`) exclude it by key — so the register's own contents were the one thing nothing checked.
- **SENS-007's note said "Followed §14.7" beside a registry tier of 2, and §14.7 says 3.** SENS-008 was not recorded at all: §14.8 gives it Tier 3, Appendix B gives it 4, and the registry carries 4. A register is a claim about the spec, and a claim nothing reads is a claim that drifts — the same shape as §13.1's lossy enum, one level up.
- **Appendix B states every one of these tiers a third time, and disagrees with §14 on two ids.** §7.3 is a summary, §14 is the detail, Appendix B is an index — three tables, one fact, and the register had compared only two of them. SENS-005 is `1 (basic) / 4 (monitoring)` in §14.5 and `2` in Appendix B; SENS-007 is `3` in §14.7 and `2` in Appendix B. Which table governs is a question for whoever owns the spec, so all four values are carried and none is overruled.
- **The register is now a model, not a sentence.** Each row is a `TierDivergence` naming its §14 section, that section's `**Tier:**` cell verbatim, Appendix B's tier, and the registry's own — and the test reads `docs/spec.md` and the Appendix B table to check all four. `DIVERGENT_IDS` is the frozenset the two crossings key on, so membership is derived from the register rather than restated beside it.
- **The served payload changed shape and got better for it.** `/features/taxonomy`'s `divergences` was a map of id to prose; it is now a list of objects with named fields, so a client reads `section_tier_cell` and `registry_tier` rather than parsing a sentence.
- **Canaried four ways, each watched failing and reverted from a file backup.** SENS-007's §14 cell misstated (the defect the register actually had), SENS-008's registry tier misstated, SENS-005's Appendix B tier misstated, and §14.8's row dropped from the register (the defect that was actually absent). 960 tests green, pyright clean.

The spec-coverage gate could not see an id written only inside a range (2026-10-12). `tests/ci/test_spec_coverage.py` reads ids out of `docs/spec.md` with a literal scan and asserts each resolves in the registry — the gate that stops a domain getting a namespace and never getting built. §7.3 and Appendix B write a span as `AI-004…005`, and `AI-005` appears in the spec in no other spelling.
- **The canary found it: deleting `AI-005` from the registry left all six tests green.** A feature could disappear with the gate reporting clean, which is the exact failure the module's own docstring says it exists to prevent. The extractor now expands `PREFIX-001…003` ranges and asserts the endpoints are ordered, and a named test asserts `AI-005` is visible to it — so a new range cannot reintroduce the blind spot.
- **The same shape is live in Appendix B.** Appendix B is the spec's own feature index, 45 rows across seven domains, and it omits the Records domain's own members: `REC-004`…`REC-009`, `LOC-001` and the eight sensors are filed under `### Records`. Nothing compares Appendix B to §7.3 or to the registry, so its two disagreeing tier cells are reported here rather than by a gate.
- **Canaried two ways, each watched failing and reverted from a file backup.** `AI-005` deleted from the registry (blind before the fix, caught after), and the range branch reverted to the literal scan (caught). 960 tests green, pyright clean.

§8's remaining four Tier-1 sections, the fourth tranche of the content audit (2026-10-12). §8 has thirteen feature sections and the second tranche audited nine of them, so FND-003, FND-005, EMG-003 and INF-006 — the tier the whole adoption argument rests on — were named in neither the audited nor the unaudited list. The report reads 24 audited / 23 unaudited / 96 missing / 0 unresolved, and the tranche assertion now names all four.
- **The omission was invisible and the partition test is what would have caught it.** A section in neither list is one nobody can find out is unaudited, which is worse than either verdict — and it was live here across four Tier-1 sections for two tranches. The lists partition the 47 labelled sections and that is asserted against the spec, but the assertion cannot see a section that *should* be in one and is in neither; only reading the tier against its own section count did. The docstring's "nine §8 Tier-1 sections" was the tell: §8.2 through §8.6 print thirteen `#### FID:` headings.
- **INF-006 carries one of eight contacts, and the other seven are not a directory problem.** `HOTLINES` is two rows — MoH 719 and an ODPC complaints desk — served by `/info/hotlines`. The mental-health and counselling numbers exist in `mental.COUNSELLING_LINES`, which the directory route never reads, so "mental health helpline" is missing from the directory although the numbers are in the tree; GBV and child helplines exist nowhere at all. The county health office, nearest facility, ambulance and CHW have no entry: `Facility` carries no phone field and `CaseReport.chw_ref` is a reference with no number, so neither can be listed without a model change.
- **All four of its Features render nothing callable.** No `tel:` link, no `sms:` link, no vCard and no shareable payload — the directory is data a client cannot act on, where `Directions` renders `apple_maps_url`/`google_maps_url` for the same reason. §3.3 principle 10 requires every output to be shareable as a WhatsApp card.
- **EMG-003's "emergency contacts" is one contact.** The section prints the plural; `EmergencyCard.emergency_contact` is a single `str` validated as one phone number, so the list collapses. `current medications`, `organ donor status` and `SHA number` have no field, and `SHA number` cannot reuse `InsuranceCard.sha_member_no_hash` because a hash is not the number the card would show.
- **FND-003's and FND-005's filter sets are flattened to zero.** Both ask to filter by four or five dimensions — test, cost, age eligibility, walk-in vs appointment, results turnaround — and `Place` carries only `opening_hours`, a free-text field the client can filter on. This is the §13.1 lossy-enum class one step further: a named set not narrowed but absent, so no client can distinguish a free testing site from a paid one.
- **One bullet was reclassified during the work, and the boundary is the reason.** INF-006's "save to contacts" was first marked `deferred` (a device action, like the maps app), which broke the deferred test at 8 against 7. It is `missing`: `HotlineInfo` carries no contact payload and the route renders no saveable artifact, whereas `Directions` does render one. A device action with nothing behind it is a gap, not a deferral, and the test that pins the split is what forced the distinction.
- **Canaried five ways, each watched failing and reverted from a file backup.** A bullet reworded off the section (the spec-comparison test), the whole FND-005 tranche dropped (the coverage, partition and per-feature tests together), INF-006 removed from `FEATURE_CONTENT` and named nowhere (the partition test), a carried reference rotted to a nonexistent attribute (the resolve test), and "save to contacts" turned `deferred` (the per-feature and deferred-split tests). A sixth canary adding a second contact field to `EmergencyCard` **passed**, which is the correct result and worth recording: the per-feature counts pin the audit table, they do not re-derive the model, so closing a gap shows up as a failing spec-comparison test only when the table changes with it. 960 tests green, pyright clean.

Appendix D was the last block of the spec carried nowhere (2026-10-12). Its seven rows are decisions the spec says are *required*, and they were cited in prose three times (`rollout/service.py:34`, `registry/gate.py:66`, `test_activation.py:162`) and held as data nowhere — so the list of what is still open was itself a thing a reader had to remember.
- **An open question is not a blank, and that is the finding.** Five of the seven are already answered in the tree by whoever last edited a file: the hotline is 719 unverified, the activation protocol is whoever calls the gate, the cloud provider is none, Tier-4 flags are internal, and the retention cap is 730 days. `OpenQuestion` carries `assumed` for each, checked against the code rather than trusted, because a register of assumptions that drifted from the assumptions would read as an inventory of what is undecided while being a description of what was decided by default.
- **Question 4 has already been answered in the negative, and §15.3's own example is the casualty.** The row asks whether to use AWS Africa or Azure South Africa; `HOST_JURISDICTIONS` classifies every `amazonaws.com` and `azure.com` host as `outside_africa`, so both options the appendix names are refused for case management, contact tracing and citizen personal data — and no host in the table is classified `african_union` at all, so the middle option §15.3 permits ("at minimum, African Union jurisdiction") is unreachable. `s3.af-south-1.amazonaws.com` with case-management data is a refusal today. That is a deliberate fail-closed default working correctly; it is also the answer to an open question, and it was invisible because the row was prose.
- **Question 7's cap was a bare literal.** `src/afya/privacy/service.py:257` read `assert record.retention_days <= 730` with the message "24 months cap". The appendix states the same number and the same unit and says it is *assumed*; the code stated it with no link to the appendix, so the one place that could have said "this is unconfirmed" said only "this is the rule". It is now `RETENTION_CAP_DAYS`, named once, with the appendix row's own provenance in the comment and the refusal message.
- **`live_at` is the checkable half of each row and `unresolved` is the finding.** A row naming a `module:attr` that no longer resolves is a blocker someone will believe is tracked after the code it names is gone — the same defect as a mitigation naming a module that was renamed away. Question 1 is the one row with no artefact: it asks which entity owns the product, and inventing a reference for it would be the fabrication the field exists to avoid.
- **Two of my own tests were wrong on first run and both are recorded.** The Q3 guard `'by' in field` matched `authorized_by_pheoc` — the very field it was meant to exclude, a substring check that cannot see the thing it guards — so it now names the holder fields a protocol would need. And the retention test did not `await` the call, so the coroutine never ran, the assert never fired and the result was `DID NOT RAISE`: the CLAUDE.md lesson about a fixture nobody awaited, reproduced exactly, caught by the test failing rather than passing.
- **Canaried five ways, each watched failing and reverted from a file backup.** A `live_at` rotted to a nonexistent attribute (the resolve test), a question reworded off the appendix (the verbatim test), a `Blocks` cell pointing at §15.4 where the appendix says §15.3 (the same test), the cap raised to 3650 (the assumption check and the refusal test), and an `african_union` host rule added (the Q4 negative). The fifth was reverted by edit rather than from a backup, because I had backed up two of the three files I mutated and `git checkout` would have taken the real `OpenQuestion` model with the canary. 965 tests green, pyright clean.

## §INF-006 implemented: the directory was a table, and the section asks for a screen

The content audit recorded §INF-006 as carrying one of its eight Contents and none of its four Features. Reporting that was not implementing it, and the gap had a shape worth naming: three of the eight numbers were *already in the repository* — `mental.COUNSELLING_LINES` held Befrienders Kenya, NACADA and the emergency line — and `/info/hotlines` served two rows of a different table and never read it.

- **The fold is by reference, not by copy.** `_directory_rows()` reads `mental.COUNSELLING_LINES` and builds `HotlineInfo` rows from it, so the counselling module keeps ownership of the numbers and the two cannot drift; an assert fires if a name it expects leaves the table. Each folded row keeps `mental`'s own `verified: 'False'`, so a number does not arrive on a life-safety screen looking checked because it moved.
- **`nearest_facility` is the one Content that is not a row.** It is an answer about where the caller is, so it is composed from `PlacesService.nearest` and `Place.phone` only when `lat`/`lon` are given, and reported `absent` otherwise rather than guessed. A facility OSM gave no number for is still listed — the row answers "where do I go", and dropping it for want of a number hides the destination because the number is missing; `actions` is None on that row, which is what "listed but not dialable" looks like.
- **`_dialable` exists because a life-safety row was written as prose.** The tree's own emergency entry is `1199 (ambulance) / 719 (MoH)`, and stripping non-digits from it produces `1199719` — a number that dials nothing, on the screen someone opens in an emergency. It cuts to the first number, asserts the result is non-empty, and `hotline_actions` uses it, so the ODPC desk's `+254-20-4226849` also becomes dialable.
- **The four Features are server-rendered, the way `Directions` renders its two map URLs.** `tel:`, `sms:`, a vCard 3.0 body and a `wa.me` share link. A directory whose "one-tap call" is a client obligation is a directory where two clients disagree about whether it works; and §3.3 principle 10 requires every output be shareable as a WhatsApp card, which needs a link to carry.
- **`absent` is derived in the model, and that is the second attempt.** It was first computed in the service from `SPEC_CONTENTS`, and a canary that swapped `SPEC_CONTENTS` for `ContactKind` — a gap list over the whole enum instead of the section's eight — *passed*. The reason is the interesting part: on today's data the two spellings give identical sets, because both non-Content members happen to be present, so no assertion over the served rows can tell them apart. The distinction is only visible in the case where a directory holds all eight *plus* the ODPC desk, which would report itself incomplete for carrying an extra. The fix was structural rather than a better assertion: `absent` and `complete` are `computed_field`s on `ContactDirectory`, derived from `SPEC_CONTENTS`, so a caller cannot hand over a gap list that disagrees with the rows beside it — and the test now constructs the case where the two spellings differ.
- **The audit rows were rewritten to state what the code does.** `INF-006` is 5 missing of 12 (was 11), `missing` 96 → 89. Still genuinely absent: county health office, CHW, GBV helpline, child helpline — no number for any exists in the tree, and each is now named in `absent` on the served screen rather than being a blank. `nearest facility`, `ambulance`, `mental health helpline` and all four Features moved to `carried`.
- **One of my own audit rows broke its own gate, correctly.** I marked `one-tap SMS` as `missing` while naming `HotlineActions.sms_uri` as its carrier; `test_every_verdict_is_one_of_three_and_only_one_is_a_finding` refuses a non-carried bullet that names code. It is carried — "one-tap" is the client opening the composer with the number prefilled — and §EMG-001's "works over SMS when data is unavailable" is a different claim with a different gap, which the note now keeps separate.
- **Canaried six ways, each watched failing, reverted from file backups of every mutated file.** The counselling fold removed (3 tests), `_dialable` no longer cutting a two-number row, `absent` derived over the enum (the one that had been blind, now caught by the constructed case), `complete` no longer reading the derivation, the route serving the old bare list, and `actions` dropped from the served rows. The harness asserts its target is present *and unique* before patching, and continues past a bad target rather than aborting — one wrong path in the first version would otherwise have hidden the remaining canaries, which is how the blind gate was found at all. 973 tests green, pyright clean.

## §EMG-003 implemented: the offline card carried five of its seven Contents

The card is the one artefact in this product a stranger reads about an unconscious person, and it held five fields where the section prints seven. The two gaps that mattered were not the missing fields but the two that were *collapsed*.

- **"emergency contacts" is plural, and each one has a name.** The model carried `emergency_contact: str` — one phone number validated against a single-number pattern — so the plural the section writes could not be expressed. `EmergencyContact` carries a name, a number and an optional relationship, and the QR renders each as `name:number`. A bare number tells a clinician nothing about who they are ringing.
- **Organ-donor status is tri-state, and that is the one field where a defaulted boolean is a safety property.** A hospital reading the card must be able to tell "this person declined" from "this person was never asked"; `organ_donor: bool = False` answers the second as the first and nothing on the card would say which had happened. It is `bool | None` and renders `yes`/`no`/`unknown`.
- **The SHA number and the hash-only rule are not in tension.** `insurance.views.sha_of_member_no` exists so member numbers are never *persisted*, and §EMG-003 asks for the number a hospital can read off a card. `sha_number` lives on the payload and no method in `emergency` stores a card, which is what keeps both true. `InsuranceCard.sha_member_no_hash` is unchanged and still the stored form.
- **§EMG-003's Access clause is now a field.** "Available from the lock screen without unlocking the phone (opt-in)" — the opt-in *is* the clause, so `lock_screen_opt_in` defaults False. A card is not lock-screen readable because it exists, and the default is the one that shows a stranger nothing.
- **`Access` is a sixth auditable label and the label gate had to learn it.** The spec prints it twice: §EMG-003's two sentences and §19.4's "PHEOC, county health teams, MoH. Role-based. Audit logged." It is a different kind of list from the five content labels — who may reach a feature rather than what it holds — and both are content a section states. Adding it to `_LABELS` meant the audit's own `assert all(label in _LABELS ...)` fired first, which is the gate working: a new label cannot be added to the table without being declared. §19.4's own Access row is unaudited and named as such in the module's coverage paragraph.
- **A second coverage figure was wrong and the recount caught it.** I first wrote "293 items across 48 sections"; the recount over the spec says 293 across **47**. The item count moved (292 → 293) because §EMG-003's Access cell adds one, and the section count did not because EMG-003 was already counted — §19.4 is outside the §8–§12 range the figure describes.
- **`EMG-003` now has no row in the missing-by-feature dict at all**, which is the strongest verdict the audit has and reads as an omission unless it is labelled: all seven Contents and both Access clauses resolve to code. The dict carries a comment saying so.
- **Canaried five ways, each watched failing, all three mutated files restored from backups.** `organ_donor` back to a defaulted `False`, the plural list allowed empty, `card_qr` collapsing `unknown` into `no`, `lock_screen_opt_in` defaulting True, and a contact losing its name (4 tests). `missing` 89 → 85. 977 tests green, pyright clean.

## §FND-003 and §FND-005 implemented: the finders had no filter to apply

Both sections' Features cells are filter lists — "Filter by test, cost, hours, results turnaround" and "Filter by vaccine, age eligibility, cost (usually free), hours, whether walk-in or appointment" — and both routes took `lat`/`lon`/`limit` and returned everything. `Place` is an OSM-normalised POI: OSM knows a clinic's name and position, not what it tests for or what it charges, so there was no field to filter on and the audit recorded eight of the nine dimensions missing.

- **The offering is a list on the place, not a column.** `TestOffering` and `VaccineOffering` carry the dimensions per test and per vaccine, because a facility's price and turnaround differ by test — a single `cost_kes` on the clinic would have to be wrong for all but one of them.
- **The tri-state rule from `EmergencyCard.organ_donor` applies to all four numeric fields.** `cost_kes`, `turnaround_hours`, `min_age_months` and `walk_in` are `| None`, and `0`/`False` are real values. "This test is free" and "nobody has priced it" are different answers on the screen someone uses to decide whether they can afford to go; a defaulted `0` answers the second as the first.
- **`unanswered` is the finding, and it is the reason the fields are tri-state at all.** Filtering a facility out because its row has no `tests` published turns "nobody has filled this in" into "this clinic does not test for HIV" — a wrong answer arrived at by a filter that looks like it worked. Each dimension is applied only over the places that published it, and the dimensions nothing published are returned so the screen can say "cost not published" rather than showing a shorter list that reads as an answer. An empty pool returns `[]` and *no* unanswered dimensions: "we have imported nothing" is a different sentence from "nobody has published a test list".
- **A cost ceiling keeps unpriced places.** A place with no prices has not said it is expensive; it has said nothing. Dropping it would hide the public clinic whose row nobody has filled in — the one a person looking for the cheapest option most needs to see. `walk_in_only` is the deliberate exception and excludes on absence, because §FND-005 asks a yes/no question and someone turning up without an appointment needs a yes rather than a maybe.
- **`TestOffering` is a pytest collection warning.** A model whose name begins `Test` is collected as a test class; `__test__ = False` on the model is the fix, and the warning had been there since the first run.
- **The mobile action catalogue carries the filters.** `/places/testing-sites` and `/places/vaccination-points` gained their sections' arguments, and the two `_a(...)` entries gained matching `_f(...)` fields — the `test` placeholder names examples ("e.g. malaria, HIV, TB") rather than the spec's feature id, per the no-feature-codes-in-UI rule.
- **FND-003 and FND-005 now have no row in the missing-by-feature dict.** With EMG-003 that is three audited sections carrying nothing missing.
- **Canaried six ways, each watched failing, both mutated files restored from backups.** The test filter not applying, an unpublished dimension silently filtered instead of reported, `walk_in_only` not excluding, `cost_kes` defaulting to `0`, the route dropping its filter arguments, and an empty pool reporting a filter defect. `missing` 85 → 78, `carried` 72 of 157. 984 tests green, pyright clean.

## Content audit completed: all 47 labelled sections, and the report's own coverage claim

The audit read 24 of the 47 §8–§12 sections that carry a `**Features:**`-style list and served
`unaudited_features` naming the other 23. That list was honest and it was also the module's own
admission that 136 labelled items had never been crossed against the code. All 23 are now audited;
`UNAUDITED_FEATURES` is an empty tuple.

- **The tranches are kept as assertions after the coverage went to 47/47.** A rule that is only true at the moment of the merge rots on the next edit. Each block in `test_the_audited_sections_are_the_ones_the_survey_found_uncited` names sections whose *reason for being audited* differs, so removing any one fails with the reason attached rather than as a smaller number.
- **`UNAUDITED_FEATURES` is kept and asserted, not deleted.** The empty list *is* the claim of coverage, and a reader is entitled to see the mechanism that would name a section the day the spec gains one and this table does not. The partition test still walks the spec's own `#### FID:` headings, so it fails on the next unaudited section rather than on a stale count.
- **§19.4's `**Access:**` is out of scope rather than unaudited.** It is the spec's only labelled list outside §8–§12, and this module declares §8–§12. The distinction matters: "unaudited" invites a to-do, and a section outside the declared scope invites a scope argument, which is the honest one.
- **The 22 sections without a labelled list are not omissions.** They state their content as prose, tables or route lists, and a section with no list under a label has nothing for this module to cross. `test_the_report_states_how_much_of_the_spec_it_read` asserts `len(labelled) == 47` against the spec so the two sets stay identified.
- **The three verdicts moved as the new tranches were read.** `deferred` went from 7 to 10 — eight device actions (a maps app, a dialler, a barcode reader, a camera, a call-log and location permission) and two conditions on the world (TRI-003's vaccination input, ALT-002's check-in prompt). The test now names the two world-conditioned ones individually, because a deferral on a *world state* is the kind most easily abused to make a gap disappear.
- **The new tranches found 59 gaps**, taking `missing` from 78 to 137 across 43 sections. The largest are §MON-002 (9), §REC-001 (6), §AI-003 (6), §REC-005 (5) and §MON-009 (5) — the mental-health section names two validated instruments, a mood time series, psychoeducation and a referral path, and the module carries a single WHO-5 instrument and a counselling-line table.
- **Canaried six ways, each watched failing, both mutated files restored from backups.** A carried reference rotted to a nonexistent attribute (the resolve test), a bullet reworded away from the spec, a section dropped from the table, a `missing` bullet reclassified `deferred` to make the gap vanish, an audited section re-listed in `UNAUDITED_FEATURES`, and a bullet's verdict flipped. The first attempt at the rotted-reference canary hit a target that appeared twice and was reported `NOT RUN` — a canary whose patch does not apply is a canary that did not run, and the harness continues past it rather than aborting.
- **Coverage reads 47 audited / 0 unaudited / 137 missing / 0 unresolved.** 293 labelled items across 47 sections; `carried` 146 of 293. 984 tests green, pyright clean.

## §TRI-001 and §TRI-002 implemented: the triage result was one of its four Outputs

§8.1 prints four Outputs and the route served the first. `recommendation` was prose and
`escalate_719` a boolean, so a client had a sentence and a flag and nothing executable; the
watch-for list and the summary card did not exist. §TRI-002's five Features were a log and four
absences: `diary_append` stored an entry and `diary` returned the list, and the prompt, the
escalation, the trend and the export were named in neither list.

- **§8.1 prints High twice and the enum had it once.** "High (Ebola suspicion)" and "High (other cause)" send a person to different places — isolate-and-notify under IDSR versus seek-care-today — and `RiskLevel.high` answered both. `emergency` was missing too, so a bleeding case carried the same value as an exposure risk. The enum is six members now, one per rung the section prints, and `strings.TRIAGE_RECS` gained the two keys so the recommendation can say which.
- **The red flags were absent from the input entirely.** §8.1 lists eight as its own Inputs list, separate from the symptom multi-select, and a convulsing person with a normal temperature could not be triaged at all. `TriageInput.red_flags` is a closed set — an unknown flag is refused — and `EMERGENCY_FLAGS` is the four that mean an ambulance rather than advice.
- **The three exposure criteria are one derived field.** Travel, contact and attendance at a known exposure site were three booleans with the `or` written twice in the algorithm, and `exposure_site` had no field, so a person who attended a funeral of a known case could only be triaged by claiming contact. `exposure_history` is a `@computed_field`.
- **The summary card carries no exposure detail, and that is a safety property.** §3.3 principle 10 wants every output forwardable; §8.1's Privacy clause says triage data stays on-device. The card is the one output that leaves the phone, so it carries the classification and what to do — not the symptom list, not the travel flag, not the exposure site. The test asserts the card is exactly its four lines rather than grepping for words, because the recommendation legitimately says "do not travel by public transport" and a substring check for `travel` would fail on the advice while a real leak went unnoticed.
- **§TRI-002's escalation is about *new* flags.** A version that fired on any entry carrying one would repeat the same ambulance message daily until the person stopped reading it, so the escalation is computed from the diary and tracks which flags have already fired. It returns `None` rather than a low-risk result: a client that renders the return value would otherwise show a triage answer where the section asks for silence.
- **The trend has an `unknown` member.** A first entry has no trend, and "no change yet" is a different answer from "stable over four days" — a two-member enum forces the first entry to claim one.
- **The daily prompt's opt-in is the gate, not a flag.** §TRI-002 writes the opt-in into the Feature, so a declined prompt returns `null`. The server owns the opt-in, the cadence and the words; the device owns the notification — the same split `HotlineActions` uses, because a server that claimed to have *sent* a prompt would be claiming a push channel the product does not have.
- **The GSM-7 gate caught a defect in the new copy.** The `emergency` recommendation contained an em dash, which cannot be sent as a plain SMS — §6.2's forwardability rule, enforced over the served corpus, and it failed the moment the string was added. Rewritten without it.
- **Canaried nine ways, each watched failing, all three mutated files restored from backups.** The two `high`s collapsed back, a red flag stopped escalating, the watch-for list emptied, the one-tap actions collapsed to one, the card started carrying the symptom list, the escalation re-fired on a repeated flag, the prompt ignored the opt-in, the trend claimed a direction from one entry, and the export dropped the red flags. The fourth canary came back `BLIND` — nothing asserted that an emergency still offers all three actions — so the test was widened and the canary re-run until it fired.
- **§TRI-001 and §TRI-002 now have no row in the missing-by-feature dict.** With §EMG-003, §FND-003 and §FND-005 that is five audited sections carrying nothing missing. `missing` 137 → 129, `carried` 154 of 293, gaps across 41 sections. 998 tests green, pyright clean.

## Content audit, third instrument: the unit of coverage is the (section, label) pair

The audit's first two versions both reported a total that was a fact about the instrument. The
first knew six labels and called its coverage complete over 47 sections; §8.2 FND-001's ten-item
content list sits under `**Data displayed per facility:**`, which it had never heard of, and three
of the sections it called gap-free were the ones it had not read. The second widened the vocabulary
to all 74 labels the spec prints but split them by *name* into content and claim — and eight of the
labels it filed as claims (`Application`, `Behaviour`, `Conditions supported`, `Deployment points`,
`How it works`, `Privacy properties`, `Standards`, `Technical approach`) print bullet lists. Those
eight were the whole of the eight sections it then called contentless. Both times the miss was one
level up from the spec, in the measuring instrument.

- **The partition is now on the shape of the body, not the name of the label.** `_LABELS` is every label whose body enumerates what the feature does or holds; `_CLAIM_LABELS` is every label whose body is a sentence about it. `test_a_label_declared_out_of_scope_has_no_list_under_it` fails the moment a bullet or numbered list appears under a claim label, so the partition cannot rot silently. 30 + 44 = 74, asserted disjoint and asserted to equal the spec's own label set.
- **Coverage is per (section, label), not per section.** `test_every_content_label_a_section_prints_has_rows_under_it` walks the spec's pairs and fails on any pair with no rows. That gate found 44 items sitting under labels *inside sections the audit already claimed to have audited* — §TRI-001's `Inputs`, §FND-001's `Data displayed per facility`, §FND-003's `Test types`, §INF-004's `Format`, §MON-003's `Conditions supported`, §AI-001's `Inputs`, §SEC-001's `Consent categories`. A section in the table was never evidence that its lists had been read.
- **The parser knew two list shapes; the spec writes three.** Bullets, numbered steps, and one-sentence comma-separated prose. §LOC-002's `How it works` is a six-step proximity protocol written `1.` … `6.`, and the two-shape parser read it as one prose cell — which is how a six-step exposure-notification design became a single item, and how step 5, where a user's app checks the uploaded tokens and notifies them, went unmeasured.
- **Fixing the pair gate exposed the last fourteen sections.** Their content hangs off a label naming an *artefact* rather than a feature — a `Displays`, an `Entry questions`, a `Format`, a `Topics`, an `Options`, a `Targets`, a `Content`, a `User rights`. The first six labels the module ever knew were all feature-shaped, which is exactly why these read as sections with nothing to audit. They are the ninth tranche in `test_the_audited_sections_are_the_ones_the_survey_found_uncited`, and the first tranche a count could not have produced: the eight before it were found by asking what the instrument could not *see*, this one by asking what it had read but not *finished*.
- **The scope is 490 items across 69 sections, not 293 across 47.** 197 rows were written by three agents against the spec and spliced in document order — section order, then the section's own label order, then the spec's bullet order within a label. Five sections print their labels in the reverse of the declaration order (§FND-003, §LOC-004, §INF-003 among them), so ordering by `_LABELS` would have moved rows away from the text they transcribe.
- **The splice was proven lossless before it was trusted.** The pre-existing 293 rows were re-read from a backup by AST and compared: 0 lost, 0 altered, no (section, label) pair shrank, 35 pairs added. The table is rewritten through AST offsets rather than string search, because the file carries `# --- §8.1 TRI-001` comments between rows and the first `\n)\n` after the opening paren is not the closing one.
- **Every agent row was verified against the spec rather than trusted.** All 197 bullets match the spec character-for-character and in order, and all 113 `carried` references resolve. The writers' own narratives were checked and one miscounted (42 vs the file's 44) — the file was verified directly.
- **The findings the new rows carry are real.** §FND-001's `Place`/`Facility` carries name, phone and hours and none of the section's level, services, SHA/NHIF acceptance, cost band, Ebola-screening designation or user reports. §INF-003's 13 topics, §INF-008's 11 and §INF-009's 10 have no corpus item behind them. §SEC-003's "at rest: AES-256" is carried by a string constant that names another claim — `EncryptionPosture` sets booleans true and no store encrypts. §ACC-004's "adaptive sampling" is a hardcoded `charging_adaptive=True`. §LOC-001's alert string is absent repo-wide. §REC-002's certificates, PDF export, timeline and growth charts are absent.
- **Canaried three ways, each watched failing, both files restored from backups.** A label moved into `_LABELS` with no rows (`Battery`, and moved *across* from `_CLAIM_LABELS` so it tripped the coverage gate rather than the partition test — the first attempt was masked by the partition assertion, which is the same masking the earlier session hit). A (section, label) pair's only row dropped. And the rotted-carrier canary. Reverted from `cp` backups, never `git checkout`.
- **Coverage reads 69 audited / 0 unaudited / 213 missing / 0 unresolved.** 490 labelled items across 69 sections; `carried` 261 of 490; `deferred` 16 (14 device actions, 2 world-conditioned). 1001 tests green, pyright clean.

## §FND-001/002/003/004: the facility finder becomes a finder

The audit's first finding was that §8.2's four locator sections declared filter lists and content
lists that no field existed to satisfy. `Facility.model_fields` was eleven entries —
`facility_id, name, kind, county, lat, lon, open_now, hours24, wait_minutes, ed_status, crowdload`
— and the section prints a level ladder, seven services, SHA acceptance, a cost band, an Ebola
designation, isolation beds, ICU beds, ambulances and trauma capability. `TestOffering.name` was
free text, so §FND-003's seven test types had no vocabulary to be one of.

- **`FacilityLevel` and `ServiceOffered` are closed sets, and both assert their own totality.** `_LEVEL_RANK` maps every member to a rung and asserts `set(_LEVEL_RANK) == set(FacilityLevel)`, so a level added without a rank fails at import rather than sorting last. `_COST_RANK` does the same with `free` at 0, which is what makes `max_cost_band=free` mean "only free" rather than "not high".
- **Tri-state where the section's own reasoning demands it, and not where it doesn't.** `accepts_sha`, `cost_band`, `icu_beds`, `ambulances`, `trauma_capable` are `X | None` because "nobody filed the row" and "the answer is no" are different answers, and §FND-001 calls SHA acceptance "critical for cost anxiety" — a defaulted `False` tells a person their insurance is refused when the county has simply not filled it in. The four §FND-002 capacity filters are the opposite and deliberately so: `min_icu_beds`, `needs_ambulance`, `needs_trauma`, `needs_isolation` **exclude on absence**, because a person looking for an ICU bed needs a yes. The two rules sit in the same method and the difference is the section's, not the code's.
- **`find()` reports the dimensions nothing published rather than applying them.** A filter over a pool where nobody filed a cost band would answer "no facility is affordable" — turning "the county has not filed this" into a finding about the facilities. It returns `(results, unanswered)` and `/facilities/find` serves `unanswered` alongside, the same contract `/places/find` already kept.
- **The offline bundle is the radius *plus* the home county.** §FND-001 prints 50 km and its own Offline note adds "Full offline bundle for user's home county available on first sync". Both are the bundle: a person near a county border has facilities in their own county farther than 50 km that it still owes them. Served as `OfflineFacility` rows rather than dicts, so the `km` a screen sorts on is a validated field instead of a key a reader guesses.
- **`TestType` closes §FND-003's seven, with `name` left free for what the facility calls the test.** A person typing "RDT" and a filter chip generated from the spec are different queries over the same offering, so `test` matches the name and `test_type` matches the vocabulary. `TestOffering.__test__ = False` because pytest collects any class starting with `Test`, and this one is a model.
- **The routes are where the gap was.** A capability with no route is one nobody can use: `/facilities/find`, `/facilities/offline-bundle`, `POST`/`GET /facilities/{id}/reports` and `/places/pharmacies` are new, and `/places/testing-sites` gained `test_type`. `POST /facilities/{id}/reports` and `/facilities/find` were added to `UNGATED_WRITES` with their justification, which is the gate that caught them.
- **`FacilityReportRequest` is a separate model from `FacilityReport`.** The facility id is in the path, so repeating it in the body creates a mismatch between the two that nothing checks.
- **Counts moved: 21 rows flipped `missing` → `carried`, 213 → 192.** §FND-001 (9), §FND-002 (4), §FND-003 (7) and §FND-004 (1) leave `test_the_missing_bullets_are_pinned_by_feature`, which asserts per-section counts precisely so a repair in one section cannot hide a regression in another. 490 rows, `carried` 282, `missing` 192, `deferred` 16. 1017 tests green, pyright clean.

## §INF-003/008/009/010: the health library becomes the four sections' library

§8.5's Ebola Information Library and §10.5's three features were all accounted for in the coverage
gate as "items in the health library corpus". Each had one item. The sections print nine, eight,
eleven and six topics, plus four Format cells, and a section accounted for by the existence of a
corpus is a section whose contents were never read.

- **The unit of coverage is the (topic, item) pair, and coverage is computed, not asserted.** `covers(item, topic)` reads the item's own title, body and slug; `coverage()` returns `covered` and `gaps` and the two partition the section's topic list exactly. Every one of the 34 topics across the four sections now resolves to a corpus item.
- **`covers` was a strict subset of what it tested and failed toward "clean".** The first version matched any keyword and read `'for' in haystack`, so a burial item covered "Support for grieving families" by containing "for", and an Ebola item covered "Stigma and how to fight it" by containing "it". Fixed with `_GENERIC` (a function-word blocklist), sibling-word distinctiveness in `_keywords()` — a word shared by every topic in a list cannot distinguish between them — and a `_TOPIC_PHRASES` exact-phrase table for the topics whose subject is a phrase rather than a word.
- **A rendition is not an item a reader opens.** §INF-003 asks for "illustrations, audio versions, video versions" and §INF-008 for "30-second videos, audio clips". Served as library entries, a non-text item is a blank card beside the article it belongs to — 11 of them, confirmed by listing `library('en')`. `ContentItem` gained `format`, `media_ref` and `rendition_of`, with assertions tying the three together: a text item has no media reference and no parent, a rendition has both. `library()` withholds renditions; `renditions_of(slug)` returns them; `/info/library` serves them as a `renditions` list on the parent article, which is what lets a client know an audio version exists before rendering the text.
- **§INF-009's illustrations are asked for in its Description, not its Format cell.** "Offline first-aid instructions with illustrations" is the one feature whose second dimension is not in `FEATURE_FORMATS`, so it has its own `illustrated()` computation over the eleven first-aid topics rather than being read as a format label.
- **"Short articles (under 200 words)" is a requirement inside a Format cell, so it is measured rather than parsed.** `ARTICLE_MAX_WORDS = 200`, reported by `over_length()` rather than enforced by a route: an article at 210 words is not a defect to refuse a read over.
- **66 items and 22 renditions.** The corpus is the four sections' 34 topics in both languages where the topic is life-safety, plus the burial guidance's six content points and the §INF-003 library's articles. `_TAG_FORMAT` is what makes §INF-008's tips render as `card` — the Format cell's "short cards" had nothing to match while every row defaulted to `article`.
- **§6.2.10's long-sentence rule caught ten of the new sentences, and the gate is title-plus-body.** "Design for low literacy. Short sentences." reads the concatenated text, so the first "sentence" includes the title. Ten sentences over 25 words, all in the new content, all split; the three that failed `test_content_principles.py` were the visible end of a gate that had been right about the other seven.
- **The audit moves: 37 rows flipped `missing` → `carried`, 192 → 155.** §INF-003 (13), §INF-008 (11), §INF-009 (10) and §INF-010 (3) leave `test_the_missing_bullets_are_pinned_by_feature`. One of those 37 was a gap the brief did not name: §INF-010's "Who to contact (burial team)" had no carrier under the sibling rule either. Its old `carried` note credited a `safe-burial` item that never said "contact", which is what a carrier note written from the item's name rather than its text looks like.
- **Not fixed, and named rather than left:** §ACC-003's "Pre-cached offline bundles: facility list for home county, first aid guide, information library, drug interaction database" is marked `carried` by `afya.rollout.service:MODULES`, a size plan with megabyte figures rather than a bundle payload. The facility bundle, the library and the drug interactions exist as three separate endpoints and no single pre-cached bundle does. That is §ACC-003's unit.
- **Three model guards canaried and reverted, `library()`'s withholding canaried and reverted, the widened `/info/library` code-free gate canaried and reverted.** 490 rows, `carried` 319, `missing` 155, `deferred` 16. 1022 tests green, pyright clean.

## §MON-002: the antenatal tracker was two features wearing one name

§MON-002 and §REC-008 were accounted for by the same sentence — "same antenatal tracker as REC-008,
which the catalogue reaches" — and the coverage gate took it. §MON-002 prints ten features; REC-008's
name is the tracker. So nine of the ten had no carrier at all, and the shared sentence is what made
that invisible: the section was reachable, which is not the same as the section being read.

- **A section accounted for by a sibling is a section nobody read.** The two ids do name one module —
  the schedule and a danger-sign classifier — but §MON-002's Features list is where the other nine
  live, and none of them existed. The `ON_DEVICE` entry came off; a comment in its place records why,
  because the entry was the reason the gap survived three audits.
- **Naegele's rule, not an input.** `estimated_due_date(lmp_iso)` adds `GESTATION_DAYS` = 280 to the
  first day of the last period, and `/maternal/due-date` serves it ungated — a date in, a date out,
  no subject and no record, the same shape `/places/find` has. `Pregnancy` gained `lmp_iso`, so
  `gestation_week` reads the same number back off either the LMP or a clinic-card EDD and the two
  registration routes agree at the same week.
- **A reminder is a date, not a contact number.** §MON-002 asks for visit reminders; the section's
  own eight-contact table is weeks, so `visits()` returns each contact with the date it falls on and
  the 3-day and 1-day leads. A contact already recorded carries no lead — a reminder for a visit that
  happened is a wrong date, which is worse than a missing one.
- **Danger-sign education and the one-tap are one payload, and the order is the classifier's.**
  `DANGER_SIGNS` has nine members and `DANGER_SIGN_EDUCATION` is asserted equal to it at import, so a
  sign added to the classifier cannot reach a screen as a bare word. `assess_danger` now returns the
  education for the signs reported and a `CareAction`: `tel:719` when the classification is immediate,
  the maternity finder otherwise. Rendered by the server for the same reason §8.1's is — the phone
  number is a fact about the deployment, not about the client.
- **The birth plan is five optional fields with `gaps()` in the section's order.** Facility,
  transport, birth companion, blood donor, funds. Every field optional because a birth plan is built
  over several conversations; `gaps()` exists because a screen that cannot see what is unanswered
  renders an incomplete plan as a finished one. Served together at `/maternal/birth-plan`.
- **Postnatal contacts count from a recorded birth, and before it the list is empty.** Four WHO
  contacts — day 1, day 3, day 7–14, week 6 — from a `record_birth` date. Four dates derived from a
  delivery that has not happened are four wrong dates, so the empty list is the honest answer.
- **The newborn signs are the section's own eight, not the mother's.** Not feeding, convulsions, fast
  breathing, hot, cold, jaundice, cord infection, floppy. The one sign the two lists share is a
  convulsion, which is a convulsion in either.
- **Trimester guidance is keyed by trimester and asserted to cover all three**, so a pregnancy cannot
  reach a trimester with nothing behind it — the same shape as `_LEVEL_RANK` in §FND-001.
- **The maternity finder is §FND-001's finder with the service pinned.** `FacilityKind` still has no
  maternity member and does not need one: the section filters on the *service*, so `ServiceOffered.
  maternal` is pinned the way `/places/pharmacies` pins its kind, with `level` and `accepts_sha` open
  and `unanswered` travelling as it does on the general finder.
- **The PMTCT referral takes the boolean, never the result.** The caller derives relevance at the
  point of care; the HIV status does not reach this module, which has no PIN on it. Same rule §MON-003
  keeps for the same fact.
- **Ten catalogue actions, and the reverse gate was canaried.** Every one of the ten maps to MON-002
  in `FEATURE_OF`. The self-scope gate was pointed at `/maternal/{ref}/visits` with its
  `require_self(...)` removed and watched to fail — `personal-data routes without a subject-binding
  guard: ['GET /maternal/{ref}/visits (None)']` — then reverted from a file backup. The audit rows
  are claims about code and were rewritten as such: the nine `missing` rows flipped to `carried` with
  the carrier named, and `test_the_missing_bullets_are_pinned_by_feature` lost `'§MON-002': 9`.
- **Counts: 9 rows flipped `missing` → `carried`, 155 → 146.** 490 rows, `carried` 328, `missing`
  146, `deferred` 16. 1033 tests green, pyright clean.

## §INF-002: the tree had one door and the section prints six

The section prints six Entry questions and an Output of "specific, actionable guidance with facility
and hotline links". What existed was one root — "Do you have fever (≥38.0 °C)?" — and one sentence
per leaf. Those are two different products, and the gap between them is the audience §6.2.10 exists
for: a reader who opens the app saying "I have a fever" has already established the fact the root
asks them to measure, and a sentence naming 719 is a number they must retype from text §ACC-001 is
reading aloud.

- **The six entries are served, and the test reads them off the spec.** `ENTRY_ANSWERS` is the
  section's own six in its own order, at `/info/entry-answers`; `tests/ci/test_decision_tree.py`
  parses `docs/spec.md` and asserts the served list equals the printed one, so a spec revision fails
  here instead of leaving the menu serving the old six. This is the same contract `RANKED_QUESTIONS`
  keeps with §6.1.
- **Three entries open the walk and three open a screen, and `kind` says which.** A rumour check is
  §INF-004's corpus and a travel worry is §LOC-001's advisory; neither is a branch of a fever
  classifier, and forcing them into the tree would produce leaves whose answer has nothing to do
  with the question. What the section asks is that each entry lead somewhere specific, which `href`
  makes a fact rather than a label.
- **An entry that opens a screen names the inputs that screen needs.** `asks_for` is the travel
  advisory's destination and origin and the facility search's position; the test reads each route's
  own signature and asserts the two agree in both directions — every required parameter declared, or
  the client opens a door that returns 422, and every declared input real, or the client prompts for
  something the route ignores. This is the `MATERNITY_FINDER_HREF` discipline from §MON-002 applied
  to a menu.
- **"Someone in my house is sick" is a second root, not a branch.** Routing it through the fever
  tree makes the caller answer "no" to a question about their own temperature and be told no action
  is needed, while the person in their house is the one who is unwell. `TREE['household']` asks about
  the sick person and reaches two leaves disjoint from the fever walk's four — asserted, because two
  roots sharing a leaf is one root answering the other's question.
- **The Output is a shape, not a sentence.** `DecisionStep` carries `done` so a client cannot render
  a question as a recommendation, and `links` — empty while the walk is still asking, because a
  facility button under an unanswered question is a reader leaving before the tree has said
  anything. `leaf_ok` is deliberately empty: "No action needed" is the answer, and a button under it
  sends someone who needs nothing to a clinic. The household home-care leaf carries the facility
  search without the call, for the same reason — the clinic two days from now, not an ambulance
  today.
- **`LEAF_LINKS` is asserted against the tree at import, in both directions**, so a leaf with
  nowhere to go and a row for a node that is not a leaf both fail at import rather than on a screen.
  Canaried: adding a `leaf_nonexistent` row raised the assertion by name.
- **`/info/library` gained the `tag` filter** the fourth and fifth entries open. Without it an entry
  question opens the whole corpus and leaves the reader to find their own section, which is not what
  an entry question is for. The entry reachability gate was canaried against the real table —
  pointing the travel entry at `/location/nope` failed with the dead path named — and the canary runs
  the gate's own comparison rather than a copy of it.
- **Counts: 8 rows flipped `missing` → `carried`, 146 → 139.** §INF-002 leaves
  `test_the_missing_bullets_are_pinned_by_feature`. 490 rows, `carried` 335, `missing` 139,
  `deferred` 16. 1042 tests green, pyright clean.

## §REC-001/§REC-002/§REC-003: the wallet was five row types with no set to operate on

§9.2 lists eight things a family health wallet holds and §10.1 lists four operations over them —
timeline, search, export, share — plus a provider view, a certificate and a backup. Thirteen audit
rows, six of them marked `missing` for the same reason: the documents existed as five unrelated row
types (`ImmunisationRecord`, `LabResult`, `Prescription`, `InsuranceCard`, a `Booking` in another
module) and there was no set, so each operation would have had to be written once per type. They are
not thirteen features. They are four operations over one set, and the set was what was absent.

- **One envelope, four operations.** `WalletDocument` carries §9.2's eight kinds with `payload:
  dict[str, object]` for each kind's typed fields, so the envelope is lossless rather than a second,
  poorer copy. The alternative — eight nullable columns — makes every kind's fields optional for
  every other kind, which is a schema that can hold nothing. `kind` is a closed set, so a document
  that is not one of the eight is refused at the model.
- **`media_ref`, not bytes.** "Photo capture and storage" is the client uploading through the
  existing evidence route and filing the document with the returned reference. A wallet holding image
  blobs would put every family's photographs in the row a query returns; `ContentItem.media_ref` is
  the same split for audio and video.
- **The timeline is a sort, not a second store.** An event log written on each filing path would
  drift from the wallet the first time a path forgot, and the timeline would be missing a document
  the wallet holds while both looked correct. It asks `owns` per member, so a member who turns 18
  drops out of their guardian's timeline on their own birthday — §17.6's transfer, applied to the
  view and not only to the record routes.
- **One grant serves REC-001's secure link and REC-002's provider share.** They are the same
  mechanism; written as two features they would have produced two expiry rules, and the one that
  dropped the expiry would be the one nobody noticed. `expires_iso` is required, `share_view` refuses
  past it (inclusive at the boundary), and a grant ending before it begins is refused at issue. The
  refusal is the feature: a time-limited share whose reader is not stopped at the limit is an
  unlimited share with a date on it, and the date is the part that gets tested.
- **Revocation checks who is asking.** `revoke_share` takes an id alone, which is right for the
  service and wrong for a route — an id is a value a caller can guess, and a revocation that only
  needed one would let a stranger switch off a share they are not party to: a denial of care with
  §17.1 on it. The route reads the grant, checks ownership, and only then withdraws it. Found by the
  route test, not by review.
- **`issued_by` defaults and the server overwrites it.** It was `min_length=1`, so the route refused
  every client that did not send a value the server discards — a required field the caller types and
  nothing reads. It now defaults, the route sets it from the token, and the service refuses a grant
  that reaches it unattributed: §17.1's accountability is about who disclosed, not who typed.
- **`names_subject=False` on the self-scoped reads.** `/records/timeline`, `/records/search` and the
  revoke route took `require_self()`'s default, which demands the request name a subject matching the
  token. There is no subject to name — the wallet is the caller's own — so every client that did not
  send a redundant `?subject_ref=` got a 422 on a route whose whole content is "mine". Also found by
  the route test.
- **A real PDF, not a `.pdf` filename.** No PDF library is installed, so `afya.records.pdf` writes
  the format: header, numbered objects, a cross-reference table with true byte offsets, trailer. The
  two load-bearing parts have tests — the offsets must land on the objects they name, and a `(` in a
  title ("(review)" in a clinic note) must be escaped or the literal closes early and the file opens
  to garbage. Verified by a real reader: `pdftotext` extracts the text with the parentheses intact.
- **The certificate is a view of the dose log.** One keeping its own copy could disagree with the
  record it certifies, and the disagreement would surface at a border post. The seal is an HMAC over
  the canonical fields and `certificate_seal_holds` is what a clinic runs — present so the seal is a
  mechanism rather than a hex digest printed at the bottom of a page. `issuer` says in words that it
  is a deployment seal and not a Ministry of Health signature, because this deployment holds no such
  key and a document implying one would be forged authority.
- **The backup states its own cipher.** It is consent-gated on `ConsentCategory.cloud_backup`, read
  from the privacy service rather than taken as a request field, and it reports `cipher=none` and
  `user_held_key=False`. §SEC-003 asks for end-to-end encryption with a user-held key;
  `retention.encryption_posture()` asserts both as posture booleans, and this deployment holds no key
  it does not also hold the data with. The §SEC-003 finding stays open and is now stated by the
  service that would have to implement it rather than inherited from a neighbouring boolean.
- **Growth is the WHO standard, exactly.** §REC-003 asks for percentile charts and undernutrition
  alerts, and both need a z-score: the old band compared against a hand-written table at six ages out
  of sixty and called a 12-month boy at 7.7 kg — WHO's own -2 SD, the threshold the alert hangs on —
  `normal`. `z = ((x/M)**L - 1)/(L*S)` over the published LMS parameters, evaluated at the child's own
  age rather than interpolated, and `L≠1` for weight because it is right-skewed. The published SD
  columns are rounded to one decimal: 0.1 kg on a 3.3 kg infant is 3% of body weight and enough to
  move a classification across its boundary, which is why the parameters are used and the printed
  column only checked against them. `sources/who-child-growth-standards/` archives the six WHO PDFs
  and `sources/INDEX.md` records the retrieval URLs, checksums and method.
- **The two WHO height tables overlap at 24 months** — recumbent length and standing height, about
  0.7 cm apart — so concatenating them put two rows and two medians on one month. The standing table
  wins at the boundary, which is the measurement a child of that age gets, and an assertion now
  refuses a joined table with a duplicate month. Found by a test asserting the reference spans 61
  months, not by reading the join.
- **Canaries run the shipped check, not a copy.** The xref canary re-runs `_xref_offsets_that_miss`
  over patched bytes and asserts the patch applied first, so it cannot pass against untouched code —
  a canary against a re-implementation passes while the real check rots.
- **Counts: 13 rows flipped `missing` → `carried`, 139 → 126.** §REC-001 14/14 carried, §REC-002 7/7.
  490 rows, `carried` 348, `missing` 126, `deferred` 16. §REC-003 keeps 2 missing (weight-for-length
  and BMI-for-age wasting, which the section's wording leaves unspecified) and §SEC-003 keeps 3 (the
  end-to-end key, now stated by the service rather than by a boolean). 1071 tests green, pyright clean.

## §MON-003 — three conditions with nothing behind them, and three features with nowhere to sit

Six rows were `missing` and they had six different reasons, which is why the repair is not one
change. Three were conditions `ConditionProfile.conditions` would accept as free text and nothing
would act on: epilepsy, sickle cell disease, chronic kidney disease. Three were features — trend
charts, appointment tracking, lifestyle guidance — and two of those three were missing because
something they depend on was missing.

- **The storage had to exist before the chart could.** `log_peak_flow` and `log_weight` returned a
  verdict and stored nothing, so two of the four readings §MON-003 names had no series at all. A
  chart is a series, so the fix is `MonitoringService._peak_flow`/`_weight` and their accessors, and
  the chart builder reads them where they are rather than copying them into a second store. The
  reading's date arrives as an `at_iso` query parameter, not a model field: the models forbid extras
  and the date is not part of the measurement, it is where the measurement goes on the chart. Omitted,
  the reading is scored and not charted — a chart that used the server's clock would put two readings
  taken a month apart on the same day.
- **A three-point window is identically zero at three points.** `build_chart` shipped with fixed
  `[:3]`/`[-3:]` windows, which is right for every series of six or more and wrong at exactly the
  smallest series it accepts: with three readings the two windows *are* the same three points, so
  `change` is always 0.0 and a peak flow falling 380 → 340 → 300 — a fifth of that person's best, a
  red-zone move — came back `stable`. Found by the end-to-end route test, not by review. The window
  is now the first third against the last third as a partition, and the canary for it is a
  three-point falling series asserted not to be `stable`.
- **CKD-EPI 2021, and the interval is part of the definition.** `egfr = 142 × min(Scr/κ,1)^α ×
  max(Scr/κ,1)^-1.200 × 0.9938^age × 1.012 (female)`, κ 0.7/0.9, α −0.241/−0.302, staged by KDIGO
  G1–G5 with G3 split at 45 and albuminuria A1–A3. KDIGO requires the abnormality "present for at
  least three months", so `assess_kidney` reports the stage and *separately* whether the history
  sustains it: one low eGFR is an acute finding and the person is told to repeat it, not told they
  have kidney disease. An undated reading is never called sustained — the route used to stamp one
  from the clock, which compared a prior reading of unknown age against today and reported the
  result as a duration.
- **ILAE's two time points, because one cannot serve.** t1 = 5 minutes is when treatment begins and
  t2 = 30 is when long-term harm is likely, so a single threshold either calls a treatable seizure an
  emergency or a harmful one a wait. Three durations produce three different instructions, and a
  cluster escalates at any duration because the definition treats it as continuous.
- **Where a source states no threshold, none is carried.** The archived sources give sickle cell
  disease's danger signs but no severity score, so the escalation keys on the signs themselves rather
  than on an invented score. They recommend daily penicillin and print no milligram dose, so
  `PROPHYLAXIS` says a dose is not stated instead of stating one. `SICKLE_FEVER_C = 38.0` is the one
  number here that is an assumption rather than a citation, and it is named as one in the source
  index. A dose invented to fill a table is worse than a table with a gap: the gap is visible.
- **`overdue` and `remind` are two answers.** An appointment that passed needs "you missed this" and
  one coming up needs "this is in a week"; one boolean produces the wrong sentence for one of the
  two. The due date is computed from the condition's interval — and for kidney disease from the
  *stage's*, which is the thing that changes the answer — rather than stored, because a stored date
  goes stale the moment the stage changes.
- **Lifestyle is keyed on the condition, not the age.** `nutrition_guidance` bands by age, which is
  right for a well-child visit and wrong here: what a person with hypertension eats and what a person
  with sickle cell disease must avoid are different lists at the same age.
- **A secondary copy disagreed with the primary and the primary won.** Wikipedia's CKD-EPI article
  prints the SCr-above-κ exponent as −1.209 and the female multiplier as 143; the archived NKF page
  states −1.200 and 142. The difference is under 1% of eGFR, below the assay's own variability, but a
  constant copied from the wrong source is a constant nobody can check, so the disagreement is
  recorded in `sources/INDEX.md` rather than averaged.
- **Counts: 6 rows flipped `missing` → `carried`, 126 → 120.** §MON-003 is now 16/16 carried. 490
  rows, `carried` 354, `missing` 120, `deferred` 16. 1115 tests green, pyright clean.

## §AI-003 — outbreak early warning had a scorer and no collector

`WarningSignal.signal` already listed §11.7's six signals and `assess_warning` already scored them,
refusing a caller-supplied z-score. Nothing produced them: `SurveillanceService.weekly_signal` read a
count the *caller* typed into `CountySignal`, and the app's six real surfaces — fever triage, cough
detection, the facility finder, medicine lookup, the well-being check-in, proximity encounters — each
recorded their event and none of them counted it into a locality. A detection layer nothing feeds is
invisible in review, because the scorer's own 32 tests pass.

**The ledger, not a tally.** `SignalEvent` rows are appended by the routes and counted at read time
by ISO week. A count incremented at each route loses the period it happened in, and a baseline is a
distribution over periods, so the window has to be explicit at the point it is read. `_iso_week`
takes the year from `isocalendar()` and not from the date string: 2025-12-29 is week 1 of ISO year
**2026**, and a collector that read the year off the timestamp would file those events under a period
eleven months earlier, where they would never be counted again.

**One door.** The six surfaces call `_record_signal`, which refuses an event with no county and reads
the clock in one place. Six routes stamping their own timestamp is six chances to disagree about when
"now" is, and a signal with no locality is a national count against a county baseline — a number that
cannot mean anything.

**The refusals are the finding.** A signal below §19.3's minimum cell size is withheld *by name and
with its count*, because a signal dropped silently and a signal that did not occur are different
facts. The same distinction runs through the baseline: an all-zero history means this county has
never produced the signal, and a flat non-zero one means a rise cannot be told from its own noise.
Both were reported as "no variation", which described a first-ever signal as four weeks of quiet
observation. They now say different things.

**Three gates caught three omissions in this unit, all of them real.**

- `test_every_unguarded_write_is_named_and_justified` flagged `POST /ai/signals`. My docstring said
  the route was deliberately unscoped because the event carries no subject — true, and beside the
  point: an unguarded ingest lets anyone inflate a county's baseline until an epidemiologist is
  paged about nothing. Guarded on `county_aggregate`; the app's own surfaces emit in-process from
  routes that already carry their own guards, so nothing lost.
- `test_a_carried_bullet_names_code_that_imports` refused `afya.service:triage_preliminary` and four
  like it. The route handlers are closures inside `create_app`, so no reference to one can resolve —
  and the correct answer was not to weaken the audit but to give the emission one module-level door,
  which is the better shape anyway.
- `test_every_subject_carrying_route_is_guarded` read `SignalEvent.ref` as a person. The field held a
  drug name or a PET prefix, never a subject, so it is now `event_ref`: a gate that walks routes
  reads names, not intent, and `ref` already means "the subject" everywhere else in this app.

**The mobile catalogue gained two actions, and the second is the one that matters.** `signal_scan`
is the county's week; `signal_report` is marked operator-only for the same reason the route is
guarded. The six option values it offers (`fever_triage`, …) are the strings the API accepts — the
same convention as the `under_5` age band and the `low` risk level already in that file — and no spec
feature code appears in any title, label, placeholder or description.

**Counts: 6 rows flipped `missing` → `carried`, 120 → 114.** §AI-003 is now 6/6 carried. 490 rows,
`carried` 360, `missing` 114, `deferred` 16. 1152 tests green, pyright clean.

---

## §REC-005 — Mental health self-check and support

Five of six bullets were `missing`. The carried one was the counselling-line directory; what was
there for the rest was **WHO-5**, which is not a smaller PHQ-9 — five positional 0–5 scores with no
item text, `raw = sum × 4`, and different cut-points. `WHO5.scores[2]` is a number nobody can be
asked, and a screening whose items are never shown cannot be localised at all.

**The instruments are transcribed, not summarised.** `afya.mental.instruments` holds the PHQ-9 and
GAD-7 item banks, the four-point scale and the cut-points, from the archived sources:
`sources/phq9-gad7/PHQ-9_English.pdf`, `GAD-7_English.pdf`, `PHQ-9_Kiswahili.pdf` and
`instructions.pdf`. The cut-points are the manual's Table 4 (p. 6) for PHQ-9 and its pp. 6–7
statement for GAD-7, including that further evaluation is recommended at **10** — which is *not* one
of the severity bands, so the two are separate fields rather than one band doing double duty.

**A boundary test caught an off-by-one I had written.** The band table first read
`((5, 'none_minimal'), (10, 'mild'), …)`, i.e. the cut-points themselves as ceilings. That scores a
5 as `none_minimal` and a 10 as `mild`, and it is exactly what the manual's "scores of 5, 10, 15 and
20 represent cutpoints for mild, moderate, moderately severe and severe" invites if you read the
numbers as the top of each band instead of the start. Table 4 prints them as intervals — 0–4, 5–9,
10–14, 15–19, 20–27 — so the ceilings are 4/9/14/19/27. The canary for this gate lowers the ceiling
back and the boundary assertions fail, which is the only reason to trust them.

**Item 9 outranks the band.** PHQ-9's ninth item asks about being better off dead or hurting
yourself. A total of 1 is `none_minimal`, whose advice is "nothing here suggests you need
treatment" — and with item 9 positive that is a person at risk being waved through by their own
total. So the self-harm item is read on its own *and* summed, and when it is positive it overrides
every band. The advice names what was endorsed without quoting the instrument back at the person:
"better off dead" is a clinical phrasing written to be answerable on a form, and repeating it
verbatim to someone who just ticked the box is blunter than saying the same thing plainly.

**Localisation: PHQ-9 yes, GAD-7 no — and the gap is the publisher's.** A Kiswahili PHQ-9 exists
("PHQ9_Swahili for Africa", retrieved from the Wayback Machine because the live path 404s) and is
served with its own translated items, options and timeframe. There is **no** Kiswahili GAD-7: the
publisher's language listing runs Afrikaans to Urdu across 41 languages and Swahili is not among
them. So `GET /mental/screen` with `lang: sw` and `instrument: gad7` serves the English items and
sets `served_in_english_instead`, and the advice says so. The failure that design refuses is the one
that looks best on a screenshot: English items under a `sw` label, returning a score from a person
who could not read the questions. The manual's own caveat is recorded too — the translations are
"linguistically valid", but "unlike the English versions … few … have been psychometrically
validated", so §REC-005's word *validated* is discharged for the English forms and *localised* for
the Kiswahili PHQ-9, and neither claim is stretched over the other.

**Coping and psychoeducation come from WHO PFA, in both languages.** `sources/who-pfa/` holds
*Psychological first aid: guide for field workers* (WHO/War Trauma Foundation/World Vision, 2011) in
English and in the publisher's own Kiswahili edition, so the Kiswahili guidance is a published text
rather than a rendering of the English one. The source's three action principles — look, listen,
link, rendered as *Tazama, Sikiliza, Unganisha* — are the spine of the six strategies. More
importantly the guide states what PFA **is not**: "not professional counselling", "not
'psychological debriefing'", "not about pressuring people to tell you their feelings". A wellness
feature's commonest error is precisely the opposite — pushing a distressed person into an unguided
debrief — so the content is tested against the source's own line rather than trusted to have
respected it, and the canary plants a debrief-promoting sentence to watch that test fail.

**The three outbreak-specific conditions are named conditions, not bands.** Isolation distress, grief
and healthcare worker burnout each carry signs to recognise and a route, because "your score is 14"
does not tell someone in quarantine that what they are feeling has a name. Grief is explicitly *not*
medicalised — the source lists crying, sadness and grief among expected reactions, and the text says
so — and the worker content points staff at the same lines they send others to.

**Referral routes somebody, and admits what it cannot reach.** The predecessor was a prose sentence
in `assess`: "consider 719 for referral". Nothing was created and nobody was routed.
`MentalHealthService.refer` builds a record that names the services, keeps the person's own reason,
and lists by name every line whose number is unverified — all three in `COUNSELLING_LINES` are
marked `verified: 'False'`, so all three appear in `unreachable`. A referral to a number nobody
checked is worse than no referral, because the person stops looking. `ReferralRequest` is separate
from `ServiceReferral` so a client cannot supply the id, the service list or the unreachable list:
those are the app's statements about what it can reach.

**The mood log is not the instrument scale.** `MoodEntry.score` is 0–10 and PHQ-9 is 0–27; averaging
a self-rating with a scored instrument produces a number with neither a person's trend nor a
validated instrument's cut-points, so they are stored and served apart. `mood_trend` returns a
direction or the named `too_few`, because two readings with the same score are two readings and not
a steady mood.

**Routes, all self-scoped where a subject is involved:** `POST /mental/screen`, `GET
/mental/instruments`, `POST /mental/mood`, `GET /mental/mood/trend`, `GET /mental/coping`, `GET
/mental/outbreak-support/{condition}`, `POST /mental/referral`. A positive self-harm item is
deliberately **not** turned into a §AI-003 signal: that ledger is counts by county, and nothing in it
may point at a person.

**Counts: 5 rows flipped `missing` → `carried`, 114 → 109.** §REC-005 is now 6/6 carried. 490 rows,
`carried` 365, `missing` 109, `deferred` 16. 1210 tests green, pyright clean.

## §MON-009 — the 21-day diary: reminders, consent, household, support, and the officer

The section's five missing bullets shared one shape: a field existed and nothing read it. `members`
was a list nobody populated, `household_member` a name nobody looked at, `monitoring_officer` a
free-text string, `location_logged` a boolean nothing set, and the reminders were a method that
returned missing day numbers with nothing to escalate on. Filling them meant making each field
load-bearing rather than adding a parallel surface beside it.

**The reminders are state, not a queue.** `ReminderSlot` names the two slots a day has — morning and
evening — and `MonitoringService.reminders` reports which are in, which are missing, and the §11.3
escalation rung. The rung is computed from the *window*, not from today: a person who has missed four
days needs a firmer message than one who has missed this morning, and a surface that only knows about
today cannot tell them apart. `_day_complete` counts a **half-kept** day as missed, which is the
canary this bullet turns on — a ladder that counts only days with *no* entry sees four logged
mornings as a perfect record and never fires for the person who forgets every evening, and that is
the commonest way a 21-day diary is lost. `_slots_logged` is the one place "complete" is decided;
`reminders` and `_day_complete` both read it, so the two cannot drift.

**Consent is a recorded decision, not a client boolean.** `MonitoringDay.location_logged` was a flag
nothing set, and making it settable is not consent — it is a client asserting consent on the
person's behalf. `HouseholdMonitor` now carries `location_consent` and `location_consent_at_iso`, and
`record_location_consent` writes both directions: consent that cannot be withdrawn is not consent.
`log_day` refuses an entry claiming a location without it, following the precedent in
`location/service.py` where `assert history.consent_granted` gates every point.

**A household member has their own series, inside the same window.** Members are added to the
household and a day filed for one is read back through `member_diary`. The other half matters more:
`diary`, `_slots_logged` and `adherence_reminder_days` all *exclude* member entries, because the
predecessor's defect was the reverse — it accepted `household_member` and read nothing, so a member's
fever sat in the contact's series and the contact's adherence counted it. A household of five could
otherwise keep one person's diary complete for them. The escalation message now names whose reading
it is ("for M1" / "for you"), because one household shares one diary and a fever recorded without
attribution is a message the contact has to decode at the moment they are least able to.

**Support is attached to the verdict, not filed elsewhere.** `support_resources` returns §REC-005's
counselling lines read from the one place they live — a second copy of the numbers is a second set to
keep current, and the copy that goes stale is the one nobody is looking at — plus the coping and
outbreak-support routes. It travels on **every** verdict including the clear ones, because the day
someone most needs it is not always a flagged day; a flagged verdict leads with a note saying why the
lines are on the screen.

**The officer line is dialable or it says it is not.** `monitoring_officer_number` travels with the
name, and `monitoring_officer_line` serves a `tel:` target only when there is a number behind it. A
name with no number is *named* and falls back to 719 rather than being served as a dead button —
which is exactly the predecessor's defect in this bullet, a free-text name with nothing to dial. The
name-without-number case is accepted at enrolment rather than refused: the officer roster may not
have synced, and withholding the diary over a contact detail is the wrong trade.

**Routes, all self-scoped:** `GET /monitoring/contact/{subject_ref}/reminders/{day}`, `POST
.../location-consent`, `POST .../members`, `DELETE .../members/{member_ref}`, `GET
.../members/{member_ref}/diary`, `GET .../officer`; `POST /monitoring/contact/enrol` gained
`officer_number`.

**One gate needed a scoped exemption.** `test_self_scope.py` reads `member_ref` as a wallet member
and demanded the ownership guard on the three household routes — but a household member is a handle
inside the caller's *own* contact diary, not a minor in their wallet, so `require_self` is the right
guard and `require_self_or_guardian` would be wrong (it would let a guardian into somebody else's
diary). The routes are exempted from the family-member rule by an explicit named set, and a new test
asserts each one still carries `require_self` — an exemption list that drifts into an
unguarded-route list is the one way that gate can fail open.

**Counts: 5 rows flipped `missing` → `carried`, 109 → 104.** §MON-009 is now 9/9 carried. 490 rows,
`carried` 370, `missing` 104, `deferred` 16.

## §INF-004 — the myth-busting library: one rumour, four things done to it

§INF-004 is four lines long. It prints a Format, "Rumour: [claim]. Fact: [correction]. Source:
[authority].", and four Features over it — Search, Browse by category, "Ask about a rumour",
Shareable as a card — and none of the five had a carrier. The corpus held a rumour as one `body`
string: the claim, the correction and the authority were prose in that order, findable by accident,
weightable by nobody, and forwardable as whatever a client chose to compose. Five audit rows said so.

**The three parts are fields, and they travel together.** `ContentItem` gained `claim` and `source`,
and two `model_post_init` assertions make the Format structural rather than a convention the seed
happens to follow: a claim with no source is refused (a correction nobody can weigh), a source with
no claim is refused (an authority correcting nothing), and either on a row that is not tagged
`mythbusting` is refused — a first-aid card has no rumour to refute. The row that states a rumour as
its own correction is the shape the old corpus had, and `Myth` refuses it outright.

**One table, two consumers.** The correction existed in two unlinked places: the library rows, and
`community.CORRECTION_LIBRARY` holding fact-plus-authority per §6.4 topic in en and sw. A rumour
answered one way in the library and another way by the response protocol is the same fact stated
twice, and the two drift the moment either is edited. `afya/info/myths.py` is now the one table —
ten rows, five topics in both languages — and both consumers derive from it: `content_seed.myth_rows`
builds the library items, `CORRECTION_LIBRARY = correction_library()` builds the protocol's. The
correction §6.4 publishes and the correction the library serves are the same string by construction.
The module imports nothing from `afya` at all, which is what keeps the `community → info` direction
intact; the six §6.4 categories moved here from `community/protocol.py` and are re-exported.

**Search reaches the claim, and the test that said so was wrong first.** `InfoService.search` AND-s
every term over the lowercased claim, title and body, and `/info/library?q=` serves it. The first
version of the gate searched "salt water" and passed with the claim dropped from the haystack
entirely — the *title* carries those words too, so the assertion restated what the title already
proved. The canary caught it: the test now queries `warm`, which lives in `myth-salt-water`'s claim
and nowhere else in that row, and asserts that premise rather than assuming it.

**Browse by category counts what it serves.** `facets()` reads through `library()`, not off
`_content`, so a category is offered only when something published is behind it. Pointed at the
store instead it reports `first-aid 33` against 11 served rows — a browse screen opening onto two
thirds empty, which is the defect the count exists to prevent. Labels are human (`Rumours and
corrections`), because a browse screen showing `mythbusting` is the feature-code failure one level
down.

**Asking is not flagging.** `CommunityService.answer_claim` classifies a claim against a per-language
keyword table and returns the drafted correction with its authority; `POST /info/myths/ask` serves it
unauthenticated, because §6.2.7's whole point is that the correction reaches the person who has the
rumour. It is deliberately not `flag_misinfo`, which takes a rumour someone *else* spread and returns
PHEOC a cluster — a person asking whether something is true is not reporting anything, and answering
them with a surveillance row answers a question they did not ask. An unmatched claim is answered
"under verification" with `recognised=false` rather than attached to the nearest rumour: a confident
correction to the wrong question is worse than §6.2.8's honest one. The fallback is drafted in both
languages, so a Swahili speaker gets Swahili and `answered_in` reports the language actually served
rather than the one asked for.

**The card is the Format.** `ContentItem.share_card` and `share_url` are computed fields, rendered
server-side for §3.3 principle 10's reason: §5.4 puts this answer on WhatsApp, USSD and SMS, and only
one of those can compose a forwardable message. A myth renders the section's own three lines, with
the rumour named before the correction — a card stating the correction alone reads as an assertion
out of nowhere, and the recipient cannot tell what it answers.

**The computed fields broke the API, and that is the finding worth keeping.** Adding `share_card` and
`share_url` made `ContentItem` refuse its own `model_dump()`: `extra='forbid'` counts a derived field
as an extra, so the API's output became a 422 against the API's input. Nothing in this section failed.
It surfaced two files away, as two localisation tests failing on `assert 422 == 200` because they seed
a translated row by round-tripping a library item through `POST /info/content` — and the same latent
break was live in `TriageInput.exposure_history` and `DiaryEntry.worst_red_flag`, both request bodies.
`afya/derived.py` is the fix: a `mode='before'` validator drops exactly the names the model computes,
so a round trip closes while an invented key is still refused. `test_request_bodies_round_trip.py`
walks every request body the published schema names, so a model that gains a computed field is caught
at the model rather than at whichever route happens to post it.

**Four actions, no codes.** §INF-004 came off `ON_DEVICE` — "myth-busting items are in the health
library corpus" was true while the corpus was all there was — and gained `search_library`,
`library_categories`, `myth_library` and `ask_about_a_rumour`, each with friendly copy. Catalogue
coverage 59 → 63 of 79 available features.

**Counts: 5 rows flipped `missing` → `carried`, 109 → 99.** §INF-004 is now 5/5 carried. 490 rows,
`carried` 375, `missing` 99, `deferred` 16.

## §MED-001 — the medicine verifier: four outcomes, not two

**A boolean is a set with the members thrown away.** §MED-001 prints its result as four named
outcomes — "Registered / Not found / Expired registration / Recalled" — and `VerifyResult` carried
`genuine: bool` plus free text. A recalled medicine and a medicine that was never registered both
read `False`, and the two call for opposite actions: take it back to where you bought it, versus
this product does not exist and do not take it at all. `RegistrationStatus` is the section's four,
and `genuine` survives as a `@computed_field` — it is the question the person actually asked, and
collapsing *to* it is safe in a way collapsing *from* it never was, because exactly one member is a
yes. This is the §13.1 lossy-enum defect one level up: a set the spec names, collapsed where a
client can no longer tell the members apart.

**The fifth member is the one that is not in the section and matters most.** `unverified` is not a
fifth verdict, it is the absence of one. A registry that answered nothing has not said the medicine
is bad — only that nobody checked — and rendering that as `not_found` tells a person to throw away
medicine that was fine. That is this feature's own worst failure mode, pointing the other way from
the one it exists to prevent, and it is the reason the offline stub answers `unverified` rather
than `not_found`: it holds no registry, so "not in the registry" is a claim it cannot make.
`genuine` is False either way, so the fail-closed behaviour is unchanged; what changed is that the
client can now say *why*.

**The Display line cost no new integration.** The five fields the section names come out of the
same `/verify` answer — the product row and any recall rows it carries — assembled by
`display_from`. Every field is optional because a product the registry does not hold has none of
them, and a filled-in name for a `not_found` batch would be an invented medicine. Recall rows are
filtered to the batch the person scanned: a registry that returns every recall it holds must not
put another batch's withdrawal on this person's screen, which is the kind of false alarm that
teaches people to ignore the real one. A recall outranks a registration, because a product can be
registered, unexpired and still withdrawn.

**One audit row was stale and three were real.** "Report a suspicious medicine" claimed no report
route to PPB existed. It does — `POST /medicine/suspicious`, self-scoped, with
`PPBClient.report_suspicious` behind it — and the row had been written by a non-recursive walk of
`app.routes`, which returns `[]` because every `include_router` nests its paths on
`original_router.routes`. A gate that concludes a route is absent from a walk that cannot see it is
the same shape as the checks that went on reporting success after a nested move. What that route
*did* have wrong is now fixed: it took a bare `dict` forwarded verbatim to the regulator's intake,
so a client that sent `batch` instead of `batch_number` filed a report naming nothing and received
a case reference for it. `SuspiciousReport` is the typed body, with `extra='forbid'` and at least
one of gtin/batch asserted.

**The packaging photo is deferred, and the reason is the section's own Privacy clause.** "Scans are
not stored or transmitted unless the user reports a suspicious product" — and there is no OCR in
this tree, so a server handed the image could only return a reading the client already had by the
time it holds the batch number. The one case where a photo does travel is a report, and that path
carries `photo_sha256` rather than the image, because the evidence pipeline is what hashes, dedupes
and size-caps every other image in the app.

**Counts: 4 rows left `missing` — 3 to `carried`, 1 to `deferred` — 99 → 95.** §MED-001 is 6/6
accounted for: four `carried`, two `deferred` (the barcode read and the packaging photo, both
device-side). 490 rows, `carried` 378, `missing` 95, `deferred` 17.

## §MED-004 — the stock map answers two questions, and only one of them had an answer

**`stock_for` is keyed on (drug, facility) and needs both.** That answers "is this drug at this
place". The section's own example is *"available at [pharmacy], 2 hours ago"* — a person holding a
prescription, wanting a list of places. Those are different questions, and the second one could not
be asked at all. `search_stock` is it: one row per (drug, place) rather than one per report, because
ten reports about the same pair are one answer with `reports=10` and a raw feed of ten identical
rows tells a reader nothing the newest one did not. `StockAvailability` is what makes the section's
sentence renderable — `age_hours` as a duration a screen prints without diffing against its own
clock, `reported_at_iso` beside it so the number stays auditable. A report from a client that
predates `at_iso` carries no age rather than an age measured from now; the second would make the
oldest possible data read as the freshest.

**"Prioritised" is an ordering, and an ordering nothing applies is a comment.** `ESSENTIAL_MEDICINES`
is the section's eight, each with the aliases a crowd actually types — "ARVs", "dolutegravir" and
"TLD" are one medicine. `search_stock` sorts essential first and freshness second, so the vitamin
does not outrank the insulin by being newer. The match is on whole words, not substrings: "insulin"
is inside "insulinoma" and "act" inside "contact", and a substring test would prioritise a tumour
and an optician.

**The restock alert fires on the transition, not the state.** A report that a medicine is in stock
is not news unless the last thing anyone said was that it had run out. "Previous" is read by the
time the report was *made*, not the order it arrived: a report queued offline and flushed later is
older than one filed after it, and arrival order would make the slowest-travelling report the
newest thing anyone knows — in the alert path and in the availability a person reads.

**The Anti-gaming clause names three controls and each is a different failure mode.**

- *"Require location proximity to report."* The report carries a geohash rather than a coordinate,
  per §LOC-003, and the cell is decoded to a centre and measured against the facility the report
  names. A cell too coarse to be a position — two characters is a county — is refused rather than
  rounded. The refusal is a 422 on the served path, not a silent drop: a report that vanished looks
  like a network fault to the person who filed it, and they file it again from the same place.
- *"Weight reports by reporter reliability."* Derived server-side from the reporter's own history
  and never accepted from the client, because a client that sets its own weight has none. Starts at
  5: an unknown reporter is not a distrusted one, and starting at the floor would silence every new
  person. A report a *later* report from someone else contradicts loses a point; one that stands
  gains one; the newest report moves nothing, because silence is not agreement and counting it as
  confirmation would reward whoever reported last regardless of what they said. Clamped to 1–10.

  The field check is not the whole control. `reporter_weight` is absent from the request, but
  `reported_by` is not — and the weight is computed *from* `reported_by`. On a route that is
  deliberately ungated, that makes the identity behind the control whatever the client typed: a
  reporter whose record has been contradicted files the next report under a fresh name and starts
  at the middle again. The route now takes the token's subject when the caller presents one and
  falls back to the body's name only when it does not, so a queued offline batch still lands under
  the name it was filed with while a live report cannot choose who it is.
- *"Show report age clearly."* `age_hours` and `reported_at_iso` on every availability.

**A report with no location is accepted, and that is the control's own limit.** `within_proximity`
answers `False` for a report it cannot place — as a predicate on "is this report from here", an
unplaceable report has not shown that it is, and `True` would assert something it did not check.
The route then *skips* the check rather than reading `False` as a refusal, because §13.2's `gps`
fallback exists so a phone without a fix can still report and refusing it is the accessibility
failure §ACC-001 is about. Both directions fail as working code, which is why both are pinned.

**Six catalogue actions, and the sixth was already there.** `report_suspicious_medicine` sits under
MED-004 in `FEATURE_OF` and is §MED-001's report path — the id has been in the catalogue since
before this unit. The gate asserts each action's `(method, path)` against a recursive walk of
`app.routes`, so an action pointing at a route nobody serves fails rather than shipping as a screen
that 404s.

**Counts: 4 rows left `missing` — 4 to `carried` — 95 → 91.** §MED-004 is 9/9 accounted for: six
Features and three Anti-gaming controls, all `carried`. The three Anti-gaming rows are new rows
rather than reclassified ones: the audit module's own rule is that a claim label whose body is a
list is miscategorised, and `Anti-gaming` named three controls, so it was a content label wearing a
claim label's name and moved to `_LABELS`. 493 rows, `carried` 385, `missing` 91, `deferred` 17.

## §MED-004, follow-up — the catalogue could point at a live route and still be unfillable

**A form that cannot fill its own route.** `test_every_action_path_exists_in_app` asks whether the
route exists. Nothing asked whether the catalogue's field list covers what that route's *body model*
requires, so an action could name a live route and still be impossible to complete. Six were, and
each failed differently:

- `fairness_audit` and `book_appointment` carried the *verdict* as a required input — `passed`/`action`
  on `FairnessAudit`, `queue_position` on `Booking`. Both are the answer the server computes, so the
  model was asking the caller to hand in its own conclusion. Split into `FairnessAuditRequest`/
  `FairnessAudit` and `BookingRequest`/`Booking`: the request is what a caller knows, the result is
  what comes back. A client that could set its own `queue_position` could book itself to the front.
- `wellbeing_check` offered `s1..s5` where `WHO5` holds `scores: list[int]` of exactly five; no
  client could turn five scalars into the list, so every submission was refused however it was
  filled. The catalogue already has the shape for a multi-value answer — `mood_screen`'s `answers`.
- `log_location` offered one free-text `point` where `LocationPoint` wants `geohash` and `at_iso`, so
  a client could say neither where nor when. §LOC-003 keeps raw coordinates off this boundary, which
  is why the field is the geohash the phone already computed.
- `emergency_card` offered the singular `emergency_contact` as one string where `EmergencyCard`
  holds named contacts. A bare number tells a clinician looking at an unconscious patient neither
  who to ring nor what they are to them, so the model is right and the form was wrong: a
  `model_validator(mode='before')` now accepts `"Jane:0722000111"` and the plural list alike, and
  leaves `relationship` absent rather than guessing a third fact from a two-part string.
- `water_advisory` offered `ecoli` where the model requires `ecoli_detected` — a rename.

**Three more classes were found while fixing those, each proved against the live ASGI app.**

- **A path placeholder no field names is a route neither client can reach.** Android's
  `BackendClient.perform` substitutes `{f.name}` strictly by field name; iOS's `Endpoints.buildRequest`
  matches by name and falls back to position. Eighteen actions had a field called `id`/`ref` under a
  `{facility_id}`/`{member_ref}` placeholder — `/facilities/{facility_id}/ed-status` returned **500**
  with the literal braces, the records actions **403**. The gate now drives the same substitution the
  clients use, so the defect is caught where it happens rather than read for.
- **A required field whose placeholder read "generated for you" is a form nobody can complete.**
  Twelve actions carried a reference the *server* mints — `entry_id`, `sos_id`, `doc_id`, `alert_id`
  and eight more — and the client hides an undrawn field, so the submission went without it and the
  server answered 422 naming a field the person had no control for. Each model now defaults it with
  `default_factory`, the repo's established pattern for a server-minted reference.
- **A free-text field carrying `options` is a picker that yields a refused value.** Four carried
  options while typed `text`: a client drawing a picker sent `sex: 'Female'` or `metric: 'BP'` and
  got a 422. Retyped `select`.

**`server_assigned` is a separate flag from `client_supplied`, and the reason is in the clients.**
Both gate their subject injection on "this action has a client-supplied field", so broadening that
flag to cover a server-minted reference would have injected a bogus `subject_ref` into requests that
have no subject. The two are undrawn for different reasons — one because the client already knows the
value, one because nobody does until the request arrives — and only the first is an identity. Both
shipped clients now key on the field name, and both skip drawing either flag.

**The gate I wrote for this was wrong first, and the wrongness is the same shape as the defect.**
It asserted `undrawn & required == {}`, which flagged 43 actions — every one of them `subject_ref`,
which is *legitimately* hidden from the form and *required* by the model because the client injects
it from its own token. That is what `client_supplied` means. The predicate was too wide by exactly
the flag it conflated. Only `server_assigned` must not be required, and must not fill a path segment.
Six canaries were run against the corrected gates — the substitution made a no-op, a field renamed
away from its placeholder, a required field marked server-assigned, a server-assigned field asked to
fill a path, a mark whose model default was removed, and the flag check blinded — and all six fired.

## §MED-003 — a calculator that asked the caller for the number it exists to look up

**`dose` took `mg_per_kg` from the client.** So the route computed `weight_kg * mg_per_kg` and the
weight-based lookup — the whole of a dosage calculator — happened on the caller's side. A parent who
already knew the mg/kg figure for their child's medicine did not need the app; a parent who did not
could not use it. The answer was a multiplication wearing a clinical feature's name.

**The section asks for a range, and the route returned one number.** "Get dose range" is the
bullet, and `total_mg` was a single figure derived from a constant the caller chose. Paracetamol is
10–15 mg/kg, so the honest answer is a spread: `mg_low`/`mg_high` are the source's own, and a
midpoint would be a number no guideline states that a prescriber has no way to trace.

**`afya.medicine.formulary` is the table, and every figure in it comes from the WHO Pocket Book of
Hospital Care for Children, 2nd ed.** The five formulations the section names are the five the
module holds — paracetamol 10–15 mg/kg up to six times a day (Appendix 2, p. 367), amoxicillin
25 mg/kg generally and 40 mg/kg for pneumonia (p. 357), ORS 50–100 ml per loose stool under two years
and 100–200 ml from two (p. 136) plus about 5 ml/kg per hour alongside IV fluids (p. 135), zinc 10 mg
a day under six months and 20 mg from six (p. 134), artemether–lumefantrine by weight band (p. 164).
The source is archived at `sources/who-pocket-book/` with both checksums and the page references in
`sources/INDEX.md`.

**Three things the source does *not* say, and the code carries none of them.**

- **No maximum for paracetamol, amoxicillin, ORS or zinc.** The Pocket Book gives paracetamol a
  *frequency* ceiling and no milligram total, and gives the other three no maximum at all.
  `max_mg_per_dose` is `None` for all four, and the result says so in words — an empty maximum
  column reads as "no limit", and the source's silence is neither zero nor infinity. A number
  invented to fill that column is a limit a prescriber would trust that no guideline set.
- **No mg/kg figure for artemether–lumefantrine.** It is stated as whole tablets of a fixed-strength
  combined tablet for a weight band, so that is what the calculator returns. Deriving a milligram
  dose from a tablet count would be a precision the formulation does not have.
- **No dose by age for anything but zinc.** Age is a threshold in the source, not a dose axis, so
  `age_months` is optional in the model and the zinc path refuses without it rather than picking a
  band — defaulting would dose a six-month-old at the toddler amount or the reverse.

**A syrup is measured and a tablet is counted.** `DoseLine` carries the range in the form's own
unit, because a person holding a 5 ml spoon should not have to divide a milligram figure by the
strength printed on the bottle — that division is the calculator's whole job.

**The bug this unit's own first test run found.** pydantic v2 copies a list on validation, so
`warns.append(...)` on the *local* list after `DoseResult(...)` wrote to a list the model no longer
held: six warnings vanished silently, and a zinc lookup with no age returned an empty result with no
explanation at all. An AST pass over `src/` for the shape — a local list passed into a constructor
and mutated afterwards — found no other instance.

**The gate I wrote first failed open.** Every figure check was wrapped in `if SOURCE.exists():`,
which means losing the archive would silently stop every check in the file — the one failure it
exists to prevent. The guard is gone: presence and the recorded checksum are assertions of their own,
and the canary that proves the rest are live points `SOURCE` at a path that does not exist and
requires the suite to fail. Seven canaries were run — a figure drifting, an invented maximum, a moved
age threshold, a lost archive against both the figure check and the integrity gate, the whole-word
drug match becoming a substring test, and a weight band drifting — and all seven fired.

**Counts: 4 rows left `missing` — 4 to `carried` — 91 → 87.** §MED-003 is 5/5 accounted for.
493 rows, `carried` 389, `missing` 87, `deferred` 17.

## §EMG-001 — the SOS button that named three things it did not do

**Five Features, one and a half carried.** The section prints a large SOS button, a fan-out to up
to three emergency contacts, an ambulance dispatch where integrated, a preset message over SMS with
no data, a countdown with cancel, an optional medical profile, and an optional auto-dial. `SOSEvent`
held a position and a severity. `sos` notified the 719 hotline and returned
`['call-719', 'geofence-perimeter', 'sms-contacts']` — three strings naming three things nothing in
the tree did. The contacts were not on the event, the preset message nobody composed *was* the
string `sms-contacts`, the ambulance leg did not exist, and the countdown was called "client state"
and left there.

**The device owns the timer; the server owns the window.** A server-held countdown would contradict
§ACC-004's no-background-polling rule and §EMG-001's own `Offline: Yes, via SMS` note — a client
with no data cannot be told that a second has passed. So `arm` returns the deadline and nothing
else, `cancel` is refused past it, and `fire` is idempotent: a queued alert replayed over a link
that dropped mid-request returns the first dispatch instead of texting the same three people twice.
The duration is a deployment parameter (`DEFAULT_COUNTDOWN_S = 10`) that travels on the alert,
because the section prints no figure and a constant invented here would read as one the spec states.

**Three legs, because they fail separately.** `SOSDispatch` splits the section's "up to three
emergency contacts" into `contacts_notified` and `contacts_unreachable`. A receipt that says "3
contacts" for two deliveries is the failure the split exists to prevent: a person who pressed SOS
needs to know their sister's number was a landline. One dead leg does not silence the others — an
`Exploding` gateway still lets the hotline leg run.

**Reused rather than duplicated.** The SMS leg goes through §5.3's `ChannelService`, so zero-rating
is resolved at the moment of sending, by the same code every other message's cost runs through; a
second SMS port would be a second place that decides what an emergency message costs, and the wrong
one would be the quiet one. The ambulance leg is `FacilityAmbulancePort` wrapped around §FND-001's
finder, because the facilities that have an ambulance *are* the facility registry — `Facility.ambulances`
is §FND-002's own field, and a second list of bases would be a second answer to "where is the
nearest one". The "where integrated" half of the bullet is that class existing at all: no registry,
no port, and the dispatch reports the leg absent rather than inventing one.

**GSM7 is load-bearing, so the message is GSM7.** §5.3's zero-rating and `segment_sms` both turn on
it, and this is the one message in the product that must not fail to send. The preset message
carries where, a maps link, the first four symptoms and "Call 719." — and names nobody, because
`SOSEvent` holds the *recipients'* contacts and nothing about the sender, so "Peter needs help"
would be a guess that tells his family the wrong person was hurt.

**Two defects the gates found in the code, and one in the gates.**

- **A landline counted as delivered.** `_sms_dialable('0202712345')` returned `'+254202712345'`,
  because `^0(\d{9})$` matched Nairobi landlines — so a contact with a landline was reported
  *reached* by a message no gateway could deliver. Kenya's mobile ranges are `07xx` and `01xx`; the
  regex is now a prefix test, `^\+254[17]\d{8}$` / `^0([17]\d{8})$`.
- **`sos_id` collided within a millisecond.** `uuid7str().replace('-','')[:6]` slices UUID7's
  *timestamp* prefix, so two alerts minted in the same millisecond got the identical id and the
  second overwrote the first in the armed map; the end-to-end state route returned the wrong alert.
  `[-6:]` takes the random tail. Sixteen other models in the tree use the same `[:N]` shape with
  wider slices that do reach the random bits, so the collision risk is lower there but the pattern
  is the same one.
- **Two gates that could not fail, found by canarying them.** `test_firing_twice_sends_once`
  asserted `first == second` — but `SOSDispatch` is a value, so a second fan-out produces an *equal*
  one and the assertion holds whether or not anyone was texted again; it now counts messages at the
  port. And the E.164 landline had no gate watching it: the fan-out test used the local spelling, so
  loosening `_KE_MOBILE` changed nothing observable. The two spellings are now watched separately.

Thirteen canaries were run against `tests/ci/canary_emg001.py` — the contacts leg dropped, the
three-contact cap raised, each of the two reachability regexes loosened, a non-GSM7 em dash in the
preset message, the ambulance leg inventing a dispatch, the cancel deadline not travelling, a cancel
no longer stopping the alert, a late cancel accepted, the replay guard removed, an empty profile
attached, the state route hiding the dispatch, and a cancelled alert handed a receipt instead of a
409. All thirteen fire.

**Counts: 5 rows left `missing` — 5 to `carried` (4 §EMG-001, 1 §EMG-002) — 87 → 82.** 493 rows,
`carried` 394, `missing` 82, `deferred` 17.

## §REC-004 — a tracker whose every date was wrong, and four features it never had

The audit had this section at two Features carried of six, and the two it counted were wrong in a way
no gate could see. Three defects in the code the audit had already marked carried:

- **Every predicted date was wrong.** `_add_days` was `int(month) * 30 + int(day)` arithmetic — a
  30-day month for every month, on both branches, and the "fast" branch (`day <= 28`) never carried
  the month at all. January 31 plus 28 days came out `2026-03-03` where the calendar says
  `2026-02-28`. The same 30-day month measured the cycle span, so a real 31-day cycle read as 30 and
  a 28-day one as 27. A date an app shows a person about their own body has to be the date
  `datetime` computes, so `_add_days`, `_days_between` and `_months_between` are now calendar
  arithmetic, and the tests cover a leap year (`2024-02-29`) and a year boundary.
- **The anchor was the last *logged* entry, not the latest period.** `predict` read `logs[-1]`, so a
  person who backfilled a missed earlier period — the ordinary way a tracker is used — moved their
  own anchor backwards and the prediction followed it. A backfilled December log against
  January–March entries produced a next-period date in January, for a person standing in March.
  `_ordered` sorts by `start_iso` and every calculation reads the sorted list.
- **`ref_date` was an argument nobody used.** A prediction is anchored to the last period and is
  therefore always in that period's future, so a person who has not logged for three months got a
  confident date in the past — the tracker telling them they were due last month. There is now an
  overdue branch that says so, in the section's own terms, and names the clinician route.

Then the four Features the audit had at `missing`, built from the archived sources rather than
invention (`sources/who-reproductive-health/`, checksummed in `sources/INDEX.md`):

- **Fertility awareness.** `fertile_window_days` was declared on the model and set to `None` on
  every path — the window existed only inside the `advise` string, so no client could read it as a
  value. It is now a value on both spellings: the pair of cycle days a calendar reader wants, and
  `fertile_from_iso`/`fertile_to_iso`/`ovulation_iso` as dates, because a person plans by date. The
  window is derived from two NHS figures — ovulation `LUTEAL_PHASE_DAYS` before the next period, the
  window opening `SPERM_SURVIVAL_DAYS` before that. **The NHS source gives no egg-viability figure**,
  so `EGG_VIABILITY_DAYS = 1` and the gap is recorded in `INDEX.md` rather than filled with a
  12-to-24-hour number nobody published.
- **Contraception reminders.** `ContraceptionPlan` records the method and carries `next_due_iso`;
  `contraception_due` returns the ones whose date has arrived. WHO groups contraceptives into three
  reliability bands and **states no percentage for any method**, so the code repeats WHO's own
  strings — `highly effective and long-lasting`, `works well when taken correctly`, `less reliable` —
  and the method table is served so a client renders the groups we record against. A method the
  source does not list cannot be recorded as one it does.
- **Menopause support.** `MenopauseStatus` runs the fact sheet's twelve-month rule over the person's
  own logs: twelve consecutive months with no period is how WHO defines the end of perimenopause.
  The state is `perimenopausal` until then, and `contraception_still_recommended` is true through the
  whole transition, because the source's sentence is "Pregnancy is still possible during
  perimenopause. Contraception is recommended to avoid unintended pregnancy until after 12
  consecutive months without menstruation." The 45–55 range is what "most women" experience — a
  population figure, not a test to apply to a person — so the tracker never uses age to reach a
  state.
- **Referral to services.** `ReproductiveReferral` names the services and lists by name the
  counselling lines whose numbers nobody verified. It reads `mental.COUNSELLING_LINES`, the same
  table §REC-005's referral and §INF-006's directory read, so a number cannot drift between the
  three screens that show it.

**A model that cannot be filled from the catalogue is a defect, not a licence.**
`test_mobile_catalogue.py::test_every_action_can_fill_the_body_its_route_requires` failed on
`set_contraception`, and it was right: `label`, `reliability` and `prevents_sti` are read from WHO's
table by the service, so they are not inputs and a form cannot fill them. The fix is the one the
gate's own history records for `Booking` and `FairnessAudit` — **split into a request and a result**
so the verdict stops being an input. `ContraceptionRequest` carries what a caller may say about their
own contraception and nothing about how well it works; a caller that sends a reliability band is
refused by `extra='forbid'`, which is a stronger statement than ignoring it.

Eighteen canaries were run against `tests/ci/canary_rec004.py` — the 30-day month returning, the span
in 30-day months, the anchor reverting to `logs[-1]`, the window dropped from the value, the window
dates dropped, the estimate caveat dropped, the overdue branch disabled, the reliability read from
the caller, a long-acting method given a schedule, an unknown method accepted, the STI note dropped,
the due filter loosened, the twelve-month rule shortened, contraception not recommended, the symptom
list altered, unverified numbers dropped, a spec code leaking into the referral, and the IDOR guard
loosened. All eighteen fire. Three of them had to be re-pointed after the `ContraceptionPlan` →
`ContraceptionRequest` split moved the code they patched — **a canary whose target the code has moved
past is a canary that did not run**, and the `assert count == 1` guard is what says so.

**Counts: 4 rows left `missing` — 4 to `carried` — 82 → 78.** 493 rows, `carried` 398, `missing` 78,
`deferred` 17.

**Not done in this unit, and named so it is not mistaken for done.** §REC-004's clause "Privacy:
PIN-protected. Excluded from cloud backup by default" is not implemented. It is a privacy requirement
alongside the six Features, not one of them, and it belongs with §MON-003's `hiv_pin_set` in a unit of
its own rather than folded into a tracker change.

## §MON-001 — a schedule kept twice, a dose that never reached the record, and four Features with no carrier

The section prints nine Features. Five were implemented and four were not, and the four failed in
three different ways — a fact with no carrier, a fact with two carriers that disagreed, and a fact
whose only carrier was a status string nobody read.

**The schedule existed twice, and the two copies disagreed.** `records.views.EPI_SCHEDULE` named
`RV1`, `MMR` and IPV at dose 2; `monitoring.views.EPI_DUE_WEEKS` named `RV`, `Measles-Rubella` and
IPV at dose 1. The keys are what the two modules join on, so a dose recorded through the tracker was
invisible to the wallet's gap check and a dose recorded through the wallet was invisible to the
tracker's. This is the second time in this build that one fact had two homes — §REC-004's
`LUTEAL_PHASE_DAYS` was the first — and the dependency direction settles it the same way: `records`
never imports `monitoring`, so the wallet owns the record and the schedule, and the tracker is a
*view* over them. `EPI_DUE_WEEKS` is now `= EPI_SCHEDULE`, a re-export, and
`test_the_schedule_is_one_dict_and_the_tracker_re_exports_it` asserts identity (`is`), not equality.
Two dicts that agree today are not one source of truth.

**`immunisation_gaps` measured age in whole years times twelve.** A child of eleven months had age 0,
so the six-week, ten-week and fourteen-week sets — BCG, OPV1–3, PCV10, pentavalent, rotavirus, IPV,
three visits carrying most of the infant schedule — first appeared on the child's *first birthday*.
The list was silent for the exact eleven months it exists to cover, and a parent reading an empty gap
list concludes nothing is due. It now measures days. Same class as §REC-004's 30-day month:
arithmetic that is internally consistent and wrong for the population it serves.

**A dose recorded on the tracker never reached the record.** `record_dose` took four scalars and
added a tuple to a set of its own. The section's own "Why this works" says the record "outlives the
paper card" — a dose filed through the tracker and absent from the wallet is that promise lost at the
seam. `record_dose` now takes an `ImmunisationRecord` and writes through to
`RecordsService.record_immunisation`, so the dose is one object in one place, and
`immunisation_gaps`, the vaccination certificate and the export all see it.

- **Record doses given (with photo of card).** `card_photo_sha256`, a 64-hex digest, optional. A
  digest rather than the image, because the record outlives the device and a base64 photograph in a
  wallet record is a different storage problem; optional, because a dose logged without a photograph
  is still a dose and refusing it would lose the dose to protect the photo.
- **Missed-dose alerts.** `missed_dose_alerts` returns an alert per dose, split into `overdue` (with
  `days_overdue`) and `due_soon` (from `REMINDER_LEAD_DAYS`, the 3-day and 1-day lead the section
  names). Served as data for the device to schedule rather than as a notification queue — §ACC-004
  wants no background polling, and the same reasoning produced §REC-004's contraception reminder and
  §EMG-001's countdown.
- **Campaign notifications (polio, measles).** `CampaignNotice` carries the disease slug, the
  counties, the age band and the window; `publish_campaign` files one verified `FeedItem` per county
  under a new `immunisation` feed category, and `campaigns(county, on_iso)` returns only those
  running that day. **Polio is expressible as a campaign target precisely because it is not a §3.3
  principle 12 outbreak disease** — `SPEC_DISEASES` is `('evd','cholera','rvf','mpox','measles')`, so
  `outbreak_polio` correctly raises `ValueError`, and the audit row that read "`AlertKind` carries
  neither polio nor a campaign type" was asking the wrong model to hold the fact. The age band has a
  `model_validator` because `(59, 9)` is a tuple of two ints and a campaign addressed to nobody, and
  a client posting the notice reaches the model before it reaches any service assert.
- **Shareable immunisation record.** The wallet's own `ShareGrant` over the `immunisation` document
  kind, with `share_view` enforcing the expiry. Not a second share mechanism: a second one would be
  a second expiry rule, and the two would drift.

**The toggle that had no producer now has one.** `immunisation_reminders` was in `TOGGLEABLE` and
`FEED_PREFERENCE` had no entry mapping a feed category to it, so a parent who switched it on could
not receive anything under it whatever the server published. The `immunisation` category closes that,
and the ALT-003 row is updated rather than left saying "no producer".

**A gate that could not fail.** `test_another_persons_child_is_refused` originally asked for a child
ref that did not exist — refused three times over, by the route guard, by the route's own ownership
check and by the service's "unknown child" assertion — so it passed whether or not the ownership rule
was applied at all. The distinguishing case is a child who *exists* in somebody else's wallet: only
the ownership rule refuses that, and without it the caller is served a named child's schedule. The
test now registers the child, asserts the guardian reads it, then asserts a stranger gets 403. That
was canary 15, and it was the one that MISSED on the first run.

Fifteen canaries were run against `tests/ci/canary_mon001.py` and all fifteen fire: the schedule
copied and renamed again, the dose stopping short of the wallet, the card digest accepting any
string, dose zero refused again (OPV0 is the birth dose), the gap list measuring whole years again,
the coming alert never firing, a missed dose raising nothing, a given dose reported missed, the
campaign landing under a category nobody set, a campaign with no county published anyway, a backwards
age band accepted, the campaign window ignored, the feed publishing unverified, the share never
expiring, and the IDOR guard loosened.

**Counts: 4 rows left `missing` — 4 to `carried` — 78 → 74.** 493 rows, `carried` 402, `missing` 74,
`deferred` 17.

**Not done in this unit, and named so it is not mistaken for done.** §MON-001's "Facility finder
integration for vaccination points" stays `carried` with its caveat: `/places/vaccination-points`
serves the kind and the immunisation schedule does not call it, so the client joins the two itself.
§MON-007's "larviciding campaign notifications" is a `missing` row with no producer, and the
`CampaignNotice`/`publish_campaign` machinery built here is its obvious carrier — it should be reused
rather than duplicated, and that is a §MON-007 unit.

## §TRI-003 — an Ebola triage that could not tell a funeral from a bushmeat exposure

§11.2 prints three Additional inputs and four Outputs. Two were implemented — the Ebola suspicion
classification and the contact list. The other five had no carrier, and they failed in four ways.

**One boolean stood in for four named exposures.** The section names funeral attendance, healthcare
work, contact with a case and consumption of bushmeat. `TriageInput` carried `ebola_contact: bool`,
so a person who had washed a cousin's body and a person who had handled bushmeat reported the same
fact — to a classifier that keys its whole Ebola rung on exposure history, and to a county team whose
first question is what the contact was. The four are now a closed vocabulary (`EBOLA_EXPOSURES`),
refused if unknown by `model_post_init` for the same reason `RED_FLAGS` is closed: an exposure list a
client can extend is one the classifier cannot reason about. Each carries its own note
(`EXPOSURE_NOTE`), and the notes render in the section's order rather than the request's, so two
identical reports do not produce two differently-ordered answers.

The four feed `exposure_history` **inside the model**, not at the call site. §8.1's three
epidemiological criteria are the general form of §11.2's four, so a person who reports healthcare
work without precautions has contact history whether or not they also ticked a boolean — and a client
that had to know which of the four implies which of the three would be the second place the two lists
are related.

**The transport instruction was simply absent.** §11.2's third Output is "Immediate action (call 719,
do not travel by public transport, await instructions)". The high-risk recommendation named 719 and
isolation and said nothing about how not to arrive. It is the instruction that matters most
operationally: a person who calls 719 and then takes a matatu to the nearest clinic has exposed
everyone on the route. All three now travel as a list of `ImmediateAction`, on the section's order —
rendered as a model rather than appended to `recommendation`, because `recommendation` is a clinical
string with a translation table behind it (§ACC-002) and folding an operational checklist into it
would put the checklist behind a translator who never saw it.

**"Isolate now" was advice with no input behind it.** The result said isolate and carried no status,
so the same sentence went to a person already in a separate room and to one who was not. `isolation`
is now one of three states, and `None` is a real fourth answer — "not asked" is not "not isolated",
and a default would make every caller that never asked claim the person told them. It changes the
*message*, not the guidance: `HouseholdIsolation.already_isolating` says which of the two readings
applies.

**The household guidance was behind a CHW's login.** `JOB_AIDS["isolation_basics"]` is §5.3
job-aid reference material for a community health worker; a person triaged at home cannot reach it.
Eight lines now travel as an Output, with their `provenance` on them — the WHO fact sheet states the
mechanism and gives no home-care procedure, so the block says which part is the source's and which is
standard treatment-unit practice. A block that let a reader assume all of it was WHO's would be a
citation the source does not carry.

**The Escalation had no carrier either.** "Any Ebola-suspected triage result triggers an automatic,
consented notification to the county rapid response team if the user opts in." There was no
notification, no consent read and no route. `TriageService.notify_county_rrt` is now the one path
that can send it, and it checks three conditions rather than one: the branch has to be an Ebola
suspicion, the person has to hold §SEC-001's `share_health_authorities` consent, and there has to be
a county to address it to. The mapping from §11.2's "if the user opts in" to §SEC-001's category is a
judgement, so it is a *named* method on the privacy service (`has_notification_consent`) rather than
a call at the triage site — a judgement written at the call site is one a reader re-derives.

**A control that failed open, caught before it shipped.** The first `notify_county_rrt` skipped the
consent check when `self._privacy is None` — and notified. That is the worst direction for it to fail
in: the thing it would send is a person's triage result to a health authority. Consent that cannot be
established is consent that is not held, so an unwired service refuses, and canary 10 plants exactly
this defect and watches the test catch it.

**The gate is the model's, not the service's.** `TriageResult._ebola_branch_carries_its_outputs`
asserts that the immediate-action list and the household block travel together and only on
`high_ebola_suspicion`. A service-level assert is only reached by callers that go through the
service; a route that constructed a `TriageResult` would not touch it. The same validator refuses a
result that claims a notification went out for a rung that is not Ebola, or that reports one without
the sentence explaining it.

**The route takes an optional identity.** `/triage/evd` is §8.1's Tier 1 triage, which has anonymous
mode — refusing a caller with no token would break the feature. But §11.2's Escalation needs a
subject, because consent is held per person. So the identity is optional (`optional_subject()`) and
the *consent* decides the escalation. A malformed token is treated as no token rather than as a 401:
the triage is still owed to the caller, and an expired token must not turn a clinical answer into an
error page. `/triage/rrt/{county}` reads the team's queue behind `assigned` — a CHW scope, and the
test mints that token through the app's own PKCE flow because `provision_staff` refuses a role the
app issues, which is the point of that refusal.

Twenty canaries were run against `tests/ci/canary_tri003.py` and all twenty fire: the four exposures
ceasing to be contact history, the vocabulary opening, every exposure getting the same sentence, the
notes following the request order, the action list emptied, the transport instruction dropped alone,
the pair leaking onto every rung, the validator loosened, consent not consulted, an unwired service
notifying, every classification escalating, a notification with no county filed, the county filter
dropped, isolation status not reaching the guidance, the exposures not travelling to the team, a case
identifier invented from the subject, §11.1's gate removed, the route escalating without the ledger,
the route claiming a notification that did not go, and the county view unscoped.

**Counts: 4 rows left `missing` — 4 to `carried` — 74 → 70.** 493 rows, `carried` 406, `missing` 70,
`deferred` 17.

**Sources.** `sources/ebola-transmission/` holds the WHO Ebola disease fact sheet (24 April 2025) and
CDC's About Ebola Disease page, both checksummed in `sources/INDEX.md` with what each does and does
not support. The 21-day window and the contact-with-a-body route are the fact sheet's; the household
procedure is not, and the code says so where it is served.

**Not done in this unit, and named so it is not mistaken for done.** §TRI-003's "Vaccination status
(if a vaccine is available and deployed)" stays `deferred` — it is conditioned on a fact about the
world, not on this tree. `case_ref` is a parameter with no caller: nothing in this tree mints a case
identifier for a triage result, so the notification carries `None` unless a future caller has one.

## §COM-102 — an alert with a body a CHW wrote, and a follow-up list nothing read

§11.4 prints five Features and one Verification clause. Two were implemented — the geofenced zones
and the tone gate. The four below had no carrier, and the first is the one that could have hurt
someone.

**The alert body was free text.** `PeerAlert` carried a caller-supplied `headline` and `body`, and
nothing drafted the section's sentence. A free-text body is a body that can be alarmist, that can
name a person, and that no reviewer sees before it reaches a whole village — and the section says its
wording was "tested with community representatives before deployment", which a sentence typed at 3am
is not. `ALERT_TEMPLATE` is now the section's sentence and `body` is a `computed_field` over it, so a
free-text body is not representable rather than merely discouraged. The only slot is `location`.

That is also how the second Feature is enforced. "No personally identifiable information about the
case" was unenforced rather than absent: the template has nowhere to put an identifier, which is a
property of the type rather than a reviewer's attention. The residual leak is the location itself —
"House 14, next to Mama Otieno's" is a person — so `model_post_init` refuses identifier shapes
(dwelling-plus-number, determiner-plus-person-noun). "the case" is deliberately allowed: it names
nobody, it is the section's own anonymised phrasing, and a rule that banned it would refuse "The Case
Hotel, Nairobi" and teach a CHW to write around the check rather than use it. A rule people route
around is worse than the narrow one they keep.

**The zones were a range, not the section's three.** `radius_m` was bounded `ge=500, le=5000`, which
admits 3000 — a radius the section does not offer and a county cannot configure, since the zones are a
choice from three and not a slider. The set now lives in `afya.location.views:ALERT_ZONE_RADII_M`,
which is where §LOC-001's alert radii are too, and `afya.location.service:ALLOWED_RADII_M` re-exports
it under an identity assert (`is`, not `==`): two tuples that agree today are not one source of truth,
and the earlier module-constant defect in this very section was a constant nothing read. It is in
`views` rather than `service` because a *model* validates against it, and a views module importing a
service module for a constant that is a fact about the spec is the dependency pointing the wrong way.

**Acknowledgement and guidance were the same missing bullet.** "Users acknowledge alerts and receive
follow-up guidance" — there was no acknowledgement model, no route, and nothing returned after one.
`PeerAlertAck` is posted to `/community/peer-alert/ack` behind `require_self()`, which *refuses* a
body naming another person (403) rather than silently rewriting it, and returns `PeerAlertGuidance`:
the four actions that resolve a concern inside an alert zone, plus one more line for a person who says
they are worried — the section's Tone clause is "calm, factual, actionable", so a worried person gets
the action rather than reassurance. The receipt counts *distinct subjects*, because the number a CHW
reads is "how many people heard this" and a double tap is one person, not two.

**The follow-up list was carried and never read.** `followup_days` defaulted to `[3, 7, 14, 21]` and
no code path touched it. `followup_prompt` reads it now, on a day passed in rather than read from a
clock — the scheduler is the deployment's, and a service reading `date.today()` would make every test
that exercises day 21 depend on when it ran. The day a person is *on* is derived from
`alert.issued_iso`, not from the client: the window opens when the alert was issued, so a phone with a
wrong clock cannot read someone the day-21 prompt on day 1, and a late acknowledgement is clamped
into the window rather than refused — an acknowledgement that arrives late is still an
acknowledgement. `model_post_init` pins `followup_days` to the section's four, so a caller cannot send
`[1..21]` and turn four prompts into a daily nag, which is the thing the section avoids precisely by
naming four.

**Wiring.** Three mobile catalogue actions (`peer_alert`, `peer_alert_followup`, `ack_peer_alert`),
all three in `DORMANT_SLUGS` because §COM-102 is Tier 4 — an alert network that can wake a whole
village must not be reachable before PHEOC activates the event. Two existing gates caught two real
defects during this unit and both were load-bearing rather than decorative:
`test_every_request_body_tolerates_its_own_derived_fields` refused `PeerAlert` until it mixed in
`DerivedFields` (a computed field a request carries back would otherwise be a 422), and
`test_every_tier4_action_is_dormant` refused `ack_peer_alert` while it was live.

Twenty canaries were run against `tests/ci/canary_com102.py` and all twenty fire: the body becoming
caller-supplied, `DerivedFields` removed, the 21-day window dropped from the sentence, the location
rule removed, the rule widened to refuse the section's own phrasing, the zone set loosened to a range,
`followup_days` made settable, a prompt on every day, a prompt on no day, an unknown alert answering
instead of refusing, the acknowledgement not recorded, the ledger keyed so a double tap counts twice,
the day ignoring the issue date, a late acknowledgement refused, the guidance emptied, the worried
line dropped, the receipt carrying a different body than it sent, the route not reading the ledger,
the ack route not binding the token, and the three actions going live.

One canary is worth naming because its first version passed for the wrong reason. #12 was written
against `acknowledged_count`'s set comprehension, and mutating it was caught by *nothing* — the
ledger dict already dedupes on `(alert_id, subject_ref)`, so the set is a second line of defence with
no independent failure. It was rewritten against the key itself. A canary aimed at the belt when the
braces are doing the work is a canary that reports a gate it never tested.

**Counts: 4 rows left `missing` — 4 to `carried` — 70 → 66.** 493 rows, `carried` 410, `missing` 66,
`deferred` 17.

**Sources.** No new archive: the section's 21-day window is the same WHO Ebola disease fact sheet
already archived under `sources/ebola-transmission/` for §TRI-003, and §COM-102 states no threshold of
its own. The 500 m / 1 km / 5 km zones are the section's, and the recipient estimate
(`π r² × 4,000 /km²`) is a stated modelling assumption in the code, not a sourced figure — it is
labelled as such where it is computed.

## §INF-006 — a directory that printed two numbers and four Features nobody could use

The section asks for "a single screen with all relevant contacts", prints eight Contents and four
Features. What existed was `GET /info/hotlines` serving a list of two rows of a table as text: one of
eight Contents, none of the four Features, and no statement about the seven it lacked.

**The gap had a shape, and it was two shapes.** Four Contents were national numbers the tree simply
did not hold — the GBV helpline and the child helpline among them, while `mental.COUNSELLING_LINES`
held the counselling numbers three modules away and the route never read the table. Two more were not
national numbers at all: "county health office" and "CHW" are whoever the *caller's* county and
community have, so a directory built without a county cannot list them and must say so. And the
sixth was unanswerable by construction — `ChwProfile` carried a name, a county and a community and
**no way to reach the person**, so a CHW row could not be composed for a deployment that had
provisioned every worker in the country.

**What changed.** `HOTLINES` gained three rows (1195 the National GBV Helpline, 0800720565 GVRC, 116
Childline Kenya), each `verified=False` with the archive named in the comment — these are the
operators' own statements and none has been confirmed against MoH/PHEOC, which is the confirmation
§18.4 asks for. `HotlineInfo.county` is `None` for a national row and the caller's county for a
row about them; a county-scoped row is served only to a caller who named that county, because a
directory that showed every county's office to everyone would be a list, not an answer.
`InfoService._county_office_rows` and `_chw_rows` follow `_nearest_facility_rows`' pattern: they
return `[]` when the row is unanswerable, so the kind lands in `absent` and the screen prints a gap
rather than a blank line. `ChwProfile.phone` is new — optional, because it is personal data the
worker may not have given — and `ChwService.serving(county)` returns `None` rather than asserting,
because "this county has no CHW provisioned" is an answer a life-safety screen must be able to print
and an assert would turn a gap in the deployment into a 500. The pick is the lowest `chw_ref` among
the county's workers: stable across restarts, so the number a person saved is the number they reach
next time. `register_county_office` refuses an empty number, because `_county_office_rows` treats a
falsy number as "not on file" — an empty string would be a registration that silently disappears
while the operator believes they filed it.

**The four Features are rendered server-side** as `actions` on each row (`tel_uri`, `sms_uri`,
`vcard`, `share_url`), the way `Directions` renders its two map URLs. "One-tap call" as a client
obligation is a feature two clients implement differently; as a URI it is one behaviour. The
`vcard` is why "save to contacts" is a row field and not a client string.

**Wiring.** `POST /info/county-office`, guarded by `require_scope('infrastructure')` — matching
`POST /info/dashboard/{county}` — because the row it fills is one a caller may dial in an emergency,
and a citizen-scoped write would let anyone put a number on a life-safety screen. `GET /info/hotlines`
gained `county`, and passes it through.

**Counts: 4 rows left `missing` — 4 to `carried` — 66 → 62.**

**Sources.** New archive `sources/helpline-directory/` — UN Women on 1195 (national, toll-free,
24/7, multilingual, with an SMS route, operated by HAK), Childline Kenya's own site on 116 (the
National Child Helpline, the number owned by the Government through the Department of Children
Services), and GVRC's own site on 0800720565 (24/7, free, the one of the three that is a clinical
service). What each does and does not support is recorded in `sources/INDEX.md`; none of the three is
the deploying authority speaking, which is why every added row is `verified=False`.

## §INF-007 — a screen that was correct, wired, reachable, and permanently empty

The section is one sentence naming six Contents: "School closures, border post status, market
closures, water interruptions, road closures affecting facility access, public transport
disruptions." Two were carried and four had no carrier.

**The gap had a shape worth naming, because it is not the usual one.** `GET /alerting/service-status`
already existed. It filtered the feed's `service` category, the category already had a preference
mapping (`service → facility_alerts`) and the socket already fanned out over it. **Nothing produced a
`service` item.** So the screen answered zero however many closures the county had published: a read
with no producer, which is the same failure as a capability with no route wearing the opposite coat.
A missing route is visible from the outside — the path 404s. A read with no producer returns `200`
with an empty list forever, and every test written against the read passes.

**What changed.** `ServiceStatus` in `afya/alerts/views.py` carries the six kinds as a closed set
(`SERVICE_STATUS_KINDS`) with a **per-kind state vocabulary** (`STATES_FOR`): a school is `open` or
`closed`, a water supply `interrupted` or `restored`, a border post or road `restricted` as well. One
shared vocabulary would let a school be "interrupted", and a status a reader cannot map onto a
decision is a status that does not answer "can I go there today". §INF-007's own qualifier —
"road closures **affecting facility access**" — is carried as a field and enforced in
`model_post_init`, because this feed exists to answer whether the reader can reach care and a closure
that does not affect reaching care belongs in a traffic feed. `headline` and `body` are derived
properties, so the alert text cannot drift from the status, and `body` names the place again because
§3.3 principle 10 requires every output be shareable: a body forwarded without its headline says
"Closed after flooding" and names nothing.

`AlertsService.publish_status(status, feed)` is the producer. It **publishes into the feed rather
than storing beside it**, so the status screen and the phone alert are one fact rather than two that
can disagree; the feed is written first and `_statuses` second, so the list is a view of what was
published. The verification rule is not restated: `verified=status.verified` is passed and the feed's
own §ALT-001 gate refuses an unverified item, so one rule lives in one place. `service_status()` is
keyed on `(kind, name)` and returns the latest per place — a feed is a record of what was announced,
a status screen answers "can I go there today" — while `status_coverage()` reports the section's six
and how many current statuses each carries, so a deployment with no road-closure feed says so instead
of rendering an empty section. `feed` is typed loosely (`object`) for the reason every cross-module
port here is: the two are wired at the composition root and neither imports the other's class, so a
status publishes with no feed wired and still records.

`POST /alerting/service-status` is guarded by `require_scope('assigned')` — the same scope as
`POST /alerting/feed`, for the same reason: a market closure or border-post restriction reaches every
phone in the county.

**Wiring.** One new route and one widened read. `GET /alerting/service-status` now serves `count`
(the current statuses), `statuses`, `coverage` and `items` (the feed items that produced them), which
differ deliberately — a market that closed and reopened has one current status and two feed items.

Sixteen canaries were run against `tests/ci/canary_inf007.py` and all sixteen fire, across both
sections: one shared state vocabulary; the road qualifier dropped; the headline losing the place; the
status stored without being published (the original defect restored — the screen goes back to being
permanently empty while the status service looks like it works); the verification flag written rather
than passed; the status screen becoming a log; the county filter dropped; the coverage report naming
one of six; the publish route losing its guard; the route not passing the caller's county; another
county's office served to a caller who named their own; an unreachable CHW listed anyway; an empty
county-office number stored; the CHW profile losing its phone number; `serving` asserting instead of
answering; and the CHW pick made unstable.

**Counts: 4 rows left `missing` — 4 to `carried` — 62 → 58.** 493 rows, `carried` 418, `missing` 58,
`deferred` 17.

**Sources.** No new archive for §INF-007: the section states no threshold, and the one external fact
it leans on — that a border post's status is a thing the tree already models — is §LOC-005's
`BorderPost`, carried by `afya.location.service:LocationService.border_status`. The two are not yet
reconciled onto one screen, which is noted rather than papered over.

## §AI-001 — two signals with no consumer, and a consumer with no signal

The section names five Inputs, three Outputs, and a privacy rule. Three of the five Inputs were
carried; the other two, and two of the three Outputs, were not — and the four gaps were two failures
wearing opposite coats.

**Two signals the product recorded and never used.** `AggregateCell` had no `geofence_entries` and no
`search_signals`, while the tree held both quantities: `integrations.feeds.build_geofence_feed`
already aggregated distinct subjects per cell at the min-cell floor, and §AI-003's own
`_signal_events` ledger already recorded `facility_search` and `medicine_search` rows. Neither
reached the prediction. A signal the product collects and does not feed to the model it exists to
inform is an Input the section names and nobody wired — invisible, because both halves work.

**One output with a builder and no producer.** `build_resource_feed` rendered §18.3's
`resource_deployment` feed correctly, with `auto_actioned: False` on every row, and **nothing produced
its recommendations**. That is the same failure as §INF-007's read-with-no-producer, on the write
side: the arrow AI → PHEOC had a renderer at one end and no source at the other.

**What changed.** `AggregateCell` gained `geofence_entries`, `search_signals`, and optional `lat`/`lon`
— optional because a cell rolled up from a sub-county has no centroid, and adjacency is a spatial
claim that a cell without a position cannot make. `AIService._signal_score` is the model's whole
definition in one place: **every term is a rate, not a count**, because a cell of 40,000 and a cell of
200 with the same count are not the same event and a model that added counts would rank by population
and call it epidemiology. The weights are the model's own — the section states none — and fever
dominates because fever is what the product collects at scale. `cells_from_signals` is the bridge:
it reads the search ledger for the county and day, takes the geofence count from its caller (the floor
lives in the module that owns the aggregation, and a second copy of it here is a second floor that can
differ), and **builds the cell whatever its population**, leaving suppression to `hotspots` — the one
place that decides what may be published, and the place whose count would be wrong if a bridge
pre-filtered.

`TransmissionCluster` with `ClusterLink` edges is the second Output, built by single-linkage over the
cells that cleared **both** the min-cell floor and the baseline. That ordering is the privacy control:
a cluster whose `reason` named a cell of four people would re-identify exactly what the floor exists
to prevent, and a cluster built before suppression would do it through the back door. Clustering the
whole eligible set instead of the hotspots would produce one country-spanning cluster whenever the map
is dense — naming every cell and therefore identifying none. A cell with no position is **reported**
in the cluster's `reason`, not dropped: "we could not tell whether this cell touches the others" is a
fact PHEOC can act on, and a cluster that quietly omitted it would read as complete.

`ResourceRecommendation` is the third Output, derived from the clusters and hotspots and never from
the raw cells — a recommendation has to trace to a finding. A cluster gets a rapid response team
(sampling is what verifies a cluster) and test kits; a lone hotspot gets risk communication, because
one elevated cell is a signal to check, not a finding to deploy against. `quantity` is `None` where
the section's arithmetic does not determine one: how many test kits a county needs depends on the
cluster population and a stock position this service does not hold, and a modelled number wearing the
authority of a recommendation is worse than an absent one. `model_post_init` refuses
`auto_actioned=True` — §19.3's human in the loop, as a gate rather than a comment.

`POST /ai/hotspots/deploy` is the producer: it takes the map's **own** recommendations, not the
caller's, and pushes them through the existing §18.3 feed. A caller posting its own recommendation
list could put a rapid-response team on the wire with nothing behind it; what the route adds is the
transport, not the judgement. A map with nothing above baseline returns `recommendations: 0` with the
reason named, rather than surfacing the transport's (deliberate) refusal of an empty batch as though
the caller had sent something malformed.

Thirteen canaries were run against `tests/ci/canary_ai001.py` and all thirteen fire: an input on the
cell and out of the score; geofence entries stop moving the score; the score counting instead of
rating; every cell clustered rather than the hotspots; the cluster radius covering everything; an
unlinkable cell silently dropped; a lone cell becoming a cluster; a lone hotspot getting a team; a
recommendation actioning itself; a quantity invented for the kits; the deploy route inventing a
recommendation; search signals counted as facility reports; and the bridge pre-filtering the floor.

**Three of those canaries MISSED on the first run, and all three were the test's fault, not the
code's.** `test_cells_further_apart_than_the_radius_are_not_one_cluster` had one cell below baseline,
which is filtered *before* clustering runs — so it was testing the baseline filter while claiming to
test the distance, and would have passed whatever the radius. `test_one_cell_above_baseline_is_a_hotspot_and_not_a_cluster`
had its neighbour far away, so a version clustering every eligible cell also produced nothing.
`test_a_lone_hotspot_gets_communication_and_not_a_deployment` asserted on the *communication* rows,
which are emitted after the team rows, so widening the team rule changed nothing it looked at. Each
was rewritten to differ from its control in exactly the one respect it claims to test. A canary aimed
at a filter upstream of the behaviour under test reports a gate it never reached.

**Counts: 4 rows left `missing` — 4 to `carried` — 58 → 54.** 493 rows, `carried` 422, `missing` 54,
`deferred` 17.

**Sources.** No new archive. The section states no threshold and no weight; the min-cell floor of 10
is §19.3's own and was already archived with §SEC-004, and the model weights and the 5 km cluster
radius are the model's own parameters, named as constants in `AIService` with the reasoning attached
rather than presented as sourced figures.

---

## §INF-001 — three Displays nobody could put a fact behind

§8.5 prints seven Displays. Four were carried and three were not, and the three were the ones a reader
opens the screen for: **how many cases, where inside my county, and can I go there today.** The fourth
that the audit called carried — "service status (schools, borders, markets)" — is the one §INF-007 had
just built a producer for, so a third of this unit is wiring rather than new machinery.

### The counts, and the word that must not be typed

`CaseCounts` carries `confirmed` and `suspected` as two fields because the section prints them as a
pair and the distinction is the whole point: a reader of an outbreak dashboard is deciding whether a
feverish child has Ebola or malaria, and one `cases` number answers that question with the wrong one
of the two. One row **per disease**, because the section's first Display is "Ebola **and other
notifiable diseases**" — a county at three confirmed Ebola and forty confirmed cholera has two
answers and the response to each is different.

`trend` is a `@computed_field`, not a field. A carried trend is a word a caller asserts, and "rising"
on an outbreak dashboard is the one word that has to follow from the figures. Deriving it also means
the API's own output is not a 422 against the API's own input, which is what `DerivedFields` exists
for — asserted in the test rather than assumed.

**The previous period is carried forward from the row already on file, not asked for.** A trend needs
two periods and the service holds the earlier one. A caller who had to restate last week's figures
would sooner or later restate them wrongly, and the word on the dashboard would then be a
transcription of their recollection rather than a reading of the data. A caller who *does* supply one
wins, because a county may be comparing against a period this deployment never saw. The carry-forward
is skipped when `as_of_iso` matches the stored row: that is a **correction** to the period on file,
and shifting the old figures into `previous_*` would make a corrected count read as a rise or fall —
the dashboard would report an epidemiological event that did not happen, caused by someone fixing a
typo.

`new` rather than `steady` when there is no earlier period: a county reporting its first cases has not
held steady, and a dashboard that said so would tell a reader the outbreak is stable on the day it was
first detected.

### The sub-counties, and what "affected" means

`SubCountyStatus` carries the sub-county, its disease, its counts, and the named `locations` inside it
— a market, a village, a facility — because a sub-county name alone still covers tens of thousands of
people. `model_post_init` refuses an "affected" area carrying neither a case nor a named location: a
place with nothing to report is not affected, and listing it puts a name on a life-safety screen with
nothing behind it. Re-reporting a place **supersedes** it rather than appending, because a sub-county's
status is current — a place that had two cases and now has five has one answer, and a screen listing
both makes the reader work out which is today's from two dates. The list is ordered worst-first, ties
broken on the name so two identical deployments serve the same screen.

### The service status, which is §INF-007's fact on a second surface

The fifth Display is `AlertsService.publish_status`'s output, read from that service rather than
restated — the same fact on two screens, and a second copy would be the one that goes stale. The join
happens in the route, where both services are in scope, so there is one reader per fact. The section's
"where available" is answered by the feed being empty rather than by a placeholder row, and the test
drives the *producer* through its own route and then asks the dashboard whether the fact arrived.

### Neighbouring counties needed a border table, and there was none

The section's Description asks for "the user's county **and neighbouring counties**", and nothing in
the repo recorded that Busia is next to Bungoma. `afya.info.counties` is **derived** from
geoBoundaries' Kenya ADM1 release, archived under `sources/county-adjacency/` with the rule stated:
two counties are adjacent when their polygons share a boundary segment at least 1 km long, coordinates
rounded to 3 decimals. Both constants are load-bearing — a shared *vertex* is not a shared border
(four counties meet at one point in western Kenya), and without rounding the two sides of a border
never compare equal and the rule returns zero pairs while looking correct.

`test_county_adjacency.py` **re-derives the table** from the archived GeoJSON on every run and
compares all 113 pairs, rather than checking a count. A count survives a swap: if Bungoma gained Busia
and lost Kakamega the total would be unchanged, and the swap is exactly what a hand edit produces. It
also pins the counties whose geography is least forgiving — Mandera has one neighbour and that is
correct — because a per-county check catches what a total does not.

### One architecture decision worth naming

`CountyDashboard` carries **no** `updated_at_ms` and **no** `source`. Both are §8.5's "Last updated
timestamp" and "Data source attribution", and both belong to the risk assessment: the field the
section dates is "current outbreak status by county", and a second stamp on the container that had to
equal the first is a drift hazard with nothing to gain. Each part dates itself — a count carries
`as_of_iso`, a status carries `effective_iso` — and `served()` spreads the risk's stamp to the top
level so a client reading the payload flat still finds it. **The four keys that were already top-level
stay top-level**: `risk_level`, `active_signals`, `bulletin`, `source` and `updated_at_ms` were this
payload's shape before the dashboard grew, and nesting them under `risk` would break every client to
gain nothing a reader can see.

### Canaries

Nineteen canaries run against `tests/ci/canary_inf001.py` and all nineteen fire: the previous period
not carried forward; the trend ceasing to be a computed field; the trend ignoring suspected cases; a
correction becoming a new period; half a comparison period accepted; an empty sub-county accepted; the
sub-county read ignoring the county; the case-count read ignoring the county; the sub-county read
ignoring the disease; the dashboard dropping the service statuses; the border table losing one side of
a pair; the neighbouring counties dropped; a neighbour wearing the caller's risk; the route no longer
checking the county agrees; the write losing its guard; a sub-county appended rather than superseded;
the sub-county order ceasing to mean anything; the served payload nesting the risk row; and an unknown
county raising.

**One canary was intermittently blind, and the cause was the harness rather than the code.** Canaries
#7 and #8 mutate different methods — the sub-county read and the case-count read — and both edits
happen to be the *same byte length*, because each removes a `X_county == county and (` of exactly 24
characters. CPython validates a `.pyc` on (source mtime, source size), both recorded to a coarse
granularity, so when the two writes landed in the same second the second canary's pytest run reused
the **first** canary's bytecode: `case_counts` was never mutated, the test passed, and the script
reported a gate it had never pointed anywhere. It fired 19/19 on most runs and 18/19 on others — a
canary that is sometimes blind is blind, and the tell was the disagreement between runs rather than
any single result. The fix is a `__pycache__` purge after each write. **This is the same class as the
`assert before in s` rule and for the same reason: the failure is in the instrument, and it is
invisible precisely because it looks like a clean result.**

**Counts: 3 rows left `missing` — 3 to `carried` — 54 → 51.** 493 rows, `carried` 425, `missing` 51,
`deferred` 17.

**Sources.** `sources/county-adjacency/` — geoBoundaries Kenya ADM1 (simplified), public domain, with
the API's own metadata record and the derived table; the derivation rule and what the source does and
does not support are in `sources/INDEX.md`. The section states no threshold and no count, and the 1 km
segment rule is the repo's own parameter, named as a constant beside its reasoning rather than
presented as a sourced figure.

## §FND-006 — a booking with no owner, and three verbs that could not exist without one

§9.4 prints five Features. Two were carried and three were not, and the three were the whole of the
section: a person could be *given* an appointment and could not choose, move or release one. The
`book` that existed took a `slot_iso` the caller supplied and wrote a row — which is the shape that
makes the other two bullets look like missing screens rather than a missing relation.

### "reschedule, cancel" could not be built, because the booking belonged to nobody

`Booking` had a six-character reference and no owner. That is enough for a *create* and nothing else:
a cancel keyed on a reference anyone can read off a screen is a delete key anyone can perform, and a
reschedule is the same with a new time on it. So the unit is one field — `subject_ref` — and the three
verbs are the three things it makes possible.

The owner is taken from the token, never from the body. `optional_subject()` rather than a guard,
because booking an appointment is Tier 2 and a login between a person and a clinic slot would break
the feature it is there to provide; but a booking filed *with* a token records whose it is, and that
is the difference between an appointment only its owner can move and one that six guessed characters
take. The route reads the token to decide who the appointment belongs to, which is why it left
`UNGATED_WRITES` — the walker counts an optional dependency as a guard, and that is the honest
reading of what the route now does.

`owns()` is the single place §17's ownership relation is applied. A second implementation in a route
would be a second rule, and the two would diverge on the case that matters.

### The unknown reference and the someone-else's reference answer identically

A 404 for a reference that names nothing and a 403 for one that exists but is not the caller's turns
the route into an **oracle**: six characters is a search space a script walks in minutes, and the 404
tells it which guesses named a real appointment. Both now answer the same 403 with the same detail,
and the only place a booking's existence is admitted is a route its owner has already passed.

The service refuses an unknown reference too, and that is not redundant. `owns` guards the route; the
gRPC surface, an offline replay and a test all reach `FacilityService` without passing it, and each
would otherwise get a booking minted out of nothing. Canary #18 fires on exactly that — it is the
second line, and the one a caller who never sees an HTTP status depends on.

### A cancel is a state, not a deletion

§FND-006's queue is a **position**. A booking that vanished would silently move everyone behind it,
and "where did my place go" is not a question a clinic can answer after the row is gone. So
`cancelled` is a flag, the row survives, and the place it held is released — which is what the person
actually asked for.

A reschedule keeps the queue position and moves only the time. A person who booked in March and moves
to April has not joined the back of a new line, and renumbering them punishes the one behaviour a
clinic most wants: being told in advance. The old slot's place is released before the new one's is
taken, so a facility's booked count is never briefly wrong in the direction that oversells it.

### The slot is published one at a time, and a full one stays on the screen

A day is not a formula. A clinic that runs a queue at nine and appointments in the afternoon cannot be
expressed as a start, an interval and a count, and the generic mobile form's `list` field is
comma-separated text — it cannot render a body carrying a list of *objects*. So `SlotOffer` publishes
one slot per call, which is the shape a form can fill and the shape a facility actually decides in.

`FacilitySlot` carries `capacity` and `booked` rather than a boolean `taken`, and the day is served
with the taken slots in it at `free == 0`. A screen that offered only free times would tell a person
nothing about whether the clinic is full today or closed, and "nothing available" is the answer they
most need before they travel. `free` is a `@computed_field` so a slot cannot advertise places its
bookings have taken, and `model_post_init` refuses a slot claiming more booked than it offers.

A facility with no published schedule still takes a booking. Most of the registry has none, and "we do
not run appointments here" is not the same answer as "that time is taken" — refusing would make the
feature unavailable everywhere it has not been configured, which is everywhere.

### The reminder is derived, and a cancelled booking carries none

§FND-006's "Reminder notifications" is `Booking.reminder_due_iso`, a `@computed_field` computed from
the slot. On §ACC-004's reasoning — the same shape as §MON-001's missed-dose alert and §REC-004's
contraception reminder — the server states *when* the reminder is due and the device holds it, so the
reminder fires with no network and §ACC-001's offline mode keeps working.

Derived rather than stored is the load-bearing half: a stored lead is a second copy of a policy the
facility sets, and the copy that drifts is the one already written into somebody's appointment. A
reschedule moves the reminder because the reminder *is* the slot, minus the lead. A cancelled booking
returns the empty string, because a notification for an appointment the person has already released is
worse than none — it sends them to a clinic for nothing.

### Canaries

Eighteen canaries run against `tests/ci/canary_fnd006.py` and all eighteen fire: a booking ignoring the
published slot; a full slot dropped from the day; a reschedule renumbering the queue; the ownership
check removed; an unowned booking becoming anyone's; a cancel deleting the row; the reminder ceasing
to follow the slot; a cancelled booking keeping its reminder; a reschedule oversubscribing a slot; a
reschedule leaking the old slot; re-publishing forgetting the bookings; the path/body facility
agreement dropped; the publish route losing its guard; the owner taken from the caller; a slot
claiming more booked than it offers; a schedule carrying another day; a cancelled booking being
movable; and the service inventing a booking for an unknown reference.

**Two canaries were blind on the first run, and both were the same failure in the instrument.** #3
asserted `moved.queue_position == first.queue_position` where `moved is first` — the same object the
mutation writes to — so the assertion held whatever the code did; it now reads both positions back
through the service. #18 targeted a route branch that the route's own `owns` check had made
unreachable, so the mutation never ran; it now targets the service's assertion, which is the guard
that is actually load-bearing. A canary that passes is a bug in the canary, and a *test* that compares
an object to itself is a canary's blind spot wearing the test's clothes.

**Counts: 3 rows left `missing` — 3 to `carried` — 51 → 48.** 493 rows, `carried` 428, `missing` 48,
`deferred` 17.

**Sources.** None. §9.4 states no threshold, no interval and no lead time; `REMINDER_LEAD_HOURS = 24`
is the repo's own parameter, named as a constant beside its reasoning rather than presented as a
sourced figure.

## §MON-005 — a warning that named no method, and a container nobody mentioned

§10.2 prints five Features. Two were carried and three were not, and the three were the part a
household acts on. What existed was `water_alert`, which reads "do not drink without boiling" — a
**warning**, not guidance. It names no method a person can perform, says nothing about the container
the water goes back into, and schedules nothing. A household told its water is unsafe and given
nothing to do next has been told to stop drinking.

Writing the three missing bullets meant answering four questions the section does not: *which*
methods may be offered, when one must be withheld, how long treated water keeps, and what residual
protects it in storage. Every answer is a figure or a condition out of a WHO document, so two are
archived under `sources/water-treatment/` and the third is cited by name — and the ones the sources
do **not** state are recorded as the repo's own parameters rather than dressed as WHO's.

### Chlorine is withheld from water it was never evaluated in

The load-bearing decision, and the one that is silent when it is wrong. WHO's Round II evaluation
states the tested products "should only be used in nonturbid water (<5 NTU)". A household that doses
cloudy water, waits half an hour and drinks it has drunk water the turbidity never let the chlorine
reach — no visible failure, no symptom that points at the cause.

Two figures sit in that source and they mean different things: **5 NTU** is the limit the products
are evaluated to, and **30 NTU** is where WHO says pretreatment is required whatever the product.
`CHLORINE_TURBIDITY_LIMIT_NTU` is 5.0, and canary #3 moves it onto the 30 so the offer *looks*
justified by the source while sitting 25 NTU outside the condition the products were tested in.

Boiling is the one method offered on every reading and led with on all of them, because the brief
calls it "highly efficacious, killing human pathogens even in turbid water and at high altitude" — no
condition attached, which is exactly why the advisory can name it without knowing more about the
water. That is also why the notice leads with it and the storage block and reminder are built from
the lead.

### Every method carries its limit, and the limits are the reason the bullets exist

`TREATMENT_CAVEATS` is not decoration. The same brief says boiling "does not provide any residual
protection"; Round II says chlorine is "ineffective against most protozoan cysts including
Cryptosporidium". A method named without its limit is the one a household follows into water that is
still infectious, so the caveats are asserted to be as long as the method list.

### The residual belongs to a method, so storage is one block per method

WHO's Round II gives the figure that protects stored chlorinated water — ">=0.5 mg/L after 30 minutes
of contact time, or >=0.2 mg/L in stored household water" — and it is the one number in the answer
that only chlorine can produce.

This is where the first draft was wrong, and the test caught it: `WaterSafety` carried a *single*
`storage` block. The block has to be the lead method's, and the lead is always boiling, so
`residual_chlorine_mg_l` was **unreachable in every served payload** — a field nothing could populate,
carried as though it were a feature. Storage is now one block per permitted method, in the same order,
so a clear reading offers chlorination with its 0.2 mg/L and a cloudy one offers none. Canary #6 puts
the residual back on every method, which is boiled water being served a figure a reader cannot act on.

Storage is served on *every* reading, including a safe one, because the source says it is not the
lesser bullet: Round II cites a meta-analysis finding "filtration and integrated safe storage can
reduce the risk of diarrhoeal disease by 61% compared to 51% from filtration only".

### The reminder is told when, and the interval is the storage advice's own

A household that boils in the morning and one that boils at night need different reminders, so the
route is *told* the time rather than picking one. `treated_at_iso` is a query parameter and not a
field of `WaterQuality`, because it is not part of the reading — it is when this household last
treated water, and putting it in the reading's model would make the county's post and the household's
schedule one object.

`REMINDER_INTERVAL_HOURS = 24` is the repo's own figure, and it is the storage guidance's own "drink
it within a day": a reminder on a longer interval would remind a household to drink water that has
stood too long, which is the failure the storage step exists to prevent. Neither archived source
states how long treated water keeps, and the INDEX says so.

When the household has not said when, there is **no reminder** — the honest answer, and the same
defect §FND-006's derived reminder exists to avoid. Canary #8 invents one from a default.

### One decision, one payload

The five Features are one household decision, so `WaterSafety` carries them together: the reading,
the advisory, the permitted methods with their steps and limits, a storage block per method, and the
reminder. The advisory is `water_alert`'s own string rather than a second wording — one fact on two
surfaces, and the copy that drifts is the one the mobile catalogue does not point at. Canary #10
makes it a second wording.

### Canaries

Fourteen canaries run against `tests/ci/canary_mon005.py` and all fourteen fire: boiling no longer led
with; chlorine offered on turbid water; the threshold moved onto the pretreatment figure; a method
offered with no stated limit; the steps ceasing to belong to the methods; the residual carried for
every method; the reminder losing its method; a reminder invented from a default; a method offered
with no storage advice; the advisory becoming a second wording; an unreadable time accepted; the
route ceasing to refuse one; a storage block naming another county; and a method left with an empty
step list.

**One canary was written wrong and fixed before it was trusted.** #14 first replaced the solar step
tuple with an empty one *and* introduced a name that does not exist, so the module failed at import
and the canary fired for a reason that had nothing to do with the assertion it was aimed at — a
mutation that breaks the import is a canary that never reached the test. It now leaves the enum
intact and empties only the table.

**Counts: 3 rows left `missing` — 3 to `carried` — 48 → 45.** 493 rows, `carried` 431, `missing` 45,
`deferred` 17.

**Sources.** `sources/water-treatment/` — WHO/FWC/WSH/15.02 *Boil water* (technical brief, 2015),
archived with its `pdftotext -layout` copy and both checksums; and WHO's *Results of Round II of the
WHO International Scheme to Evaluate Household Water Treatment Technologies* (2019), cited by name
and quoted verbatim in the code but **not** archived, which is recorded as a deliberate departure
from the two-copy rule in `sources/INDEX.md`. The boiling duration, the storage interval and the
SODIS exposure times are the repo's own and are named as such there rather than presented as WHO's.

## §MON-006 — a band that disagreed with its own index, and two hours nobody measured

§MON-006 lists five Features under "Air Quality Index". Three of them — "AQI for user's location",
"best times for outdoor activity" and "pollution source information" — were bullets with no carrier
at all. What existed was `air_alert`: a string, built from a raw PM2.5 figure the caller supplies,
branching on two cuts at 35 and 55 µg/m³.

The section is called *Air Quality Index* and there was no index. That is the first defect, and it is
not cosmetic. An index is the number a person can hold against a bulletin, the category a screen
prints, and the six-way scale the three bands were an approximation of — and the approximation was
wrong in a way that only shows up at the boundary.

**The band disagreed with the index it was standing in for.** 35 and 55 are the index's own category
boundaries arrived at by a different route, and not quite the same ones: the index crosses 100 at
35.5 µg/m³ and 150 at 55.5. So a reading of 35.2 was served an "AIR ALERT" beside an index that said
clean, and 55.2 was served an alert beside an index that said watch. Two answers to one question in
one payload. `AirQuality.band` is now read off `aqi` rather than off the raw figure, so the two cannot
diverge — `test_the_three_way_band_now_agrees_with_the_index_it_is_read_off` walks the four values
that used to disagree.

**The index is the EPA's, and the code says so.** WHO publishes guideline levels and interim targets
in µg/m³ and no AQI at all; the 0–500 scale, its seven PM2.5 bands, its six categories and its linear
interpolation are the EPA's, from `EPA-454/B-18-002`. `sources/INDEX.md` states this explicitly,
because a table presented as WHO's that is not WHO's is the attribution error the whole sources
discipline exists to prevent. The document's own worked example — 35.9 µg/m³ interpolating to index
102 — is asserted verbatim, which makes the arithmetic checkable against the source rather than
against itself. The truncation is the source's too: the band is chosen from the value truncated to
one decimal, which is why 35.45 lands in the band *below* the one it is nearer to.

**"Best times for outdoor activity" is a time of day because of what WHO says about exposure.** The
guidelines state that risk "is a product of the pollutant concentration and the time over which a
person is in contact with that pollutant", and that concentrations follow "the temporal pattern of
operation of outdoor sources (e.g. traffic) but also on indoor sources (e.g. the daily cycle of
cooking)". A household cooking on charcoal and a road at rush hour are both visible in an hourly
series and neither is visible in a daily mean. So `outdoor_window` takes `(hour, pm25)` pairs and
returns the cleanest hours — every hour at the best level, not one, because a person with a fixed
appointment at nine needs to know whether nine is inside the window.

**The window that is not there.** With no hourly series the window is *empty* and its advice says
why. Naming an hour from the single daily figure would be naming an hour nobody measured, which is
exactly the fabrication §MON-006's own Data sources clause — "Reference monitors where available;
low-cost sensor networks; satellite-derived estimates; crowdsourced visibility reports" — is written
against. The four other Features do not depend on the series, so a client without one still gets the
index, the advisory, the mask guidance and the source.

**"Pollution source information" is an exclusion and not a detection.** A monitor reads a
concentration and cannot read a source, so the field is `likely` and the method is what the evidence
rules out. The categories are WHO's own — road traffic, waste and agricultural burning, forest and
savannah fire, household fuel combustion — and the caller supplies the flags, because a market's
waste burning is something a county team reports and not something a PM2.5 number contains. With
nothing reported the list is empty and `evidence` says the source is not known. That is the honest
answer, and it is not a dead end: the advice says an unexplained high reading is often the one worth
reporting, rather than leaving a person with a number and no action.

**The mask text is the repo's own, and it says what a mask does not do.** WHO's guidelines
deliberately do not make this recommendation — individual-level measures are "addressed in another
document" — so what the source supports is the *absence* of a recommendation, not a wording. The text
therefore names N95/KN95, says a cloth or surgical mask helps much less, and states plainly that a
mask is not a substitute for staying out of the smoke. Guidance implying otherwise has somebody
standing in traffic smoke feeling safe.

**Counts: 3 rows left `missing` — 3 to `carried` — 45 → 42.** 493 rows, `carried` 434, `missing` 42,
`deferred` 17.

**Sources.** `sources/air-quality/` — WHO's *Global air quality guidelines* (2021), and the US EPA's
*Technical Assistance Document for the Reporting of Daily Air Quality* (EPA-454/B-18-002, 2018), each
archived with its `pdftotext -layout` copy and both checksums. `sources/INDEX.md` records per source
what it supports and what it does **not**: WHO gives no index and no mask recommendation; the EPA's
scale is the US one and its top row carries a footnote the lower rows do not.

**Canaries: 16/16 fired.** The truncation removed before the band is chosen; the top of the scale
extrapolated instead of capped; the reading and the index free to disagree; the index and the
category free to disagree; one hour named instead of every hour at the best level; the window
invented from the daily figure when no series exists; the hours left in the order they arrived; a
source asserted with no evidence; the mask text losing what a mask does not do; the advisory becoming
a second wording; the window ceasing to say when no hour is clean; the route dropping its required
location; the route dropping the hourly series; a window carrying an index with no hours; an unnamed
source passing the list check; and a day with no readings getting a window instead of a refusal.

## §LOC-005 — a schedule with nothing on the other end, and a language nobody read

§11.5 LOC-005 lists seven Features for the border and point-of-entry module. Four were carried. The
three that were not share a shape, and it is the shape worth naming: the module described a **plan**
and had no other end of it.

**The enrolment stated a schedule and no route accepted a report against it.** `TravellerEnrolment`
carried `report_schedule = [1, 3, 7, 14, 21]` and a message telling the traveller "we will ask how
you feel on days 1, 3, 7, 14 and 21" — and nothing in the tree accepted an answer. The schedule was a
notification plan with nothing behind it, which is worse than no schedule: it tells a person they
will be checked on. `LocationService.report_arrival_day` is the other end, and it enforces the two
things that make the promise real — the day must be one the schedule names, and the person must have
declared. A report on day 5 is refused rather than accepted, because accepting it tells a traveller
they were checked on a day nobody reads, and day 5 of a 21-day Ebola window is not a day to be
casual about.

The escalation rule is §MON-009's own, read off `MONITORING_ALERT_SYMPTOMS` rather than written a
second time: a traveller and a contact are the same person under the same criteria, and two lists
would drift on the day one of them was edited. `test_a_warning_sign_without_fever_escalates_too` is
the one that matters — a thermometer is not the only way into this, and it is the one a traveller
without one does not have.

**`TravelerDeclaration.lang` was accepted and never read.** The field was a claim: the advisory was
an English literal and the enrolment acknowledgement was an English literal, so a traveller crossing
at Busia who reads Kiswahili was served English on the one screen where getting it wrong means
arriving unwell and not knowing to call 719. The strings now live in `afya.strings` beside the triage
tables — the advisory, the enrolment acknowledgement, the daily prompt and both report outcomes —
and they fall back through §ACC-002's `answerable()` rather than through a second rule that agrees
today.

**The language set is the honest one, and that is the decision.** §ACC-002 requires six languages for
*voice-guided symptom reporting*; §LOC-005 asks for multi-language support for *cross-border
travellers*. Those are different requirements and this section does not close the other one.
`SUPPORTED_LANGS` is `{'en', 'sw'}` and stays there — `test_personas.py` pins Dholuo's absence as a
finding, and widening the set to make a count look better is exactly the failure mode that test
exists to prevent. So the traveller path has hand-written English and Kiswahili strings, serves
English to everything else **and says which language it got**, and its own catalogue offers only the
two it can answer in rather than a dropdown that promises Dholuo and delivers English.
`sources/INDEX.md` records this, including that the strings are not clinically reviewed or
back-translated.

**`BorderPost` described a queue and nothing about testing.** A post either has a mobile lab on site
or sends its samples onward, and a screen that could not say which is a traveller sent to a post that
cannot test them. `mobile_lab`, `lab_turnaround_hours` and `lab_tests` describe it, and a validator
makes the three move together: a turnaround with no lab is a promise from a post that cannot keep it,
and a test list with no lab is a menu for a service that is not there. The national *result* still
reaches a person through §REC-001's `LabResult` wallet document — the border screen is the entry to
that, not a second copy of it, which is why this is three fields on the post and not a result store.

**Counts: 3 rows left `missing` — 3 to `carried` — 42 → 39.** 493 rows, `carried` 437, `missing` 39,
`deferred` 17.

**Sources.** No new document is archived for this section, deliberately, and `sources/INDEX.md` says
why: the strings are the repo's own and no source states a Kenyan border advisory in Dholuo. What is
sourced is the language *set*, which comes from §ACC-002's `LANGUAGE_MATRIX` and its own six-language
list, both already in the tree.

**Canaries: 14/14 fired.** Any day accepted as a scheduled day; a report from an unenrolled person
accepted; a warning sign ceasing to escalate; the advisory ignoring its language; the enrolment
acknowledgement ignoring the declared language; the daily prompt ignoring it; the prompt answering
for any day; a lab turnaround allowed with no lab; tests allowed with no lab; the report route losing
its guard; the report route ceasing to refuse a bad day; a Kiswahili string losing its placeholders;
an unknown key returning a placeholder; and the fallback ceasing to go through `answerable`.

---

## §ACC-002 — a voice interface whose hard part was never built

§ACC-002 is five bullets, and the shape of the gap was the same in all of them: the tree had the
*shape* of a voice interface and none of its substance. `VoiceRequest` took an `utterance` — a
transcript — so every voice path in the repo began after the hard part was already done, and a
person who cannot type had no way in at all. `VoiceResult.on_device` reported offline recognition
that did not exist. The three bullets left `missing` were the three where that showed.

**Two closed, one deliberately left open.**

- **"Voice-to-text for CHW notes and case descriptions"** — `VoiceRequest.purpose` now separates the
  two questions one entry point was answering. `purpose='note'` makes the transcript the result and
  skips the intent map; the predecessor ran a dictation through the intent map, discarded it, and
  answered `intent=unknown`, so a CHW describing a household got nothing back. `CaseReport.voice_note`
  carries the transcript with the language it was said in, asserted paired. §COM-101's "voice-to-text
  notes in local languages" rides on the same field and closed with it.
- **"Voice note triage on WhatsApp"** — `WhatsAppIn.kind='voice'` reaches `route_whatsapp_voice`,
  which transcribes the note and puts the transcript through the *same* `transcribe` the typed path
  uses, so a spoken report and a typed one cannot diverge into two sets of rules. `route_whatsapp`
  now refuses a note by name rather than reading its media reference as a message body.
- **"Voice-guided symptom reporting in Swahili, Dholuo, Luhya, Kalenjin, Kikuyu, and English"** —
  **stays `missing`.** The reporting half is real now: `VOICE_SYMPTOM_WORDS` reads the symptoms out of
  free text rather than matching six intent keywords, so "fever and headache since Tuesday" no longer
  loses the headache. But the bullet names six languages and recognition ships for two. `LANGUAGE_MATRIX`
  carries `asr: False` for `luo`, `bxk`, `kln` and `ki`, and `SUPPORTED_LANGS` has tables for `en` and
  `sw` only. Widening either set to make the count look better is precisely the failure
  `test_personas.py` was written to prevent, and `test_acc002.py` inherits the pin.

**The recogniser is real, and it is not the obvious implementation.** `WhisperSpeechEngine` runs
whisper-tiny int8 through `onnxruntime` and numpy — no torch, no transformers, no tokenizers — the
same zero-dependency shape as §SENS-002's YAMNet. Two things were measured rather than assumed:

1. **The merged decoder's KV-cache branch is broken in this export.** It produces *confidently wrong*
   text — "After early morning, the" for audio saying "After early nightfall, the" — with cached and
   uncached agreeing for two tokens and then diverging. Re-running the full prefix each step costs
   ~0.35 s for a 30-token utterance, which is inside budget, so the cache is deliberately unused.
2. **The language is prompted, never detected.** A three-word utterance is too short to detect from,
   and a wrong guess produces a fluent transcript of the wrong words — worse than a refusal, because
   it reads like a successful recording. `transcribe` asserts the language is one the model was
   trained on and refuses otherwise.

**One correction, recorded because it nearly shipped as a false claim.** The module docstring and the
first version of canary #1 both stated that using `np.hanning` — the *symmetric* window, where
whisper uses the periodic one — yields a wrong transcript. Measured directly, both windows produce
the identical, correct sentence for `speech_en.wav`. The original garbage transcript had a different
cause (a truncated prompt), and attributing it to the window was wrong. The canary is now pointed at
the structural assertion that can actually fail (`periodic[1] > 0.0` fails for `np.hanning`), and the
docstring says what is true: the windows differ by one sample of phase, and this fixture does not
separate them.

**Counts: §ACC-002 3 `missing` → 1 — two closed, one held open deliberately.** Across the repo the
three flipped rows move the totals 437/39 → **440 `carried`, 36 `missing`**, 493 rows, `deferred` 17
unchanged. Two of the three are §ACC-002's; the third is §COM-101's "voice-to-text notes in local
languages", which rides on `CaseReport.voice_note` and moves that section 2 → 1.

**Sources.** `sources/whisper-asr/` archives the whisper paper (arXiv:2212.04356, 28 pp.) and OpenAI's
`mel_filters.npz`, both checksummed, with the `.txt` extraction beside the PDF. The INDEX entry states
what the paper supports — 16 kHz, 80-channel log-Mel, 25 ms windows, 10 ms stride, all of which
`preprocessor_config.json` mirrors and `speech.py` asserts — and what it does not: the window function
and the decoder merge strategy are read from the reference implementation, not the paper. The deployed
`mel_80.npy` is asserted byte-identical to the archived `mel_80`.

**Canaries: 16/16 fired.** The symmetric window; the language prompt dropped; a note triaged as a
symptom report; symptoms no longer read out of free text; the audio path transcribing without
triaging; `served_in` claiming the requested language; audio answered with no recogniser deployed;
the recogniser accepting a language it does not know; the six-language gap closed by widening the
table list; the voice dropdown offering a language recognition does not ship for; a voice note read
as a text body; the voice branch accepting a text message; the channel layer answering a note with no
recogniser; a voice note declaring no language; a case report carrying half a voice note; and the
audio route losing its guard.

**Two canary lessons.** Canary #9 looked for a literal (`frozenset({'en', 'sw'})`) that appears
nowhere — the definition is `frozenset(TRIAGE_RECS)` — and because the script asserts on a missing
target, it aborted the run and **canaries #10–#16 never executed**. A canary that crashes the runner
silently deletes every canary after it. Separately, the first green 16/16 was invalid: a syntax error
in the test file made collection fail, and a test file that does not import makes every mutation look
caught. The suite was re-run against a file that parses and reports zero collection errors.

---

## §SEC-003 — a standard stated in three places and applied in none

§SEC-003 is five Standards, three of which were `missing`. They shared one shape: the tree named the
control and applied it nowhere. `ENCRYPTION_STANDARD` was a string constant. `EncryptionPosture`
returned three hardcoded `True`s. `SqliteStore` wrote plaintext rows. §17.5's control table named the
*string* as the enforcer of the at-rest row, and a test asserted the three `True`s — so the claim and
its own absence were both pinned in the tree, and neither could be contradicted.

**All three closed, and the posture can now disagree with the design.**

- **"At rest: AES-256"** — `SqliteStore` seals its sensitive columns with AES-256-GCM, a fresh 96-bit
  nonce per value, and verifies the tag on open. The at-rest key persists in a `0600` sidecar beside
  the database. `EncryptionPosture.at_rest` reads `none` when no key is wired.
- **"Contact lists and location history: additional application-layer encryption"** — the datasets
  the section names by hand get a *second* key, and `CryptoService` refuses to be constructed with
  the two keys equal, because one key fitted twice is not two layers. The layer travels with the
  value, so a reader who takes the database and the at-rest key still cannot open a contact list.
- **"Cloud backup: end-to-end encrypted with user-held key"** — with a passphrase the wallet is
  sealed under a scrypt-derived key with a fresh salt per backup, the derived key is never stored,
  and the envelope reports `aes-256-gcm`/`user_held_key=True` with `documents` empty. Without one it
  still reports `none`/False. The two cases are distinguishable on the payload rather than both
  claiming the standard.

**The key-management row stays `deferred`, deliberately.** §SEC-003 names the Android Keystore and
the iOS Secure Enclave; a server-side Python process reaches neither. A sidecar key protects a copy
of the database file alone — a dump, a backup bucket holding only `.db` — and does not protect
against a reader with the whole directory, who has the key beside the ciphertext. That is a real
improvement on plaintext and is not the hardware-backed keystore, and the posture reports the
difference rather than letting AES-256 close it by implication. `docs/research/encryption-at-rest/`
records the decision and the rejected options.

**Two defects found by building it, both of which would have shipped.**

1. **A per-boot key silently destroys data.** The first wiring generated the at-rest key at boot. A
   restart then produced a new key and every stored row became unreadable — "encrypted" turned into
   "lost", which is worse than the plaintext it replaced. Caught by probing a restart directly; the
   key is now persisted and `test_the_key_persists_across_a_restart` pins it.
2. **`Scrypt` has no `maxmem`.** That parameter belongs to `hashlib.scrypt`, not
   `cryptography`'s `Scrypt`. Pyright caught it before the test did.

**The cipher was not hand-rolled.** The repo hand-rolled a PDF writer rather than add a library, so
the precedent was worth checking and it does not transfer: a PDF format is a data layout where a bug
is a malformed file, a cipher is a security primitive where a bug is silent. `cryptography` 50.0.2
is the only new runtime dependency; `pip-audit` reports no known vulnerabilities and `bandit` no
medium or high findings.

**Counts: §SEC-003 3 `missing` → 0.** Across the repo 440/36 → **443 `carried`, 33 `missing`**, 493
rows, `deferred` 17. §17.5's control table now names `CryptoService.seal` for the at-rest row instead
of the string constant.

**Canaries: 11/11 fired.** A sealed value losing its layer tag; contact lists losing their second
layer; the two keys allowed to be equal; the store falling back to plaintext under an encryption
label; the nonce ceasing to be fresh; the backup shipping the plaintext beside its ciphertext; the
posture asserting the design again; the at-rest key regenerated per boot; a passphrase ignored when
no crypto service is wired; a tampered ciphertext swallowed instead of raised; and a legacy plaintext
row ceasing to read back.

**A canary-runner fix carried over from §ACC-002.** The runner initially passed both test files'
node ids to every canary. A node that does not exist makes pytest exit non-zero on the *collection*
error, which reads as CAUGHT — a canary passing for the wrong reason, which is the failure the script
exists to prevent. Each canary now names the file its target lives in, and the runner raises if the
target did not run.

## §MED-002 — four hand-typed rows where a reference belonged, and a contraindication axis that did not exist

§MED-002's four `Features` bullets split two and two. "Select or scan two or more medicines" and
"Check for known interactions" were `carried`, because `check_interactions` existed and looked up a
pair. "Flag contraindications for pregnancy, children, and common conditions" and "Guidance to
consult a pharmacist" were `missing`, and both were missing for the same reason: there was no
clinical data behind either.

The interaction "table" was four rows typed into `service.py`:

	'warfarin|aspirin:major:additive bleeding risk',
	'metronidazole|alcohol:moderate:disulfiram-like reaction',
	'artemether|ketoconazole:moderate:QT prolongation',
	'rifampicin|oral_contraceptives:major:reduced efficacy',

and `check_interactions` returned `list[str]` — a shape with nowhere to put a contraindication, a
guidance line, or the name of a medicine the reference does not contain.

### The source, and why the `-layout` copy is load-bearing

The **WHO Model Formulary 2008** supplies all four axes from one authority: Appendix 1 (Interactions,
p. 503) for drug pairs, Appendix 2 (Pregnancy, p. 582), Appendix 3 (Breastfeeding, p. 599), and a
`Contraindications:` line in each of the ~250 monographs for the age and condition axes. It is
archived at `sources/who-model-formulary/` with its checksums and page references in
`sources/INDEX.md`, and the generator scripts are committed beside it under `tools/`.

Appendix 1 and Appendix 2 are two-column tables, and IRIS's own plain-text extraction of this
document interleaves the columns into unreadable runs. `pdftotext -layout` keeps them in order, which
is what makes the tables checkable against the code row by row rather than by eye.

### Three properties of the data that are not transcription

1. **The appendix lists each pair twice**, once under each drug: 2,853 rows reduce to 1,452 unique
   unordered pairs, and 1,370 appear under both. `lookup` keys on the unordered pair, so
   `['warfarin', 'aspirin']` and `['aspirin', 'warfarin']` are the same question.
2. **Seven pairs carry a different hazard marking in the two listings** — Clomipramine + Warfarin is
   `noted` under clomipramine and `hazardous` under warfarin. The table keeps the **more severe** of
   the two. Where a source disagrees with itself the disagreement resolves toward the warning, never
   away from it. (The plan for this work said 54; the emitter measures 7, and the emitted module
   states the measured figure.)
3. **The appendix's severity axis is two-valued, not graded.** Its own definition: "the symbol *
   indicates a potentially hazardous interaction … Interactions with no symbol do not usually have
   serious consequences." So a row is `hazardous` or `noted`, and `HAZARD_DEFINITION` carries that
   sentence because "noted" is not a reassurance. The dead `InteractionPair` model's invented
   `minor|moderate|major` pattern is gone.

### The two caveats that travel with the pregnancy axis

Appendix 2 says in its own words that **"Absence of a medicine from the list does not imply safety"**
and that "Drugs should be prescribed in pregnancy only if the expected benefits to the mother are
thought to be greater than the risk to the fetus." Both are served with every answer that asked about
pregnancy. Without them, a "no flag" result reads as reassurance for a drug the appendix simply does
not list — a claim the source explicitly refuses to make. A caller who did not say they are pregnant
has not asked the question, so the sentence is not volunteered about a patient whose state nobody
stated.

### The age axis is a floor the source states, not a dose

Twenty-one monographs state an age floor, some as a number ("children under 8 years", "infants less
than 3 months") and some as the bare word "children" or "neonates". A word is stored as `None` rather
than converted to a figure the source did not write — the same reason `afya.medicine.formulary`
leaves `max_mg_per_dose` empty where no maximum is stated.

### Two extraction defects, each invisible in the output

1. **Operator precedence in the header filter.** The running headers (the folio line and the section
   title repeated at the top of every page) were filtered by `'WHO Model Formulary 2008' in l or
   label in l and l.strip() != label`, which Python parses as `A or (B and C)`. Only the folio line
   was dropped; every section title was kept and appended to the comment above it, so
   `Not known to be harmful` acquired an `Appendix 2: Pregnancy` tail. It parses, it runs, and the
   only symptom is a sentence that reads slightly wrong.
2. **A name longer than its column.** Two Appendix 2 rows are typeset with a single space between
   the name and its comment, and one name — `Pentamidine isetionate` — is longer than the comment
   column, so neither a 2+-space rule nor the column position finds the boundary. A fixed `col - 1`
   split landed mid-word (`'Phenoxymethylpenicilli'` / `'n Not known to be harmful'`). The fix reads
   the source's own vocabulary: split at the longest leading substring that is a drug name the
   Formulary uses elsewhere.

Both are fixed in the committed generators, which regenerate both data modules **byte-identically**
(verified by `diff` after re-running them from the committed copies).

### Paracetamol is the row a window-based read gets wrong

Paracetamol's monograph has only `Precautions:` — no `Contraindications:` line at all — so it has no
condition or age flags and none may be invented for it. The first extraction attempt used a
fixed-size character window and attributed Propranolol's contraindications to paracetamol. The
extraction is now bounded by the *next field keyword* rather than by a window, and
`test_med002.py::test_paracetamol_has_no_contraindication_line_and_is_not_invented_one` pins it.

### What the answer looks like now

`check_interactions(drugs, pregnant=None, age_months=None, conditions=None) -> InteractionReport`,
serving `pairs`, `flags`, `unmatched`, `guidance`, `disclaimer`, `hazards` and `pregnancy_caveat`.
Refusals are answers, as `dose()` established: a name the reference cannot place comes back in
`unmatched` rather than raising, because "we do not know this medicine" and "these medicines are safe
together" are opposite claims and only one of them is safe to act on. `POST /medicine/interactions`
carries the three optional patient fields, and the mobile catalogue's `drug_interactions` action
gained `pregnant`, `age_months` and a `conditions` select whose options are the condition labels —
no spec feature code appears in any served string.

**Counts: §MED-002 2 `missing` → 0**, both now `carried` with refs that resolve through
`afya.refs.py`. Across the repo **443 → 445 `carried`, 33 → 31 `missing`**, 493 rows, `deferred` 17.

**Canaries: 10/10 fired.** The pair lookup made order-dependent; the hazard disagreement resolved
downward; an unmatched name silently dropped; the pregnancy caveat dropped; the pregnancy caveat
volunteered to a caller who never said they were pregnant; the age floor off by one band; a condition
firing without being named; the guidance line emptied; the route dropping the patient fields; and a
single medicine accepted where the section says two or more.

**One canary had to be rewritten.** The first attempt at the disagreement canary patched `lookup`'s
sort order, which does not change any hazard — the resolution direction is baked into the committed
table at emit time — so it MISSED. A canary that passes is a bug in the canary: it now flips the
actual `Clomipramine + Warfarin` row, and the test asserts that specific pair rather than only the
count.

## §MON-004 — a count where a time belonged, and a rule for a dataset nothing wrote

§MON-004 prints seven Features. Five had carriers; the two that did not failed in the two ways this
codebase keeps failing — the fact existed somewhere and nothing acted on it, or the fact existed and
was the wrong shape.

### `times_per_day` is a count, and a count cannot be notified at

"Multiple daily reminders" was `missing` for a shape reason. `MedSchedule.times_per_day` was `ge=1,
le=6` and there was no reminder *instant* anywhere in the system, so a client that wanted to wake
somebody for a twice-daily course had to invent both times — and two clients inventing them invent
two different days. The dose log would then disagree with the reminders that produced it.

`REMINDER_CLOCK` is a table of the 1–6 frequencies, each with its own 24-hour instants, and
`reminder_times(times_per_day)` reads it. **A table rather than arithmetic**, and the difference is
the whole point: dividing 24 hours evenly by six gives `04:00` as the first dose of a four-hourly
course, a time nobody chose, presented to a patient as the time to take a medicine. The table gives
`06:00/10:00/14:00/18:00/22:00/02:00` — four-hourly across a day, wrapping once at midnight, which is
what a four-hourly course is. The service derives the instants in `add_schedule` and overwrites
anything a caller supplied, and the route returns them with the schedule id: a schedule acknowledged
with its id alone is the count this bullet replaced.

### A conflict rule with no producer is a rule for a dataset nothing writes

"Works with no data connection" was `missing` for the other reason. `SyncService` already carried
`ConflictRule(dataset='medication', strategy=lww, rationale='Personal')` in `CONFLICT_RULES` — the
spec's own rule, in §16.3's table — and nothing in the codebase ever queued a `medication` op. A dose
could only be recorded through `POST /monitoring/medication/adherence`, so the highest-frequency
health action anyone takes was the one most likely to be logged with no bars and the one that could
not be.

`record_adherence` now records the dose locally and queues it, and the dataset name is read from the
spec's table rather than chosen at the call site, so the strategy applied on replay is §16.3's own.
The queue is a constructor argument and the **composition root** passes it — the same decision §MON-001
made about the wallet: a route that had to remember to queue would eventually forget, and the screen
would say the dose was recorded while the server never learned of it.

The dependency is a `typing.Protocol` (`SyncQueue`) rather than an import of `SyncService`, because
`sync` imports nothing from `monitoring` and a direct reference would be a cycle. It also lets a test
pass a queue that records what it was handed instead of standing up the whole sync service.

### The defect this work found

The queue is keyed on `op_id`, and the first version built it from the *head* of a UUID7:
`uuid7str()[:8]`. A UUID7's leading bytes are its millisecond timestamp, so two doses logged in the
same millisecond produce the same id and the second silently overwrites the first. Doses arrive in
bursts — a week of them replayed after an outage is exactly when the collisions cluster — so the
failure mode is losing adherence data at the moment the offline queue exists to keep it. The suffix
is the unique part; `CampaignNotice` already took its suffix for this reason.

It was caught by a test that counted two doses in the queue rather than checking one existed, and it
is now canary #7.

**Counts: §MON-004 2 `missing` → 0**, both `carried` with refs that resolve through `afya.refs.py`.
Across the repo **445 → 447 `carried`, 31 → 29 `missing`**, 493 rows, `deferred` 17.

**Canaries: 7/7 fired.** The instants divided out of 24 hours instead of read from the table; the
caller's own times honoured; the route answering with the id alone; the dose recorded and never
queued; the dose queued under a dataset with no conflict rule; the composition root handing the
tracker no queue; and the op id taken from the timestamp end of the uuid.

**One canary had to be rewritten, and the reason is worth keeping.** The first version of #1 patched
the table into arithmetic and MISSED — because the test it named checked only that the instants were
well-formed `HH:MM` strings, distinct and in order, and arithmetic satisfies all three. A canary that
passes is a bug in the canary, but the bug was in the *test*: it asserted the shape of the answer and
not the choice behind it. It now asserts the property `REMINDER_CLOCK`'s own comment gives — a
twice-daily course is a morning and an evening — which is the thing arithmetic cannot do.

## §REC-006 — a field nobody read, and a vocabulary that had to be looked up

§REC-006 prints five Features. Three had carriers; the two that did not failed from opposite sides
of the same table — one was a question the code answered for the wrong person, the other a word the
code had no word for.

### `match` answers the requester, and the bullet is about the donor

"Receive alerts when your blood type is urgently needed nearby" was `missing` while `match` was
fully implemented, tested and routed. The two statements are not in tension: `match` answers *who can
I call*, ranked, and returns it to the facility that asked. The bullet is the other direction — *my
group is needed, here* — and no path in the codebase told a donor anything. The tell was the request's
own `urgency` field: `routine|urgent|critical`, carried on `BloodRequest`, validated, and read by
nobody. A field that decides nothing is a feature that decides nothing.

`donor_alerts` makes urgency decide two things, and both are decisions rather than filters:

- **`URGENCY_REACH` widens the counties, in hops** — 0 for the request's own, 1 for the counties
  that touch it, 2 for the counties that touch those, over §INF-001's adjacency table. This is what
  makes the alert *nearby* rather than *local*: a county hospital short of B+ calls Kiambu because a
  donor an hour away is a donor, and calls Nakuru because a donor three hours away still beats no
  unit at all. The walk returns each county's distance, so `distance_counties` is what the search
  already computed rather than a second `if` that would drift from it.
- **`URGENCY_DEPTH` widens the groups.** A `routine` need notifies the exact group in its own county
  and nobody else. A routine request is met from the stock list; waking a donor for it spends the one
  thing a donor list runs on, which is their willingness to be woken.

Two rules bound it. **An ineligible donor is not alerted** — the 90-day interval is a safety rule
about the donor, not a supply rule, and an alert is an invitation to break it; the check is the same
`_eligible` that `match` and `record_donation` use, so the three cannot disagree about one donor. And
**an incompatible donor is not alerted** — an A+ donor cannot be given to a B+ patient, and bringing
someone in to be turned away is worse than not calling them, because it spends the same goodwill the
first rule protects.

Each alert carries both `requested_group` and `donor_group`. They are usually different groups: a B+
patient can be given O- blood, so most alerts go to a donor whose group is not the one on the request,
and "B+ is needed" and "your O- can be given to a B+ patient" are different sentences. A donor told
only the first has to work out whether it applies to them.

### A word the code did not have, and the source that has it

"Find donation centres" was `missing` for the bluntest reason: `PlaceKind` had eight members and none
of them was a donation centre, so no route could list one and no import could carry one.

The vocabulary is not invented. OpenStreetMap documents **two** kinds, and documents them as different
things — `healthcare=blood_donation` is "a facility where you can donate blood, plasma and/or
platelets", `healthcare=blood_bank` is where donated blood "is stored and preserved for later use in
blood transfusion". Both are archived at `sources/osm-healthcare-tags/`. Two members rather than one
because a storage site is somewhere the blood already is, not somewhere a donor can go: a finder that
collapsed them would put a place a donor cannot use at the top of a distance-sorted list.

`donation_centres` therefore defaults to `blood_donation` alone and offers `blood_bank` only when it
is named — the same reasoning §FND-003's `test_type` filter applies to a test a facility does not
offer. The label comes from `DONATION_SITE_KINDS` rather than from the caller, so the two cannot be
presented as one.

**The key is the part that would have gone wrong silently.** The donation tags live under `healthcare`,
not `amenity` — `amenity=blood_donation` is not a value OSM defines, and the wiki page for it 404s.
An Overpass query written against `amenity` returns the empty set while appearing to work, and a
parser reading only `amenity` drops every site the query found: a zero that looks like "Kenya has no
donation centres" rather than like a bug. The query and the parser are asserted against each other
for that reason, and canary #7 reproduces exactly that shape.

### The defect this work found, twice

The first version of `URGENCY_REACH` was `{'routine': 0, 'urgent': 1, 'critical': 2}` read as a
**boolean** — nonzero meant "also the counties that touch it". So `urgent` and `critical` reached
byte-identical sets and the table's top row was a value that decided nothing: the same defect the
bullet was about, `urgency` carried and read by nobody, reintroduced one level down. A live probe of
the route showed the two responses differing only in the word `Urgent`/`Critical` inside the message.
Reading the number as **hops** and walking breadth-first fixes it — `critical` now reaches Nakuru,
which does not touch Nairobi, and `Murang'a`, which is two hops out — and a test asserts the three
values are distinct, so the table cannot silently collapse again. Canary #9 patches the walk back to
one hop and is the one that would have caught it.

The second was in the *test*, and it is the same class of bug the §MON-004 canary had. Canary #1
flattens `URGENCY_REACH` so every request reaches the neighbours, and it MISSED on the first run: the
fixture had no exact-group donor in a neighbouring county, so widening the reach changed nothing the
test looked at. The canary was fine; the test was asserting depth while claiming to assert reach.
Adding a B+ donor in Kiambu — one the *routine* case must not wake and the *urgent* case must — made
the table's first row testable at all. A gate that cannot fail for the reason it names is not testing
what it says.

A third thing the gates found, which is a control working rather than a defect: `test_ui_vocabulary`'s
unguarded-write check failed on the new `POST /blood/alerts`. It is a POST because the request is a
body, not because it writes — it computes the alerts and stores none — so it went onto the named list
with that justification, beside `/blood/match`, which is the same shape.

**Counts: §REC-006 2 `missing` → 0**, both `carried` with refs that resolve through `afya.refs.py`.
Across the repo **447 → 449 `carried`, 29 → 27 `missing`**, 493 rows, `deferred` 17.

**Canaries: 9/9 fired.** The urgency tables flattened to full reach; the reach walk stopping after one
hop; the depth table flattened so a routine request reaches every compatible group; an ineligible
donor invited to donate; an incompatible donor alerted; the finder defaulting to both kinds; the two
place kinds collapsed into one; the importer reading only the `amenity` key; and the route forgetting
the adjacency table.

## §MON-007 and §MON-008 — a notice with no category, and a season that was a field name

Both sections are Tier 3 and both were three-quarters built. §MON-007's `vector_risk` decided the
rain band, `report_breeding_site` routed a report and `rvf_alert` fired for livestock-adjacent
households; §MON-008 had aflatoxin and recall alerts, `NUTRITION_BY_AGE` for infant feeding and its
local-food lists for the recipe bullet. The four `missing` rows were the two in each section that
*reach a person* — a notice nobody published and a reminder nobody scheduled; a season with no data
behind it and a place kind that did not exist.

### §MON-007: a category the feed did not have, and two reminders nothing scheduled

**"larviciding campaign notifications"** failed because there was nowhere to put one. The audit row
was precise: "the alert feed has no vector or larviciding category and `AlertKind` carries none".

Two things follow from that sentence, and the second is the one that decides the design. A feed
category is not free: `FEED_PREFERENCE` maps every category to a §ALT-003 preference, and
`tests/ci/test_realtime.py` asserts the two sets are equal — so a twelfth category with no
preference behind it is a notice published into a feed no subscriber can match. The preference
already existed. §ALT-003's Options list has nine entries and one of them is "County alerts", which
is exactly what a larviciding round is: a county operation over named habitats on named days, whose
audience is everyone living around them rather than an age band. So `vector_control` maps to
`county_alerts` and **`TOGGLEABLE` is deliberately not widened** — a twelfth switch would be a
preference the section never printed, and `test_no_new_toggle_was_invented_for_it` asserts the
length stays 11.

`AlertKind` was left alone for the same reason from the other side. A larviciding round is not a
community hazard; it is an operation. Filing it as an alert would have made the hazard vocabulary
carry something that is not one, and the feed is the surface that already carries operations
(`immunisation` campaign notices, `service` status).

**The supplement rule is appended, not trusted.** The WHO manual is unambiguous — larviciding
"should never be seen as a substitute for ITNs or IRS in areas with significant malaria risk" — and
a county notice is exactly the document in which that sentence goes missing, because the round is
visible and the nets are not. `publish_larviciding` appends `SUPPLEMENT_RULE` to the caller's body
rather than validating that the caller included it: a body that must contain a sentence can be
written without one, and the failure mode is a resident who stops using a net. Canary #1 drops the
append and is the one whose failure mode is a malaria case.

**"personal protection reminders"** failed on the word *reminder*. `VectorRisk.advise` already said
"drain containers, use nets every night" — as text, on a screen, once. A reminder needs a time, and
nothing produced one.

`ProtectionReminder` schedules both acts, and the two are not the same kind of act:

- **The net is a nightly habit**, and the manual fixes when: biting is "between dusk and dawn (and
  especially during the early hours of the morning)", with `An. gambiae` and `An. funestus` peaking
  "an hour before dawn". So `net_due_iso` is the next dusk, and a reminder asked for *after* dusk
  rolls to tomorrow — otherwise it fires in the past, which on a device means it fires immediately,
  telling a person to go to bed at the moment they are already up.
- **Draining containers is habitat manipulation**, which the manual calls "a recurrent activity",
  and its interval is `LARVICIDE_INTERVAL_FLOOR_DAYS` — derived as `min` over `LARVICIDE_CLASSES`
  rather than typed. A household is then asked to clear standing water at least as often as a county
  would re-treat the same water, and a class added to the table with a shorter interval moves the
  household's date without anyone editing a second constant.

The message varies with the rain band, and that required a refactor worth naming: `vector_risk` had
the four bands inline as a chained ternary and `protection_reminder` needs the same four. A second
copy is a second definition, and the two would eventually disagree about where `wet` starts — which
is the difference between "keep using your net" and "drain the containers now". `_rainfall_band` is
now the one definition, and `test_the_four_rain_bands_are_one_definition` walks the seven boundary
values through *both* callers.

### §MON-008: a field name with nothing behind it, and a kind OSM does not have

**"Seasonal food availability"** is the clearest example in the audit of a name that reads as a
feature. `NutritionGuidance.seasonal_foods` existed and `NUTRITION_BY_AGE` filled it — with fixed
lists that do not vary by season. The seasonal half was the field's name.

The FAO Crop Calendar for Kenya is machine-readable, and `SEASONAL_FOODS` is **generated from it
rather than typed**: 29 crops with a stated harvest month, plus the 5 the source flags `all_year`,
each row carrying the source's own French crop name beside the English label. The generator is at
`/tmp/afya_extract/crops.py` and the table is reproducible from the archived JSON — which is the
point of the second column. A translation asserted by position alone is unverifiable; `Fève, vert`
beside `Broad bean` is checkable.

Two limits are the source's and are recorded rather than papered over:

- **The data is disaggregated by agro-ecological zone** and carries no national month, so a month in
  the table means "harvested this month somewhere in Kenya". That is the right granularity for a
  national app and the wrong one for county advice.
- **Avocado, mango, banana, amaranth and fish are absent from the data entirely** — and
  `NUTRITION_BY_AGE` names avocado and small fish. They are therefore absent from the seasonal table
  rather than given invented months, and the module comment says so.

`in_season` is a **separate field**, not a replacement for `seasonal_foods`. The existing pinned
assertions at `test_monitoring.py:209,211,214` still hold, and that is the correct outcome rather
than a test that needed relaxing: a parent is making two different decisions — what to feed this
child, and what to buy this week — and a merged list cannot say which entry was which. Canary #4
merges them.

**"therapeutic feeding programme locations"** failed for the bluntest reason: no vocabulary. The
audit row named `PlaceKind` and `FacilityKind`, and neither had a member.

OpenStreetMap has **no tag** for a therapeutic feeding centre or a malnutrition treatment site. That
was established three ways rather than assumed: the `healthcare` key's 31 values include only
`healthcare=nutrition_counselling`, which is dietary counselling and not treatment; the `amenity`
key's feeding values are all animal feeding (`feeding_place` is for livestock); and a live taginfo
search for `malnutrition` returns no structured keys. So a place vocabulary had no source while the
national clinical guideline has one.

`IMAM_PROGRAMMES` carries Kenya's own three programme types with the guideline's definitions —
`OTP`, `SC`, `SFP`, from its abbreviation list — and they are served as the **national vocabulary,
not as a per-site claim**. The registry records *that* a facility is a therapeutic feeding site and
not which of the three it runs; a per-row claim invented from nothing would send a child with
complications to an out-patient queue, because the guideline is explicit that an OTP treats severe
acute malnutrition *without* complications while an SC admits those with them, or an infant under
six months. Canary #10 collapses the vocabulary to a single per-site claim.

The kind went to `FacilityKind`, not `ServiceOffered`. That enum's own docstring is §FND-001's
printed list of seven, closed, and a nutrition programme is not one of the seven — widening it would
make the finder offer a service the section never printed.

### What the canaries found

Two things, and the second is a test defect rather than a code one.

The first was mechanical: three canary targets were **not unique**. `for county in notice.counties:`
appears twice in `monitoring/service.py` — once in §MON-001's `publish_campaign` and once in the new
`publish_larviciding` — and the assert-unique guard caught it before the patch applied to the wrong
function. The guard earning its keep is the whole reason it exists; a canary that patches the wrong
copy tests nothing and reports CAUGHT.

The second: canary #11 of the §MON-008 set — the site label emptied to the bare slug — **MISSED on
the first run**, and the test was wrong, not the canary. `test_the_three_programmes_travel_with_every_site`
asserted `site.label == THERAPEUTIC_FEEDING_LABEL`, which is a constant compared with itself: it
agrees whatever the constant says, so a label emptied to `'therapeutic_feeding'` passed it. The
assertion was about a field's *presence*, not its content, which is the shape §MON-004's canary
found in its own fixture. The fix is `test_the_site_label_is_a_sentence_and_not_the_internal_slug`,
which pins the content — a sentence, naming the condition, not the slug. This is the same lesson
twice in two sections: **a gate that cannot fail for the reason it names is not testing what it
says**, and the only way to know is to watch it fail.

### Counts

**§MON-007 2 `missing` → 0** and **§MON-008 2 `missing` → 0**, all four `carried` with refs that
resolve through `afya.refs.py`. Across the repo **449 → 453 `carried`, 27 → 23 `missing`**, 493 rows,
`deferred` 17 unchanged (the flips go to `carried`, not `deferred`).

Five sources archived with both checksums in `sources/INDEX.md`: the WHO larval source management
manual, the FAO Crop Calendar for Kenya, the FEWS NET seasonal calendar, the Kenya IMAM guideline,
and the WHO/UNICEF/WFP/SC CMAM joint statement. The joint statement is archived as provenance and
explicitly **not** as the source of any served string — it writes "therapeutic feeding centre" only
descriptively — and `sources/INDEX.md` says so, so the citation is not read as carrying more than it
does.

**Canaries: 23/23 fired** — 11 for §MON-007 and 12 for §MON-008. The supplement rule dropped from
the published body; the round filed under the wrong feed category; every item addressed to the first
county; the reach filter inverted; the net reminder anchored at an arbitrary hour; a reminder asked
for after dusk firing in the past; the container interval hand-typed; the rain band threshold
shifted; the message collapsed to one string; the bad instant accepted; the publish route dropping
its county scope. And: the all-year flag ignored; the month filter inverted; a month outside the year
accepted; the two food lists merged; the finder filtering on the wrong facility kind; the finder not
ordering by distance; the county filter dropped; the limit ignored; an empty county raising instead
of answering; the programme vocabulary collapsed to a per-site claim; the site label emptied to the
bare slug; and the nutrition route dropping the month.

## §REC-003 — two fields nobody read, and a checklist that was an annex

§REC-003 prints eight Features, and the audit read them as four: the last five are written with a
semicolon, and the parser split prose lists on the comma alone. So "MUAC; percentile charts;
undernutrition alerts; feeding guidance by age; milestone checklists" was **one bullet**, and four of
the eight things the section asks for sat inside a cell named after the first of them. That is the
finding underneath the finding — the audit reported four bullets and carried four of eight, and the
one row it raised named a run of five clauses in a single cell, which is a row nobody can act on.

The parser now splits on `[;,]`, and the claim that makes that safe is a test rather than a comment:
`test_the_only_semicolon_list_in_the_spec_is_the_one_that_was_read` asserts §REC-003 is the only
prose list in the spec written with a semicolon, and that the eight items come back with none of them
still carrying one. A separator added to a parser is a change to every section the parser reads, so
its jurisdiction is asserted; canaries #15 and #16 watch it fail in both directions — the split
reverted to the comma, and the split widened past the prose branch into the bullets, where §LOC-002's
"Opt-in only; can be disabled at any time" is one privacy property and its rationale and would become
two bullets the section does not print.

### The two genuine gaps were the same shape

**Head circumference** and **MUAC** were both `missing`, and both were the shape §REC-006's `urgency`
field was: `GrowthRecord` carried `head_circumference_cm` and `muac_mm`, they were written, and
nothing read them. The audit note had rotted in the other direction — it claimed no head-circumference
field existed — which is why the rows were re-derived from the code rather than from the note.

Both now score against WHO tables archived for the purpose: head circumference-for-age (0–60 months,
`L == 1` on every row, so the ordinary standard score) and arm circumference-for-age (**3**–60
months, `L` never 1 and crossing zero, so the Box-Cox form is required). The extraction was checked
against the source rather than read off it: all four tables' L/M/S columns were recomputed to WHO's
own printed −3 SD … +3 SD columns, **238 rows, 0 disagreements** at 0.05 cm. `growth_standards.py`
now holds 484 rows across five indicators and its assert loop walks all five.

Three things came out of the sources that are decisions rather than code:

- **Two vocabularies, not one.** WHO's z-score answers *how far is this arm from the reference
  median*; Kenya's IMAM Table 1.5 answers *which programme is this child admitted to*. `classify_muac`
  is deliberately not `classify`, and the two are served in separate fields. The IMAM table's own
  footnote says where its cut-offs come from — "*Anthropometric criteria based on WHO Child Growth
  Standards (2006)" — which is exactly the reason they must not be collapsed: the numbers are
  Kenya's, the reference population behind them is WHO's, and one is not the other.
- **Two age floors that do not coincide.** WHO's arm standard starts at 3 months; IMAM's MUAC
  admission rule starts at 6 (Table 1.5 is scoped "children 6 to 59 months" and the guideline refers
  an infant below that to Section 3, its inpatient protocol). Between them a child has a z-score and
  no category. That is the correct answer and it is reported as such rather than one standing in for
  the other. Canary #4 applies the admission rule where the guideline refers the infant elsewhere.
- **`None` is not 0.0.** An absent head measurement stays `None`; defaulting it to a z-score of 0
  would report an unmeasured child as exactly average, which for a screening field is the dangerous
  direction. Canary #3 is that one line.

`MUAC_ALERTS` carries the guideline's admission rule in the words a caregiver is given, and it has
**no `normal` entry on purpose**: a lookup that returns a message for a healthy child turns the
absence of a finding into a finding. Canary #6 softens the severe alert to advice to watch, which is
the one direction it may not fail in.

### Milestone checklists were an annex, and the annex has a rule that is easy to collapse

The last bullet had no carrier because there was no milestone table anywhere in the tree. There is
one in the archived IMAM guideline: **Annex 9**, eight age bands and 30 milestones under ASSESS, with
a three-outcome CLASSIFY chart. `MILESTONES` reproduces the bands and the milestone wording verbatim —
the label is the sentence a caregiver is read — and `RecordsService.milestone_check` applies the rule:

- **DELAY** — absence from the current band *and* absence from an earlier one, **or** a regression.
- **ALERT** — absence from the current band alone.
- **NORMAL** — every current-band milestone present.

The precedence is the part that collapses silently. Canary #9 makes every current-band gap a delay,
which refers a child who is merely late on one skill; canary #10 drops regression from the rule,
which is the criterion a series of checklists cannot catch and the one the guideline names in its own
right.

Two properties of the annex are recorded because both are miscounts waiting to happen: the bands
**meet at their endpoints** (0–2 and 2–4 both name month 2), and the 0–2 month band lists **only two**
milestones where every other band lists four. I asserted 32 on the first pass; the annex says 30 and
the annex was right.

**`checked_earlier` is a design decision the source forced.** Annex 9's DELAY rule needs a gap in an
earlier band, and a caregiver asked only about the child's own age group supplied no evidence about
the others. Reading that silence as absence classifies *every* child as delayed — a false positive in
the direction that sends families to a clinic — so the earlier bands are counted only when the caller
says they were checked, and `earlier_checked` travels on the report so the answer says what it did
and did not look at. Canary #11 counts them unasked.

### What the live probe found, which no test had

Both defects came from `curl` against a dev server, and neither was reachable by a unit test over
the service — which is the argument for probing the front door rather than reasoning about it.

**A re-weigh at the same age was a 500.** `record_growth` files a wallet document and `add_document`
asserts its `doc_id` unique — correctly, because a wallet that overwrote a document on a repeated id
would lose the earlier one at the moment a retry happened. The id was `growth-{member}-{age}`, so a
child weighed at twelve months who comes back a fortnight later, still twelve months, was an
`AssertionError` at the front door with the first visit already stored. It was unreachable until this
work, because the route called `growth_flag`, which files nothing; the moment it started calling
`record_growth` the collision became the ordinary path. A re-weigh is not a retry — a retry sends the
same measurement, and this sends a different one the chart has to plot — so the id carries a
per-member visit sequence. Canary #18.

**The checklist read as a finding about a child nobody had assessed.** The read half serves the list
a caregiver answers against, and it classified an empty answer set through the same classifier, so
every current-band milestone came back missing and the status was `alert` — "One or more skills for
this age are not there yet." That sentence, served before anyone has looked at the child, is Annex
9's ALERT read as a result rather than as the instruction to go and assess. It is exactly the failure
`checked_earlier` guards against, one level up: silence about a child is not evidence about the
child. `status` gained a fourth value, `unanswered`, and the guidance with it; the missing list is
still served, because the list *is* the checklist. Canary #17.

### What the canaries found

Three MISSED on the first run, all three a defect in the test rather than in the canary:

- **#8, the arm z-score read with the normal form** — the test only asserted the table's `L` values,
  so forcing `L = 1.0` at the call site passed it. The fix computes the Box-Cox and normal results at
  11 cm / 12 months, asserts they differ by more than 0.01, and asserts `muac_z` matches the first and
  not the second. A test that reads a constant is not a test that the constant is used.
- **#11, the earlier bands counted unasked** — the test drove only the checked case and never
  asserted the negative. The fix asserts `report.missing_earlier == []` on the unchecked report. This
  is the same shape as §MON-008's label canary: an assertion about a field's presence where the
  finding is about its content.
- **#13, the guidance collapsed to one sentence** — the test compared the `MILESTONE_GUIDANCE` dict
  with itself, so patching the *report* to always serve `'normal'` passed it. The fix drives all three
  classifications and asserts the served guidance equals the dict entry for the status that came back.

The pattern across all three is one line: **assert the value that was served, not the constant it was
served from.** A constant compared with itself agrees whatever the code does with it.

The canary harness itself gained a guard this round: a nonexistent node id makes pytest exit non-zero
on a *collection* error, which reads as CAUGHT, so the script now collects both test files first and
asserts every canary names a test that exists.

### Counts

**§REC-003 2 `missing` → 0**, all eight bullets `carried` with refs that resolve through
`afya.refs.py`. Across the repo **453 → 459 `carried`, 23 → 21 `missing`**, 497 rows, `deferred` 17
unchanged.

Four WHO table files archived with both checksums in `sources/INDEX.md`, and the growth-standards
section now records what the two new tables do and do not support — the arm table's 3-month floor,
the `L == 1` property of head circumference, that neither is a percentile chart, and that the IMAM
cut-offs are a different instrument with a different age floor. The IMAM section gained the Table 1.5
cut-offs, Section 3's under-six-month protocol, and Annex 9 with its two easy miscounts, plus one new
line under "what the source does not support": the annex states **no threshold** for how far behind a
child may be, so no severity grade is invented for a missing milestone.

**Canaries: 18/18 fired.** The head circumference not read; the MUAC read in millimetres; an
unmeasured child scored as average; the IMAM category applied below six months; the moderate band off
by a tenth; the severe alert softened; the head z-score computed from the arm table; the arm z-score
read with the normal form; every current-band gap a delay; regression dropped; the earlier bands
counted unasked; an unknown milestone counted as absent; the guidance collapsed to one sentence; the
growth route reverted to the one-word flag; the semicolon list read as one bullet; the semicolon
split reaching the bullets; the unchecked checklist reading as an alert; and a re-weigh at the same
age filing a duplicate document.

---

## §INF-005 — a country half that was a constant, and a link that was a sentence

§INF-005 is five Features, one of them `missing` and three of the four `carried` ones disclosing a
gap in their own note. All four turned out to be the same shape: **a claim with no table behind it.**

### The country half was a constant, and the county half had no carrier

`LocationService.advisory(destination, origin_country)` interpolated its two arguments into one fixed
paragraph. Kampala, Kinshasa and Kinshasa-from-Nairobi were answered identically — a traveller asking
whether it was safe to cross at Busia got a sentence that would have read the same had the outbreak
been in another hemisphere. That is the `missing` row, and the fix is `afya/location/advisories.py`:
a table built strictly from WHO's own v4 rapid risk assessment and the two Disease Outbreak News
notices.

**The table is short because the source is short, and that is the finding.** WHO publishes a band per
*group of countries* — the DRC very high, "countries sharing land borders with the DRC" high, the rest
of the African Region and the world low — and then names three countries individually inside the high
band ("Uganda, the Central African Republic and South Sudan are of particular concern"). It does not
enumerate the DRC's land-border states. **Burundi shares a land border with the DRC and has no row in
either source**, so `COUNTRIES` carries exactly seven rows and the test asserts Burundi, Rwanda and
Tanzania resolve to *nothing* rather than to the regional band. Reading Burundi's band off "rest of
the African Region" would be the single most consequential invented number in this unit: the regional
band is about the Region, and the land-border band is where Burundi actually sits.

**Kenya is `not_assessed`, and it is the row the whole section is for.** DON619 says in its own words
that "a detailed rapid risk assessment is currently ongoing to assess the risk in Kenya and will be
reported once available". Kenya sits inside the "rest of the African Region" band, and reading it off
that band answers `low` about the country the advisory is served in. `not_assessed` and `unknown` are
refusals, not bands: `BAND_LABELS` renders both as "not assessed", and WHO's own caveat — that a
country with no row "has not been assessed in this notice — that is not the same as being assessed as
low risk" — travels on every report. Same shape as §MED-002's pregnancy caveat.

**The county half had a carrier the whole time, just not in this module.** The row said it had none.
`CountyRisk` already holds a per-county band with a stamp and a source, and §INF-001's dashboard route
already serves it; `LocationService` now takes that read as a collaborator (`CountyRiskRead`, a
`Protocol`) and `_county_advisory` returns `None` for anything that is not a Kenyan county so the
caller falls through to the country table. A second table here would be the copy that goes stale the
first time a county office publishes a risk level.

The two halves use **different vocabularies** and the overlap between them is why `kind` is not
decoration. A country carries WHO's `very_high|high|low|not_assessed`; a Kenyan county carries
`low|moderate|high`. They share `high` and `low` — and "high" for Uganda is WHO's land-border band
while "high" for Busia is a dashboard reading. `PlaceAdvisory.band` accepts the union so one model
serves both tables and `kind` says which table a row came from, so a client cannot render the union
as one scale and let a reader rank a Kenyan county against the DRC.

### "What to do if you feel unwell" was one sentence

The advisory ended "if you feel unwell after arrival, call 719 and say where you travelled" — one of
five things the sources say, and the only one a Kenyan reader already knows. `POST_TRAVEL_STEPS` now
carries five: 21 days of monitoring and "seek medical care immediately" from CDC, the symptom set from
WHO's fact sheet, and the 719 call and the arrival declaration as this deployment's own operating
rule. **Each step carries its `source`**, because three are quoted from an authority and two are ours,
and `STEP_SOURCES` says so in the served payload rather than presenting five instructions as one
voice. `TRAVELLER_RISK_NOTE` carries CDC's own counterweight — the viruses "pose little risk to
travelers or the general public" — because a reader who saw only the bands would conclude the
opposite.

### The MON-009 link was a message string

"21-day self-monitoring enrolment for travellers (**links to MON-009**)" linked by *saying so*: the
acknowledgement named days 1, 3, 7, 14 and 21 while `MonitoringService` had never heard of the
traveller, so `/monitoring/contact/{ref}/diary` answered an empty list and no day was ever logged.
`self_declare` now calls `self._monitoring.enrol(...)`, and `TravellerEnrolment.diary_linked` reports
whether it did — a deployment with no monitoring service wired says `False` rather than promising a
schedule nothing will ask about. The officer is deliberately not passed: a traveller is not a contact
of a named officer, and inventing one would put a stranger's name on a 21-day record.

### What the canaries found

One MISSED on the first run, and it was a defect in the test rather than in the canary. **Canary #1
replaced the source's own sentence with an empty string while leaving the band in place** — and the
test passed, because it compared two destinations' bands and never asserted the sentence reached the
paragraph. A paragraph that carried a band and dropped the sentence behind it still differs between
two countries while leaving a reader with a number nobody can check. The fix asserts
`row_for('Uganda').stated in uganda.advisory`. It is the same shape as §REC-003's three: **assert the
value that was served, not the constant it was served from.**

**13/13 fired.** The advisory paragraph back to a constant; Kenya served as `low`; an unassessed place
labelled as low risk; the not-assessed caveat dropped; an unknown place resolved to a band; the county
half given its own table; the county row stamped with WHO's assessment date; the WHO travel advice
dropped; a deployment rule relabelled as CDC's; the traveller risk note dropped; the enrolment no
longer reaching the monitoring service; `diary_linked` reported true with nothing enrolled; and a band
from neither table accepted.

### What the live probe found, which no test had

The declaration route and the diary route are wired together in `build_services` and not in the
service — `LocationService` takes the monitoring service as a constructor argument, so a unit test
that builds both by hand proves the call and proves nothing about the deployment. The front door is
the only place that shows it: `POST /location/traveller/declare` then
`POST /monitoring/contact/day` then `GET /monitoring/contact/{ref}/diary` returns `[3]`. The test
drives all three through `create_app(build_services(...))` for exactly that reason, and asserts
`diary_linked is True` on the response — the field is what makes the link checkable rather than
inferred from a message string.

### Counts

**§INF-005 1 `missing` → 0**, all five bullets `carried` with refs that resolve through
`afya.refs.py`. Across the repo **459 → 460 `carried`, 21 → 20 `missing`**, 497 rows, `deferred` 17
unchanged.

Five source files archived in `sources/who-ebola-outbreak-news/` with both checksums in
`sources/INDEX.md`, and the new section records what the sources do and do not support — that WHO
bands *groups* rather than countries, that it does not enumerate the DRC's land-border states
(Burundi has no row), that Kenya's assessment was still running, and that the 719 line and the
declaration are this deployment's own.

The `sources/INDEX.md` table gained the five directories that had a `##` section but no row —
`air-quality`, `county-adjacency`, `ebola-transmission`, `helpline-directory` and `water-treatment`.
The sections were all present and the table, which is the list a reader checks against `ls sources/`,
under-reported the archive by five. It is the internal-link checker's defect in a different file: a
table that enumerates some of the ways a source is recorded reports a gap as closed.

---

## §LOC-001 — a bracket that named nothing, and an exit that did not exist

`docs/spec.md:1026-1040` (Tier 1 / Tier 4). One row was `missing` and one half of the feature had no
carrier at all.

### The Alert content: `[specific location]`

The row was not missing because the sentence was absent. `/surveillance/geofences-at` emitted a
near-verbatim line inline, so the sentence existed — and the section's own bracket, `Avoid [specific
location]`, was served as **"avoid the named location"**. That is the one action the sentence asks a
person to take, asked of a place the sentence declined to name. It is the same shape as a gate that
passes on a known-bad input: the output looked right, and the one field that carried the meaning was
the one nobody had.

The sentence now lives in `afya.strings.GEOFENCE_ALERT_STRINGS` and `[specific location]` resolves
through `zone_place`, in three steps, because a zone can be registered before anyone has named it:

1. the zone's own `place_label`, when the county health authority set one;
2. the zone's `county`, when it did not — `Geofence.place_label` is optional, and a registry row
   that knows only its county should narrow to the county rather than to a phrase that names nothing;
3. the section's own words, said plainly, when the registry knows neither.

`Geofence` gained both `place_label` and `county`. The second is what makes the fallback a place
rather than a placeholder, and it is the field the alert narrows to.

### The half that did not exist: entry *and* exit

Tier 4 asks the system to "alert on entry **and exit**". Nothing derived a crossing from a position:
`geofences_at` answered which zones contain a point, and every caller was left to diff that against
its own last answer. Two things were missing, and the second is the one that makes the feature
usable:

- **A zone is an event, not a reading.** `ZoneWatch.inside` records which zones the last check found
  the person in, so someone crossing a 5 km zone is told once on the way in and once on the way out
  rather than on every GPS fix. An alert that fires per fix is one people turn off, and a turned-off
  alert is the whole feature gone.
- **An exit is not an all-clear.** The exit line names the place that was left and says the 21-day
  watch that started on entry is still running. A client that rendered one sentence for both
  directions has told someone leaving an outbreak zone the same thing it told them entering.

**The exit can name a zone the registry no longer returns**, and this is why `_seen_fences` exists:
a zone is left by walking out of it, so the registry's answer for the current point does not contain
it. An exit built from that answer alone could not say *which* place was left. The device keeps the
fence it announced — the zone, never the coordinates — so a departure and a county lifting the zone
are both reported to the person who was told about it.

### "Fully disableable" does not mean blind

The Privacy line is "Only entry/exit events logged, and only with consent", and the switch is what
makes it checkable rather than asserted. With alerts off the crossing is **still reported** — the
person standing in a zone is owed that warning — and `logged` is `False` and `inside` is not written.
Serving nothing at all would make the privacy control cost the person the one warning the feature
exists to give, which is the shape a privacy-minded implementation ships and nobody reports as a bug.

The switch is a **stored decision**, not a request parameter: `POST /location/zone-alerts/{subject}`
sets it and the route reads it. A client that sent `enabled=true` with each position fix would be
asserting the person's consent on their behalf.

### What the route gate found

The unit first shipped a single route, `/surveillance/geofences-at`, taking an optional
`subject_ref`. `tests/ci/test_self_scope.py` refused it: a `subject_ref` on a route that does not
compare it to the token is an IDOR, and the gate reported `GET /surveillance/geofences-at (None)` as
a personal-data route without a subject-binding guard. The gate was right and the route was split:

| Route | Guard | Subject |
|---|---|---|
| `GET /surveillance/geofences-at` | open | none, by design — nothing about the caller is recorded |
| `GET /location/zones/{subject_ref}` | `require_self` | the token's own, and the answer depends on their consent |
| `GET`/`POST /location/zone-alerts/{subject_ref}` | `require_self` | the switch itself |

`test_mobile_catalogue.py`'s client-supplied check caught the second half of the same mistake: the
mobile action marked its `subject_ref` `client_supplied=True` on a route that no longer bound one.
The catalogue now carries two actions, one per route, which is the honest shape — they are two routes
with two guards.

### What the canaries found

Nothing missed, and the first run's 13/14 was a defect in a test rather than in a canary. **Canary #10
("the switch is read from the request")** replaced `logging = watch.alerts_enabled` with
`logging = watch is not None`, and the test passed — because its subject had **no watch at all**, so
"the person opted out" and "this subject has never been heard of" were the same branch. The test now
creates the watch and turns it *off* before checking. It is the §REC-003 shape again, and the same
lesson: a fixture that cannot distinguish two states cannot test the difference between them.

The live probe then found one no unit test had: **the entry message printed the section's sentence
twice**, because the `entry` template restated the clause the alert already opens with. A unit test
over `alert` cannot see it — the field was correct and the composed message was not. `message` is now
asserted to equal `alert` on entry.

`logged`/`not_logged` were in the string table and served by nothing, which is the defect this repo's
audit hunts in code. They are now `ZoneEvent.privacy_note` — the Privacy line addressed to the
person rather than only checkable in a payload, with both answers served, because a feature that said
only the reassuring half would be describing a consent decision as a preference.

**18/18 fired.** The place collapsed to the placeholder; the county fallback naming nothing; a blank
label counting as a label; the exit dropping the place it left; an exit reading as an all-clear; the
alert emitted per position fix; the crossing recorded with alerts off; alerts off going blind; the
anonymous caller remembered; the switch read from the request; the alert served in the asked-for
language; the window retyped on the client; the route reverted to the zone list; the open route
growing an unbound subject; the guarded route and the switch route each stopping binding the token;
the entry message saying it twice; and the privacy note going one way.

### Counts

**§LOC-001 1 `missing` → 0.** Across the repo **460 → 461 `carried`, 20 → 19 `missing`**, 497 rows,
`deferred` 17 unchanged.

**No new source directory.** The unit introduced no new external fact: the 21-day window is the WHO
fact sheet's incubation range already archived under `ebola-transmission/` ("varies from 2 to 21
days"), the alert's wording is the specification's own, and the 719 line is this deployment's as it
is everywhere else. The reasoning is recorded in `sources/INDEX.md` under that section so the absence
of a new directory is not read as a missing citation — a source left unarchived and a source that was
never needed look identical from the outside.

## §ALT-002 — a button that only worked in the app

`docs/spec.md:1382-1391` (Tier 3). One row was `missing`, and the feature it names is the one that
matters most in the week the network is what broke.

### "Works over SMS when data is unavailable"

The audit row said it precisely: `/alerting/family/check-in` was HTTP only, `SafetyCheckIn.channel`
accepted `sms`, and **nothing in the product ever sent or received one**. So the failure was not a
missing screen. Every screen looked right — the button existed, the board existed, the model had a
field for the channel — and the half of the feature that exists for the outage had no carrier at all.
`SafetyCheckIn` was a model with no writer anywhere in the repo, which is the same shape as
`InteractionPair` and the §LOC-001 `privacy_note`: a type the design anticipated and the
implementation never reached.

Both directions were built, and they fail differently.

**Outbound.** `AlertingService.check_in` now texts every member who has not answered, through §5.3's
channel service, so §18.8's zero-rating is resolved at the moment a check-in message is sent by the
same rule as every other message. Three properties are load-bearing:

- **The check-in is written before the fan-out.** A carrier that refuses everything still leaves the
  board correct: the person *is* safe whatever the gateway did with the text, and a check-in lost
  because an SMS failed would be the button failing at the moment it matters.
- **A member who cannot be reached is named, not counted.** `sms_sent` and `sms_unreachable` are the
  split §EMG-001's SOS dispatch already draws, and it is the same reason: "told your family" for two
  deliveries out of four is the failure the split exists to prevent. The deployment routes the
  identity model's answer through `_sms_dialable`, so a Nairobi landline lands in `unreachable`
  rather than being handed to a gateway that will drop it.
- **`notify=False` still composes the message.** `sms_body` is the message, not the receipt —
  `sms_sent` is what says whether it went — so a board that carried an empty string whenever nothing
  was sent would leave a client rendering a blank line where the confirmation belongs.

**Inbound.** `/integrations/telco/sms/inbound` routes a body carrying a safe word to
`check_in_by_msisdn`, which resolves the sender's number to a subject through §5.4's identity model
and files the check-in against their group. It is a branch in the route rather than in
`route_whatsapp` because that router is §CHAN-3's WhatsApp keyword map and is **synchronous** — a
check-in records state and texts the family, which is I/O, and a sync router cannot await it.

### Three answers, not a boolean

The first shape was `any(k in body.lower() for k in SMS_SAFE_KEYWORDS)`, and it had a defect the
tests did not catch until one was written for it: **"I am not safe" contains "safe"**, so a substring
test files it as a check-in — telling a family their relative is accounted for on the strength of a
message that says the opposite. That is the one error here worse than silence.

`afya.alerting.service:safe_intent` returns `check-in`, `negated`, `third-party` or `none`, and each
of the three non-check-in answers is a different reply rather than a silent drop:

- **A negation is not a check-in, and it is not nothing either.** The live probe found what the
  fall-through did: "I am not safe" matched no keyword, went to §CHAN-3's map, and was answered with
  **the welcome menu** — a person saying they are in danger, handed a list of options. It now gets
  the 719 line. The word before the keyword is read, and a glued negation is read too, because
  Kiswahili puts the negative inside the verb (`hatuko salama`, `hatusalama`) and English does it in
  one word (`unsafe`).
- **A message about somebody else is not the sender's check-in.** "My brother is safe" marks the
  *sender* safe under any keyword test, and no keyword list can tell a relayed message from a
  first-person one — so it is answered with a question instead of being filed. The same error as the
  negation, one step removed.
- **An unlinked number is told it is unlinked.** An SMS that gets no answer is indistinguishable
  from a network that dropped it, so every branch answers.

Two more that the first shape got wrong, both caught by a test written for the purpose:

- **A group named that is not the sender's** was filed against their own. `SAFE NAIROBI` from a
  person in one group landed in that group — two families told the wrong thing at once. The name is
  now checked against every group on record, which is the difference between "named nothing" and
  "named a stranger's".
- **A person in two groups** was guessed into whichever sorted first. They are asked which.

The check-in record is now the model that anticipated it: `SafetyCheckIn` is written on every
check-in, with `channel` recording `sms` or `native`. That is what makes the SMS leg auditable after
the fact — a deployment asked to show the feature works without data can show which check-ins arrived
that way, and a board storing only a timestamp could not. The id is derived from subject and instant,
so a gateway retry or a queued resend is one check-in and not two on a board whose whole purpose is
counting who is accounted for.

`at_iso` on the route is now optional and defaults to the server clock. The field exists so a queued
check-in can carry the instant it was actually made, **not** so every person has to have one — the
mobile catalogue marked it required, which meant a question the server can answer itself standing
between a person and the button.

### Gates

`tests/ci/test_self_scope.py` and `tests/ci/test_mobile_catalogue.py` each caught a real defect in
the first shape, and both were the same mistake seen from two sides: the check-ins route carried a
`subject_ref` that was not compared to the token. The route is now self-bound and filtered to the
caller — a check-in carries a subject and an instant, which together are a log of who is where.

**20/20 fired.** A member who cannot be reached counted as told; a landline texted; one dead leg
silencing the rest; the check-in lost when the text fails; `notify=False` emptying the message;
the message naming the members; the reply speaking the asked-for language; a negation read as a
check-in; a negation falling through to the welcome menu; a third-party message filed as the
sender's; an unlinked number silently ignored; a stranger's group name filed as their own; a
two-group sender guessed into one; a retried message becoming two check-ins; the SMS check-in
stopping reaching the fan-out; the route dropping the check-in branch; the route claiming the triage
intents; the check-in record losing its channel; and the two routes each stopping binding the token.

Two canaries were **MISSED** on the first run and both were the canary's fault, not the gate's: one
patched a string that had moved, and one named the wrong node — the `notify=False` mutation is caught
by the *body* assertion, which the named test did not make until it was strengthened. Same lesson as
§LOC-001's canary #10: a canary that passes is a bug in the canary.

### Counts

**§ALT-002 1 `missing` → 0.** Across the repo **461 → 462 `carried`, 19 → 18 `missing`**, 497 rows,
`deferred` 17 unchanged.

**No new source directory.** The strings are this deployment's own copy — the specification names the
feature, the button and the SMS channel, and prints none of the sentences — and the GSM7 constraint
is a property of the SMS standard rather than of a document. The reasoning is recorded in
`sources/INDEX.md` beside §LOC-001's, for the same reason: so the absence of a citation is not read
as an omission.
