from __future__ import annotations

import argparse
import csv
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from speedytype.config import load_config
from speedytype.pipeline import process_wav


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env")
    parser.add_argument("--audio-dir", default="test_audio")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--no-paste", action="store_true")
    args = parser.parse_args()

    config = load_config(args.env)
    audio_paths = [
        Path(args.audio_dir) / "short_16k.wav",
        Path(args.audio_dir) / "medium_16k.wav",
        Path(args.audio_dir) / "long_16k.wav",
    ]
    for path in audio_paths:
        if not path.exists():
            raise FileNotFoundError(path)

    results = []
    for index in range(args.runs):
        path = audio_paths[index % len(audio_paths)]
        print(f"BENCH_RUN {index + 1}/{args.runs} audio={path}")
        result = process_wav(path, config, do_paste=not args.no_paste)
        results.append(result.latency)
        print(f"BENCH_RESULT {index + 1}: raw={result.raw_transcript!r} polished={result.polished_text!r} paste_ok={result.paste_ok} paste_message={result.paste_message!r}")

    totals = [item.total_tail_latency_seconds for item in results]
    whispers = [item.whisper_seconds for item in results]
    geminis = [item.gemini_seconds for item in results]
    pastes = [item.paste_seconds for item in results]

    total_sum = sum(totals)
    whisper_sum = sum(whispers)
    gemini_sum = sum(geminis)
    paste_sum = sum(pastes)
    print("BENCH_SUMMARY")
    print(f"runs={len(results)}")
    print(f"avg_total_tail={statistics.mean(totals):.6f}")
    print(f"min_total_tail={min(totals):.6f}")
    print(f"max_total_tail={max(totals):.6f}")
    print(f"avg_whisper={statistics.mean(whispers):.6f}")
    print(f"avg_gemini={statistics.mean(geminis):.6f}")
    print(f"avg_paste={statistics.mean(pastes):.6f}")
    print(f"share_whisper={(whisper_sum / total_sum * 100.0):.2f}%")
    print(f"share_gemini={(gemini_sum / total_sum * 100.0):.2f}%")
    print(f"share_paste={(paste_sum / total_sum * 100.0):.2f}%")
    print(f"latency_log={config.latency_log_path}")

    with config.latency_log_path.open("r", encoding="utf-8", newline="") as handle:
        row_count = sum(1 for _ in csv.DictReader(handle))
    print(f"latency_log_rows={row_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
