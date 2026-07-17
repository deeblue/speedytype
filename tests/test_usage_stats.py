from __future__ import annotations

import csv
import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
import os
import threading

import pytest

from speedytype.usage_stats import (
    LlmPricing,
    PricingData,
    calculate_usage,
    calculate_budget_capacity,
    calculate_monthly_usage,
    load_pricing,
    save_pricing,
)


def test_monthly_usage_uses_local_calendar_month_rollover(tmp_path):
    csv_path = tmp_path / "latency.csv"
    pricing_path = tmp_path / "pricing.json"
    write_pricing(pricing_path)
    write_csv(
        csv_path,
        [
            {"timestamp": "2026-07-31T16:30:00+00:00", "usage_scope": "daily", "recording_seconds": "60"},
            {"timestamp": "2026-07-31T15:30:00+00:00", "usage_scope": "daily", "recording_seconds": "120"},
        ],
    )

    result = calculate_monthly_usage(
        csv_path,
        pricing_path,
        now=datetime(2026, 8, 10, tzinfo=timezone(timedelta(hours=8))),
        local_timezone=timezone(timedelta(hours=8)),
    )

    assert (result.year, result.month) == (2026, 8)
    assert result.usage.stt_calls == 1
    assert result.usage.stt_minutes == Decimal("1")


def test_monthly_usage_skips_missing_naive_and_malformed_timestamps(tmp_path):
    csv_path = tmp_path / "latency.csv"
    pricing_path = tmp_path / "pricing.json"
    write_pricing(pricing_path)
    write_csv(
        csv_path,
        [
            {"timestamp": "", "usage_scope": "daily", "recording_seconds": "60"},
            {"timestamp": "2026-07-10T10:00:00", "usage_scope": "daily", "recording_seconds": "60"},
            {"timestamp": "broken", "usage_scope": "daily", "recording_seconds": "60"},
            {"timestamp": "2026-07-10T10:00:00+00:00", "usage_scope": "daily", "recording_seconds": "60"},
        ],
    )

    with pytest.warns(UserWarning, match="timezone-unsafe"):
        result = calculate_monthly_usage(
            csv_path, pricing_path, now=datetime(2026, 7, 15, tzinfo=timezone.utc), local_timezone=timezone.utc
        )

    assert result.skipped_timestamp_rows == 3
    assert result.usage.stt_calls == 1
    assert sum("timezone-unsafe" in warning for warning in result.usage.warnings) == 3


def test_all_time_usage_still_includes_rows_with_unsafe_timestamps(tmp_path):
    csv_path = tmp_path / "latency.csv"
    pricing_path = tmp_path / "pricing.json"
    write_pricing(pricing_path)
    write_csv(csv_path, [{"timestamp": "broken", "usage_scope": "daily", "recording_seconds": "60"}])

    assert calculate_usage(csv_path, pricing_path).stt_calls == 1


def test_budget_capacity_keeps_exact_uncapped_percentage():
    capacity = calculate_budget_capacity(Decimal("12.50"), Decimal("10.00"))

    assert capacity is not None
    assert capacity.percentage == Decimal("125.00")
    assert capacity.remaining == Decimal("0")
    assert capacity.exceeded == Decimal("2.50")


CSV_FIELDS = [
    "timestamp",
    "usage_scope",
    "run_label",
    "recording_seconds",
    "hybrid_request_count",
    "stt_model",
    "stt_audio_seconds",
    "gemini_seconds",
    "llm_model",
    "llm_input_tokens",
    "llm_output_tokens",
]


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_pricing(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "updated_date": "2026-07-14",
                "currency": "USD",
                "stt": {"whisper-1": {"per_minute": 0.006}},
                "llm": {
                    "gemini-3.1-flash-lite": {
                        "input_per_million": 0.25,
                        "output_per_million": 1.50,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_hybrid_fallback_cost_uses_all_uploaded_audio_seconds(tmp_path: Path) -> None:
    csv_path = tmp_path / "usage.csv"
    pricing_path = tmp_path / "pricing.json"
    write_pricing(pricing_path)
    write_csv(
        csv_path,
        [
            {
                "timestamp": "2026-07-15T00:00:00+00:00",
                "usage_scope": "daily",
                "run_label": "hybrid_fallback",
                "recording_seconds": 60,
                "hybrid_request_count": 3,
                "stt_model": "whisper-1",
                "stt_audio_seconds": 150,
            }
        ],
    )

    summary = calculate_usage(csv_path, pricing_path)

    assert summary.stt_calls == 3
    assert summary.stt_minutes == Decimal("2.5")
    assert summary.stt_cost == Decimal("0.0150")


def editable_pricing(*, stt_price: Decimal = Decimal("0.006")) -> PricingData:
    return PricingData(
        updated_date="2026-07-14",
        currency="USD",
        stt=MappingProxyType({"whisper-1": stt_price}),
        llm=MappingProxyType(
            {
                "gemini-3.1-flash-lite": LlmPricing(
                    input_per_million=Decimal("0.25"),
                    output_per_million=Decimal("1.50"),
                )
            }
        ),
    )


def generated_temp_paths(pricing_path: Path) -> list[Path]:
    return list(pricing_path.parent.glob(f"{pricing_path.name}.*.tmp"))


def test_save_pricing_rejects_negative_price_without_changing_exact_bytes(tmp_path: Path) -> None:
    pricing_path = tmp_path / "pricing.json"
    original = b'{\r\n  "keep": "these exact bytes"\r\n}\r\n'
    pricing_path.write_bytes(original)

    with pytest.raises(ValueError, match="non-negative"):
        save_pricing(pricing_path, editable_pricing(stt_price=Decimal("-0.001")))

    assert pricing_path.read_bytes() == original
    assert generated_temp_paths(pricing_path) == []


def test_save_pricing_updates_date_from_injected_today(tmp_path: Path) -> None:
    pricing_path = tmp_path / "pricing.json"
    write_pricing(pricing_path)

    save_pricing(pricing_path, editable_pricing(), today=date(2030, 2, 3))

    saved = json.loads(pricing_path.read_text(encoding="utf-8"))
    assert saved["updated_date"] == "2030-02-03"
    assert saved["stt"]["whisper-1"]["per_minute"] == 0.006


def test_save_pricing_cleans_partial_temp_and_preserves_original_on_write_failure(
    tmp_path: Path, monkeypatch
) -> None:
    pricing_path = tmp_path / "pricing.json"
    original = b'{"original":true}\n'
    pricing_path.write_bytes(original)

    def partial_write(file, data):
        file.write('{"partial":')
        raise OSError("disk full")

    monkeypatch.setattr("speedytype.usage_stats._write_pricing_json", partial_write)

    with pytest.raises(OSError, match="disk full"):
        save_pricing(pricing_path, editable_pricing())

    assert pricing_path.read_bytes() == original
    assert generated_temp_paths(pricing_path) == []


def test_save_pricing_cleans_temp_and_preserves_original_on_replace_failure(
    tmp_path: Path, monkeypatch
) -> None:
    pricing_path = tmp_path / "pricing.json"
    original = b'{"original":true}\n'
    pricing_path.write_bytes(original)
    real_replace = Path.replace
    attempted_temps = []

    def fail_owned_temp_replace(source: Path, target: Path):
        if target == pricing_path:
            attempted_temps.append(source)
            raise OSError("replace denied")
        return real_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_owned_temp_replace)

    with pytest.raises(OSError, match="replace denied"):
        save_pricing(pricing_path, editable_pricing())

    assert pricing_path.read_bytes() == original
    assert len(attempted_temps) == 1
    assert attempted_temps[0].parent == pricing_path.parent
    assert attempted_temps[0].suffix == ".tmp"
    assert not attempted_temps[0].exists()


def test_save_pricing_cleans_same_inode_when_handle_and_path_ctime_differ(
    tmp_path: Path, monkeypatch
) -> None:
    from speedytype import usage_stats

    pricing_path = tmp_path / "pricing.json"
    original = b'{"original":true}\n'
    pricing_path.write_bytes(original)
    attempted_temps = []
    real_stat = Path.stat

    monkeypatch.setattr(
        usage_stats.os,
        "fstat",
        lambda fd: SimpleNamespace(st_dev=10, st_ino=20, st_ctime_ns=100),
    )

    def path_stat_with_changed_ctime(path: Path, *args, **kwargs):
        if path.suffix == ".tmp":
            return SimpleNamespace(st_dev=10, st_ino=20, st_ctime_ns=200)
        return real_stat(path, *args, **kwargs)

    def fail_replace(source: Path, target: Path):
        attempted_temps.append(source)
        raise OSError("replace denied")

    monkeypatch.setattr(Path, "stat", path_stat_with_changed_ctime)
    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="replace denied"):
        save_pricing(pricing_path, editable_pricing())

    assert pricing_path.read_bytes() == original
    assert len(attempted_temps) == 1
    assert not os.path.exists(attempted_temps[0])


def test_owned_replace_failure_temp_cleanup_survives_repeated_windows_attempts(
    tmp_path: Path, monkeypatch
) -> None:
    pricing_path = tmp_path / "pricing.json"
    original = b'{"original":true}\n'
    pricing_path.write_bytes(original)
    monkeypatch.setattr(
        Path,
        "replace",
        lambda source, target: (_ for _ in ()).throw(OSError("replace denied")),
    )

    for _ in range(50):
        with pytest.raises(OSError, match="replace denied"):
            save_pricing(pricing_path, editable_pricing())

    assert pricing_path.read_bytes() == original
    assert generated_temp_paths(pricing_path) == []


def test_save_pricing_does_not_delete_foreign_temp_swapped_before_cleanup(
    tmp_path: Path, monkeypatch
) -> None:
    pricing_path = tmp_path / "pricing.json"
    original = b'{"original":true}\n'
    foreign = b'{"foreign":true}\n'
    pricing_path.write_bytes(original)
    swapped_paths = []

    def swap_before_failure(source: Path, target: Path):
        swapped_paths.append(source)
        source.unlink()
        source.write_bytes(foreign)
        raise OSError("replace raced")

    monkeypatch.setattr(Path, "replace", swap_before_failure)

    with pytest.raises(OSError, match="replace raced"):
        save_pricing(pricing_path, editable_pricing())

    assert pricing_path.read_bytes() == original
    assert len(swapped_paths) == 1
    assert swapped_paths[0].read_bytes() == foreign


def test_save_pricing_preserves_preexisting_temp_it_does_not_own(tmp_path: Path) -> None:
    pricing_path = tmp_path / "pricing.json"
    temp_path = pricing_path.with_suffix(".json.tmp")
    foreign = b'{"foreign":true}\n'
    write_pricing(pricing_path)
    temp_path.write_bytes(foreign)

    save_pricing(pricing_path, editable_pricing(), today=date(2030, 2, 3))

    assert temp_path.read_bytes() == foreign
    assert load_pricing(pricing_path).updated_date == "2030-02-03"


def test_concurrent_saves_use_distinct_sibling_temp_paths(tmp_path: Path, monkeypatch) -> None:
    from speedytype import usage_stats

    pricing_path = tmp_path / "pricing.json"
    write_pricing(pricing_path)
    real_write = usage_stats._write_pricing_json
    real_replace = Path.replace
    lock = threading.Lock()
    replace_lock = threading.Lock()
    both_writers_entered = threading.Event()
    temp_paths = []
    errors = []

    def synchronized_write(file, data):
        with lock:
            temp_paths.append(Path(file.name))
            if len(temp_paths) == 2:
                both_writers_entered.set()
        if not both_writers_entered.wait(timeout=2):
            raise AssertionError("concurrent save never obtained a distinct temp file")
        real_write(file, data)

    def save_in_thread():
        try:
            save_pricing(pricing_path, editable_pricing())
        except Exception as exc:
            errors.append(exc)

    def serialized_replace(source: Path, target: Path):
        with replace_lock:
            return real_replace(source, target)

    monkeypatch.setattr(usage_stats, "_write_pricing_json", synchronized_write)
    monkeypatch.setattr(Path, "replace", serialized_replace)
    threads = [threading.Thread(target=save_in_thread) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert len(temp_paths) == 2
    assert temp_paths[0] != temp_paths[1]
    assert all(path.parent == pricing_path.parent and path.suffix == ".tmp" for path in temp_paths)
    assert all(not path.exists() for path in temp_paths)


def test_save_pricing_roundtrips_long_decimal_without_binary_float_loss(tmp_path: Path) -> None:
    pricing_path = tmp_path / "pricing.json"
    precise = Decimal("0.123456789012345678901234567890123456789")

    save_pricing(pricing_path, editable_pricing(stt_price=precise), today=date(2030, 2, 3))

    assert precise.to_eng_string() in pricing_path.read_text(encoding="utf-8")
    assert load_pricing(pricing_path).stt["whisper-1"] == precise


@pytest.mark.parametrize(
    "price",
    [
        Decimal("1E+12"),
        Decimal("1.23456789E-12"),
        Decimal("9.99E+999999"),
        Decimal("1E-999999"),
        Decimal("-0"),
        Decimal("123456789012345678901234567890.12345678901234567890"),
    ],
)
def test_save_pricing_serializer_roundtrips_decimal_notation_extremes(
    tmp_path: Path, price: Decimal
) -> None:
    pricing_path = tmp_path / "pricing.json"

    save_pricing(pricing_path, editable_pricing(stt_price=price), today=date(2030, 2, 3))

    text = pricing_path.read_text(encoding="utf-8")
    raw = json.loads(text, parse_float=Decimal, parse_int=Decimal)
    parsed = raw["stt"]["whisper-1"]["per_minute"]
    loaded = load_pricing(pricing_path).stt["whisper-1"]
    assert isinstance(parsed, Decimal)
    assert parsed.as_tuple() == price.as_tuple()
    assert loaded.as_tuple() == price.as_tuple()


def test_save_pricing_serializer_escapes_and_roundtrips_json_strings(tmp_path: Path) -> None:
    pricing_path = tmp_path / "pricing.json"
    stt_model = 'stt"\\line\n\t\x01中文'
    llm_model = 'llm"\\line\r\b模型'
    currency = '\t\x02U"S\\D\n幣\r'
    data = PricingData(
        updated_date="2026-07-14",
        currency=currency,
        stt=MappingProxyType({stt_model: Decimal("1E+3")}),
        llm=MappingProxyType(
            {
                llm_model: LlmPricing(
                    input_per_million=Decimal("1E-3"),
                    output_per_million=Decimal("2.5E+9"),
                )
            }
        ),
    )

    save_pricing(pricing_path, data, today=date(2030, 2, 3))

    text = pricing_path.read_text(encoding="utf-8")
    raw = json.loads(text, parse_float=Decimal, parse_int=Decimal)
    loaded = load_pricing(pricing_path)
    assert raw["currency"] == currency
    assert list(raw["stt"]) == [stt_model]
    assert list(raw["llm"]) == [llm_model]
    assert loaded.currency == currency
    assert loaded.stt[stt_model] == Decimal("1E+3")
    assert loaded.llm[llm_model].input_per_million == Decimal("1E-3")
    assert loaded.llm[llm_model].output_per_million == Decimal("2.5E+9")


def test_save_pricing_rejects_datetime_today_without_changing_original(tmp_path: Path) -> None:
    pricing_path = tmp_path / "pricing.json"
    original = b'{"original":true}\n'
    pricing_path.write_bytes(original)

    with pytest.raises(ValueError, match="exact date"):
        save_pricing(pricing_path, editable_pricing(), today=datetime(2030, 2, 3, 4, 5))

    assert pricing_path.read_bytes() == original


@pytest.mark.parametrize("empty_field", ["stt", "llm"])
def test_save_pricing_rejects_empty_required_price_mapping(
    tmp_path: Path, empty_field: str
) -> None:
    pricing_path = tmp_path / "pricing.json"
    original = b'{"original":true}\n'
    pricing_path.write_bytes(original)
    data = replace(editable_pricing(), **{empty_field: MappingProxyType({})})

    with pytest.raises(ValueError, match="must not be empty"):
        save_pricing(pricing_path, data)

    assert pricing_path.read_bytes() == original


@pytest.mark.parametrize(
    "contents",
    [
        '{"updated_date":"2026-02-30","currency":"USD","stt":{"x":{"per_minute":1}},"llm":{"y":{"input_per_million":1,"output_per_million":1}}}',
        '{"updated_date":"20260715","currency":"USD","stt":{"x":{"per_minute":1}},"llm":{"y":{"input_per_million":1,"output_per_million":1}}}',
        '{"updated_date":"2026-07-15","currency":"USD","stt":{},"llm":{"y":{"input_per_million":1,"output_per_million":1}}}',
        '{"updated_date":"2026-07-15","currency":"USD","stt":{"x":{"per_minute":1}},"llm":{}}',
        '{"updated_date":"2026-07-15","currency":"USD","stt":{" ":{"per_minute":1}},"llm":{"y":{"input_per_million":1,"output_per_million":1}}}',
        '{"updated_date":"2026-07-15","currency":"USD","stt":{"x":{"per_minute":"0.1"}},"llm":{"y":{"input_per_million":1,"output_per_million":1}}}',
        '{"updated_date":"2026-07-15","currency":"USD","stt":{"x":{"per_minute":true}},"llm":{"y":{"input_per_million":1,"output_per_million":1}}}',
        '{"updated_date":"2026-07-15","currency":"USD","stt":{"x":{"per_minute":null}},"llm":{"y":{"input_per_million":1,"output_per_million":1}}}',
    ],
)
def test_load_pricing_rejects_strict_schema_violations(tmp_path: Path, contents: str) -> None:
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError):
        load_pricing(pricing_path)


def test_load_pricing_reads_decimal_schema_and_all_approved_models(tmp_path: Path) -> None:
    pricing = load_pricing(Path(__file__).parents[1] / "pricing.json")

    assert pricing.updated_date == "2026-07-14"
    assert pricing.currency == "USD"
    assert pricing.stt["whisper-1"] == Decimal("0.006")
    assert pricing.llm["gemini-3.1-flash-lite"].input_per_million == Decimal("0.25")
    assert pricing.llm["gemini-3.5-flash"].output_per_million == Decimal("9")
    assert pricing.llm["gpt-5.5"].input_per_million == Decimal("5")
    assert pricing.llm["gpt-5.4-mini"].output_per_million == Decimal("4.5")
    assert pricing.llm["gpt-5.4-nano"].input_per_million == Decimal("0.20")
    assert pricing.llm["MiniMax-M3"].output_per_million == Decimal("1.2")
    with pytest.raises(TypeError):
        pricing.stt["other"] = Decimal("1")


def test_calculate_usage_matches_known_fixture_and_excludes_non_daily_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "latency.csv"
    pricing_path = tmp_path / "pricing.json"
    write_pricing(pricing_path)
    write_csv(
        csv_path,
        [
            {
                "usage_scope": "daily",
                "run_label": "real_voice",
                "recording_seconds": 60,
                "stt_model": "whisper-1",
                "gemini_seconds": 1,
                "llm_model": "gemini-3.1-flash-lite",
                "llm_input_tokens": 1000,
                "llm_output_tokens": 200,
            },
            {
                "usage_scope": "daily",
                "run_label": "",
                "recording_seconds": 30,
                "hybrid_request_count": 1,
                "stt_model": "whisper-1",
                "gemini_seconds": 1,
                "llm_model": "gemini-3.1-flash-lite",
                "llm_input_tokens": 500,
                "llm_output_tokens": 100,
            },
            {
                "usage_scope": "development",
                "run_label": "",
                "recording_seconds": 60,
                "stt_model": "whisper-1",
                "gemini_seconds": 1,
                "llm_model": "gemini-3.1-flash-lite",
                "llm_input_tokens": 9999,
                "llm_output_tokens": 9999,
            },
            {
                "usage_scope": "",
                "run_label": "real_voice",
                "recording_seconds": 60,
                "stt_model": "whisper-1",
                "gemini_seconds": 1,
                "llm_model": "gemini-3.1-flash-lite",
                "llm_input_tokens": 9999,
                "llm_output_tokens": 9999,
            },
            {
                "usage_scope": "",
                "run_label": "",
                "recording_seconds": 30,
                "stt_model": "",
                "gemini_seconds": 0,
                "llm_model": "",
                "llm_input_tokens": "",
                "llm_output_tokens": "",
            },
        ],
    )

    summary = calculate_usage(csv_path, pricing_path)

    assert summary.stt_calls == 3
    assert summary.stt_minutes == Decimal("2.0")
    assert summary.llm_calls == 2
    assert summary.llm_input_tokens == 1500
    assert summary.llm_output_tokens == 300
    assert summary.stt_cost == Decimal("0.012")
    assert summary.llm_cost == Decimal("0.000825")
    assert summary.total_cost == Decimal("0.012825")
    assert summary.legacy_inferred_rows == 1
    assert summary.usage_available is True


@pytest.mark.parametrize(
    ("header", "row"),
    [
        (["timestamp", "run_label", "recording_seconds"], ["legacy", "hybrid", "60"]),
        (
            ["timestamp", "run_label", "recording_seconds", "usage_scope"],
            ["current", "real_voice", "60", "daily"],
        ),
    ],
)
def test_minimal_supported_old_and_new_latency_schemas_are_accepted(
    tmp_path: Path, header: list[str], row: list[str]
) -> None:
    csv_path = tmp_path / "latency.csv"
    pricing_path = tmp_path / "pricing.json"
    write_pricing(pricing_path)
    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(header)
        writer.writerow(row)

    summary = calculate_usage(csv_path, pricing_path)

    assert summary.usage_available is True
    assert summary.stt_calls == 1
    assert summary.stt_minutes == Decimal("1")


@pytest.mark.parametrize(
    "contents",
    [
        b"",
        b"garbage,other\n1,2\n",
        b"timestamp,recording_seconds\nnow,60\n",
        b"run_label,recording_seconds\nhybrid,60\n",
    ],
)
def test_invalid_or_missing_latency_schema_is_unavailable_not_legacy_usage(
    tmp_path: Path, contents: bytes
) -> None:
    csv_path = tmp_path / "latency.csv"
    pricing_path = tmp_path / "pricing.json"
    write_pricing(pricing_path)
    csv_path.write_bytes(contents)

    summary = calculate_usage(csv_path, pricing_path)

    assert summary.usage_available is False
    assert summary.stt_calls == 0
    assert summary.stt_cost is None
    assert summary.total_cost is None
    assert any("Invalid latency CSV schema" in warning for warning in summary.warnings)


@pytest.mark.parametrize(
    "contents",
    [
        b"\xff\xfe\x80",
        (
            b"timestamp,run_label,recording_seconds,usage_scope\n"
            b"ok,real_voice,60,daily\n"
            b"\xff,real_voice,60,daily\n"
        ),
        (
            b"timestamp,run_label,recording_seconds,usage_scope\n"
            + b"ok,real_voice,60,daily\n" * 500
            + b"\xff,real_voice,60,daily\n"
        ),
    ],
)
def test_invalid_utf8_anywhere_in_latency_csv_is_safely_unavailable(
    tmp_path: Path, contents: bytes
) -> None:
    csv_path = tmp_path / "latency.csv"
    pricing_path = tmp_path / "pricing.json"
    write_pricing(pricing_path)
    csv_path.write_bytes(contents)

    summary = calculate_usage(csv_path, pricing_path)

    assert summary.usage_available is False
    assert summary.stt_calls == 0
    assert summary.stt_minutes == Decimal("0")
    assert summary.stt_cost is None
    assert summary.total_cost is None
    assert any("Usage data unavailable" in warning for warning in summary.warnings)


@pytest.mark.parametrize("pricing_contents", [None, "{not-json"])
def test_usage_remains_visible_when_pricing_file_is_unavailable(
    tmp_path: Path, pricing_contents: str | None
) -> None:
    csv_path = tmp_path / "latency.csv"
    pricing_path = tmp_path / "pricing.json"
    write_csv(
        csv_path,
        [
            {
                "usage_scope": "daily",
                "recording_seconds": 60,
                "stt_model": "whisper-1",
                "gemini_seconds": 1,
                "llm_model": "gemini-3.1-flash-lite",
                "llm_input_tokens": 100,
                "llm_output_tokens": 20,
            }
        ],
    )
    if pricing_contents is not None:
        pricing_path.write_text(pricing_contents, encoding="utf-8")

    summary = calculate_usage(csv_path, pricing_path)

    assert summary.stt_calls == 1
    assert summary.stt_minutes == Decimal("1")
    assert summary.llm_input_tokens == 100
    assert summary.stt_cost is None
    assert summary.llm_cost is None
    assert summary.total_cost is None
    assert summary.warnings


def test_unknown_used_model_makes_only_relevant_costs_unavailable(tmp_path: Path) -> None:
    csv_path = tmp_path / "latency.csv"
    pricing_path = tmp_path / "pricing.json"
    write_pricing(pricing_path)
    write_csv(
        csv_path,
        [
            {
                "usage_scope": "daily",
                "recording_seconds": 60,
                "stt_model": "whisper-1",
                "gemini_seconds": 1,
                "llm_model": "unknown-model",
                "llm_input_tokens": 100,
                "llm_output_tokens": 20,
            }
        ],
    )

    summary = calculate_usage(csv_path, pricing_path)

    assert summary.stt_cost == Decimal("0.006")
    assert summary.llm_input_tokens == 100
    assert summary.llm_output_tokens == 20
    assert summary.llm_cost is None
    assert summary.total_cost is None


def test_missing_provider_tokens_are_not_estimated(tmp_path: Path) -> None:
    csv_path = tmp_path / "latency.csv"
    pricing_path = tmp_path / "pricing.json"
    write_pricing(pricing_path)
    write_csv(
        csv_path,
        [
            {
                "usage_scope": "daily",
                "recording_seconds": 30,
                "stt_model": "whisper-1",
                "gemini_seconds": 2,
                "llm_model": "gemini-3.1-flash-lite",
                "llm_input_tokens": "",
                "llm_output_tokens": "",
            }
        ],
    )

    summary = calculate_usage(csv_path, pricing_path)

    assert summary.llm_calls == 1
    assert summary.llm_input_tokens == 0
    assert summary.llm_output_tokens == 0
    assert summary.llm_cost == Decimal("0")


def test_gemini_seconds_fallback_counts_only_accepted_legacy_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "latency.csv"
    pricing_path = tmp_path / "pricing.json"
    write_pricing(pricing_path)
    write_csv(
        csv_path,
        [
            {
                "usage_scope": "daily",
                "run_label": "",
                "recording_seconds": 10,
                "stt_model": "whisper-1",
                "gemini_seconds": 1,
                "llm_model": "",
            },
            {
                "usage_scope": "",
                "run_label": "",
                "recording_seconds": 10,
                "gemini_seconds": 1,
            },
            {
                "usage_scope": "",
                "run_label": "hybrid",
                "recording_seconds": 10,
                "gemini_seconds": 1,
            },
            {
                "usage_scope": "",
                "run_label": "hybrid_fallback",
                "recording_seconds": 10,
                "gemini_seconds": 1,
            },
        ],
    )

    summary = calculate_usage(csv_path, pricing_path)

    assert summary.llm_calls == 3
    assert summary.legacy_inferred_rows == 3


def test_structurally_truncated_row_is_skipped_with_one_warning(tmp_path: Path) -> None:
    csv_path = tmp_path / "latency.csv"
    pricing_path = tmp_path / "pricing.json"
    write_pricing(pricing_path)
    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(CSV_FIELDS)
        writer.writerow(["truncated"])
        writer.writerow(["valid", "daily", "", "60", "", "whisper-1", "", "0", "", "", ""])

    with pytest.warns(UserWarning) as caught:
        summary = calculate_usage(csv_path, pricing_path)

    assert len(caught) == 1
    assert str(caught[0].message) == "Skipped malformed CSV row 2."
    assert summary.stt_calls == 1
    assert summary.stt_minutes == Decimal("1")
    assert len(summary.warnings) == 1


def test_malformed_numeric_row_is_skipped_with_one_warning(tmp_path: Path) -> None:
    csv_path = tmp_path / "latency.csv"
    pricing_path = tmp_path / "pricing.json"
    write_pricing(pricing_path)
    write_csv(
        csv_path,
        [
            {
                "usage_scope": "daily",
                "recording_seconds": "not-a-number",
                "stt_model": "whisper-1",
            },
            {
                "usage_scope": "daily",
                "recording_seconds": 60,
                "stt_model": "whisper-1",
            },
        ],
    )

    with pytest.warns(UserWarning) as caught:
        summary = calculate_usage(csv_path, pricing_path)

    assert len(caught) == 1
    assert str(caught[0].message) == "Skipped malformed CSV row 2."
    assert summary.stt_calls == 1
    assert summary.stt_minutes == Decimal("1")
    assert len(summary.warnings) == 1
