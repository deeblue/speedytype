from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import win32clipboard
import win32con
from pywinauto import Desktop

from speedytype.clipboard import paste_text_preserving_clipboard


ORIGINAL_SNIPPET = "def handle_request(req):\n    return req.user.token  # pre-existing clipboard content"
POLISHED_TEXT = "SpeedyType clipboard restore test 語音輸入完成內容 BIOS TPE 團隊"


def set_clipboard_text(text: str) -> None:
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
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


def log(name: str, delay: float, status: str, detail: str) -> None:
    print(f"RESTORE_TEST target={name} delay={delay:.2f} status={status} - {detail}", flush=True)


def notepad_case(delay: float, settle_seconds: float) -> None:
    tmp_file = Path(tempfile.gettempdir()) / f"speedytype_restore_{int(time.time() * 1000)}.txt"
    tmp_file.write_text("", encoding="utf-8")
    proc = subprocess.Popen(["notepad.exe", str(tmp_file)])
    window = None
    try:
        window = Desktop(backend="uia").window(title_re=f".*{tmp_file.name}.*")
        window.wait("visible", timeout=10)
        window.set_focus()
        time.sleep(0.5)

        set_clipboard_text(ORIGINAL_SNIPPET)
        result = paste_text_preserving_clipboard(
            POLISHED_TEXT, restore_delay_seconds=delay, background=True
        )
        if not result.ok:
            log("notepad", delay, "FAIL", f"paste itself failed: {result.message}")
            return

        time.sleep(0.6)
        pasted_content = ""
        for control in window.descendants():
            if control.friendly_class_name() in {"Edit", "Document"}:
                try:
                    pasted_content = control.window_text() or control.get_value()
                except Exception:
                    pasted_content = control.window_text()
                if POLISHED_TEXT in pasted_content or ORIGINAL_SNIPPET in pasted_content:
                    break

        time.sleep(settle_seconds)
        clipboard_after = get_clipboard_text()

        pasted_correct = POLISHED_TEXT in pasted_content
        restored_correct = clipboard_after == ORIGINAL_SNIPPET
        status = "PASS" if pasted_correct and restored_correct else "FAIL"
        log(
            "notepad",
            delay,
            status,
            f"pasted_correct={pasted_correct} restored_correct={restored_correct} "
            f"pasted_content={pasted_content!r} clipboard_after={clipboard_after!r}",
        )
    finally:
        try:
            if window is not None:
                window.close()
        except Exception:
            pass
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            tmp_file.unlink()
        except Exception:
            pass


def browser_exe() -> str | None:
    candidates = [
        shutil.which("msedge"),
        shutil.which("chrome"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def browser_case(delay: float, settle_seconds: float, tmp: Path) -> None:
    exe = browser_exe()
    if not exe:
        log("browser_textarea", delay, "NOT_TESTED", "No Edge/Chrome executable found.")
        return
    token = f"SpeedyTypeRestoreTarget{int(time.time() * 1000)}"
    html = tmp / f"restore_target_{int(time.time() * 1000)}.html"
    html.write_text(
        textwrap.dedent(
            f"""
            <!doctype html>
            <html><head><meta charset="utf-8"><title>{token}:PASTE:</title></head>
            <body>
            <textarea id="t" autofocus style="width:600px;height:240px"></textarea>
            <script>
            const t = document.getElementById('t');
            t.focus();
            setInterval(() => {{ document.title = '{token}:PASTE:' + t.value; }}, 100);
            </script>
            </body></html>
            """
        ),
        encoding="utf-8",
    )
    proc = subprocess.Popen([exe, "--new-window", str(html)])
    try:
        time.sleep(3.0)
        desktop = Desktop(backend="uia")
        window = desktop.window(title_re=f"{token}:PASTE:.*")
        window.wait("visible", timeout=15)
        window.set_focus()
        rect = window.rectangle()
        window.click_input(coords=(rect.left + 120, rect.top + 180))
        time.sleep(0.5)

        set_clipboard_text(ORIGINAL_SNIPPET)
        result = paste_text_preserving_clipboard(
            POLISHED_TEXT, restore_delay_seconds=delay, background=True
        )
        if not result.ok:
            log("browser_textarea", delay, "FAIL", f"paste itself failed: {result.message}")
            return

        time.sleep(0.8)
        title = window.window_text()

        time.sleep(settle_seconds)
        clipboard_after = get_clipboard_text()

        pasted_correct = POLISHED_TEXT in title
        restored_correct = clipboard_after == ORIGINAL_SNIPPET
        status = "PASS" if pasted_correct and restored_correct else "FAIL"
        log(
            "browser_textarea",
            delay,
            status,
            f"pasted_correct={pasted_correct} restored_correct={restored_correct} "
            f"title={title!r} clipboard_after={clipboard_after!r}",
        )
    finally:
        try:
            proc.terminate()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delays", type=float, nargs="+", default=[0.15, 0.3, 0.6])
    parser.add_argument("--settle-seconds", type=float, default=1.0, help="extra wait after target read before checking clipboard restore")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        for delay in args.delays:
            notepad_case(delay, args.settle_seconds)
            browser_case(delay, args.settle_seconds, tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
