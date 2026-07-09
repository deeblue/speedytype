from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import textwrap
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pywinauto import Desktop

from speedytype.clipboard import paste_text
from speedytype.console import safe_print
from speedytype.config import load_config
from speedytype.quasi_streaming import run_baseline_transcription, simulate_quasi_streaming_transcription


def quality_flags(name: str, output: str) -> dict[str, object]:
    filler_ok = all(f not in output for f in ["呃", "那個", "就是說"])
    if name == "short":
        correction_ok = all(f not in output for f in ["啊不對", "不對", "下週一"]) and "下週三" in output
        required_terms = ["TPE 團隊", "BIOS"]
    elif name == "medium":
        correction_ok = all(f not in output for f in ["啊不對", "不對", "下週一"]) and "下週三" in output
        required_terms = ["Firmware", "NPI", "QA", "BJ 團隊"]
    else:
        correction_ok = all(f not in output for f in ["啊不對", "不對", "下週一", "BIOS測試版", "BIOS 測試版"]) and "下週三" in output and "Firmware" in output
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
    }


def start_target(tmp: Path, hold_seconds: int) -> tuple[subprocess.Popen, Path]:
    output = tmp / "streaming_benchmark_result.txt"
    app_script = tmp / "streaming_target.py"
    app_script.write_text(
        textwrap.dedent(
            f"""
            import pathlib
            import tkinter as tk

            root = tk.Tk()
            root.title("SpeedyTypeStreamingBenchmarkTarget")
            text = tk.Text(root, width=120, height=30)
            text.pack()
            text.focus_set()

            def save_and_close():
                pathlib.Path(r"{output}").write_text(text.get("1.0", "end-1c"), encoding="utf-8")
                root.destroy()

            root.after({hold_seconds * 1000}, save_and_close)
            root.mainloop()
            """
        ),
        encoding="utf-8",
    )
    proc = subprocess.Popen([sys.executable, str(app_script)])
    window = Desktop(backend="uia").window(title="SpeedyTypeStreamingBenchmarkTarget")
    window.wait("visible", timeout=10)
    window.set_focus()
    return proc, output


def focus_target() -> float:
    started = time.perf_counter()
    window = Desktop(backend="uia").window(title="SpeedyTypeStreamingBenchmarkTarget")
    window.wait("visible", timeout=10)
    window.set_focus()
    time.sleep(0.2)
    return time.perf_counter() - started


def paste_after_focus(text: str) -> tuple[float, object]:
    started = time.perf_counter()
    paste = paste_text(text + "\n")
    return time.perf_counter() - started, paste


def summarize(label: str, values: list[float]) -> None:
    safe_print(f"{label} avg={statistics.mean(values):.6f} min={min(values):.6f} max={max(values):.6f}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env")
    parser.add_argument("--audio-dir", default="test_audio")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--chunk-seconds", type=float, default=3.0)
    parser.add_argument("--overlap-seconds", type=float, default=0.75)
    parser.add_argument("--target-hold-seconds", type=int, default=300)
    parser.add_argument("--output-jsonl", default="phase3_quasi_streaming_results.jsonl")
    args = parser.parse_args()

    config = load_config(args.env)
    cases = [
        ("short", Path(args.audio_dir) / "short_16k.wav"),
        ("medium", Path(args.audio_dir) / "medium_16k.wav"),
        ("long", Path(args.audio_dir) / "long_16k.wav"),
    ]
    for _, path in cases:
        if not path.exists():
            raise FileNotFoundError(path)

    records = []
    output_path = Path(args.output_jsonl)
    with tempfile.TemporaryDirectory() as tmp_dir:
        proc, _ = start_target(Path(tmp_dir), args.target_hold_seconds)
        try:
            for mode in ("baseline", "quasi_streaming"):
                for index in range(args.runs):
                    case_name, audio_path = cases[index % len(cases)]
                    focus_seconds = focus_target()
                    if mode == "baseline":
                        raw, stt_wall, llm_wall, llm_result = run_baseline_transcription(audio_path, config)
                        paste_wall, paste_result = paste_after_focus(llm_result.text)
                        total_tail = stt_wall + llm_wall + focus_seconds + paste_wall
                        record = {
                            "mode": mode,
                            "case": case_name,
                            "audio_path": str(audio_path),
                            "raw_transcript": raw,
                            "polished_text": llm_result.text,
                            "stt_tail_seconds": stt_wall,
                            "llm_wall_seconds": llm_wall,
                            "focus_window_seconds": focus_seconds,
                            "paste_wall_seconds": paste_wall,
                            "total_tail_seconds": total_tail,
                            "quality": quality_flags(case_name, llm_result.text),
                            "paste_ok": paste_result.ok,
                        }
                    else:
                        streaming = simulate_quasi_streaming_transcription(
                            audio_path,
                            config,
                            chunk_seconds=args.chunk_seconds,
                            overlap_seconds=args.overlap_seconds,
                        )
                        paste_wall, paste_result = paste_after_focus(streaming.llm_result.text)
                        total_tail = streaming.stt_tail_seconds + streaming.llm_wall_seconds + focus_seconds + paste_wall
                        record = {
                            "mode": mode,
                            "case": case_name,
                            "audio_path": str(audio_path),
                            "raw_transcript": streaming.merged_transcript,
                            "polished_text": streaming.llm_result.text,
                            "stt_tail_seconds": streaming.stt_tail_seconds,
                            "llm_wall_seconds": streaming.llm_wall_seconds,
                            "focus_window_seconds": focus_seconds,
                            "paste_wall_seconds": paste_wall,
                            "total_tail_seconds": total_tail,
                            "total_whisper_request_seconds": streaming.total_whisper_request_seconds,
                            "chunk_count": len(streaming.chunk_results),
                            "chunks": [
                                {
                                    "index": chunk.plan.index,
                                    "start_seconds": chunk.plan.start_seconds,
                                    "end_seconds": chunk.plan.end_seconds,
                                    "commit_until_seconds": chunk.plan.commit_until_seconds,
                                    "request_seconds": chunk.request_seconds,
                                    "started_at_seconds": chunk.started_at_seconds,
                                    "finished_at_seconds": chunk.finished_at_seconds,
                                    "text": chunk.text,
                                }
                                for chunk in streaming.chunk_results
                            ],
                            "quality": quality_flags(case_name, streaming.llm_result.text),
                            "paste_ok": paste_result.ok,
                        }
                    safe_print(json.dumps(record, ensure_ascii=False), flush=True)
                    records.append(record)
        finally:
            try:
                proc.terminate()
            except Exception:
                pass

    output_path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n", encoding="utf-8")
    safe_print(f"WROTE {output_path}")
    for mode in ("baseline", "quasi_streaming"):
        subset = [record for record in records if record["mode"] == mode]
        tails = [float(record["total_tail_seconds"]) for record in subset]
        stt = [float(record["stt_tail_seconds"]) for record in subset]
        ok = sum(1 for record in subset if record["quality"]["overall_ok"])
        safe_print(f"SUMMARY {mode}")
        safe_print(f"runs={len(subset)} quality_pass={ok}/{len(subset)}")
        summarize("total_tail_seconds", tails)
        summarize("stt_tail_seconds", stt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
