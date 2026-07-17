# SpeedyType POC Report

## 2026-07-17 macOS native stability candidate

`docs/log/mac_log_002.rtf` records the confirmed Settings crash path through
`TSMGetInputSourceProperty`/ctypes on a Python worker thread while Qt was
executing the dialog. The former macOS implementation started a
`pynput.keyboard.Listener` from that path. `mac_log_001.rtf` is consistent with
the same unsafe native path after daemon processing, but remains an inference
without its matching `.ips` report.

The v0.5.4 candidate removes `pynput` from macOS keyboard and paste paths,
uses a process-wide Quartz event tap, configures the daemon as an AppKit
accessory application, and locally skips sub-0.1-second recordings. Automated
tests use fake Quartz/AppKit adapters and therefore do not claim real-Mac
success. Final release remains blocked on the exact acceptance checklist in
`MAC_SETUP.md`.

Date: 2026-07-09

## Current Status

The POC is functionally working. Phase 2 corrected the LLM measurement method, compared Gemini/OpenAI/MiniMax polishing models, selected a new default LLM setting, reran the 10-run full pipeline benchmark, and completed the first real-human recording validation run.

Phase 3 added:

- paste latency substage instrumentation,
- prompt-based ambiguity hints for `API/NPI` and `TPE/PD/BJ`,
- a quasi-streaming Whisper POC,
- a second-round real-voice script and completed validation run.

Current default LLM setting:

- `LLM_PROVIDER=gemini`
- `LLM_MODEL=gemini-3.1-flash-lite`
- `LLM_THINKING_LEVEL=minimal`

Reason: it delivered the best measured balance of latency, quality compliance, cost, and engineering simplicity.

## Phase 1 Baseline vs Phase 2

Previous full-pipeline baseline:

```text
avg_total_tail 26.039232
min_total_tail 5.929520
max_total_tail 76.393551
share_gemini 85.70%
```

Phase 2 full-pipeline benchmark with the new default:

```text
avg_total_tail 3.978559
min_total_tail 2.660100
max_total_tail 5.281294
avg_whisper 2.192584
avg_gemini 0.702315
avg_paste 1.083617
share_whisper 55.11%
share_gemini 17.65%
share_paste 27.24%
```

Measured improvement:

- Average tail latency reduced from `26.039s` to `3.979s`.
- Absolute reduction: `22.061s`.
- Relative reduction: about `84.72%`.

## Target Check

The original `1.0-1.5s` tail-latency target is still not met.

- Current average tail latency is `3.979s`.
- This is `2.479s` above the `1.5s` upper bound.
- The fastest observed full run was `2.660s`, still `1.160s` above the target.

## Real Voice Validation

Real-user recording was completed on July 9, 2026 with 10 final WAV segments in `real_voice/segment01_final.wav` through `segment10_final.wav`.

Summary from [REAL_VOICE_REPORT.md](/C:/WORK/Claude/poc/speedtype/REAL_VOICE_REPORT.md):

- 專有名詞辨識正確率: `50.0%`
- 自我修正處理正確率: `100.0%`
- 贅字清除正確率: `100.0%`

Measured real-voice latency from `run_label=real_voice` rows in `speedytype_latency_log.csv`:

```text
count=10
avg_tail=2.862630
min_tail=1.774415
max_tail=6.526238
avg_whisper=2.209856
avg_llm=0.652579
```

Interpretation:

- The selected Gemini Flash-Lite polishing setting remains fast on real speech.
- The main quality weakness is now Whisper term recognition on real human input, not the LLM cleanup step.
- Representative misses: `TPE` -> `PD`, one `API` -> `NPI`, and one sentence where `TPE` disappeared after the STT stage.

Test-condition note:

- The last recorded sentence had less background noise than earlier sentences. This makes the recording conditions imperfectly uniform, but the run is still valid as an initial real-user benchmark and error analysis set.

## Real Voice Validation Round 2

Second-round real-user recording and validation were also completed on July 9, 2026 with 16 final WAV segments in `real_voice_round2`.

Summary from [REAL_VOICE_REPORT_ROUND2.md](/C:/WORK/Claude/poc/speedtype/REAL_VOICE_REPORT_ROUND2.md):

- 專有名詞辨識正確率: `93.8%`
- 自我修正處理正確率: `100.0%`
- 贅字清除正確率: `100.0%`

Key interpretation:

- The first round’s `50.0%` term-accuracy result was not representative of the broader real-voice behavior.
- On the larger and more controlled second-round dataset, the system is mostly accurate on real speech.
- Residual risk is concentrated mainly on:
  - `API` (`71.4%` in Round 2)
  - `BJ 團隊` (`83.3%` in Round 2)
- All other tracked technical terms in Round 2 reached `100.0%`.

Updated technical judgment:

- The current blocker is no longer “general real-voice term recognition is weak”.
- The remaining problem is narrower: a small set of easily confused terms still need focused STT-side improvement or targeted model comparison.

## Paste and Error Handling

Verified non-admin paste targets:

- Notepad: PASS
- Browser textarea: PASS
- Normal-permission app: PASS
- Admin-elevated window: NOT_TESTED

Silent-audio handling with a real Whisper call:

```text
Recording ended.
Whisper raw transcript:
Whisper returned empty text; skipped Gemini and paste.
```

## Tests

Latest automated test result:

```text
python -m pytest -q
17 passed in 1.05s
```

## Detailed Phase 2 Results

See [PHASE2_MODEL_REPORT.md](/C:/WORK/Claude/poc/speedtype/PHASE2_MODEL_REPORT.md) for:

- provider/model probe evidence,
- cross-provider latency and quality table,
- cost estimates,
- MiniMax/OpenAI/Gemini tradeoff analysis,
- guided-recording fixes and resume support,
- completed real-voice validation results.

## Phase 3 Results

See [PHASE3_REPORT.md](/C:/WORK/Claude/poc/speedtype/PHASE3_REPORT.md) for:

- paste latency breakdown,
- recording-length bucket analysis,
- disambiguation prompt before/after comparison,
- quasi-streaming Whisper benchmark and adoption judgment,
- completed second-round real-voice validation.

## Phase 4 Results

See [PHASE4_REPORT.md](/C:/WORK/Claude/poc/speedtype/PHASE4_REPORT.md) for:

- real production-path latency retest without the benchmark focus artifact,
- Round 2 disambiguation hints on/off comparison,
- focused `API` / `BJ 團隊` STT comparison across `whisper-1`, `gpt-4o-mini-transcribe`, `gpt-4o-transcribe`, and `gpt-realtime-whisper`,
- boundary-case quasi-streaming latency diagnostic.

Phase 4 headline:

- Real-path average tail latency is `3.575354s`, not the older harness-inflated `3.978559s`, but it still misses the `1.0-1.5s` target.
- Disambiguation hints showed no measurable benefit on Round 2: overall term accuracy stayed `93.8%`.
- `whisper-1` remains the recommended STT default for now because it had the best focused `BJ 團隊` accuracy in the Phase 4 comparison.

## Phase 5: Daily-Usability Hardening

Phase 5 shifts from "does the architecture work" validation to closing gaps that block daily use. This round is scoped as Part A (clipboard protection) → Part B (background daemon + visual feedback, checkpointed) → Part C (documentation).

### Part A: Clipboard Protection (completed)

Problem: every paste previously overwrote the user's actual clipboard contents unconditionally. If the user had just copied something else (code, a link) before dictating, it was permanently lost.

Implementation:

- [speedytype/clipboard.py](speedytype/clipboard.py) adds `snapshot_clipboard()` / `restore_clipboard()`, using `win32clipboard` to capture and restore **all** clipboard formats present (not just text), so images/file-drops/app-specific formats are handled without crashing even when they can't be fully round-tripped.
- `paste_text_preserving_clipboard()` wraps the existing `paste_text()`: snapshot before paste, paste as before, then restore the original clipboard content after a configurable delay (`CLIPBOARD_RESTORE_DELAY_SECONDS`, default `0.3s`). The restore runs on a background thread by default so it does not add to measured pipeline latency (the paste has already visibly completed by then).
- `speedytype/pipeline.py` now calls `paste_text_preserving_clipboard()` instead of `paste_text()`.

Restore-delay evidence ([scripts/test_clipboard_restore.py](scripts/test_clipboard_restore.py)):

- Tested delays `0.0s, 0.02s, 0.05s, 0.15s, 0.3s, 0.6s` against Notepad and an Edge browser textarea. All delays down to `0.0s` passed cleanly except one flaky Notepad readback at `0.02s` that was not reproducible over 3 repeats (restore itself succeeded in that run; only the test harness's UI read was stale).
- Selected default: `0.3s` — comfortably above the observed working range, and still far under the ~3.5s total pipeline latency so it is not user-perceptible.

5-run full-pipeline evidence ([scripts/run_clipboard_protection_benchmark.py](scripts/run_clipboard_protection_benchmark.py)), using real Whisper + Gemini + paste against Notepad, five distinct "pre-existing clipboard" snippets (code, a URL, SQL, a shell command, JS):

```text
RUN 1/5 status=PASS paste_ok=True polished_present=True restored_correct=True
RUN 2/5 status=PASS paste_ok=True polished_present=True restored_correct=True
RUN 3/5 status=PASS paste_ok=True polished_present=True restored_correct=True
RUN 4/5 status=PASS paste_ok=True polished_present=True restored_correct=True
RUN 5/5 status=PASS paste_ok=True polished_present=True restored_correct=True
IMAGE_EDGE_CASE status=PASS paste_ok=True polished_present=True cf_dib_restored=True
SUMMARY total=6 passed=6 failed=0
```

The `IMAGE_EDGE_CASE` run pre-loaded the clipboard with a minimal synthetic `CF_DIB` bitmap (non-text) instead of a code snippet, confirming the snapshot/restore path does not crash or silently drop non-text formats.

Automated tests: [tests/test_clipboard.py](tests/test_clipboard.py) adds 6 tests covering text round-trip, empty-clipboard restore, an opaque/unknown binary format, a simulated snapshot-read failure, and both the synchronous and background restore paths. Full suite: `python -m pytest -q` → `23 passed`.

### Part B: Background Daemon + Visual Feedback (completed)

Implementation:

- [speedytype/audio.py](speedytype/audio.py): `Recorder.record_until_stop()` gained an optional `on_level(rms)` callback, throttled to fire at most once per `level_interval_seconds` (default `0.12s`, inside the requested 100-150ms range), computed from the real audio block being recorded.
- [speedytype/overlay.py](speedytype/overlay.py): `RecordingPill`, a frameless, translucent, always-on-top, click-through PyQt6 widget. Fixed dark background (`#1a1a1a`, not theme-reactive), two decorative side dots, and 9 bars whose heights are driven by `update_level(rms)`. A second "processing" render mode shows a spinner + `處理中...` label. `AudioLevelEmitter` is a `QObject` with a `pyqtSignal(float)`; emitting it from the recording thread and connecting it to the pill's slot is the thread-safe bridge to the Qt GUI thread — no shared variables or polling.
- [speedytype/daemon.py](speedytype/daemon.py): `DaemonController` wires the hotkey (`keyboard.on_press_key`), `Recorder`, the existing `process_wav()` pipeline, and the overlay together. Every widget mutation crosses threads via `pyqtSignal`s (`show_recording_signal`, `show_processing_signal`, `hide_signal`), never by touching the widget directly from a worker thread. Writes/removes a PID file (`speedytype_daemon.pid`) so it can be stopped externally.
- [speedytype/cli.py](speedytype/cli.py): new subcommands `daemon`, `daemon-stop`, `install-autostart`, `uninstall-autostart`.
- [speedytype/autostart.py](speedytype/autostart.py): writes/removes a `.bat` script in the user's Startup folder that launches the daemon via `pythonw.exe` (no console window) at logon. Task Scheduler was tried first and rejected with `Access is denied` by this machine's local policy even for a plain per-user trigger (confirmed independent of SpeedyType's code by calling `schtasks` directly); the Startup-folder script is the documented fallback in the task brief and needs no elevation. See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) item 7.
- `PyQt6==6.11.0` added to [requirements.txt](requirements.txt).

No tray icon was added. The task brief's idle-state requirement ("平時畫面上不應該有任何常駐圖示、視窗或系統匣提示") and its own alternative ("...或至少提供一個簡單指令可以停止背景程序") together point to a stop *command* rather than a persistent tray icon competing with "zero idle footprint"; `daemon-stop` was chosen to satisfy both.

Test evidence:

- **Widget rendering**: `pill.grab()` screenshots confirm the recording-mode pill (dots + bars) and processing-mode pill (spinner + text) render as specified.
- **Headless/background operation** ([scripts/test_daemon_smoke.py](scripts/test_daemon_smoke.py)): daemon launched via `pythonw.exe` with `CREATE_NO_WINDOW | DETACHED_PROCESS` (no console ever allocated — the same mechanism the Startup script and a real logon launch use). 5 consecutive hotkey-hold cycles all completed cleanly (2 produced a Whisper-transcribed/polished/pasted result from ambient/played audio, 3 correctly and silently skipped paste on an empty transcript); daemon log showed no exceptions across any run. `daemon-stop` correctly terminated the process by PID afterward.
  - Caveat: because no live human speaker is available to this automated session, "with-text" runs relied on ambient sound/played-back audio rather than fresh dictated speech; content-correctness of the underlying pipeline on real human speech was already established via Part A's 5 real runs and Phases 1-4's real-voice validation, since the daemon calls the exact same `process_wav()`. If a live "hold F9 and speak" check is wanted for full closure of this specific gap, that requires the user's own voice.
- **Volume-reactive bars** ([scripts/verify_volume_bars.py](scripts/verify_volume_bars.py)): real microphone RMS was captured live (through the same `Recorder.record_until_stop(on_level=...)` code path the daemon uses) and each sample logged alongside the resulting bar height, confirming the mapping is driven by live audio, not a fixed animation loop. However, three attempted loudness conditions (silence, played-back audio, amplified played-back audio) produced statistically indistinguishable RMS ranges (all roughly `0.0001-0.009`) on this machine's hardware — the microphone is part of an "AT-CSP1" conferencing speakerphone unit, which likely applies acoustic echo cancellation that suppresses its own speaker output from its own mic feed. This is a hardware constraint discovered during testing, not a code defect; a live "quiet vs. loud human voice" contrast still needs the user's own voice to verify definitively. **Resolved in Phase 8**: the user spoke live at normal then louder volume and confirmed the bars visibly rose — see Phase 8 below and [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) item 13.
- **Mouse click-through** ([scripts/verify_click_through.py](scripts/verify_click_through.py)): the pill was positioned to exactly cover a point inside a real Notepad text-edit control; a real OS-level click was sent at that point, followed by typed text. The typed text appeared inside Notepad, proving the click passed through the visually-opaque pill to the window underneath. `PASS`.
- **Multi-monitor**: **not tested** — this environment has a single display, so multi-monitor positioning/covering behavior could not be verified either way.
- **Real reboot**: **not tested** — a real OS reboot was not performed. Instead, the Startup `.bat` script was invoked directly (the same file, the same way Windows invokes everything in the Startup folder at logon) and confirmed to correctly launch the daemon and produce a valid PID file.
- Full test suite unaffected: `python -m pytest -q` → `23 passed`.

### Part C: Known Limitations

See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) for all limitation entries: the five carried forward from Phases 1-4 (tail latency, `API`/`BJ 團隊` residual error, UAC-elevated paste, plaintext API keys, disambiguation-hint effectiveness), plus two added by Part B (Python-vs-native daemon tradeoff, and Task Scheduler being blocked in favor of the Startup-folder script) — each with its current state, why it isn't being addressed now, and the condition that should trigger re-evaluation.

## Phase 6: Tray Settings, Combo Hotkeys, and About

Phase 6 extends the daemon with a real system tray menu (setting up the `QSystemTrayIcon` this POC did not previously have — Phase 5 had used a `daemon-stop` CLI command instead of a tray icon), a Settings dialog covering recording length/hotkey/vocabulary/API keys, an About dialog, and a `settings.json` persistence layer separate from `.env`.

### Part A: `settings.json` Persistence

- [speedytype/settings.py](speedytype/settings.py): `AppSettings` (max record seconds, hotkey combo as a list, vocab terms as a list), auto-created with defaults on first run, and falling back to in-memory defaults **without touching the file** if it's malformed (so a manually-broken file is diagnosable, not silently clobbered).
- [speedytype/config.py](speedytype/config.py): `load_config()` now sources `max_record_seconds`, `hotkey`, and `whisper_vocab_bias` from `settings.json` instead of `.env`; API keys, provider/model, and other tuning stay in `.env` as before. Default `max_record_seconds` raised from `30s` to `60s` to match the new slider floor.
- Tests ([tests/test_settings.py](tests/test_settings.py), 7 tests): auto-create-on-missing, round-trip, malformed-JSON fallback (file left untouched, warning printed), wrong-shape JSON, hotkey-validation rule, vocab export/import round-trip.

### Part B: Settings Dialog

- [speedytype/settings_dialog.py](speedytype/settings_dialog.py): a `QDialog` with four sections.
  - **Recording length**: a `QSlider` hard-locked to `60-540s` (can't be dragged outside that range — this is a Qt property, not just UI styling), with a live human-readable label (`format_seconds_readable`, e.g. "3 分 30 秒").
  - **Hotkey**: a "擷取新組合鍵" button that calls `keyboard.read_hotkey(suppress=True)` on a background thread and delivers the result back via a `pyqtSignal`. Captured combos are rejected (with an on-screen message, not silently) unless they include a modifier (Ctrl/Alt/Shift/Win) or are a single dedicated function key (F1-F24) — see the design note below. A captured combo is also checked against a small static list of well-known Windows/app shortcuts and flagged as a possible conflict if matched.
  - **Vocabulary**: add/remove/reset-to-default/export/import, with import explicitly labeled "匯入並取代" (replace, not merge) to avoid ambiguity.
  - **API keys**: `OPENAI_API_KEY`/`GEMINI_API_KEY`/`MINIMAX_API_KEY`, masked to the last 4 characters by default with a per-field reveal toggle, plus a "測試連線" button that pings a minimal-cost endpoint (model list) with whatever is currently typed, not necessarily the saved value.
- [speedytype/env_writer.py](speedytype/env_writer.py): `update_env_key()` rewrites only the target `KEY=value` line, leaving every other line (including comments and blank lines) byte-for-byte untouched; appends the line if the key wasn't present. `mask_secret()` implements the last-4-visible masking. `test_openai_key`/`test_gemini_key`/`test_minimax_key` each do a lightweight "list models" GET.
- Save writes `settings.json` unconditionally (cheap/safe) and only touches `.env` for keys that actually changed, reporting exactly which ones in the status line (e.g. "一般設定已儲存 / 金鑰已更新（GEMINI_API_KEY）"). Cancel (`close()`) writes nothing at all, even if a key field was edited during a test-connection check.

**Hotkey design decision (any-key-release ends recording, not all-keys-released)**: reusing the existing single-key `wait_until_hotkey_released()` polling loop unchanged, driven by `keyboard.is_pressed("ctrl+alt+space")`, means recording stops the instant *any one* key of the combo is released — this is the `keyboard` library's documented behavior for `is_pressed()` on a `+`-joined string, not extra code written for this feature. Reasoning for keeping this rather than requiring all keys released: (1) it requires zero new release-detection logic, reusing an already-working path; (2) real combo releases are rarely simultaneous, and requiring every key held until the last one lifts is a less forgiving, less natural gesture than the common "push-to-talk" convention (e.g. Discord) of stopping on first release.

**This design was not verified with real/simulated key presses this round.** At the user's explicit request, no synthetic system-wide key events (`keyboard.press()/release()`) were sent, since those affect whatever window currently has focus regardless of which app "owns" the test. What *was* verified without any OS-level input simulation:
- Countdown-timer and auto-stop-at-limit behavior ([scripts/verify_countdown_and_autostop.py](scripts/verify_countdown_and_autostop.py)): `DaemonController.on_press()` called directly (a plain method call, not a key event) with `max_record_seconds=8.0` and `countdown_warning_seconds=4.0`, `keyboard.is_pressed` monkeypatched to `True` for the test's duration (an in-process Python function stand-in with no OS-level effect, the same technique already used in `tests/test_hotkey.py`). Result: countdown first appeared at `t=4.03s` (threshold `4.0s`), ticked down to `0`, and recording auto-stopped at `t=8.55s` (limit `8.0s`, the ~0.5s overshoot being the 0.2s ticker poll interval); `process_wav` was invoked exactly once.
- Non-blocking Settings dialog ([scripts/verify_settings_dialog_nonblocking.py](scripts/verify_settings_dialog_nonblocking.py)): opened non-modally (`.show()`, not `.exec()`) alongside a simulated (direct-call) recording/timeout/processing cycle; the dialog remained visible and interactively responsive (a live text edit was accepted) throughout, and the pipeline still completed. `PASS`.
- Settings dialog widget behavior ([tests/test_settings_dialog.py](tests/test_settings_dialog.py), 7 tests; [tests/test_about_dialog.py](tests/test_about_dialog.py), 1 test): slider min/max clamping, vocab add/remove/reset, vocab export-then-import round-trip (content compared, not just file existence), masked-field reveal/hide/edit, save-only-touches-changed-keys with `.env` line preservation verified against a multi-line file with comments, cancel-writes-nothing, and About dialog content matching the live config — all via Qt method calls (`.click()`, `.setText()`), which are in-process signal triggers, not OS input.

**Live verification (post-delivery)**: the user captured `ctrl+alt+space` via the Settings dialog, saved, restarted the daemon from the tray, and confirmed holding/releasing the combo starts and stops recording normally — confirming the any-key-release-ends design above works in practice, not just per the `keyboard` library's documented behavior. See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) item 8 (now marked resolved) and item 9 (conflict detection, still a static list only).

### Part C: About Dialog

- [speedytype/version.py](speedytype/version.py): `VERSION = "0.5.3"`, `BUILD_DATE = "2026-07-16"`, `STT_MODEL = "whisper-1"`.
- [speedytype/about_dialog.py](speedytype/about_dialog.py): shows version, build date, current `llm_provider`/`llm_model` (read live from config), STT model, and a pointer to `KNOWN_LIMITATIONS.md`. Verified by test to match the live `AppConfig` rather than hardcoded strings.

### Part D: Tray Menu Integration

- [speedytype/daemon.py](speedytype/daemon.py): added a `QSystemTrayIcon` (icon generated at runtime — no icon asset file exists in this POC) with a context menu: 設定, 關於, a separator, 重新啟動, 結束. Hotkey registration switched from `keyboard.on_press_key` (single-key only) to `keyboard.add_hotkey()`, which accepts both single keys and `+`-joined combos through the same call, so no special-casing is needed for the new combo support.
- "重新啟動" spawns a fresh detached `pythonw.exe` daemon process, then calls `app.quit()` on the current one. `run_daemon()`'s PID-file cleanup now only deletes the file if it still names *this* process's PID (checked before unlinking), closing a race where a fast-starting new process's PID file could otherwise be deleted by the old process's shutdown.
- Both dialogs are opened non-modally (`.show()`), confirmed above to keep the hotkey/pipeline fully functional while either is open.

Full automated suite after all Phase 6 changes: `python -m pytest -q` → `43 passed` (one `test_paste_text_preserving_clipboard_background_restores_after_delay` run showed a transient, pre-existing `OpenClipboard`/`Access is denied` flake unrelated to this round's changes — passes cleanly on rerun, consistent with clipboard-contention flakiness already noted in Phase 5).

### Bug found and fixed: the daemon crashed immediately whenever launched via `pythonw.exe` without an explicit stdout redirect

While verifying the live "重新啟動" tray action (in response to the user reporting no tray icon appeared after restart, and that it also never appeared when using the Startup-folder autostart), the actual root cause was found and confirmed with direct evidence, not assumed:

```text
stdout=None
safe_print_failed=AttributeError("'NoneType' object has no attribute 'write'")
```

`pythonw.exe` has no console, so `sys.stdout`/`sys.stderr` are `None` unless a caller explicitly redirects them. `speedytype/console.py`'s `safe_print()` called `sys.stdout.write(...)` directly with no guard for `None`, so the very first `safe_print()` call in `run_daemon()` — right after `tray.show()` — crashed the whole process. The tray icon would appear for a fraction of a second (from `tray.show()` succeeding) and then vanish as the process died, matching the user's report exactly. This same code path exists in the **Phase 5** `run_daemon()`, so the Startup-folder autostart added in Phase 5 has likely never actually kept the daemon running after logon; this had gone unnoticed because the daemon smoke test in Phase 5 happened to explicitly redirect `stdout=` to a log file when spawning, which avoided triggering the crash.

Fix, verified with real (non-simulated) process checks:

- [speedytype/console.py](speedytype/console.py): `safe_print()` now returns silently instead of raising if `sys.stdout` is `None` or the stream write/flush fails (`AttributeError`/`ValueError`/`OSError`), tested in [tests/test_console.py](tests/test_console.py) (3 tests, including one that monkeypatches `sys.stdout = None` directly).
- [speedytype/daemon.py](speedytype/daemon.py)'s `_relaunch_daemon()` and [speedytype/autostart.py](speedytype/autostart.py)'s generated `.bat` now both explicitly redirect stdout/stderr to `speedytype_daemon.log` (with `PYTHONIOENCODING=utf-8` set for the child process, since the default encoding for a redirected non-console stream otherwise mangled Chinese log text into `?`/`??`) — belt-and-suspenders on top of the `safe_print` fix, so restart/autostart failures stay diagnosable.
- Verified: launched `pythonw.exe -m speedytype daemon` directly (mirroring exactly what restart/autostart do) — confirmed via `tasklist` and the PID file that the process was still alive after 9 seconds (previously it died within ~1s of starting), then re-ran the actual generated Startup `.bat` script end-to-end and confirmed the log file now contains correctly-encoded Chinese text (`結束`) instead of `??`.
- Also fixed while in the area: `speedytype/settings_dialog.py`/`about_dialog.py` now call `setWindowIcon()` (previously unset, leaving a blank top-left title-bar icon, which the user also flagged), reusing a small shared glyph generator moved to [speedytype/icon.py](speedytype/icon.py).

See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) item 11 for how this affects Phase 5's already-shipped autostart claim.

## Phase 7: Recording Device Selection

Adds a microphone/input-device picker to the Settings dialog. No other section of the dialog (recording-length slider, hotkey, vocabulary, API keys) was touched.

Implementation:

- [speedytype/audio.py](speedytype/audio.py): `list_input_device_names()` and `find_input_device_index_by_name(name)` (exact-name lookup against `sounddevice.query_devices()`).
- [speedytype/settings.py](speedytype/settings.py): `AppSettings.mic_device_name` (empty string = system default), persisted in `settings.json` like the other behavior settings. Stored **by name, not index**, since device indices can shift across reboots/replugs/host-API enumeration order changes.
- [speedytype/config.py](speedytype/config.py): new `resolve_mic_device_setting(name)` resolves a saved device name against currently-available devices at `load_config()` time. If the name is no longer found, it falls back to the system default (empty string) and returns a non-empty warning message instead of raising — `AppConfig` gained a `mic_device_warning: str` field carrying that message through.
- [speedytype/settings_dialog.py](speedytype/settings_dialog.py): a new "錄音裝置" `QComboBox` group, "系統預設裝置" listed first (maps to `""`), followed by every current input device's name (no raw index shown to the user). If `config.mic_device_warning` is non-empty, it's shown as a red warning label at the top of this group when the dialog opens — chosen over the About dialog since it's the actionable place to immediately pick a replacement device. Marked with the same "restart required" note as hotkey/recording-length, since the daemon's `Recorder` is only constructed once at startup.

Test evidence:

- **List accuracy** ([tests/test_settings_dialog.py](tests/test_settings_dialog.py), `test_device_combo_lists_current_input_devices_matching_sounddevice`; also [scripts/verify_mic_device_selection.py](scripts/verify_mic_device_selection.py)): the combo box's contents were compared directly against a raw `sounddevice.query_devices()` filter, not just against our own wrapper — exact match confirmed on the real machine (16 real input devices enumerated, including duplicate names across host APIs, e.g. four devices all named `Microphone (AT-CSP1)` at different indices — resolution is first-match-in-enumeration-order, which happens to coincide with the system default here).
- **Selection actually changes the device passed to recording** (`scripts/verify_mic_device_selection.py`): built a `Recorder` with the system default (`device=""`) and confirmed its resolved `.device` matched `sounddevice`'s actual default index; then built one with an explicit **non-default** device name and confirmed `.device` resolved to that device's own distinct index — proving the UI selection genuinely changes what gets passed to `sd.InputStream`, not a hardcoded value. Repeated with a second, genuinely distinct physical microphone (`Microphone Array (2- Intel...)`, index 2 vs. default index 1) for stronger evidence than the first pass (which happened to land on a virtual "Sound Mapper" pseudo-device).
- **Real audio captured through the selected device**: `record_diagnostic()` through the explicit non-default device produced non-zero real samples (`rms=0.000204-0.002159`, `peak` correspondingly non-zero across two different devices tested) — not a stub.
- **End-to-end via settings.json + load_config()**: saved a specific device name to a real `settings.json`, loaded config, and confirmed `config.mic_device` equals that name with no warning, and that a `Recorder` built from that config resolves to the correct device index.
- **Fallback on a missing device**: saved a fabricated nonexistent device name to `settings.json`; `load_config()` correctly fell back to `config.mic_device == ""` with a non-empty `mic_device_warning`, and a `Recorder` built from the fallback config did not crash (resolved to the real system default). Also covered in the Settings dialog itself (`test_device_combo_falls_back_to_default_when_saved_device_missing`): the combo box selects "系統預設裝置" without crashing when the saved name isn't found among current devices.
- Full suite: `python -m pytest -q` → `55 passed` (one `test_snapshot_restore_survives_opaque_binary_format_without_crashing` run hit the same pre-existing transient `OpenClipboard`/`Access is denied` clipboard-contention flake noted in Phases 5-6 — passes cleanly on rerun).

## Phase 8: Overlay Centering, PID Staleness, and Long-Text Real-Voice Retest

### Part A: Overlay Centered at Bottom of Screen

- [speedytype/overlay.py](speedytype/overlay.py): `_position_at_corner()` renamed to `_position_bottom_center()`. Horizontal offset changed from `geo.right() - PILL_WIDTH - SCREEN_MARGIN` (bottom-right) to `geo.left() + (geo.width() - PILL_WIDTH) // 2` (horizontally centered); the vertical offset (`geo.bottom() - PILL_HEIGHT - SCREEN_MARGIN`) is unchanged, per the task's scope. Multi-monitor logic is unchanged — still resolves via `QApplication.primaryScreen()`, only the horizontal formula changed.
- Verified with real coordinates, not just a screenshot: on this machine's primary screen (`availableGeometry` = left=0, top=0, width=1536, height=912), the pill's actual position after `show_recording()` was `x=658, y=831`, exactly matching the computed expectation, and the pill's own center (`658 + 220/2 = 768`) exactly matches the screen's center (`1536/2 = 768`, diff `0.0`). Re-verified against a **real running `DaemonController`** (`on_press()` called directly, real `Recorder`, real overlay, real ~2s recording) rather than just an isolated widget — same exact match.
- Single-monitor environment only; multi-monitor centering behavior remains **not tested**, unchanged from Phase 5's note.
- Bonus fix found while verifying: `tests/test_clipboard.py`'s helper functions (`_set_clipboard_text`, `_clear_clipboard`, `_get_clipboard_text`) called `win32clipboard.OpenClipboard()` directly with no retry, unlike production code's `_open_clipboard()` which already retries 5× with backoff — back-to-back tests in the same file gave near-zero gap between clipboard operations, causing exactly the transient `Access is denied` flakiness documented (and shrugged off) since Phase 5. Added the same retry pattern to the test helpers; confirmed with 5 consecutive clean full-suite runs (previously failing on most runs) that this was the actual root cause, not unfixable OS-level contention.

### Part B: PID Staleness Detection

Checked current behavior first, per the task's explicit request not to assume:

- Normal `daemon-stop` → PID file deletion: confirmed still correct (unchanged).
- Stale PID file (manually wrote a non-existent PID, confirmed via `tasklist` that it corresponded to no process) → **no check existed at all**. `run_daemon()` unconditionally overwrote the PID file and started normally regardless of its prior content. This means a stale PID file was never actually a "wrongly refuses to start" problem — but by the same token, a **genuinely live** daemon's PID file also provided zero protection against a second real instance starting, which independently confirms a bug an earlier code review had already flagged (dual-daemon race on restart).

Implemented `check_existing_daemon()` in [speedytype/daemon.py](speedytype/daemon.py): no PID file → proceed silently; unreadable/non-numeric content → treated as stale, cleaned up, proceed; PID file names a process confirmed via `tasklist` to no longer be running → cleaned up automatically, proceed (no manual deletion needed); PID file names a genuinely live process → refuse to start with a clear message instead of launching a second instance. Wired into `run_daemon()` before any Qt/tray setup.

This also exposed and fixed a second bug: `restart_daemon()` (tray "重新啟動") spawns the replacement process *before* the current one quits, so the new process's own `check_existing_daemon()` check would see the still-alive old PID and refuse to start — silently breaking restart. Fixed by having `restart_daemon()` remove its own PID file (via the existing `_remove_pid_file_if_mine()`, which only acts if the file still names the calling process) immediately before spawning the replacement.

Test evidence, all against real processes (not mocks):

- `tests/test_daemon_pid.py` (4 tests): no-file, stale-numeric-PID (auto-cleaned), genuinely-running-PID (this test process's own PID — refused, file left untouched), and non-numeric-content (treated as stale).
- Real end-to-end: wrote a fake stale PID (`888888`), launched the real daemon via `pythonw.exe` — it started cleanly with a fresh real PID, confirmed via `tasklist`. Then attempted a **second** real launch while the first was genuinely running — confirmed via its log that it printed the refusal message and exited, and `tasklist` showed only the original single process throughout; the PID file was untouched.
- Full restart cycle: reproduced `restart_daemon()`'s exact sequence (`_remove_pid_file_if_mine()` then `_relaunch_daemon()`) from within a process holding its own real PID in the file — confirmed the new process started cleanly (not refused) and wrote its own fresh PID.

### Part C: Long-Text + Live Real-Voice Retest

All three sub-tests below used the user's own live voice through the real daemon and real microphone — no synthetic playback, no environment-noise substitution, addressing both the Phase 5 AEC gap and the never-tested "long recording through the full pipeline" question.

**Test 1 — quiet vs. loud, real voice**: user held the hotkey, spoke at normal volume, released; held again, spoke noticeably louder, released. Confirmed: the pill's bars visibly rose higher during the louder pass. This closes [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) item 13 (previously blocked because the test machine's mic is part of an echo-cancelling conferencing speakerphone that suppressed its own played-back test audio — a live human voice sidesteps that entirely). Both runs completed normally (`total_tail_latency_seconds` = `2.664s`, `3.420s`).

**Test 2 — short-sentence regression (4 runs, reusing Round 2-style sentences)**: all technical terms preserved correctly across all runs — `TPE 團隊` (×2), `BIOS` (×2), `QA`, `NPI`, `BJ 團隊`, `USB`. Tail latencies: `2.817s, 3.532s, 2.484s, 1.771s` (avg `2.651s`).

**Test 3 — long-form (~2-2.5 minutes, real continuous speech)**: two recordings, `126.4s` and `133.8s` long. The countdown warning was confirmed by the user to display correctly during both (both recordings ran past the 120s mark, i.e. within 60s of the temporary 180s test ceiling used for this round). Neither hit the hard 180s cutoff (both were released by the user), so auto-stop-at-limit itself was not re-exercised here — that was already verified synthetically in Phase 6 ([scripts/verify_countdown_and_autostop.py](scripts/verify_countdown_and_autostop.py)) and this round's own live countdown confirmation is the piece that mattered (a real multi-minute recording, not a mocked timer). The second recording's polished output (reproduced from the actual Notepad paste) correctly used two Markdown bullet lists, preserved every technical term mentioned (`Python`, `BIOS`, `Firmware`, `TPE 團隊`, `BJ 團隊`, `API`, `USB`, `Thunderbolt`, `PM`), and organized freeform rambling into two clearly-labeled sections. Whisper time for these ~130s recordings was `6.49s` and `7.19s` — meaningfully higher than short clips but far from linear with the ~26× increase in audio duration, confirming with real human speech (not just TTS, as in Phase 3) that Whisper latency does not scale proportionally with recording length. Tail latencies: `8.167s`, `8.839s` — a new data point (no prior long-form baseline to compare against), but well within usable range for a 2+ minute dictation.

Note: recording 1 of Test 3 pasted into a window that had lost focus by the time processing finished (a real, if narrow, timing risk with long dictations — the user must keep the target window focused for the full duration plus processing time); this is not a new bug, just an observation, and is left unaddressed as out of this round's scope.

The user also flagged, from the Test 3 transcript, that "LeetCode" was misheard by Whisper as "Zcode" — a minor STT miss on a term not in the tracked vocabulary bias list; noted but not acted on this round.

### Follow-up finding: Whisper collapses an exact phrase repeated back-to-back in one recording

After the main three tests, the user asked to specifically verify a suspicion: that a short recording containing the same phrase repeated multiple times might lose content. Live-tested: user held the hotkey **once** and said "測試1、2、3、4" three times in a row within a single continuous recording. The daemon's own log showed only **one** `Recording...` cycle (not three separate ones — confirming the user did one continuous hold, not three press/release cycles) and:

```text
Recording ended.
Whisper raw transcript: 測試 1、2、3、4
Gemini polished text: 測試 1、2、3、4
Latency seconds: recording=8.580, whisper=1.098, gemini=0.572, paste=0.188, total_tail=1.859
```

The raw Whisper transcript already contains only one instance of the phrase — Gemini's polishing stage passed it through completely unchanged, proving the loss happens at the Whisper API stage itself, not in this project's prompt or polishing logic. This is a real, narrow finding (repeating the exact same short phrase with no variation inside one continuous recording), distinct from Test 2's result (three *different* sentences across three *separate* recordings, all transcribed correctly with zero loss). Documented as [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) item 15.

**Latency comparison table** (all numbers real, pulled directly from `speedytype_latency_log.csv`):

| Source | Content type | n | Avg tail (s) | Min (s) | Max (s) |
|---|---|---:|---:|---:|---:|
| Phase 2 full-pipeline benchmark | TTS-generated, short/medium/long | 10 | 3.979 | 2.660 | 5.281 |
| Phase 4 real-path benchmark | TTS-generated, harness artifact removed | 10 | 3.575 | 2.071 | 4.684 |
| Historical `real_voice` validate-real-voice runs (Rounds 1-2 combined) | Real human, guided short/medium sentences | 36 | 3.632 | 1.311 | 14.222 |
| **Phase 8 Test 1+2 (this round)** | **Real human, live daemon, short sentences** | **6** | **2.781** | **1.771** | **3.532** |
| **Phase 8 Test 3 (this round)** | **Real human, live daemon, ~2-2.5 min continuous** | **2** | **8.503** | **8.167** | **8.839** |

Conclusion: **no latency regression detected** from Phases 5-6's UI/feature additions (tray icon, Settings/About dialogs, settings.json loading, clipboard protection). This round's short-sentence real-voice numbers are as good as or better than every prior benchmark, including the very first Phase 2/4 TTS-based ones. The long-form number is a new data point with no prior baseline, not a regression by definition, and is itself reassuringly modest for 2+ minutes of continuous dictation.

Full suite after all Phase 8 changes: `python -m pytest -q` → `59 passed`, confirmed stable across 3 consecutive full runs (this also includes the clipboard-flake fix noted in Part A above).
# Cross-Platform Core Follow-up (2026-07-11)

This round intentionally implemented only the platform abstraction layer and macOS source backends. Packaging, signing/notarization, installers, icons, `pyproject.toml`, and CI were not created.

## Windows evidence

- Pre-change baseline: `59 passed in 6.30s`.
- Post-change suite: `72 passed` before final documentation/script tests; final count is recorded by the closing verification command.
- Clean environment: a new `.venv-clean` installed `requirements.txt` successfully and printed `CLEAN_IMPORT_OK` after importing numpy, PyQt6, platformdirs, psutil, CLI, and daemon modules.
- Startup integration: the real Startup-folder script was installed, queried as present, removed, and queried as absent.
- Daemon smoke: the updated app-data PID path was observed with a live `pythonw` process; one hotkey record/process/paste run returned `PASS_WITH_TEXT`, then daemon-stop succeeded.
- Full paste latency: one valid run measured `3.732907s` total tail (`2.024753s` Whisper, `0.612778s` Gemini, `1.095331s` paste), consistent with the historical approximately 3.5-second baseline.

## External API investigations

- Gemini prompt follow-up (historical 2026-07-11 state): current prompt produced 4/4 valid number-preserving samples; quota errors prevented new candidate evidence at that time. This conclusion was superseded by the completed 2026-07-12 investigation below.
- Long recordings: the initial 262s composite was rejected as decisive evidence because its two source recordings discuss overlapping meeting topics. A replacement 294.792s continuous, non-repeating TTS narrative measured 18.098s batch tail versus 1.874s for the 30s/5s-overlap quasi simulation (89.6% improvement). This confirms the latency trend is not a splice artifact, while transcript omissions/boundary errors still block production enablement.

## macOS handoff

Code and Windows-runnable contracts exist for text-only clipboard preservation, pynput hold/release and capture, canonical hotkey tokens, LaunchAgent plist management, reserved shortcut warnings, and permission guidance. These are not claimed as operationally verified until the exact real-Mac checklist in `KNOWN_LIMITATIONS.md` item 18 is completed.

## Hybrid v2 follow-up

The silence-aware hybrid plan was implemented behind a disabled-by-default feature flag. Offline and integration coverage reached 122 passing tests, and a Windows daemon smoke exercised the real hybrid record/transcribe/polish/paste path. The final three-run benchmark showed 72.3% complete-tail improvement on the 295-second continuous file with 1.83x Whisper request work. Quality was split into source accuracy and same-run batch-relative hybrid regression so baseline Whisper errors are not blamed on hybrid code; the hybrid regression gate nevertheless passed 0/3 for every case. Cases A-C were recovered; Case D remained an extra hybrid lexical corruption inside a distinct segment. Because the batch-relative content gate failed and real Mac/paste benchmark gates remain incomplete, production stays on batch transcription.

## Combined LLM polishing investigation (2026-07-12)

The candidate number/repeated-content prompt rule was adopted after reaching 6/6 valid candidate samples preserving `123`, reproducing current-prompt loss versus candidate preservation on the production Gemini model, and confirming no regression in self-correction, filler removal, key-term preservation, list formatting, natural-stutter cleanup, or Chinese-number preservation. The production prompt now keeps numbers, identifiers, and real content while consolidating garbled repetition, with an explicit exception for genuine self-correction.

The separate `API` / `BJ 團隊` over-correction hypothesis was rejected after 17 raw-Whisper-versus-polished comparisons. The old 71.4% / 83.3% figures used an invalid denominator that counted corrected-away terms as required final output. The only observed final-intent failures were two raw-STT `API` substitutions (`NPI` and `AVM`); Gemini introduced no target-term error. The corpus is too small to publish a replacement real-world percentage. Full quota accounting, six-dimension prompt results, and every sentence-level pair are in [COMBINED_LLM_INVESTIGATION_REPORT.md](COMBINED_LLM_INVESTIGATION_REPORT.md).

## Part A: Keyring-backed API keys (2026-07-14)

### Architecture

- `load_config(real_env_path, settings_path=<temporary settings.json>)` delegates secret resolution to `resolve_api_keys()` without creating or changing the production `settings.json`. For each configured provider, the resolution order is OS keyring (`SpeedyType` service), process environment, then `.env` compatibility fallback.
- File-sourced values migrate only after a successful keyring write and exact read-back. Only the effective `.env` assignment whose parsed value still matches the verified migrated value is scrubbed; unrelated lines and changed source values are preserved.
- The Settings dialog uses the same keyring-backed store for changed-key writes and deletes. Production usernames are `openai_api_key`, `gemini_api_key`, and `minimax_api_key` and are read-only in the fallback verifier.
- `scripts/verify_keyring_live.py` bootstraps the repository root onto `sys.path` before package imports so invocation through the documented direct command can import the project package. Its `--env` option selects the real environment file while defaulting to the app-data path; on this machine the POC file remains in place and must be selected explicitly. It performs production migration/readback and prints only fixed provider `PASS`/`FAIL` status, never helper messages, exceptions, URLs, or response bodies. Its isolated fallback exercise can mutate only the fixed `fallback_test_api_key` username, confines its `.env` and settings file to a supplied temporary directory, uses explicit runtime guards that cannot be optimized away, refuses an unknown pre-existing value without mutation, and verifies absence after every delete. A fallback result passes only when `resolve_api_keys()` reports that the fake value was migrated from the temporary `.env`, so a lingering keyring value cannot masquerade as fallback success.

### Automated evidence

- RED: `python -m pytest tests/test_keyring_live_script.py -v` failed during collection because `scripts.verify_keyring_live` did not yet exist, which was the expected missing-feature failure.
- GREEN verifier safety tests after pre-execution review, direct-script import fix, and env-selection fix: `python -m pytest tests/test_keyring_live_script.py -q` → `12 passed in 1.62s`. Coverage includes isolated direct-script import, explicit/default env argument forwarding without live operations, mutation-username isolation, foreign-value refusal with zero mutation, known-fake residue cleanup, delete readback enforcement, temporary `.env`/settings confinement, migration provenance, explicit production-username rejection, fixed provider output for returned messages and raised exceptions, production read-only lookup, and optional MiniMax absence.
- Focused Part A regression set: `python -m pytest tests/test_keyring_live_script.py tests/test_secrets_store.py tests/test_config.py tests/test_settings_dialog.py -q` → `47 passed in 2.60s`.
- Full suite: `python -m pytest -q` → `161 passed in 4.82s`.

### Live evidence

- Guarded verifier: `python scripts/verify_keyring_live.py --env C:/WORK/Claude/poc/speedytype/.env` exited `0`. It reported migration of `OPENAI_API_KEY`, `GEMINI_API_KEY`, and `MINIMAX_API_KEY`; every production entry reported `exists=PASS` and `matches_resolved=PASS`; OpenAI, Gemini, and MiniMax provider checks all reported `PASS`; isolated keyring round-trip, temporary `.env` fallback, and cleanup all reported `PASS`; final status was `live keyring verification: PASS`.
- Plaintext scrub post-check: `remaining_env_lines=0` for each of `OPENAI_API_KEY`, `GEMINI_API_KEY`, and `MINIMAX_API_KEY` in the parent POC `.env`.
- Windows Credential Manager inspection: `cmdkey /list` showed Generic targets `openai_api_key@SpeedyType`, `gemini_api_key@SpeedyType`, and `minimax_api_key@SpeedyType`. No credential values were exposed.
- Daemon API evidence: the first smoke run started PID `6324`; its daemon log contained `whisper_success_markers=1`, `llm_success_markers=1`, and `failure_markers=0`. The smoke harness then hit a local `cp1252` `UnicodeEncodeError` while printing pasted Chinese text, after the daemon API work had succeeded. PID `6324` was explicitly stopped successfully.
- UTF-8 harness rerun: with `PYTHONIOENCODING=utf-8`, the smoke started and stopped PID `38744` cleanly and reported `SUMMARY total=1 empty_handled=1 crashed=False`. Its silent input produced no API call, so the first run's log markers—not this silent rerun—are the successful daemon API evidence.
- Latency isolation: neither smoke used the production latency log; the harness pointed to ignored `.superpowers/sdd/daemon-smoke-latency.csv`.

## Part B: Daily usage and estimated costs (2026-07-15)

### Recorded data and scope policy

- The latency CSV appends `usage_scope`, `stt_model`, `stt_audio_seconds`, `llm_input_tokens`, `llm_output_tokens`, and `llm_total_tokens`. Old headers are migrated with existing values preserved and new cells blank. Missing provider token metadata is written as blank, never manufactured as zero-valued provider usage.
- `process_wav()` defaults to `usage_scope="development"`. The daemon normal/hybrid paths and CLI `run-once`/`listen` explicitly pass `daily`; benchmark, real-voice, and other programmatic callers remain excluded unless they explicitly opt in.
- For older rows without `usage_scope`, only blank, `hybrid`, and `hybrid_fallback` `run_label` values are inferred as daily. Other non-empty legacy labels, including `real_voice`, are excluded. The Settings warning reports how many rows were inferred.
- STT calls use a positive `hybrid_request_count` when present, otherwise one call per accepted row. STT minutes use authoritative submitted `stt_audio_seconds`: normal batch calls submit the recording once, while hybrid sums every attempted chunk and adds the full recording when batch fallback runs. Legacy rows without this field fall back to `recording_seconds`. LLM calls are recognized from a recorded model, with the old `gemini_seconds > 0` fallback limited to accepted inferred-legacy rows. LLM input/output totals use only provider-reported `LlmUsage`; absent tokens are not estimated.

### Fixed known-data proof

The fixed fixture contains two explicit daily rows (60s and 30s), one explicit development row, one excluded legacy `real_voice` row, and one accepted blank-label 30s legacy row. The development and excluded legacy rows carry deliberately large values so accidental inclusion fails visibly.

- STT: `60 + 30 + 30 = 120` seconds = `2.0` minutes and `3` calls. At `whisper-1` `$0.006/minute`, the estimate is exactly `$0.012`.
- LLM: only the two new daily rows provide authoritative usage, totaling `1,500` input and `300` output tokens. At `$0.25`/`$1.50` per million, the estimate is exactly `(1500 × 0.25 + 300 × 1.50) / 1,000,000 = $0.000825`.
- Total: exactly `$0.012 + $0.000825 = $0.012825`.

### Pricing and Settings behavior

- Root `pricing.json` is the only price source. Its bundled `updated_date` is `2026-07-14`, currency is USD, and it contains the approved Whisper, Gemini, OpenAI, and MiniMax model rows. Python contains schema/formula constants but no fallback price amounts. These are dated local estimates: no provider usage/billing endpoint is queried and no invoice reconciliation occurs.
- Missing, unreadable, malformed, structurally invalid, or unknown-used-model price data makes the affected cost unavailable, never an implicit zero. Missing/invalid latency input makes usage and costs unavailable and clears partial totals; isolated malformed CSV rows are skipped with an explicit count while the remaining readable rows stay usable.
- Settings displays models, STT calls/minutes, LLM calls and authoritative input/output tokens, six-decimal component/total estimates, `updated_date`, legacy inference, and the exact disclaimer `估算費用，非實際帳單，價格可能已變動`. Usage remains visible when pricing alone is unavailable.
- `PriceEditorDialog` edits numeric prices for existing models only. Controls accept `0..1,000,000` with eight decimal places; model add/delete remains manual JSON work. A successful save validates the complete schema, serializes exact Decimal JSON numbers to a unique exclusively-created sibling temp, flushes and `fsync`s it, then atomically replaces the destination and refreshes Settings exactly once. Validation/write/replace failures preserve the original bytes; missing/corrupt inputs expose no editable controls. The remaining stat/unlink cleanup interval is only a theoretical hostile-process race on the unique failed-temp path, not a loss of atomic destination replacement.

### Fresh Task 5 automated evidence

- Full retry, required first: `QT_QPA_PLATFORM=offscreen python -m pytest -q` → `243 passed, 5 failed in 7.31s`. All five failures were in `tests/test_clipboard.py`; every failing path exhausted its retry loop at `win32clipboard.OpenClipboard()` with Windows error 5, `Access is denied`. No separate clipboard probe, clipboard mutation workaround, or process termination was performed.
- Required targeted proof: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_usage_stats.py tests/test_pipeline_usage.py tests/test_settings_dialog.py tests/test_pricing_dialog.py -v` → `100 passed in 2.25s`. This includes exact fixed-fixture costs, explicit development exclusion, authoritative token propagation, daily entry-point scope, pricing tolerance, Settings copy/date, and atomic editor behavior.
- Full suite excluding only the externally blocked real-clipboard module: `QT_QPA_PLATFORM=offscreen python -m pytest -q --ignore=tests/test_clipboard.py` → `242 passed in 4.62s`.
- Static/syntax check: `python -m compileall -q speedytype scripts` → exit `0`, no output.
- Documentation diff check: `git diff --check` → exit `0`; Git printed only the checkout's LF-to-CRLF notices for the two edited Markdown files.

### Integration verification after current-master reconciliation

- The feature branch was reconciled with keyring-enabled `master`; the feature's stricter source-change checks, cross-platform file locking, delete read-back verification, and redacted errors were retained.
- Reviewer-found fallback regressions were fixed: empty keyring and process-environment values now continue to valid `.env` fallback, and `PasswordDeleteError` is idempotent only when read-back confirms the credential is absent.
- Hybrid fallback cost accounting now records all submitted STT audio seconds rather than charging only one copy of the original recording.
- Old latency CSV migration now runs under a writer lock, writes the migrated history plus new row to a unique sibling temp file, flushes and `fsync`s it, then atomically replaces the destination. Injected write and replace failures preserve the original bytes.
- Targeted usage/cost, keyring, hybrid, pipeline, and latency regression sets passed during the fixes.
- Fresh complete suite, including the real Windows clipboard module: `python -m pytest -q` → `273 passed in 7.40s`.
- Fresh static/syntax and diff checks: `python -m compileall -q speedytype scripts` and `git diff --check` both exited `0`.

### Part A Windows evidence retained without rerunning live operations

- Three Windows Generic Credential targets were observed exactly as `openai_api_key@SpeedyType`, `gemini_api_key@SpeedyType`, and `minimax_api_key@SpeedyType`; values were not exposed.
- The guarded verifier recorded production `exists=PASS` and `matches_resolved=PASS` for all three resolved credentials and OpenAI, Gemini, and MiniMax provider probes all returned `PASS`. The successful migration scrub left zero effective plaintext assignments for the three key names in the selected parent `.env`, while preserving unrelated content.
- The daemon smoke log recorded `whisper_success_markers=1`, `llm_success_markers=1`, and `failure_markers=0`. Its later console encoding failure occurred after API success; the daemon PID was explicitly stopped, and the UTF-8 silent-input rerun then started/stopped cleanly.
- The fallback exercise mutated and deleted only the dedicated `fallback_test_api_key` with a known fake value and temporary `.env`/settings paths. Production usernames were read-only in this exercise. No real key was deleted, overwritten, substituted, or printed. Normal resolution remains keyring first, then process environment/`.env` compatibility fallback when no stored credential is available; failed migration leaves the source value intact.
- Task 5 did not rerun the live verifier, provider probes, keyring inspection, or daemon smoke. The bullets above are the reviewed Part A observations already captured in this report and the ignored Part A task report.

### Completion matrix

| Checklist line | Status | Evidence boundary |
|---|---|---|
| Three real Windows credential entries | **PASS** | `cmdkey /list` previously showed the three exact Generic target names; values were not exposed. |
| Daemon/API resolves stored credentials | **PASS** | Prior guarded verifier: three provider probes PASS; prior daemon log: one Whisper and one LLM success marker, zero failure markers. Not rerun in Task 5. |
| Missing required keys fail cleanly | **PASS** | Automated config coverage verifies the missing-key error names required keys and directs the user to Settings or `.env`; no destructive live missing-key exercise was performed. |
| Settings masked/reveal/test/save/delete/retry/cancel key UX | **PASS** | Automated Settings tests passed in the fresh targeted/full non-clipboard runs. Save/retry semantics were not repeated as a manual live edit cycle. |
| Fallback is isolated to a fake credential | **PASS** | Prior live fallback used only `fallback_test_api_key`, a known fake value, and temporary files; production entries were read-only and were never deleted. |
| Fixed usage/cost math | **PASS** | Fresh targeted proof asserts `$0.012`, `$0.000825`, and `$0.012825` exactly with Decimal arithmetic. |
| Development and excluded legacy calls do not count | **PASS** | Fresh fixture and call-site tests verify default development exclusion, explicit daily user paths, and legacy-label policy. |
| Pricing date and estimate disclaimer shown | **PASS** | Fresh Settings tests verify `2026-07-14` and `估算費用，非實際帳單，價格可能已變動`; provider billing reconciliation remains out of scope. |
| Documentation records architecture, limits, tests, and live/automated distinction | **PASS** | `KNOWN_LIMITATIONS.md` items 4/10 and this Part B section record the implemented policy, residuals, exact evidence, and non-rerun live boundary. |
| Complete suite including real Windows clipboard tests | **PASS** | Integration verification reran the complete suite without exclusions: `273 passed in 7.40s`, including the real Windows clipboard module. |

## Cross-platform short command alias (2026-07-15)

- One-time setup is separate from daily execution: Windows uses
  `scripts/setup_windows.ps1`, macOS uses `scripts/setup_mac.sh`, and both call
  the shared `python -m speedytype ... install-command` implementation.
- Windows installs `%APPDATA%\SpeedyType\bin\speedytype.bat` and adds that
  directory once to the user PATH. macOS installs executable
  `~/.local/bin/speedytype` and prints the exact shell PATH instruction when
  needed.
- Generated wrappers capture only absolute Python, repository, and default
  `.env` paths. They forward all arguments with `%*` or `"$@"`; a later
  `speedytype --env other.env <action>` overrides the installed default.
- Wrappers never contain or modify API key values. Configuration continues
  through the existing Keyring-first resolver and legacy `.env` migration.
- Automated evidence covers atomic replacement, Windows PATH preservation and
  case-insensitive deduplication, environment-change notification, Mac mode and
  PATH guidance, secret sentinels, CLI override behavior, setup-script
  contracts, PowerShell parsing, and Bash syntax.
- Windows live evidence is produced by
  `scripts/verify_command_alias_windows.ps1`, which refreshes PATH from the
  user/machine environment for new `cmd.exe` processes and exercises
  `diagnose-config`, parameter forwarding, daemon start, and daemon stop.
- Real macOS execution remains pending; [MAC_SETUP.md](MAC_SETUP.md) contains
  the target-device checklist.

### Verification evidence

- TDD RED: wrapper tests initially failed during collection because
  `speedytype.command_alias` did not exist; CLI tests then failed because
  `install_command_alias` was absent; setup contract tests failed because both
  setup scripts were absent.
- Fresh complete suite before live installation: `python -m pytest -q` →
  `289 passed in 9.09s`.
- `scripts/setup_windows.ps1` ran twice successfully. The first installed the
  wrapper and user PATH entry; the second reported that the command directory
  was already present. Registry inspection found exactly one normalized alias
  directory entry (`ALIAS_PATH_COUNT=1`).
- `scripts/verify_command_alias_windows.ps1` ran commands through fresh
  `cmd.exe` processes. `diagnose-config` printed `Config OK`,
  `guided-recording --help` displayed both parameter options, daemon PID
  `16360` was stopped successfully, and the script ended with
  `COMMAND_ALIAS_WINDOWS_OK`.
- Explicit override:
  `speedytype --env C:\WORK\Claude\poc\speedytype\.env diagnose-config`
  exited `0`, selected that file's distinct `gemini-3.1-flash-lite` model, and
  printed no credential values.
- `bash -n scripts/setup_mac.sh`, PowerShell parser checks for both Windows
  scripts, `python -m compileall -q speedytype scripts`, and
  `git diff --check` all exited `0` on Windows.
- The installed wrapper was inspected: it contains only repository, venv
  Python, and default `.env` paths followed by `%*`; it contains no API key.

## Reproducible source release (updated 2026-07-16)

- `python scripts/build_release.py` builds from an explicit allowlist into
  ignored `dist/`. Repository tests, recordings, benchmark evidence,
  development plans, caches, local settings, `.env`, and Keyring data are not
  release inputs.
- `speedytype/version.py` is the sole runtime version source. Package
  `__version__`, `speedytype --version`, the tray About dialog, and the release
  builder all resolve the same value. The CLI prints `SpeedyType 0.5.3` without
  loading configuration or credentials.
- Release output consists of the versioned source directory, matching source
  ZIP, and `SHA256SUMS.txt`.
- The release README documents automatic setup and manual venv plus
  `pip install -r requirements.txt` installation on Windows and macOS,
  Keyring-backed credential configuration, daily commands, updates,
  troubleshooting, and checksum verification.
- A fresh install can run `speedytype settings` before credentials exist. That
  command alone uses non-strict credential loading to open the existing
  Keyring-backed Settings dialog; daemon, diagnose, recording, and provider
  paths retain strict missing-key validation.

### Source release verification evidence

- Full automated suite: `python -m pytest -q` → `311 passed in 15.89s`.
- On first run, each masked API key field accepts typing and native paste before
  reveal; **Show** is only needed to inspect the entered value.
- Repeatability: `python scripts/build_release.py` completed twice and replaced
  the same versioned outputs without duplicate or stale files. Both builds
  produced the same ZIP length and SHA-256, which also matched
  `SHA256SUMS.txt`.
- Generated outputs: `dist/SpeedyType-0.5.3/`,
  `dist/SpeedyType-0.5.3-source.zip` (101,167 bytes), and
  `dist/SHA256SUMS.txt`.
- ZIP SHA-256:
  `46a22b0d746997fe8a7e5bb7e2bdb52b22a54f2a5e2c2f9c10f56e4ecd8e3ada`.
  The checksum file was parsed and independently matched against the ZIP.
- Released text uses LF line endings, ZIP entries use a fixed timestamp,
  shell scripts are stored as mode `0755`, and other files as `0644` so
  checkout metadata does not change the archive.
- Top-level release inventory was exactly `.env.example`,
  `KNOWN_LIMITATIONS.md`, `MAC_SETUP.md`, `README.md`, `pricing.json`,
  `real_voice_script.md`, `requirements.txt`, `scripts/`, and `speedytype/`.
- The `0.5.3` ZIP was extracted into a unique, guarded temporary directory.
  Before cleanup, the resolved extraction path was required to remain strictly
  beneath the system temporary root. From the
  extracted release, `python -m compileall -q speedytype`,
  `python -m speedytype --version`, package `__version__`,
  `bash -n scripts/setup_mac.sh`, and Windows PowerShell parser checks for
  `setup_windows.ps1` and `verify_command_alias_windows.ps1` all succeeded.
  CLI output was exactly `SpeedyType 0.5.3` and package output was `0.5.3`.
  The released setup and `MAC_SETUP.md` audit found all required Python 3.13
  preflight, explicit `python@3.13`, pip-upgrade, and stale-venv recovery
  guidance strings.
- Real-Mac `0.5.2` setup failed because the default `python3` created a venv
  with pip 21.2.4, then requirements installation stopped at
  `audioop-lts==0.2.2` with no matching distribution; the alias/PATH steps did
  not run. In `0.5.3`, setup now fails early when Python is older than 3.13 or
  an existing venv is incompatible, with exact `brew install python@3.13` and
  `.venv` backup/recreation guidance before dependency installation.
- The macOS `0.5.3` real-device rerun, including setup, Keychain, PATH, and
  command execution, remains pending.
