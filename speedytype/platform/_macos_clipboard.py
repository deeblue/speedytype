from __future__ import annotations

from dataclasses import dataclass

import pyperclip


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


def send_paste_shortcut() -> None:
    from pynput.keyboard import Controller, Key

    controller = Controller()
    with controller.pressed(Key.cmd):
        controller.press("v")
        controller.release("v")
