from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_path


def app_data_dir() -> Path:
    return Path(user_data_path("SpeedyType", appauthor=False, roaming=True))


def default_env_path() -> Path:
    return app_data_dir() / ".env"


def default_settings_path() -> Path:
    return app_data_dir() / "settings.json"


def default_pid_path() -> Path:
    return app_data_dir() / "speedytype_daemon.pid"


def default_daemon_log_path() -> Path:
    return app_data_dir() / "speedytype_daemon.log"


def default_latency_log_path() -> Path:
    return app_data_dir() / "speedytype_latency_log.csv"
