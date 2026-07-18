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


def test_windows_standalone_identity_sets_app_user_model_id(monkeypatch):
    calls = []

    class FakeShell32:
        def SetCurrentProcessExplicitAppUserModelID(self, value):
            calls.append(value)
            return 0

    class FakeWindll:
        shell32 = FakeShell32()

    monkeypatch.setattr(_windows_app.ctypes, "windll", FakeWindll(), raising=False)

    _windows_app.configure_standalone_application_identity()

    assert calls == ["SpeedyType.SpeedyType"]


def test_windows_standalone_identity_is_best_effort(monkeypatch):
    class BrokenShell32:
        def SetCurrentProcessExplicitAppUserModelID(self, value):
            raise OSError("shell unavailable")

    class FakeWindll:
        shell32 = BrokenShell32()

    monkeypatch.setattr(_windows_app.ctypes, "windll", FakeWindll(), raising=False)

    assert _windows_app.configure_standalone_application_identity() is None


def test_macos_standalone_identity_does_not_force_accessory_policy():
    appkit = FakeAppKit()

    assert _macos_app.configure_standalone_application_identity(appkit=appkit) is None

    assert appkit.app.calls == []
