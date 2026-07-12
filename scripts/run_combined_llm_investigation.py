from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from scripts.test_prompt_variants import CANDIDATE_PROMPT, CURRENT_PROMPT, TEST_CASES, build_prompt
from scripts.test_prompt_variants_repeated import PROBLEM_INPUT
from speedytype.api import gemini_generate_content_url, parse_gemini_text, transcribe_audio
from speedytype.config import load_config
from speedytype.real_voice import parse_real_voice_script


CORPORA = (
    ("round1", Path("real_voice"), Path("real_voice_script.md")),
    ("round2", Path("real_voice_round2"), Path("real_voice_script_round2.md")),
)


def append_record(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, ensure_ascii=False) + "\n")


def gemini_once(text: str, prompt: str, config, model: str) -> dict:
    started = time.perf_counter()
    try:
        response = requests.post(
            gemini_generate_content_url(model, config.gemini_api_key),
            headers={"Content-Type": "application/json"},
            json={
                "systemInstruction": {"parts": [{"text": prompt}]},
                "contents": [{"role": "user", "parts": [{"text": text}]}],
                "generationConfig": {"temperature": 0.1},
            },
            timeout=120,
        )
    except requests.RequestException as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "seconds": time.perf_counter() - started}
    if response.status_code != 200:
        return {
            "ok": False,
            "status_code": response.status_code,
            "error": response.text[:500],
            "seconds": time.perf_counter() - started,
        }
    try:
        output = parse_gemini_text(response.json())
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "seconds": time.perf_counter() - started}
    return {"ok": True, "output": output, "seconds": time.perf_counter() - started}


def run_candidate_repeats(config, output: Path) -> None:
    prompt = build_prompt(CANDIDATE_PROMPT, config.use_disambiguation_hints)
    prior = []
    if output.exists():
        prior = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    existing = [record for record in prior if record.get("stage") == "part_a_candidate_repeated"]
    valid = sum(1 for record in existing if record.get("ok"))
    for attempt in range(len(existing) + 1, 9):
        if valid >= 5:
            break
        result = gemini_once(PROBLEM_INPUT, prompt, config, config.gemini_model)
        record = {
            "stage": "part_a_candidate_repeated",
            "attempt": attempt,
            "model": config.gemini_model,
            "input": PROBLEM_INPUT,
            **result,
        }
        if result.get("ok"):
            text = str(result["output"])
            record["numbers_preserved"] = "123" in text
            valid += 1
        append_record(output, record)
        print(json.dumps(record, ensure_ascii=False), flush=True)
        if valid >= 5:
            break
        if result.get("status_code") == 429:
            break


def run_prompt_dimensions(config, output: Path) -> None:
    prompts = {
        "current": build_prompt(CURRENT_PROMPT, config.use_disambiguation_hints),
        "candidate": build_prompt(CANDIDATE_PROMPT, config.use_disambiguation_hints),
    }
    for name, text in TEST_CASES:
        for variant, prompt in prompts.items():
            result = gemini_once(text, prompt, config, config.llm_model)
            record = {
                "stage": "part_a_dimensions",
                "case": name,
                "variant": variant,
                "model": config.llm_model,
                "input": text,
                **result,
            }
            append_record(output, record)
            print(json.dumps(record, ensure_ascii=False), flush=True)
            if result.get("status_code") == 429:
                return


def selected_voice_items() -> list[tuple[str, Path, object]]:
    selected = []
    for corpus, audio_dir, script_path in CORPORA:
        for item in parse_real_voice_script(script_path):
            if "API" not in item.text and "BJ 團隊" not in item.text:
                continue
            selected.append((corpus, audio_dir / f"segment{item.index:02d}_final.wav", item))
    return selected


def run_voice_pairs(config, output: Path) -> None:
    prompt = build_prompt(CURRENT_PROMPT, config.use_disambiguation_hints)
    prior = []
    if output.exists():
        prior = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    previous = {
        (record.get("corpus"), record.get("segment")): record
        for record in prior
        if record.get("stage") == "part_b_voice_pair"
    }
    for corpus, audio_path, item in selected_voice_items():
        old = previous.get((corpus, item.index))
        if old and old.get("llm", {}).get("ok"):
            continue
        base = {
            "stage": "part_b_voice_pair",
            "corpus": corpus,
            "segment": item.index,
            "audio": str(audio_path),
            "expected_script": item.text,
            "model_stt": "whisper-1",
            "model_llm": config.llm_model,
        }
        if old and old.get("stt_ok"):
            raw = str(old["raw_transcript"])
            stt_result = {
                "stt_ok": True,
                "raw_transcript": raw,
                "stt_seconds": old.get("stt_seconds"),
                "stt_reused": True,
            }
        else:
            try:
                started = time.perf_counter()
                raw = transcribe_audio(audio_path, config)
                stt_result = {"stt_ok": True, "raw_transcript": raw, "stt_seconds": time.perf_counter() - started}
            except Exception as exc:
                record = {**base, "stt_ok": False, "stt_error": f"{type(exc).__name__}: {exc}"}
                append_record(output, record)
                print(json.dumps(record, ensure_ascii=False), flush=True)
                continue
        llm_result = gemini_once(raw, prompt, config, config.llm_model)
        record = {**base, **stt_result, "llm": llm_result}
        append_record(output, record)
        print(json.dumps(record, ensure_ascii=False), flush=True)
        if llm_result.get("status_code") == 429:
            break


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env")
    parser.add_argument("--output", default="combined_llm_investigation_results.jsonl")
    parser.add_argument(
        "--stage",
        required=True,
        choices=("candidate-repeats", "dimensions", "voice-pairs", "list-voice"),
    )
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    output = Path(args.output)
    if args.reset:
        output.unlink(missing_ok=True)
    config = load_config(args.env)
    if args.stage == "candidate-repeats":
        run_candidate_repeats(config, output)
    elif args.stage == "dimensions":
        run_prompt_dimensions(config, output)
    elif args.stage == "voice-pairs":
        run_voice_pairs(config, output)
    else:
        for corpus, audio_path, item in selected_voice_items():
            print(f"{corpus} segment={item.index} audio={audio_path} script={item.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
