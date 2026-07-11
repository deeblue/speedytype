from __future__ import annotations

from pathlib import Path
from typing import Callable
import tempfile
import threading
import time

import sounddevice as sd
import soundfile as sf
import numpy as np


SAMPLE_RATE = 16000
CHANNELS = 1


def list_input_devices() -> list[dict[str, object]]:
    devices = []
    for index, device in enumerate(sd.query_devices()):
        if device["max_input_channels"] > 0:
            devices.append(
                {
                    "index": index,
                    "name": device["name"],
                    "hostapi": device["hostapi"],
                    "max_input_channels": device["max_input_channels"],
                    "default_samplerate": device["default_samplerate"],
                }
            )
    return devices


def list_input_device_names() -> list[str]:
    """Names of currently available input devices, for a UI picker. Order
    matches list_input_devices()/sd.query_devices() enumeration order."""
    return [str(device["name"]) for device in list_input_devices()]


def find_input_device_index_by_name(name: str) -> int | None:
    """Exact-name lookup among currently available input devices (used to
    resolve a device name saved in settings.json back to a live index at
    startup). Returns None if no current input device has that exact name."""
    if not name:
        return None
    for index, device in enumerate(sd.query_devices()):
        if device["max_input_channels"] > 0 and str(device["name"]) == name:
            return index
    return None


def resolve_input_device(device_hint: str | int | None) -> int | None:
    if device_hint in (None, ""):
        default_input = sd.default.device[0]
        return None if default_input in (-1, None) else int(default_input)
    if isinstance(device_hint, int):
        return device_hint
    text = str(device_hint).strip()
    if text.isdigit():
        return int(text)
    lowered = text.lower()
    for index, device in enumerate(sd.query_devices()):
        if device["max_input_channels"] > 0 and lowered in str(device["name"]).lower():
            return index
    raise RuntimeError(f"Input device not found for MIC_DEVICE={device_hint!r}")


class Recorder:
    def __init__(self, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS, device: str | int | None = None):
        self.sample_rate = sample_rate
        self.channels = channels
        self.device = resolve_input_device(device)
        self._stop_event = threading.Event()

    def record_until_stop(
        self,
        output_path: Path,
        on_level: Callable[[float], None] | None = None,
        level_interval_seconds: float = 0.12,
    ) -> float:
        """Record until `stop()` is called.

        If `on_level` is given, it is called with the RMS amplitude (0.0-1.0
        range for normalized float audio) of the most recent audio block, at
        most once every `level_interval_seconds`, so a UI can show real-time
        volume feedback without being flooded by every low-level audio
        callback.
        """
        self._stop_event.clear()
        started = time.perf_counter()
        last_level_emit = 0.0
        with sf.SoundFile(output_path, mode="w", samplerate=self.sample_rate, channels=self.channels, subtype="PCM_16") as wav_file:
            def callback(indata, frames, time_info, status):
                nonlocal last_level_emit
                if status:
                    print(f"Recording warning: {status}", flush=True)
                wav_file.write(indata.copy())
                if on_level is not None:
                    now = time.perf_counter()
                    if now - last_level_emit >= level_interval_seconds:
                        rms = float(np.sqrt(np.mean(np.square(indata)))) if indata.size else 0.0
                        on_level(rms)
                        last_level_emit = now

            with sd.InputStream(samplerate=self.sample_rate, channels=self.channels, device=self.device, callback=callback):
                while not self._stop_event.is_set():
                    time.sleep(0.02)
            wav_file.flush()
        return time.perf_counter() - started

    def stop(self) -> None:
        self._stop_event.set()


def temp_wav_path(prefix: str = "speedytype_") -> Path:
    handle = tempfile.NamedTemporaryFile(prefix=prefix, suffix=".wav", delete=False)
    path = Path(handle.name)
    handle.close()
    return path


def record_diagnostic(output_path: Path, seconds: float = 2.0, device: str | int | None = None) -> dict[str, float | int | str]:
    chunks: list[np.ndarray] = []

    def callback(indata, frames, time_info, status):
        if status:
            print(f"Recording warning: {status}", flush=True)
        chunks.append(indata.copy())

    resolved = resolve_input_device(device)
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, device=resolved, callback=callback):
        sd.sleep(int(seconds * 1000))

    audio = np.concatenate(chunks, axis=0) if chunks else np.zeros((0, 1), dtype="float32")
    sf.write(output_path, audio, SAMPLE_RATE, subtype="PCM_16")
    rms = float(np.sqrt(np.mean(np.square(audio)))) if len(audio) else 0.0
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    return {
        "device_index": -1 if resolved is None else int(resolved),
        "seconds": float(seconds),
        "samples": int(len(audio)),
        "rms": rms,
        "peak": peak,
        "path": str(output_path.resolve()),
    }
