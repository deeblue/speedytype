from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np
import soundfile as sf
import websocket

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from speedytype.api import parse_whisper_text
from speedytype.console import safe_print
from speedytype.config import load_config
from speedytype.real_voice import parse_real_voice_script
from speedytype.pipeline import wav_duration_seconds

import requests


TARGET_TERMS = ["API", "BJ 團隊"]
DEFAULT_MODELS = ["whisper-1", "gpt-4o-mini-transcribe", "gpt-4o-transcribe", "gpt-realtime-whisper"]


def compact_text(value: str) -> str:
    return "".join(value.split())


def term_in_transcript(term: str, transcript: str) -> bool:
    return compact_text(term) in compact_text(transcript)


def transcribe_with_model(audio_path: Path, api_key: str, model: str, prompt: str, timeout_seconds: int = 120) -> tuple[str, float, dict[str, Any]]:
    if model == "gpt-realtime-whisper":
        return transcribe_with_realtime_whisper(audio_path, api_key, timeout_seconds=timeout_seconds)

    started = time.perf_counter()
    with audio_path.open("rb") as audio_file:
        response = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (audio_path.name, audio_file, "audio/wav")},
            data={"model": model, "prompt": prompt, "response_format": "json"},
            timeout=timeout_seconds,
        )
    elapsed = time.perf_counter() - started
    if not 200 <= response.status_code < 300:
        return "", elapsed, {"ok": False, "status_code": response.status_code, "body": response.text}
    payload = response.json()
    return parse_whisper_text(payload), elapsed, {"ok": True, "payload": payload}


def wav_to_pcm24_base64(audio_path: Path) -> str:
    audio, sample_rate = sf.read(audio_path, dtype="float32", always_2d=True)
    mono = audio.mean(axis=1)
    target_rate = 24000
    if sample_rate != target_rate and len(mono):
        old_x = np.linspace(0.0, 1.0, num=len(mono), endpoint=False)
        new_len = int(round(len(mono) * target_rate / sample_rate))
        new_x = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
        mono = np.interp(new_x, old_x, mono).astype("float32")
    pcm16 = np.clip(mono, -1.0, 1.0)
    pcm16 = (pcm16 * 32767.0).astype("<i2").tobytes()
    return base64.b64encode(pcm16).decode("ascii")


def transcribe_with_realtime_whisper(audio_path: Path, api_key: str, timeout_seconds: int = 120) -> tuple[str, float, dict[str, Any]]:
    started = time.perf_counter()
    events: list[dict[str, Any]] = []
    try:
        ws = websocket.create_connection(
            "wss://api.openai.com/v1/realtime?intent=transcription",
            header=[f"Authorization: Bearer {api_key}"],
            timeout=timeout_seconds,
        )
        ws.settimeout(timeout_seconds)
        ws.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "type": "transcription",
                        "audio": {
                            "input": {
                                "format": {"type": "audio/pcm", "rate": 24000},
                                "transcription": {
                                    "model": "gpt-realtime-whisper",
                                    "language": "zh",
                                    "delay": "low",
                                },
                                "turn_detection": None,
                            }
                        },
                    },
                }
            )
        )
        session_ready = False
        while not session_ready:
            event = json.loads(ws.recv())
            events.append(event)
            if event.get("type") == "session.updated":
                session_ready = True
            if event.get("type") == "error":
                raise RuntimeError(json.dumps(event, ensure_ascii=False))

        ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": wav_to_pcm24_base64(audio_path)}))
        ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

        transcript = ""
        while True:
            event = json.loads(ws.recv())
            events.append(event)
            if event.get("type") == "conversation.item.input_audio_transcription.completed":
                transcript = str(event.get("transcript", ""))
                break
            if event.get("type") == "error":
                raise RuntimeError(json.dumps(event, ensure_ascii=False))
        ws.close()
        return transcript, time.perf_counter() - started, {"ok": True, "events": events[-10:]}
    except Exception as exc:
        try:
            ws.close()  # type: ignore[name-defined]
        except Exception:
            pass
        return "", time.perf_counter() - started, {"ok": False, "status_code": "realtime_error", "body": str(exc), "events": events[-10:]}


def sample_audio_path(directory: Path, index: int) -> Path:
    return directory / f"segment{index:02d}_final.wav"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env")
    parser.add_argument("--dir", default="real_voice_round2")
    parser.add_argument("--script", default="real_voice_script_round2.md")
    parser.add_argument("--output-jsonl", default="phase4_focused_stt_results.jsonl")
    parser.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    args = parser.parse_args()

    config = load_config(args.env)
    items = parse_real_voice_script(Path(args.script))
    samples = []
    for item in items:
        expected_terms = [term for term in TARGET_TERMS if term in item.text]
        if not expected_terms:
            continue
        audio_path = sample_audio_path(Path(args.dir), item.index)
        if not audio_path.exists():
            raise FileNotFoundError(audio_path)
        samples.append((item, expected_terms, audio_path))

    records = []
    output_path = Path(args.output_jsonl)
    with output_path.open("w", encoding="utf-8") as handle:
        for model in args.models:
            for item, expected_terms, audio_path in samples:
                text, elapsed, raw = transcribe_with_model(audio_path, config.openai_api_key, model, config.whisper_vocab_bias)
                term_hits = {term: term_in_transcript(term, text) for term in expected_terms}
                record = {
                    "model": model,
                    "index": item.index,
                    "audio_path": str(audio_path),
                    "duration_seconds": wav_duration_seconds(audio_path),
                    "expected_text": item.text,
                    "expected_terms": expected_terms,
                    "ok": bool(raw.get("ok")),
                    "status_code": raw.get("status_code"),
                    "elapsed_seconds": elapsed,
                    "transcript": text,
                    "term_hits": term_hits,
                    "error_body": raw.get("body", ""),
                }
                safe_print(json.dumps(record, ensure_ascii=False), flush=True)
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                records.append(record)

    safe_print(f"WROTE {output_path}")
    safe_print(f"samples={len(samples)} models={','.join(args.models)}")
    for model in args.models:
        subset = [record for record in records if record["model"] == model and record["ok"]]
        errors = [record for record in records if record["model"] == model and not record["ok"]]
        if not subset:
            safe_print(f"SUMMARY {model}: ok=0 errors={len(errors)}")
            if errors:
                safe_print(f"FIRST_ERROR {model}: status={errors[0]['status_code']} body={errors[0]['error_body'][:300]!r}")
            continue
        safe_print(f"SUMMARY {model}: ok={len(subset)} errors={len(errors)} avg_latency={sum(r['elapsed_seconds'] for r in subset) / len(subset):.6f}")
        for term in TARGET_TERMS:
            expected = [record for record in subset if term in record["expected_terms"]]
            correct = [record for record in expected if record["term_hits"].get(term)]
            rate = 0.0 if not expected else len(correct) / len(expected) * 100.0
            safe_print(f"  {term}: {len(correct)}/{len(expected)} {rate:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
