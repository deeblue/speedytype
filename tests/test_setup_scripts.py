from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parent.parent


def test_windows_setup_uses_script_relative_root_venv_and_install_command():
    content = (ROOT / "scripts" / "setup_windows.ps1").read_text(
        encoding="utf-8"
    )

    assert "$PSScriptRoot" in content
    assert '".venv\\Scripts\\python.exe"' in content
    assert '"requirements.txt"' in content
    assert '"install-command"' in content
    assert "$EnvPath" in content


def test_macos_setup_uses_script_relative_root_venv_and_install_command():
    content = (ROOT / "scripts" / "setup_mac.sh").read_text(encoding="utf-8")

    assert "SCRIPT_DIR=" in content
    assert "PROJECT_ROOT=" in content
    assert '"$PROJECT_ROOT/.venv/bin/python"' in content
    assert '"$PROJECT_ROOT/requirements.txt"' in content
    assert "install-command" in content
    assert 'ENV_PATH="${1:-' in content


def test_macos_setup_has_valid_bash_syntax_when_bash_is_available():
    bash = shutil.which("bash")
    if bash is None:
        return

    result = subprocess.run(
        [bash, "-n", str(ROOT / "scripts" / "setup_mac.sh")],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
