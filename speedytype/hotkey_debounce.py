"""Privacy-safe diagnostics for rejected recording-hotkey activations."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import threading


DEBOUNCE_THRESHOLD_MS = 80
_LOG_LOCK = threading.Lock()


def append_rejection_record(
    log_path: Path,
    *,
    platform: str,
    mode: str,
    hotkey: str,
    intent: str,
    held_ms: float,
    cleanup: str,
) -> None:
    """Append one complete diagnostic line; logging is deliberately best effort."""
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "platform": platform,
        "mode": mode,
        "hotkey": hotkey,
        "intent": intent,
        "held_ms": round(float(held_ms), 3),
        "threshold_ms": DEBOUNCE_THRESHOLD_MS,
        "decision": "rejected",
        "cleanup": cleanup,
    }
    line = "HOTKEY_DEBOUNCE " + json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    )
    try:
        with _LOG_LOCK:
            with Path(log_path).open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(line + "\n")
                stream.flush()
    except OSError:
        return
