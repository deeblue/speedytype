from speedytype.env_writer import mask_secret, update_env_key


RICH_ENV = """# SpeedyType environment file
# API keys below
OPENAI_API_KEY=sk-old-openai-value
GEMINI_API_KEY=old-gemini-value

# behavior settings
WHISPER_VOCAB_BIAS="BIOS, Firmware, NPI, QA, API, PD, USB, Thunderbolt, TPE 團隊, BJ 團隊"
HOTKEY=f9
GEMINI_MODEL=gemini-3.5-flash
LATENCY_LOG_PATH=speedytype_latency_log.csv
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.1-flash-lite
LLM_THINKING_LEVEL=minimal
LLM_REASONING_EFFORT=
LLM_THINKING_TYPE=
MIC_DEVICE=1
"""


def test_update_env_key_only_changes_target_line(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(RICH_ENV, encoding="utf-8")

    update_env_key(env_path, "OPENAI_API_KEY", "sk-new-openai-value")

    result_lines = env_path.read_text(encoding="utf-8").splitlines()
    original_lines = RICH_ENV.splitlines()

    assert len(result_lines) == len(original_lines)
    for original, updated in zip(original_lines, result_lines):
        if original.startswith("OPENAI_API_KEY="):
            assert updated == "OPENAI_API_KEY=sk-new-openai-value"
            assert original != updated
        else:
            assert original == updated


def test_update_env_key_appends_when_missing(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(RICH_ENV, encoding="utf-8")

    update_env_key(env_path, "MINIMAX_API_KEY", "mm-brand-new-value")

    content = env_path.read_text(encoding="utf-8")
    assert "MINIMAX_API_KEY=mm-brand-new-value" in content
    # everything from the original file must still be present verbatim
    for original_line in RICH_ENV.splitlines():
        assert original_line in content.splitlines()


def test_update_env_key_creates_file_if_absent(tmp_path):
    env_path = tmp_path / ".env"
    assert not env_path.exists()

    update_env_key(env_path, "OPENAI_API_KEY", "sk-fresh")

    assert env_path.read_text(encoding="utf-8").strip() == "OPENAI_API_KEY=sk-fresh"


def test_mask_secret_shows_only_last_four_chars():
    assert mask_secret("sk-proj-abcdefgh1234") == "•" * (len("sk-proj-abcdefgh1234") - 4) + "1234"
    assert mask_secret("abcd") == "••••"
    assert mask_secret("ab") == "••"
    assert mask_secret("") == ""
