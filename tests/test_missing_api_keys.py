from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from speedytype.api import GroqRateLimitError, transcribe_audio_groq_request, transcribe_audio_request, transcribe_audio_result, polish_text, discover_flash_model
from speedytype.config import AppConfig, MissingApiKeyError
from speedytype.daemon import DaemonController
from speedytype.llm import call_gemini_polisher, call_openai_polisher, call_minimax_polisher


@pytest.mark.parametrize("action,key", [
    (lambda c: transcribe_audio_groq_request(Path("unused.wav"), c), "GROQ_API_KEY"),
    (lambda c: transcribe_audio_request(Path("unused.wav"), c), "OPENAI_API_KEY"),
    (lambda c: polish_text("text", c), "GEMINI_API_KEY"),
    (lambda c: discover_flash_model(c.gemini_api_key), "GEMINI_API_KEY"),
    (lambda c: call_gemini_polisher("text", c, model="model"), "GEMINI_API_KEY"),
    (lambda c: call_openai_polisher("text", c, model="model"), "OPENAI_API_KEY"),
    (lambda c: call_minimax_polisher("text", c, model="model"), "MINIMAX_API_KEY"),
])
def test_missing_key_is_reported_before_network_or_file_access(action, key):
    with pytest.raises(MissingApiKeyError) as error:
        action(AppConfig(openai_api_key="", gemini_api_key=""))
    assert error.value.key_name == key
    assert "設定頁面" in str(error.value)


def test_daemon_reports_missing_key_and_retains_recording(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    controller = DaemonController(AppConfig(openai_api_key="", gemini_api_key=""))
    notifications = []
    controller.processing_error_signal.connect(notifications.append)
    def fail(*args, **kwargs):
        raise MissingApiKeyError("GEMINI_API_KEY")
    monkeypatch.setattr("speedytype.daemon.process_wav", fail)
    path = tmp_path / "recording.wav"
    controller._process_recording(path)
    app.processEvents()
    assert len(notifications) == 1
    assert "GEMINI_API_KEY" in notifications[0]
    assert "設定頁面" in notifications[0]
    assert str(path) in notifications[0]


def test_groq_rate_limit_reports_missing_openai_fallback_key(monkeypatch):
    def rate_limited(*args, **kwargs):
        raise GroqRateLimitError("rate limited")
    monkeypatch.setattr("speedytype.api.transcribe_audio_groq_request", rate_limited)
    config = AppConfig(openai_api_key="", gemini_api_key="", groq_api_key="configured")
    with pytest.raises(MissingApiKeyError) as error:
        transcribe_audio_result(Path("unused.wav"), config)
    assert error.value.key_name == "OPENAI_API_KEY"
