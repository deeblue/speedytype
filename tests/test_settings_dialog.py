import csv
import json
from dataclasses import replace

import pytest
import sounddevice as sd
from PyQt6.QtWidgets import QApplication, QPushButton, QScrollArea

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


USAGE_CSV_FIELDS = [
    "timestamp",
    "usage_scope",
    "run_label",
    "recording_seconds",
    "hybrid_request_count",
    "stt_model",
    "gemini_seconds",
    "llm_model",
    "llm_input_tokens",
    "llm_output_tokens",
]


def write_usage_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=USAGE_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_test_pricing(path):
    path.write_text(
        json.dumps(
            {
                "updated_date": "2026-07-14",
                "currency": "USD",
                "stt": {"whisper-1": {"per_minute": 0.006}},
                "llm": {
                    "gemini-3.1-flash-lite": {
                        "input_per_million": 0.25,
                        "output_per_million": 1.50,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def known_usage_dialog(tmp_path, pricing_path=None):
    csv_path = tmp_path / "latency.csv"
    settings_path = tmp_path / "settings.json"
    write_usage_csv(
        csv_path,
        [
            {
                "usage_scope": "daily",
                "run_label": "real_voice",
                "recording_seconds": 60,
                "stt_model": "whisper-1",
                "gemini_seconds": 1,
                "llm_model": "gemini-3.1-flash-lite",
                "llm_input_tokens": 1000,
                "llm_output_tokens": 200,
            },
            {
                "usage_scope": "daily",
                "recording_seconds": 30,
                "hybrid_request_count": 1,
                "stt_model": "whisper-1",
                "gemini_seconds": 1,
                "llm_model": "gemini-3.1-flash-lite",
                "llm_input_tokens": 500,
                "llm_output_tokens": 100,
            },
            {
                "usage_scope": "",
                "run_label": "",
                "recording_seconds": 30,
                "stt_model": "",
            },
            {
                "usage_scope": "development",
                "run_label": "",
                "recording_seconds": 6000,
                "stt_model": "whisper-1",
                "gemini_seconds": 100,
                "llm_model": "gemini-3.1-flash-lite",
                "llm_input_tokens": 9999999,
                "llm_output_tokens": 9999999,
            },
            {
                "usage_scope": "",
                "run_label": "real_voice",
                "recording_seconds": 6000,
                "stt_model": "whisper-1",
                "gemini_seconds": 100,
                "llm_model": "gemini-3.1-flash-lite",
                "llm_input_tokens": 9999999,
                "llm_output_tokens": 9999999,
            },
        ],
    )
    save_settings(settings_path, AppSettings())
    config = replace(make_config(), latency_log_path=csv_path)
    return SettingsDialog(
        config,
        tmp_path / ".env",
        settings_path,
        pricing_path=pricing_path,
    )


def test_usage_group_shows_known_totals_models_price_date_and_disclaimer(qapp, tmp_path):
    pricing_path = tmp_path / "pricing.json"
    write_test_pricing(pricing_path)

    dialog = known_usage_dialog(tmp_path, pricing_path)

    assert "whisper-1" in dialog.usage_models_label.text()
    assert "gemini-3.1-flash-lite" in dialog.usage_models_label.text()
    assert "3" in dialog.usage_stt_label.text()
    assert "2.00" in dialog.usage_stt_label.text()
    assert "$0.012000" in dialog.usage_stt_label.text()
    assert "2" in dialog.usage_llm_label.text()
    assert "1,500" in dialog.usage_llm_label.text()
    assert "300" in dialog.usage_llm_label.text()
    assert "$0.000825" in dialog.usage_llm_label.text()
    assert "$0.012825" in dialog.usage_total_label.text()
    assert "2026-07-14" in dialog.usage_pricing_note_label.text()
    assert "估算費用，非實際帳單，價格可能已變動" in dialog.usage_pricing_note_label.text()
    assert "舊版" in dialog.usage_warning_label.text()
    assert "推定" in dialog.usage_warning_label.text()


def test_usage_is_calculated_exactly_once_when_settings_dialog_is_constructed(
    qapp, tmp_path, monkeypatch
):
    from speedytype.usage_stats import calculate_usage as real_calculate_usage

    pricing_path = tmp_path / "pricing.json"
    write_test_pricing(pricing_path)
    calls = []

    def calculate_once_spy(csv_path, selected_pricing_path):
        calls.append((csv_path, selected_pricing_path))
        return real_calculate_usage(csv_path, selected_pricing_path)

    monkeypatch.setattr("speedytype.settings_dialog.calculate_usage", calculate_once_spy)

    dialog = known_usage_dialog(tmp_path, pricing_path)

    assert dialog.usage_total_label.text()
    assert len(calls) == 1


@pytest.mark.parametrize("pricing_contents", [None, "{not-json"])
def test_usage_group_keeps_usage_visible_when_pricing_is_unavailable(
    qapp, tmp_path, pricing_contents
):
    pricing_path = tmp_path / "pricing.json"
    if pricing_contents is not None:
        pricing_path.write_text(pricing_contents, encoding="utf-8")

    dialog = known_usage_dialog(tmp_path, pricing_path)

    assert "3" in dialog.usage_stt_label.text()
    assert "2.00" in dialog.usage_stt_label.text()
    assert "1,500" in dialog.usage_llm_label.text()
    assert "300" in dialog.usage_llm_label.text()
    assert "價格資料缺失，無法估算費用" in dialog.usage_warning_label.text()
    assert "$0.000000" not in dialog.usage_total_label.text()


@pytest.mark.parametrize(
    "csv_contents",
    [None, b"", b"\xff\xfe\x80", b"garbage,other\n1,2\n"],
)
def test_usage_group_handles_unavailable_latency_csv(qapp, tmp_path, csv_contents):
    csv_path = tmp_path / "latency.csv"
    settings_path = tmp_path / "settings.json"
    pricing_path = tmp_path / "pricing.json"
    if csv_contents is not None:
        csv_path.write_bytes(csv_contents)
    write_test_pricing(pricing_path)
    save_settings(settings_path, AppSettings())

    dialog = SettingsDialog(
        replace(make_config(), latency_log_path=csv_path),
        tmp_path / ".env",
        settings_path,
        pricing_path=pricing_path,
    )

    assert "用量無法取得" in dialog.usage_stt_label.text()
    assert "用量無法取得" in dialog.usage_llm_label.text()
    assert "用量資料缺失，無法確認實際用量與費用" in dialog.usage_warning_label.text()
    assert "$0.000000" not in dialog.usage_total_label.text()


@pytest.mark.parametrize(
    ("latency_contents", "pricing_contents"),
    [
        (None, None),
        (None, "{not-json"),
        (b"\xff\xfe\x80", None),
        (b"garbage,other\n1,2\n", "{not-json"),
    ],
)
def test_usage_group_reports_usage_and_pricing_failures_independently_without_generic_count(
    qapp, tmp_path, latency_contents, pricing_contents
):
    csv_path = tmp_path / "latency.csv"
    settings_path = tmp_path / "settings.json"
    pricing_path = tmp_path / "pricing.json"
    if latency_contents is not None:
        csv_path.write_bytes(latency_contents)
    if pricing_contents is not None:
        pricing_path.write_text(pricing_contents, encoding="utf-8")
    save_settings(settings_path, AppSettings())

    dialog = SettingsDialog(
        replace(make_config(), latency_log_path=csv_path),
        tmp_path / ".env",
        settings_path,
        pricing_path=pricing_path,
    )

    warning = dialog.usage_warning_label.text()
    assert warning.count("用量資料缺失，無法確認實際用量與費用") == 1
    assert warning.count("價格資料缺失，無法估算費用") == 1
    assert "其他用量或價格資料警告" not in warning


def test_usage_group_skips_malformed_numeric_row_but_keeps_file_available(qapp, tmp_path):
    csv_path = tmp_path / "latency.csv"
    settings_path = tmp_path / "settings.json"
    pricing_path = tmp_path / "pricing.json"
    write_usage_csv(
        csv_path,
        [
            {
                "timestamp": "broken",
                "usage_scope": "daily",
                "run_label": "real_voice",
                "recording_seconds": "not-a-number",
            }
        ],
    )
    write_test_pricing(pricing_path)
    save_settings(settings_path, AppSettings())

    dialog = SettingsDialog(
        replace(make_config(), latency_log_path=csv_path),
        tmp_path / ".env",
        settings_path,
        pricing_path=pricing_path,
    )

    assert "0" in dialog.usage_stt_label.text()
    assert "$0.000000" in dialog.usage_total_label.text()
    assert "已略過 1 筆格式錯誤的用量紀錄" in dialog.usage_warning_label.text()


def test_settings_content_scrolls_to_keep_actions_reachable_on_short_screens(
    qapp, tmp_path, monkeypatch
):
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, AppSettings())
    monkeypatch.setattr(
        "speedytype.settings_dialog.list_input_devices",
        lambda: [{"name": "Very long audio input device " + "X" * 300}],
    )

    dialog = SettingsDialog(make_config(), tmp_path / ".env", settings_path)
    dialog.resize(520, 420)
    dialog.show()
    qapp.processEvents()

    save_button = next(
        button for button in dialog.findChildren(QPushButton) if button.text() == "儲存"
    )
    cancel_button = next(
        button for button in dialog.findChildren(QPushButton) if button.text() == "取消"
    )

    assert dialog.findChild(QScrollArea) is not None
    assert dialog.minimumSizeHint().height() <= qapp.primaryScreen().availableGeometry().height()
    assert dialog.settings_scroll_area.verticalScrollBar().maximum() > 0
    assert dialog.settings_scroll_area.horizontalScrollBar().maximum() > 0
    assert not dialog.settings_scroll_area.isAncestorOf(save_button)
    assert not dialog.settings_scroll_area.isAncestorOf(cancel_button)
    assert save_button.isVisible()
    assert cancel_button.isVisible()
    dialog.close()


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


def test_save_max_record_time_uses_default_path_when_cli_omits_settings(qapp, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    monkeypatch.setattr("speedytype.settings.default_settings_path", lambda: settings_path)
    monkeypatch.setattr("speedytype.settings_dialog.default_settings_path", lambda: settings_path, raising=False)
    monkeypatch.setattr("speedytype.settings_dialog.default_env_path", lambda: env_path, raising=False)

    dialog = SettingsDialog(make_config(), None, None)
    dialog.slider.setValue(540)
    dialog._save()

    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["max_record_seconds"] == 540.0


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


def test_masked_key_field_test_connection_uses_currently_edited_value(qapp, tmp_path):
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, AppSettings())
    dialog = SettingsDialog(make_config(), tmp_path / ".env", settings_path)
    tested_values = []
    dialog.openai_field._test_func = lambda value: tested_values.append(value) or (True, "connected")

    dialog.openai_field.toggle_button.click()
    dialog.openai_field.line_edit.setText("sk-currently-edited")
    dialog.openai_field.test_button.click()

    assert tested_values == ["sk-currently-edited"]
    assert dialog.openai_field.status_label.text() == "OK: connected"


def test_save_writes_only_changed_secret_to_keyring(qapp, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    env_path = tmp_path / ".env"
    original_env = "GEMINI_API_KEY=legacy-fallback\n# keep\n"
    env_path.write_text(original_env, encoding="utf-8")
    save_settings(settings_path, AppSettings())
    writes = []
    monkeypatch.setattr("speedytype.settings_dialog.set_api_key", lambda name, value: writes.append((name, value)))
    monkeypatch.setattr("speedytype.settings_dialog.delete_api_key", lambda name: None)
    dialog = SettingsDialog(make_config(), env_path, settings_path)
    dialog.gemini_field.toggle_button.click()
    dialog.gemini_field.line_edit.setText("gem-new-fake")
    dialog.gemini_field.toggle_button.click()
    dialog._save()
    assert writes == [("GEMINI_API_KEY", "gem-new-fake")]
    assert env_path.read_text(encoding="utf-8") == original_env


def test_save_empty_changed_secret_deletes_keyring_entry(qapp, tmp_path, monkeypatch):
    deleted = []
    monkeypatch.setattr("speedytype.settings_dialog.set_api_key", lambda *a: None)
    monkeypatch.setattr("speedytype.settings_dialog.delete_api_key", lambda name: deleted.append(name))
    dialog = SettingsDialog(make_config(), tmp_path / ".env", tmp_path / "settings.json")
    dialog.minimax_field.toggle_button.click()
    dialog.minimax_field.line_edit.clear()
    dialog._save()
    assert deleted == ["MINIMAX_API_KEY"]


def test_save_reports_secret_errors_independently_and_retries_only_failed_keys(qapp, tmp_path, monkeypatch):
    from speedytype.secrets_store import SecretStoreError

    writes = []

    def fake_set(name, value):
        writes.append((name, value))
        if name == "OPENAI_API_KEY":
            raise SecretStoreError("credential manager unavailable")

    monkeypatch.setattr("speedytype.settings_dialog.set_api_key", fake_set)
    monkeypatch.setattr("speedytype.settings_dialog.delete_api_key", lambda name: None)
    dialog = SettingsDialog(make_config(), tmp_path / ".env", tmp_path / "settings.json")
    dialog.openai_field.toggle_button.click()
    dialog.openai_field.line_edit.setText("sk-new-fake")
    dialog.gemini_field.toggle_button.click()
    dialog.gemini_field.line_edit.setText("gem-new-fake")

    dialog._save()

    assert writes == [
        ("OPENAI_API_KEY", "sk-new-fake"),
        ("GEMINI_API_KEY", "gem-new-fake"),
    ]
    assert "金鑰儲存失敗（OPENAI_API_KEY）：credential manager unavailable" in dialog.status_label.text()
    assert "金鑰已更新（GEMINI_API_KEY）" in dialog.status_label.text()

    dialog._save()

    assert writes == [
        ("OPENAI_API_KEY", "sk-new-fake"),
        ("GEMINI_API_KEY", "gem-new-fake"),
        ("OPENAI_API_KEY", "sk-new-fake"),
    ]


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


def test_autostart_checkbox_installs_when_enabled_on_save(qapp, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    env_path = tmp_path / ".env"
    save_settings(settings_path, AppSettings())
    calls = []
    monkeypatch.setattr("speedytype.settings_dialog.query_autostart", lambda: (False, "disabled"))
    monkeypatch.setattr(
        "speedytype.settings_dialog.install_autostart",
        lambda path: calls.append(path) or (True, "installed"),
    )
    monkeypatch.setattr("speedytype.settings_dialog.uninstall_autostart", lambda: (True, "removed"))

    dialog = SettingsDialog(make_config(), str(env_path), str(settings_path))
    assert dialog.autostart_checkbox.isChecked() is False
    dialog.autostart_checkbox.setChecked(True)
    dialog._save()

    assert calls == [str(env_path)]
    assert "installed" in dialog.status_label.text()


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
