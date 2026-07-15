# Reproducible Source Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a clean, reproducible, versioned SpeedyType source bundle and ZIP with complete Windows/macOS installation and usage documentation.

**Architecture:** A bootstrap-safe `settings` CLI opens the existing Keyring-backed dialog through a non-strict config load while every operational command retains strict credential validation. A standalone standard-library builder uses a strict source-to-destination manifest, a fresh staging directory, guarded transactional directory replacement, atomic ZIP/checksum replacement, and no application imports beyond reading `version.py` with `runpy`. A tracked release README is copied into the bundle while a separate root README explains the development tree and build command.

**Tech Stack:** Python 3.13 standard library (`argparse`, `dataclasses`, `hashlib`, `pathlib`, `runpy`, `shutil`, `tempfile`, `zipfile`), pytest, PowerShell parser, Bash syntax check.

## Global Constraints

- Release output must live under ignored `dist/` and must not be committed.
- The builder must copy only an explicit allowlist; unknown future repository files are excluded by default.
- No `.env`, settings, credential value, Keyring data, test/research artifact, venv, cache, Git metadata, or development plan may enter the release.
- The released README must document automatic setup and manual venv plus `pip install -r requirements.txt` setup for both Windows and macOS.
- Existing historical files remain in place so report links do not break.
- Versioned names come only from `speedytype/version.py`.
- A failed staging/swap operation must preserve the last completed release; ZIP and checksum files change only after new bytes are complete.
- Only `speedytype settings` may load configuration without required API keys; daemon, diagnose, recording, and provider commands remain strict.

---

### Task 1: Bootstrap-safe Settings command

**Files:**
- Modify: `speedytype/config.py`
- Create: `speedytype/settings_launcher.py`
- Modify: `speedytype/cli.py`
- Modify: `tests/test_config.py`
- Create: `tests/test_settings_launcher.py`

**Interfaces:**
- Produces: `load_config(..., *, require_api_keys: bool = True) -> AppConfig`.
- Produces: `show_settings_dialog(env_path: str | Path | None = None) -> int`.
- Produces: `speedytype [--env PATH] settings`.

- [ ] **Step 1: Write failing strict/non-strict config tests**

Append to `tests/test_config.py`:

```python
def test_settings_config_allows_missing_required_keys(tmp_path):
    config = load_config(
        tmp_path / ".env",
        settings_path=tmp_path / "settings.json",
        require_api_keys=False,
    )
    assert config.openai_api_key == ""
    assert config.gemini_api_key == ""


def test_operational_config_still_rejects_missing_required_keys(tmp_path):
    with pytest.raises(ConfigError, match="OPENAI_API_KEY, GEMINI_API_KEY"):
        load_config(tmp_path / ".env", settings_path=tmp_path / "settings.json")
```

- [ ] **Step 2: Run config tests and verify RED**

Run: `python -m pytest tests/test_config.py::test_settings_config_allows_missing_required_keys tests/test_config.py::test_operational_config_still_rejects_missing_required_keys -q`

Expected: the settings test fails because `load_config()` does not accept `require_api_keys`; the operational test passes under the existing strict behavior.

- [ ] **Step 3: Implement the opt-in non-strict config load**

Change the signature and missing-key check in `speedytype/config.py`:

```python
def load_config(
    path: str | Path | None = None,
    settings_path: str | Path | None = None,
    *,
    require_api_keys: bool = True,
) -> AppConfig:
```

```python
missing = [
    name
    for name, value in (
        ("OPENAI_API_KEY", openai_api_key),
        ("GEMINI_API_KEY", gemini_api_key),
    )
    if not value
]
if missing and require_api_keys:
    raise ConfigError(
        "Missing required configuration: "
        + ", ".join(missing)
        + ". 請從 SpeedyType 設定頁面新增金鑰，或在 keyring 不可用時於 .env 提供備援值："
        + f"{env_path.resolve()}."
    )
```

Run the two named tests again; expected: both pass.

- [ ] **Step 4: Write failing launcher and CLI tests**

Create `tests/test_settings_launcher.py`:

```python
from pathlib import Path

import speedytype.cli as cli
import speedytype.settings_launcher as launcher


def test_settings_launcher_uses_non_strict_config_and_selected_env(monkeypatch, tmp_path):
    calls = []
    config = object()
    env_path = tmp_path / "config.env"

    monkeypatch.setattr(
        launcher,
        "load_config",
        lambda path, require_api_keys: calls.append((path, require_api_keys)) or config,
    )

    class FakeApplication:
        @staticmethod
        def instance():
            return object()

    class FakeDialog:
        def __init__(self, actual_config, actual_env, settings_path):
            calls.append((actual_config, actual_env, settings_path))

        def exec(self):
            calls.append("exec")

    monkeypatch.setattr(launcher, "QApplication", FakeApplication)
    monkeypatch.setattr(launcher, "SettingsDialog", FakeDialog)

    assert launcher.show_settings_dialog(env_path) == 0
    assert calls == [
        (env_path, False),
        (config, env_path, None),
        "exec",
    ]


def test_settings_cli_forwards_explicit_env(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        cli,
        "show_settings_dialog",
        lambda env_path: calls.append(env_path) or 0,
    )
    env_path = tmp_path / "selected.env"

    result = cli.main(["--env", str(env_path), "settings"])

    assert result == 0
    assert calls == [str(env_path)]
```

Run: `python -m pytest tests/test_settings_launcher.py -q`

Expected: collection fails because `speedytype.settings_launcher` does not exist.

- [ ] **Step 5: Implement the launcher and CLI command, verify, and commit**

Create `speedytype/settings_launcher.py`:

```python
from __future__ import annotations

from pathlib import Path
import sys

from PyQt6.QtWidgets import QApplication

from speedytype.config import load_config
from speedytype.settings_dialog import SettingsDialog


def show_settings_dialog(env_path: str | Path | None = None) -> int:
    config = load_config(env_path, require_api_keys=False)
    application = QApplication.instance()
    if application is None:
        application = QApplication(sys.argv)
    dialog = SettingsDialog(config, env_path, None)
    dialog.exec()
    return 0
```

Modify `speedytype/cli.py`:

```python
from speedytype.settings_launcher import show_settings_dialog


def command_settings(args: argparse.Namespace) -> int:
    return show_settings_dialog(args.env)
```

Add to `build_parser()`:

```python
settings_command = sub.add_parser("settings")
settings_command.set_defaults(func=command_settings)
```

Run:

```powershell
python -m pytest tests/test_config.py tests/test_settings_launcher.py tests/test_settings_dialog.py -q
git diff --check
```

Expected: all tests pass and strict missing-key behavior remains covered. Then commit:

```powershell
git add speedytype/config.py speedytype/settings_launcher.py speedytype/cli.py tests/test_config.py tests/test_settings_launcher.py
git commit -m "feat: open settings before credentials exist"
```

---

### Task 2: Release and repository README contracts

**Files:**
- Create: `release/README.md`
- Create: `README.md`
- Create: `tests/test_release_docs.py`

**Interfaces:**
- Produces: `release/README.md`, copied by Task 3 to bundle `README.md`.
- Produces: root `README.md`, which labels the checkout as a development tree and documents `python scripts/build_release.py`.

- [ ] **Step 1: Write the failing documentation contract tests**

Create `tests/test_release_docs.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_release_readme_documents_automatic_and_manual_installation():
    content = (ROOT / "release" / "README.md").read_text(encoding="utf-8")
    required = (
        "scripts/setup_windows.ps1",
        "scripts/setup_mac.sh",
        "py -3.13 -m venv .venv",
        "python3 -m venv .venv",
        "pip install -r requirements.txt",
        "speedytype install-command",
    )
    for text in required:
        assert text in content


def test_release_readme_documents_keyring_usage_and_daily_commands():
    content = (ROOT / "release" / "README.md").read_text(encoding="utf-8")
    required = (
        "Windows Credential Manager",
        "macOS Keychain",
        "speedytype settings",
        "speedytype diagnose-config",
        "speedytype daemon",
        "speedytype daemon-stop",
        "speedytype guided-recording --script real_voice_script.md",
        "speedytype --env other.env daemon",
        "SHA256SUMS.txt",
    )
    for text in required:
        assert text in content


def test_root_readme_distinguishes_development_tree_from_release():
    content = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "development tree" in content.lower()
    assert "python scripts/build_release.py" in content
    assert "dist/SpeedyType-" in content
    assert "tests" in content
    assert "benchmark" in content
```

- [ ] **Step 2: Run the documentation tests and verify RED**

Run: `python -m pytest tests/test_release_docs.py -q`

Expected: file-not-found failures for `release/README.md` and root `README.md`.

- [ ] **Step 3: Create the release README**

Create `release/README.md` with these sections and commands:

```markdown
# SpeedyType Source Release

SpeedyType is a local Windows/macOS voice-input daemon. It records from a
configurable hotkey, transcribes speech, optionally polishes text, and pastes
the result into the active application.

## Prerequisites

- Python 3.13 (64-bit recommended)
- A working microphone
- Windows 10/11 or a supported macOS version
- OpenAI plus the selected LLM provider credentials

## Automatic setup

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_windows.ps1
```

macOS:

```sh
./scripts/setup_mac.sh
```

Both scripts create/reuse `.venv`, run `pip install -r requirements.txt`, and
install the short `speedytype` command. Open a new terminal afterward.

## Manual setup

Windows:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m speedytype install-command
```

macOS:

```sh
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m speedytype install-command
```

## Credentials and first start

Run `speedytype settings` and save provider keys before starting the daemon.
Keys are stored by Keyring in Windows Credential Manager or macOS Keychain. Do
not put new keys in `.env`; file keys exist only for legacy fallback/migration.
Use `.env.example` for non-secret configuration reference. Then run
`speedytype diagnose-config` followed by `speedytype daemon`.

## Daily commands

```text
speedytype diagnose-config
speedytype daemon
speedytype daemon-stop
speedytype guided-recording --script real_voice_script.md
speedytype --env other.env daemon
```

Rerun the platform setup script after replacing files with a newer release.

## Troubleshooting

- Windows: open a new terminal if `speedytype` is not found; rerun setup to
  refresh the user PATH entry.
- macOS: add `export PATH="$HOME/.local/bin:$PATH"` to `~/.zshrc` or
  `~/.bash_profile` when setup requests it. Grant Accessibility and Input
  Monitoring permissions to the selected Python executable.
- Run `speedytype diagnose-config` before starting the daemon.
- Real macOS runtime verification remains required; see `MAC_SETUP.md`.

## Verify the archive

Compare the downloaded ZIP SHA-256 with `SHA256SUMS.txt` using
`Get-FileHash SpeedyType-0.5.0-source.zip -Algorithm SHA256` on Windows or
`shasum -a 256 SpeedyType-0.5.0-source.zip` on macOS.
```

- [ ] **Step 4: Create the root development-tree README**

Create `README.md`:

```markdown
# SpeedyType Development Repository

This checkout is the development tree. It intentionally contains tests,
benchmark evidence, recordings, research reports, and local virtual
environments that are not part of a release.

Build the clean source release with:

```text
python scripts/build_release.py
```

The generated folder and ZIP appear under `dist/SpeedyType-VERSION/` and
`dist/SpeedyType-VERSION-source.zip`, where `VERSION` comes from
`speedytype/version.py`. `dist/` is generated and ignored by Git.
End users should follow the README inside the generated bundle.

Developer verification:

```text
python -m pytest -q
```
```

- [ ] **Step 5: Run README tests and verify GREEN**

Run: `python -m pytest tests/test_release_docs.py -q`

Expected: `3 passed`.

- [ ] **Step 6: Commit README contracts and content**

```powershell
git add README.md release/README.md tests/test_release_docs.py
git commit -m "docs: add source release installation guide"
```

---

### Task 3: Manifest-based release builder

**Files:**
- Create: `scripts/build_release.py`
- Create: `tests/test_build_release.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `ReleaseResult(release_dir: Path, archive_path: Path, checksum_path: Path)`.
- Produces: `build_release(repo_root: Path | None = None, output_root: Path | None = None) -> ReleaseResult`.
- CLI: `python scripts/build_release.py --output-dir C:\release-output` (the
  option is omitted to use repository `dist/`).

- [ ] **Step 1: Write failing inventory, archive, checksum, and secret tests**

Create `tests/test_build_release.py`:

```python
from hashlib import sha256
from pathlib import Path
import os
import zipfile

import scripts.build_release as build_release


ROOT = Path(__file__).resolve().parent.parent
EXPECTED_TOP_LEVEL = {
    ".env.example",
    "KNOWN_LIMITATIONS.md",
    "MAC_SETUP.md",
    "README.md",
    "pricing.json",
    "real_voice_script.md",
    "requirements.txt",
    "scripts",
    "speedytype",
}
EXPECTED_SCRIPTS = {
    "setup_mac.sh",
    "setup_windows.ps1",
    "verify_command_alias_windows.ps1",
}


def test_build_release_has_exact_runtime_inventory(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sentinel-release-secret")
    result = build_release.build_release(ROOT, tmp_path / "dist")

    assert result.release_dir.name == "SpeedyType-0.5.0"
    assert {path.name for path in result.release_dir.iterdir()} == EXPECTED_TOP_LEVEL
    assert {path.name for path in (result.release_dir / "scripts").iterdir()} == EXPECTED_SCRIPTS
    assert (result.release_dir / "speedytype" / "cli.py").is_file()
    assert not list(result.release_dir.rglob("__pycache__"))
    assert not list(result.release_dir.rglob("*.pyc"))
    assert not (result.release_dir / "tests").exists()
    assert not (result.release_dir / ".env").exists()

    released_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in result.release_dir.rglob("*")
        if path.is_file()
    )
    assert "sentinel-release-secret" not in released_text


def test_archive_matches_directory_and_checksum(tmp_path):
    result = build_release.build_release(ROOT, tmp_path / "dist")
    folder_files = {
        path.relative_to(result.release_dir).as_posix(): path.read_bytes()
        for path in result.release_dir.rglob("*")
        if path.is_file()
    }
    with zipfile.ZipFile(result.archive_path) as archive:
        archive_files = {
            name.removeprefix(f"{result.release_dir.name}/"): archive.read(name)
            for name in archive.namelist()
            if not name.endswith("/")
        }
    assert archive_files == folder_files

    digest = sha256(result.archive_path.read_bytes()).hexdigest()
    assert result.checksum_path.read_text(encoding="utf-8") == (
        f"{digest}  {result.archive_path.name}\n"
    )
```

- [ ] **Step 2: Run builder tests and verify RED**

Run: `python -m pytest tests/test_build_release.py -q`

Expected: collection fails because `scripts.build_release` does not exist.

- [ ] **Step 3: Implement the builder**

Create `scripts/build_release.py`:

```python
from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os
import runpy
import shutil
import tempfile
import uuid
import zipfile


ROOT = Path(__file__).resolve().parent.parent
STATIC_FILES = {
    "release/README.md": "README.md",
    "MAC_SETUP.md": "MAC_SETUP.md",
    "KNOWN_LIMITATIONS.md": "KNOWN_LIMITATIONS.md",
    "requirements.txt": "requirements.txt",
    "pricing.json": "pricing.json",
    ".env.example": ".env.example",
    "real_voice_script.md": "real_voice_script.md",
    "scripts/setup_windows.ps1": "scripts/setup_windows.ps1",
    "scripts/setup_mac.sh": "scripts/setup_mac.sh",
    "scripts/verify_command_alias_windows.ps1": "scripts/verify_command_alias_windows.ps1",
}


@dataclass(frozen=True)
class ReleaseResult:
    release_dir: Path
    archive_path: Path
    checksum_path: Path


def _load_version(repo_root: Path) -> str:
    namespace = runpy.run_path(str(repo_root / "speedytype" / "version.py"))
    version = namespace.get("VERSION")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("speedytype/version.py must define a non-empty VERSION")
    return version


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _safe_remove(path: Path, output_root: Path) -> None:
    if not _is_within(path, output_root) or path.resolve() == output_root.resolve():
        raise ValueError(f"Refusing to remove path outside release output: {path}")
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _copy_release_content(repo_root: Path, staging: Path) -> None:
    shutil.copytree(
        repo_root / "speedytype",
        staging / "speedytype",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    for source_name, destination_name in STATIC_FILES.items():
        source = repo_root / source_name
        if not source.is_file():
            raise FileNotFoundError(f"Required release file is missing: {source}")
        destination = staging / destination_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _swap_directory(staging: Path, target: Path, output_root: Path) -> None:
    backup = output_root / f".{target.name}.{uuid.uuid4().hex}.backup"
    had_target = target.exists()
    if had_target:
        target.replace(backup)
    try:
        staging.replace(target)
    except Exception:
        if had_target and backup.exists() and not target.exists():
            backup.replace(target)
        raise
    else:
        if backup.exists():
            _safe_remove(backup, output_root)


def _write_archive(release_dir: Path, archive_path: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{archive_path.name}.", suffix=".tmp", dir=archive_path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(release_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, f"{release_dir.name}/{path.relative_to(release_dir).as_posix()}")
        os.replace(temporary, archive_path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_checksum(archive_path: Path, checksum_path: Path) -> None:
    digest = sha256(archive_path.read_bytes()).hexdigest()
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{checksum_path.name}.", suffix=".tmp", dir=checksum_path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{digest}  {archive_path.name}\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, checksum_path)
    finally:
        temporary.unlink(missing_ok=True)


def build_release(
    repo_root: Path | None = None,
    output_root: Path | None = None,
) -> ReleaseResult:
    root = Path(repo_root or ROOT).resolve()
    output = Path(output_root or (root / "dist")).resolve()
    output.mkdir(parents=True, exist_ok=True)
    version = _load_version(root)
    release_dir = output / f"SpeedyType-{version}"
    archive_path = output / f"SpeedyType-{version}-source.zip"
    checksum_path = output / "SHA256SUMS.txt"
    staging = output / f".{release_dir.name}.{uuid.uuid4().hex}.staging"
    try:
        staging.mkdir()
        _copy_release_content(root, staging)
        _swap_directory(staging, release_dir, output)
        _write_archive(release_dir, archive_path)
        _write_checksum(archive_path, checksum_path)
    finally:
        if staging.exists():
            _safe_remove(staging, output)
    return ReleaseResult(release_dir, archive_path, checksum_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the SpeedyType source release")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    result = build_release(output_root=args.output_dir)
    print(result.release_dir)
    print(result.archive_path)
    print(result.checksum_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Ignore generated release output**

Append this exact entry to `.gitignore`:

```gitignore
dist/
```

- [ ] **Step 5: Run builder and documentation tests and verify GREEN**

Run: `python -m pytest tests/test_build_release.py tests/test_release_docs.py -q`

Expected: `5 passed`.

- [ ] **Step 6: Commit the manifest-based builder**

```powershell
git add .gitignore scripts/build_release.py tests/test_build_release.py
git commit -m "feat: build allowlisted source releases"
```

---

### Task 4: Idempotence and failure preservation

**Files:**
- Modify: `tests/test_build_release.py`
- Modify: `scripts/build_release.py` only if tests expose a defect.

**Interfaces:**
- Consumes: `build_release()`, `_copy_release_content()`, and guarded staging cleanup from Task 3.
- Verifies: stale-file removal and preservation of the last complete bundle on staging failure.

- [ ] **Step 1: Write failing repeat-build and injected-failure tests**

Append to `tests/test_build_release.py`:

```python
import pytest


def test_repeat_build_removes_stale_release_files(tmp_path):
    output = tmp_path / "dist"
    first = build_release.build_release(ROOT, output)
    stale = first.release_dir / "stale-development-output.txt"
    stale.write_text("must disappear", encoding="utf-8")

    second = build_release.build_release(ROOT, output)

    assert second.release_dir == first.release_dir
    assert not stale.exists()


def test_failed_staging_preserves_previous_complete_release(tmp_path, monkeypatch):
    output = tmp_path / "dist"
    first = build_release.build_release(ROOT, output)
    marker = first.release_dir / "previous-complete-marker.txt"
    marker.write_text("preserve me", encoding="utf-8")
    archive_bytes = first.archive_path.read_bytes()
    checksum_bytes = first.checksum_path.read_bytes()

    def fail_copy(repo_root, staging):
        (staging / "partial.txt").write_text("partial", encoding="utf-8")
        raise OSError("injected staging failure")

    monkeypatch.setattr(build_release, "_copy_release_content", fail_copy)

    with pytest.raises(OSError, match="injected staging failure"):
        build_release.build_release(ROOT, output)

    assert marker.read_text(encoding="utf-8") == "preserve me"
    assert first.archive_path.read_bytes() == archive_bytes
    assert first.checksum_path.read_bytes() == checksum_bytes
    assert not list(output.glob("*.staging"))
```

- [ ] **Step 2: Run the idempotence tests and verify behavior**

Run: `python -m pytest tests/test_build_release.py -q`

Expected: all four tests pass. If either fails, fix only the transactional cleanup/swap code required by that failure and rerun until green.

- [ ] **Step 3: Add a containment-guard regression test**

Append:

```python
def test_safe_remove_rejects_paths_outside_output(tmp_path):
    output = tmp_path / "dist"
    outside = tmp_path / "outside"
    outside.mkdir()

    with pytest.raises(ValueError, match="outside release output"):
        build_release._safe_remove(outside, output)

    assert outside.exists()
```

- [ ] **Step 4: Run the complete builder test file**

Run: `python -m pytest tests/test_build_release.py -q`

Expected: `5 passed`.

- [ ] **Step 5: Commit failure-safety coverage**

```powershell
git add scripts/build_release.py tests/test_build_release.py
git commit -m "test: verify repeatable release replacement"
```

---

### Task 5: Plan bookkeeping and release evidence

**Files:**
- Modify: `docs/superpowers/plans/2026-07-15-command-alias.md`
- Modify: `POC_REPORT.md`

**Interfaces:**
- Records: all 34 command-alias implementation steps as complete.
- Preserves: real-Mac runtime verification as pending in `MAC_SETUP.md` and `KNOWN_LIMITATIONS.md`.
- Records: exact generated artifact names and observed verification commands.

- [ ] **Step 1: Mark completed command-alias plan steps**

Mechanically replace every step marker `- [ ]` with `- [x]` in
`docs/superpowers/plans/2026-07-15-command-alias.md`. Verify the result with:

```powershell
$plan = Get-Content docs/superpowers/plans/2026-07-15-command-alias.md
if (($plan | Select-String '^- \[ \]').Count -ne 0) { exit 1 }
if (($plan | Select-String '^- \[x\]').Count -ne 34) { exit 1 }
```

- [ ] **Step 2: Add the release section to `POC_REPORT.md`**

Record these facts, replacing command results with exact observed values from
Task 6 rather than estimates:

```markdown
## Reproducible source release

- `python scripts/build_release.py` builds from an explicit allowlist into
  ignored `dist/`, so repository tests, recordings, benchmark evidence,
  development plans, caches, local settings, `.env`, and Keyring data are not
  release inputs.
- The version comes from `speedytype/version.py`; output consists of the
  versioned source directory, matching source ZIP, and `SHA256SUMS.txt`.
- The release README documents automatic setup and manual venv plus
  `pip install -r requirements.txt` installation on Windows and macOS,
  Keyring-backed credential configuration, daily commands, updates,
  troubleshooting, and checksum verification.
- Verification evidence is added in Task 6 from the observed pytest, build,
  extraction, syntax, and checksum command outputs.
```

- [ ] **Step 3: Run focused tests and documentation checks**

Run:

```powershell
python -m pytest tests/test_release_docs.py tests/test_build_release.py -q
git diff --check
```

Expected: `8 passed` and diff check exit 0.

- [ ] **Step 4: Commit bookkeeping and evidence structure**

```powershell
git add docs/superpowers/plans/2026-07-15-command-alias.md POC_REPORT.md
git commit -m "docs: record source release workflow"
```

---

### Task 6: Build and verify the real release

**Files:**
- Modify: `POC_REPORT.md` only to replace evidence text with exact results.
- Generated/ignored: `dist/SpeedyType-0.5.0/`
- Generated/ignored: `dist/SpeedyType-0.5.0-source.zip`
- Generated/ignored: `dist/SHA256SUMS.txt`

**Interfaces:**
- Consumes: the complete builder, docs, and existing project environment.
- Produces: real release artifacts and final verification evidence.

- [ ] **Step 1: Run the full suite before building**

Run: `python -m pytest -q`

Expected: all tests pass with zero failures.

- [ ] **Step 2: Build twice to verify real idempotence**

Run:

```powershell
python scripts/build_release.py
python scripts/build_release.py
```

Expected: both runs exit 0 and print the same three versioned output paths.

- [ ] **Step 3: Verify checksum and inventory**

Run:

```powershell
$zip = Resolve-Path dist/SpeedyType-0.5.0-source.zip
$line = (Get-Content dist/SHA256SUMS.txt).Trim()
$actual = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant()
if (-not $line.StartsWith($actual)) { throw "Release checksum mismatch" }
Get-ChildItem dist/SpeedyType-0.5.0 -Force
```

Expected: checksum matches and the inventory equals the documented allowlist.

- [ ] **Step 4: Extract and smoke-test the archive**

Run in a temporary directory:

```powershell
$temp = Join-Path ([System.IO.Path]::GetTempPath()) ("speedytype-release-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $temp | Out-Null
try {
    Expand-Archive dist/SpeedyType-0.5.0-source.zip -DestinationPath $temp
    $release = Join-Path $temp "SpeedyType-0.5.0"
    python -m compileall -q (Join-Path $release "speedytype")
    Push-Location $release
    try { python -m speedytype --help | Out-Null } finally { Pop-Location }
    & 'C:\Program Files\Git\bin\bash.EXE' -n (Join-Path $release "scripts/setup_mac.sh")
    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile(
        (Join-Path $release "scripts/setup_windows.ps1"),
        [ref]$tokens,
        [ref]$errors
    ) | Out-Null
    if ($errors.Count) { $errors | Format-List; exit 1 }
} finally {
    Remove-Item -LiteralPath $temp -Recurse -Force
}
```

Expected: compile, CLI help, Bash syntax, and PowerShell parse all exit 0.

- [ ] **Step 5: Update exact evidence and commit if changed**

Replace the evidence line in `POC_REPORT.md` with observed test counts, artifact
names, checksum result, and extraction smoke result, then:

```powershell
git add POC_REPORT.md
git diff --cached --quiet || git commit -m "docs: record verified source release"
```

- [ ] **Step 6: Run final verification on committed HEAD**

Run:

```powershell
python -m pytest -q
python -m compileall -q speedytype scripts
git diff --check
git status --short
```

Expected: all tests pass, compile/diff checks exit 0, and the worktree is clean;
`dist/` remains present but ignored.
