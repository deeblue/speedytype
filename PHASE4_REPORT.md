# Phase 4 Report

Date: 2026-07-09

Execution order used: `A -> B -> C -> D`.

Reason: Part A and Part B reused existing tooling/data and answered the two highest-risk interpretation gaps first. Part C then focused the remaining STT term errors on the same Round 2 audio. Part D was a diagnostic-only replay after the main product decision points were already measured.

## Part A: Real Production Path Latency

Implementation:

- Added [scripts/run_real_path_latency_benchmark.py](/C:/WORK/Claude/poc/speedtype/scripts/run_real_path_latency_benchmark.py).
- The script opens Notepad and focuses it once before timing. Each measured run uses the normal `process_wav(..., do_paste=True)` path and does not call the benchmark harness `focus_target()` helper.
- The production path itself recorded `focus_window_seconds=0.0` on all 10 runs.

Command:

```powershell
$env:LATENCY_LOG_PATH='phase4_real_path_latency.csv'
python scripts/run_real_path_latency_benchmark.py --env .env --audio-dir test_audio --runs 10
```

Actual output summary:

```text
REAL_PATH_NOTE Notepad was focused once before measurement; no per-run focus helper is used.
REAL_PATH_SUMMARY
runs=10
avg_total_tail=3.575354
min_total_tail=2.070694
max_total_tail=4.684211
avg_whisper=2.698143
avg_llm=0.656107
avg_paste=0.220941
phase4_real_path_rows=10
```

CSV re-analysis from [phase4_real_path_latency.csv](/C:/WORK/Claude/poc/speedtype/phase4_real_path_latency.csv):

```text
total_tail_latency_seconds 10 avg=3.575354 min=2.070694 max=4.684211
recording_seconds 10 avg=16.852000 min=9.400000 max=26.520000
whisper_seconds 10 avg=2.698143 min=1.267424 max=3.695369
llm_call_seconds 10 avg=0.656107 min=0.536732 max=0.802260
paste_seconds 10 avg=0.220941 min=0.186426 max=0.467701
focus_window_seconds 10 avg=0.000000 min=0.000000 max=0.000000
clipboard_write_seconds 10 avg=0.013010 min=0.007968 max=0.016976
pre_paste_wait_seconds 10 avg=0.120347 min=0.120219 max=0.120514
key_send_seconds 10 avg=0.036754 min=0.005831 max=0.278494
post_paste_wait_seconds 10 avg=0.050465 min=0.050144 max=0.050595
paste_verification_seconds 10 avg=0.000345 min=0.000096 max=0.002334
```

Comparison:

- Phase 2 reported `avg_total_tail=3.978559s` with benchmark harness artifact included.
- Phase 4 real path measured `avg_total_tail=3.575354s`.
- Difference: `0.403205s`, smaller than the Phase 3 `focus_window_seconds` estimate of `0.848255s`.
- Current average is still `2.075354s` above the upper edge of the original `1.0-1.5s` target. Fastest run was `2.070694s`, still `0.570694s` above `1.5s`.

Conclusion: the benchmark focus artifact did inflate previous totals, but removing it does not bring the current batch pipeline into the 1.0-1.5s target. Whisper remains the dominant real-path delay.

## Part B: Disambiguation Hints On/Off

Implementation:

- Added `LLM_DISAMBIGUATION_HINTS=on/off` in [speedytype/config.py](/C:/WORK/Claude/poc/speedtype/speedytype/config.py).
- Updated [speedytype/api.py](/C:/WORK/Claude/poc/speedtype/speedytype/api.py) so only the disambiguation hint block is switched; the other system prompt rules stay unchanged.
- Updated LLM callers in [speedytype/llm.py](/C:/WORK/Claude/poc/speedtype/speedytype/llm.py) to use the generated prompt.

Configuration check:

```powershell
$env:LLM_DISAMBIGUATION_HINTS='off'
$env:LATENCY_LOG_PATH='phase4_no_disambig_latency.csv'
python -m speedytype --env .env diagnose-config
```

Actual output:

```text
Config OK. HOTKEY=f9, MIC_DEVICE=1, GEMINI_MODEL=gemini-3.5-flash, LLM_PROVIDER=gemini, LLM_MODEL=gemini-3.1-flash-lite, LLM_THINKING_LEVEL=minimal, LLM_DISAMBIGUATION_HINTS=off, MAX_RECORD_SECONDS=30.0, LATENCY_LOG_PATH=phase4_no_disambig_latency.csv
```

Validation command:

```powershell
$env:LLM_DISAMBIGUATION_HINTS='off'
$env:LATENCY_LOG_PATH='phase4_no_disambig_latency.csv'
python -m speedytype --env .env validate-real-voice --dir real_voice_round2 --script real_voice_script_round2.md --report REAL_VOICE_REPORT_ROUND2_NO_DISAMBIG.md
```

Actual output:

```text
Real voice report written: REAL_VOICE_REPORT_ROUND2_NO_DISAMBIG.md
```

Round 2 comparison, same 16 audio files:

| Setting | Overall term accuracy | API | BJ 團隊 | Self-correction | Filler removal |
|---|---:|---:|---:|---:|---:|
| Hints on, existing [REAL_VOICE_REPORT_ROUND2.md](/C:/WORK/Claude/poc/speedtype/REAL_VOICE_REPORT_ROUND2.md) | 93.8% | 5/7, 71.4% | 5/6, 83.3% | 100.0% | 100.0% |
| Hints off, new [REAL_VOICE_REPORT_ROUND2_NO_DISAMBIG.md](/C:/WORK/Claude/poc/speedtype/REAL_VOICE_REPORT_ROUND2_NO_DISAMBIG.md) | 93.8% | 5/7, 71.4% | 6/6, 100.0% | 100.0% | 100.0% |

Interpretation:

- On this Round 2 dataset, the disambiguation hints did not improve overall term accuracy or API accuracy.
- `BJ 團隊` was better with hints off in this run, but this is one small dataset and Gemini output has some run-to-run variability; this is not enough evidence to claim the hints are harmful.
- The evidence supports keeping the default as `on` only as a conservative, low-cost future guardrail, not because this dataset proves a measurable benefit.

Metric caveat: the report’s row-level `terms_ok` value can be lenient when the raw transcript contains a term but the polished final text drops it. The per-term table is the better signal for final-output term correctness.

## Part C: API / BJ 團隊 Focused STT Comparison

Implementation:

- Added [scripts/run_focused_stt_comparison.py](/C:/WORK/Claude/poc/speedtype/scripts/run_focused_stt_comparison.py).
- The script selects Round 2 segments whose script text contains `API` or `BJ 團隊`.
- It compares `whisper-1`, `gpt-4o-mini-transcribe`, `gpt-4o-transcribe`, and `gpt-realtime-whisper`.
- `BJ 團隊` matching ignores whitespace, so `BJ團隊` is counted as correct.
- Added `websocket-client==1.8.0` to [requirements.txt](/C:/WORK/Claude/poc/speedtype/requirements.txt).

Official OpenAI references checked:

- Realtime transcription guide: `gpt-realtime-whisper` is described as the lowest-latency streaming transcription path, while `gpt-4o-transcribe` and `gpt-4o-mini-transcribe` are standard request-response transcription models for file workflows. Source: https://developers.openai.com/api/docs/guides/realtime-transcription
- Speech-to-text guide: file transcription examples use `/v1/audio/transcriptions` with `gpt-4o-transcribe` and `gpt-4o-mini-transcribe`. Source: https://developers.openai.com/api/docs/guides/speech-to-text
- Pricing: `gpt-realtime-whisper` is `$0.017/min`, `gpt-4o-transcribe` is estimated `$0.006/min`, and `gpt-4o-mini-transcribe` is estimated `$0.003/min`. Source: https://developers.openai.com/api/docs/pricing

First Realtime attempt evidence:

```text
FIRST_ERROR gpt-realtime-whisper: status=realtime_error body='{"type": "error", ... "message": "Passing a transcription session update to a realtime session is not allowed." ...}'
```

Fix applied: changed the WebSocket URL to `wss://api.openai.com/v1/realtime?intent=transcription`, then reran the comparison.

Final command:

```powershell
python scripts/run_focused_stt_comparison.py --env .env --dir real_voice_round2 --script real_voice_script_round2.md --models whisper-1 gpt-4o-mini-transcribe gpt-4o-transcribe gpt-realtime-whisper --output-jsonl phase4_focused_stt_results.jsonl
```

Actual summary from [phase4_focused_stt_results.jsonl](/C:/WORK/Claude/poc/speedtype/phase4_focused_stt_results.jsonl):

| STT model | Calls OK | Avg latency | Min | Max | API accuracy | BJ 團隊 accuracy | Price |
|---|---:|---:|---:|---:|---:|---:|---:|
| `whisper-1` | 11/11 | 2.212518s | 0.881840s | 3.728925s | 6/7, 85.7% | 6/6, 100.0% | existing baseline |
| `gpt-4o-mini-transcribe` | 11/11 | 1.184863s | 0.818079s | 2.182684s | 6/7, 85.7% | 2/6, 33.3% | `$0.003/min` |
| `gpt-4o-transcribe` | 11/11 | 1.824535s | 0.829258s | 6.620267s | 6/7, 85.7% | 5/6, 83.3% | `$0.006/min` |
| `gpt-realtime-whisper` | 11/11 | 4.375068s | 3.249958s | 5.762154s | 4/7, 57.1% | 0/6, 0.0% | `$0.017/min` |

Decision:

- Do not switch away from `whisper-1` for the current product path based on this focused test.
- `gpt-4o-mini-transcribe` is much faster but badly regresses `BJ 團隊`.
- `gpt-4o-transcribe` is faster than `whisper-1` on average and cheaper than Realtime, but it still loses one `BJ 團隊` case and had one high-latency outlier at `6.620267s`.
- `gpt-realtime-whisper` worked after the URL fix, but in this bounded-audio test it was both slower and worse on these target terms. It is not a drop-in replacement for the current batch path.
- Current recommendation: keep `whisper-1` as default; list `gpt-4o-transcribe` as a possible future candidate only if a broader corpus confirms the latency gain without term regression.

## Part D: Boundary Case Latency Diagnostic

Implementation:

- Added [scripts/diagnose_boundary_case.py](/C:/WORK/Claude/poc/speedtype/scripts/diagnose_boundary_case.py).
- The script records baseline whole-file STT time and quasi-streaming chunk send time, audio duration, response time, simulated finish time, and text for each chunk.

Command:

```powershell
python scripts/diagnose_boundary_case.py --env .env --audio phase3_boundary_audio/boundary_case_16k.wav --output phase4_boundary_diagnostic.json
```

Actual output:

```text
WROTE phase4_boundary_diagnostic.json
baseline_stt_seconds=1.588426
quasi_stt_tail_seconds=1.291326
chunk=1 audio=3.000s send_at=3.000000 response=1.903978 finish_at=4.903978
chunk=2 audio=3.000s send_at=5.250000 response=1.685347 finish_at=6.935347
chunk=3 audio=3.000s send_at=7.500000 response=1.930228 finish_at=9.430228
chunk=4 audio=2.600s send_at=9.430228 response=1.211098 finish_at=10.641326
```

Diagnostic details from [phase4_boundary_diagnostic.json](/C:/WORK/Claude/poc/speedtype/phase4_boundary_diagnostic.json):

| Chunk | Audio range | Audio length | Send time | Whisper response | Finish time | Transcript |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 0.00-3.00s | 3.00s | 3.000000s | 1.903978s | 4.903978s | 先招待一下背景 先招待一下背景 |
| 2 | 2.25-5.25s | 3.00s | 5.250000s | 1.685347s | 6.935347s | 接著我們下週一 |
| 3 | 4.50-7.50s | 3.00s | 7.500000s | 1.930228s | 9.430228s | 下週一 啊 不對 下週三 |
| 4 | 6.75-9.35s | 2.60s | 9.430228s | 1.211098s | 10.641326s | 下週三要跟 BJ 團隊開會 |

Conclusion:

- The Phase 3 boundary-case `5.09s` quasi-streaming tail was not reproduced.
- This rerun showed quasi-streaming tail `1.291326s`, slightly faster than whole-file baseline STT `1.588426s`.
- No single chunk was an extreme outlier; chunk response times ranged from `1.211098s` to `1.930228s`.
- The most likely explanation for the previous `5.09s` result is transient API latency or run-to-run variance rather than a deterministic chunk-boundary failure.
- This does not change the Phase 3 adoption decision: quasi-streaming still adds thread/chunk/merge complexity, and Part C shows the STT quality problem is term-specific rather than solved by changing segmentation.

## Verification

Automated tests after Phase 4 code changes:

```powershell
python -m pytest -q
```

Result:

```text
17 passed in 1.05s
```
