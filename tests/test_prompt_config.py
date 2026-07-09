from speedytype.api import build_system_prompt
from speedytype.config import AppConfig


def test_disambiguation_hints_default_on():
    prompt = build_system_prompt(AppConfig(openai_api_key="x", gemini_api_key="y"))

    assert "API / NPI" in prompt
    assert "TPE 團隊 / PD 團隊 / BJ 團隊" in prompt
    assert "刪除所有口語贅字" in prompt


def test_disambiguation_hints_can_be_disabled():
    prompt = build_system_prompt(
        AppConfig(openai_api_key="x", gemini_api_key="y", llm_disambiguation_hints="off")
    )

    assert "API / NPI" not in prompt
    assert "TPE 團隊 / PD 團隊 / BJ 團隊" not in prompt
    assert "刪除所有口語贅字" in prompt
    assert "專業名詞校正" in prompt
