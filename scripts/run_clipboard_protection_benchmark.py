from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import win32clipboard
import win32con
from pywinauto import Desktop

from speedytype.config import load_config
from speedytype.pipeline import process_wav


ORIGINAL_SNIPPETS = [
    "def handle_request(req):\n    return req.user.token  # snippet A",
    "https://example.com/some/deep/link?id=12345&token=abcxyz  # snippet B (a link)",
    "SELECT * FROM users WHERE id = 42;  -- snippet C",
    "git rebase -i HEAD~5  # snippet D",
    "const total = items.reduce((a, b) => a + b.price, 0);  // snippet E",
]


def set_clipboard_text(text: str) -> None:
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


def set_clipboard_image_placeholder() -> None:
    """Put a non-text format on the clipboard: a minimal 1x1 DIB bitmap."""
    # BITMAPINFOHEADER (40 bytes) for a 1x1 24bpp bitmap + 4 bytes pixel data (padded to 4-byte row).
    header = (
        (40).to_bytes(4, "little")       # biSize
        + (1).to_bytes(4, "little")       # biWidth
        + (1).to_bytes(4, "little")       # biHeight
        + (1).to_bytes(2, "little")       # biPlanes
        + (24).to_bytes(2, "little")      # biBitCount
        + (0).to_bytes(4, "little")       # biCompression
        + (0).to_bytes(4, "little")       # biSizeImage
        + (0).to_bytes(4, "little", signed=True)  # biXPelsPerMeter
        + (0).to_bytes(4, "little", signed=True)  # biYPelsPerMeter
        + (0).to_bytes(4, "little")       # biClrUsed
        + (0).to_bytes(4, "little")       # biClrImportant
    )
    pixel_data = b"\x00\x00\xff\x00"  # one BGR pixel + row padding
    dib = header + pixel_data
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_DIB, dib)
    finally:
        win32clipboard.CloseClipboard()


def get_clipboard_text() -> str | None:
    win32clipboard.OpenClipboard()
    try:
        try:
            return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        except Exception:
            return None
    finally:
        win32clipboard.CloseClipboard()


def clipboard_has_format(fmt: int) -> bool:
    win32clipboard.OpenClipboard()
    try:
        return bool(win32clipboard.IsClipboardFormatAvailable(fmt))
    finally:
        win32clipboard.CloseClipboard()


def start_notepad() -> tuple[subprocess.Popen, Path, object]:
    target_file = Path(tempfile.gettempdir()) / f"speedytype_clip_protect_{int(time.time() * 1000)}.txt"
    target_file.write_text("", encoding="utf-8")
    proc = subprocess.Popen(["notepad.exe", str(target_file)])
    window = Desktop(backend="uia").window(title_re=f".*{target_file.name}.*")
    window.wait("visible", timeout=10)
    window.set_focus()
    time.sleep(0.5)
    return proc, target_file, window


def read_notepad_text(window) -> str:
    try:
        descendants = window.descendants()
    except Exception:
        return ""
    for control in descendants:
        if control.friendly_class_name() in {"Edit", "Document"}:
            try:
                return control.window_text() or control.get_value()
            except Exception:
                return control.window_text()
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env")
    parser.add_argument("--audio", default="test_audio/short_16k.wav")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--settle-seconds", type=float, default=1.0)
    args = parser.parse_args()

    config = load_config(args.env)
    audio_path = Path(args.audio)
    if not audio_path.exists():
        raise FileNotFoundError(audio_path)

    proc, target_file, window = start_notepad()
    results = []
    try:
        for index in range(args.runs):
            snippet = ORIGINAL_SNIPPETS[index % len(ORIGINAL_SNIPPETS)]
            set_clipboard_text(snippet)
            try:
                window.set_focus()
            except Exception:
                pass
            time.sleep(0.2)

            pipeline_result = process_wav(audio_path, config, do_paste=True, run_label="phase5_clipboard_protect")

            time.sleep(args.settle_seconds)
            pasted_text = read_notepad_text(window)
            clipboard_after = get_clipboard_text()

            paste_ok = pipeline_result.paste_ok
            polished_present = bool(pipeline_result.polished_text) and pipeline_result.polished_text.strip() in pasted_text
            restored_correct = clipboard_after == snippet
            status = "PASS" if paste_ok and polished_present and restored_correct else "FAIL"
            print(
                f"RUN {index + 1}/{args.runs} status={status} paste_ok={paste_ok} "
                f"polished_present={polished_present} restored_correct={restored_correct} "
                f"snippet={snippet!r} clipboard_after={clipboard_after!r} polished={pipeline_result.polished_text!r}",
                flush=True,
            )
            results.append(status)

        # Non-text clipboard edge case: original clipboard content is an image (CF_DIB), not text.
        set_clipboard_image_placeholder()
        try:
            window.set_focus()
        except Exception:
            pass
        time.sleep(0.2)
        pipeline_result = process_wav(audio_path, config, do_paste=True, run_label="phase5_clipboard_protect_image_case")
        time.sleep(args.settle_seconds)
        pasted_text = read_notepad_text(window)
        image_restored = clipboard_has_format(win32con.CF_DIB)
        paste_ok = pipeline_result.paste_ok
        polished_present = bool(pipeline_result.polished_text) and pipeline_result.polished_text.strip() in pasted_text
        status = "PASS" if paste_ok and polished_present and image_restored else "FAIL"
        print(
            f"IMAGE_EDGE_CASE status={status} paste_ok={paste_ok} polished_present={polished_present} "
            f"cf_dib_restored={image_restored} polished={pipeline_result.polished_text!r}",
            flush=True,
        )
        results.append(status)
    finally:
        try:
            window.close()
        except Exception:
            pass
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            target_file.unlink()
        except Exception:
            pass

    print(f"SUMMARY total={len(results)} passed={results.count('PASS')} failed={results.count('FAIL')}")
    return 0 if results.count("FAIL") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
