# SpeedyType Architecture

This document describes the current production path. Historical proposals and
experiments are evidence, not active architecture; see the
[decision register](DECISIONS.md) for the selected alternatives.

## Configuration and Credentials

CLI arguments select an optional configuration file, then application settings
and environment-compatible values are resolved. API secrets are read from the
operating-system keyring first, with process environment and legacy `.env`
values retained as migration/compatibility sources. New keys entered in
Settings remain masked and are stored in Windows Credential Manager or macOS
Keychain.

## Platform Boundary

The shared daemon delegates global-hotkey, paste, application-lifecycle, and
status-menu behavior to platform implementations. Windows presents a system
tray icon. macOS runs as an AppKit accessory application with a menu-bar icon
and Quartz event tap, so normal daemon operation does not show a Python Dock
icon. See [the platform decision](DECISIONS.md#2026-07-16--use-native-macos-hotkey-and-accessory-application-boundaries).

## Recording State and Feedback

The daemon owns one tokenized Hold/Toggle state machine. Every start enters
`PENDING_START`; Toggle stop enters `PENDING_STOP`. A fixed 80 ms qualification
stage applies on Windows and macOS. Provisional capture and its recovery
sidecar begin immediately, but the recording pill remains hidden until the
matching token confirms. A short start stops and joins capture, then may remove
only its explicitly owned `capturing` or `captured` WAV/sidecar. A short Toggle
stop returns to armed recording without interrupting capture or UI. Stale
release/timer workers cannot act on a later token.

Confirmed Hold starts stop immediately on release. Confirmed Toggle starts
rearm on release and stop on the next confirmed activation. Each rejection
appends one privacy-safe `HOTKEY_DEBOUNCE` line directly to the persistent
daemon log. See [the qualification decision](DECISIONS.md#2026-07-18--qualify-recording-hotkey-activations-cross-platform).

Duplicate events cannot create a second processing path.
While active, the recording pill shows elapsed `MM:SS`, then a final 60-second
countdown. The configured ceiling is at most 25 minutes; automatic stop uses
the same guarded stop-and-process transition and displays a pill-local warning.

## Durable Capture and Recovery

One microphone stream writes sample-indexed mono 16 kHz PCM16 WAV data. Capture
rotation and drain-on-stop conserve input frames. Recovery sidecars describe
retained recordings and processing state so startup can report evidence without
automatically uploading or deleting it.

## Lossless Admission and Transcription

After stop, SpeedyType encodes the durable WAV to temporary lossless FLAC. It
validates container/format, exact sample count, and decoded PCM SHA-256, then
measures the actual file size. Only a validated file strictly below 23 MiB is
admitted to one complete-file `whisper-1` request with
`response_format=json` and no timestamps. A short WAV may be uploaded only when
FLAC preparation fails and the WAV passes both duration and byte guards. See
[the long-recording decisions](DECISIONS.md#2026-07-18--use-durable-wav-and-validated-lossless-flac).

Chunked transcription is not part of the production path. Current research on
borrowing Deepgram/DeepL-style boundary semantics for better local chunk
planning is tracked separately in
[Chunking Strategy Proposal](CHUNKING_STRATEGY_PROPOSAL.md).

## Polish, Paste, and Usage Records

The raw transcript can be sent to the configured LLM for polishing. The paste
layer preserves existing clipboard text, places the output into the active
application, and restores supported clipboard content. The operation records
latency and estimated STT/LLM usage; Settings combines those records with
`pricing.json` to visualize current-month cost, budget, and remaining capacity.

## Failure Boundaries

- Empty or effectively silent input is skipped without crashing the daemon.
- A recoverable WAV is retained when encoding, validation, admission,
  transcription, polishing, or paste fails.
- Oversize or invalid uploads fail closed; SpeedyType does not bypass the
  admission guard or silently segment production audio.
- Startup recovery reports retained paths and never silently deletes or uploads
  evidence.
- Process and operating-system crash recovery is supported through durable WAV
  and sidecar state; sudden-power-loss survival is not claimed.
