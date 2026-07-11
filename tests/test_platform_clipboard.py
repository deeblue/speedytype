from speedytype.platform._macos_clipboard import ClipboardSnapshot, restore_clipboard, snapshot_clipboard


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
