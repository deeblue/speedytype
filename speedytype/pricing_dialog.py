from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

from PyQt6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from speedytype.usage_stats import LlmPricing, PricingData, load_pricing, save_pricing


class PriceEditorDialog(QDialog):
    def __init__(self, pricing_path: str | Path, parent=None) -> None:
        super().__init__(parent)
        self.pricing_path = Path(pricing_path)
        self._pricing: PricingData | None = None
        self._stt_controls: dict[str, QDoubleSpinBox] = {}
        self._llm_controls: dict[str, tuple[QDoubleSpinBox, QDoubleSpinBox]] = {}

        self.setWindowTitle("編輯價格")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)

        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #cc4444;")
        layout.addWidget(self.error_label)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        contents = QWidget()
        self._prices_layout = QVBoxLayout(contents)
        self._prices_layout.addStretch(1)
        scroll_area.setWidget(contents)
        layout.addWidget(scroll_area, 1)

        note = QLabel("僅能修改現有模型的數值；新增或刪除模型請手動編輯 pricing.json。")
        note.setWordWrap(True)
        layout.addWidget(note)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.save_button = QPushButton("儲存")
        self.save_button.clicked.connect(self._save)
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(self.save_button)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

        self._load_controls()

    @staticmethod
    def _price_control(value: Decimal, object_name: str) -> QDoubleSpinBox:
        control = QDoubleSpinBox()
        control.setObjectName(object_name)
        control.setRange(0.0, 1_000_000.0)
        control.setDecimals(8)
        control.setValue(float(value))
        return control

    def _load_controls(self) -> None:
        try:
            pricing = load_pricing(self.pricing_path)
            if pricing.warnings:
                raise ValueError("Pricing contains invalid values.")
        except (OSError, ValueError):
            self.error_label.setText("價格資料無法載入，請檢查 pricing.json。")
            self.save_button.setEnabled(False)
            return

        self._pricing = pricing
        stt_group = QGroupBox("STT 每分鐘價格")
        stt_layout = QFormLayout(stt_group)
        for model, price in pricing.stt.items():
            if price is None:
                continue
            control = self._price_control(price, f"stt.{model}.per_minute")
            self._stt_controls[model] = control
            stt_layout.addRow(model, control)
        self._prices_layout.insertWidget(self._prices_layout.count() - 1, stt_group)

        llm_group = QGroupBox("LLM 每百萬 tokens 價格")
        llm_layout = QFormLayout(llm_group)
        for model, prices in pricing.llm.items():
            if prices.input_per_million is None or prices.output_per_million is None:
                continue
            input_control = self._price_control(
                prices.input_per_million, f"llm.{model}.input_per_million"
            )
            output_control = self._price_control(
                prices.output_per_million, f"llm.{model}.output_per_million"
            )
            self._llm_controls[model] = (input_control, output_control)
            llm_layout.addRow(f"{model} 輸入", input_control)
            llm_layout.addRow(f"{model} 輸出", output_control)
        self._prices_layout.insertWidget(self._prices_layout.count() - 1, llm_group)

    @staticmethod
    def _decimal_value(control: QDoubleSpinBox) -> Decimal:
        return Decimal(str(control.value()))

    def _save(self) -> None:
        if self._pricing is None:
            return
        stt = {
            model: self._decimal_value(control)
            for model, control in self._stt_controls.items()
        }
        llm = {
            model: LlmPricing(
                input_per_million=self._decimal_value(controls[0]),
                output_per_million=self._decimal_value(controls[1]),
            )
            for model, controls in self._llm_controls.items()
        }
        edited = PricingData(
            updated_date=self._pricing.updated_date,
            currency=self._pricing.currency,
            stt=MappingProxyType(stt),
            llm=MappingProxyType(llm),
        )
        try:
            save_pricing(self.pricing_path, edited)
        except Exception:
            self.error_label.setText("價格儲存失敗，原始檔案未變更。")
            return
        self.accept()
