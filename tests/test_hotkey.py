from speedytype.hotkey import wait_until_hotkey_released


def test_wait_until_hotkey_released_returns_released(monkeypatch):
    states = iter([True, True, False])
    elapsed = {"value": 10.0}

    monkeypatch.setattr("speedytype.hotkey.keyboard.is_pressed", lambda hotkey: next(states))
    monkeypatch.setattr("speedytype.hotkey.time.sleep", lambda seconds: elapsed.__setitem__("value", elapsed["value"] + seconds))
    monkeypatch.setattr("speedytype.hotkey.time.perf_counter", lambda: elapsed["value"])

    reason, held_seconds = wait_until_hotkey_released("f9", timeout_seconds=5.0, poll_interval=0.5)

    assert reason == "released"
    assert held_seconds == 1.0


def test_wait_until_hotkey_released_returns_timeout(monkeypatch):
    elapsed = {"value": 20.0}

    monkeypatch.setattr("speedytype.hotkey.keyboard.is_pressed", lambda hotkey: True)
    monkeypatch.setattr("speedytype.hotkey.time.sleep", lambda seconds: elapsed.__setitem__("value", elapsed["value"] + seconds))
    monkeypatch.setattr("speedytype.hotkey.time.perf_counter", lambda: elapsed["value"])

    reason, held_seconds = wait_until_hotkey_released("f9", timeout_seconds=1.0, poll_interval=0.25)

    assert reason == "timeout"
    assert held_seconds == 1.0
