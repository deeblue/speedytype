# Toggle Recording and Persistent Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe Hold/Toggle recording choice, one idempotent 25-minute automatic stop, and a persistent elapsed/countdown/auto-stop pill for daily daemon recording.

**Architecture:** Persist one canonical recording mode and keep platform hotkey backends unchanged. A small thread-safe state machine decides start, rearm, stop, timeout, failure, and completion; `DaemonController` performs side effects only after accepted decisions. `RecordingPill` owns its two-second warning-to-processing/hide visual coordination so transcription starts immediately without stale UI.

**Tech Stack:** Python 3.13, PyQt6, existing Windows `keyboard` backend, existing macOS Quartz event-tap backend, pytest.

## Global Constraints

- `recording_mode` is exactly `hold` or `toggle`; `hold` remains the default.
- Toggle rearms only after the configured hotkey becomes inactive through the existing any-member-release waiter.
- Both modes use the same monotonic deadline and validated `max_record_seconds <= 1500.0`.
- Stop/drain/process is accepted at most once even when hotkey, timeout, failure, and shutdown race.
- Normal overlay shows elapsed `MM:SS`; the final 60 seconds show remaining time.
- Automatic stop renders `已達錄音上限，自動停止` at the pill location for at least two seconds while processing starts immediately.
- Guided recording remains Hold-only; do not change platform hotkey backends or the complete-file FLAC pipeline.
- Real Windows/macOS long-recording checks remain release gates and must not be reported as automated proof.

---

### Task 1: Persist and expose the recording mode

**Files:**
- Modify: `speedytype/settings.py`
- Modify: `speedytype/config.py`
- Modify: `speedytype/settings_dialog.py`
- Modify: `tests/test_settings.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_settings_dialog.py`

**Interfaces:**
- Produces: `DEFAULT_RECORDING_MODE = "hold"`, `RECORDING_MODES`, `AppSettings.recording_mode`, and `AppConfig.recording_mode`.
- Consumed by: Task 2 state machine and Task 4 daemon controller.

- [x] **Step 1: Write failing settings/config tests**

Add tests asserting default `hold`, `toggle` round-trip, direct save rejection for unsupported values, invalid persisted fallback to `hold` with a Chinese load warning, and propagation through `load_config()`:

```python
def test_invalid_recording_mode_falls_back_to_hold_with_warning(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"recording_mode":"bad"}', encoding="utf-8")
    loaded = load_settings(path)
    assert loaded.recording_mode == "hold"
    assert any("錄音模式" in item for item in loaded.load_warnings)
```

- [x] **Step 2: Confirm the model tests fail**

Run: `python -m pytest tests/test_settings.py tests/test_config.py -q`

Expected: missing `recording_mode` attributes and absent validation warning.

- [x] **Step 3: Implement canonical validation and config propagation**

Add one validator and use it in both `to_dict()` and `from_dict()`:

```python
DEFAULT_RECORDING_MODE = "hold"
RECORDING_MODES = frozenset({"hold", "toggle"})

def _validated_recording_mode(raw: object) -> tuple[str, tuple[str, ...]]:
    value = str(raw or DEFAULT_RECORDING_MODE).strip().lower()
    if value not in RECORDING_MODES:
        return DEFAULT_RECORDING_MODE, ("錄音模式設定無效，已改用按住錄音。",)
    return value, ()
```

Direct serialization raises if the validator produced a warning. Loading appends its warning to existing duration/budget warnings. `load_config()` passes `settings.recording_mode` into `AppConfig`.

- [x] **Step 4: Write failing Settings UI tests**

Assert the mode control has the two labels `按住錄音，放開停止` and `按一下開始，再按一下停止`, loads `toggle`, saves the canonical value, and displays the daemon-restart note.

- [x] **Step 5: Implement the Settings control**

Add `_build_recording_mode_group()` immediately after maximum recording time. Use a `QComboBox` whose item data is `hold`/`toggle`, initialize it from `_settings.recording_mode`, and pass `currentData()` to `AppSettings` in `_save()`.

- [x] **Step 6: Run Task 1 tests and commit**

Run: `python -m pytest tests/test_settings.py tests/test_config.py tests/test_settings_dialog.py -q`

Expected: all pass.

```powershell
git add speedytype/settings.py speedytype/config.py speedytype/settings_dialog.py tests/test_settings.py tests/test_config.py tests/test_settings_dialog.py
git commit -m "feat: configure hold or toggle recording"
```

---

### Task 2: Add a thread-safe recording decision state machine

**Files:**
- Create: `speedytype/recording_control.py`
- Create: `tests/test_recording_control.py`

**Interfaces:**
- Produces: `RecordingAction` enum (`START`, `STOP`, `NONE`), `RecordingPhase` enum, and `RecordingControl(mode: str)` with `activate()`, `hotkey_released()`, `timeout()`, `mark_processing()`, `recording_failed()`, `processing_finished()`, and `.phase`.
- Consumed by: Task 4 `DaemonController`.

- [ ] **Step 1: Write failing state-transition tests**

Cover these exact sequences:

```python
assert RecordingControl("hold").activate() is RecordingAction.START

toggle = RecordingControl("toggle")
assert toggle.activate() is RecordingAction.START
assert toggle.activate() is RecordingAction.NONE       # repeat while held
assert toggle.hotkey_released() is RecordingAction.NONE # rearm only
assert toggle.activate() is RecordingAction.STOP
assert toggle.timeout() is RecordingAction.NONE         # stop already won
```

Also test Hold release returns `STOP`, timeout returns `STOP` exactly once in both modes, failure makes later events no-ops, activations during processing are ignored, and `processing_finished()` returns to idle for the next recording.

- [ ] **Step 2: Confirm the new module tests fail**

Run: `python -m pytest tests/test_recording_control.py -q`

Expected: import failure because `recording_control.py` does not exist.

- [ ] **Step 3: Implement the locked state machine**

Use one `threading.Lock`; every public transition acquires it. Exact phases are `IDLE`, `RECORDING_UNARMED`, `RECORDING_ARMED`, `STOPPING`, and `PROCESSING`. Hold starts directly in `RECORDING_ARMED`; Toggle starts in `RECORDING_UNARMED`. A successful stop transition moves to `STOPPING`; `mark_processing()` (also required) moves only `STOPPING -> PROCESSING`.

- [ ] **Step 4: Run Task 2 tests and commit**

Run: `python -m pytest tests/test_recording_control.py -q`

Expected: all pass.

```powershell
git add speedytype/recording_control.py tests/test_recording_control.py
git commit -m "feat: coordinate recording mode transitions"
```

---

### Task 3: Extend the pill with elapsed time and local timeout warning

**Files:**
- Modify: `speedytype/overlay.py`
- Create: `tests/test_overlay.py`

**Interfaces:**
- Produces: `format_recording_elapsed(seconds: int) -> str`, `RecordingPill.show_elapsed(int)`, `show_auto_stopped()`, warning-aware `show_processing()`, and warning-aware `hide_pill()`.
- Consumed by: Task 4 daemon signals.

- [ ] **Step 1: Write failing formatting and visual-state tests**

Assert `0 -> "00:00"`, `65 -> "01:05"`, `1500 -> "25:00"`; `show_elapsed(65)` stores recording mode/text; countdown supersedes elapsed; `show_auto_stopped()` stores the exact approved text; immediate `show_processing()` remains warning-pending; immediate `hide_pill()` remains visible until the warning timer expires.

Use an injectable `warning_duration_ms=2000` constructor argument and call a focused `_finish_warning()` slot in tests rather than sleeping.

- [ ] **Step 2: Confirm overlay tests fail**

Run: `python -m pytest tests/test_overlay.py -q`

Expected: missing formatter and slots.

- [ ] **Step 3: Implement the pill states**

Keep the current bottom-center geometry. In recording mode, reserve the left portion for bars and draw elapsed text on the right. Add `auto_stopped` warning styling with `COUNTDOWN_COLOR`. `show_auto_stopped()` starts a single-shot `QTimer`; `show_processing()` during the warning sets `_processing_pending`; `hide_pill()` sets `_hide_pending`; `_finish_warning()` hides when completion is pending, otherwise enters processing.

- [ ] **Step 4: Run overlay regressions and commit**

Run: `python -m pytest tests/test_overlay.py tests/test_settings_dialog.py -q`

Expected: all pass.

```powershell
git add speedytype/overlay.py tests/test_overlay.py
git commit -m "feat: show persistent recording time and timeout"
```

---

### Task 4: Integrate Hold/Toggle orchestration, documentation, and release verification

**Files:**
- Modify: `speedytype/daemon.py`
- Modify: `tests/test_daemon_recovery.py`
- Modify: `tests/test_pipeline_usage.py`
- Modify: `release/README.md`
- Modify: `MAC_SETUP.md`
- Modify: `KNOWN_LIMITATIONS.md`
- Modify: `POC_REPORT.md`
- Modify: `tests/test_release_docs.py`

**Interfaces:**
- Consumes: Task 1 `AppConfig.recording_mode`, Task 2 `RecordingControl`, and Task 3 pill slots.
- Produces: one daemon start/rearm/stop/deadline path and documented real-device gates.

- [ ] **Step 1: Write failing daemon orchestration tests**

Use fake recorder/thread/clock objects without OS key injection. Assert:

- Hold activation starts once and release drains/processes once.
- Toggle first activation starts, duplicate activation is ignored, release rearms, and second activation drains/processes once.
- Deadline calls the same stop path in both modes and later release/activation cannot duplicate processing.
- Every pre-warning tick emits elapsed seconds; final 60 seconds emit countdown.
- Timeout emits `show_auto_stopped_signal` before `show_processing_signal`, but the processing worker starts immediately.
- Recorder failure moves control to idle/reusable and later deadline cannot process the failed recording.

- [ ] **Step 2: Confirm daemon tests fail**

Run: `python -m pytest tests/test_daemon_recovery.py tests/test_pipeline_usage.py -q`

Expected: Toggle activation and elapsed/auto-stop signal assertions fail.

- [ ] **Step 3: Implement one idempotent stop path**

Add signals `show_elapsed_signal = pyqtSignal(int)` and `show_auto_stopped_signal = pyqtSignal()`. The state-machine event handler calls one side-effect method only after receiving `RecordingAction.STOP`:

```python
def _finish_recording(self, reason: str) -> None:
    self.recorder.stop()
    self._active_thread.join()
    path = self._active_path
    if reason == "timeout":
        self.show_auto_stopped_signal.emit()
    self.show_processing_signal.emit()
    self._recording_control.mark_processing()
    threading.Thread(target=lambda: self._process_recording(path), daemon=True).start()
```

`on_press()` asks the state machine for `START`, `STOP`, or `NONE`; only the
single caller that receives `STOP` invokes `_finish_recording()`. The release
waiter rearms Toggle or stops Hold. The monotonic ticker emits elapsed until the
warning threshold, emits remaining time inside it, and calls `timeout()` at
`remaining <= 0`; again, only a returned `STOP` enters `_finish_recording()`.
`_process_recording()` always calls `processing_finished()` in `finally`.
Recorder failure calls `recording_failed()` before hiding.

- [ ] **Step 4: Run orchestration and existing FLAC tests**

Run: `python -m pytest tests/test_recording_control.py tests/test_daemon_recovery.py tests/test_pipeline_usage.py tests/test_flac_upload.py tests/test_audio_recording.py -q`

Expected: all pass and no duplicate processing calls.

- [ ] **Step 5: Write failing release-document tests, then update docs**

Require documentation to state both recording modes, default Hold, Toggle release/repress behavior, persistent `MM:SS`, final 60-second countdown, pill-local automatic-stop warning, 25-minute stop, daemon restart requirement, guided-recording exclusion, and pending Windows/macOS real-device gates. Update the four user/engineering documents without claiming real-hardware completion.

- [ ] **Step 6: Run complete verification**

```powershell
python -m pytest tests/test_settings.py tests/test_config.py tests/test_settings_dialog.py tests/test_recording_control.py tests/test_overlay.py tests/test_daemon_recovery.py tests/test_pipeline_usage.py tests/test_release_docs.py -q
python -m pytest -q -k "not test_paste_text_preserving_clipboard_restores_original_synchronously and not test_paste_text_preserving_clipboard_background_restores_after_delay and not test_empty_masked_key_field_accepts_paste_without_reveal"
python -m pytest tests/test_clipboard.py::test_paste_text_preserving_clipboard_restores_original_synchronously tests/test_clipboard.py::test_paste_text_preserving_clipboard_background_restores_after_delay tests/test_settings_dialog.py::test_empty_masked_key_field_accepts_paste_without_reveal -q
python -m compileall -q speedytype scripts
git diff --check
```

Expected: every command exits 0. Record real Windows/macOS Toggle and ≥24-minute checks as pending release gates.

- [ ] **Step 7: Commit**

```powershell
git add speedytype/daemon.py tests/test_daemon_recovery.py tests/test_pipeline_usage.py release/README.md MAC_SETUP.md KNOWN_LIMITATIONS.md POC_REPORT.md tests/test_release_docs.py docs/superpowers/plans/2026-07-18-toggle-recording-overlay.md
git commit -m "feat: support toggle long recordings"
```
