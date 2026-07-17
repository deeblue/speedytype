from datetime import datetime, timezone
from decimal import Decimal

import pytest
from PyQt6.QtWidgets import QApplication

from speedytype.budget_dialog import BudgetDialog
from speedytype.capacity_widget import BudgetCapacityWidget
from speedytype.usage_stats import MonthlyUsageSummary, UsageSummary


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def summary(*, total=Decimal("2.50"), available=True):
    usage = UsageSummary(
        stt_calls=3, stt_minutes=Decimal("12.5"), llm_calls=2,
        llm_input_tokens=1000, llm_output_tokens=200,
        stt_cost=total if total is None else Decimal("2"),
        llm_cost=total if total is None else Decimal("0.5"), total_cost=total,
        stt_models=("whisper-1",), llm_models=("model-x",),
        legacy_inferred_rows=0, pricing_updated_date="2026-07-14", currency="USD",
        usage_available=available,
    )
    return MonthlyUsageSummary(2026, 7, usage)


def test_budget_dialog_validates_and_returns_exact_value(qapp):
    dialog = BudgetDialog(Decimal("10"), "USD")
    dialog.amount_edit.setText("0")
    dialog._accept_value()
    assert "大於 0" in dialog.error_label.text()
    assert dialog.result() == 0

    dialog.amount_edit.setText("10.2500")
    dialog._accept_value()
    assert dialog.value == Decimal("10.2500")


def test_budget_dialog_can_clear_pending_budget(qapp):
    dialog = BudgetDialog(Decimal("10"), "USD")
    dialog._clear_value()
    assert dialog.value is None


def test_capacity_widget_unconfigured_state_has_empty_track(qapp):
    widget = BudgetCapacityWidget()
    widget.set_summary(summary(), None)
    assert "尚未設定月預算" in widget.status_label.text()
    assert "%" not in widget.status_label.text()
    assert widget.progress_bar.value() == 0
    assert widget.budget_button.text() == "設定月預算"


def test_capacity_widget_within_budget_state(qapp):
    widget = BudgetCapacityWidget()
    widget.set_summary(summary(), Decimal("10"))
    assert "25" in widget.status_label.text()
    assert "剩餘" in widget.detail_label.text()
    assert widget.progress_bar.value() == 25


def test_capacity_widget_over_budget_keeps_uncapped_label_and_capped_bar(qapp):
    widget = BudgetCapacityWidget()
    widget.set_summary(summary(total=Decimal("12.5")), Decimal("10"))
    assert "125" in widget.status_label.text()
    assert "超出" in widget.detail_label.text()
    assert "仍會正常錄音" in widget.detail_label.text()
    assert widget.progress_bar.value() == 100


def test_capacity_widget_unavailable_has_no_percentage(qapp):
    widget = BudgetCapacityWidget()
    widget.set_summary(summary(total=None, available=False), Decimal("10"))
    assert "無法取得" in widget.status_label.text()
    assert "%" not in widget.status_label.text()
    assert widget.progress_bar.value() == 0
