#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_ROOT="${SPEEDYTYPE_INSTALL_ROOT:-$HOME/Applications/SpeedyType}"
INSTALL_ROOT="$(mkdir -p "$(dirname "$INSTALL_ROOT")" && cd "$(dirname "$INSTALL_ROOT")" && pwd)/$(basename "$INSTALL_ROOT")"
VENV_DIR="$INSTALL_ROOT/.venv"
VENV_PYTHON="$INSTALL_ROOT/.venv/bin/python"
ENV_PATH="${1:-$HOME/Library/Application Support/SpeedyType/.env}"
MIN_PYTHON_VERSION="3.13"

sync_to_install_root() {
    mkdir -p "$INSTALL_ROOT"
    rm -rf \
        "$INSTALL_ROOT/speedytype" \
        "$INSTALL_ROOT/scripts" \
        "$INSTALL_ROOT/docs" \
        "$INSTALL_ROOT/README.md" \
        "$INSTALL_ROOT/MAC_SETUP.md" \
        "$INSTALL_ROOT/KNOWN_LIMITATIONS.md" \
        "$INSTALL_ROOT/requirements.txt" \
        "$INSTALL_ROOT/pricing.json" \
        "$INSTALL_ROOT/.env.example" \
        "$INSTALL_ROOT/real_voice_script.md"
    (
        cd "$PROJECT_ROOT"
        tar --exclude="./.venv" --exclude="./__pycache__" --exclude="./.pytest_cache" -cf - .
    ) | (
        cd "$INSTALL_ROOT"
        tar -xf -
    )
}

check_python_313() {
    local interpreter="$1"
    local version

    if ! command -v "$interpreter" >/dev/null 2>&1; then
        echo "Python executable not found: $interpreter" >&2
        return 1
    fi
    if ! version="$("$interpreter" -c 'import platform; print(platform.python_version())')"; then
        echo "Could not run Python executable: $interpreter" >&2
        return 1
    fi
    if ! "$interpreter" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 13) else 1)'; then
        echo "Python 3.13 or newer is required; $interpreter reports $version." >&2
        return 1
    fi
}

if [[ "$PROJECT_ROOT" != "$INSTALL_ROOT" ]]; then
    sync_to_install_root
    echo "Installed SpeedyType source at: $INSTALL_ROOT"
    exec bash "$INSTALL_ROOT/scripts/setup_mac.sh" "$@"
fi

if [[ -d "$VENV_DIR" && ! -x "$VENV_PYTHON" ]]; then
    cat >&2 <<EOF
Existing .venv is incomplete or unusable. SpeedyType did not modify it.
Move it aside, then recreate it with Python 3.13 or newer:
  mv "$VENV_DIR" "$VENV_DIR.backup"
  brew install python@3.13
  PYTHON="\$(brew --prefix python@3.13)/bin/python3.13" bash "$INSTALL_ROOT/scripts/setup_mac.sh"
EOF
    exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
    BOOTSTRAP_PYTHON="${PYTHON:-python3}"
    if ! check_python_313 "$BOOTSTRAP_PYTHON"; then
        cat >&2 <<EOF
Install a compatible Python, then rerun setup:
  brew install python@3.13
  PYTHON="\$(brew --prefix python@3.13)/bin/python3.13" bash "$INSTALL_ROOT/scripts/setup_mac.sh"
EOF
        exit 1
    fi
    "$BOOTSTRAP_PYTHON" -m venv "$VENV_DIR"
fi

if ! check_python_313 "$VENV_PYTHON"; then
    cat >&2 <<EOF
The existing virtual environment is incompatible. SpeedyType did not remove it.
Move it aside, then recreate it with Python 3.13 or newer:
  mv "$INSTALL_ROOT/.venv" "$INSTALL_ROOT/.venv.backup"
  brew install python@3.13
  PYTHON="\$(brew --prefix python@3.13)/bin/python3.13" bash "$INSTALL_ROOT/scripts/setup_mac.sh"
EOF
    exit 1
fi

"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r "$INSTALL_ROOT/requirements.txt"
"$VENV_PYTHON" -m speedytype --env "$ENV_PATH" install-command

echo "Setup complete. Open a new terminal and run: speedytype diagnose-config"
echo "SpeedyType fixed install path: $INSTALL_ROOT"
cat <<EOF
macOS privacy note: this source release does not install SpeedyType.app.
If macOS asks for Accessibility or Input Monitoring, allow the terminal app
that runs SpeedyType, or allow this Python executable:
  $VENV_PYTHON
Then fully restart the daemon:
  speedytype daemon-stop
  speedytype daemon
EOF
