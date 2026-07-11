from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import keyboard
from pywinauto import Desktop, mouse
from PyQt6.QtWidgets import QApplication

from speedytype.overlay import RecordingPill


PROBE_TEXT = "clickthrough_ok"


def read_notepad_text(window) -> str:
    for control in window.descendants():
        if control.friendly_class_name() in {"Edit", "Document"}:
            try:
                return control.window_text() or control.get_value()
            except Exception:
                return control.window_text()
    return ""


def main() -> int:
    app = QApplication(sys.argv)
    pill = RecordingPill()

    target_file = Path(tempfile.gettempdir()) / f"speedytype_clickthrough_{int(time.time() * 1000)}.txt"
    target_file.write_text("", encoding="utf-8")
    proc = subprocess.Popen(["notepad.exe", str(target_file)])
    try:
        window = Desktop(backend="uia").window(title_re=f".*{target_file.name}.*")
        window.wait("visible", timeout=10)
        window.set_focus()
        time.sleep(0.3)

        edit_control = None
        for control in window.descendants():
            if control.friendly_class_name() in {"Edit", "Document"}:
                edit_control = control
                break
        if edit_control is None:
            print("NO_EDIT_CONTROL_FOUND")
            return 1

        rect = edit_control.rectangle()
        click_x = (rect.left + rect.right) // 2
        click_y = (rect.top + rect.bottom) // 2
        print(f"NOTEPAD_EDIT_RECT={rect} CLICK_POINT=({click_x},{click_y})")

        # Position the pill so it visually covers the exact point we are about to click.
        pill.move(click_x - pill.width() // 2, click_y - pill.height() // 2)
        pill.show()
        app.processEvents()
        pill_rect = pill.frameGeometry()
        print(
            f"PILL_RECT left={pill_rect.left()} top={pill_rect.top()} "
            f"width={pill_rect.width()} height={pill_rect.height()}"
        )
        covers_click_point = pill_rect.contains(click_x, click_y)
        print(f"PILL_COVERS_CLICK_POINT={covers_click_point}")

        # Real OS-level click at a point visually covered by the (click-through) pill.
        mouse.click(button="left", coords=(click_x, click_y))
        time.sleep(0.3)
        app.processEvents()
        keyboard.write(PROBE_TEXT)
        time.sleep(0.3)

        observed = read_notepad_text(window)
        print(f"NOTEPAD_TEXT_AFTER_CLICK_AND_TYPE={observed!r}")
        passed = covers_click_point and PROBE_TEXT in observed
        print(f"CLICK_THROUGH_STATUS={'PASS' if passed else 'FAIL'}")
    finally:
        pill.hide_pill()
        app.quit()
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            target_file.unlink()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
