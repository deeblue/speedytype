from __future__ import annotations

from pathlib import Path

from speedytype import macos_permissions


def test_keyboard_permission_guidance_names_source_release_python(monkeypatch):
    executable = "/Users/example/Applications/SpeedyType/.venv/bin/python"
    monkeypatch.setattr(
        macos_permissions.sys,
        "executable",
        executable,
    )

    message = macos_permissions.keyboard_permission_guidance()

    assert "Source release 不會安裝 SpeedyType.app" in message
    assert "Terminal/iTerm" in message
    assert str(Path(executable).resolve()) in message
    assert "Accessibility" in message
    assert "Input Monitoring" in message


def test_daemon_and_settings_use_shared_keyboard_permission_guidance():
    root = Path(__file__).resolve().parent.parent

    assert "keyboard_permission_guidance()" in (root / "speedytype" / "daemon.py").read_text(
        encoding="utf-8"
    )
    assert "keyboard_permission_guidance()" in (
        root / "speedytype" / "settings_dialog.py"
    ).read_text(encoding="utf-8")
