from __future__ import annotations

from pathlib import Path

import requests


def update_env_key(path: str | Path, key: str, value: str) -> None:
    """Update a single `KEY=value` line in a .env file in place, preserving
    every other line (comments, blank lines, other settings) exactly as-is.
    Appends a new line at the end if the key is not already present.
    """
    env_path = Path(path)
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []

    new_line = f"{key}={value}"
    found = False
    out_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not found and stripped and not stripped.startswith("#") and "=" in stripped:
            existing_key = stripped.split("=", 1)[0].strip()
            if existing_key == key:
                out_lines.append(new_line)
                found = True
                continue
        out_lines.append(line)

    if not found:
        out_lines.append(new_line)

    env_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def mask_secret(value: str, visible_suffix: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= visible_suffix:
        return "•" * len(value)
    return "•" * (len(value) - visible_suffix) + value[-visible_suffix:]


def test_openai_key(api_key: str, timeout_seconds: float = 15.0) -> tuple[bool, str]:
    if not api_key:
        return False, "No key provided."
    try:
        response = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds,
        )
    except requests.RequestException as exc:
        return False, f"Request failed: {exc}"
    if response.status_code == 200:
        return True, "OpenAI key OK (model list retrieved)."
    return False, f"OpenAI key check failed: status={response.status_code} body={response.text[:200]}"


def test_gemini_key(api_key: str, timeout_seconds: float = 15.0) -> tuple[bool, str]:
    if not api_key:
        return False, "No key provided."
    try:
        response = requests.get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
            timeout=timeout_seconds,
        )
    except requests.RequestException as exc:
        return False, f"Request failed: {exc}"
    if response.status_code == 200:
        return True, "Gemini key OK (model list retrieved)."
    return False, f"Gemini key check failed: status={response.status_code} body={response.text[:200]}"


def test_minimax_key(api_key: str, timeout_seconds: float = 15.0) -> tuple[bool, str]:
    if not api_key:
        return False, "No key provided."
    try:
        response = requests.get(
            "https://api.minimax.io/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds,
        )
    except requests.RequestException as exc:
        return False, f"Request failed: {exc}"
    if response.status_code == 200:
        return True, "MiniMax key OK (model list retrieved)."
    return False, f"MiniMax key check failed: status={response.status_code} body={response.text[:200]}"
