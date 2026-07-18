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
    content = (ROOT / "RELEASE.md").read_text(encoding="utf-8")
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
    setup = (ROOT / "MAC_SETUP.md").read_text(encoding="utf-8")
    release = (ROOT / "release" / "README.md").read_text(encoding="utf-8")
    limitations = (ROOT / "KNOWN_LIMITATIONS.md").read_text(encoding="utf-8")
    report = (ROOT / "POC_REPORT.md").read_text(encoding="utf-8")

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


def test_release_docs_describe_complete_file_flac_lifecycle_and_pending_gates():
    release = (ROOT / "release" / "README.md").read_text(encoding="utf-8")
    setup = (ROOT / "MAC_SETUP.md").read_text(encoding="utf-8")
    limitations = (ROOT / "KNOWN_LIMITATIONS.md").read_text(encoding="utf-8")
    report = (ROOT / "POC_REPORT.md").read_text(encoding="utf-8")
    combined = "\n".join((release, setup, limitations, report))

    required = (
        "25 minutes",
        "23 MiB",
        "PCM16 WAV",
        "lossless FLAC",
        "response_format=json",
        "short-WAV fallback",
        "failed-retained",
        "real-device release gate",
        "Windows",
        "macOS",
    )
    for text in required:
        assert text in combined
    assert "25 minutes" in release
    assert "25 minutes" in setup


def test_release_docs_describe_hold_toggle_overlay_timeout_and_pending_device_gates():
    release = (ROOT / "release" / "README.md").read_text(encoding="utf-8")
    setup = (ROOT / "MAC_SETUP.md").read_text(encoding="utf-8")
    limitations = (ROOT / "KNOWN_LIMITATIONS.md").read_text(encoding="utf-8")
    report = (ROOT / "POC_REPORT.md").read_text(encoding="utf-8")
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
        "Windows Toggle real-device gate is pending",
        "macOS Toggle real-device gate is pending",
    )
    for text in required:
        assert text in combined

    assert "Hold mode" in release and "Toggle mode" in release
    assert "Hold mode" in setup and "Toggle mode" in setup
    assert "release rearms; next press stops" in report
    assert "process/OS crash durability" in combined
    assert "sudden-power-loss real-device gate remains pending" in combined
