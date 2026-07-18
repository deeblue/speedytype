import threading

import speedytype.hotkey as public_hotkey
from speedytype.platform import _macos_hotkey, _windows_hotkey
from speedytype.platform.hotkey import normalize_hotkey_tokens


def test_normalize_hotkey_tokens_migrates_windows_names():
    assert normalize_hotkey_tokens(["Windows", "CTRL", "space", "ctrl"]) == ["cmd", "ctrl", "space"]


def test_macos_hotkey_public_api_delegates_to_process_service(monkeypatch):
    calls = []

    class Service:
        state = type(
            "State", (), {"release_event": threading.Event(), "active": True}
        )()
        is_started = True

        def configure_daemon(self, hotkey, callback):
            calls.append(("configure", hotkey, callback))

        def start(self):
            calls.append(("start",))

        def stop(self):
            calls.append(("stop",))

        def capture_hotkey(self):
            return "ctrl+shift+r"

    service = Service()
    monkeypatch.setattr(_macos_hotkey, "get_event_tap_service", lambda: service)
    callback = lambda: None

    handle = _macos_hotkey.register_hold_hotkey("f9", callback)
    assert handle.service is service
    assert _macos_hotkey.capture_hotkey() == "ctrl+shift+r"
    _macos_hotkey.remove_hotkey(handle)

    assert calls == [("configure", "f9", callback), ("start",), ("stop",)]


def test_windows_active_state_uses_normalized_combo(monkeypatch):
    checked = []
    monkeypatch.setattr(
        _windows_hotkey.keyboard,
        "is_pressed",
        lambda combo: checked.append(combo) or True,
    )

    assert _windows_hotkey.is_hotkey_active("cmd+f9") is True
    assert checked == ["windows+f9"]


def test_macos_active_state_uses_event_tap_state(monkeypatch):
    service = type("Service", (), {"state": type("State", (), {"active": True})()})()
    monkeypatch.setattr(_macos_hotkey, "get_event_tap_service", lambda: service)

    assert _macos_hotkey.is_hotkey_active("f9") is True


def test_public_hotkey_module_exports_active_state():
    assert callable(public_hotkey.is_hotkey_active)
