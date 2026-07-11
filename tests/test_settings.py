import json

import pytest

from speedytype.settings import (
    AppSettings,
    DEFAULT_MAX_RECORD_SECONDS,
    DEFAULT_VOCAB_TERMS,
    export_vocab,
    hotkey_has_modifier_or_is_function_key,
    import_vocab,
    load_settings,
    save_settings,
)


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
