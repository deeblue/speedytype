from pathlib import Path

import pytest

from speedytype.config import ConfigError, load_config, resolve_mic_device_setting
from speedytype.settings import AppSettings, save_settings


def test_load_config_reads_env_file(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=sk-test",
                "GEMINI_API_KEY=gem-test",
                "GEMINI_MODEL=gemini-test-flash",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(env_file, settings_path=tmp_path / "settings.json")

    assert config.openai_api_key == "sk-test"
    assert config.gemini_api_key == "gem-test"
    assert config.gemini_model == "gemini-test-flash"


def test_load_config_reads_behavior_settings_from_settings_json(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-test\nGEMINI_API_KEY=gem-test\n", encoding="utf-8")
    settings_file = tmp_path / "settings.json"
    save_settings(
        settings_file,
        AppSettings(max_record_seconds=180.0, hotkey_combo=["ctrl", "alt", "space"], vocab_terms=["BIOS", "TPE 團隊"]),
    )

    config = load_config(env_file, settings_path=settings_file)

    assert config.max_record_seconds == 180.0
    assert config.hotkey == "ctrl+alt+space"
    assert config.whisper_vocab_bias == "BIOS, TPE 團隊"


def test_resolve_mic_device_setting_empty_means_default():
    value, warning = resolve_mic_device_setting("")
    assert value == ""
    assert warning == ""


def test_resolve_mic_device_setting_found_device_passes_through(monkeypatch):
    monkeypatch.setattr("speedytype.config.find_input_device_index_by_name", lambda name: 3)
    value, warning = resolve_mic_device_setting("My Real Microphone")
    assert value == "My Real Microphone"
    assert warning == ""


def test_resolve_mic_device_setting_missing_device_falls_back_with_warning(monkeypatch):
    monkeypatch.setattr("speedytype.config.find_input_device_index_by_name", lambda name: None)
    value, warning = resolve_mic_device_setting("Unplugged USB Mic")
    assert value == ""
    assert "Unplugged USB Mic" in warning
    assert "系統預設" in warning


def test_load_config_falls_back_when_saved_mic_device_is_missing(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-test\nGEMINI_API_KEY=gem-test\n", encoding="utf-8")
    settings_file = tmp_path / "settings.json"
    save_settings(settings_file, AppSettings(mic_device_name="A Device That No Longer Exists"))

    monkeypatch.setattr("speedytype.config.find_input_device_index_by_name", lambda name: None)
    config = load_config(env_file, settings_path=settings_file)

    assert config.mic_device == ""
    assert "A Device That No Longer Exists" in config.mic_device_warning


def test_load_config_reports_missing_required_keys(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=\nHOTKEY=f9\n", encoding="utf-8")

    with pytest.raises(ConfigError) as exc:
        load_config(env_file, settings_path=tmp_path / "settings.json")

    message = str(exc.value)
    assert "Missing required configuration: OPENAI_API_KEY, GEMINI_API_KEY" in message
    assert str(env_file) in message
    assert "Copy .env.example to .env" in message


def test_load_config_reads_ollama_settings_without_gemini_key(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_KEY=sk-test\n"
        "LLM_PROVIDER=ollama\n"
        "LLM_MODEL=gemma4:12b\n"
        "OLLAMA_BASE_URL=http://localhost:11435/\n"
        "OLLAMA_KEEP_ALIVE=15m\n",
        encoding="utf-8",
    )

    config = load_config(env_file, settings_path=tmp_path / "settings.json")

    assert config.llm_provider == "ollama"
    assert config.llm_model == "gemma4:12b"
    assert config.ollama_base_url == "http://localhost:11435"
    assert config.ollama_keep_alive == "15m"
    assert config.gemini_api_key == ""


def test_load_config_requires_openai_key_for_ollama(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_PROVIDER=ollama\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        load_config(env_file, settings_path=tmp_path / "settings.json")


def test_load_config_requires_gemini_key_for_gemini_provider(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-test\nLLM_PROVIDER=gemini\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="GEMINI_API_KEY"):
        load_config(env_file, settings_path=tmp_path / "settings.json")


def test_load_config_requires_minimax_key_for_minimax_provider(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-test\nLLM_PROVIDER=minimax\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="MINIMAX_API_KEY"):
        load_config(env_file, settings_path=tmp_path / "settings.json")


def test_load_config_uses_default_for_empty_ollama_base_url(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_KEY=sk-test\nLLM_PROVIDER=ollama\nOLLAMA_BASE_URL=///\n",
        encoding="utf-8",
    )

    config = load_config(env_file, settings_path=tmp_path / "settings.json")

    assert config.ollama_base_url == "http://127.0.0.1:11434"
    assert config.ollama_keep_alive == "10m"
