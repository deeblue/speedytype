from __future__ import annotations

from dataclasses import dataclass, field
import time

import keyboard
import win32clipboard


@dataclass(frozen=True)
class ClipboardSnapshot:
    ok: bool
    formats: dict[int, object] = field(default_factory=dict)
    error: str = ""


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
