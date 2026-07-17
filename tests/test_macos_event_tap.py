from __future__ import annotations

import threading

import pytest

from speedytype.platform import _macos_event_tap as tap


def test_fixed_keycode_mapping_does_not_depend_on_input_source():
    assert tap.token_for_keycode(101) == "f9"
    assert tap.token_for_keycode(15) == "r"
    assert tap.token_for_keycode(9999) is None


def test_plain_f9_fires_once_suppresses_repeat_and_releases():
    fired = []
    state = tap.EventTapState()
    state.configure_daemon("f9", lambda: fired.append("record"))

    down = state.handle_key("down", 101, flags=0, autorepeat=False)
    repeat = state.handle_key("down", 101, flags=0, autorepeat=True)
    up = state.handle_key("up", 101, flags=0, autorepeat=False)

    assert fired == ["record"]
    assert (down.suppress, repeat.suppress, up.suppress) == (True, True, True)
    assert state.release_event.is_set()


def test_modified_chord_suppresses_only_terminal_key_and_passes_unrelated_events():
    fired = []
    state = tap.EventTapState()
    state.configure_daemon("ctrl+shift+r", lambda: fired.append(True))
    required = tap.FLAG_CTRL | tap.FLAG_SHIFT

    assert state.handle_key("down", 15, flags=0).suppress is False
    assert state.handle_key("down", 0, flags=required).suppress is False
    assert state.handle_key("down", 15, flags=required).suppress is True
    assert state.handle_key("up", 15, flags=required).suppress is True
    assert fired == [True]


def test_callback_failure_is_fail_open():
    state = tap.EventTapState()
    state.configure_daemon("f9", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    decision = state.handle_key("down", 101, flags=0)

    assert decision.suppress is False
    assert isinstance(decision.error, RuntimeError)


def test_marked_synthetic_event_always_passes_through():
    state = tap.EventTapState()
    state.configure_daemon("cmd+v", lambda: pytest.fail("synthetic paste must not trigger recording"))

    decision = state.handle_key(
        "down",
        9,
        flags=tap.FLAG_CMD,
        source_marker=tap.SPEEDYTYPE_EVENT_MARKER,
    )

    assert decision.suppress is False


def test_capture_suspends_daemon_and_restores_it_after_terminal_release():
    daemon_fired = []
    state = tap.EventTapState()
    state.configure_daemon("f9", lambda: daemon_fired.append(True))
    state.begin_capture()

    state.handle_key("down", 15, flags=tap.FLAG_CTRL | tap.FLAG_SHIFT)
    state.handle_key("up", 15, flags=tap.FLAG_CTRL | tap.FLAG_SHIFT)

    assert state.capture_result == "ctrl+shift+r"
    assert daemon_fired == []
    state.end_capture()
    state.handle_key("down", 101, flags=0)
    assert daemon_fired == [True]


class FakeBackend:
    def __init__(self, *, ready=True):
        self.ready = ready
        self.started = 0
        self.stopped = 0
        self.enabled = 0

    def start(self, callback, ready_event, error_box):
        self.started += 1
        if self.ready:
            ready_event.set()

    def stop(self):
        self.stopped += 1

    def enable(self):
        self.enabled += 1
        return True


def test_service_has_bounded_ready_shutdown_and_reenable():
    backend = FakeBackend()
    service = tap.MacEventTapService(backend=backend)

    service.start(timeout_seconds=0.01)
    assert service.reenable() is True
    service.stop()

    assert (backend.started, backend.enabled, backend.stopped) == (1, 1, 1)


def test_service_ready_timeout_stops_partial_backend():
    backend = FakeBackend(ready=False)
    service = tap.MacEventTapService(backend=backend)

    with pytest.raises(tap.PlatformPermissionError, match="could not start"):
        service.start(timeout_seconds=0.001)
    assert backend.stopped == 1
