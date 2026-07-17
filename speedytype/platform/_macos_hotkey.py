from __future__ import annotations

from dataclasses import dataclass
import time

from ._macos_event_tap import PlatformPermissionError, get_event_tap_service


@dataclass(frozen=True)
class MacHotkeyHandle:
    service: object


def register_hold_hotkey(hotkey: str, callback):
    service = get_event_tap_service()
    service.configure_daemon(hotkey, callback)
    service.start()
    return MacHotkeyHandle(service)


def remove_hotkey(handle) -> None:
    handle.service.stop()


def wait_until_hotkey_released(
    hotkey: str,
    timeout_seconds: float,
    poll_interval: float = 0.02,
) -> tuple[str, float]:
    del hotkey, poll_interval
    service = get_event_tap_service()
    started = time.perf_counter()
    released = service.state.release_event.wait(timeout_seconds)
    service.state.release_event.clear()
    return ("released" if released else "timeout"), time.perf_counter() - started


def capture_hotkey() -> str:
    service = get_event_tap_service()
    was_started = service.is_started
    try:
        return service.capture_hotkey()
    finally:
        if not was_started:
            service.stop()
