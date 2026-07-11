from speedytype.chunking import PlannedChunk
from speedytype.hybrid_validation import (
    HybridChunkResult,
    resolve_with_batch_fallback,
    validate_hybrid_result,
)
from speedytype.segment_merge import MergeResult


def merge(text="第一句 第二句", gaps=(), duplicates=()):
    return MergeResult(text, 20.0, (), tuple(gaps), tuple(duplicates))


def plans():
    return [PlannedChunk(1, 0, 10, "silence", 0.2), PlannedChunk(2, 9.8, 20, "final", 0)]


def results(first="第一句", second="第二句", error=""):
    return [HybridChunkResult(1, 0, 10, first, error), HybridChunkResult(2, 9.8, 20, second, "")]


def test_failed_chunk_is_rejected():
    validation = validate_hybrid_result(plans(), merge(), results(error="HTTP 429"), [(0, 20)])
    assert not validation.ok
    assert any("chunk 1 failed" in reason for reason in validation.reasons)


def test_empty_active_speech_chunk_is_rejected():
    validation = validate_hybrid_result(plans(), merge(), results(first=""), [(0, 8)])
    assert any("chunk 1 is empty" in reason for reason in validation.reasons)


def test_non_silent_timeline_gap_is_rejected():
    validation = validate_hybrid_result(plans(), merge(gaps=((4, 7),)), results(), [(4, 7)])
    assert any("active-audio gap" in reason for reason in validation.reasons)


def test_abnormal_transcript_shrinkage_is_rejected():
    three_plans = [
        PlannedChunk(1, 0, 10, "silence", 0.2),
        PlannedChunk(2, 9.8, 20, "silence", 0.2),
        PlannedChunk(3, 19.8, 30, "final", 0),
    ]
    chunks = [
        HybridChunkResult(1, 0, 10, "這是足夠長度的第一段文字內容", ""),
        HybridChunkResult(2, 9.8, 20, "字", ""),
        HybridChunkResult(3, 19.8, 30, "這是足夠長度的第三段文字內容", ""),
    ]
    validation = validate_hybrid_result(three_plans, merge(), chunks, [(0, 30)])
    assert any("abnormal text density" in reason for reason in validation.reasons)


def test_repeated_paragraph_is_rejected():
    validation = validate_hybrid_result(plans(), merge(text="相同句子。相同句子。"), results(), [(0, 20)])
    assert any("repeated sentence" in reason for reason in validation.reasons)


def test_valid_output_passes():
    validation = validate_hybrid_result(plans(), merge(gaps=((8, 9),)), results(), [(0, 8), (9, 20)])
    assert validation.ok, validation.reasons


def test_invalid_output_uses_batch_once():
    calls = []
    validation = validate_hybrid_result(plans(), merge(gaps=((4, 7),)), results(), [(4, 7)])
    outcome = resolve_with_batch_fallback(validation, "unsafe partial", lambda: calls.append(1) or "safe batch")
    assert outcome.text == "safe batch"
    assert outcome.fallback_used is True
    assert calls == [1]


def test_short_timestamp_gap_is_tolerated():
    validation = validate_hybrid_result(plans(), merge(gaps=((4, 5.5),)), results(), [(4, 5.5)])
    assert validation.ok, validation.reasons
