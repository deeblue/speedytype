import speedytype.cli as cli
import speedytype.settings_launcher as launcher


def test_settings_launcher_uses_non_strict_config_and_selected_env(
    monkeypatch, tmp_path
):
    calls = []
    config = object()
    env_path = tmp_path / "config.env"

    monkeypatch.setattr(
        launcher,
        "load_config",
        lambda path, require_api_keys: calls.append((path, require_api_keys))
        or config,
    )

    class FakeApplication:
        @staticmethod
        def instance():
            return None

        def __init__(self, argv):
            calls.append(("app", argv))

        def setApplicationName(self, name):
            calls.append(("name", name))

        def setWindowIcon(self, icon):
            calls.append(("icon", icon))

    class FakeDialog:
        def __init__(self, actual_config, actual_env, settings_path):
            calls.append((actual_config, actual_env, settings_path))

        def exec(self):
            calls.append("exec")

    monkeypatch.setattr(launcher, "QApplication", FakeApplication)
    monkeypatch.setattr(launcher, "SettingsDialog", FakeDialog)
    monkeypatch.setattr(
        launcher,
        "configure_standalone_application_identity",
        lambda: calls.append("identity"),
    )
    monkeypatch.setattr(launcher, "build_app_icon", lambda: "icon")

    assert launcher.show_settings_dialog(env_path) == 0
    assert calls[0:2] == [(env_path, False), "identity"]
    assert calls[2][0] == "app"
    assert calls[3:] == [
        ("name", "SpeedyType"),
        ("icon", "icon"),
        (config, env_path, None),
        "exec",
    ]


def test_settings_cli_forwards_explicit_env(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        cli,
        "show_settings_dialog",
        lambda env_path: calls.append(env_path) or 0,
    )
    env_path = tmp_path / "selected.env"

    result = cli.main(["--env", str(env_path), "settings"])

    assert result == 0
    assert calls == [str(env_path)]
