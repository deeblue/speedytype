from __future__ import annotations

import argparse
import csv
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pywinauto import Desktop

from speedytype.config import load_config
from speedytype.pipeline import process_wav


def start_notepad() -> tuple[subprocess.Popen, Path]:
    target_file = Path(tempfile.gettempdir()) / f"speedytype_real_path_{int(time.time() * 1000)}.txt"
    target_file.write_text("", encoding="utf-8")
    proc = subprocess.Popen(["notepad.exe", str(target_file)])
    window = Desktop(backend="uia").window(title_re=f".*{target_file.name}.*")
    window.wait("visible", timeout=10)
    window.set_focus()
    time.sleep(0.5)
    return proc, target_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env")
    parser.add_argument("--audio-dir", default="test_audio")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--keep-notepad-open", action="store_true")
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

    proc, target_file = start_notepad()
    print(f"REAL_PATH_TARGET file={target_file}")
    print("REAL_PATH_NOTE Notepad was focused once before measurement; no per-run focus helper is used.")

    results = []
    try:
        for index in range(args.runs):
            path = audio_paths[index % len(audio_paths)]
            result = process_wav(path, config, do_paste=True, run_label="phase4_real_path")
            record = result.latency
            results.append(record)
            print(
                f"REAL_PATH_RUN {index + 1}/{args.runs} audio={path} "
                f"whisper={record.whisper_seconds:.6f} llm={record.llm_call_seconds:.6f} "
                f"paste={record.paste_seconds:.6f} total_tail={record.total_tail_latency_seconds:.6f} "
                f"focus_window={record.focus_window_seconds:.6f} paste_ok={result.paste_ok}",
                flush=True,
            )
    finally:
        if not args.keep_notepad_open:
            try:
                proc.terminate()
            except Exception:
                pass

    totals = [item.total_tail_latency_seconds for item in results]
    whispers = [item.whisper_seconds for item in results]
    llms = [item.llm_call_seconds for item in results]
    pastes = [item.paste_seconds for item in results]
    print("REAL_PATH_SUMMARY")
    print(f"runs={len(results)}")
    print(f"avg_total_tail={statistics.mean(totals):.6f}")
    print(f"min_total_tail={min(totals):.6f}")
    print(f"max_total_tail={max(totals):.6f}")
    print(f"avg_whisper={statistics.mean(whispers):.6f}")
    print(f"avg_llm={statistics.mean(llms):.6f}")
    print(f"avg_paste={statistics.mean(pastes):.6f}")
    with config.latency_log_path.open("r", encoding="utf-8", newline="") as handle:
        count = sum(1 for row in csv.DictReader(handle) if row.get("run_label") == "phase4_real_path")
    print(f"phase4_real_path_rows={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
