# Long-Recording Hybrid Transcription Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce post-recording latency for recordings longer than 90 seconds without introducing missing sentences, duplicated boundaries, reordered content, or uncontrolled Whisper request cost.

**Architecture:** Replace fixed 30-second slicing with silence-aware dynamic chunks bounded by minimum, preferred, and maximum durations. Merge timestamped Whisper segments through a committed audio timeline, validate completeness, and automatically fall back to one batch transcription whenever hybrid output is structurally unsafe.

**Tech Stack:** Python 3, NumPy, soundfile, existing Recorder RMS stream, Whisper verbose timestamps, pytest, optional future WebRTC/Silero VAD.

## Global Constraints

- Short recordings remain on the existing batch path.
- Initial hybrid threshold is 90 seconds and remains configurable.
- No production enablement until the full quality and latency gate passes.
- Natural silence is preferred; forced cuts are a bounded fallback.
- API requests remain serial in the first production version.
- Every uncertain hybrid result falls back to batch rather than pasting incomplete text.
- Gemini polishing receives only the validated final transcript.
- Existing Windows and macOS platform abstractions must not change.

## Initial Parameters

```text
hybrid_threshold_seconds = 90.0
min_chunk_seconds = 15.0
preferred_chunk_seconds = 25.0
max_chunk_seconds = 45.0
minimum_silence_seconds = 0.6
natural_cut_context_seconds = 0.2
forced_cut_overlap_seconds = 1.5
analysis_frame_ms = 20
noise_floor_window_seconds = 5.0
silence_enter_multiplier = 1.8
silence_exit_multiplier = 2.4
```

These are starting values, not hidden constants. They belong in an immutable configuration dataclass and must be recorded in benchmark output.

## Evidence Driving This Plan

The decisive long-file test uses `test_audio_long/continuous_tts_295s.wav`: a 294.792-second, single continuous TTS reading of the non-repeating script in `test_audio_long/continuous_tts_script.txt`. It replaced the earlier 262-second composite because the two composite source recordings discuss overlapping meeting topics and could confound the result.

With fixed 30-second chunks and five-second overlap:

| Path | STT tail | Total Whisper request time | Requests |
|---|---:|---:|---:|
| Batch | 18.098s | 18.098s | 1 |
| Quasi-streaming POC | 1.874s | 34.742s | 12 |

The modeled tail improved by 89.6%, confirming that the latency benefit is not caused by the old splice. However, the quasi transcript is not production-safe. Direct comparison with the complete source and batch transcript found concrete content failures:

- **[Case A]** The complete sentence `列車準時出發` is present in batch but absent from quasi output.
- **[Case B]** `我在海邊停留約四十分鐘，記錄潮水顏色和風速變化` is corrupted to `一分鐘，記錄潮水顏色和風速變化`, losing the subject and changing the duration.
- **[Case C]** `傍晚，我回到車站附近的咖啡館整理筆記` is reduced to `整理筆記`, dropping the time, return action, and location.
- **[Case D]** `把博物館、市場、舊城街道和海邊步道依照距離重新排序` becomes the malformed `把博物館、市場、舊城街道和海邊不到一兆距離重新排序` near a chunk boundary.
- Other substitutions such as `一杯清香` becoming `清爽` show that Whisper variability also exists, but the complete missing clauses and boundary-shaped corruption are the blocking failures addressed by this plan.

Therefore the current conclusion is deliberately two-part:

1. **Latency conclusion:** long-recording background transcription is worth pursuing; the improvement persists on genuine continuous, non-repeating audio.
2. **Quality conclusion:** the current fixed-chunk/midpoint/exact-overlap merger must not be enabled in production because it can omit or corrupt content. Silence-aware cutting, timestamp-safe deferred boundary ownership, integrity checks, and batch fallback are required before enablement.

Raw evidence is stored in `long_recording_results_continuous.jsonl`. The earlier `long_recording_results.jsonl` remains available only as superseded composite evidence.

> **Case labels A-D above are referenced later in Task 1 and Task 7. They are the confirmed, real-content failures this plan exists to fix. Every later fix must be checked against these specific cases by name, not only against aggregate pass/fail metrics.**

---

### Task 1: Establish Transcript Quality Metrics

**Files:**
- Create: `speedytype/transcript_quality.py`
- Create: `tests/test_transcript_quality.py`
- Modify: `scripts/run_long_recording_benchmark.py`

**Interfaces:**
- Produces: `normalize_transcript(text: str) -> str`
- Produces: `TranscriptQuality(reference, candidate)` with coverage, duplicate, ordering, number-preservation, and key-term metrics.
- Produces: `passes_quality_gate(metrics) -> tuple[bool, list[str]]`.

- [ ] Write failing tests for an omitted sentence, duplicated boundary phrase, reordered sentence, changed number, and unchanged transcript.
- [ ] Include Cases A-D from the Evidence section verbatim as named regression fixtures, not only synthetic constructed cases, so the metrics are proven against the actual confirmed failures before being trusted on new data.
- [ ] Run `python -m pytest tests/test_transcript_quality.py -q`; expect missing-module failure.
- [ ] Implement sentence/token normalization without hiding numbers or technical terms.
- [ ] Implement metrics and explicit failure reasons.
- [ ] Require no missing complete sentence, no new repeated sentence, preserved number set, ordered coverage of at least 98%, and key-term recall of at least 98%.
- [ ] Add the metrics and gate result to every benchmark record.
- [ ] Run focused and full tests.

### Task 2: Silence-Aware Chunk Planner

**Files:**
- Create: `speedytype/chunking.py`
- Create: `tests/test_chunking.py`

**Interfaces:**
- Produces: `ChunkingConfig` containing every initial parameter.
- Produces: `AudioFrame(start_seconds, end_seconds, rms)`.
- Produces: `SilenceRegion(start_seconds, end_seconds, noise_floor)`.
- Produces: `PlannedChunk(index, start_seconds, end_seconds, cut_reason, overlap_seconds)`.
- Produces: `detect_silence_regions(samples, sample_rate, config) -> list[SilenceRegion]`.
- Produces: `plan_dynamic_chunks(duration, silences, config) -> list[PlannedChunk]`.

- [ ] Write failing tests for silence near 25 seconds, a breath shorter than 600ms, continuous speech through 45 seconds, silence before the 15-second minimum, and trailing audio.
- [ ] Verify RED with `python -m pytest tests/test_chunking.py -q`.
- [ ] Calculate 20ms RMS frames and a rolling lower-percentile noise floor over five seconds.
- [ ] Use separate enter/exit thresholds to prevent silence-state oscillation.
- [ ] After 15 seconds, select the first valid silence centered nearest the preferred 25-second point.
- [ ] If no valid silence exists, force a cut at 45 seconds with 1.5 seconds of overlap.
- [ ] Natural cuts retain only 200ms context and must never create a chunk shorter than 15 seconds.
- [ ] Ensure chunks cover the complete audio timeline with no unplanned gaps.
- [ ] Run focused and full tests.

### Task 3: Timestamp-Safe Segment Committer

**Files:**
- Create: `speedytype/segment_merge.py`
- Create: `tests/test_segment_merge.py`
- Modify: `speedytype/quasi_streaming.py`

**Interfaces:**
- Produces: `TimedSegment(start_seconds, end_seconds, text, chunk_index)`.
- Produces: `MergeDecision(segment, action, reason)`.
- Produces: `MergeResult(text, committed_until_seconds, decisions, gaps, duplicates)`.
- Produces: `merge_timed_segments(chunks, duration_seconds) -> MergeResult`.

- [ ] Write failing tests for identical overlap, punctuation differences, near-duplicate overlap, a segment crossing a natural cut, a segment crossing a forced cut, a timeline gap, and out-of-order API output.
- [ ] Verify RED.
- [ ] Convert every Whisper segment timestamp to absolute recording time.
- [ ] Commit complete segments from each chunk's safe core; never classify ownership solely by midpoint.
- [ ] Defer a boundary-crossing segment until the adjacent chunk is available.
- [ ] Resolve overlap using normalized similarity plus timestamp intersection, not exact suffix matching alone.
- [ ] Preserve the more complete version of two overlapping segments and record the decision.
- [ ] Sort output by absolute timestamps and flag uncovered timeline regions containing non-silent audio.
- [ ] Replace the current `merge_text_with_overlap` production path while keeping it for old benchmark reproducibility.
- [ ] Run focused and full tests.

### Task 4: Structural Integrity Validator and Batch Fallback

**Files:**
- Create: `speedytype/hybrid_validation.py`
- Create: `tests/test_hybrid_validation.py`
- Modify: `speedytype/quasi_streaming.py`

**Interfaces:**
- Produces: `HybridValidation(ok, reasons, transcript_duration_coverage, text_density)`.
- Produces: `validate_hybrid_result(plan, merge_result, chunk_results, audio_activity) -> HybridValidation`.

- [ ] Write failing tests for a failed chunk request, empty active-speech chunk, non-silent timeline gap, abnormal transcript shrinkage, repeated paragraph, and valid output.
- [ ] Verify RED.
- [ ] Reject missing/failed chunk requests and uncovered active-speech intervals.
- [ ] Reject implausibly short transcript density relative to neighboring chunks.
- [ ] Reject repeated sentences introduced at boundaries.
- [ ] On rejection, call the existing whole-file batch transcription once and record `fallback_used=true` plus reasons.
- [ ] Never send rejected hybrid text to Gemini or clipboard.
- [ ] Run focused and full tests.

### Task 5: True Recording-Time Background Pipeline

**Files:**
- Modify: `speedytype/audio.py`
- Create: `speedytype/hybrid_pipeline.py`
- Create: `tests/test_hybrid_pipeline.py`
- Modify: `speedytype/daemon.py`
- Modify: `speedytype/config.py`

**Interfaces:**
- Produces: `HybridTranscriber.feed(samples, timestamp)`.
- Produces: `HybridTranscriber.finish(final_path) -> HybridOutcome`.
- Produces: `HybridOutcome(raw_text, tail_seconds, request_seconds, request_count, fallback_used, diagnostics)`.

- [ ] Write failing tests using a fake recorder clock and fake Whisper backend: under-threshold recording, natural cut, forced cut, release during an in-flight request, request failure, and fallback.
- [ ] Verify RED.
- [ ] Keep recording into the authoritative full WAV while also feeding samples to the planner.
- [ ] Do not issue a chunk request before recording duration crosses 90 seconds; earlier samples remain available in the full WAV.
- [ ] Once hybrid mode activates, enqueue closed chunks during recording and process them serially on one worker.
- [ ] On release, close the final chunk, wait for the worker, validate/merge, and fall back to the authoritative WAV if needed.
- [ ] Pass only validated raw text into the existing Gemini and paste stages.
- [ ] Keep short recordings on the unchanged batch function.
- [ ] Expose configuration through `AppConfig` and `.env` overrides without adding Settings UI until parameters stabilize.
- [ ] Run focused and full tests.

### Task 6: Request Cost and Failure Controls

**Files:**
- Modify: `speedytype/hybrid_pipeline.py`
- Modify: `speedytype/latency.py`
- Create: `tests/test_hybrid_cost_controls.py`

**Interfaces:**
- Produces diagnostics for request count, cumulative request seconds, chunk reasons, retries, and fallback cost.

- [ ] Write failing tests for maximum request count, repeated API throttling, worker backlog, and fallback after partial work.
- [ ] Limit active Whisper calls to one.
- [ ] Stop starting new background calls after repeated 429/5xx responses and defer to batch at release.
- [ ] Set a request-count ceiling derived from recording duration and minimum chunk size.
- [ ] Record request amplification relative to batch in benchmarks and latency logs.
- [ ] Ensure fallback cannot recursively re-enter hybrid processing.
- [ ] Run focused and full tests.

### Task 7: Deterministic Benchmark and Quality Gate

**Files:**
- Modify: `scripts/run_long_recording_benchmark.py`
- Modify: `test_audio_long/manifest.json`
- Create: `long_recording_hybrid_v2_results.jsonl`
- Modify: `KNOWN_LIMITATIONS.md`
- Modify: `POC_REPORT.md`

**Interfaces:**
- Consumes the existing 126.412s and 133.796s real recordings plus the 294.792s continuous TTS recording.

- [ ] Run batch at least three times per recording and save all raw outputs/timings.
- [ ] Run hybrid v2 at least three times per recording with identical configuration.
- [ ] Compare each hybrid output with its same-run batch reference using Task 1 metrics.
- [ ] For each of Cases A-D specifically, record whether it is now resolved and attribute the resolution to a specific task. If a case is resolved by a combination of tasks or remains unresolved, state that explicitly rather than only reporting an aggregate pass/fail.
- [ ] Record STT tail, complete Gemini/paste tail, request amplification, fallback rate, chunk locations, cut reasons, merge decisions, and quality metrics.
- [ ] Inspect the 295-second output against `continuous_tts_script.txt`, not only against imperfect batch text.
- [ ] Confirm natural cuts dominate when pauses exist and forced cuts remain bounded.
- [ ] Run one quiet-room and one realistic-background-noise recording to validate adaptive RMS behavior.

## Production Enablement Gate

Hybrid mode may be enabled by default only when all conditions pass:

1. Every tested recording has at least 98% ordered content coverage.
2. No complete source sentence is omitted.
3. No new repeated sentence is introduced.
4. All numbers and at least 98% of configured technical terms are preserved.
5. The 294.792-second case improves complete post-release tail by at least 50% after Gemini and paste are included.
6. Request-time amplification stays at or below 2.5x batch.
7. No unrecovered API failure produces partial pasted text.
8. Fallback succeeds for every intentionally injected failure.
9. Windows full tests and latency regression remain green.
10. The target Mac passes the same long-recording workflow after the existing macOS handoff checklist.
11. Cases A-D are each individually confirmed resolved per Task 7's attribution record; a passing aggregate metric alone does not satisfy this gate if any named case remains unresolved or its resolution is unverified.

If any gate fails, production remains batch-only. The failed metric and raw result must be documented rather than lowering the threshold after seeing results.

## Recommended Delivery Sequence

1. Implement Tasks 1-4 entirely offline with synthetic signals and recorded Whisper payload fixtures.
2. Run an offline replay against the three existing WAV files.
3. Implement true recording-time background processing in Tasks 5-6.
4. Execute paid API benchmarks only after offline merge and validation tests pass.
5. Enable hybrid behind `HYBRID_TRANSCRIPTION_ENABLED=false` first.
6. Change the default only after every production gate passes.

## Implementation Result (2026-07-11)

Tasks 1-6 were implemented behind `HYBRID_TRANSCRIPTION_ENABLED=false`. The Windows suite reached 122 passing tests, including named Case A-D metric fixtures, clean/noisy VAD signals, timestamp merging, structural fallback, circuit breaking, non-blocking Recorder feed, pipeline integration, and latency diagnostics. A real Windows daemon smoke with a temporary one-second threshold completed record, hybrid Whisper, Gemini, paste, and shutdown successfully.

Three paid API runs per audio case were saved to `long_recording_hybrid_v2_gate_results.jsonl`:

| Case | Batch complete tail | Hybrid complete tail | Improvement | Request amplification | Raw quality gate |
|---|---:|---:|---:|---:|---:|
| 126.412s real | 9.521s | 6.003s | 37.0% | 1.70x | 0/3 |
| 133.796s real | 9.491s | 6.306s | 33.6% | 2.18x | 0/3 |
| 294.792s continuous TTS | 23.185s | 6.423s | 72.3% | 1.83x | 0/3 |

The structural validator passed all final runs without fallback. This only proves that requests completed and no actionable active-audio gap, empty chunk, or repeated sentence was detected; it does not override the reference-based content gate.

### Case A-D Attribution

- **Case A:** Resolved in raw output in all three final runs. The result is attributable to the combined Task 2 natural-silence plan and Task 3 full timestamped-segment commit; no single-task ablation was performed.
- **Case B:** Resolved in raw output in all three final runs, attributable to the same Task 2+3 combination.
- **Case C:** Resolved in raw output in all three final runs, attributable to the same Task 2+3 combination.
- **Case D:** Not resolved. Raw output consistently contained `海邊不到一兆距離重新排序` in the final gate runs. Merge logs classified the segment as distinct rather than an overlap duplicate, so this occurrence is a Whisper lexical error inside one chunk, not evidence that Task 3 dropped or duplicated a boundary. Gemini produced a semantically sensible itinerary, but exact-phrase matching is not a valid polished-output judge because Gemini restructures text.

### Gate Decision

Production enablement is rejected. Gate 5 passes only for the 295-second case, gate 6 passes for all cases, and the Windows regression/failure controls pass. Gates 1-4 and 11 fail because every hybrid case missed at least one raw content requirement and Case D remains unstable. Real long-output paste timing and the target-Mac workflow were not completed, so gates 5 (including paste) and 10 also remain incomplete. The feature flag must remain `false`.
