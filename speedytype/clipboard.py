from __future__ import annotations

from dataclasses import dataclass, field, replace
import threading
import time

import keyboard
import pyperclip
import win32clipboard


@dataclass(frozen=True)
class PasteResult:
    ok: bool
    message: str
    clipboard_write_seconds: float
    pre_send_wait_seconds: float
    key_send_seconds: float
    post_send_wait_seconds: float
    verification_seconds: float
    clipboard_restored: bool = False
    clipboard_restore_message: str = ""

    @property
    def total_seconds(self) -> float:
        return (
            self.clipboard_write_seconds
            + self.pre_send_wait_seconds
            + self.key_send_seconds
            + self.post_send_wait_seconds
            + self.verification_seconds
        )


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
    """Capture the current clipboard content across all present formats.

    Best-effort: an individual format that fails to read is skipped rather
    than aborting the whole snapshot, since the clipboard may hold formats
    (images, file drops, app-specific data) that are not always readable.
    """
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
    """Restore a previously captured clipboard snapshot.

    Returns (ok, message). Never raises: an unsupported/unwritable format is
    skipped individually so one bad format does not block restoring the rest.
    """
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


def paste_text(text: str, delay_seconds: float = 0.12, post_send_wait_seconds: float = 0.05) -> PasteResult:
    copy_started = time.perf_counter()
    pyperclip.copy(text)
    clipboard_write_seconds = time.perf_counter() - copy_started

    wait_started = time.perf_counter()
    time.sleep(delay_seconds)
    pre_send_wait_seconds = time.perf_counter() - wait_started

    send_started = time.perf_counter()
    try:
        keyboard.send("ctrl+v")
    except Exception as exc:
        key_send_seconds = time.perf_counter() - send_started
        return PasteResult(
            ok=False,
            message=f"已複製但貼上可能失敗，請手動貼上。原因：{exc}",
            clipboard_write_seconds=clipboard_write_seconds,
            pre_send_wait_seconds=pre_send_wait_seconds,
            key_send_seconds=key_send_seconds,
            post_send_wait_seconds=0.0,
            verification_seconds=0.0,
        )
    key_send_seconds = time.perf_counter() - send_started

    post_wait_started = time.perf_counter()
    time.sleep(post_send_wait_seconds)
    measured_post_send_wait_seconds = time.perf_counter() - post_wait_started

    verify_started = time.perf_counter()
    clipboard_ok = pyperclip.paste() == text
    verification_seconds = time.perf_counter() - verify_started
    if not clipboard_ok:
        return PasteResult(
            ok=False,
            message="已複製但貼上可能失敗，請手動貼上。原因：剪貼簿內容在貼上後被其他程式改變。",
            clipboard_write_seconds=clipboard_write_seconds,
            pre_send_wait_seconds=pre_send_wait_seconds,
            key_send_seconds=key_send_seconds,
            post_send_wait_seconds=measured_post_send_wait_seconds,
            verification_seconds=verification_seconds,
        )
    return PasteResult(
        ok=True,
        message="Paste shortcut sent.",
        clipboard_write_seconds=clipboard_write_seconds,
        pre_send_wait_seconds=pre_send_wait_seconds,
        key_send_seconds=key_send_seconds,
        post_send_wait_seconds=measured_post_send_wait_seconds,
        verification_seconds=verification_seconds,
    )


def paste_text_preserving_clipboard(
    text: str,
    delay_seconds: float = 0.12,
    post_send_wait_seconds: float = 0.05,
    restore_delay_seconds: float = 0.3,
    background: bool = True,
) -> PasteResult:
    """Paste `text` like `paste_text`, then restore whatever was on the
    clipboard beforehand so an unrelated copy the user made earlier (code,
    a link, ...) is not permanently lost.

    The restore happens `restore_delay_seconds` after a successful paste, to
    give the target application time to actually read the pasted value
    before the clipboard is overwritten again. By default the wait+restore
    runs on a background thread so it does not add to the caller's measured
    latency (the paste itself has already visibly completed by then); pass
    `background=False` for deterministic synchronous testing.
    """
    snapshot = snapshot_clipboard()
    result = paste_text(text, delay_seconds=delay_seconds, post_send_wait_seconds=post_send_wait_seconds)
    if not result.ok:
        return result

    if background:
        def _restore_after_delay() -> None:
            time.sleep(restore_delay_seconds)
            restore_clipboard(snapshot)

        threading.Thread(target=_restore_after_delay, daemon=True).start()
        return replace(
            result,
            clipboard_restored=False,
            clipboard_restore_message="Clipboard restore scheduled in background.",
        )

    time.sleep(restore_delay_seconds)
    restored_ok, restore_message = restore_clipboard(snapshot)
    return replace(result, clipboard_restored=restored_ok, clipboard_restore_message=restore_message)
