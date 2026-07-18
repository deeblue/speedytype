# Full-file FLAC Long-recording Production Design

**Date:** 2026-07-17

**Target release:** SpeedyType 0.5.4

**Status:** Approved architecture, pending implementation plan

## Decision

SpeedyType will use one complete-file `whisper-1` transcription request rather than segmented transcription. Microphone capture always writes recoverable mono 16-bit PCM WAV at 16 kHz. After recording stops, SpeedyType creates a lossless FLAC upload artifact, validates it, measures its actual byte size, and submits it with `response_format=json` without timestamp granularities.

The product recording ceiling is 25 minutes (1,500 seconds). This limit reduces the probability of exceeding the provider upload limit but never replaces an actual byte-size check. Segmented transcription, `verbose_json`, word timestamps, Opus, and MP3 are excluded from the production path.

## Evidence Behind the Decision

- Complete fixture C encoded as lossless FLAC passed the unchanged complete-WAV quality floors in three of three paid runs.
- The 1,683.508-second composite FLAC completed successfully but took 93.706 seconds, above the product's prior 60-second tail target.
- Full-file `verbose_json` with word timestamps failed the fixture C quality floor.
- Two-segment JSON prompt chaining failed its first quality run even with a silence boundary, no overlap, and exact PCM conservation.

The design therefore accepts complete-file JSON transcription latency and closes the tested segmentation paths. Progressive display may be considered separately; it must not replace or compete with the authoritative complete-file request.

## Capture and File Lifecycle

1. Capture writes directly to a durable WAV in SpeedyType's recordings directory through the sample-indexed writer.
2. The recorder drains queued samples before marking capture complete.
3. The WAV remains the authoritative recovery artifact throughout encoding, validation, upload, transcription, and downstream processing.
4. FLAC is written to a temporary sibling path and atomically promoted only after the encoder closes it successfully.
5. A successful complete pipeline may delete the temporary FLAC. WAV deletion follows the existing retention policy, but no failure path may delete or truncate it.
6. Encoding, validation, size, transport, provider, parsing, polishing, paste, daemon, or process failures retain the WAV and report its sanitized location to the user.

Each completed capture receives minimal recovery metadata sufficient to distinguish `captured`, `encoding`, `ready`, `processing`, `completed`, and `failed-retained` states. On daemon startup, SpeedyType scans its own recording directory for incomplete owned records. It does not submit them automatically: it reports recoverable recordings and exposes their locations so duplicate paid requests cannot occur silently.

## Lossless FLAC Preparation and Three Validation Layers

The encoder uses FLAC lossless compression only, with metadata removed and output fixed to mono 16 kHz PCM16 semantics. The source WAV is never modified in place.

Before upload, the FLAC must pass all three layers:

1. **Artifact and format validity:** the promoted file exists, is a regular non-empty `.flac`, is readable by the audio decoder, and reports one channel, 16 kHz, and PCM16 decoded samples.
2. **Lossless conservation:** decoded FLAC frame count equals WAV frame count and the decoded PCM SHA-256 equals the WAV PCM SHA-256.
3. **Admission guard:** recording duration is at most 1,500 seconds and the actual FLAC file size is strictly less than the internal `23 * 1024 * 1024` byte upload ceiling.

Any failed layer prevents FLAC upload. Validation results contain sizes, frame counts, hashes, and sanitized error categories but never transcript text, clipboard content, or credentials.

## Upload and Fallback Rules

The normal request fingerprint is fixed to:

- provider/model: OpenAI `whisper-1`;
- container/MIME: FLAC / `audio/flac`;
- `response_format=json`;
- existing vocabulary prompt;
- language and temperature not sent;
- timestamp granularities not sent.

WAV may be uploaded directly only when FLAC encoding or validation fails and the actual WAV size is strictly below the same 23 MiB internal ceiling. This fallback is expected only for short recordings and exists solely to satisfy the never-lose-recording rule. It uses the same complete-file JSON request fingerprint except for WAV container/MIME.

If FLAC exceeds the size ceiling, or if both FLAC and WAV are ineligible, SpeedyType sends no transcription request. It retains the WAV, marks the record `failed-retained`, and tells the user that the recording is saved but exceeds upload capacity. It never substitutes lossy encoding or segmentation.

The fallback decision and chosen upload artifact are recorded in latency/usage diagnostics without changing billing enforcement or exposing file contents.

## Settings and Runtime Limit

- `MAX_MAX_RECORD_SECONDS` becomes exactly `1500.0`.
- The Settings slider maximum and readable label become 25 minutes.
- The default remains 60 seconds.
- Saving through Settings cannot persist a value above 1,500 seconds.
- Existing settings above 1,500 seconds load as 1,500 seconds with a visible warning and are normalized on the next save.
- Runtime configuration independently enforces `60 <= max_record_seconds <= 1500`; manual JSON editing cannot bypass the daemon limit.
- Timeout auto-stop, countdown display, hold-to-record, and any later toggle-record mode consume the same validated maximum.

## Error Handling and User Feedback

- Empty recordings continue to skip locally without encoding or API use.
- Encoding errors are sanitized and do not include raw command output containing user paths beyond the intentionally reported preserved WAV path.
- A failed encode removes only an owned partial FLAC, never the source WAV.
- A failed validation retains both WAV and the diagnostic FLAC when useful; routine successful processing removes the temporary FLAC.
- An upload with uncertain provider disposition is not retried automatically during recovery.
- The daemon remains reusable after every preparation or transcription failure.
- User-visible copy distinguishes `recording preserved`, `upload too large`, `FLAC preparation failed; WAV fallback used`, and `transcription failed`.

## Components

- `speedytype/audio.py` and the sample-indexed writer own durable WAV capture and drain-on-stop.
- A focused `speedytype/flac_upload.py` module owns lossless encoding, atomic promotion, three-layer validation, byte admission, cleanup, and short-WAV fallback selection.
- A focused recovery module owns state metadata and startup discovery; it never calls provider APIs.
- `speedytype/pipeline.py` coordinates selected upload artifacts and records diagnostics.
- `speedytype/settings.py`, `config.py`, and `settings_dialog.py` jointly enforce and display the 1,500-second maximum.
- `speedytype/api.py` continues to map `.flac` to `audio/flac`; production uses its normal JSON transcription entry point.

The existing experimental `audio_encoding.py` Opus/MP3 implementation is not reused and must not enter the release.

## Verification

### Automated

- WAV capture frame conservation, queue drain, write failure, and retained-path tests.
- FLAC atomic-write success and cleanup-on-encoder-failure tests.
- Format, frame-count, PCM-hash, duration, and strict 23 MiB boundary tests.
- Normal FLAC selection, short-WAV encode-failure fallback, and long/ineligible fail-retained tests.
- Tests proving `response_format=json` and no timestamp granularities on both FLAC and WAV fallback requests.
- Pipeline tests proving the WAV survives every injected failure and temporary FLAC cleanup never targets the WAV.
- Recovery discovery tests proving no automatic API request or duplicate submission.
- Settings load/save/config/UI tests for 1,500 seconds, legacy over-limit normalization, warning visibility, and 60-second default compatibility.
- Full Windows test suite plus compile and diff checks.

### Release gates

- Complete the Windows simulation/automation suite for capture conservation,
  admission, timeout, failure injection, and daemon reuse. Windows is not a
  real-device release gate because these paths can be exercised deterministically
  in the development environment.
- On real macOS hardware, verify capture and FLAC preparation with frame/hash
  conservation, failure retention, menu-bar responsiveness, and daemon reuse.
  No minimum real-recording duration is required.
- Confirm on macOS that the Settings slider displays the 25-minute product
  ceiling and that automatic stop can be exercised with a bounded test
  configuration; a 24- or 25-minute live recording is not required.

No additional paid quality run is required to implement this design. Real-device release checks may stop before provider submission when validating capture, encoding, size, and recovery behavior.

## Acceptance Criteria

- Every recording is first durably captured as WAV.
- Normal eligible uploads use one complete lossless FLAC JSON request.
- All three FLAC validation layers pass before upload.
- Direct WAV upload occurs only after FLAC preparation failure and only below 23 MiB.
- Oversize and uncertain cases retain WAV and never silently retry, segment, or use lossy audio.
- Settings and runtime enforce a 25-minute/1,500-second maximum while preserving the 60-second default.
- Startup discovery reports incomplete owned recordings without automatically spending API budget.
- Windows automation and the single real-macOS integration gate pass before
  v0.5.4 is tagged.
