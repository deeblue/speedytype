from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import threading
import wave

import pytest
from PyQt6.QtWidgets import QApplication

from speedytype.config import AppConfig
import speedytype.daemon as daemon_module
from speedytype.daemon import DaemonController, report_recoverable_recordings
from speedytype.flac_upload import UploadPreparationError
from speedytype.recording_recovery import RecoveryRecord, create_recording_path, recording_sidecar_path
from speedytype.recording_control import RecordingPhase


_REAL_THREAD = threading.Thread


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
        ),
        activation_threshold_seconds=0,
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
    session = controller._active_session
    controller.on_press()
    controller._finish_after_release(session)
    controller._finish_after_release(session)

    assert len([thread for thread in threads if not thread.daemon]) == 1
    assert recorder_calls == ["stop"]
    assert processed == [tmp_path / "recording-0.wav"]


@pytest.mark.parametrize("mode", ["hold", "toggle"])
def test_start_path_failure_rolls_back_and_controller_is_reusable(tmp_path, monkeypatch, mode):
    app, controller, _, _, threads = _orchestration_controller(tmp_path, monkeypatch, mode=mode)
    notifications = []
    controller.processing_error_signal.connect(notifications.append)
    paths = iter((OSError("private temp detail"), tmp_path / "reused.wav"))

    def next_path():
        value = next(paths)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr("speedytype.daemon.temp_wav_path", next_path)

    controller.on_press()
    controller.on_press()
    app.processEvents()

    assert controller._active_session is not None
    assert controller._active_session.path == tmp_path / "reused.wav"
    assert len([thread for thread in threads if not thread.daemon]) == 1
    assert notifications == ["Recording failed (OSError). Daemon remains available."]
    assert "private temp detail" not in notifications[0]


@pytest.mark.parametrize("mode", ["hold", "toggle"])
@pytest.mark.parametrize("failure_point", ["construct", "start"])
def test_thread_setup_failure_retains_owned_path_and_controller_is_reusable(
    tmp_path, monkeypatch, mode, failure_point
):
    app = QApplication.instance() or QApplication([])
    controller = DaemonController(
        AppConfig(openai_api_key="x", gemini_api_key="y", recording_mode=mode),
        activation_threshold_seconds=0,
    )
    failed_path = create_recording_path(directory=tmp_path)
    reused_path = tmp_path / "reused.wav"
    paths = iter((failed_path, reused_path))
    notifications = []
    controller.processing_error_signal.connect(notifications.append)
    construction_calls = 0
    start_failed = False

    class SetupThread(_ControlledThread):
        def start(self):
            nonlocal start_failed
            if failure_point == "start" and not start_failed:
                start_failed = True
                raise RuntimeError("private start detail")
            super().start()

    def thread_factory(*, target, daemon, args=()):
        nonlocal construction_calls
        construction_calls += 1
        if failure_point == "construct" and construction_calls == 1:
            raise RuntimeError("private construct detail")
        return SetupThread(target=target, daemon=daemon, args=args)

    monkeypatch.setattr("speedytype.daemon.temp_wav_path", lambda: next(paths))
    monkeypatch.setattr("speedytype.daemon.threading.Thread", thread_factory)

    controller.on_press()
    controller.on_press()
    app.processEvents()

    assert '"state": "failed-retained"' in recording_sidecar_path(failed_path).read_text(encoding="utf-8")
    assert controller._active_session is not None
    assert controller._active_session.path == reused_path
    assert notifications == ["Recording failed (RuntimeError). Daemon remains available."]
    assert "private" not in notifications[0]


def test_auxiliary_start_failure_keeps_capture_owned_until_join_then_reuses(
    tmp_path, monkeypatch
):
    app = QApplication.instance() or QApplication([])
    controller = DaemonController(
        AppConfig(openai_api_key="x", gemini_api_key="y", max_record_seconds=10_000),
        activation_threshold_seconds=0,
    )
    capture_live = threading.Event()
    stop_a = threading.Event()
    draining_a = threading.Event()
    allow_a_exit = threading.Event()
    b_started = threading.Event()
    stop_b = threading.Event()
    release_b_waiter = threading.Event()
    recorder_calls = 0
    auxiliary_failed = False
    paths = iter(create_recording_path(directory=tmp_path) for _ in range(2))

    class Recorder:
        def record_until_stop(self, _path, **_kwargs):
            nonlocal recorder_calls
            recorder_calls += 1
            if recorder_calls == 1:
                capture_live.set()
                assert stop_a.wait(timeout=2)
                draining_a.set()
                assert allow_a_exit.wait(timeout=2)
                return
            b_started.set()
            assert stop_b.wait(timeout=2)

        def stop(self):
            if recorder_calls == 1:
                stop_a.set()
            else:
                stop_b.set()

    class FailingAuxThread:
        def start(self):
            raise RuntimeError("private auxiliary start detail")

        def is_alive(self):
            return False

        def join(self, timeout=None):
            return None

    def thread_factory(*, target, daemon, args=()):
        nonlocal auxiliary_failed
        if getattr(target, "__name__", "") == "_finish_after_release" and not auxiliary_failed:
            auxiliary_failed = True
            return FailingAuxThread()
        return _REAL_THREAD(target=target, args=args, daemon=daemon)

    controller.recorder = Recorder()
    monkeypatch.setattr("speedytype.daemon.temp_wav_path", lambda: next(paths))
    monkeypatch.setattr("speedytype.daemon.threading.Thread", thread_factory)
    monkeypatch.setattr(
        "speedytype.daemon.wait_until_hotkey_released",
        lambda *args: (release_b_waiter.wait(timeout=2), ("released", 1.0))[1],
    )

    rollback = _REAL_THREAD(target=controller.on_press)
    rollback.start()
    assert capture_live.wait(timeout=2)
    assert draining_a.wait(timeout=2)
    session_a = controller._active_session

    concurrent_press = _REAL_THREAD(target=controller.on_press)
    concurrent_press.start()
    concurrent_press.join(timeout=2)
    b_started_before_join = b_started.is_set()
    a_owned_before_join = controller._active_session is session_a

    allow_a_exit.set()
    rollback.join(timeout=2)
    idle_after_join = controller._active_session is None
    controller.on_press()
    reused_after_join = b_started.wait(timeout=2)

    controller.shutdown_active_recording()
    release_b_waiter.set()
    app.processEvents()

    assert b_started_before_join is False
    assert a_owned_before_join is True
    assert idle_after_join is True
    assert reused_after_join is True


def test_daemon_startup_instruction_matches_recording_mode():
    hold = daemon_module._daemon_recording_instruction(
        AppConfig(openai_api_key="x", gemini_api_key="y", hotkey="f9", recording_mode="hold")
    )
    toggle = daemon_module._daemon_recording_instruction(
        AppConfig(openai_api_key="x", gemini_api_key="y", hotkey="f9", recording_mode="toggle")
    )

    assert hold == "Hold F9 to record."
    assert toggle == "Press F9 once to start recording and again to stop."
    assert "Hold" not in toggle


def test_toggle_release_rearms_and_second_activation_processes_once(tmp_path, monkeypatch):
    _, controller, recorder_calls, processed, threads = _orchestration_controller(
        tmp_path, monkeypatch, mode="toggle"
    )
    monkeypatch.setattr("speedytype.daemon.wait_until_hotkey_released", lambda *args: ("released", 1.0))

    controller.on_press()
    session = controller._active_session
    controller.on_press()
    controller._finish_after_release(session)
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
    session = controller._active_session
    controller._finish_after_release(session)
    controller._finish_after_release(session)
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
    session = controller._active_session
    controller._run_countdown_ticker(session)

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
    controller._finish_after_release(controller._active_session)

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
    session = controller._active_session
    controller._record_session(session)
    controller._finish_after_release(session)
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
    session = controller._active_session
    session.thread.join = lambda: controller._record_session(session)
    controller._finish_after_release(session)

    assert recorder_calls == ["stop"]
    assert processed == []
    app.processEvents()


def test_failed_take_stop_owner_cannot_capture_or_process_new_take(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    controller = DaemonController(
        AppConfig(openai_api_key="x", gemini_api_key="y", max_record_seconds=10_000),
        activation_threshold_seconds=0,
    )
    allow_a_waiter = threading.Event()
    allow_a_failure = threading.Event()
    a_joined = threading.Event()
    allow_a_stop_continuation = threading.Event()
    b_recording = threading.Event()
    b_release = threading.Event()
    b_stopped = threading.Event()
    processing_started = threading.Event()
    processed = []
    wait_call = 0

    class RaceRecorder:
        def __init__(self):
            self.call = 0

        def record_until_stop(self, path, **kwargs):
            self.call += 1
            if self.call == 1:
                allow_a_failure.wait(timeout=2)
                raise OSError("take A failed")
            b_recording.set()
            b_stopped.wait(timeout=2)

        def stop(self):
            if b_recording.is_set():
                b_stopped.set()

    def wait_for_release(*args):
        nonlocal wait_call
        wait_call += 1
        if wait_call == 1:
            allow_a_waiter.wait(timeout=2)
            return "timeout", 1.0
        b_release.wait(timeout=2)
        return "released", 1.0

    class JoinGate:
        def __init__(self, thread):
            self.thread = thread

        def is_alive(self):
            return self.thread.is_alive()

        def join(self):
            self.thread.join()
            a_joined.set()
            allow_a_stop_continuation.wait(timeout=2)

    paths = iter(create_recording_path(directory=tmp_path) for _ in range(2))
    controller.recorder = RaceRecorder()
    monkeypatch.setattr("speedytype.daemon.temp_wav_path", lambda: next(paths))
    monkeypatch.setattr("speedytype.daemon.wait_until_hotkey_released", wait_for_release)
    def process(path, *args, **kwargs):
        processed.append(path)
        processing_started.set()

    monkeypatch.setattr("speedytype.daemon.process_wav", process)

    controller.on_press()
    session_a = controller._active_session
    session_a.thread = JoinGate(session_a.thread)
    allow_a_waiter.set()
    allow_a_failure.set()
    assert a_joined.wait(timeout=2)

    controller.on_press()
    session_b = controller._active_session
    assert session_b is not session_a
    assert b_recording.wait(timeout=2)
    allow_a_stop_continuation.set()
    session_a.stop_thread.join(timeout=2)

    assert controller._active_session is session_b
    assert processed == []
    assert session_b.thread.is_alive()

    b_release.set()
    session_b.stop_thread.join(timeout=2)
    assert processing_started.wait(timeout=2)
    assert processed == [session_b.path]
    app.processEvents()


def test_stale_waiter_and_ticker_cannot_rearm_or_stop_new_toggle_take(tmp_path, monkeypatch):
    app, controller, recorder_calls, processed, _ = _orchestration_controller(
        tmp_path, monkeypatch, mode="toggle", max_seconds=100.0
    )
    monkeypatch.setattr("speedytype.daemon.wait_until_hotkey_released", lambda *args: ("released", 1.0))
    controller.on_press()
    session_a = controller._active_session

    with controller._session_lock:
        controller._recording_control.recording_failed()
        controller._active_session = None

    controller.on_press()
    session_b = controller._active_session
    start = threading.Barrier(3)

    def old_waiter():
        start.wait(timeout=2)
        controller._finish_after_release(session_a)

    def old_ticker():
        start.wait(timeout=2)
        controller._run_countdown_ticker(session_a)

    waiter = _REAL_THREAD(target=old_waiter)
    ticker = _REAL_THREAD(target=old_ticker)
    waiter.start()
    ticker.start()
    start.wait(timeout=2)
    waiter.join(timeout=2)
    ticker.join(timeout=2)

    assert controller._active_session is session_b
    assert controller._recording_control.phase is RecordingPhase.RECORDING_UNARMED
    assert recorder_calls == []
    assert processed == []
    app.processEvents()


def test_stale_stop_owner_cannot_stop_current_take(tmp_path, monkeypatch):
    app, controller, recorder_calls, processed, _ = _orchestration_controller(
        tmp_path, monkeypatch
    )
    controller.on_press()
    session_a = controller._active_session

    with controller._session_lock:
        controller._recording_control.recording_failed()
        controller._active_session = None

    controller.on_press()
    session_b = controller._active_session

    controller._finish_recording(session_a, "timeout")

    assert recorder_calls == []
    assert processed == []
    assert controller._active_session is session_b
    assert session_b.thread.is_alive()
    app.processEvents()


@pytest.mark.parametrize("mode", ["hold", "toggle"])
def test_shutdown_drains_capture_once_without_processing_and_leaves_recoverable_wav(
    tmp_path, monkeypatch, mode
):
    app = QApplication.instance() or QApplication([])
    controller = DaemonController(
        AppConfig(openai_api_key="x", gemini_api_key="y", recording_mode=mode, max_record_seconds=10_000),
        activation_threshold_seconds=0,
    )
    recording = threading.Event()
    stopped = threading.Event()
    release_waiter = threading.Event()
    stop_calls = []
    processed = []
    path = create_recording_path(directory=tmp_path)

    class DrainRecorder:
        def record_until_stop(self, active_path, **kwargs):
            recording.set()
            stopped.wait(timeout=2)
            from speedytype.recording_recovery import mark_recording
            mark_recording(active_path, "captured")

        def stop(self):
            stop_calls.append(True)
            stopped.set()

    controller.recorder = DrainRecorder()
    monkeypatch.setattr("speedytype.daemon.temp_wav_path", lambda: path)
    monkeypatch.setattr(
        "speedytype.daemon.wait_until_hotkey_released",
        lambda *args: (release_waiter.wait(timeout=2), ("released", 1.0))[1],
    )
    monkeypatch.setattr("speedytype.daemon.process_wav", lambda *args, **kwargs: processed.append(args[0]))

    controller.on_press()
    assert recording.wait(timeout=2)
    session = controller._active_session

    controller.shutdown_active_recording()
    controller.shutdown_active_recording()

    assert stop_calls == [True]
    assert not session.thread.is_alive()
    assert controller._active_session is None
    assert processed == []
    assert '"state": "captured"' in recording_sidecar_path(path).read_text(encoding="utf-8")
    release_waiter.set()
    session.stop_thread.join(timeout=2)
    app.processEvents()


def test_restart_and_quit_hooks_drain_before_relaunch_or_exit(monkeypatch):
    events = []
    controller = SimpleNamespace(
        shutdown_active_recording=lambda: events.append("drain")
    )
    app = SimpleNamespace(quit=lambda: events.append("quit"))
    monkeypatch.setattr("speedytype.daemon._remove_pid_file_if_mine", lambda: events.append("remove-pid"))
    monkeypatch.setattr("speedytype.daemon._relaunch_daemon", lambda env: events.append(("relaunch", env)))

    daemon_module._restart_running_daemon(controller, app, "settings.env")

    assert events == ["drain", "remove-pid", ("relaunch", "settings.env"), "quit"]

    events.clear()
    daemon_module._quit_running_daemon(controller, app)

    assert events == ["drain", "quit"]


def test_processing_failure_is_sanitized_hides_overlay_and_controller_is_reusable(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    controller = DaemonController(
        AppConfig(openai_api_key="secret", gemini_api_key="secret"),
        activation_threshold_seconds=0,
    )
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
    controller = DaemonController(
        AppConfig(openai_api_key="secret", gemini_api_key="secret"),
        activation_threshold_seconds=0,
    )
    notifications = []
    hidden = []
    controller.processing_error_signal.connect(notifications.append)
    controller.hide_signal.connect(lambda: hidden.append(True))
    path = create_recording_path(directory=tmp_path)
    monkeypatch.setattr(
        controller.recorder,
        "record_until_stop",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("secret microphone detail")),
    )
    threads = []

    def thread_factory(*, target, daemon, args=()):
        thread = _ControlledThread(target=target, daemon=daemon, args=args)
        threads.append(thread)
        return thread

    monkeypatch.setattr("speedytype.daemon.temp_wav_path", lambda: path)
    monkeypatch.setattr("speedytype.daemon.threading.Thread", thread_factory)

    controller.on_press()
    controller._record_session(controller._active_session)
    app.processEvents()

    assert hidden == [True]
    assert notifications == ["Recording failed (OSError). Daemon remains available."]
    assert '"state": "failed-retained"' in recording_sidecar_path(
        path
    ).read_text(encoding="utf-8")


def test_short_recording_bypasses_hybrid_finish_before_pipeline_guard(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "short.wav"
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16_000)
        wav_file.writeframes(b"\0\0" * 160)
    controller = DaemonController(
        AppConfig(openai_api_key="x", gemini_api_key="y"),
        activation_threshold_seconds=0,
    )
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
    controller = DaemonController(config, activation_threshold_seconds=0)
    active_path = tmp_path / "recording.wav"
    started = []

    class FakeThread:
        def __init__(self, *, target, daemon, args=()):
            self.target = target
            self.args = args

        def start(self):
            started.append((self.target, self.args))

    monkeypatch.setattr("speedytype.daemon.temp_wav_path", lambda: active_path)
    monkeypatch.setattr("speedytype.daemon.threading.Thread", FakeThread)

    controller.on_press()

    assert controller._hybrid_transcriber is None
    assert started
    app.processEvents()


def test_upload_refusal_notification_reports_preserved_wav_and_category(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    controller = DaemonController(
        AppConfig(openai_api_key="x", gemini_api_key="y"),
        activation_threshold_seconds=0,
    )
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
