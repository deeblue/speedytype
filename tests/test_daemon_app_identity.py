from __future__ import annotations

import speedytype.daemon as daemon


class FakeApplication:
    def __init__(self):
        self.calls = []

    def setApplicationName(self, name):
        self.calls.append(("name", name))

    def setWindowIcon(self, icon):
        self.calls.append(("icon", icon))


def test_daemon_qt_application_uses_speedytype_identity(monkeypatch):
    app = FakeApplication()
    monkeypatch.setattr(daemon, "build_app_icon", lambda: "icon")

    daemon._configure_daemon_qt_application(app)

    assert app.calls == [("name", "SpeedyType"), ("icon", "icon")]
