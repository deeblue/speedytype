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

from pywinauto import Application, Desktop

from speedytype.clipboard import paste_text


TEST_TEXT = "SpeedyType paste 測試 BIOS TPE 團隊"


def result(name: str, status: str, detail: str) -> None:
    print(f"PASTE_TEST {name}: {status} - {detail}")


def run_notepad_check() -> None:
    tmp_file = Path(tempfile.gettempdir()) / f"speedytype_notepad_{int(time.time() * 1000)}.txt"
    tmp_file.write_text("", encoding="utf-8")
    proc = subprocess.Popen(["notepad.exe", str(tmp_file)])
    try:
        window = Desktop(backend="uia").window(title_re=f".*{tmp_file.name}.*")
        window.wait("visible", timeout=10)
        window.set_focus()
        time.sleep(0.5)
        paste = paste_text(TEST_TEXT)
        ok, message = paste.ok, paste.message
        time.sleep(1.0)
        content = ""
        for control in window.descendants():
            if control.friendly_class_name() in {"Edit", "Document"}:
                try:
                    content = control.window_text() or control.get_value()
                except Exception:
                    content = control.window_text()
                if TEST_TEXT in content:
                    break
        status = "PASS" if ok and TEST_TEXT in content else "FAIL"
        result("notepad", status, f"paste_ok={ok}; message={message}; observed_contains={TEST_TEXT in content}")
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


def run_browser_textarea_check(tmp: Path) -> None:
    exe = browser_exe()
    if not exe:
        result("browser_textarea", "NOT_TESTED", "No Edge/Chrome executable found.")
        return
    token = f"SpeedyTypeBrowserPasteTarget{int(time.time() * 1000)}"
    html = tmp / "paste_target.html"
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
        paste = paste_text(TEST_TEXT)
        ok, message = paste.ok, paste.message
        time.sleep(1.5)
        title = window.window_text()
        status = "PASS" if ok and TEST_TEXT in title else "FAIL"
        result("browser_textarea", status, f"paste_ok={ok}; message={message}; title_contains={TEST_TEXT in title}; title={title!r}")
    finally:
        try:
            proc.terminate()
        except Exception:
            pass


def run_normal_tk_app_check(tmp: Path) -> None:
    output = tmp / "tk_paste_result.txt"
    app_script = tmp / "tk_target.py"
    app_script.write_text(
        textwrap.dedent(
            f"""
            import pathlib
            import tkinter as tk
            root = tk.Tk()
            root.title("SpeedyTypeNormalPasteTarget")
            text = tk.Text(root, width=80, height=10)
            text.pack()
            text.focus_set()
            root.after(3000, lambda: (pathlib.Path(r"{output}").write_text(text.get("1.0", "end-1c"), encoding="utf-8"), root.destroy()))
            root.mainloop()
            """
        ),
        encoding="utf-8",
    )
    proc = subprocess.Popen([sys.executable, str(app_script)])
    try:
        time.sleep(1.0)
        window = Desktop(backend="uia").window(title="SpeedyTypeNormalPasteTarget")
        window.wait("visible", timeout=10)
        window.set_focus()
        time.sleep(0.5)
        paste = paste_text(TEST_TEXT)
        ok, message = paste.ok, paste.message
        proc.wait(timeout=10)
        observed = output.read_text(encoding="utf-8") if output.exists() else ""
        status = "PASS" if ok and TEST_TEXT in observed else "FAIL"
        result("normal_app", status, f"paste_ok={ok}; message={message}; observed_contains={TEST_TEXT in observed}; observed={observed!r}")
    finally:
        if proc.poll() is None:
            proc.terminate()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        for name, test in (
            ("notepad", run_notepad_check),
            ("browser_textarea", lambda: run_browser_textarea_check(tmp)),
            ("normal_app", lambda: run_normal_tk_app_check(tmp)),
        ):
            try:
                test()
            except Exception as exc:
                result(name, "ERROR", repr(exc))
    result("admin_elevated_window", "NOT_TESTED", "Not attempted because launching an elevated target requires UAC interaction and could not be safely automated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
