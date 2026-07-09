from __future__ import annotations

from dataclasses import dataclass
import time

import keyboard
import pyperclip


@dataclass(frozen=True)
class PasteResult:
    ok: bool
    message: str
    clipboard_write_seconds: float
    pre_send_wait_seconds: float
    key_send_seconds: float
    post_send_wait_seconds: float
    verification_seconds: float

    @property
    def total_seconds(self) -> float:
        return (
            self.clipboard_write_seconds
            + self.pre_send_wait_seconds
            + self.key_send_seconds
            + self.post_send_wait_seconds
            + self.verification_seconds
        )


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
