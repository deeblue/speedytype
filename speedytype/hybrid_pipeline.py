from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import queue
import re
import tempfile
import threading
import time

import numpy as np
import soundfile as sf

from speedytype.chunking import ChunkingConfig, PlannedChunk, SilenceRegion, detect_silence_regions, plan_dynamic_chunks
from speedytype.hybrid_validation import HybridChunkResult, resolve_with_batch_fallback, validate_hybrid_result
from speedytype.segment_merge import TimedSegment, merge_timed_segments


@dataclass(frozen=True)
class HybridOutcome:
    raw_text: str
    tail_seconds: float
    request_seconds: float
    request_count: int
    fallback_used: bool
    diagnostics: dict[str, object]


@dataclass
class _CompletedChunk:
    plan: PlannedChunk
    request_seconds: float
    text: str
    segments: list[TimedSegment]
    error: str = ""
    request_attempted: bool = False


class HybridTranscriber:
    def __init__(
        self,
        config: ChunkingConfig,
        verbose_transcribe,
        batch_transcribe,
        *,
        sample_rate: int = 16000,
        initial_prompt: str = "",
    ) -> None:
        self.config = config
        self.verbose_transcribe = verbose_transcribe
        self.batch_transcribe = batch_transcribe
        self.sample_rate = sample_rate
        self._initial_prompt = initial_prompt.strip()
        self._audio: list[np.ndarray] = []
        self._audio_lock = threading.Lock()
        self._sample_count = 0
        self._duration = 0.0
        self._active = False
        self._queue: queue.Queue[PlannedChunk | None] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._planner_thread: threading.Thread | None = None
        self._planner_event = threading.Event()
        self._planner_stop = threading.Event()
        self._queued: set[tuple[float, float]] = set()
        self._plans: dict[tuple[float, float], PlannedChunk] = {}
        self._completed: list[_CompletedChunk] = []
        self._lock = threading.Lock()
        self._consecutive_retryable_failures = 0
        self._circuit_open = False
        self._max_backlog = 0

    @staticmethod
    def request_limit(duration_seconds: float, config: ChunkingConfig) -> int:
        return max(1, math.ceil(duration_seconds / config.min_chunk_seconds) + 1)

    def feed(self, samples: np.ndarray, timestamp: float) -> None:
        block = np.asarray(samples, dtype=np.float32).copy()
        if block.ndim == 1:
            block = block[:, None]
        with self._audio_lock:
            self._audio.append(block)
            self._sample_count += len(block)
            self._duration = self._sample_count / self.sample_rate
        if not self._active and self._duration >= self.config.hybrid_threshold_seconds:
            self._active = True
            self._worker = threading.Thread(target=self._run_worker, daemon=True)
            self._worker.start()
            self._planner_thread = threading.Thread(target=self._run_planner, daemon=True)
            self._planner_thread.start()
        if self._active:
            self._planner_event.set()

    def _all_audio(self) -> np.ndarray:
        with self._audio_lock:
            blocks = list(self._audio)
        return np.concatenate(blocks, axis=0) if blocks else np.zeros((0, 1), dtype=np.float32)

    def _run_planner(self) -> None:
        while True:
            self._planner_event.wait()
            self._planner_event.clear()
            if self._planner_stop.is_set():
                return
            self._enqueue_closed_chunks(include_final=False)

    def _current_plan(self) -> tuple[list[PlannedChunk], list[SilenceRegion]]:
        audio = self._all_audio()
        silences = detect_silence_regions(audio, self.sample_rate, self.config)
        return plan_dynamic_chunks(len(audio) / self.sample_rate, silences, self.config), silences

    def _enqueue_closed_chunks(self, *, include_final: bool) -> None:
        plans, _ = self._current_plan()
        selected = plans if include_final else plans[:-1]
        for plan in selected:
            key = (plan.start_seconds, plan.end_seconds)
            if key in self._queued:
                continue
            if len(self._queued) >= self.request_limit(self._duration, self.config):
                continue
            self._queued.add(key)
            self._plans[key] = plan
            self._queue.put(plan)
            self._max_backlog = max(self._max_backlog, self._queue.qsize())

    def _run_worker(self) -> None:
        while True:
            plan = self._queue.get()
            try:
                if plan is None:
                    return
                self._process_chunk(plan)
            finally:
                self._queue.task_done()

    def _process_chunk(self, plan: PlannedChunk) -> None:
        if self._circuit_open:
            with self._lock:
                self._completed.append(_CompletedChunk(plan, 0.0, "", [], "circuit open after repeated API failures"))
            return
        audio = self._all_audio()
        start = max(0, int(plan.start_seconds * self.sample_rate))
        end = min(len(audio), int(plan.end_seconds * self.sample_rate))
        handle = tempfile.NamedTemporaryFile(prefix="speedytype_hybrid_", suffix=".wav", delete=False)
        path = Path(handle.name)
        handle.close()
        sf.write(path, audio[start:end], self.sample_rate, subtype="PCM_16")
        started = time.perf_counter()
        try:
            payload = self.verbose_transcribe(path, prompt_override=self._initial_prompt)
            request_seconds = time.perf_counter() - started
            segments = [
                TimedSegment(
                    plan.start_seconds + float(segment.get("start", 0.0)),
                    plan.start_seconds + float(segment.get("end", 0.0)),
                    str(segment.get("text", "")).strip(),
                    plan.index,
                )
                for segment in payload.get("segments", []) or []
            ]
            completed = _CompletedChunk(
                plan,
                request_seconds,
                str(payload.get("text", "")).strip(),
                segments,
                request_attempted=True,
            )
            self._consecutive_retryable_failures = 0
        except Exception as exc:
            completed = _CompletedChunk(
                plan,
                time.perf_counter() - started,
                "",
                [],
                f"{type(exc).__name__}: {exc}",
                request_attempted=True,
            )
            message = str(exc).lower()
            if "429" in message or re.search(r"\b5\d\d\b", message):
                self._consecutive_retryable_failures += 1
                if self._consecutive_retryable_failures >= 2:
                    self._circuit_open = True
        finally:
            path.unlink(missing_ok=True)
        with self._lock:
            self._completed.append(completed)

    @staticmethod
    def _activity_intervals(duration: float, silences: list[SilenceRegion]) -> list[tuple[float, float]]:
        intervals = []
        cursor = 0.0
        for silence in silences:
            if silence.start_seconds > cursor:
                intervals.append((cursor, silence.start_seconds))
            cursor = max(cursor, silence.end_seconds)
        if cursor < duration:
            intervals.append((cursor, duration))
        return intervals

    def finish(self, final_path: Path) -> HybridOutcome:
        tail_started = time.perf_counter()
        if not self._active:
            text = self.batch_transcribe(final_path)
            return HybridOutcome(text, time.perf_counter() - tail_started, 0.0, 1, False, {"mode": "batch"})

        self._planner_stop.set()
        self._planner_event.set()
        if self._planner_thread is not None:
            self._planner_thread.join()
        self._enqueue_closed_chunks(include_final=True)
        self._queue.join()
        self._queue.put(None)
        self._queue.join()
        if self._worker is not None:
            self._worker.join(timeout=2)

        completed = sorted(self._completed, key=lambda item: item.plan.start_seconds)
        plans = [item.plan for item in completed]
        merge = merge_timed_segments([item.segments for item in completed], self._duration)
        _, silences = self._current_plan()
        chunks = [
            HybridChunkResult(
                item.plan.index,
                item.plan.start_seconds,
                item.plan.end_seconds,
                item.text,
                item.error,
            )
            for item in completed
        ]
        validation = validate_hybrid_result(
            plans,
            merge,
            chunks,
            self._activity_intervals(self._duration, silences),
        )
        resolved = resolve_with_batch_fallback(validation, merge.text, lambda: self.batch_transcribe(final_path))
        request_seconds = sum(item.request_seconds for item in completed)
        request_count = sum(item.request_attempted for item in completed) + int(resolved.fallback_used)
        return HybridOutcome(
            resolved.text,
            time.perf_counter() - tail_started,
            request_seconds,
            request_count,
            resolved.fallback_used,
            {
                "mode": "hybrid",
                "cut_reasons": [item.plan.cut_reason for item in completed],
                "validation_reasons": list(validation.reasons),
                "merge_gaps": list(merge.gaps),
                "circuit_open": self._circuit_open,
                "request_limit": self.request_limit(self._duration, self.config),
                "max_backlog": self._max_backlog,
            },
        )
