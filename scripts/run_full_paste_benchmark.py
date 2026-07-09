from __future__ import annotations

import argparse
import csv
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import textwrap
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pywinauto import Desktop

from speedytype.api import transcribe_audio
from speedytype.clipboard import paste_text
from speedytype.console import safe_print
from speedytype.config import load_config
from speedytype.latency import LatencyRecord, append_latency_record
from speedytype.llm import call_llm_polisher, retry_api_call
from speedytype.pipeline import wav_duration_seconds


def start_target(tmp: Path, hold_seconds: int) -> tuple[subprocess.Popen, Path]:
    output = tmp / "full_paste_benchmark_result.txt"
    app_script = tmp / "full_paste_target.py"
    app_script.write_text(
        textwrap.dedent(
            f"""
            import pathlib
            import tkinter as tk

            root = tk.Tk()
            root.title("SpeedyTypeFullPasteBenchmarkTarget")
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
    window = Desktop(backend="uia").window(title="SpeedyTypeFullPasteBenchmarkTarget")
    window.wait("visible", timeout=10)
    window.set_focus()
    return proc, output


def focus_target() -> float:
    started = time.perf_counter()
    window = Desktop(backend="uia").window(title="SpeedyTypeFullPasteBenchmarkTarget")
    window.wait("visible", timeout=10)
    window.set_focus()
    time.sleep(0.2)
    return time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env")
    parser.add_argument("--audio-dir", default="test_audio")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--target-hold-seconds", type=int, default=240)
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

    with tempfile.TemporaryDirectory() as tmp_dir:
        proc, output = start_target(Path(tmp_dir), args.target_hold_seconds)
        results: list[LatencyRecord] = []
        paste_successes = 0
        pasted_texts: list[str] = []
        try:
            for index in range(args.runs):
                path = audio_paths[index % len(audio_paths)]
                recording_seconds = wav_duration_seconds(path)
                safe_print(f"FULL_BENCH_RUN {index + 1}/{args.runs} audio={path} recording_seconds={recording_seconds:.3f}", flush=True)

                tail_start = time.perf_counter()
                whisper_start = time.perf_counter()
                raw, _, _, _ = retry_api_call("Whisper", lambda: transcribe_audio(path, config))
                whisper_seconds = time.perf_counter() - whisper_start

                if raw.strip():
                    llm_result = call_llm_polisher(raw, config)
                    polished = llm_result.text
                    gemini_seconds = llm_result.llm_call_seconds
                    retry_wait_seconds = llm_result.retry_wait_seconds
                    retry_count = llm_result.retry_count
                    llm_provider = llm_result.provider
                    llm_model = llm_result.model
                else:
                    polished = ""
                    gemini_seconds = 0.0
                    retry_wait_seconds = 0.0
                    retry_count = 0
                    llm_provider = config.llm_provider
                    llm_model = config.llm_model

                paste_start = time.perf_counter()
                paste_result = None
                focus_window_seconds = 0.0
                if polished.strip():
                    focus_window_seconds = focus_target()
                    paste_result = paste_text(polished + "\n")
                    paste_ok, paste_message = paste_result.ok, paste_result.message
                else:
                    paste_ok, paste_message = False, "Whisper returned empty text; skipped paste."
                paste_seconds = time.perf_counter() - paste_start
                total_tail = time.perf_counter() - tail_start

                record = LatencyRecord.create(
                    recording_seconds=recording_seconds,
                    whisper_seconds=whisper_seconds,
                    gemini_seconds=gemini_seconds,
                    paste_seconds=paste_seconds,
                    total_tail_latency_seconds=total_tail,
                    run_label="phase2_full_benchmark",
                    llm_provider=llm_provider,
                    llm_model=llm_model,
                    llm_call_seconds=gemini_seconds,
                    retry_wait_seconds=retry_wait_seconds,
                    focus_window_seconds=focus_window_seconds,
                    clipboard_write_seconds=0.0 if paste_result is None else paste_result.clipboard_write_seconds,
                    pre_paste_wait_seconds=0.0 if paste_result is None else paste_result.pre_send_wait_seconds,
                    key_send_seconds=0.0 if paste_result is None else paste_result.key_send_seconds,
                    post_paste_wait_seconds=0.0 if paste_result is None else paste_result.post_send_wait_seconds,
                    paste_verification_seconds=0.0 if paste_result is None else paste_result.verification_seconds,
                )
                append_latency_record(config.latency_log_path, record)
                results.append(record)
                if paste_ok:
                    paste_successes += 1
                pasted_texts.append(polished)

                safe_print(
                    f"FULL_BENCH_RESULT {index + 1}: "
                    f"whisper={whisper_seconds:.6f} gemini={gemini_seconds:.6f} "
                    f"paste={paste_seconds:.6f} total_tail={total_tail:.6f} "
                    f"focus_window={focus_window_seconds:.6f} "
                    f"clipboard_write={0.0 if paste_result is None else paste_result.clipboard_write_seconds:.6f} "
                    f"pre_paste_wait={0.0 if paste_result is None else paste_result.pre_send_wait_seconds:.6f} "
                    f"key_send={0.0 if paste_result is None else paste_result.key_send_seconds:.6f} "
                    f"post_paste_wait={0.0 if paste_result is None else paste_result.post_send_wait_seconds:.6f} "
                    f"paste_verify={0.0 if paste_result is None else paste_result.verification_seconds:.6f} "
                    f"retry_wait={retry_wait_seconds:.6f} retry_count={retry_count} llm_provider={llm_provider} llm_model={llm_model} "
                    f"paste_ok={paste_ok} paste_message={paste_message!r} "
                    f"raw={raw!r} polished={polished!r}",
                    flush=True,
                )
        finally:
            try:
                proc.terminate()
            except Exception:
                pass

        totals = [item.total_tail_latency_seconds for item in results]
        whispers = [item.whisper_seconds for item in results]
        geminis = [item.gemini_seconds for item in results]
        pastes = [item.paste_seconds for item in results]
        total_sum = sum(totals)
        safe_print("FULL_BENCH_SUMMARY")
        safe_print(f"runs={len(results)}")
        safe_print(f"paste_successes={paste_successes}")
        safe_print(f"avg_total_tail={statistics.mean(totals):.6f}")
        safe_print(f"min_total_tail={min(totals):.6f}")
        safe_print(f"max_total_tail={max(totals):.6f}")
        safe_print(f"avg_whisper={statistics.mean(whispers):.6f}")
        safe_print(f"avg_gemini={statistics.mean(geminis):.6f}")
        safe_print(f"avg_paste={statistics.mean(pastes):.6f}")
        safe_print(f"share_whisper={(sum(whispers) / total_sum * 100.0):.2f}%")
        safe_print(f"share_gemini={(sum(geminis) / total_sum * 100.0):.2f}%")
        safe_print(f"share_paste={(sum(pastes) / total_sum * 100.0):.2f}%")
        with config.latency_log_path.open("r", encoding="utf-8", newline="") as handle:
            row_count = sum(1 for _ in csv.DictReader(handle))
        safe_print(f"latency_log_rows={row_count}")
        if output.exists():
            observed = output.read_text(encoding="utf-8")
            safe_print(f"target_observed_chars={len(observed)}")
            safe_print(f"target_contains_last={bool(pasted_texts and pasted_texts[-1] in observed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
