from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
import wave

import numpy as np

from speedytype.api import DEFAULT_STT_MODEL, transcribe_audio_result
from speedytype.platform.clipboard import PasteTarget
from speedytype.clipboard import paste_text_preserving_clipboard
from speedytype.console import safe_print
from speedytype.config import AppConfig
from speedytype.flac_upload import prepare_upload
from speedytype.latency import LatencyRecord, append_latency_record
from speedytype.llm import call_llm_polisher
from speedytype.recording_recovery import mark_recording


SILENT_RECORDING_MAX_RMS = 0.002
SILENT_RECORDING_MAX_PEAK = 0.02
SHORT_RECORDING_SPEECH_GATE_SECONDS = 2.0
SHORT_RECORDING_MIN_ACTIVE_SECONDS = 0.25
ACTIVE_FRAME_SECONDS = 0.05


@dataclass(frozen=True)
class PipelineResult:
    raw_transcript: str
    polished_text: str
    paste_ok: bool
    paste_message: str
    latency: LatencyRecord


@dataclass(frozen=True)
class WavSignalStats:
    rms: float
    peak: float
    active_seconds: float = 0.0


def wav_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate()
        return frames / float(rate) if rate else 0.0


def wav_signal_stats(path: Path) -> WavSignalStats:
    with wave.open(str(path), "rb") as wav_file:
        sample_width = wav_file.getsampwidth()
        frames = wav_file.readframes(wav_file.getnframes())
    if not frames:
        return WavSignalStats(rms=0.0, peak=0.0)
    if sample_width != 2:
        return WavSignalStats(rms=1.0, peak=1.0, active_seconds=1.0)
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if samples.size == 0:
        return WavSignalStats(rms=0.0, peak=0.0)
    active_seconds = _estimate_active_audio_seconds(samples)
    return WavSignalStats(
        rms=float(np.sqrt(np.mean(np.square(samples)))),
        peak=float(np.max(np.abs(samples))),
        active_seconds=active_seconds,
    )


def _estimate_active_audio_seconds(samples: np.ndarray, sample_rate: int = 16_000) -> float:
    frame_size = max(1, int(sample_rate * ACTIVE_FRAME_SECONDS))
    frame_count = samples.size // frame_size
    if frame_count <= 0:
        return 0.0
    framed = samples[: frame_count * frame_size].reshape(frame_count, frame_size)
    frame_rms = np.sqrt(np.mean(np.square(framed), axis=1))
    noise_floor = float(np.percentile(frame_rms, 20))
    # Short accidental activations often contain low room noise plus one click
    # or key sound. Require sustained frames above a noise-relative floor, while
    # capping that floor so genuinely short spoken words are not rejected just
    # because the whole clip is speech.
    active_threshold = max(0.006, min(noise_floor * 3.0, 0.03))
    return float(np.count_nonzero(frame_rms >= active_threshold) * ACTIVE_FRAME_SECONDS)


def is_silent_recording(path: Path) -> bool:
    try:
        stats = wav_signal_stats(path)
    except Exception:
        return False
    return stats.rms <= SILENT_RECORDING_MAX_RMS and stats.peak <= SILENT_RECORDING_MAX_PEAK


def is_short_recording_without_sustained_speech(path: Path, recording_seconds: float) -> bool:
    if recording_seconds >= SHORT_RECORDING_SPEECH_GATE_SECONDS:
        return False
    try:
        stats = wav_signal_stats(path)
    except Exception:
        return False
    return stats.active_seconds < SHORT_RECORDING_MIN_ACTIVE_SECONDS


def is_empty_recording_hallucination(text: str, recording_seconds: float) -> bool:
    if recording_seconds >= SHORT_RECORDING_SPEECH_GATE_SECONDS:
        return False
    normalized = " ".join(text.strip().lower().split())
    if not normalized:
        return False
    return (
        "amara.org" in normalized
        or "字幕由" in normalized
        or "社區提供" in normalized
        or "社区提供" in normalized
    )


def process_wav(
    audio_path: Path,
    config: AppConfig,
    *,
    do_paste: bool = True,
    run_label: str = "",
    usage_scope: str = "development",
    stt_model: str = DEFAULT_STT_MODEL,
    raw_transcript_override: str | None = None,
    whisper_seconds_override: float | None = None,
    hybrid_request_count: int = 0,
    hybrid_request_seconds: float = 0.0,
    stt_audio_seconds: float | None = None,
    hybrid_fallback_used: bool = False,
    hybrid_validation_reasons: str = "",
    precomputed_tail_seconds: float = 0.0,
    paste_target: PasteTarget | None = None,
) -> PipelineResult:
    if usage_scope not in {"daily", "development"}:
        raise ValueError("usage_scope must be 'daily' or 'development'")
    recording_seconds = wav_duration_seconds(audio_path)
    resolved_stt_audio_seconds = (
        recording_seconds if stt_audio_seconds is None else stt_audio_seconds
    )
    tail_start = time.perf_counter()
    safe_print("Recording ended.", flush=True)

    if recording_seconds < 0.1 and raw_transcript_override is None:
        message = "Recording too short; skipped."
        safe_print(message, flush=True)
        latency = LatencyRecord.create(
            recording_seconds=recording_seconds,
            whisper_seconds=0.0,
            gemini_seconds=0.0,
            paste_seconds=0.0,
            total_tail_latency_seconds=time.perf_counter() - tail_start,
            run_label="recording_too_short",
            usage_scope=usage_scope,
            stt_model=stt_model,
            stt_audio_seconds=0.0,
        )
        mark_recording(audio_path, "processing")
        mark_recording(audio_path, "completed")
        return PipelineResult("", "", False, message, latency)

    if raw_transcript_override is None and is_silent_recording(audio_path):
        message = "Recording is silent or too quiet; skipped."
        safe_print(message, flush=True)
        latency = LatencyRecord.create(
            recording_seconds=recording_seconds,
            whisper_seconds=0.0,
            gemini_seconds=0.0,
            paste_seconds=0.0,
            total_tail_latency_seconds=time.perf_counter() - tail_start,
            run_label="recording_silent",
            usage_scope=usage_scope,
            stt_model=stt_model,
            stt_audio_seconds=0.0,
        )
        mark_recording(audio_path, "processing")
        mark_recording(audio_path, "completed")
        return PipelineResult("", "", False, message, latency)

    if raw_transcript_override is None and is_short_recording_without_sustained_speech(
        audio_path, recording_seconds
    ):
        message = "Recording has no sustained speech; skipped."
        safe_print(message, flush=True)
        latency = LatencyRecord.create(
            recording_seconds=recording_seconds,
            whisper_seconds=0.0,
            gemini_seconds=0.0,
            paste_seconds=0.0,
            total_tail_latency_seconds=time.perf_counter() - tail_start,
            run_label="recording_no_sustained_speech",
            usage_scope=usage_scope,
            stt_model=stt_model,
            stt_audio_seconds=0.0,
        )
        mark_recording(audio_path, "processing")
        mark_recording(audio_path, "completed")
        return PipelineResult("", "", False, message, latency)

    upload_container = ""
    upload_bytes: int | None = None
    encoding_seconds = 0.0
    wav_fallback_used = False
    wav_fallback_reason = ""
    processing_started = False
    actual_stt_model = stt_model
    try:
        if raw_transcript_override is None:
            mark_recording(audio_path, "encoding")
            with prepare_upload(audio_path) as prepared:
                upload_container = prepared.container
                upload_bytes = prepared.upload_bytes
                encoding_seconds = prepared.encoding_seconds
                wav_fallback_used = prepared.fallback_used
                wav_fallback_reason = prepared.fallback_reason
                if wav_fallback_used:
                    safe_print(
                        "FLAC preparation failed; admissible WAV fallback will be uploaded "
                        f"({wav_fallback_reason}).",
                        flush=True,
                    )
                mark_recording(audio_path, "ready")
                mark_recording(audio_path, "processing")
                processing_started = True
                whisper_start = time.perf_counter()
                transcription = transcribe_audio_result(prepared.path, config, model=stt_model)
                raw = transcription.text
                actual_stt_model = transcription.stt_model
                whisper_seconds = time.perf_counter() - whisper_start
        else:
            mark_recording(audio_path, "processing")
            processing_started = True
            raw = raw_transcript_override
            whisper_seconds = 0.0 if whisper_seconds_override is None else whisper_seconds_override
    except Exception as exc:
        category = str(getattr(exc, "category", type(exc).__name__))
        mark_recording(audio_path, "failed-retained", error_category=category)
        raise
    safe_print(f"Whisper raw transcript: {raw}", flush=True)

    if is_empty_recording_hallucination(raw, recording_seconds):
        latency = LatencyRecord.create(
            recording_seconds=recording_seconds,
            whisper_seconds=whisper_seconds,
            gemini_seconds=0.0,
            paste_seconds=0.0,
            total_tail_latency_seconds=precomputed_tail_seconds + time.perf_counter() - tail_start,
            run_label="empty_recording_hallucination",
            usage_scope=usage_scope,
            stt_model=actual_stt_model,
            stt_audio_seconds=resolved_stt_audio_seconds,
            stt_upload_container=upload_container,
            stt_upload_bytes=upload_bytes,
            stt_encoding_seconds=encoding_seconds,
            stt_wav_fallback_used=wav_fallback_used,
            stt_wav_fallback_reason=wav_fallback_reason,
        )
        message = "Whisper returned an empty-recording hallucination; skipped."
        safe_print(message, flush=True)
        mark_recording(audio_path, "completed")
        return PipelineResult(raw, "", False, message, latency)

    if not raw.strip():
        latency = LatencyRecord.create(
            recording_seconds=recording_seconds,
            whisper_seconds=whisper_seconds,
            gemini_seconds=0.0,
            paste_seconds=0.0,
            total_tail_latency_seconds=precomputed_tail_seconds + time.perf_counter() - tail_start,
            run_label=run_label,
            llm_provider="",
            llm_model="",
            llm_call_seconds=0.0,
            retry_wait_seconds=0.0,
            hybrid_request_count=hybrid_request_count,
            hybrid_request_seconds=hybrid_request_seconds,
            hybrid_fallback_used=hybrid_fallback_used,
            hybrid_validation_reasons=hybrid_validation_reasons,
            usage_scope=usage_scope,
            stt_model=actual_stt_model,
            stt_audio_seconds=resolved_stt_audio_seconds,
            stt_upload_container=upload_container,
            stt_upload_bytes=upload_bytes,
            stt_encoding_seconds=encoding_seconds,
            stt_wav_fallback_used=wav_fallback_used,
            stt_wav_fallback_reason=wav_fallback_reason,
        )
        append_latency_record(config.latency_log_path, latency)
        message = "Whisper returned empty text; skipped Gemini and paste."
        safe_print(message, flush=True)
        mark_recording(audio_path, "failed-retained", error_category="EmptyTranscript")
        return PipelineResult("", "", False, message, latency)

    try:
        gemini_start = time.perf_counter()
        llm_result = call_llm_polisher(raw, config)
        polished = llm_result.text
        gemini_seconds = time.perf_counter() - gemini_start
        safe_print(f"Gemini polished text: {polished}", flush=True)

        paste_start = time.perf_counter()
        paste_result = None
        if do_paste and polished.strip():
            paste_result = paste_text_preserving_clipboard(
                polished,
                restore_delay_seconds=config.clipboard_restore_delay_seconds,
                paste_target=paste_target,
            )
            paste_ok, paste_message = paste_result.ok, paste_result.message
        else:
            paste_ok, paste_message = False, "Paste skipped by command option."
        paste_seconds = time.perf_counter() - paste_start
        total_tail = precomputed_tail_seconds + time.perf_counter() - tail_start
    except Exception as exc:
        if processing_started:
            mark_recording(audio_path, "failed-retained", error_category=type(exc).__name__)
        raise

    latency = LatencyRecord.create(
        recording_seconds=recording_seconds,
        whisper_seconds=whisper_seconds,
        gemini_seconds=gemini_seconds,
        paste_seconds=paste_seconds,
        total_tail_latency_seconds=total_tail,
        run_label=run_label,
        llm_provider=llm_result.provider,
        llm_model=llm_result.model,
        llm_call_seconds=llm_result.llm_call_seconds,
        retry_wait_seconds=llm_result.retry_wait_seconds,
        focus_window_seconds=0.0 if paste_result is None else paste_result.focus_window_seconds,
        clipboard_write_seconds=0.0 if paste_result is None else paste_result.clipboard_write_seconds,
        pre_paste_wait_seconds=0.0 if paste_result is None else paste_result.pre_send_wait_seconds,
        key_send_seconds=0.0 if paste_result is None else paste_result.key_send_seconds,
        post_paste_wait_seconds=0.0 if paste_result is None else paste_result.post_send_wait_seconds,
        paste_verification_seconds=0.0 if paste_result is None else paste_result.verification_seconds,
        hybrid_request_count=hybrid_request_count,
        hybrid_request_seconds=hybrid_request_seconds,
        hybrid_fallback_used=hybrid_fallback_used,
        hybrid_validation_reasons=hybrid_validation_reasons,
        usage_scope=usage_scope,
        stt_model=actual_stt_model,
        stt_audio_seconds=resolved_stt_audio_seconds,
        stt_upload_container=upload_container,
        stt_upload_bytes=upload_bytes,
        stt_encoding_seconds=encoding_seconds,
        stt_wav_fallback_used=wav_fallback_used,
        stt_wav_fallback_reason=wav_fallback_reason,
        llm_input_tokens=llm_result.usage.input_tokens,
        llm_output_tokens=llm_result.usage.output_tokens,
        llm_total_tokens=llm_result.usage.total_tokens,
    )
    append_latency_record(config.latency_log_path, latency)
    if do_paste and not paste_ok:
        mark_recording(audio_path, "failed-retained", error_category="PasteFailed")
    else:
        mark_recording(audio_path, "completed")
    safe_print(
        "Latency seconds: "
        f"recording={recording_seconds:.3f}, whisper={whisper_seconds:.3f}, "
        f"gemini={gemini_seconds:.3f}, paste={paste_seconds:.3f}, total_tail={total_tail:.3f}",
        flush=True,
    )
    if not paste_ok:
        safe_print(paste_message, flush=True)
    return PipelineResult(raw, polished, paste_ok, paste_message, latency)
