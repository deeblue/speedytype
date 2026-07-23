from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
import time

import keyboard
import win32clipboard


HWND = ctypes.c_void_p
DWORD = ctypes.c_ulong


@dataclass(frozen=True)
class ClipboardSnapshot:
    ok: bool
    formats: dict[int, object] = field(default_factory=dict)
    error: str = ""


@dataclass(frozen=True)
class PasteTarget:
    hwnd: int


def _open_clipboard(max_attempts: int = 5, retry_delay_seconds: float = 0.05) -> bool:
    for attempt in range(max_attempts):
        try:
            win32clipboard.OpenClipboard()
            return True
        except Exception:
            if attempt == max_attempts - 1:
                return False
            time.sleep(retry_delay_seconds)
    return False


def snapshot_clipboard() -> ClipboardSnapshot:
    if not _open_clipboard():
        return ClipboardSnapshot(ok=False, error="Could not open clipboard for snapshot.")
    formats: dict[int, object] = {}
    try:
        fmt = 0
        while True:
            try:
                fmt = win32clipboard.EnumClipboardFormats(fmt)
            except Exception:
                break
            if fmt == 0:
                break
            try:
                formats[fmt] = win32clipboard.GetClipboardData(fmt)
            except Exception:
                continue
    finally:
        win32clipboard.CloseClipboard()
    return ClipboardSnapshot(ok=True, formats=formats)


def restore_clipboard(snapshot: ClipboardSnapshot) -> tuple[bool, str]:
    if not snapshot.ok:
        return False, f"Skipped restore: snapshot was not captured ({snapshot.error})."
    if not _open_clipboard():
        return False, "Could not open clipboard for restore."
    restored = 0
    try:
        win32clipboard.EmptyClipboard()
        if not snapshot.formats:
            return True, "Original clipboard was empty; cleared clipboard to match."
        for fmt, data in snapshot.formats.items():
            try:
                win32clipboard.SetClipboardData(fmt, data)
                restored += 1
            except Exception:
                continue
    finally:
        win32clipboard.CloseClipboard()
    if restored == 0:
        return False, "Clipboard restore attempted but no formats could be written back."
    return True, f"Clipboard restored ({restored}/{len(snapshot.formats)} formats)."


def send_paste_shortcut() -> None:
    keyboard.send("ctrl+v")


def capture_paste_target() -> PasteTarget | None:
    try:
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = HWND
        hwnd = user32.GetForegroundWindow()
    except Exception:
        return None
    hwnd_value = int(hwnd or 0)
    if hwnd_value <= 0:
        return None
    return PasteTarget(hwnd=hwnd_value)


def focus_paste_target(target: PasteTarget | None) -> tuple[bool, str, float]:
    if target is None:
        return True, "No paste target captured.", 0.0

    started = time.perf_counter()
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.IsWindow.argtypes = [HWND]
        user32.IsWindow.restype = ctypes.c_bool
        user32.ShowWindow.argtypes = [HWND, ctypes.c_int]
        user32.BringWindowToTop.argtypes = [HWND]
        user32.SetForegroundWindow.argtypes = [HWND]
        user32.GetForegroundWindow.restype = HWND
        user32.GetWindowThreadProcessId.argtypes = [HWND, ctypes.c_void_p]
        user32.GetWindowThreadProcessId.restype = DWORD
        user32.AttachThreadInput.argtypes = [DWORD, DWORD, ctypes.c_bool]
        user32.AttachThreadInput.restype = ctypes.c_bool
        kernel32.GetCurrentThreadId.restype = DWORD
        hwnd = int(target.hwnd)
        hwnd_arg = HWND(hwnd)
        if hwnd <= 0 or not user32.IsWindow(hwnd_arg):
            return False, "Captured paste target is no longer a valid window.", time.perf_counter() - started

        SW_RESTORE = 9
        user32.ShowWindow(hwnd_arg, SW_RESTORE)

        current_thread = kernel32.GetCurrentThreadId()
        foreground_hwnd = user32.GetForegroundWindow()
        foreground_thread = user32.GetWindowThreadProcessId(foreground_hwnd, None) if foreground_hwnd else 0
        target_thread = user32.GetWindowThreadProcessId(hwnd_arg, None)
        attached: list[tuple[int, int]] = []
        for other_thread in {foreground_thread, target_thread}:
            if other_thread and other_thread != current_thread:
                if user32.AttachThreadInput(current_thread, other_thread, True):
                    attached.append((current_thread, other_thread))
        try:
            user32.BringWindowToTop(hwnd_arg)
            user32.SetForegroundWindow(hwnd_arg)
        finally:
            for source_thread, other_thread in reversed(attached):
                user32.AttachThreadInput(source_thread, other_thread, False)

        focused_hwnd = int(user32.GetForegroundWindow())
        elapsed = time.perf_counter() - started
        if focused_hwnd != hwnd:
            return False, "Could not restore captured paste target to foreground.", elapsed
        return True, "Restored captured paste target to foreground.", elapsed
    except Exception as exc:
        return False, f"Could not restore paste target: {type(exc).__name__}.", time.perf_counter() - started
