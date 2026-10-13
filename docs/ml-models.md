# ML Models — Descriptions & Decisions

Status: 2026-10-08 · Owner: engineering buildout · Source spec: `docs/spec.md` v2.0 §14/§15.2/§19

## Registry matrix

| ID | Capability | Engine today | Provenance | Tier gate | Files |
|---|---|---|---|---|---|
| SENS-002 | Acoustic cough/respiratory sound detection | **YamnetCoughEngine** (`src/afya/ml/cough.py`) | **YAMNet** ONNX, AudioSet 521 classes — fetched from HuggingFace `audiomagic/yamnet-onnx` (Apache-2.0 per repo LICENSE) | **Tier 4** (dormant until PHEOC+DPIA+flag) | `models/cough/yamnet.onnx` (16 MB), `models/cough/yamnet_class_map.csv` |
| SENS-004 | Rash/red-eye/pallor photo triage | **No classifier — deliberately.** Photo + textual note → `POST /evidence` (sha256-verified, deduped) → clinician review | No derm/rash ONNX exists on HF; `google/derm-foundation` is a TF-SavedModel *embeddings* model (~300 MB), not a classifier | Tier 4 for EVD-symptom kinds; scene photos Tier 1 | — (evidence pipeline instead) |
| SENS-003 / EMG-002 | Fall detection | Deterministic physics rule: **near-zero-g freefall window (<2 m/s²) strictly before impact spike (>25 m/s²)** | No credible HF asset for IMU fall detection; rule is correct-by-construction and unit-tested (impact-without-freefall rejected) | Tier 1 | — |
| SENS-005 | PPG heart-rate banding | Deterministic bands (HR 45–120 bpm, watch 55–100) | No HF PPG classifier of value; derived-metric contract stands | Tier 2 | — |
| SENS-001 | Respiration | **`estimate_breath_rate()`** peak-window counting on the *on-device-derived* chest-motion series (§14.1 LiBre pipeline split: estimation stays on-device, server bands 12–25 br/min) | No HF asset (LiBre is paper + reference code, no deployable ONNX) | Tier 4 | — |
| SENS-007/008 | Sleep / ambient PM2.5 | Deterministic bands | No HF assets | Tier 2/4 | — |
| AI-PRED (§19.2) | Server-side early-signal prediction | Weekly z-score signal (`weekly_signal`) + county risk bands | Statistical, transparent by design (spec §19.3 forbids opaque public-health risk scoring) | Surveillance | — |
| ACC-002 | Multilingual voice — speech-to-text for symptom reports and CHW notes | **WhisperSpeechEngine** (`src/afya/ml/speech.py`) | **whisper-tiny** int8 ONNX, from HuggingFace `onnx-community/whisper-tiny`; front end per Radford et al. arXiv:2212.04356; Mel filterbank from OpenAI `whisper/assets/mel_filters.npz` (MIT) | Tier 1 for `en`/`sw`; no recognition for the other four languages the bullet names | `models/speech/encoder_model_quantized.onnx` (10 MB), `decoder_model_merged_quantized.onnx` (31 MB), `tokenizer.json`, `mel_80.npy` |

## Decisions (and why)

1. **YAMNet as the cough backbone.** Chosen off HF after an API-verified search (`filter=onnx`); it is small (16 MB), CPU-fast, runs zero-dependency via `onnxruntime`, and the AudioSet map gives respiratory-relevant classes for free. Score threshold 0.30/frame; temporal clustering (consecutive frames) yields events, not just detections.
2. **Tier-4 gating is enforced *at the engine*, not only at the API.** `analyze(..., tier4_active=)` raises before inference when SENS-002 is dormant, so the model physically cannot produce an EVD signal without the three-party activation (PHEOC authorization + reviewed DPIA + feature flag).
3. **No dermatology model, deliberately.** A wrong "not-EVD rash" verdict is a public-health hazard (spec §6.2 false-reassurance risk). The clinically defensible path: on-device photo capture + sha256-verified submission + human triage. If MoH later curates a validated derm set, `EvidenceService` is the seam to hang evaluation on.
4. **Raw data never leaves the handset (§17.2).** Every server-facing contract accepts *derived* metrics only: motion series (not depth frames), respiration *rate* (not audio), cough *counts* (not audio). Enforcement is structural (`extra='forbid'` models + raw-field name blacklists + tests).
5. **Input contracts are strict, error paths are mapped.** 16 kHz mono enforced (422), asset-missing (503), dormant (403) — verified end-to-end live; no silent fallbacks.
6. **Engine parity.** Band semantics (cough/respiration/PPG/fall) are implemented identically three times — server (`sensors/service.py`), Swift (`SenseBands.swift`), Kotlin (`SenseBands.kt`) — so mobile inference never disagrees with server classification about what counts as "alert".
7. **On-device port is a drop-in.** The same `yamnet.onnx` + class map go into both app bundles via onnxruntime-mobile; engine API already mirrors `SenseBands` contracts. Not yet wired in-app.
8. **Whisper-tiny for speech-to-text, decoded without its KV cache.** §ACC-002's voice path needed
   an actual recogniser, not a keyword map, and the export runs on `onnxruntime` alone — no torch, no
   transformers, no tokenizers, the same zero-dependency shape as YAMNet. Two findings are recorded
   in `speech.py` because they are not in any doc: **(a)** the merged decoder's `use_cache_branch`
   path produces *confidently wrong* text ("After early morning, the" for audio saying "After early
   nightfall, the") — cached and uncached agree for two tokens then diverge — so every step re-runs
   the full prefix, ~0.35 s for a 30-token utterance; **(b)** the language is *prompted*, never
   detected, because auto-detection on a three-word utterance is a coin toss and a wrong toss is a
   fluent transcript of the wrong words. `canary_acc002.py` pins both.
9. **Heavy NLP/MT not adopted.** `Helsinki-NLP/opus-mt-en-sw` exists but is PyTorch-only (~300 MB, no ONNX port) and wrong-sized for USSD/WhatsApp latency budgets; keyword routing + content seed serve the bots. Revisit if MoH ships a validated en/sw clinical corpus.

## Verification

```sh
uv run pytest -q tests/ci/test_ml_cough.py          # engine: 6 tests incl. real inference
uv run python examples/deploy_schema.py             # unrelated live check of PG path
```

Live proof (2026-10-08): white-noise WAV → `{'cough_frames': 0, 'dominant_class': 'White noise', 'band': 'normal'}`; dormant gate → `403 'SENS-002 acoustic cough is Tier 4 dormant'`.

## Re-fetch / upgrade commands

```sh
hf download audiomagic/yamnet-onnx yamnet.onnx yamnet_class_map.csv --local-dir models/cough
```

The speech assets (2026-10-13):

```sh
hf download onnx-community/whisper-tiny \
  onnx/encoder_model_quantized.onnx onnx/decoder_model_merged_quantized.onnx \
  tokenizer.json vocab.json merges.txt added_tokens.json config.json \
  generation_config.json preprocessor_config.json --local-dir models/speech
# rename the two graphs flat, then the filterbank:
curl -sSL -o /tmp/mel_filters.npz \
  https://github.com/openai/whisper/raw/main/whisper/assets/mel_filters.npz
python -c "import numpy as np; np.save('models/speech/mel_80.npy', np.load('/tmp/mel_filters.npz')['mel_80'])"
```

The archived copy of that filterbank is `sources/whisper-asr/mel_filters.npz`, and
`np.array_equal` against the deployed `mel_80.npy` is asserted in `sources/INDEX.md`'s entry.

```sh
uv run pytest -q tests/ci/test_acc002.py    # 36 tests incl. real inference on real speech
uv run python tests/ci/canary_acc002.py     # 16 canaries, all must fire
```