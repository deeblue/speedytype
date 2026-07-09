from pathlib import Path

import pytest

from speedytype.config import ConfigError, load_config


def test_load_config_reads_env_file(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=sk-test",
                "GEMINI_API_KEY=gem-test",
                'WHISPER_VOCAB_BIAS="BIOS, Firmware, TPE 團隊"',
                "HOTKEY=f10",
                "GEMINI_MODEL=gemini-test-flash",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(env_file)

    assert config.openai_api_key == "sk-test"
    assert config.gemini_api_key == "gem-test"
    assert config.whisper_vocab_bias == "BIOS, Firmware, TPE 團隊"
    assert config.hotkey == "f10"
    assert config.gemini_model == "gemini-test-flash"


def test_load_config_reports_missing_required_keys(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=\nHOTKEY=f9\n", encoding="utf-8")

    with pytest.raises(ConfigError) as exc:
        load_config(env_file)

    message = str(exc.value)
    assert "Missing required configuration: OPENAI_API_KEY, GEMINI_API_KEY" in message
    assert str(env_file) in message
    assert "Copy .env.example to .env" in message
