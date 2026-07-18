from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PyQt6.QtWidgets import QApplication

from speedytype.config import AppConfig
from speedytype.daemon import DaemonController
from speedytype.recording_control import RecordingPhase
from speedytype.recording_recovery import create_recording_path, recording_sidecar_path


class ControlledThread:
    def __init__(self, *, target, daemon, args=()):
        self.target = target
        self.daemon = daemon
        self.args = args
        self.started = False
        self.joined = False

    def start(self):
        self.started = True

    def join(self, timeout=None):
        del timeout
        self.joined = True

    def is_alive(self):
        return self.started and not self.joined


def _controller(tmp_path, monkeypatch, *, mode="hold"):
    app = QApplication.instance() or QApplication([])
    path = create_recording_path(directory=tmp_path)
    recorder_calls = []
    processed = []
    threads = []

    def thread_factory(*, target, daemon, args=()):
        thread = ControlledThread(target=target, daemon=daemon, args=args)
        threads.append(thread)
        return thread

    controller = DaemonController(
        AppConfig(
            openai_api_key="x",
            gemini_api_key="y",
            recording_mode=mode,
            hotkey="f9",
        ),
        activation_threshold_seconds=0.08,
        daemon_log_path=tmp_path / "speedytype_daemon.log",
    )
    controller._test_app = app
    controller.recorder = SimpleNamespace(
        stop=lambda: recorder_calls.append("stop"),
        record_until_stop=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr("speedytype.daemon.temp_wav_path", lambda: path)
    monkeypatch.setattr("speedytype.daemon.threading.Thread", thread_factory)
    monkeypatch.setattr(
        "speedytype.daemon.process_wav",
        lambda wav, *args, **kwargs: processed.append(wav),
    )
    return controller, path, recorder_calls, processed, threads


def test_provisional_capture_starts_without_recording_ui(tmp_path, monkeypatch):
    controller, path, _, _, threads = _controller(tmp_path, monkeypatch)
    shown = []
    controller.show_recording_signal.connect(lambda: shown.append("recording"))

    controller.on_press()

    session = controller._active_session
    assert session is not None
    assert session.path == path
    assert session.thread.started is True
    assert session.candidate.intent == "start"
    assert controller._recording_control.phase is RecordingPhase.PENDING_START
    assert shown == []
    assert len(threads) == 3  # capture, release, confirmation


def test_confirmation_shows_recording_ui_and_starts_countdown(tmp_path, monkeypatch):
    controller, _, _, _, _ = _controller(tmp_path, monkeypatch)
    shown = []
    controller.show_recording_signal.connect(lambda: shown.append("recording"))
    controller.on_press()
    session = controller._active_session

    controller._resolve_candidate(
        session,
        session.candidate,
        key_active=True,
        held_seconds=0.08,
    )

    assert shown == ["recording"]
    assert session.confirmed is True
    assert session.countdown_thread.started is True
    assert controller._recording_control.phase is RecordingPhase.RECORDING_ARMED


def test_short_start_removes_artifacts_logs_once_and_never_processes(
    tmp_path, monkeypatch
):
    controller, path, recorder_calls, processed, _ = _controller(tmp_path, monkeypatch)
    controller.on_press()
    session = controller._active_session

    controller._resolve_candidate(
        session,
        session.candidate,
        key_active=False,
        held_seconds=0.0243,
    )

    assert recorder_calls == ["stop"]
    assert session.thread.joined is True
    assert controller._active_session is None
    assert controller._recording_control.phase is RecordingPhase.IDLE
    assert not path.exists()
    assert not recording_sidecar_path(path).exists()
    assert processed == []
    lines = (tmp_path / "speedytype_daemon.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert '"intent":"start"' in lines[0]
    assert '"cleanup":"removed"' in lines[0]


def test_short_toggle_stop_keeps_capture_and_ui_alive(tmp_path, monkeypatch):
    controller, path, recorder_calls, processed, _ = _controller(
        tmp_path, monkeypatch, mode="toggle"
    )
    controller.on_press()
    session = controller._active_session
    start = session.candidate
    controller._resolve_candidate(session, start, key_active=True, held_seconds=0.08)
    controller._release_candidate(session, start, held_seconds=0.1)
    assert controller._recording_control.phase is RecordingPhase.RECORDING_ARMED

    controller.on_press()
    stop = session.candidate
    assert stop.intent == "stop"
    assert controller._recording_control.phase is RecordingPhase.PENDING_STOP
    controller._resolve_candidate(session, stop, key_active=False, held_seconds=0.02)

    assert controller._active_session is session
    assert session.path == path
    assert session.thread.joined is False
    assert recorder_calls == []
    assert processed == []
    assert controller._recording_control.phase is RecordingPhase.RECORDING_ARMED
    line = (tmp_path / "speedytype_daemon.log").read_text(encoding="utf-8")
    assert '"intent":"stop"' in line
    assert '"cleanup":"not-applicable"' in line


def test_cleanup_failure_retains_evidence_and_does_not_process(tmp_path, monkeypatch):
    controller, path, recorder_calls, processed, _ = _controller(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "speedytype.daemon.remove_unconfirmed_recording",
        lambda wav: (_ for _ in ()).throw(OSError("locked")),
    )
    controller.on_press()
    session = controller._active_session

    controller._resolve_candidate(
        session,
        session.candidate,
        key_active=False,
        held_seconds=0.01,
    )

    assert recorder_calls == ["stop"]
    assert path.exists()
    assert recording_sidecar_path(path).exists()
    assert processed == []
    assert controller._active_session is None
    line = (tmp_path / "speedytype_daemon.log").read_text(encoding="utf-8")
    assert '"cleanup":"retained-after-failure"' in line


def test_confirmation_worker_setup_failure_retains_evidence(tmp_path, monkeypatch):
    controller, path, recorder_calls, processed, _ = _controller(tmp_path, monkeypatch)
    notifications = []
    controller.processing_error_signal.connect(notifications.append)
    controller.on_press()
    session = controller._active_session

    def fail_countdown(*, target, daemon, args=()):
        if getattr(target, "__name__", "") == "_run_countdown_ticker":
            raise RuntimeError("thread unavailable")
        return ControlledThread(target=target, daemon=daemon, args=args)

    monkeypatch.setattr("speedytype.daemon.threading.Thread", fail_countdown)

    controller._resolve_candidate(
        session,
        session.candidate,
        key_active=True,
        held_seconds=0.08,
    )

    assert recorder_calls == ["stop"]
    assert processed == []
    assert controller._active_session is None
    assert path.exists()
    assert '"state": "failed-retained"' in recording_sidecar_path(path).read_text(
        encoding="utf-8"
    )
    assert notifications == [
        "Recording failed (RuntimeError). Daemon remains available."
    ]


def test_release_duration_is_measured_from_raw_activation(tmp_path, monkeypatch):
    controller, path, recorder_calls, processed, _ = _controller(tmp_path, monkeypatch)
    controller.on_press()
    session = controller._active_session
    candidate = session.candidate
    controller._monotonic = lambda: candidate.started_at + 0.1
    monkeypatch.setattr(
        "speedytype.daemon.wait_until_hotkey_released",
        lambda *args: ("released", 0.001),
    )

    controller._finish_after_release(session, candidate)

    assert recorder_calls == ["stop"]
    assert processed == []  # controlled processing thread has not executed
    assert session.path == path
    assert controller._recording_control.phase is RecordingPhase.PROCESSING


def test_toggle_stop_worker_setup_failure_rearms_recording(tmp_path, monkeypatch):
    controller, _, recorder_calls, processed, _ = _controller(
        tmp_path, monkeypatch, mode="toggle"
    )
    controller.on_press()
    session = controller._active_session
    start = session.candidate
    controller._resolve_candidate(session, start, key_active=True, held_seconds=0.08)
    controller._release_candidate(session, start, held_seconds=0.1)

    monkeypatch.setattr(
        "speedytype.daemon.threading.Thread",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("thread unavailable")),
    )

    controller.on_press()

    assert controller._active_session is session
    assert controller._recording_control.phase is RecordingPhase.RECORDING_ARMED
    assert session.candidate is None
    assert recorder_calls == []
    assert processed == []
