import pytest
from PyQt6.QtWidgets import QApplication

from speedytype.overlay import RecordingPill, format_recording_elapsed


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def pill(qapp):
    widget = RecordingPill(warning_duration_ms=2000)
    yield widget
    widget.close()


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "00:00"), (65, "01:05"), (1500, "25:00")],
)
def test_format_recording_elapsed(seconds, expected):
    assert format_recording_elapsed(seconds) == expected


def test_show_elapsed_stores_recording_mode_and_formatted_text(pill):
    pill.show_elapsed(65)

    assert pill._mode == "recording"
    assert pill._elapsed_text == "01:05"


def test_countdown_supersedes_elapsed_state(pill):
    pill.show_elapsed(65)
    pill.show_countdown(59)

    assert pill._mode == "countdown"
    assert pill._countdown_remaining == 59


def test_show_auto_stopped_stores_approved_warning_and_starts_timer(pill):
    pill.show_auto_stopped()

    assert pill._mode == "auto_stopped"
    assert pill._warning_text == "已達錄音上限，自動停止"
    assert pill._warning_timer.isActive()
    assert pill.isVisible()


def test_processing_waits_for_auto_stop_warning_to_finish(pill):
    pill.show_auto_stopped()
    pill.show_processing()

    assert pill._mode == "auto_stopped"
    assert pill._processing_pending is True

    pill._finish_warning()

    assert pill._mode == "processing"
    assert pill._processing_pending is False
    assert pill.isVisible()


def test_hide_waits_for_auto_stop_warning_to_finish(pill):
    pill.show_auto_stopped()
    pill.show_processing()
    pill.hide_pill()

    assert pill._mode == "auto_stopped"
    assert pill._processing_pending is True
    assert pill._hide_pending is True
    assert pill.isVisible()

    pill._finish_warning()

    assert pill._hide_pending is False
    assert pill._processing_pending is False
    assert not pill.isVisible()


@pytest.mark.parametrize(
    ("name", "action"),
    [
        ("recording_start", lambda widget: widget.show_recording()),
        ("recording_25min", lambda widget: widget.show_elapsed(1500)),
        ("countdown_60", lambda widget: widget.show_countdown(60)),
        ("countdown_0", lambda widget: widget.show_countdown(0)),
        ("auto_stopped", lambda widget: widget.show_auto_stopped()),
        ("processing", lambda widget: widget._show_processing_now()),
    ],
)
def test_recording_pill_states_render_nonblank(qapp, pill, name, action):
    action(pill)
    qapp.processEvents()

    image = pill.grab().toImage()

    assert not image.isNull(), name
    colors = {
        image.pixelColor(x, y).rgba()
        for x in range(0, image.width(), 8)
        for y in range(0, image.height(), 8)
    }
    assert len(colors) > 1, name
