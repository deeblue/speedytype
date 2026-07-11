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
from speedytype.settings_dialog import SettingsDialog


def main() -> int:
    app = QApplication(sys.argv)

    process_wav_calls = []

    def fake_process_wav(path, config, do_paste=True):
        process_wav_calls.append((path, do_paste))

        class FakeResult:
            pass

        return FakeResult()

    tmp_dir = Path("scratch_nonblocking_test")
    tmp_dir.mkdir(exist_ok=True)
    env_path = tmp_dir / ".env"
    env_path.write_text("OPENAI_API_KEY=x\nGEMINI_API_KEY=y\n", encoding="utf-8")
    settings_path = tmp_dir / "settings.json"

    with mock.patch("speedytype.hotkey.keyboard.is_pressed", lambda combo: True), \
         mock.patch.object(daemon_module, "process_wav", fake_process_wav):

        config = AppConfig(openai_api_key="unused", gemini_api_key="unused", max_record_seconds=3.0, hotkey="f9", mic_device="")
        controller = DaemonController(config, countdown_warning_seconds=60.0)

        dialog = SettingsDialog(controller.config, str(env_path), str(settings_path))
        dialog.show()
        app.processEvents()
        print(f"DIALOG_VISIBLE_BEFORE={dialog.isVisible()}")

        hide_events = []
        controller.hide_signal.connect(lambda: hide_events.append(time.perf_counter()))

        start = time.perf_counter()
        controller.on_press()
        print("Hotkey press simulated via direct on_press() call (dialog is open, non-modal .show())")

        deadline = start + 8.0
        while time.perf_counter() < deadline and not hide_events:
            app.processEvents()
            # Also interact with the still-open dialog while pipeline runs, to
            # prove it's genuinely responsive, not just technically visible.
            dialog.vocab_input.setText("liveness_check_term")
            time.sleep(0.05)

        elapsed = (hide_events[0] - start) if hide_events else None
        print(f"PIPELINE_COMPLETED={bool(hide_events)} elapsed={elapsed}")
        print(f"PROCESS_WAV_CALLS={len(process_wav_calls)}")
        print(f"DIALOG_VISIBLE_AFTER={dialog.isVisible()}")
        dialog._add_vocab_term()
        print(f"DIALOG_STILL_RESPONSIVE_TO_INTERACTION={'liveness_check_term' in dialog._vocab_terms}")

        status = "PASS" if hide_events and process_wav_calls and dialog.isVisible() else "FAIL"
        print(f"STATUS={status}")

    for path in (env_path, settings_path):
        try:
            path.unlink()
        except Exception:
            pass
    try:
        tmp_dir.rmdir()
    except Exception:
        pass

    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
