import pytest

from speedytype import api
from speedytype.api import ApiResponseFormatError, parse_gemini_text, parse_whisper_text
from speedytype.config import AppConfig


def test_parse_whisper_text_reads_text_field():
    assert parse_whisper_text({"text": "我們下週三要開會"}) == "我們下週三要開會"


def test_transcribe_audio_forwards_selected_model_to_request(tmp_path, monkeypatch):
    captured = []
    monkeypatch.setattr(
        api,
        "transcribe_audio_request",
        lambda path, config, **kwargs: captured.append(kwargs) or {"text": "ok"},
    )

    result = api.transcribe_audio(
        tmp_path / "audio.wav",
        AppConfig(openai_api_key="x", gemini_api_key="y"),
        model="whisper-selected",
    )

    assert result == "ok"
    assert captured == [{"timeout_seconds": 120, "model": "whisper-selected"}]


def test_parse_whisper_text_rejects_missing_text_with_raw_response():
    payload = {"result": {"text": "wrong nesting"}}

    with pytest.raises(ApiResponseFormatError) as exc:
        parse_whisper_text(payload)

    message = str(exc.value)
    assert "Whisper response missing string field: text" in message
    assert '"result"' in message


def test_parse_gemini_text_reads_standard_candidate_part():
    payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "我們下週三要開會，請 TPE 團隊同步 BIOS 狀態。"}
                    ]
                }
            }
        ]
    }

    assert parse_gemini_text(payload) == "我們下週三要開會，請 TPE 團隊同步 BIOS 狀態。"


def test_parse_gemini_text_joins_multiple_text_parts():
    payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "第一段"},
                        {"inlineData": {"mimeType": "text/plain"}},
                        {"text": "\n第二段"},
                    ]
                }
            }
        ]
    }

    assert parse_gemini_text(payload) == "第一段\n第二段"


def test_parse_gemini_text_rejects_unexpected_nesting_with_raw_response():
    payload = {"output": {"candidates": [{"text": "wrong nesting"}]}}

    with pytest.raises(ApiResponseFormatError) as exc:
        parse_gemini_text(payload)

    message = str(exc.value)
    assert "Gemini response missing candidates[0].content.parts text" in message
    assert '"output"' in message
