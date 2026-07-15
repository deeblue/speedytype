from pathlib import Path

import pytest

from speedytype.config import ConfigError, load_config, resolve_mic_device_setting
from speedytype.secrets_store import SecretResolution
from speedytype.settings import AppSettings, save_settings


def test_settings_config_allows_missing_required_keys(tmp_path):
    config = load_config(
        tmp_path / ".env",
        settings_path=tmp_path / "settings.json",
        require_api_keys=False,
    )

    assert config.openai_api_key == ""
    assert config.gemini_api_key == ""


def test_operational_config_still_rejects_missing_required_keys(tmp_path):
    with pytest.raises(ConfigError, match="OPENAI_API_KEY, GEMINI_API_KEY"):
        load_config(tmp_path / ".env", settings_path=tmp_path / "settings.json")


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


def test_load_config_uses_resolved_keyring_values(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=file-openai\nGEMINI_API_KEY=file-gemini\n", encoding="utf-8")
    monkeypatch.setattr(
        "speedytype.config.resolve_api_keys",
        lambda *a, **k: SecretResolution({
            "OPENAI_API_KEY": "ring-openai",
            "GEMINI_API_KEY": "ring-gemini",
            "MINIMAX_API_KEY": "ring-minimax",
        }),
    )
    config = load_config(env_file, settings_path=tmp_path / "settings.json")
    assert config.openai_api_key == "ring-openai"
    assert config.gemini_api_key == "ring-gemini"


def test_load_config_missing_message_mentions_settings_and_env(tmp_path, monkeypatch):
    monkeypatch.setattr("speedytype.config.resolve_api_keys", lambda *a, **k: SecretResolution({}))
    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path / ".env", settings_path=tmp_path / "settings.json")
    assert "設定頁面" in str(exc.value)
    assert ".env" in str(exc.value)


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
    assert "設定頁面" in message
    assert "keyring 不可用時於 .env 提供備援值" in message
