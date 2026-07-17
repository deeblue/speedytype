from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from typing import Any, Callable

import numpy as np
import soundfile as sf


class CaptureQueueFull(RuntimeError):
    pass


class CaptureWriteError(RuntimeError):
    pass


@dataclass(frozen=True)
class CaptureWriteStats:
    submitted_frames: int
    written_frames: int
    submitted_blocks: int
    written_blocks: int


@dataclass(frozen=True)
class _Block:
    start_frame: int
    end_frame: int
    samples: np.ndarray


_STOP = object()


class SampleIndexedWavWriter:
    def __init__(
        self,
        path: Path,
        *,
        sample_rate: int,
        channels: int,
        queue_capacity: int = 256,
        sound_file_factory: Callable[..., Any] = sf.SoundFile,
    ) -> None:
        if sample_rate <= 0 or channels <= 0 or queue_capacity <= 0:
            raise ValueError("writer format and queue capacity must be positive")
        self.path = Path(path)
        self.sample_rate = sample_rate
        self.channels = channels
        self._queue: Queue[object] = Queue(maxsize=queue_capacity)
        self._factory = sound_file_factory
        self._lock = Lock()
        self._ready = Event()
        self._finished = False
        self._submitted_frames = 0
        self._submitted_blocks = 0
        self._written_frames = 0
        self._written_blocks = 0
        self._error: BaseException | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._thread = Thread(target=self._run, name="speedytype-wav-writer", daemon=False)
        self._thread.start()
        if not self._ready.wait(5):
            raise CaptureWriteError("background WAV writer did not initialize")
        if self._error is not None:
            raise CaptureWriteError("background WAV writer failed to initialize") from self._error

    def submit(self, samples: np.ndarray) -> None:
        values = np.asarray(samples)
        if values.ndim != 2 or values.shape[1] != self.channels:
            raise ValueError("capture block channel count does not match writer")
        copied = np.array(values, copy=True)
        with self._lock:
            if self._finished:
                raise CaptureWriteError("cannot submit after writer finish")
            if self._error is not None:
                raise CaptureWriteError("background WAV writer failed") from self._error
            start = self._submitted_frames
            block = _Block(start, start + len(copied), copied)
            try:
                self._queue.put_nowait(block)
            except Full as exc:
                raise CaptureQueueFull("capture writer queue is full") from exc
            self._submitted_frames = block.end_frame
            self._submitted_blocks += 1

    def finish(self) -> CaptureWriteStats:
        with self._lock:
            if not self._finished:
                self._finished = True
                should_stop = True
            else:
                should_stop = False
        if should_stop:
            self._queue.put(_STOP)
            self._thread.join()
        stats = CaptureWriteStats(
            submitted_frames=self._submitted_frames,
            written_frames=self._written_frames,
            submitted_blocks=self._submitted_blocks,
            written_blocks=self._written_blocks,
        )
        if self._error is not None:
            raise CaptureWriteError("background WAV writer failed") from self._error
        if stats.submitted_frames != stats.written_frames:
            raise CaptureWriteError("captured WAV frame conservation failed")
        return stats

    def _run(self) -> None:
        try:
            with self._factory(
                self.path,
                mode="w",
                samplerate=self.sample_rate,
                channels=self.channels,
                subtype="PCM_16",
            ) as wav_file:
                self._ready.set()
                expected_frame = 0
                while True:
                    item = self._queue.get()
                    try:
                        if item is _STOP:
                            break
                        block = item
                        if not isinstance(block, _Block):
                            raise RuntimeError("unexpected capture queue item")
                        if self._error is not None:
                            continue
                        if block.start_frame != expected_frame:
                            raise RuntimeError("capture block frame order mismatch")
                        wav_file.write(block.samples)
                        expected_frame = block.end_frame
                        self._written_frames = expected_frame
                        self._written_blocks += 1
                    except BaseException as exc:
                        if self._error is None:
                            self._error = exc
                    finally:
                        self._queue.task_done()
                if self._error is None:
                    wav_file.flush()
        except BaseException as exc:
            if self._error is None:
                self._error = exc
            self._ready.set()
            while True:
                try:
                    item = self._queue.get_nowait()
                except Empty:
                    break
                else:
                    self._queue.task_done()
