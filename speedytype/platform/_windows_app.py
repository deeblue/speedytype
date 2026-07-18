from __future__ import annotations

import ctypes


APP_USER_MODEL_ID = "SpeedyType.SpeedyType"


def configure_daemon_application() -> None:
    configure_standalone_application_identity()


def configure_standalone_application_identity() -> None:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        return None


def activate_window(window) -> None:
    window.show()
    window.raise_()
    window.activateWindow()
