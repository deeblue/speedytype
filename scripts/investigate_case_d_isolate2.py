from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from speedytype.api import transcribe_audio_verbose
from speedytype.config import load_config
from speedytype.quasi_streaming import slice_wav

PATH = Path("test_audio_long/continuous_tts_295s.wav")
TARGET_PHRASE_CORRECT = "海邊步道依照距離重新排序"
TARGET_PHRASE_CORRUPT = "一兆"
CHUNK_3 = (50.88, 75.24)

VOCAB_ONLY = "BIOS, Firmware, NPI, QA, API, TPE 團隊, BJ 團隊, USB, Thunderbolt"
TAIL_ONLY = (
    "報,決定帶一把折疊傘 然後把昨晚充電的相機、行動電源和筆記本放進背包 早餐是一杯無糖豆漿、兩片烤吐司和一顆水煮蛋 "
    "出門前,我關閉瓦斯,確認陽台窗戶已經鎖好 並替門口的植物澆了一點水 七點十五分,我走到附近車站搭乘公車 "
    "車上乘客不多,有人看新聞,有人戴著耳機聽音樂 經過河堤時,雨勢逐漸變小,雲層之間露出一小片藍天 "
    "抵達火車站後,我在自動售票機領取預定車票,再到月台旁的商店買了一瓶礦泉水 列車準時出發"
)


def check(text: str) -> tuple[bool, bool]:
    cleaned = text.replace(" ", "").replace(",", "").replace("、", "")
    return TARGET_PHRASE_CORRECT in cleaned, TARGET_PHRASE_CORRUPT in text


def log(name: str, correct: bool, corrupt: bool, text: str) -> None:
    with open("case_d_investigation_results.txt", "a", encoding="utf-8") as out:
        out.write(f"=== {name} ===\ncorrect={correct} corrupt={corrupt}\nTEXT: {text}\n\n")
    print(f"{name}: correct={correct} corrupt={corrupt}")


def run(name: str, config, prompt: str, repeats: int = 2) -> None:
    for i in range(repeats):
        chunk = slice_wav(PATH, *CHUNK_3)
        try:
            payload = transcribe_audio_verbose(chunk, config, prompt_override=prompt)
        finally:
            chunk.unlink(missing_ok=True)
        text = str(payload.get("text", "")).strip()
        correct, corrupt = check(text)
        log(f"{name}_trial{i+1}", correct, corrupt, text)


def main() -> int:
    config = load_config(".env")
    with open("case_d_investigation_results.txt", "a", encoding="utf-8") as out:
        out.write("\n--- Isolation experiments part 2: which half of the prompt triggers it? ---\n\n")

    run("I_vocab_bias_only_no_tail", config, VOCAB_ONLY)
    run("J_tail_text_only_no_vocab", config, TAIL_ONLY)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
