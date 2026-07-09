from __future__ import annotations

from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from speedytype.config import load_config
from speedytype.llm import call_gemini_polisher, call_minimax_polisher, call_openai_polisher


def openai_models(api_key: str) -> list[str]:
    response = requests.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=30)
    response.raise_for_status()
    data = response.json()
    return sorted(item["id"] for item in data.get("data", []) if isinstance(item, dict) and isinstance(item.get("id"), str))


def gemini_models(api_key: str) -> list[str]:
    response = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}", timeout=30)
    response.raise_for_status()
    data = response.json()
    names = []
    for item in data.get("models", []):
        name = str(item.get("name", "")).removeprefix("models/")
        if "generateContent" in item.get("supportedGenerationMethods", []):
            names.append(name)
    return sorted(names)


def try_call(label: str, func):
    try:
        result = func()
        print(f"PROBE {label}: OK text={result.text!r} seconds={result.llm_call_seconds:.6f} usage={result.usage.raw}")
        return {
            "label": label,
            "ok": True,
            "text": result.text,
            "llm_call_seconds": result.llm_call_seconds,
            "retry_wait_seconds": result.retry_wait_seconds,
            "usage": result.usage.raw,
        }
    except Exception as exc:
        print(f"PROBE {label}: ERROR {exc}")
        return {"label": label, "ok": False, "error": str(exc)}


def main() -> int:
    config = load_config(".env")
    results: dict[str, object] = {
        "anthropic": {"skipped": True, "reason": "No Anthropic API billing plan per task instruction."},
        "providers": {},
        "probes": [],
    }

    o_models = openai_models(config.openai_api_key)
    g_models = gemini_models(config.gemini_api_key)
    results["providers"] = {
        "openai_models_sample": [m for m in o_models if m.startswith("gpt-5")][:30],
        "gemini_flash_models": [m for m in g_models if "flash" in m],
        "minimax_models_from_docs": ["MiniMax-M3", "MiniMax-M2.7", "MiniMax-M2.7-highspeed", "MiniMax-M2.5", "MiniMax-M2.5-highspeed"],
    }

    gemini_candidates = [m for m in ["gemini-3.5-flash", "gemini-3.1-flash-lite"] if m in g_models]
    for model in gemini_candidates:
        for level in ["", "none", "minimal", "low"]:
            label = f"gemini:{model}:thinking={level or 'default'}"
            results["probes"].append(
                try_call(label, lambda model=model, level=level: call_gemini_polisher("你好", config, model=model, thinking_level=level))
            )

    requested_openai = ["gpt-5.5", "gpt-5.4-mini", "gpt-5.4-nano"]
    openai_candidates = [m for m in requested_openai if m in o_models]
    if not openai_candidates:
        openai_candidates = [m for m in o_models if m.startswith("gpt-5.4") or m.startswith("gpt-5.5")][:3]
    for model in openai_candidates:
        for effort in ["none", "minimal", "low"]:
            label = f"openai:{model}:reasoning={effort}"
            results["probes"].append(
                try_call(label, lambda model=model, effort=effort: call_openai_polisher("你好", config, model=model, reasoning_effort=effort))
            )

    for thinking_type in ["", "disabled", "adaptive"]:
        label = f"minimax:MiniMax-M3:thinking={thinking_type or 'default'}"
        results["probes"].append(
            try_call(label, lambda thinking_type=thinking_type: call_minimax_polisher("你好", config, model="MiniMax-M3", thinking_type=thinking_type))
        )

    Path("phase2_probe_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE phase2_probe_results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
