from __future__ import annotations

from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget


PILL_BG_COLOR = QColor("#1a1a1a")
BAR_COLOR = QColor("#ffffff")
DOT_COLOR = QColor("#8a8a8a")
TEXT_COLOR = QColor("#ffffff")
COUNTDOWN_COLOR = QColor("#ff6b6b")

NUM_BARS = 9
BAR_WIDTH = 4
BAR_GAP = 4
BAR_MIN_HEIGHT = 4
BAR_MAX_HEIGHT = 26

PILL_WIDTH = 220
PILL_HEIGHT = 56
SCREEN_MARGIN = 24


class AudioLevelEmitter(QObject):
    """Lives on the audio callback thread's side conceptually, but as a
    QObject its signal emission is queued onto whichever thread the
    connected slot's receiver belongs to. This is the thread-safe bridge
    between the sounddevice recording thread and the Qt GUI thread; no
    shared mutable state or polling is used.
    """

    level_changed = pyqtSignal(float)


class RecordingPill(QWidget):
    """Floating always-on-top, click-through, dark pill.

    Three modes:
      - "recording": shows a decorative dot on each side and a row of bars
        whose heights reflect real-time microphone volume.
      - "countdown": replaces the bars with a large remaining-seconds number,
        shown once recording is within the last N seconds of the configured
        maximum (so the user knows the hard cutoff is approaching).
      - "processing": shows a small spinner and a status label.

    Hidden by default; only shown while the hotkey is held or while the
    pipeline is processing the result.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.resize(PILL_WIDTH, PILL_HEIGHT)

        self._mode = "recording"
        self._bar_heights = [float(BAR_MIN_HEIGHT)] * NUM_BARS
        self._spinner_angle = 0
        self._processing_text = "處理中..."
        self._countdown_remaining = 0

        self._spinner_timer = QTimer(self)
        self._spinner_timer.timeout.connect(self._tick_spinner)

    def _tick_spinner(self) -> None:
        self._spinner_angle = (self._spinner_angle + 30) % 360
        self.update()

    def _position_bottom_center(self) -> None:
        """Bottom-center on the primary screen (the screen the user's main
        session runs on): horizontally centered, vertically anchored to the
        bottom with the same margin the previous bottom-right placement used.
        """
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.left() + (geo.width() - PILL_WIDTH) // 2
        y = geo.bottom() - PILL_HEIGHT - SCREEN_MARGIN
        self.move(x, y)

    def show_recording(self) -> None:
        self._mode = "recording"
        self._bar_heights = [float(BAR_MIN_HEIGHT)] * NUM_BARS
        self._spinner_timer.stop()
        self._position_bottom_center()
        self.show()
        self.update()

    def show_processing(self) -> None:
        self._mode = "processing"
        self._spinner_timer.start(80)
        self._position_bottom_center()
        self.show()
        self.update()

    def show_countdown(self, remaining_seconds: int) -> None:
        """Slot: switch to (or update) the countdown-warning display."""
        self._mode = "countdown"
        self._countdown_remaining = max(0, remaining_seconds)
        self.update()

    def hide_pill(self) -> None:
        self._spinner_timer.stop()
        self.hide()

    def update_level(self, rms: float) -> None:
        """Slot: push a new real-time volume sample into the bar history."""
        normalized = max(0.0, min(1.0, rms * 6.0))
        height = BAR_MIN_HEIGHT + normalized * (BAR_MAX_HEIGHT - BAR_MIN_HEIGHT)
        self._bar_heights = self._bar_heights[1:] + [height]
        if self._mode == "recording":
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override name)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(PILL_BG_COLOR))
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

        if self._mode == "recording":
            self._paint_bars(painter, rect)
        elif self._mode == "countdown":
            self._paint_countdown(painter, rect)
        else:
            self._paint_processing(painter, rect)
        painter.end()

    def _paint_bars(self, painter: QPainter, rect) -> None:
        dot_radius = 4
        painter.setBrush(QBrush(DOT_COLOR))
        center_y = rect.height() // 2
        painter.drawEllipse(14, center_y - dot_radius, dot_radius * 2, dot_radius * 2)
        painter.drawEllipse(rect.width() - 14 - dot_radius * 2, center_y - dot_radius, dot_radius * 2, dot_radius * 2)

        painter.setBrush(QBrush(BAR_COLOR))
        total_bars_width = NUM_BARS * BAR_WIDTH + (NUM_BARS - 1) * BAR_GAP
        start_x = (rect.width() - total_bars_width) / 2
        for index, height in enumerate(self._bar_heights):
            x = start_x + index * (BAR_WIDTH + BAR_GAP)
            y = center_y - height / 2
            painter.drawRoundedRect(int(x), int(y), BAR_WIDTH, int(height), 2, 2)

    def _paint_countdown(self, painter: QPainter, rect) -> None:
        dot_radius = 4
        painter.setBrush(QBrush(DOT_COLOR))
        center_y = rect.height() // 2
        painter.drawEllipse(14, center_y - dot_radius, dot_radius * 2, dot_radius * 2)
        painter.drawEllipse(rect.width() - 14 - dot_radius * 2, center_y - dot_radius, dot_radius * 2, dot_radius * 2)

        painter.setPen(COUNTDOWN_COLOR)
        font = painter.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 4)
        painter.setFont(font)
        text = f"{self._countdown_remaining}s"
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)

    def _paint_processing(self, painter: QPainter, rect) -> None:
        pen = QPen(TEXT_COLOR, 2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy, radius = 28, rect.height() // 2, 9
        painter.drawArc(cx - radius, cy - radius, radius * 2, radius * 2, self._spinner_angle * 16, 270 * 16)

        painter.setPen(TEXT_COLOR)
        text_rect = rect.adjusted(50, 0, -12, 0)
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter), self._processing_text)
