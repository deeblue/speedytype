from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)


class BudgetDialog(QDialog):
    def __init__(self, current_value: Decimal | None, currency: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("設定月預算")
        self.value = current_value
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"每月合併預算（{currency or '目前價格幣別'}）"))
        self.amount_edit = QLineEdit("" if current_value is None else current_value.to_eng_string())
        self.amount_edit.setPlaceholderText("例如：10.00")
        layout.addWidget(self.amount_edit)
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #b3261e;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        actions = QHBoxLayout()
        self.clear_button = QPushButton("清除預算")
        self.clear_button.clicked.connect(self._clear_value)
        actions.addWidget(self.clear_button)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_value)
        buttons.rejected.connect(self.reject)
        actions.addWidget(buttons)
        layout.addLayout(actions)

    def _accept_value(self) -> None:
        try:
            value = Decimal(self.amount_edit.text().strip())
            if not value.is_finite() or value <= 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            self.error_label.setText("請輸入大於 0 的有限十進位金額。")
            return
        self.value = value
        self.accept()

    def _clear_value(self) -> None:
        self.value = None
        self.accept()
