from __future__ import annotations

from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import sounddevice as sd
import soundfile as sf
from PyQt6.QtWidgets import QApplication

from speedytype.audio import Recorder
from speedytype.overlay import AudioLevelEmitter, RecordingPill


def run_condition(app, pill, emitter, recorder, name: str, seconds: float, play_path: Path | None, gain: float) -> list[tuple[float, float, float]]:
    samples: list[tuple[float, float, float]] = []
    started = time.perf_counter()

    def on_level(rms: float) -> None:
        elapsed = time.perf_counter() - started
        emitter.level_changed.emit(rms)
        app.processEvents()
        height = pill._bar_heights[-1]
        samples.append((elapsed, rms, height))

    tmp_wav = Path(f"scratch_volume_probe_{name}.wav")
    import threading

    record_thread = threading.Thread(target=lambda: recorder.record_until_stop(tmp_wav, on_level=on_level, level_interval_seconds=0.12))
    record_thread.start()
    time.sleep(0.3)
    if play_path is not None:
        data, sr = sf.read(play_path, dtype="float32")
        data = np.clip(data * gain, -0.98, 0.98)
        sd.play(data, sr)
    end_time = time.perf_counter() + seconds
    while time.perf_counter() < end_time:
        app.processEvents()
        time.sleep(0.02)
    recorder.stop()
    record_thread.join()
    tmp_wav.unlink(missing_ok=True)

    pill.grab().save(f"scratch_volume_bars_{name}.png")
    return samples


def main() -> int:
    app = QApplication(sys.argv)
    pill = RecordingPill()
    emitter = AudioLevelEmitter()
    emitter.level_changed.connect(pill.update_level)
    recorder = Recorder(device=1)

    pill.show_recording()
    app.processEvents()

    conditions = [
        ("quiet_ambient", 4.0, None, 1.0),
        ("normal_playback", 5.0, Path("test_audio/short_16k.wav"), 1.0),
        ("loud_playback", 5.0, Path("test_audio/short_16k.wav"), 6.0),
    ]

    all_results = {}
    for name, seconds, play_path, gain in conditions:
        samples = run_condition(app, pill, emitter, recorder, name, seconds, play_path, gain)
        all_results[name] = samples
        rms_values = [s[1] for s in samples]
        height_values = [s[2] for s in samples]
        avg_rms = sum(rms_values) / len(rms_values) if rms_values else 0.0
        max_rms = max(rms_values) if rms_values else 0.0
        avg_h = sum(height_values) / len(height_values) if height_values else 0.0
        max_h = max(height_values) if height_values else 0.0
        print(f"CONDITION={name} n={len(samples)} avg_rms={avg_rms:.6f} max_rms={max_rms:.6f} avg_bar_height={avg_h:.2f} max_bar_height={max_h:.2f}")
        for elapsed, rms, height in samples:
            print(f"  t={elapsed:.2f}s rms={rms:.6f} bar_height={height:.2f}")
        time.sleep(0.5)

    pill.hide_pill()
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
