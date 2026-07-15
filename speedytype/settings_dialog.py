from __future__ import annotations

import threading
import sys
import warnings
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from speedytype.audio import list_input_devices
from speedytype.autostart import install_autostart, query_autostart, uninstall_autostart
from speedytype.config import AppConfig
from speedytype.env_writer import mask_secret, test_gemini_key, test_minimax_key, test_openai_key
from speedytype.icon import build_app_icon
from speedytype.hotkey import PlatformPermissionError, capture_hotkey
from speedytype.paths import default_env_path, default_pricing_path, default_settings_path
from speedytype.pricing_dialog import PriceEditorDialog
from speedytype.secrets_store import SecretStoreError, delete_api_key, set_api_key
from speedytype.settings import (
    MAX_MAX_RECORD_SECONDS,
    MIN_MAX_RECORD_SECONDS,
    AppSettings,
    DEFAULT_VOCAB_TERMS,
    export_vocab,
    hotkey_has_modifier_or_is_function_key,
    import_vocab,
    load_settings,
    save_settings,
)
from speedytype.usage_stats import calculate_usage


# Best-effort, non-exhaustive: a static denylist of well-known Windows/common
# app shortcuts. Real-time conflict detection against arbitrary other
# background programs is not reliably automatable, so this is a warning
# hint, not a guarantee of no conflicts. See KNOWN_LIMITATIONS.md.
WINDOWS_RESERVED_SHORTCUTS = {
    "ctrl+alt+delete",
    "ctrl+shift+esc",
    "alt+f4",
    "alt+tab",
    "ctrl+alt+tab",
    "windows+l",
    "windows+d",
    "windows+e",
    "windows+r",
    "windows+tab",
    "windows+shift+s",
    "win+l",
    "win+d",
    "win+e",
    "win+r",
    "win+tab",
    "win+shift+s",
    "ctrl+shift+space",
}
MACOS_RESERVED_SHORTCUTS = {
    "cmd+space",
    "cmd+tab",
    "cmd+alt+esc",
    "cmd+shift+3",
    "cmd+shift+4",
    "cmd+shift+5",
    "ctrl+cmd+q",
    "cmd+h",
    "cmd+m",
}
KNOWN_RESERVED_SHORTCUTS = MACOS_RESERVED_SHORTCUTS if sys.platform == "darwin" else WINDOWS_RESERVED_SHORTCUTS

SYSTEM_DEFAULT_DEVICE_LABEL = "系統預設裝置"


def format_seconds_readable(seconds: float) -> str:
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    if minutes and secs:
        return f"{minutes} 分 {secs} 秒"
    if minutes:
        return f"{minutes} 分鐘"
    return f"{secs} 秒"


class HotkeyCaptureSignal(QObject):
    """Thread-safe bridge: keyboard.read_hotkey() blocks on a worker thread;
    this signal delivers the captured combo string back to the GUI thread."""

    captured = pyqtSignal(str)


class MaskedKeyField(QWidget):
    """One API key row: masked-by-default value, reveal/hide toggle, and a
    minimal-cost test-connection button using whatever is currently in the
    field (not necessarily the saved value)."""

    def __init__(self, label: str, initial_value: str, test_func, parent=None) -> None:
        super().__init__(parent)
        self._value = initial_value
        self._revealed = False
        self._test_func = test_func

        layout = QHBoxLayout(self)
        layout.addWidget(QLabel(label))

        self.line_edit = QLineEdit()
        self.line_edit.setReadOnly(True)
        self.line_edit.setText(mask_secret(self._value))
        layout.addWidget(self.line_edit, 1)

        self.toggle_button = QPushButton("顯示")
        self.toggle_button.clicked.connect(self._toggle_reveal)
        layout.addWidget(self.toggle_button)

        self.test_button = QPushButton("測試連線")
        self.test_button.clicked.connect(self._run_test)
        layout.addWidget(self.test_button)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

    def _sync_value_from_field_if_editable(self) -> None:
        if not self.line_edit.isReadOnly():
            self._value = self.line_edit.text()

    def _toggle_reveal(self) -> None:
        self._sync_value_from_field_if_editable()
        self._revealed = not self._revealed
        if self._revealed:
            self.line_edit.setReadOnly(False)
            self.line_edit.setText(self._value)
            self.toggle_button.setText("隱藏")
        else:
            self.line_edit.setReadOnly(True)
            self.line_edit.setText(mask_secret(self._value))
            self.toggle_button.setText("顯示")

    def current_value(self) -> str:
        self._sync_value_from_field_if_editable()
        return self._value

    def _run_test(self) -> None:
        self.status_label.setText("測試中...")
        try:
            ok, _message = self._test_func(self.current_value())
        except Exception:
            ok = False
        self.status_label.setText("連線測試成功" if ok else "連線測試失敗")


class SettingsDialog(QDialog):
    # Emitted on Save with the new vocab bias string, so the running daemon
    # can apply it immediately without a restart.
    vocab_applied = pyqtSignal(str)

    def __init__(
        self,
        config: AppConfig,
        env_path: str | Path | None,
        settings_path: str | Path | None,
        parent=None,
        pricing_path: str | Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.env_path = str(env_path or default_env_path())
        self.settings_path = str(settings_path or default_settings_path())
        self.pricing_path = Path(pricing_path) if pricing_path is not None else default_pricing_path()
        self._saved_key_values = {
            "OPENAI_API_KEY": config.openai_api_key,
            "GEMINI_API_KEY": config.gemini_api_key,
            "MINIMAX_API_KEY": config.minimax_api_key,
        }
        self.setWindowTitle("SpeedyType 設定")
        self.setWindowIcon(build_app_icon())
        self.setMinimumWidth(520)

        self._settings = load_settings(self.settings_path)
        self._pending_hotkey_combo = list(self._settings.hotkey_combo)
        self._vocab_terms = list(self._settings.vocab_terms)
        self._hotkey_capture_signal = HotkeyCaptureSignal()
        self._hotkey_capture_signal.captured.connect(self._on_hotkey_captured)
        self._autostart_enabled, _ = query_autostart()

        layout = QVBoxLayout(self)
        self.settings_scroll_area = QScrollArea()
        self.settings_scroll_area.setWidgetResizable(True)
        self.settings_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_contents = QWidget()
        settings_layout = QVBoxLayout(scroll_contents)
        self.settings_scroll_area.setWidget(scroll_contents)

        settings_layout.addWidget(self._build_record_seconds_group())
        settings_layout.addWidget(self._build_hotkey_group())
        settings_layout.addWidget(self._build_device_group())
        settings_layout.addWidget(self._build_vocab_group())
        settings_layout.addWidget(self._build_keys_group())
        settings_layout.addWidget(self._build_usage_group())
        self._refresh_usage()

        self.autostart_checkbox = QCheckBox("開機時自動啟動")
        self.autostart_checkbox.setChecked(self._autostart_enabled)
        settings_layout.addWidget(self.autostart_checkbox)
        settings_layout.addStretch(1)
        layout.addWidget(self.settings_scroll_area, 1)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        button_bar = QHBoxLayout()
        save_button = QPushButton("儲存")
        save_button.clicked.connect(self._save)
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.close)
        button_bar.addWidget(save_button)
        button_bar.addWidget(cancel_button)
        layout.addLayout(button_bar)

    # --- max record seconds -------------------------------------------------

    def _build_record_seconds_group(self) -> QGroupBox:
        group = QGroupBox("最大錄音時間")
        group_layout = QVBoxLayout(group)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(int(MIN_MAX_RECORD_SECONDS))
        self.slider.setMaximum(int(MAX_MAX_RECORD_SECONDS))
        self.slider.setValue(int(self._settings.max_record_seconds))
        self.slider.valueChanged.connect(self._on_slider_changed)

        self.slider_label = QLabel(format_seconds_readable(self._settings.max_record_seconds))

        group_layout.addWidget(self.slider)
        group_layout.addWidget(self.slider_label)
        group_layout.addWidget(self._restart_note())
        return group

    # --- usage and estimated costs -----------------------------------------

    def _build_usage_group(self) -> QGroupBox:
        group = QGroupBox("用量與估算費用")
        group_layout = QVBoxLayout(group)

        self.usage_models_label = QLabel("")
        self.usage_stt_label = QLabel("")
        self.usage_llm_label = QLabel("")
        self.usage_total_label = QLabel("")
        self.usage_pricing_note_label = QLabel("")
        self.usage_warning_label = QLabel("")
        for label in (
            self.usage_models_label,
            self.usage_stt_label,
            self.usage_llm_label,
            self.usage_total_label,
            self.usage_pricing_note_label,
            self.usage_warning_label,
        ):
            label.setWordWrap(True)
            group_layout.addWidget(label)
        self.edit_pricing_button = QPushButton("編輯價格")
        self.edit_pricing_button.clicked.connect(self._edit_pricing)
        group_layout.addWidget(self.edit_pricing_button)
        return group

    def _edit_pricing(self) -> None:
        dialog = PriceEditorDialog(self.pricing_path, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._refresh_usage()

    @staticmethod
    def _format_usage_cost(cost, currency: str) -> str:
        if cost is None:
            return "無法估算"
        currency_suffix = f" {currency}" if currency else ""
        return f"${cost:.6f}{currency_suffix}"

    def _refresh_usage(self) -> None:
        # The summary itself retains all warning details; suppress the pure
        # parser's Python warning here because the same condition is rendered
        # visibly in the dialog.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            summary = calculate_usage(self.config.latency_log_path, self.pricing_path)

        usage_unavailable = not summary.usage_available
        stt_cost = None if usage_unavailable else summary.stt_cost
        llm_cost = None if usage_unavailable else summary.llm_cost
        total_cost = None if usage_unavailable else summary.total_cost
        if usage_unavailable:
            self.usage_models_label.setText("目前使用模型：用量無法取得")
            self.usage_stt_label.setText("STT：用量無法取得，估算費用 無法估算")
            self.usage_llm_label.setText("LLM：用量無法取得，估算費用 無法估算")
        else:
            stt_models = ", ".join(summary.stt_models) or "無紀錄"
            llm_models = ", ".join(summary.llm_models) or "無紀錄"
            self.usage_models_label.setText(f"目前使用模型：STT {stt_models}；LLM {llm_models}")
            self.usage_stt_label.setText(
                f"STT：{summary.stt_calls:,} 次呼叫，{summary.stt_minutes:.2f} 分鐘，"
                f"估算費用 {self._format_usage_cost(stt_cost, summary.currency)}"
            )
            self.usage_llm_label.setText(
                f"LLM：{summary.llm_calls:,} 次呼叫，輸入 {summary.llm_input_tokens:,} tokens，"
                f"輸出 {summary.llm_output_tokens:,} tokens，"
                f"估算費用 {self._format_usage_cost(llm_cost, summary.currency)}"
            )
        self.usage_total_label.setText(
            f"總估算費用：{self._format_usage_cost(total_cost, summary.currency)}"
        )

        pricing_date = summary.pricing_updated_date or "無法取得"
        self.usage_pricing_note_label.setText(
            f"價格更新日期：{pricing_date}\n估算費用，非實際帳單，價格可能已變動"
        )

        warning_messages = []
        pricing_warning_prefixes = (
            "Pricing data unavailable:",
            "Invalid price for ",
            "STT price unavailable for used model ",
            "LLM price unavailable for used model ",
        )
        pricing_warning_count = sum(
            message.startswith(pricing_warning_prefixes) for message in summary.warnings
        )
        if pricing_warning_count or (
            not usage_unavailable
            and (summary.stt_cost is None or summary.llm_cost is None or summary.total_cost is None)
        ):
            warning_messages.append("價格資料缺失，無法估算費用")
        if summary.legacy_inferred_rows:
            warning_messages.append(
                f"有 {summary.legacy_inferred_rows:,} 筆舊版紀錄依標籤推定為每日用量"
            )
        usage_unavailable_warning_count = sum(
            message.startswith("Usage data unavailable:") for message in summary.warnings
        )
        if usage_unavailable:
            warning_messages.append("用量資料缺失，無法確認實際用量與費用")
        skipped_rows = sum(
            message.startswith("Skipped malformed CSV row") for message in summary.warnings
        )
        if skipped_rows:
            warning_messages.append(f"已略過 {skipped_rows:,} 筆格式錯誤的用量紀錄")
        uncategorized_warnings = (
            len(summary.warnings)
            - pricing_warning_count
            - usage_unavailable_warning_count
            - skipped_rows
        )
        if uncategorized_warnings > 0:
            warning_messages.append(f"其他用量或價格資料警告：{uncategorized_warnings:,} 筆")
        self.usage_warning_label.setText("；".join(warning_messages))

    def _on_slider_changed(self, value: int) -> None:
        self.slider_label.setText(format_seconds_readable(value))

    # --- hotkey --------------------------------------------------------------

    def _build_hotkey_group(self) -> QGroupBox:
        group = QGroupBox("啟動熱鍵")
        group_layout = QVBoxLayout(group)

        self.hotkey_label = QLabel(f"目前：{'+'.join(self._pending_hotkey_combo)}")
        self.capture_button = QPushButton("擷取新組合鍵")
        self.capture_button.clicked.connect(self._start_capture)
        self.hotkey_warning_label = QLabel("")
        self.hotkey_warning_label.setWordWrap(True)

        group_layout.addWidget(self.hotkey_label)
        group_layout.addWidget(self.capture_button)
        group_layout.addWidget(self.hotkey_warning_label)
        group_layout.addWidget(self._restart_note())
        return group

    def _start_capture(self) -> None:
        self.capture_button.setEnabled(False)
        self.capture_button.setText("請按下想要的組合鍵...")
        self.hotkey_warning_label.setText("")

        def worker() -> None:
            try:
                combo = capture_hotkey()
            except PlatformPermissionError:
                self._hotkey_capture_signal.captured.emit("")
                return
            self._hotkey_capture_signal.captured.emit(combo)

        threading.Thread(target=worker, daemon=True).start()

    def _on_hotkey_captured(self, combo_string: str) -> None:
        self.capture_button.setEnabled(True)
        self.capture_button.setText("擷取新組合鍵")
        if not combo_string:
            self.hotkey_warning_label.setText(
                "無法擷取熱鍵。請到 macOS 系統設定 > 隱私權與安全性，允許 Accessibility 與 Input Monitoring。"
            )
            return
        parts = combo_string.split("+")

        if not hotkey_has_modifier_or_is_function_key(parts):
            self.hotkey_warning_label.setText(
                f"「{combo_string}」不符合要求：組合鍵需包含至少一個修飾鍵"
                "（Ctrl/Alt/Shift/Win），或為單一功能鍵（F1-F24）。未套用，請重新擷取。"
            )
            return

        self._pending_hotkey_combo = parts
        self.hotkey_label.setText(f"目前：{combo_string}（尚未儲存）")

        if combo_string.lower() in KNOWN_RESERVED_SHORTCUTS:
            self.hotkey_warning_label.setText(
                f"注意：「{combo_string}」可能已被作業系統或其他常駐程式使用，建議換一組。"
            )
        else:
            self.hotkey_warning_label.setText("")

    # --- recording device ----------------------------------------------------

    def _build_device_group(self) -> QGroupBox:
        group = QGroupBox("錄音裝置")
        group_layout = QVBoxLayout(group)

        if self.config.mic_device_warning:
            warning_label = QLabel(self.config.mic_device_warning)
            warning_label.setWordWrap(True)
            warning_label.setStyleSheet("color: #cc4444;")
            group_layout.addWidget(warning_label)

        self.device_combo = QComboBox()
        # Parallel list: index i's stored value ("" for system default, else
        # the exact device name) corresponds to device_combo item i.
        self._device_values: list[str] = [""]
        self.device_combo.addItem(SYSTEM_DEFAULT_DEVICE_LABEL)
        for device in list_input_devices():
            name = str(device["name"])
            self._device_values.append(name)
            self.device_combo.addItem(name)

        try:
            selected_index = self._device_values.index(self._settings.mic_device_name)
        except ValueError:
            selected_index = 0  # saved device name no longer present among current devices
        self.device_combo.setCurrentIndex(selected_index)

        group_layout.addWidget(self.device_combo)
        group_layout.addWidget(self._restart_note())
        return group

    # --- vocab -----------------------------------------------------------------

    def _build_vocab_group(self) -> QGroupBox:
        group = QGroupBox("使用者詞彙表")
        group_layout = QVBoxLayout(group)

        self.vocab_list = QListWidget()
        self.vocab_list.addItems(self._vocab_terms)
        group_layout.addWidget(self.vocab_list)

        add_row = QHBoxLayout()
        self.vocab_input = QLineEdit()
        add_button = QPushButton("新增")
        add_button.clicked.connect(self._add_vocab_term)
        add_row.addWidget(self.vocab_input)
        add_row.addWidget(add_button)
        group_layout.addLayout(add_row)

        button_row = QHBoxLayout()
        delete_button = QPushButton("刪除選取")
        delete_button.clicked.connect(self._delete_selected_vocab)
        reset_button = QPushButton("重置為預設")
        reset_button.clicked.connect(self._reset_vocab)
        export_button = QPushButton("匯出...")
        export_button.clicked.connect(self._export_vocab)
        import_button = QPushButton("匯入並取代...")
        import_button.clicked.connect(self._import_vocab)
        for button in (delete_button, reset_button, export_button, import_button):
            button_row.addWidget(button)
        group_layout.addLayout(button_row)
        group_layout.addWidget(QLabel("變更立即生效，下一次語音辨識即套用，不需重新啟動。"))
        return group

    def _add_vocab_term(self) -> None:
        term = self.vocab_input.text().strip()
        if term and term not in self._vocab_terms:
            self._vocab_terms.append(term)
            self.vocab_list.addItem(term)
        self.vocab_input.clear()

    def _delete_selected_vocab(self) -> None:
        for item in self.vocab_list.selectedItems():
            if item.text() in self._vocab_terms:
                self._vocab_terms.remove(item.text())
            self.vocab_list.takeItem(self.vocab_list.row(item))

    def _reset_vocab(self) -> None:
        self._vocab_terms = list(DEFAULT_VOCAB_TERMS)
        self.vocab_list.clear()
        self.vocab_list.addItems(self._vocab_terms)

    def _export_vocab(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "匯出詞彙表", "vocab_export.json", "JSON (*.json)")
        if path:
            export_vocab(path, self._vocab_terms)
            self.status_label.setText(f"已匯出至 {path}")

    def _import_vocab(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "匯入並取代詞彙表", "", "JSON (*.json)")
        if not path:
            return
        try:
            terms = import_vocab(path)
        except Exception as exc:
            self.status_label.setText(f"匯入失敗：{exc}")
            return
        self._vocab_terms = terms
        self.vocab_list.clear()
        self.vocab_list.addItems(self._vocab_terms)
        self.status_label.setText(f"已從 {path} 匯入並取代詞彙表")

    # --- api keys ----------------------------------------------------------

    def _build_keys_group(self) -> QGroupBox:
        group = QGroupBox("API 金鑰")
        group_layout = QVBoxLayout(group)

        self.openai_field = MaskedKeyField("OpenAI", self.config.openai_api_key, test_openai_key)
        self.gemini_field = MaskedKeyField("Gemini", self.config.gemini_api_key, test_gemini_key)
        self.minimax_field = MaskedKeyField("MiniMax", self.config.minimax_api_key, test_minimax_key)
        group_layout.addWidget(self.openai_field)
        group_layout.addWidget(self.gemini_field)
        group_layout.addWidget(self.minimax_field)
        storage_note = QLabel(
            "金鑰主要儲存於系統保密管理機制（Windows Credential Manager / macOS Keychain）；"
            ".env 僅作為 keyring 不可用時的相容備援。"
        )
        storage_note.setWordWrap(True)
        group_layout.addWidget(storage_note)
        return group

    # --- save/cancel ---------------------------------------------------------

    def _restart_note(self) -> QLabel:
        label = QLabel("變更後需要重新啟動 daemon 才會生效（系統匣選單 -> 重新啟動）。")
        label.setWordWrap(True)
        return label

    def _save(self) -> None:
        messages = []

        chosen_device_name = self._device_values[self.device_combo.currentIndex()]
        new_settings = AppSettings(
            max_record_seconds=float(self.slider.value()),
            hotkey_combo=list(self._pending_hotkey_combo),
            vocab_terms=list(self._vocab_terms),
            mic_device_name=chosen_device_name,
        )
        save_settings(self.settings_path, new_settings)
        messages.append("一般設定已儲存")
        self.vocab_applied.emit(new_settings.vocab_bias_string)

        desired_autostart = self.autostart_checkbox.isChecked()
        if desired_autostart != self._autostart_enabled:
            if desired_autostart:
                ok, autostart_message = install_autostart(self.env_path)
            else:
                ok, autostart_message = uninstall_autostart()
            messages.append(("自動啟動：" if ok else "自動啟動失敗：") + autostart_message)
            if ok:
                self._autostart_enabled = desired_autostart

        key_changes = []
        for field, env_key in (
            (self.openai_field, "OPENAI_API_KEY"),
            (self.gemini_field, "GEMINI_API_KEY"),
            (self.minimax_field, "MINIMAX_API_KEY"),
        ):
            new_value = field.current_value()
            if new_value != self._saved_key_values[env_key]:
                try:
                    if new_value:
                        set_api_key(env_key, new_value)
                    else:
                        delete_api_key(env_key)
                except SecretStoreError as exc:
                    messages.append(f"金鑰儲存失敗（{env_key}）：{exc}")
                    continue
                self._saved_key_values[env_key] = new_value
                key_changes.append(env_key)

        if key_changes:
            messages.append(f"金鑰已更新（{', '.join(key_changes)}）")

        self.status_label.setText(" / ".join(messages))
