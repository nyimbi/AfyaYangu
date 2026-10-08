# Engineering Buildout Map (spec § → module → tests)

| Spec area | Module | Tests |
|---|---|---|
| §7 tiers, App. B features | `src/afya/registry/` | `test_registry.py` |
| §5 CHAN-000..006 | `src/afya/channels/` (SMS GSM-7 segmentation, USSD FSM, WhatsApp router, radio/CHW/push) | `test_channels.py` |
| §8.1 TRI-001/002/003 + §6.3 malaria trap | `src/afya/triage/` | `test_triage.py` |
| §8.2 FND-001..006, §18.5 MoHF | `src/afya/facilities/` | `test_facilities.py` |
| §8.3 MED-001..004, §18.7 PPB | `src/afya/medicine/` (port + stub fallback + interaction table + dosing) | `test_medicine.py` |
| §8.4 EMG-001..003 | `src/afya/emergency/` (SOS fan-out port, IMU fall detection, offline card) | `test_emergency.py` |
| §8.5 INF-001..006, §6 content harmony | `src/afya/info/` (decision tree, county dashboard, hotlines) | `test_info.py` |
| §9–10 REC-001..003, EPI, growth | `src/afya/records/` | `test_records.py` |
| §16 offline sync, conflict matrix | `src/afya/sync/` | `test_sync.py` |
| §11/§19.4 Tier-4 surveillance | `src/afya/surveillance/` (z-score signal, geofences, PET store, activation gate) | `test_surveillance.py` |
| §17 DPA 2019 / ODPC / DHA 2023 | `src/afya/privacy/` (consent ledger, DPIA gate, RBAC, anonymize, 72h breach) | `test_privacy.py` |
| §18 ADaM/JALI/PHEOC/PPB/MoHF | `src/afya/integrations/` (httpx adapters) | `test_integrations.py` |
| §15.5 API | `src/afya/service.py` (FastAPI) | `test_app.py` |
| Native clients | `ios/` (SwiftUI), `android/` (Kotlin) | xcodebuild + gradle assembleDebug |

Known gaps (tracked): persistence layer is SQLite adapter; production Postgres/Timescale (asyncpg) swap of same Protocol pending; §19.1 TFLite/ONNX model assets not present — Tier 4 ML stays dormant by design; spec.md appendices C–D reconstructed (source truncation); hotline codes unverified per spec's own verification note; Android BackendClient context-bound paths lack JVM tests (pure-logic extraction or Robolectric pending).

Buildout increments (2026-10-08): mobile feature screens shipped on both platforms — iOS (Finder/Wallet/Diary/CHW tabs, xcodebuild+XCTest 5/5 green) and Android (FeaturesActivity with FND-001/REC-001/TRI-002/CHAN-005/sensor-ingest sections, APK assembled); server-side sensor ingestion with band engines (tier4-gated, raw-payload rejection); AT SMS REST + WhatsApp Business clients (HTTP-tested) with env-driven ServiceConfig; en/sw i18n (USSD menus, triage recommendations); CHW task assign/open/done + AT USSD callback endpoints; wallet aggregate endpoint.