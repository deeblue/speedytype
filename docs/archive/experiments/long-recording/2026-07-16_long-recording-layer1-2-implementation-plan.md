# SpeedyType 30-Minute Recording — Implementation Plan

**Layer 1 committed / Layer 2 committed after Layer 1 acceptance / Layer 3 conditional and deferred**

- Date: 2026-07-16
- Status: Phase 0 + Layer 1 feasibility evaluated; capture path passes, single-request authoritative upload hypothesis rejected
- Predecessor: `2026-07-16_long-recording-hybrid-transcription-investigation.md`
- Approved amendment: 2026-07-16 review against the current recorder, API, Hybrid pipeline, and provider configuration

## 0. Decision Summary

Hybrid segmented text as final output is **rejected** (0/6 across two feasibility rounds; investigation §6.1 stands). Production design:

- **Layer 1** — Compressed single-request batch transcription is the sole authoritative text source.
- **Layer 2** — In-recording transcription is retained but demoted to a live provisional draft, atomically replaced by Layer 1 output. The current Round 1 in-memory pipeline must not be reused unchanged.
- **Layer 3** — Overlap + timestamp-aligned merge. Not started. Gated behind Layer 1+2 outcome review and explicit entry criteria (§5).

Scope guardrails:

- Phase 1 supports the existing OpenAI STT path first. Multi-provider STT routing is separate future work; the current `LLM_PROVIDER` setting controls polishing, not transcription.
- OpenAI currently documents `ogg` as an accepted transcription upload format, but the actual configured endpoint/deployment still requires an integration test.
- Raise the configurable recording ceiling from 540 seconds to 1800 seconds. Keep the default at 60 seconds and preserve existing saved values.

## 1. Layer 1 — Authoritative Batch Path

### 1.1 Capture (carried over from investigation §5.2 / §6.2, now production requirements)

- **R1.** Single uninterrupted microphone input stream for the entire recording; never stop/restart the capture device.
- **R2.** The sounddevice callback only copies each block into a capture record containing a monotonic starting sample index. A dedicated writer thread owns all WAV writes. WAV rotation, if enabled for recovery or draft consumption, occurs only in that writer at an exact sample index; never stop/restart the capture device.
- **R3.** On stop: cease accepting new frames → fully drain the primary writer queue → close/finalize the original recording. The realtime callback must not block on disk or network I/O. The primary queue is bounded and must never silently drop frames; queue exhaustion is a fatal recording error that stops capture, preserves all successfully written audio, and reports the exact last committed sample. Do not copy the WebRTC repo's drop-on-full behavior.
- **R4.** Per-segment PCM conservation checks (byte-length sum + concatenated SHA-256 vs. continuous reference) run in CI/self-test mode; in production, log segment hashes for audit.
- **R5.** Full original WAV (or a lossless, indexed segment set) is written to a recoverable SpeedyType data/session directory, not an anonymous OS temporary file, and is always preserved until final text is confirmed delivered. Session metadata records sample rate, channels, sample count, segment index/range/hash, and recording state.

### 1.2 Encode & submit

- **R6.** Encode the full recording to a single compressed mono upload artifact. Target: **Ogg/Opus ~32 kbps** (preferred; ~7 MiB @ 30 min) with **MP3 64 kbps fallback** (~14 MiB) if the configured endpoint rejects Ogg/Opus. Both are far under the legacy `whisper-1` 25 MiB limit. The multipart filename and MIME type must match the actual format; the current hard-coded `audio/wav` behavior must be removed.
- **R7.** Encoding failure → fall back to raw WAV if within size limit; otherwise fail with a clear, user-readable error. **Never lose the recording** (investigation §6.3 rule retained).
- **R8.** Single Whisper request on the full recording. No text merging exists anywhere in the final-text path.
- **R9.** Phase 1 remains OpenAI-STT-only. Design a separate STT provider abstraction before adding Gemini, Azure OpenAI, AssemblyAI, Deepgram, or other endpoints; do not infer STT routing from the existing polishing-provider setting. Provider-specific size/format rules belong behind that future abstraction.

### 1.3 Tail-latency reductions (real seconds, no quality risk)

- **R10.** Continuous shadow pre-encode: feed the same ordered PCM blocks to one long-lived background Ogg/Opus encoder and finalize one container at stop. Do **not** independently encode segments and byte-concatenate Ogg/Opus files; chained containers, timestamps, and encoder delay would introduce a new boundary risk. The original WAV writer is authoritative. The encoder uses a separate bounded queue; if it falls behind or fails, disable/discard the shadow artifact and re-encode from the lossless original after stop without affecting capture.
- **R11.** Measure and log: stop→upload-start, upload duration, STT duration, total stop→final-text. These are the Layer 1 KPIs.

### 1.4 Acceptance criteria — Layer 1

- **A1.** Three reference recordings (A/B/C) plus one new ≥28-minute recording transcribe successfully end-to-end via compressed batch.
- **A2.** Compressed-batch transcript quality: run the self-consistency control first (§3), then require compressed-vs-WAV batch differences to be within the measured Whisper run-to-run noise band.
- **A3.** Zero recordings lost across all failure-injection tests (encode fail, network fail, API 4xx/5xx, disk full during rotation).
- **A4.** stop→upload-start < 2 s with pre-encode enabled (R10).
- **A4a.** At 1800 seconds, callback time, primary/encoder queue high-water marks, process RSS, writer throughput, and encoder throughput remain inside recorded test limits; no PortAudio overflow/underflow status is ignored.
- **A4b.** Existing settings retain their saved duration, a new install defaults to 60 seconds, and the UI accepts a maximum of 1800 seconds.

## 2. Layer 2 — Live Draft Transcript

### 2.1 Behavior

- **R12.** During recording, closed persistent segments or a strictly bounded rolling buffer are transcribed opportunistically and streamed to the UI as a **draft**, visibly labeled (e.g., 「即時草稿 — 最終文字處理中會自動更新」). Do not reuse the current `HybridTranscriber` unchanged: it retains the complete float32 recording, repeatedly concatenates it, and repeatedly scans the growing timeline.
- **R13.** Draft text is never persisted as final output, never fed to summary/normalization, never exported. It is UI-only state.
- **R14.** On stop, Layer 1 runs; on completion, final text **atomically replaces** the draft (single swap, no partial merge).
- **R15.** Draft pipeline failures (segment error, empty result, rate limit) degrade silently to "draft unavailable" — they must never block or delay Layer 1.
- **R16.** Draft API spend is bounded: cap concurrent draft requests and draft audio at ~1.0–1.1× realtime. Because Layer 1 still submits the complete recording, the combined STT bill is approximately 2.0–2.1× recording duration. Expose an explicit settings toggle, show the incremental estimate in usage/capacity calculations, and ship draft opt-in until actual cost is accepted.
- **R17.** Draft state crosses into Qt only through signals and remains bounded UI-only state. The existing recording pill is not a transcript viewer; Layer 2 requires a dedicated non-focus-stealing draft surface. It must not alter the active application's clipboard, focus, or document before the final atomic replacement/paste.

### 2.2 Acceptance criteria — Layer 2

- **A5.** Draft appears within ~30–60 s of recording start and updates continuously on the three reference recordings.
- **A6.** Kill-test: force-fail every draft request → Layer 1 final text still arrives, timing unaffected (±5%).
- **A7.** Final swap leaves no draft remnants in UI, storage, exports, or summary input.
- **A8.** User-visible wait after stop (spinner-with-nothing-to-read time) ≈ 0 when draft succeeded.
- **A9.** A 30-minute draft run stays within an explicit RSS/CPU envelope and shows no whole-recording in-memory accumulation or repeated full-timeline silence scan.
- **A10.** Usage statistics report draft audio and authoritative batch audio separately and show their combined cost.

## 3. Validator Recalibration (prerequisite — small, do first)

Required before A2 and before any future Layer 3 work:

- **C1.** Transcribe each reference recording **unsplit, twice**, same provider/params.
- **C2.** Score run 2 against run 1 with the existing validator (coverage, missing sentences, duplicates, number preservation, keyword recall).
- **C3.** Record results as the **noise floor**. If unsplit-vs-unsplit fails coverage ≥ 0.98 or number preservation, the current thresholds are measuring Whisper non-determinism, and all gates (A2, Layer 3 entry) are restated relative to the noise floor instead of absolute values. Pay specific attention to whether 「數字保留」 failures are normalization variance (digit vs. 中文數字 vs. spelled-out) — if so, the number check needs a normalization pass before comparison.

## 4. Rollout Sequence

1. **Phase 0** — Validator recalibration (§3). Small effort, unblocks everything.
2. **Phase 1A** — Capture durability: R1–R5, sample-indexed callback records, bounded primary queue, writer ownership, stop/drain semantics, recoverable sessions, and failure injection.
3. **Phase 1B** — Compressed authoritative upload: R6–R10, continuous shadow encoder, post-stop fallback encode, format-aware multipart upload, and endpoint compatibility tests.
4. **Phase 1C** — Daemon integration and observability: R11, 1800-second ceiling, final state/error handling, and acceptance A1–A4b. Ship behind the existing flow for long recordings first, then make it the default after reference tests pass.
5. **Phase 2** — Layer 2 draft UI: R12–R17, acceptance A5–A10. It starts only after Layer 1 acceptance and ships opt-in first.
6. **Checkpoint** — Outcome review (§5). Only after this do we decide on Layer 3.

> Note from investigation §7: macOS live file rotation during a real long recording was never tested — add it explicitly to the Phase 1 test matrix.

## 5. Layer 3 — Conditional Future Work (not scheduled)

**Entry criteria — start Layer 3 only if, after Phase 2 has been in use:**

- **E1.** A concrete automated consumer needs final-quality text materially faster than Layer 1 delivers (e.g., summary must start < N seconds after stop, and measured Layer 1 tail exceeds N), **or** recordings grow beyond what single-request compression supports (~60–90 min); **and**
- **E2.** The recalibrated validator (§3) exists, so pass/fail is meaningful.

**Design (pre-committed so scope doesn't drift):**

- Segments overlap 15–30 s at rotation boundaries (capture layer already supports this cheaply).
- Request word-level timestamps (`verbose_json`); merge by aligning tokens in the overlap window on timestamp + token match — never butt-joint string concatenation.
- Same three reference recordings, per investigation §7; pass bar: 3/3 within noise floor on all recalibrated gates, zero missing sentences beyond noise floor, numbers preserved post-normalization.
- Any failure → Layer 1 remains the final-text source; Layer 3 output is discarded, exactly like the Layer 2 draft.

**Kill criterion:** if Layer 3 fails the recalibrated gate on these recordings in one full round, stop — Layer 1+2 is the permanent design and no further hybrid rounds are run without new entry evidence.

## 6. Open Items

- **O1.** Confirm Ogg/Opus acceptance, MIME handling, duration, and transcript quality on the actual OpenAI endpoint/configuration in use. Azure or other provider deployment checks are deferred with multi-provider STT routing.
- **O2.** Decide draft-feature default (on/off) based on per-minute STT pricing of the customer's BYOAI provider.
- **O3.** Retention policy for original WAVs after confirmed final text (align with existing SpeedyType storage policy).
- **O4.** Set measured queue capacities and RSS/CPU acceptance limits from Windows and macOS stress runs; do not choose them from guesswork.

## 7. 2026-07-16 Implementation and Evaluation Outcome

This plan was used as a test/estimation vehicle. Work was isolated on branch `feature/long-recording-layer1-eval`; it is not merged into `master`.

### 7.1 Phase 0 — validator noise floor

Each unsplit reference WAV was transcribed twice with the same `whisper-1` configuration:

| Recording | Coverage | Missing sentences | Numbers | Absolute gate |
|---|---:|---:|---|---|
| A, 522.860 s | 1.0000 | 0 | pass | pass |
| B, 480.324 s | 0.9642 | 14 | fail | fail |
| C, 480.324 s | 1.0000 | 0 | pass | pass |

Conclusion: the validator must use a per-recording measured noise floor. Recording B proves that two unsplit WAV requests can fail the absolute 0.98/number gate without any segmentation or encoding change.

Artifact: `C:\Users\HPDOCK\AppData\Roaming\SpeedyType\hybrid_test_audio\validator_noise_floor_round1.jsonl`

### 7.2 Capture path — pass

The feasibility branch implements a sample-indexed writer queue, writer-thread-owned WAV I/O, drain-before-close, explicit queue-full failure, recoverable recording paths, and daemon error propagation.

A synthetic 1800-second capture was fed at approximately 1000× realtime:

- accepted/written frames: 28,800,000 / 28,800,000;
- lost or duplicated frames: 0;
- final WAV duration: 1800.0 seconds;
- queue high-water: 6;
- process RSS growth: 921,600 bytes (~0.88 MiB);
- wall time: 2.87 seconds; CPU time: 0.375 seconds;
- output WAV size: 57,600,044 bytes.

Conclusion: the Layer 1 capture/writer architecture is viable on this Windows machine. A real macOS 30-minute capture remains required before shipping.

Artifact: `C:\Users\HPDOCK\AppData\Roaming\SpeedyType\hybrid_test_audio\capture_writer_30min_benchmark.json`

### 7.3 Lossy single-request batch — reject

#### Ogg/Opus 32 kbps

| Recording | Upload/source ratio | Encode time | Best coverage | Missing | Numbers | Within WAV noise floor |
|---|---:|---:|---:|---:|---|---|
| A | 0.1125 | 7.89 s | 0.9308 | 37 | fail | no |
| B | 0.1106 | 6.97 s | 0.9721 | 6 | pass | yes |
| C | 0.1192 | 7.13 s | 0.9783 | 9 | pass | no |

Result: 1/3 within the measured WAV noise floor.

#### MP3 64 kbps

| Recording | Upload/source ratio | Encode time | Best coverage | Missing | Numbers | Within WAV noise floor |
|---|---:|---:|---:|---:|---|---|
| A | 0.2501 | 1.43 s | 0.9203 | 36 | fail | no |
| B | 0.2501 | 1.30 s | 0.9110 | 36 | fail | no |
| C | 0.2501 | 1.36 s | 0.9817 | 6 | fail | no |

Result: 0/3 within the measured WAV noise floor.

Conclusion: API acceptance and smaller files do not establish transcription equivalence. Neither tested lossy format may become the authoritative default. The prototype therefore keeps lossy preparation behind an explicit internal experimental opt-in.

Artifacts:

- `C:\Users\HPDOCK\AppData\Roaming\SpeedyType\hybrid_test_audio\opus_batch_feasibility_round1.jsonl`
- `C:\Users\HPDOCK\AppData\Roaming\SpeedyType\hybrid_test_audio\mp3_batch_feasibility_round1.jsonl`

### 7.4 Lossless and newer-model alternatives — reject for the 30-minute requirement

- FLAC measured ratios were 0.50–0.54. Projected 30-minute files are 27.7–29.7 MiB, still above the legacy `whisper-1` 25 MiB limit.
- A 1683.508-second (about 28-minute), 53,872,300-byte real-speech composite WAV was built from A+B+C plus silence.
- `gpt-4o-mini-transcribe` without server chunking rejected it as `input_too_large`.
- `gpt-4o-mini-transcribe` with `chunking_strategy=auto` accepted it in 62.06 seconds, but scored coverage 0.8563, 221 missing sentences, 8 new duplicates, and number failure against the three reference transcripts.
- `gpt-4o-transcribe` with `chunking_strategy=auto` rejected it because 1683.508 seconds exceeds that model's reported 1400-second maximum.

Conclusion: none of the tested single-request paths satisfies both the 30-minute limit and the existing transcript-quality expectation.

### 7.5 Rollout decision

- **Keep:** sample-indexed capture, writer queue, exact drain, recoverable WAV storage, error visibility, format-aware MIME, validator noise-floor tool, and 1800-second stress coverage.
- **Do not enable:** automatic Opus/MP3 authoritative upload.
- **Do not start Layer 2 production UI yet:** a provisional draft does not solve the missing authoritative final-text path and would add approximately another 1.0–1.1× STT charge.
- **Layer 1 decision:** R6/R8/R10 as originally written are not viable and must be redesigned before release.

The next authoritative-path investigation must choose one of these explicitly:

1. large persistent audio segments with boundary overlap/timestamps and a validator that does not rely on an impossible full-file fallback;
2. an STT provider proven to accept ≥30-minute lossless input in one job;
3. local/on-device long-form transcription;
4. an ongoing realtime transcription session whose final quality is validated against the same recordings.

No option should be promoted without a new 3/3 reference pass plus one real ≥28-minute macOS recording.

---

*End of plan — Capture feasibility passed; authoritative upload redesign required*
