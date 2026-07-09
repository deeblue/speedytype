from __future__ import annotations

import sys


def safe_print(*parts: object, sep: str = " ", end: str = "\n", flush: bool = False) -> None:
    text = sep.join(str(part) for part in parts) + end
    stream = sys.stdout
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        stream.buffer.write(text.encode(encoding, errors="replace"))
    if flush:
        stream.flush()
