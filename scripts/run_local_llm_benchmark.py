from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from speedytype.config import load_config
from speedytype.llm import call_gemini_polisher, call_ollama_polisher


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    category: str
    text: str


CASES = (
    BenchmarkCase(
        "short",
        "phase2",
        "呃,我們下週一,啊不對,下週三要開會,請 TPE 團隊同步 BIOS 狀態。",
    ),
    BenchmarkCase(
        "medium",
        "phase2",
        "那個,我今天想先確認三件事 第一,Firmware 的 NPI 進度要更新 第二,QA 要在週五前回報 第三,我們下週一,不對,下週三要跟 BJ 團隊開會",
    ),
    BenchmarkCase(
        "long",
        "phase2",
        "這段是SpeedyType的長距測試 我們原本打算下週一發BIOS測試版 不對,應該是下週三發Firmware測試版 請TPE團隊先確認USB和Thunderbolt的相容性 然後QA在NPI會議前整理API測試結果 最後,BJ團隊協助確認使用者回饋",
    ),
    BenchmarkCase(
        "numbers_repeated_english",
        "number_regression",
        "123測試測試 123測試測試 123 test 123 test",
    ),
)

CANDIDATES = (
    {"provider": "gemini", "model": "gemini-3.1-flash-lite", "thinking": "minimal"},
    {"provider": "ollama", "model": "gemma4:12b"},
    {"provider": "ollama", "model": "gemma4:26b"},
)

DEFAULT_OUTPUT_PATH = Path("local_llm_benchmark_results.jsonl")
EXPLANATORY_PREFIXES = ("以下是", "修飾後", "您好", "Here is")


def quality_flags(case: BenchmarkCase, output: str) -> dict[str, bool]:
    filler_ok = all(filler not in output for filler in ("呃", "那個", "就是說"))
    extra_ok = not any(prefix in output for prefix in EXPLANATORY_PREFIXES)

    if case.name == "numbers_repeated_english":
        terms_ok = "123" in output and ("test" in output.lower() or "測試" in output)
        residual = re.sub(r"123|測試|\btest\b", "", output, flags=re.IGNORECASE)
        extra_ok = extra_ok and re.search(r"\w", residual) is None
        correction_ok = True
        bullets_ok = True
    elif case.name == "short":
        correction_ok = all(term not in output for term in ("啊不對", "不對", "下週一")) and "下週三" in output
        terms_ok = all(term in output for term in ("TPE 團隊", "BIOS"))
        bullets_ok = True
    elif case.name == "medium":
        correction_ok = all(term not in output for term in ("啊不對", "不對", "下週一")) and "下週三" in output
        terms_ok = all(term in output for term in ("Firmware", "NPI", "QA", "BJ 團隊"))
        bullets_ok = True
    else:
        correction_ok = (
            all(term not in output for term in ("啊不對", "不對", "下週一", "BIOS 測試版"))
            and "下週三" in output
            and "Firmware" in output
        )
        terms_ok = all(
            term in output
            for term in ("Firmware", "TPE", "USB", "Thunderbolt", "QA", "NPI", "API", "BJ")
        )
        bullets_ok = any(marker in output for marker in ("-", "*", "1."))

    return {
        "filler_ok": filler_ok,
        "correction_ok": correction_ok,
        "terms_ok": terms_ok,
        "bullets_ok": bullets_ok,
        "extra_ok": extra_ok,
        "overall_ok": filler_ok and correction_ok and terms_ok and bullets_ok and extra_ok,
    }


def _identity(candidate: dict[str, str], case: BenchmarkCase, mode: str, repetition: int) -> tuple[str, str, str, str, int]:
    return candidate["provider"], candidate["model"], case.name, mode, repetition


def expected_identities(repetitions: int) -> set[tuple[str, str, str, str, int]]:
    expected = set()
    for candidate in CANDIDATES:
        if candidate["provider"] == "ollama":
            expected.add(_identity(candidate, CASES[0], "cold", 1))
        for case in CASES:
            for repetition in range(1, repetitions + 1):
                expected.add(_identity(candidate, case, "warm", repetition))
    return expected


def summarize_results(output_path: Path, *, repetitions: int) -> int:
    expected = expected_identities(repetitions)
    actual: list[tuple[str, str, str, str, int]] = []
    parse_errors = 0
    try:
        lines = output_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        lines = []
        parse_errors = 1

    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            actual.append(
                (
                    record["provider"],
                    record["model"],
                    record["case"],
                    record["mode"],
                    record["repetition"],
                )
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            parse_errors += 1

    unique = set(actual)
    duplicates = len(actual) - len(unique)
    missing = len(expected - unique)
    unexpected = len(unique - expected)
    complete = parse_errors == duplicates == missing == unexpected == 0
    print(f"records={len(actual)} expected={len(expected)} unique={len(unique)}")
    print(
        f"parse_errors={parse_errors} duplicates={duplicates} "
        f"missing={missing} unexpected={unexpected}"
    )
    print(f"complete={str(complete).lower()}")
    return 0 if complete else 1


def stop_ollama_model(model: str) -> None:
    subprocess.run(["ollama", "stop", model], check=True, capture_output=True, text=True)


def ollama_ps() -> str:
    return subprocess.run(
        ["ollama", "ps"], check=True, capture_output=True, text=True
    ).stdout.strip()


def run_candidate(
    config: Any,
    candidate: dict[str, str],
    case: BenchmarkCase,
    mode: str,
    repetition: int,
) -> dict[str, Any]:
    identity = _identity(candidate, case, mode, repetition)
    record: dict[str, Any] = {
        "provider": identity[0],
        "model": identity[1],
        "case": identity[2],
        "category": case.category,
        "mode": identity[3],
        "repetition": identity[4],
        "identity": list(identity),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        if candidate["provider"] == "gemini":
            result = call_gemini_polisher(
                case.text,
                config,
                model=candidate["model"],
                thinking_level=candidate["thinking"],
            )
        else:
            result = call_ollama_polisher(case.text, config, model=candidate["model"])

        record.update(
            ok=True,
            output=result.text,
            llm_call_seconds=result.llm_call_seconds,
            retry_wait_seconds=result.retry_wait_seconds,
            retry_count=result.retry_count,
            usage=result.usage.raw,
            quality=quality_flags(case, result.text),
        )
        if candidate["provider"] == "ollama":
            raw = result.raw_response
            eval_seconds = raw.get("eval_duration", 0) / 1_000_000_000
            output_tokens = raw.get("eval_count", result.usage.output_tokens)
            record.update(
                load_duration=raw.get("load_duration"),
                prompt_eval_duration=raw.get("prompt_eval_duration"),
                eval_duration=raw.get("eval_duration"),
                load_seconds=raw.get("load_duration", 0) / 1_000_000_000,
                prompt_eval_seconds=raw.get("prompt_eval_duration", 0) / 1_000_000_000,
                eval_seconds=eval_seconds,
                prompt_tokens=raw.get("prompt_eval_count", result.usage.input_tokens),
                output_tokens=output_tokens,
                output_tokens_per_second=(output_tokens / eval_seconds if output_tokens is not None and eval_seconds else None),
            )
            try:
                record["ollama_ps"] = ollama_ps()
                other_models = [
                    item["model"] for item in CANDIDATES
                    if item["provider"] == "ollama"
                    and item["model"] != candidate["model"]
                    and item["model"] in record["ollama_ps"]
                ]
                if other_models:
                    record.update(
                        ok=False,
                        error="ollama ps shows unexpected resident candidate(s): "
                        + ", ".join(other_models),
                    )
            except Exception as exc:
                record["ollama_ps_error"] = f"ollama ps failed: {exc}"
    except Exception as exc:
        record.update(ok=False, error=str(exc))
    return record


def _completed_identities(output_path: Path) -> set[tuple[str, str, str, str, int]]:
    completed = set()
    if not output_path.exists():
        return completed
    content = output_path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            is_trailing_fragment = index == len(lines) - 1 and not line.endswith(("\n", "\r"))
            if not is_trailing_fragment:
                raise ValueError(f"Malformed non-final JSONL record at line {index + 1}") from exc
            valid_prefix = "".join(lines[:index])
            output_path.write_text(valid_prefix, encoding="utf-8")
            break
        completed.add(
            (
                record["provider"],
                record["model"],
                record["case"],
                record["mode"],
                record["repetition"],
            )
        )
    return completed


def run_benchmark(
    config: Any,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    *,
    rerun: bool = False,
    repetitions: int = 3,
) -> None:
    completed = set() if rerun else _completed_identities(output_path)
    with output_path.open("w" if rerun else "a", encoding="utf-8") as handle:
        for candidate in CANDIDATES:
            trials: list[tuple[BenchmarkCase, str, int]] = []
            if candidate["provider"] == "ollama":
                cold_identity = _identity(candidate, CASES[0], "cold", 1)
                if cold_identity not in completed:
                    for local_candidate in CANDIDATES:
                        if local_candidate["provider"] == "ollama":
                            stop_ollama_model(local_candidate["model"])
                    trials.append((CASES[0], "cold", 1))
            for case in CASES:
                trials.extend((case, "warm", repetition) for repetition in range(1, repetitions + 1))

            for case, mode, repetition in trials:
                if _identity(candidate, case, mode, repetition) in completed:
                    continue
                record = run_candidate(config, candidate, case, mode, repetition)
                line = json.dumps(record, ensure_ascii=False)
                handle.write(line + "\n")
                handle.flush()
                print(json.dumps(record, ensure_ascii=True), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the resumable Gemini/Gemma benchmark")
    parser.add_argument("--env", default=".env")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--rerun", action="store_true")
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args()
    if args.summarize_only:
        return summarize_results(args.output, repetitions=args.repetitions)
    run_benchmark(
        load_config(args.env),
        args.output,
        rerun=args.rerun,
        repetitions=args.repetitions,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
