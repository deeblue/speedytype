from pathlib import Path

import speedytype.paths as paths


def test_default_paths_share_platform_data_directory(monkeypatch, tmp_path):
    expected = tmp_path / "SpeedyType"
    monkeypatch.setattr(paths, "user_data_path", lambda *args, **kwargs: expected)

    assert paths.app_data_dir() == expected
    assert paths.default_env_path() == expected / ".env"
    assert paths.default_settings_path() == expected / "settings.json"
    assert paths.default_pid_path() == expected / "speedytype_daemon.pid"
    assert paths.default_daemon_log_path() == expected / "speedytype_daemon.log"
    assert paths.default_latency_log_path() == expected / "speedytype_latency_log.csv"


def test_path_lookup_does_not_create_directory(monkeypatch, tmp_path):
    expected = tmp_path / "missing" / "SpeedyType"
    monkeypatch.setattr(paths, "user_data_path", lambda *args, **kwargs: expected)

    assert paths.app_data_dir() == expected
    assert not expected.exists()


def test_default_pricing_path_points_to_repository_root():
    expected = Path(paths.__file__).resolve().parent.parent / "pricing.json"

    assert paths.default_pricing_path() == expected
