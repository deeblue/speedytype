from __future__ import annotations

from speedytype.platform import _macos_app, _windows_app


class FakeWindow:
    def __init__(self):
        self.calls = []

    def show(self):
        self.calls.append("show")

    def raise_(self):
        self.calls.append("raise")

    def activateWindow(self):
        self.calls.append("activate")


class FakeApplication:
    def __init__(self):
        self.calls = []

    def setActivationPolicy_(self, policy):
        self.calls.append(("policy", policy))

    def activateIgnoringOtherApps_(self, value):
        self.calls.append(("foreground", value))


class FakeAppKit:
    NSApplicationActivationPolicyAccessory = 7

    def __init__(self):
        self.app = FakeApplication()
        self.NSApplication = type(
            "NSApplication",
            (),
            {"sharedApplication": staticmethod(lambda: self.app)},
        )


def test_macos_daemon_uses_accessory_activation_policy():
    appkit = FakeAppKit()

    _macos_app.configure_daemon_application(appkit=appkit)

    assert appkit.app.calls == [("policy", 7)]


def test_macos_window_is_shown_and_activated_in_front():
    appkit = FakeAppKit()
    window = FakeWindow()

    _macos_app.activate_window(window, appkit=appkit)

    assert window.calls == ["show", "raise", "activate"]
    assert appkit.app.calls == [("foreground", True)]


def test_windows_adapter_preserves_existing_window_behavior():
    window = FakeWindow()

    assert _windows_app.configure_daemon_application() is None
    _windows_app.activate_window(window)

    assert window.calls == ["show", "raise", "activate"]
