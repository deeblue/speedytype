from __future__ import annotations

from pathlib import Path
import os
import plistlib
import subprocess
import sys

from speedytype.paths import default_daemon_log_path, default_env_path


LABEL = "com.speedytype.daemon"


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _uid() -> int:
    return os.getuid()


def _launchctl(*args: str) -> tuple[bool, str]:
    result = subprocess.run(["launchctl", *args], capture_output=True, text=True)
    message = (result.stderr or result.stdout).strip()
    return result.returncode == 0, message


def install_autostart(env_path: str | Path | None = None) -> tuple[bool, str]:
    path = _plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    log = default_daemon_log_path().resolve()
    payload = {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, "-m", "speedytype", "--env", str(Path(env_path or default_env_path()).resolve()), "daemon"],
        "RunAtLoad": True,
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
    }
    path.write_bytes(plistlib.dumps(payload))
    ok, message = _launchctl("bootstrap", f"gui/{_uid()}", str(path))
    return (ok, f"LaunchAgent installed at {path}." if ok else f"launchctl bootstrap failed: {message}")


def uninstall_autostart() -> tuple[bool, str]:
    path = _plist_path()
    if not path.exists():
        return True, f"LaunchAgent not found at {path}; nothing to remove."
    ok, message = _launchctl("bootout", f"gui/{_uid()}", str(path))
    if not ok:
        return False, f"launchctl bootout failed: {message}"
    path.unlink()
    return True, f"Removed LaunchAgent {path}."


def query_autostart() -> tuple[bool, str]:
    path = _plist_path()
    return (True, f"LaunchAgent present at {path}.") if path.exists() else (False, f"No LaunchAgent at {path}.")
