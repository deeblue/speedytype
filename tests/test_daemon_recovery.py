from __future__ import annotations

from pathlib import Path
import wave

from PyQt6.QtWidgets import QApplication

from speedytype.config import AppConfig
from speedytype.daemon import DaemonController, report_recoverable_recordings
from speedytype.recording_recovery import RecoveryRecord, create_recording_path, recording_sidecar_path


def test_processing_failure_is_sanitized_hides_overlay_and_controller_is_reusable(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    controller = DaemonController(AppConfig(openai_api_key="secret", gemini_api_key="secret"))
    notifications = []
    hidden = []
    controller.processing_error_signal.connect(notifications.append)
    controller.hide_signal.connect(lambda: hidden.append(True))

    monkeypatch.setattr(
        "speedytype.daemon.process_wav",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Bearer sk-secret provider body")),
    )
    controller._process_recording(Path(tmp_path / "first.wav"))
    app.processEvents()

    assert hidden == [True]
    assert len(notifications) == 1
    assert "RuntimeError" in notifications[0]
    assert "secret" not in notifications[0]
    assert "provider body" not in notifications[0]

    monkeypatch.setattr("speedytype.daemon.process_wav", lambda *args, **kwargs: None)
    controller._process_recording(Path(tmp_path / "second.wav"))
    app.processEvents()
    assert hidden == [True, True]
    assert len(notifications) == 1


def test_recording_worker_failure_is_sanitized_and_hides_overlay(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    controller = DaemonController(AppConfig(openai_api_key="secret", gemini_api_key="secret"))
    notifications = []
    hidden = []
    controller.processing_error_signal.connect(notifications.append)
    controller.hide_signal.connect(lambda: hidden.append(True))
    controller._active_path = create_recording_path(directory=tmp_path)
    monkeypatch.setattr(
        controller.recorder,
        "record_until_stop",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("secret microphone detail")),
    )

    controller._record_active_path()
    app.processEvents()

    assert hidden == [True]
    assert notifications == ["Recording failed (OSError). Daemon remains available."]
    assert '"state": "failed-retained"' in recording_sidecar_path(
        controller._active_path
    ).read_text(encoding="utf-8")


def test_short_recording_bypasses_hybrid_finish_before_pipeline_guard(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "short.wav"
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16_000)
        wav_file.writeframes(b"\0\0" * 160)
    controller = DaemonController(AppConfig(openai_api_key="x", gemini_api_key="y"))
    controller._hybrid_transcriber = type(
        "Hybrid",
        (),
        {"finish": lambda self, audio: (_ for _ in ()).throw(AssertionError("hybrid must not run"))},
    )()
    calls = []
    monkeypatch.setattr("speedytype.daemon.process_wav", lambda *args, **kwargs: calls.append((args, kwargs)))

    controller._process_recording(path)
    app.processEvents()

    assert len(calls) == 1
    assert calls[0][1]["usage_scope"] == "daily"


def test_startup_recovery_reports_paths_without_processing(tmp_path, monkeypatch):
    wav_path = tmp_path / "retained.wav"
    records = (RecoveryRecord(wav_path, "failed-retained", "id-1", "RuntimeError"),)
    printed = []
    shown = []
    tray = type("Tray", (), {"showMessage": lambda self, *args: shown.append(args)})()
    monkeypatch.setattr("speedytype.daemon.safe_print", lambda message, **kwargs: printed.append(message))

    report_recoverable_recordings(tray, records)

    assert any(str(wav_path) in line for line in printed)
    assert shown and "1" in shown[0][1]
