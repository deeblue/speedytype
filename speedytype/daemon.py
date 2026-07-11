from __future__ import annotations

from pathlib import Path
from dataclasses import replace
import os
import subprocess
import sys
import threading
import time

import keyboard
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from speedytype.audio import Recorder, temp_wav_path
from speedytype.config import AppConfig
from speedytype.console import safe_print
from speedytype.hotkey import wait_until_hotkey_released
from speedytype.icon import build_app_icon
from speedytype.overlay import AudioLevelEmitter, RecordingPill
from speedytype.pipeline import process_wav


PID_FILE = Path("speedytype_daemon.pid")
COUNTDOWN_WARNING_SECONDS = 60.0


class DaemonController(QObject):
    """Bridges the hotkey/recording/pipeline logic (running on plain Python
    threads) to the Qt-owned overlay widget. All widget-touching calls are
    routed through Qt signals so the widget is only ever mutated on the Qt
    GUI thread, regardless of which thread triggered the change.
    """

    show_recording_signal = pyqtSignal()
    show_processing_signal = pyqtSignal()
    show_countdown_signal = pyqtSignal(int)
    hide_signal = pyqtSignal()

    def __init__(self, config: AppConfig, env_path: str = ".env", settings_path: str = "settings.json",
                 countdown_warning_seconds: float = COUNTDOWN_WARNING_SECONDS) -> None:
        super().__init__()
        self.config = config
        self.env_path = env_path
        self.settings_path = settings_path
        self.countdown_warning_seconds = countdown_warning_seconds
        self.pill = RecordingPill()
        self.level_emitter = AudioLevelEmitter()

        self.level_emitter.level_changed.connect(self.pill.update_level)
        self.show_recording_signal.connect(self.pill.show_recording)
        self.show_processing_signal.connect(self.pill.show_processing)
        self.show_countdown_signal.connect(self.pill.show_countdown)
        self.hide_signal.connect(self.pill.hide_pill)

        self.recorder = Recorder(device=config.mic_device)
        self._active_thread: threading.Thread | None = None
        self._stop_wait_thread: threading.Thread | None = None
        self._countdown_thread: threading.Thread | None = None
        self._active_path: Path | None = None
        self._hotkey_handle = None

    def apply_live_vocab_update(self, vocab_bias_string: str) -> None:
        """Vocabulary bias is read fresh on every Whisper call, so it can be
        updated in the running daemon without restarting it."""
        self.config = replace(self.config, whisper_vocab_bias=vocab_bias_string)

    def register_hotkey(self) -> None:
        if self._hotkey_handle is not None:
            try:
                keyboard.remove_hotkey(self._hotkey_handle)
            except Exception:
                pass
        self._hotkey_handle = keyboard.add_hotkey(self.config.hotkey, self.on_press, suppress=False)

    def on_press(self) -> None:
        if self._active_thread and self._active_thread.is_alive():
            return
        self._active_path = temp_wav_path()
        safe_print("Recording...", flush=True)
        self.show_recording_signal.emit()

        record_started = time.perf_counter()

        def record() -> None:
            self.recorder.record_until_stop(
                self._active_path,
                on_level=lambda rms: self.level_emitter.level_changed.emit(rms),
            )

        self._active_thread = threading.Thread(target=record, daemon=False)
        self._active_thread.start()
        self._stop_wait_thread = threading.Thread(target=self._finish_after_release, daemon=True)
        self._stop_wait_thread.start()
        self._countdown_thread = threading.Thread(
            target=self._run_countdown_ticker, args=(record_started,), daemon=True
        )
        self._countdown_thread.start()

    def _run_countdown_ticker(self, record_started: float) -> None:
        while self._active_thread and self._active_thread.is_alive():
            elapsed = time.perf_counter() - record_started
            remaining = self.config.max_record_seconds - elapsed
            if remaining <= self.countdown_warning_seconds:
                self.show_countdown_signal.emit(max(0, round(remaining)))
            time.sleep(0.2)

    def _finish_after_release(self) -> None:
        reason, elapsed = wait_until_hotkey_released(self.config.hotkey, self.config.max_record_seconds)
        if not self._active_thread or not self._active_thread.is_alive() or self._active_path is None:
            return
        if reason == "timeout":
            safe_print(f"Recording timed out after {elapsed:.1f}s; stopping automatically.", flush=True)
        self.recorder.stop()
        self._active_thread.join()
        safe_print("Processing...", flush=True)
        self.show_processing_signal.emit()

        active_path = self._active_path

        def process() -> None:
            try:
                process_wav(active_path, self.config, do_paste=True)
            finally:
                self.hide_signal.emit()

        threading.Thread(target=process, daemon=True).start()


def _write_pid_file() -> None:
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def _is_pid_running(pid: int) -> bool:
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
        capture_output=True,
        text=True,
    )
    return str(pid) in result.stdout


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
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    interpreter = str(pythonw) if pythonw.exists() else sys.executable
    creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    # pythonw.exe has no console, so sys.stdout/sys.stderr are None unless
    # explicitly redirected here; safe_print() tolerates that, but redirecting
    # to a real log file keeps restart/autostart diagnostics visible.
    log_path = Path("speedytype_daemon.log")
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


def run_daemon(config: AppConfig, env_path: str = ".env", settings_path: str = "settings.json") -> int:
    should_start, message = check_existing_daemon()
    if message:
        safe_print(message, flush=True)
    if not should_start:
        return 1

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    controller = DaemonController(config, env_path=env_path, settings_path=settings_path)
    controller.register_hotkey()

    tray = QSystemTrayIcon(build_app_icon())
    tray.setToolTip("SpeedyType")
    menu = QMenu()

    settings_dialogs: list = []
    about_dialogs: list = []

    def open_settings() -> None:
        from speedytype.settings_dialog import SettingsDialog

        dialog = SettingsDialog(controller.config, env_path, settings_path)
        dialog.vocab_applied.connect(controller.apply_live_vocab_update)
        settings_dialogs.append(dialog)  # keep a reference so it isn't garbage-collected
        dialog.show()

    def open_about() -> None:
        from speedytype.about_dialog import AboutDialog

        dialog = AboutDialog(controller.config)
        about_dialogs.append(dialog)
        dialog.show()

    def restart_daemon() -> None:
        safe_print("Restarting daemon...", flush=True)
        # Remove our own PID file before spawning the replacement, so the new
        # process's startup check (check_existing_daemon) doesn't see this
        # (still technically alive for a moment) process and refuse to start.
        _remove_pid_file_if_mine()
        _relaunch_daemon(env_path)
        app.quit()

    def quit_daemon() -> None:
        app.quit()

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

    _write_pid_file()
    safe_print(
        f"SpeedyType daemon running (pid={os.getpid()}). Hold {config.hotkey.upper()} to record. "
        f"Stop with: python -m speedytype daemon-stop (or tray menu -> 結束)",
        flush=True,
    )
    try:
        return app.exec()
    finally:
        _remove_pid_file_if_mine()


def stop_daemon(pid_file: Path = PID_FILE) -> tuple[bool, str]:
    if not pid_file.exists():
        return False, "No PID file found; daemon does not appear to be running."

    pid_text = pid_file.read_text(encoding="utf-8").strip()
    if not pid_text.isdigit():
        return False, f"PID file content is invalid: {pid_text!r}"
    pid = int(pid_text)

    result = subprocess.run(
        ["taskkill", "/PID", str(pid), "/F"],
        capture_output=True,
        text=True,
    )
    try:
        pid_file.unlink()
    except Exception:
        pass

    if result.returncode == 0:
        return True, f"Stopped daemon PID {pid}."
    return False, f"taskkill failed (code={result.returncode}): {(result.stderr or result.stdout).strip()}"
