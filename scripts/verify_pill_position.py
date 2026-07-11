from __future__ import annotations

from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication

from speedytype.overlay import PILL_HEIGHT, PILL_WIDTH, SCREEN_MARGIN, RecordingPill


def main() -> int:
    app = QApplication(sys.argv)
    screen = QApplication.primaryScreen()
    geo = screen.availableGeometry()
    expected_x = geo.left() + (geo.width() - PILL_WIDTH) // 2
    expected_y = geo.bottom() - PILL_HEIGHT - SCREEN_MARGIN
    print(f"SCREEN geometry: left={geo.left()} top={geo.top()} width={geo.width()} height={geo.height()}")
    print(f"EXPECTED pill position: x={expected_x} y={expected_y}")

    pill = RecordingPill()
    pill.show_recording()
    for v in [0.02, 0.08, 0.15, 0.05]:
        pill.update_level(v)
    app.processEvents()
    time.sleep(0.3)
    app.processEvents()

    actual_pos = pill.pos()
    print(f"ACTUAL pill position: x={actual_pos.x()} y={actual_pos.y()}")
    print(f"MATCH: {actual_pos.x() == expected_x and actual_pos.y() == expected_y}")

    pill_center_x = actual_pos.x() + PILL_WIDTH / 2
    screen_center_x = geo.left() + geo.width() / 2
    print(f"Pill center x={pill_center_x}, screen center x={screen_center_x}, diff={abs(pill_center_x - screen_center_x)}")

    pill.hide_pill()
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
