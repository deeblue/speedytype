from __future__ import annotations

import json
import os

import pytest

from speedytype.recording_recovery import (
    create_recording_path,
    discover_recoverable_recordings,
    mark_recording,
    recording_sidecar_path,
    remove_unconfirmed_recording,
)


def test_create_and_mark_recording_writes_atomic_recovery_sidecar(tmp_path):
    wav = create_recording_path(directory=tmp_path)
    sidecar = recording_sidecar_path(wav)

    initial = json.loads(sidecar.read_text(encoding="utf-8"))
    assert wav.exists()
    assert initial["state"] == "capturing"
    assert initial["recording_id"]
    assert not list(tmp_path.glob("*.tmp"))
    assert mark_recording(wav, "captured") is True
    assert json.loads(sidecar.read_text(encoding="utf-8"))["state"] == "captured"
    assert not list(tmp_path.glob("*.tmp"))


def test_recovery_metadata_is_fsynced_before_atomic_replace(tmp_path, monkeypatch):
    descriptors = []
    real_fsync = os.fsync

    def track_fsync(descriptor):
        descriptors.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", track_fsync)

    wav = create_recording_path(directory=tmp_path)
    mark_recording(wav, "captured")

    assert len(descriptors) == 2


def test_invalid_recovery_transition_is_rejected_without_rewriting(tmp_path):
    wav = create_recording_path(directory=tmp_path)
    sidecar = recording_sidecar_path(wav)
    original = sidecar.read_bytes()

    with pytest.raises(ValueError, match="transition"):
        mark_recording(wav, "completed")

    assert sidecar.read_bytes() == original


def test_mark_external_wav_without_owned_sidecar_is_noop(tmp_path):
    wav = tmp_path / "external.wav"
    wav.write_bytes(b"external")

    assert mark_recording(wav, "captured") is False
    assert not recording_sidecar_path(wav).exists()


def test_discovery_returns_only_incomplete_records_and_sanitized_categories(tmp_path):
    captured = create_recording_path(directory=tmp_path)
    mark_recording(captured, "captured")
    failed = create_recording_path(directory=tmp_path)
    mark_recording(failed, "failed-retained", error_category="EncoderError")
    completed = create_recording_path(directory=tmp_path)
    mark_recording(completed, "captured")
    mark_recording(completed, "encoding")
    mark_recording(completed, "ready")
    mark_recording(completed, "processing")
    mark_recording(completed, "completed")

    records = discover_recoverable_recordings(tmp_path)

    assert {record.wav_path for record in records} == {captured, failed}
    assert {record.state for record in records} == {"captured", "failed-retained"}
    assert next(record for record in records if record.wav_path == failed).error_category == "EncoderError"


def test_discovery_reports_corrupt_sidecar_without_importing_provider_api(tmp_path, monkeypatch):
    wav = tmp_path / "owned.wav"
    wav.write_bytes(b"wav")
    recording_sidecar_path(wav).write_text("{broken", encoding="utf-8")

    records = discover_recoverable_recordings(tmp_path)

    assert len(records) == 1
    assert records[0].wav_path == wav
    assert records[0].state == "corrupt"
    assert records[0].metadata_valid is False


@pytest.mark.parametrize("state", ["capturing", "captured"])
def test_remove_unconfirmed_recording_deletes_only_owned_provisional_pair(
    tmp_path, state
):
    wav = create_recording_path(directory=tmp_path)
    wav.write_bytes(b"wav")
    if state == "captured":
        mark_recording(wav, "captured")
    sidecar = recording_sidecar_path(wav)

    assert remove_unconfirmed_recording(wav) is True
    assert not wav.exists()
    assert not sidecar.exists()


@pytest.mark.parametrize(
    "state",
    ["encoding", "ready", "processing", "failed-retained"],
)
def test_remove_unconfirmed_recording_refuses_protected_states(tmp_path, state):
    wav = create_recording_path(directory=tmp_path)
    wav.write_bytes(b"valid evidence")
    mark_recording(wav, "captured")
    if state == "encoding":
        mark_recording(wav, "encoding")
    elif state == "ready":
        mark_recording(wav, "encoding")
        mark_recording(wav, "ready")
    elif state == "processing":
        mark_recording(wav, "processing")
    else:
        mark_recording(wav, "failed-retained", error_category="CaptureError")

    with pytest.raises(ValueError, match="refusing to remove"):
        remove_unconfirmed_recording(wav)

    assert wav.exists()
    assert recording_sidecar_path(wav).exists()


def test_remove_unconfirmed_recording_refuses_foreign_sidecar(tmp_path):
    wav = create_recording_path(directory=tmp_path)
    wav.write_bytes(b"valid evidence")
    sidecar = recording_sidecar_path(wav)
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload["wav_path"] = str((tmp_path / "other.wav").resolve())
    sidecar.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="does not own"):
        remove_unconfirmed_recording(wav)

    assert wav.exists()
    assert sidecar.exists()
