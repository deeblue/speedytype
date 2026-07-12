from __future__ import annotations

from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from speedytype.config import load_config
from scripts.test_prompt_variants import (
    CANDIDATE_PROMPT,
    CURRENT_PROMPT,
    build_prompt,
    polish_with_prompt,
)


PROBLEM_INPUT = "123測試測試 123測試測試 123 test 123 test"
REPEATS = 8


def count_numbers_preserved(text: str) -> int:
    return len(re.findall(r"123", text))


def is_valid_result(text: str) -> bool:
    return not text.startswith(("[ERROR ", "[FAILED ", "[REQUEST_EXCEPTION]"))


def main() -> int:
    config = load_config(".env")
    current_prompt = build_prompt(CURRENT_PROMPT, config.use_disambiguation_hints)
    candidate_prompt = build_prompt(CANDIDATE_PROMPT, config.use_disambiguation_hints)

    print(f"Running {REPEATS} repeats each for CURRENT and CANDIDATE prompts on the same garbled input.\n")

    current_results = []
    current_outputs = []
    for i in range(REPEATS):
        result = polish_with_prompt(PROBLEM_INPUT, current_prompt, config)
        has_numbers = count_numbers_preserved(result) > 0
        current_results.append(has_numbers)
        current_outputs.append(result)
        print(f"CURRENT   run {i + 1}/{REPEATS}: numbers_preserved={has_numbers} -> {result!r}")

    print()
    candidate_results = []
    candidate_outputs = []
    for i in range(REPEATS):
        result = polish_with_prompt(PROBLEM_INPUT, candidate_prompt, config)
        has_numbers = count_numbers_preserved(result) > 0
        candidate_results.append(has_numbers)
        candidate_outputs.append(result)
        print(f"CANDIDATE run {i + 1}/{REPEATS}: numbers_preserved={has_numbers} -> {result!r}")

    print()
    current_valid = [ok for ok, text in zip(current_results, current_outputs) if is_valid_result(text)]
    candidate_valid = [ok for ok, text in zip(candidate_results, candidate_outputs) if is_valid_result(text)]
    print(f"CURRENT preserved-numbers rate:   {sum(current_valid)}/{len(current_valid)} valid samples")
    print(f"CANDIDATE preserved-numbers rate: {sum(candidate_valid)}/{len(candidate_valid)} valid samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
