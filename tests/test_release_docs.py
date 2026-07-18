from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
USER_README = ROOT / "docs" / "current" / "user" / "README.md"
MAC_SETUP = ROOT / "docs" / "current" / "user" / "MAC_SETUP.md"
LIMITATIONS = (
    ROOT / "docs" / "current" / "engineering" / "KNOWN_LIMITATIONS.md"
)
RELEASE = ROOT / "docs" / "current" / "engineering" / "RELEASE.md"
STATUS = ROOT / "docs" / "current" / "STATUS.md"
ARCHIVED_POC_REPORT = (
    ROOT / "docs" / "archive" / "reports" / "POC_REPORT.md"
)


def test_release_readme_documents_automatic_and_manual_installation():
    content = USER_README.read_text(encoding="utf-8")
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
    content = USER_README.read_text(encoding="utf-8")
    assert "paste" in content
    assert "masked" in content
    required = (
        "Windows Credential Manager",
        "macOS Keychain",
        "speedytype settings",
        "speedytype --version",
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


def test_release_checklist_documents_verified_annotated_tag_workflow():
    content = RELEASE.read_text(encoding="utf-8")
    required = (
        'VERSION = "0.5.3"',
        'BUILD_DATE = "2026-07-16"',
        "python -m pytest -q",
        "python -m compileall -q speedytype scripts",
        "python scripts/build_release.py",
        'git tag -a v0.5.3 -m "SpeedyType 0.5.3"',
        "git push origin master",
        "git push origin v0.5.3",
        "Never move or force-update an existing release tag",
    )
    for text in required:
        assert text in content


def test_macos_docs_describe_native_menu_bar_permissions_and_release_gate():
    setup = MAC_SETUP.read_text(encoding="utf-8")
    release = USER_README.read_text(encoding="utf-8")
    limitations = LIMITATIONS.read_text(encoding="utf-8")
    report = ARCHIVED_POC_REPORT.read_text(encoding="utf-8")

    required_setup = (
        "menu-bar icon",
        "no Python icon in the Dock",
        "Input Monitoring",
        "Accessibility",
        "Microphone",
        "restart the daemon",
        "Python .ips",
        "ten consecutive recording/paste cycles",
        "v0.5.4",
    )
    for text in required_setup:
        assert text in setup
    assert "real-Mac acceptance remains pending" in release
    assert "Quartz event tap" in limitations
    assert "mac_log_002.rtf" in report


def test_release_docs_describe_complete_file_flac_lifecycle_and_macos_only_gate():
    release = USER_README.read_text(encoding="utf-8")
    setup = MAC_SETUP.read_text(encoding="utf-8")
    limitations = LIMITATIONS.read_text(encoding="utf-8")
    report = ARCHIVED_POC_REPORT.read_text(encoding="utf-8")
    combined = "\n".join((release, setup, limitations, report))

    required = (
        "25 minutes",
        "23 MiB",
        "PCM16 WAV",
        "lossless FLAC",
        "response_format=json",
        "short-WAV fallback",
        "failed-retained",
        "macOS is the only hardware release gate",
        "Windows simulation/automation",
        "Windows",
        "macOS",
    )
    for text in required:
        assert text in combined
    assert "25 minutes" in release
    assert "25 minutes" in setup


def test_release_docs_describe_hold_toggle_overlay_timeout_and_macos_gate():
    release = USER_README.read_text(encoding="utf-8")
    setup = MAC_SETUP.read_text(encoding="utf-8")
    limitations = LIMITATIONS.read_text(encoding="utf-8")
    report = ARCHIVED_POC_REPORT.read_text(encoding="utf-8")
    combined = "\n".join((release, setup, limitations, report))

    required = (
        "Hold mode",
        "Toggle mode",
        "default recording mode is Hold",
        "release and repress",
        "MM:SS",
        "final 60-second countdown",
        "pill-local automatic-stop warning",
        "25-minute stop",
        "restart the daemon",
        "guided-recording is excluded",
        "macOS is the only hardware release gate",
        "bounded-duration automatic-stop",
    )
    for text in required:
        assert text in combined

    assert "Hold mode" in release and "Toggle mode" in release
    assert "Hold mode" in setup and "Toggle mode" in setup
    assert "release rearms; next press stops" in report
    assert "process/OS crash durability" in combined
    assert "No 24- or 25-minute real recording is required" in combined
    assert "Sudden-power-loss survival is not claimed and is not a separate release gate" in combined
    assert "Windows Toggle real-device gate is pending" not in combined
    assert "≥24-minute" not in combined
    assert "sudden-power-loss real-device gate" not in combined
