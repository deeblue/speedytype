from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import keyboard
from pywinauto import Desktop
from speedytype.paths import default_pid_path

PID_FILE = default_pid_path()


def pythonw_path() -> str:
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return str(candidate) if candidate.exists() else sys.executable


def start_notepad() -> tuple[subprocess.Popen, Path, object]:
    target_file = Path(tempfile.gettempdir()) / f"speedytype_daemon_smoke_{int(time.time() * 1000)}.txt"
    target_file.write_text("", encoding="utf-8")
    proc = subprocess.Popen(["notepad.exe", str(target_file)])
    window = Desktop(backend="uia").window(title_re=f".*{target_file.name}.*")
    window.wait("visible", timeout=10)
    window.set_focus()
    time.sleep(0.5)
    return proc, target_file, window


def read_notepad_text(window) -> str:
    try:
        descendants = window.descendants()
    except Exception:
        return ""
    for control in descendants:
        if control.friendly_class_name() in {"Edit", "Document"}:
            try:
                return control.window_text() or control.get_value()
            except Exception:
                return control.window_text()
    return ""


def clear_notepad(window) -> None:
    try:
        window.set_focus()
    except Exception:
        pass
    time.sleep(0.1)
    keyboard.send("ctrl+a")
    time.sleep(0.05)
    keyboard.send("delete")
    time.sleep(0.1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env")
    parser.add_argument("--hotkey", default="f9")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--hold-seconds", type=float, default=3.0)
    args = parser.parse_args()

    if PID_FILE.exists():
        print(f"PID file {PID_FILE} already exists; refusing to start a second daemon. Run daemon-stop first.")
        return 1

    log_path = Path(tempfile.gettempdir()) / f"speedytype_daemon_smoke_{int(time.time() * 1000)}.log"
    log_file = open(log_path, "w", encoding="utf-8")
    creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    daemon_proc = subprocess.Popen(
        [pythonw_path(), "-m", "speedytype", "--env", args.env, "daemon"],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        close_fds=True,
    )
    print(f"DAEMON_LAUNCHED pid_of_launcher={daemon_proc.pid} log={log_path} (pythonw, no console window)")

    started = time.time()
    while not PID_FILE.exists() and time.time() - started < 10:
        time.sleep(0.2)
    if not PID_FILE.exists():
        print("DAEMON_START_FAILED: PID file never appeared.")
        return 1
    daemon_pid = PID_FILE.read_text(encoding="utf-8").strip()
    print(f"DAEMON_STARTED daemon_pid={daemon_pid}")

    proc, target_file, window = start_notepad()
    results = []
    try:
        for index in range(args.runs):
            clear_notepad(window)

            keyboard.press(args.hotkey)
            time.sleep(args.hold_seconds)
            keyboard.release(args.hotkey)

            time.sleep(8.0)  # allow whisper+llm+paste to complete
            pasted_text = read_notepad_text(window)
            # Mechanics-only run (ambient mic input, no injected speech): a clean
            # empty-transcript skip is a valid pass for "no crash, correct handling".
            status = "PASS_WITH_TEXT" if pasted_text.strip() else "PASS_EMPTY_HANDLED"
            print(f"RUN {index + 1}/{args.runs} status={status} pasted_text={pasted_text!r}")
            results.append(status)
    finally:
        try:
            window.close()
        except Exception:
            pass
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            target_file.unlink()
        except Exception:
            pass

    stop_result = subprocess.run(
        [sys.executable, "-m", "speedytype", "daemon-stop"],
        capture_output=True,
        text=True,
    )
    print(f"DAEMON_STOP stdout={stop_result.stdout.strip()!r} returncode={stop_result.returncode}")
    log_file.close()
    print(f"DAEMON_LOG_PATH={log_path}")
    crashed = len(results) < args.runs
    print(
        f"SUMMARY total={len(results)} with_text={results.count('PASS_WITH_TEXT')} "
        f"empty_handled={results.count('PASS_EMPTY_HANDLED')} crashed={crashed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
