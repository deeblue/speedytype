from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_release_readme_documents_automatic_and_manual_installation():
    content = (ROOT / "release" / "README.md").read_text(encoding="utf-8")
    required = (
        "scripts/setup_windows.ps1",
        "scripts/setup_mac.sh",
        "py -3.13 -m venv .venv",
        "python3 -m venv .venv",
        "pip install -r requirements.txt",
        "speedytype install-command",
    )
    for text in required:
        assert text in content


def test_release_readme_documents_keyring_usage_and_daily_commands():
    content = (ROOT / "release" / "README.md").read_text(encoding="utf-8")
    required = (
        "Windows Credential Manager",
        "macOS Keychain",
        "speedytype settings",
        "speedytype diagnose-config",
        "speedytype daemon",
        "speedytype daemon-stop",
        "speedytype guided-recording --script real_voice_script.md",
        "speedytype --env other.env daemon",
        "SHA256SUMS.txt",
    )
    for text in required:
        assert text in content


def test_root_readme_distinguishes_development_tree_from_release():
    content = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "development tree" in content.lower()
    assert "python scripts/build_release.py" in content
    assert "dist/SpeedyType-" in content
    assert "tests" in content
    assert "benchmark" in content
