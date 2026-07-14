from pathlib import Path
import wave

from speedytype.config import AppConfig, load_config
from speedytype.llm import LlmUsage
from speedytype.pipeline import process_wav


def write_empty_wav(path: Path):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 160)


def test_config_reads_hybrid_feature_flag(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "OPENAI_API_KEY=x\nGEMINI_API_KEY=y\nHYBRID_TRANSCRIPTION_ENABLED=true\nHYBRID_THRESHOLD_SECONDS=120\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("speedytype.config.resolve_mic_device_setting", lambda value: ("", ""))
    config = load_config(env, tmp_path / "settings.json")
    assert config.hybrid_transcription_enabled is True
    assert config.hybrid_threshold_seconds == 120


def test_pipeline_override_does_not_call_whisper(tmp_path, monkeypatch):
    wav = tmp_path / "audio.wav"
    write_empty_wav(wav)
    monkeypatch.setattr(
        "speedytype.pipeline.transcribe_audio",
        lambda *args: (_ for _ in ()).throw(AssertionError("Whisper must not run twice")),
    )
    monkeypatch.setattr("speedytype.pipeline.call_llm_polisher", lambda text, config: type("R", (), {
        "text": text,
        "provider": "fake",
        "model": "fake",
        "llm_call_seconds": 0.0,
        "retry_wait_seconds": 0.0,
        "usage": LlmUsage(),
    })())
    config = AppConfig(openai_api_key="x", gemini_api_key="y", latency_log_path=tmp_path / "latency.csv")
    result = process_wav(
        wav,
        config,
        do_paste=False,
        raw_transcript_override="validated hybrid text",
        whisper_seconds_override=1.25,
    )
    assert result.raw_transcript == "validated hybrid text"
    assert result.latency.whisper_seconds == 1.25


def test_latency_records_hybrid_diagnostics(tmp_path, monkeypatch):
    wav = tmp_path / "audio.wav"
    write_empty_wav(wav)
    monkeypatch.setattr("speedytype.pipeline.call_llm_polisher", lambda text, config: type("R", (), {
        "text": text, "provider": "fake", "model": "fake", "llm_call_seconds": 0.0, "retry_wait_seconds": 0.0,
        "usage": LlmUsage(),
    })())
    config = AppConfig(openai_api_key="x", gemini_api_key="y", latency_log_path=tmp_path / "latency.csv")
    result = process_wav(
        wav, config, do_paste=False, raw_transcript_override="text", whisper_seconds_override=1,
        hybrid_request_count=4, hybrid_request_seconds=8.5, hybrid_fallback_used=True,
        hybrid_validation_reasons="active gap", precomputed_tail_seconds=2.0,
    )
    assert result.latency.hybrid_request_count == 4
    assert result.latency.hybrid_request_seconds == 8.5
    assert result.latency.hybrid_fallback_used is True
    assert result.latency.total_tail_latency_seconds >= 2.0
    assert "active gap" in (tmp_path / "latency.csv").read_text(encoding="utf-8")
