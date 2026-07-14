"""Guarded live checks for SpeedyType's keyring integration.

This script intentionally treats production credential usernames as read-only.
Its only writes and deletes use the fixed ``fallback_test_api_key`` username.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from speedytype.config import load_config
from speedytype.env_writer import test_gemini_key, test_minimax_key, test_openai_key
from speedytype.paths import default_env_path
from speedytype.secrets_store import (
    SECRET_KEY_NAMES,
    SERVICE_NAME,
    SecretResolution,
    SecretStoreError,
    delete_api_key,
    get_api_key,
    resolve_api_keys,
    set_api_key,
)


FALLBACK_ENV_NAME = "OPENAI_API_KEY"
FALLBACK_USERNAME = "fallback_test_api_key"
FALLBACK_VALUE = "speedytype-fake-not-a-real-key"
FALLBACK_KEY_NAMES = {FALLBACK_ENV_NAME: FALLBACK_USERNAME}


def _status(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def _delete_fallback(key_names: Mapping[str, str] = FALLBACK_KEY_NAMES) -> None:
    username = key_names[FALLBACK_ENV_NAME]
    if username != FALLBACK_USERNAME:
        raise RuntimeError("refusing to delete a non-test credential")
    current = get_api_key(
        FALLBACK_ENV_NAME,
        service_name=SERVICE_NAME,
        key_names=key_names,
    )
    if current is None:
        return
    if current != FALLBACK_VALUE:
        raise RuntimeError("refusing to delete an unexpected fallback credential value")
    delete_api_key(
        FALLBACK_ENV_NAME,
        service_name=SERVICE_NAME,
        key_names=key_names,
    )
    remaining = get_api_key(
        FALLBACK_ENV_NAME,
        service_name=SERVICE_NAME,
        key_names=key_names,
    )
    if remaining is not None:
        raise RuntimeError("fallback test credential is still present after delete")


def verify_isolated_fallback(temp_root: str | Path) -> bool:
    """Exercise migration fallback using only a fixed test credential."""
    root = Path(temp_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    env_path = (root / "keyring-fallback-test.env").resolve()
    if not env_path.is_relative_to(root):
        raise RuntimeError("fallback environment escaped temporary root")
    env_path.write_text(f"{FALLBACK_ENV_NAME}={FALLBACK_VALUE}\n", encoding="utf-8")

    passed = False
    cleanup_allowed = False
    try:
        existing = get_api_key(
            FALLBACK_ENV_NAME,
            service_name=SERVICE_NAME,
            key_names=FALLBACK_KEY_NAMES,
        )
        if existing not in (None, FALLBACK_VALUE):
            raise RuntimeError("fallback test username contains an unexpected value")
        cleanup_allowed = True
        if existing == FALLBACK_VALUE:
            _delete_fallback()

        set_api_key(
            FALLBACK_ENV_NAME,
            FALLBACK_VALUE,
            service_name=SERVICE_NAME,
            key_names=FALLBACK_KEY_NAMES,
        )
        stored = get_api_key(
            FALLBACK_ENV_NAME,
            service_name=SERVICE_NAME,
            key_names=FALLBACK_KEY_NAMES,
        )
        round_trip_ok = stored == FALLBACK_VALUE
        print(f"isolated keyring round-trip: {_status(round_trip_ok)}")

        _delete_fallback()
        resolution = resolve_api_keys(
            env_path,
            {FALLBACK_ENV_NAME: FALLBACK_VALUE},
            environment={},
            service_name=SERVICE_NAME,
            key_names=FALLBACK_KEY_NAMES,
        )
        fallback_ok = (
            resolution.values.get(FALLBACK_ENV_NAME) == FALLBACK_VALUE
            and FALLBACK_ENV_NAME in resolution.migrated
        )
        print(f"isolated .env fallback: {_status(fallback_ok)}")
        passed = round_trip_ok and fallback_ok
    finally:
        if cleanup_allowed:
            try:
                _delete_fallback()
            except (SecretStoreError, RuntimeError):
                passed = False
                print("isolated cleanup: FAIL")
            else:
                print("isolated cleanup: PASS")
        env_path.unlink(missing_ok=True)

    return passed


def run_live_verification(real_env_path: str | Path, fallback_root: str | Path) -> bool:
    """Run production read-only checks plus the isolated fallback exercise."""
    env_path = Path(real_env_path)
    temp_root = Path(fallback_root).resolve()
    settings_path = (temp_root / "settings.json").resolve()
    if not settings_path.is_relative_to(temp_root):
        raise RuntimeError("verifier settings path escaped temporary root")
    config = load_config(env_path, settings_path=settings_path)
    resolved_values = {
        "OPENAI_API_KEY": config.openai_api_key,
        "GEMINI_API_KEY": config.gemini_api_key,
        "MINIMAX_API_KEY": config.minimax_api_key,
    }

    checks_ok = True
    for env_name, username in SECRET_KEY_NAMES.items():
        stored = get_api_key(
            env_name,
            service_name=SERVICE_NAME,
            key_names=SECRET_KEY_NAMES,
        )
        exists = stored is not None
        matches = exists and stored == resolved_values[env_name]
        required = env_name != "MINIMAX_API_KEY" or bool(resolved_values[env_name])
        checks_ok = checks_ok and (not required or (exists and matches))
        print(
            f"production {env_name} ({username}): "
            f"exists={_status(exists)} matches_resolved={_status(matches)}"
        )

    provider_checks = (
        ("OpenAI", test_openai_key, resolved_values["OPENAI_API_KEY"]),
        ("Gemini", test_gemini_key, resolved_values["GEMINI_API_KEY"]),
        ("MiniMax", test_minimax_key, resolved_values["MINIMAX_API_KEY"]),
    )
    for provider, check, value in provider_checks:
        if provider == "MiniMax" and not value:
            continue
        try:
            passed, _message = check(value)
        except Exception:
            passed = False
        checks_ok = checks_ok and passed
        print(f"provider {provider}: {_status(passed)}")

    return verify_isolated_fallback(fallback_root) and checks_ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify SpeedyType keyring integration.")
    parser.add_argument(
        "--env",
        type=Path,
        default=default_env_path(),
        help="Environment file to migrate/read (default: app data .env).",
    )
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="speedytype-keyring-live-") as temp_root:
        passed = run_live_verification(args.env, temp_root)
    print(f"live keyring verification: {_status(passed)}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
