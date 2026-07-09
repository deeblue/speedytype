from __future__ import annotations

from pathlib import Path
import json
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from speedytype.config import load_config
from speedytype.llm import call_gemini_polisher, call_minimax_polisher, call_openai_polisher


TRANSCRIPTS = {
    "short": "呃,我們下週一,啊不對,下週三要開會,請 TPE 團隊同步 BIOS 狀態。",
    "medium": "那個,我今天想先確認三件事 第一,Firmware 的 NPI 進度要更新 第二,QA 要在週五前回報 第三,我們下週一,不對,下週三要跟 BJ 團隊開會",
    "long": "這段是SpeedyType的長距測試 我們原本打算下週一發BIOS測試版 不對,應該是下週三發Firmware測試版 請TPE團隊先確認USB和Thunderbolt的相容性 然後QA在NPI會議前整理API測試結果 最後,BJ團隊協助確認使用者回饋",
}


def quality_flags(name: str, output: str) -> dict[str, object]:
    filler_ok = all(f not in output for f in ["呃", "那個", "就是說"])
    if name == "short":
        correction_ok = all(f not in output for f in ["啊不對", "不對", "下週一"]) and "下週三" in output
        required_terms = ["TPE 團隊", "BIOS"]
    elif name == "medium":
        correction_ok = all(f not in output for f in ["啊不對", "不對", "下週一"]) and "下週三" in output
        required_terms = ["Firmware", "NPI", "QA", "BJ 團隊"]
    else:
        correction_ok = all(f not in output for f in ["啊不對", "不對", "下週一", "BIOS 測試版"]) and "下週三" in output and "Firmware" in output
        required_terms = ["Firmware", "TPE", "USB", "Thunderbolt", "QA", "NPI", "API", "BJ"]
    extra_ok = not any(prefix in output for prefix in ["以下是", "修飾後", "您好", "Here is"])
    terms_ok = all(term in output for term in required_terms)
    bullets_ok = name != "long" or ("-" in output or "*" in output or "1." in output)
    return {
        "filler_ok": filler_ok,
        "correction_ok": correction_ok,
        "terms_ok": terms_ok,
        "bullets_ok": bullets_ok,
        "extra_ok": extra_ok,
        "overall_ok": filler_ok and correction_ok and terms_ok and bullets_ok and extra_ok,
        "subjective_zh": "natural" if "的" in output or "請" in output or "：" in output else "check_manually",
    }


def parse_label(label: str) -> dict[str, str]:
    provider, model, param = label.split(":", 2)
    key, value = param.split("=", 1)
    return {"provider": provider, "model": model, key: value}


def call_candidate(config, candidate: dict[str, str], text: str):
    provider = candidate["provider"]
    if provider == "gemini":
        return call_gemini_polisher(text, config, model=candidate["model"], thinking_level="" if candidate.get("thinking") == "default" else candidate.get("thinking", ""))
    if provider == "openai":
        return call_openai_polisher(text, config, model=candidate["model"], reasoning_effort=candidate.get("reasoning", ""))
    if provider == "minimax":
        return call_minimax_polisher(text, config, model=candidate["model"], thinking_type="" if candidate.get("thinking") == "default" else candidate.get("thinking", ""))
    raise RuntimeError(provider)


def main() -> int:
    config = load_config(".env")
    probe = json.loads(Path("phase2_probe_results.json").read_text(encoding="utf-8"))
    ok_labels = [p["label"] for p in probe["probes"] if p.get("ok")]

    candidates = []
    for label in ok_labels:
        parsed = parse_label(label)
        if label == "gemini:gemini-3.5-flash:thinking=default":
            candidates.append(parsed)
        elif parsed["provider"] == "gemini" and parsed["model"] == "gemini-3.1-flash-lite" and parsed.get("thinking") in {"minimal", "low"}:
            candidates.append(parsed)
        elif parsed["provider"] == "openai" and parsed.get("reasoning") in {"none", "minimal"}:
            candidates.append(parsed)
        elif parsed["provider"] == "minimax" and parsed.get("thinking") in {"disabled", "adaptive"}:
            candidates.append(parsed)

    output_path = Path("phase2_llm_results.jsonl")
    with output_path.open("w", encoding="utf-8") as handle:
        for candidate in candidates:
            for name, text in TRANSCRIPTS.items():
                for rep in range(1, 4):
                    started = time.time()
                    try:
                        result = call_candidate(config, candidate, text)
                        record = {
                            "candidate": candidate,
                            "case": name,
                            "rep": rep,
                            "ok": True,
                            "output": result.text,
                            "llm_call_seconds": result.llm_call_seconds,
                            "retry_wait_seconds": result.retry_wait_seconds,
                            "retry_count": result.retry_count,
                            "usage": result.usage.raw,
                            "quality": quality_flags(name, result.text),
                            "created": started,
                        }
                    except Exception as exc:
                        record = {"candidate": candidate, "case": name, "rep": rep, "ok": False, "error": str(exc), "created": started}
                    print(json.dumps(record, ensure_ascii=False), flush=True)
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"WROTE {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
