import pytest

from speedytype.platform._macos_clipboard import (
    ClipboardSnapshot,
    PasteTarget,
    capture_paste_target,
    focus_paste_target,
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


def test_macos_capture_paste_target_records_frontmost_application():
    class Application:
        def bundleIdentifier(self):
            return "com.apple.TextEdit"

        def processIdentifier(self):
            return 123

    class Workspace:
        def frontmostApplication(self):
            return Application()

    class AppKit:
        class NSWorkspace:
            @staticmethod
            def sharedWorkspace():
                return Workspace()

    assert capture_paste_target(appkit=AppKit()) == PasteTarget(
        bundle_identifier="com.apple.TextEdit",
        process_identifier=123,
    )


def test_macos_focus_paste_target_activates_captured_application(monkeypatch):
    calls = []

    class RunningApplication:
        def activateWithOptions_(self, options):
            calls.append(("activate", options))
            return True

    class AppKit:
        NSApplicationActivateIgnoringOtherApps = 1

        class NSRunningApplication:
            @staticmethod
            def runningApplicationWithProcessIdentifier_(pid):
                calls.append(("lookup", pid))
                return RunningApplication()

    monkeypatch.setattr(
        "speedytype.platform._macos_clipboard.time.perf_counter",
        iter([10.0, 10.25]).__next__,
    )

    ok, message, seconds = focus_paste_target(
        PasteTarget(bundle_identifier="com.apple.TextEdit", process_identifier=123),
        appkit=AppKit(),
    )

    assert ok is True
    assert "Restored" in message
    assert seconds == pytest.approx(0.25)
    assert calls == [("lookup", 123), ("activate", 1)]


def test_macos_focus_paste_target_fails_closed_when_application_is_gone(monkeypatch):
    class AppKit:
        class NSRunningApplication:
            @staticmethod
            def runningApplicationWithProcessIdentifier_(pid):
                return None

    monkeypatch.setattr(
        "speedytype.platform._macos_clipboard.time.perf_counter",
        iter([20.0, 20.1]).__next__,
    )

    ok, message, seconds = focus_paste_target(
        PasteTarget(bundle_identifier="com.apple.TextEdit", process_identifier=123),
        appkit=AppKit(),
    )

    assert ok is False
    assert "no longer running" in message
    assert seconds == pytest.approx(0.1)
