"""Credential storage and safe migration of API keys from ``.env`` files."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import re

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
        raise SecretStoreError(f"Credential store failed for {env_name}: {exc}") from exc


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
        if _get_password(service_name, username) != value:
            raise SecretStoreError(f"Credential verification failed for {env_name}")
    except SecretStoreError:
        raise
    except Exception as exc:
        raise SecretStoreError(f"Credential store failed for {env_name}: {exc}") from exc


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
        raise SecretStoreError(f"Credential store failed for {env_name}: {exc}") from exc


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
    migrated: list[str] = []
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
            migrated.append(env_name)

    if migrated:
        _remove_env_keys(Path(env_path), migrated)

    return SecretResolution(values, tuple(migrated), tuple(warnings))


def _remove_env_keys(env_path: Path, env_names: list[str]) -> None:
    if not env_path.exists():
        return

    key_pattern = "|".join(re.escape(name) for name in env_names)
    active_key = re.compile(rf"^[ \t]*(?:export[ \t]+)?(?:{key_pattern})[ \t]*=")
    with env_path.open("r", encoding="utf-8", newline="") as env_file:
        lines = env_file.read().splitlines(keepends=True)
    retained = [line for line in lines if not active_key.match(line)]
    with env_path.open("w", encoding="utf-8", newline="") as env_file:
        env_file.write("".join(retained))
