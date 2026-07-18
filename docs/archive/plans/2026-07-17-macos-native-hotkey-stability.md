# macOS Native Hotkey and Daemon Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove macOS `pynput` keyboard paths, eliminate the Python Dock icon, and keep the daemon alive after short recordings or recoverable processing failures.

**Architecture:** A process-wide Quartz event-tap service owns daemon/capture key state and selective suppression. Thin platform adapters preserve existing public APIs; daemon and pipeline changes remain platform-neutral and Windows behavior stays unchanged.

**Tech Stack:** Python 3.13, PyQt6, PyObjC Cocoa/Quartz on Darwin, pytest with injected fake adapters.

## Global Constraints

- Do not import or install PyObjC on Windows.
- Do not modify Windows hotkey or clipboard backends.
- No signed app, Swift helper, CLI/settings-format change, or hybrid-transcription redesign.
- Real-Mac acceptance remains mandatory before tag `v0.5.4`.

---

### Task 1: Quartz event-tap state and service

**Files:**
- Create: `speedytype/platform/_macos_event_tap.py`
- Replace: `speedytype/platform/_macos_hotkey.py`
- Test: `tests/test_macos_event_tap.py`
- Modify: `tests/test_platform_hotkey.py`

**Interfaces:**
- Produces `MacEventTapService`, `EventDecision`, `register_hold_hotkey()`, `wait_until_hotkey_released()`, `capture_hotkey()`, and `remove_hotkey()`.
- Consumes only normalized string chords outside the platform module; Quartz is injected for tests.

- [ ] Write failing tests for fixed keycode mapping, modifier normalization, plain/modified chord down-repeat-up handling, selective terminal-key suppression, unrelated and marked-event pass-through, callback fail-open, capture/daemon restoration, ready timeout, re-enable, and shutdown.
- [ ] Run `python -m pytest tests/test_macos_event_tap.py tests/test_platform_hotkey.py -q` and confirm missing-service failures.
- [ ] Implement a state engine plus one process-wide service with an injected Quartz adapter and bounded ready/shutdown behavior; `_macos_hotkey.py` delegates without importing `pynput`.
- [ ] Re-run the focused tests and require all green.
- [ ] Commit `feat: replace macOS hotkeys with Quartz event tap`.

### Task 2: Marked Quartz paste events

**Files:**
- Modify: `speedytype/platform/_macos_clipboard.py`
- Modify: `speedytype/platform/_macos_event_tap.py`
- Test: `tests/test_platform_clipboard.py`
- Test: `tests/test_macos_event_tap.py`

**Interfaces:**
- Produces `send_paste_shortcut(quartz=None)` posting Command-down, V-down, V-up, Command-up with a shared source marker.
- Event tap consumes the marker and passes synthesized events through unchanged.

- [ ] Add failing tests asserting event order, flags, source marker, and marker pass-through.
- [ ] Run the two focused test modules and confirm RED.
- [ ] Implement the four marked Quartz events and remove all macOS `pynput.Controller` use.
- [ ] Re-run focused tests and require green.
- [ ] Commit `fix: use marked Quartz events for macOS paste`.

### Task 3: Accessory app and foreground windows

**Files:**
- Create: `speedytype/platform/app.py`
- Create: `speedytype/platform/_macos_app.py`
- Create: `speedytype/platform/_windows_app.py`
- Modify: `speedytype/daemon.py`
- Test: `tests/test_platform_app.py`
- Modify: `tests/test_daemon_pid.py`

**Interfaces:**
- Produces `configure_daemon_application()` and `activate_window(window)`.
- Daemon calls configuration after QApplication construction and activation after Settings/About `show()`.

- [ ] Write failing dispatch and fake-AppKit tests for accessory policy and foreground activation; add daemon call-order assertions.
- [ ] Run focused tests and confirm RED.
- [ ] Implement lazy platform dispatch, no-op Windows behavior, AppKit accessory policy/activation, and daemon integration for Settings/About.
- [ ] Re-run focused tests and require green.
- [ ] Commit `fix: keep macOS daemon out of the Dock`.

### Task 4: Short recordings and recoverable daemon failures

**Files:**
- Modify: `speedytype/pipeline.py`
- Modify: `speedytype/daemon.py`
- Test: `tests/test_pipeline_usage.py`
- Create: `tests/test_daemon_recovery.py`

**Interfaces:**
- `process_wav()` returns a local skipped `PipelineResult` for duration below 0.1 seconds without API, CSV, clipboard, or paste calls.
- `DaemonController` emits a sanitized notification and always hides the overlay after recoverable capture/processing errors.

- [ ] Add failing tests for a sub-0.1-second file, zero external calls and no latency row; add tests for sanitized worker errors, overlay cleanup, notification, and subsequent reuse.
- [ ] Run focused tests and confirm RED.
- [ ] Implement the early duration guard and daemon error boundary using Qt signals; never include provider bodies or secrets in notification text.
- [ ] Re-run focused tests and require green.
- [ ] Commit `fix: keep daemon alive after short or failed recordings`.

### Task 5: Dependencies, documentation, and release-candidate evidence

**Files:**
- Modify: `requirements.txt`
- Modify: `MAC_SETUP.md`
- Modify: `release/README.md`
- Modify: `KNOWN_LIMITATIONS.md`
- Modify: `POC_REPORT.md`
- Modify: `tests/test_setup_scripts.py`
- Modify: `tests/test_release_docs.py`

**Interfaces:**
- Darwin installs Cocoa/Quartz `12.2.1`; Windows installs neither PyObjC nor pynput.
- Documentation produces the exact 13-item real-Mac acceptance handoff and explicitly blocks final `v0.5.4`.

- [ ] Add failing requirement-marker and documentation-contract tests covering permissions, menu-bar/no-Dock behavior, update instructions, `.ips` collection, and real-Mac gate.
- [ ] Run focused documentation/setup tests and confirm RED.
- [ ] Replace Darwin `pynput` with Cocoa/Quartz markers and update user/release documentation without claiming real-Mac success.
- [ ] Run focused tests, `python -m pytest -q`, `python -m compileall -q speedytype tests`, and `git diff --check`.
- [ ] Commit `docs: prepare macOS stability release candidate`.

## Self-review

- Spec coverage: native hotkey/capture, suppression, marked paste, accessory activation, short-recording skip, worker containment, dependencies, documentation, and real-Mac gate are each mapped above.
- Deferred by design: actual macOS permissions/runtime acceptance and final `v0.5.4` tag require the user's Mac.
- No placeholder or production-path hybrid work is included.
