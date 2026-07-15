# Source Release Bundle Design

## Goal

Create a reproducible, clearly separated SpeedyType source release that
contains only runtime and end-user installation material. The release must be
usable on Windows and macOS, explain both automatic and manual dependency
installation, and exclude the repository's tests, research evidence, local
environments, secrets, caches, and generated data.

## Release Boundary

The repository remains the development tree. Existing benchmark recordings,
phase reports, JSONL/CSV evidence, test corpora, and historical research files
will not be moved in this change because many reports refer to their current
paths. Instead, a strict allowlist defines the release boundary.

Generated output lives under ignored `dist/`:

```text
dist/
├── SpeedyType-0.5.0/
│   ├── speedytype/
│   ├── scripts/
│   │   ├── setup_windows.ps1
│   │   ├── setup_mac.sh
│   │   └── verify_command_alias_windows.ps1
│   ├── README.md
│   ├── MAC_SETUP.md
│   ├── KNOWN_LIMITATIONS.md
│   ├── requirements.txt
│   ├── pricing.json
│   ├── .env.example
│   └── real_voice_script.md
├── SpeedyType-0.5.0-source.zip
└── SHA256SUMS.txt
```

The version is loaded from `speedytype/version.py`; it is not duplicated in
the builder. The folder name and archive name use the same version.

## Builder

Add `scripts/build_release.py` as the single release entry point. It will:

1. Resolve the repository root from its own location.
2. Load `VERSION` without importing the complete application dependency graph.
3. Create a unique staging directory beneath `dist/`.
4. Copy only the explicit allowlist.
5. Recursively copy the `speedytype` package while rejecting `__pycache__`,
   `.pyc`, and other generated files.
6. Copy the tracked `release/README.md` template to `README.md` inside the
   bundle.
7. Transactionally replace the versioned release directory after staging
   succeeds: rename an old target to a sibling backup, rename staging to the
   target, restore the backup on failure, then remove the backup on success.
8. Create `SpeedyType-<version>-source.zip` through a unique sibling temporary
   archive followed by atomic file replacement.
9. Write `SHA256SUMS.txt` through a unique sibling temporary file followed by
   atomic file replacement.

The builder may remove only a resolved target within the repository's `dist/`
directory. A path-containment guard must reject any unexpected target before a
recursive remove or replace.

Repeated builds remove stale files from the versioned output because every
bundle is assembled from a fresh staging directory. A failed staging or target
swap removes its temporary files and restores the last completed release
directory. Archive and checksum replacements preserve their previous completed
files until the new bytes are ready.

## Included and Excluded Content

The allowlist includes:

- `speedytype/**/*.py`
- `scripts/setup_windows.ps1`
- `scripts/setup_mac.sh`
- `scripts/verify_command_alias_windows.ps1`
- `requirements.txt`
- `pricing.json`
- `.env.example`
- `real_voice_script.md`
- `MAC_SETUP.md`
- `KNOWN_LIMITATIONS.md`
- `release/README.md` as bundle `README.md`

It excludes everything not named above, including:

- `.env`, `settings.json`, OS Keyring data, daemon PID/log files, and latency
  logs
- `.git`, `.claude`, `.worktrees`, `.venv`, `.venv-clean`, and pytest/Python
  caches
- `tests/`, test audio directories, recorded real-voice directories, WAV
  files, JSONL/CSV benchmark results, phase reports, and development plans
- arbitrary files added to the repository later unless the release manifest is
  deliberately updated and reviewed

The secret-safety test uses sentinel values and scans every released text file.
It does not read or inspect the real OS Keyring.

## Fresh-Install Settings Command

A clean installation has no API keys in Keyring, but the existing daemon loads
and validates credentials before it exposes the tray Settings action. The
release therefore adds `speedytype settings` as a bootstrap-safe entry point.

`load_config()` gains a keyword-only `require_api_keys: bool = True` option.
Its default preserves every existing daemon, diagnose, recording, and API path:
missing OpenAI or Gemini credentials still raise `ConfigError`. The settings
launcher alone passes `require_api_keys=False`; it receives the same `AppConfig`
with missing credential fields represented as empty strings. Keyring lookup,
process-environment lookup, legacy `.env` fallback/migration, settings parsing,
and non-secret defaults remain the same in both modes.

Add `speedytype/settings_launcher.py` with:

```python
def show_settings_dialog(env_path: str | Path | None = None) -> int:
    """Open Settings without requiring credentials and return a CLI exit code."""
```

The launcher creates or reuses `QApplication`, constructs the existing
`SettingsDialog` with the non-strict config and selected `.env` path, executes
it modally, and returns `0` after the dialog closes. Saving continues through
the existing Keyring-backed Settings implementation; Cancel continues to write
nothing. No second credential store or settings model is introduced.

The CLI adds a `settings` subcommand that forwards the globally selected
`--env` path to this launcher. It does not weaken `diagnose-config`, `daemon`,
or any command that performs recording/provider work.

## README Content

The release README begins with prerequisites and a two-path installation guide.

Windows automatic setup:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_windows.ps1
```

Windows manual setup:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m speedytype install-command
```

macOS automatic setup:

```sh
./scripts/setup_mac.sh
```

macOS manual setup:

```sh
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m speedytype install-command
```

The README also covers:

- opening a new terminal after command installation
- first-run `speedytype settings`, followed by `diagnose-config` and daemon
  startup after credentials are saved
- API key storage in Windows Credential Manager or macOS Keychain through the
  existing Keyring implementation
- the fact that `.env` is for configuration and legacy credential migration,
  not the preferred place for new API keys
- `diagnose-config`, `daemon`, `daemon-stop`, `guided-recording`, and explicit
  `--env` override examples
- Windows PATH troubleshooting, macOS PATH and privacy permissions, update by
  rerunning setup, and the real-Mac verification boundary
- source archive checksum verification

The repository root receives a short developer-facing `README.md` that labels
the checkout as a development tree, explains the research/test clutter, gives
the build command, and points users to the generated release README.

## Documentation Updates

- Mark all 34 implementation steps in
  `docs/superpowers/plans/2026-07-15-command-alias.md` complete. Real Mac
  runtime verification remains explicitly pending in `MAC_SETUP.md` and
  `KNOWN_LIMITATIONS.md`; checking the implementation-plan steps does not claim
  that hardware evidence exists.
- Update `POC_REPORT.md` with the release boundary, exact builder verification,
  and generated artifact names.
- Add `dist/` to `.gitignore` so release output stays reproducible instead of
  becoming another mixed set of tracked artifacts.

## Verification

Automated tests will build into a temporary output root and verify:

- the versioned folder, ZIP, and checksum file names
- the exact top-level allowlist and selected scripts
- package recursion includes Python source while excluding caches/bytecode
- no excluded test, recording, benchmark, development-plan, `.env`, or local
  settings file enters the bundle
- no API key sentinel appears in released text
- the ZIP member set and file bytes match the generated directory
- `SHA256SUMS.txt` matches the archive bytes
- a second build removes an injected stale file
- a failed staging build preserves a previous completed release
- the release README contains automatic setup, manual venv creation,
  `pip install -r requirements.txt`, Keyring guidance, and daily command examples
- strict config loading still rejects missing required keys while the settings
  loader accepts empty keys without bypassing the normal resolver
- the `settings` CLI forwards an explicit `--env` path and opens the existing
  dialog without starting the daemon

Final release verification will run the full pytest suite, build the real
release, extract the ZIP into a temporary directory, compile the released
Python sources, invoke `python -m speedytype --help` using the prepared project
environment, parse both PowerShell scripts, run `bash -n` on the macOS setup
script, validate the checksum, and inspect the bundle inventory.

## Acceptance Criteria

- `python scripts/build_release.py` produces one clean versioned directory, one
  matching source ZIP, and one valid SHA-256 checksum file under `dist/`.
- The release contains every file needed by the current source-based Windows
  and macOS setup flows and no development/test/research material.
- The release README gives automatic and manual installation instructions,
  including `pip install -r requirements.txt`, plus configuration, Keyring,
  usage, update, troubleshooting, and checksum guidance.
- A clean installation can run `speedytype settings` before credentials exist;
  all operational commands retain strict missing-key validation.
- Rebuilding is safe and idempotent, and an interrupted/failed staging build
  does not damage the last completed artifact.
- Existing repository references remain valid because historical files are not
  moved.
