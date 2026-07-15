from __future__ import annotations

from pathlib import Path
import os
import shlex
import sys
import tempfile

from speedytype.paths import app_data_dir, default_env_path


_REG_EXPAND_SZ = 2


def _project_root() -> Path:
    import speedytype

    return Path(speedytype.__file__).resolve().parent.parent


def _windows_bin_dir() -> Path:
    return app_data_dir() / "bin"


def _posix_bin_dir() -> Path:
    return Path.home() / ".local" / "bin"


def _atomic_write(path: Path, content: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
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
        0xFFFF,
        0x001A,
        0,
        "Environment",
        0x0002,
        5000,
        None,
    )
    if not result:
        raise OSError(
            "Windows did not acknowledge the environment change notification"
        )


def _normalized_windows_path(value: str) -> str:
    unquoted = value.strip().strip('"')
    expanded = os.path.expandvars(unquoted)
    return os.path.normcase(os.path.normpath(expanded))


def _ensure_windows_user_path(directory: Path) -> tuple[bool, str]:
    current, kind = _read_user_path()
    entries = [entry for entry in current.split(";") if entry]
    target = str(directory)
    normalized_target = _normalized_windows_path(target)
    if any(
        _normalized_windows_path(entry) == normalized_target for entry in entries
    ):
        return False, "User PATH already contains the command directory."
    updated = ";".join([*entries, target])
    _write_user_path(updated, kind)
    _broadcast_environment_change()
    return True, "Added the command directory to the user PATH."


def _install_windows(env_path: Path) -> tuple[bool, str]:
    path = _windows_bin_dir() / "speedytype.bat"
    project = _project_root().resolve()
    python = sys.executable
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
    python = shlex.quote(sys.executable)
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
