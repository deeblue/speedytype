#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
ENV_PATH="${1:-$HOME/Library/Application Support/SpeedyType/.env}"
MIN_PYTHON_VERSION="3.13"

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

if [[ -d "$VENV_DIR" && ! -x "$VENV_PYTHON" ]]; then
    cat >&2 <<EOF
Existing .venv is incomplete or unusable. SpeedyType did not modify it.
Move it aside, then recreate it with Python 3.13 or newer:
  mv "$VENV_DIR" "$VENV_DIR.backup"
  brew install python@3.13
  PYTHON="\$(brew --prefix python@3.13)/bin/python3.13" bash "$PROJECT_ROOT/scripts/setup_mac.sh"
EOF
    exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
    BOOTSTRAP_PYTHON="${PYTHON:-python3}"
    if ! check_python_313 "$BOOTSTRAP_PYTHON"; then
        cat >&2 <<EOF
Install a compatible Python, then rerun setup:
  brew install python@3.13
  PYTHON="\$(brew --prefix python@3.13)/bin/python3.13" bash "$PROJECT_ROOT/scripts/setup_mac.sh"
EOF
        exit 1
    fi
    "$BOOTSTRAP_PYTHON" -m venv "$VENV_DIR"
fi

if ! check_python_313 "$VENV_PYTHON"; then
    cat >&2 <<EOF
The existing virtual environment is incompatible. SpeedyType did not remove it.
Move it aside, then recreate it with Python 3.13 or newer:
  mv "$PROJECT_ROOT/.venv" "$PROJECT_ROOT/.venv.backup"
  brew install python@3.13
  PYTHON="\$(brew --prefix python@3.13)/bin/python3.13" bash "$PROJECT_ROOT/scripts/setup_mac.sh"
EOF
    exit 1
fi

"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r "$PROJECT_ROOT/requirements.txt"
"$VENV_PYTHON" -m speedytype --env "$ENV_PATH" install-command

echo "Setup complete. Open a new terminal and run: speedytype diagnose-config"
