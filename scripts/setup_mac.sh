#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
ENV_PATH="${1:-$HOME/Library/Application Support/SpeedyType/.env}"

if [[ ! -x "$VENV_PYTHON" ]]; then
    "${PYTHON:-python3}" -m venv "$PROJECT_ROOT/.venv"
fi

"$VENV_PYTHON" -m pip install -r "$PROJECT_ROOT/requirements.txt"
"$VENV_PYTHON" -m speedytype --env "$ENV_PATH" install-command

echo "Setup complete. Open a new terminal and run: speedytype diagnose-config"
