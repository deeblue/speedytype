import numpy as np

from speedytype.chunking import ChunkingConfig, SilenceRegion, detect_silence_regions, plan_dynamic_chunks


def signal_with_silence(duration: float, start: float, end: float, sample_rate: int = 1000) -> np.ndarray:
    samples = np.full(int(duration * sample_rate), 0.2, dtype=np.float32)
    samples[int(start * sample_rate):int(end * sample_rate)] = 0.005
    return samples


def test_detects_silence_longer_than_minimum():
    regions = detect_silence_regions(signal_with_silence(30, 24.5, 25.3), 1000, ChunkingConfig())
    assert any(region.start_seconds <= 24.55 and region.end_seconds >= 25.25 for region in regions)


def test_ignores_short_breath():
    regions = detect_silence_regions(signal_with_silence(30, 24.8, 25.2), 1000, ChunkingConfig())
    assert regions == []


def test_planner_prefers_natural_silence_near_25_seconds():
    chunks = plan_dynamic_chunks(60.0, [SilenceRegion(24.5, 25.3, 0.005), SilenceRegion(31, 32, 0.005)], ChunkingConfig())
    assert chunks[0].cut_reason == "silence"
    assert 24.8 <= chunks[0].end_seconds <= 25.1
    assert chunks[0].overlap_seconds == 0.2


def test_planner_ignores_silence_before_minimum():
    chunks = plan_dynamic_chunks(50.0, [SilenceRegion(8, 9, 0.005)], ChunkingConfig())
    assert chunks[0].cut_reason == "forced"
    assert chunks[0].end_seconds == 45.0


def test_continuous_speech_forces_cut_with_overlap():
    chunks = plan_dynamic_chunks(70.0, [], ChunkingConfig())
    assert chunks[0].cut_reason == "forced"
    assert chunks[0].end_seconds == 45.0
    assert chunks[0].overlap_seconds == 1.5
    assert chunks[1].start_seconds == 43.5


def test_trailing_audio_is_fully_covered():
    chunks = plan_dynamic_chunks(52.0, [SilenceRegion(24.6, 25.4, 0.005)], ChunkingConfig())
    assert chunks[-1].end_seconds == 52.0
    assert chunks[-1].cut_reason == "final"
    assert min(chunk.start_seconds for chunk in chunks) == 0.0
    for left, right in zip(chunks, chunks[1:]):
        assert right.start_seconds <= left.end_seconds
