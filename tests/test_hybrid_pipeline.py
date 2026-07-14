from pathlib import Path
import threading
import time

import numpy as np

from speedytype.chunking import ChunkingConfig
from speedytype.hybrid_pipeline import HybridTranscriber


def config(**changes):
    values = dict(
        hybrid_threshold_seconds=2.0,
        min_chunk_seconds=1.0,
        preferred_chunk_seconds=2.0,
        max_chunk_seconds=3.0,
        minimum_silence_seconds=0.4,
        natural_cut_context_seconds=0.1,
        forced_cut_overlap_seconds=0.5,
        analysis_frame_ms=20,
        noise_floor_window_seconds=1.0,
    )
    values.update(changes)
    return ChunkingConfig(**values)


def speech(seconds, sample_rate=100):
    return np.full((int(seconds * sample_rate), 1), 0.2, dtype=np.float32)


def fake_verbose(calls, fail_at=None, blocker=None):
    def transcribe(path, *, prompt_override=""):
        index = len(calls) + 1
        calls.append(Path(path))
        if blocker is not None:
            blocker.wait(2)
        if index == fail_at:
            raise RuntimeError("HTTP 429")
        import soundfile as sf
        duration = sf.info(path).duration
        return {"text": f"第{index}段", "segments": [{"start": 0.0, "end": duration, "text": f"第{index}段"}]}
    return transcribe


def test_under_threshold_uses_batch_without_chunk_requests(tmp_path):
    calls = []
    batches = []
    transcriber = HybridTranscriber(
        config(), fake_verbose(calls), lambda path: batches.append(path) or "batch text", sample_rate=100
    )
    transcriber.feed(speech(1.5), 1.5)
    outcome = transcriber.finish(tmp_path / "full.wav")
    assert outcome.raw_text == "batch text"
    assert outcome.fallback_used is False
    assert calls == []
    assert batches == [tmp_path / "full.wav"]
    assert outcome.request_count == 1


def test_natural_silence_closes_chunk(tmp_path):
    calls = []
    audio = speech(6)
    audio[190:250] = 0.001
    transcriber = HybridTranscriber(config(), fake_verbose(calls), lambda path: "batch", sample_rate=100)
    transcriber.feed(audio, 6.0)
    outcome = transcriber.finish(tmp_path / "full.wav")
    assert "silence" in outcome.diagnostics["cut_reasons"]
    assert outcome.request_count >= 2


def test_continuous_speech_uses_forced_cut(tmp_path):
    calls = []
    transcriber = HybridTranscriber(config(), fake_verbose(calls), lambda path: "batch", sample_rate=100)
    transcriber.feed(speech(7), 7.0)
    outcome = transcriber.finish(tmp_path / "full.wav")
    assert "forced" in outcome.diagnostics["cut_reasons"]


def test_finish_waits_for_inflight_request(tmp_path):
    calls = []
    blocker = threading.Event()
    transcriber = HybridTranscriber(config(), fake_verbose(calls, blocker=blocker), lambda path: "batch", sample_rate=100)
    transcriber.feed(speech(7), 7.0)
    timer = threading.Timer(0.1, blocker.set)
    timer.start()
    outcome = transcriber.finish(tmp_path / "full.wav")
    assert outcome.request_count > 0
    timer.cancel()


def test_request_failure_falls_back_to_batch(tmp_path):
    calls = []
    batches = []
    transcriber = HybridTranscriber(
        config(), fake_verbose(calls, fail_at=1), lambda path: batches.append(path) or "safe batch", sample_rate=100
    )
    transcriber.feed(speech(7), 7.0)
    outcome = transcriber.finish(tmp_path / "full.wav")
    assert outcome.raw_text == "safe batch"
    assert outcome.fallback_used is True
    assert len(batches) == 1
    assert outcome.request_count == len(calls) + len(batches)


def test_every_chunk_uses_vocab_bias_without_prior_narrative(tmp_path):
    prompts = []

    def verbose(path, *, prompt_override=""):
        prompts.append(prompt_override)
        import soundfile as sf
        duration = sf.info(path).duration
        text = f"內容{len(prompts)}"
        return {"text": text, "segments": [{"start": 0, "end": duration, "text": text}]}

    transcriber = HybridTranscriber(config(), verbose, lambda path: "batch", sample_rate=100, initial_prompt="BIOS, API")
    transcriber.feed(speech(7), 7)
    transcriber.finish(tmp_path / "full.wav")
    assert len(prompts) >= 2
    assert set(prompts) == {"BIOS, API"}


def test_feed_does_not_run_slow_vad_on_audio_callback_thread(monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    def slow_detect(*args, **kwargs):
        entered.set()
        release.wait(2)
        return []

    monkeypatch.setattr("speedytype.hybrid_pipeline.detect_silence_regions", slow_detect)
    transcriber = HybridTranscriber(config(), lambda *args, **kwargs: {}, lambda path: "batch", sample_rate=100)
    started = time.perf_counter()
    transcriber.feed(speech(3), 3)
    elapsed = time.perf_counter() - started
    assert entered.wait(1)
    assert elapsed < 0.05
    release.set()
