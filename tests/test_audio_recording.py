from __future__ import annotations

from threading import Thread
import time

import numpy as np

from speedytype.audio import Recorder, temp_wav_path
from speedytype.recording_recovery import recording_sidecar_path


def test_temp_wav_path_is_owned_and_starts_recovery_metadata(tmp_path):
    path = temp_wav_path(directory=tmp_path)

    assert path.parent == tmp_path
    assert path.suffix == ".wav"
    assert recording_sidecar_path(path).exists()


def test_recorder_drains_writer_then_marks_capture_complete(tmp_path, monkeypatch):
    path = temp_wav_path(directory=tmp_path)
    callbacks = []

    class FakeStream:
        def __init__(self, *, callback, **_kwargs):
            callbacks.append(callback)

        def __enter__(self):
            callbacks[0](np.ones((160, 1), dtype="float32") * 0.1, 160, None, None)
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("speedytype.audio.sd.InputStream", FakeStream)
    recorder = Recorder()
    worker = Thread(target=recorder.record_until_stop, args=(path,))
    worker.start()
    time.sleep(0.03)
    recorder.stop()
    worker.join(2)

    assert not worker.is_alive()
    assert recorder.last_write_stats is not None
    assert recorder.last_write_stats.written_frames == 160
    assert '"state": "captured"' in recording_sidecar_path(path).read_text(encoding="utf-8")
