# SpeedyType Cross-Platform Core and macOS Backend Design

## Goal

Make SpeedyType runnable from source on the owner's Windows and macOS machines by fixing current defects, introducing concern-based platform boundaries, and adding macOS backends. Packaging, signing, notarization, installer work, and CI are explicitly excluded.

## Delivery Order

1. Establish the current Windows test and latency baseline.
2. Fix dependency completeness, autostart path resolution, and the missing Settings autostart control.
3. Complete or explicitly defer the Gemini prompt investigation based on API availability.
4. Measure long-recording batch and quasi-streaming behavior before changing the pipeline architecture.
5. Introduce platform abstractions while preserving Windows behavior.
6. Add macOS implementations and Windows-runnable contract tests.
7. Run Windows regression checks, document Mac-only validation, and update project reports.

## Existing-Issue Fixes

### Runtime Dependencies

`requirements.txt` will include `PyQt6`, `numpy`, `psutil`, and `platformdirs`. Windows-only packages will use `sys_platform == "win32"` markers. The macOS hotkey dependency will use a Darwin marker. Dependency verification uses a clean virtual environment followed by an import/startup smoke test; the existing developer environment is not sufficient evidence.

### Autostart Path Resolution

The Windows Startup script must not infer the project root from the autostart backend file's parent count. Source execution will derive the import root from the installed `speedytype` package location, while the interpreter and explicit environment path are resolved to absolute paths at installation time. The generated script will invoke the module without relying on its own location. Tests will install into a temporary Startup directory and assert the generated command remains valid when the checkout root changes.

### Settings Autostart Control

`SettingsDialog` will display a launch-at-login checkbox initialized from `query_autostart()`. Saving will call `install_autostart()` or `uninstall_autostart()` only when the desired state differs from the current state, and surface backend failures in the status message. Backend calls will be dependency-injected or patched at the public platform boundary in tests. A Windows manual check will verify the actual Startup script creation and deletion.

### Gemini Prompt Investigation

The existing repeated prompt script will be run until both current and candidate prompts have comparable valid sample counts, with API errors excluded rather than counted as semantic failures. The decision will consider preservation of numbers and regressions in correction, filler removal, formatting, and key terms. If quota prevents enough valid samples, item 16 remains open with the exact counts and error recorded.

### Long-Recording Evaluation

Two existing recordings will be reused:

- `speedytype_0l1h1hcx.wav`: 126.412 seconds, SHA-256 `43d0fa628eae24c370dad90c0e1d35440a26caa73aa5cd2504b779a814c77d63`
- `speedytype_6alyelny.wav`: 133.796 seconds, SHA-256 `c5f8a62b0076625b4cad8522044002cef70277965158e994419594a231c7e6e7`

Both are 16 kHz, mono, PCM16 WAV files. They will be copied into a stable project test-data directory. One additional 4-5 minute TTS recording with non-repeating technical prose will be generated and normalized to the same format.

The benchmark will run batch and existing quasi-streaming implementations on the same three files. It will record audio duration, Whisper wall time, LLM wall time, post-recording tail latency, total Whisper request time, chunk count, output, and failures. Quality checks will be case metadata-driven rather than reuse the old short/medium/long hard-coded assertions. The decision is based on latency improvement, request amplification, output completeness, and implementation complexity. A hybrid threshold is adopted only if long recordings show a material and consistent benefit without unacceptable quality loss; otherwise the batch pipeline remains unchanged.

## Platform Architecture

### Public Boundaries

Create `speedytype/platform/` with public modules by concern:

- `clipboard.py`: snapshot and restore contracts, plus platform paste shortcut dispatch.
- `hotkey.py`: register/remove hold hotkeys, wait for release, and capture a shortcut.
- `process.py`: process existence and termination via `psutil`.
- `autostart.py`: install, uninstall, and query launch-at-login state.

Each public module selects a private implementation using `sys.platform`. Unsupported platforms fail with a clear `RuntimeError` when the capability is used, not through accidental import errors. Existing imports will be migrated to these public boundaries.

### Paths

`speedytype/paths.py` will use `platformdirs.user_data_path("SpeedyType")` as the base for default `.env`, settings, PID, daemon log, and latency log paths. Explicit CLI or function parameters continue to override defaults. Parent directories are created only when a write is required, avoiding import-time filesystem side effects.

### Windows Behavior

Clipboard format snapshot/restore and keyboard semantics move to private Windows modules without intentional behavior changes. Process checks and termination switch from `tasklist`/`taskkill` to `psutil`. Restart subprocess flags remain Windows-specific behind a process helper so importing daemon code on macOS is safe.

### OS-Neutral Hotkey Model

Stored shortcuts use canonical lowercase tokens such as `ctrl`, `alt`, `shift`, `cmd`, `space`, letters, digits, and `f1`-`f24`. Legacy `win` values are normalized to `cmd` as the OS-neutral primary-command token, displayed and executed as Win on Windows and Command on macOS. Parsing rejects duplicate tokens and shortcuts lacking a modifier unless they are a single function key. Display names and backend key objects are platform-specific.

### macOS Clipboard

The macOS implementation snapshots and restores text only through `pyperclip`. Non-text pasteboard formats are intentionally not preserved. Cmd+V is sent through the macOS hotkey controller. This limitation will be recorded in `KNOWN_LIMITATIONS.md`.

### macOS Hotkeys and Permissions

The pynput backend maintains a pressed-key set. A recording press callback fires once when every configured key becomes held; release completion occurs as soon as any configured key is released. Shortcut capture uses a short-lived listener and finalizes the chord on the first release after at least one key was pressed.

Listener startup and callback failures associated with Accessibility or Input Monitoring permissions are converted to a platform permission error. The Settings/daemon UI displays concrete System Settings navigation instructions. The application does not attempt to grant permissions programmatically.

### macOS Autostart

The backend writes `~/Library/LaunchAgents/com.speedytype.daemon.plist` with an absolute interpreter, module arguments, environment path, log paths, and `RunAtLoad`. Installation and removal use the supported `launchctl bootstrap`/`bootout` form for the current GUI user domain, with a compatibility fallback only when command output demonstrates the newer form is unavailable. XML is generated with `plistlib`, not string concatenation.

### Reserved Shortcuts

Reserved shortcut warnings are selected per platform. macOS includes Spotlight, application switching, force quit, screenshots, lock screen, and common system navigation combinations. Warnings do not block saving because third-party remapping and user preferences can change availability.

## Testing and Evidence

Every behavior change follows red-green-refactor. Platform contracts and dispatch are tested without importing unavailable OS libraries. Windows clipboard integration tests are skipped before Windows-only imports on non-Windows systems.

Windows evidence includes:

- Clean-environment dependency installation and startup/import smoke test.
- Full pytest count compared with the pre-change baseline of 59 passing tests.
- Real Startup folder install/query/uninstall cycle.
- Daemon PID/process behavior and restart smoke check.
- Tray and Settings dialog manual check.
- Existing full-paste latency benchmark compared with the approximately 3.5-second historical level.
- Long-recording benchmark raw results and decision summary.

Mac-only acceptance remains unverified until performed on real hardware. The handoff checklist will specify hotkey hold/release recording, timeout, Cmd+V paste and clipboard restoration, shortcut capture, denied-permission guidance, LaunchAgent install/query/removal and logout/login persistence, tray/settings behavior, and overlay click-through/always-on-top behavior across Spaces and Mission Control.

## Documentation

`KNOWN_LIMITATIONS.md` will record the text-only macOS clipboard behavior, exact real-Mac verification backlog, prompt-test status, and long-recording conclusion. `POC_REPORT.md` will separate code completion, Windows verification, external API evidence, and pending macOS hardware evidence. `CROSS_PLATFORM_PLAN.md` will retain future packaging and CI phases as references but mark them excluded from this delivery.

## Explicit Exclusions

This work will not create or modify packaging manifests, PyInstaller specifications, Inno Setup scripts, DMG tooling, icons for distribution, signing/notarization configuration, Apple Developer Program decisions, or CI matrices. No preparatory work for those phases is included.
