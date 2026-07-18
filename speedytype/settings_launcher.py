from __future__ import annotations

from pathlib import Path
import sys

from PyQt6.QtWidgets import QApplication

from speedytype.config import load_config
from speedytype.icon import build_app_icon
from speedytype.platform.app import configure_standalone_application_identity
from speedytype.settings_dialog import SettingsDialog


def show_settings_dialog(env_path: str | Path | None = None) -> int:
    config = load_config(env_path, require_api_keys=False)
    configure_standalone_application_identity()
    application = QApplication.instance()
    if application is None:
        application = QApplication(sys.argv)
    application.setApplicationName("SpeedyType")
    application.setWindowIcon(build_app_icon())
    dialog = SettingsDialog(config, env_path, None)
    dialog.exec()
    return 0
