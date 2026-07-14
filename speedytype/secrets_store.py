"""Credential storage and safe migration of API keys from ``.env`` files."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import shlex

from keyring import delete_password as _delete_password
from keyring import get_password as _get_password
from keyring import set_password as _set_password


SERVICE_NAME = "SpeedyType"
SECRET_KEY_NAMES = {
    "OPENAI_API_KEY": "openai_api_key",
    "GEMINI_API_KEY": "gemini_api_key",
    "MINIMAX_API_KEY": "minimax_api_key",
}


class SecretStoreError(RuntimeError):
    """Raised when the operating system credential store cannot be used."""


@dataclass(frozen=True)
class SecretResolution:
    values: dict[str, str]
    migrated: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _backend_error(env_name: str, operation: str, exc: Exception) -> SecretStoreError:
    return SecretStoreError(
        f"Credential store {operation} failed for {env_name} ({type(exc).__name__})"
    )


def get_api_key(
    env_name: str,
    *,
    service_name: str = SERVICE_NAME,
    key_names: Mapping[str, str] = SECRET_KEY_NAMES,
) -> str | None:
    username = key_names[env_name]
    try:
        return _get_password(service_name, username)
    except Exception as exc:
        raise _backend_error(env_name, "get", exc) from None


def set_api_key(
    env_name: str,
    value: str,
    *,
    service_name: str = SERVICE_NAME,
    key_names: Mapping[str, str] = SECRET_KEY_NAMES,
) -> None:
    username = key_names[env_name]
    try:
        _set_password(service_name, username, value)
    except Exception as exc:
        raise _backend_error(env_name, "set", exc) from None
    try:
        stored_value = _get_password(service_name, username)
    except Exception as exc:
        raise _backend_error(env_name, "verify", exc) from None
    if stored_value != value:
        raise SecretStoreError(f"Credential verification failed for {env_name}")


def delete_api_key(
    env_name: str,
    *,
    service_name: str = SERVICE_NAME,
    key_names: Mapping[str, str] = SECRET_KEY_NAMES,
) -> None:
    username = key_names[env_name]
    try:
        _delete_password(service_name, username)
    except Exception as exc:
        raise _backend_error(env_name, "delete", exc) from None


def resolve_api_keys(
    env_path: str | Path,
    file_values: Mapping[str, str],
    environment: Mapping[str, str] | None = None,
    service_name: str = SERVICE_NAME,
    key_names: Mapping[str, str] = SECRET_KEY_NAMES,
) -> SecretResolution:
    """Resolve credentials and migrate only verified file-sourced values."""
    if environment is None:
        environment = os.environ

    values: dict[str, str] = {}
    migrated_values: dict[str, str] = {}
    warnings: list[str] = []

    for env_name in key_names:
        try:
            stored_value = get_api_key(env_name, service_name=service_name, key_names=key_names)
        except SecretStoreError as exc:
            warnings.append(str(exc))
            stored_value = None

        if stored_value is not None:
            values[env_name] = stored_value
            continue

        if env_name in environment:
            values[env_name] = environment[env_name]
            continue

        file_value = file_values.get(env_name)
        if file_value is None:
            continue

        values[env_name] = file_value
        try:
            set_api_key(env_name, file_value, service_name=service_name, key_names=key_names)
        except SecretStoreError as exc:
            warnings.append(str(exc))
        else:
            migrated_values[env_name] = file_value

    if migrated_values:
        warnings.extend(_remove_env_keys(Path(env_path), migrated_values))

    return SecretResolution(values, tuple(migrated_values), tuple(warnings))


def _normalize_env_value(value: str) -> str:
    value = value.strip()
    if value:
        try:
            parsed = shlex.split(value, posix=False)
            if len(parsed) == 1:
                value = parsed[0].strip('"').strip("'")
        except ValueError:
            value = value.strip('"').strip("'")
    return value


def _parse_env_assignment(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    return key.strip(), _normalize_env_value(value)


def _scrub_warning(env_name: str) -> str:
    return f"Environment file scrub skipped for {env_name}: source changed"


def _remove_env_keys(env_path: Path, migrated_values: Mapping[str, str]) -> list[str]:
    if not env_path.exists():
        return [_scrub_warning(env_name) for env_name in migrated_values]

    with env_path.open("r", encoding="utf-8", newline="") as env_file:
        snapshot = env_file.read()
    lines = snapshot.splitlines(keepends=True)
    effective: dict[str, tuple[int, str]] = {}
    for index, line in enumerate(lines):
        assignment = _parse_env_assignment(line)
        if assignment is not None and assignment[0] in migrated_values:
            effective[assignment[0]] = (index, assignment[1])

    remove_indices: set[int] = set()
    warnings: list[str] = []
    for env_name, verified_value in migrated_values.items():
        current = effective.get(env_name)
        if current is None or current[1] != verified_value:
            warnings.append(_scrub_warning(env_name))
        else:
            remove_indices.add(current[0])

    if not remove_indices:
        return warnings

    with env_path.open("r", encoding="utf-8", newline="") as env_file:
        if env_file.read() != snapshot:
            return [_scrub_warning(env_name) for env_name in migrated_values]

    retained = [line for index, line in enumerate(lines) if index not in remove_indices]
    with env_path.open("w", encoding="utf-8", newline="") as env_file:
        env_file.write("".join(retained))
    return warnings
