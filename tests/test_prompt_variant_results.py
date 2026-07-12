import json
from pathlib import Path

from scripts.test_prompt_variants_repeated import is_valid_result
from speedytype.api import build_system_prompt
from speedytype.config import AppConfig


def test_api_failures_are_not_valid_prompt_samples():
    assert is_valid_result("123 測試") is True
    assert is_valid_result("[FAILED after 4 attempts] [ERROR 429]") is False
    assert is_valid_result("[ERROR 500] unavailable") is False


def test_repeated_123_loss_regression_is_guarded_by_production_prompt():
    results_path = Path(__file__).resolve().parents[1] / "combined_llm_investigation_results.jsonl"
    records = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines()]
    cases = {
        record["variant"]: record
        for record in records
        if record.get("stage") == "part_a_dimensions" and record.get("case") == "numbers_repeated_english"
    }
    prompt = build_system_prompt(AppConfig(openai_api_key="x", gemini_api_key="y"))

    assert cases["current"]["input"] == "123測試測試 123測試測試 123 test 123 test"
    assert "123" not in cases["current"]["output"]
    assert "123" in cases["candidate"]["output"]
    assert "數字與重複內容保留" in prompt
    assert "必須完整保留其中出現過的所有數字、代號與實際內容" in prompt
