from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import csv


LATENCY_FIELDS = [
    "timestamp",
    "run_label",
    "recording_seconds",
    "whisper_seconds",
    "gemini_seconds",
    "llm_provider",
    "llm_model",
    "llm_call_seconds",
    "retry_wait_seconds",
    "focus_window_seconds",
    "clipboard_write_seconds",
    "pre_paste_wait_seconds",
    "key_send_seconds",
    "post_paste_wait_seconds",
    "paste_verification_seconds",
    "paste_seconds",
    "total_tail_latency_seconds",
]


@dataclass(frozen=True)
class LatencyRecord:
    timestamp: str
    run_label: str
    recording_seconds: float
    whisper_seconds: float
    gemini_seconds: float
    llm_provider: str
    llm_model: str
    llm_call_seconds: float
    retry_wait_seconds: float
    focus_window_seconds: float
    clipboard_write_seconds: float
    pre_paste_wait_seconds: float
    key_send_seconds: float
    post_paste_wait_seconds: float
    paste_verification_seconds: float
    paste_seconds: float
    total_tail_latency_seconds: float

    @classmethod
    def create(
        cls,
        recording_seconds: float,
        whisper_seconds: float,
        gemini_seconds: float,
        paste_seconds: float,
        total_tail_latency_seconds: float,
        run_label: str = "",
        llm_provider: str = "",
        llm_model: str = "",
        llm_call_seconds: float | None = None,
        retry_wait_seconds: float = 0.0,
        focus_window_seconds: float = 0.0,
        clipboard_write_seconds: float = 0.0,
        pre_paste_wait_seconds: float = 0.0,
        key_send_seconds: float = 0.0,
        post_paste_wait_seconds: float = 0.0,
        paste_verification_seconds: float = 0.0,
    ) -> "LatencyRecord":
        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(),
            run_label=run_label,
            recording_seconds=recording_seconds,
            whisper_seconds=whisper_seconds,
            gemini_seconds=gemini_seconds,
            llm_provider=llm_provider,
            llm_model=llm_model,
            llm_call_seconds=gemini_seconds if llm_call_seconds is None else llm_call_seconds,
            retry_wait_seconds=retry_wait_seconds,
            focus_window_seconds=focus_window_seconds,
            clipboard_write_seconds=clipboard_write_seconds,
            pre_paste_wait_seconds=pre_paste_wait_seconds,
            key_send_seconds=key_send_seconds,
            post_paste_wait_seconds=post_paste_wait_seconds,
            paste_verification_seconds=paste_verification_seconds,
            paste_seconds=paste_seconds,
            total_tail_latency_seconds=total_tail_latency_seconds,
        )


def append_latency_record(path: Path, record: LatencyRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True) if path.parent != Path(".") else None
    exists = path.exists()
    if exists:
        first_line = path.read_text(encoding="utf-8").splitlines()[0] if path.read_text(encoding="utf-8").splitlines() else ""
        if first_line and first_line.split(",") != LATENCY_FIELDS:
            existing_rows: list[dict[str, str]] = []
            with path.open("r", encoding="utf-8", newline="") as csv_file:
                for row in csv.DictReader(csv_file):
                    existing_rows.append(row)
            with path.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=LATENCY_FIELDS)
                writer.writeheader()
                for row in existing_rows:
                    writer.writerow({field: row.get(field, "") for field in LATENCY_FIELDS})
    with path.open("a", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=LATENCY_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": record.timestamp,
                "run_label": record.run_label,
                "recording_seconds": f"{record.recording_seconds:.6f}",
                "whisper_seconds": f"{record.whisper_seconds:.6f}",
                "gemini_seconds": f"{record.gemini_seconds:.6f}",
                "llm_provider": record.llm_provider,
                "llm_model": record.llm_model,
                "llm_call_seconds": f"{record.llm_call_seconds:.6f}",
                "retry_wait_seconds": f"{record.retry_wait_seconds:.6f}",
                "focus_window_seconds": f"{record.focus_window_seconds:.6f}",
                "clipboard_write_seconds": f"{record.clipboard_write_seconds:.6f}",
                "pre_paste_wait_seconds": f"{record.pre_paste_wait_seconds:.6f}",
                "key_send_seconds": f"{record.key_send_seconds:.6f}",
                "post_paste_wait_seconds": f"{record.post_paste_wait_seconds:.6f}",
                "paste_verification_seconds": f"{record.paste_verification_seconds:.6f}",
                "paste_seconds": f"{record.paste_seconds:.6f}",
                "total_tail_latency_seconds": f"{record.total_tail_latency_seconds:.6f}",
            }
        )
