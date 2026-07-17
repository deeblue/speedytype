from __future__ import annotations

from decimal import Decimal

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from speedytype.usage_stats import MonthlyUsageSummary, calculate_budget_capacity


def _money(value: Decimal | None, currency: str) -> str:
    if value is None:
        return "無法估算"
    suffix = f" {currency}" if currency else ""
    return f"${value:.6f}{suffix}"


class BudgetCapacityWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.period_label = QLabel("")
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.detail_label = QLabel("")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        self.models_label = QLabel("")
        self.stt_label = QLabel("")
        self.llm_label = QLabel("")
        self.pricing_note_label = QLabel("")
        self.warning_label = QLabel("")
        for label in (
            self.period_label, self.status_label, self.detail_label, self.models_label,
            self.stt_label, self.llm_label, self.pricing_note_label, self.warning_label,
        ):
            label.setWordWrap(True)
        for widget in (
            self.period_label, self.status_label, self.detail_label, self.progress_bar,
            self.models_label, self.stt_label, self.llm_label, self.pricing_note_label,
            self.warning_label,
        ):
            layout.addWidget(widget)
        actions = QHBoxLayout()
        self.budget_button = QPushButton("設定月預算")
        self.pricing_button = QPushButton("編輯價格")
        actions.addWidget(self.budget_button)
        actions.addWidget(self.pricing_button)
        layout.addLayout(actions)

    def set_summary(
        self,
        monthly: MonthlyUsageSummary,
        budget: Decimal | None,
        extra_warnings: tuple[str, ...] = (),
    ) -> None:
        usage = monthly.usage
        self.period_label.setText(f"{monthly.year} 年 {monthly.month} 月")
        self.models_label.setText(
            f"模型：STT {', '.join(usage.stt_models) or '無紀錄'}；"
            f"LLM {', '.join(usage.llm_models) or '無紀錄'}"
        )
        if usage.usage_available:
            self.stt_label.setText(
                f"STT　{usage.stt_minutes:.2f} 分鐘 / {usage.stt_calls:,} 次　"
                f"{_money(usage.stt_cost, usage.currency)}"
            )
            total_tokens = usage.llm_input_tokens + usage.llm_output_tokens
            self.llm_label.setText(
                f"LLM　{total_tokens:,} tokens / {usage.llm_calls:,} 次　"
                f"{_money(usage.llm_cost, usage.currency)}"
            )
        else:
            self.stt_label.setText("STT：用量無法取得")
            self.llm_label.setText("LLM：用量無法取得")

        capacity = calculate_budget_capacity(
            usage.total_cost if usage.usage_available else None, budget
        )
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("")
        if not usage.usage_available or usage.total_cost is None:
            self.status_label.setText("本月容量無法取得")
            self.detail_label.setText(f"總估算費用：{_money(None, usage.currency)}")
        elif budget is None:
            self.status_label.setText("尚未設定月預算")
            self.detail_label.setText(f"本月總估算費用：{_money(usage.total_cost, usage.currency)}")
            self.progress_bar.setStyleSheet(
                "QProgressBar { border: 1px dashed #888; background: transparent; }"
            )
        elif capacity is not None:
            shown_percent = capacity.percentage.quantize(Decimal("0.1"))
            self.status_label.setText(
                f"已使用 {shown_percent}%　{_money(capacity.used, usage.currency)} / "
                f"{_money(capacity.budget, usage.currency)}"
            )
            self.progress_bar.setValue(min(100, int(capacity.percentage)))
            if capacity.exceeded > 0:
                self.detail_label.setText(
                    f"估計超出 {_money(capacity.exceeded, usage.currency)}；"
                    "SpeedyType 仍會正常錄音與處理。"
                )
                self.progress_bar.setStyleSheet("QProgressBar::chunk { background: #d35400; }")
            else:
                self.detail_label.setText(
                    f"估計剩餘 {_money(capacity.remaining, usage.currency)}"
                )
        self.budget_button.setText("設定月預算" if budget is None else "調整月預算")
        date = usage.pricing_updated_date or "無法取得"
        self.pricing_note_label.setText(
            f"價格更新日期：{date}\n估算費用，非實際帳單，價格可能已變動"
        )
        self.warning_label.setText("；".join(extra_warnings))
