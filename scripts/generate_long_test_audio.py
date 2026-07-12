from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import re
import subprocess
import tempfile

import edge_tts
import imageio_ffmpeg


def source_chunks(path: Path, max_chars: int) -> list[str]:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"[`#>*_\[\]()]", " ", text)
    paragraphs = [re.sub(r"\s+", " ", part).strip() for part in re.split(r"\n\s*\n", text)]
    selected = []
    used = 0
    for part in (part for part in paragraphs if part):
        if used + len(part) > max_chars:
            break
        selected.append(part)
        used += len(part)
    return selected


async def generate(chunks: list[str], output: Path, voice: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for index, text in enumerate(chunks):
            part = Path(tmp) / f"part_{index:03d}.mp3"
            for attempt in range(4):
                try:
                    await edge_tts.Communicate(text, voice, rate="-10%").save(str(part))
                    break
                except edge_tts.exceptions.NoAudioReceived:
                    if attempt == 3:
                        raise RuntimeError(f"TTS returned no audio for paragraph {index + 1}")
                    await asyncio.sleep(2 * (attempt + 1))
            parts.append(part)
            await asyncio.sleep(0.5)
        concat_file = Path(tmp) / "concat.txt"
        concat_file.write_text("".join(f"file '{part.as_posix()}'\n" for part in parts), encoding="utf-8")
        subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-filter:a", "atempo=1.02", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(output)],
            check=True,
            capture_output=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="test_audio_long/continuous_tts_script.txt")
    parser.add_argument("--output", default="test_audio_long/continuous_tts_295s.wav")
    parser.add_argument("--max-chars", type=int, default=10000)
    parser.add_argument("--voice", default="zh-TW-YunJheNeural")
    args = parser.parse_args()
    asyncio.run(generate(source_chunks(Path(args.source), args.max_chars), Path(args.output), args.voice))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
