from __future__ import annotations

from dataclasses import dataclass

import pyperclip

from ._macos_event_tap import SPEEDYTYPE_EVENT_MARKER


@dataclass(frozen=True)
class ClipboardSnapshot:
    ok: bool
    text: str = ""
    error: str = ""


def snapshot_clipboard() -> ClipboardSnapshot:
    try:
        return ClipboardSnapshot(ok=True, text=pyperclip.paste())
    except Exception as exc:
        return ClipboardSnapshot(ok=False, error=str(exc))


def restore_clipboard(snapshot: ClipboardSnapshot) -> tuple[bool, str]:
    if not snapshot.ok:
        return False, f"Skipped restore: snapshot was not captured ({snapshot.error})."
    try:
        pyperclip.copy(snapshot.text)
    except Exception as exc:
        return False, f"Could not restore clipboard text: {exc}"
    return True, "Clipboard text restored."


def send_paste_shortcut(*, quartz=None) -> None:
    if quartz is None:
        import Quartz as quartz

    for keycode, is_down in ((55, True), (9, True), (9, False), (55, False)):
        event = quartz.CGEventCreateKeyboardEvent(None, keycode, is_down)
        quartz.CGEventSetIntegerValueField(
            event,
            quartz.kCGEventSourceUserData,
            SPEEDYTYPE_EVENT_MARKER,
        )
        quartz.CGEventSetFlags(event, quartz.kCGEventFlagMaskCommand)
        quartz.CGEventPost(quartz.kCGHIDEventTap, event)
