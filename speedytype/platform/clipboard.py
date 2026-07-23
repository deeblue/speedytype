from __future__ import annotations

import sys

if sys.platform == "win32":
    from ._windows_clipboard import (
        ClipboardSnapshot,
        PasteTarget,
        capture_paste_target,
        focus_paste_target,
        restore_clipboard,
        send_paste_shortcut,
        snapshot_clipboard,
    )
elif sys.platform == "darwin":
    from ._macos_clipboard import (
        ClipboardSnapshot,
        PasteTarget,
        capture_paste_target,
        focus_paste_target,
        restore_clipboard,
        send_paste_shortcut,
        snapshot_clipboard,
    )
else:
    raise RuntimeError(f"Unsupported platform for clipboard operations: {sys.platform}")

__all__ = [
    "ClipboardSnapshot",
    "PasteTarget",
    "capture_paste_target",
    "focus_paste_target",
    "restore_clipboard",
    "send_paste_shortcut",
    "snapshot_clipboard",
]
