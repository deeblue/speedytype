from pathlib import Path
import wave

from speedytype.config import AppConfig
from speedytype.real_voice import discover_completed_indices, discover_final_wavs, parse_real_voice_script, prompt_accept_or_rerecord


def test_parse_real_voice_script_reads_numbered_items(tmp_path: Path):
    script = tmp_path / "script.md"
    script.write_text(
        """
# Script

1. **短句** [停頓提示：自然停頓] 呃，請 TPE 團隊確認 BIOS。
2. **中句** [停頓提示：先停一下] 我們下週二，啊不對，下週四要跟 QA 開會。
""",
        encoding="utf-8",
    )

    items = parse_real_voice_script(script)

    assert [item.index for item in items] == [1, 2]
    assert "TPE 團隊" in items[0].text
    assert "下週四" in items[1].text


def test_discover_final_wavs_orders_by_segment_number(tmp_path: Path):
    for name in ["segment02_final.wav", "segment01_final.wav"]:
        path = tmp_path / name
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(b"\0\0" * 160)

    paths = discover_final_wavs(tmp_path)

    assert [path.name for path in paths] == ["segment01_final.wav", "segment02_final.wav"]


def test_discover_completed_indices_reads_existing_finals(tmp_path: Path):
    for name in ["segment02_final.wav", "segment05_final.wav", "segment05_take1.wav"]:
        path = tmp_path / name
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(b"\0\0" * 160)

    assert discover_completed_indices(tmp_path) == {2, 5}


def test_validate_real_voice_writes_report(tmp_path: Path, monkeypatch):
    from speedytype.real_voice import validate_real_voice

    script = tmp_path / "script.md"
    script.write_text("1. **短句** [停頓提示：自然停頓] 呃，請 TPE 團隊確認 BIOS。\n", encoding="utf-8")
    wav_path = tmp_path / "segment01_final.wav"
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\0\0" * 160)

    class FakeResult:
        raw_transcript = "呃，請 TPE 團隊確認 BIOS。"
        polished_text = "請 TPE 團隊確認 BIOS。"

    monkeypatch.setattr("speedytype.real_voice.process_wav", lambda *args, **kwargs: FakeResult())
    report = tmp_path / "REAL_VOICE_REPORT.md"
    config = AppConfig(openai_api_key="x", gemini_api_key="y")

    validate_real_voice(tmp_path, script, config, report)

    text = report.read_text(encoding="utf-8")
    assert "TPE 團隊" in text
    assert "請 TPE 團隊確認 BIOS。" in text


def test_prompt_accept_or_rerecord_falls_back_to_input(monkeypatch):
    monkeypatch.setattr("speedytype.real_voice.os.name", "posix")
    monkeypatch.setattr("builtins.input", lambda prompt: "r")

    assert prompt_accept_or_rerecord() == "r"
