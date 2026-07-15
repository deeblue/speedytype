from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

import pytest

from speedytype.latency import LATENCY_FIELDS, LatencyRecord, append_latency_record
from speedytype.usage_stats import calculate_usage


NEW_USAGE_FIELDS = [
    "usage_scope",
    "stt_model",
    "stt_audio_seconds",
    "llm_input_tokens",
    "llm_output_tokens",
    "llm_total_tokens",
]


def _record(**overrides) -> LatencyRecord:
    values = {
        "recording_seconds": 1.0,
        "whisper_seconds": 0.2,
        "gemini_seconds": 0.3,
        "paste_seconds": 0.0,
        "total_tail_latency_seconds": 0.5,
    }
    values.update(overrides)
    return LatencyRecord.create(**values)


def test_append_migrates_old_header_and_preserves_old_values(tmp_path) -> None:
    path = tmp_path / "latency.csv"
    old_fields = [field for field in LATENCY_FIELDS if field not in NEW_USAGE_FIELDS]
    old_row = {field: "" for field in old_fields}
    old_row.update({"timestamp": "legacy-time", "run_label": "hybrid", "recording_seconds": "12.5"})
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=old_fields)
        writer.writeheader()
        writer.writerow(old_row)

    append_latency_record(
        path,
        _record(
            usage_scope="daily",
            stt_model="whisper-1",
            llm_input_tokens=120,
            llm_output_tokens=30,
            llm_total_tokens=150,
        ),
    )

    with path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = list(reader)
        assert reader.fieldnames == LATENCY_FIELDS
    assert rows[0]["timestamp"] == "legacy-time"
    assert rows[0]["recording_seconds"] == "12.5"
    assert all(rows[0][field] == "" for field in NEW_USAGE_FIELDS)
    assert rows[1]["usage_scope"] == "daily"
    assert rows[1]["stt_model"] == "whisper-1"
    assert rows[1]["stt_audio_seconds"] == ""
    assert rows[1]["llm_input_tokens"] == "120"
    assert rows[1]["llm_output_tokens"] == "30"
    assert rows[1]["llm_total_tokens"] == "150"


def _write_legacy_latency_file(path: Path) -> bytes:
    old_fields = [field for field in LATENCY_FIELDS if field not in NEW_USAGE_FIELDS]
    old_row = {field: "" for field in old_fields}
    old_row.update({"timestamp": "legacy-time", "run_label": "hybrid", "recording_seconds": "12.5"})
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=old_fields)
        writer.writeheader()
        writer.writerow(old_row)
    return path.read_bytes()


def test_schema_migration_write_failure_preserves_original_bytes(tmp_path, monkeypatch) -> None:
    path = tmp_path / "latency.csv"
    original = _write_legacy_latency_file(path)
    real_writerow = csv.DictWriter.writerow

    def fail_new_schema_write(writer, rowdict):
        if "usage_scope" in rowdict:
            raise OSError("simulated disk full")
        return real_writerow(writer, rowdict)

    monkeypatch.setattr(csv.DictWriter, "writerow", fail_new_schema_write)

    with pytest.raises(OSError, match="simulated disk full"):
        append_latency_record(path, _record(usage_scope="daily"))

    assert path.read_bytes() == original


def test_schema_migration_replace_failure_preserves_original_bytes(tmp_path, monkeypatch) -> None:
    path = tmp_path / "latency.csv"
    original = _write_legacy_latency_file(path)
    real_replace = Path.replace

    def fail_target_replace(source, target):
        if Path(target) == path:
            raise OSError("simulated replace failure")
        return real_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_target_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        append_latency_record(path, _record(usage_scope="daily"))

    assert path.read_bytes() == original
    assert list(tmp_path.glob("latency.csv.*.tmp")) == []


def test_optional_token_counts_are_written_as_blank(tmp_path) -> None:
    path = tmp_path / "latency.csv"

    append_latency_record(path, _record())

    with path.open("r", encoding="utf-8", newline="") as csv_file:
        row = next(csv.DictReader(csv_file))
    assert row["llm_input_tokens"] == ""
    assert row["llm_output_tokens"] == ""
    assert row["llm_total_tokens"] == ""


def test_append_after_zero_byte_reset_writes_header_and_aggregates(tmp_path) -> None:
    path = tmp_path / "latency.csv"
    path.write_bytes(b"")

    append_latency_record(
        path,
        _record(
            recording_seconds=60,
            usage_scope="daily",
            stt_model="whisper-1",
            llm_provider="gemini",
            llm_model="gemini-3.1-flash-lite",
            llm_input_tokens=100,
            llm_output_tokens=20,
            llm_total_tokens=120,
        ),
    )

    with path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = list(reader)
    assert reader.fieldnames == LATENCY_FIELDS
    assert len(rows) == 1

    pricing_path = Path(__file__).parents[1] / "pricing.json"
    summary = calculate_usage(path, pricing_path)
    assert summary.usage_available is True
    assert summary.stt_calls == 1
    assert summary.stt_minutes == Decimal("1")
    assert summary.llm_calls == 1
    assert summary.llm_input_tokens == 100
    assert summary.llm_output_tokens == 20
