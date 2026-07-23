from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass, replace
from typing import Callable
import os
import subprocess
import sys
import threading
import time

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from speedytype.audio import Recorder, temp_wav_path
from speedytype.config import AppConfig
from speedytype.console import safe_print
from speedytype.hotkey import PlatformPermissionError, is_hotkey_active, register_hold_hotkey, remove_hotkey, wait_until_hotkey_released
from speedytype.hotkey_debounce import append_rejection_record
from speedytype.icon import build_app_icon
from speedytype.macos_permissions import keyboard_permission_guidance
from speedytype.overlay import AudioLevelEmitter, RecordingPill
from speedytype.pipeline import process_wav
from speedytype.paths import default_daemon_log_path, default_env_path, default_pid_path, default_settings_path
from speedytype.platform.app import activate_window, configure_daemon_application
from speedytype.platform.clipboard import PasteTarget, capture_paste_target
from speedytype.recording_control import RecordingAction, RecordingControl, RecordingPhase
from speedytype.recording_recovery import RecoveryRecord, discover_recoverable_recordings, mark_recording, remove_unconfirmed_recording
from speedytype.platform.process import is_process_running, terminate_process


PID_FILE = default_pid_path()
COUNTDOWN_WARNING_SECONDS = 60.0
HOTKEY_ACTIVATION_THRESHOLD_SECONDS = 0.08


@dataclass(frozen=True)
class _ActivationCandidate:
    token: int
    intent: str
    started_at: float


@dataclass
class _RecordingSession:
    token: int
    path: Path
    started_at: float
    thread: threading.Thread | None = None
    stop_thread: threading.Thread | None = None
    countdown_thread: threading.Thread | None = None
    confirmation_thread: threading.Thread | None = None
    candidate: _ActivationCandidate | None = None
    capture_started: bool = False
    capture_prepared: bool = False
    confirmed: bool = False
    stop_started: bool = False
    rollback_requested: bool = False
    shutdown_requested: bool = False
    shutdown_draining: bool = False
    paste_target: PasteTarget | None = None


def report_recoverable_recordings(
    tray: QSystemTrayIcon, records: tuple[RecoveryRecord, ...]
) -> None:
    if not records:
        return
    safe_print(f"Found {len(records)} retained SpeedyType recording(s):", flush=True)
    for record in records:
        safe_print(f"- [{record.state}] {record.wav_path}", flush=True)
    tray.showMessage(
        "SpeedyType 錄音已保留",
        f"找到 {len(records)} 筆尚未完成的錄音；檔案路徑已寫入 daemon log，不會自動上傳。",
        QSystemTrayIcon.MessageIcon.Warning,
        10_000,
    )


class DaemonController(QObject):
    """Bridges the hotkey/recording/pipeline logic (running on plain Python
    threads) to the Qt-owned overlay widget. All widget-touching calls are
    routed through Qt signals so the widget is only ever mutated on the Qt
    GUI thread, regardless of which thread triggered the change.
    """

    show_recording_signal = pyqtSignal()
    show_processing_signal = pyqtSignal()
    show_elapsed_signal = pyqtSignal(int)
    show_countdown_signal = pyqtSignal(int)
    show_auto_stopped_signal = pyqtSignal()
    hide_signal = pyqtSignal()
    processing_error_signal = pyqtSignal(str)

    def __init__(self, config: AppConfig, env_path: str | Path | None = None, settings_path: str | Path | None = None,
                 countdown_warning_seconds: float = COUNTDOWN_WARNING_SECONDS,
                 activation_threshold_seconds: float = HOTKEY_ACTIVATION_THRESHOLD_SECONDS,
                 monotonic: Callable[[], float] | None = None,
                 sleep: Callable[[float], None] | None = None,
                 daemon_log_path: str | Path | None = None) -> None:
        super().__init__()
        self.config = config
        self.env_path = str(env_path or default_env_path())
        self.settings_path = str(settings_path or default_settings_path())
        self.countdown_warning_seconds = countdown_warning_seconds
        self.activation_threshold_seconds = activation_threshold_seconds
        self._monotonic = monotonic or (lambda: time.perf_counter())
        self._sleep = sleep or (lambda seconds: time.sleep(seconds))
        self._daemon_log_path = Path(daemon_log_path or default_daemon_log_path())
        self.pill = RecordingPill()
        self.level_emitter = AudioLevelEmitter()

        self.level_emitter.level_changed.connect(self.pill.update_level)
        self.show_recording_signal.connect(self.pill.show_recording)
        self.show_processing_signal.connect(self.pill.show_processing)
        self.show_elapsed_signal.connect(self.pill.show_elapsed)
        self.show_countdown_signal.connect(self.pill.show_countdown)
        self.show_auto_stopped_signal.connect(self.pill.show_auto_stopped)
        self.hide_signal.connect(self.pill.hide_pill)

        self.recorder = Recorder(device=config.mic_device)
        self._recording_control = RecordingControl(config.recording_mode)
        # Lock order is always controller session lock, then RecordingControl's
        # internal lock. No code acquires these locks in the opposite order.
        self._session_lock = threading.Lock()
        self._active_session: _RecordingSession | None = None
        self._hotkey_handle = None
        # Kept as an inert compatibility attribute for old diagnostics. Daily
        # production recording always uses one complete-file JSON request.
        self._hybrid_transcriber = None

    def apply_live_vocab_update(self, vocab_bias_string: str) -> None:
        """Vocabulary bias is read fresh on every Whisper call, so it can be
        updated in the running daemon without restarting it."""
        self.config = replace(self.config, whisper_vocab_bias=vocab_bias_string)

    def register_hotkey(self) -> None:
        if self._hotkey_handle is not None:
            try:
                remove_hotkey(self._hotkey_handle)
            except Exception:
                pass
        self._hotkey_handle = register_hold_hotkey(self.config.hotkey, self.on_press)

    def on_press(self) -> None:
        session_to_finish = None
        start_failure = None
        with self._session_lock:
            action, activation_token = self._recording_control.begin_activation()
            if action is RecordingAction.BEGIN_STOP:
                session = self._active_session
                if session is not None and activation_token is not None:
                    candidate = _ActivationCandidate(
                        activation_token, "stop", self._monotonic()
                    )
                    session.candidate = candidate
                    if self.activation_threshold_seconds <= 0:
                        if self._recording_control.confirm_activation(
                            candidate.token
                        ) is RecordingAction.STOP:
                            session_to_finish = session
                    else:
                        try:
                            session.stop_thread = threading.Thread(
                                target=self._finish_after_release,
                                args=(session, candidate),
                                daemon=True,
                            )
                            session.confirmation_thread = threading.Thread(
                                target=self._confirm_candidate,
                                args=(session, candidate),
                                daemon=True,
                            )
                            session.stop_thread.start()
                            session.confirmation_thread.start()
                        except Exception as exc:
                            rollback = self._recording_control.hotkey_released(
                                candidate.token
                            )
                            if rollback is RecordingAction.CANCEL_STOP:
                                session.candidate = None
                            safe_print(
                                "Hotkey qualification failed "
                                f"({type(exc).__name__}); recording continues.",
                                flush=True,
                            )
            elif action is RecordingAction.BEGIN_START and activation_token is not None:
                path = None
                session = None
                try:
                    path = temp_wav_path()
                    candidate = _ActivationCandidate(
                        activation_token, "start", self._monotonic()
                    )
                    session = _RecordingSession(
                        token=activation_token,
                        path=path,
                        started_at=candidate.started_at,
                        candidate=candidate,
                        paste_target=capture_paste_target(),
                    )
                    session.thread = threading.Thread(
                        target=self._record_session, args=(session,), daemon=False
                    )
                    session.stop_thread = threading.Thread(
                        target=self._finish_after_release,
                        args=(session, candidate),
                        daemon=True,
                    )
                    if self.activation_threshold_seconds > 0:
                        session.confirmation_thread = threading.Thread(
                            target=self._confirm_candidate,
                            args=(session, candidate),
                            daemon=True,
                        )
                    self._active_session = session
                    self._hybrid_transcriber = None
                    prepare_recording = getattr(
                        self.recorder, "prepare_recording", None
                    )
                    if callable(prepare_recording):
                        prepare_recording()
                        session.capture_prepared = True
                    session.thread.start()
                    session.capture_started = True
                    if self.activation_threshold_seconds <= 0:
                        confirmed = self._recording_control.confirm_activation(
                            candidate.token
                        )
                        if confirmed is RecordingAction.CONFIRM_START:
                            self._confirm_start_locked(session)
                    session.stop_thread.start()
                    if session.confirmation_thread is not None:
                        session.confirmation_thread.start()
                except Exception as exc:
                    join_capture = False
                    if session is not None and self._active_session is session:
                        if session.capture_started:
                            session.rollback_requested = True
                            join_capture = True
                            session.stop_started = True
                            self.recorder.stop()
                        else:
                            self._active_session = None
                    if not join_capture:
                        self._recording_control.recording_failed()
                    start_failure = (exc, path, session, join_capture)

        if session_to_finish is not None:
            self._finish_recording(session_to_finish, "activation")
        if start_failure is not None:
            exc, path, session, join_capture = start_failure
            if join_capture and session is not None and session.thread is not None:
                session.thread.join()
                with self._session_lock:
                    if self._active_session is session:
                        self._active_session = None
                        self._recording_control.recording_failed()
            if path is not None:
                mark_recording(path, "failed-retained", error_category=type(exc).__name__)
            message = f"Recording failed ({type(exc).__name__}). Daemon remains available."
            safe_print(message, flush=True)
            self.processing_error_signal.emit(message)
            self.hide_signal.emit()

    def _confirm_start_locked(self, session: _RecordingSession) -> None:
        if self._active_session is not session or session.confirmed:
            return
        session.countdown_thread = threading.Thread(
            target=self._run_countdown_ticker, args=(session,), daemon=True
        )
        session.confirmed = True
        session.countdown_thread.start()
        safe_print("Recording...", flush=True)
        self.show_recording_signal.emit()

    def _confirm_candidate(
        self, session: _RecordingSession, candidate: _ActivationCandidate
    ) -> None:
        deadline = candidate.started_at + self.activation_threshold_seconds
        remaining = deadline - self._monotonic()
        if remaining > 0:
            self._sleep(remaining)
        held_seconds = max(0.0, self._monotonic() - candidate.started_at)
        try:
            active = is_hotkey_active(self.config.hotkey)
        except Exception:
            active = False
        self._resolve_candidate(
            session,
            candidate,
            key_active=active,
            held_seconds=held_seconds,
        )

    def _resolve_candidate(
        self,
        session: _RecordingSession,
        candidate: _ActivationCandidate,
        *,
        key_active: bool,
        held_seconds: float,
    ) -> None:
        if not key_active:
            self._release_candidate(session, candidate, held_seconds=held_seconds)
            return

        session_to_finish = None
        confirmation_failure = None
        with self._session_lock:
            if self._active_session is not session or session.candidate is not candidate:
                return
            action = self._recording_control.confirm_activation(candidate.token)
            if action is RecordingAction.CONFIRM_START:
                try:
                    self._confirm_start_locked(session)
                except Exception as exc:
                    session.rollback_requested = True
                    confirmation_failure = exc
            elif action is RecordingAction.STOP:
                session.candidate = None
                session_to_finish = session
        if confirmation_failure is not None:
            self._fail_confirmed_start(session, confirmation_failure)
        elif session_to_finish is not None:
            self._finish_recording(session_to_finish, "activation")

    def _fail_confirmed_start(
        self, session: _RecordingSession, exc: BaseException
    ) -> None:
        self._stop_and_join(session)
        mark_recording(
            session.path,
            "failed-retained",
            error_category=type(exc).__name__,
        )
        with self._session_lock:
            if self._active_session is session:
                self._recording_control.recording_failed()
                self._active_session = None
        message = f"Recording failed ({type(exc).__name__}). Daemon remains available."
        safe_print(message, flush=True)
        self.processing_error_signal.emit(message)
        self.hide_signal.emit()

    def _release_candidate(
        self,
        session: _RecordingSession,
        candidate: _ActivationCandidate,
        *,
        held_seconds: float,
    ) -> None:
        action = RecordingAction.NONE
        with self._session_lock:
            if self._active_session is not session or session.candidate is not candidate:
                return
            action = self._recording_control.hotkey_released(candidate.token)
            if action in (RecordingAction.CANCEL_STOP, RecordingAction.NONE):
                if action is RecordingAction.CANCEL_STOP:
                    session.candidate = None
            elif action is RecordingAction.STOP:
                session.candidate = None

        if action is RecordingAction.CANCEL_START:
            self._cancel_provisional_start(session, candidate, held_seconds)
        elif action is RecordingAction.CANCEL_STOP:
            self._log_rejection(candidate, held_seconds, "not-applicable")
        elif action is RecordingAction.STOP:
            self._finish_recording(session, "released")

    def _cancel_provisional_start(
        self,
        session: _RecordingSession,
        candidate: _ActivationCandidate,
        held_seconds: float,
    ) -> None:
        with self._session_lock:
            if self._active_session is not session or session.candidate is not candidate:
                return
            session.rollback_requested = True
        self._stop_and_join(session)
        cleanup = "removed"
        try:
            remove_unconfirmed_recording(session.path)
        except (OSError, ValueError):
            cleanup = "retained-after-failure"
        with self._session_lock:
            if self._active_session is session and session.candidate is candidate:
                session.candidate = None
                self._active_session = None
        self._log_rejection(candidate, held_seconds, cleanup)

    def _log_rejection(
        self,
        candidate: _ActivationCandidate,
        held_seconds: float,
        cleanup: str,
    ) -> None:
        append_rejection_record(
            self._daemon_log_path,
            platform=sys.platform,
            mode=self.config.recording_mode,
            hotkey=self.config.hotkey.strip().lower(),
            intent=candidate.intent,
            held_ms=max(0.0, held_seconds) * 1000.0,
            cleanup=cleanup,
        )

    def _run_countdown_ticker(self, session: _RecordingSession) -> None:
        while True:
            with self._session_lock:
                if self._active_session is not session:
                    return
                if session.rollback_requested or session.shutdown_requested:
                    return
                if session.thread is None or not session.thread.is_alive():
                    return
            elapsed = time.perf_counter() - session.started_at
            remaining = self.config.max_record_seconds - elapsed
            if remaining <= 0:
                with self._session_lock:
                    if self._active_session is not session:
                        return
                    if session.rollback_requested or session.shutdown_requested:
                        return
                    self.show_countdown_signal.emit(0)
                    action = self._recording_control.timeout()
                if action is RecordingAction.STOP:
                    self._finish_recording(session, "timeout")
                return
            with self._session_lock:
                if self._active_session is not session:
                    return
                if session.rollback_requested or session.shutdown_requested:
                    return
                if remaining <= self.countdown_warning_seconds:
                    self.show_countdown_signal.emit(max(0, round(remaining)))
                else:
                    self.show_elapsed_signal.emit(max(0, round(elapsed)))
            time.sleep(0.2)

    def _finish_after_release(
        self,
        session: _RecordingSession,
        candidate: _ActivationCandidate | None = None,
    ) -> None:
        candidate = candidate or session.candidate
        if candidate is None:
            return
        reason, waiter_elapsed = wait_until_hotkey_released(
            self.config.hotkey, self.config.max_record_seconds
        )
        elapsed = max(
            float(waiter_elapsed),
            max(0.0, self._monotonic() - candidate.started_at),
        )
        if reason != "timeout" and elapsed >= self.activation_threshold_seconds:
            self._resolve_candidate(
                session,
                candidate,
                key_active=True,
                held_seconds=elapsed,
            )
        with self._session_lock:
            if self._active_session is not session:
                return
            if session.rollback_requested or session.shutdown_requested:
                return
            if reason == "timeout":
                action = self._recording_control.timeout()
            else:
                action = self._recording_control.hotkey_released(candidate.token)
                if action is RecordingAction.CANCEL_STOP:
                    session.candidate = None
                elif action is RecordingAction.STOP:
                    session.candidate = None

        if action is RecordingAction.CANCEL_START:
            self._cancel_provisional_start(session, candidate, elapsed)
        elif action is RecordingAction.CANCEL_STOP:
            self._log_rejection(candidate, elapsed, "not-applicable")
        elif action is RecordingAction.STOP:
            if reason == "timeout":
                safe_print(f"Recording timed out after {elapsed:.1f}s; stopping automatically.", flush=True)
            self._finish_recording(session, reason)

    def _stop_and_join(self, session: _RecordingSession) -> None:
        with self._session_lock:
            if self._active_session is session and not session.stop_started:
                # Recorder.stop() is an Event.set() in production. Keep this
                # nonblocking ownership side effect inside the session lock so
                # a failed take cannot yield to a new take between the identity
                # check and stopping the shared Recorder instance.
                session.stop_started = True
                self.recorder.stop()
        if session.thread is not None:
            session.thread.join()

    def _finish_recording(self, session: _RecordingSession, reason: str) -> None:
        self._stop_and_join(session)
        with self._session_lock:
            if self._active_session is not session:
                return
            session.candidate = None
            if session.shutdown_requested or self._recording_control.phase is RecordingPhase.IDLE:
                self._recording_control.recording_failed()
                self._active_session = None
                return
            safe_print("Processing...", flush=True)
            if reason == "timeout":
                self.show_auto_stopped_signal.emit()
            self.show_processing_signal.emit()
            self._recording_control.mark_processing()
        threading.Thread(
            target=lambda: self._process_recording(session.path, session), daemon=True
        ).start()

    def _record_session(self, session: _RecordingSession) -> None:
        try:
            self.recorder.record_until_stop(
                session.path,
                on_level=lambda rms: self.level_emitter.level_changed.emit(rms),
                on_audio=None,
                prepared=session.capture_prepared,
            )
        except Exception as exc:
            mark_recording(
                session.path,
                "failed-retained",
                error_category=type(exc).__name__,
            )
            message = f"Recording failed ({type(exc).__name__}). Daemon remains available."
            safe_print(message, flush=True)
            with self._session_lock:
                if self._active_session is session and not session.rollback_requested:
                    self.processing_error_signal.emit(message)
                    self._recording_control.recording_failed()
                    self._active_session = None
                    self.hide_signal.emit()

    def _process_recording(
        self, active_path: Path, session: _RecordingSession | None = None
    ) -> None:
        try:
            if session is None:
                process_wav(active_path, self.config, do_paste=True, usage_scope="daily")
            else:
                process_wav(
                    active_path,
                    self.config,
                    do_paste=True,
                    usage_scope="daily",
                    paste_target=session.paste_target,
                )
        except Exception as exc:
            category = str(getattr(exc, "category", type(exc).__name__))
            preserved_path = Path(getattr(exc, "preserved_wav", active_path))
            mark_recording(active_path, "failed-retained", error_category=category)
            message = (
                f"Recording processing failed ({category}). WAV preserved: "
                f"{preserved_path}. Daemon remains available."
            )
            safe_print(message, flush=True)
            self.processing_error_signal.emit(message)
        finally:
            with self._session_lock:
                if session is None or self._active_session is session:
                    self._recording_control.processing_finished()
                    if session is not None:
                        self._active_session = None
                    self.hide_signal.emit()

    def shutdown_active_recording(self) -> None:
        """Drain the current capture without submitting it for processing."""
        with self._session_lock:
            session = self._active_session
            if session is None or self._recording_control.phase is RecordingPhase.PROCESSING:
                return
            session.shutdown_requested = True
            if session.shutdown_draining:
                return
            session.shutdown_draining = True
            self._recording_control.timeout()

        self._stop_and_join(session)
        with self._session_lock:
            if self._active_session is session:
                self._recording_control.recording_failed()
                self._active_session = None
                self.hide_signal.emit()


def _write_pid_file() -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def _is_pid_running(pid: int) -> bool:
    return is_process_running(pid)


def check_existing_daemon(pid_file: Path = PID_FILE) -> tuple[bool, str]:
    """Check for an existing daemon before starting a new one.

    Returns (should_start, message):
    - No PID file at all: (True, "") — nothing to report, proceed silently.
    - PID file names a process that is genuinely still running: (False, ...)
      — refuse to start a second daemon on top of it.
    - PID file is stale (unreadable content, or names a PID that is no
      longer running — e.g. after a crash or a forced kill): the stale file
      is cleaned up automatically and (True, ...) is returned, so the user
      never has to manually delete it before starting again.
    """
    if not pid_file.exists():
        return True, ""

    pid_text = pid_file.read_text(encoding="utf-8").strip()
    if not pid_text.isdigit():
        pid_file.unlink(missing_ok=True)
        return True, f"Ignored unreadable PID file content ({pid_text!r}); starting normally."

    pid = int(pid_text)
    if _is_pid_running(pid):
        return False, (
            f"A SpeedyType daemon appears to already be running (pid={pid}). "
            "Stop it first with: python -m speedytype daemon-stop (or tray menu -> 結束)."
        )

    pid_file.unlink(missing_ok=True)
    return True, f"Found a stale PID file (pid={pid} is no longer running); cleaned it up and starting normally."


def _remove_pid_file_if_mine() -> None:
    """Only remove the PID file if it still names this process, so a
    'restart' (new process starts, then the old one exits) can never race
    into deleting the new process's freshly-written PID file.
    """
    try:
        if PID_FILE.exists() and PID_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
            PID_FILE.unlink()
    except Exception:
        pass


def _relaunch_daemon(env_path: str) -> None:
    if sys.platform == "win32":
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        interpreter = str(pythonw) if pythonw.exists() else sys.executable
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    else:
        interpreter = sys.executable
        creationflags = 0
    # pythonw.exe has no console, so sys.stdout/sys.stderr are None unless
    # explicitly redirected here; safe_print() tolerates that, but redirecting
    # to a real log file keeps restart/autostart diagnostics visible.
    log_path = default_daemon_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "a", encoding="utf-8")
    child_env = dict(os.environ)
    child_env["PYTHONIOENCODING"] = "utf-8"
    subprocess.Popen(
        [interpreter, "-m", "speedytype", "--env", env_path, "daemon"],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        close_fds=True,
        env=child_env,
    )


def _restart_running_daemon(
    controller: DaemonController, app: QApplication, env_path: str
) -> None:
    controller.shutdown_active_recording()
    _remove_pid_file_if_mine()
    _relaunch_daemon(env_path)
    app.quit()


def _quit_running_daemon(controller: DaemonController, app: QApplication) -> None:
    controller.shutdown_active_recording()
    app.quit()


def _daemon_recording_instruction(config: AppConfig) -> str:
    hotkey = config.hotkey.upper()
    if config.recording_mode == "toggle":
        return f"Press {hotkey} once to start recording and again to stop."
    return f"Hold {hotkey} to record."


def _configure_daemon_qt_application(app: QApplication) -> None:
    app.setApplicationName("SpeedyType")
    app.setWindowIcon(build_app_icon())


def run_daemon(config: AppConfig, env_path: str | Path | None = None, settings_path: str | Path | None = None) -> int:
    should_start, message = check_existing_daemon()
    if message:
        safe_print(message, flush=True)
    if not should_start:
        return 1

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    configure_daemon_application()
    _configure_daemon_qt_application(app)
    controller = DaemonController(config, env_path=env_path, settings_path=settings_path)
    try:
        controller.register_hotkey()
    except PlatformPermissionError:
        QMessageBox.critical(
            None,
            "SpeedyType 權限不足",
            keyboard_permission_guidance(),
        )
        return 2

    tray = QSystemTrayIcon(build_app_icon())
    tray.setToolTip("SpeedyType")
    controller.processing_error_signal.connect(
        lambda message: tray.showMessage(
            "SpeedyType",
            message,
            QSystemTrayIcon.MessageIcon.Warning,
        )
    )
    menu = QMenu()

    settings_dialogs: list = []
    about_dialogs: list = []

    def open_settings() -> None:
        from speedytype.settings_dialog import SettingsDialog

        dialog = SettingsDialog(controller.config, controller.env_path, controller.settings_path)
        dialog.vocab_applied.connect(controller.apply_live_vocab_update)
        settings_dialogs.append(dialog)  # keep a reference so it isn't garbage-collected
        activate_window(dialog)

    def open_about() -> None:
        from speedytype.about_dialog import AboutDialog

        dialog = AboutDialog(controller.config)
        about_dialogs.append(dialog)
        activate_window(dialog)

    def restart_daemon() -> None:
        safe_print("Restarting daemon...", flush=True)
        # Remove our own PID file before spawning the replacement, so the new
        # process's startup check (check_existing_daemon) doesn't see this
        # (still technically alive for a moment) process and refuse to start.
        _restart_running_daemon(controller, app, env_path)

    def quit_daemon() -> None:
        _quit_running_daemon(controller, app)

    action_settings = QAction("設定", menu)
    action_settings.triggered.connect(open_settings)
    action_about = QAction("關於", menu)
    action_about.triggered.connect(open_about)
    action_restart = QAction("重新啟動", menu)
    action_restart.triggered.connect(restart_daemon)
    action_quit = QAction("結束", menu)
    action_quit.triggered.connect(quit_daemon)

    menu.addAction(action_settings)
    menu.addAction(action_about)
    menu.addSeparator()
    menu.addAction(action_restart)
    menu.addAction(action_quit)

    tray.setContextMenu(menu)
    tray.show()
    report_recoverable_recordings(tray, discover_recoverable_recordings())

    _write_pid_file()
    safe_print(
        f"SpeedyType daemon running (pid={os.getpid()}). {_daemon_recording_instruction(config)} "
        f"Stop with: python -m speedytype daemon-stop (or tray menu -> 結束)",
        flush=True,
    )
    try:
        return app.exec()
    finally:
        controller.shutdown_active_recording()
        if controller._hotkey_handle is not None:
            try:
                remove_hotkey(controller._hotkey_handle)
            except Exception:
                pass
        _remove_pid_file_if_mine()


def stop_daemon(pid_file: Path = PID_FILE) -> tuple[bool, str]:
    if not pid_file.exists():
        return False, "No PID file found; daemon does not appear to be running."

    pid_text = pid_file.read_text(encoding="utf-8").strip()
    if not pid_text.isdigit():
        return False, f"PID file content is invalid: {pid_text!r}"
    pid = int(pid_text)

    ok, message = terminate_process(pid)
    try:
        pid_file.unlink()
    except Exception:
        pass

    return ok, message
