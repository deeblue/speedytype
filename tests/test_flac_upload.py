from __future__ import annotations

from pathlib import Path
import subprocess

import numpy as np
import pytest
import soundfile as sf

from speedytype.flac_upload import (
    FlacEncodingError,
    FlacValidation,
    FlacValidationError,
    UploadPreparationError,
    encode_lossless_flac,
    prepare_upload,
    validate_lossless_flac,
)


def _wav(path: Path, *, frames: int = 16_000, channels: int = 1) -> Path:
    values = np.linspace(-0.5, 0.5, frames * channels, dtype="float32").reshape(
        frames, channels
    )
    sf.write(path, values, 16_000, subtype="PCM_16")
    return path


def test_prepare_upload_creates_valid_lossless_flac_then_cleans_only_flac(tmp_path):
    source = _wav(tmp_path / "source.wav")

    with prepare_upload(source) as prepared:
        upload_path = prepared.path
        assert upload_path.exists()
        assert prepared.container == "flac"
        assert prepared.fallback_used is False
        assert prepared.validation is not None
        assert prepared.validation.format_valid is True
        assert prepared.validation.frame_count_match is True
        assert prepared.validation.pcm_sha256_match is True
        assert prepared.upload_bytes == upload_path.stat().st_size
        assert source.exists()

    assert source.exists()
    assert not upload_path.exists()
    assert not list(tmp_path.glob("*.partial.flac"))


def test_validate_rejects_frame_or_pcm_mismatch(tmp_path):
    source = _wav(tmp_path / "source.wav", frames=1_000)
    short = tmp_path / "short.flac"
    changed = tmp_path / "changed.flac"
    sf.write(short, np.zeros((999, 1), dtype="float32"), 16_000, subtype="PCM_16")
    sf.write(changed, np.zeros((1_000, 1), dtype="float32"), 16_000, subtype="PCM_16")

    with pytest.raises(FlacValidationError, match="frame_count"):
        validate_lossless_flac(source, short)
    with pytest.raises(FlacValidationError, match="pcm_sha256"):
        validate_lossless_flac(source, changed)


def test_validate_rejects_wrong_format_or_empty_artifact(tmp_path):
    source = _wav(tmp_path / "source.wav")
    stereo = tmp_path / "stereo.flac"
    empty = tmp_path / "empty.flac"
    sf.write(stereo, np.zeros((16_000, 2), dtype="float32"), 16_000, subtype="PCM_16")
    empty.write_bytes(b"")

    with pytest.raises(FlacValidationError, match="format"):
        validate_lossless_flac(source, stereo)
    with pytest.raises(FlacValidationError, match="artifact"):
        validate_lossless_flac(source, empty)


def test_encode_failure_removes_owned_partial_and_never_source(tmp_path):
    source = _wav(tmp_path / "source.wav")
    target = tmp_path / "target.flac"

    def failing_runner(command, **_kwargs):
        Path(command[-1]).write_bytes(b"partial")
        raise subprocess.CalledProcessError(1, command, stderr="private path detail")

    with pytest.raises(FlacEncodingError):
        encode_lossless_flac(source, target, ffmpeg_exe="ffmpeg", runner=failing_runner)

    assert source.exists()
    assert not target.exists()
    assert not list(tmp_path.glob("*.partial.flac"))


def test_actual_byte_guard_is_strict(tmp_path):
    source = _wav(tmp_path / "source.wav")
    with prepare_upload(source) as first:
        exact_size = first.upload_bytes

    with pytest.raises(UploadPreparationError) as exc:
        with prepare_upload(source, max_bytes=exact_size):
            pass

    assert exc.value.category == "upload_too_large"
    assert exc.value.preserved_wav == source
    assert source.exists()


def test_duration_guard_is_inclusive_at_limit_and_rejects_above(tmp_path):
    source = _wav(tmp_path / "source.wav", frames=16_000)

    with prepare_upload(source, max_seconds=1.0) as prepared:
        assert prepared.duration_seconds == 1.0

    with pytest.raises(UploadPreparationError) as exc:
        with prepare_upload(source, max_seconds=0.999):
            pass
    assert exc.value.category == "recording_too_long"
    assert source.exists()


def test_encoding_failure_uses_wav_only_when_wav_is_admissible(tmp_path):
    source = _wav(tmp_path / "source.wav", frames=1_000)

    def fail(_source, _target):
        raise FlacEncodingError("encoded detail must not escape")

    with prepare_upload(source, encoder=fail) as prepared:
        assert prepared.path == source
        assert prepared.container == "wav"
        assert prepared.fallback_used is True
        assert prepared.fallback_reason == "FlacEncodingError"

    assert source.exists()


def test_encoding_failure_with_ineligible_wav_retains_and_refuses(tmp_path):
    source = _wav(tmp_path / "source.wav", frames=1_000)

    def fail(_source, _target):
        raise FlacEncodingError("failure")

    with pytest.raises(UploadPreparationError) as exc:
        with prepare_upload(source, max_bytes=source.stat().st_size, encoder=fail):
            pass

    assert exc.value.category == "upload_too_large"
    assert exc.value.preserved_wav == source
    assert source.exists()


def test_oversize_valid_flac_never_falls_back_to_admissible_wav(tmp_path):
    source = _wav(tmp_path / "source.wav", frames=100)
    max_bytes = source.stat().st_size + 1

    def oversize_encoder(_source, target):
        target.write_bytes(b"x" * max_bytes)
        return 0.1

    validation = FlacValidation(True, True, True, 100, 100, "same", "same")

    with pytest.raises(UploadPreparationError) as exc:
        with prepare_upload(
            source,
            max_bytes=max_bytes,
            encoder=oversize_encoder,
            validator=lambda *_args: validation,
        ):
            pass

    assert exc.value.category == "upload_too_large"
    assert exc.value.preserved_wav == source
    assert source.stat().st_size < max_bytes
    assert not list(tmp_path.glob("*.flac"))
