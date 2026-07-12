from __future__ import annotations

from pathlib import Path
import os
import sys

from speedytype.paths import default_daemon_log_path, default_env_path


STARTUP_SCRIPT_NAME = "SpeedyTypeDaemon.bat"


def _pythonw_path() -> str:
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return str(candidate) if candidate.exists() else sys.executable


def _project_root() -> Path:
    import speedytype

    return Path(speedytype.__file__).resolve().parent.parent


def _startup_folder() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA environment variable is not set; cannot locate the Startup folder.")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def install_autostart(env_path: str | Path | None = None) -> tuple[bool, str]:
    try:
        startup_dir = _startup_folder()
    except RuntimeError as exc:
        return False, str(exc)
    if not startup_dir.exists():
        return False, f"Startup folder not found at {startup_dir}."
    env = Path(env_path or default_env_path()).resolve()
    log = default_daemon_log_path().resolve()
    script_path = startup_dir / STARTUP_SCRIPT_NAME
    script_path.write_text(
        "@echo off\r\n"
        f'cd /d "{_project_root()}"\r\n'
        "set PYTHONIOENCODING=utf-8\r\n"
        f'"{_pythonw_path()}" -m speedytype --env "{env}" daemon >> "{log}" 2>&1\r\n',
        encoding="utf-8",
    )
    return True, f"Autostart script written to {script_path}. It will run at next logon."


def uninstall_autostart() -> tuple[bool, str]:
    try:
        script_path = _startup_folder() / STARTUP_SCRIPT_NAME
    except RuntimeError as exc:
        return False, str(exc)
    if not script_path.exists():
        return True, f"Autostart script not found at {script_path}; nothing to remove."
    script_path.unlink()
    return True, f"Removed autostart script {script_path}."


def query_autostart() -> tuple[bool, str]:
    try:
        script_path = _startup_folder() / STARTUP_SCRIPT_NAME
    except RuntimeError as exc:
        return False, str(exc)
    return (True, f"Autostart script present at {script_path}.") if script_path.exists() else (False, f"No autostart script at {script_path}.")
