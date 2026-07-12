from __future__ import annotations

import requests
import pytest

from speedytype.config import AppConfig
from speedytype.llm import call_llm_polisher, call_ollama_polisher, parse_ollama_text


PAYLOAD = {
    "model": "gemma4:12b",
    "message": {"role": "assistant", "content": "  整理後文字。  "},
    "done": True,
    "total_duration": 2_000_000_000,
    "load_duration": 500_000_000,
    "prompt_eval_count": 120,
    "prompt_eval_duration": 300_000_000,
    "eval_count": 20,
    "eval_duration": 1_000_000_000,
}


def make_config(**overrides):
    values = {
        "openai_api_key": "test-openai",
        "gemini_api_key": "test-gemini",
        "llm_provider": "ollama",
        "llm_model": "gemma4:12b",
        "ollama_base_url": "http://localhost:11434",
        "ollama_keep_alive": "15m",
    }
    values.update(overrides)
    return AppConfig(**values)


def test_parse_ollama_text_trims_assistant_content():
    assert parse_ollama_text(PAYLOAD) == "整理後文字。"


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        ({"message": {"role": "assistant", "content": "  "}}, "empty"),
        ({"message": "not an object"}, "message"),
    ],
)
def test_parse_ollama_text_rejects_unusable_content(payload, detail):
    with pytest.raises(RuntimeError, match=rf"(?i)Ollama.*{detail}"):
        parse_ollama_text(payload)


def test_call_ollama_polisher_sends_native_chat_request_and_maps_usage(monkeypatch):
    captured = {}

    class Response:
        status_code = 200

        def json(self):
            return PAYLOAD

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()

    monkeypatch.setattr("speedytype.llm.requests.post", fake_post)
    config = make_config()

    result = call_ollama_polisher("raw transcript", config, model="gemma4:12b", timeout_seconds=9)

    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["timeout"] == 9
    assert captured["json"] == {
        "model": "gemma4:12b",
        "messages": [
            {"role": "system", "content": pytest.importorskip("speedytype.api").build_system_prompt(config)},
            {"role": "user", "content": "raw transcript"},
        ],
        "stream": False,
        "think": False,
        "keep_alive": "15m",
        "options": {"temperature": 0.1, "num_predict": 512},
    }
    assert result.text == "整理後文字。"
    assert result.provider == "ollama"
    assert result.model == "gemma4:12b"
    assert result.usage.input_tokens == 120
    assert result.usage.output_tokens == 20
    assert result.usage.total_tokens == 140
    assert result.raw_response is PAYLOAD
    assert result.retry_count == 0
    assert result.retry_wait_seconds == 0


@pytest.mark.parametrize("error", [requests.ConnectionError("refused"), requests.Timeout("slow")])
def test_call_ollama_polisher_names_url_and_model_for_network_failures(monkeypatch, error):
    calls = 0

    def fail(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise error

    monkeypatch.setattr("speedytype.llm.requests.post", fail)

    with pytest.raises(RuntimeError, match=r"Ollama.*http://localhost:11434/api/chat.*gemma4:12b"):
        call_ollama_polisher("text", make_config(), model="gemma4:12b")
    assert calls == 1


def test_call_llm_polisher_dispatches_to_ollama(monkeypatch):
    sentinel = object()
    received = {}

    def fake_call(text, config, *, model):
        received.update(text=text, config=config, model=model)
        return sentinel

    monkeypatch.setattr("speedytype.llm.call_ollama_polisher", fake_call)
    config = make_config(llm_model="gemma4:12b")

    assert call_llm_polisher("draft", config) is sentinel
    assert received == {"text": "draft", "config": config, "model": "gemma4:12b"}


@pytest.mark.parametrize("provider", ["OlLaMa", "GeMiNi", "MiNiMaX"])
def test_call_llm_polisher_dispatch_is_case_insensitive(monkeypatch, provider):
    config = make_config(llm_provider=provider)
    sentinel = object()
    target = {"ollama": "call_ollama_polisher", "gemini": "call_gemini_polisher", "minimax": "call_minimax_polisher"}[provider.lower()]
    monkeypatch.setattr(f"speedytype.llm.{target}", lambda *args, **kwargs: sentinel)
    assert call_llm_polisher("draft", config) is sentinel
