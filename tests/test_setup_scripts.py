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


def test_macos_setup_uses_fixed_install_root_venv_and_install_command():
    content = (ROOT / "scripts" / "setup_mac.sh").read_text(encoding="utf-8")

    assert "SCRIPT_DIR=" in content
    assert "PROJECT_ROOT=" in content
    assert 'INSTALL_ROOT="${SPEEDYTYPE_INSTALL_ROOT:-$HOME/Applications/SpeedyType}"' in content
    assert 'if [[ "$PROJECT_ROOT" != "$INSTALL_ROOT" ]]' in content
    assert 'exec bash "$INSTALL_ROOT/scripts/setup_mac.sh" "$@"' in content
    assert '"$INSTALL_ROOT/.venv/bin/python"' in content
    assert '"$INSTALL_ROOT/requirements.txt"' in content
    assert "install-command" in content
    assert 'ENV_PATH="${1:-' in content
    assert "does not install SpeedyType.app" in content
    assert "$VENV_PYTHON" in content
    assert "Input Monitoring" in content


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
        '"$VENV_PYTHON" -m pip install -r "$INSTALL_ROOT/requirements.txt"'
    )
    alias = content.index(
        '"$VENV_PYTHON" -m speedytype --env "$ENV_PATH" install-command'
    )

    assert upgrade < requirements < alias


def test_macos_dependencies_use_pyobjc_and_remove_pynput():
    content = (ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert 'pyobjc-framework-Cocoa==12.2.1; sys_platform == "darwin"' in content
    assert 'pyobjc-framework-Quartz==12.2.1; sys_platform == "darwin"' in content
    assert 'pynput' not in content


def test_mac_setup_documentation_has_python_313_recovery_flow():
    content = (
        ROOT / "docs" / "current" / "user" / "MAC_SETUP.md"
    ).read_text(encoding="utf-8")
    required = (
        "Python 3.13 or newer",
        "~/Applications/SpeedyType",
        "python3 --version",
        ".venv/bin/python --version",
        "does not install `SpeedyType.app`",
        "~/Applications/SpeedyType/.venv/bin/python",
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
    (project / "speedytype").mkdir()
    (project / "speedytype" / "__init__.py").write_text("", encoding="utf-8")
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
    env.update(
        PYTHON="./old-python",
        SPEEDYTYPE_INSTALL_ROOT=(tmp_path / "install" / "SpeedyType").as_posix(),
        FAKE_PYTHON_CALLS=str(calls),
    )

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
    assert not (tmp_path / "install" / "SpeedyType" / ".venv").exists()
    assert not calls.exists()


def test_macos_setup_syncs_to_fixed_install_root_before_creating_venv(tmp_path):
    bash = shutil.which("bash")
    if bash is None:
        return

    project = _copy_macos_setup_project(tmp_path)
    install_root = tmp_path / "home" / "Applications" / "SpeedyType"
    fake_python = project / "python313"
    calls = tmp_path / "calls.txt"
    fake_python.write_text(
        """#!/usr/bin/env bash
if [[ "$1" == "-c" && "$2" == *"platform.python_version"* ]]; then
    echo "3.13.1"
    exit 0
fi
if [[ "$1" == "-c" && "$2" == *"sys.version_info"* ]]; then
    exit 0
fi
if [[ "$1" == "-m" && "$2" == "venv" ]]; then
    mkdir -p "$3/bin"
    cp "$0" "$3/bin/python"
    exit 0
fi
if [[ "$1" == "-m" && "$2" == "pip" ]]; then
    echo "pip $*" >> "${FAKE_PYTHON_CALLS:?}"
    exit 0
fi
if [[ "$1" == "-m" && "$2" == "speedytype" ]]; then
    echo "speedytype $*" >> "${FAKE_PYTHON_CALLS:?}"
    exit 0
fi
echo "$*" >> "${FAKE_PYTHON_CALLS:?}"
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    env = os.environ.copy()
    env.update(
        PYTHON=str(fake_python),
        SPEEDYTYPE_INSTALL_ROOT=install_root.as_posix(),
        FAKE_PYTHON_CALLS=str(calls),
    )

    result = subprocess.run(
        [bash, "scripts/setup_mac.sh"],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (install_root / "scripts" / "setup_mac.sh").is_file()
    assert (install_root / "requirements.txt").is_file()
    assert (install_root / ".venv" / "bin" / "python").is_file()
    assert not (project / ".venv").exists()
    assert "Installed SpeedyType source at:" in result.stdout
    assert "/Applications/SpeedyType" in result.stdout
    assert ".venv/bin/python" in result.stdout
    assert calls.read_text(encoding="utf-8").count("speedytype -m speedytype") == 1


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
    env.update(
        SPEEDYTYPE_INSTALL_ROOT=project.as_posix(),
        FAKE_PYTHON_CALLS=str(calls),
    )

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
