import threading
import time

import numpy as np

from speedytype.chunking import ChunkingConfig
from speedytype.hybrid_pipeline import HybridTranscriber


def tiny_config():
    return ChunkingConfig(
        hybrid_threshold_seconds=1,
        min_chunk_seconds=1,
        preferred_chunk_seconds=1.5,
        max_chunk_seconds=2,
        minimum_silence_seconds=0.4,
        analysis_frame_ms=20,
        noise_floor_window_seconds=1,
    )


def test_request_ceiling_is_derived_from_duration_and_minimum_chunk():
    assert HybridTranscriber.request_limit(90, tiny_config()) == 91


def test_repeated_throttling_opens_circuit_and_falls_back(tmp_path):
    calls = []
    batches = []

    def throttled(path, *, prompt_override=""):
        calls.append(path)
        raise RuntimeError("HTTP 429 quota")

    transcriber = HybridTranscriber(tiny_config(), throttled, lambda path: batches.append(path) or "batch", sample_rate=100)
    transcriber.feed(np.full((1000, 1), 0.2, dtype=np.float32), 10)
    outcome = transcriber.finish(tmp_path / "full.wav")
    assert len(calls) == 2
    assert outcome.fallback_used
    assert batches == [tmp_path / "full.wav"]
    assert outcome.diagnostics["circuit_open"] is True


def test_worker_never_runs_requests_concurrently(tmp_path):
    lock = threading.Lock()
    active = 0
    maximum = 0

    def verbose(path, *, prompt_override=""):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.01)
        with lock:
            active -= 1
        import soundfile as sf
        duration = sf.info(path).duration
        return {"text": "內容", "segments": [{"start": 0, "end": duration, "text": "內容"}]}

    transcriber = HybridTranscriber(tiny_config(), verbose, lambda path: "batch", sample_rate=100)
    transcriber.feed(np.full((800, 1), 0.2, dtype=np.float32), 8)
    transcriber.finish(tmp_path / "full.wav")
    assert maximum == 1
