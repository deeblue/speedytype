from __future__ import annotations

import csv
import argparse
from pathlib import Path
from types import SimpleNamespace
import threading
import wave

import pytest

from speedytype.config import AppConfig
from speedytype.llm import LlmResult, LlmUsage
from speedytype.pipeline import process_wav
from speedytype.paths import default_pricing_path
from speedytype.usage_stats import calculate_usage


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16_000)
        wav_file.writeframes(b"\x00\x00" * 1600)


def test_sub_tenth_second_recording_skips_all_external_work_and_latency_row(tmp_path, monkeypatch):
    wav_path = tmp_path / "empty.wav"
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16_000)
        wav_file.writeframes(b"\x00\x00" * 160)
    config = _config(tmp_path)
    monkeypatch.setattr(
        "speedytype.pipeline.transcribe_audio",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Whisper must not run")),
    )
    monkeypatch.setattr(
        "speedytype.pipeline.call_llm_polisher",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("LLM must not run")),
    )
    monkeypatch.setattr(
        "speedytype.pipeline.paste_text_preserving_clipboard",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("paste must not run")),
    )

    result = process_wav(wav_path, config, do_paste=True, usage_scope="daily")

    assert result.raw_transcript == result.polished_text == ""
    assert result.paste_ok is False
    assert result.paste_message == "Recording too short; skipped."
    assert result.latency.recording_seconds == pytest.approx(0.01)
    assert not config.latency_log_path.exists()


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(openai_api_key="x", gemini_api_key="y", latency_log_path=tmp_path / "latency.csv")


def test_process_wav_propagates_authoritative_llm_usage(tmp_path, monkeypatch) -> None:
    wav_path = tmp_path / "audio.wav"
    _write_wav(wav_path)
    monkeypatch.setattr(
        "speedytype.pipeline.call_llm_polisher",
        lambda text, config: LlmResult(
            text="polished",
            provider="gemini",
            model="gemini-test",
            llm_call_seconds=0.25,
            retry_wait_seconds=0.0,
            retry_count=0,
            usage=LlmUsage(input_tokens=120, output_tokens=30, total_tokens=150),
            raw_response={},
        ),
    )
    config = _config(tmp_path)

    result = process_wav(
        wav_path,
        config,
        do_paste=False,
        raw_transcript_override="raw",
        usage_scope="daily",
        stt_model="whisper-special",
    )

    assert result.latency.usage_scope == "daily"
    assert result.latency.stt_model == "whisper-special"
    assert result.latency.llm_input_tokens == 120
    assert result.latency.llm_output_tokens == 30
    assert result.latency.llm_total_tokens == 150
    with config.latency_log_path.open("r", encoding="utf-8", newline="") as csv_file:
        row = next(csv.DictReader(csv_file))
    assert row["usage_scope"] == "daily"
    assert row["stt_model"] == "whisper-special"
    assert row["llm_input_tokens"] == "120"
    assert row["llm_output_tokens"] == "30"
    assert row["llm_total_tokens"] == "150"


def test_normal_transcription_sends_and_records_selected_stt_model(tmp_path, monkeypatch) -> None:
    wav_path = tmp_path / "audio.wav"
    _write_wav(wav_path)
    sent_models = []

    def fake_transcribe(path, config, *, model):
        sent_models.append(model)
        return "raw"

    monkeypatch.setattr("speedytype.pipeline.transcribe_audio", fake_transcribe)
    monkeypatch.setattr(
        "speedytype.pipeline.call_llm_polisher",
        lambda text, config: LlmResult(
            text="polished",
            provider="gemini",
            model="gemini-test",
            llm_call_seconds=0.25,
            retry_wait_seconds=0.0,
            retry_count=0,
            usage=LlmUsage(),
            raw_response={},
        ),
    )
    config = _config(tmp_path)

    result = process_wav(wav_path, config, do_paste=False, stt_model="whisper-selected")

    assert sent_models == ["whisper-selected"]
    assert result.latency.stt_model == "whisper-selected"
    with config.latency_log_path.open("r", encoding="utf-8", newline="") as csv_file:
        assert next(csv.DictReader(csv_file))["stt_model"] == "whisper-selected"


def test_process_wav_rejects_invalid_usage_scope(tmp_path) -> None:
    with pytest.raises(ValueError, match="usage_scope"):
        process_wav(tmp_path / "missing.wav", _config(tmp_path), usage_scope="benchmark")


def test_daily_empty_transcript_does_not_record_an_llm_call(tmp_path, monkeypatch) -> None:
    wav_path = tmp_path / "audio.wav"
    _write_wav(wav_path)
    monkeypatch.setattr(
        "speedytype.pipeline.call_llm_polisher",
        lambda *args: (_ for _ in ()).throw(AssertionError("empty transcript must skip the LLM")),
    )
    monkeypatch.setattr("speedytype.pipeline.transcribe_audio", lambda path, config, *, model: "   ")
    config = _config(tmp_path)

    result = process_wav(
        wav_path,
        config,
        do_paste=False,
        usage_scope="daily",
    )

    assert result.latency.usage_scope == "daily"
    assert result.latency.stt_model == "whisper-1"
    assert result.latency.llm_provider == ""
    assert result.latency.llm_model == ""
    assert result.latency.llm_input_tokens is None
    assert result.latency.llm_output_tokens is None
    assert result.latency.llm_total_tokens is None
    summary = calculate_usage(config.latency_log_path, default_pricing_path())
    assert summary.llm_calls == 0


@pytest.mark.parametrize("hybrid_enabled", [False, True])
def test_daemon_processing_paths_mark_usage_daily(tmp_path, monkeypatch, hybrid_enabled) -> None:
    from PyQt6.QtWidgets import QApplication
    from speedytype.daemon import DaemonController

    app = QApplication.instance() or QApplication([])
    config = _config(tmp_path)
    controller = DaemonController(config)
    controller._active_path = tmp_path / "audio.wav"
    controller._active_thread = SimpleNamespace(is_alive=lambda: True, join=lambda: None)
    controller.recorder = SimpleNamespace(stop=lambda: None)
    if hybrid_enabled:
        hybrid_result = SimpleNamespace(
            raw_text="hybrid text",
            tail_seconds=1.5,
            fallback_used=False,
            request_count=2,
            request_seconds=2.5,
            audio_seconds=75.0,
            diagnostics={"validation_reasons": []},
        )
        controller._hybrid_transcriber = SimpleNamespace(finish=lambda path: hybrid_result)
    else:
        controller._hybrid_transcriber = None

    calls = []
    monkeypatch.setattr("speedytype.daemon.wait_until_hotkey_released", lambda *args: ("released", 0.1))
    monkeypatch.setattr("speedytype.daemon.process_wav", lambda *args, **kwargs: calls.append(kwargs))

    class ImmediateThread:
        def __init__(self, *, target, daemon):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr("speedytype.daemon.threading.Thread", ImmediateThread)

    controller._finish_after_release()

    assert calls[0]["usage_scope"] == "daily"
    if hybrid_enabled:
        assert calls[0]["stt_audio_seconds"] == 75.0
    app.processEvents()


def test_cli_run_once_marks_usage_daily(tmp_path, monkeypatch) -> None:
    from speedytype import cli

    calls = []
    monkeypatch.setattr(cli, "_load_config_or_print", lambda path: _config(tmp_path))
    monkeypatch.setattr(cli, "process_wav", lambda *args, **kwargs: calls.append(kwargs))

    result = cli.command_run_once(argparse.Namespace(env="unused", wav="audio.wav", no_paste=True))

    assert result == 0
    assert calls[0]["usage_scope"] == "daily"


def test_cli_listen_marks_usage_daily(tmp_path, monkeypatch) -> None:
    from speedytype import cli

    recorder_stopped = threading.Event()
    processed = threading.Event()
    calls = []

    class FakeRecorder:
        def __init__(self, device):
            pass

        def record_until_stop(self, path):
            recorder_stopped.wait(timeout=1)

        def stop(self):
            recorder_stopped.set()

    class InterruptingEvent:
        def wait(self):
            raise KeyboardInterrupt

    def register_hotkey(hotkey, on_press):
        on_press()
        return "handle"

    def fake_process_wav(*args, **kwargs):
        calls.append(kwargs)
        processed.set()

    monkeypatch.setattr(cli, "_load_config_or_print", lambda path: _config(tmp_path))
    monkeypatch.setattr(cli, "Recorder", FakeRecorder)
    monkeypatch.setattr(cli, "temp_wav_path", lambda: tmp_path / "audio.wav")
    monkeypatch.setattr(cli, "wait_until_hotkey_released", lambda *args: ("released", 0.1))
    monkeypatch.setattr(cli, "register_hold_hotkey", register_hotkey)
    monkeypatch.setattr(cli, "remove_hotkey", lambda handle: None)
    monkeypatch.setattr(cli, "process_wav", fake_process_wav)
    monkeypatch.setattr(cli, "threading", SimpleNamespace(Thread=threading.Thread, Event=InterruptingEvent))

    result = cli.command_listen(argparse.Namespace(env="unused"))

    assert result == 0
    assert processed.wait(timeout=1)
    assert calls[0]["usage_scope"] == "daily"
