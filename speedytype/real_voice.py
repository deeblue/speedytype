from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import shutil
import time
import wave
import threading

from speedytype.audio import Recorder
from speedytype.config import AppConfig
from speedytype.hotkey import wait_until_hotkey_released
from speedytype.pipeline import process_wav

TARGET_TERMS = ["BIOS", "Firmware", "NPI", "QA", "API", "TPE 團隊", "BJ 團隊", "USB", "Thunderbolt"]


@dataclass(frozen=True)
class ScriptItem:
    index: int
    title: str
    text: str
    estimated_seconds: str


def parse_real_voice_script(path: Path) -> list[ScriptItem]:
    items: list[ScriptItem] = []
    pattern = re.compile(r"^\s*(\d+)\.\s*(?:\*\*(.*?)\*\*)?\s*(?:\[.*?\])?\s*(.+?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        index = int(match.group(1))
        title = (match.group(2) or f"句子 {index}").strip()
        text = match.group(3).strip()
        length = len(re.sub(r"\s+", "", text))
        if length <= 35:
            estimated = "<5s"
        elif length <= 90:
            estimated = "10-15s"
        else:
            estimated = "20-30s"
        items.append(ScriptItem(index=index, title=title, text=text, estimated_seconds=estimated))
    return items


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav_file:
        return wav_file.getnframes() / float(wav_file.getframerate())


def discover_final_wavs(directory: Path) -> list[Path]:
    def key(path: Path) -> int:
        match = re.search(r"segment(\d+)_final\.wav$", path.name)
        return int(match.group(1)) if match else 9999

    return sorted(directory.glob("segment*_final.wav"), key=key)


def discover_completed_indices(directory: Path) -> set[int]:
    completed: set[int] = set()
    for path in discover_final_wavs(directory):
        match = re.search(r"segment(\d+)_final\.wav$", path.name)
        if match:
            completed.add(int(match.group(1)))
    return completed


def expected_terms(text: str) -> list[str]:
    return [term for term in TARGET_TERMS if term in text]


def build_term_stats(rows: list[dict[str, str]]) -> dict[str, dict[str, int]]:
    stats = {term: {"expected": 0, "correct": 0} for term in TARGET_TERMS}
    for row in rows:
        expected = [term for term in TARGET_TERMS if term in row["expected"]]
        for term in expected:
            stats[term]["expected"] += 1
            if term in row["polished"]:
                stats[term]["correct"] += 1
    return stats


def prompt_accept_or_rerecord() -> str:
    prompt = "按 Enter 接受並前往下一句；按 r 重錄這句: "
    if os.name == "nt":
        import msvcrt

        print(prompt, end="", flush=True)
        while True:
            key = msvcrt.getwch()
            if key in ("\r", "\n"):
                print("", flush=True)
                return ""
            if key.lower() == "r":
                print("r", flush=True)
                return "r"
    response = input(prompt)
    return response.strip().lower()


def guided_recording(
    script_path: Path,
    output_dir: Path,
    hotkey: str = "f9",
    mic_device: str | int | None = None,
    max_record_seconds: float = 30.0,
) -> None:
    import keyboard

    items = parse_real_voice_script(script_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    completed_indices = discover_completed_indices(output_dir)
    recorder = Recorder(device=mic_device)
    started = time.perf_counter()
    retake_counts: dict[int, int] = {}

    for item in items:
        if item.index in completed_indices:
            print(f"\n[{item.index}/{len(items)}] 已存在 segment{item.index:02d}_final.wav，跳過。")
            continue
        take = 1
        while True:
            print(f"\n[{item.index}/{len(items)}] {item.title} estimated={item.estimated_seconds}")
            print(item.text)
            print(f"準備好後按住 {hotkey.upper()} 開始念，念完放開。")
            keyboard.wait(hotkey)
            path = output_dir / f"segment{item.index:02d}_take{take}.wav"
            print("Recording...")
            thread = threading.Thread(target=recorder.record_until_stop, args=(path,), daemon=False)
            thread.start()
            reason, elapsed = wait_until_hotkey_released(hotkey, max_record_seconds)
            if reason == "timeout":
                print(f"錄音超時 {elapsed:.1f}s，已自動停止。")
            recorder.stop()
            thread.join()
            duration = wav_duration(path)
            print(f"錄音完成: {path} duration={duration:.2f}s")
            choice = prompt_accept_or_rerecord()
            if choice != "r":
                final_path = output_dir / f"segment{item.index:02d}_final.wav"
                shutil.copyfile(path, final_path)
                break
            take += 1
            retake_counts[item.index] = retake_counts.get(item.index, 1) + 1

    elapsed = time.perf_counter() - started
    high_retakes = [idx for idx, count in retake_counts.items() if count > 2]
    print(f"完成 {len(items)} 句，總時間 {elapsed / 60:.1f} 分鐘。")
    print(f"重錄超過 2 次的句子: {high_retakes if high_retakes else '無'}")


def validate_real_voice(directory: Path, script_path: Path, config: AppConfig, report_path: Path) -> None:
    items = {item.index: item for item in parse_real_voice_script(script_path)}
    wavs = discover_final_wavs(directory)
    rows: list[dict[str, str]] = []
    for wav_path in wavs:
        match = re.search(r"segment(\d+)_final\.wav$", wav_path.name)
        if not match:
            continue
        index = int(match.group(1))
        item = items.get(index)
        result = process_wav(wav_path, config, do_paste=False, run_label="real_voice")
        text = result.polished_text
        expected = item.text if item else ""
        rows.append(
            {
                "index": str(index),
                "expected": expected,
                "whisper": result.raw_transcript,
                "polished": text,
                "expected_terms": ", ".join(expected_terms(expected)),
                "missing_terms": ", ".join(term for term in expected_terms(expected) if term not in text),
                "terms_ok": "✅" if all(term not in expected or term in result.raw_transcript + text for term in TARGET_TERMS) else "❌",
                "self_correction_ok": "✅" if "啊不對" not in text and "不對" not in text else "❌",
                "filler_removed_ok": "✅" if all(filler not in text for filler in ["呃", "那個", "就是說"]) else "❌",
            }
        )

    lines = ["# Real Voice Report", "", "Generated after user-provided recordings.", ""]
    lines.append("| # | 原始腳本 | Whisper | 修飾後 | 預期專有名詞 | 缺失專有名詞 | 專有名詞 | 自我修正 | 贅字 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for row in rows:
        lines.append(
            f"| {row['index']} | {row['expected']} | {row['whisper']} | {row['polished']} | {row['expected_terms']} | {row['missing_terms'] or '-'} | {row['terms_ok']} | {row['self_correction_ok']} | {row['filler_removed_ok']} |"
        )
    if rows:
        terms_rate = sum(1 for row in rows if row["terms_ok"] == "✅") / len(rows) * 100.0
        correction_rate = sum(1 for row in rows if row["self_correction_ok"] == "✅") / len(rows) * 100.0
        filler_rate = sum(1 for row in rows if row["filler_removed_ok"] == "✅") / len(rows) * 100.0
        term_stats = build_term_stats(rows)
        lines.extend(
            [
                "",
                "## Summary",
                "",
                f"- 專有名詞辨識正確率：{terms_rate:.1f}%",
                f"- 自我修正處理正確率：{correction_rate:.1f}%",
                f"- 贅字清除正確率：{filler_rate:.1f}%",
                "",
                "## Per-Term Accuracy",
                "",
                "| 詞彙 | 正確次數 | 出現次數 | 正確率 |",
                "|---|---:|---:|---:|",
            ]
        )
        for term in TARGET_TERMS:
            expected_count = term_stats[term]["expected"]
            correct_count = term_stats[term]["correct"]
            rate_text = "-" if expected_count == 0 else f"{(correct_count / expected_count * 100.0):.1f}%"
            lines.append(f"| {term} | {correct_count} | {expected_count} | {rate_text} |")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
