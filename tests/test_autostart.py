from pathlib import Path
import plistlib

from speedytype.platform import _macos_autostart, _windows_autostart


def test_windows_script_uses_absolute_runtime_paths(monkeypatch, tmp_path):
    startup = tmp_path / "Startup"
    startup.mkdir()
    project = tmp_path / "moved project"
    project.mkdir()
    env = project / ".env"
    monkeypatch.setattr(_windows_autostart, "_startup_folder", lambda: startup)
    monkeypatch.setattr(_windows_autostart, "_project_root", lambda: project)
    monkeypatch.setattr(_windows_autostart, "_pythonw_path", lambda: r"C:\Python\pythonw.exe")

    ok, _ = _windows_autostart.install_autostart(env)

    assert ok
    script = (startup / _windows_autostart.STARTUP_SCRIPT_NAME).read_text(encoding="utf-8")
    assert f'cd /d "{project}"' in script
    assert f'--env "{env.resolve()}"' in script


def test_macos_install_writes_valid_launch_agent(monkeypatch, tmp_path):
    plist_path = tmp_path / "com.speedytype.daemon.plist"
    calls = []
    monkeypatch.setattr(_macos_autostart, "_plist_path", lambda: plist_path)
    monkeypatch.setattr(_macos_autostart, "_launchctl", lambda *args: calls.append(args) or (True, "ok"))
    monkeypatch.setattr(_macos_autostart, "_uid", lambda: 501)

    ok, _ = _macos_autostart.install_autostart(tmp_path / ".env")

    assert ok
    payload = plistlib.loads(plist_path.read_bytes())
    assert payload["RunAtLoad"] is True
    assert payload["ProgramArguments"][1:3] == ["-m", "speedytype"]
    assert calls == [("bootstrap", "gui/501", str(plist_path))]
