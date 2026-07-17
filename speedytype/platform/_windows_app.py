from __future__ import annotations


def configure_daemon_application() -> None:
    return None


def activate_window(window) -> None:
    window.show()
    window.raise_()
    window.activateWindow()
