from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re

from speedytype.chunking import PlannedChunk
from speedytype.segment_merge import MergeResult


@dataclass(frozen=True)
class HybridChunkResult:
    index: int
    start_seconds: float
    end_seconds: float
    text: str
    error: str = ""


@dataclass(frozen=True)
class HybridValidation:
    ok: bool
    reasons: tuple[str, ...]
    transcript_duration_coverage: float
    text_density: float


@dataclass(frozen=True)
class ValidatedTranscript:
    text: str
    fallback_used: bool
    fallback_reasons: tuple[str, ...]


def _intersects(left: tuple[float, float], right: tuple[float, float]) -> bool:
    return min(left[1], right[1]) > max(left[0], right[0])


def _active_duration(intervals: list[tuple[float, float]]) -> float:
    return sum(max(0.0, end - start) for start, end in intervals)


def validate_hybrid_result(
    plan: list[PlannedChunk],
    merge_result: MergeResult,
    chunk_results: list[HybridChunkResult],
    audio_activity: list[tuple[float, float]],
) -> HybridValidation:
    reasons: list[str] = []
    by_index = {result.index: result for result in chunk_results}
    densities: list[tuple[int, float]] = []
    for chunk in plan:
        result = by_index.get(chunk.index)
        if result is None:
            reasons.append(f"chunk {chunk.index} missing result")
            continue
        if result.error:
            reasons.append(f"chunk {chunk.index} failed: {result.error}")
        active = any(_intersects((chunk.start_seconds, chunk.end_seconds), interval) for interval in audio_activity)
        if active and not result.text.strip() and not result.error:
            reasons.append(f"chunk {chunk.index} is empty despite active audio")
        duration = max(1e-6, result.end_seconds - result.start_seconds)
        densities.append((result.index, len(result.text.strip()) / duration))

    nonzero_densities = sorted(density for _, density in densities if density > 0)
    if len(nonzero_densities) >= 3:
        median = nonzero_densities[len(nonzero_densities) // 2]
        for index, density in densities:
            if density > 0 and density < median * 0.25:
                reasons.append(f"chunk {index} has abnormal text density {density:.3f} versus median {median:.3f}")

    active_total = _active_duration(audio_activity)
    active_gap = 0.0
    for gap in merge_result.gaps:
        for interval in audio_activity:
            overlap = max(0.0, min(gap[1], interval[1]) - max(gap[0], interval[0]))
            active_gap += overlap
            if overlap > 1e-6:
                reasons.append(f"active-audio gap {gap[0]:.3f}-{gap[1]:.3f}")
                break
    coverage = 1.0 if active_total <= 0 else max(0.0, 1.0 - active_gap / active_total)

    sentences = [
        re.sub(r"\s+", "", sentence)
        for sentence in re.split(r"[。！？!?；;\n]+", merge_result.text)
        if re.sub(r"\s+", "", sentence)
    ]
    for sentence, count in Counter(sentences).items():
        if count > 1:
            reasons.append(f"repeated sentence introduced: {sentence}")

    total_duration = sum(max(0.0, result.end_seconds - result.start_seconds) for result in chunk_results)
    text_density = len(merge_result.text.strip()) / total_duration if total_duration else 0.0
    return HybridValidation(not reasons, tuple(dict.fromkeys(reasons)), coverage, text_density)


def resolve_with_batch_fallback(validation: HybridValidation, hybrid_text: str, batch_transcribe) -> ValidatedTranscript:
    if validation.ok:
        return ValidatedTranscript(hybrid_text, False, ())
    return ValidatedTranscript(batch_transcribe(), True, validation.reasons)
