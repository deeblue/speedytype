from hashlib import sha256
import os
from pathlib import Path
import shutil
import zipfile

import pytest

import scripts.build_release as build_release


ROOT = Path(__file__).resolve().parent.parent
EXPECTED_TOP_LEVEL = {
    ".env.example",
    "KNOWN_LIMITATIONS.md",
    "MAC_SETUP.md",
    "README.md",
    "pricing.json",
    "real_voice_script.md",
    "requirements.txt",
    "scripts",
    "speedytype",
}
EXPECTED_SCRIPTS = {
    "setup_mac.sh",
    "setup_windows.ps1",
    "verify_command_alias_windows.ps1",
}


def _copy_release_inputs(destination):
    shutil.copytree(ROOT / "speedytype", destination / "speedytype")
    for source_name in build_release.STATIC_FILES:
        source = ROOT / source_name
        target = destination / source_name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def test_build_release_has_exact_runtime_inventory(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sentinel-release-secret")

    result = build_release.build_release(ROOT, tmp_path / "dist")

    assert result.release_dir.name == "SpeedyType-0.5.0"
    assert {path.name for path in result.release_dir.iterdir()} == EXPECTED_TOP_LEVEL
    assert {
        path.name for path in (result.release_dir / "scripts").iterdir()
    } == EXPECTED_SCRIPTS
    assert (result.release_dir / "speedytype" / "cli.py").is_file()
    assert not list(result.release_dir.rglob("__pycache__"))
    assert not list(result.release_dir.rglob("*.pyc"))
    assert not (result.release_dir / "tests").exists()
    assert not (result.release_dir / ".env").exists()

    released_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in result.release_dir.rglob("*")
        if path.is_file()
    )
    assert "sentinel-release-secret" not in released_text


def test_archive_matches_directory_and_checksum(tmp_path):
    result = build_release.build_release(ROOT, tmp_path / "dist")
    folder_files = {
        path.relative_to(result.release_dir).as_posix(): path.read_bytes()
        for path in result.release_dir.rglob("*")
        if path.is_file()
    }
    with zipfile.ZipFile(result.archive_path) as archive:
        archive_files = {
            name.removeprefix(f"{result.release_dir.name}/"): archive.read(name)
            for name in archive.namelist()
            if not name.endswith("/")
        }
        mac_setup = archive.getinfo(
            f"{result.release_dir.name}/scripts/setup_mac.sh"
        )

    assert archive_files == folder_files
    assert (mac_setup.external_attr >> 16) & 0o777 == 0o755
    digest = sha256(result.archive_path.read_bytes()).hexdigest()
    assert result.checksum_path.read_text(encoding="utf-8") == (
        f"{digest}  {result.archive_path.name}\n"
    )


def test_archive_is_reproducible_across_mtime_and_checkout_line_endings(
    tmp_path,
):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    _copy_release_inputs(first_root)
    _copy_release_inputs(second_root)

    second_readme = second_root / "release" / "README.md"
    readme_bytes = second_readme.read_bytes().replace(b"\r\n", b"\n")
    second_readme.write_bytes(
        readme_bytes.replace(b"\n", b"\r\n")
    )
    for path in first_root.rglob("*"):
        if path.is_file():
            os.utime(path, (1_600_000_000, 1_600_000_000))
    for path in second_root.rglob("*"):
        if path.is_file():
            os.utime(path, (1_700_000_000, 1_700_000_000))

    first = build_release.build_release(first_root, tmp_path / "first-dist")
    second = build_release.build_release(second_root, tmp_path / "second-dist")

    assert first.archive_path.read_bytes() == second.archive_path.read_bytes()


def test_repeat_build_removes_stale_release_files(tmp_path):
    output = tmp_path / "dist"
    first = build_release.build_release(ROOT, output)
    stale = first.release_dir / "stale-development-output.txt"
    stale.write_text("must disappear", encoding="utf-8")

    second = build_release.build_release(ROOT, output)

    assert second.release_dir == first.release_dir
    assert not stale.exists()


def test_failed_staging_preserves_previous_complete_release(tmp_path, monkeypatch):
    output = tmp_path / "dist"
    first = build_release.build_release(ROOT, output)
    marker = first.release_dir / "previous-complete-marker.txt"
    marker.write_text("preserve me", encoding="utf-8")
    archive_bytes = first.archive_path.read_bytes()
    checksum_bytes = first.checksum_path.read_bytes()

    def fail_copy(repo_root, staging):
        (staging / "partial.txt").write_text("partial", encoding="utf-8")
        raise OSError("injected staging failure")

    monkeypatch.setattr(build_release, "_copy_release_content", fail_copy)

    with pytest.raises(OSError, match="injected staging failure"):
        build_release.build_release(ROOT, output)

    assert marker.read_text(encoding="utf-8") == "preserve me"
    assert first.archive_path.read_bytes() == archive_bytes
    assert first.checksum_path.read_bytes() == checksum_bytes
    assert not list(output.glob("*.staging"))


def test_safe_remove_rejects_paths_outside_output(tmp_path):
    output = tmp_path / "dist"
    outside = tmp_path / "outside"
    outside.mkdir()

    with pytest.raises(ValueError, match="outside release output"):
        build_release._safe_remove(outside, output)

    assert outside.exists()
