from __future__ import annotations

import json

import pytest
from PyQt6.QtWidgets import QApplication, QDoubleSpinBox, QPushButton

from speedytype.pricing_dialog import PriceEditorDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def write_pricing(path) -> None:
    path.write_text(
        json.dumps(
            {
                "updated_date": "2026-07-14",
                "currency": "USD",
                "stt": {
                    "whisper-1": {"per_minute": 0.006},
                    "local-stt": {"per_minute": 0.125},
                },
                "llm": {
                    "gemini-test": {
                        "input_per_million": 0.25,
                        "output_per_million": 1.5,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def button(dialog: PriceEditorDialog, text: str) -> QPushButton:
    return next(item for item in dialog.findChildren(QPushButton) if item.text() == text)


def test_editor_builds_every_existing_price_control_with_zero_minimum(qapp, tmp_path) -> None:
    pricing_path = tmp_path / "pricing.json"
    write_pricing(pricing_path)

    dialog = PriceEditorDialog(pricing_path)
    controls = dialog.findChildren(QDoubleSpinBox)

    assert len(controls) == 4
    assert all(control.minimum() == 0.0 for control in controls)
    assert all(control.maximum() == 1_000_000.0 for control in controls)
    assert all(control.decimals() == 8 for control in controls)


def test_editor_save_changes_real_json_and_accepts(qapp, tmp_path) -> None:
    pricing_path = tmp_path / "pricing.json"
    write_pricing(pricing_path)
    dialog = PriceEditorDialog(pricing_path)
    control = dialog.findChild(QDoubleSpinBox, "stt.whisper-1.per_minute")
    assert control is not None
    control.setValue(0.01234567)

    button(dialog, "儲存").click()

    saved = json.loads(pricing_path.read_text(encoding="utf-8"))
    assert saved["stt"]["whisper-1"]["per_minute"] == 0.01234567
    assert dialog.result() == dialog.DialogCode.Accepted


def test_editor_cancel_does_not_change_source(qapp, tmp_path) -> None:
    pricing_path = tmp_path / "pricing.json"
    write_pricing(pricing_path)
    original = pricing_path.read_bytes()
    dialog = PriceEditorDialog(pricing_path)
    dialog.findChild(QDoubleSpinBox, "stt.whisper-1.per_minute").setValue(999)

    button(dialog, "取消").click()

    assert pricing_path.read_bytes() == original
    assert dialog.result() == dialog.DialogCode.Rejected


@pytest.mark.parametrize("price_token", ["0.123456789", "1000000.00000001", "1000001"])
def test_editor_rejects_source_price_it_cannot_represent_without_changing_bytes(
    qapp, tmp_path, price_token
) -> None:
    pricing_path = tmp_path / "pricing.json"
    original = (
        '{"updated_date":"2026-07-14","currency":"USD",'
        f'"stt":{{"whisper-1":{{"per_minute":{price_token}}}}},'
        '"llm":{"model":{"input_per_million":1,"output_per_million":2}}}\n'
    ).encode()
    pricing_path.write_bytes(original)

    dialog = PriceEditorDialog(pricing_path)
    button(dialog, "儲存").click()

    assert dialog.findChildren(QDoubleSpinBox) == []
    assert dialog.error_label.text() == "價格資料超出編輯器支援範圍，原始檔案未變更。"
    assert not button(dialog, "儲存").isEnabled()
    assert pricing_path.read_bytes() == original


@pytest.mark.parametrize(
    "contents",
    [
        '{"updated_date":"2026-07-14","currency":"USD","stt":{},"llm":{"model":{"input_per_million":1,"output_per_million":2}}}',
        '{"updated_date":"2026-07-14","currency":"USD","stt":{"whisper-1":{"per_minute":1}},"llm":{}}',
    ],
)
def test_editor_rejects_empty_required_mapping_without_controls(
    qapp, tmp_path, contents
) -> None:
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(contents, encoding="utf-8")

    dialog = PriceEditorDialog(pricing_path)

    assert dialog.findChildren(QDoubleSpinBox) == []
    assert dialog.error_label.text() == "價格資料無法載入，請檢查 pricing.json。"
    assert not button(dialog, "儲存").isEnabled()


@pytest.mark.parametrize("contents", [None, "{not-json", '{"updated_date":"x"}', '{"updated_date":"x","currency":"USD","stt":{"bad":{"per_minute":-1}},"llm":{}}'])
def test_missing_or_malformed_source_has_error_and_no_editable_controls(
    qapp, tmp_path, contents
) -> None:
    pricing_path = tmp_path / "pricing.json"
    if contents is not None:
        pricing_path.write_text(contents, encoding="utf-8")

    dialog = PriceEditorDialog(pricing_path)

    assert dialog.findChildren(QDoubleSpinBox) == []
    assert dialog.error_label.text() == "價格資料無法載入，請檢查 pricing.json。"
    assert not button(dialog, "儲存").isEnabled()


def test_save_failure_shows_safe_error_and_keeps_dialog_open(
    qapp, tmp_path, monkeypatch
) -> None:
    pricing_path = tmp_path / "pricing.json"
    write_pricing(pricing_path)
    original = pricing_path.read_bytes()
    dialog = PriceEditorDialog(pricing_path)
    dialog.show()
    qapp.processEvents()
    monkeypatch.setattr(
        "speedytype.pricing_dialog.save_pricing",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("C:\\private\\secret")),
    )

    button(dialog, "儲存").click()

    assert dialog.error_label.text() == "價格儲存失敗，原始檔案未變更。"
    assert dialog.isVisible()
    assert dialog.result() != dialog.DialogCode.Accepted
    assert pricing_path.read_bytes() == original
    dialog.close()
