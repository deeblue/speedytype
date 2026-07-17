from speedytype.platform._macos_clipboard import (
    ClipboardSnapshot,
    restore_clipboard,
    send_paste_shortcut,
    snapshot_clipboard,
)
from speedytype.platform._macos_event_tap import SPEEDYTYPE_EVENT_MARKER


def test_macos_text_snapshot_and_restore(monkeypatch):
    content = {"text": "original"}
    monkeypatch.setattr("speedytype.platform._macos_clipboard.pyperclip.paste", lambda: content["text"])
    monkeypatch.setattr("speedytype.platform._macos_clipboard.pyperclip.copy", lambda value: content.update(text=value))

    snapshot = snapshot_clipboard()
    content["text"] = "replacement"

    assert restore_clipboard(snapshot) == (True, "Clipboard text restored.")
    assert content["text"] == "original"


def test_macos_snapshot_failure_is_safe(monkeypatch):
    monkeypatch.setattr(
        "speedytype.platform._macos_clipboard.pyperclip.paste",
        lambda: (_ for _ in ()).throw(RuntimeError("unavailable")),
    )
    snapshot = snapshot_clipboard()
    assert snapshot.ok is False
    assert restore_clipboard(snapshot)[0] is False


def test_macos_paste_posts_four_marked_quartz_events():
    class Quartz:
        kCGHIDEventTap = 0
        kCGEventSourceUserData = 99
        kCGEventFlagMaskCommand = 1 << 20

        def __init__(self):
            self.posted = []

        def CGEventCreateKeyboardEvent(self, source, keycode, down):
            return {"keycode": keycode, "down": down, "fields": {}, "flags": 0}

        def CGEventSetIntegerValueField(self, event, field, value):
            event["fields"][field] = value

        def CGEventSetFlags(self, event, flags):
            event["flags"] = flags

        def CGEventPost(self, tap, event):
            self.posted.append(event)

    quartz = Quartz()

    send_paste_shortcut(quartz=quartz)

    assert [(event["keycode"], event["down"]) for event in quartz.posted] == [
        (55, True),
        (9, True),
        (9, False),
        (55, False),
    ]
    assert all(event["fields"][99] == SPEEDYTYPE_EVENT_MARKER for event in quartz.posted)
    assert all(event["flags"] == quartz.kCGEventFlagMaskCommand for event in quartz.posted)
