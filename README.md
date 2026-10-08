# Afya Yangu / Mlinzi

**A national health companion for Kenya with dormant outbreak superpowers.**
Public-facing brand: **Afya Yangu** (*My Health*) · Product codename: **Mlinzi** (*Guardian*).

Source of truth: [`docs/spec.md`](docs/spec.md) (v2.0 — Kenya MoH / PHEOC-facing product spec: 7 channels, 4 feature tiers, 9 sensor subsystems, DPA 2019/Digital Health Act 2023 privacy architecture).

> ⚠️ The spec carries its own verification note: epidemiological figures, hotline codes and platform specifics must be validated against MoH/PHEOC official channels before external use.

---

## What this repository is

A **working vertical implementation** of the spec:

- **Backend core** — Python 3.11+/FastAPI/Pydantic v2 service layer implementing every product domain: feature registry & tier model, channel contracts (SMS/USSD/WhatsApp/radio/social/CHW/native), triage (with the **malaria trap** rule), facilities, medicine registry, emergency, content, family health wallet, offline-first sync, Tier-4 surveillance, privacy (consent/DPIA/RBAC/breach), vendor gateway clients, and on-device-provenance ML engines.
- **Fully native mobile apps** (owner decision, 2026-10-08 — supersedes the spec's Flutter row): **SwiftUI for iOS** and **Kotlin for Android**, zero external app dependencies, speaking the same REST contract, offline-first with persistent local caches.
- **PostgreSQL schema + adapters** and **SQLite adapters** on the same persistence Protocol.

**Not contained here**: vendor credentials (telco/WhatsApp Business/PPB), MoH-sourced clinical content corpora, and production ML training assets — each has a coded seam (`docs/ml-models.md`, `docs/buildout.md`).

---

## Repository layout

```
docs/
  spec.md            product spec v2.0 (Appendices B–D reconstructed after a source truncation)
  buildout.md        spec § → module → test map + remaining gap ledger
  ml-models.md       ML engine descriptions, provenance, decisions
src/afya/
  service.py         FastAPI app assembly (30+ endpoints), build_services(), env-driven config
  config.py          env-driven ServiceConfig (AT/WhatsApp/PPB/JALI/PHEOC/MoHF/PG DSN)
  strings.py         en/sw string tables (USSD menus, triage recommendations)
  ids.py             UUID7 helpers    logmixin.py  _log_* logging convention
  registry/          45-feature catalog (Appendix B), tier model, Tier-4 activation gate
  triage/            TRI-001 (malaria trap) / TRI-002 (21-day diary) / TRI-003 (gated)
  facilities/        FND-001..006 nearest/ED-status/booking, MoHF ingestion
  medicine/          MED-001..004 PPB port, interactions, dosing, stock crowdsourcing
  emergency/         EMG-001..003 SOS fan-out, fall detection, offline card
  info/              INF-001..010 content (harmony-tagged), decision tree, hotlines
  records/           REC-001..003 wallet, EPI gaps, growth flags, med reminders
  channels/          C HAN-000..006 SMS GSM-7 segmentation, USSD FSM + AT callback, WA router, CHW tasks
  sync/              §16 offline queue, conflict matrix, backoff
  surveillance/      county signals, geofences, PET store, breath-rate estimation, tier-4 gate
  sensors/           derived-metric ingestion: respiration/cough/fall/PPG/sleep/PM2.5 (raw rejected)
  evidence/          SENS-004 photo+note: sha256 verify, mime whitelist, 8 MB cap, dedupe, tier-4 gate
  privacy/           consent ledger, DPIA gate (blocks raw-sensor retention), RBAC, 72h breach, anonymize
  ml/                YamnetCoughEngine (SENS-002) via ONNX runtime
  persistence/       schema.sql + PostgresStore (asyncpg) + SqliteStore — same Protocol
ios/                 SwiftUI app (xcodegen project.yml → AfyaYangu.xcodeproj)
android/             Kotlin app (AGP 9.0, Gradle 9.8)
models/cough/        yamnet.onnx + class map (fetched from HF)
tests/ci/            109 pytest tests incl. contract tests over real HTTP (pytest-httpserver)
examples/            deploy_schema.py (PG), demo.py (end-to-end narrative)
```

---

## Quickstart

### 1. Backend

```sh
uv sync                                   # creates .venv from pyproject.toml
uv run pytest -vxs tests/ci               # 109 tests
uv run pyright                            # strict types: 0 errors
uv run uvicorn afya.service:app --port 8000
# → http://localhost:8000/health  /features  /docs (OpenAPI)
```

Optional persistence:

```sh
createdb afya && uv run python examples/deploy_schema.py     # Postgres (local server)
AFYA_DB_PATH=/tmp/afya.db uv run uvicorn afya.service:app    # SQLite adapter
```

Env vars (all optional): `AFYA_DB_PATH`, `AFYA_PG_DSN`, `AT_API_KEY/AT_USERNAME/AT_BASE_URL` (Africa's Talking zero-rated SMS), `WHATSAPP_TOKEN/WHATSAPP_PHONE_ID` (Meta Cloud API), `PPB_URL`, `JALI_URL`, `PHEOC_URL`, `MOHF_URL`.

### 2. iOS (native SwiftUI)

```sh
cd ios
xcodegen generate                                        # regenerates AfyaYangu.xcodeproj from project.yml
xcodebuild -project AfyaYangu.xcodeproj -scheme AfyaYangu \
	-destination 'generic/platform=iOS Simulator' build CODE_SIGNING_ALLOWED=NO
xcodebuild test -project AfyaYangu.xcodeproj -scheme AfyaYangu \
	-destination 'id=<simulator-udid>' CODE_SIGNING_ALLOWED=NO
```

App surfaces: Status (health/tier-4 state), FND-001 Finder, REC-001 Wallet, TRI-002 Diary, CHAN-005 CHW console, SENS-004 Evidence upload, TRI-001 triage chips, 719 SOS.

### 3. Android (native Kotlin)

```sh
cd android
gradle :app:testDebugUnitTest assembleDebug
# APK → app/build/outputs/apk/debug/app-debug.apk
```

App surfaces mirror iOS: MainActivity (triage/SOS) → FeaturesActivity (finder/wallet/diary/CHW/sensor ingest) → EvidenceActivity (photo + note).

Both clients default to `http://localhost:8000` (Simulator/emulator loops back to a locally running backend).

### 4. End-to-end demo

```sh
uv run python examples/demo.py    # USSD menu → malaria-trap triage → SOS → offline sync → tier-4 activation → TRI-003 unlock
```

---

## Key API surfaces

| Route | Purpose |
|---|---|
| `GET /health` · `GET /features` | liveness + registry (tier-4 features absent when dormant) |
| `POST /triage/preliminary` · `/triage/evd` · `/triage/diary` | febrile triage (malaria trap), gated EVD triage, 21-day diary |
| `POST /sensors/ingest` · `/sensors/breath/estimate` · `POST /ml/cough/analyze` | derived sensor metrics, LiDAR breath estimation, YAMNet cough verdict (tier-4 gated) |
| `POST /evidence` | photo + textual note (multipart, sha256-verified, deduped) |
| `POST /facilities`·`/facilities/nearest`·`/{id}/ed-status`·`/{id}/booking` | facility layer |
| `POST /medicine/verify`·`/interactions`·`/dose` | PPB-backed medicine layer |
| `POST /emergency/sos`·`/fall`·`/card/qr` | emergency layer |
| `GET /records/{ref}/wallet`·`/{ref}/immunisation-gaps` | family health wallet |
| `POST /channels/sms`·`/ussd`·`/whatsapp`·`/ussd/callback`·`/channels/chw/tasks…` | channel layer (zero-rated SMS, AT USSD callback CON/END, CHW assign/open/done) |
| `POST /sync/ops`·`/sync/flush` | offline-first queue |
| `POST /privacy/consent`·`/privacy/dpia` | privacy layer |
| `POST /tier4/activate` · `/surveillance/*` | dormant outbreak superpower |

OpenAPI: `http://localhost:8000/docs`.

---

## Architecture invariants (enforced by tests)

1. **Tier-4 is dormant by default.** Activation requires all three: PHEOC authorization, reviewed DPIA, feature flag. The engine checks the gate — not just the router.
2. **Raw sensor data never reaches the server.** Models reject raw payloads structurally; only derived metrics pass.
3. **Local write always succeeds; UI never blocks on the network** (§16.1). Both mobile clients keep last-good responses in persistent storage and degrade visibly to cached state.
4. **The malaria trap (§6.3).** Febrile illness without contact history is treated malaria-first; EVD escalation requires exposure/contact or a full symptom cluster.
5. **No unharmonised content is ever served.** The INF library refuses while any item lacks a provenance tag.
6. **Evidence integrity.** Photo blobs are stored only after sha256 matches the declared hash; duplicates dedupe on receipt.
7. **DB-level safety.** Postgres schema carries CHECK constraints (dataset allowlist, geo bounds, retention bounds) that tests prove fire.

---

## Verification gates (per change)

```sh
uv run pytest -vxs tests/ci   # backend contracts
uv run pyright                 # static types
cd ios && xcodebuild test ...  # XCTest
cd android && gradle :app:testDebugUnitTest
```

Current state: **109 backend tests green · pyright 0 errors · iOS XCTest green · Android JVM tests green · APK assembles.**

---

## Governance and honest-gap ledger

See [`docs/buildout.md`](docs/buildout.md) for the full §→module→test map and [`docs/ml-models.md`](docs/ml-models.md) for model provenance/decisions. Deliberately *not* faked: vendor credentials, MoH content corpora, dermatology classification (no validated model exists — evidence pipeline + clinician review instead), and heavy statistical models (transparency over opacity per §19.3).

History note: the original repo skeleton (JS/Swift/Kotlin sketches) never compiled and was removed after a full assessment; git history preserves it. This buildout replaced it spec-first.