from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata


@dataclass(frozen=True)
class TimedSegment:
    start_seconds: float
    end_seconds: float
    text: str
    chunk_index: int


@dataclass(frozen=True)
class MergeDecision:
    segment: TimedSegment
    action: str
    reason: str


@dataclass(frozen=True)
class MergeResult:
    text: str
    committed_until_seconds: float
    decisions: tuple[MergeDecision, ...]
    gaps: tuple[tuple[float, float], ...]
    duplicates: tuple[TimedSegment, ...]


def _normalized(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).lower()
    return "".join(char for char in value if char.isalnum())


def _similarity(left: str, right: str) -> float:
    a, b = _normalized(left), _normalized(right)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return min(len(a), len(b)) / max(len(a), len(b))
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def _overlaps(left: TimedSegment, right: TimedSegment, tolerance: float = 0.15) -> bool:
    return min(left.end_seconds, right.end_seconds) >= max(left.start_seconds, right.start_seconds) - tolerance


def merge_timed_segments(
    chunks: list[list[TimedSegment]],
    duration_seconds: float,
) -> MergeResult:
    pending = sorted(
        (segment for chunk in chunks for segment in chunk if segment.text.strip()),
        key=lambda segment: (segment.start_seconds, segment.end_seconds, segment.chunk_index),
    )
    accepted: list[TimedSegment] = []
    decisions: list[MergeDecision] = []
    duplicates: list[TimedSegment] = []
    for segment in pending:
        duplicate_index = next(
            (
                index
                for index in range(len(accepted) - 1, -1, -1)
                if _overlaps(accepted[index], segment) and _similarity(accepted[index].text, segment.text) >= 0.60
            ),
            None,
        )
        if duplicate_index is None:
            accepted.append(segment)
            decisions.append(MergeDecision(segment, "commit", "distinct-timestamped-segment"))
            continue
        existing = accepted[duplicate_index]
        duplicates.append(segment)
        if len(_normalized(segment.text)) > len(_normalized(existing.text)):
            accepted[duplicate_index] = segment
            decisions.append(MergeDecision(existing, "replace", "overlap-more-complete"))
            decisions.append(MergeDecision(segment, "commit", "overlap-more-complete"))
        else:
            decisions.append(MergeDecision(segment, "drop", "overlap-duplicate"))

    accepted.sort(key=lambda segment: (segment.start_seconds, segment.end_seconds))
    gaps: list[tuple[float, float]] = []
    cursor = 0.0
    for segment in accepted:
        if segment.start_seconds > cursor + 1e-6:
            gaps.append((round(cursor, 6), round(segment.start_seconds, 6)))
        cursor = max(cursor, segment.end_seconds)
    if duration_seconds > cursor + 1e-6:
        gaps.append((round(cursor, 6), round(duration_seconds, 6)))
    text = " ".join(segment.text.strip() for segment in accepted)
    return MergeResult(
        text=re.sub(r"\s+", " ", text).strip(),
        committed_until_seconds=min(duration_seconds, cursor),
        decisions=tuple(decisions),
        gaps=tuple(gaps),
        duplicates=tuple(duplicates),
    )
