import pytest
from PyQt6.QtWidgets import QApplication, QLabel

from speedytype.about_dialog import AboutDialog
from speedytype.config import AppConfig
from speedytype.version import BUILD_DATE, STT_MODEL, VERSION


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_about_dialog_shows_current_config(qapp):
    config = AppConfig(
        openai_api_key="sk-x",
        gemini_api_key="gem-x",
        llm_provider="gemini",
        llm_model="gemini-3.1-flash-lite",
    )
    dialog = AboutDialog(config)

    all_text = " ".join(label.text() for label in dialog.findChildren(QLabel))

    assert VERSION in all_text
    assert BUILD_DATE in all_text
    assert STT_MODEL in all_text
    assert "gemini" in all_text
    assert "gemini-3.1-flash-lite" in all_text
