import json
from decimal import Decimal

import pytest
import speedytype.settings as settings_module

from speedytype.settings import (
    AppSettings,
    DEFAULT_MAX_RECORD_SECONDS,
    DEFAULT_VOCAB_TERMS,
    MAX_MAX_RECORD_SECONDS,
    export_vocab,
    hotkey_has_modifier_or_is_function_key,
    import_vocab,
    load_settings,
    save_settings,
)


def test_recording_mode_defaults_to_hold():
    assert settings_module.DEFAULT_RECORDING_MODE == "hold"
    assert AppSettings.default().recording_mode == "hold"


def test_toggle_recording_mode_roundtrips(tmp_path):
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, AppSettings(recording_mode="toggle"))

    loaded = load_settings(settings_path)

    assert loaded.recording_mode == "toggle"
    assert json.loads(settings_path.read_text(encoding="utf-8"))["recording_mode"] == "toggle"


def test_direct_save_rejects_unsupported_recording_mode(tmp_path):
    settings_path = tmp_path / "settings.json"

    with pytest.raises(ValueError, match="recording_mode"):
        save_settings(settings_path, AppSettings(recording_mode="bad"))

    assert not settings_path.exists()


def test_invalid_recording_mode_falls_back_to_hold_with_warning(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"recording_mode":"bad"}', encoding="utf-8")

    loaded = load_settings(settings_path)

    assert loaded.recording_mode == "hold"
    assert any("錄音模式" in item for item in loaded.load_warnings)


def test_max_record_limit_is_exactly_twenty_five_minutes():
    assert MAX_MAX_RECORD_SECONDS == 1500.0


def test_load_settings_creates_default_file_when_missing(tmp_path):
    settings_path = tmp_path / "settings.json"
    assert not settings_path.exists()

    settings = load_settings(settings_path)

    assert settings_path.exists()
    assert settings.max_record_seconds == DEFAULT_MAX_RECORD_SECONDS
    assert settings.vocab_terms == DEFAULT_VOCAB_TERMS
    on_disk = json.loads(settings_path.read_text(encoding="utf-8"))
    assert on_disk["max_record_seconds"] == DEFAULT_MAX_RECORD_SECONDS


def test_load_settings_roundtrips_saved_values(tmp_path):
    settings_path = tmp_path / "settings.json"
    original = AppSettings(max_record_seconds=120.0, hotkey_combo=["ctrl", "alt", "space"], vocab_terms=["Foo", "Bar"])
    save_settings(settings_path, original)

    loaded = load_settings(settings_path)

    assert loaded.max_record_seconds == 120.0
    assert loaded.hotkey_combo == ["ctrl", "alt", "space"]
    assert loaded.vocab_terms == ["Foo", "Bar"]
    assert loaded.hotkey_string == "ctrl+alt+space"


def test_over_limit_recording_setting_is_clamped_with_visible_warning(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"max_record_seconds": 1800}), encoding="utf-8")

    loaded = load_settings(settings_path)

    assert loaded.max_record_seconds == 1500.0
    assert any("25 分鐘" in warning for warning in loaded.load_warnings)


def test_exact_twenty_five_minute_setting_roundtrips(tmp_path):
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, AppSettings(max_record_seconds=1500.0))

    assert load_settings(settings_path).max_record_seconds == 1500.0


def test_direct_save_rejects_recording_setting_above_limit(tmp_path):
    settings_path = tmp_path / "settings.json"

    with pytest.raises(ValueError, match="max_record_seconds"):
        save_settings(settings_path, AppSettings(max_record_seconds=1500.1))

    assert not settings_path.exists()


def test_monthly_budget_roundtrips_as_exact_decimal_string(tmp_path):
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, AppSettings(monthly_budget=Decimal("10.2500")))

    loaded = load_settings(settings_path)

    assert loaded.monthly_budget == Decimal("10.2500")
    assert json.loads(settings_path.read_text(encoding="utf-8"))["monthly_budget"] == "10.2500"


@pytest.mark.parametrize("stored", [None, ""])
def test_absent_or_empty_monthly_budget_is_unconfigured(tmp_path, stored):
    settings_path = tmp_path / "settings.json"
    payload = {}
    if stored is not None:
        payload["monthly_budget"] = stored
    settings_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_settings(settings_path)

    assert loaded.monthly_budget is None
    assert loaded.load_warnings == ()


@pytest.mark.parametrize("stored", ["0", "-1", "NaN", "Infinity", "oops", 5])
def test_invalid_persisted_monthly_budget_is_safe_and_warned(tmp_path, stored):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"monthly_budget": stored}), encoding="utf-8")

    loaded = load_settings(settings_path)

    assert loaded.monthly_budget is None
    assert any("月預算" in warning for warning in loaded.load_warnings)


def test_load_settings_falls_back_to_defaults_on_malformed_json(tmp_path, capsys):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{not valid json!!", encoding="utf-8")

    settings = load_settings(settings_path)

    assert settings.max_record_seconds == DEFAULT_MAX_RECORD_SECONDS
    assert settings.vocab_terms == DEFAULT_VOCAB_TERMS
    captured = capsys.readouterr()
    assert "Warning" in captured.out
    # file must be left untouched, not overwritten with defaults
    assert settings_path.read_text(encoding="utf-8") == "{not valid json!!"


def test_load_settings_falls_back_on_wrong_json_shape(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    settings = load_settings(settings_path)

    assert settings.max_record_seconds == DEFAULT_MAX_RECORD_SECONDS


def test_hotkey_validation_requires_modifier_unless_function_key():
    assert hotkey_has_modifier_or_is_function_key(["f9"]) is True
    assert hotkey_has_modifier_or_is_function_key(["ctrl", "alt", "space"]) is True
    assert hotkey_has_modifier_or_is_function_key(["space"]) is False
    assert hotkey_has_modifier_or_is_function_key(["a"]) is False
    assert hotkey_has_modifier_or_is_function_key([]) is False


def test_vocab_export_import_roundtrip(tmp_path):
    export_path = tmp_path / "vocab_export.json"
    terms = ["BIOS", "自訂詞", "Thunderbolt"]

    export_vocab(export_path, terms)
    imported = import_vocab(export_path)

    assert imported == terms


def test_vocab_import_rejects_wrong_shape(tmp_path):
    bad_path = tmp_path / "bad_vocab.json"
    bad_path.write_text(json.dumps({"not_vocab_terms": [1, 2]}), encoding="utf-8")

    with pytest.raises(ValueError):
        import_vocab(bad_path)
