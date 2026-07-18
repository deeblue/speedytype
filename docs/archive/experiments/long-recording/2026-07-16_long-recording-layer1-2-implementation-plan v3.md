# SpeedyType 30-Minute Recording — Implementation Plan

**Layer 1 capture prototype evaluated / authoritative transcription path under evaluation / Layer 2 blocked / Layer 3 conditional and deferred**

- Date: 2026-07-16
- Status: Capture prototype passed a Windows synthetic stress test; §8 candidate round executed and stopped per S3 (§9); next round defined in §10
- Reading guide: this document is a cumulative record. Sections marked **Historical** or **Executed** are completed or superseded and must not be re-run. Only §10 contains open work.
- Predecessor: `2026-07-16_long-recording-hybrid-transcription-investigation.md`
- Approved amendment: 2026-07-16 review against the current recorder, API, Hybrid pipeline, and provider configuration

## 0. Current Decision Summary (authoritative)

This section and §10 are the authoritative plan. Sections §1, §3, and §4 preserve the original hypothesis for audit only; §8 was the executed candidate-round protocol and §9 its results — both are complete. **Nothing before §10 is to be implemented or re-run** where it conflicts with §7, §9, or §10.

- **Layer 1 capture** — Keep the sample-indexed writer prototype, but describe it as Windows-synthetic validated rather than ship-ready until real Windows/macOS capture and failure-injection gates pass.
- **Layer 1 authoritative transcription** — The lossy OpenAI single-request, Gemini 3.5 Flash, and faster-whisper CPU hypotheses are rejected for the tested configurations. Round 2 evaluates lossless `whisper-1` overlap/timestamp merge first and staged hardware-accelerated local engines second, exclusively through §10.
- **Layer 2** — In-recording transcription remains a possible live provisional draft, atomically replaced by authoritative output. It stays blocked until the selected §10 path passes the release gates in §8.5; the current Round 1 in-memory pipeline must not be reused unchanged.
- **Layer 3** — A minimal overlap + timestamp-aligned merge **feasibility spike** is open in §10.4. Production Layer 3 remains unapproved until that spike passes and §8.5 release gates are satisfied.

Scope guardrails:

- Existing `LLM_PROVIDER` controls polishing, not transcription. Candidate A is an isolated STT feasibility adapter; a production multi-provider abstraction is designed only after selection.
- Provider model IDs, API behavior, price, limits, prompts, and decoding parameters must be recorded with every run; no moving `latest` alias may be used for a release decision.
- Raise the configurable recording ceiling from 540 seconds to 1800 seconds. Keep the default at 60 seconds and preserve existing saved values.

## 1. Historical Layer 1 Hypothesis — Superseded by §7 and §8

> **Do not implement this section as a production design.** R6, R8, and R10 were rejected by the results in §7.3–§7.5. R1–R5 remain prototype requirements subject to the release gates in §8.5. The text below is retained to explain what was tested.

### 1.1 Capture (carried over from investigation §5.2 / §6.2, now production requirements)

- **R1.** Single uninterrupted microphone input stream for the entire recording; never stop/restart the capture device.
- **R2.** The sounddevice callback only copies each block into a capture record containing a monotonic starting sample index. A dedicated writer thread owns all WAV writes. WAV rotation, if enabled for recovery or draft consumption, occurs only in that writer at an exact sample index; never stop/restart the capture device.
- **R3.** On stop: cease accepting new frames → fully drain the primary writer queue → close/finalize the original recording. The realtime callback must not block on disk or network I/O. The primary queue is bounded and must never silently drop frames; queue exhaustion is a fatal recording error that stops capture, preserves all successfully written audio, and reports the exact last committed sample. Do not copy the WebRTC repo's drop-on-full behavior.
- **R4.** Per-segment PCM conservation checks (byte-length sum + concatenated SHA-256 vs. continuous reference) run in CI/self-test mode; in production, log segment hashes for audit.
- **R5.** Full original WAV (or a lossless, indexed segment set) is written to a recoverable SpeedyType data/session directory, not an anonymous OS temporary file, and is always preserved until final text is confirmed delivered. Session metadata records sample rate, channels, sample count, segment index/range/hash, and recording state.

### 1.2 Rejected encode-and-submit hypothesis

- **R6.** Encode the full recording to a single compressed mono upload artifact. Target: **Ogg/Opus ~32 kbps** (preferred; ~7 MiB @ 30 min) with **MP3 64 kbps fallback** (~14 MiB) if the configured endpoint rejects Ogg/Opus. Both are far under the legacy `whisper-1` 25 MiB limit. The multipart filename and MIME type must match the actual format; the current hard-coded `audio/wav` behavior must be removed.
- **R7.** Encoding failure → fall back to raw WAV if within size limit; otherwise fail with a clear, user-readable error. **Never lose the recording** (investigation §6.3 rule retained).
- **R8.** Single Whisper request on the full recording. No text merging exists anywhere in the final-text path.
- **R9.** Phase 1 remains OpenAI-STT-only. Design a separate STT provider abstraction before adding Gemini, Azure OpenAI, AssemblyAI, Deepgram, or other endpoints; do not infer STT routing from the existing polishing-provider setting. Provider-specific size/format rules belong behind that future abstraction.

### 1.3 Rejected shadow-encode hypothesis

- **R10.** Continuous shadow pre-encode: feed the same ordered PCM blocks to one long-lived background Ogg/Opus encoder and finalize one container at stop. Do **not** independently encode segments and byte-concatenate Ogg/Opus files; chained containers, timestamps, and encoder delay would introduce a new boundary risk. The original WAV writer is authoritative. The encoder uses a separate bounded queue; if it falls behind or fails, disable/discard the shadow artifact and re-encode from the lossless original after stop without affecting capture.
- **R11.** Measure and log: stop→upload-start, upload duration, STT duration, total stop→final-text. These are the Layer 1 KPIs.

### 1.4 Historical acceptance criteria — replaced by §8.4–§8.5

- **A1.** Three reference recordings (A/B/C) plus one new ≥28-minute recording transcribe successfully end-to-end via compressed batch.
- **A2.** Compressed-batch transcript quality: run the self-consistency control first (§3), then require compressed-vs-WAV batch differences to be within the measured Whisper run-to-run noise band.
- **A3.** Zero recordings lost across all failure-injection tests (encode fail, network fail, API 4xx/5xx, disk full during rotation).
- **A4.** stop→upload-start < 2 s with pre-encode enabled (R10).
- **A4a.** At 1800 seconds, callback time, primary/encoder queue high-water marks, process RSS, writer throughput, and encoder throughput remain inside recorded test limits; no PortAudio overflow/underflow status is ignored.
- **A4b.** Existing settings retain their saved duration, a new install defaults to 60 seconds, and the UI accepts a maximum of 1800 seconds.

## 2. Future Layer 2 — Live Draft Transcript (blocked until §8.5)

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

## 3. Historical Validator Recalibration — Round 1 only

> C1–C3 produced the preliminary results in §7.1. They are superseded by the repeated-run, distribution-based protocol in §8.1.

Required before A2 and before any future Layer 3 work:

- **C1.** Transcribe each reference recording **unsplit, twice**, same provider/params.
- **C2.** Score run 2 against run 1 with the existing validator (coverage, missing sentences, duplicates, number preservation, keyword recall).
- **C3.** Record results as the **noise floor**. If unsplit-vs-unsplit fails coverage ≥ 0.98 or number preservation, the current thresholds are measuring Whisper non-determinism, and all gates (A2, Layer 3 entry) are restated relative to the noise floor instead of absolute values. Pay specific attention to whether 「數字保留」 failures are normalization variance (digit vs. 中文數字 vs. spelled-out) — if so, the number check needs a normalization pass before comparison.

## 4. Historical Rollout Sequence — Superseded by §8.0

> This sequence assumed compressed authoritative upload was viable. Use §8.0 instead.

1. **Phase 0** — Validator recalibration (§3). Small effort, unblocks everything.
2. **Phase 1A** — Capture durability: R1–R5, sample-indexed callback records, bounded primary queue, writer ownership, stop/drain semantics, recoverable sessions, and failure injection.
3. **Phase 1B** — Compressed authoritative upload: R6–R10, continuous shadow encoder, post-stop fallback encode, format-aware multipart upload, and endpoint compatibility tests.
4. **Phase 1C** — Daemon integration and observability: R11, 1800-second ceiling, final state/error handling, and acceptance A1–A4b. Ship behind the existing flow for long recordings first, then make it the default after reference tests pass.
5. **Phase 2** — Layer 2 draft UI: R12–R17, acceptance A5–A10. It starts only after Layer 1 acceptance and ships opt-in first.
6. **Checkpoint** — Outcome review (§5). Only after this do we decide on Layer 3.

> Note from investigation §7: macOS live file rotation during a real long recording was never tested — add it explicitly to the Phase 1 test matrix.

## 5. Historical Layer 3 Production Criteria — Superseded for feasibility by §10

> This section remains the production rollout policy. §10.4 is a bounded feasibility spike authorized before Layer 2; it does not authorize production Layer 3 or weaken §8.5.

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

## 8. 2026-07-16 Amendment — Authoritative Path Redesign Plan **[Executed — see §9 for results; do not re-run]**

> Execution status of this section: §8.1 N1 baseline **complete** (§9.1). §8.2 Candidate A pilot **executed and rejected** at P5 (§9.2); P6 never ran and must not be run for `gemini-3.5-flash`. §8.3 Candidate B Windows pilot **executed and rejected** at L4 on performance (§9.4); L2 macOS pilot and L5/L6 **never ran** and are re-scoped in §10, not here. §8.4 S3 fired (§9.5). §8.5–§8.7 remain valid as future gates for whichever path §10 selects — they are gates, not pending tasks.

This was the executed Round 1 protocol. It is retained for audit only; §10 is the only executable section.

Status carried forward from §7.5:

- **Keep as a prototype:** capture architecture R1–R5. It passed an accelerated Windows synthetic writer test, not a real-device release test.
- **Rejected:** lossy Opus/MP3 as authoritative upload; R6/R8/R10 as originally written are void.
- **Blocked:** Layer 2 draft UI, until an authoritative final-text path passes §8.5.

### 8.0 Staged execution and stop rules

Do not run Candidate A and Candidate B as a full matrix in parallel. Use staged spikes so a failed premise stops further cost and engineering work:

1. Finish the validator and run-manifest changes in §8.1.
2. Candidate A pilot: one reference recording plus the 1683.508-second composite. Stop Candidate A immediately on upload incompatibility, truncation, incomplete final-minute content, or quality outside the provisional gate.
3. Candidate B Windows pilot: one reference recording. Stop before the full model matrix if extrapolated 30-minute tail or resources exceed the limits declared in §8.3.
4. Run repeated A/B/C plus composite tests only for candidates that pass their pilot.
5. Select one candidate using §8.4, then run both Windows and macOS release gates in §8.5.
6. Do not start Layer 2 until every §8.5 gate passes.

Before any paid run, record a maximum API-spend budget and estimated call count in the run manifest. Reaching that budget is a hard stop requiring a new decision. Model downloads require their expected size, source, checksum, and storage location to be recorded before download.

### 8.1 Step 1 — Repeated-run validator and reference controls

The §7.1 noise floor used one pair of runs per recording. It is not a distribution and cannot support a release decision.

- **N1. Baseline runs.** Transcribe each unsplit reference WAV A/B/C five times with an exact, unchanged `whisper-1` configuration. Store the raw transcript, request parameters, provider response metadata, start/end time, duration, and source-audio SHA-256 for every run.
- **N2. Candidate runs.** A candidate that advances past its pilot runs each A/B/C reference at least three times. Do not compare a single candidate sample with a repeated baseline.
- **N3. Distribution gate.** Compute every unordered pair of baseline runs per recording. For higher-is-better metrics use the fifth percentile of pairwise values; for lower-is-better counts use the ninety-fifth percentile. Because five runs produce only ten pairs, report the full distribution and do not describe these percentiles as population confidence bounds. Predeclare any fixed numeric allowance in the run manifest before candidate output is inspected; do not use the single worst observed pair as the floor.
- **N4. Directional comparison.** Compare every candidate transcript against every baseline transcript for the same recording. A candidate passes a metric only when its median comparison meets the baseline distribution gate and no candidate run exceeds the predeclared catastrophic limit: missing final-minute sentinel (or the final known audible-speech sentinel when the fixture intentionally ends in silence), missing critical number, new repeated passage, or ordered coverage below 0.90.
- **N5. Human reference.** Create a reviewed checklist for A/B/C and the composite covering critical numbers, product/proper names, section boundaries, and an audible sentinel phrase in the final minute. Automated model-vs-model agreement cannot override a failure of this checklist.
- **N6. Reproducibility.** Pin model ID, prompt, temperature, language, decoding parameters, client/library versions, and validator commit. Save all raw transcripts and a machine-readable run manifest. Never place API keys or keyring values in artifacts.
- **N7. Composite reference.** The concatenated baseline text may seed the composite reference, but a human must verify joins and silence boundaries before it is used as a gate. The current composite intentionally ends in about 200 seconds of silence, so its completeness control is the final known audible phrase from recording C (`就這樣子 OK`) plus a check that trailing silence creates no hallucinated passage; it cannot use a literal final-minute audible sentinel.

The validator implementation must have unit tests for pair generation, percentile direction, repeated candidate comparisons, catastrophic limits, and manifest secret redaction before paid/provider runs begin.

### 8.2 Step 2 — Candidate A: pinned Gemini long-audio job

This is a feasibility STT adapter, separate from the current Gemini text-polishing path. The current implementation only sends text to `generateContent`; it must not be presented as already supporting audio transcription.

- **P1. Fixed configuration.** Pin the exact Gemini model ID available at test time; the initial target is `gemini-3.5-flash`. Record the resolved model ID, API/client version, prompt, temperature, maximum output tokens, and pricing snapshot in the manifest. If that model is unavailable, amend the manifest and this section before running a replacement—do not silently substitute it.
- **P2. Files API lifecycle.** Because the composite is about 53.9 MB and exceeds the 20 MB inline-request limit, implement: upload lossless WAV → poll until usable/ACTIVE → submit one audio job without client-side chunking → collect response and usage → delete the remote file in `finally`. Define upload, processing, and generation timeouts; bounded retry policy; cancellation; deletion retry; and a visible retained-local-audio recovery state.
- **P3. Output completeness.** Treat max-token/length finish reasons, safety refusal, missing usage metadata, empty text, or absent final-minute sentinel as failure. Record finish reason and token usage. A response that is syntactically successful but truncated is not a pass.
- **P4. Privacy and cost.** Document that audio leaves the device, provider retention implications, input/audio and output-token cost, upload duration, processing duration, generation duration, and total wall time. Cost is calculated from the pinned model's pricing snapshot, not a generic Gemini estimate.
- **P5. Pilot.** Run one selected 8–9-minute reference and the composite once. Both must pass the human checklist; the reference must also meet the provisional §8.1 gate. Failure triggers the Candidate A stop rule.
- **P6. Full feasibility.** Only after P5, run A/B/C three times each and the composite at least twice. Each reference and composite must pass §8.1, including completeness and the final-minute sentinel.

### 8.3 Step 3 — Candidate B: pinned platform-specific local engines

Do not treat faster-whisper and whisper.cpp as interchangeable. They use different runtimes and platform acceleration paths.

- **L1. Windows pilot configuration.** On the current Intel Arc Windows host, evaluate `faster-whisper` with `large-v3-turbo`, CPU `int8`, fixed beam size, language, VAD, `condition_on_previous_text`, and thread count recorded in the manifest. Do not claim GPU acceleration: the documented faster-whisper GPU path requires NVIDIA CUDA, which this host does not provide.
- **L2. macOS pilot configuration.** On the representative Apple Silicon Mac, evaluate a pinned whisper.cpp release using Metal and a pinned `large-v3-turbo` quantized model. Record Mac model, RAM, macOS version, architecture, engine build flags, exact model filename, quantization, SHA-256, thread count, and decoding parameters. Do not reuse Windows performance assumptions.
- **L3. Distribution and first-run UX.** Record engine/model licenses, download URL, compressed and installed size, checksum validation, cache path, first-run download time, offline behavior, update/rollback method, and macOS quarantine/code-signing implications. A release cannot depend on an unverified mutable model download.
- **L4. Pilot.** Run one 8–9-minute reference on Windows first. Record decode wall time, peak RSS, average/peak CPU, model-load time, and transcript quality. Extrapolate the 30-minute decode tail and declare the acceptable limit before seeing a composite result. If the estimate exceeds that limit or system responsiveness becomes unacceptable, stop this configuration instead of running the full matrix.
- **L5. Full feasibility.** A configuration surviving L4 runs A/B/C three times each and the composite at least twice on Windows. The chosen configuration is then repeated on the representative Mac. All runs must use §8.1 and must not truncate or lose the final-minute sentinel.
- **L6. Resource pass bar.** In addition to transcript quality, record model load separately from decode, peak RSS/disk use, and realtime factor. The 30-minute post-stop tail limit and maximum RSS/CPU envelope must be explicitly approved from pilot evidence; “acceptable” without numeric bounds is not a pass criterion.

### 8.4 Step 4 — Candidate selection

- **S1. Required evidence.** A candidate is selectable only if A/B/C and the composite pass the repeated quality and completeness gates, its Windows and macOS deployment path is demonstrated, numeric tail/resource limits pass, and its failure behavior preserves the original recording.
- **S2. Comparison.** If both pass, document API cost, privacy, offline availability, first-run size/time, update burden, Windows/macOS performance, BYOAI alignment, and recovery behavior. Make the selection explicit; passing 3/3 alone does not select a winner.
- **S3. No winner.** If neither passes, stop and report the evidence before expanding scope. Overlap/timestamp segments (§7.5 option 1) are considered before a realtime final session (§7.5 option 4), but neither begins automatically.

### 8.5 Step 5 — Release gate for the selected path

- **F1. Real capture.** Record and process one new ≥28-minute real microphone session on Windows and one on representative macOS hardware. Synthetic writer results do not satisfy this gate.
- **F2. Reference for new audio.** Build a human-reviewed checklist/reference for each new long recording before judging quality; a new recording cannot inherit A/B/C's noise floor without its own reference evidence.
- **F3. Capture integrity.** Verify sample count/duration, PortAudio status, queue high-water, finalized recoverable WAV, session metadata, hashes/rotation where enabled, daemon restart recovery, and delivery of the final transcript.
- **F4. Failure injection.** Exercise disk-full/write failure, queue exhaustion, provider/network timeout, API 4xx/5xx or local-engine failure, cancellation, daemon crash/restart, and remote-file deletion failure where applicable. No accepted audio may be silently lost; the UI must identify the retained recording and recovery action.
- **F5. Cross-platform performance.** Record stop-to-submit/decode, upload/processing/generation or model-load/decode, stop-to-final-text, peak RSS/CPU, and disk usage on both platforms. All predeclared limits must pass.
- **F6. Regression.** Run the complete automated suite plus existing short-recording, empty-recording, push-to-talk, toggle-recording, settings, keyring, daemon, and tray behavior tests before merge.

### 8.6 Step 6 — Unblock Layer 2

Only after §8.5 passes:

- Layer 2 draft UI proceeds per R12–R17 and A5–A10, opt-in first.
- If the selected authoritative path is local, revisit R16 cost math: draft API audio may become the only per-minute STT cost.
- Layer 2 receives its own implementation plan and cannot weaken or bypass the selected authoritative path.

### 8.7 Deferred

- Layer 3 remains shelved per §5 and §8.4 S3.
- A production multi-provider STT abstraction is designed only after candidate selection and is informed by the selected provider/runtime.
- Retention policy O3 and measured resource limits O4 remain release decisions. Ogg compatibility O1 is closed as irrelevant to the authoritative path; draft default O2 remains blocked with Layer 2.

## 9. 2026-07-16 Execution Update — N1 complete, both candidates stopped **[Complete record — results final for the tested configurations]**

### 9.1 Repeated `whisper-1` baseline (N1)

Five fresh runs were completed for each reference recording (15 paid calls, approximately 123.6 audio minutes and US$0.7418 at the recorded US$0.006/minute rate). Each recording produced ten unordered baseline comparisons:

| Recording | Coverage fifth percentile | Missing-sentence 95th percentile | Duplicate 95th percentile | Number-preservation fifth percentile | Request latency range |
|---|---:|---:|---:|---:|---:|
| A, 522.860 s | 0.9830 | 6 | 0 | 0 | 23.52–31.94 s |
| B, 480.324 s | 0.9416 | 19 | 3 | 0 | 21.95–33.11 s |
| C, 480.324 s | 0.9919 | 0 | 0 | 1 | 20.24–25.04 s |

Consequences:

- Model-vs-model number preservation is unusable as an automated release gate for A and B because their baseline floors already reach zero. Their critical numbers require the human checklist in N5.
- Recording C is the stable pilot fixture. All five C runs end with `就這樣子 OK`, so this phrase is the final-audible-speech completeness control for C and the current composite.
- Artifact: `C:\Users\HPDOCK\AppData\Roaming\SpeedyType\hybrid_test_audio\validator_noise_floor_round2_manifest.json`.

### 9.2 Candidate A Gemini pilot — rejected before composite upload

The pinned `gemini-3.5-flash` Files API lifecycle succeeded for recording C: upload, ACTIVE polling, generation, normal `STOP` finish, sentinel presence, and remote deletion completed in 40.47 seconds. The transcript nevertheless failed the stable C quality gate:

- median ordered coverage: 0.9533 versus floor 0.9919;
- median missing sentences: 35 versus floor 0;
- median new duplicates: 1 versus floor 0;
- number preservation: fail versus floor pass;
- catastrophic repeated-passage check: fail.

The P5 stop rule therefore fired. The 53.9 MB composite was **not uploaded**, P6 was not started, and Gemini is not a selectable authoritative path from this feasibility round.

The first pilot manifest over-redacted usage keys such as `promptTokenCount`; actual token counts for this rejected run cannot be recovered from the artifact. A regression test now preserves non-secret usage counters while still redacting API keys, authorization values, keyring values, access/refresh tokens, passwords, secrets, and bearer strings. The paid run is not repeated merely to repair telemetry.

Artifact: `C:\Users\HPDOCK\AppData\Roaming\SpeedyType\hybrid_test_audio\gemini_long_audio_pilot_manifest.json`.

### 9.3 Next executable step

Candidate B proceeds only as the single Windows pilot in L1/L4. Record the exact faster-whisper/runtime/model versions, model source/hash/size, CPU-only configuration, system resources, download footprint, and a numeric 30-minute tail limit before running. Do not download or run the full A/B/C/composite matrix unless that one-file pilot passes.

### 9.4 Candidate B Windows pilot — rejected on performance

The Windows pilot used the predeclared configuration and limits:

- engine: `faster-whisper 1.2.1`, `CTranslate2 4.8.1`;
- model: `deepdml/faster-whisper-large-v3-turbo-ct2` at revision `4df90f75321148c3a29a9e2351b7ddf8f5b115a8`;
- verified `model.bin`: 1,617,884,929 bytes, SHA-256 `e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da`;
- CPU `int8`, 16 threads, one worker, beam size 5, language `zh`, VAD off, previous-text conditioning on;
- stop limits: extrapolated 30-minute decode ≤180 seconds and peak RSS ≤8 GiB.

Results on the Intel Core Ultra 9 285H Windows host:

- model download: 91.57 seconds; installed snapshot: 1,621,671,886 bytes;
- model load: 5.06 seconds;
- decode for 480.324 seconds of audio: 195.96 seconds;
- realtime factor: 0.408;
- extrapolated 30-minute decode: 734.34 seconds (about 12.24 minutes), over the 180-second limit by approximately 4.1×;
- peak RSS: 1,400,975,360 bytes (about 1.30 GiB), within the memory limit;
- sampled process CPU: approximately 1015%, indicating use of about ten logical cores on average.

The resource gate therefore failed independently of transcript scoring. No local composite or full matrix was run.

The raw local transcript used Simplified Chinese while the OpenAI baselines use Traditional Chinese. The current validator normalizes case, width, punctuation, and numbers but does not normalize Chinese script variants. It consequently reported coverage 0.6923 and a missing sentinel even though the raw ending contains the Simplified-Chinese equivalent `就这样子OK`. Candidate B quality is therefore **inconclusive**, not a trustworthy quality failure; a Simplified↔Traditional normalization layer and regression cases are required before comparing future cross-provider Chinese transcripts. This does not change the performance rejection.

Artifact: `C:\Users\HPDOCK\AppData\Roaming\SpeedyType\hybrid_test_audio\faster_whisper_windows_pilot_manifest.json`.

### 9.5 Stop decision

Candidate A failed the stable-C transcript-quality gate. Candidate B failed the predeclared Windows performance gate. Per S3, there is no authoritative-path winner and scope expansion stops here. Do not begin overlap/timestamp segmentation or realtime-final work automatically; report these results and make a new explicit design decision first.

The explicit design decision required by this section is recorded in §10.

## 10. 2026-07-16 Decision Memo — Round 2 Authoritative-Path Spikes **[Open work — the only executable section]**

### 10.1 What the §9 evidence establishes

- **E-1.** `whisper-1` on lossless audio remains the only engine that has ever met the transcript-quality bar on these recordings. Every rejected path (Opus, MP3, `gpt-4o-mini-transcribe` chunked, `gemini-3.5-flash`) failed by not being whisper-1 on lossless input. The sole obstacle between whisper-1 and 30 minutes is the 25 MiB request limit.
- **E-2.** The original anti-segmentation evidence is weakened by the §9.1 recalibration. Investigation §5.4 two-segment butt-joint scores (A 0.9578, B 0.9288, C 0.9835) were judged against an absolute 0.98 gate now known to be invalid; measured floors are A 0.9830, B 0.9416, C 0.9919. Recording B nearly clears its own floor with **zero overlap and string concatenation** — the worst possible method. Overlap + timestamp-aligned merge has never been tested and is not covered by any prior rejection.
- **E-3.** Candidate B's rejection covers exactly one configuration: faster-whisper, CPU int8, beam 5, VAD off, on Windows. The Intel Arc iGPU and NPU on the Core Ultra 9 285H were never used. Faster-whisper's documented GPU path is CUDA-only; whisper.cpp documents a cross-vendor Vulkan backend, while OpenVINO GenAI documents Whisper execution on Intel CPU/GPU/NPU subject to model, runtime, and driver compatibility. None of those accelerated configurations has passed a device/model preflight on this host. The §8.3 L2 macOS Metal pilot never ran. Candidate B quality remains formally inconclusive pending zh-Hant/zh-Hans normalization (§9.4).
- **E-4.** Candidate A's rejection is final for `gemini-3.5-flash`. A pro-tier retry is permitted under a new manifest but is assessed low-probability given the hallucinated-repeat failure mode; it is not scheduled.

### 10.2 Resolved Round 2 product decisions

- **Q-1. Tail limit — resolved.** Keep the predeclared **180-second maximum stop-to-authoritative-text tail for a 30-minute recording**. A future live draft cannot justify relaxing this limit while Layer 2 remains blocked behind authoritative-path acceptance. Accepting a 4–6-minute tail would require a separate decision memo that makes Layer 2 a release prerequisite and changes §8.6 ordering; Round 2 does neither. The §9.4 734-second CPU-only result remains rejected.
- **Q-2. Fixtures — resolved.** Keep B as a high-variance stress fixture, but do not let its loose model-vs-model floor be the only discriminator. Add a clean 8–10-minute real mixed Chinese/English fixture D with deliberate numbers, product/proper names, section boundaries, and a final audible sentinel. D requires a human reference plus five pinned `whisper-1` baseline runs before the full matrix. Pilot work continues to use stable fixture C.

### 10.3 Prerequisites (blocking; no provider or local-engine spike starts first)

- **PR-0. Direction-invariant validator floors.** `TranscriptQuality.compare(reference, candidate)` is directional, but the current `pairwise_qualities()` evaluates only the index-ordered left→right orientation. For every unordered pair `(x, y)`, compute both `x→y` and `y→x`, then collapse them into one symmetric pair observation: coverage and key-term recall use `min`; missing-sentence and new-duplicate counts use `max`; number preservation passes only when both orientations pass. Candidate-vs-baseline comparisons use the same symmetric aggregation. Add regression cases proving transcript-list reordering cannot change floors or pass/fail. Recompute A/B/C floors from stored N1 transcripts; no paid calls.
- **PR-1. Chinese script normalization.** Add evaluation-only dependency `opencc-python-reimplemented==0.1.7` in a separate `requirements-eval.txt`, not production `requirements.txt`. Canonicalize comparison text with OpenCC `s2t` after Unicode NFKC and before numeric/alphanumeric normalization. Preserve raw transcripts. Tests cover `就这样子OK` ↔ `就這樣子 OK`, idempotence, English abbreviations, numbers, Kyle, BIOS, API, Windows, Mac, and Spotlight. Recompute A/B/C floors after PR-1 and version the result as a new artifact; do not reuse §9.1 numeric gates under a changed normalizer.
- **PR-2. Human references.** Create machine-readable A/B/C checklists containing source-audio SHA-256, timecoded critical numbers, proper/product names, section-boundary phrases, final-audible sentinel, and reviewer/date. Listen at every cited timecode; model output alone cannot create ground truth. Add D using the same schema, then generate its five-run baseline under the PR-0/PR-1 validator. A/B number gates and every cross-engine result require these checklists.

### 10.4 Spike 1 (primary) — Size-aware overlap + timestamp merge on `whisper-1`

This is the minimal form of §7.5 option 1 and a bounded §5 feasibility spike. It is **not** the rejected fine-grained hybrid (17–20 butt-jointed chunks) and **not** the rejected two-segment string concatenation.

- **SP1-1. Size-aware lossless segmentation.** Encode self-contained FLAC upload artifacts from the recoverable WAV while retaining exact source `start_sample`/`end_sample`. Target ≤23 MiB per artifact, leaving margin below the 25 MiB request limit. For the 8–9-minute A/B/C/D fixtures, each half is expected to be roughly 4–5 MiB; for the 28-minute composite, each half is expected to be roughly 14–15 MiB. Use more than two segments if measured output would exceed 23 MiB; never assume two segments support arbitrary future duration.
- **SP1-2. Deterministic boundary.** Search ±60 seconds around the sample midpoint for at least 300 ms below a predeclared RMS threshold of −40 dBFS. Choose the qualifying interval with the lowest RMS, breaking ties by earliest source sample. If none qualifies, use the exact sample midpoint. Create a fixed 30-second overlap centered on that boundary and record every sample range/hash. Pre-overlap non-duplicated ranges must conserve the original PCM sample count and SHA-256 semantics from R4.
- **SP1-3. Word timestamps on the source timeline.** Request `whisper-1`, `verbose_json`, and `timestamp_granularities[]=word` for every artifact. Convert each returned timestamp before alignment: `absolute_seconds = segment.start_sample / sample_rate + relative_seconds`. Record encoding, upload, provider, and parsing duration separately because word timestamps add provider latency.
- **SP1-4. Deterministic merge.** Normalize overlap words through PR-1, retain their original text, and find the longest ordered matching sequence containing at least five normalized non-empty words whose absolute start times differ by ≤1.5 seconds per word. Select maximum match length, then minimum summed timestamp error, then earliest absolute time. More than one candidate after all tie-breakers, fewer than five matches, non-monotonic timestamps, or a provider response without words is a hard alignment failure. Emit segment 1 through the matched sequence once, then segment 2 after that sequence. Never fall back to butt-joint concatenation.
- **SP1-5. Parallelism and recovery.** Submit the two pilot artifacts concurrently with concurrency capped at two; future multi-segment runs use the same bounded concurrency. One request failure, rate limit after bounded retry, invalid timestamp response, or merge failure fails the authoritative run and retains the original WAV plus all diagnostic artifacts. Tail latency is FLAC preparation + the slower parallel provider call + merge, not the sum of provider durations.
- **SP1-6. Pilot.** Run C once only after PR-0/PR-1/PR-2. It must meet the recomputed symmetric C floors and C human checklist, preserve the final sentinel, produce no repeated passage, align unambiguously, and remain within the 180-second 30-minute-equivalent tail. Any failure stops Spike 1.
- **SP1-7. Full feasibility.** Only after pilot pass, run A/B/C/D three times each and the composite twice. The composite uses its known last-audible sentinel and must produce no text attributable to its trailing 200 seconds of silence. All automated and human gates apply.
- **SP1 budget.** Whisper billing follows total submitted duration, not request count. Two halves with a 30-second overlap submit approximately `original_duration + 30 seconds`: about 1.062× for C and 1.018× for the 28-minute composite, not 2×. Record the exact estimated call count, submitted seconds, price snapshot, and hard USD cap before the pilot/full round.

### 10.5 Spike 2 (secondary; may run independently after PR-0/PR-1/PR-2)

Each item is a new pinned configuration and does not re-run the rejected faster-whisper CPU configuration. Fixture C is the only pilot input; no backend advances merely because it loads successfully.

- **SP2-1. Windows device preflight.** Record Windows build, Intel graphics/NPU driver versions, OpenVINO/OpenVINO GenAI versions, and `Core().available_devices`. A missing target device stops that target without fallback masquerading as acceleration. Resolve the exact immutable Hugging Face revision for `openai/whisper-large-v3-turbo`, record export/quantization commands and hashes, and prove model conversion/load before timing. If that exact model is unsupported, fail the configuration; do not silently substitute a smaller model.
- **SP2-2. Windows order.** Test at most one configuration at a time: (1) OpenVINO GenAI 2026.0 WhisperPipeline on NPU; if it cannot load or misses a gate, (2) the same pinned model/config on Intel GPU; if that fails, (3) a pinned whisper.cpp Vulkan release/model. Vulkan is the documented cross-vendor whisper.cpp backend; SYCL is not assumed without a separately cited/pinned build. Stop each configuration after one C run on load, quality, 180-second extrapolated tail, responsiveness, or resource failure.
- **SP2-3. macOS Metal pilot.** On the representative Apple Silicon Mac, pin the whisper.cpp release, immutable quantized `large-v3-turbo` model and SHA-256, Metal build flags, macOS/hardware details, and first-run footprint. Run C once under the same quality and 180-second extrapolated-tail gates. Windows results do not proxy for Metal.
- **SP2-4. Decode variants.** Default each backend to its documented deterministic/greedy decode. A second beam/VAD variant is allowed only when the first configuration passes quality but narrowly misses performance; it receives a new manifest identity and one C run. Do not create a combinatorial engine×device×beam×VAD matrix.
- **SP2-5. Full feasibility.** Only a pilot configuration passing load, PR-0/PR-1 automated quality, PR-2 checklist, completeness, 180-second tail, RSS/CPU/device utilization, and restart/cleanup behavior may run A/B/C/D three times plus composite twice.

### 10.6 Selection and exits

- **SEL-1.** Selection criteria remain §8.4 S1–S2. A path must pass A/B/C/D and composite gates on Windows and representative macOS hardware before §8.5 release work.
- **SEL-2.** If Spike 1 passes and Spike 2 fails, size-aware lossless overlap/timestamp merge becomes the proposed authoritative path. Durations requiring more than two ≤23 MiB artifacts still use the same bounded-concurrency and alignment rules.
- **SEL-3.** If Spike 2 passes and Spike 1 fails, the exact winning backend/model/config—not “local Whisper” generically—becomes the proposed path.
- **SEL-4.** If both pass, decide using measured tail, cross-platform coverage, privacy, install/update size, offline behavior, support burden, and BYOAI alignment before production implementation.
- **SEL-5.** If both fail, realtime final transcription is the remaining §7.5 option. It does not start automatically; create a new evidence-based decision memo.

### 10.7 Implementation task map and TDD gates

1. **Validator invariance and zh normalization**
   - Modify `scripts/run_transcript_noise_floor.py` and `speedytype/transcript_quality.py`; create `requirements-eval.txt`.
   - Extend `tests/test_transcript_noise_floor.py` with list-reordering invariance, asymmetric missing/extra text, symmetric duplicate aggregation, OpenCC equivalence/idempotence, and preserved English/numbers.
   - RED: `python -m pytest tests/test_transcript_noise_floor.py -q` must fail on the new assertions before implementation. GREEN: the same command passes. Then regenerate floors from the existing round-2 manifest without API calls.
2. **Human-reference artifacts**
   - Create `docs/log/long-recording-reference-checklists.json` using the PR-2 schema and a validator that rejects missing SHA-256, reviewer/date, timecode, category, expected value, or sentinel fields.
   - Test the schema/loader without audio-network calls; checklist content requires user review of the cited audio times before approval.
3. **Word-timestamp API support**
   - Modify `speedytype/api.py` so `transcribe_audio_verbose(..., timestamp_granularities=("word",))` returns and validates `words`; retain existing segment behavior for existing callers.
   - Extend `tests/test_parsers.py` for valid words, missing/malformed words, multipart field names, and unchanged existing parsing. Run the focused test RED then GREEN.
4. **Segmenter and merger**
   - Create `speedytype/overlap_transcription.py` with typed `SourceSegment`, `TimedWord`, `Alignment`, `choose_boundary()`, `make_size_aware_segments()`, `to_absolute_words()`, and `merge_aligned_words()` interfaces implementing SP1-1–SP1-4.
   - Create `tests/test_overlap_transcription.py` covering exact sample conservation, silence/tie/fallback boundary choice, 30-second overlap, timestamp offset, unique alignment, ambiguous/no-match failure, repeated-text prevention, and >23 MiB re-segmentation.
   - No production daemon integration occurs in this task.
5. **Spike 1 runner**
   - Create `scripts/run_whisper_overlap_pilot.py` and `tests/test_whisper_overlap_pilot.py` with dry-run default, explicit `--execute`, two-request concurrency cap, resumable manifest writes, budget hard stop, retained-WAV failure behavior, latency fields, PR-0/PR-1/PR-2 gates, and C-only pilot stop rule.
   - Run all focused tests before the paid C pilot. Full feasibility requires a separate `--full` action that refuses to start unless the pilot manifest is a verified pass.
6. **Hardware pilot runners**
   - Keep OpenVINO and whisper.cpp runners separate so dependencies/builds cannot be confused. Each defaults to device/model preflight and requires explicit execution, immutable model revision/hash, resource sampling, raw transcript retention, and C-only stop rules.
   - macOS execution remains a user-run step on representative hardware; Windows must not fabricate a Metal result.
7. **Regression and handoff**
   - Run focused tests, then the complete project suite. Preserve the known Qt clipboard/COM ordering-flake evidence separately rather than hiding it.
   - Do not merge the evaluation branch or enable a production path until selection and §8.5 gates are complete.

### 10.8 2026-07-17 implementation update — PR-0/PR-1 complete

PR-0 and PR-1 are implemented on `feature/long-recording-layer1-eval`. No provider request or paid transcription was made during this update.

- `scripts/run_transcript_noise_floor.py` now collapses both comparison directions into one stricter symmetric observation. Baseline ordering and candidate-vs-baseline ordering regression cases pass.
- `speedytype/transcript_quality.py` now accepts an explicit normalizer and provides an evaluation-only OpenCC `s2t` normalizer. The default production normalizer and production `requirements.txt` remain unchanged.
- `requirements-eval.txt` pins `opencc-python-reimplemented==0.1.7`; OpenCC-specific tests run in the evaluation venv and skip explicitly in a production-only environment.
- `scripts/recompute_transcript_noise_floor.py` recomputes an immutable source manifest into a separate artifact, records the source SHA-256 and validator identity, and rejects attempts to use the same input/output path.

The existing Round 2 A/B/C runs were recomputed offline into:

`C:\Users\HPDOCK\AppData\Roaming\SpeedyType\hybrid_test_audio\validator_noise_floor_round3_symmetric_s2t_manifest.json`

Source manifest SHA-256: `3cb4c83eb509c167e526767843c45688d0af97d6938f2cd38a829b10bf65e03a`.

| Recording | Coverage min | Missing max | Duplicate max | Number rate min | Change from Round 2 |
|---|---:|---:|---:|---:|---|
| A, 522.860 s | 0.982985 | 6 | 1 | 0 | Symmetric comparison exposes one duplicate that the prior direction omitted. |
| B, 480.324 s | 0.941628 | 19 | 3 | 0 | Gate unchanged. |
| C, 480.324 s | 0.991942 | 0 | 0 | 1 | Gate unchanged. |

Verification evidence:

- Evaluation venv focused suite: `21 passed`.
- Production-environment transcript suite: `35 passed, 2 skipped`; the skips are the evaluation-only OpenCC module/case.
- Main suite excluding the known Windows Qt settings-dialog ordering case group: `319 passed, 2 skipped`.
- Settings-dialog suite excluding the isolated paste case: `37 passed, 1 deselected`.
- Isolated paste case: `1 passed`.
- `python -m compileall -q speedytype scripts` and `git diff --check`: passed; Git reported only existing LF-to-CRLF conversion warnings.

PR-2 remains open. It requires human listening and signed, timecoded A/B/C references plus the new fixture D before either Spike 1 or Spike 2 can start. No authoritative production path has been selected or enabled.

### 10.9 2026-07-17 PR-2 tooling update — automation complete, human gate open

The automatable PR-2 groundwork is implemented on `feature/long-recording-layer1-eval`:

- `scripts/long_recording_reference_checklist.py` provides a dependency-free schema loader and validator.
- Strict validation requires recordings A/B/C/D, valid source metadata, all five required check categories, in-range timecodes, exact expected values, `confirmed=true`, reviewer identity, and an offset-aware review date.
- `--allow-pending` validates draft structure without presenting it as ground truth. `--verify-audio` recomputes file size, SHA-256, and WAV duration.
- `docs/log/long-recording-reference-checklists.json` contains an A/B/C pending draft. Suggested phrases come only from stored model output, have null timecodes, remain unconfirmed, and are explicitly not ground truth.
- `docs/log/long-recording-reference-review.md` contains the listening/sign-off procedure and fixture D requirements.

Verification evidence:

- Checklist-focused tests: `13 passed`.
- Pending A/B/C validation with physical audio verification: `recordings=3`, `audio_verified=True`, `approved_for_quality_gate=False`.
- Strict validation intentionally rejects the draft with `checklist status must be approved`.
- Main suite excluding the known Windows Qt settings-dialog ordering group: `332 passed, 2 skipped`.
- Settings-dialog suite excluding the isolated paste case: `37 passed, 1 deselected`; isolated paste case: `1 passed`.
- Compile and diff-whitespace checks passed, with only the repository's existing LF-to-CRLF warnings.

PR-2 is still blocking. A human reviewer must listen to A/B/C, replace or confirm every proposed value, add exact timecodes and sign-off, then record and review D. No five-run D baseline, paid request, Spike 1, or Spike 2 was started by this update.

---

*End of plan — §8 candidate round executed and closed (§9); Round 2 decisions are fixed in §10.2 and execution begins with PR-0/PR-1/PR-2 only. Sections §1–§9 are record; do not re-run.*
