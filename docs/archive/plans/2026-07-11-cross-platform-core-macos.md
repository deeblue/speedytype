# SpeedyType Cross-Platform Core and macOS Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SpeedyType runnable from source on Windows and macOS through tested platform boundaries while fixing current defects and excluding distribution work.

**Architecture:** Public concern-based modules in `speedytype/platform/` dispatch to private Windows or macOS implementations. Stateful defaults come from `platformdirs`; process operations use `psutil`; canonical hotkey tokens isolate persisted settings from OS-specific key names.

**Tech Stack:** Python 3, pytest, PyQt6, keyboard (Windows), pynput (macOS), pyperclip, pywin32, psutil, platformdirs, plistlib, Edge TTS, Whisper and Gemini APIs.

## Global Constraints

- Preserve the pre-change Windows baseline of 59 passing tests and existing clipboard/hotkey behavior.
- Use test-first red-green-refactor for production behavior changes.
- Explicit paths and `--env` continue to override platform defaults.
- macOS clipboard preservation is text-only.
- Do not implement PyInstaller, Inno Setup, DMG, icons, signing, notarization, or CI.
- Do not claim real macOS behavior verified from Windows.
- Preserve unrelated dirty-worktree changes.

---

### Task 1: Dependency and Path Defaults

**Files:**
- Modify: `requirements.txt`
- Create: `speedytype/paths.py`
- Create: `tests/test_paths.py`
- Modify: `speedytype/config.py`
- Modify: `speedytype/settings.py`
- Modify: `speedytype/daemon.py`
- Modify: `speedytype/cli.py`

**Interfaces:**
- Produces: `app_data_dir() -> Path`, `default_env_path() -> Path`, `default_settings_path() -> Path`, `default_pid_path() -> Path`, `default_daemon_log_path() -> Path`, `default_latency_log_path() -> Path`.

- [ ] Write tests that monkeypatch `platformdirs.user_data_path`, assert every default lives below `SpeedyType`, and assert explicit loader/CLI paths remain unchanged.
- [ ] Run `python -m pytest tests/test_paths.py tests/test_config.py tests/test_settings.py -q`; expect failures because `speedytype.paths` does not exist.
- [ ] Implement side-effect-free path helpers and migrate default arguments/constants without changing explicit overrides.
- [ ] Add `PyQt6`, `numpy`, `psutil`, `platformdirs`, Darwin-only `pynput`, and Windows markers for Windows-only dependencies.
- [ ] Re-run focused tests and then `python -m pytest -q`; expect all tests green.

### Task 2: Process Abstraction

**Files:**
- Create: `speedytype/platform/__init__.py`
- Create: `speedytype/platform/process.py`
- Create: `tests/test_platform_process.py`
- Modify: `speedytype/daemon.py`
- Modify: `tests/test_daemon_pid.py`

**Interfaces:**
- Produces: `is_process_running(pid: int) -> bool`, `terminate_process(pid: int) -> tuple[bool, str]`, and platform-safe detached daemon spawning.

- [ ] Write tests for live/missing/access-denied processes using injected or monkeypatched `psutil.Process` behavior and for daemon PID cleanup messages.
- [ ] Run focused tests; expect import/function failures.
- [ ] Implement `psutil` process checks and graceful termination handling, then replace `tasklist`/`taskkill` use.
- [ ] Move Windows-only detached-process flags behind a guarded helper so daemon imports on Darwin.
- [ ] Run focused and full suites; expect green.

### Task 3: Clipboard Abstraction

**Files:**
- Create: `speedytype/platform/clipboard.py`
- Create: `speedytype/platform/_windows_clipboard.py`
- Create: `speedytype/platform/_macos_clipboard.py`
- Modify: `speedytype/clipboard.py`
- Modify: `tests/test_clipboard.py`
- Create: `tests/test_platform_clipboard.py`

**Interfaces:**
- Produces: `ClipboardSnapshot`, `snapshot_clipboard()`, `restore_clipboard(snapshot)`, and `send_paste_shortcut()`.
- Consumes: `PasteResult` remains in `speedytype.clipboard`.

- [ ] Move the skip guard ahead of Windows-only imports and write dispatch/contract tests with fake backend modules.
- [ ] Add macOS text snapshot/restore tests by monkeypatching `pyperclip`, including empty and failed snapshots.
- [ ] Run focused tests; expect missing abstraction failures.
- [ ] Move Windows snapshot/restore code without semantic edits, implement macOS text-only behavior, and route paste shortcut through the public boundary.
- [ ] Run focused tests, real Windows clipboard tests, and full suite.

### Task 4: Canonical Hotkeys and Platform Backends

**Files:**
- Create: `speedytype/platform/hotkey.py`
- Create: `speedytype/platform/_windows_hotkey.py`
- Create: `speedytype/platform/_macos_hotkey.py`
- Modify: `speedytype/hotkey.py`
- Modify: `speedytype/daemon.py`
- Modify: `speedytype/settings.py`
- Modify: `tests/test_hotkey.py`
- Create: `tests/test_platform_hotkey.py`

**Interfaces:**
- Produces: `normalize_hotkey_tokens()`, `hotkey_to_storage()`, `hotkey_for_display()`, `register_hold_hotkey()`, `remove_hotkey()`, `wait_until_hotkey_released()`, `capture_hotkey()`, and `PlatformPermissionError`.

- [ ] Write normalization tests for legacy `win`, canonical `cmd`, duplicate tokens, function keys, and platform display conversion.
- [ ] Write listener-state tests using fake pynput key events: fire once on full chord, finish on first configured-key release, timeout, and permission failure conversion.
- [ ] Run focused tests; expect missing APIs.
- [ ] Implement canonical parsing and move the Windows keyboard implementation behind the boundary.
- [ ] Implement a lazy-imported pynput listener/controller backend so Windows tests do not require macOS APIs.
- [ ] Migrate daemon registration/release calls and settings persistence; keep legacy values readable.
- [ ] Run focused and full suites.

### Task 5: Autostart Abstraction and Relocatable Windows Script

**Files:**
- Create: `speedytype/platform/autostart.py`
- Create: `speedytype/platform/_windows_autostart.py`
- Create: `speedytype/platform/_macos_autostart.py`
- Modify: `speedytype/autostart.py`
- Create: `tests/test_autostart.py`

**Interfaces:**
- Produces: `install_autostart(env_path)`, `uninstall_autostart()`, `query_autostart()` with existing `(bool, str)` results.

- [ ] Write Windows tests with temporary APPDATA asserting absolute interpreter, package root, env, and log paths and no backend-file parent-count assumption.
- [ ] Write macOS plist tests for absolute arguments, `RunAtLoad`, GUI user domain, bootstrap/bootout invocation, query, and subprocess errors.
- [ ] Run focused tests; expect failures against current path behavior and missing macOS backend.
- [ ] Implement dispatch, relocatable Windows script generation, and plistlib-based LaunchAgent management.
- [ ] Keep `speedytype.autostart` as a compatibility re-export for existing callers.
- [ ] Run focused and full suites.

### Task 6: Settings Autostart UI, Capture, Reserved Keys, and Permission Guidance

**Files:**
- Modify: `speedytype/settings_dialog.py`
- Modify: `tests/test_settings_dialog.py`

**Interfaces:**
- Consumes: public hotkey and autostart APIs from Tasks 4-5.

- [ ] Write Qt tests asserting initial checkbox state, install/uninstall only on changed state, visible backend failures, platform-specific warnings, and captured canonical tokens.
- [ ] Write a test that a `PlatformPermissionError` produces macOS System Settings Accessibility/Input Monitoring guidance.
- [ ] Run focused tests; expect missing UI/control failures.
- [ ] Add the checkbox, platform-specific reserved shortcut sets, public capture API usage, and permission dialog/status handling.
- [ ] Run focused and full suites.

### Task 7: Prompt Investigation

**Files:**
- Modify: `scripts/test_prompt_variants.py`
- Modify: `scripts/test_prompt_variants_repeated.py`
- Update: `KNOWN_LIMITATIONS.md`
- Create or update: prompt result JSONL under `benchmark_results/`

**Interfaces:**
- Produces: machine-readable valid/error classification and comparable current/candidate sample summaries.

- [ ] Add parser/unit tests for excluding `[ERROR ...]` and `[FAILED ...]` results from semantic success counts.
- [ ] Run parser tests red, implement result classification/output persistence, then run green.
- [ ] Execute repeated API tests until each prompt has at least 5-6 valid samples or quota blocks progress.
- [ ] Record exact valid counts, preservation rates, regression observations, and decision; do not treat API failures as content failures.

### Task 8: Long-Audio Corpus and Benchmark

**Files:**
- Create: `test_audio_long/manifest.json`
- Add: three normalized WAV fixtures under `test_audio_long/`
- Create: `scripts/generate_long_test_audio.py`
- Create: `scripts/run_long_recording_benchmark.py`
- Create: `tests/test_long_benchmark.py`
- Create: raw result JSONL/summary under `benchmark_results/`

**Interfaces:**
- Consumes: `run_baseline_transcription()` and `simulate_quasi_streaming_transcription()`.
- Produces: metadata-driven cases and batch/quasi records with duration, STT/LLM/tail timing, request amplification, chunks, output, and quality checks.

- [ ] Copy the two approved Temp recordings, verify their hashes/durations, and add provenance to the manifest.
- [ ] Write manifest/result/summary tests, including API failure records and no hard-coded short-case quality logic.
- [ ] Run tests red, implement the generator and benchmark, then run green.
- [ ] Generate one 4-5 minute technical TTS recording and normalize it to 16 kHz mono PCM16.
- [ ] Run batch and quasi-streaming on all three recordings with identical configuration.
- [ ] Compare latency improvement, Whisper request amplification, completeness, and quality; decide batch, hybrid threshold, or quasi-streaming without changing pipeline unless evidence supports it.

### Task 9: Clean Environment and Windows Regression Verification

**Files:**
- Update: evidence sections in `POC_REPORT.md`

**Interfaces:** None.

- [ ] Create a fresh virtual environment outside the source environment, install `requirements.txt`, and run import/startup smoke checks.
- [ ] Run `python -m pytest -q` and record pass/skip count against the 59-pass baseline.
- [ ] Run the actual Windows Startup install/query/uninstall cycle and inspect the generated file.
- [ ] Run daemon PID/start-stop smoke tests, tray, Settings, and autostart checkbox manual checks.
- [ ] Run `scripts/run_full_paste_benchmark.py` and compare tail latency with the approximately 3.5-second historical baseline.
- [ ] Record commands, timestamps, outputs, failures, and anything not executable; never replace missing evidence with assumptions.

### Task 10: Documentation and Mac Handoff

**Files:**
- Modify: `KNOWN_LIMITATIONS.md`
- Modify: `POC_REPORT.md`
- Modify: `CROSS_PLATFORM_PLAN.md`

**Interfaces:** None.

- [ ] Document macOS text-only clipboard preservation and its user-visible consequence.
- [ ] Document prompt and long-recording conclusions with raw-result paths.
- [ ] Separate Windows-verified, unit-tested-only, API-tested, and real-Mac-unverified claims.
- [ ] Add exact Mac operations: permissions denied/granted, hold/release, timeout, Cmd+V and restore, capture UI, reserved warning, LaunchAgent lifecycle and logout/login, tray/settings, overlay click-through/topmost across Spaces/Mission Control.
- [ ] Mark packaging/signing/CI as retained future references and explicitly not executed or prepared.
- [ ] Run `git diff --check`, full tests, and inspect the final diff for accidental distribution work.

