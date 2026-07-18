from __future__ import annotations

import csv
import argparse
import builtins
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import threading
import wave

import pytest

from speedytype.config import AppConfig
from speedytype.flac_upload import UploadPreparationError
from speedytype.llm import LlmResult, LlmUsage
from speedytype.pipeline import process_wav
from speedytype.paths import default_pricing_path
from speedytype.recording_recovery import (
    create_recording_path,
    mark_recording,
    recording_sidecar_path,
)
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
        "speedytype.pipeline.prepare_upload",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("FLAC must not run")),
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


def _owned_wav(tmp_path: Path) -> Path:
    path = create_recording_path(directory=tmp_path)
    _write_wav(path)
    mark_recording(path, "captured")
    return path


def _llm_result(text: str = "polished") -> LlmResult:
    return LlmResult(
        text=text,
        provider="gemini",
        model="gemini-test",
        llm_call_seconds=0.25,
        retry_wait_seconds=0.0,
        retry_count=0,
        usage=LlmUsage(),
        raw_response={},
    )


def test_owned_recording_prepares_flac_records_upload_and_completes(tmp_path, monkeypatch) -> None:
    wav_path = _owned_wav(tmp_path)
    flac_path = tmp_path / "prepared.flac"
    flac_path.write_bytes(b"flac")
    prepared = SimpleNamespace(
        path=flac_path, container="flac", upload_bytes=4, encoding_seconds=1.25,
        fallback_used=False, fallback_reason="",
    )

    @contextmanager
    def fake_prepare(path):
        assert path == wav_path
        yield prepared

    sent = []
    monkeypatch.setattr("speedytype.pipeline.prepare_upload", fake_prepare)
    monkeypatch.setattr(
        "speedytype.pipeline.transcribe_audio",
        lambda path, config, *, model: sent.append(path) or "raw",
    )
    monkeypatch.setattr("speedytype.pipeline.call_llm_polisher", lambda *args: _llm_result())

    result = process_wav(wav_path, _config(tmp_path), do_paste=False, usage_scope="daily")

    assert sent == [flac_path]
    assert result.latency.stt_upload_container == "flac"
    assert result.latency.stt_upload_bytes == 4
    assert result.latency.stt_encoding_seconds == pytest.approx(1.25)
    assert result.latency.stt_wav_fallback_used is False
    assert '"state": "completed"' in recording_sidecar_path(wav_path).read_text(encoding="utf-8")
    assert wav_path.exists()


def test_pipeline_records_short_wav_fallback_metadata(tmp_path, monkeypatch) -> None:
    wav_path = _owned_wav(tmp_path)
    prepared = SimpleNamespace(
        path=wav_path, container="wav", upload_bytes=wav_path.stat().st_size,
        encoding_seconds=0.0, fallback_used=True, fallback_reason="FlacEncodingError",
    )

    @contextmanager
    def fake_prepare(path):
        yield prepared

    monkeypatch.setattr("speedytype.pipeline.prepare_upload", fake_prepare)
    monkeypatch.setattr("speedytype.pipeline.transcribe_audio", lambda *args, **kwargs: "raw")
    monkeypatch.setattr("speedytype.pipeline.call_llm_polisher", lambda *args: _llm_result())

    result = process_wav(wav_path, _config(tmp_path), do_paste=False)

    assert result.latency.stt_upload_container == "wav"
    assert result.latency.stt_wav_fallback_used is True
    assert result.latency.stt_wav_fallback_reason == "FlacEncodingError"


def test_transcription_failure_marks_owned_wav_failed_retained(tmp_path, monkeypatch) -> None:
    wav_path = _owned_wav(tmp_path)
    flac_path = tmp_path / "prepared.flac"
    flac_path.write_bytes(b"flac")
    prepared = SimpleNamespace(
        path=flac_path, container="flac", upload_bytes=4, encoding_seconds=0.1,
        fallback_used=False, fallback_reason="",
    )

    @contextmanager
    def fake_prepare(path):
        yield prepared

    monkeypatch.setattr("speedytype.pipeline.prepare_upload", fake_prepare)
    monkeypatch.setattr(
        "speedytype.pipeline.transcribe_audio",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider detail")),
    )

    with pytest.raises(RuntimeError, match="provider detail"):
        process_wav(wav_path, _config(tmp_path), do_paste=False)

    metadata = recording_sidecar_path(wav_path).read_text(encoding="utf-8")
    assert '"state": "failed-retained"' in metadata
    assert '"error_category": "RuntimeError"' in metadata
    assert wav_path.exists()


def test_upload_refusal_preserves_specific_failure_category(tmp_path, monkeypatch) -> None:
    wav_path = _owned_wav(tmp_path)

    @contextmanager
    def refusing_prepare(path):
        raise UploadPreparationError("upload_too_large", path)
        yield  # pragma: no cover - keeps this a context manager

    monkeypatch.setattr("speedytype.pipeline.prepare_upload", refusing_prepare)

    with pytest.raises(UploadPreparationError):
        process_wav(wav_path, _config(tmp_path), do_paste=False)

    metadata = recording_sidecar_path(wav_path).read_text(encoding="utf-8")
    assert '"state": "failed-retained"' in metadata
    assert '"error_category": "upload_too_large"' in metadata


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


def test_daemon_processing_path_marks_usage_daily(tmp_path, monkeypatch) -> None:
    from PyQt6.QtWidgets import QApplication
    from speedytype.daemon import DaemonController

    app = QApplication.instance() or QApplication([])
    config = _config(tmp_path)
    controller = DaemonController(config, activation_threshold_seconds=0)
    controller.recorder = SimpleNamespace(
        stop=lambda: None,
        record_until_stop=lambda *args, **kwargs: None,
    )
    controller._hybrid_transcriber = None

    calls = []
    monkeypatch.setattr("speedytype.daemon.wait_until_hotkey_released", lambda *args: ("released", 0.1))
    monkeypatch.setattr("speedytype.daemon.process_wav", lambda *args, **kwargs: calls.append(kwargs))

    class ImmediateThread:
        def __init__(self, *, target, daemon, args=()):
            self.target = target
            self.args = args
            self.started = False
            self.joined = False

        def start(self):
            self.started = True
            if getattr(self.target, "__name__", "") == "<lambda>":
                self.target(*self.args)

        def is_alive(self):
            return self.started and not self.joined

        def join(self):
            self.joined = True

    monkeypatch.setattr("speedytype.daemon.threading.Thread", ImmediateThread)
    monkeypatch.setattr("speedytype.daemon.temp_wav_path", lambda: tmp_path / "audio.wav")

    controller.on_press()
    controller._finish_after_release(controller._active_session)

    assert calls[0]["usage_scope"] == "daily"
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
            assert processed.wait(timeout=1)
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
    monkeypatch.setattr(
        cli,
        "threading",
        SimpleNamespace(Thread=threading.Thread, Lock=threading.Lock, Event=InterruptingEvent),
    )

    result = cli.command_listen(argparse.Namespace(env="unused"))

    assert result == 0
    assert processed.wait(timeout=1)
    assert calls[0]["usage_scope"] == "daily"


def test_cli_listen_sanitizes_failed_capture_retains_wav_and_reuses_listener(
    tmp_path, monkeypatch, capsys
) -> None:
    from speedytype import cli

    first_path = create_recording_path(directory=tmp_path)
    second_path = create_recording_path(directory=tmp_path)
    paths = iter((first_path, second_path))
    first_failed = threading.Event()
    second_recording = threading.Event()
    second_stopped = threading.Event()
    processed = threading.Event()
    callbacks = []
    process_calls = []

    class FailingThenWorkingRecorder:
        calls = 0

        def __init__(self, device):
            pass

        def record_until_stop(self, path):
            type(self).calls += 1
            if type(self).calls == 1:
                first_failed.set()
                raise OSError("Bearer private-provider-detail")
            second_recording.set()
            second_stopped.wait(timeout=2)

        def stop(self):
            second_stopped.set()

    class DrivingEvent:
        def wait(self):
            assert first_failed.wait(timeout=2)
            for _ in range(200):
                if '"state": "failed-retained"' in recording_sidecar_path(first_path).read_text(encoding="utf-8"):
                    break
                threading.Event().wait(0.01)
            callbacks[0]()
            assert second_recording.wait(timeout=2)
            assert processed.wait(timeout=2)
            raise KeyboardInterrupt

    def register_hotkey(_hotkey, callback):
        callbacks.append(callback)
        callback()
        return "handle"

    def process(path, *args, **kwargs):
        process_calls.append((path, kwargs))
        processed.set()

    monkeypatch.setattr(cli, "_load_config_or_print", lambda path: _config(tmp_path))
    monkeypatch.setattr(cli, "Recorder", FailingThenWorkingRecorder)
    monkeypatch.setattr(cli, "temp_wav_path", lambda: next(paths))
    monkeypatch.setattr(cli, "wait_until_hotkey_released", lambda *args: ("released", 0.1))
    monkeypatch.setattr(cli, "register_hold_hotkey", register_hotkey)
    monkeypatch.setattr(cli, "remove_hotkey", lambda handle: None)
    monkeypatch.setattr(cli, "process_wav", process)
    monkeypatch.setattr(
        cli,
        "threading",
        SimpleNamespace(Thread=threading.Thread, Lock=threading.Lock, Event=DrivingEvent),
    )

    result = cli.command_listen(argparse.Namespace(env="unused"))
    output = capsys.readouterr()

    assert result == 0
    assert '"state": "failed-retained"' in recording_sidecar_path(first_path).read_text(encoding="utf-8")
    assert process_calls == [(second_path, {"do_paste": True, "usage_scope": "daily"})]
    assert "Recording failed (OSError)." in output.err
    assert str(first_path) in output.err
    assert "private-provider-detail" not in output.err
    assert "Bearer" not in output.err


def test_cli_listen_metadata_failure_still_sanitizes_cleans_up_and_reuses(
    tmp_path, monkeypatch, capsys
) -> None:
    from speedytype import cli

    first_path = create_recording_path(directory=tmp_path)
    second_path = create_recording_path(directory=tmp_path)
    paths = iter((first_path, second_path))
    failure_reported = threading.Event()
    second_recording = threading.Event()
    second_stopped = threading.Event()
    processed = threading.Event()
    callbacks = []
    process_calls = []

    class Recorder:
        calls = 0

        def __init__(self, device):
            pass

        def record_until_stop(self, path):
            type(self).calls += 1
            if type(self).calls == 1:
                raise OSError("primary private detail")
            second_recording.set()
            second_stopped.wait(timeout=2)

        def stop(self):
            second_stopped.set()

    class DrivingEvent:
        def wait(self):
            assert failure_reported.wait(timeout=2)
            callbacks[0]()
            assert second_recording.wait(timeout=2)
            assert processed.wait(timeout=2)
            raise KeyboardInterrupt

    def tracked_print(*args, **kwargs):
        builtins.print(*args, **kwargs)
        if args and "Recording failed" in str(args[0]):
            failure_reported.set()

    def register_hotkey(_hotkey, callback):
        callbacks.append(callback)
        callback()
        return "handle"

    def process(path, *args, **kwargs):
        process_calls.append(path)
        processed.set()

    monkeypatch.setattr(cli, "_load_config_or_print", lambda path: _config(tmp_path))
    monkeypatch.setattr(cli, "Recorder", Recorder)
    monkeypatch.setattr(cli, "temp_wav_path", lambda: next(paths))
    monkeypatch.setattr(cli, "mark_recording", lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("metadata private detail")))
    monkeypatch.setattr(cli, "wait_until_hotkey_released", lambda *args: ("released", 0.1))
    monkeypatch.setattr(cli, "register_hold_hotkey", register_hotkey)
    monkeypatch.setattr(cli, "remove_hotkey", lambda handle: None)
    monkeypatch.setattr(cli, "process_wav", process)
    monkeypatch.setattr(cli, "print", tracked_print, raising=False)
    monkeypatch.setattr(
        cli,
        "threading",
        SimpleNamespace(Thread=threading.Thread, Lock=threading.Lock, Event=DrivingEvent),
    )

    result = cli.command_listen(argparse.Namespace(env="unused"))
    output = capsys.readouterr()

    assert result == 0
    assert process_calls == [second_path]
    assert "Recording failed (OSError)." in output.err
    assert str(first_path) in output.err
    assert "Recovery metadata update failed (PermissionError)." in output.err
    assert "primary private detail" not in output.err
    assert "metadata private detail" not in output.err
