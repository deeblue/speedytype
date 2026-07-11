from speedytype.platform._macos_hotkey import ChordState
from speedytype.platform.hotkey import normalize_hotkey_tokens


def test_normalize_hotkey_tokens_migrates_windows_names():
    assert normalize_hotkey_tokens(["Windows", "CTRL", "space", "ctrl"]) == ["cmd", "ctrl", "space"]


def test_chord_state_fires_once_and_releases_on_first_key_up():
    events = []
    state = ChordState({"cmd", "space"}, lambda: events.append("pressed"))

    state.press("cmd")
    state.press("space")
    state.press("space")
    assert events == ["pressed"]
    assert state.release("cmd") is True
    assert state.release("space") is False
