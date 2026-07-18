# macOS Native Hotkey and Daemon Stability Design

**Date:** 2026-07-16
**Target release:** SpeedyType 0.5.4
**Status:** Approved design, pending implementation plan

## Purpose

SpeedyType 0.5.3 exposes macOS-specific failures that do not occur on Windows:

- Python appears in the Dock even though the daemon already has a menu-bar icon.
- Holding the default F9 recording key produces the macOS key warning sound.
- capturing a new recording hotkey in Settings terminates Python with `EXC_BREAKPOINT (SIGTRAP)`.
- the daemon can terminate with a similar `trace trap` after transcription and polishing.
- a recording shorter than the Whisper minimum produces an unhandled worker-thread exception.

`docs/log/mac_log_002.rtf` proves that Settings crashed on a Python worker thread in `TSMGetInputSourceProperty`, reached through `libffi` and ctypes, after macOS rejected the dispatch queue. The main thread was in `QDialog::exec()`. The existing macOS hotkey implementation starts `pynput.keyboard.Listener` from a worker thread, so the design removes `pynput` from the macOS keyboard path instead of attempting to catch the native signal. The daemon crash in `mac_log_001` is strongly consistent with the same path but remains an inference unless its matching `.ips` report is recovered.

Windows hotkeys, clipboard handling, tray behavior, and dependencies must remain unchanged.

## Scope

This release will:

1. replace macOS `pynput` hotkey listening and capture with an in-process Quartz event tap;
2. replace macOS `pynput.Controller` paste with marked Quartz keyboard events;
3. run the daemon as an AppKit accessory application so only the menu-bar icon remains;
4. activate Settings and About correctly when opened from the menu bar;
5. skip recordings shorter than 0.1 seconds before any API call;
6. contain recoverable recording-processing exceptions without stopping the daemon;
7. document macOS permissions, update behavior, validation, and troubleshooting;
8. require real-Mac validation before the final 0.5.4 tag and release artifact.

This release will not enable or redesign hybrid transcription, package a signed `.app`, add a Swift helper, change CLI syntax, change settings-file format, or change Windows keyboard and clipboard implementations.

The two Windows recordings captured on 2026-07-16 (522.860 and 480.324 seconds) are retained outside the repository in the SpeedyType user-data directory for a later hybrid-transcription project. They are not release inputs and must not be committed.

## Architecture

### Native macOS event service

Create `speedytype/platform/_macos_event_tap.py` containing one process-wide `MacEventTapService`. It owns the Quartz event tap, a dedicated `CFRunLoop` thread, lifecycle synchronization, normalized key state, the configured daemon chord, and the temporary Settings capture state.

The service consumes virtual keycodes and modifier flags directly. It must not call text-input-source translation APIs. A fixed mapping covers the function keys and the letter, digit, navigation, punctuation, and modifier keys accepted by SpeedyType settings. Unknown keys fail capture visibly instead of being guessed from the current keyboard input source.

The service has two mutually exclusive modes:

- **daemon mode:** recognize the configured chord, invoke the hold callback once on the initial terminal-key down event, signal release once on terminal-key up, and ignore auto-repeat as a new press;
- **capture mode:** suspend the daemon callback, collect modifiers plus one terminal key, finish after the chord is fully released, return the normalized chord, and restore daemon mode.

Opening Settings from the daemon must reuse the process-wide service. It must not create a second event tap. Running `speedytype settings` as a separate process creates a transient service for capture and stops it immediately afterward.

`speedytype/platform/_macos_hotkey.py` retains the public cross-platform-facing functions `register_hold_hotkey()`, `wait_until_hotkey_released()`, `capture_hotkey()`, and `remove_hotkey()`, but delegates them to the native service. Callers outside the platform layer do not acquire Quartz types.

### Selective suppression

The event tap is active rather than listen-only so it can suppress only the configured terminal key. For a plain F9 chord, its down, repeat, and up events are withheld from macOS, eliminating the warning sound. For a modified chord such as `ctrl+shift+r`, the modifier events remain visible to the system; only `r` down, repeat, and up are suppressed while the required modifier state matches. Every unrelated event is returned unchanged.

Callback failures are fail-open: the original event is returned so SpeedyType cannot block general keyboard input.

### Native paste

`speedytype/platform/_macos_clipboard.py` retains the existing clipboard snapshot, write, delayed restore, and verification contracts. Its shortcut sender uses Quartz `CGEventPost` to post:

```text
Command down -> V down -> V up -> Command up
```

Each synthesized event carries a SpeedyType-specific source-data marker. `MacEventTapService` returns marked events without interpreting or suppressing them. This prevents synthetic paste from starting a recording even if the configured chord overlaps `cmd+v`.

### Application activation

Add a platform application adapter with shared functions for configuring the daemon application and activating a window. The Windows implementation preserves current behavior. The macOS implementation is isolated in `speedytype/platform/_macos_app.py` and uses AppKit.

After `QApplication` is created, the macOS daemon selects accessory activation policy before showing its existing `QSystemTrayIcon`. This removes the Python Dock icon while retaining the SpeedyType menu-bar icon. Opening Settings or About calls Qt `show()`, `raise_()`, and `activateWindow()`, followed by AppKit activation so the selected window comes to the foreground. The standalone `speedytype settings` command remains a regular foreground application and does not select accessory policy.

### Dependencies

Remove the Darwin-only `pynput` requirement and add these Darwin-only direct requirements:

```text
pyobjc-framework-Cocoa==12.2.1; sys_platform == "darwin"
pyobjc-framework-Quartz==12.2.1; sys_platform == "darwin"
```

Both packages publish Python 3.13 universal2 wheels. They must not be installed or imported on Windows.

## Event Lifecycle

Daemon startup follows this order:

1. reject a duplicate daemon;
2. create `QApplication`;
3. apply the platform daemon-application policy;
4. check macOS event-access permissions;
5. create the event tap and start its `CFRunLoop` thread;
6. wait for an explicit ready result with a bounded timeout;
7. create and show the menu-bar item;
8. write the PID file and report that the daemon is running.

Permission denial, event-tap creation failure, or startup timeout returns a nonzero status, gives actionable guidance, stops any partial service, and leaves no PID file.

At runtime, tap-disabled timeout or user-input notifications trigger re-enablement. An unexpected callback error is recorded and returned fail-open. If the tap cannot recover, a Qt signal tells the main thread to show a tray notification that hotkey monitoring stopped and the daemon must be restarted. Settings, About, Restart, and Quit remain available. Restart and Quit stop the tap, wake the run loop, join its thread with a bound, and then exit.

## Short Recordings and Recoverable Failures

Before Whisper, Gemini, clipboard, or paste work, the shared pipeline measures the WAV. A duration below 0.1 seconds produces a local skipped result:

- no Whisper or LLM request;
- no clipboard mutation or paste;
- a concise `Recording too short; skipped.` message;
- processing UI is hidden;
- the daemon is immediately ready for another recording.

Skipped recordings do not append an API latency/usage CSV row, because no billable request occurred. Existing temporary-WAV retention behavior is unchanged. This guard applies on every platform, but changes no valid Windows recording path.

The daemon processing worker catches recoverable Python exceptions from transcription, polishing, clipboard, and paste. It records a sanitized summary, signals the Qt main thread to show a tray notification, always hides the overlay, and leaves the daemon running. Messages must not include API keys, Keyring values, or complete provider responses. Native signals such as `SIGTRAP` are not considered catchable error handling; removing the unsafe native path is the required remedy.

## Permissions and User Experience

Input Monitoring or Accessibility prompts may still appear the first time the terminal-launched Python process installs an active event tap. Microphone permission may still appear on the first recording. These are expected macOS controls, not application crashes.

The documentation must identify the executable identity the user is authorizing (normally Terminal/Python for the source release), give the exact System Settings locations, instruct the user to restart the daemon after granting access, and explain how to find recent Python `.ips` reports if a native crash recurs.

## Verification

### Automated and Windows regression

Tests use injected fake Quartz and AppKit adapters to verify logic without claiming native-macOS execution. Coverage includes:

- virtual-keycode and modifier normalization;
- plain and modified chord recognition;
- selective down/repeat/up suppression;
- unrelated-event pass-through and callback fail-open behavior;
- daemon/capture mode transitions and restoration;
- synthesized-event marker pass-through;
- event-tap ready, shutdown, re-enable, and unrecoverable-error paths;
- accessory-policy and foreground-window adapter calls;
- sub-0.1-second recording skip with zero API and paste calls;
- processing-error notification, overlay cleanup, and subsequent reuse;
- requirements platform markers and `setup_mac.sh` syntax/logic.

Run the complete pytest suite plus Windows daemon/tray, Settings, clipboard, and paste smoke tests. Verify that Windows neither imports nor installs PyObjC and that its tray UI and hotkey behavior are unchanged.

### Required real-Mac acceptance

The 0.5.4 release candidate must pass all of the following on the user's Mac:

1. update an existing 0.5.3 source installation and reinstall requirements;
2. start `speedytype daemon` in a new zsh terminal;
3. observe the SpeedyType menu-bar icon and no Python Dock icon;
4. open Settings and About from the menu bar and see each window brought forward;
5. hold and release F9 without a macOS warning sound;
6. complete a normal recording, paste, and clipboard restoration;
7. press and release F9 too quickly, observe a safe skip, and then complete a normal recording;
8. capture F9 and a modified chord in Settings without recording or crashing;
9. save, restart, and record with the new chord;
10. complete at least ten consecutive recording/paste cycles;
11. use tray Restart and Quit without leaving a Python process;
12. run standalone `speedytype settings` and capture a chord;
13. confirm that the test period produced no new Python `.ips` crash report.

Any failure preserves the daemon log and matching `.ips`, blocks the final release tag, and returns to diagnosis.

## Documentation and Release

Update `MAC_SETUP.md` with menu-bar behavior, permissions, updating from 0.5.3, validation commands, and troubleshooting. Update `release/README.md` with normal daemon/menu usage and first-run authorization. Update `KNOWN_LIMITATIONS.md` and `POC_REPORT.md` with the evidence from `mac_log_001` and `mac_log_002`, the confirmed versus inferred root causes, and final Windows/Mac verification evidence.

The release sequence is:

1. implement with automated tests;
2. pass the complete Windows regression suite;
3. build a 0.5.4 release candidate without tagging it as final;
4. pass the required real-Mac acceptance suite;
5. fix and repeat if any acceptance item fails;
6. rerun complete Windows regression;
7. build the final source archive and checksum;
8. update release evidence;
9. commit and create annotated tag `v0.5.4`;
10. push `master` and the tag only after explicit user approval.

## Acceptance Criteria

- macOS Settings hotkey capture no longer uses `pynput` or crashes with the `TSMGetInputSourceProperty` dispatch assertion.
- macOS daemon hotkey and paste paths no longer use `pynput`.
- only the configured hotkey is suppressed; normal keyboard input remains unaffected.
- F9 hold-to-record produces no system warning sound.
- synthesized paste cannot recursively trigger recording.
- daemon mode shows a menu-bar icon without a Python Dock icon.
- Settings and About reliably come to the foreground from the menu bar.
- recordings shorter than 0.1 seconds make no API call and do not stop the daemon.
- recoverable processing failures leave the daemon usable and do not expose secrets.
- Windows behavior and dependencies remain unchanged.
- all automated, Windows regression, and real-Mac acceptance gates pass before `v0.5.4` is finalized.
