import json

import pytest
import sounddevice as sd
from PyQt6.QtWidgets import QApplication

from speedytype.audio import list_input_devices
from speedytype.settings import AppSettings, DEFAULT_VOCAB_TERMS, save_settings
from speedytype.settings_dialog import SYSTEM_DEFAULT_DEVICE_LABEL, SettingsDialog, format_seconds_readable


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def make_config():
    from speedytype.config import AppConfig

    return AppConfig(openai_api_key="sk-test-key-1234", gemini_api_key="gem-test-key-5678", minimax_api_key="mm-test-key-9999")


def test_format_seconds_readable():
    assert format_seconds_readable(60) == "1 分鐘"
    assert format_seconds_readable(90) == "1 分 30 秒"
    assert format_seconds_readable(45) == "45 秒"
    assert format_seconds_readable(540) == "9 分鐘"


def test_slider_bounds_are_locked(qapp, tmp_path):
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, AppSettings(max_record_seconds=120.0))
    dialog = SettingsDialog(make_config(), str(tmp_path / ".env"), str(settings_path))

    dialog.slider.setValue(5)  # below the 60s floor
    assert dialog.slider.value() == 60

    dialog.slider.setValue(9999)  # above the 540s ceiling
    assert dialog.slider.value() == 540


def test_vocab_add_remove_reset(qapp, tmp_path):
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, AppSettings(vocab_terms=["BIOS", "API"]))
    dialog = SettingsDialog(make_config(), str(tmp_path / ".env"), str(settings_path))

    dialog.vocab_input.setText("自訂新詞")
    dialog._add_vocab_term()
    assert "自訂新詞" in dialog._vocab_terms
    assert dialog.vocab_list.count() == 3

    dialog.vocab_list.setCurrentRow(0)  # "BIOS"
    dialog._delete_selected_vocab()
    assert "BIOS" not in dialog._vocab_terms
    assert dialog.vocab_list.count() == 2

    dialog._reset_vocab()
    assert dialog._vocab_terms == DEFAULT_VOCAB_TERMS
    assert dialog.vocab_list.count() == len(DEFAULT_VOCAB_TERMS)


def test_vocab_export_import_roundtrip_via_dialog(qapp, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, AppSettings(vocab_terms=["BIOS", "Custom1"]))
    dialog = SettingsDialog(make_config(), str(tmp_path / ".env"), str(settings_path))

    export_path = tmp_path / "exported_vocab.json"
    monkeypatch.setattr(
        "speedytype.settings_dialog.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(export_path), "JSON (*.json)"),
    )
    dialog._export_vocab()
    assert export_path.exists()
    exported_data = json.loads(export_path.read_text(encoding="utf-8"))
    assert exported_data["vocab_terms"] == ["BIOS", "Custom1"]

    # Change the in-memory list, then import-and-replace from the exported file.
    dialog._vocab_terms = ["SomethingElseEntirely"]
    dialog.vocab_list.clear()
    dialog.vocab_list.addItems(dialog._vocab_terms)

    monkeypatch.setattr(
        "speedytype.settings_dialog.QFileDialog.getOpenFileName",
        lambda *a, **k: (str(export_path), "JSON (*.json)"),
    )
    dialog._import_vocab()
    assert dialog._vocab_terms == ["BIOS", "Custom1"]
    assert [dialog.vocab_list.item(i).text() for i in range(dialog.vocab_list.count())] == ["BIOS", "Custom1"]


def test_masked_key_field_reveal_toggle_and_edit(qapp, tmp_path):
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, AppSettings())
    dialog = SettingsDialog(make_config(), str(tmp_path / ".env"), str(settings_path))

    field = dialog.openai_field
    assert field.line_edit.isReadOnly()
    assert field.line_edit.text() == "•" * (len("sk-test-key-1234") - 4) + "1234"
    assert field.current_value() == "sk-test-key-1234"

    field.toggle_button.click()
    assert not field.line_edit.isReadOnly()
    assert field.line_edit.text() == "sk-test-key-1234"

    field.line_edit.setText("sk-brand-new-value")
    field.toggle_button.click()
    assert field.line_edit.isReadOnly()
    assert field.current_value() == "sk-brand-new-value"


def test_save_writes_settings_and_only_changed_keys(qapp, tmp_path):
    settings_path = tmp_path / "settings.json"
    env_path = tmp_path / ".env"
    env_path.write_text(
        "OPENAI_API_KEY=sk-test-key-1234\nGEMINI_API_KEY=gem-test-key-5678\nMINIMAX_API_KEY=mm-test-key-9999\n# a comment\nHOTKEY=f9\n",
        encoding="utf-8",
    )
    save_settings(settings_path, AppSettings(max_record_seconds=90.0))
    dialog = SettingsDialog(make_config(), str(env_path), str(settings_path))

    dialog.slider.setValue(200)
    dialog.vocab_input.setText("NewTerm")
    dialog._add_vocab_term()

    # Reveal + change only the Gemini key.
    dialog.gemini_field.toggle_button.click()
    dialog.gemini_field.line_edit.setText("gem-changed-value")
    dialog.gemini_field.toggle_button.click()

    dialog._save()

    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["max_record_seconds"] == 200.0
    assert "NewTerm" in saved["vocab_terms"]

    env_text = env_path.read_text(encoding="utf-8")
    assert "GEMINI_API_KEY=gem-changed-value" in env_text
    assert "OPENAI_API_KEY=sk-test-key-1234" in env_text  # untouched
    assert "# a comment" in env_text  # preserved
    assert "已儲存" in dialog.status_label.text()
    assert "GEMINI_API_KEY" in dialog.status_label.text()
    assert "OPENAI_API_KEY" not in dialog.status_label.text()


def test_cancel_writes_nothing(qapp, tmp_path):
    settings_path = tmp_path / "settings.json"
    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=sk-original\nGEMINI_API_KEY=gem-original\nMINIMAX_API_KEY=mm-original\n", encoding="utf-8")
    save_settings(settings_path, AppSettings(max_record_seconds=90.0))
    before_settings = settings_path.read_text(encoding="utf-8")
    before_env = env_path.read_text(encoding="utf-8")

    dialog = SettingsDialog(make_config(), str(env_path), str(settings_path))
    dialog.slider.setValue(300)
    dialog.gemini_field.toggle_button.click()
    dialog.gemini_field.line_edit.setText("gem-changed-but-not-saved")
    dialog.close()

    assert settings_path.read_text(encoding="utf-8") == before_settings
    assert env_path.read_text(encoding="utf-8") == before_env


def make_config_with_warning(warning=""):
    from speedytype.config import AppConfig

    return AppConfig(
        openai_api_key="sk-test-key-1234",
        gemini_api_key="gem-test-key-5678",
        minimax_api_key="mm-test-key-9999",
        mic_device_warning=warning,
    )


def test_device_combo_lists_current_input_devices_matching_sounddevice(qapp, tmp_path):
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, AppSettings())
    dialog = SettingsDialog(make_config_with_warning(), str(tmp_path / ".env"), str(settings_path))

    expected_names = [SYSTEM_DEFAULT_DEVICE_LABEL] + [str(d["name"]) for d in list_input_devices()]
    actual_names = [dialog.device_combo.itemText(i) for i in range(dialog.device_combo.count())]

    assert actual_names == expected_names
    # Cross-check directly against the raw sounddevice query too, not just our own wrapper.
    raw_input_names = [
        str(d["name"]) for d in sd.query_devices() if d["max_input_channels"] > 0
    ]
    assert actual_names[1:] == raw_input_names


def test_device_combo_preselects_saved_device(qapp, tmp_path):
    real_devices = list_input_devices()
    assert real_devices, "test machine must have at least one input device"
    target_name = str(real_devices[0]["name"])

    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, AppSettings(mic_device_name=target_name))
    dialog = SettingsDialog(make_config_with_warning(), str(tmp_path / ".env"), str(settings_path))

    assert dialog.device_combo.currentText() == target_name
    assert dialog._device_values[dialog.device_combo.currentIndex()] == target_name


def test_device_combo_falls_back_to_default_when_saved_device_missing(qapp, tmp_path):
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, AppSettings(mic_device_name="A Totally Fake Unplugged Device XYZ"))
    warning = "先前選定的錄音裝置「A Totally Fake Unplugged Device XYZ」目前找不到，已自動改用系統預設裝置。"

    dialog = SettingsDialog(make_config_with_warning(warning), str(tmp_path / ".env"), str(settings_path))

    assert dialog.device_combo.currentIndex() == 0
    assert dialog.device_combo.currentText() == SYSTEM_DEFAULT_DEVICE_LABEL


def test_save_persists_chosen_device_name(qapp, tmp_path):
    real_devices = list_input_devices()
    assert real_devices, "test machine must have at least one input device"
    target_name = str(real_devices[0]["name"])

    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, AppSettings())
    dialog = SettingsDialog(make_config_with_warning(), str(tmp_path / ".env"), str(settings_path))

    index = dialog._device_values.index(target_name)
    dialog.device_combo.setCurrentIndex(index)
    dialog._save()

    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["mic_device_name"] == target_name


def test_save_persists_system_default_as_empty_string(qapp, tmp_path):
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, AppSettings(mic_device_name="SomePreviouslyChosenDevice"))
    dialog = SettingsDialog(make_config_with_warning(), str(tmp_path / ".env"), str(settings_path))

    dialog.device_combo.setCurrentIndex(0)  # system default
    dialog._save()

    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["mic_device_name"] == ""
