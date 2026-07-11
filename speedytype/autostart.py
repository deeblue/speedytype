from __future__ import annotations

from pathlib import Path
import os
import sys


STARTUP_SCRIPT_NAME = "SpeedyTypeDaemon.bat"


def _pythonw_path() -> str:
    """Prefer pythonw.exe (no console window) if it sits next to the
    interpreter currently running this process; fall back to sys.executable.
    """
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return str(candidate) if candidate.exists() else sys.executable


def _startup_folder() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA environment variable is not set; cannot locate the Startup folder.")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def install_autostart(env_path: str = ".env") -> tuple[bool, str]:
    """Write a small .bat file into the current user's Startup folder so the
    daemon launches at every logon, with no admin/elevation required.

    (Windows Task Scheduler was tried first and is the more commonly
    documented option, but `schtasks /Create` returned "Access is denied"
    on this machine even for a plain per-user ONLOGON trigger, which looks
    like a local security policy restriction rather than something fixable
    in this code. The Startup folder is the standard fallback and does not
    require elevation on any standard Windows account.)

    Not installed automatically; the user must explicitly run
    `python -m speedytype install-autostart`.
    """
    project_dir = Path(__file__).resolve().parents[1]
    pythonw = _pythonw_path()
    try:
        startup_dir = _startup_folder()
    except RuntimeError as exc:
        return False, str(exc)
    if not startup_dir.exists():
        return False, f"Startup folder not found at {startup_dir}."

    script_path = startup_dir / STARTUP_SCRIPT_NAME
    # pythonw.exe has no console, so sys.stdout/sys.stderr are None unless a
    # log file is redirected here; without this the daemon used to crash on
    # its first startup print (safe_print() now also tolerates that, but the
    # log redirect is kept so autostart failures stay diagnosable).
    script_path.write_text(
        "@echo off\r\n"
        f'cd /d "{project_dir}"\r\n'
        "set PYTHONIOENCODING=utf-8\r\n"
        f'"{pythonw}" -m speedytype --env "{env_path}" daemon >> speedytype_daemon.log 2>&1\r\n',
        encoding="utf-8",
    )
    return True, (
        f"Autostart script written to {script_path}. It will run at next logon. "
        "Disable any time with: python -m speedytype uninstall-autostart "
        "(or just delete that file)."
    )


def uninstall_autostart() -> tuple[bool, str]:
    try:
        startup_dir = _startup_folder()
    except RuntimeError as exc:
        return False, str(exc)
    script_path = startup_dir / STARTUP_SCRIPT_NAME
    if not script_path.exists():
        return True, f"Autostart script not found at {script_path}; nothing to remove."
    script_path.unlink()
    return True, f"Removed autostart script {script_path}."


def query_autostart() -> tuple[bool, str]:
    try:
        startup_dir = _startup_folder()
    except RuntimeError as exc:
        return False, str(exc)
    script_path = startup_dir / STARTUP_SCRIPT_NAME
    if script_path.exists():
        return True, f"Autostart script present at {script_path}:\n{script_path.read_text(encoding='utf-8')}"
    return False, f"No autostart script at {script_path}."
