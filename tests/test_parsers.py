import pytest
from types import SimpleNamespace

from speedytype import api
from speedytype.api import (
    ApiResponseFormatError,
    DEFAULT_STT_MODEL,
    GroqRateLimitError,
    parse_gemini_text,
    parse_whisper_text,
)
from speedytype.config import AppConfig


def test_parse_whisper_text_reads_text_field():
    assert parse_whisper_text({"text": "我們下週三要開會"}) == "我們下週三要開會"


def test_transcribe_audio_forwards_selected_openai_model_to_request(tmp_path, monkeypatch):
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


def test_transcribe_audio_defaults_to_groq_model_and_key(tmp_path, monkeypatch):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"audio")
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return SimpleNamespace(status_code=200, json=lambda: {"text": "groq raw"})

    monkeypatch.setattr(api.requests, "post", fake_post)

    result = api.transcribe_audio_result(
        audio_path,
        AppConfig(openai_api_key="openai", gemini_api_key="gemini", groq_api_key="groq"),
    )

    assert result.text == "groq raw"
    assert result.provider == "groq"
    assert result.model == "whisper-large-v3"
    assert result.stt_model == DEFAULT_STT_MODEL
    assert captured["url"] == api.GROQ_TRANSCRIPTIONS_URL
    assert captured["headers"]["Authorization"] == "Bearer groq"
    assert captured["data"]["model"] == "whisper-large-v3"


def test_transcribe_audio_falls_back_to_openai_on_groq_rate_limit(tmp_path, monkeypatch):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"audio")
    calls = []

    def fake_groq_request(*args, **kwargs):
        calls.append(("groq", kwargs["model"]))
        raise GroqRateLimitError("limited")

    def fake_openai_request(*args, **kwargs):
        calls.append(("openai", kwargs["model"]))
        return {"text": "openai raw"}

    monkeypatch.setattr(api, "transcribe_audio_groq_request", fake_groq_request)
    monkeypatch.setattr(api, "transcribe_audio_request", fake_openai_request)

    result = api.transcribe_audio_result(
        audio_path,
        AppConfig(openai_api_key="openai", gemini_api_key="gemini", groq_api_key="groq"),
    )

    assert result.text == "openai raw"
    assert result.provider == "openai"
    assert result.model == "whisper-1"
    assert result.fallback_used is True
    assert result.fallback_reason == "groq_rate_limit"
    assert calls == [("groq", "whisper-large-v3"), ("openai", "whisper-1")]


def test_transcribe_audio_does_not_fallback_on_non_rate_limit_groq_error(tmp_path, monkeypatch):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"audio")
    openai_calls = []

    def fake_groq_request(*args, **kwargs):
        raise RuntimeError("groq bad request")

    monkeypatch.setattr(api, "transcribe_audio_groq_request", fake_groq_request)
    monkeypatch.setattr(api, "transcribe_audio_request", lambda *args, **kwargs: openai_calls.append(kwargs))

    with pytest.raises(RuntimeError, match="groq bad request"):
        api.transcribe_audio_result(
            audio_path,
            AppConfig(openai_api_key="openai", gemini_api_key="gemini", groq_api_key="groq"),
        )

    assert openai_calls == []


@pytest.mark.parametrize(
    ("filename", "expected_mime"),
    [("audio.wav", "audio/wav"), ("audio.flac", "audio/flac")],
)
def test_transcription_request_uses_container_mime_and_json_without_timestamps(
    tmp_path, monkeypatch, filename, expected_mime
):
    audio_path = tmp_path / filename
    audio_path.write_bytes(b"audio")
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(status_code=200, json=lambda: {"text": "ok"})

    monkeypatch.setattr(api.requests, "post", fake_post)

    result = api.transcribe_audio_request(
        audio_path,
        AppConfig(openai_api_key="x", gemini_api_key="y"),
    )

    assert result == {"text": "ok"}
    assert captured["files"]["file"][2] == expected_mime
    assert captured["data"]["response_format"] == "json"
    assert not any(key.startswith("timestamp_granularities") for key in captured["data"])


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
