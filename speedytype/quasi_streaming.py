from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
import time

import soundfile as sf

from speedytype.api import transcribe_audio, transcribe_audio_verbose
from speedytype.config import AppConfig
from speedytype.llm import LlmResult, call_llm_polisher


def merge_text_with_overlap(left: str, right: str, max_overlap_chars: int = 48) -> str:
    left_clean = left.strip()
    right_clean = right.strip()
    if not left_clean:
        return right_clean
    if not right_clean:
        return left_clean

    best = 0
    max_overlap = min(len(left_clean), len(right_clean), max_overlap_chars)
    for size in range(max_overlap, 0, -1):
        if left_clean[-size:] == right_clean[:size]:
            best = size
            break
    if best:
        return left_clean + right_clean[best:]
    separator = "" if left_clean.endswith((" ", "\n")) or right_clean.startswith((" ", "\n", "，", "。", ",", ".")) else " "
    return left_clean + separator + right_clean


@dataclass(frozen=True)
class ChunkPlan:
    index: int
    start_seconds: float
    end_seconds: float
    commit_until_seconds: float
    is_final: bool


@dataclass(frozen=True)
class ChunkResult:
    plan: ChunkPlan
    request_seconds: float
    text: str
    segments: list[dict[str, float | str]]
    started_at_seconds: float
    finished_at_seconds: float


@dataclass(frozen=True)
class StreamingResult:
    merged_transcript: str
    chunk_results: list[ChunkResult]
    stt_tail_seconds: float
    llm_wall_seconds: float
    llm_result: LlmResult

    @property
    def total_whisper_request_seconds(self) -> float:
        return sum(chunk.request_seconds for chunk in self.chunk_results)


def build_chunk_plan(audio_seconds: float, chunk_seconds: float = 3.0, overlap_seconds: float = 0.75) -> list[ChunkPlan]:
    if overlap_seconds >= chunk_seconds:
        raise ValueError("overlap_seconds must be smaller than chunk_seconds")
    step = chunk_seconds - overlap_seconds
    plans: list[ChunkPlan] = []
    start = 0.0
    index = 1
    while start < audio_seconds - 1e-9:
        end = min(audio_seconds, start + chunk_seconds)
        is_final = end >= audio_seconds - 1e-9
        commit_until = end if is_final else min(audio_seconds, start + step)
        plans.append(
            ChunkPlan(
                index=index,
                start_seconds=round(start, 6),
                end_seconds=round(end, 6),
                commit_until_seconds=round(commit_until, 6),
                is_final=is_final,
            )
        )
        if is_final:
            break
        start += step
        index += 1
    return plans


def slice_wav(audio_path: Path, start_seconds: float, end_seconds: float) -> Path:
    data, sample_rate = sf.read(audio_path, always_2d=True)
    start_frame = max(0, int(start_seconds * sample_rate))
    end_frame = min(len(data), int(end_seconds * sample_rate))
    chunk = data[start_frame:end_frame]
    handle = tempfile.NamedTemporaryFile(prefix="speedytype_chunk_", suffix=".wav", delete=False)
    path = Path(handle.name)
    handle.close()
    sf.write(path, chunk, sample_rate, subtype="PCM_16")
    return path


def tail_prompt(config: AppConfig, prior_text: str, max_chars: int = 200) -> str:
    """Return stable vocabulary hints without feeding prior transcript text back to Whisper.

    ``prior_text`` and ``max_chars`` remain in the compatibility signature for
    the historical benchmark callers. Real API trials showed that the rolling
    narrative tail deterministically triggered Case D's ``一兆`` hallucination.
    """
    return config.whisper_vocab_bias


def simulate_quasi_streaming_transcription(
    audio_path: Path,
    config: AppConfig,
    *,
    chunk_seconds: float = 3.0,
    overlap_seconds: float = 0.75,
) -> StreamingResult:
    info = sf.info(str(audio_path))
    audio_seconds = info.frames / float(info.samplerate)
    plans = build_chunk_plan(audio_seconds, chunk_seconds=chunk_seconds, overlap_seconds=overlap_seconds)

    committed_text = ""
    worker_free_at = 0.0
    chunk_results: list[ChunkResult] = []
    try:
        for plan in plans:
            chunk_path = slice_wav(audio_path, plan.start_seconds, plan.end_seconds)
            prompt = tail_prompt(config, committed_text)
            started = time.perf_counter()
            payload = transcribe_audio_verbose(chunk_path, config, prompt_override=prompt)
            request_seconds = time.perf_counter() - started
            try:
                chunk_path.unlink()
            except Exception:
                pass

            shifted_segments = []
            for segment in payload.get("segments", []) or []:
                seg_start = float(segment.get("start", 0.0)) + plan.start_seconds
                seg_end = float(segment.get("end", 0.0)) + plan.start_seconds
                shifted_segments.append({"start": seg_start, "end": seg_end, "text": str(segment.get("text", "")).strip()})

            for segment in shifted_segments:
                midpoint = (float(segment["start"]) + float(segment["end"])) / 2.0
                if midpoint <= plan.commit_until_seconds + 1e-6:
                    committed_text = merge_text_with_overlap(committed_text, str(segment["text"]))

            start_at = max(plan.end_seconds, worker_free_at)
            finish_at = start_at + request_seconds
            worker_free_at = finish_at
            chunk_results.append(
                ChunkResult(
                    plan=plan,
                    request_seconds=request_seconds,
                    text=str(payload.get("text", "")).strip(),
                    segments=shifted_segments,
                    started_at_seconds=start_at,
                    finished_at_seconds=finish_at,
                )
            )
    finally:
        pass

    stt_tail_seconds = max(0.0, worker_free_at - audio_seconds)
    llm_started = time.perf_counter()
    llm_result = call_llm_polisher(committed_text, config)
    llm_wall_seconds = time.perf_counter() - llm_started
    return StreamingResult(
        merged_transcript=committed_text.strip(),
        chunk_results=chunk_results,
        stt_tail_seconds=stt_tail_seconds,
        llm_wall_seconds=llm_wall_seconds,
        llm_result=llm_result,
    )


def run_baseline_transcription(audio_path: Path, config: AppConfig) -> tuple[str, float, float, LlmResult]:
    stt_started = time.perf_counter()
    raw = transcribe_audio(audio_path, config)
    whisper_wall_seconds = time.perf_counter() - stt_started
    llm_started = time.perf_counter()
    llm_result = call_llm_polisher(raw, config)
    llm_wall_seconds = time.perf_counter() - llm_started
    return raw, whisper_wall_seconds, llm_wall_seconds, llm_result
