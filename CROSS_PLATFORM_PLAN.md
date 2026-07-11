# SpeedyType: Cross-Platform (Windows + macOS) Port and Installer Packaging Plan

Status: **planned, not started**. No Phase 1-4 implementation work below has been approved or begun yet — this document exists so the plan survives beyond any single session. Approval for Phase 1 (or any phase) should be sought explicitly before starting code changes against this plan.

## Context

SpeedyType has been built and validated exclusively on Windows across 8 phases (Whisper/LLM pipeline, background daemon, PyQt6 tray + overlay + Settings/About UI, autostart, clipboard protection, combo hotkeys, mic device selection — see `POC_REPORT.md`). The goal of this plan is to (1) make it run on macOS as well as Windows, and (2) ship it as a real installable package on both, instead of "clone the repo, `pip install`, run from source."

Two independent codebase audits plus a design-validation pass (all via sub-agent research, not guesswork) confirmed this is a substantial, multi-part rewrite, not a config tweak: five core modules have hard Windows-only dependencies (`win32clipboard`, the `keyboard` hotkey library with no macOS backend at all, Windows-only process commands, a Windows-only autostart mechanism, and Windows subprocess flags), and there is currently zero packaging infrastructure (no `pyproject.toml`, no icons, `requirements.txt` is missing `PyQt6`/`numpy` outright, and every stateful file defaults to a bare CWD-relative path).

**Constraint worth stating plainly**: the Claude Code environment used to write this plan has no macOS machine — none of the macOS-specific code below can be executed or verified from that environment directly. The user confirmed they have access to a real Mac, so Phase 2/3's macOS work should be written correctly per documented library behavior (pynput, pyobjc/AppKit conventions, `launchctl`), then handed off for the user to actually run and validate on their Mac — this plan is explicit throughout about which pieces are Windows-verifiable in a dev environment now versus which need that real-Mac validation step, rather than claiming false confidence.

**Open question, not yet answered**: whether to budget $99/yr for an Apple Developer Program membership for code-signing + notarization on macOS. This plan's default is an **unsigned macOS build for now** (documented Gatekeeper bypass step for early use), on the assumption that's the lower-cost starting point and is easy to revisit later without redoing other work. Confirm or override this before/during Phase 3.

## Recommended Approach

Four phases, each with a clear exit criterion, so work can be checkpointed rather than attempted as one giant change.

### Phase 1 — Platform abstraction layer + plumbing fixes (Windows-only behavior change; fully verifiable in a Windows dev environment)

Goal: restructure the codebase so OS-specific code lives behind small interfaces, without changing any actual behavior on Windows. This de-risks the big rewrite before touching anything unverifiable.

- New `speedytype/platform/` package, one module per **concern** (not per OS): `clipboard.py`, `hotkey.py`, `process.py`, `autostart.py`. Each is a thin public interface that dispatches at import time (via `sys.platform`) to a private `_windows.py` sibling (macOS siblings added in Phase 2). Move existing logic verbatim:
  - `speedytype/clipboard.py`'s `win32clipboard`-based `snapshot_clipboard`/`restore_clipboard`/`_open_clipboard` → `platform/_windows_clipboard.py` (keep `pyperclip`-based `paste_text`/`paste_text_preserving_clipboard` in `clipboard.py` itself, calling into the new interface for snapshot/restore only).
  - `speedytype/hotkey.py`'s `keyboard.is_pressed`-based `wait_until_hotkey_released` → stays using the `keyboard` library on Windows (see below — **not migrating Windows off `keyboard`**), just re-homed behind the new interface.
  - `speedytype/daemon.py`'s `_is_pid_running()`/`stop_daemon()` (currently `tasklist`/`taskkill` shell-outs) → replaced with **`psutil`** (`psutil.pid_exists()`, `psutil.Process(pid).terminate()`), used on **both** OSes as a single dependency — this is a simplification, not a Windows/macOS duplication. Wrap in `try/except (psutil.NoSuchProcess, psutil.AccessDenied)`.
  - `speedytype/autostart.py`'s Startup-folder `.bat` logic → `platform/_windows_autostart.py`. Fix the existing bug where `project_dir = Path(__file__).resolve().parents[1]` hardcodes the dev checkout location — must resolve correctly from a packaged/frozen install location too (relevant for `--onedir` PyInstaller builds in Phase 3).
- **Explicit non-migration**: keep the `keyboard` library for the Windows hotkey backend as-is. It's proven working with a real user (verified live with `ctrl+alt+space` in Phase 6). pynput is added *only* for macOS in Phase 2, accepting two parallel implementations of the same hold/release semantic (start on all-combo-keys-down, end on any-combo-key-up) rather than risking a Windows regression for zero benefit.
- New `speedytype/paths.py` using the **`platformdirs`** package: `app_data_dir()` → `%APPDATA%\SpeedyType` (Windows) / `~/Library/Application Support/SpeedyType` (macOS). Change the *default* values of `.env`, `settings.json` (`speedytype/settings.py`'s `SETTINGS_FILE_NAME`), `speedytype_daemon.pid`/`.log` (`speedytype/daemon.py`), and `speedytype_latency_log.csv` (`speedytype/config.py`) to live there. Keep existing `--env`/explicit-path parameters as overrides — no loss of dev/test flexibility.
- **New: "啟動時自動執行" (launch at login) checkbox in `SettingsDialog`**, wired to `install_autostart`/`uninstall_autostart`/`query_autostart`. This closes a real, pre-existing gap found during validation: autostart is *currently CLI-only* (`install-autostart`/`uninstall-autostart` subcommands), with zero UI entry point — once Phase 3 packaging drops the dev CLI surface from the shipped binary, there would be no way for an end user to enable it at all. This item is Windows-relevant today, independent of the macOS work.
- Fix `requirements.txt`: add `PyQt6` and `numpy` (both are hard runtime deps, confirmed **currently missing entirely** — `pip install -r requirements.txt` today does not produce a working app), add `psutil` and `platformdirs`. Mark `pywin32`/`pywinauto` Windows-only via environment markers (`pywin32==312; sys_platform == "win32"`).
- `tests/test_clipboard.py` currently imports `win32clipboard`/`win32con` at module level and drives the real Windows clipboard — mark it `@pytest.mark.skipif(sys.platform != "win32", ...)` so a future macOS CI run doesn't fail at collection time.
- **Exit criterion**: full existing test suite passes unchanged on Windows (`python -m pytest -q`); daemon/tray/Settings/autostart all manually re-verified working exactly as before (regression check, not new functionality) — the deliverable of this phase is invisible to a Windows user except the new "launch at login" checkbox and files now living in `%APPDATA%\SpeedyType` instead of the project directory.

### Phase 2 — macOS backends (written correctly per documented behavior; needs the user's real Mac to verify)

- `platform/_macos_clipboard.py`: `pyperclip`-only, **text-only** snapshot/restore (no full multi-format `NSPasteboard` port). This is a deliberate, documented scope cut — Phase 5's original clipboard-protection testing was against text content (code snippets, links) so text-only parity is an acceptable v1 given the real cost of a `pyobjc-framework-Cocoa`-based full pasteboard reimplementation. Record this explicitly in `KNOWN_LIMITATIONS.md` once implemented.
- `platform/_macos_hotkey.py`: **`pynput`**-based hold/release tracker. `pynput.keyboard.Listener`'s `on_press`/`on_release` callbacks maintain a currently-held-keys set; "start" fires when all of the configured combo's keys are present, "release" fires the instant any one leaves — reproducing the exact semantic already verified on Windows. `pynput.keyboard.Controller` sends `Cmd+V` for paste. `keyboard.read_hotkey()` (used by the Settings dialog's hotkey-capture UI) has **no pynput equivalent** — needs a hand-rolled capture routine (short-lived `Listener` that finalizes on first release) as genuinely new code, not a drop-in swap. Needs an explicit combo-token mapping table (`"windows"/"win"` → `pynput.keyboard.Key.cmd`, since macOS has no Windows key) — recommend OS-neutral storage in `settings.json`, normalized for display/lookup per OS, to keep the file portable if a user ever moves it between machines.
- `platform/_macos_autostart.py`: `~/Library/LaunchAgents/com.speedytype.daemon.plist` (XML, `ProgramArguments` + `RunAtLoad`), registered/unregistered via `launchctl load`/`bootstrap` and `unload`/`bootout`.
- `speedytype/settings_dialog.py`'s `KNOWN_RESERVED_SHORTCUTS` (currently Windows-only: `win+l`, `ctrl+shift+esc`, etc.) needs a parallel macOS list (`cmd+space` Spotlight, `cmd+tab`, `cmd+shift+3/4` screenshot, etc.) — these don't translate, they need to be authored separately per OS.
- First-run **Accessibility / Input Monitoring permission** dialog: attempt hotkey listener setup, catch the failure pynput raises when permission is missing, show instructions to grant it in System Settings. This can't be granted programmatically. Note: rebuilding/re-signing the `.app` during development is known to cause macOS to silently revoke or fail to re-prompt for this permission — accepted dev friction, not a bug to chase.
- **Needs the user's Mac to verify**: all of the above end-to-end; the LaunchAgent surviving reboot/logout; and whether `speedytype/overlay.py`'s `Qt.WindowType.Tool | WindowStaysOnTopHint` + `WA_TransparentForMouseEvents` combination (verified working on Windows for the floating overlay pill's always-on-top/click-through behavior) behaves the same under macOS's window manager/Spaces/Mission Control — a real unknown, not an assumed-portable Qt behavior. Hand-off point: implement the `_macos_*.py` backends, then the user runs the daemon on their Mac and reports back (mirroring how live-voice/hotkey testing was done on Windows throughout Phases 5-8).
- **Can verify on Windows alone**: the abstraction layer still dispatches correctly to the Windows backends (no regression), and the combo-token mapping table's logic is internally consistent (unit-testable against fake/mock backends without needing real macOS APIs).

### Phase 3 — Packaging (Windows fully buildable/testable in a Windows dev environment; macOS build needs real hardware, signing needs a paid Apple account)

- New `pyproject.toml` with `sys_platform`-conditional dependency groups.
- New icon assets (`.ico` for Windows, `.icns` for macOS) — none exist today (the current tray/dialog icon is generated at runtime via `QPainter`, `speedytype/icon.py`); need a real base image designed and converted to both formats.
- **PyInstaller**, `--onedir` (not `--onefile` — onefile re-extracts to a temp dir on every launch, bad for an autostart-launched background daemon, and complicates the `Path(__file__)`-relative autostart logic from Phase 1), `--windowed`, one spec file per OS.
  - Known gotcha to budget explicit verification time for: `sounddevice`/`soundfile` bundle native shared libraries (PortAudio/libsndfile) that PyInstaller's hook discovery frequently misses — likely needs `--collect-all sounddevice --collect-all soundfile` or a custom hook, verified by actually running the packaged binary, not assumed from a clean build log.
  - Verify PyQt6's platform plugin (`qwindows.dll` / `libqcocoa.dylib`) is actually bundled per OS — a missing one produces an opaque "could not find the Qt platform plugin" crash.
- New thin entry-point script that calls `run_daemon()` directly (bypassing the full `argparse` CLI surface) as the packaged binary's target; the ~11 developer/diagnostic subcommands (`listen`, `run-once`, `diagnose-*`, `guided-recording`, `validate-real-voice`, etc.) stay source-only, not bundled into the shipped installer.
- **Windows installer**: Inno Setup (free, scriptable, can register Start Menu entries + uninstaller) wrapping the PyInstaller `--onedir` output — fully buildable and testable in a Windows dev environment.
- **macOS installer**: `.dmg` via `dmgbuild`/`create-dmg` wrapping the `.app`. Signing/notarization (Developer ID Application certificate, `xcrun notarytool submit`, `xcrun stapler staple`) requires a paid Apple Developer Program membership ($99/yr) and real macOS hardware — **out of scope for the first pass per the default above**; ship unsigned and document the Gatekeeper bypass (`xattr -cr` or right-click → Open) for early users. Revisit later; doesn't require redoing other Phase 3 work.
- Also worth budgeting: unsigned Windows `.exe`s from PyInstaller are frequently flagged by Defender/SmartScreen (packer heuristic false-positive) — a Windows code-signing certificate is a separate, smaller cost if a clean first-run matters there too.

### Phase 4 — CI (GitHub Actions matrix, supplementary given the user's Mac covers manual validation)

- `windows-latest` + `macos-latest` runners building both installers on push/tag, as a repeatable-build safety net alongside (not instead of) manual Mac testing in Phases 2-3. The Windows leg is fully actionable immediately; the macOS leg can at least do an unsigned build+smoke-test without any paid credentials, and gains signing once/if that's set up as CI secrets later.

## Critical Files

- `speedytype/clipboard.py`, `speedytype/hotkey.py`, `speedytype/daemon.py`, `speedytype/autostart.py` — the four modules being split into `platform/` interfaces.
- `speedytype/settings.py`, `speedytype/settings_dialog.py` — hotkey combo storage/validation and capture UI, needs the OS-neutral token mapping.
- `speedytype/config.py`, `speedytype/paths.py` (new) — default path resolution.
- `requirements.txt`, `pyproject.toml` (new) — dependency correctness and packaging manifest.
- `tests/test_clipboard.py`, `tests/test_hotkey.py`, `tests/test_daemon_pid.py` — need to keep passing through the Phase 1 refactor; `test_clipboard.py` needs the Windows-only skip guard.
- `KNOWN_LIMITATIONS.md` — record the macOS text-only clipboard scope cut, the unsigned-macOS-build decision, and the unverified-without-real-hardware caveat for Phase 2/3 macOS work as each is implemented.

## Verification

- **Phase 1**: `python -m pytest -q` must still show the same pass count as before this phase on Windows; manually re-run the daemon/tray/Settings dialog/autostart install-uninstall cycle exactly as done in Phases 5-8 (real process checks via `psutil` instead of `tasklist`/`taskkill`, real file locations now under `%APPDATA%\SpeedyType`) to confirm zero behavior change beyond the new file locations and the new login-checkbox.
- **Phase 2**: unit tests against fake/mock platform backends run and pass on Windows (verifying the abstraction's contract, not real macOS behavior). The actual macOS backends need a real run-through on the user's Mac: hold-hotkey-to-record, release-to-stop, Cmd+V paste, Settings dialog hotkey capture, LaunchAgent install survives a logout/login cycle, and a live check of the floating overlay's click-through/always-on-top behavior.
- **Phase 3**: Windows — build the Inno Setup installer, install it on a clean-ish Windows profile (or VM) and confirm the daemon launches, tray icon appears, hotkey works, autostart survives a real reboot. macOS — build the `.dmg`, confirm it mounts and the `.app` launches on the user's Mac (accepting the unsigned-Gatekeeper-bypass step), same functional checklist as Windows.
- **Phase 4**: CI matrix green on both OSes; artifacts (installer/dmg) downloadable from the Actions run.

## Related documents

- `POC_REPORT.md` — full history of Phases 1-8 that produced the current Windows-only implementation this plan is porting.
- `KNOWN_LIMITATIONS.md` — accumulated known limitations and resolved-issue history; items 13-16 are the most recent (Phase 8 and the subsequent LLM-repetition investigation).
