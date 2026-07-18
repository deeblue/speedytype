from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import uuid

from speedytype.paths import default_recordings_dir


RECOVERABLE_STATES = frozenset(
    {"capturing", "captured", "encoding", "ready", "processing", "failed-retained"}
)
_ALLOWED_TRANSITIONS = {
    "capturing": {"captured", "failed-retained"},
    "captured": {"encoding", "processing", "failed-retained"},
    "encoding": {"ready", "failed-retained"},
    "ready": {"processing", "failed-retained"},
    "processing": {"completed", "failed-retained"},
    "failed-retained": {"failed-retained"},
    "completed": set(),
}
_SAFE_CATEGORY = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


@dataclass(frozen=True)
class RecoveryRecord:
    wav_path: Path
    state: str
    recording_id: str
    error_category: str
    metadata_valid: bool = True


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def recording_sidecar_path(wav_path: Path) -> Path:
    wav = Path(wav_path)
    return wav.with_name(wav.name + ".speedytype.json")


def _write_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def create_recording_path(
    prefix: str = "speedytype_", *, directory: Path | None = None
) -> Path:
    target = Path(directory) if directory is not None else default_recordings_dir()
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=prefix, suffix=".wav", dir=target, delete=False) as handle:
        wav_path = Path(handle.name)
    _write_atomic(
        recording_sidecar_path(wav_path),
        {
            "schema_version": 1,
            "recording_id": uuid.uuid4().hex,
            "wav_path": str(wav_path.resolve()),
            "state": "capturing",
            "created_at_utc": _utc_now(),
            "updated_at_utc": _utc_now(),
            "error_category": "",
        },
    )
    return wav_path


def mark_recording(wav_path: Path, state: str, *, error_category: str = "") -> bool:
    sidecar = recording_sidecar_path(Path(wav_path))
    if not sidecar.exists():
        return False
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    current = str(payload.get("state", ""))
    if state not in _ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid recording state transition: {current} -> {state}")
    category = error_category if _SAFE_CATEGORY.fullmatch(error_category) else "UnknownError"
    payload["state"] = state
    payload["updated_at_utc"] = _utc_now()
    payload["error_category"] = category if state == "failed-retained" else ""
    _write_atomic(sidecar, payload)
    return True


def discover_recoverable_recordings(directory: Path | None = None) -> tuple[RecoveryRecord, ...]:
    root = Path(directory) if directory is not None else default_recordings_dir()
    if not root.exists():
        return ()
    records: list[RecoveryRecord] = []
    for sidecar in sorted(root.glob("*.wav.speedytype.json")):
        wav_path = sidecar.with_name(sidecar.name.removesuffix(".speedytype.json"))
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            state = str(payload["state"])
            recording_id = str(payload["recording_id"])
            if state not in RECOVERABLE_STATES:
                continue
            records.append(
                RecoveryRecord(
                    wav_path=wav_path,
                    state=state,
                    recording_id=recording_id,
                    error_category=str(payload.get("error_category", "")),
                )
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            records.append(RecoveryRecord(wav_path, "corrupt", "", "MetadataError", False))
    return tuple(records)
