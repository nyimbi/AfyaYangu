# Afya Yangu / Mlinzi

National health companion (Kenya) — backend core + fully native mobile apps per `docs/spec.md` v2.0.

## Layout

| Path | What |
|---|---|
| `docs/spec.md` | Source-of-truth product spec (v2.0; tail truncated — see buildout notes) |
| `src/afya/` | FastAPI backend core: registry (tiers/features), triage, facilities, medicine, emergency, info, records, channels, sync, surveillance, privacy, integrations |
| `ios/` | Native SwiftUI app (Xcode 27); project generated from `project.yml` via xcodegen |
| `android/` | Native Kotlin app (AGP 9.0, Gradle 9.8); zero external deps, HttpURLConnection |
| `tests/ci/` | pytest suite (contract tests incl. pytest-httpserver for vendor HTTP) |
| `legacy/` | — removed; pre-buildout JS/Swift/Kotlin sketches live in git history |

## Verify

```sh
uv sync
uv run pytest -vxs tests/ci
uv run pyright
uv run uvicorn afya.service:app --port 8000   # then apps hit http://localhost:8000

cd ios && xcodegen generate && xcodebuild -project AfyaYangu.xcodeproj -scheme AfyaYangu \
	-destination 'generic/platform=iOS Simulator' build CODE_SIGNING_ALLOWED=NO
cd android && gradle assembleDebug   # app/build/outputs/apk/debug/app-debug.apk
```

## Stack decisions (supersede spec §15.2 where noted)

- **Backend**: single Python FastAPI service (spec's Node Fastify row consolidated here — one runtime for API + ML pipeline).
- **Mobile**: fully native SwiftUI (iOS 17+) + Kotlin (minSdk 24) — **replaces the spec's Flutter row** per owner decision (2026-10-08).
- Offline-first contract (§16) implemented in both clients: local cache never blocks UI; sync opportunistic.
- Tier 4 dormancy enforced server-side (PHEOC authorization + DPIA + feature flag, all three required).