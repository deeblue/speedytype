from pathlib import Path

import speedytype.command_alias as command_alias


def test_windows_wrapper_quotes_paths_and_forwards_all_arguments(monkeypatch, tmp_path):
    install_dir = tmp_path / "alias dir"
    project = tmp_path / "project dir"
    env_path = tmp_path / "config dir" / ".env"
    monkeypatch.setattr(command_alias, "_windows_bin_dir", lambda: install_dir)
    monkeypatch.setattr(command_alias, "_project_root", lambda: project)
    monkeypatch.setattr(command_alias.sys, "executable", r"C:\Python Dir\python.exe")
    monkeypatch.setattr(command_alias, "_ensure_windows_user_path", lambda path: (False, "already present"))

    ok, _ = command_alias._install_windows(env_path)

    assert ok
    content = (install_dir / "speedytype.bat").read_text(encoding="utf-8")
    assert f'cd /d "{project.resolve()}"' in content
    assert '"C:\\Python Dir\\python.exe" -m speedytype' in content
    assert f'--env "{env_path.resolve()}" %*' in content


def test_posix_wrapper_quotes_paths_for_exec_and_forwards_arguments(monkeypatch, tmp_path):
    install_dir = tmp_path / "alias dir"
    project = tmp_path / "project dir"
    env_path = tmp_path / "config dir" / ".env"
    monkeypatch.setattr(command_alias, "_posix_bin_dir", lambda: install_dir)
    monkeypatch.setattr(command_alias, "_project_root", lambda: project)
    monkeypatch.setattr(command_alias.sys, "executable", "/tmp/python dir/python3")
    monkeypatch.setenv("PATH", str(install_dir))
    chmod_modes = []
    original_chmod = Path.chmod
    monkeypatch.setattr(
        Path,
        "chmod",
        lambda self, mode: chmod_modes.append(mode) or original_chmod(self, mode),
    )

    ok, _ = command_alias._install_macos(env_path)

    assert ok
    wrapper = install_dir / "speedytype"
    content = wrapper.read_text(encoding="utf-8")
    assert f"cd '{project.resolve()}'" in content
    assert "exec '/tmp/python dir/python3' -m speedytype" in content
    assert f"--env '{env_path.resolve()}' \"$@\"" in content
    assert chmod_modes == [0o755]


def test_installed_wrapper_never_contains_secret_values(monkeypatch, tmp_path):
    monkeypatch.setattr(command_alias, "_posix_bin_dir", lambda: tmp_path / "bin")
    monkeypatch.setattr(command_alias, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(command_alias.sys, "executable", "/usr/bin/python3")
    monkeypatch.setenv("OPENAI_API_KEY", "sentinel-openai-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "sentinel-gemini-secret")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))

    ok, _ = command_alias._install_macos(tmp_path / ".env")

    assert ok
    content = (tmp_path / "bin" / "speedytype").read_text(encoding="utf-8")
    assert "sentinel-openai-secret" not in content
    assert "sentinel-gemini-secret" not in content


def test_install_command_alias_dispatches_by_platform(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(command_alias, "_install_windows", lambda env: calls.append(("win", env)) or (True, "ok"))
    monkeypatch.setattr(command_alias.sys, "platform", "win32")

    assert command_alias.install_command_alias(tmp_path / ".env") == (True, "ok")
    assert calls == [("win", (tmp_path / ".env").resolve())]


def test_windows_path_is_preserved_and_deduplicated_case_insensitively(monkeypatch):
    values = {"Path": (r"C:\Tools;C:\Users\Me\Alias", command_alias._REG_EXPAND_SZ)}
    notifications = []
    monkeypatch.setattr(command_alias, "_read_user_path", lambda: values["Path"])
    monkeypatch.setattr(
        command_alias,
        "_write_user_path",
        lambda value, kind: values.__setitem__("Path", (value, kind)),
    )
    monkeypatch.setattr(
        command_alias,
        "_broadcast_environment_change",
        lambda: notifications.append(True),
    )

    changed, _ = command_alias._ensure_windows_user_path(Path("c:/users/me/alias/"))

    assert changed is False
    assert values["Path"][0] == r"C:\Tools;C:\Users\Me\Alias"
    assert notifications == []


def test_windows_path_addition_preserves_existing_value_type(monkeypatch):
    values = {"Path": (r"C:\Tools", command_alias._REG_EXPAND_SZ)}
    notifications = []
    monkeypatch.setattr(command_alias, "_read_user_path", lambda: values["Path"])
    monkeypatch.setattr(
        command_alias,
        "_write_user_path",
        lambda value, kind: values.__setitem__("Path", (value, kind)),
    )
    monkeypatch.setattr(
        command_alias,
        "_broadcast_environment_change",
        lambda: notifications.append(True),
    )

    changed, _ = command_alias._ensure_windows_user_path(Path(r"C:\SpeedyType\bin"))

    assert changed is True
    assert values["Path"] == (
        r"C:\Tools;C:\SpeedyType\bin",
        command_alias._REG_EXPAND_SZ,
    )
    assert notifications == [True]


def test_macos_repeat_install_replaces_same_wrapper(monkeypatch, tmp_path):
    install_dir = tmp_path / "bin"
    monkeypatch.setattr(command_alias, "_posix_bin_dir", lambda: install_dir)
    monkeypatch.setattr(command_alias, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(command_alias.sys, "executable", "/usr/bin/python3")
    monkeypatch.setenv("PATH", str(install_dir))

    first = command_alias._install_macos(tmp_path / "first.env")
    second = command_alias._install_macos(tmp_path / "second.env")

    assert first[0] and second[0]
    wrappers = list(install_dir.iterdir())
    assert [path.name for path in wrappers] == ["speedytype"]
    assert "second.env" in wrappers[0].read_text(encoding="utf-8")
    assert "first.env" not in wrappers[0].read_text(encoding="utf-8")


def test_macos_install_prints_exact_path_guidance(monkeypatch, tmp_path):
    monkeypatch.setattr(
        command_alias,
        "_posix_bin_dir",
        lambda: tmp_path / ".local" / "bin",
    )
    monkeypatch.setattr(command_alias, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(command_alias.sys, "executable", "/usr/bin/python3")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    ok, message = command_alias._install_macos(tmp_path / ".env")

    assert ok
    assert 'export PATH="$HOME/.local/bin:$PATH"' in message
    assert "~/.zshrc" in message
    assert "~/.bash_profile" in message


def test_atomic_write_failure_preserves_existing_wrapper(monkeypatch, tmp_path):
    wrapper = tmp_path / "speedytype"
    wrapper.write_text("original", encoding="utf-8")

    def fail_fsync(_descriptor):
        raise OSError("disk full")

    monkeypatch.setattr(command_alias.os, "fsync", fail_fsync)

    try:
        command_alias._atomic_write(wrapper, "replacement", 0o755)
    except OSError as exc:
        assert str(exc) == "disk full"
    else:
        raise AssertionError("expected atomic write to fail")

    assert wrapper.read_text(encoding="utf-8") == "original"
    assert [path.name for path in tmp_path.iterdir()] == ["speedytype"]


def test_windows_broadcast_failure_is_reported_without_secret_text(monkeypatch, tmp_path):
    monkeypatch.setattr(command_alias, "_windows_bin_dir", lambda: tmp_path / "bin")
    monkeypatch.setattr(command_alias, "_project_root", lambda: tmp_path)

    def fail_path_update(_path):
        raise OSError("notification failed")

    monkeypatch.setattr(command_alias, "_ensure_windows_user_path", fail_path_update)
    monkeypatch.setenv("OPENAI_API_KEY", "sentinel-secret")

    ok, message = command_alias._install_windows(tmp_path / ".env")

    assert ok is False
    assert "notification failed" in message
    assert "sentinel-secret" not in message
