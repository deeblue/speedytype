from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QLabel, QVBoxLayout

from speedytype.config import AppConfig
from speedytype.icon import build_app_icon
from speedytype.version import BUILD_DATE, STT_MODEL, VERSION


class AboutDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("關於 SpeedyType")
        self.setWindowIcon(build_app_icon())
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        lines = [
            f"SpeedyType POC",
            f"版本：{VERSION}",
            f"建置日期：{BUILD_DATE}",
            f"LLM 供應商 / 模型：{config.llm_provider} / {config.llm_model}",
            f"STT 模型：{STT_MODEL}",
            "已知限制請見 KNOWN_LIMITATIONS.md",
        ]
        for line in lines:
            layout.addWidget(QLabel(line))
