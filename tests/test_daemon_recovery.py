from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import wave

import pytest
from PyQt6.QtWidgets import QApplication

from speedytype.config import AppConfig
from speedytype.daemon import DaemonController, report_recoverable_recordings
from speedytype.flac_upload import UploadPreparationError
from speedytype.recording_recovery import RecoveryRecord, create_recording_path, recording_sidecar_path


class _ControlledThread:
    def __init__(self, *, target, daemon, args=()):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.started = False
        self.joined = False

    def start(self):
        self.started = True
        if getattr(self.target, "__name__", "") == "<lambda>":
            self.target(*self.args)

    def is_alive(self):
        return self.started and not self.joined

    def join(self):
        self.joined = True


def _orchestration_controller(tmp_path, monkeypatch, *, mode="hold", max_seconds=100.0):
    app = QApplication.instance() or QApplication([])
    controller = DaemonController(
        AppConfig(
            openai_api_key="x",
            gemini_api_key="y",
            recording_mode=mode,
            max_record_seconds=max_seconds,
        )
    )
    paths = iter(tmp_path / f"recording-{index}.wav" for index in range(10))
    recorder_calls = []
    processed = []
    threads = []

    def thread_factory(*, target, daemon, args=()):
        thread = _ControlledThread(target=target, daemon=daemon, args=args)
        threads.append(thread)
        return thread

    controller.recorder = SimpleNamespace(
        stop=lambda: recorder_calls.append("stop"),
        record_until_stop=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr("speedytype.daemon.temp_wav_path", lambda: next(paths))
    monkeypatch.setattr("speedytype.daemon.threading.Thread", thread_factory)
    monkeypatch.setattr(
        "speedytype.daemon.process_wav",
        lambda path, *args, **kwargs: processed.append(path),
    )
    return app, controller, recorder_calls, processed, threads


def test_hold_activation_starts_once_and_release_processes_once(tmp_path, monkeypatch):
    _, controller, recorder_calls, processed, threads = _orchestration_controller(tmp_path, monkeypatch)
    monkeypatch.setattr("speedytype.daemon.wait_until_hotkey_released", lambda *args: ("released", 1.0))

    controller.on_press()
    controller.on_press()
    controller._finish_after_release()
    controller._finish_after_release()

    assert len([thread for thread in threads if not thread.daemon]) == 1
    assert recorder_calls == ["stop"]
    assert processed == [tmp_path / "recording-0.wav"]


def test_toggle_release_rearms_and_second_activation_processes_once(tmp_path, monkeypatch):
    _, controller, recorder_calls, processed, threads = _orchestration_controller(
        tmp_path, monkeypatch, mode="toggle"
    )
    monkeypatch.setattr("speedytype.daemon.wait_until_hotkey_released", lambda *args: ("released", 1.0))

    controller.on_press()
    controller.on_press()
    controller._finish_after_release()
    controller.on_press()

    assert len([thread for thread in threads if not thread.daemon]) == 1
    assert recorder_calls == ["stop"]
    assert processed == [tmp_path / "recording-0.wav"]


@pytest.mark.parametrize("mode", ["hold", "toggle"])
def test_deadline_uses_idempotent_stop_path_and_later_events_do_not_reprocess(
    tmp_path, monkeypatch, mode
):
    app, controller, recorder_calls, processed, _ = _orchestration_controller(
        tmp_path, monkeypatch, mode=mode
    )
    events = []
    controller.show_auto_stopped_signal.connect(lambda: events.append("auto-stopped"))
    controller.show_processing_signal.connect(lambda: events.append("processing"))
    monkeypatch.setattr("speedytype.daemon.wait_until_hotkey_released", lambda *args: ("timeout", 100.0))

    controller.on_press()
    controller._finish_after_release()
    controller._finish_after_release()
    controller.on_press()
    app.processEvents()

    assert recorder_calls == ["stop"]
    assert processed == [tmp_path / "recording-0.wav"]
    assert events == ["auto-stopped", "processing"]


def test_ticker_emits_elapsed_then_final_minute_countdown_and_times_out(tmp_path, monkeypatch):
    app, controller, recorder_calls, processed, _ = _orchestration_controller(tmp_path, monkeypatch)
    elapsed_updates = []
    countdown_updates = []
    controller.show_elapsed_signal.connect(elapsed_updates.append)
    controller.show_countdown_signal.connect(countdown_updates.append)
    clock = iter([0.0, 1.0, 39.0, 40.0, 100.0])
    monkeypatch.setattr("speedytype.daemon.time.perf_counter", lambda: next(clock))
    monkeypatch.setattr("speedytype.daemon.time.sleep", lambda _seconds: None)

    controller.on_press()
    controller._run_countdown_ticker(0.0)

    assert elapsed_updates == [1, 39]
    assert countdown_updates == [60, 0]
    assert recorder_calls == ["stop"]
    assert processed == [tmp_path / "recording-0.wav"]
    app.processEvents()


def test_timeout_warning_does_not_delay_processing_worker(tmp_path, monkeypatch):
    app, controller, _, processed, _ = _orchestration_controller(tmp_path, monkeypatch)
    signal_order = []
    controller.show_auto_stopped_signal.connect(lambda: signal_order.append("auto-stopped"))
    controller.show_processing_signal.connect(lambda: signal_order.append("processing"))
    monkeypatch.setattr("speedytype.daemon.wait_until_hotkey_released", lambda *args: ("timeout", 100.0))

    controller.on_press()
    controller._finish_after_release()

    assert processed == [tmp_path / "recording-0.wav"]
    app.processEvents()
    assert signal_order == ["auto-stopped", "processing"]


def test_recording_worker_failure_returns_idle_and_deadline_cannot_process_failed_take(
    tmp_path, monkeypatch
):
    _, controller, recorder_calls, processed, threads = _orchestration_controller(tmp_path, monkeypatch)
    monkeypatch.setattr(
        controller.recorder,
        "record_until_stop",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("microphone failed")),
    )
    monkeypatch.setattr("speedytype.daemon.wait_until_hotkey_released", lambda *args: ("timeout", 100.0))

    controller.on_press()
    controller._record_active_path()
    controller._finish_after_release()
    controller.on_press()

    assert recorder_calls == []
    assert processed == []
    assert len([thread for thread in threads if not thread.daemon]) == 2


def test_recording_worker_failure_while_stop_joins_does_not_start_processing(tmp_path, monkeypatch):
    app, controller, recorder_calls, processed, _ = _orchestration_controller(tmp_path, monkeypatch)
    monkeypatch.setattr(
        controller.recorder,
        "record_until_stop",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("microphone failed during stop")),
    )
    monkeypatch.setattr("speedytype.daemon.wait_until_hotkey_released", lambda *args: ("timeout", 100.0))

    controller.on_press()
    controller._active_thread.join = controller._record_active_path
    controller._finish_after_release()

    assert recorder_calls == ["stop"]
    assert processed == []
    app.processEvents()


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


def test_daemon_never_constructs_hybrid_transcriber_for_daily_recording(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        openai_api_key="x",
        gemini_api_key="y",
        hybrid_transcription_enabled=True,
        hybrid_threshold_seconds=1.0,
    )
    controller = DaemonController(config)
    controller._active_path = tmp_path / "recording.wav"
    started = []

    class FakeThread:
        def __init__(self, *, target, daemon, args=()):
            self.target = target
            self.args = args

        def start(self):
            started.append((self.target, self.args))

    monkeypatch.setattr("speedytype.daemon.temp_wav_path", lambda: controller._active_path)
    monkeypatch.setattr("speedytype.daemon.threading.Thread", FakeThread)

    controller.on_press()

    assert controller._hybrid_transcriber is None
    assert started
    app.processEvents()


def test_upload_refusal_notification_reports_preserved_wav_and_category(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    controller = DaemonController(AppConfig(openai_api_key="x", gemini_api_key="y"))
    path = tmp_path / "retained.wav"
    notifications = []
    controller.processing_error_signal.connect(notifications.append)
    monkeypatch.setattr(
        "speedytype.daemon.process_wav",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            UploadPreparationError("upload_too_large", path)
        ),
    )

    controller._process_recording(path)
    app.processEvents()

    assert len(notifications) == 1
    assert "upload_too_large" in notifications[0]
    assert str(path) in notifications[0]
