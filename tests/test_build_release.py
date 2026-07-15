from hashlib import sha256
from pathlib import Path
import zipfile

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

    assert archive_files == folder_files
    digest = sha256(result.archive_path.read_bytes()).hexdigest()
    assert result.checksum_path.read_text(encoding="utf-8") == (
        f"{digest}  {result.archive_path.name}\n"
    )
