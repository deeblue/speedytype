from __future__ import annotations

import sys


class PlatformPermissionError(RuntimeError):
    pass


def normalize_hotkey_tokens(tokens: list[str]) -> list[str]:
    normalized = []
    for raw in tokens:
        token = raw.strip().lower()
        if token in {"win", "windows", "command"}:
            token = "cmd"
        if token and token not in normalized:
            normalized.append(token)
    return normalized


if sys.platform == "win32":
    from ._windows_hotkey import capture_hotkey, register_hold_hotkey, remove_hotkey, wait_until_hotkey_released
elif sys.platform == "darwin":
    from ._macos_hotkey import capture_hotkey, register_hold_hotkey, remove_hotkey, wait_until_hotkey_released
    from ._macos_hotkey import PlatformPermissionError
else:
    raise RuntimeError(f"Unsupported platform for hotkeys: {sys.platform}")

__all__ = ["PlatformPermissionError", "capture_hotkey", "normalize_hotkey_tokens", "register_hold_hotkey", "remove_hotkey", "wait_until_hotkey_released"]
