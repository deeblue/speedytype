from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time


class PlatformPermissionError(RuntimeError):
    pass


@dataclass
class ChordState:
    required: set[str]
    callback: object
    held: set[str] = field(default_factory=set)
    active: bool = False

    def press(self, token: str) -> None:
        self.held.add(token)
        if not self.active and self.required <= self.held:
            self.active = True
            self.callback()

    def release(self, token: str) -> bool:
        was_required = self.active and token in self.required
        self.held.discard(token)
        if was_required:
            self.active = False
            return True
        return False


@dataclass
class MacHotkeyHandle:
    listener: object
    released: threading.Event


_current_handle: MacHotkeyHandle | None = None


def _token(key) -> str:
    from pynput.keyboard import Key

    special = {Key.cmd: "cmd", Key.cmd_l: "cmd", Key.cmd_r: "cmd", Key.ctrl: "ctrl", Key.ctrl_l: "ctrl", Key.ctrl_r: "ctrl", Key.alt: "alt", Key.alt_l: "alt", Key.alt_r: "alt", Key.shift: "shift", Key.shift_l: "shift", Key.shift_r: "shift", Key.space: "space"}
    if key in special:
        return special[key]
    char = getattr(key, "char", None)
    return str(char).lower() if char else str(key).replace("Key.", "").lower()


def register_hold_hotkey(hotkey: str, callback):
    global _current_handle
    try:
        from pynput.keyboard import Listener
        released = threading.Event()
        state = ChordState(set(hotkey.split("+")), callback)
        listener = Listener(on_press=lambda key: state.press(_token(key)), on_release=lambda key: released.set() if state.release(_token(key)) else None)
        listener.start()
    except Exception as exc:
        raise PlatformPermissionError("macOS Accessibility/Input Monitoring permission is required.") from exc
    _current_handle = MacHotkeyHandle(listener, released)
    return _current_handle


def remove_hotkey(handle) -> None:
    handle.listener.stop()


def wait_until_hotkey_released(hotkey: str, timeout_seconds: float, poll_interval: float = 0.02) -> tuple[str, float]:
    started = time.perf_counter()
    handle = _current_handle
    if handle is None:
        return "released", 0.0
    released = handle.released.wait(timeout_seconds)
    handle.released.clear()
    elapsed = time.perf_counter() - started
    return ("released" if released else "timeout"), elapsed


def capture_hotkey() -> str:
    try:
        from pynput.keyboard import Listener
        pressed: list[str] = []
        done = threading.Event()
        listener = None

        def on_press(key):
            token = _token(key)
            if token not in pressed:
                pressed.append(token)

        def on_release(_key):
            done.set()
            return False

        listener = Listener(on_press=on_press, on_release=on_release)
        listener.start()
        done.wait()
        listener.join()
        return "+".join(pressed)
    except Exception as exc:
        raise PlatformPermissionError("macOS Accessibility/Input Monitoring permission is required.") from exc
