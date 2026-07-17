# Toggle Recording and Persistent Overlay Design

**Date:** 2026-07-18

**Target release:** SpeedyType 0.5.4

**Status:** Approved design, pending implementation plan

## Goal

Make long recordings practical without requiring the user to hold a hotkey for
the entire recording. Daily daemon recording supports both the existing
push-to-talk mode and a new press-once-to-start, press-again-to-stop mode. Both
modes share the same validated recording limit, visible recording status, and
automatic stop behavior.

This design extends the approved complete-file FLAC long-recording path. It
does not change durable WAV capture, FLAC preparation, upload admission,
transcription, recovery, or the 25-minute ceiling.

## User-visible Behavior

Settings provides one recording-mode choice:

- **Hold:** press and hold the configured hotkey to record; releasing any key
  in the configured chord stops recording. This remains the default.
- **Toggle:** press the configured hotkey once to start; release at least one
  member of the configured key/chord so it is no longer active, then press the
  full hotkey again to stop.

The setting is persisted in `settings.json` and applied after daemon restart,
consistent with other daemon behavior settings. Invalid or unknown persisted
values safely fall back to Hold with a visible load warning.

The guided-recording workflow remains push-to-talk because its per-script-item
prompts and review loop are intentionally separate from daily daemon recording.
The daemon and its normal autostart path use the selected mode on Windows and
macOS through the shared controller logic.

## Hotkey State Model

The existing platform hotkey backends remain unchanged. They continue to emit
the configured hotkey activation and provide the existing release/timeout
waiter. A shared daemon recording controller owns these states:

1. `idle`
2. `recording-unarmed` — Toggle recording started, but the configured hotkey is
   still active.
3. `recording-armed` — Toggle recording is active and a new press may stop it.
4. `stopping`
5. `processing`

In Hold mode, activation starts recording and the existing release waiter
requests stop on release or timeout. In Toggle mode, activation starts
recording in `recording-unarmed`; a release watcher arms the next activation
without stopping. Only an activation in `recording-armed` requests stop.

The existing release waiter rearms as soon as the configured chord is no longer
active, matching Hold mode's established any-member-release semantics. This
prevents key repeat, a long initial press, or backend callback duplication from
immediately stopping a Toggle recording. Stop is an
idempotent controller operation protected by one lock/event. A second press,
timeout, recorder failure, and shutdown may race, but only the first accepted
stop drains capture and starts one processing operation.

## Time Limit and Automatic Stop

Both modes use the same validated `max_record_seconds`, whose product maximum
is 1,500 seconds. A controller-owned deadline watcher runs for every recording
and is independent of hotkey release behavior. It requests an automatic stop
when the deadline is reached unless another stop reason has already won.

The deadline is based on a monotonic clock. The overlay timer and stop decision
derive from the same start time and configured limit so the UI cannot display
a different limit from the recorder. The existing 60-second countdown-warning
threshold remains the default.

An automatic stop immediately drains the WAV and starts processing. It does
not wait for the warning message to disappear and does not automatically retry
any downstream API operation.

## Persistent Recording Overlay

The existing `RecordingPill` remains in its current floating location and is
extended rather than replaced:

- From start until the final warning interval, it shows the recording indicator,
  audio-level animation, and elapsed time formatted as `MM:SS`.
- During the final 60 seconds, it switches to a visually prominent remaining
  time display.
- At automatic stop, that same pill location displays
  `已達錄音上限，自動停止` with warning styling.
- Processing begins immediately while the automatic-stop message remains
  visible for at least two seconds. The pill then shows processing if work is
  still running, or hides after the two-second minimum if processing already
  completed.

The timeout message is not a system notification or a second window. Qt widget
updates remain signal-driven on the GUI thread. Timer work stays off the GUI
thread and emits only elapsed/countdown/status values.

## Settings and Configuration

`AppSettings` stores a canonical `recording_mode` value of `hold` or `toggle`.
`AppConfig` exposes the validated value to the daemon. Settings UI uses two
clear mutually exclusive choices with Hold selected by default. Saving an
unsupported value is rejected; loading one produces Hold plus a warning and
does not crash startup.

The UI also continues to show the existing 60-to-1,500-second recording limit.
Changing either the hotkey, recording mode, or maximum duration requires a
daemon restart, and the Settings copy states this explicitly.

## Error Handling

- A recorder failure moves the controller out of recording state, retains the
  WAV under the existing recovery rules, and prevents a later timeout or hotkey
  event from starting duplicate processing.
- A very short Toggle recording follows the existing local no-API skip.
- A repeated activation received before the configured hotkey becomes inactive
  is ignored.
- Activations during `stopping` or `processing` are ignored.
- If the automatic-stop warning and processing completion overlap, overlay
  coordination preserves the warning for its minimum display interval and then
  hides cleanly; it never leaves a stale recording indicator.
- Restarting the daemon during recording relies on the existing durable WAV and
  recovery sidecar behavior; startup reports the incomplete recording without
  auto-submitting it.

## Scope Boundaries

Included:

- daily daemon Hold/Toggle selection on Windows and macOS;
- persistent elapsed/countdown overlay;
- same-location automatic-stop warning;
- shared timeout and idempotent stop state;
- settings, documentation, and automated regression coverage.

Excluded:

- changes to guided-recording interaction;
- segmented or streaming transcription;
- progressive transcript display;
- changes to provider requests, FLAC admission, or recording retention;
- platform-specific replacement hotkey libraries.

## Verification

Automated tests must prove:

- settings default, persistence, invalid-value fallback/warning, config
  propagation, and UI save/load behavior;
- Hold starts once and stops on release;
- Toggle does not stop until the first hotkey activation becomes inactive and a
  second distinct activation occurs;
- duplicated/repeated callbacks cannot create duplicate stop or processing;
- timeout stops both modes exactly once and reports the automatic reason;
- elapsed display uses `MM:SS`, final 60 seconds use remaining time, and timeout
  renders the approved message at the pill location;
- processing begins without waiting for the timeout message duration;
- recorder and processing failures leave the controller reusable and retain
  owned WAV files;
- existing complete-file FLAC, settings, hotkey, daemon, and clipboard suites
  remain green.

Release gates remain:

- real Windows tests for Hold, Toggle, second-press stop, 25-minute auto-stop,
  overlay timing, and one injected failure;
- the equivalent real macOS tests, including no warning sound, menu-bar/Dock
  behavior, and permissions;
- a real at-least-24-minute recording on each platform before v0.5.4 is tagged.

## Acceptance Criteria

- Hold remains the safe default and preserves current behavior.
- Toggle starts on one activation and stops only on a separate activation after
  the configured hotkey has first become inactive.
- Both modes automatically stop at the same configured limit, never process a
  recording more than once, and retain the WAV on failure.
- The floating pill continuously tells the user that recording is active and
  shows elapsed time until the final 60-second countdown.
- Automatic stop is shown at the pill location with the approved text while
  processing starts immediately.
- Windows automation passes; real Windows/macOS release gates are explicitly
  pending until executed on target hardware.
