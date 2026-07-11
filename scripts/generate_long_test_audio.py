from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import re
import subprocess
import tempfile

import edge_tts
import imageio_ffmpeg


def source_text(path: Path, max_chars: int) -> str:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"[`#>*_\[\]()]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


async def generate(text: str, output: Path, voice: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        mp3 = Path(tmp) / "long.mp3"
        await edge_tts.Communicate(text, voice, rate="-10%").save(str(mp3))
        subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", str(mp3), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(output)],
            check=True,
            capture_output=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="CROSS_PLATFORM_PLAN.md")
    parser.add_argument("--output", default="test_audio_long/long_tts_4m.wav")
    parser.add_argument("--max-chars", type=int, default=1350)
    parser.add_argument("--voice", default="zh-TW-YunJheNeural")
    args = parser.parse_args()
    asyncio.run(generate(source_text(Path(args.source), args.max_chars), Path(args.output), args.voice))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
