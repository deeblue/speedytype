from __future__ import annotations

import sys


def safe_print(*parts: object, sep: str = " ", end: str = "\n", flush: bool = False) -> None:
    text = sep.join(str(part) for part in parts) + end
    stream = sys.stdout
    if stream is None:
        # No console attached (e.g. running under pythonw.exe with no stdio
        # redirection, as the daemon does when launched from the tray
        # "restart" action or the Startup-folder autostart script). Printing
        # is purely diagnostic here, so drop it rather than crash the process.
        return
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        stream.buffer.write(text.encode(encoding, errors="replace"))
    except (AttributeError, ValueError, OSError):
        return
    if flush:
        try:
            stream.flush()
        except (AttributeError, ValueError, OSError):
            pass
