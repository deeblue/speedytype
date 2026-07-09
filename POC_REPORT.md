# SpeedyType POC Report

Date: 2026-07-09

## Current Status

The POC is functionally working. Phase 2 corrected the LLM measurement method, compared Gemini/OpenAI/MiniMax polishing models, selected a new default LLM setting, reran the 10-run full pipeline benchmark, and completed the first real-human recording validation run.

Phase 3 added:

- paste latency substage instrumentation,
- prompt-based ambiguity hints for `API/NPI` and `TPE/PD/BJ`,
- a quasi-streaming Whisper POC,
- a second-round real-voice script and completed validation run.

Current default LLM setting:

- `LLM_PROVIDER=gemini`
- `LLM_MODEL=gemini-3.1-flash-lite`
- `LLM_THINKING_LEVEL=minimal`

Reason: it delivered the best measured balance of latency, quality compliance, cost, and engineering simplicity.

## Phase 1 Baseline vs Phase 2

Previous full-pipeline baseline:

```text
avg_total_tail 26.039232
min_total_tail 5.929520
max_total_tail 76.393551
share_gemini 85.70%
```

Phase 2 full-pipeline benchmark with the new default:

```text
avg_total_tail 3.978559
min_total_tail 2.660100
max_total_tail 5.281294
avg_whisper 2.192584
avg_gemini 0.702315
avg_paste 1.083617
share_whisper 55.11%
share_gemini 17.65%
share_paste 27.24%
```

Measured improvement:

- Average tail latency reduced from `26.039s` to `3.979s`.
- Absolute reduction: `22.061s`.
- Relative reduction: about `84.72%`.

## Target Check

The original `1.0-1.5s` tail-latency target is still not met.

- Current average tail latency is `3.979s`.
- This is `2.479s` above the `1.5s` upper bound.
- The fastest observed full run was `2.660s`, still `1.160s` above the target.

## Real Voice Validation

Real-user recording was completed on July 9, 2026 with 10 final WAV segments in `real_voice/segment01_final.wav` through `segment10_final.wav`.

Summary from [REAL_VOICE_REPORT.md](/C:/WORK/Claude/poc/speedtype/REAL_VOICE_REPORT.md):

- 專有名詞辨識正確率: `50.0%`
- 自我修正處理正確率: `100.0%`
- 贅字清除正確率: `100.0%`

Measured real-voice latency from `run_label=real_voice` rows in `speedytype_latency_log.csv`:

```text
count=10
avg_tail=2.862630
min_tail=1.774415
max_tail=6.526238
avg_whisper=2.209856
avg_llm=0.652579
```

Interpretation:

- The selected Gemini Flash-Lite polishing setting remains fast on real speech.
- The main quality weakness is now Whisper term recognition on real human input, not the LLM cleanup step.
- Representative misses: `TPE` -> `PD`, one `API` -> `NPI`, and one sentence where `TPE` disappeared after the STT stage.

Test-condition note:

- The last recorded sentence had less background noise than earlier sentences. This makes the recording conditions imperfectly uniform, but the run is still valid as an initial real-user benchmark and error analysis set.

## Real Voice Validation Round 2

Second-round real-user recording and validation were also completed on July 9, 2026 with 16 final WAV segments in `real_voice_round2`.

Summary from [REAL_VOICE_REPORT_ROUND2.md](/C:/WORK/Claude/poc/speedtype/REAL_VOICE_REPORT_ROUND2.md):

- 專有名詞辨識正確率: `93.8%`
- 自我修正處理正確率: `100.0%`
- 贅字清除正確率: `100.0%`

Key interpretation:

- The first round’s `50.0%` term-accuracy result was not representative of the broader real-voice behavior.
- On the larger and more controlled second-round dataset, the system is mostly accurate on real speech.
- Residual risk is concentrated mainly on:
  - `API` (`71.4%` in Round 2)
  - `BJ 團隊` (`83.3%` in Round 2)
- All other tracked technical terms in Round 2 reached `100.0%`.

Updated technical judgment:

- The current blocker is no longer “general real-voice term recognition is weak”.
- The remaining problem is narrower: a small set of easily confused terms still need focused STT-side improvement or targeted model comparison.

## Paste and Error Handling

Verified non-admin paste targets:

- Notepad: PASS
- Browser textarea: PASS
- Normal-permission app: PASS
- Admin-elevated window: NOT_TESTED

Silent-audio handling with a real Whisper call:

```text
Recording ended.
Whisper raw transcript:
Whisper returned empty text; skipped Gemini and paste.
```

## Tests

Latest automated test result:

```text
python -m pytest -q
17 passed in 1.05s
```

## Detailed Phase 2 Results

See [PHASE2_MODEL_REPORT.md](/C:/WORK/Claude/poc/speedtype/PHASE2_MODEL_REPORT.md) for:

- provider/model probe evidence,
- cross-provider latency and quality table,
- cost estimates,
- MiniMax/OpenAI/Gemini tradeoff analysis,
- guided-recording fixes and resume support,
- completed real-voice validation results.

## Phase 3 Results

See [PHASE3_REPORT.md](/C:/WORK/Claude/poc/speedtype/PHASE3_REPORT.md) for:

- paste latency breakdown,
- recording-length bucket analysis,
- disambiguation prompt before/after comparison,
- quasi-streaming Whisper benchmark and adoption judgment,
- completed second-round real-voice validation.

## Phase 4 Results

See [PHASE4_REPORT.md](/C:/WORK/Claude/poc/speedtype/PHASE4_REPORT.md) for:

- real production-path latency retest without the benchmark focus artifact,
- Round 2 disambiguation hints on/off comparison,
- focused `API` / `BJ 團隊` STT comparison across `whisper-1`, `gpt-4o-mini-transcribe`, `gpt-4o-transcribe`, and `gpt-realtime-whisper`,
- boundary-case quasi-streaming latency diagnostic.

Phase 4 headline:

- Real-path average tail latency is `3.575354s`, not the older harness-inflated `3.978559s`, but it still misses the `1.0-1.5s` target.
- Disambiguation hints showed no measurable benefit on Round 2: overall term accuracy stayed `93.8%`.
- `whisper-1` remains the recommended STT default for now because it had the best focused `BJ 團隊` accuracy in the Phase 4 comparison.
