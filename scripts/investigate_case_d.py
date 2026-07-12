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


def run_variant(name: str, config, start: float, end: float) -> None:
    chunk = slice_wav(PATH, start, end)
    try:
        text = transcribe_audio(chunk, config)
    finally:
        chunk.unlink(missing_ok=True)
    correct = TARGET_PHRASE_CORRECT in text.replace(" ", "").replace(",", "").replace("、", "")
    corrupt = TARGET_PHRASE_CORRUPT in text
    with open("case_d_investigation_results.txt", "a", encoding="utf-8") as out:
        out.write(f"=== {name} (window {start:.2f}-{end:.2f}s, {end-start:.2f}s long) ===\n")
        out.write(f"contains_correct_phrase={correct} contains_corrupt_1trillion={corrupt}\n")
        out.write(f"TEXT: {text}\n\n")
    print(f"{name}: correct={correct} corrupt={corrupt}")


def main() -> int:
    config = load_config(".env")
    Path("case_d_investigation_results.txt").write_text("", encoding="utf-8")

    # A: baseline, exact production chunk boundaries (reproduces the known bug)
    run_variant("A_baseline_exact_chunk", config, 50.88, 75.24)
    # B: more leading context (10s earlier start), same end
    run_variant("B_extra_leading_context", config, 40.88, 75.24)
    # C: more trailing context (10s later end), same start
    run_variant("C_extra_trailing_context", config, 50.88, 85.24)
    # D: much larger window both directions
    run_variant("D_wide_both_directions", config, 30.0, 100.0)
    # E: full context from the start of the recording up through this point
    run_variant("E_full_context_from_start", config, 0.0, 100.0)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
