from __future__ import annotations

from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from speedytype.api import DISAMBIGUATION_HINTS, gemini_generate_content_url, parse_gemini_text
from speedytype.config import load_config


CURRENT_PROMPT = """你是一個精通多國語言的「語音輸入修飾專家」。
1. 刪除所有口語贅字：如「呃」、「然後」、「那個」、「就是說」。
2. 智能修正語病：若使用者在陳述中途自我修正（例如：「我們下週一，啊不對，下週三要開會」），
   請直接輸出修正後的結果（「我們下週三要開會」），不要保留修正前的內容。
3. 智能排版：根據內容邏輯自動分段，若包含多個平行觀點、步驟，請自動使用 Markdown 條列式排版。
4. 專業名詞校正：精準識別技術與研發專有名詞（例如：BIOS, Firmware, NPI, QA, API, TPE 團隊, BJ 團隊），
   修正前後文中因語音辨識造成的錯別字或同音異字。
{disambiguation_hints}
5. 嚴格限制：只輸出修飾後的最終文字，絕對不要包含任何自我解釋、招呼語或
   「以下是修飾後的文字」等額外內容。""".replace("\n\n5.", "\n5.")

CANDIDATE_PROMPT = """你是一個精通多國語言的「語音輸入修飾專家」。
1. 刪除所有口語贅字：如「呃」、「然後」、「那個」、「就是說」。
2. 智能修正語病：若使用者在陳述中途自我修正（例如：「我們下週一，啊不對，下週三要開會」），
   請直接輸出修正後的結果（「我們下週三要開會」），不要保留修正前的內容。
3. 智能排版：根據內容邏輯自動分段，若包含多個平行觀點、步驟，請自動使用 Markdown 條列式排版。
4. 專業名詞校正：精準識別技術與研發專有名詞（例如：BIOS, Firmware, NPI, QA, API, TPE 團隊, BJ 團隊），
   修正前後文中因語音辨識造成的錯別字或同音異字。
5. 數字與重複內容保留：若語音辨識結果因使用者重複講述相同內容而出現破碎、重複的文字（例如同一句話講了
   好幾次），請合併為一次乾淨的版本，但必須完整保留其中出現過的所有數字、代號與實際內容，絕對不能因為
   內容看起來雜亂或重複，就整段省略其中的數字或關鍵詞。這條規則不適用於規則2的自我修正情境（自我修正時
   仍應捨棄修正前的錯誤內容）。
{disambiguation_hints}
6. 嚴格限制：只輸出修飾後的最終文字，絕對不要包含任何自我解釋、招呼語或
   「以下是修飾後的文字」等額外內容。""".replace("\n\n6.", "\n6.")


def build_prompt(template: str, use_hints: bool) -> str:
    hints = DISAMBIGUATION_HINTS if use_hints else ""
    return template.format(disambiguation_hints=hints)


def polish_with_prompt(text: str, system_prompt: str, config, timeout_seconds: int = 60, max_attempts: int = 4) -> str:
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "generationConfig": {"temperature": 0.1},
    }
    last_error = ""
    for attempt in range(max_attempts):
        try:
            response = requests.post(
                gemini_generate_content_url(config.gemini_model, config.gemini_api_key),
                headers={"Content-Type": "application/json"},
                json=body,
                timeout=timeout_seconds,
            )
        except requests.RequestException as exc:
            last_error = f"[REQUEST_EXCEPTION] {exc}"
            time.sleep(2 * (attempt + 1))
            continue
        if response.status_code == 503 or response.status_code == 429:
            last_error = f"[ERROR {response.status_code}] {response.text[:200]}"
            time.sleep(2 * (attempt + 1))
            continue
        if response.status_code != 200:
            return f"[ERROR {response.status_code}] {response.text[:300]}"
        return parse_gemini_text(response.json())
    return f"[FAILED after {max_attempts} attempts] {last_error}"


TEST_CASES = [
    ("numbers_repeated_english", "123測試測試 123測試測試 123 test 123 test"),
    ("self_correction", "我們下週一，啊不對，下週三要開會"),
    ("filler_removal", "呃，請TPE團隊今天同步BIOS狀態"),
    ("list_formatting", "今天要做三件事，第一，開會，第二，寫報告，第三，回信"),
    ("stutter_repeat", "我們我們下週三要開會"),
    ("numbers_repeated_chinese", "測試1、2、3、4"),
]


def main() -> int:
    config = load_config(".env")
    current_prompt = build_prompt(CURRENT_PROMPT, config.use_disambiguation_hints)
    candidate_prompt = build_prompt(CANDIDATE_PROMPT, config.use_disambiguation_hints)

    for name, text in TEST_CASES:
        print(f"=== {name} ===")
        print(f"INPUT: {text}")
        current_result = polish_with_prompt(text, current_prompt, config)
        print(f"CURRENT prompt  -> {current_result!r}")
        candidate_result = polish_with_prompt(text, candidate_prompt, config)
        print(f"CANDIDATE prompt -> {candidate_result!r}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
