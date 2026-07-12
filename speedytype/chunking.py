from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ChunkingConfig:
    hybrid_threshold_seconds: float = 90.0
    min_chunk_seconds: float = 15.0
    preferred_chunk_seconds: float = 25.0
    max_chunk_seconds: float = 45.0
    minimum_silence_seconds: float = 0.6
    natural_cut_context_seconds: float = 0.2
    forced_cut_overlap_seconds: float = 1.5
    analysis_frame_ms: int = 20
    noise_floor_window_seconds: float = 5.0
    silence_enter_multiplier: float = 1.8
    silence_exit_multiplier: float = 2.4


@dataclass(frozen=True)
class AudioFrame:
    start_seconds: float
    end_seconds: float
    rms: float


@dataclass(frozen=True)
class SilenceRegion:
    start_seconds: float
    end_seconds: float
    noise_floor: float


@dataclass(frozen=True)
class PlannedChunk:
    index: int
    start_seconds: float
    end_seconds: float
    cut_reason: str
    overlap_seconds: float


def _rms_frames(samples: np.ndarray, sample_rate: int, frame_ms: int) -> list[AudioFrame]:
    mono = np.asarray(samples, dtype=np.float32)
    if mono.ndim > 1:
        mono = mono.mean(axis=1)
    frame_size = max(1, round(sample_rate * frame_ms / 1000))
    frames = []
    for start in range(0, len(mono), frame_size):
        data = mono[start:start + frame_size]
        rms = float(np.sqrt(np.mean(np.square(data), dtype=np.float64))) if len(data) else 0.0
        frames.append(AudioFrame(start / sample_rate, min(len(mono), start + frame_size) / sample_rate, rms))
    return frames


def detect_silence_regions(samples: np.ndarray, sample_rate: int, config: ChunkingConfig) -> list[SilenceRegion]:
    frames = _rms_frames(samples, sample_rate, config.analysis_frame_ms)
    if not frames:
        return []
    window_frames = max(1, round(config.noise_floor_window_seconds * 1000 / config.analysis_frame_ms))
    regions: list[SilenceRegion] = []
    silence_start: float | None = None
    region_floor = 0.0
    history: list[float] = []
    for frame in frames:
        history.append(frame.rms)
        recent = np.asarray(history[-window_frames:], dtype=np.float64)
        noise_floor = max(1e-8, float(np.min(recent)))
        typical_level = max(1e-8, float(np.median(recent)))
        enter_threshold = min(noise_floor * config.silence_enter_multiplier, typical_level * 0.5)
        exit_threshold = max(noise_floor * config.silence_exit_multiplier, typical_level * 0.65)
        if silence_start is None and frame.rms <= enter_threshold:
            silence_start = frame.start_seconds
            region_floor = noise_floor
        elif silence_start is not None:
            region_floor = min(region_floor, noise_floor)
            if frame.rms >= exit_threshold:
                if frame.start_seconds - silence_start >= config.minimum_silence_seconds:
                    regions.append(SilenceRegion(silence_start, frame.start_seconds, region_floor))
                silence_start = None
    if silence_start is not None and frames[-1].end_seconds - silence_start >= config.minimum_silence_seconds:
        regions.append(SilenceRegion(silence_start, frames[-1].end_seconds, region_floor))
    return regions


def plan_dynamic_chunks(
    duration_seconds: float,
    silences: list[SilenceRegion],
    config: ChunkingConfig,
) -> list[PlannedChunk]:
    if duration_seconds <= 0:
        return []
    chunks: list[PlannedChunk] = []
    start = 0.0
    index = 1
    while duration_seconds - start > config.max_chunk_seconds:
        earliest = start + config.min_chunk_seconds
        latest = start + config.max_chunk_seconds
        candidates = [
            region for region in silences
            if earliest <= (region.start_seconds + region.end_seconds) / 2 <= latest
        ]
        if candidates:
            preferred = start + config.preferred_chunk_seconds
            region = min(candidates, key=lambda item: abs((item.start_seconds + item.end_seconds) / 2 - preferred))
            cut = (region.start_seconds + region.end_seconds) / 2
            overlap = config.natural_cut_context_seconds
            reason = "silence"
        else:
            cut = latest
            overlap = config.forced_cut_overlap_seconds
            reason = "forced"
        chunks.append(PlannedChunk(index, round(start, 6), round(cut, 6), reason, overlap))
        next_start = cut - overlap
        if next_start <= start:
            raise RuntimeError("Chunk planner did not advance")
        start = next_start
        index += 1
    chunks.append(PlannedChunk(index, round(start, 6), round(duration_seconds, 6), "final", 0.0))
    return chunks
