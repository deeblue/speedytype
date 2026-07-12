from speedytype.config import AppConfig
from speedytype.quasi_streaming import tail_prompt


def test_tail_prompt_keeps_vocab_bias_without_prior_narrative():
    config = AppConfig(
        openai_api_key="test",
        gemini_api_key="test",
        whisper_vocab_bias="BIOS, API, TPE 團隊, BJ 團隊",
    )

    prompt = tail_prompt(config, "上一段已辨識的旅行敘事，不應傳給下一個 chunk。")

    assert prompt == "BIOS, API, TPE 團隊, BJ 團隊"
