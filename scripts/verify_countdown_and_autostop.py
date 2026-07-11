from __future__ import annotations

from pathlib import Path
import sys
import time
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication

from speedytype import daemon as daemon_module
from speedytype.config import AppConfig
from speedytype.daemon import DaemonController


def main() -> int:
    app = QApplication(sys.argv)

    process_wav_calls = []

    def fake_process_wav(path, config, do_paste=True):
        process_wav_calls.append((path, do_paste))

        class FakeResult:
            pass

        return FakeResult()

    with mock.patch("speedytype.hotkey.keyboard.is_pressed", lambda combo: True), \
         mock.patch.object(daemon_module, "process_wav", fake_process_wav):

        config = AppConfig(
            openai_api_key="unused",
            gemini_api_key="unused",
            max_record_seconds=8.0,
            hotkey="f9",
            mic_device="",
        )
        controller = DaemonController(config, countdown_warning_seconds=4.0)

        countdown_events: list[tuple[float, int]] = []
        hide_events: list[float] = []
        controller.show_countdown_signal.connect(lambda remaining: countdown_events.append((time.perf_counter(), remaining)))
        controller.hide_signal.connect(lambda: hide_events.append(time.perf_counter()))

        start = time.perf_counter()
        controller.on_press()
        print("PRESS_SIMULATED (calling on_press() directly, not a real keypress)")

        deadline = start + 15.0
        while time.perf_counter() < deadline and not hide_events:
            app.processEvents()
            time.sleep(0.05)

        if not hide_events:
            print("FAIL: recording never auto-stopped within 15s")
            return 1

        total_elapsed = hide_events[0] - start
        print(f"AUTO_STOP_ELAPSED={total_elapsed:.2f}s (config max_record_seconds=8.0)")

        print(f"PROCESS_WAV_CALLS={len(process_wav_calls)}")

        if not countdown_events:
            print("FAIL: countdown never appeared")
            return 1

        first_time = countdown_events[0][0] - start
        first_remaining = countdown_events[0][1]
        last_remaining = countdown_events[-1][1]
        print(f"FIRST_COUNTDOWN at t={first_time:.2f}s remaining={first_remaining}s (warning threshold=4.0s)")
        print(f"LAST_COUNTDOWN remaining={last_remaining}s")
        for t, remaining in countdown_events:
            print(f"  t={t - start:.2f}s remaining={remaining}s")

        countdown_ok = 3.0 <= first_time <= 5.0
        autostop_ok = 7.0 <= total_elapsed <= 10.0
        status = "PASS" if countdown_ok and autostop_ok and process_wav_calls else "FAIL"
        print(f"STATUS={status} countdown_timing_ok={countdown_ok} autostop_timing_ok={autostop_ok}")
        return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
