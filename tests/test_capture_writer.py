from __future__ import annotations

from threading import Event
import os

import numpy as np
import pytest
import soundfile as sf

from speedytype.capture_writer import (
    CaptureQueueFull,
    CaptureWriteError,
    SampleIndexedWavWriter,
)


def test_writer_preserves_block_order_and_exact_frame_counts(tmp_path):
    path = tmp_path / "capture.wav"
    writer = SampleIndexedWavWriter(path, sample_rate=16_000, channels=1)
    blocks = [
        np.full((13, 1), 0.1, dtype="float32"),
        np.full((7, 1), -0.2, dtype="float32"),
        np.full((5, 1), 0.3, dtype="float32"),
    ]

    for block in blocks:
        writer.submit(block)
    stats = writer.finish()

    decoded, rate = sf.read(path, dtype="float32", always_2d=True)
    expected = np.concatenate(blocks)
    assert rate == 16_000
    assert len(decoded) == len(expected) == 25
    assert np.allclose(decoded, expected, atol=1 / 32768)
    assert stats.submitted_frames == stats.written_frames == 25
    assert stats.submitted_blocks == stats.written_blocks == 3


def test_writer_fsyncs_completed_real_wav_after_close(tmp_path, monkeypatch):
    path = tmp_path / "capture.wav"
    descriptors = []
    real_fsync = os.fsync

    def track_fsync(descriptor):
        descriptors.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", track_fsync)
    writer = SampleIndexedWavWriter(path, sample_rate=16_000, channels=1)
    writer.submit(np.zeros((16, 1), dtype="float32"))

    writer.finish()

    assert len(descriptors) == 1


class _BlockingSink:
    def __init__(self, entered: Event, release: Event):
        self.entered = entered
        self.release = release

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def write(self, _block):
        self.entered.set()
        assert self.release.wait(2)

    def flush(self):
        pass


def test_writer_refuses_when_bounded_queue_is_full(tmp_path):
    entered = Event()
    release = Event()
    writer = SampleIndexedWavWriter(
        tmp_path / "capture.wav",
        sample_rate=16_000,
        channels=1,
        queue_capacity=1,
        sound_file_factory=lambda *args, **kwargs: _BlockingSink(entered, release),
    )
    block = np.zeros((4, 1), dtype="float32")
    writer.submit(block)
    assert entered.wait(2)
    writer.submit(block)

    with pytest.raises(CaptureQueueFull):
        writer.submit(block)

    release.set()
    writer.finish()


class _FailingSink:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def write(self, _block):
        raise OSError("disk failed")

    def flush(self):
        pass


def test_writer_surfaces_background_write_failure_on_finish(tmp_path):
    writer = SampleIndexedWavWriter(
        tmp_path / "capture.wav",
        sample_rate=16_000,
        channels=1,
        sound_file_factory=lambda *args, **kwargs: _FailingSink(),
    )
    writer.submit(np.zeros((100, 1), dtype="float32"))

    with pytest.raises(CaptureWriteError, match="background WAV writer failed"):
        writer.finish()


class _CountingSink:
    def __init__(self):
        self.frames = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def write(self, block):
        self.frames += len(block)

    def flush(self):
        pass


def test_writer_synthetic_thirty_minute_stress_conserves_28_8m_frames(tmp_path):
    sink = _CountingSink()
    writer = SampleIndexedWavWriter(
        tmp_path / "stress.wav",
        sample_rate=16_000,
        channels=1,
        queue_capacity=2_048,
        sound_file_factory=lambda *args, **kwargs: sink,
    )
    block = np.zeros((16_000, 1), dtype="float32")

    for _ in range(1_800):
        writer.submit(block)
    stats = writer.finish()

    assert sink.frames == 28_800_000
    assert stats.submitted_frames == stats.written_frames == 28_800_000
