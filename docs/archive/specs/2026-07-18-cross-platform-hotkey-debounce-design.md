# Cross-Platform Hotkey Debounce Design

**Date:** 2026-07-18

**Status:** Implemented and verified

## Goal

Reject unintended, very short recording-hotkey activations consistently on
Windows and macOS without losing the beginning of a valid recording. The same
80 ms qualification rule applies to Hold start, Toggle start, and Toggle stop.

Rejected activations must not show the recording pill, start downstream
processing, or leave WAV/recovery artifacts. They must leave one privacy-safe
diagnostic record in the persistent daemon log.

## Current Gap

The daemon currently treats the platform hotkey callback as an immediately
valid activation. It creates the recording session and shows the pill before
the release waiter can determine that a key event lasted only a few
milliseconds. On Windows, the `keyboard` package invokes the callback
asynchronously and does not preserve the Win32 injected-event flag, so a short
physical or synthetic F9 event can appear as a brief recording pill even when
the user did not intentionally record.

macOS already owns key-down/key-up state in its Quartz event tap, suppresses
autorepeat, and ignores SpeedyType-marked synthetic events. Other applications
can still generate a matching event, so debounce belongs above both platform
backends rather than in one platform implementation.

The current documentation promises one serialized Hold/Toggle state machine,
but it does not define whether an activation is qualified before becoming a
recording action. This design makes that boundary explicit.

## Non-Goals

- Do not replace the Windows hotkey backend with Raw Input or a native Win32
  hook in this change.
- Do not change the macOS Quartz event tap.
- Do not expose a debounce setting in Settings or `.env`.
- Do not debounce Hold release after a start has been confirmed.
- Do not change capture format, recovery durability, FLAC admission, STT, LLM,
  clipboard, paste, budget, or usage behavior.
- Do not retain rejected provisional audio for later processing.

## Selected Approach

Use immediate provisional capture with a fixed 80 ms, platform-neutral
activation qualification stage.

Delaying microphone capture until 80 ms would be simpler but could remove the
beginning of speech. Platform-specific debounce would provide more native event
detail but duplicate behavior and testing. Immediate provisional capture keeps
audio quality while centralizing the behavioral rule in the existing daemon
and recording-control boundary.

## User-Visible Behavior

### Hold mode

1. Key down begins provisional capture immediately.
2. No recording pill or countdown is shown during the first 80 ms.
3. If release occurs before 80 ms, SpeedyType cancels and removes the
   provisional artifacts.
4. If the key remains active for 80 ms, SpeedyType confirms recording, shows
   the pill, and starts normal elapsed/countdown feedback.
5. After confirmation, key release stops immediately through the existing
   stop-and-process path. Release has no second debounce delay.

### Toggle mode start

1. The first key down begins provisional capture immediately.
2. A release before 80 ms cancels the candidate without showing the pill.
3. At 80 ms the recording is confirmed and the pill becomes visible.
4. The following release rearms Toggle exactly as it does today.

### Toggle mode stop

1. A key down while Toggle is recording creates a pending-stop candidate.
2. The existing recording, pill, level display, elapsed time, and countdown
   continue during the 80 ms qualification window.
3. Release before 80 ms cancels only the stop candidate; recording continues.
4. Reaching 80 ms confirms stop and invokes the existing stop-and-process path
   exactly once, even if the key remains held afterward.

## State Model

`RecordingPhase` adds two phases:

- `PENDING_START`: a provisional capture exists but recording has not been
  confirmed for UI or processing.
- `PENDING_STOP`: Toggle recording continues while its stop press is being
  qualified.

Every activation candidate has an opaque token. Only events carrying the
current token may confirm or cancel it. This makes release/timer races and
stale worker completion deterministic.

The state transitions are:

```text
IDLE
  -- begin activation --> PENDING_START

PENDING_START
  -- release < 80 ms --> IDLE + CANCEL_START
  -- confirm at 80 ms, Hold --> RECORDING_ARMED + CONFIRM_START
  -- confirm at 80 ms, Toggle --> RECORDING_UNARMED + CONFIRM_START
  -- timeout/shutdown/failure --> existing guarded termination behavior

RECORDING_ARMED (Hold)
  -- release --> STOPPING + STOP

RECORDING_UNARMED (Toggle)
  -- release --> RECORDING_ARMED

RECORDING_ARMED (Toggle)
  -- begin activation --> PENDING_STOP

PENDING_STOP
  -- release < 80 ms --> RECORDING_ARMED + CANCEL_STOP
  -- confirm at 80 ms --> STOPPING + STOP
  -- recording timeout --> STOPPING + STOP; pending token invalidated
```

`RecordingAction` adds the exact members `BEGIN_START`, `CONFIRM_START`,
`CANCEL_START`, `BEGIN_STOP`, and `CANCEL_STOP`, while retaining `STOP` and
`NONE`. `RecordingControl` exposes `begin_activation() ->
tuple[RecordingAction, int | None]`, `confirm_activation(token: int) ->
RecordingAction`, and `hotkey_released(token: int) -> RecordingAction`.

The token is a controller-owned, monotonically increasing integer. An IDLE
begin returns `(BEGIN_START, token)`; an armed Toggle begin returns
`(BEGIN_STOP, token)`. Confirmation returns `CONFIRM_START`, `STOP`, or `NONE`.
Release returns `CANCEL_START`, `CANCEL_STOP`, the existing confirmed Hold
`STOP`, or `NONE`. No caller may infer state only from elapsed wall time.

## Activation Workers and Locking

Each accepted raw key-down creates one activation candidate with two bounded
workers:

- a confirmation worker waits until the monotonic 80 ms deadline, then checks
  the platform adapter's `is_hotkey_active(hotkey) -> bool` before confirming;
- a release worker uses the existing platform
  `wait_until_hotkey_released()` interface.

Both workers present the same token to `RecordingControl`. If the hotkey is no
longer active at the deadline, the confirmation worker cancels instead of
confirming. This prevents a delayed release worker from validating a key that
was physically or synthetically released before 80 ms. The controller lock
serializes the winner and makes the loser a no-op. The existing lock order is
preserved: daemon session lock first, then `RecordingControl`'s internal lock.
No worker may update Qt widgets directly; it emits existing Qt signals after a
successful state transition.

The public platform dispatcher adds `is_hotkey_active()`. Windows delegates to
the existing `keyboard.is_pressed()` state; macOS reads the event-tap service's
explicit active state. This is a small adapter addition, not a rewrite of
either platform event backend.

For Toggle stop, a new release worker is created for the second press because
the worker used to rearm the first press has already exited. Confirmation
stops at the 80 ms deadline; the later key-up only retires the stale candidate.

The maximum-recording timeout has priority over a pending Toggle stop. It
invalidates the candidate token and enters the existing idempotent timeout
path. Shutdown and capture failure also invalidate candidate tokens so a late
timer cannot display the pill or start processing.

## Provisional Capture and Cleanup

`PENDING_START` creates the normal WAV path and recovery sidecar, then starts
the recorder immediately. When a release wins before 80 ms:

1. mark that session as debounce-cancel requested;
2. signal `Recorder.stop()` exactly once;
3. join the capture thread outside the session lock;
4. reacquire the lock and verify the same session/token still owns
   `PENDING_START` cancellation;
5. remove the WAV and its recovery sidecar;
6. return the controller to `IDLE` without FLAC, STT, LLM, paste, usage, or
   error UI.

The capture thread normally transitions the sidecar from `capturing` to
`captured` before cleanup. A focused recovery helper may remove only an
explicitly unconfirmed session in one of those states. It must reject deletion
of `failed-retained`, `encoding`, `ready`, `processing`, or any artifact not
owned by the canceling session.

Only release-before-threshold is an intentional discard case:

- capture/write failure retains the artifact under existing failure rules;
- process/OS crash and daemon shutdown retain whatever the normal recovery
  path can recover;
- cleanup failure leaves the WAV/sidecar available for recovery, records the
  failed cleanup result, and does not submit the audio for processing;
- Toggle pending-stop cancellation creates no new audio artifact and therefore
  performs no file cleanup.

This narrow deletion authority preserves the project's never-silently-lose-a-
valid-recording rule while defining sub-80 ms candidates as unconfirmed input,
not valid recordings.

## Persistent Diagnostic Record

Every rejected start or stop activation appends exactly one line to the
existing `speedytype_daemon.log`, even when a manually launched daemon's stdout
is attached to a terminal rather than redirected to that file.

The line prefix and JSON payload are:

```text
HOTKEY_DEBOUNCE {"timestamp_utc":"2026-07-18T06:00:00.000000+00:00","platform":"win32","mode":"hold","hotkey":"f9","intent":"start","held_ms":24.3,"threshold_ms":80,"decision":"rejected","cleanup":"removed"}
```

Required fields:

- UTC timestamp;
- `sys.platform` value;
- normalized configured hotkey;
- recording mode;
- intent: `start` or `stop`;
- measured monotonic hold duration in milliseconds;
- fixed threshold in milliseconds;
- decision: `rejected`;
- cleanup: `removed`, `retained-after-failure`, or `not-applicable`.

The record must not contain audio, transcription text, other keystrokes, API
keys, clipboard content, or a full WAV path. Appending the diagnostic line is
best effort: a logging failure must not resurrect a canceled activation or
crash the daemon. Concurrent rejected events are serialized so JSON records do
not interleave.

Confirmed activations are not logged by this feature; normal daemon and latency
records continue unchanged.

## Error Handling

- Failure to allocate/start provisional capture follows the existing recording
  failure path and invalidates the pending token.
- A capture failure is never reclassified as a debounce rejection and its
  recovery evidence is not deleted.
- A cleanup failure is logged, leaves recoverable artifacts, returns the daemon
  to a usable idle state, and never enters downstream processing.
- A stale confirmation/release worker performs no state, UI, recorder, file,
  or log action.
- Repeated raw key-down events while a candidate is pending are ignored.
- Existing idempotent stop, session ownership, timeout, and processing guards
  remain authoritative after confirmation.

## Testing Strategy

### Recording-control unit tests

- Hold begins pending, short release cancels, 80 ms confirm arms, and confirmed
  release stops.
- Toggle short start cancels; confirmed start plus release rearms.
- Toggle pending-stop short release restores recording; confirmed stop stops
  exactly once.
- Duplicate activation while pending has no effect.
- Timer/release races yield one winning action.
- Timeout wins over pending-stop and invalidates its token.
- Stale tokens cannot modify the next recording.

### Daemon orchestration tests

- provisional capture starts before confirmation;
- pill/countdown/level UI is not emitted before confirmation;
- confirmation emits recording UI and starts countdown once;
- rejected start stops and joins capture, removes WAV/sidecar, logs once, and
  never invokes the processing pipeline;
- rejected Toggle stop keeps the existing capture/UI alive and logs once;
- confirmed Toggle stop processes once;
- capture failure retains evidence and is not deleted;
- cleanup failure retains evidence and logs `retained-after-failure`;
- timeout, shutdown, stale worker, and overlapping-event regression cases pass.

### Recovery and logging tests

- cleanup helper removes only owned `capturing`/`captured` provisional
  artifacts;
- protected recovery states cannot be removed;
- log line is valid JSON after the fixed prefix and contains exactly the
  approved non-sensitive fields;
- manual-console and redirected-daemon launch paths both write the persistent
  record;
- concurrent append attempts produce complete individual lines.

### Platform and regression verification

- Existing Windows polling and macOS event-tap adapter contract tests remain
  unchanged and pass.
- No real 80 ms sleep is used in unit tests; monotonic clock, candidate deadline,
  and workers are controlled deterministically.
- Full daemon recovery, recording control, overlay, FLAC, pipeline, release,
  and documentation suites pass.
- A Windows real-device smoke test covers intentional Hold, intentional Toggle
  start/stop, injected or synthetic sub-threshold activation, and diagnostic
  log output.
- The existing macOS hardware release gate adds short Hold and short Toggle
  start/stop checks; no separate long-duration test is introduced.

## Expected Implementation Scope

Primary files:

- `speedytype/recording_control.py`
- `speedytype/daemon.py`
- `speedytype/recording_recovery.py`
- `speedytype/platform/hotkey.py`
- `speedytype/platform/_windows_hotkey.py`
- `speedytype/platform/_macos_hotkey.py`
- `tests/test_recording_control.py`
- `tests/test_daemon_recovery.py`
- `tests/test_recording_recovery.py`
- `tests/test_platform_hotkey.py`

Current documentation updated after implementation:

- `docs/current/user/README.md`
- `docs/current/user/MAC_SETUP.md`
- `docs/current/engineering/ARCHITECTURE.md`
- `docs/current/engineering/DECISIONS.md`
- `docs/current/engineering/KNOWN_LIMITATIONS.md` only if implementation leaves
  a new externally relevant limitation.

Expected size is approximately 350–550 changed lines including tests. Platform
event-hook implementations, settings schema/UI, overlay rendering, audio
format, and the downstream processing pipeline remain structurally unchanged;
the platform adapters only expose current active-key state.

## Acceptance Criteria

- A start or Toggle-stop press held for less than 80 ms is rejected on both
  platforms.
- Hold/Toggle actions held for at least 80 ms preserve current behavior after
  confirmation.
- Provisional capture begins immediately, but the recording pill and countdown
  do not appear before confirmation.
- Rejected start removes its WAV and sidecar and never incurs STT/LLM/paste or
  usage activity.
- Rejected Toggle stop leaves the active recording uninterrupted.
- Every rejection writes one persistent privacy-safe daemon-log record with the
  correct intent, duration, threshold, and cleanup result.
- Cleanup/capture failures retain recoverable evidence; no valid confirmed
  recording gains a new silent-deletion path.
- Timeout, shutdown, repeated activation, timer/release race, and stale-token
  behavior remain idempotent.
- Windows automated/real-device smoke checks and the existing macOS hardware
  gate cover the new behavior.
