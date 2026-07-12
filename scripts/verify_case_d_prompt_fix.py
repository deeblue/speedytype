from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from speedytype.api import transcribe_audio_verbose
from speedytype.config import load_config
from speedytype.quasi_streaming import slice_wav, tail_prompt


AUDIO_PATH = Path("test_audio_long/continuous_tts_295s.wav")
OUTPUT_PATH = Path("case_d_prompt_fix_results.txt")
CHUNK_3 = (50.88, 75.24)
CORRECT_PHRASE = "海邊步道依照距離重新排序"
CORRUPT_TOKEN = "一兆"
TRIGGERING_TAIL = (
    "報,決定帶一把折疊傘 然後把昨晚充電的相機、行動電源和筆記本放進背包 "
    "早餐是一杯無糖豆漿、兩片烤吐司和一顆水煮蛋 出門前,我關閉瓦斯,確認陽台窗戶已經鎖好 "
    "並替門口的植物澆了一點水 七點十五分,我走到附近車站搭乘公車 車上乘客不多,有人看新聞,有人戴著耳機聽音樂 "
    "經過河堤時,雨勢逐漸變小,雲層之間露出一小片藍天 抵達火車站後,我在自動售票機領取預定車票,再到月台旁的商店買了一瓶礦泉水 列車準時出發"
)


def normalize(text: str) -> str:
    return "".join(character for character in text if character not in " \t\r\n,，、。")


def main() -> int:
    config = load_config(".env")
    prompt = tail_prompt(config, TRIGGERING_TAIL)
    records: list[str] = [
        "=== Case D prompt-fix isolation: mirror of group J ===",
        f"audio={AUDIO_PATH}",
        f"window={CHUNK_3[0]:.2f}-{CHUNK_3[1]:.2f}s",
        f"triggering_tail_chars={len(TRIGGERING_TAIL)}",
        f"actual_prompt={prompt!r}",
        "",
    ]
    correct_count = 0
    corrupt_count = 0
    for trial in range(1, 7):
        chunk_path = slice_wav(AUDIO_PATH, *CHUNK_3)
        try:
            payload = transcribe_audio_verbose(chunk_path, config, prompt_override=prompt)
        finally:
            chunk_path.unlink(missing_ok=True)
        text = str(payload.get("text", "")).strip()
        normalized = normalize(text)
        correct = normalize(CORRECT_PHRASE) in normalized
        corrupt = CORRUPT_TOKEN in text
        correct_count += int(correct)
        corrupt_count += int(corrupt)
        records.extend(
            [
                f"=== fixed_vocab_only_trial_{trial} ===",
                f"correct={correct} corrupt_1trillion={corrupt}",
                f"TEXT: {text}",
                "",
            ]
        )

    passed = correct_count == 6 and corrupt_count == 0
    records.append(
        f"SUMMARY: correct={correct_count}/6 corrupt_1trillion={corrupt_count}/6 gate_ok={passed}"
    )
    OUTPUT_PATH.write_text("\n".join(records) + "\n", encoding="utf-8")
    print(records[-1])
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
