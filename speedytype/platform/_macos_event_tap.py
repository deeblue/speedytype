from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Callable


class PlatformPermissionError(RuntimeError):
    pass


SPEEDYTYPE_EVENT_MARKER = 0x53545950
FLAG_SHIFT = 1 << 17
FLAG_CTRL = 1 << 18
FLAG_ALT = 1 << 19
FLAG_CMD = 1 << 20
MODIFIER_FLAGS = {
    "cmd": FLAG_CMD,
    "ctrl": FLAG_CTRL,
    "alt": FLAG_ALT,
    "shift": FLAG_SHIFT,
}

KEYCODE_TO_TOKEN = {
    0: "a", 1: "s", 2: "d", 3: "f", 4: "h", 5: "g", 6: "z", 7: "x", 8: "c", 9: "v",
    11: "b", 12: "q", 13: "w", 14: "e", 15: "r", 16: "y", 17: "t", 18: "1", 19: "2",
    20: "3", 21: "4", 22: "6", 23: "5", 24: "=", 25: "9", 26: "7", 27: "-", 28: "8",
    29: "0", 30: "]", 31: "o", 32: "u", 33: "[", 34: "i", 35: "p", 36: "enter", 37: "l",
    38: "j", 39: "'", 40: "k", 41: ";", 42: "\\", 43: ",", 44: "/", 45: "n", 46: "m",
    47: ".", 48: "tab", 49: "space", 50: "`", 51: "backspace", 53: "esc", 64: "f17", 79: "f18",
    80: "f19", 90: "f20", 96: "f5", 97: "f6", 98: "f7", 99: "f3", 100: "f8", 101: "f9",
    103: "f11", 105: "f13", 106: "f16", 107: "f14", 109: "f10", 111: "f12", 113: "f15",
    114: "help", 115: "home", 116: "pageup", 117: "delete", 118: "f4", 119: "end", 120: "f2",
    121: "pagedown", 122: "f1", 123: "left", 124: "right", 125: "down", 126: "up",
}
TOKEN_TO_KEYCODE = {token: code for code, token in KEYCODE_TO_TOKEN.items()}


def token_for_keycode(keycode: int) -> str | None:
    return KEYCODE_TO_TOKEN.get(int(keycode))


@dataclass(frozen=True)
class EventDecision:
    suppress: bool = False
    error: BaseException | None = None


class EventTapState:
    def __init__(self) -> None:
        self.required_flags = 0
        self.terminal_token: str | None = None
        self.callback: Callable[[], None] | None = None
        self.active = False
        self.release_event = threading.Event()
        self.mode = "daemon"
        self.capture_done = threading.Event()
        self.capture_result = ""

    def configure_daemon(self, hotkey: str, callback: Callable[[], None]) -> None:
        tokens = [token.strip().lower() for token in hotkey.split("+") if token.strip()]
        terminals = [token for token in tokens if token not in MODIFIER_FLAGS]
        if len(terminals) != 1 or terminals[0] not in TOKEN_TO_KEYCODE:
            raise ValueError(f"unsupported macOS hotkey: {hotkey}")
        self.required_flags = 0
        for token in tokens:
            self.required_flags |= MODIFIER_FLAGS.get(token, 0)
        self.terminal_token = terminals[0]
        self.callback = callback
        self.active = False
        self.release_event.clear()

    def begin_capture(self) -> None:
        self.mode = "capture"
        self.capture_result = ""
        self.capture_done.clear()

    def end_capture(self) -> None:
        self.mode = "daemon"

    def handle_key(
        self,
        kind: str,
        keycode: int,
        *,
        flags: int,
        autorepeat: bool = False,
        source_marker: int = 0,
    ) -> EventDecision:
        if source_marker == SPEEDYTYPE_EVENT_MARKER:
            return EventDecision()
        token = token_for_keycode(keycode)
        if token is None:
            return EventDecision()
        if self.mode == "capture":
            if kind == "up" and not self.capture_done.is_set():
                modifiers = [name for name in ("cmd", "ctrl", "alt", "shift") if flags & MODIFIER_FLAGS[name]]
                self.capture_result = "+".join([*modifiers, token])
                self.capture_done.set()
            return EventDecision()
        if token != self.terminal_token:
            return EventDecision()
        modifiers_match = (flags & self.required_flags) == self.required_flags
        if kind == "down":
            if not modifiers_match:
                return EventDecision()
            if not self.active and not autorepeat:
                try:
                    if self.callback is not None:
                        self.callback()
                except BaseException as exc:
                    return EventDecision(error=exc)
                self.active = True
                self.release_event.clear()
            return EventDecision(suppress=True)
        if kind == "up" and self.active:
            self.active = False
            self.release_event.set()
            return EventDecision(suppress=True)
        return EventDecision()


class QuartzEventTapBackend:
    def __init__(self) -> None:
        self._run_loop = None
        self._tap = None
        self._thread: threading.Thread | None = None

    def start(self, callback, ready_event: threading.Event, error_box: list[BaseException]) -> None:
        if self._thread and self._thread.is_alive():
            ready_event.set()
            return

        def run() -> None:
            try:
                import Quartz

                mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown) | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)

                def event_callback(_proxy, event_type, event, _refcon):
                    if event_type in {
                        Quartz.kCGEventTapDisabledByTimeout,
                        Quartz.kCGEventTapDisabledByUserInput,
                    }:
                        Quartz.CGEventTapEnable(self._tap, True)
                        return event
                    kind = "down" if event_type == Quartz.kCGEventKeyDown else "up"
                    keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
                    autorepeat = bool(
                        Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventAutorepeat)
                    )
                    marker = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUserData)
                    decision = callback(kind, keycode, int(Quartz.CGEventGetFlags(event)), autorepeat, marker)
                    return None if decision.suppress else event

                self._tap = Quartz.CGEventTapCreate(
                    Quartz.kCGSessionEventTap,
                    Quartz.kCGHeadInsertEventTap,
                    Quartz.kCGEventTapOptionDefault,
                    mask,
                    event_callback,
                    None,
                )
                if self._tap is None:
                    raise PlatformPermissionError(
                        "macOS Accessibility/Input Monitoring permission is required for the keyboard event tap."
                    )
                source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
                self._run_loop = Quartz.CFRunLoopGetCurrent()
                Quartz.CFRunLoopAddSource(self._run_loop, source, Quartz.kCFRunLoopCommonModes)
                Quartz.CGEventTapEnable(self._tap, True)
                ready_event.set()
                Quartz.CFRunLoopRun()
            except BaseException as exc:
                error_box.append(exc)
                ready_event.set()

        self._thread = threading.Thread(target=run, name="speedytype-macos-event-tap", daemon=True)
        self._thread.start()

    def enable(self) -> bool:
        if self._tap is None:
            return False
        import Quartz

        Quartz.CGEventTapEnable(self._tap, True)
        return bool(Quartz.CGEventTapIsEnabled(self._tap))

    def stop(self) -> None:
        if self._run_loop is not None:
            import Quartz

            Quartz.CFRunLoopStop(self._run_loop)
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2.0)
        self._thread = None
        self._tap = None
        self._run_loop = None


class MacEventTapService:
    def __init__(self, backend=None) -> None:
        self.state = EventTapState()
        self.backend = backend or QuartzEventTapBackend()
        self._started = False

    @property
    def is_started(self) -> bool:
        return self._started

    def configure_daemon(self, hotkey: str, callback: Callable[[], None]) -> None:
        self.state.configure_daemon(hotkey, callback)

    def _dispatch(self, kind, keycode, flags, autorepeat, marker) -> EventDecision:
        return self.state.handle_key(
            kind,
            keycode,
            flags=flags,
            autorepeat=autorepeat,
            source_marker=marker,
        )

    def start(self, timeout_seconds: float = 3.0) -> None:
        if self._started:
            return
        ready = threading.Event()
        errors: list[BaseException] = []
        self.backend.start(self._dispatch, ready, errors)
        if not ready.wait(timeout_seconds) or errors:
            self.backend.stop()
            cause = errors[0] if errors else None
            raise PlatformPermissionError("macOS keyboard event tap could not start; check permissions.") from cause
        self._started = True

    def capture_hotkey(self, timeout_seconds: float = 30.0) -> str:
        self.start()
        self.state.begin_capture()
        try:
            if not self.state.capture_done.wait(timeout_seconds):
                raise TimeoutError("macOS hotkey capture timed out")
            return self.state.capture_result
        finally:
            self.state.end_capture()

    def reenable(self) -> bool:
        return bool(self.backend.enable())

    def stop(self) -> None:
        self.backend.stop()
        self._started = False


_SERVICE: MacEventTapService | None = None


def get_event_tap_service() -> MacEventTapService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = MacEventTapService()
    return _SERVICE
