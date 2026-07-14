from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Iterator, Mapping, TextIO
import csv
import json
import os
import warnings as runtime_warnings


MILLION = Decimal("1000000")
MINIMUM_LATENCY_FIELDS = frozenset({"timestamp", "run_label", "recording_seconds"})


@dataclass(frozen=True)
class LlmPricing:
    input_per_million: Decimal | None
    output_per_million: Decimal | None


@dataclass(frozen=True)
class PricingData:
    updated_date: str
    currency: str
    stt: Mapping[str, Decimal | None]
    llm: Mapping[str, LlmPricing]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class UsageSummary:
    stt_calls: int
    stt_minutes: Decimal
    llm_calls: int
    llm_input_tokens: int
    llm_output_tokens: int
    stt_cost: Decimal | None
    llm_cost: Decimal | None
    total_cost: Decimal | None
    stt_models: tuple[str, ...]
    llm_models: tuple[str, ...]
    legacy_inferred_rows: int
    pricing_updated_date: str
    currency: str
    warnings: tuple[str, ...] = ()
    usage_available: bool = True


def _price(value: object, label: str, warning_messages: list[str]) -> Decimal | None:
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError):
        warning_messages.append(f"Invalid price for {label}.")
        return None
    if not price.is_finite() or price < 0:
        warning_messages.append(f"Invalid price for {label}.")
        return None
    return price


def load_pricing(path: str | Path) -> PricingData:
    pricing_path = Path(path)
    with pricing_path.open("r", encoding="utf-8") as pricing_file:
        raw = json.load(pricing_file, parse_float=Decimal, parse_int=Decimal)
    if not isinstance(raw, dict):
        raise ValueError("Pricing data must be a JSON object.")

    updated_date = raw.get("updated_date")
    currency = raw.get("currency")
    stt_raw = raw.get("stt")
    llm_raw = raw.get("llm")
    if not isinstance(updated_date, str) or not updated_date.strip():
        raise ValueError("Pricing updated_date must be a non-empty string.")
    if not isinstance(currency, str) or not currency.strip():
        raise ValueError("Pricing currency must be a non-empty string.")
    if not isinstance(stt_raw, dict) or not isinstance(llm_raw, dict):
        raise ValueError("Pricing stt and llm fields must be objects.")

    warning_messages: list[str] = []
    stt: dict[str, Decimal | None] = {}
    for model, model_data in stt_raw.items():
        if not isinstance(model, str) or not isinstance(model_data, dict):
            raise ValueError("Each STT pricing entry must be a named object.")
        stt[model] = _price(model_data.get("per_minute"), f"STT model {model}", warning_messages)

    llm: dict[str, LlmPricing] = {}
    for model, model_data in llm_raw.items():
        if not isinstance(model, str) or not isinstance(model_data, dict):
            raise ValueError("Each LLM pricing entry must be a named object.")
        llm[model] = LlmPricing(
            input_per_million=_price(
                model_data.get("input_per_million"),
                f"LLM model {model} input",
                warning_messages,
            ),
            output_per_million=_price(
                model_data.get("output_per_million"),
                f"LLM model {model} output",
                warning_messages,
            ),
        )

    return PricingData(
        updated_date=updated_date,
        currency=currency,
        stt=MappingProxyType(stt),
        llm=MappingProxyType(llm),
        warnings=tuple(warning_messages),
    )


def _validated_saved_price(value: object, label: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError(f"{label} must be a finite, non-negative Decimal.")
    return value


def _json_number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def save_pricing(
    path: str | Path,
    data: PricingData,
    today: date | None = None,
) -> None:
    if not isinstance(data, PricingData):
        raise ValueError("Pricing data must be PricingData.")
    if not isinstance(data.currency, str) or not data.currency.strip():
        raise ValueError("Pricing currency must be a non-empty string.")
    if data.warnings:
        raise ValueError("Pricing data contains invalid prices.")
    if not isinstance(data.stt, Mapping) or not isinstance(data.llm, Mapping):
        raise ValueError("Pricing stt and llm fields must be mappings.")

    stt: dict[str, dict[str, int | float]] = {}
    for model, price in data.stt.items():
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Each STT pricing entry must have a non-empty model name.")
        validated = _validated_saved_price(price, f"STT model {model} price")
        stt[model] = {"per_minute": _json_number(validated)}

    llm: dict[str, dict[str, int | float]] = {}
    for model, prices in data.llm.items():
        if not isinstance(model, str) or not model.strip() or not isinstance(prices, LlmPricing):
            raise ValueError("Each LLM pricing entry must have a non-empty model name and prices.")
        input_price = _validated_saved_price(
            prices.input_per_million, f"LLM model {model} input price"
        )
        output_price = _validated_saved_price(
            prices.output_per_million, f"LLM model {model} output price"
        )
        llm[model] = {
            "input_per_million": _json_number(input_price),
            "output_per_million": _json_number(output_price),
        }

    selected_date = date.today() if today is None else today
    if not isinstance(selected_date, date):
        raise ValueError("today must be a date.")
    serialized = {
        "updated_date": selected_date.isoformat(),
        "currency": data.currency.strip(),
        "stt": stt,
        "llm": llm,
    }

    pricing_path = Path(path)
    temp_path = pricing_path.with_suffix(pricing_path.suffix + ".tmp")
    owns_temp = False
    try:
        with temp_path.open("x", encoding="utf-8", newline="\n") as temp_file:
            owns_temp = True
            json.dump(serialized, temp_file, ensure_ascii=False, indent=2)
            temp_file.write("\n")
            temp_file.flush()
            os.fsync(temp_file.fileno())
        temp_path.replace(pricing_path)
        owns_temp = False
    except Exception:
        if owns_temp:
            temp_path.unlink(missing_ok=True)
        raise


def _text_field(row: Mapping[str, object], name: str) -> str:
    raw = row.get(name, "")
    if not isinstance(raw, str):
        raise ValueError(f"CSV field {name} is not text.")
    return raw.strip()


def _is_daily_row(row: Mapping[str, object]) -> tuple[bool, bool]:
    scope = _text_field(row, "usage_scope").lower()
    if scope:
        return scope == "daily", False
    return _text_field(row, "run_label") in {"", "hybrid", "hybrid_fallback"}, True


def _decimal_field(row: Mapping[str, object], name: str) -> Decimal:
    raw = _text_field(row, name)
    if not raw:
        return Decimal("0")
    value = Decimal(raw)
    if not value.is_finite() or value < 0:
        raise InvalidOperation
    return value


def _integer_field(row: Mapping[str, object], name: str) -> int:
    value = _decimal_field(row, name)
    if value != value.to_integral_value():
        raise InvalidOperation
    return int(value)


def _usage_rows(
    csv_file: TextIO,
    warning_messages: list[str],
    availability: list[bool],
) -> Iterator[tuple[int, dict[str, str | None]]]:
    try:
        reader = csv.DictReader(csv_file)
        fieldnames = reader.fieldnames
    except (UnicodeError, csv.Error, OSError) as exc:
        availability[0] = False
        warning_messages.append(f"Usage data unavailable: {exc}")
        return

    if fieldnames is None or not MINIMUM_LATENCY_FIELDS.issubset(fieldnames):
        availability[0] = False
        warning_messages.append("Usage data unavailable: Invalid latency CSV schema.")
        return

    try:
        yield from enumerate(reader, start=2)
    except (UnicodeError, csv.Error, OSError) as exc:
        availability[0] = False
        warning_messages.append(f"Usage data unavailable: {exc}")


def calculate_usage(csv_path: str | Path, pricing_path: str | Path) -> UsageSummary:
    warning_messages: list[str] = []
    try:
        pricing = load_pricing(pricing_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        pricing = None
        warning_messages.append(f"Pricing data unavailable: {exc}")
    else:
        warning_messages.extend(pricing.warnings)

    stt_calls = 0
    stt_minutes = Decimal("0")
    llm_calls = 0
    llm_input_tokens = 0
    llm_output_tokens = 0
    stt_cost: Decimal | None = Decimal("0") if pricing is not None else None
    llm_cost: Decimal | None = Decimal("0") if pricing is not None else None
    stt_models: set[str] = set()
    llm_models: set[str] = set()
    legacy_inferred_rows = 0
    availability = [True]

    latency_path = Path(csv_path)
    try:
        csv_file = latency_path.open("r", encoding="utf-8", newline="")
    except OSError as exc:
        availability[0] = False
        warning_messages.append(f"Usage data unavailable: {exc}")
    else:
        with csv_file:
            for line_number, row in _usage_rows(csv_file, warning_messages, availability):
                try:
                    is_daily, inferred = _is_daily_row(row)
                    if not is_daily:
                        continue
                    recording_seconds = _decimal_field(row, "recording_seconds")
                    request_count = _integer_field(row, "hybrid_request_count")
                    gemini_seconds = _decimal_field(row, "gemini_seconds")
                    input_tokens = _integer_field(row, "llm_input_tokens")
                    output_tokens = _integer_field(row, "llm_output_tokens")
                    stt_model = _text_field(row, "stt_model") or "whisper-1"
                    llm_model = _text_field(row, "llm_model")
                except (InvalidOperation, ValueError):
                    message = f"Skipped malformed CSV row {line_number}."
                    warning_messages.append(message)
                    runtime_warnings.warn(message, UserWarning, stacklevel=2)
                    continue

                if inferred:
                    legacy_inferred_rows += 1

                row_minutes = recording_seconds / Decimal("60")
                stt_calls += request_count if request_count > 0 else 1
                stt_minutes += row_minutes
                stt_models.add(stt_model)
                if stt_cost is not None and row_minutes:
                    price = pricing.stt.get(stt_model) if pricing is not None else None
                    if price is None:
                        stt_cost = None
                        warning_messages.append(f"STT price unavailable for used model {stt_model}.")
                    else:
                        stt_cost += row_minutes * price

                if llm_model or (inferred and gemini_seconds > 0):
                    llm_calls += 1
                llm_input_tokens += input_tokens
                llm_output_tokens += output_tokens
                if llm_model:
                    llm_models.add(llm_model)
                if llm_cost is not None and (input_tokens or output_tokens):
                    price = pricing.llm.get(llm_model) if pricing is not None and llm_model else None
                    if price is None:
                        llm_cost = None
                        warning_messages.append(f"LLM price unavailable for used model {llm_model or '(blank)'}.")
                    elif (input_tokens and price.input_per_million is None) or (
                        output_tokens and price.output_per_million is None
                    ):
                        llm_cost = None
                        warning_messages.append(f"LLM price unavailable for used model {llm_model}.")
                    else:
                        llm_cost += (
                            Decimal(input_tokens) * (price.input_per_million or Decimal("0"))
                            + Decimal(output_tokens) * (price.output_per_million or Decimal("0"))
                        ) / MILLION

    if not availability[0]:
        stt_calls = 0
        stt_minutes = Decimal("0")
        llm_calls = 0
        llm_input_tokens = 0
        llm_output_tokens = 0
        stt_cost = None
        llm_cost = None
        stt_models.clear()
        llm_models.clear()
        legacy_inferred_rows = 0
    total_cost = stt_cost + llm_cost if stt_cost is not None and llm_cost is not None else None
    return UsageSummary(
        stt_calls=stt_calls,
        stt_minutes=stt_minutes,
        llm_calls=llm_calls,
        llm_input_tokens=llm_input_tokens,
        llm_output_tokens=llm_output_tokens,
        stt_cost=stt_cost,
        llm_cost=llm_cost,
        total_cost=total_cost,
        stt_models=tuple(sorted(stt_models)),
        llm_models=tuple(sorted(llm_models)),
        legacy_inferred_rows=legacy_inferred_rows,
        pricing_updated_date=pricing.updated_date if pricing is not None else "",
        currency=pricing.currency if pricing is not None else "",
        warnings=tuple(warning_messages),
        usage_available=availability[0],
    )
