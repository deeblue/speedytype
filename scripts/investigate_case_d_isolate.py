from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from speedytype.api import transcribe_audio, transcribe_audio_verbose
from speedytype.config import load_config
from speedytype.quasi_streaming import slice_wav, tail_prompt

PATH = Path("test_audio_long/continuous_tts_295s.wav")
TARGET_PHRASE_CORRECT = "海邊步道依照距離重新排序"
TARGET_PHRASE_CORRUPT = "一兆"

CHUNKS_1_2 = [(1, 0.00, 25.24), (2, 25.04, 51.08)]
CHUNK_3 = (50.88, 75.24)


def check(text: str) -> tuple[bool, bool]:
    cleaned = text.replace(" ", "").replace(",", "").replace("、", "")
    return TARGET_PHRASE_CORRECT in cleaned, TARGET_PHRASE_CORRUPT in text


def log(name: str, correct: bool, corrupt: bool, text: str) -> None:
    with open("case_d_investigation_results.txt", "a", encoding="utf-8") as out:
        out.write(f"=== {name} ===\ncorrect={correct} corrupt={corrupt}\nTEXT: {text}\n\n")
    print(f"{name}: correct={correct} corrupt={corrupt}")


def get_real_committed_prompt(config) -> str:
    committed_prompt = ""
    for index, start, end in CHUNKS_1_2:
        chunk = slice_wav(PATH, start, end)
        try:
            payload = transcribe_audio_verbose(chunk, config, prompt_override=tail_prompt(config, committed_prompt))
        finally:
            chunk.unlink(missing_ok=True)
        text = str(payload.get("text", "")).strip()
        committed_prompt = f"{committed_prompt} {text}"[-200:].strip()
    return committed_prompt


def main() -> int:
    config = load_config(".env")
    real_prompt_override = tail_prompt(config, get_real_committed_prompt(config))
    with open("case_d_investigation_results.txt", "a", encoding="utf-8") as out:
        out.write(f"\n--- Isolation experiments ---\nCaptured real prompt_override: {real_prompt_override!r}\n\n")

    # F: chunk 3 alone, verbose_json, NO prompt_override at all
    for i in range(2):
        chunk = slice_wav(PATH, *CHUNK_3)
        try:
            payload = transcribe_audio_verbose(chunk, config, prompt_override="")
        finally:
            chunk.unlink(missing_ok=True)
        text = str(payload.get("text", "")).strip()
        correct, corrupt = check(text)
        log(f"F_verbose_no_prompt_trial{i+1}", correct, corrupt, text)

    # G: chunk 3 alone, verbose_json, WITH the real captured prompt_override
    for i in range(2):
        chunk = slice_wav(PATH, *CHUNK_3)
        try:
            payload = transcribe_audio_verbose(chunk, config, prompt_override=real_prompt_override)
        finally:
            chunk.unlink(missing_ok=True)
        text = str(payload.get("text", "")).strip()
        correct, corrupt = check(text)
        log(f"G_verbose_with_real_prompt_trial{i+1}", correct, corrupt, text)

    # H: chunk 3 alone, PLAIN json (transcribe_audio doesn't support prompt_override
    # in the same way -- use transcribe_audio_request directly to control both axes)
    from speedytype.api import transcribe_audio_request
    for i in range(2):
        chunk = slice_wav(PATH, *CHUNK_3)
        try:
            payload = transcribe_audio_request(chunk, config, response_format="json", prompt_override=real_prompt_override)
        finally:
            chunk.unlink(missing_ok=True)
        text = str(payload.get("text", "")).strip()
        correct, corrupt = check(text)
        log(f"H_plain_json_with_real_prompt_trial{i+1}", correct, corrupt, text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
