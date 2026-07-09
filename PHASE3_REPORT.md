# Phase 3 Report

Date: 2026-07-09

Execution order used in practice: `A -> C -> B -> D`.

Reason:

- Part A was the lowest-cost way to verify whether the remaining latency problem was really Whisper or whether the old `paste` bucket was hiding something else.
- Part C reused the existing 10 real-voice recordings, so it was cheap to validate before taking on new architecture work.
- Part B was the largest engineering change, so I delayed it until the latency breakdown and the real-voice baseline were both clear.
- Part D depends on a second round of user recording, so the useful work in this turn was to prepare the script and handoff cleanly.

## Part A

### A1. Paste latency breakdown

New instrumentation was added to:

- [speedytype/clipboard.py](/C:/WORK/Claude/poc/speedtype/speedytype/clipboard.py)
- [speedytype/latency.py](/C:/WORK/Claude/poc/speedtype/speedytype/latency.py)
- [scripts/run_full_paste_benchmark.py](/C:/WORK/Claude/poc/speedtype/scripts/run_full_paste_benchmark.py)
- [scripts/run_paste_breakdown_benchmark.py](/C:/WORK/Claude/poc/speedtype/scripts/run_paste_breakdown_benchmark.py)

Paste-only benchmark command:

```powershell
python scripts/run_paste_breakdown_benchmark.py --runs 10
```

Actual output summary:

```text
PASTE_BREAKDOWN_SUMMARY
runs=10
successes=10
wall_seconds: avg=0.213004 min=0.185169 max=0.428658
clipboard_write_seconds: avg=0.011008 min=0.008134 max=0.013166
pre_send_wait_seconds: avg=0.120398 min=0.120227 max=0.120570
key_send_seconds: avg=0.031041 min=0.005919 max=0.244097
post_send_wait_seconds: avg=0.050350 min=0.050146 max=0.050584
verification_seconds: avg=0.000182 min=0.000097 max=0.000704
```

Full benchmark rerun with focus timing:

```powershell
$env:LATENCY_LOG_PATH='phase3_full_benchmark_latency.csv'
python scripts/run_full_paste_benchmark.py --env .env --audio-dir test_audio --runs 10
```

Actual full-benchmark paste substage summary from the latest 10 rows:

```text
focus_window_seconds avg 0.848255 min 0.811883 max 0.899355
clipboard_write_seconds avg 0.013462 min 0.007832 max 0.039092
pre_paste_wait_seconds avg 0.120381 min 0.120104 max 0.120700
key_send_seconds avg 0.033504 min 0.005383 max 0.268314
post_paste_wait_seconds avg 0.050267 min 0.050106 max 0.050469
paste_verification_seconds avg 0.000248 min 0.000100 max 0.000849
paste_seconds avg 1.066159 min 1.001925 max 1.272900
```

Conclusion:

- The actual paste path (`copy + waits + send + verify`) is about `0.21s` on this machine, not `1.08s`.
- The old `paste` bucket was dominated by the benchmark wrapper’s `focus_target()` step, which averaged `0.848s`.
- Necessary costs:
  - clipboard write: about `13ms`
  - simulated key send: about `34ms` average
- Deliberate conservative waits:
  - pre-send wait: `120ms`
  - post-send wait: `50ms`
- Verification cost is negligible (`~0.25ms`) and is not the optimization target.

Honest optimization judgment:

- In the real product path, there is no `focus_target()` helper, so the measured `1.08s` does **not** mean the product’s own `Ctrl+V` path is inherently that slow.
- The two explicit sleeps (`120ms + 50ms`) are conservative and probably reducible, but even removing them only saves about `170ms`, not `1s`.

### A2. Latency by recording-length bucket

Analysis script:

```powershell
python scripts/analyze_latency_by_duration.py --csv phase3_full_benchmark_latency.csv --run-label phase2_full_benchmark
```

I excluded one aborted pre-fix row and summarized the latest clean 10-run set:

```text
0-10s samples 4
 whisper 2.312574 1.559327 2.982277
 total 4.109670 3.206558 4.892037
10-20s samples 3
 whisper 2.220346 1.494471 3.542622
 total 3.973347 3.245913 5.277377
20-30s samples 3
 whisper 2.264305 1.934977 2.651665
 total 4.031109 3.697735 4.454912
```

Conclusion:

- On this sample, Whisper latency did **not** scale cleanly with audio duration.
- The `20-30s` group was not slower than the `10-20s` group.
- Sample sizes are small (`4 / 3 / 3`), so this is a directional observation, not a statistically strong result.
- The current data does **not** support a strong claim that “longer clip means proportionally slower Whisper tail” for this setup.

## Part C

### C1. Prompt update

Updated [speedytype/api.py](/C:/WORK/Claude/poc/speedtype/speedytype/api.py) rule 4 with explicit ambiguity guidance for:

- `API / NPI`
- `TPE 團隊 / PD 團隊 / BJ 團隊`

The prompt explicitly tells the LLM:

- use context when confident
- keep the original STT output when context is insufficient
- avoid speculative team-name replacement

### C2. Rerun on the same real-voice set

Baseline report preserved:

- [REAL_VOICE_REPORT_PHASE2_BASELINE.md](/C:/WORK/Claude/poc/speedtype/REAL_VOICE_REPORT_PHASE2_BASELINE.md)

Rerun with disambiguation prompt:

```powershell
python -m speedytype --env .env validate-real-voice --dir real_voice --script real_voice_script.md --report REAL_VOICE_REPORT_PHASE3_DISAMBIG.md
```

Output:

```text
Real voice report written: REAL_VOICE_REPORT_PHASE3_DISAMBIG.md
```

Result:

- Before: `50.0%`
- After: `50.0%`

Updated per-term report:

- [REAL_VOICE_REPORT_PHASE3_DISAMBIG.md](/C:/WORK/Claude/poc/speedtype/REAL_VOICE_REPORT_PHASE3_DISAMBIG.md)

Per-term accuracy from the rerun:

| 詞彙 | 正確次數 | 出現次數 | 正確率 |
|---|---:|---:|---:|
| `BIOS` | 4 | 4 | 100.0% |
| `Firmware` | 4 | 5 | 80.0% |
| `NPI` | 3 | 3 | 100.0% |
| `QA` | 4 | 4 | 100.0% |
| `API` | 1 | 3 | 33.3% |
| `TPE 團隊` | 3 | 5 | 60.0% |
| `BJ 團隊` | 3 | 4 | 75.0% |
| `USB` | 2 | 2 | 100.0% |
| `Thunderbolt` | 3 | 3 | 100.0% |

Conclusion:

- The added disambiguation hints did **not** improve sentence-level technical-term accuracy on this 10-sample real-voice set.
- I did not observe a new false replacement where a previously correct term was turned into a wrong one.
- The dominant misses remained the same:
  - `TPE 團隊` -> `PD 團隊`
  - missing `API`
  - one self-correction sentence where `BJ 團隊` was dropped because the corrected clause kept only `TPE 團隊`

Interpretation:

- The new prompt is not harmful in this sample, but it is also not enough to recover low-confidence STT ambiguity by itself.

## Part B

### B1. Feasibility check

Official OpenAI docs used:

- Realtime transcription guide: <https://developers.openai.com/api/docs/guides/realtime-transcription>
- Speech-to-text guide: <https://developers.openai.com/api/docs/guides/speech-to-text>
- Pricing: <https://developers.openai.com/api/docs/pricing>

Relevant doc findings:

- OpenAI explicitly states that for the lowest-latency streaming transcription path, `gpt-realtime-whisper` is the dedicated realtime choice, while `whisper-1` is an existing integration and is “not natively streaming in the same way”.
- The standard Speech-to-text guide says file uploads are request/response style and recommends avoiding breaking audio mid-sentence because context can be lost.
- Pricing page shows:
  - `gpt-realtime-whisper`: `$0.017 / minute`
  - `gpt-4o-transcribe`: estimated `$0.006 / minute`
  - `gpt-4o-mini-transcribe`: estimated `$0.003 / minute`

3-second real chunk test:

```powershell
# created tmp_whisper_chunk_3s.wav from test_audio/short_16k.wav
```

Actual output:

```text
chunk_file=tmp_whisper_chunk_3s.wav seconds=3.000
whisper_wall_seconds=1.716223
transcript='呃，我們下，啊不對'
```

Conclusion from the chunk test:

- Sending a short partial WAV to `/v1/audio/transcriptions` is technically viable.
- The API returns a normal transcription instead of erroring.
- Quality is clearly partial and fragile at 3 seconds, which is consistent with the docs warning about mid-sentence chunking.

### B2. Quasi-streaming POC

Implemented:

- [speedytype/quasi_streaming.py](/C:/WORK/Claude/poc/speedtype/speedytype/quasi_streaming.py)
- [scripts/run_quasi_streaming_benchmark.py](/C:/WORK/Claude/poc/speedtype/scripts/run_quasi_streaming_benchmark.py)

Design used:

- chunk size: `3.0s`
- overlap: `0.75s`
- commit window per chunk: `chunk_size - overlap`
- merge by overlapping committed text plus segment timing from Whisper `verbose_json`

This is a simulated background-streaming POC against fixed WAV files. It is enough to measure the architecture tradeoff before wiring the same logic into live recording threads.

### B3. Baseline vs quasi-streaming benchmark

Command:

```powershell
python scripts/run_quasi_streaming_benchmark.py --env .env --audio-dir test_audio --runs 10 --chunk-seconds 3.0 --overlap-seconds 0.75
```

Output file:

- [phase3_quasi_streaming_results.jsonl](/C:/WORK/Claude/poc/speedtype/phase3_quasi_streaming_results.jsonl)

Overall summary:

```text
SUMMARY baseline
runs=10 quality_pass=10/10
total_tail_seconds avg=4.392505 min=3.137235 max=5.919399
stt_tail_seconds avg=2.525444 min=1.465066 max=3.890600

SUMMARY quasi_streaming
runs=10 quality_pass=10/10
total_tail_seconds avg=3.735975 min=2.672525 max=6.158683
stt_tail_seconds avg=2.046686 min=1.098207 max=4.405264
```

Average improvement:

- total tail: `4.392505s -> 3.735975s`
- absolute improvement: `0.656530s`
- relative improvement: about `14.95%`

Per-case averages:

| Case | Baseline Avg Tail | Quasi-streaming Avg Tail | Result |
|---|---:|---:|---|
| short | 4.164154s | 3.650696s | improved |
| medium | 3.727460s | 4.387830s | regressed |
| long | 5.362018s | 3.197826s | improved strongly |

Interpretation:

- Quasi-streaming helps most on long clips.
- It is not consistently better on medium clips.
- It increases variance: the worst quasi-streaming run (`6.158683s`) was worse than the average baseline.

### B3. Boundary-case self-correction test

Generated targeted clip:

- [phase3_boundary_audio/boundary_case_16k.wav](/C:/WORK/Claude/poc/speedtype/phase3_boundary_audio/boundary_case_16k.wav)

Result file:

- [phase3_boundary_case_result.json](/C:/WORK/Claude/poc/speedtype/phase3_boundary_case_result.json)

Actual result excerpt:

```json
{
  "baseline": {
    "raw": "先交代一下背景,先交代一下背景 接著我們下週一,啊,不對,下週三要跟 BJ 團隊開會",
    "polished": "下週三要跟 BJ 團隊開會。"
  },
  "quasi_streaming": {
    "merged": "先招待一下背景 接著我們下週一 啊 不對 下週三要跟 BJ 團隊開會",
    "polished": "背景說明如下：\n\n我們下週三要與 BJ 團隊開會。",
    "chunks": [
      {"index": 2, "text": "接著我們下週一"},
      {"index": 3, "text": "下週一 啊 不對 下週三"},
      {"index": 4, "text": "下週三要跟 BJ 團隊開會"}
    ]
  }
}
```

Conclusion:

- The self-correction survived a chunk boundary and the LLM still repaired it correctly.
- But this same boundary-case run also showed the risk side:
  - baseline STT wall: `2.257865s`
  - quasi-streaming STT tail: `5.092521s`
- So the architecture can preserve the correction semantics while still suffering a worse tail when late chunks serialize badly.

### B4. Honest adoption judgment

Current judgment: **not ready to replace the existing whole-file path as the default architecture yet**.

Reason:

- There is a real average latency gain (`~15%`) in this POC.
- Quality did not collapse in the current synthetic test set; all 10 benchmark outputs still passed the same high-level quality rules.
- However, the variance and complexity are real:
  - medium clips regressed on average
  - worst-case quasi-streaming tail exceeded the worst baseline average pattern
  - chunk planning, overlap merge, segment commit windows, and background worker timing add substantial complexity
- The boundary-case test proved that chunk crossing is survivable, but not predictably faster.

If this architecture is pursued further, the next rational step would be:

- compare against OpenAI’s dedicated realtime transcription path (`gpt-realtime-whisper`) instead of spending more engineering effort on request/response chunking over `whisper-1`

That is because the official docs already position `gpt-realtime-whisper` as the lowest-latency native streaming option, while the current chunking approach is a workaround layered on top of a non-native streaming endpoint.

## Part D

### D1. Second-round script

Created:

- [real_voice_script_round2.md](/C:/WORK/Claude/poc/speedtype/real_voice_script_round2.md)

Design notes:

- 16 sentences
- all target terms appear multiple times across different contexts
- opening instructions explicitly require a fixed recording environment
- includes short, medium, and long sentences
- includes self-correction cases and list-like long utterances

### D2. Tooling status

No parser change was required for the new script format.

Existing tooling already supports this round:

- `guided-recording` now resumes from existing finals
- `validate-real-voice` now outputs per-term accuracy

### D3. Status

Round 2 recording and validation are complete.

Validation command used:

```powershell
python -m speedytype --env .env validate-real-voice --dir real_voice_round2 --script real_voice_script_round2.md --report REAL_VOICE_REPORT_ROUND2.md
```

Result file:

- [REAL_VOICE_REPORT_ROUND2.md](/C:/WORK/Claude/poc/speedtype/REAL_VOICE_REPORT_ROUND2.md)

Round 2 summary:

- 專有名詞辨識正確率：`93.8%`
- 自我修正處理正確率：`100.0%`
- 贅字清除正確率：`100.0%`

Per-term accuracy from Round 2:

| 詞彙 | 正確次數 | 出現次數 | 正確率 |
|---|---:|---:|---:|
| `BIOS` | 7 | 7 | 100.0% |
| `Firmware` | 7 | 7 | 100.0% |
| `NPI` | 6 | 6 | 100.0% |
| `QA` | 6 | 6 | 100.0% |
| `API` | 5 | 7 | 71.4% |
| `TPE 團隊` | 5 | 5 | 100.0% |
| `BJ 團隊` | 5 | 6 | 83.3% |
| `USB` | 5 | 5 | 100.0% |
| `Thunderbolt` | 5 | 5 | 100.0% |

Comparison with Round 1:

- Round 1 sentence-level term accuracy: `50.0%`
- Round 2 sentence-level term accuracy: `93.8%`

Interpretation:

- The earlier `50.0%` result was not representative of broad real-voice accuracy. It was strongly affected by small sample size and inconsistent recording conditions.
- On the larger and better-controlled second round, the system is mostly accurate on real speech.
- The remaining errors are concentrated rather than general:
  - `API` is still the main weak point (`71.4%`)
  - `BJ 團隊` had one miss (`83.3%`)
- Everything else in this round was `100.0%`.

## Final position

What Phase 3 established with real execution:

1. The old `paste` bucket was misleading; most of that number was benchmark-window focusing, not the product’s own clipboard/paste path.
2. The added LLM disambiguation prompt was safe, but on the original 10-sample round it did not improve sentence-level technical-term accuracy beyond `50.0%`.
3. Quasi-streaming over `whisper-1` can reduce average tail latency, especially on long clips, but the gain is modest relative to the added complexity and variance.
4. After Round 2, broad real-voice term recognition no longer looks fundamentally weak. The problem is now concentrated on a small subset of terms, especially `API`.
5. The next high-value experiment is not more generic prompt tuning; it is a focused STT comparison or realtime transcription comparison on `API`-heavy and team-name-heavy real speech:
   - a dedicated realtime transcription comparison (`gpt-realtime-whisper`), or
   - a better STT model comparison using the same round-2 real-voice set.
