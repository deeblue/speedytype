from pathlib import Path
import os
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


def test_macos_setup_enforces_python_313_without_deleting_existing_venv():
    content = (ROOT / "scripts" / "setup_mac.sh").read_text(encoding="utf-8")

    required = (
        'MIN_PYTHON_VERSION="3.13"',
        "sys.version_info >= (3, 13)",
        'check_python_313 "$BOOTSTRAP_PYTHON"',
        'check_python_313 "$VENV_PYTHON"',
        '[[ -d "$VENV_DIR" && ! -x "$VENV_PYTHON" ]]',
        "Existing .venv is incomplete or unusable",
        "brew install python@3.13",
        "brew --prefix python@3.13",
        "Python 3.13 or newer is required",
    )
    for text in required:
        assert text in content

    assert 'rm -rf "$PROJECT_ROOT/.venv"' not in content


def test_macos_setup_upgrades_pip_before_requirements_and_command_alias():
    content = (ROOT / "scripts" / "setup_mac.sh").read_text(encoding="utf-8")

    upgrade = content.index('"$VENV_PYTHON" -m pip install --upgrade pip')
    requirements = content.index(
        '"$VENV_PYTHON" -m pip install -r "$PROJECT_ROOT/requirements.txt"'
    )
    alias = content.index(
        '"$VENV_PYTHON" -m speedytype --env "$ENV_PATH" install-command'
    )

    assert upgrade < requirements < alias


def test_mac_setup_documentation_has_python_313_recovery_flow():
    content = (ROOT / "MAC_SETUP.md").read_text(encoding="utf-8")
    required = (
        "Python 3.13 or newer",
        "python3 --version",
        ".venv/bin/python --version",
        "brew install python@3.13",
        'PYTHON="$(brew --prefix python@3.13)/bin/python3.13"',
        "mv .venv .venv.backup",
    )
    for text in required:
        assert text in content


def _copy_macos_setup_project(tmp_path):
    project = tmp_path / "project"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "setup_mac.sh", scripts / "setup_mac.sh")
    (project / "requirements.txt").write_text("", encoding="utf-8")
    return project


def _write_old_python(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """#!/usr/bin/env bash
if [[ "$1" == "-c" && "$2" == *"platform.python_version"* ]]; then
    echo "3.12.9"
    exit 0
fi
if [[ "$1" == "-c" && "$2" == *"sys.version_info"* ]]; then
    exit 1
fi
echo "$*" >> "${FAKE_PYTHON_CALLS:?}"
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_macos_setup_rejects_old_bootstrap_python(tmp_path):
    bash = shutil.which("bash")
    if bash is None:
        return

    project = _copy_macos_setup_project(tmp_path)
    _write_old_python(project / "old-python")
    calls = project / "calls.txt"
    env = os.environ.copy()
    env.update(PYTHON="./old-python", FAKE_PYTHON_CALLS=str(calls))

    result = subprocess.run(
        [bash, "scripts/setup_mac.sh"],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Python 3.13 or newer is required" in result.stderr
    assert not (project / ".venv").exists()
    assert not calls.exists()


def test_macos_setup_rejects_old_existing_venv_without_modifying_it(tmp_path):
    bash = shutil.which("bash")
    if bash is None:
        return

    project = _copy_macos_setup_project(tmp_path)
    venv_python = project / ".venv" / "bin" / "python"
    _write_old_python(venv_python)
    original = venv_python.read_bytes()
    calls = project / "calls.txt"
    env = os.environ.copy()
    env["FAKE_PYTHON_CALLS"] = str(calls)

    result = subprocess.run(
        [bash, "scripts/setup_mac.sh"],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "existing virtual environment is incompatible" in result.stderr
    assert venv_python.read_bytes() == original
    assert not calls.exists()
