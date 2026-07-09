# Phase 2 Model and Real Voice Report

Date: 2026-07-09

## Part A

### A0. API and Billing Preconditions

- OpenAI: `OPENAI_API_KEY` exists and real Whisper/TTS/Responses API calls succeeded.
- Gemini: `GEMINI_API_KEY` exists and Gemini model/TTS/generateContent calls succeeded.
- MiniMax: `MINIMAX_API_KEY` exists and real `/v1/models`, `/v1/chat/completions`, `/v1/get_voice`, and `/v1/t2a_v2` calls succeeded.
- MiniMax subscription-specific note from official docs: Token Plan uses a separate Subscription Key from pay-as-you-go API keys, and token-plan quota is shared across text/image/speech/music resources.
- Anthropic: skipped. Reason: no API billing plan, per task instruction.

MiniMax evidence:

```text
GET https://api.minimax.io/v1/models
-> MiniMax-M3, MiniMax-M2.7, MiniMax-M2.7-highspeed, MiniMax-M2.5, MiniMax-M2.5-highspeed, ...

POST https://api.minimax.io/v1/get_voice
-> returned system voices including "Chinese (Mandarin)_Reliable_Executive"
```

### A1. Model and Parameter Probe

Probe command:

```powershell
$env:PYTHONIOENCODING='utf-8'; python scripts/phase2_probe_models.py
```

Probe results were written to `phase2_probe_results.json`.

Accepted combinations from real API responses:

| Provider | Model | Control Param | Accepted Values | Rejected Values |
|---|---|---|---|---|
| Gemini | `gemini-3.5-flash` | `thinking_level` | `default`, `minimal`, `low` | `none` |
| Gemini | `gemini-3.1-flash-lite` | `thinking_level` | `default`, `minimal`, `low` | `none` |
| OpenAI | `gpt-5.5` | `reasoning.effort` | `none`, `low` | `minimal` |
| OpenAI | `gpt-5.4-mini` | `reasoning.effort` | `none`, `low` | `minimal` |
| OpenAI | `gpt-5.4-nano` | `reasoning.effort` | `none`, `low` | `minimal` |
| MiniMax | `MiniMax-M3` | `thinking.type` | `default`, `disabled`, `adaptive` | none observed |

Notable probe evidence:

- Gemini rejects `thinking_level=none` with `400 INVALID_ARGUMENT`.
- OpenAI `gpt-5.x` rejects `reasoning.effort=minimal` with `400 unsupported_value`.
- MiniMax `thinking.type=disabled` was accepted and returned a valid response.

Representative probe latencies:

```text
gemini-3.5-flash default: 2.790s
gemini-3.1-flash-lite minimal: 0.773s
gpt-5.4-mini none: 0.895s
MiniMax-M3 disabled: 2.479s
```

### A1 Supplement. Multi-TTS Test Inputs

Updated `scripts/generate_test_audio.py` to generate:

- default set via OpenAI TTS when available,
- fallback set via Gemini TTS,
- second source set via MiniMax TTS `speech-2.8-turbo`.

Generation command:

```powershell
$env:PYTHONIOENCODING='utf-8'; python scripts/generate_test_audio.py --env .env --output-dir test_audio_phase2
```

Actual output excerpt:

```text
short: test_audio_phase2\short_16k.wav duration=10.000s source=openai-gpt-4o-mini-tts
short: test_audio_phase2\short_minimax_16k.wav duration=7.465s source=minimax-speech-2.8-turbo
medium: test_audio_phase2\medium_16k.wav duration=16.300s source=openai-gpt-4o-mini-tts
medium: test_audio_phase2\medium_minimax_16k.wav duration=15.488s source=minimax-speech-2.8-turbo
long: test_audio_phase2\long_16k.wav duration=26.550s source=openai-gpt-4o-mini-tts
long: test_audio_phase2\long_minimax_16k.wav duration=22.932s source=minimax-speech-2.8-turbo
```

### A2. Latency Measurement Fix

Implemented provider-neutral LLM calling in [speedytype/llm.py](/C:/WORK/Claude/poc/speedtype/speedytype/llm.py) and expanded latency records in [speedytype/latency.py](/C:/WORK/Claude/poc/speedtype/speedytype/latency.py).

New log fields:

- `llm_provider`
- `llm_model`
- `llm_call_seconds`
- `retry_wait_seconds`
- `run_label`

Key correction:

- `llm_call_seconds` now records only the sum of actual HTTP call durations.
- `retry_wait_seconds` records backoff sleep separately.
- This prevents 429/503 sleep time from polluting model latency.

### A3. Cross-Provider Control Experiment

Experiment command:

```powershell
$env:PYTHONIOENCODING='utf-8'; python scripts/phase2_run_llm_experiment.py
```

Results were written to `phase2_llm_results.jsonl`.

Candidate summary:

| Candidate | Success | Quality Pass | Avg LLM Call | Avg Retry Wait | Avg Est. Cost / call |
|---|---:|---:|---:|---:|---:|
| `gemini-3.5-flash` default | 4/9 | 4/9 | 3.130s | 1.000s | $0.00469087 |
| `gemini-3.1-flash-lite` minimal | 9/9 | 9/9 | 0.743s | 0.000s | $0.00014050 |
| `gemini-3.1-flash-lite` low | 9/9 | 9/9 | 1.166s | 0.444s | $0.00033567 |
| `gpt-5.5` none | 9/9 | 7/9 | 1.854s | 0.000s | $0.00168500 |
| `gpt-5.4-mini` none | 9/9 | 6/9 | 1.017s | 0.000s | $0.00024975 |
| `gpt-5.4-nano` none | 9/9 | 6/9 | 1.426s | 0.000s | $0.00007363 |
| `MiniMax-M3` disabled | 9/9 | 9/9 | 4.959s | 0.000s | $0.00019457 |
| `MiniMax-M3` adaptive | 9/9 | 8/9 | 6.267s | 0.000s | $0.00045460 |

Cost notes:

- OpenAI prices are from the official API pricing page.
- Gemini prices are from the official Gemini API pricing page.
- MiniMax cost is estimated at pay-as-you-go equivalent pricing for `MiniMax-M3`; for Subscription/Token Plan usage, quota is consumed first, with credits overflow priced at the pay-as-you-go list price.

### A4. Quality Check

Quality rules checked for every run:

1. filler removal
2. self-correction handling
3. list formatting for the long multi-step case
4. technical term preservation
5. no extra explanation or greeting

Observed quality conclusions:

- `gemini-3.1-flash-lite` minimal: all 9/9 outputs passed.
- `gemini-3.1-flash-lite` low: all 9/9 outputs passed, but slower and occasionally retried.
- `gpt-5.5` none: failed 2 long-case runs because list formatting was inconsistent.
- `gpt-5.4-mini` none: failed all 3 long-case runs because it flattened the multi-step content instead of consistently outputting Markdown bullets.
- `gpt-5.4-nano` none: failed all 3 long-case runs because it retained more of the pre-correction structure.
- `MiniMax-M3` disabled: 9/9 passed, but average latency was much slower than Gemini Flash-Lite.
- `MiniMax-M3` adaptive: 1 failure with empty long output.

Subjective Chinese fluency:

- Gemini Flash-Lite minimal: natural and concise, no obvious translation feel.
- OpenAI models: generally natural, but the long-form formatting was less stable.
- MiniMax M3: natural Chinese, but more variable latency.

### A4 Bonus. Cross-TTS Full Pipeline Check

Commands:

```powershell
python -m speedytype --env phase2_selected.env run-once test_audio_phase2\short_16k.wav --no-paste
python -m speedytype --env phase2_selected.env run-once test_audio_phase2\short_minimax_16k.wav --no-paste
```

Observed outputs:

```text
OpenAI TTS source -> Whisper raw: 呃,我們下週一,呃,不對,下週三要開會,請 TPE 團隊同步 BIOS 狀態。
OpenAI TTS source -> Polished: 我們下週三要開會，請 TPE 團隊同步 BIOS 狀態。

MiniMax TTS source -> Whisper raw: 呃,我們下週一,不對,下週三要歪尾,請 TPE 團隊同步 BIOS 狀態
MiniMax TTS source -> Polished: 我們下週三要開會，請 TPE 團隊同步 BIOS 狀態。
```

Interpretation:

- Different TTS sources do affect Whisper error patterns.
- The selected LLM recovered a MiniMax-TTS-induced STT error (`開會` -> `歪尾`) in this sample.

### A5. Final Selection and Application

Selected default:

- Provider: `gemini`
- Model: `gemini-3.1-flash-lite`
- Param: `LLM_THINKING_LEVEL=minimal`

Why this setting won:

- Lowest average LLM latency among all candidates that also passed quality 9/9.
- Zero retry wait in the experiment.
- Lower estimated cost than OpenAI `gpt-5.5` and lower engineering complexity than switching providers.
- Reuses the existing Gemini integration path, so the extra implementation cost is near-zero.

Why not the alternatives:

- `gemini-3.5-flash` default: unstable under quota/rate limits and much slower.
- OpenAI `gpt-5.4-mini`: fast, but long-case formatting quality failed.
- OpenAI `gpt-5.4-nano`: cheap, but long-case correction/formatting quality failed.
- MiniMax-M3 disabled: quality passed, but latency was much worse than Gemini Flash-Lite minimal.

Engineering complexity judgment:

- Staying on Gemini is materially simpler because the pipeline already had Gemini support.
- Switching to OpenAI or MiniMax would be justified only if they clearly beat Gemini Flash-Lite on both latency and quality. They did not.

Applied defaults:

- [speedytype/config.py](/C:/WORK/Claude/poc/speedtype/speedytype/config.py)
- [.env.example](/C:/WORK/Claude/poc/speedtype/.env.example)
- local `.env` updated to the same default provider/model controls

### A5. Full Pipeline Benchmark After Applying the New Default

Benchmark command:

```powershell
$env:PYTHONIOENCODING='utf-8'; python scripts/run_full_paste_benchmark.py --env phase2_selected.env --audio-dir test_audio --runs 10
```

Actual summary:

```text
runs=10
paste_successes=10
avg_total_tail=3.978559
min_total_tail=2.660100
max_total_tail=5.281294
avg_whisper=2.192584
avg_gemini=0.702315
avg_paste=1.083617
share_whisper=55.11%
share_gemini=17.65%
share_paste=27.24%
latency_log_rows=10
```

Direct comparison with the previous benchmark:

- Previous average total tail: `26.039232s`
- New average total tail: `3.978559s`
- Improvement: `-22.060673s` (`84.72%` reduction)

Honest target answer:

- The new setting did **not** reach the original `1.0-1.5s` target.
- The new average is `3.979s`, still `2.479s` above the `1.5s` upper bound.
- The fastest observed run was `2.660s`, still above target.

## Part B

### B1. Reading Script

Created [real_voice_script.md](/C:/WORK/Claude/poc/speedtype/real_voice_script.md) with 10 lines covering:

- filler words,
- self-correction,
- technical terms,
- a list-format long sentence,
- short/medium/long timing distribution.

### B2. Guided Recording Tool

Implemented:

```powershell
python -m speedytype guided-recording --script real_voice_script.md
```

Behavior implemented:

- shows sentence index and content,
- waits for hotkey recording,
- records to `real_voice/segmentXX_takeY.wav`,
- shows duration after recording,
- supports re-record via `r`,
- copies accepted take to `segmentXX_final.wav`,
- prints total time and high-retake summary.
- skips sentences that already have `segmentXX_final.wav`, so interrupted sessions can resume.

Note: this version uses duration display instead of immediate playback, which is explicitly allowed by the task.

Post-implementation fixes made during real-user execution:

- Replaced fragile release-event waiting with explicit key-up polling plus `MAX_RECORD_SECONDS` timeout.
- Replaced `input()` in the accept/re-record prompt with Windows-safe direct key reads to avoid `OSError: [WinError 6] The handle is invalid`.
- Added resume support so existing `segmentXX_final.wav` files are skipped automatically.

### B3. Real Voice Validation Tool

Implemented:

```powershell
python -m speedytype validate-real-voice --dir real_voice
```

Behavior implemented:

- discovers `*_final.wav`,
- runs full pipeline with the selected default LLM setting,
- writes `REAL_VOICE_REPORT.md`,
- logs these runs with `run_label=real_voice`.

### B4. Tooling Tests

Automated tests added for tooling flow pieces, without fabricating real human audio:

- parser and file ordering tests,
- fake-WAV report generation test for `validate-real-voice`.

Latest test result:

```text
python -m pytest -q
15 passed in 1.10s
```

### B5. Real Voice Validation Run Completed

The user completed the guided recording session on July 9, 2026. Final files:

- `real_voice/segment01_final.wav`
- `real_voice/segment02_final.wav`
- `real_voice/segment03_final.wav`
- `real_voice/segment04_final.wav`
- `real_voice/segment05_final.wav`
- `real_voice/segment06_final.wav`
- `real_voice/segment07_final.wav`
- `real_voice/segment08_final.wav`
- `real_voice/segment09_final.wav`
- `real_voice/segment10_final.wav`

Validation command:

```powershell
python -m speedytype --env .env validate-real-voice --dir real_voice --script real_voice_script.md --report REAL_VOICE_REPORT.md
```

Actual completion output:

```text
Real voice report written: REAL_VOICE_REPORT.md
```

Real-voice report summary:

- 專有名詞辨識正確率：`50.0%`
- 自我修正處理正確率：`100.0%`
- 贅字清除正確率：`100.0%`

Measured real-voice latency summary from `speedytype_latency_log.csv` with `run_label=real_voice`:

```text
count 10
avg_tail 2.862630
min_tail 1.774415
max_tail 6.526238
avg_whisper 2.209856
avg_llm 0.652579
```

Observed quality conclusion:

- The selected Gemini polishing configuration remained low-latency and consistently removed fillers / handled self-corrections.
- The dominant accuracy issue on real speech is STT term recognition before the LLM stage.
- Representative misses from `REAL_VOICE_REPORT.md`:
  - sentence 1: `TPE 團隊` recognized as `PD 團隊`
  - sentence 5: corrected output lost the intended `TPE 團隊` reference and kept only `BJ 團隊`
  - sentence 10: expected `API`, Whisper produced `NPI`

Test-condition note:

- The final sentence was recorded with less background noise than earlier sentences. This reduces environmental consistency slightly, but the set is still useful and was kept as the first completed real-user benchmark.
