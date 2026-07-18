from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import secrets
import subprocess
import time
from typing import Callable, Iterator

import imageio_ffmpeg
import numpy as np
import soundfile as sf


MAX_UPLOAD_BYTES = 23 * 1024 * 1024
MAX_RECORD_SECONDS = 1500.0


class FlacEncodingError(RuntimeError):
    pass


class FlacValidationError(RuntimeError):
    pass


class UploadPreparationError(RuntimeError):
    def __init__(self, category: str, preserved_wav: Path) -> None:
        self.category = category
        self.preserved_wav = Path(preserved_wav)
        super().__init__(f"{category}; preserved WAV: {self.preserved_wav}")


@dataclass(frozen=True)
class FlacValidation:
    format_valid: bool
    frame_count_match: bool
    pcm_sha256_match: bool
    source_frames: int
    flac_frames: int
    source_pcm_sha256: str
    flac_pcm_sha256: str


@dataclass(frozen=True)
class PreparedUpload:
    path: Path
    container: str
    source_wav: Path
    source_bytes: int
    upload_bytes: int
    duration_seconds: float
    encoding_seconds: float
    fallback_used: bool
    fallback_reason: str
    validation: FlacValidation | None


def _pcm_sha256(path: Path) -> str:
    digest = sha256()
    for block in sf.blocks(path, blocksize=65_536, dtype="int16", always_2d=True):
        digest.update(np.asarray(block, dtype="<i2").tobytes(order="C"))
    return digest.hexdigest()


def _audio_properties(path: Path) -> tuple[int, int, int, str, float]:
    try:
        with sf.SoundFile(path) as audio:
            frames = len(audio)
            sample_rate = audio.samplerate
            channels = audio.channels
            subtype = audio.subtype
    except (OSError, RuntimeError, sf.LibsndfileError) as exc:
        raise FlacValidationError("artifact is not readable") from exc
    duration = frames / sample_rate if sample_rate else 0.0
    return frames, sample_rate, channels, subtype, duration


def validate_lossless_flac(source_wav: Path, flac_path: Path) -> FlacValidation:
    source = Path(source_wav)
    artifact = Path(flac_path)
    if not artifact.is_file() or artifact.stat().st_size <= 0:
        raise FlacValidationError("artifact is missing or empty")
    source_frames, source_rate, source_channels, source_subtype, _ = _audio_properties(source)
    flac_frames, flac_rate, flac_channels, flac_subtype, _ = _audio_properties(artifact)
    if (
        source_rate != 16_000
        or source_channels != 1
        or source_subtype != "PCM_16"
        or flac_rate != 16_000
        or flac_channels != 1
        or flac_subtype != "PCM_16"
        or artifact.suffix.lower() != ".flac"
    ):
        raise FlacValidationError("format validation failed")
    if source_frames != flac_frames:
        raise FlacValidationError("frame_count validation failed")
    source_hash = _pcm_sha256(source)
    flac_hash = _pcm_sha256(artifact)
    if source_hash != flac_hash:
        raise FlacValidationError("pcm_sha256 validation failed")
    return FlacValidation(
        format_valid=True,
        frame_count_match=True,
        pcm_sha256_match=True,
        source_frames=source_frames,
        flac_frames=flac_frames,
        source_pcm_sha256=source_hash,
        flac_pcm_sha256=flac_hash,
    )


def encode_lossless_flac(
    source_wav: Path,
    target_flac: Path,
    *,
    ffmpeg_exe: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    clock: Callable[[], float] = time.perf_counter,
) -> float:
    source = Path(source_wav)
    target = Path(target_flac)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(
        f"{target.stem}.{secrets.token_hex(8)}.partial.flac"
    )
    executable = ffmpeg_exe or imageio_ffmpeg.get_ffmpeg_exe()
    command = [
        str(executable),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-map_metadata",
        "-1",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "flac",
        "-sample_fmt",
        "s16",
        str(partial),
    ]
    started = clock()
    try:
        runner(command, check=True, capture_output=True, text=True)
        elapsed = clock() - started
        if not partial.is_file() or partial.stat().st_size <= 0:
            raise FlacEncodingError("encoder returned no artifact")
        partial.replace(target)
        return elapsed
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        raise FlacEncodingError("lossless FLAC encoding failed") from exc
    finally:
        partial.unlink(missing_ok=True)


def _wav_admission(
    source_wav: Path, *, max_bytes: int, max_seconds: float
) -> tuple[int, float]:
    source = Path(source_wav)
    if not source.is_file() or source.stat().st_size <= 0:
        raise UploadPreparationError("invalid_wav", source)
    try:
        frames, rate, channels, subtype, duration = _audio_properties(source)
    except FlacValidationError as exc:
        raise UploadPreparationError("invalid_wav", source) from exc
    if rate != 16_000 or channels != 1 or subtype != "PCM_16" or frames <= 0:
        raise UploadPreparationError("invalid_wav", source)
    if duration > max_seconds:
        raise UploadPreparationError("recording_too_long", source)
    size = source.stat().st_size
    if size >= max_bytes:
        raise UploadPreparationError("upload_too_large", source)
    return size, duration


@contextmanager
def prepare_upload(
    source_wav: Path,
    *,
    max_bytes: int = MAX_UPLOAD_BYTES,
    max_seconds: float = MAX_RECORD_SECONDS,
    encoder: Callable[[Path, Path], float] = encode_lossless_flac,
    validator: Callable[[Path, Path], FlacValidation] = validate_lossless_flac,
) -> Iterator[PreparedUpload]:
    source = Path(source_wav)
    if max_bytes <= 0 or max_seconds <= 0:
        raise ValueError("upload guards must be positive")
    try:
        source_frames, source_rate, source_channels, source_subtype, duration = _audio_properties(source)
    except FlacValidationError as exc:
        raise UploadPreparationError("invalid_wav", source) from exc
    if (
        not source.is_file()
        or source.stat().st_size <= 0
        or source_frames <= 0
        or source_rate != 16_000
        or source_channels != 1
        or source_subtype != "PCM_16"
    ):
        raise UploadPreparationError("invalid_wav", source)
    if duration > max_seconds:
        raise UploadPreparationError("recording_too_long", source)

    source_bytes = source.stat().st_size
    flac = source.with_name(f"{source.stem}_upload_{secrets.token_hex(8)}.flac")
    try:
        try:
            encoding_seconds = encoder(source, flac)
            validation = validator(source, flac)
        except (FlacEncodingError, FlacValidationError) as exc:
            flac.unlink(missing_ok=True)
            try:
                wav_bytes, wav_duration = _wav_admission(
                    source, max_bytes=max_bytes, max_seconds=max_seconds
                )
            except UploadPreparationError:
                raise
            yield PreparedUpload(
                path=source,
                container="wav",
                source_wav=source,
                source_bytes=source_bytes,
                upload_bytes=wav_bytes,
                duration_seconds=wav_duration,
                encoding_seconds=0.0,
                fallback_used=True,
                fallback_reason=type(exc).__name__,
                validation=None,
            )
            return
        upload_bytes = flac.stat().st_size
        if upload_bytes >= max_bytes:
            raise UploadPreparationError("upload_too_large", source)
        yield PreparedUpload(
            path=flac,
            container="flac",
            source_wav=source,
            source_bytes=source_bytes,
            upload_bytes=upload_bytes,
            duration_seconds=duration,
            encoding_seconds=encoding_seconds,
            fallback_used=False,
            fallback_reason="",
            validation=validation,
        )
    finally:
        flac.unlink(missing_ok=True)
