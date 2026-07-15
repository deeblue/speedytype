# Cross-Platform Command Alias Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add repeatable Windows and macOS setup scripts that install a short `speedytype` command without exposing or bypassing the existing Keyring credential flow.

**Architecture:** A new `speedytype.command_alias` module renders and atomically installs the platform wrapper and owns Windows user-PATH integration. The existing CLI exposes that boundary as `install-command`; platform setup scripts create/reuse `.venv`, install dependencies, and invoke the shared command. Wrappers capture only Python, repository, and default config paths, then pass every user argument to the existing CLI.

**Tech Stack:** Python 3.13, argparse, pathlib, winreg/ctypes on Windows, POSIX shell, PowerShell, pytest.

## Global Constraints

- Wrappers must never contain, read, copy, expand, log, or modify API key values.
- Existing credential resolution remains Keyring, then process environment, then legacy `.env` fallback with migration.
- `speedytype --env other.env <action>` must override the wrapper's installed default.
- Both setup scripts and `install-command` must be safe to run repeatedly.
- Windows installation is user-scoped and must not require administrator rights.
- macOS setup must not modify shell startup files automatically.
- Autostart installation and behavior are outside this feature and must remain unchanged.
- Real macOS execution remains a documented user verification step.

---

### Task 1: Platform wrapper installer

**Files:**
- Create: `speedytype/command_alias.py`
- Create: `tests/test_command_alias.py`

**Interfaces:**
- Consumes: `speedytype.paths.app_data_dir()`, `speedytype.paths.default_env_path()`, `sys.executable`, and `sys.platform`.
- Produces: `install_command_alias(env_path: str | Path | None = None) -> tuple[bool, str]`.
- Produces: Windows `%APPDATA%/SpeedyType/bin/speedytype.bat` and macOS `~/.local/bin/speedytype`.

- [ ] **Step 1: Write failing rendering and dispatch tests**

Create `tests/test_command_alias.py` with tests that import the wished-for API, install into temporary directories, and assert exact safety properties:

```python
from pathlib import Path
import os

import speedytype.command_alias as command_alias


def test_windows_wrapper_quotes_paths_and_forwards_all_arguments(monkeypatch, tmp_path):
    install_dir = tmp_path / "alias dir"
    project = tmp_path / "project dir"
    env_path = tmp_path / "config dir" / ".env"
    monkeypatch.setattr(command_alias, "_windows_bin_dir", lambda: install_dir)
    monkeypatch.setattr(command_alias, "_project_root", lambda: project)
    monkeypatch.setattr(command_alias.sys, "executable", r"C:\Python Dir\python.exe")
    monkeypatch.setattr(command_alias, "_ensure_windows_user_path", lambda path: (False, "already present"))

    ok, _ = command_alias._install_windows(env_path)

    assert ok
    content = (install_dir / "speedytype.bat").read_text(encoding="utf-8")
    assert f'cd /d "{project.resolve()}"' in content
    assert '"C:\\Python Dir\\python.exe" -m speedytype' in content
    assert f'--env "{env_path.resolve()}" %*' in content


def test_posix_wrapper_quotes_paths_for_exec_and_forwards_arguments(monkeypatch, tmp_path):
    install_dir = tmp_path / "alias dir"
    project = tmp_path / "project dir"
    env_path = tmp_path / "config dir" / ".env"
    monkeypatch.setattr(command_alias, "_posix_bin_dir", lambda: install_dir)
    monkeypatch.setattr(command_alias, "_project_root", lambda: project)
    monkeypatch.setattr(command_alias.sys, "executable", "/tmp/python dir/python3")
    monkeypatch.setenv("PATH", str(install_dir))

    ok, _ = command_alias._install_macos(env_path)

    assert ok
    wrapper = install_dir / "speedytype"
    content = wrapper.read_text(encoding="utf-8")
    assert f"cd '{project.resolve()}'" in content
    assert "exec '/tmp/python dir/python3' -m speedytype" in content
    assert f"--env '{env_path.resolve()}' \"$@\"" in content
    assert wrapper.stat().st_mode & 0o111


def test_installed_wrapper_never_contains_secret_values(monkeypatch, tmp_path):
    monkeypatch.setattr(command_alias, "_posix_bin_dir", lambda: tmp_path / "bin")
    monkeypatch.setattr(command_alias, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(command_alias.sys, "executable", "/usr/bin/python3")
    monkeypatch.setenv("OPENAI_API_KEY", "sentinel-openai-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "sentinel-gemini-secret")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))

    ok, _ = command_alias._install_macos(tmp_path / ".env")

    assert ok
    content = (tmp_path / "bin" / "speedytype").read_text(encoding="utf-8")
    assert "sentinel-openai-secret" not in content
    assert "sentinel-gemini-secret" not in content


def test_install_command_alias_dispatches_by_platform(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(command_alias, "_install_windows", lambda env: calls.append(("win", env)) or (True, "ok"))
    monkeypatch.setattr(command_alias.sys, "platform", "win32")
    assert command_alias.install_command_alias(tmp_path / ".env") == (True, "ok")
    assert calls == [("win", (tmp_path / ".env").resolve())]
```

- [ ] **Step 2: Run the new tests and verify RED**

Run: `python -m pytest tests/test_command_alias.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'speedytype.command_alias'`.

- [ ] **Step 3: Implement atomic wrapper rendering and platform dispatch**

Create `speedytype/command_alias.py` with:

```python
from __future__ import annotations

from pathlib import Path
import os
import shlex
import sys
import tempfile

from speedytype.paths import app_data_dir, default_env_path


def _project_root() -> Path:
    import speedytype
    return Path(speedytype.__file__).resolve().parent.parent


def _windows_bin_dir() -> Path:
    return app_data_dir() / "bin"


def _posix_bin_dir() -> Path:
    return Path.home() / ".local" / "bin"


def _atomic_write(path: Path, content: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _batch_quote(value: Path | str) -> str:
    return str(value).replace("%", "%%").replace('"', '""')


def _install_windows(env_path: Path) -> tuple[bool, str]:
    path = _windows_bin_dir() / "speedytype.bat"
    project = _project_root().resolve()
    python = Path(sys.executable).resolve()
    content = (
        "@echo off\r\n"
        f'cd /d "{_batch_quote(project)}"\r\n'
        "set PYTHONIOENCODING=utf-8\r\n"
        f'"{_batch_quote(python)}" -m speedytype --env "{_batch_quote(env_path)}" %*\r\n'
    )
    try:
        _atomic_write(path, content)
        changed, detail = _ensure_windows_user_path(path.parent)
    except OSError as exc:
        return False, f"Command alias installation failed: {exc}"
    suffix = " Open a new terminal to use it." if changed else ""
    return True, f"Command alias installed at {path}. {detail}{suffix}".strip()


def _install_macos(env_path: Path) -> tuple[bool, str]:
    path = _posix_bin_dir() / "speedytype"
    project = shlex.quote(str(_project_root().resolve()))
    python = shlex.quote(str(Path(sys.executable).resolve()))
    env = shlex.quote(str(env_path))
    content = f'#!/bin/sh\ncd {project}\nexec {python} -m speedytype --env {env} "$@"\n'
    try:
        _atomic_write(path, content, 0o755)
    except OSError as exc:
        return False, f"Command alias installation failed: {exc}"
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    if str(path.parent) not in path_entries:
        return True, (
            f"Command alias installed at {path}. Add this line to ~/.zshrc (zsh) "
            'or ~/.bash_profile (bash): export PATH="$HOME/.local/bin:$PATH"'
        )
    return True, f"Command alias installed at {path}."


def install_command_alias(env_path: str | Path | None = None) -> tuple[bool, str]:
    env = Path(env_path or default_env_path()).resolve()
    if sys.platform == "win32":
        return _install_windows(env)
    if sys.platform == "darwin":
        return _install_macos(env)
    return False, f"Unsupported platform for command alias installation: {sys.platform}"
```

Leave `_ensure_windows_user_path` temporarily raising `NotImplementedError`; the dispatch test replaces it and the next cycle defines it.

- [ ] **Step 4: Run rendering tests and verify GREEN**

Run: `python -m pytest tests/test_command_alias.py -q`

Expected: all four tests pass.

- [ ] **Step 5: Write failing Windows PATH and macOS idempotence tests**

Append tests using an in-memory registry adapter seam:

```python
def test_windows_path_is_preserved_and_deduplicated_case_insensitively(monkeypatch, tmp_path):
    values = {"Path": (r"C:\Tools;C:\Users\Me\Alias", command_alias._REG_EXPAND_SZ)}
    notifications = []
    monkeypatch.setattr(command_alias, "_read_user_path", lambda: values["Path"])
    monkeypatch.setattr(command_alias, "_write_user_path", lambda value, kind: values.__setitem__("Path", (value, kind)))
    monkeypatch.setattr(command_alias, "_broadcast_environment_change", lambda: notifications.append(True))

    changed, _ = command_alias._ensure_windows_user_path(Path(r"c:\users\me\alias\"))

    assert changed is False
    assert values["Path"][0] == r"C:\Tools;C:\Users\Me\Alias"
    assert notifications == []


def test_windows_path_addition_preserves_existing_value_type(monkeypatch):
    values = {"Path": (r"C:\Tools", command_alias._REG_EXPAND_SZ)}
    notifications = []
    monkeypatch.setattr(command_alias, "_read_user_path", lambda: values["Path"])
    monkeypatch.setattr(command_alias, "_write_user_path", lambda value, kind: values.__setitem__("Path", (value, kind)))
    monkeypatch.setattr(command_alias, "_broadcast_environment_change", lambda: notifications.append(True))

    changed, _ = command_alias._ensure_windows_user_path(Path(r"C:\SpeedyType\bin"))

    assert changed is True
    assert values["Path"] == (r"C:\Tools;C:\SpeedyType\bin", command_alias._REG_EXPAND_SZ)
    assert notifications == [True]


def test_macos_repeat_install_replaces_same_wrapper(monkeypatch, tmp_path):
    install_dir = tmp_path / "bin"
    monkeypatch.setattr(command_alias, "_posix_bin_dir", lambda: install_dir)
    monkeypatch.setattr(command_alias, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(command_alias.sys, "executable", "/usr/bin/python3")
    monkeypatch.setenv("PATH", str(install_dir))

    first = command_alias._install_macos(tmp_path / "first.env")
    second = command_alias._install_macos(tmp_path / "second.env")

    assert first[0] and second[0]
    wrappers = list(install_dir.iterdir())
    assert [path.name for path in wrappers] == ["speedytype"]
    assert "second.env" in wrappers[0].read_text(encoding="utf-8")
    assert "first.env" not in wrappers[0].read_text(encoding="utf-8")


def test_macos_install_prints_exact_path_guidance(monkeypatch, tmp_path):
    monkeypatch.setattr(command_alias, "_posix_bin_dir", lambda: tmp_path / ".local" / "bin")
    monkeypatch.setattr(command_alias, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(command_alias.sys, "executable", "/usr/bin/python3")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    ok, message = command_alias._install_macos(tmp_path / ".env")

    assert ok
    assert 'export PATH="$HOME/.local/bin:$PATH"' in message
    assert "~/.zshrc" in message
    assert "~/.bash_profile" in message


def test_atomic_write_failure_preserves_existing_wrapper(monkeypatch, tmp_path):
    wrapper = tmp_path / "speedytype"
    wrapper.write_text("original", encoding="utf-8")
    monkeypatch.setattr(command_alias.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk full")))

    try:
        command_alias._atomic_write(wrapper, "replacement", 0o755)
    except OSError as exc:
        assert str(exc) == "disk full"
    else:
        raise AssertionError("expected atomic write to fail")

    assert wrapper.read_text(encoding="utf-8") == "original"
    assert [path.name for path in tmp_path.iterdir()] == ["speedytype"]


def test_windows_broadcast_failure_is_reported_without_secret_text(monkeypatch, tmp_path):
    monkeypatch.setattr(command_alias, "_windows_bin_dir", lambda: tmp_path / "bin")
    monkeypatch.setattr(command_alias, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        command_alias,
        "_ensure_windows_user_path",
        lambda path: (_ for _ in ()).throw(OSError("notification failed")),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sentinel-secret")

    ok, message = command_alias._install_windows(tmp_path / ".env")

    assert ok is False
    assert "notification failed" in message
    assert "sentinel-secret" not in message
```

- [ ] **Step 6: Run the focused tests and verify RED**

Run: `python -m pytest tests/test_command_alias.py -q`

Expected: PATH tests fail because `_REG_EXPAND_SZ`, `_read_user_path`, `_write_user_path`, `_broadcast_environment_change`, and `_ensure_windows_user_path` are not implemented.

- [ ] **Step 7: Implement Windows user PATH integration**

Add lazy Windows registry and notification helpers to `speedytype/command_alias.py` so importing the module remains safe on macOS:

```python
_REG_EXPAND_SZ = 2


def _read_user_path() -> tuple[str, int]:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
        try:
            value, kind = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            return "", winreg.REG_EXPAND_SZ
    return str(value), kind


def _write_user_path(value: str, kind: int) -> None:
    import winreg
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Environment",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, "Path", 0, kind, value)


def _broadcast_environment_change() -> None:
    import ctypes
    result = ctypes.windll.user32.SendMessageTimeoutW(
        0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None
    )
    if not result:
        raise OSError("Windows did not acknowledge the environment change notification")


def _normalized_windows_path(value: str) -> str:
    unquoted = value.strip().strip('"')
    expanded = os.path.expandvars(unquoted)
    return os.path.normcase(os.path.normpath(expanded))


def _ensure_windows_user_path(directory: Path) -> tuple[bool, str]:
    current, kind = _read_user_path()
    entries = [entry for entry in current.split(";") if entry]
    target = str(directory)
    normalized_target = _normalized_windows_path(target)
    if any(_normalized_windows_path(entry) == normalized_target for entry in entries):
        return False, "User PATH already contains the command directory."
    updated = ";".join([*entries, target])
    _write_user_path(updated, kind)
    _broadcast_environment_change()
    return True, "Added the command directory to the user PATH."
```

- [ ] **Step 8: Run installer tests and the existing Keyring tests**

Run: `python -m pytest tests/test_command_alias.py tests/test_secrets_store.py tests/test_config.py -q`

Expected: all tests pass, proving wrapper installation is independent of credential storage.

- [ ] **Step 9: Commit the installer boundary**

```powershell
git add speedytype/command_alias.py tests/test_command_alias.py
git commit -m "feat: install cross-platform command wrappers"
```

---

### Task 2: CLI `install-command` entry point and override semantics

**Files:**
- Modify: `speedytype/cli.py`
- Create: `tests/test_cli_command_alias.py`

**Interfaces:**
- Consumes: `install_command_alias(env_path: str | Path | None) -> tuple[bool, str]` from Task 1.
- Produces: `python -m speedytype --env <path> install-command`.
- Preserves: duplicate global `--env` arguments use the last value, allowing a wrapper default to be overridden.

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli_command_alias.py`:

```python
from pathlib import Path

import speedytype.cli as cli


def test_install_command_passes_selected_env_to_installer(monkeypatch, tmp_path, capsys):
    calls = []
    monkeypatch.setattr(cli, "install_command_alias", lambda env: calls.append(env) or (True, "installed"))
    env_path = tmp_path / "chosen.env"

    result = cli.main(["--env", str(env_path), "install-command"])

    assert result == 0
    assert calls == [str(env_path)]
    assert capsys.readouterr().out.strip() == "installed"


def test_install_command_returns_nonzero_on_failure(monkeypatch, capsys):
    monkeypatch.setattr(cli, "install_command_alias", lambda env: (False, "installation failed"))

    result = cli.main(["install-command"])

    assert result == 1
    assert capsys.readouterr().out.strip() == "installation failed"


def test_later_env_argument_overrides_wrapper_default():
    parser = cli.build_parser()
    args = parser.parse_args([
        "--env", "installed.env",
        "--env", "other.env",
        "diagnose-config",
    ])
    assert args.env == "other.env"
```

- [ ] **Step 2: Run the CLI tests and verify RED**

Run: `python -m pytest tests/test_cli_command_alias.py -q`

Expected: import/monkeypatch or parser failures because `install_command_alias` and `install-command` are absent.

- [ ] **Step 3: Add the CLI command**

Modify `speedytype/cli.py`:

```python
from speedytype.command_alias import install_command_alias


def command_install_command(args: argparse.Namespace) -> int:
    ok, message = install_command_alias(env_path=args.env)
    print(message)
    return 0 if ok else 1
```

Add to `build_parser()` before the autostart parsers:

```python
install_command = sub.add_parser("install-command")
install_command.set_defaults(func=command_install_command)
```

- [ ] **Step 4: Run CLI and alias tests and verify GREEN**

Run: `python -m pytest tests/test_cli_command_alias.py tests/test_command_alias.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit the CLI entry point**

```powershell
git add speedytype/cli.py tests/test_cli_command_alias.py
git commit -m "feat: expose command alias installer in CLI"
```

---

### Task 3: Symmetric Windows and macOS setup scripts

**Files:**
- Create: `scripts/setup_windows.ps1`
- Create: `scripts/setup_mac.sh`
- Create: `tests/test_setup_scripts.py`

**Interfaces:**
- Consumes: `python -m speedytype --env <path> install-command` from Task 2.
- Produces: one-time `scripts/setup_windows.ps1 [-EnvPath <path>]`.
- Produces: one-time `scripts/setup_mac.sh [env-path]`.

- [ ] **Step 1: Write failing setup-script contract tests**

Create `tests/test_setup_scripts.py`:

```python
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parent.parent


def test_windows_setup_uses_script_relative_root_venv_and_install_command():
    content = (ROOT / "scripts" / "setup_windows.ps1").read_text(encoding="utf-8")
    assert "$PSScriptRoot" in content
    assert '".venv\\Scripts\\python.exe"' in content
    assert '"requirements.txt"' in content
    assert '"install-command"' in content
    assert "-EnvPath" in content


def test_macos_setup_uses_script_relative_root_venv_and_install_command():
    content = (ROOT / "scripts" / "setup_mac.sh").read_text(encoding="utf-8")
    assert 'SCRIPT_DIR=' in content
    assert 'PROJECT_ROOT=' in content
    assert '"$PROJECT_ROOT/.venv/bin/python"' in content
    assert '"$PROJECT_ROOT/requirements.txt"' in content
    assert 'install-command' in content
    assert 'ENV_PATH="${1:-' in content


def test_macos_setup_has_valid_bash_syntax_when_bash_is_available():
    bash = shutil.which("bash")
    if bash is None:
        return
    result = subprocess.run(
        [bash, "-n", str(ROOT / "scripts" / "setup_mac.sh")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 2: Run setup-script tests and verify RED**

Run: `python -m pytest tests/test_setup_scripts.py -q`

Expected: file-not-found failures for both setup scripts.

- [ ] **Step 3: Implement `scripts/setup_windows.ps1`**

Create this PowerShell setup entry:

```powershell
[CmdletBinding()]
param(
    [string]$EnvPath = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    $BootstrapPython = if ($env:PYTHON) { $env:PYTHON } else { "python" }
    & $BootstrapPython -m venv (Join-Path $ProjectRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Failed to create .venv." }
}

& $VenvPython -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Failed to install requirements." }

$Arguments = @("-m", "speedytype")
if ($EnvPath) {
    $Arguments += @("--env", (Resolve-Path -LiteralPath $EnvPath).Path)
}
$Arguments += "install-command"
& $VenvPython @Arguments
if ($LASTEXITCODE -ne 0) { throw "Failed to install the speedytype command." }

Write-Host "Setup complete. Open a new terminal and run: speedytype diagnose-config"
```

- [ ] **Step 4: Implement `scripts/setup_mac.sh`**

Create this Bash setup entry:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
ENV_PATH="${1:-$HOME/Library/Application Support/SpeedyType/.env}"

if [[ ! -x "$VENV_PYTHON" ]]; then
    "${PYTHON:-python3}" -m venv "$PROJECT_ROOT/.venv"
fi

"$VENV_PYTHON" -m pip install -r "$PROJECT_ROOT/requirements.txt"
"$VENV_PYTHON" -m speedytype --env "$ENV_PATH" install-command

echo "Setup complete. Open a new terminal and run: speedytype diagnose-config"
```

Set executable permission with `git update-index --chmod=+x scripts/setup_mac.sh`.

- [ ] **Step 5: Run script contract and syntax tests**

Run: `python -m pytest tests/test_setup_scripts.py -q`

Expected: all tests pass; the Bash syntax test runs where Git Bash or another Bash is on PATH.

- [ ] **Step 6: Parse the PowerShell script without executing setup**

Run:

```powershell
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path scripts/setup_windows.ps1),
    [ref]$null,
    [ref]$errors
) | Out-Null
if ($errors.Count) { $errors | Format-List; exit 1 }
```

Expected: exit 0 with no parser errors.

- [ ] **Step 7: Commit both setup scripts**

```powershell
git add scripts/setup_windows.ps1 scripts/setup_mac.sh tests/test_setup_scripts.py
git commit -m "feat: add Windows and macOS setup scripts"
```

---

### Task 4: Documentation and live Windows verifier

**Files:**
- Create: `MAC_SETUP.md`
- Create: `scripts/verify_command_alias_windows.ps1`
- Modify: `POC_REPORT.md`
- Modify: `KNOWN_LIMITATIONS.md`

**Interfaces:**
- Consumes: setup scripts and installed wrappers from Tasks 1-3.
- Produces: repeatable live Windows evidence and macOS user verification instructions.

- [ ] **Step 1: Create a live Windows verification script**

Create `scripts/verify_command_alias_windows.ps1` with guarded daemon cleanup:

```powershell
[CmdletBinding()]
param([int]$DaemonStartupTimeoutSeconds = 15)

$ErrorActionPreference = "Stop"

function Invoke-SpeedyTypeCmd {
    param([Parameter(Mandatory)][string[]]$Arguments)
    $line = "speedytype " + (($Arguments | ForEach-Object { '"' + ($_ -replace '"', '\"') + '"' }) -join " ")
    $process = Start-Process cmd.exe -ArgumentList @("/d", "/c", $line) -Wait -PassThru -NoNewWindow
    if ($process.ExitCode -ne 0) { throw "Command failed ($($process.ExitCode)): $line" }
}

Invoke-SpeedyTypeCmd @("diagnose-config")
Invoke-SpeedyTypeCmd @("guided-recording", "--help")

$daemon = Start-Process cmd.exe -ArgumentList @("/d", "/c", "speedytype daemon") -PassThru -WindowStyle Hidden
try {
    $deadline = (Get-Date).AddSeconds($DaemonStartupTimeoutSeconds)
    do {
        Start-Sleep -Milliseconds 250
        $stopProbe = Start-Process cmd.exe -ArgumentList @("/d", "/c", "speedytype daemon-stop") -Wait -PassThru -NoNewWindow
        if ($stopProbe.ExitCode -eq 0) { break }
    } while ((Get-Date) -lt $deadline)
    if ($stopProbe.ExitCode -ne 0) { throw "Daemon did not become stoppable before timeout." }
}
finally {
    Start-Process cmd.exe -ArgumentList @("/d", "/c", "speedytype daemon-stop") -Wait -NoNewWindow | Out-Null
    if (-not $daemon.HasExited) { $daemon.WaitForExit(5000) | Out-Null }
}

Write-Host "COMMAND_ALIAS_WINDOWS_OK"
```

- [ ] **Step 2: Document macOS setup and Keyring-safe behavior**

Create `MAC_SETUP.md` with these concrete commands and explanations:

```markdown
# SpeedyType macOS Setup

Run once from the repository:

```sh
./scripts/setup_mac.sh
```

To select a non-default configuration file during installation:

```sh
./scripts/setup_mac.sh "/path/to/other.env"
```

The setup creates/reuses `.venv`, installs requirements, and installs
`~/.local/bin/speedytype`. If setup prints a PATH warning, add this line to
`~/.zshrc` (zsh) or `~/.bash_profile` (bash), then open a new terminal:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Daily examples:

```sh
speedytype diagnose-config
speedytype daemon
speedytype daemon-stop
speedytype guided-recording --script real_voice_script.md
speedytype --env /path/to/other.env daemon
```

The wrapper contains paths only. API keys remain in macOS Keychain through the
existing Keyring integration; setup does not copy or modify credentials.

Real-device check: rerun setup, open a new terminal, execute the examples above,
and confirm the second setup neither duplicates PATH entries nor changes keys.
```

- [ ] **Step 3: Update project evidence and limitations**

Add a `Short command alias` section to `POC_REPORT.md` recording:

- The one-time Windows and macOS setup entry points.
- Installed wrapper locations.
- Parameter forwarding and explicit `--env` override.
- Keyring safety boundary.
- Exact automated and live Windows verification commands/results from Task 5.

Update `KNOWN_LIMITATIONS.md` to state that macOS wrapper logic and Bash syntax are audited on Windows, while new-terminal and daemon behavior still require real macOS verification.

- [ ] **Step 4: Run documentation and script checks**

Run:

```powershell
python -m pytest tests/test_setup_scripts.py tests/test_command_alias.py tests/test_cli_command_alias.py -q
git diff --check
```

Expected: all focused tests pass and `git diff --check` exits 0.

- [ ] **Step 5: Commit documentation and verifier**

```powershell
git add MAC_SETUP.md POC_REPORT.md KNOWN_LIMITATIONS.md scripts/verify_command_alias_windows.ps1
git commit -m "docs: explain short command setup and verification"
```

---

### Task 5: Install, verify, and record final evidence

**Files:**
- Modify: `POC_REPORT.md` only if actual counts or live results differ from the initial evidence text recorded in Task 4.

**Interfaces:**
- Consumes: the completed setup and verifier.
- Produces: fresh automated and real Windows acceptance evidence.

- [ ] **Step 1: Run the complete automated suite before installation**

Run: `python -m pytest -q`

Expected: all tests pass with no failures.

- [ ] **Step 2: Run Windows setup twice to prove idempotence**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup_windows.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup_windows.ps1
```

Expected: both runs exit 0; the second reports the wrapper directory is already present in user PATH and does not duplicate it.

- [ ] **Step 3: Verify from fresh command-shell processes**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_command_alias_windows.ps1
```

Expected: `diagnose-config`, parameter forwarding, daemon startup, and daemon stop all exit successfully, ending with `COMMAND_ALIAS_WINDOWS_OK`.

- [ ] **Step 4: Verify explicit `.env` override without exposing secrets**

Run a new command process against a temporary valid config path:

```powershell
cmd.exe /d /c "speedytype --env `"$((Resolve-Path .env).Path)`" diagnose-config"
```

Expected: exit 0 and `Config OK`; output contains configuration names but no API key values.

- [ ] **Step 5: Audit macOS script and compile Python sources**

Run:

```powershell
bash -n scripts/setup_mac.sh
python -m compileall -q speedytype scripts
git diff --check
```

Expected: all commands exit 0. If Bash is unavailable, record the automated pytest syntax check as skipped and state that limitation rather than claiming a Bash audit.

- [ ] **Step 6: Update evidence text with exact observed results**

If test counts, timings, PATH messages, or live verification results differ from Task 4, edit `POC_REPORT.md` to contain only the observed outputs. Do not claim macOS real-device success.

- [ ] **Step 7: Commit final evidence if documentation changed**

```powershell
git add POC_REPORT.md
git diff --cached --quiet || git commit -m "docs: record command alias verification"
```

- [ ] **Step 8: Run final verification on committed HEAD**

Run:

```powershell
python -m pytest -q
python -m compileall -q speedytype scripts
git diff --check
git status --short
```

Expected: complete suite passes, compilation and diff checks exit 0, and the worktree is clean.
