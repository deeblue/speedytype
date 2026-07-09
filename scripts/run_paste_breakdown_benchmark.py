from __future__ import annotations

import argparse
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


TEST_TEXT = "SpeedyType paste breakdown test BIOS API TPE 團隊"


def start_target(tmp: Path, hold_seconds: int) -> tuple[subprocess.Popen, Path]:
    output = tmp / "paste_breakdown_result.txt"
    app_script = tmp / "paste_breakdown_target.py"
    app_script.write_text(
        textwrap.dedent(
            f"""
            import pathlib
            import tkinter as tk

            root = tk.Tk()
            root.title("SpeedyTypePasteBreakdownTarget")
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
    window = Desktop(backend="uia").window(title="SpeedyTypePasteBreakdownTarget")
    window.wait("visible", timeout=10)
    window.set_focus()
    return proc, output


def focus_target() -> None:
    window = Desktop(backend="uia").window(title="SpeedyTypePasteBreakdownTarget")
    window.wait("visible", timeout=10)
    window.set_focus()
    time.sleep(0.2)


def summarize(name: str, values: list[float]) -> None:
    print(
        f"{name}: avg={statistics.mean(values):.6f} min={min(values):.6f} max={max(values):.6f}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--target-hold-seconds", type=int, default=120)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp_dir:
        proc, output = start_target(Path(tmp_dir), args.target_hold_seconds)
        results = []
        try:
            for index in range(args.runs):
                focus_target()
                started = time.perf_counter()
                result = paste_text(TEST_TEXT + f" run={index + 1}\n")
                wall_seconds = time.perf_counter() - started
                results.append((result, wall_seconds))
                print(
                    f"PASTE_BREAKDOWN_RUN {index + 1}/{args.runs} "
                    f"ok={result.ok} wall={wall_seconds:.6f} clipboard_write={result.clipboard_write_seconds:.6f} "
                    f"pre_wait={result.pre_send_wait_seconds:.6f} key_send={result.key_send_seconds:.6f} "
                    f"post_wait={result.post_send_wait_seconds:.6f} verify={result.verification_seconds:.6f} "
                    f"message={result.message!r}",
                    flush=True,
                )
                time.sleep(0.3)
        finally:
            try:
                proc.terminate()
            except Exception:
                pass

        clip = [item[0].clipboard_write_seconds for item in results]
        pre = [item[0].pre_send_wait_seconds for item in results]
        key = [item[0].key_send_seconds for item in results]
        post = [item[0].post_send_wait_seconds for item in results]
        verify = [item[0].verification_seconds for item in results]
        wall = [item[1] for item in results]
        print("PASTE_BREAKDOWN_SUMMARY", flush=True)
        print(f"runs={len(results)}", flush=True)
        print(f"successes={sum(1 for item, _ in results if item.ok)}", flush=True)
        summarize("wall_seconds", wall)
        summarize("clipboard_write_seconds", clip)
        summarize("pre_send_wait_seconds", pre)
        summarize("key_send_seconds", key)
        summarize("post_send_wait_seconds", post)
        summarize("verification_seconds", verify)
        if output.exists():
            observed = output.read_text(encoding="utf-8")
            print(f"target_observed_chars={len(observed)}", flush=True)
            print(f"target_contains_last={TEST_TEXT in observed}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
