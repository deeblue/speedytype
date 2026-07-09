from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
import re
import time

import requests

from speedytype.api import _raise_http_error, build_system_prompt, gemini_generate_content_url, parse_gemini_text
from speedytype.config import AppConfig


@dataclass(frozen=True)
class LlmUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LlmResult:
    text: str
    provider: str
    model: str
    llm_call_seconds: float
    retry_wait_seconds: float
    retry_count: int
    usage: LlmUsage
    raw_response: dict[str, Any]


def is_transient_error(exc: Exception) -> bool:
    message = str(exc)
    return "status=429" in message or "status=503" in message


def retry_api_call(
    label: str,
    operation: Callable[[], Any],
    *,
    attempts: int = 3,
    clock: Callable[[], float] = time.perf_counter,
    sleeper: Callable[[float], None] = time.sleep,
    wait_schedule: tuple[float, ...] = (2.0, 4.0),
) -> tuple[Any, float, float, int]:
    api_seconds = 0.0
    retry_wait_seconds = 0.0
    retry_count = 0
    last_exc: Exception | None = None

    for attempt in range(1, attempts + 1):
        start = clock()
        try:
            value = operation()
            api_seconds += clock() - start
            return value, round(api_seconds, 12), retry_wait_seconds, retry_count
        except Exception as exc:
            api_seconds += clock() - start
            last_exc = exc
            if not is_transient_error(exc) or attempt == attempts:
                raise
            wait_seconds = wait_schedule[min(attempt - 1, len(wait_schedule) - 1)]
            retry_count += 1
            print(f"{label} transient error on attempt {attempt}/{attempts}; retrying in {wait_seconds}s: {exc}", flush=True)
            sleeper(wait_seconds)
            retry_wait_seconds += wait_seconds

    raise last_exc or RuntimeError(f"{label} failed")


def _gemini_usage(payload: dict[str, Any]) -> LlmUsage:
    usage = payload.get("usageMetadata", {})
    return LlmUsage(
        input_tokens=usage.get("promptTokenCount"),
        output_tokens=usage.get("candidatesTokenCount"),
        total_tokens=usage.get("totalTokenCount"),
        raw=usage if isinstance(usage, dict) else {},
    )


def _openai_usage(payload: dict[str, Any]) -> LlmUsage:
    usage = payload.get("usage", {})
    return LlmUsage(
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        total_tokens=usage.get("total_tokens"),
        raw=usage if isinstance(usage, dict) else {},
    )


def _minimax_usage(payload: dict[str, Any]) -> LlmUsage:
    usage = payload.get("usage", {})
    return LlmUsage(
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
        raw=usage if isinstance(usage, dict) else {},
    )


def _strip_minimax_think(text: str) -> str:
    return re.sub(r"(?s)<think>.*?</think>", "", text).strip()


def call_gemini_polisher(text: str, config: AppConfig, *, model: str, thinking_level: str = "", timeout_seconds: int = 120) -> LlmResult:
    def operation() -> dict[str, Any]:
        generation_config: dict[str, Any] = {"temperature": 0.1}
        if thinking_level:
            generation_config["thinkingConfig"] = {"thinkingLevel": thinking_level}
        body = {
            "systemInstruction": {"parts": [{"text": build_system_prompt(config)}]},
            "contents": [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": generation_config,
        }
        response = requests.post(
            gemini_generate_content_url(model, config.gemini_api_key),
            headers={"Content-Type": "application/json"},
            json=body,
            timeout=timeout_seconds,
        )
        _raise_http_error("Gemini", response)
        return response.json()

    payload, api_seconds, retry_wait_seconds, retry_count = retry_api_call("Gemini", operation)
    return LlmResult(
        text=parse_gemini_text(payload),
        provider="gemini",
        model=model,
        llm_call_seconds=api_seconds,
        retry_wait_seconds=retry_wait_seconds,
        retry_count=retry_count,
        usage=_gemini_usage(payload),
        raw_response=payload,
    )


def parse_openai_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str):
        return output_text.strip()
    chunks: list[str] = []
    for item in payload.get("output", []) if isinstance(payload.get("output"), list) else []:
        for content in item.get("content", []) if isinstance(item, dict) else []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    if not chunks:
        raise RuntimeError(f"OpenAI response format unexpected:\n{payload}")
    return "".join(chunks).strip()


def call_openai_polisher(text: str, config: AppConfig, *, model: str, reasoning_effort: str = "", timeout_seconds: int = 120) -> LlmResult:
    def operation() -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "instructions": build_system_prompt(config),
            "input": text,
            "max_output_tokens": 512,
        }
        if reasoning_effort:
            body["reasoning"] = {"effort": reasoning_effort}
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {config.openai_api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=timeout_seconds,
        )
        _raise_http_error("OpenAI", response)
        return response.json()

    payload, api_seconds, retry_wait_seconds, retry_count = retry_api_call("OpenAI", operation)
    return LlmResult(
        text=parse_openai_text(payload),
        provider="openai",
        model=model,
        llm_call_seconds=api_seconds,
        retry_wait_seconds=retry_wait_seconds,
        retry_count=retry_count,
        usage=_openai_usage(payload),
        raw_response=payload,
    )


def call_minimax_polisher(text: str, config: AppConfig, *, model: str, thinking_type: str = "", timeout_seconds: int = 120) -> LlmResult:
    if not config.minimax_api_key:
        raise RuntimeError("Missing MINIMAX_API_KEY; skipping MiniMax call.")

    def operation() -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": build_system_prompt(config)},
                {"role": "user", "content": text},
            ],
            "temperature": 0.1,
            "max_completion_tokens": 512,
        }
        if thinking_type:
            body["thinking"] = {"type": thinking_type}
        response = requests.post(
            "https://api.minimax.io/v1/chat/completions",
            headers={"Authorization": f"Bearer {config.minimax_api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=timeout_seconds,
        )
        _raise_http_error("MiniMax", response)
        return response.json()

    payload, api_seconds, retry_wait_seconds, retry_count = retry_api_call("MiniMax", operation)
    try:
        raw_text = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"MiniMax response format unexpected:\n{payload}") from exc
    return LlmResult(
        text=_strip_minimax_think(raw_text),
        provider="minimax",
        model=model,
        llm_call_seconds=api_seconds,
        retry_wait_seconds=retry_wait_seconds,
        retry_count=retry_count,
        usage=_minimax_usage(payload),
        raw_response=payload,
    )


def call_llm_polisher(text: str, config: AppConfig) -> LlmResult:
    provider = config.llm_provider.lower()
    if provider == "gemini":
        return call_gemini_polisher(text, config, model=config.llm_model, thinking_level=config.llm_thinking_level)
    if provider == "openai":
        return call_openai_polisher(text, config, model=config.llm_model, reasoning_effort=config.llm_reasoning_effort)
    if provider == "minimax":
        return call_minimax_polisher(text, config, model=config.llm_model, thinking_type=config.llm_thinking_type)
    raise RuntimeError(f"Unsupported LLM_PROVIDER={config.llm_provider}")
