from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import csv
import os
import secrets
from typing import Iterator


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
    "hybrid_request_count",
    "hybrid_request_seconds",
    "hybrid_fallback_used",
    "hybrid_validation_reasons",
    "usage_scope",
    "stt_model",
    "stt_audio_seconds",
    "llm_input_tokens",
    "llm_output_tokens",
    "llm_total_tokens",
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
    hybrid_request_count: int = 0
    hybrid_request_seconds: float = 0.0
    hybrid_fallback_used: bool = False
    hybrid_validation_reasons: str = ""
    usage_scope: str = "development"
    stt_model: str = "whisper-1"
    stt_audio_seconds: float | None = None
    llm_input_tokens: int | None = None
    llm_output_tokens: int | None = None
    llm_total_tokens: int | None = None

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
        hybrid_request_count: int = 0,
        hybrid_request_seconds: float = 0.0,
        hybrid_fallback_used: bool = False,
        hybrid_validation_reasons: str = "",
        usage_scope: str = "development",
        stt_model: str = "whisper-1",
        stt_audio_seconds: float | None = None,
        llm_input_tokens: int | None = None,
        llm_output_tokens: int | None = None,
        llm_total_tokens: int | None = None,
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
            hybrid_request_count=hybrid_request_count,
            hybrid_request_seconds=hybrid_request_seconds,
            hybrid_fallback_used=hybrid_fallback_used,
            hybrid_validation_reasons=hybrid_validation_reasons,
            usage_scope=usage_scope,
            stt_model=stt_model,
            stt_audio_seconds=stt_audio_seconds,
            llm_input_tokens=llm_input_tokens,
            llm_output_tokens=llm_output_tokens,
            llm_total_tokens=llm_total_tokens,
        )


def _record_row(record: LatencyRecord) -> dict[str, object]:
    return {
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
        "hybrid_request_count": record.hybrid_request_count,
        "hybrid_request_seconds": f"{record.hybrid_request_seconds:.6f}",
        "hybrid_fallback_used": str(record.hybrid_fallback_used).lower(),
        "hybrid_validation_reasons": record.hybrid_validation_reasons,
        "usage_scope": record.usage_scope,
        "stt_model": record.stt_model,
        "stt_audio_seconds": (
            "" if record.stt_audio_seconds is None else f"{record.stt_audio_seconds:.6f}"
        ),
        "llm_input_tokens": "" if record.llm_input_tokens is None else record.llm_input_tokens,
        "llm_output_tokens": "" if record.llm_output_tokens is None else record.llm_output_tokens,
        "llm_total_tokens": "" if record.llm_total_tokens is None else record.llm_total_tokens,
    }


@contextmanager
def _latency_writer_lock(path: Path) -> Iterator[None]:
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a+b") as lock_file:
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _atomic_migrate_and_append(
    path: Path,
    existing_rows: list[dict[str, str]],
    row: dict[str, object],
) -> None:
    temp_path = path.with_name(f"{path.name}.{secrets.token_hex(16)}.tmp")
    try:
        with temp_path.open("x", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=LATENCY_FIELDS)
            writer.writeheader()
            for existing in existing_rows:
                writer.writerow({field: existing.get(field, "") for field in LATENCY_FIELDS})
            writer.writerow(row)
            csv_file.flush()
            os.fsync(csv_file.fileno())
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def append_latency_record(path: Path, record: LatencyRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True) if path.parent != Path(".") else None
    with _latency_writer_lock(path):
        exists = path.exists()
        write_header = not exists
        if exists:
            with path.open("r", encoding="utf-8", newline="") as csv_file:
                first_line = csv_file.readline().rstrip("\r\n")
            write_header = not first_line
            if first_line and first_line.split(",") != LATENCY_FIELDS:
                with path.open("r", encoding="utf-8", newline="") as csv_file:
                    existing_rows = list(csv.DictReader(csv_file))
                _atomic_migrate_and_append(path, existing_rows, _record_row(record))
                return

        with path.open("a", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=LATENCY_FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerow(_record_row(record))
