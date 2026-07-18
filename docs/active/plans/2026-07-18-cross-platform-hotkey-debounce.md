# Cross-Platform Hotkey Debounce Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fixed cross-platform 80 ms qualification stage that rejects unintended Hold/Toggle start and Toggle-stop presses without losing the beginning of valid recordings.

**Architecture:** `RecordingControl` owns tokenized pending-start/pending-stop transitions. `DaemonController` starts provisional capture immediately, runs bounded confirmation/release workers, and only exposes UI or processing after confirmation. Platform adapters expose current hotkey state; recovery and diagnostic helpers narrowly delete rejected provisional artifacts and append privacy-safe records.

**Tech Stack:** Python 3.13, PyQt6 signals, `threading`, existing Windows `keyboard` backend, existing macOS Quartz event-tap service, pytest.

## Global Constraints

- The qualification threshold is fixed at exactly 80 ms and is not configurable.
- Apply the rule to Hold start, Toggle start, and Toggle stop; do not debounce confirmed Hold release.
- Start WAV capture and its recovery sidecar immediately, but do not show recording UI before confirmation.
- A rejected start may delete only the explicitly owned `capturing` or `captured` WAV/sidecar pair.
- Capture, cleanup, shutdown, or crash failures retain recovery evidence and never enter downstream processing.
- Every rejected candidate appends exactly one privacy-safe `HOTKEY_DEBOUNCE` JSON line to the persistent daemon log.
- Do not change platform hooks, settings schema/UI, capture format, FLAC/STT/LLM/paste/usage behavior, or release gates.
- Production defaults use real monotonic time and sleeping; unit tests invoke transition handlers deterministically without real 80 ms sleeps.

---

### Task 1: Establish the Active Documentation Lifecycle

**Files:**
- Create: `docs/active/README.md`
- Move: `docs/archive/specs/2026-07-18-cross-platform-hotkey-debounce-design.md` → `docs/active/specs/2026-07-18-cross-platform-hotkey-debounce-design.md`
- Modify: `docs/README.md`
- Modify: `docs/archive/README.md`
- Modify: `tests/test_documentation_structure.py`

**Interfaces:**
- Consumes: existing `docs/current/` and `docs/archive/` authority boundaries.
- Produces: enforceable `active/specs → active/plans → current + archive` lifecycle.

- [ ] **Step 1: Add failing structure tests**

Add `docs/active/README.md` to `CANONICAL`; assert the hub links it, active Markdown exists only under `specs/` and `plans/`, and the approved debounce spec is active rather than archived.

- [ ] **Step 2: Run the documentation test and verify RED**

Run: `python -m pytest tests/test_documentation_structure.py -q`

Expected: failure because `docs/active/README.md` and the active spec path do not exist.

- [ ] **Step 3: Implement the lifecycle documentation**

Document these exact transitions:

```text
draft/approved design -> docs/active/specs/
approved implementation plan -> docs/active/plans/
verified implementation -> update docs/current/
completed/stopped work -> move spec, plan, and dated evidence to docs/archive/
```

Move the debounce design to `docs/active/specs/`, link Active Work from the hub, and remove its link from the archive index.

- [ ] **Step 4: Run documentation tests and commit**

Run: `python -m pytest tests/test_documentation_structure.py -q`

Expected: all documentation structure tests pass.

Commit: `docs: define active documentation lifecycle`

---

### Task 2: Implement the Tokenized Recording-Control State Machine

**Files:**
- Modify: `speedytype/recording_control.py`
- Modify: `tests/test_recording_control.py`

**Interfaces:**
- Produces: `begin_activation() -> tuple[RecordingAction, int | None]`, `confirm_activation(token: int) -> RecordingAction`, and `hotkey_released(token: int) -> RecordingAction`.
- Produces actions: `BEGIN_START`, `CONFIRM_START`, `CANCEL_START`, `BEGIN_STOP`, `CANCEL_STOP`, `STOP`, `NONE`.
- Produces phases: existing phases plus `PENDING_START` and `PENDING_STOP`.

- [ ] **Step 1: Replace immediate-action tests with pending-state tests**

Cover Hold short rejection, Hold confirmation/release, Toggle short start, Toggle rearm, Toggle short stop, Toggle confirmed stop, duplicate activation, timeout invalidation, stale token rejection, and release/timeout races.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -m pytest tests/test_recording_control.py -q`

Expected: failures for missing actions, phases, and tokenized methods.

- [ ] **Step 3: Implement minimal locked transitions**

Store monotonic integer `_next_token`, `_candidate_token`, and `_active_token`. Only the matching current token may confirm/cancel/release; every terminal failure/timeout invalidates both token slots.

- [ ] **Step 4: Run focused tests and commit**

Run: `python -m pytest tests/test_recording_control.py -q`

Expected: all pass.

Commit: `feat: add tokenized hotkey qualification state`

---

### Task 3: Expose Current Hotkey State on Both Platforms

**Files:**
- Modify: `speedytype/platform/hotkey.py`
- Modify: `speedytype/platform/_windows_hotkey.py`
- Modify: `speedytype/platform/_macos_hotkey.py`
- Modify: `speedytype/hotkey.py`
- Modify: `tests/test_platform_hotkey.py`
- Modify: `tests/test_macos_event_tap.py`

**Interfaces:**
- Produces: `is_hotkey_active(hotkey: str) -> bool` from both platform adapters and public dispatchers.
- Windows delegates to `keyboard.is_pressed(_windows_combo(hotkey))`.
- macOS ignores the text argument and returns `bool(get_event_tap_service().state.active)`.

- [ ] **Step 1: Add adapter contract tests**

Verify Windows normalization is used before `keyboard.is_pressed`, macOS reads explicit event-tap state, and the dispatcher exports the symbol.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_platform_hotkey.py tests/test_macos_event_tap.py -q`

Expected: import/attribute failures for `is_hotkey_active`.

- [ ] **Step 3: Add the minimal adapter methods and exports**

Do not change registration, release waiting, event flags, or Quartz callbacks.

- [ ] **Step 4: Run focused tests and commit**

Run: `python -m pytest tests/test_platform_hotkey.py tests/test_macos_event_tap.py tests/test_hotkey.py -q`

Expected: all pass.

Commit: `feat: expose cross-platform hotkey active state`

---

### Task 4: Add Narrow Provisional Cleanup and Persistent Rejection Logging

**Files:**
- Create: `speedytype/hotkey_debounce.py`
- Modify: `speedytype/recording_recovery.py`
- Modify: `tests/test_recording_recovery.py`
- Create: `tests/test_hotkey_debounce.py`

**Interfaces:**
- Produces: `remove_unconfirmed_recording(wav_path: Path) -> bool`; it removes only an owned sidecar in `capturing`/`captured` plus its WAV, otherwise raises `ValueError` and removes nothing.
- Produces: `append_rejection_record(log_path: Path, *, platform: str, mode: str, hotkey: str, intent: str, held_ms: float, cleanup: str) -> None`.
- Log payload contains exactly `timestamp_utc`, `platform`, `mode`, `hotkey`, `intent`, `held_ms`, `threshold_ms`, `decision`, `cleanup` after prefix `HOTKEY_DEBOUNCE `.

- [ ] **Step 1: Add cleanup and logging tests**

Test owned `capturing`/`captured` removal, protected states, foreign/missing sidecars, valid exact-field JSON, no sensitive values/full path, best-effort I/O failure, and serialized concurrent lines.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_recording_recovery.py tests/test_hotkey_debounce.py -q`

Expected: import failures for the new helpers.

- [ ] **Step 3: Implement cleanup and logger**

Use one module-level lock for append serialization, `ensure_ascii=False`, one compact JSON object per line, and catch `OSError` inside the logger. Validate both files before unlinking; if the WAV unlink succeeds but sidecar unlink fails, propagate so daemon records `retained-after-failure` and leaves remaining evidence.

- [ ] **Step 4: Run focused tests and commit**

Run: `python -m pytest tests/test_recording_recovery.py tests/test_hotkey_debounce.py -q`

Expected: all pass.

Commit: `feat: safely discard rejected hotkey captures`

---

### Task 5: Integrate Qualification Workers with the Daemon

**Files:**
- Modify: `speedytype/daemon.py`
- Modify: `tests/test_daemon_recovery.py`
- Modify: `tests/test_pipeline_usage.py`

**Interfaces:**
- `DaemonController.__init__` accepts internal-test injections `activation_threshold_seconds: float = 0.08`, `monotonic: Callable[[], float] = time.perf_counter`, and `sleep: Callable[[float], None] = time.sleep`.
- `_RecordingSession` owns the confirmed/cancel flags and the current `_ActivationCandidate(token, intent, started_at)`.
- `_confirm_candidate(session, candidate)` and `_finish_after_release(session, candidate)` both submit the same token; stale actions are no-ops.

- [ ] **Step 1: Add deterministic daemon tests**

Cover immediate provisional capture with no UI, confirmed UI/countdown once, rejected start stop/join/cleanup/log/no pipeline, rejected Toggle stop continuation/log, confirmed Toggle stop once, capture failure retention, cleanup failure retention, timeout priority, shutdown token invalidation, and stale workers.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest tests/test_daemon_recovery.py tests/test_pipeline_usage.py -q`

Expected: failures because daemon still performs immediate UI/action and lacks candidate handlers.

- [ ] **Step 3: Implement provisional start and candidate workers**

On `BEGIN_START`, allocate the normal WAV/sidecar and start capture before workers, but defer `safe_print("Recording...")`, pill, ticker, and normal recording feedback until `CONFIRM_START`. On `BEGIN_STOP`, keep the same session/capture/UI and create only a new stop candidate.

- [ ] **Step 4: Implement race-safe confirm/release handling**

The confirmation worker sleeps only until its monotonic deadline, checks `is_hotkey_active`, then confirms or cancels. The release worker uses the existing platform waiter. A release measured at or beyond 80 ms first confirms the matching candidate before applying the release so scheduler delay cannot reject a valid press. Controller/session lock order remains session then recording-control.

- [ ] **Step 5: Implement cancel cleanup and logging**

For `CANCEL_START`, mark cancellation, stop once, join outside the lock, verify identity/token, call `remove_unconfirmed_recording`, clear the session, and append one start rejection. Never emit processing/error UI for successful rejection. For `CANCEL_STOP`, leave session/UI/capture intact and append one stop rejection with `not-applicable` cleanup.

- [ ] **Step 6: Run daemon/regression tests and commit**

Run: `python -m pytest tests/test_daemon_recovery.py tests/test_pipeline_usage.py tests/test_recording_control.py tests/test_hotkey_debounce.py -q`

Expected: all pass.

Commit: `feat: debounce recording hotkey activations`

---

### Task 6: Update Current Truth, Verify, and Archive Completed Work

**Files:**
- Modify: `docs/current/user/README.md`
- Modify: `docs/current/user/MAC_SETUP.md`
- Modify: `docs/current/engineering/ARCHITECTURE.md`
- Modify: `docs/current/engineering/DECISIONS.md`
- Move on completion: active debounce spec/plan → corresponding `docs/archive/specs/` and `docs/archive/plans/`
- Modify: `docs/archive/README.md`

**Interfaces:**
- Produces current documentation for the implemented 80 ms behavior and macOS acceptance checks.
- Produces archived design/plan evidence after verification, leaving no completed artifact under `docs/active/`.

- [ ] **Step 1: Update current documentation**

Document provisional capture, delayed pill, Hold/Toggle semantics, privacy-safe rejection log, safe cleanup boundary, and macOS short-press acceptance checks. Add an accepted decision linked to the design evidence.

- [ ] **Step 2: Run focused and complete verification**

Run:

```powershell
python -m pytest tests/test_recording_control.py tests/test_platform_hotkey.py tests/test_macos_event_tap.py tests/test_recording_recovery.py tests/test_hotkey_debounce.py tests/test_daemon_recovery.py tests/test_pipeline_usage.py tests/test_documentation_structure.py -q
python -m pytest -q
python -m compileall -q speedytype scripts
git diff --check
```

Expected: focused suite passes; full suite passes except the already documented Windows Qt clipboard test may require an isolated rerun, which must pass; compileall and diff check exit 0.

- [ ] **Step 3: Archive only after implementation is verified**

Move the design and this plan from `docs/active/` to `docs/archive/`, update the archive index, and re-run `tests/test_documentation_structure.py`.

- [ ] **Step 4: Commit final documentation and archive bookkeeping**

Commit: `docs: document cross-platform hotkey debounce`

- [ ] **Step 5: Review branch state**

Run: `git status --short --branch` and `git log --oneline --decorate -8`.

Expected: clean feature branch containing focused documentation, state-machine, platform, cleanup/logging, daemon, and final documentation commits.
