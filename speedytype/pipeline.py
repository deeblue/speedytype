from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
import wave

from speedytype.api import transcribe_audio
from speedytype.clipboard import paste_text
from speedytype.console import safe_print
from speedytype.config import AppConfig
from speedytype.latency import LatencyRecord, append_latency_record
from speedytype.llm import call_llm_polisher


@dataclass(frozen=True)
class PipelineResult:
    raw_transcript: str
    polished_text: str
    paste_ok: bool
    paste_message: str
    latency: LatencyRecord


def wav_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate()
        return frames / float(rate) if rate else 0.0


def process_wav(audio_path: Path, config: AppConfig, *, do_paste: bool = True, run_label: str = "") -> PipelineResult:
    recording_seconds = wav_duration_seconds(audio_path)
    tail_start = time.perf_counter()
    safe_print("Recording ended.", flush=True)

    whisper_start = time.perf_counter()
    raw = transcribe_audio(audio_path, config)
    whisper_seconds = time.perf_counter() - whisper_start
    safe_print(f"Whisper raw transcript: {raw}", flush=True)

    if not raw.strip():
        latency = LatencyRecord.create(
            recording_seconds=recording_seconds,
            whisper_seconds=whisper_seconds,
            gemini_seconds=0.0,
            paste_seconds=0.0,
            total_tail_latency_seconds=time.perf_counter() - tail_start,
            run_label=run_label,
            llm_provider=config.llm_provider,
            llm_model=config.llm_model,
            llm_call_seconds=0.0,
            retry_wait_seconds=0.0,
        )
        append_latency_record(config.latency_log_path, latency)
        message = "Whisper returned empty text; skipped Gemini and paste."
        safe_print(message, flush=True)
        return PipelineResult("", "", False, message, latency)

    gemini_start = time.perf_counter()
    llm_result = call_llm_polisher(raw, config)
    polished = llm_result.text
    gemini_seconds = time.perf_counter() - gemini_start
    safe_print(f"Gemini polished text: {polished}", flush=True)

    paste_start = time.perf_counter()
    paste_result = None
    if do_paste and polished.strip():
        paste_result = paste_text(polished)
        paste_ok, paste_message = paste_result.ok, paste_result.message
    else:
        paste_ok, paste_message = False, "Paste skipped by command option."
    paste_seconds = time.perf_counter() - paste_start
    total_tail = time.perf_counter() - tail_start

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
        focus_window_seconds=0.0,
        clipboard_write_seconds=0.0 if paste_result is None else paste_result.clipboard_write_seconds,
        pre_paste_wait_seconds=0.0 if paste_result is None else paste_result.pre_send_wait_seconds,
        key_send_seconds=0.0 if paste_result is None else paste_result.key_send_seconds,
        post_paste_wait_seconds=0.0 if paste_result is None else paste_result.post_send_wait_seconds,
        paste_verification_seconds=0.0 if paste_result is None else paste_result.verification_seconds,
    )
    append_latency_record(config.latency_log_path, latency)
    safe_print(
        "Latency seconds: "
        f"recording={recording_seconds:.3f}, whisper={whisper_seconds:.3f}, "
        f"gemini={gemini_seconds:.3f}, paste={paste_seconds:.3f}, total_tail={total_tail:.3f}",
        flush=True,
    )
    if not paste_ok:
        safe_print(paste_message, flush=True)
    return PipelineResult(raw, polished, paste_ok, paste_message, latency)
