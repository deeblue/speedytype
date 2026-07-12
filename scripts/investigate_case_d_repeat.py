from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from speedytype.api import transcribe_audio
from speedytype.config import load_config
from speedytype.quasi_streaming import slice_wav

PATH = Path("test_audio_long/continuous_tts_295s.wav")
TARGET_PHRASE_CORRECT = "海邊步道依照距離重新排序"
TARGET_PHRASE_CORRUPT = "一兆"
REPEATS = 6


def main() -> int:
    config = load_config(".env")
    with open("case_d_investigation_results.txt", "a", encoding="utf-8") as out:
        out.write(f"\n=== Repeated baseline trials (exact chunk-3 boundaries 50.88-75.24s), {REPEATS}x ===\n")

    correct_count = 0
    corrupt_count = 0
    other_count = 0
    for i in range(REPEATS):
        chunk = slice_wav(PATH, 50.88, 75.24)
        try:
            text = transcribe_audio(chunk, config)
        finally:
            chunk.unlink(missing_ok=True)
        cleaned = text.replace(" ", "").replace(",", "").replace("、", "")
        correct = TARGET_PHRASE_CORRECT in cleaned
        corrupt = TARGET_PHRASE_CORRUPT in text
        if correct:
            correct_count += 1
        elif corrupt:
            corrupt_count += 1
        else:
            other_count += 1
        with open("case_d_investigation_results.txt", "a", encoding="utf-8") as out:
            out.write(f"trial {i+1}/{REPEATS}: correct={correct} corrupt_1trillion={corrupt}\n")
            out.write(f"  TEXT: {text}\n")
        print(f"trial {i+1}/{REPEATS}: correct={correct} corrupt={corrupt}")

    with open("case_d_investigation_results.txt", "a", encoding="utf-8") as out:
        out.write(f"\nSUMMARY: correct={correct_count}/{REPEATS} corrupt_1trillion={corrupt_count}/{REPEATS} other={other_count}/{REPEATS}\n")
    print(f"SUMMARY: correct={correct_count}/{REPEATS} corrupt={corrupt_count}/{REPEATS} other={other_count}/{REPEATS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
