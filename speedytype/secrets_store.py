from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Mapping

from keyring import delete_password as _delete_password
from keyring import get_password as _get_password
from keyring import set_password as _set_password
from keyring.errors import PasswordDeleteError


SERVICE_NAME = "SpeedyType"
SECRET_KEY_NAMES = {
    "OPENAI_API_KEY": "openai_api_key",
    "GEMINI_API_KEY": "gemini_api_key",
    "MINIMAX_API_KEY": "minimax_api_key",
}


class SecretStoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class SecretResolution:
    values: dict[str, str]
    migrated: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _username(env_name: str, key_names: Mapping[str, str]) -> str:
    try:
        return key_names[env_name]
    except KeyError as exc:
        raise SecretStoreError(f"Unknown credential name: {env_name}") from exc


def get_api_key(
    env_name: str,
    *,
    service_name: str = SERVICE_NAME,
    key_names: Mapping[str, str] = SECRET_KEY_NAMES,
) -> str:
    username = _username(env_name, key_names)
    try:
        return _get_password(service_name, username) or ""
    except Exception as exc:
        raise SecretStoreError(f"Credential store read failed for {env_name}: {exc}") from exc


def set_api_key(
    env_name: str,
    value: str,
    *,
    service_name: str = SERVICE_NAME,
    key_names: Mapping[str, str] = SECRET_KEY_NAMES,
) -> None:
    username = _username(env_name, key_names)
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
    username = _username(env_name, key_names)
    try:
        try:
            _delete_password(service_name, username)
        except PasswordDeleteError as exc:
            if _get_password(service_name, username) is None:
                return
            raise SecretStoreError(
                f"Credential deletion failed for {env_name}: backend refused deletion"
            ) from exc
        if _get_password(service_name, username) is not None:
            raise SecretStoreError(f"Credential deletion verification failed for {env_name}")
    except SecretStoreError:
        raise
    except Exception as exc:
        raise SecretStoreError(f"Credential deletion failed for {env_name}: {exc}") from exc


def _remove_env_keys(path: Path, env_names: tuple[str, ...]) -> None:
    if not env_names or not path.exists():
        return

    pattern = re.compile(
        rf"^\s*(?:export\s+)?(?:{'|'.join(re.escape(name) for name in env_names)})\s*="
    )
    with path.open("r", encoding="utf-8", newline="") as handle:
        original = handle.read()
    updated = "".join(
        line for line in original.splitlines(keepends=True) if not pattern.match(line)
    )
    if updated == original:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(updated)


def resolve_api_keys(
    env_path: str | Path,
    file_values: Mapping[str, str | None],
    environment: Mapping[str, str] | None = None,
    *,
    service_name: str = SERVICE_NAME,
    key_names: Mapping[str, str] = SECRET_KEY_NAMES,
) -> SecretResolution:
    environment = os.environ if environment is None else environment
    values: dict[str, str] = {}
    migrated: list[str] = []
    warnings: list[str] = []

    for env_name in key_names:
        try:
            stored = get_api_key(
                env_name,
                service_name=service_name,
                key_names=key_names,
            )
        except SecretStoreError as exc:
            stored = ""
            warnings.append(str(exc))

        if stored:
            values[env_name] = stored
            continue

        environment_value = environment.get(env_name, "")
        if environment_value:
            values[env_name] = environment_value
            continue

        file_value = file_values.get(env_name) or ""
        if not file_value:
            continue

        values[env_name] = file_value
        try:
            set_api_key(
                env_name,
                file_value,
                service_name=service_name,
                key_names=key_names,
            )
        except SecretStoreError as exc:
            warnings.append(str(exc))
        else:
            migrated.append(env_name)

    migrated_tuple = tuple(migrated)
    if migrated_tuple:
        try:
            _remove_env_keys(Path(env_path), migrated_tuple)
        except OSError as exc:
            warnings.append(f"Credential source cleanup failed: {exc}")

    return SecretResolution(values, migrated_tuple, tuple(warnings))
