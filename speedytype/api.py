from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from speedytype.config import AppConfig, DEFAULT_GEMINI_MODEL


WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"
GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
BASE_SYSTEM_PROMPT = """你是一個精通多國語言的「語音輸入修飾專家」。
1. 刪除所有口語贅字：如「呃」、「然後」、「那個」、「就是說」。
2. 智能修正語病：若使用者在陳述中途自我修正（例如：「我們下週一，啊不對，下週三要開會」），
   請直接輸出修正後的結果（「我們下週三要開會」），不要保留修正前的內容。
3. 智能排版：根據內容邏輯自動分段，若包含多個平行觀點、步驟，請自動使用 Markdown 條列式排版。
4. 專業名詞校正：精準識別技術與研發專有名詞（例如：BIOS, Firmware, NPI, QA, API, TPE 團隊, BJ 團隊），
   修正前後文中因語音辨識造成的錯別字或同音異字。
{disambiguation_hints}
5. 數字與重複內容保留：若語音辨識結果因使用者重複講述相同內容而出現破碎、重複的文字，請合併為一次乾淨的版本，但必須完整保留其中出現過的所有數字、代號與實際內容。這條規則不適用於規則2的自我修正情境（自我修正時仍應捨棄修正前的錯誤內容）。
6. 嚴格限制：只輸出修飾後的最終文字，絕對不要包含任何自我解釋、招呼語或
   「以下是修飾後的文字」等額外內容。"""

DISAMBIGUATION_HINTS = """   常見語音辨識易混淆詞對，請依上下文語意判斷正確用詞：
   - API / NPI：討論介面呼叫、程式規格、測試介面時通常是 API；討論新產品導入、專案進度、會議前整理項目時通常是 NPI。
   - TPE 團隊 / PD 團隊 / BJ 團隊：這些是不同的團隊代稱。若前後文只提到一個團隊名稱且發音混淆，
     優先參考完整句子中的其他線索判斷；若沒有足夠線索，保留原轉譯，不要臆測替換成另一個團隊名稱。"""


def build_system_prompt(config: AppConfig) -> str:
    hints = DISAMBIGUATION_HINTS if config.use_disambiguation_hints else ""
    return BASE_SYSTEM_PROMPT.format(disambiguation_hints=hints).replace("\n\n6.", "\n6.")


SYSTEM_PROMPT = BASE_SYSTEM_PROMPT.format(disambiguation_hints=DISAMBIGUATION_HINTS).replace("\n\n6.", "\n6.")


class ApiResponseFormatError(RuntimeError):
    pass


def _raw_payload(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_whisper_text(payload: dict[str, Any]) -> str:
    text = payload.get("text")
    if not isinstance(text, str):
        raise ApiResponseFormatError("Whisper response missing string field: text. Raw response:\n" + _raw_payload(payload))
    return text


def parse_whisper_verbose(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload.get("text")
    segments = payload.get("segments")
    if not isinstance(text, str):
        raise ApiResponseFormatError("Whisper verbose response missing string field: text. Raw response:\n" + _raw_payload(payload))
    if segments is not None and not isinstance(segments, list):
        raise ApiResponseFormatError("Whisper verbose response missing list field: segments. Raw response:\n" + _raw_payload(payload))
    return payload


def parse_gemini_text(payload: dict[str, Any]) -> str:
    try:
        candidates = payload["candidates"]
        parts = candidates[0]["content"]["parts"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ApiResponseFormatError(
            "Gemini response missing candidates[0].content.parts text. Raw response:\n" + _raw_payload(payload)
        ) from exc

    texts = [part["text"] for part in parts if isinstance(part, dict) and isinstance(part.get("text"), str)]
    if not texts:
        raise ApiResponseFormatError(
            "Gemini response missing candidates[0].content.parts text. Raw response:\n" + _raw_payload(payload)
        )
    return "".join(texts).strip()


def _raise_http_error(label: str, response: requests.Response) -> None:
    if response.status_code >= 200 and response.status_code < 300:
        return
    raise RuntimeError(f"{label} API error status={response.status_code}, body:\n{response.text}")


def transcribe_audio_request(
    audio_path: Path,
    config: AppConfig,
    *,
    timeout_seconds: int = 120,
    response_format: str = "json",
    timestamp_granularities: list[str] | None = None,
    prompt_override: str | None = None,
    model: str = "whisper-1",
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "model": model,
        "prompt": config.whisper_vocab_bias if prompt_override is None else prompt_override,
    }
    if response_format:
        data["response_format"] = response_format
    if timestamp_granularities:
        for index, value in enumerate(timestamp_granularities):
            data[f"timestamp_granularities[{index}]"] = value
    with audio_path.open("rb") as audio_file:
        response = requests.post(
            WHISPER_URL,
            headers={"Authorization": f"Bearer {config.openai_api_key}"},
            files={"file": (audio_path.name, audio_file, "audio/wav")},
            data=data,
            timeout=timeout_seconds,
        )
    _raise_http_error("Whisper", response)
    return response.json()


def transcribe_audio(audio_path: Path, config: AppConfig, timeout_seconds: int = 120) -> str:
    payload = transcribe_audio_request(audio_path, config, timeout_seconds=timeout_seconds)
    return parse_whisper_text(payload)


def transcribe_audio_verbose(
    audio_path: Path,
    config: AppConfig,
    *,
    timeout_seconds: int = 120,
    prompt_override: str | None = None,
    model: str = "whisper-1",
) -> dict[str, Any]:
    payload = transcribe_audio_request(
        audio_path,
        config,
        timeout_seconds=timeout_seconds,
        response_format="verbose_json",
        timestamp_granularities=["segment"],
        prompt_override=prompt_override,
        model=model,
    )
    return parse_whisper_verbose(payload)


def gemini_generate_content_url(model: str, api_key: str) -> str:
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"


def polish_text(text: str, config: AppConfig, timeout_seconds: int = 120) -> str:
    body = {
        "systemInstruction": {"parts": [{"text": build_system_prompt(config)}]},
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "generationConfig": {"temperature": 0.1},
    }
    response = requests.post(
        gemini_generate_content_url(config.gemini_model, config.gemini_api_key),
        headers={"Content-Type": "application/json"},
        json=body,
        timeout=timeout_seconds,
    )
    _raise_http_error("Gemini", response)
    return parse_gemini_text(response.json())


def discover_flash_model(api_key: str, timeout_seconds: int = 30) -> str:
    response = requests.get(f"{GEMINI_MODELS_URL}?key={api_key}", timeout=timeout_seconds)
    _raise_http_error("Gemini model list", response)
    payload = response.json()
    models = payload.get("models")
    if not isinstance(models, list):
        raise ApiResponseFormatError("Gemini model list missing models array. Raw response:\n" + _raw_payload(payload))

    names: list[str] = []
    for model in models:
        if not isinstance(model, dict):
            continue
        name = str(model.get("name", "")).removeprefix("models/")
        methods = model.get("supportedGenerationMethods", [])
        if "generateContent" in methods and "flash" in name.lower():
            names.append(name)

    stable = [name for name in names if "preview" not in name.lower() and "latest" not in name.lower()]
    preferred = sorted(stable or names, reverse=True)
    return preferred[0] if preferred else DEFAULT_GEMINI_MODEL
