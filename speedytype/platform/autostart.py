from __future__ import annotations

import sys

if sys.platform == "win32":
    from ._windows_autostart import install_autostart, query_autostart, uninstall_autostart
elif sys.platform == "darwin":
    from ._macos_autostart import install_autostart, query_autostart, uninstall_autostart
else:
    raise RuntimeError(f"Unsupported platform for autostart: {sys.platform}")

__all__ = ["install_autostart", "query_autostart", "uninstall_autostart"]
