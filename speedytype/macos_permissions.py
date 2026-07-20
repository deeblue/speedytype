from __future__ import annotations

from pathlib import Path
import sys


def keyboard_permission_guidance() -> str:
    python_path = Path(sys.executable).resolve()
    return (
        "請到 macOS 系統設定 > 隱私權與安全性，授權 Accessibility 與 "
        "Input Monitoring。Source release 不會安裝 SpeedyType.app；"
        "請授權啟動 SpeedyType 的 Terminal/iTerm，或目前 release 的 Python："
        f"{python_path}。變更後請重新啟動 daemon。"
    )
