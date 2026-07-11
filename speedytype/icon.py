from __future__ import annotations

from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtCore import Qt


def build_app_icon() -> QIcon:
    """Generate a small icon at runtime; no icon asset file exists in this
    POC, and a plain generated glyph is enough to identify the tray entry
    and give dialog windows a non-blank title-bar icon.
    """
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#1a1a1a"))
    painter.setPen(QColor("#ffffff"))
    painter.drawEllipse(2, 2, 28, 28)
    font = painter.font()
    font.setBold(True)
    font.setPointSize(14)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), int(Qt.AlignmentFlag.AlignCenter), "S")
    painter.end()
    return QIcon(pixmap)
