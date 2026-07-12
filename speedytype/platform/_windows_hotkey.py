from __future__ import annotations

import time

import keyboard


def _windows_combo(hotkey: str) -> str:
    return hotkey.replace("cmd", "windows")


def register_hold_hotkey(hotkey: str, callback):
    return keyboard.add_hotkey(_windows_combo(hotkey), callback, suppress=False)


def remove_hotkey(handle) -> None:
    keyboard.remove_hotkey(handle)


def wait_until_hotkey_released(hotkey: str, timeout_seconds: float, poll_interval: float = 0.02) -> tuple[str, float]:
    started = time.perf_counter()
    while True:
        if not keyboard.is_pressed(_windows_combo(hotkey)):
            return "released", time.perf_counter() - started
        elapsed = time.perf_counter() - started
        if elapsed >= timeout_seconds:
            return "timeout", elapsed
        time.sleep(poll_interval)


def capture_hotkey() -> str:
    return keyboard.read_hotkey(suppress=True).replace("windows", "cmd").replace("win", "cmd")
