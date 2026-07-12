from __future__ import annotations

import psutil


def is_process_running(pid: int) -> bool:
    try:
        return psutil.Process(pid).is_running()
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True


def terminate_process(pid: int) -> tuple[bool, str]:
    try:
        psutil.Process(pid).terminate()
    except psutil.NoSuchProcess:
        return False, f"Daemon PID {pid} no longer exists."
    except psutil.AccessDenied:
        return False, f"Access denied while stopping daemon PID {pid}."
    return True, f"Stopped daemon PID {pid}."
