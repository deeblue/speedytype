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
import secrets
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


def _price(value: object, label: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise ValueError(f"Price for {label} must be a JSON number.")
    price = value
    if not price.is_finite() or price < 0:
        raise ValueError(f"Price for {label} must be finite and non-negative.")
    return price


def _validate_date_string(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 10
        or value[4] != "-"
        or value[7] != "-"
        or not (value[:4] + value[5:7] + value[8:]).isdigit()
    ):
        raise ValueError("Pricing updated_date must use YYYY-MM-DD.")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Pricing updated_date must be a valid calendar date.") from exc
    return value


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON numeric constant: {value}.")


def load_pricing(path: str | Path) -> PricingData:
    pricing_path = Path(path)
    with pricing_path.open("r", encoding="utf-8") as pricing_file:
        raw = json.load(
            pricing_file,
            parse_float=Decimal,
            parse_int=Decimal,
            parse_constant=_reject_json_constant,
        )
    if not isinstance(raw, dict):
        raise ValueError("Pricing data must be a JSON object.")
    if set(raw) != {"updated_date", "currency", "stt", "llm"}:
        raise ValueError("Pricing data has missing or unsupported fields.")

    updated_date = _validate_date_string(raw.get("updated_date"))
    currency = raw.get("currency")
    stt_raw = raw.get("stt")
    llm_raw = raw.get("llm")
    if not isinstance(currency, str) or not currency.strip():
        raise ValueError("Pricing currency must be a non-empty string.")
    if not isinstance(stt_raw, dict) or not isinstance(llm_raw, dict) or not stt_raw or not llm_raw:
        raise ValueError("Pricing stt and llm fields must be non-empty objects.")

    stt: dict[str, Decimal | None] = {}
    for model, model_data in stt_raw.items():
        if (
            not isinstance(model, str)
            or not model.strip()
            or not isinstance(model_data, dict)
            or set(model_data) != {"per_minute"}
        ):
            raise ValueError("Each STT pricing entry must be a named object.")
        stt[model] = _price(model_data["per_minute"], f"STT model {model}")

    llm: dict[str, LlmPricing] = {}
    for model, model_data in llm_raw.items():
        if (
            not isinstance(model, str)
            or not model.strip()
            or not isinstance(model_data, dict)
            or set(model_data) != {"input_per_million", "output_per_million"}
        ):
            raise ValueError("Each LLM pricing entry must be a named object.")
        llm[model] = LlmPricing(
            input_per_million=_price(model_data["input_per_million"], f"LLM model {model} input"),
            output_per_million=_price(model_data["output_per_million"], f"LLM model {model} output"),
        )

    return PricingData(
        updated_date=updated_date,
        currency=currency,
        stt=MappingProxyType(stt),
        llm=MappingProxyType(llm),
        warnings=(),
    )


def _validated_saved_price(value: object, label: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError(f"{label} must be a finite, non-negative Decimal.")
    return value


def _json_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _write_pricing_json(file: TextIO, data: PricingData) -> None:
    file.write("{\n")
    file.write(f'  "updated_date": {_json_string(data.updated_date)},\n')
    file.write(f'  "currency": {_json_string(data.currency)},\n')
    file.write('  "stt": {\n')
    for index, (model, price) in enumerate(data.stt.items()):
        comma = "," if index + 1 < len(data.stt) else ""
        file.write(f"    {_json_string(model)}: {{\n")
        file.write(f'      "per_minute": {price.to_eng_string()}\n')
        file.write(f"    }}{comma}\n")
    file.write("  },\n")
    file.write('  "llm": {\n')
    for index, (model, prices) in enumerate(data.llm.items()):
        comma = "," if index + 1 < len(data.llm) else ""
        file.write(f"    {_json_string(model)}: {{\n")
        file.write(f'      "input_per_million": {prices.input_per_million.to_eng_string()},\n')
        file.write(f'      "output_per_million": {prices.output_per_million.to_eng_string()}\n')
        file.write(f"    }}{comma}\n")
    file.write("  }\n")
    file.write("}\n")


def _file_identity(stat_result: os.stat_result) -> tuple[int, int]:
    return (stat_result.st_dev, stat_result.st_ino)


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
    if not data.stt or not data.llm:
        raise ValueError("Pricing stt and llm mappings must not be empty.")
    _validate_date_string(data.updated_date)

    stt: dict[str, Decimal] = {}
    for model, price in data.stt.items():
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Each STT pricing entry must have a non-empty model name.")
        validated = _validated_saved_price(price, f"STT model {model} price")
        stt[model] = validated

    llm: dict[str, LlmPricing] = {}
    for model, prices in data.llm.items():
        if not isinstance(model, str) or not model.strip() or not isinstance(prices, LlmPricing):
            raise ValueError("Each LLM pricing entry must have a non-empty model name and prices.")
        input_price = _validated_saved_price(
            prices.input_per_million, f"LLM model {model} input price"
        )
        output_price = _validated_saved_price(
            prices.output_per_million, f"LLM model {model} output price"
        )
        llm[model] = LlmPricing(input_price, output_price)

    selected_date = date.today() if today is None else today
    if type(selected_date) is not date:
        raise ValueError("today must be an exact date, not a datetime or other type.")
    serialized = PricingData(
        updated_date=selected_date.isoformat(),
        currency=data.currency,
        stt=MappingProxyType(stt),
        llm=MappingProxyType(llm),
    )

    pricing_path = Path(path)
    temp_path = pricing_path.with_name(
        f"{pricing_path.name}.{secrets.token_hex(16)}.tmp"
    )
    owned_identity: tuple[int, int] | None = None
    try:
        with temp_path.open("x", encoding="utf-8", newline="\n") as temp_file:
            try:
                _write_pricing_json(temp_file, serialized)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            finally:
                owned_identity = _file_identity(os.fstat(temp_file.fileno()))
        temp_path.replace(pricing_path)
        owned_identity = None
    except Exception:
        if owned_identity is not None:
            try:
                current_identity = _file_identity(temp_path.stat())
            except OSError:
                pass
            else:
                if current_identity == owned_identity:
                    try:
                        temp_path.unlink()
                    except FileNotFoundError:
                        pass
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
