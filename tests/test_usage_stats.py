from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

import pytest

from speedytype.usage_stats import calculate_usage, load_pricing


CSV_FIELDS = [
    "usage_scope",
    "run_label",
    "recording_seconds",
    "hybrid_request_count",
    "stt_model",
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
        writer.writerow(["daily"])
        writer.writerow(["daily", "", "60", "", "whisper-1", "0", "", "", ""])

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
