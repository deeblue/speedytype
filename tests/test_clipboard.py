import time
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="requires the real Windows clipboard")

import win32clipboard
import win32con

from speedytype.clipboard import (
    ClipboardSnapshot,
    paste_text,
    paste_text_preserving_clipboard,
    restore_clipboard,
    snapshot_clipboard,
)


def _open_clipboard_with_retry(max_attempts: int = 10, retry_delay_seconds: float = 0.05) -> None:
    """Back-to-back tests in this file each open/close the real Windows
    clipboard with near-zero gap between them, which is exactly the kind of
    transient contention production code already retries for (see
    speedytype/clipboard.py's _open_clipboard). These test helpers need the
    same tolerance, or the test suite itself is flaky independent of any
    product bug."""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            win32clipboard.OpenClipboard()
            return
        except Exception as exc:
            last_exc = exc
            time.sleep(retry_delay_seconds)
    raise last_exc


def _set_clipboard_text(text: str) -> None:
    _open_clipboard_with_retry()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


def _clear_clipboard() -> None:
    _open_clipboard_with_retry()
    try:
        win32clipboard.EmptyClipboard()
    finally:
        win32clipboard.CloseClipboard()


def _get_clipboard_text():
    _open_clipboard_with_retry()
    try:
        try:
            return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        except Exception:
            return None
    finally:
        win32clipboard.CloseClipboard()


def test_paste_text_restores_target_focus_before_shortcut(monkeypatch):
    events = []
    clipboard = {"text": ""}

    monkeypatch.setattr(
        "speedytype.clipboard.pyperclip.copy",
        lambda text: events.append(("copy", text)) or clipboard.update(text=text),
    )
    monkeypatch.setattr("speedytype.clipboard.pyperclip.paste", lambda: clipboard["text"])
    monkeypatch.setattr(
        "speedytype.clipboard.focus_paste_target",
        lambda target: events.append(("focus", target)) or (True, "focused", 0.123),
    )
    monkeypatch.setattr("speedytype.clipboard.send_paste_shortcut", lambda: events.append(("paste", None)))

    result = paste_text(
        "dictated text",
        delay_seconds=0.0,
        post_send_wait_seconds=0.0,
        paste_target="editor-window",
    )

    assert result.ok
    assert result.focus_window_seconds == pytest.approx(0.123)
    assert events == [
        ("copy", "dictated text"),
        ("focus", "editor-window"),
        ("paste", None),
    ]


def test_paste_text_skips_shortcut_when_captured_target_cannot_be_restored(monkeypatch):
    events = []
    clipboard = {"text": ""}

    monkeypatch.setattr(
        "speedytype.clipboard.pyperclip.copy",
        lambda text: events.append(("copy", text)) or clipboard.update(text=text),
    )
    monkeypatch.setattr("speedytype.clipboard.pyperclip.paste", lambda: clipboard["text"])
    monkeypatch.setattr(
        "speedytype.clipboard.focus_paste_target",
        lambda target: events.append(("focus", target)) or (False, "target vanished", 0.2),
    )
    monkeypatch.setattr(
        "speedytype.clipboard.send_paste_shortcut",
        lambda: (_ for _ in ()).throw(AssertionError("must not paste into an unknown foreground window")),
    )

    result = paste_text(
        "dictated text",
        delay_seconds=0.0,
        post_send_wait_seconds=0.0,
        paste_target="editor-window",
    )

    assert result.ok is False
    assert result.focus_window_seconds == pytest.approx(0.2)
    assert "target vanished" in result.message
    assert events == [("copy", "dictated text"), ("focus", "editor-window")]


def test_snapshot_and_restore_roundtrips_text():
    original = "SpeedyType clipboard guard 原始內容 def foo(): return 42"
    _set_clipboard_text(original)

    snapshot = snapshot_clipboard()
    assert snapshot.ok

    _set_clipboard_text("this will be overwritten by the polished dictation text")
    ok, message = restore_clipboard(snapshot)

    assert ok, message
    assert _get_clipboard_text() == original


def test_restore_of_empty_clipboard_clears_it():
    _clear_clipboard()
    snapshot = snapshot_clipboard()
    assert snapshot.ok
    assert snapshot.formats == {}

    _set_clipboard_text("temporary text")
    ok, message = restore_clipboard(snapshot)

    assert ok, message
    assert _get_clipboard_text() in (None, "")


def test_snapshot_restore_survives_opaque_binary_format_without_crashing():
    custom_format = win32clipboard.RegisterClipboardFormat("SpeedyTypeTestCustomFormat")
    _open_clipboard_with_retry()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(custom_format, b"\x00\x01\x02opaque-binary-payload")
    finally:
        win32clipboard.CloseClipboard()

    snapshot = snapshot_clipboard()
    assert snapshot.ok

    _set_clipboard_text("overwritten by dictation")
    ok, message = restore_clipboard(snapshot)  # must not raise regardless of outcome
    assert isinstance(ok, bool)
    assert isinstance(message, str)


def test_snapshot_read_failure_produces_safe_restore_skip():
    broken = ClipboardSnapshot(ok=False, error="simulated read failure")

    ok, message = restore_clipboard(broken)

    assert ok is False
    assert "simulated read failure" in message


def test_paste_text_preserving_clipboard_restores_original_synchronously(monkeypatch):
    monkeypatch.setattr("speedytype.clipboard.send_paste_shortcut", lambda: None)
    original = "original clipboard content before dictation"
    _set_clipboard_text(original)

    result = paste_text_preserving_clipboard(
        "polished dictation text", restore_delay_seconds=0.05, background=False
    )

    assert result.ok
    assert result.clipboard_restored
    assert _get_clipboard_text() == original


def test_paste_text_preserving_clipboard_background_restores_after_delay(monkeypatch):
    monkeypatch.setattr("speedytype.clipboard.send_paste_shortcut", lambda: None)
    original = "original clipboard content, background path"
    _set_clipboard_text(original)

    result = paste_text_preserving_clipboard(
        "polished dictation text", restore_delay_seconds=0.05, background=True
    )

    assert result.ok
    assert not result.clipboard_restored  # restore is scheduled, not confirmed yet

    import time

    time.sleep(0.3)
    assert _get_clipboard_text() == original
