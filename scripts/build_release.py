from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os
import runpy
import shutil
import tempfile
import uuid
import zipfile


ROOT = Path(__file__).resolve().parent.parent
STATIC_FILES = {
    "release/README.md": "README.md",
    "MAC_SETUP.md": "MAC_SETUP.md",
    "KNOWN_LIMITATIONS.md": "KNOWN_LIMITATIONS.md",
    "requirements.txt": "requirements.txt",
    "pricing.json": "pricing.json",
    ".env.example": ".env.example",
    "real_voice_script.md": "real_voice_script.md",
    "scripts/setup_windows.ps1": "scripts/setup_windows.ps1",
    "scripts/setup_mac.sh": "scripts/setup_mac.sh",
    "scripts/verify_command_alias_windows.ps1": (
        "scripts/verify_command_alias_windows.ps1"
    ),
}
TEXT_SUFFIXES = {
    ".example",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".txt",
}
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class ReleaseResult:
    release_dir: Path
    archive_path: Path
    checksum_path: Path


def _load_version(repo_root: Path) -> str:
    namespace = runpy.run_path(str(repo_root / "speedytype" / "version.py"))
    version = namespace.get("VERSION")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("speedytype/version.py must define a non-empty VERSION")
    return version


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _safe_remove(path: Path, output_root: Path) -> None:
    if (
        not _is_within(path, output_root)
        or path.resolve() == output_root.resolve()
    ):
        raise ValueError(f"Refusing to remove path outside release output: {path}")
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _copy_release_file(source: str | Path, destination: str | Path) -> str:
    source_path = Path(source)
    destination_path = Path(destination)
    data = source_path.read_bytes()
    if source_path.suffix.lower() in TEXT_SUFFIXES:
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    destination_path.write_bytes(data)
    shutil.copymode(source_path, destination_path)
    return str(destination_path)


def _copy_release_content(repo_root: Path, staging: Path) -> None:
    shutil.copytree(
        repo_root / "speedytype",
        staging / "speedytype",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        copy_function=_copy_release_file,
    )
    for source_name, destination_name in STATIC_FILES.items():
        source = repo_root / source_name
        if not source.is_file():
            raise FileNotFoundError(f"Required release file is missing: {source}")
        destination = staging / destination_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        _copy_release_file(source, destination)


def _swap_directory(staging: Path, target: Path, output_root: Path) -> None:
    backup = output_root / f".{target.name}.{uuid.uuid4().hex}.backup"
    had_target = target.exists()
    if had_target:
        target.replace(backup)
    try:
        staging.replace(target)
    except Exception:
        if had_target and backup.exists() and not target.exists():
            backup.replace(target)
        raise
    else:
        if backup.exists():
            _safe_remove(backup, output_root)


def _write_archive(release_dir: Path, archive_path: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{archive_path.name}.",
        suffix=".tmp",
        dir=archive_path.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(release_dir.rglob("*")):
                if path.is_file():
                    relative = path.relative_to(release_dir).as_posix()
                    archive_name = f"{release_dir.name}/{relative}"
                    info = zipfile.ZipInfo(archive_name, ZIP_TIMESTAMP)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.create_system = 3
                    permissions = 0o755 if path.suffix == ".sh" else 0o644
                    info.external_attr = (0o100000 | permissions) << 16
                    archive.writestr(info, path.read_bytes())
        os.replace(temporary, archive_path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_checksum(archive_path: Path, checksum_path: Path) -> None:
    digest = sha256(archive_path.read_bytes()).hexdigest()
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{checksum_path.name}.",
        suffix=".tmp",
        dir=checksum_path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(
            descriptor, "w", encoding="utf-8", newline="\n"
        ) as handle:
            handle.write(f"{digest}  {archive_path.name}\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, checksum_path)
    finally:
        temporary.unlink(missing_ok=True)


def build_release(
    repo_root: Path | None = None,
    output_root: Path | None = None,
) -> ReleaseResult:
    root = Path(repo_root or ROOT).resolve()
    output = Path(output_root or (root / "dist")).resolve()
    output.mkdir(parents=True, exist_ok=True)
    version = _load_version(root)
    release_dir = output / f"SpeedyType-{version}"
    archive_path = output / f"SpeedyType-{version}-source.zip"
    checksum_path = output / "SHA256SUMS.txt"
    staging = output / f".{release_dir.name}.{uuid.uuid4().hex}.staging"
    try:
        staging.mkdir()
        _copy_release_content(root, staging)
        _swap_directory(staging, release_dir, output)
        _write_archive(release_dir, archive_path)
        _write_checksum(archive_path, checksum_path)
    finally:
        if staging.exists():
            _safe_remove(staging, output)
    return ReleaseResult(release_dir, archive_path, checksum_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the SpeedyType source release"
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    result = build_release(output_root=args.output_dir)
    print(result.release_dir)
    print(result.archive_path)
    print(result.checksum_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
