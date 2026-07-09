from __future__ import annotations

import time

import keyboard


def wait_until_hotkey_released(hotkey: str, timeout_seconds: float, poll_interval: float = 0.02) -> tuple[str, float]:
    started = time.perf_counter()
    while True:
        if not keyboard.is_pressed(hotkey):
            return "released", time.perf_counter() - started
        elapsed = time.perf_counter() - started
        if elapsed >= timeout_seconds:
            return "timeout", elapsed
        time.sleep(poll_interval)
