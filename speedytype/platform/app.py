from __future__ import annotations

import sys


def configure_daemon_application() -> None:
    if sys.platform == "darwin":
        from ._macos_app import configure_daemon_application as implementation
    elif sys.platform == "win32":
        from ._windows_app import configure_daemon_application as implementation
    else:
        return None
    return implementation()


def activate_window(window) -> None:
    if sys.platform == "darwin":
        from ._macos_app import activate_window as implementation
    else:
        from ._windows_app import activate_window as implementation
    implementation(window)
