from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import soundfile as sf

from speedytype.api import transcribe_audio, transcribe_audio_verbose
from speedytype.config import load_config
from speedytype.quasi_streaming import build_chunk_plan, merge_text_with_overlap, slice_wav, tail_prompt


def run_batch(path: Path, config) -> dict:
    started = time.perf_counter()
    text = transcribe_audio(path, config)
    wall = time.perf_counter() - started
    return {"mode": "batch", "stt_tail_seconds": wall, "total_request_seconds": wall, "request_count": 1, "text": text}


def run_quasi(path: Path, config, chunk_seconds: float, overlap_seconds: float) -> dict:
    duration = sf.info(path).duration
    committed = ""
    worker_free_at = 0.0
    total_request = 0.0
    plans = build_chunk_plan(duration, chunk_seconds, overlap_seconds)
    for plan in plans:
        chunk = slice_wav(path, plan.start_seconds, plan.end_seconds)
        try:
            started = time.perf_counter()
            payload = transcribe_audio_verbose(chunk, config, prompt_override=tail_prompt(config, committed))
            request = time.perf_counter() - started
        finally:
            chunk.unlink(missing_ok=True)
        total_request += request
        for segment in payload.get("segments", []) or []:
            midpoint = plan.start_seconds + (float(segment.get("start", 0)) + float(segment.get("end", 0))) / 2
            if midpoint <= plan.commit_until_seconds + 1e-6:
                committed = merge_text_with_overlap(committed, str(segment.get("text", "")))
        worker_started = max(plan.end_seconds, worker_free_at)
        worker_free_at = worker_started + request
    return {
        "mode": "quasi_streaming",
        "stt_tail_seconds": max(0.0, worker_free_at - duration),
        "total_request_seconds": total_request,
        "request_count": len(plans),
        "text": committed.strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env")
    parser.add_argument("--manifest", default="test_audio_long/manifest.json")
    parser.add_argument("--output", default="long_recording_results.jsonl")
    parser.add_argument("--chunk-seconds", type=float, default=30.0)
    parser.add_argument("--overlap-seconds", type=float, default=5.0)
    args = parser.parse_args()
    config = load_config(args.env)
    manifest_path = Path(args.manifest)
    records = []
    for case in json.loads(manifest_path.read_text(encoding="utf-8"))["cases"]:
        path = manifest_path.parent / case["file"]
        for runner in (lambda: run_batch(path, config), lambda: run_quasi(path, config, args.chunk_seconds, args.overlap_seconds)):
            try:
                record = {"case": case["name"], "duration_seconds": case["duration_seconds"], **runner()}
            except Exception as exc:
                record = {"case": case["name"], "duration_seconds": case["duration_seconds"], "error": f"{type(exc).__name__}: {exc}"}
            print(json.dumps(record, ensure_ascii=False), flush=True)
            records.append(record)
    Path(args.output).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
