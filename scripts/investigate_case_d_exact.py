from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from speedytype.api import transcribe_audio_verbose
from speedytype.config import load_config
from speedytype.quasi_streaming import slice_wav, tail_prompt

PATH = Path("test_audio_long/continuous_tts_295s.wav")
TARGET_PHRASE_CORRECT = "海邊步道依照距離重新排序"
TARGET_PHRASE_CORRUPT = "一兆"

# Exact production chunk boundaries for chunks 1-3 (from plan_dynamic_chunks
# with the default ChunkingConfig against this exact audio file).
CHUNKS = [
    (1, 0.00, 25.24),
    (2, 25.04, 51.08),
    (3, 50.88, 75.24),
]


def run_one_trial(trial_index: int, config) -> tuple[bool, bool, str]:
    committed_prompt = ""
    chunk3_text = ""
    for index, start, end in CHUNKS:
        chunk = slice_wav(PATH, start, end)
        try:
            payload = transcribe_audio_verbose(chunk, config, prompt_override=tail_prompt(config, committed_prompt))
        finally:
            chunk.unlink(missing_ok=True)
        text = str(payload.get("text", "")).strip()
        if index == 3:
            chunk3_text = text
        committed_prompt = f"{committed_prompt} {text}"[-200:].strip()

    cleaned = chunk3_text.replace(" ", "").replace(",", "").replace("、", "")
    correct = TARGET_PHRASE_CORRECT in cleaned
    corrupt = TARGET_PHRASE_CORRUPT in chunk3_text
    with open("case_d_investigation_results.txt", "a", encoding="utf-8") as out:
        out.write(f"=== EXACT production replay, trial {trial_index} (verbose_json + real prompt_override chain 1->2->3) ===\n")
        out.write(f"correct={correct} corrupt_1trillion={corrupt}\n")
        out.write(f"chunk3 TEXT: {chunk3_text}\n\n")
    return correct, corrupt, chunk3_text


def main() -> int:
    config = load_config(".env")
    repeats = 4
    correct_count = 0
    corrupt_count = 0
    for i in range(repeats):
        correct, corrupt, text = run_one_trial(i + 1, config)
        print(f"trial {i+1}/{repeats}: correct={correct} corrupt={corrupt}")
        if correct:
            correct_count += 1
        if corrupt:
            corrupt_count += 1
    summary = f"EXACT REPLAY SUMMARY: correct={correct_count}/{repeats} corrupt_1trillion={corrupt_count}/{repeats}"
    with open("case_d_investigation_results.txt", "a", encoding="utf-8") as out:
        out.write(summary + "\n")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
